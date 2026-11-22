# Search sensitive fields: kiểm soát tìm kiếm trên trường nhạy cảm

Trong chương **Search Rules**, bảo vệ trường nhạy cảm không chỉ là bỏ chúng khỏi JSON phản hồi. Nếu một trường vẫn được dùng để khớp từ khóa, lọc, sắp xếp hoặc tạo gợi ý, người gọi có thể suy ra thông tin dù không bao giờ nhận nguyên giá trị của trường đó.

Trong module bảo vệ logic nghiệp vụ, tìm kiếm cần giữ quyền theo đối tượng, tenant, trường và mục đích nghiệp vụ. Một kết quả tìm thấy không tự chứng minh caller được sửa tài khoản nhận tiền, xác nhận danh tính hay thực hiện bước tiếp theo trên đối tượng.

Bài học dùng ví dụ tìm nhà cung cấp. Nhân sự mua hàng được tìm theo tên và mã hiển thị trong phạm vi được giao; tra cứu theo tài khoản nhận tiền hoặc dữ liệu điều tra có chính sách và luồng riêng.

Sau bài này, bạn có thể:

- Phân biệt quyền đọc trường với quyền dùng trường làm điều kiện tìm kiếm.
- Nhận diện rò rỉ qua hit, count, sort, ranking, highlight và suggestion.
- Thiết kế một API tìm kiếm thông thường có tập trường cho phép rõ ràng.
- Thiết kế tra cứu nhạy cảm có phạm vi, mục đích và giới hạn phù hợp.
- Kiểm thử chỉ mục, cache và metadata không mở một đường đọc ngoài quyền.

## 1. Không trả trường vẫn có thể làm lộ thông tin của trường

Giả sử response chỉ có:

```json
{
  "items": [
    {
      "id": "supplier-17",
      "displayCode": "SUP-017",
      "displayName": "Nhà cung cấp thử nghiệm"
    }
  ],
  "totalCount": 1
}
```

Caller gửi:

```http
GET /suppliers?bankAccountNumber=000012340000
```

Nếu API dùng tham số đó để tìm trên số tài khoản, sự xuất hiện của nhà cung cấp đã xác nhận một quan hệ giữa đối tượng và giá trị được hỏi. Việc bỏ `bankAccountNumber` khỏi response không xóa thông tin mà phép khớp đã tiết lộ.

Tương tự, một từ chỉ xuất hiện trong ghi chú điều tra có thể làm nhà cung cấp trở thành hit của tìm kiếm toàn văn. Caller biết đối tượng có liên quan tới từ đó dù ghi chú không được trả về.

Cần hỏi:

> Caller được phép sử dụng thuộc tính nào để khám phá, xác nhận hoặc suy luận thông tin về những đối tượng trong tập tìm kiếm?

Đây là một quyết định phân quyền riêng, không chỉ là cấu hình serializer.

## 2. Tách các quyền liên quan tới một trường

| Loại quyền | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Đọc giá trị | Có được nhận nội dung trường không? | Đọc đầy đủ tài khoản nhận tiền |
| Tìm khớp | Có được hỏi đối tượng nào mang giá trị này không? | Tra cứu chính xác một tài khoản |
| Lọc theo khoảng hoặc điều kiện | Có được dùng trường để thu hẹp tập không? | Lọc điểm rủi ro lớn hơn một ngưỡng |
| Sắp xếp hoặc xếp hạng | Có được để trường ảnh hưởng thứ tự không? | Sort theo điểm rủi ro nội bộ |
| Tổng hợp | Có được đếm, nhóm hoặc thống kê theo trường không? | Đếm nhà cung cấp theo trạng thái điều tra |
| Gợi ý hoặc trích đoạn | Có được đưa giá trị hoặc từ của trường vào tính năng phụ không? | Autocomplete hoặc highlight từ ghi chú |

Một người được đọc một giá trị khi mở hồ sơ cụ thể chưa chắc được phép dùng nó để tra cứu ngược trên toàn bộ tổ chức. Quyền khám phá tập đối tượng có thể rộng hơn quyền xem từng hồ sơ đã được cấp trước.

Ngược lại, một nghiệp vụ có thể cho tra cứu chính xác và chỉ trả kết quả tối thiểu, không trả giá trị đầy đủ. Điều đó phải được định nghĩa có chủ đích cùng phạm vi, mục đích và giới hạn sử dụng.

Không suy tất cả các quyền trên từ một cờ `canViewSupplier` hoặc role nhân viên chung.

## 3. Phân loại dữ liệu và nhu cầu tìm kiếm

Với nhà cung cấp, chính sách minh họa có thể là:

| Trường | Tìm kiếm thông thường | Luồng nhạy cảm |
| --- | --- | --- |
| `displayCode` | Theo hợp đồng, trong tenant và phạm vi được phép | Không cần quyền bổ sung chỉ vì là mã |
| `displayName` | Tìm văn bản theo cơ chế được hỗ trợ | Vẫn là dữ liệu có scope, không mặc định công khai |
| `status` | Bộ lọc trạng thái được cho phép | Không dùng để suy ra một trạng thái điều tra nội bộ không được đọc |
| `contactEmail` | Chỉ nếu chính sách nghiệp vụ cho phép | Có thể cần quy tắc riêng về kiểu khớp và phạm vi |
| `bankAccountNumber` | Không tham gia tìm kiếm chung | Tra cứu chính xác trong nghiệp vụ được cấp quyền |
| `taxIdentifier` | Không tự động đưa vào mọi query | Theo quyền và mục đích cụ thể |
| `internalRiskScore` | Không cho caller thường lọc hoặc sort | Phân tích theo quyền chuyên biệt |
| `investigationNote` | Không tham gia từ khóa, gợi ý hoặc highlight chung | Luồng điều tra có kiểm soát nếu sản phẩm hỗ trợ |

Phân loại phải bao gồm trường lồng nhau, alias và dữ liệu dẫn xuất. Một field `searchText` ghép tên, email, tài khoản và ghi chú vẫn có thể làm lộ dữ liệu nhạy cảm dù API không nhận các tên trường gốc.

Không coi mọi dữ liệu có trong chỉ mục là được phép dùng cho mọi người. Chỉ mục phục vụ truy vấn, không tự định nghĩa chính sách truy cập.

## 4. Tập đối tượng được phép phải bao quanh mọi điều kiện tìm kiếm

Tìm kiếm thông thường cần giữ quan hệ:

```text
kết quả = đối tượng trong tenant và phạm vi được phép
          giao với điều kiện tìm trên các trường được phép
```

Không dùng từ khóa để chọn dữ liệu toàn cục rồi mới cố bỏ các hit ngoài quyền. Cách đó dễ làm count, ranking hoặc suggestion phản ánh dữ liệu đã bị loại ở bước sau.

SQL minh họa khi người gọi được tìm trên cả tên và mã:

```sql
SELECT id, display_code, display_name, status
FROM supplier
WHERE tenant_id = :authorized_tenant_id
  AND department_id IN (:authorized_department_ids)
  AND (
       display_name LIKE :literal_pattern ESCAPE '!'
       OR display_code LIKE :literal_pattern ESCAPE '!'
  )
ORDER BY display_name, id
LIMIT :validated_limit;
```

Cú pháp và cơ chế so sánh văn bản cần phù hợp hệ quản trị. Giá trị được bind; pattern được tạo theo hợp đồng tìm ký tự thông thường, xử lý các ký tự wildcard nếu chúng không được caller điều khiển.

Prepared statement ngăn trộn dữ liệu vào cú pháp SQL nhưng không tự giới hạn trường, tenant hoặc ý nghĩa wildcard. Tên field và sort cũng phải được ánh xạ từ lựa chọn cho phép, không nối raw input thành cấu trúc query.

Tập bộ phận rỗng phải cho kết quả rỗng hoặc lỗi quyền phù hợp, không làm mất điều kiện phạm vi.

## 5. API tìm kiếm chung cần schema hẹp

Ví dụ:

```http
POST /suppliers/search
Content-Type: application/json

{
  "query": "thiết bị",
  "searchFields": ["DISPLAY_NAME", "DISPLAY_CODE"],
  "matchMode": "TEXT",
  "limit": 20
}
```

`searchFields` là đề xuất của caller, không phải danh sách mà engine phải tin ngay. Trong hợp đồng ví dụ, chỉ hai trường trên được dùng ở luồng tìm kiếm chung; trường khác bị từ chối trước khi query được thực thi.

Các điểm cần quy định:

- Không nhận wildcard tên field như `*` nếu chưa có một hợp đồng an toàn cho nó.
- Không nhận raw query language hoặc một graph điều kiện tùy ý chỉ vì backend hỗ trợ.
- Phân biệt tập trường được tìm với tập trường được trả về.
- Field bỏ trống có default máy chủ rõ ràng; tập field được gửi rỗng không tự trở thành tìm mọi trường.
- Giới hạn query, page size, sort, filter và chi phí mở rộng phù hợp.

Một lỗi cần tránh là loại bỏ tất cả field không được phép, thấy danh sách còn rỗng rồi fallback sang cơ chế tìm mọi field của engine. Request bị cấm đã trở thành query rộng nhất.

Chọn POST có thể giúp tránh đặt một giá trị nhạy cảm trong URL, nhưng không tự tạo bảo mật: body vẫn có thể bị proxy, tracing hoặc ứng dụng ghi lại. Quyền và cấu hình ghi log vẫn phải được xử lý riêng.

## 6. Minh họa Java: tạo kế hoạch tìm kiếm chung có kiểm soát

Đoạn mã dùng record của Java 16 trở lên. `VerifiedSearchScope` được tạo từ danh tính, membership và policy máy chủ; không bind từ body. Đây là kế hoạch tìm kiếm thông thường, không phải API cho mọi loại tra cứu.

```java
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

enum SupplierSearchField {
    DISPLAY_NAME,
    DISPLAY_CODE,
    CONTACT_EMAIL,
    BANK_ACCOUNT_NUMBER,
    TAX_IDENTIFIER,
    INVESTIGATION_NOTE
}

enum MatchMode {
    TEXT, EXACT, PREFIX, FUZZY
}

record GeneralSearchInput(
        String query,
        Set<SupplierSearchField> searchFields,
        MatchMode matchMode,
        int limit) {
}

record VerifiedSearchScope(
        UUID tenantId,
        UUID principalId,
        Set<UUID> departmentIds,
        boolean maySearchSuppliers) {
}

record GeneralSearchPlan(
        UUID tenantId,
        UUID principalId,
        Set<UUID> departmentIds,
        String literalQuery,
        Set<SupplierSearchField> searchFields,
        int limit,
        boolean matchNone) {
}

final class SupplierSearchPolicy {
    private static final Set<SupplierSearchField> GENERAL_FIELDS = Set.of(
            SupplierSearchField.DISPLAY_NAME,
            SupplierSearchField.DISPLAY_CODE);

    private SupplierSearchPolicy() {
    }

    static GeneralSearchPlan planGeneral(
            VerifiedSearchScope scope, GeneralSearchInput input) {
        Objects.requireNonNull(scope);
        Objects.requireNonNull(input);
        require(scope.maySearchSuppliers(), "SEARCH_NOT_ALLOWED");

        UUID tenant = Objects.requireNonNull(scope.tenantId());
        UUID principal = Objects.requireNonNull(scope.principalId());
        Set<UUID> departments = Set.copyOf(scope.departmentIds());
        Set<SupplierSearchField> fields = Set.copyOf(input.searchFields());
        String query = Objects.requireNonNull(input.query()).strip();

        require(!query.isEmpty() && query.length() <= 120,
                "INVALID_QUERY_LENGTH");
        require(input.limit() >= 1 && input.limit() <= 50,
                "INVALID_SEARCH_LIMIT");
        require(input.matchMode() == MatchMode.TEXT,
                "UNSUPPORTED_GENERAL_MATCH_MODE");
        require(!fields.isEmpty() && GENERAL_FIELDS.containsAll(fields),
                "SEARCH_FIELD_NOT_ALLOWED");

        return new GeneralSearchPlan(tenant, principal, departments,
                query, fields, input.limit(), departments.isEmpty());
    }

    private static void require(boolean valid, String code) {
        if (!valid) {
            throw new SecurityException(code);
        }
    }
}
```

Các giới hạn ký tự và số mục là ví dụ của hợp đồng, không chứng minh query luôn rẻ. Executor chỉ ánh xạ những field đã được duyệt sang các cấu trúc query cố định và phải trả rỗng khi `matchNone` là true.

`literalQuery` là văn bản cần tìm theo hợp đồng, không tự trở thành cú pháp cho engine. Một chuỗi giống `bankAccountNumber:...` không được phép làm đổi tập field nếu API không hỗ trợ ngôn ngữ đó.

Ví dụ chưa cấu hình parser JSON, xử lý wildcard, collation, phân trang hoặc rate limit. Chúng cần được triển khai và kiểm thử ở các lớp tương ứng. Tên record không ngăn việc dùng sai nếu controller cho client tự tạo `VerifiedSearchScope` hoặc executor bỏ các điều kiện trong plan.

## 7. Full-text index không được tự mở rộng phạm vi trường

Một engine có thể hỗ trợ tìm trên nhiều trường, field mặc định hoặc một nội dung tổng hợp. Khi thêm dữ liệu mới vào index, cần xem nó có vô tình tham gia truy vấn chung hay không.

Ví dụ `searchText` được tạo từ:

```text
displayName + displayCode + bankAccountNumber + investigationNote
```

Dù response chỉ lấy tên và mã, một query trúng phần ghi chú vẫn làm lộ quan hệ giữa nhà cung cấp và từ khóa. Loại field khỏi phần dữ liệu trả về không tự loại ảnh hưởng của nó lên matching.

Các điểm cần rà soát:

- Field mặc định mà query thực sự tìm.
- Alias, field dẫn xuất hoặc nội dung được gộp từ nguồn khác.
- Các nhánh nested hoặc quan hệ được tìm mở rộng.
- Cấu hình highlight và đoạn trích.
- Scoring, boost và explain có dùng dữ liệu nhạy cảm không.
- Quy trình thêm field hoặc dựng lại index.

Không dùng quy tắc tên gần đúng như “field bắt đầu bằng display thì được tìm” nếu nó có thể bao gồm cấu trúc riêng tư mới. Dùng định danh ngữ nghĩa và mapping máy chủ được kiểm soát.

Nếu một luồng không cần tìm trên dữ liệu nhạy cảm, không đưa dữ liệu đó vào đường truy vấn của luồng chỉ để tiện cấu hình.

## 8. Count, sort và ranking cũng là kênh quan sát

Caller có thể không cần nhìn giá trị đầy đủ để suy ra một thuộc tính:

- Có hay không có hit cho một điều kiện đã chọn.
- Count thay đổi khi đổi ngưỡng lọc.
- Thứ tự nhà cung cấp khi sort theo điểm nội bộ.
- Score hoặc explain cho thấy một từ khớp trường điều tra.
- Facet hoặc nhóm thống kê cho biết trạng thái nhạy cảm tồn tại.

Nếu người dùng không được dùng `internalRiskScore`, việc ẩn nó trong source nhưng cho phép range filter hoặc sort vẫn có thể làm lộ thông tin.

Ranking cũng cần đánh giá. Một thuật toán có thể dùng tín hiệu nội bộ cho mục đích được phê duyệt, nhưng không nên coi thứ tự và score là metadata vô hại mặc định. Phải xem caller có thể quan sát và điều khiển query đến mức nào.

Không dùng việc ẩn các count nhỏ làm thay thế cho quyền sử dụng field. Nhiều truy vấn gần nhau có thể tiếp tục tiết lộ quan hệ hoặc khác biệt giữa các nhóm.

Nếu không thể tính một metadata theo đúng phạm vi được phép, hợp đồng cần xử lý phù hợp, chẳng hạn không cung cấp metadata đó. Không trả số liệu toàn cục đi kèm một danh sách hits đã được lọc rồi kết luận quyền đã được giữ.

## 9. Suggestion, autocomplete và lịch sử query cần chính sách riêng

Các tính năng phụ thường có nguồn dữ liệu khác với hits:

| Tính năng | Nguồn có thể làm lộ thông tin |
| --- | --- |
| Autocomplete | Giá trị của field nhạy cảm hoặc dữ liệu tenant khác |
| Sửa lỗi chính tả | Từ trong ghi chú nội bộ hoặc từ điển xây từ toàn bộ index |
| Truy vấn phổ biến | Lịch sử người có quyền tra cứu nhạy cảm |
| Highlight | Đoạn văn từ field không được phép đọc |
| Tìm kiếm liên quan | Quan hệ hoặc nhóm đối tượng ngoài scope |

Ví dụ nhân sự tài chính từng nhập một số tài khoản để đối soát. Nếu chuỗi đó được đưa vào gợi ý chung cho mọi nhân viên, dữ liệu bị lộ ngay cả khi endpoint lookup gốc được phân quyền đúng.

Scope cần đi cùng dữ liệu gợi ý và cache của nó. Không chỉ lọc hits theo tenant rồi dùng một từ điển hoặc danh sách query phổ biến toàn hệ thống.

Kiểm thử cả trường hợp không có hit nhưng vẫn có suggestion hoặc highlight. Dữ liệu phụ không được dùng như một đường đọc thay thế cho field đã bị chặn.

## 10. Tra cứu nhạy cảm cần một hành động có mục đích rõ ràng

Nếu nghiệp vụ cần tra theo tài khoản nhận tiền, có thể thiết kế endpoint chuyên biệt:

```http
POST /suppliers/bank-account-lookups
Content-Type: application/json

{
  "bankId": "bank-test-1",
  "accountNumber": "000012340000",
  "purposeCode": "PAYMENT_RECONCILIATION",
  "caseId": "case-17",
  "limit": 10
}
```

Các giá trị trên là dữ liệu thử nghiệm. Endpoint cần kiểm tra:

- Actor có quyền lookup tương ứng trên tenant và phạm vi đối tượng.
- Case hoặc công việc liên quan tồn tại, còn phù hợp và actor được phép xử lý.
- Mục đích được chấp nhận cho hành động, không chỉ là một chuỗi đúng enum.
- Kiểu khớp và giới hạn được policy cho phép.
- Nguồn dữ liệu, chuẩn hóa và tham chiếu ngân hàng đúng ý nghĩa.
- Quota, audit và response tối thiểu phù hợp.

`purposeCode` không tự cấp quyền. Nếu chỉ cần gửi `purpose=investigation` là có thể tìm mọi dữ liệu, hệ thống đang để caller tự chọn mức truy cập.

Theo ví dụ, lookup dùng khớp chính xác một khóa đã chuẩn hóa, không cung cấp wildcard, prefix hay autocomplete. Nếu sản phẩm cần tìm một phần, phải có chính sách riêng về phạm vi và rủi ro suy luận, không tự mở từ quyền exact lookup.

## 11. Chuẩn hóa, che dữ liệu và bảo vệ chỉ mục

Giá trị nhận dạng cần được giữ đúng ngữ nghĩa. Không chuyển mọi số tài khoản thành số nguyên và làm mất số 0 đầu. Không mặc định cùng chuỗi ở hai ngân hàng hoặc hệ định danh là cùng một đối tượng.

Chuẩn hóa phải theo loại dữ liệu và nguồn phát hành. Các trường hợp có chữ cái, dấu phân cách hoặc quy tắc khác nhau cần hợp đồng rõ; không dùng một phép xóa ký tự tùy ý cho mọi quốc gia hay hệ thống.

Che phần lớn giá trị trong response giúp giảm dữ liệu trả về, nhưng không xóa thông tin mà một phép tra cứu đã xác nhận. Bốn ký tự cuối cũng không phải một định danh duy nhất hoặc bằng chứng caller sở hữu tài khoản.

Mã hóa dữ liệu lưu trữ bảo vệ một phạm vi rủi ro khác với quyền tìm kiếm. Nếu ứng dụng được phép giải mã hoặc query chỉ mục dẫn xuất, nó vẫn phải kiểm tra ai được sử dụng khả năng đó.

Nếu dùng cơ chế index để tra cứu giá trị được bảo vệ, cần thiết kế và đánh giá bảo mật phù hợp cho đúng nhu cầu. Một hash thông thường không tự làm giá trị dễ đoán hoặc quan hệ bằng nhau trở nên vô hại; index, metadata và quyền truy cập vẫn cần bảo vệ.

Không tự thêm token tìm prefix hoặc dữ liệu dẫn xuất từ bí mật mà chưa đánh giá phần thông tin chúng tiết lộ. Tiện ích tìm kiếm và mức thông tin được bộc lộ là các quyết định phải đi cùng nhau.

## 12. Quyền thay đổi và chỉ mục cập nhật trễ

Search index có thể là một bản chiếu cập nhật sau dữ liệu nguồn. Nhà cung cấp đổi bộ phận, tài liệu bị hạn chế hoặc membership bị thu hồi có thể chưa được phản ánh ngay.

Các câu hỏi cần xác định:

- Quyền được kiểm tra theo dữ liệu nào và tại thời điểm nào?
- ACL hoặc security label trong index có hiệu lực tới đâu?
- Cơ chế cache, epoch hoặc sự kiện thu hồi đáp ứng cam kết nào?
- Count, facet và suggestion có cùng ranh giới quyền với hits không?

Tải lại hits từ database rồi lọc quyền có thể giúp chặn việc trả một số bản ghi, nhưng không tự sửa count, score hoặc gợi ý đã được tính từ tập có dữ liệu cũ ngoài quyền.

Thiết kế phải chọn cách kết hợp nguồn và kiểm tra đáp ứng hợp đồng hiệu lực. Không tuyên bố thu hồi tại mọi điểm chỉ vì một endpoint chi tiết đã chặn trong khi search vẫn trả dấu vết của đối tượng.

Nếu một dữ liệu bắt buộc để xác lập quyền không khả dụng, không mặc định tìm toàn bộ index. Có thể từ chối hoặc giữ kết quả trong phạm vi được bảo đảm theo hợp đồng, nhưng không âm thầm bỏ điều kiện bảo mật.

## 13. Giới hạn sử dụng và chi phí là lớp bổ sung

Một lookup exact có page size bằng 1 vẫn có thể bị gọi nhiều lần để xác nhận nhiều giá trị. Ngược lại, một từ khóa bình thường có thể gây truy vấn đắt nếu cho phép fuzzy, wildcard hoặc nhiều field mở rộng không giới hạn.

Có thể cần:

- Giới hạn tần suất theo actor, tenant, mục đích hoặc nhóm hành động.
- Trần công việc đang chạy và phạm vi dữ liệu được tra cứu.
- Giới hạn query, số field, filter, page size và result window.
- Quota lookup nhạy cảm được lưu ở cấp phù hợp, không chỉ mỗi session.
- Theo dõi nhiều truy vấn tương tự hoặc liên tiếp trên một tập định danh.

Các trần cần từ policy máy chủ. Client không tự tăng quyền hoặc quota bằng `trustedClient`, số dòng tự khai hay một case mới tạo không có căn cứ phù hợp.

Giới hạn tối thiểu độ dài query, masking hoặc rate limit không thay thế việc cấm sử dụng field ngoài quyền. Nếu query không được phép về ý nghĩa, cho nó chạy chậm hơn vẫn chưa giải quyết rò rỉ.

Với nhiều instance, việc kiểm tra và tiêu thụ quota cần cơ chế nhất quán tương ứng. Retry hoặc đổi thiết bị không được tự đặt lại một giới hạn được định nghĩa theo actor hoặc tenant.

## 14. Cache, URL, log và tracing có thể giữ lại giá trị nhạy cảm

Một search request chứa số tài khoản hoặc định danh cá nhân có thể xuất hiện trong URL, access log, trace, báo cáo lỗi hoặc lịch sử giao diện.

Thiết kế cần xác định:

- Kênh truyền và nơi nào có thể ghi request.
- Trường nào bị loại hoặc che trong log và telemetry.
- Ai được xem lịch sử lookup và kết quả.
- Cache có lưu query hoặc response không, theo scope nào.
- Chính sách lưu và xóa dữ liệu tìm kiếm phù hợp với nhu cầu hệ thống.

Không cho cache chỉ có key là chuỗi query dùng chung cho các tenant, actor hoặc loại hành động. Kết quả lookup đặc quyền không được trả từ cache cho tìm kiếm chung chỉ vì cùng giá trị query.

Fingerprint query có thể hỗ trợ đối chiếu hoặc thống kê, nhưng vẫn có thể tiết lộ việc nhiều request dùng cùng giá trị hoặc một giá trị dễ đoán. Không mặc định mọi dạng hash đều là metadata công khai an toàn.

Lỗi không nên trả raw query nội bộ, source đầy đủ hoặc chi tiết một hồ sơ ngoài quyền. Audit có thể ghi loại field, purpose, actor, scope và định danh công việc mà không cần ghi nguyên bí mật đã tìm.

## 15. Kết quả tìm thấy không phải bằng chứng sở hữu hoặc quyền thay đổi

Giả sử lookup tìm được một nhà cung cấp mang tài khoản được hỏi. Điều đó không chứng minh người hỏi sở hữu tài khoản hoặc có quyền sửa tài khoản nhận tiền trên một đơn.

Hành động tiếp theo vẫn cần:

```text
quyền hành động trên đúng đối tượng
tenant và quan hệ tương thích
trạng thái, version và snapshot phù hợp
bằng chứng xác minh hoặc phê duyệt theo policy
transaction và chống thực hiện trùng nếu có hiệu ứng
```

Không tự đặt `bankVerified=true` chỉ vì một giá trị khớp kết quả tìm kiếm. Xác minh là một quy trình có nguồn bằng chứng riêng.

Nếu client chọn supplier từ một kết quả cũ, command tạo hoặc sửa đơn phải kiểm tra lại quyền và quan hệ tại ranh giới áp dụng. Việc một ID từng xuất hiện trên trang không tạo quyền sử dụng vĩnh viễn.

API cũ, import, mobile và worker cần giữ cùng ranh giới này. Không để một đường hỗ trợ raw field hoặc query nội bộ đi vòng policy đã áp dụng ở màn hình tìm kiếm mới.

## 16. Ma trận kiểm thử tìm kiếm nhạy cảm

Chuẩn bị fixture trong đó một marker chỉ xuất hiện ở ghi chú điều tra, một giá trị chỉ xuất hiện ở tài khoản và các marker riêng cho tenant khác. Tạo ca đối chứng tìm theo tên hoặc mã hợp lệ để chứng minh index và route đã sẵn sàng.

| Ca kiểm thử | Kết quả cần giữ |
| --- | --- |
| Tìm tên hoặc mã được phép trong scope | Trả đúng đối tượng và trường hợp lệ |
| Từ khóa chỉ có trong ghi chú nội bộ | Tìm kiếm chung không làm lộ hit hoặc metadata của ghi chú |
| Yêu cầu field tài khoản, định danh hoặc điều tra ở route chung | Không query ngoài tập được phép |
| Gửi alias, field lồng nhau hoặc wildcard tên field | Không mở đường khác tới cùng thuộc tính nhạy cảm |
| Lọc hoặc sort theo điểm rủi ro không được phép | Không tạo kênh suy luận qua tập hoặc thứ tự |
| Không có hit nhưng engine có suggestion nhạy cảm | Không trả gợi ý, trích đoạn hoặc từ nội bộ ngoài quyền |
| Query đúng dữ liệu B từ scope A | Không trả hit, count hoặc dấu vết ngoài phạm vi |
| Tập bộ phận được phép rỗng | Không trở thành tìm toàn tenant |
| Nhân sự đủ quyền lookup exact với case hợp lệ | Có ca thành công trong đúng phạm vi |
| Cùng actor tự khai purpose khác để xin quyền rộng | Purpose không thay quyền và điều kiện case |
| Dùng prefix hoặc wildcard ở luồng chỉ cho exact | Không mở rộng kiểu khớp |
| Chỉ có quyền đọc một trường trên hồ sơ cụ thể | Không tự có quyền tra ngược toàn bộ hệ thống |

Kiểm tra JSON thực tế, count, thứ tự, score nếu được trả, facet, highlight và suggestion. Chỉ tìm canary trong trường `items` sẽ bỏ sót nhiều đường rò rỉ.

Expected cần từ bảng quyền và dữ liệu fixture độc lập, không chỉ dựa vào production query builder. Marker không được vô tình xuất hiện trong field được phép, nếu không test sẽ khó xác định nguồn khớp.

## 17. Kiểm thử cache, hiệu lực quyền và các hiệu ứng sau lookup

Các lịch tích hợp quan trọng:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| User đặc quyền lookup trước, user thường query sau | Cache không trả response hoặc metadata đặc quyền |
| Tenant A làm nóng cache rồi tenant B tìm cùng giá trị | Không dùng nhầm scope |
| Quyền bị thu hồi nhưng index hoặc token cũ còn tồn tại | Hành vi đúng cam kết hiệu lực tại search và metadata |
| Nhà cung cấp đổi bộ phận hoặc giới hạn truy cập | Hits và dữ liệu phụ không tiếp tục dùng phạm vi cũ ngoài hợp đồng |
| Reindex hoặc thêm field mới | Không tự đưa field nhạy cảm vào tìm kiếm chung |
| Lookup được retry hoặc gửi qua nhiều session | Quota cấp actor hoặc tenant không bị đặt lại ngoài policy |
| Kết quả cũ được dùng để đổi tài khoản nhận tiền | Command vẫn kiểm tra quyền, version và phê duyệt riêng |
| Log hoặc error trace được tạo khi query bị chặn | Không lưu hoặc tiết lộ nguyên dữ liệu nhạy cảm ngoài nhu cầu |
| Worker hoặc báo cáo dùng cùng index | Không bỏ policy vì có credential kỹ thuật rộng |

Với index cập nhật trễ, chờ điều kiện sẵn sàng có giới hạn theo hợp đồng thay vì một khoảng sleep tùy ý. Tách test dữ liệu ổn định với test thay đổi quyền để oracle không lẫn hai ngữ nghĩa.

Search thường là thao tác đọc, nên không được tạo quyết định xác minh, đổi chủ hoặc operation thanh toán chỉ vì query khớp. Log truy cập hoặc bộ đếm quota có thể thay đổi theo thiết kế; cần phân biệt chúng với hiệu ứng nghiệp vụ bị cấm.

Audit nên nối được actor, tenant đã xác minh, loại lookup, nhóm field, purpose và case, policy hoặc version liên quan, kết quả được phép cùng mã tương quan. Không dùng toàn bộ giá trị tìm kiếm như cách duy nhất để giải thích quyết định.

## 18. Cách bảo vệ tìm kiếm trên trường nhạy cảm

1. Phân loại field theo quyền đọc, tìm khớp, filter, sort, aggregate và gợi ý.
2. Định nghĩa tập đối tượng được phép theo tenant và quan hệ trước khi áp dụng query.
3. Tạo schema và mapping field rõ cho tìm kiếm chung, không dùng raw DSL hoặc fallback tìm mọi field.
4. Kiểm tra cả index, field dẫn xuất, ranking, count, highlight và suggestion.
5. Tách lookup nhạy cảm thành hành động có quyền, mục đích, kiểu khớp và response tối thiểu phù hợp.
6. Chuẩn hóa định danh đúng ngữ nghĩa và bảo vệ dữ liệu cùng chỉ mục dẫn xuất.
7. Xác định hiệu lực quyền khi cache hoặc index trễ, không chỉ lọc lại hits rồi bỏ qua metadata.
8. Giới hạn việc sử dụng, chi phí và dữ liệu lưu trong log hoặc cache.
9. Kiểm thử suy luận qua kết quả cùng các command dùng kết quả tìm kiếm về sau.

Một trường được bảo vệ khi hệ thống kiểm soát cả việc trả giá trị lẫn những cách dùng giá trị đó để khám phá thông tin. Scope đúng, quyền sử dụng field rõ và các kênh phụ được kiểm thử giúp tìm kiếm phục vụ công việc mà không trở thành đường đọc dữ liệu nhạy cảm ngoài thẩm quyền.

# Stable sort requirement: yêu cầu thứ tự xác định trong truy vấn nghiệp vụ

Trong chương **Sorting Rules**, stable sort requirement là yêu cầu hệ thống xác định rõ thứ tự của các bản ghi, kể cả khi những giá trị sắp xếp chính bằng nhau. Yêu cầu này đặc biệt quan trọng với phân trang, hàng đợi xử lý, đối soát và các màn hình chọn đối tượng để duyệt hoặc thực hiện hàng loạt.

Trong module bảo vệ logic nghiệp vụ, thứ tự không rõ ràng có thể làm người dùng thấy trùng hoặc bỏ sót đối tượng, khiến cursor đi sai vị trí hoặc làm một tiến trình chọn nhầm mục để xử lý. Thứ tự xác định cần kết hợp với quyền theo đối tượng, snapshot, version, transaction và idempotency; nó không tự thay thế những cơ chế đó.

Bài học dùng ví dụ danh sách đề nghị chi đang chờ duyệt, có thời điểm gửi và mức ưu tiên. Các sort profile là hợp đồng minh họa, cần điều chỉnh theo mô hình dữ liệu và chính sách thực tế.

Sau bài này, bạn có thể:

- Phân biệt stable sorting algorithm với một thứ tự kết quả xác định.
- Thiết kế khóa sort có thành phần phân xử duy nhất trong tập kết quả.
- Giữ predicate của cursor khớp đầy đủ chiều và khóa sắp xếp.
- Xử lý null, collation và độ chính xác thời gian theo cùng ngữ nghĩa.
- Phân biệt thứ tự ổn định với snapshot dữ liệu hoặc quyền có hiệu lực.
- Kiểm thử sự ổn định mà không chỉ trông chờ database tình cờ trả cùng thứ tự.

## 1. Ba khái niệm dễ bị gọi chung là ổn định

| Khái niệm | Ý nghĩa | Điều chưa được bảo đảm |
| --- | --- | --- |
| Thuật toán sort ổn định | Các phần tử được comparator coi là bằng nhau giữ thứ tự đầu vào | Đầu vào từ database có thứ tự xác định hay không |
| Thứ tự kết quả xác định | Với cùng tập dữ liệu và cùng ngữ nghĩa sort, thứ tự được quy định đầy đủ | Dữ liệu không thay đổi giữa hai request |
| Snapshot nhất quán | Các lần đọc làm việc trên cùng một phiên bản tập dữ liệu theo hợp đồng | Thứ tự trong snapshot đã có khóa phân xử đầy đủ hay chưa |

Một thuật toán sort ổn định trong Java không sửa được vấn đề nếu query ban đầu trả các bản ghi đồng hạng theo thứ tự không được quy định. Nó chỉ giữ lại thứ tự đầu vào đó, mà thứ tự đầu vào có thể khác ở lần đọc sau.

Ngược lại, `ORDER BY submitted_at, id` có thể xác định thứ tự cho một tập dữ liệu, nhưng insert, delete hoặc đổi `submitted_at` vẫn có thể làm kết quả phân trang thay đổi.

Khi đặc tả yêu cầu “stable”, cần nói rõ đang yêu cầu tính chất nào, với tập dữ liệu, khoảng thời gian và quyền nào.

## 2. ORDER BY một trường không duy nhất có thể để lại khoảng mơ hồ

Giả sử ba đề nghị có cùng thời điểm gửi:

| ID | submitted_at | state |
| --- | --- | --- |
| R101 | Cùng thời điểm T | `PENDING_APPROVAL` |
| R102 | Cùng thời điểm T | `PENDING_APPROVAL` |
| R103 | Cùng thời điểm T | `PENDING_APPROVAL` |

Truy vấn:

```sql
SELECT id, submitted_at
FROM expense_request
WHERE tenant_id = :authorized_tenant_id
  AND state = 'PENDING_APPROVAL'
ORDER BY submitted_at ASC
LIMIT :limit OFFSET :offset;
```

Điều kiện ORDER BY chưa quy định R101, R102 và R103 đứng trước nhau thế nào. Một engine có thể tình cờ trả giống nhau nhiều lần, nhưng ứng dụng chưa có hợp đồng đầy đủ cho nhóm đồng hạng đó.

Với page size bằng 2, hai truy vấn có thể sử dụng thứ tự hợp lệ khác nhau trong nhóm bằng thời gian:

```text
lần đọc trang 1 dựa trên: R101, R102, R103
trang 1 trả: R101, R102

lần đọc trang 2 dựa trên: R103, R101, R102
offset 2 trả: R102
```

Đây là một lịch kết quả minh họa được cho phép bởi phần thứ tự còn thiếu, không phải khẳng định mọi database luôn đổi thứ tự như vậy. Hậu quả là R102 xuất hiện lại và R103 bị bỏ qua.

## 3. Vì sao thứ tự là một phần của quy tắc nghiệp vụ?

Thứ tự có thể ảnh hưởng:

- Đề nghị nào được người duyệt nhìn thấy trước.
- Đối tượng nào được một job chọn trong một lần xử lý có giới hạn.
- Thứ tự phân bổ tài nguyên khi không đủ cho mọi yêu cầu.
- Tập bản ghi được đưa vào một báo cáo hoặc thao tác hàng loạt.
- Cách người dùng đối chiếu kết quả giữa các lần đọc.

Với một hàng đợi, “cũ nhất trước” cần định nghĩa thời điểm cũ nhất đến từ đâu và cách phân xử khi bằng nhau. Không dùng timestamp client tự khai để ưu tiên một yêu cầu nếu chính sách không cho phép.

Nếu FIFO có ý nghĩa chặt theo trình tự nhận, có thể cần một sequence do nguồn có thẩm quyền cấp. Một ID ngẫu nhiên làm thứ tự xác định nhưng không tự chứng minh thứ tự đến thực tế.

Tương tự, mức ưu tiên phải được xác lập hoặc kiểm tra theo policy. Caller chọn một cách hiển thị danh sách không có nghĩa được thay đổi mức ưu tiên xử lý chính thức.

## 4. Định nghĩa một sort contract đầy đủ

Một hợp đồng cần chỉ rõ:

| Thành phần | Ví dụ |
| --- | --- |
| Tập kết quả | Đề nghị chờ duyệt trong tenant và bộ phận được phép |
| Khóa chính | Thời điểm gửi |
| Chiều | Tăng dần |
| Khóa phân xử | ID duy nhất trong tập kết quả |
| Ngữ nghĩa null | Không được null trong trạng thái này, hoặc một vị trí null được định nghĩa |
| Ngữ nghĩa kiểu dữ liệu | Thời điểm thực, số, chuỗi theo collation đã chọn |
| Phiên bản sort | Một định nghĩa được nhận diện khi tạo hoặc dùng cursor |
| Giới hạn | Page size, result window và chi phí query phù hợp |

Với nhiều khóa, có thể biểu diễn:

```text
SUBMITTED_ASC:
  submitted_at ASC, id ASC

RECENT_FIRST:
  submitted_at DESC, id DESC

REVIEW_QUEUE:
  priority_rank DESC, submitted_at ASC, id ASC
```

Khóa cuối cần phân biệt được các hàng trong tập thực sự trả về. Một field có vẻ duy nhất trong dữ liệu mẫu chưa đủ; nên có ràng buộc hoặc lý do mô hình dữ liệu bảo đảm tính duy nhất.

Không để client vô tình thay hoặc loại khóa phân xử. Nếu API cho nhiều khóa sort, cần chuẩn hóa, loại mâu thuẫn theo hợp đồng và giữ thành phần cuối bắt buộc.

## 5. Truy vấn có thứ tự xác định vẫn phải giữ scope

Ví dụ:

```sql
SELECT id, submitted_at, amount, currency
FROM expense_request
WHERE tenant_id = :authorized_tenant_id
  AND department_id IN (:authorized_department_ids)
  AND state = 'PENDING_APPROVAL'
ORDER BY submitted_at ASC, id ASC
LIMIT :validated_limit OFFSET :validated_offset;
```

SQL chỉ minh họa; cú pháp phân trang và kiểu dữ liệu cần phù hợp hệ quản trị. Các điều kiện tenant, quyền và trạng thái xác định tập trước khi phân trang.

Không sort một tập toàn cục, lấy LIMIT rồi lọc quyền trong ứng dụng. Cách đó vừa làm trang thiếu dữ liệu hợp lệ vừa có thể làm metadata hoặc vị trí phản ánh các hàng ngoài quyền.

Nếu ID chỉ duy nhất trong tenant, `(submitted_at, id)` có thể đủ trong một query đã cố định tenant. Với query quản trị thực sự được phép đi qua nhiều tenant, cần khóa phân xử duy nhất trên toàn tập đó, chẳng hạn thêm tenant cùng ID theo ngữ nghĩa đã chọn.

Trường `submitted_at` phải có ý nghĩa hợp lệ cho đối tượng chờ duyệt. Dữ liệu thiếu căn cứ cần được xử lý theo invariant, không chỉ thêm điều kiện bỏ qua để che các đề nghị bị lỗi.

## 6. Minh họa Java: chọn sort profile từ định nghĩa máy chủ

Đoạn mã dùng record của Java 16 trở lên. Nó trả những fragment SQL cố định do máy chủ định nghĩa, không nhận tên cột hoặc chiều sort tùy ý từ request.

```java
import java.util.List;
import java.util.Objects;

enum SortProfile {
    SUBMITTED_ASC,
    RECENT_FIRST,
    REVIEW_QUEUE
}

record VerifiedListPermissions(
        boolean mayReadRequests,
        boolean mayUseReviewQueueOrder) {
}

record SortPlan(
        SortProfile profile,
        int specificationVersion,
        String orderByClause,
        List<String> cursorKeyFields) {
    SortPlan {
        cursorKeyFields = List.copyOf(cursorKeyFields);
    }
}

final class RequestSortPolicy {
    private RequestSortPolicy() {
    }

    static SortPlan resolve(
            SortProfile profile, VerifiedListPermissions permissions) {
        Objects.requireNonNull(profile);
        Objects.requireNonNull(permissions);
        require(permissions.mayReadRequests(), "REQUEST_READ_NOT_ALLOWED");

        return switch (profile) {
            case SUBMITTED_ASC -> new SortPlan(profile, 1,
                    "pr.submitted_at ASC, pr.id ASC",
                    List.of("submittedAt", "id"));
            case RECENT_FIRST -> new SortPlan(profile, 1,
                    "pr.submitted_at DESC, pr.id DESC",
                    List.of("submittedAt", "id"));
            case REVIEW_QUEUE -> {
                require(permissions.mayUseReviewQueueOrder(),
                        "REVIEW_QUEUE_ORDER_NOT_ALLOWED");
                yield new SortPlan(profile, 1,
                        "pr.priority_rank DESC, pr.submitted_at ASC, pr.id ASC",
                        List.of("priorityRank", "submittedAt", "id"));
            }
        };
    }

    private static void require(boolean allowed, String code) {
        if (!allowed) {
            throw new SecurityException(code);
        }
    }
}
```

Permission được tải từ nguồn đã xác minh cho ngữ cảnh hiện tại, không bind từ body. `SortPlan` là mô hình nội bộ; không cho client tự cung cấp `orderByClause` dù có cùng tên cấu trúc.

Nếu không gửi profile, tầng input có thể chọn một default đã được công bố. Giá trị không được hỗ trợ không nên âm thầm trở thành default nếu điều đó làm client hiểu sai thứ tự hoặc ngữ nghĩa cursor.

Ví dụ chỉ chọn thứ tự. Repository vẫn phải giữ tenant, quyền đối tượng, bộ lọc và giới hạn. Cursor predicate cần được xây theo đúng profile, không chỉ đọc tên các field rồi mặc định mọi chiều đều tăng.

## 7. Cursor phải dùng đầy đủ khóa và đúng chiều so sánh

Với thứ tự tăng:

```text
submitted_at ASC, id ASC
```

Trang tiếp theo cần điều kiện tương ứng:

```sql
AND (
     submitted_at > :last_submitted_at
     OR (submitted_at = :last_submitted_at AND id > :last_id)
)
ORDER BY submitted_at ASC, id ASC
```

Chỉ dùng `submitted_at > last` sẽ bỏ các hàng cùng timestamp nhưng có ID đứng sau. Dùng `>=` mà không phân xử đầy đủ có thể trả lại hàng cũ.

Với profile nhiều chiều:

```text
priority_rank DESC, submitted_at ASC, id ASC
```

Predicate tiếp theo có thể là:

```sql
AND (
     priority_rank < :last_priority
     OR (
          priority_rank = :last_priority
          AND submitted_at > :last_submitted_at
     )
     OR (
          priority_rank = :last_priority
          AND submitted_at = :last_submitted_at
          AND id > :last_id
     )
)
ORDER BY priority_rank DESC, submitted_at ASC, id ASC
```

Các trường ở ví dụ này được giả định không null trong tập hợp lệ. Khi thêm null, phải bổ sung ngữ nghĩa tương ứng thay vì dùng nguyên các phép so sánh trên.

Giữ toàn bộ nhóm OR bên trong điều kiện tenant và quyền bắt buộc. Predicate đúng về thứ tự nhưng thiếu scope vẫn là một query không an toàn.

## 8. Null phải có vị trí và predicate rõ ràng

Một số sort key như hạn xử lý có thể null. Cần định nghĩa null đứng trước hay sau, không dựa vào giả định giống nhau ở mọi engine hoặc chiều sort.

Ví dụ muốn `due_at` tăng dần và null ở cuối, một cách thể hiện có thể là:

```sql
ORDER BY
    CASE WHEN due_at IS NULL THEN 1 ELSE 0 END ASC,
    due_at ASC,
    id ASC;
```

Cú pháp hoặc cách tối ưu có thể khác theo hệ quản trị. Điều quan trọng là hợp đồng và query thực tế cùng có một thứ tự.

Nếu cursor cuối có `due_at` khác null, phần sau gồm các giá trị lớn hơn, các giá trị bằng có ID lớn hơn, rồi tới nhóm null. Nếu cursor đang ở nhóm null, chỉ tiếp tục nhóm null theo ID.

Không so `due_at = null` như một phép so sánh thông thường. Không thay null bằng một ngày giả có thể trùng ngày thật mà không có quy tắc phân biệt.

Cursor cần giữ được thông tin đang ở nhóm nào. Test phải đi qua ranh giới từ giá trị có thật sang null và qua nhiều bản ghi null, không chỉ một trường hợp đơn lẻ.

## 9. Collation, kiểu dữ liệu và độ chính xác phải thống nhất

Thứ tự văn bản có thể phụ thuộc locale, phân biệt hoa–thường, dấu và normalization. Hai tên khác nhau ở đầu vào có thể được comparator xem là đồng hạng; vẫn cần khóa phân xử phù hợp.

Các điểm cần xác định:

- Sort theo chuỗi hay số thực sự của field.
- Collation và quy tắc chuẩn hóa văn bản.
- Cách xử lý ký tự có dấu, hoa–thường và chuỗi rỗng.
- Độ chính xác timestamp dùng trong query và cursor.
- Cách biểu diễn timezone và giá trị đã được lưu.

Không mặc định thứ tự so sánh của Java, JSON hoặc một search engine giống database. Nếu sort ở nhiều nơi, các comparator phải có cùng ngữ nghĩa cho dữ liệu đang dùng.

Một lỗi cursor thường gặp là database giữ thời gian chính xác hơn dữ liệu được serialize. Nếu cursor làm mất phần độ chính xác mà query cần để phân biệt các khóa, predicate tiếp theo có thể bỏ sót hoặc lặp hàng.

Khi đổi collation, normalization hoặc định nghĩa sort, cần xem đó là thay đổi ngữ nghĩa. Cursor cũ có thể phải hết hiệu lực hoặc được xử lý theo một version tương thích; không chỉ giữ cùng danh sách tên field rồi áp comparator mới.

## 10. Thứ tự xác định không đóng băng dữ liệu

Với offset, insert hoặc delete trước vị trí hiện tại làm các hàng dịch chỗ. Thêm ID vào ORDER BY không loại bỏ sự dịch chuyển đó.

Với keyset, hành vi thường phù hợp hơn cho việc đi tiếp theo khóa, nhưng các bản ghi đổi chính sort key vẫn có thể chuyển qua ranh giới cursor. Nó không tự tạo một snapshot đầy đủ.

```text
Tập dữ liệu giữ nguyên + sort contract đầy đủ
  → có cơ sở kiểm thử một thứ tự lặp lại xác định

Dữ liệu hoặc quyền thay đổi
  → cần hợp đồng nhất quán và hiệu lực riêng
```

Nếu cần báo cáo chính xác tại một thời điểm, dùng snapshot hoặc job có phạm vi, thời gian sống và nguồn dữ liệu phù hợp. Một mốc `created_at <= cutoff` có thể chặn thêm mới sau mốc, nhưng không tự ngăn mọi cập nhật và xóa.

Quyền cũng có thể thay đổi giữa hai trang. Snapshot dữ liệu không mặc định cấp quyền đọc cũ vô thời hạn; cursor hoặc job phải đáp ứng chính sách hiệu lực đã công bố.

Đừng mở một transaction không có giới hạn theo thời gian người dùng lật trang để cố giữ snapshot. Yêu cầu dài hạn cần được thiết kế và giới hạn như một tiến trình riêng.

## 11. Khóa duy nhất phải thuộc đúng đơn vị kết quả

Một join có thể tạo nhiều hàng cho cùng một đề nghị. Thêm `pr.id` vào ORDER BY chưa phân biệt các hàng join nếu chúng mang cùng ID và cùng sort key.

Cần xác định API đang trả:

- Một hàng cho mỗi đề nghị.
- Một hàng cho mỗi dòng chi tiết.
- Một hàng cho mỗi nhóm tổng hợp.
- Một cấu trúc cha chứa các phần tử con.

Nếu API trả đề nghị, query cần tạo đúng tập đề nghị trước khi phân trang hoặc dùng mô hình tổng hợp phù hợp. Thứ tự của các hàng SQL không tự giải quyết việc một parent bị lặp do join.

Nếu sort theo dữ liệu con, định nghĩa rõ giá trị đại diện: mới nhất, sớm nhất, lớn nhất hay một quy tắc khác. “Sort theo thời gian ghi chú” không rõ ràng khi có nhiều ghi chú cho cùng parent.

Với nhóm aggregate, khóa phân xử cần phân biệt các nhóm. Các giá trị tổng hợp có thể thay đổi giữa các request, nên vẫn cần hợp đồng snapshot hoặc xử lý dữ liệu động.

Quyền theo trường cũng áp dụng cho sort. Một actor được đọc đề nghị chưa chắc được dùng điểm điều tra nội bộ để xếp thứ tự và suy luận thông tin. Không trả thêm sort key nhạy cảm trong cursor hoặc metadata ngoài phạm vi được phép.

## 12. Thứ tự giao diện không phải thẩm quyền của hàng đợi hoặc command

Người dùng có thể chọn xem đề nghị mới nhất trước. Điều đó không tự thay đổi chính sách xử lý ưu tiên chính thức của hệ thống.

Một worker chọn công việc cần dùng thứ tự và guard do policy xác định, cùng cơ chế nhận công việc nguyên tử phù hợp. Hai worker thấy cùng mục đầu không được cùng nhận quyền thực hiện chỉ vì query đã có thứ tự.

Nếu việc phân bổ tài nguyên phụ thuộc thứ tự, cần ghi rõ ai được chọn thứ tự và căn cứ nào được dùng. Không để caller đặt `priorityRank`, `submittedAt` hoặc một sort profile tùy ý để đưa yêu cầu của mình lên trước khi chính sách không cho phép.

Với hành động duyệt hàng loạt, không dùng “các mục trên trang hiện tại” làm bằng chứng duy nhất. Trang có thể thay đổi trước khi command chạy. Lệnh cần gắn ID, version và snapshot hoặc selection snapshot có thẩm quyền rồi kiểm tra lại quyền và trạng thái.

Sort ổn định giúp người dùng xem và đối chiếu dữ liệu; nó không chứng minh các bước duyệt đã xảy ra hay đối tượng vẫn được phép thực hiện.

## 13. Cursor, cache và idempotency cần giữ ngữ nghĩa sort

Một cursor có thể cần ràng buộc:

```text
sort profile và specification version
mọi thành phần khóa cuối, gồm thông tin null nếu có
tenant và ngữ cảnh quyền theo hợp đồng
filter đã chuẩn hóa
snapshot hoặc cutoff nếu được dùng
thời hạn của token
```

Tính toàn vẹn của cursor không thay quyền. Dùng token hợp lệ từ actor hoặc tenant khác không được mở dữ liệu ngoài scope hiện tại.

Cache key cần phân biệt sort, chiều, specification version, filter và các chiều scope hoặc projection phù hợp. Không trả trang sort tăng từ cache cho request sort giảm hoặc dùng response đã xếp theo một trường đặc quyền cho actor không được dùng cách xếp đó.

Với command mà thứ tự mục có ý nghĩa, idempotency fingerprint phải giữ ý nghĩa ấy. Không tự sort ID trước khi hash rồi coi hai thứ tự phân bổ khác nhau là cùng ý định. Nếu thứ tự không có ý nghĩa theo hợp đồng, có thể chuẩn hóa một cách xác định.

Request GET có thể trả dữ liệu khác khi hệ thống thay đổi; tính idempotent của phương thức không đồng nghĩa response phải giống từng byte. Tương tự, sort ổn định không biến hai lần đọc ở hai snapshot khác nhau thành cùng một quyết định nghiệp vụ.

## 14. Thứ tự đúng vẫn cần giới hạn chi phí

Một ORDER BY đầy đủ không bảo đảm query rẻ. Sort theo nhiều khóa, aggregate hoặc dữ liệu con có thể tăng chi phí và cần index hay kế hoạch phù hợp.

Cần kết hợp:

- Tập sort profile được hỗ trợ, không raw expression từ caller.
- Page size và result window có giới hạn.
- Scope quyền trong query, không lọc sau LIMIT.
- Trần fan-out hoặc số phần tử con.
- Mức song song, timeout và quota sử dụng phù hợp.
- Đo kế hoạch và chi phí trên dữ liệu đại diện.

Đừng bỏ khóa phân xử chỉ vì query mẫu chạy nhanh hơn mà chưa xác định cách giữ hợp đồng. Có thể cần điều chỉnh index, schema hoặc giới hạn use case thay vì để thứ tự không rõ ràng.

Nếu một profile được cho phép theo role hoặc scope, quyết định đó từ policy máy chủ. Client không tự mở quyền dùng field nhạy cảm qua `customSort`, tên cột hoặc alias chưa được kiểm soát.

Các fragment trong code minh họa là literal đã được định nghĩa. Những giá trị dữ liệu của filter hoặc cursor vẫn cần được bind theo cơ chế phù hợp của hệ quản trị.

## 15. Ma trận kiểm thử với dataset không thay đổi

Tạo nhiều bản ghi đồng hạng hơn page size, đồng thời có dữ liệu ngoài quyền xen kẽ. Xác định expected từ sort contract và fixture độc lập.

| Ca kiểm thử | Kết quả cần giữ |
| --- | --- |
| Nhiều hàng cùng submitted_at | Khóa phân xử tạo thứ tự đầy đủ |
| Nhiều hàng cùng priority và submitted_at | Profile hàng đợi vẫn phân biệt được mọi hàng hợp lệ |
| Page size nhỏ đi qua nhóm đồng hạng | Không bỏ hoặc lặp ID trong một traversal ổn định |
| Sort tăng và sort giảm | Cả thứ tự lẫn predicate tiếp theo đúng chiều |
| Nhiều giá trị null liên tiếp | Vị trí null và các trang trong nhóm null đúng hợp đồng |
| Tên khác hoa–thường hoặc dấu | Kết quả theo collation và khóa phân xử đã chọn |
| Timestamp khác ở phần độ chính xác nhỏ | Cursor không mất thông tin cần so sánh |
| ID chỉ duy nhất trong tenant | Query cố định tenant đúng; query xuyên tenant có khóa đầy đủ riêng |
| Parent có nhiều hàng con | API không lặp parent hoặc phân trang sai đơn vị |
| Profile không được phép hoặc field tùy ý | Không tạo ORDER BY ngoài hợp đồng |

Kiểm tra từng trang và toàn bộ tập theo thứ tự, không chỉ so số lượng hoặc tập ID không có thứ tự.

Chạy lặp nhiều lần mà luôn nhận cùng kết quả chưa chứng minh query có một thứ tự được cam kết. Engine có thể tình cờ chọn cùng một kế hoạch. Cần rà soát cấu trúc ORDER BY, ràng buộc uniqueness và test các nhóm đồng hạng cùng những đường query thực tế.

Không dùng chính comparator production làm oracle duy nhất cho expected. Nó có thể chia sẻ lỗi chiều hoặc null với implementation đang kiểm tra.

## 16. Kiểm thử cursor và các thay đổi giữa trang

Các ca cần lịch rõ ràng:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Cursor chỉ có timestamp trong nhóm nhiều ID | Test phát hiện mất hoặc lặp các hàng đồng hạng |
| Đổi sort nhưng giữ cursor | Không ghép khóa của profile cũ với predicate mới |
| Specification version đổi | Cursor cũ được xử lý theo chính sách tương thích hoặc hết hiệu lực rõ ràng |
| Cursor đi qua ranh giới có giá trị sang null | Không bỏ hoặc đọc lại một nhóm ngoài hợp đồng |
| Insert hoặc delete trước vị trí offset | Hành vi đúng hợp đồng dữ liệu động, không bị gọi nhầm là snapshot bất biến |
| Một hàng đổi priority hoặc thời gian sort | Không coi token cũ là bằng chứng đối tượng vẫn ở vị trí cũ |
| Anchor bị xóa hoặc mất quyền | Không lookup toàn cục hoặc bỏ scope để tiếp tục |
| Actor bị thu hồi quyền giữa hai trang | Quyền hiệu lực vẫn đúng dù cursor còn nguyên vẹn |
| Hai worker chọn cùng đầu hàng đợi | Chỉ nhận công việc theo cơ chế loại trừ đã định |
| Command chạy sau khi trang đã đổi | Chỉ xử lý đúng ID, version và nội dung được chấp nhận |

Với keyset nhiều chiều, tạo dữ liệu phân biệt từng nhánh OR. Một ca chỉ có priority giống nhau không chứng minh nhánh chuyển sang priority thấp hơn đã đúng.

Với snapshot hoặc export, kiểm thử riêng insert, update và delete để biết phạm vi nhất quán thật sự. Các test transaction hoặc nhận việc đồng thời cần cơ chế lưu trữ và điểm đồng bộ phù hợp, không chỉ gọi hai hàm tuần tự.

Nếu dùng cache hoặc search index, chạy các profile và scope theo cả thứ tự làm nóng khác nhau để phát hiện việc dùng lại kết quả hoặc comparator sai ngữ cảnh.

## 17. Thay đổi sort contract và khả năng giải thích

Thay đổi khóa phân xử, chiều, null order hoặc collation có thể ảnh hưởng client, cursor đang tồn tại, export và tiến trình xử lý nền. Cần đánh giá như một thay đổi hợp đồng, không chỉ chỉnh trình bày.

Một kế hoạch chuyển đổi nên xác định:

- Sort specification version mới và phạm vi endpoint bị ảnh hưởng.
- Cursor cũ còn được đọc hay cần bắt đầu lại.
- Cache hoặc index cần cập nhật thế nào.
- Job đang chạy giữ snapshot hoặc quy tắc nào.
- Các command có phụ thuộc thứ tự được xử lý ra sao.

Không âm thầm đổi ý nghĩa một token cũ để giữ request thành công. Một lỗi rõ ràng yêu cầu bắt đầu lại có thể đúng hơn việc tiếp tục với một tập sai.

Audit hoặc trace nên có actor, tenant, query hoặc nhóm filter phù hợp, sort profile, specification version, reference tới cursor hoặc snapshot và kết quả xử lý. Không cần log nguyên token hoặc sort key nhạy cảm ngoài nhu cầu.

Với hàng đợi, ghi được căn cứ chọn mục và operation đã nhận để phân biệt “được nhìn thấy trước” với “đã nhận quyền thực hiện”. Thứ tự trong response không tự là lịch thực thi thực tế.

## 18. Cách áp dụng stable sort requirement

1. Xác định thứ tự phục vụ hiển thị, phân trang, báo cáo hay phân bổ tài nguyên.
2. Định nghĩa đầy đủ các khóa, chiều, null order, kiểu dữ liệu và khóa phân xử duy nhất trong tập kết quả.
3. Giữ tenant, quyền đối tượng và quyền sử dụng field trong query trước phân trang.
4. Dùng sort profile hoặc cấu trúc query có kiểm soát, không nhận raw ORDER BY từ client.
5. Xây cursor predicate khớp mọi khóa và chiều, giữ đủ độ chính xác cùng ngữ cảnh.
6. Nêu rõ ảnh hưởng của insert, update, delete và thay đổi quyền; thiết kế snapshot riêng nếu cần.
7. Tách thứ tự giao diện khỏi quyền chọn ưu tiên hoặc thực hiện command.
8. Version hóa thay đổi ngữ nghĩa và cập nhật cache, cursor cùng job liên quan.
9. Kiểm thử nhóm đồng hạng, null, nhiều chiều, dữ liệu biến động và các đường tạo hiệu ứng.

Thứ tự xác định giúp hệ thống giải thích được vì sao một bản ghi đứng ở vị trí nào trong cùng một tập dữ liệu. Khi kết hợp với scope, snapshot và guard nghiệp vụ phù hợp, nó giảm nguy cơ bỏ sót, lặp hoặc xử lý nhầm đối tượng chỉ vì các khóa sắp xếp chưa được định nghĩa đầy đủ.

# Giới hạn của phân trang trên dữ liệu đang thay đổi

Trong **Spring Data Couchbase**, phân trang giúp ứng dụng trả một lượng nhỏ dữ liệu thay vì tải toàn bộ collection. Nhưng một câu hỏi quan trọng thường bị bỏ qua: **danh sách có còn là cùng một danh sách giữa hai lần người dùng bấm “Trang tiếp theo” không?**

Đối với Couchbase, document có thể được thêm, sửa, xóa hoặc hết hạn TTL trong khi người dùng đang duyệt. Truy vấn SQL++ còn đi qua Query Service và các index với cơ chế scan consistency riêng. Vì thế, ngay cả khi mỗi trang có `ORDER BY` rõ ràng và `LIMIT` nhỏ, việc đi qua nhiều trang **không tự bảo đảm** đọc một snapshot bất biến của toàn bộ dữ liệu.

Bài thuộc chương **Chiếu và phân trang** của module **SPRING_DATA_COUCHBASE**. Ta sẽ xem xét giới hạn về tính đúng khi kết hợp Spring Data repository, `CouchbaseTemplate`, truy vấn SQL++, bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và reactive API.

Sau bài học, bạn có thể:

1. Phân biệt thứ tự xác định trong **một query** với tính nhất quán của **nhiều query** nối tiếp.
2. Mô phỏng hiện tượng trùng, bỏ sót, nhảy trang, thay đổi tổng và dịch chuyển vị trí khi insert/delete/update.
3. Giải thích vì sao `Page`/`Slice`, `OFFSET`/`LIMIT`, keyset/cursor và scan consistency giải quyết **những vấn đề khác nhau**.
4. Xác định khi nào cursor vẫn có thể lặp hoặc bỏ sót document và khi nào dùng một mốc thời gian chưa đủ.
5. Chọn một hợp đồng API phù hợp: danh sách “live”, duyệt tuần tự gần ổn định, hay export/báo cáo cần tập dữ liệu cố định.
6. Xây dựng integration test có mutation giữa các trang và đo cả tính đúng lẫn hiệu năng.

## 1. Bài toán minh họa: danh sách khách hàng đang thay đổi

Giả sử bucket `shop`, scope `crm`, collection `customers` có các document:

~~~json
{
  "fullName": "Trần Minh",
  "email": "minh@example.test",
  "active": true,
  "tenantId": "tenant-01",
  "createdAt": "2026-11-20T08:15:00.000Z",
  "updatedAt": "2026-11-24T10:30:00.000Z"
}
~~~

Document key, ví dụ `customer::42`, nằm ở metadata Couchbase, không bắt buộc xuất hiện trong body.

API danh sách lấy 3 khách hàng mỗi trang theo `createdAt DESC`, dùng document key để phân xử khi thời điểm tạo trùng nhau:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.createdAt AS createdAt
FROM `shop`.`crm`.`customers` AS c
WHERE c.tenantId = $tenantId
  AND c.active = TRUE
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 3 OFFSET 0;
~~~

Một người dùng mở trang đầu lúc 09:00 rồi mở trang tiếp theo lúc 09:02. Trong hai phút đó:

- Có khách hàng mới được thêm.
- Một khách hàng bị xóa hoặc hết hạn TTL.
- Một khách hàng chuyển từ `active = true` sang `false`.
- Một document được sửa `createdAt` hoặc field dùng để sắp xếp.
- Index có thể phản ánh các mutation với độ trễ tùy scan consistency.

Kết quả của trang thứ hai là **một truy vấn mới trên một tập dữ liệu có thể đã khác**, không phải phần tiếp theo được giữ sẵn trong bộ nhớ của truy vấn trang đầu.

### Ba điều thường bị đánh đồng

| Vấn đề | Câu hỏi cần trả lời | Cơ chế liên quan |
| --- | --- | --- |
| Thứ tự một trang | Các hàng trong query này được xếp thế nào? | `ORDER BY`, khóa phân xử duy nhất |
| Vị trí trang sau | Làm sao tìm hàng tiếp theo từ vị trí đã xem? | `OFFSET` hoặc keyset cursor |
| Tính nhất quán xuyên nhiều trang | Có đang duyệt cùng một tập và cùng một phiên bản dữ liệu không? | Hợp đồng snapshot, vật hóa tập, transaction/mô hình dữ liệu |

**Một câu SQL++ có thứ tự ổn định không tự mang lại tính nhất quán xuyên request.**

## 2. OFFSET drift khi có document mới

Giả sử tại thời điểm T0, tập dữ liệu theo thứ tự mới nhất trước là:

~~~text
A  B  C  D  E  F  G
~~~

`pageSize = 3`. Trang đầu:

~~~sql
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 3 OFFSET 0
~~~

Trả:

~~~text
A  B  C
~~~

Ngay sau đó, document mới `X` có thời điểm tạo mới hơn A được thêm:

~~~text
X  A  B  C  D  E  F  G
~~~

Trang thứ hai dùng:

~~~sql
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 3 OFFSET 3
~~~

Trả:

~~~text
C  D  E
~~~

**C bị lặp** dù `ORDER BY` hoàn toàn xác định. Vì `OFFSET 3` có nghĩa “bỏ ba hàng hiện đang đứng đầu”, không có nghĩa “tiếp tục sau C mà người dùng đã thấy”.

Nếu user tiếp tục nhiều trang trong lúc document mới liên tục được chèn trước vị trí đang duyệt, các hàng có thể lặp nhiều lần hoặc quá trình duyệt khó kết thúc theo mong muốn.

### Một tình huống khác: chèn giữa những hàng đã đọc

Giả sử X được chèn vào giữa A và B. Sau khi trang đầu A–B–C đã tải, trang hai vẫn có thể bắt đầu bằng một hàng đã thấy. Nguyên nhân vẫn là số vị trí phía trước ranh giới trang thay đổi.

**Khóa phân xử duy nhất giải quyết các giá trị sort trùng nhau; nó không ngăn offset drift.**

## 3. OFFSET drift khi xóa document hoặc TTL hết hạn

Tập ban đầu vẫn là:

~~~text
A  B  C  D  E  F  G
~~~

Trang đầu: `A, B, C`.

Sau đó B bị xóa hoặc hết hạn TTL:

~~~text
A  C  D  E  F  G
~~~

Trang thứ hai lấy `OFFSET 3`, trả:

~~~text
E  F  G
~~~

Document **D chưa từng được hiển thị nhưng bị bỏ qua** vì vị trí của D đã dịch từ chỉ số 3 sang chỉ số 2.

Tương tự, nếu B không bị xóa nhưng chuyển từ `active = TRUE` sang `FALSE`, B rời khỏi tập kết quả của truy vấn `WHERE c.active = TRUE`. Với offset pagination, hiệu ứng có thể giống một lần xóa.

| Thay đổi trước ranh giới | Hiện tượng với OFFSET | Có cần lỗi SQL++ xảy ra? |
| --- | --- | --- |
| Chèn một document | Hàng đã thấy có thể bị lặp | Không |
| Xóa một document | Hàng chưa thấy có thể bị bỏ qua | Không |
| TTL làm document hết hạn | Trang sâu có thể bị dịch | Không |
| Document không còn khớp filter | Vị trí các hàng còn lại đổi | Không |
| Document bắt đầu khớp filter | Hàng mới có thể đẩy các hàng khác xuống | Không |

Đây là **giới hạn ngữ nghĩa** của offset khi tập kết quả biến động, không phải lỗi converter của Spring Data Couchbase.

## 4. Update trường sắp xếp: không cần insert/delete cũng có thể sai

Giả sử UI dùng:

~~~sql
ORDER BY c.updatedAt DESC, META(c).id DESC
~~~

Một khách hàng D ban đầu đứng ở trang sau. Khi nhân viên chỉnh sửa D, `updatedAt` được cập nhật và D nhảy lên đầu danh sách.

Nếu trang đầu A–B–C đã được người dùng xem trước đó, việc D nhảy lên đầu có thể làm ranh giới offset dịch chuyển. D có thể không bao giờ xuất hiện trong các trang sau của cùng phiên duyệt, mặc dù document vẫn tồn tại.

Ngược lại, một document đã xem có thể được sửa khiến nó đi từ đầu danh sách xuống phía sau ranh giới, làm nó xuất hiện **lần thứ hai** trong những trang sau.

| Trường dùng để sort | Có thường thay đổi sau khi tạo? | Rủi ro |
| --- | --- | --- |
| `createdAt` bất biến theo hợp đồng | Thường không | Giảm dịch chuyển do update trường sort |
| `updatedAt` | Có | Rất dễ đổi vị trí sau mỗi cập nhật |
| `score`, `ranking`, `balance` | Có | Đổi vị trí khi nghiệp vụ biến động |
| `fullName` | Có thể | Đổi vị trí khi sửa tên |
| `META(c).id` | Không đổi với cùng document key | Ổn định để phân xử, nhưng document có thể bị xóa hoặc tái tạo |

Một sort key bất biến có lợi cho keyset pagination, nhưng **không đủ** để giữ snapshot nếu document vẫn có thể bị thêm, xóa, hết hạn hoặc đổi trạng thái lọc.

## 5. Vì sao `ORDER BY` có khóa phụ vẫn cần thiết?

Các biến động vừa mô tả không có nghĩa bỏ `ORDER BY`. Ngược lại, một câu query thiếu thứ tự còn không xác định được trang ngay cả khi dữ liệu đứng yên.

Ví dụ nhiều khách hàng có `createdAt` bằng nhau:

~~~sql
-- Không đủ để sắp xếp toàn phần.
ORDER BY c.createdAt DESC
~~~

Hãy bổ sung document key:

~~~sql
ORDER BY c.createdAt DESC, META(c).id DESC
~~~

Khi cùng timestamp, ID định nghĩa thứ tự tiếp theo. Trong một collection đơn nguồn, document key là duy nhất. Nếu dùng `JOIN` hoặc `UNNEST` tạo nhiều result row từ một document, ID có thể bị lặp theo row và cần khóa phân xử khác ở **mức result row**.

Phân biệt:

1. **Thứ tự toàn phần:** tất cả hàng trong một tập tĩnh có vị trí rõ ràng.
2. **Thứ tự bất biến qua thời gian:** cần giá trị sort và thành viên tập không đổi, hoặc cần một định nghĩa snapshot.
3. **Hiển thị không lặp khi duyệt:** có thể cải thiện bằng cursor, nhưng không tự suy ra từ hai điều trên khi dữ liệu đang thay đổi.

## 6. Page, Slice và List không cung cấp snapshot tự động

Trong Spring Data, `Pageable` yêu cầu trang và sort:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id"))
);
~~~

Repository minh họa:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    Page<Customer> findByActiveTrue(Pageable pageable);

    Slice<Customer> findByActive(boolean active, Pageable pageable);
}
~~~

Các kiểu kết quả:

| Kiểu | Có gì | Không bảo đảm điều gì |
| --- | --- | --- |
| `List<T>` | Nội dung các hàng đã query | Không có thông tin tổng/trang tiếp theo; không có snapshot |
| `Slice<T>` | Nội dung, `hasNext`, metadata trang | Không có tổng số; `hasNext` không giữ dữ liệu bất biến |
| `Page<T>` | Nội dung, `totalElements`, `totalPages` | Total có thể đổi; không tạo snapshot xuyên nhiều request |
| Custom keyset result | Nội dung và cursor dựa trên giá trị sort | Không tự giữ nguyên mọi document/phiên bản đã tồn tại |

`Page<T>` có thể cần một câu `COUNT` ngoài query dữ liệu. `Slice<T>` thường lấy thêm một hàng để biết có trang tiếp theo mà không cần count. **Cả hai có thể dựa trên offset** nếu được tạo từ `PageRequest.of(page, size)`. Chuyển `Page` sang `Slice` giúp tránh chi phí tổng khi không cần, nhưng không loại bỏ offset drift.

### Lưu ý về `Sort.by("id")`

Trong entity Couchbase, `@Id` thường là document key ở metadata, không phải field `c.id` của body. `Sort.by("id")` là property Spring Data; cách ánh xạ sang SQL++ cần kiểm tra trên phiên bản thực tế. Khi cần ràng buộc chắc chắn vào key, custom SQL++ dùng `META(c).id` tường minh.

## 7. Metadata của Page có thể mâu thuẫn với nội dung trang

Ví dụ UI cần:

~~~json
{
  "items": [
    {"id": "customer::42", "fullName": "Trần Minh"}
  ],
  "page": 0,
  "size": 20,
  "totalElements": 5000,
  "totalPages": 250
}
~~~

Để trả `totalElements`, ứng dụng có thể chạy:

~~~sql
SELECT COUNT(1) AS total
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.tenantId = $tenantId;
~~~

Trong khi query dữ liệu là:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.tenantId = $tenantId
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT $limit OFFSET $offset;
~~~

Nếu một document được thêm, xóa hoặc đổi trạng thái giữa hai câu query, `totalElements` và `items` có thể phản ánh **hai thời điểm khác nhau**. Không nên diễn giải số tổng như bằng chứng cả page và count thuộc cùng snapshot.

Trường hợp khác: người dùng đã ở trang cuối. Giữa lúc họ xem và lúc họ bấm “Tiếp”, document bị xóa hoặc TTL hết hạn khiến tổng số trang giảm. Trang trước đó hợp lệ nhưng trang hiện tại có thể rỗng. Đây không mặc nhiên là lỗi repository.

### Những nhầm lẫn về tổng

- `getNumberOfElements()`: số phần tử thực có trong **trang này**.
- `getTotalElements()`: số phần tử toàn bộ theo metadata của `Page`/cách count.
- `getTotalPages()`: số trang tính từ total và kích thước trang, không phải số cố định mãi mãi.
- `Slice.hasNext()`: có hàng kế tiếp theo lần truy vấn hiện tại, không phải lời hứa rằng trang sau vẫn còn hàng khi người dùng bấm.

Nếu giao diện chỉ cần “Tải thêm”, tránh tính `COUNT` liên tục khi không cần. Nếu nghiệp vụ thật sự yêu cầu tổng chính xác đồng thời với dữ liệu, phải thiết kế mức nhất quán riêng thay vì chỉ chọn kiểu `Page`.

## 8. Keyset pagination giảm một số rủi ro, nhưng không phải snapshot

**Keyset pagination** (seek pagination) thay `OFFSET` bằng một điều kiện `WHERE` dựa trên bộ khóa của hàng cuối đã trả.

Với thứ tự:

~~~sql
ORDER BY c.createdAt DESC, META(c).id DESC
~~~

Trang đầu:

~~~sql
SELECT META(c).id AS id,
       c.createdAt AS createdAt,
       c.fullName AS fullName
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.tenantId = $tenantId
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 21;
~~~

Nếu hiển thị 20 hàng và có hàng thứ 21, `hasNext = true`. Cursor lấy từ **hàng cuối trong 20 hàng hiển thị**, không lấy từ hàng thứ 21.

Giả sử:

~~~json
{
  "afterCreatedAt": "2026-11-20T08:15:00.000Z",
  "afterId": "customer::42"
}
~~~

Trang sau:

~~~sql
SELECT META(c).id AS id,
       c.createdAt AS createdAt,
       c.fullName AS fullName
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.tenantId = $tenantId
  AND (
      c.createdAt < $afterCreatedAt
      OR (
          c.createdAt = $afterCreatedAt
          AND META(c).id < $afterId
      )
  )
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 21;
~~~

**Vì sao giúp giảm drift?** Trang sau chỉ xét giá trị khóa nằm phía sau cursor, không bỏ một số hàng thay đổi theo vị trí. Nếu một document mới được chèn **trước cursor**, nó thường không đẩy một hàng cũ đã xem vào kết quả trang kế tiếp.

**Vì sao vẫn chưa phải snapshot?**

- Document mới được thêm **sau cursor** có thể xuất hiện dù không tồn tại ở thời điểm trang đầu.
- Document cũ bị xóa hoặc hết hạn TTL sẽ không thể xuất hiện ở trang sau.
- Một document đổi `createdAt` từ trước cursor sang sau cursor có thể xuất hiện lại.
- Một document chưa xem đổi `createdAt` sang trước cursor có thể bị bỏ sót.
- Một document đổi `active` hoặc tenant/filter nghiệp vụ có thể vào/ra tập kết quả.

Đối với dataset có sort key bất biến và chỉ bổ sung record mới ở phía đầu (không backdate, không xóa, không đổi filter), keyset **thường** tạo hành vi duyệt dễ dự đoán hơn offset; nhưng đó là **giả định nghiệp vụ cần được thực thi**, không phải bảo đảm chung của Couchbase.

## 9. Kịch bản keyset vẫn có thể lặp

Giả sử sắp theo `updatedAt DESC, id DESC`, trang đầu trả:

~~~text
A(updatedAt=10:00)
B(updatedAt=09:00)
C(updatedAt=08:00)  ← cursor
~~~

Trang sau sẽ chọn các hàng có `updatedAt < 08:00` (hoặc cùng giờ và ID nhỏ hơn).

Giả sử B đã được xem, rồi một tác vụ **sửa ngược timestamp** của B thành `07:00`:

~~~text
A(10:00)
C(08:00)
B(07:00)  ← đã hiển thị nhưng giờ đứng sau cursor
D(06:00)
~~~

Lúc lấy trang sau, B có thể xuất hiện **lần nữa**. Điều này thường gặp khi hệ thống cho phép sửa khóa sắp xếp, nhận sự kiện trễ hoặc import/backfill dữ liệu có timestamp cũ.

Một kịch bản ngược: D chưa xem có timestamp `06:00` nhưng được cập nhật lên `11:00`. D chuyển sang **trước cursor**, nên trang sau theo điều kiện seek có thể **không bao giờ trả D** trong phiên duyệt này.

**Kết luận:** keyset làm vị trí của cursor ổn định theo giá trị so sánh, nhưng **không khóa vị trí của các document khác**.

## 10. “Chốt thời điểm” bằng watermark: có ích nhưng có giới hạn

Một cách thiết kế feed là lấy **watermark** ở lần đầu rồi giới hạn các trang tiếp theo:

~~~sql
WHERE c.tenantId = $tenantId
  AND c.active = TRUE
  AND c.createdAt <= $cutoff
~~~

Ví dụ `cutoff = 2026-11-25T02:00:00.000Z` và cursor theo `createdAt DESC, id DESC`. Dữ liệu tạo với `createdAt` **sau** cutoff bị loại khỏi phiên duyệt. Điều này có thể giảm xáo trộn do bản ghi mới.

Nhưng điều kiện `createdAt <= cutoff` **không tạo snapshot**. Phân tích:

| Sự kiện sau khi bắt đầu duyệt | Watermark `createdAt <= cutoff` xử lý thế nào? |
| --- | --- |
| Document mới có timestamp sau cutoff | Thường bị loại |
| Backfill document mới nhưng timestamp trước cutoff | **Vẫn có thể lọt vào** |
| Document cũ bị xóa | Không thể khôi phục chỉ nhờ cutoff |
| Document cũ hết hạn TTL | Vẫn biến mất |
| Document cũ đổi `active` | Có thể vào/ra tập lọc |
| Document cũ đổi `createdAt` | Có thể vượt qua ranh giới cursor |
| Body bị sửa nhưng `createdAt` không đổi | Cursor có thể ổn, **nội dung đã thay đổi** |

Nếu hệ thống cần “mọi document tồn tại đúng tại thời điểm T0 và giá trị của chúng tại T0”, watermark dựa trên trường nghiệp vụ không đủ. Cần **lưu lại tập và/hoặc phiên bản dữ liệu** theo một cơ chế riêng.

### Khi nào watermark đáng dùng?

Feed thường ghi chỉ thêm, thời điểm tạo do server cấp không cho backdate và không cần bảo đảm snapshot mạnh có thể dùng watermark như một **quy tắc điều hướng sản phẩm**. Phải công khai rằng dữ liệu có thể bị xóa hoặc trạng thái hiện tại khác lúc người dùng bắt đầu.

Cũng cần lưu ý đồng hồ giữa các producer, timezone, format ISO-8601, độ chính xác timestamp và giá trị `NULL`/`MISSING`. Nếu `createdAt` không được chuẩn hóa, phép so sánh chuỗi có thể không phản ánh thứ tự thời gian mong muốn.

## 11. Scan consistency của SQL++ giải quyết một vấn đề khác

Couchbase Query Service thực thi truy vấn SQL++ dựa trên secondary index trong nhiều workload. Sau khi mutation thành công ở Data Service, index có thể chưa phản ánh mutation ngay, tùy thời điểm và cơ chế consistency.

Các lựa chọn thường gặp:

- **`NOT_BOUNDED`**: query không nhất thiết chờ index bắt kịp mutation mới nhất; có thể thấy dữ liệu chưa thật mới.
- **`REQUEST_PLUS`**: query đợi các index liên quan bắt kịp các mutation đã hoàn tất theo ngữ nghĩa consistency của request, có thể tăng độ trễ.
- **`AT_PLUS`**: khi SDK/đường query hỗ trợ mutation state, query có thể yêu cầu nhất quán tối thiểu theo những mutation token cụ thể.

Mục tiêu của các chế độ này chủ yếu là **mức độ mới của dữ liệu mà một lần query có thể nhìn thấy**. Chúng **không** tự tạo một snapshot duy nhất dùng lại cho hàng chục HTTP request sau đó.

### Ví dụ SDK với `REQUEST_PLUS`

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

String statement = """
    SELECT META(c).id AS id, c.fullName AS fullName
    FROM `shop`.`crm`.`customers` AS c
    WHERE c.active = TRUE
    ORDER BY c.createdAt DESC, META(c).id DESC
    LIMIT 20
    """;

QueryResult result = cluster.query(
    statement,
    queryOptions().scanConsistency(
        QueryScanConsistency.REQUEST_PLUS));
~~~

Đây là ví dụ một request query. Nó có thể giúp khi UI vừa tạo khách hàng và cần đọc danh sách phản ánh cập nhật, nhưng không có nghĩa `page=0` lúc 09:00 và `page=1` lúc 09:05 cùng nhìn một trạng thái dữ liệu.

### KV get, CAS và SQL++ consistency

KV API như `collection.get(id)` đọc trực tiếp một document theo key và trả CAS cho phiên bản đã đọc. Nó phù hợp khi cần **đọc/sửa một document** với optimistic locking, nhưng không giải quyết snapshot của một query liệt kê toàn collection.

CAS của document không phải global timestamp, không phải cursor trang và không cho phép “quay lại trạng thái các document ở thời điểm CAS_X”. `@Version` của Spring Data cũng chỉ liên quan đến optimistic locking ở mức entity/document.

## 12. Hai query của một Page không mặc nhiên cùng thời điểm

Với `Page<T>`, một implementation có thể cần:

1. SQL++ lấy dữ liệu trang bằng `ORDER BY/LIMIT/OFFSET`.
2. SQL++ `COUNT(1)` để tính tổng số phần tử khớp điều kiện.

Không phải mọi Page luôn chạy đúng hai query: Spring Data có thể bỏ truy vấn count trong một số trường hợp suy được tổng, hoặc repository tùy chỉnh có chiến lược khác. Nhưng nếu có hai lần đọc riêng, có khả năng dữ liệu đổi giữa chúng.

Ngay cả khi dùng `REQUEST_PLUS` cho cả hai, kết quả không tự buộc chúng nhìn **cùng một thời điểm**. Cần định nghĩa yêu cầu sản phẩm:

- Danh sách quản trị: tổng “gần đúng ở thời điểm hiện tại” có thể đủ.
- Kế toán/quyết toán: tổng và danh sách có thể cần được tạo bởi **một job/chế độ snapshot** có điều kiện nhất quán rõ.
- Feed thời gian thực: không cần total, chỉ có `hasNext` hoặc “Tải thêm”.
- Search có filter thay đổi: khi filter thay đổi, phải bắt đầu lại từ trang đầu hoặc tạo cursor mới.

Đừng ghi `totalPages` lên UI như một con số bất biến nếu dữ liệu đang thay đổi liên tục.

## 13. API nên công khai loại nhất quán nào?

Không có một kiểu phân trang tối ưu cho mọi nghiệp vụ. Có thể phân thành ba hợp đồng:

| Hợp đồng | Ý nghĩa | Công cụ thường phù hợp |
| --- | --- | --- |
| **Live list** | Mỗi lần gọi phản ánh trạng thái mới theo consistency đã chọn; có thể trùng/bỏ sót giữa trang | Pageable + offset hoặc cursor với lưu ý |
| **Continue after cursor** | Đi tiếp theo bộ khóa của hàng cuối; giảm dịch trang do chèn/xóa phía trước | Keyset/seek theo khóa sort ổn định |
| **Fixed export/snapshot** | Duyệt một tập và/hoặc dữ liệu ở một mốc xác định, có thể resume/retry | Vật hóa tập, versioned data, pipeline snapshot được thiết kế riêng |

### Hợp đồng Live list

Ví dụ bảng vận hành có nút “Làm mới”. Chấp nhận danh sách thay đổi là hợp lý; người dùng muốn nhìn trạng thái hiện tại. UI có thể hiển thị thời điểm tải trang và cho phép refresh. Nếu dùng offset, cần chấp nhận khả năng lặp/bỏ sót khi chuyển trang; nếu dùng keyset, vẫn phải chấp nhận các mutation làm thay đổi khóa sort.

### Hợp đồng Continue after cursor

Feed “Tải thêm” phù hợp nếu người dùng muốn đọc các hàng đứng sau mốc cuối. API trả một opaque cursor và `hasNext`. Nó không cần total và thường không cần nhảy thẳng đến trang 200.

Cần quy định nếu document đã đọc được chỉnh sửa, nếu filter thay đổi, hoặc nếu cursor hết hạn thì phải làm gì.

### Hợp đồng Fixed export/snapshot

Nếu phải đảm bảo đọc **chính xác tập ban đầu**, ví dụ kiểm kê hoặc xử lý số liệu cần đối soát, nên xem xét một snapshot/export job:

1. Xác định và ghi lại bộ tiêu chí lọc, quyền và thời điểm/mốc nghiệp vụ.
2. Tạo **tập ID** hoặc các bản ghi/version bất biến trong một nơi lưu bền vững theo chính sách dự án.
3. Duyệt tập đã vật hóa qua các lô có checkpoint; không dựa vào offset trên collection sống.
4. Nếu cần **giá trị field tại thời điểm snapshot**, phải lưu cả giá trị hoặc có versioned/history data; chỉ lưu ID không đủ khi body bị sửa/xóa.
5. Xây cơ chế retry idempotent, hết hạn snapshot, phân quyền, quota và dọn dữ liệu tạm.

Tính nhất quán của **quá trình tạo snapshot** cũng cần được thiết kế và kiểm chứng. Việc tuần tự quét một collection đang biến động để lấy ID **không tự tạo** snapshot chuẩn. Cơ chế transaction của Couchbase cần được cân nhắc theo khả năng và phạm vi giao dịch; không coi một transaction mở suốt nhiều HTTP request là giải pháp mặc định cho job dài.

## 14. Thế nào là duyệt “đúng một lần”?

Cụm “không trùng, không bỏ sót” có thể mang ít nhất ba ý nghĩa:

1. **Không lặp ID trong response của phiên duyệt.**
2. **Không bỏ sót document nào có mặt trong một tập mục tiêu.**
3. **Không xử lý một sự kiện/record hai lần sau retry hoặc sự cố.**

Một cursor dựa trên sort key **không tự chứng minh cả ba** trong dữ liệu biến động.

Ví dụ job tính phí có thể gặp timeout sau khi cập nhật một số document. Khi retry từ checkpoint, một số document có thể bị xử lý lại. Dù keyset ổn định, thao tác ghi phải có **idempotency key**, trạng thái đã xử lý, transaction phù hợp hoặc cách đối soát nghiệp vụ để tránh tính phí hai lần.

Nếu muốn “đúng một lần” theo snapshot của tập ban đầu, cần định nghĩa:

- Tập mục tiêu hình thành ở thời điểm/mốc nào?
- Tại sao document mới tạo sau đó không được tính?
- Document bị xóa/hết hạn trước khi xử lý có được tính không?
- Giá trị nào của một document đã chỉnh sửa sẽ được dùng?
- Khi retry, làm sao tránh tác động lặp?
- Có giới hạn thời gian, số phần tử và cách dọn checkpoint không?

Những câu hỏi này quan trọng hơn việc chọn `Page` hay `Slice` trong repository.

## 15. Khi nào cần de-duplication phía client?

Một giao diện live list có thể muốn **không hiển thị trùng ID** trong phiên cuộn. Một lựa chọn là lưu tập ID đã thấy ở client:

~~~text
seenIds = {}
for each received row:
    if id not in seenIds:
        append row to view
        add id to seenIds
~~~

Cách này **chặn một số lần lặp trong UI**, nhưng không sửa được việc thiếu hàng. Nếu 20 row của trang tiếp theo có 5 ID đã thấy, sau loại trùng chỉ còn 15 row hiển thị. Không được suy rằng “đã nhận 20 rows” tức là đã nhận 20 **hàng mới**.

Chi phí của tập `seenIds` tăng theo thời gian phiên cuộn; cần giới hạn dung lượng hoặc chính sách xóa/làm mới. Với danh sách vô hạn hoặc hàng triệu document, bộ nhớ này có thể đáng kể.

**Quan trọng:** de-duplication theo ID ở UI không thay thế idempotency trong xử lý nghiệp vụ. Chặn hiển thị lặp không bảo vệ khỏi gọi thanh toán/lưu dữ liệu lặp.

## 16. Cursor cần mang đúng ngữ cảnh bộ lọc và thứ tự

Một cursor dựa trên (`createdAt`, `id`) chỉ có ý nghĩa trong một truy vấn có cùng:

- Bucket/scope/collection hoặc phạm vi nguồn dữ liệu.
- Tenant, type discriminator, quyền truy cập và filter nghiệp vụ.
- Thứ tự `ORDER BY`, cả danh sách khóa và hướng ASC/DESC.
- Quy tắc xử lý `NULL`/`MISSING`, chuẩn hóa timestamp và collation.
- Mức giới hạn/trang hoặc chính sách phiên nếu API có ràng buộc đó.

Một API có thể trả opaque token:

~~~json
{
  "items": [
    {
      "id": "customer::42",
      "fullName": "Trần Minh",
      "createdAt": "2026-11-20T08:15:00.000Z"
    }
  ],
  "hasNext": true,
  "nextCursor": "eyJ2IjoxLCJ..."
}
~~~

Token ký HMAC hoặc được lưu dạng server-side reference có thể chứa payload logic:

~~~json
{
  "v": 1,
  "tenant": "tenant-01",
  "sort": "createdAt_desc__id_desc",
  "filterHash": "hash-of-canonical-filter",
  "after": {
    "createdAt": "2026-11-20T08:15:00.000Z",
    "id": "customer::42"
  },
  "expiresAt": "2026-11-25T03:00:00Z"
}
~~~

Ví dụ chỉ minh họa cấu trúc; Base64URL **không phải mã hóa bí mật**, và chuỗi token mẫu không phải chữ ký thực tế. Nếu chứa thông tin nhạy cảm, cần tối giản dữ liệu hoặc mã hóa đúng cách.

Backend phải xác minh chữ ký/hạn dùng, tenant từ context xác thực, filter/sort và kiểu giá trị; cursor **không cấp quyền truy cập**. Khi filter hoặc sort đổi, client bắt đầu lại từ trang đầu thay vì tái dùng cursor cũ.

Đặt ngoặc predicate seek khi có `OR` để không vô tình bỏ filter tenant:

~~~sql
WHERE c.tenantId = $tenantId
  AND c.active = TRUE
  AND (
      c.createdAt < $afterCreatedAt
      OR (
          c.createdAt = $afterCreatedAt
          AND META(c).id < $afterId
      )
  )
~~~

Nếu thiếu ngoặc, một nhánh `OR` có thể vượt qua điều kiện tenant và gây sai dữ liệu, thậm chí rò rỉ kết quả của tenant khác.

## 17. NULL, MISSING, kiểu dữ liệu và thay đổi schema

Ngay cả khi không có mutation, thứ tự có thể khó tái lập nếu field sort không nhất quán:

- Một document có `createdAt` dạng string chuẩn.
- Document khác có `createdAt: null`.
- Document khác thiếu hẳn `createdAt` (`MISSING`).
- Document cũ có timestamp kiểu number.
- Một số document lưu timezone/precision khác nhau.

SQL++ sắp xếp các giá trị theo quy tắc so sánh dữ liệu; predicate range trong keyset không tự bao quát các nhóm `NULL`/`MISSING` như một biểu thức sort đã chuẩn hóa.

Một chính sách đơn giản là chỉ dùng cursor trên các document có sort key hợp lệ:

~~~sql
WHERE c.tenantId = $tenantId
  AND c.createdAt IS NOT MISSING
  AND c.createdAt IS NOT NULL
~~~

Nhưng như vậy document thiếu ngày tạo bị **loại khỏi tập kết quả**. Nếu nghiệp vụ phải trả cả chúng, cần thiết kế normalized key hoặc một cơ chế phân nhóm/seek bao quát đầy đủ trường hợp thiếu/null.

Nếu sort theo tên người Việt, thứ tự chuỗi SQL++ có thể không khớp kỳ vọng ngôn ngữ về dấu, chữ hoa/thường và Unicode normalization. Hãy thống nhất khóa sort trước khi triển khai cursor, và chú ý **schema migration thay đổi quy tắc sort** có thể làm cursor cũ mất hiệu lực.

## 18. Dữ liệu vừa ghi, reactive và `CouchbaseTemplate`

Spring Data Couchbase cho phép nhiều đường truy cập:

- Repository query/`Pageable` cho danh sách entity hoặc projection.
- `CouchbaseTemplate` cho thao tác query/mapping phù hợp với model và phiên bản.
- Couchbase Java SDK `Cluster.query(...)` cho SQL++ tường minh, custom DTO.
- Reactive repository, `ReactiveCouchbaseTemplate` hoặc SDK reactive cho WebFlux.

**Không đường nào tự biến nhiều request độc lập thành một snapshot cố định.**

### Reactive không sửa ngữ nghĩa phân trang

Reactive giúp tránh chiếm thread khi chờ IO và hỗ trợ xử lý bất đồng bộ. Nhưng nếu hai page được query ở hai thời điểm khác nhau, chúng vẫn có thể nhìn dữ liệu khác nhau. `Flux`/`Mono` không tự bảo đảm tập document không bị thêm/xóa hoặc vị trí sort không bị đổi.

Nếu cần “load more”, dùng query reactive với limit hợp lý, cursor và filter cố định; không gọi `block()` trong event-loop. Tránh khởi chạy nhiều request các trang khác nhau song song rồi ghép kết quả chỉ dựa trên thứ tự hoàn thành: completion order của request không phải `ORDER BY` của dataset.

### Khi đọc để chỉnh sửa

Nếu một hàng trong danh sách có nút “Sửa”, nên dùng document ID để đọc lại bản hiện tại theo đường KV/repository phù hợp. Khi cần optimistic locking, giữ CAS/`@Version` từ lần đọc cho form và mutation kèm điều kiện đó. Đây là **vấn đề tránh lost update của một document**, không phải bảo đảm đồng nhất của hàng chục trang danh sách.

## 19. Những lỗi thiết kế dễ mắc

| Phát biểu/hiện tượng | Vì sao chưa đúng | Hướng xử lý |
| --- | --- | --- |
| “Đã `ORDER BY` nên các trang không thể trùng” | Thứ tự mỗi query không chặn insert/delete giữa request | Chọn cursor hoặc chấp nhận live list |
| “Thêm `META().id` sẽ cố định trang 2” | ID chỉ phân xử giá trị sort trùng | Tách tie-breaker khỏi vấn đề snapshot |
| “`Slice` sẽ không bị offset drift” | `Slice` vẫn có thể dùng `PageRequest` với offset | Dùng keyset nếu cần duyệt tiếp theo giá trị |
| “Keyset không bao giờ bỏ sót” | Document có thể đổi sort key, filter hoặc biến mất | Khóa sort bất biến, watermark có giới hạn, snapshot khi cần |
| “`REQUEST_PLUS` giữ nguyên mọi trang” | Nó liên quan mức mới của index trong mỗi query | Không đồng nhất scan consistency với snapshot nhiều request |
| “Có `totalPages` nên trang cuối luôn tồn tại” | Tổng thay đổi theo mutation/TTL | UI xử lý trang rỗng và reset khi cần |
| “Watermark theo `createdAt` là snapshot” | Backfill, delete, update, TTL vẫn thay tập hoặc giá trị | Vật hóa tập/phiên bản nếu yêu cầu nghiêm ngặt |
| “CAS có thể đánh dấu trang” | CAS là token version của document | Cursor dùng bộ khóa sort |
| “Client lọc ID trùng thì không thể bỏ sót” | Chặn trùng không khôi phục ID đã bị skip | Xác định ngữ nghĩa và cơ chế đọc đúng |
| “Dùng repository `save` trên DTO phân trang” | Projection có thể thiếu field/metadata | Đọc entity đầy đủ hoặc dùng mutation riêng có CAS |
| “COUNT và dữ liệu trang luôn ở cùng thời điểm” | Hai query riêng có thể thấy tập khác nhau | Chấp nhận live semantics hoặc thiết kế snapshot |
| “Lấy index plan một lần là đủ” | Optimizer, dữ liệu và workload biến động | Benchmark với query profile và dữ liệu gần production |

## 20. Kiểm thử cạnh tranh: đừng chỉ test dữ liệu đứng yên

Một bài test pagination thường seed 100 bản ghi, chạy `page=0`, `page=1` và kiểm tra không lặp. Điều đó **chưa đủ** cho hệ thống có nhiều writer.

Nên viết integration test với Couchbase thật, xen mutation giữa các lần query:

### Test A — Chèn trước ranh giới offset

~~~text
Given  thứ tự A B C D E F G, size=3
When   query OFFSET 0 -> A B C
And    thêm X đứng trước A
And    query OFFSET 3
Then   quan sát C có thể xuất hiện lại
~~~

### Test B — Xóa trước ranh giới offset

~~~text
Given  thứ tự A B C D E F G, size=3
When   query OFFSET 0 -> A B C
And    xóa B
And    query OFFSET 3
Then   quan sát D có thể bị bỏ qua
~~~

### Test C — Keyset với khóa sort bất biến

~~~text
Given  thứ tự A B C D E F G, size=3
When   query trang đầu -> A B C, cursor=C
And    thêm X đứng trước A
And    query sau cursor C
Then   các hàng có khóa đứng sau C vẫn được tìm theo predicate
And    X không tự chen vào trang kế tiếp
~~~

Kết luận chỉ đúng trong giả định **sort key và filter của các hàng cần duyệt không đổi**.

### Test D — Keyset với sort key thay đổi

~~~text
Given  thứ tự theo updatedAt DESC
When   đọc trang đầu và giữ cursor
And    đổi updatedAt của một document đã xem
And    document chuyển xuống phía sau cursor
Then   document đó có thể xuất hiện lại
~~~

### Test E — TTL và count

~~~text
Given  có document sắp hết hạn TTL
When   query trang đầu
And    chờ document hết hạn
And    query trang kế tiếp và COUNT
Then   tổng và trang có thể thay đổi
~~~

### Test F — Scan consistency

1. Ghi một document mới bằng KV hoặc repository.
2. Query SQL++ ngay sau đó với scan consistency đã cấu hình.
3. Ghi nhận document xuất hiện khi nào, độ trễ và trường hợp chưa phản ánh mutation.
4. So sánh chính sách `NOT_BOUNDED`/`REQUEST_PLUS` theo hỗ trợ của SDK/Server.
5. Không kết luận từ việc query thấy dữ liệu mới rằng nhiều query tiếp theo cùng một snapshot.

Các bài test trên cần phân biệt **bất định do mutation** với **thiếu thứ tự toàn phần** và **độ trễ index**. Nên kiểm tra ba yếu tố riêng rẽ để định vị đúng nguyên nhân.

## 21. Kế hoạch đo hiệu năng và tính đúng

Với dữ liệu 10.000, 100.000 và 1.000.000 document, có thể đo:

| Chỉ số | Mục đích |
| --- | --- |
| `p50`, `p95`, `p99` query latency | Độ trễ trong tải thật |
| Số index entries scanned | Mức công việc Index Service |
| Có operator `Fetch`/`Order` hay không | Chi phí đọc body và sort |
| Response bytes | Payload do projection và page size |
| Số query `COUNT` mỗi request | Chi phí bổ sung của Page |
| Tỷ lệ row trùng ID qua các trang | Biểu hiện drift khi biến động |
| Số ID trong tập mục tiêu chưa được trả | Kiểm tra bỏ sót khi có định nghĩa tập mục tiêu |
| Thời gian snapshot/export | Chi phí của yêu cầu nhất quán mạnh hơn |
| Timeout, retry và sai lệch sau retry | Rủi ro vận hành |

Dùng `EXPLAIN` cho câu SQL++ để xem kế hoạch, nhưng cần chạy profiling/metric thực tế để kết luận latency và số hàng đã quét. So sánh offset và keyset trên cùng filter, sort, projection, index và consistency.

Nếu muốn đo **bỏ sót** trên dataset thay đổi, phải định nghĩa rõ tập mục tiêu là gì. Không thể đếm “thiếu so với snapshot T0” khi chưa có cách ghi nhận trạng thái T0; dùng một snapshot test fixture hoặc tập ID nền được giữ cố định để đối chứng.

## 22. Bảng quyết định cho sản phẩm

| Yêu cầu thật sự | Lựa chọn khởi đầu | Điều phải nói rõ với người dùng |
| --- | --- | --- |
| Bảng quản trị, có nhảy trang số | `Pageable` + `ORDER BY` toàn phần | Dữ liệu và total có thể đổi giữa các trang |
| Feed cuộn liên tục | Keyset/cursor, `pageSize+1` | Hàng thêm trước cursor có thể không xuất hiện trong phiên cũ |
| Danh sách “live” có nhiều chỉnh sửa | Cursor theo khóa ổn định hoặc refresh-first UX | Sort/filter thay đổi vẫn gây dịch chuyển |
| Danh sách chỉ cần `hasNext` | `Slice` hoặc cursor custom | `Slice` mặc định không có snapshot |
| Cần tổng chính xác theo một bộ lọc | `COUNT` phù hợp với filter | Query count có thể tốn chi phí và không cùng thời điểm dữ liệu |
| Duyệt toàn bộ để xử lý nghiệp vụ | Job lô với checkpoint và idempotency | Không dùng page number như bằng chứng xử lý đúng một lần |
| Báo cáo/kiểm kê yêu cầu trạng thái “as of T0” | Snapshot/versioned data/vật hóa kết quả | Chi phí lưu trữ, tạo snapshot, hạn dùng và vận hành cần thiết kế |
| Đọc/sửa một document | KV get theo ID + CAS/`@Version` | CAS xử lý cạnh tranh của document, không phải snapshot danh sách |

Khi chọn giao diện, cần hỏi rõ:

- Người dùng có cần quay lại một trang số bất kỳ hay chỉ cuộn tiếp?
- Có chấp nhận hàng mới xuất hiện và hàng cũ biến mất trong phiên không?
- Có cần tổng chính xác và nội dung cùng “as of” một mốc không?
- Nếu item bị sửa trong lúc đang xem, UI phải refresh, giữ giá trị cũ hay cảnh báo?
- Nếu request bị timeout/retry, cần tránh tác động lặp ở mức nghiệp vụ không?
- Chi phí snapshot, index và lưu trữ có tương xứng với yêu cầu nhất quán không?

## 23. Bài tập thực hành

Xây dựng API danh sách `GET /customers` có hai chế độ:

**Chế độ 1 — live list theo trang số**

~~~http
GET /customers?page=0&size=20&sort=createdAt,desc
~~~

- Dùng Spring Data `Pageable` và một sort toàn phần được kiểm chứng ở SQL++.
- Giới hạn page size và offset tối đa.
- Công khai rằng total và nội dung có thể thay đổi giữa request.
- Test insert/delete giữa hai trang, nhận diện lặp/bỏ sót.
- Trường hợp trang cuối biến mất phải trả response hợp lý, không mặc định lỗi hệ thống.

**Chế độ 2 — feed với cursor**

~~~http
GET /customers/feed?limit=20&cursor=...
~~~

- Dùng SQL++ keyset trên (`createdAt DESC`, `META(c).id DESC`).
- Lấy tối đa 21 hàng để quyết định `hasNext`.
- Cursor từ hàng cuối hiển thị, không từ hàng look-ahead.
- Giữ nguyên tenant, filter, sort và quyền giữa các trang.
- Thử update field sort và một document hết hạn TTL; ghi lại giới hạn snapshot.
- Thử watermark: đánh giá điều nó chặn được và trường hợp backfill/delete vẫn sai.

**Mở rộng — export cần tập cố định**

- Viết đặc tả một job tạo danh sách ID hoặc phiên bản dữ liệu được vật hóa.
- Quy định mốc snapshot, phạm vi tenant, TTL của kết quả snapshot và checkpoint.
- Xác định có cần giá trị **tại T0** hay chỉ cần định danh document có mặt ở T0.
- Thiết kế retry idempotent và kiểm thử mutation trong lúc tạo snapshot.
- So sánh độ phức tạp với feed live để thấy vì sao không nên áp dụng snapshot cho mọi UI.

### Câu hỏi tự kiểm tra

1. Vì sao `ORDER BY createdAt, id` không ngăn được offset drift khi insert?
2. Sau khi xóa một document đứng trước offset, vì sao có thể bỏ sót hàng?
3. Dùng keyset với sort bất biến giúp tránh vấn đề nào, và chưa giúp được vấn đề nào?
4. Nếu một document đã xem thay `updatedAt` để chuyển xuống sau cursor, điều gì có thể xảy ra?
5. `REQUEST_PLUS` giải quyết vấn đề gì? Nó có tạo snapshot cho 10 request phân trang không?
6. Vì sao `Page.getTotalElements()` không phải cam kết tổng bất biến?
7. Vì sao `createdAt <= cutoff` vẫn có thể nhận document backfill và không cứu được document đã xóa?
8. Chỉ lưu danh sách ID tại T0 đã đủ tái tạo **giá trị field tại T0** chưa?
9. CAS/`@Version` dùng trong trường hợp nào, tại sao không dùng làm cursor?
10. Tại sao client lọc ID trùng vẫn không chứng minh đã duyệt đủ tập ban đầu?
11. Những điều kiện tenant/filter/sort nào phải được gắn với cursor?
12. Khi nghiệp vụ cần xử lý đúng một lần sau retry, cần thêm gì ngoài phân trang?

## 24. Tài liệu chính thức

- [Spring Data Couchbase — Couchbase Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): repository query, phân trang, `Pageable` và `@Query`.
- [Spring Data — Query Methods](https://docs.spring.io/spring-data/couchbase/reference/repositories/query-methods-details.html): sự khác nhau giữa `Page`, `Slice`, `List`, metadata và đếm tổng.
- [Couchbase SQL++ — ORDER BY](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/orderby.html): quy tắc thứ tự của truy vấn.
- [Couchbase SQL++ — LIMIT](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/limit.html): giới hạn số kết quả.
- [Couchbase SQL++ — OFFSET](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/offset.html): vị trí bỏ qua trong kết quả.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): query parameters, scan consistency và result rows.
- [Couchbase Server — Index Pushdowns](https://docs.couchbase.com/server/current/indexes/index_pushdowns.html): điều kiện tối ưu `ORDER BY/LIMIT/OFFSET` tại index.
- [Couchbase Server — Transactions](https://docs.couchbase.com/server/current/learn/data/transactions.html): phạm vi và semantics của transaction; không đồng nhất với snapshot phân trang lâu dài.

**Lưu ý theo phiên bản:** cú pháp/query optimization, khả năng của `CouchbaseTemplate`, reactive repository và các lựa chọn consistency cần đối chiếu với **Couchbase Server, Java SDK và Spring Data Couchbase** được khóa trong dự án. Bài này mô tả thiết kế và giới hạn ngữ nghĩa; không coi ví dụ như một cam kết rằng mọi phiên bản tự cung cấp snapshot qua nhiều request.

> **Ghi nhớ:** Phân trang là **cách chia kết quả truy vấn**, không phải cơ chế giữ nguyên lịch sử dữ liệu. `ORDER BY` có khóa phụ định nghĩa thứ tự; keyset giúp tiếp tục theo giá trị khóa thay vì vị trí; scan consistency tác động mức mới của index; CAS bảo vệ một document khi ghi. Nếu sản phẩm cần **cùng tập và cùng giá trị dữ liệu ở một thời điểm**, phải có chiến lược snapshot/versioned data được thiết kế và kiểm chứng riêng.

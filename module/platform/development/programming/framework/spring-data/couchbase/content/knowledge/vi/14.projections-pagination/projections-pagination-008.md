# Phân trang theo khóa bằng điều kiện SQL++ tường minh

Trong ứng dụng dùng **Spring Data Couchbase**, cách phân trang quen thuộc là truyền `Pageable` với số trang rồi thực thi SQL++ chứa `LIMIT` và `OFFSET`. Khi dữ liệu lớn hoặc danh sách thường xuyên có bản ghi mới, việc “bỏ qua N hàng đầu tiên” vừa có thể tốn tài nguyên vừa khiến các hàng bị lặp/bỏ sót khi vị trí của chúng thay đổi.

**Phân trang theo khóa (keyset/seek pagination)** giải quyết một phần vấn đề đó bằng cách lưu **bộ giá trị sắp xếp của hàng cuối đã hiển thị**. Trang sau không bắt đầu từ chỉ số vị trí, mà dùng một điều kiện `WHERE` tường minh để chọn những hàng **đứng sau khóa đó** theo cùng thứ tự `ORDER BY`.

Bài học thuộc chương **Chiếu và phân trang** của module **SPRING_DATA_COUCHBASE**. Chúng ta xây dựng cách tiếp cận từ SQL++ đến Java SDK, custom repository, projection, index, scan consistency và API reactive để giữ **đúng thứ tự, đúng cursor, đúng phạm vi dữ liệu** khi vận hành.

Sau khi học, bạn có thể:

1. Viết điều kiện keyset cho một khóa và nhiều khóa, kể cả tổ hợp `ASC`/`DESC`.
2. Chọn khóa phân xử duy nhất như `META(c).id`, xử lý các trường sắp xếp không duy nhất.
3. Dùng `LIMIT pageSize + 1` để tính `hasNext` mà không cần truy vấn đếm tổng.
4. Ánh xạ result row SQL++ sang DTO và tạo cursor từ **hàng cuối thực sự trả cho client**.
5. Thiết kế cursor an toàn, ràng buộc với bộ lọc/tenant/sort và chống sử dụng sai hoặc sửa token.
6. Đánh giá rủi ro của `NULL`, `MISSING`, cập nhật khóa sắp xếp, TTL và dữ liệu đọc từ index chưa kịp đồng bộ.
7. Đọc `EXPLAIN` để kiểm tra index, `Fetch`, `Order` và chi phí của predicate keyset.

> **Phân biệt thuật ngữ:** “Phân trang theo khóa” ở đây là *keyset pagination* dựa trên **bộ giá trị sort**. Nó **không giống** thao tác Couchbase KV `collection.get(documentId)` hay SQL++ `USE KEYS` để lấy trực tiếp một document đã biết ID.

## 1. Bối cảnh: từ trang số đến “Tải thêm”

Giả sử document ở bucket `shop`, scope `crm`, collection `customers` có body:

~~~json
{
  "fullName": "Trần Minh",
  "email": "minh@example.test",
  "active": true,
  "tenantId": "tenant-01",
  "createdAt": "2026-11-20T08:15:00.000Z"
}
~~~

Document key là `customer::42`, nằm ở Couchbase metadata.

API muốn trả khách hàng đang hoạt động, mới nhất trước, mỗi lần 20 hàng. Với offset pagination:

~~~sql
SELECT META(c).id AS id,
       c.createdAt AS createdAt,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.tenantId = $tenantId
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 20 OFFSET 20000;
~~~

Để trả trang bắt đầu sau 20.000 hàng, Query Engine có thể cần xử lý rất nhiều index entries hoặc hàng trung gian trước khi bỏ phần đầu. Index có thể giúp, nhưng `LIMIT 20` **không chứng minh toàn bộ truy vấn chỉ xử lý 20 hàng**.

Trong keyset pagination, client thay số trang bằng cursor:

~~~json
{
  "afterCreatedAt": "2026-11-20T08:15:00.000Z",
  "afterId": "customer::42"
}
~~~

Câu query cho trang kế tiếp tìm các document có bộ khóa sort **nhỏ hơn** bộ khóa này theo thứ tự `DESC`. Không cần `OFFSET`.

### Khi nào phù hợp?

| Nhu cầu giao diện | Giải pháp nên cân nhắc | Vì sao |
| --- | --- | --- |
| Feed “Tải thêm”, cuộn vô hạn | Keyset/cursor | Đi tới hàng sau khóa cuối, không cần biết tổng trang |
| Đồng bộ theo lô, xử lý tập lớn tuần tự | Keyset với checkpoint phù hợp | Tiếp tục từ mốc đã xử lý |
| Nhảy trực tiếp đến “trang 500” | Offset hoặc cơ chế điều hướng khác | Keyset cần cursor của vị trí trước đó |
| Báo cáo phải giữ nguyên tập dữ liệu trong toàn phiên | Snapshot/export riêng | Keyset **không tạo snapshot** khi dữ liệu biến động |
| Chỉ tìm một document đã biết ID | KV get hoặc `USE KEYS` | Không phải bài toán phân trang |

Keyset không mặc nhiên nhanh hơn offset ở mọi trường hợp. Hiệu quả phụ thuộc vào predicate, sort, index và kế hoạch Query Service.

## 2. Điều kiện đầu tiên: xác định một thứ tự toàn phần

Giả sử sort theo `createdAt DESC`. Hai khách hàng có thể có cùng timestamp do import cùng lúc hoặc timestamp chỉ chính xác đến mili-giây. Nếu chỉ dùng:

~~~sql
ORDER BY c.createdAt DESC
~~~

thì thứ tự giữa các hàng trùng thời điểm **không xác định**. Một cursor chỉ chứa `createdAt` sẽ không phân biệt được vị trí giữa nhóm này.

Giải pháp: bổ sung khóa duy nhất làm tiêu chí cuối.

~~~sql
ORDER BY c.createdAt DESC, META(c).id DESC
~~~

`META(c).id` lấy document key; nó khác `c.id`, vốn chỉ là một thuộc tính trong JSON body nếu tồn tại.

Trong một collection đơn nguồn, document key là duy nhất và thường ổn định. Tổ hợp (`createdAt`, `id`) vì vậy tạo thứ tự toàn phần cho các document trong tập lọc, giả sử kiểu và giá trị của `createdAt` được chuẩn hóa.

### Dữ liệu minh họa

Với thứ tự `createdAt DESC, id DESC`:

| Thứ tự | `createdAt` | Document key |
| ---: | --- | --- |
| 1 | 2026-11-20T10:00:00.000Z | `customer::109` |
| 2 | 2026-11-20T10:00:00.000Z | `customer::108` |
| 3 | 2026-11-20T10:00:00.000Z | `customer::107` |
| 4 | 2026-11-20T09:00:00.000Z | `customer::106` |
| 5 | 2026-11-19T18:00:00.000Z | `customer::105` |

Nếu page size bằng 2, trang đầu trả `109`, `108`. Cursor phải lưu (`2026-11-20T10:00:00.000Z`, `customer::108`), không chỉ timestamp.

**Chú ý phạm vi:** nếu `JOIN` hoặc `UNNEST` tạo nhiều row từ một document, `META(c).id` có thể lặp giữa các row; khi đó cần thêm khóa duy nhất cho **row kết quả**, không chỉ cho document nguồn.

## 3. Từ `ORDER BY` đến biểu thức `WHERE`

Điểm trung tâm của keyset pagination là **biểu thức so sánh theo thứ tự từ điển (lexicographic comparison)**.

Với hai khóa tăng dần:

~~~sql
ORDER BY c.fullName ASC, META(c).id ASC
~~~

một hàng đứng **sau** cursor (`lastName`, `lastId`) khi:

~~~sql
c.fullName > $lastName
OR (
    c.fullName = $lastName
    AND META(c).id > $lastId
)
~~~

Diễn giải: nếu tên lớn hơn, hàng chắc chắn đứng sau; nếu tên bằng nhau, xét tiếp document key.

Với hai khóa giảm dần:

~~~sql
ORDER BY c.createdAt DESC, META(c).id DESC
~~~

thì điều kiện sau cursor đảo chiều:

~~~sql
c.createdAt < $afterCreatedAt
OR (
    c.createdAt = $afterCreatedAt
    AND META(c).id < $afterId
)
~~~

Cách so sánh này không dựa vào số trang. Nó định nghĩa một **ranh giới trong thứ tự dữ liệu**.

### Công thức tổng quát cho hai khóa

Cho `ORDER BY k1 direction1, k2 direction2`, sau cursor (`v1`, `v2`):

~~~text
(k1 đứng sau v1 theo direction1)
OR
(k1 = v1 AND k2 đứng sau v2 theo direction2)
~~~

Phép “đứng sau” là:

- `>` khi khóa được sắp `ASC`;
- `<` khi khóa được sắp `DESC`.

Điều kiện này cần được dùng **cùng với** toàn bộ `WHERE` lọc nghiệp vụ như ở trang đầu, không được thay thế bộ lọc.

## 4. SQL++ hoàn chỉnh cho trang đầu

Đối với `createdAt DESC, id DESC`, giả định `createdAt` được lưu ở mọi document như chuỗi ISO-8601 UTC có độ dài và độ chính xác nhất quán.

~~~sql
SELECT META(c).id AS id,
       c.createdAt AS createdAt,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.tenantId = $tenantId
  AND c.active = TRUE
  AND c.createdAt IS NOT MISSING
  AND c.createdAt IS NOT NULL
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT $limit;
~~~

Với page size 20, truyền `limit = 21`. Kết quả có tối đa 21 hàng, nhưng API chỉ cho client thấy tối đa 20.

Phải trả `createdAt` và `id` (hoặc giữ chúng nội bộ trong mapper) vì ứng dụng cần tạo cursor. Nếu projection chỉ có `fullName`/`email` mà bỏ cả hai khóa sort, ứng dụng không đủ thông tin để dựng cursor trang sau.

### Vì sao query lọc `MISSING`/`NULL`?

Đây là một **chính sách dữ liệu có chủ đích** để điều kiện range `<` hoạt động trên tập timestamp có thể so sánh được. Truy vấn không tự giải quyết các trường sai kiểu JSON; application cần validation/migration tương ứng.

Nếu nghiệp vụ phải hiển thị cả document thiếu `createdAt`, không được âm thầm bỏ chúng. Cần thiết kế normalized sort key có fallback hoặc một biểu thức và thuật toán cursor bao quát đủ các nhóm `MISSING`/`NULL`.

## 5. SQL++ hoàn chỉnh cho trang sau

Sau khi client đã thấy hàng cuối có:

~~~json
{
  "id": "customer::108",
  "createdAt": "2026-11-20T10:00:00.000Z"
}
~~~

Trang kế tiếp dùng:

~~~sql
SELECT META(c).id AS id,
       c.createdAt AS createdAt,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.tenantId = $tenantId
  AND c.active = TRUE
  AND c.createdAt IS NOT MISSING
  AND c.createdAt IS NOT NULL
  AND (
      c.createdAt < $afterCreatedAt
      OR (
          c.createdAt = $afterCreatedAt
          AND META(c).id < $afterId
      )
  )
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT $limit;
~~~

Named parameters:

~~~json
{
  "tenantId": "tenant-01",
  "afterCreatedAt": "2026-11-20T10:00:00.000Z",
  "afterId": "customer::108",
  "limit": 21
}
~~~

Trang này có thể trả `customer::107` dù `createdAt` bằng cursor, vì khóa ID đứng sau theo hướng `DESC`. Nếu điều kiện chỉ là `c.createdAt < $afterCreatedAt` thì document `107` sẽ bị **bỏ sót**.

Tương tự, nếu dùng `<=` với timestamp mà không kết hợp khóa phụ, các hàng đã hiển thị có thể bị **lặp**.

### Các tính chất cần giữ giữa trang đầu và trang sau

- `FROM` trỏ vào cùng keyspace.
- Bộ lọc `tenantId`, `active` và mọi điều kiện phân quyền/loại document phải giống nhau.
- `ORDER BY` không đổi cả danh sách khóa lẫn hướng ASC/DESC.
- Cursor chứa giá trị của mọi khóa phân biệt thứ tự.
- Predicate keyset được đặt trong `WHERE` **trước** `ORDER BY`/`LIMIT`, không lọc ở Java sau khi đã cắt 20 hàng.
- Đặt `LIMIT pageSize + 1` để biết còn hàng tiếp hay không nếu API cần `hasNext`.

## 6. Ví dụ kiểm tra bằng tay với dữ liệu trùng khóa

Giả sử page size 2 và tập kết quả đã sắp xếp:

~~~text
1. createdAt=10:00, id=109
2. createdAt=10:00, id=108
3. createdAt=10:00, id=107
4. createdAt=09:00, id=106
5. createdAt=18:00 ngày trước, id=105
~~~

Trang đầu query `LIMIT 3` và nhận hàng `109`, `108`, `107`.

- Trả client: `109` và `108`.
- `hasNext = true` vì có hàng thứ ba.
- Cursor: (`10:00`, `108`), **không** phải (`10:00`, `107`).

Trang hai bắt đầu sau `108`. Query trả `107`, `106`, `105`:

- Trả client: `107` và `106`.
- `hasNext = true`.
- Cursor: (`09:00`, `106`).

Trang ba trả `105`, không có hàng dư; `hasNext = false` và `nextCursor = null` trong hợp đồng API minh họa.

Nếu cursor bị dựng từ hàng look-ahead (`107` ở trang đầu), hàng `107` sẽ không bao giờ được trả cho client. Đây là một lỗi off-by-one phổ biến.

| Trường hợp | Số hàng truy vấn nhận khi `pageSize = 2` | Nội dung API | `hasNext` |
| --- | ---: | --- | --- |
| Hết dữ liệu | 0 | Rỗng | false |
| Còn một hàng | 1 | Một hàng | false |
| Còn đúng hai hàng | 2 | Hai hàng | false |
| Còn ba hàng trở lên | 3 (do `LIMIT 3`) | Hai hàng đầu | true |

## 7. Hai khóa với chiều sắp xếp khác nhau

Không phải tất cả tiêu chí `ORDER BY` đều cùng hướng. Ví dụ danh sách xếp điểm cao trước, khi điểm bằng nhau thì ID tăng dần:

~~~sql
ORDER BY c.score DESC, META(c).id ASC
~~~

Điều kiện đi **sau** cursor (`lastScore`, `lastId`):

~~~sql
AND (
    c.score < $lastScore
    OR (
        c.score = $lastScore
        AND META(c).id > $lastId
    )
)
~~~

Dấu `<` của `score` và `>` của ID khác nhau vì hướng sắp xếp khác nhau.

| `ORDER BY` | Phần so sánh khóa 1 | Phần so sánh khóa 2 khi khóa 1 bằng nhau |
| --- | --- | --- |
| `k1 ASC, k2 ASC` | `k1 > v1` | `k2 > v2` |
| `k1 ASC, k2 DESC` | `k1 > v1` | `k2 < v2` |
| `k1 DESC, k2 ASC` | `k1 < v1` | `k2 > v2` |
| `k1 DESC, k2 DESC` | `k1 < v1` | `k2 < v2` |

Khi đổi chiều sort từ UI, **cursor cũ không còn hợp lệ**. Nó phải được tạo lại theo thứ tự mới; không chỉ đổi `ORDER BY` mà giữ predicate/keyset token cũ.

### Từ hai khóa lên ba khóa

Ví dụ:

~~~sql
ORDER BY c.tier ASC,
         c.createdAt DESC,
         META(c).id ASC
~~~

Điều kiện tương ứng:

~~~sql
AND (
    c.tier > $afterTier
    OR (
        c.tier = $afterTier
        AND c.createdAt < $afterCreatedAt
    )
    OR (
        c.tier = $afterTier
        AND c.createdAt = $afterCreatedAt
        AND META(c).id > $afterId
    )
)
~~~

Đây là biểu thức “so khóa đầu tiên khác cursor; nếu bằng thì chuyển sang khóa kế tiếp”. Với `n` khóa, ta có các nhánh so sánh theo thứ tự từ trái sang phải. Mỗi field thêm vào cursor cũng làm phức tạp index và logic kiểm thử. Không cần cho phép sort tùy ý nếu API thực tế chỉ có vài thứ tự được hỗ trợ.

## 8. Đặt điều kiện `WHERE` đúng và giữ nguyên bộ lọc

Truy vấn trang đầu:

~~~sql
WHERE c.tenantId = $tenantId
  AND c.active = TRUE
  AND c.type = "customer"
~~~

Trang sau **phải giữ nguyên** ba điều kiện trên và **thêm** predicate cursor:

~~~sql
WHERE c.tenantId = $tenantId
  AND c.active = TRUE
  AND c.type = "customer"
  AND (
      c.createdAt < $afterCreatedAt
      OR (
          c.createdAt = $afterCreatedAt
          AND META(c).id < $afterId
      )
  )
~~~

Không viết thiếu ngoặc theo dạng:

~~~sql
-- SAI: nhánh OR có thể bỏ qua tenant và active.
WHERE c.tenantId = $tenantId
  AND c.active = TRUE
  AND c.createdAt < $afterCreatedAt
  OR META(c).id < $afterId;
~~~

Do thứ tự ưu tiên toán tử, nhánh sau `OR` có thể nhận document nằm ngoài tenant hoặc không active. Đây không chỉ là bug phân trang, mà còn có thể gây **rò rỉ dữ liệu ngoài phạm vi truy cập**.

Nếu Spring Data lưu nhiều loại entity trong cùng collection, custom SQL++ còn cần điều kiện discriminator tương ứng. `#{#n1ql.filter}` dùng trong một số query entity của Spring Data Couchbase **không đồng nghĩa** query SDK viết tay tự được gắn type filter. Hãy dùng predicate đúng với mô hình dữ liệu thực tế.

## 9. `NULL`, `MISSING` và khác biệt về kiểu dữ liệu

Couchbase là document database; một field có thể có giá trị, là `NULL` hoặc hoàn toàn không có trong document (`MISSING`). Một query sort có thể đặt các trạng thái này trong một thứ tự, nhưng phép so sánh `>`/`<` trong `WHERE` **không tự lặp lại mọi quy tắc xếp vị trí của NULL/MISSING**.

Ví dụ không nên tự giả định rằng:

~~~sql
WHERE c.createdAt < $afterCreatedAt
~~~

sẽ nhận đủ các row `NULL`/`MISSING` đúng như `ORDER BY`. Đối với dữ liệu thời gian, nên quy định:

- `createdAt` bắt buộc khi tạo document.
- Lưu dạng thống nhất: timestamp theo số hoặc chuỗi ISO-8601 UTC **chuẩn hóa cùng precision**.
- Không trộn string, number, null và thiếu field trong cùng một khóa sort khi chưa có chính sách.
- Nếu có tài liệu cũ thiếu trường, migration hoặc định nghĩa normalized sort expression phù hợp.
- Dùng cùng biểu thức chuẩn hóa trong `ORDER BY`, cursor predicate và index nếu có.

Ví dụ `WHERE c.createdAt IS NOT MISSING AND c.createdAt IS NOT NULL` đã **loại** document không có timestamp. Chỉ làm vậy nếu hợp đồng nghiệp vụ cho phép; đừng gọi đó là “giải pháp chung” khi sản phẩm bắt buộc hiển thị mọi bản ghi.

### Sắp xếp chuỗi và ngôn ngữ

Với `fullName` tiếng Việt, thứ tự SQL++ theo chuỗi có thể khác mong đợi về dấu, hoa/thường và Unicode normalization. Nếu nghiệp vụ yêu cầu thứ tự ngôn ngữ tự nhiên, cần khóa sort chuẩn hóa hoặc cơ chế collation được thiết kế rõ ràng. Không dùng cursor theo tên gốc khi backend và client có thể hiểu thứ tự khác nhau.

### Trường sort thay đổi

`createdAt` thường phù hợp hơn `updatedAt` cho feed vì có thể giữ nguyên sau khi tạo. Nếu sort theo `updatedAt` hoặc `score`, cập nhật có thể chuyển document qua ranh giới cursor. Ngay cả điều kiện keyset hoàn toàn đúng cũng có thể **lặp hoặc bỏ sót** document trên một chuỗi request khi khóa sort thay đổi.

## 10. Java SDK: repository adapter có cursor tường minh

Với Spring Data Couchbase, `Pageable`/`PageRequest` là cơ chế tốt cho phân trang theo số trang. Nhưng điều kiện keyset có thể phức tạp và cần kiểm soát `META(c).id`. Khi đó một **custom repository adapter** sử dụng Couchbase Java SDK là lựa chọn rõ ràng.

Định nghĩa read model và token logic:

~~~java
import java.util.List;

public record CustomerCard(
        String id,
        String createdAt,
        String fullName,
        String email) {}

public record SeekCursor(
        String createdAt,
        String documentId) {}

public record SeekPage(
        List<CustomerCard> items,
        boolean hasNext,
        SeekCursor nextCursor) {}
~~~

Một method synchronous minh họa:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import java.util.List;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

// Phương thức bên trong custom repository/service, nhận Cluster đã cấu hình.
public SeekPage findActiveCustomers(
        Cluster cluster,
        String tenantId,
        int pageSize,
        SeekCursor after) {

    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("pageSize must be 1..100");
    }
    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("tenantId is required");
    }
    if (after != null &&
            (after.createdAt() == null || after.createdAt().isBlank()
            || after.documentId() == null || after.documentId().isBlank())) {
        throw new IllegalArgumentException("Invalid cursor");
    }

    // Chỉ ghép các mảnh SQL++ cố định do ứng dụng định nghĩa.
    String seekPredicate = after == null ? "" : """
        AND (
            c.createdAt < $afterCreatedAt
            OR (
                c.createdAt = $afterCreatedAt
                AND META(c).id < $afterId
            )
        )
        """;

    String statement = """
        SELECT META(c).id AS id,
               c.createdAt AS createdAt,
               c.fullName AS fullName,
               c.email AS email
        FROM `shop`.`crm`.`customers` AS c
        WHERE c.tenantId = $tenantId
          AND c.active = TRUE
          AND c.createdAt IS NOT MISSING
          AND c.createdAt IS NOT NULL
        """ + seekPredicate + """
        ORDER BY c.createdAt DESC, META(c).id DESC
        LIMIT $limit
        """;

    JsonObject parameters = JsonObject.create()
            .put("tenantId", tenantId)
            .put("limit", pageSize + 1);

    if (after != null) {
        parameters.put("afterCreatedAt", after.createdAt());
        parameters.put("afterId", after.documentId());
    }

    QueryResult result = cluster.query(
            statement,
            queryOptions().parameters(parameters));

    List<CustomerCard> fetched = result.rowsAsObject()
            .stream()
            .map(row -> new CustomerCard(
                    row.getString("id"),
                    row.getString("createdAt"),
                    row.getString("fullName"),
                    row.getString("email")))
            .toList();

    boolean hasNext = fetched.size() > pageSize;
    List<CustomerCard> visible = hasNext
            ? fetched.subList(0, pageSize)
            : fetched;

    SeekCursor nextCursor = hasNext
            ? new SeekCursor(
                    visible.get(visible.size() - 1).createdAt(),
                    visible.get(visible.size() - 1).id())
            : null;

    return new SeekPage(visible, hasNext, nextCursor);
}
~~~

Mã trên là **ví dụ method và record** cần đặt vào các lớp/Java file phù hợp của dự án. `Cluster` đã được quản lý bởi cấu hình Couchbase, không tạo mới mỗi request.

Các lựa chọn quan trọng:

1. `pageSize` giới hạn trong khoảng 1–100 theo **chính sách ứng dụng minh họa**, không phải giới hạn của Couchbase.
2. Cả trang đầu và trang tiếp theo dùng **cùng filter, sort, select**.
3. `seekPredicate` chỉ có hai nhánh **chuỗi cố định** do developer kiểm soát; giá trị cursor/tenant/limit được truyền bằng named parameters. Không nối input người dùng thành SQL++.
4. `META(c).id AS id` cung cấp document key để ánh xạ và dùng làm tie-breaker.
5. `LIMIT pageSize + 1` dùng look-ahead; phần tử dư không trả cho client.
6. `nextCursor` lấy từ hàng cuối trong `visible`, **không** lấy từ phần tử cuối của `fetched`.
7. Không chạy `COUNT` chỉ để biết `hasNext`.
8. Nếu SDK gặp kết quả sai kiểu, lỗi query hoặc timeout, adapter phải có chiến lược xử lý lỗi, logging và mapping sang hợp đồng API.

**Không coi đoạn code là snapshot pagination:** khi document đổi `createdAt`, bị xóa hoặc được thêm giữa các request, tập kết quả vẫn biến động.

## 11. Ranh giới giữa `Pageable`, Spring Data repository và SQL++ custom

Spring Data repository có thể hỗ trợ:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    Page<Customer> findByActiveTrue(Pageable pageable);
}
~~~

Cách này có ý nghĩa khi UI **nhảy theo số trang** và framework quản lý phân trang kiểu offset/count theo những đường query được hỗ trợ.

Tuy nhiên, cursor keyset không chỉ là một `PageRequest.of(page, size)` khác. Nó cần điều kiện so sánh được sinh từ **giá trị của hàng cuối**. Để triển khai chính xác khi sort theo `META().id`, nên dùng custom repository/SDK hoặc `CouchbaseTemplate`/cơ chế query đã được kiểm chứng thay vì ép ý nghĩa cursor vào `Pageable` thông thường.

### `@Query` và `Pageable`

Với query entity:

~~~java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} AND active = $1")
Page<Customer> findActiveByQuery(boolean active, Pageable pageable);
~~~

Spring Data Couchbase có thể thêm `ORDER BY`, `LIMIT` và `OFFSET` dựa trên `Pageable`. Nếu bạn viết sẵn chúng trong inline query rồi truyền `Pageable`, SQL++ có thể bị **trùng clause** hoặc không còn đúng thứ tự mong đợi.

Với keyset, hãy chọn **một nơi duy nhất kiểm soát cả `WHERE` cursor và `ORDER BY/LIMIT`**. Khi query trả DTO/record tùy chỉnh, cũng phải kiểm thử ánh xạ alias và converter trên phiên bản Spring Data Couchbase thực tế.

### `CouchbaseTemplate` và reactive API

`CouchbaseTemplate` và `ReactiveCouchbaseTemplate` hữu ích cho entity mapping và một số truy vấn. Nhưng API query tùy chỉnh, converter và hỗ trợ DTO có thể khác theo phiên bản. Nếu dùng template thay SDK, hãy kiểm chứng:

- Query có đặt predicate keyset trước bước giới hạn không?
- `META(c).id` được ánh xạ đúng?
- Sort theo document ID có dùng metadata hay chỉ một field body `id`?
- Cursor được xây từ giá trị đã chọn trong result row?
- Reactive không vô tình gọi blocking query hoặc `block()` trên event-loop?

Reactive không thay đổi thuật toán so khóa và không tự cải thiện một query thiếu index.

## 12. Thiết kế cursor cho REST API

Thay vì cho client tự truyền ba tham số kỹ thuật, có thể cung cấp một cursor **opaque**.

Trang đầu:

~~~http
GET /customers/feed?limit=20
~~~

Kết quả rút gọn:

~~~json
{
  "items": [
    {
      "id": "customer::109",
      "createdAt": "2026-11-20T10:00:00.000Z",
      "fullName": "An",
      "email": "an@example.test"
    }
  ],
  "hasNext": true,
  "nextCursor": "eyJ2IjoxLCJ..."
}
~~~

Token ở ví dụ chỉ minh họa, không phải token đã được tạo bởi thuật toán ký thực tế. Khi client gửi:

~~~http
GET /customers/feed?limit=20&cursor=eyJ2IjoxLCJ...
~~~

backend giải mã cursor, xác minh rồi truyền các giá trị khóa sort vào query SQL++.

### Payload logic bên trong token

~~~json
{
  "v": 1,
  "after": {
    "createdAt": "2026-11-20T10:00:00.000Z",
    "id": "customer::108"
  },
  "sort": "createdAt_desc__id_desc",
  "tenant": "tenant-01",
  "filterHash": "sha256-of-canonical-filter",
  "pageSize": 20,
  "expiresAt": "2026-11-20T11:00:00Z"
}
~~~

Đây là **thiết kế gợi ý**, không phải schema bắt buộc của Couchbase. Ứng dụng có thể encode JSON theo Base64URL và dùng chữ ký HMAC để phát hiện token bị chỉnh sửa. Base64URL **không mã hóa bí mật**: người có token vẫn có thể giải mã nội dung. Nếu cursor chứa dữ liệu nhạy cảm, cần giảm payload hoặc dùng mã hóa/opaque server-side reference phù hợp.

Quy trình kiểm tra token:

1. Kiểm tra độ dài tối đa và định dạng token.
2. Xác minh chữ ký/HMAC bằng khóa bí mật do backend quản lý, dùng phép so sánh an toàn khi phù hợp.
3. Kiểm tra version `v` được hỗ trợ và hạn dùng.
4. Xác minh `tenant` từ token khớp với tenant đã xác thực, không lấy quyền từ token làm nguồn duy nhất.
5. Xác minh sort, filter hash và page size theo chính sách API; nếu thay bộ lọc, **cursor cũ vô hiệu**.
6. Kiểm tra `createdAt` đúng format và `id` hợp lệ; bind cả hai vào SQL++, không nối vào text query.
7. Nếu token sai/hết hạn, trả lỗi validation phù hợp và hướng dẫn bắt đầu lại từ trang đầu.

Đừng trả lời bằng cách dùng `afterId` trực tiếp từ user mà bỏ kiểm tra tenant hoặc ràng buộc filter. Cursor không phải cơ chế authorization.

## 13. Cursor có phải snapshot token không?

**Không.** Cursor keyset chỉ định một vị trí tương đối theo bộ khóa sort. Nó không khóa hay chụp ảnh một tập document tại thời điểm nào.

Các kịch bản:

| Thay đổi giữa hai request | Offset | Keyset |
| --- | --- | --- |
| Chèn document mới trước điểm đang duyệt | Có thể lặp hàng đã thấy vì offset bị dịch | Thường không lặp do dịch chỉ số, nhưng hàng mới trước cursor có thể không được đọc |
| Xóa document trước điểm đang duyệt | Có thể bỏ sót hàng do offset bị dịch | Không dựa vào vị trí số, nhưng document bị xóa đương nhiên biến mất |
| Sửa field sort của document đã hiển thị | Có thể lặp/bỏ sót | Vẫn có thể lặp/bỏ sót nếu document vượt qua ranh giới cursor |
| Sửa field không ảnh hưởng sort/filter | Vị trí thường không đổi | Vị trí thường không đổi; nội dung đọc được có thể khác |
| TTL làm document hết hạn | Tập kết quả dịch chuyển | Document hết hạn không còn trong tập duyệt |
| Index phản ánh thay đổi với độ trễ | Kết quả tùy consistency | Kết quả vẫn tùy consistency |

`REQUEST_PLUS` có thể giúp query chờ index bắt kịp các mutation đã hoàn tất tới thời điểm request theo cơ chế scan consistency, nhưng **không cung cấp snapshot chung** cho nhiều lần gọi HTTP.

### Cần xử lý một tập bất biến thì làm gì?

Nếu nghiệp vụ yêu cầu “duyệt chính xác mỗi document trong tập tại thời điểm 08:00”, hãy xem xét thiết kế riêng:

- Vật hóa danh sách ID hoặc snapshot/export theo yêu cầu.
- Gắn watermark và định nghĩa rõ thế nào là phần tử của tập.
- Dùng một cơ chế transaction/snapshot phù hợp với khả năng Server và giới hạn thời gian của công việc.
- Với job dài, lưu checkpoint và thiết kế idempotency để xử lý lại an toàn khi xảy ra lỗi.

Đừng hứa đạt tính đúng đắn snapshot chỉ bằng `ORDER BY` và keyset. CAS chỉ bảo vệ phiên bản của **một document** trong thao tác ghi có điều kiện, không phải mốc snapshot của toàn collection và không phù hợp làm khóa thứ tự cursor.

## 14. Đọc `EXPLAIN`: keyset có thực sự nhanh hơn?

Một query keyset tiêu biểu:

~~~sql
EXPLAIN
SELECT META(c).id AS id,
       c.createdAt AS createdAt,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.tenantId = "tenant-01"
  AND c.active = TRUE
  AND c.createdAt IS NOT MISSING
  AND c.createdAt IS NOT NULL
  AND (
      c.createdAt < "2026-11-20T10:00:00.000Z"
      OR (
          c.createdAt = "2026-11-20T10:00:00.000Z"
          AND META(c).id < "customer::108"
      )
  )
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 21;
~~~

Index ứng viên:

~~~sql
CREATE INDEX ix_customers_tenant_active_created
ON `shop`.`crm`.`customers` (
    tenantId,
    active,
    createdAt DESC
);
~~~

**Đây chỉ là index để khảo sát.** Việc tối ưu đầy đủ `ORDER BY createdAt DESC, META(c).id DESC` còn tùy cách optimizer xử lý document key, thứ tự và cấu trúc index; `fullName`/`email` không nằm trong khóa index đã khai báo nên Query Engine có thể cần `Fetch`. Nếu collection chứa nhiều loại document, cần cân nhắc discriminator filter và index tương ứng.

Khi dùng `EXPLAIN`/profiling, xem:

- **IndexScan:** có dùng index phù hợp với tenant, active và range trên `createdAt` không?
- **Span/range:** điều kiện cursor có thu hẹp vùng quét không, hay server vẫn xét rất nhiều entries?
- **`Order`:** query có sort thêm ở Query Service vì index chưa cung cấp đúng thứ tự không?
- **`Fetch`:** có phải đọc body để lấy projection/predicate không?
- **`covers`:** index có bao phủ các biểu thức cần đọc/sắp xếp không?
- **`Limit`:** được áp dụng sớm hay sau nhiều operator đắt tiền?
- **Số hàng quét và độ trễ:** thực tế ở trang đầu và sau cursor sâu, không chỉ số hàng output.

### So sánh công bằng với offset

Đối chứng:

~~~sql
EXPLAIN
SELECT META(c).id AS id,
       c.createdAt AS createdAt,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.tenantId = "tenant-01"
  AND c.active = TRUE
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 21 OFFSET 200000;
~~~

Cần giữ cùng tập dữ liệu, bộ lọc, sort, projection, index và scan consistency. So sánh scan entries, `Fetch`, `Order` và p95 latency. Với keyset có `OR`, optimizer có thể không chọn index tối ưu như dự kiến. Không kết luận “bỏ OFFSET nghĩa là query luôn O(pageSize)”.

### Index và chi phí ghi

Một index rộng có thể phục vụ tốt truy vấn đọc nhưng tăng dung lượng, thời gian cập nhật index và write amplification. Với Couchbase có nhiều workload, chọn index theo các sort thật sự phổ biến thay vì cho client sắp xếp theo hàng chục trường tùy ý.

## 15. Phân trang theo khóa, `Page` và `Slice` có thể kết hợp thế nào?

`Page<T>` cung cấp `getTotalElements()` và `getTotalPages()`. Điều này có thể buộc ứng dụng chạy một query `COUNT` cho toàn bộ filter, ngay cả khi trang dữ liệu chỉ lấy 20 hàng.

`Slice<T>` biết nội dung hiện tại và `hasNext()` mà không cần tổng, thường dựa trên look-ahead `pageSize + 1`.

Tuy nhiên:

- Một `Slice` được lấy bằng `PageRequest.of(page, size)` vẫn có thể dùng offset. `Slice` không đồng nghĩa **keyset**.
- Keyset thường dùng **cursor token riêng** thay cho `pageNumber`, nên DTO kết quả kiểu `SeekPage` trong ví dụ là dễ hiểu.
- Có thể tự gói kết quả keyset thành kiểu tương tự `Slice`, nhưng phải tránh ngụ ý rằng client có thể gọi `nextPageable()` để tìm đúng trang sau; `Pageable` mặc định không mang cursor.
- Trừ khi UI thật sự cần total chính xác, không chạy `COUNT` chỉ để xác định `hasNext`.

| Phương án | Xác định trang sau bằng | Tổng phần tử | Đặc điểm |
| --- | --- | --- | --- |
| `Page<T>` + `Pageable` | Số trang/offset | Có | Phù hợp UI trang số, count có thể đắt |
| `Slice<T>` + `Pageable` | Số trang/offset | Không | Tránh count, vẫn có thể tốn offset |
| Keyset/cursor custom | Bộ khóa sort của hàng cuối | Không mặc định | Tốt cho duyệt tiếp, cần filter/sort/cursor ổn định |
| KV get theo ID | Document key cụ thể | Không phải phân trang | Đọc một document đã biết key |

Đây là các hợp đồng khác nhau. Không nên tự đổi kiểu `Page` sang `Slice` rồi tuyên bố đã chuyển sang keyset.

## 16. Cursor và bảo mật truy vấn

SQL++ bind parameter xử lý **giá trị**, không thay thế kiểm tra quyền.

Các nguyên tắc:

1. Lấy tenant và quyền từ context xác thực, không từ cursor do người dùng gửi.
2. Predicate giới hạn dữ liệu (`tenantId`, loại entity, quyền) phải được áp dụng ở **mọi trang**.
3. Đặt ngoặc toàn bộ nhánh `OR` của keyset trước khi kết hợp với các điều kiện `AND`.
4. Dùng allowlist các sort cố định; không biến `sort=...` từ URL thành text SQL++ tùy ý.
5. Không dùng tên keyspace/field từ client để ghép câu query mà không xác minh.
6. Token cursor có thể bị đoán hoặc chỉnh sửa: dùng chữ ký, hạn dùng và ràng buộc filter khi cần.
7. Trả DTO đủ dùng, không trả entity chứa thông tin nhạy cảm nếu API không yêu cầu.
8. Nếu cần chính xác quyền trên từng document, kiểm tra predicate và chính sách authorization độc lập với cursor.

Một lỗi ngoặc `OR` trong `WHERE` có thể làm vượt qua bộ lọc tenant, đặc biệt nguy hiểm hơn lỗi lặp hàng.

## 17. Vận hành với Spring Data, TTL, CAS và reactive

### Projection

Có thể dùng interface projection hoặc DTO để giới hạn field Java được tiêu thụ. Nhưng chỉ khai báo DTO nhỏ **không bảo đảm** SQL++ gửi ít field; kiểm tra query thực tế, alias và `META(c).id`. Với keyset, phải giữ mọi khóa sort cần để tạo cursor.

### CAS

CAS dùng cho **optimistic locking** khi sửa document. Cursor keyset dùng thứ tự để đọc tiếp. Không đưa CAS vào predicate “đứng sau” vì CAS không phải thứ tự nghiệp vụ hay timestamp toàn cục. Nếu UI cho phép sửa trực tiếp mỗi hàng, CAS có thể được giữ **riêng** cho luồng cập nhật.

### TTL

Document hết hạn TTL có thể biến mất giữa hai lần lấy trang. Keyset không phục hồi document đã hết hạn, nhưng thường giảm hiện tượng offset bị dịch bởi việc xóa các hàng ở trước vị trí hiện tại. Hãy xác định rõ ứng dụng cho phép tập kết quả biến động đến đâu.

### Reactive

Couchbase Java SDK và Spring Data Couchbase có các API reactive, nhưng thuật toán `WHERE` keyset không đổi. Với WebFlux, dùng reactive query path, không gọi `block()` trên event-loop. Giới hạn page size dù có backpressure; một câu SQL++ không giới hạn có thể vẫn tiêu thụ nhiều tài nguyên server.

### Giao dịch

Couchbase transaction có thể cần thiết cho bất biến nhiều document, không phải giải pháp mặc định để giữ một cursor vô thời hạn qua nhiều request. Một feed keyset bình thường thường chấp nhận dữ liệu đang thay đổi; một báo cáo cần snapshot phải được thiết kế khác.

## 18. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Cursor chỉ chứa `createdAt` | Bỏ sót các document cùng timestamp | Thêm `META(c).id` làm tie-breaker |
| Dùng `>` cho khóa `DESC` | Lặp/bỏ sót hoặc quay ngược | So `<` cho khóa giảm dần |
| `ORDER BY score DESC, id ASC` nhưng cả hai dùng `<` | Sai vị trí trong nhóm score bằng nhau | So score `<`, ID `>` |
| Lấy cursor từ hàng look-ahead | Mất hàng chưa hiển thị | Lấy từ hàng cuối của trang **visible** |
| Thiếu ngoặc quanh `OR` | Sai filter, có nguy cơ lộ dữ liệu tenant khác | Bọc toàn bộ predicate keyset bằng `(...)` |
| Trang sau đổi sort hoặc filter | Cursor không còn ý nghĩa | Reset về trang đầu hoặc từ chối token |
| Dùng `PageRequest` rồi gọi là keyset | Vẫn chạy offset | Tạo predicate từ khóa cuối, không dùng offset |
| Field sort là `NULL`/`MISSING` | So range không tương thích thứ tự | Thiết kế normalized key/chính sách null |
| Truy vấn có JOIN làm trùng document ID | Tie-breaker không duy nhất theo row | Bổ sung khóa riêng cho row kết quả |
| Dữ liệu update field sort trong lúc cuộn | Có thể lặp/bỏ sót dù predicate đúng | Chính sách snapshot/mốc dữ liệu nếu cần |
| Keyset chậm dù bỏ offset | Index không hỗ trợ range/order, `Fetch`/`Order` đắt | Kiểm tra `EXPLAIN` và số đo |
| Cursor bị chỉnh sửa | Sai bộ lọc hoặc giá trị seek | Xác thực token, tenant/sort/filter |
| SQL++ chỉ chọn vài field rồi lưu thành entity | Có thể mất field khác khi replace | Tách read DTO và đường mutation có CAS |
| Khi nhiều document trùng tên, không có ID | Thứ tự không toàn phần | Thêm khóa phân xử duy nhất |

## 19. Kiểm thử tích hợp từng lớp

### Kiểm thử cú pháp và kết quả query

1. Seed tập dữ liệu có ít nhất ba document cùng `createdAt`, khác ID.
2. Query trang đầu `LIMIT 3` với page size 2, xác nhận thứ tự đúng.
3. Lấy cursor từ hàng thứ hai, query trang sau, xác nhận hàng thứ ba xuất hiện.
4. Thử nhóm có nhiều timestamp, vị trí chuyển nhóm và trang cuối.
5. Thử các cặp sort `ASC/ASC`, `ASC/DESC`, `DESC/ASC`, `DESC/DESC`.
6. Kiểm tra số hàng API tối đa là page size, không bao gồm hàng look-ahead.

### Kiểm thử dữ liệu và bảo mật

7. Tạo document có `createdAt = null`, thiếu field, sai kiểu; xác minh chính sách không bỏ sót trái yêu cầu.
8. Tạo document thuộc tenant khác, cùng giá trị sort; xác minh mọi trang vẫn lọc theo tenant.
9. Thử cursor cũ sau khi đổi sort/filter/tenant/page size; phải bị từ chối hoặc khởi tạo lại.
10. Thử token hỏng, hết hạn, quá dài, bị chỉnh sửa và chứa giá trị không hợp lệ.
11. Thử field sort trùng, ID đặc biệt, Unicode và giá trị gần ranh giới so sánh.

### Kiểm thử dữ liệu động và vận hành

12. Chèn document mới đứng trước cursor giữa hai request; ghi nhận nó có thể không nằm trong các trang sau.
13. Xóa document trước cursor và so với offset; keyset không phụ thuộc việc đếm vị trí hàng bị xóa.
14. Đổi `createdAt` của document đã trả; chứng minh keyset không phải snapshot.
15. Thử TTL hết hạn và query ngay sau mutation với scan consistency đã chọn.
16. Dùng `EXPLAIN`/profiling so offset sâu với keyset trên cùng index, filter và sort.
17. Đo p50/p95, index entries scanned, `Fetch`, `Order`, timeout và số byte trả về.
18. Kiểm tra đường code blocking/reactive thực tế và số query mỗi lần “Tải thêm”.

### Bảng ca kiểm thử tối thiểu

Với `pageSize = 2`, sort `createdAt DESC, id DESC`:

| Bộ dữ liệu | Hành vi mong muốn |
| --- | --- |
| 0 hàng | `items=[]`, `hasNext=false`, cursor null |
| 1 hàng | Trả một hàng, không có trang sau |
| 2 hàng | Trả đúng hai hàng, không có trang sau |
| 3 hàng | Trả hai hàng, có trang sau; hàng thứ ba không bị mất |
| 3 hàng cùng timestamp | Không bỏ sót vì cursor giữ ID |
| 5 hàng nhiều timestamp | Duyệt hết từng hàng đúng một lần **khi dữ liệu đứng yên** |
| Query bị thay đổi filter | Cursor cũ bị từ chối hoặc reset |
| Có insert/delete/update giữa request | Phản ánh chính sách dữ liệu biến động, không hứa snapshot |

## 20. Bài tập thực hành

Xây dựng endpoint `GET /customers/feed` với:

- `limit` trong khoảng 1–100.
- `cursor` tùy chọn; không cung cấp cursor nghĩa là trang đầu.
- Filter `tenantId` từ người dùng đã xác thực và `active = TRUE`.
- Thứ tự `createdAt DESC, META(c).id DESC`.
- `LIMIT limit+1`; trả tối đa `limit` hàng.
- `nextCursor` opaque chỉ xuất hiện khi `hasNext = true`.
- Không chạy `COUNT` chỉ để phục vụ nút “Tải thêm”.

Các bước:

1. Tạo 50 document với nhiều document có cùng `createdAt`, cộng thêm một số document thuộc tenant khác.
2. Viết SQL++ trang đầu và trang sau, bind parameters.
3. Tạo `CustomerCard`, `SeekCursor` và `SeekPage` hoặc kiểu tương đương.
4. Thêm token encoding/validation, version, thời hạn và ràng buộc tenant/filter/sort.
5. Chạy thử duyệt hết dữ liệu: không trùng, không bỏ sót **khi dữ liệu không đổi**.
6. Đổi điều kiện sang `createdAt DESC, id ASC`; sửa đúng dấu trong predicate.
7. Dùng `EXPLAIN` để so query cursor với `OFFSET` 10.000 và 100.000; không kết luận trước khi đo.
8. Chèn/xóa/sửa một document giữa các trang; mô tả rõ giới hạn tính nhất quán.
9. Viết kiểm thử SQL++ có ngoặc `OR` đúng, không đọc document của tenant khác.
10. Nêu những thay đổi cần thiết nếu product manager yêu cầu nhảy thẳng đến trang 200 hoặc xuất báo cáo snapshot.

### Câu hỏi tự kiểm tra

1. Keyset pagination khác KV get theo document ID ở điểm nào?
2. Vì sao `ORDER BY createdAt DESC` không đủ cho một cursor chắc chắn?
3. Với `ORDER BY score DESC, id ASC`, điều kiện “sau cursor” dùng dấu gì ở mỗi khóa?
4. Vì sao cursor được tạo từ hàng cuối **hiển thị**, không phải hàng look-ahead?
5. Nếu `WHERE` chứa `OR` thiếu ngoặc, điều gì có thể xảy ra với bộ lọc tenant?
6. Vì sao `Pageable` có thể vẫn dùng offset ngay cả khi method trả `Slice`?
7. Thế nào là snapshot pagination, và vì sao keyset đơn thuần không đáp ứng yêu cầu đó?
8. Cần xem những operator/thông số nào trong `EXPLAIN` để đánh giá index phù hợp?
9. Khi nào timestamp string có thể so sánh đúng thứ tự thời gian?
10. Vì sao không được dùng CAS làm cursor thay cho (`createdAt`, `id`)?

## 21. Tài liệu chính thức

- [Couchbase SQL++ — ORDER BY clause](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/orderby.html): quy tắc thứ tự, hướng ASC/DESC, giá trị MISSING/NULL.
- [Couchbase SQL++ — WHERE clause](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/where.html): predicate và biểu thức điều kiện.
- [Couchbase SQL++ — LIMIT clause](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/limit.html): cắt số hàng kết quả.
- [Couchbase SQL++ — OFFSET clause](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/offset.html): khác biệt khi bỏ qua hàng theo vị trí.
- [Couchbase Server — Index pushdowns](https://docs.couchbase.com/server/current/indexes/index_pushdowns.html): điều kiện đẩy scan/order/limit/offset xuống indexer.
- [Couchbase Server — EXPLAIN](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/explain.html): đọc query plan.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): named parameters, `QueryResult` và các lựa chọn consistency.
- [Spring Data Couchbase — Couchbase repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): query methods, `@Query` và `Pageable`.
- [Spring Data Couchbase — Projections](https://docs.spring.io/spring-data/couchbase/reference/repositories/projections.html): trả kết quả projection và giới hạn mapping tùy phiên bản.

Khi triển khai trong dự án, hãy đối chiếu **phiên bản Couchbase Server, Couchbase Java SDK và Spring Data Couchbase** đang được khóa. Kế hoạch index, converter, cách repository ghép `Pageable` và API reactive có thể khác nhau theo phiên bản; kiểm thử tích hợp và profiling vẫn là cơ sở kết luận.

> **Ghi nhớ:** Keyset pagination là câu hỏi **“hàng nào đứng sau bộ khóa sort cuối cùng đã thấy?”**. Viết predicate lexicographic tương ứng chính xác với `ORDER BY`, thêm khóa phân xử duy nhất, giữ nguyên bộ lọc, bind cursor an toàn và lấy cursor từ hàng cuối hiển thị. Nó giúp tránh chi phí bỏ qua offset sâu trong nhiều trường hợp, nhưng **không tự bảo đảm snapshot hay hiệu năng nếu index không phù hợp**.

# Giới hạn từng store, từng loại query và từng phiên bản

## 1. Phạm vi của abstraction scrolling

Trong module Spring Data Commons, scrolling là một phần của cách đọc dữ liệu theo từng lô. Bài này giúp xác định **tổ hợp nào thực sự chạy được** khi kết hợp repository, loại truy vấn, projection và phiên bản thư viện.

Commons định nghĩa hợp đồng dùng chung như `Window<T>` và `ScrollPosition`; việc chuyển hợp đồng đó thành truy vấn thuộc về module store. Vì vậy, import được một kiểu Java chưa đủ để kết luận repository của mọi store đều thực thi được kiểu trả về đó.

Một quyết định triển khai cần ghi rõ:

```text
Phiên bản thư viện thực tế
+ module store và đường thực thi
+ loại query
+ offset hoặc keyset
+ sort và dữ liệu trả về
+ khả năng của database/driver
= phạm vi scrolling cần xác minh
```

Ví dụ, hai phương thức cùng trả về `Window<Account>` vẫn có thể khác khả năng hỗ trợ nếu một phương thức được suy diễn từ tên, còn phương thức kia khai báo JPQL bằng `@Query`. Bài học này không coi một ví dụ chạy trên JPA là cam kết tương thích với MongoDB, JDBC, R2DBC hoặc Elasticsearch.

## 2. Phân biệt ba câu hỏi thường bị gộp lại

| Câu hỏi | Bằng chứng cần có | Điều chưa thể kết luận |
|---|---|---|
| API có tồn tại không? | Javadoc của đúng phiên bản có lớp và phương thức cần dùng | Store đã triển khai đường thực thi đó |
| Tổ hợp query có được hỗ trợ không? | Tài liệu store hoặc kiểm chứng tích hợp với đúng chữ ký repository | Kết quả đúng khi có null, trùng khóa sort hoặc cập nhật đồng thời |
| Cách đọc có phù hợp với nghiệp vụ không? | Kiểm tra thứ tự, tính nhất quán, bộ nhớ và cơ chế tiếp tục công việc | Tự có snapshot hoặc bảo đảm xử lý đúng một lần |

Có thể biên dịch thành công nhưng repository khởi tạo thất bại. Cũng có thể ứng dụng khởi động được nhưng chỉ gặp lỗi khi gọi truy vấn hoặc khi lấy vị trí cho cửa sổ tiếp theo.

Một lô đầu trả về đúng dữ liệu chỉ chứng minh được một phần rất nhỏ: điều kiện tiếp tục thường chỉ xuất hiện từ lô thứ hai.

## 3. Giới hạn theo store và đường thực thi

Các mốc dưới đây dùng tài liệu có phiên bản để minh họa. Chúng không xác nhận phiên bản đang được dùng trong một dự án cụ thể.

| Store/đường đọc | Mốc tham chiếu | Điều có thể sử dụng làm căn cứ |
|---|---|---|
| Spring Data JPA | Nhánh 3.5 | Tài liệu nêu Scroll API cho query methods, Query by Example và Querydsl; đồng thời loại trừ string-based query methods và `@Procedure` |
| Spring Data MongoDB, template | API 4.1.0 | `MongoOperations.scroll(Query, Class)` trả về `Window<T>`; đây là API có từ MongoDB module 4.1 |
| Spring Data JDBC, string-based query | Nhánh 3.5 | Tài liệu nêu giới hạn của pagination và các tham số đặc biệt trên SQL khai báo bằng chuỗi; không suy từ khả năng của derived query sang `@Query` |
| Spring Data R2DBC | Phải đối chiếu đường đọc của phiên bản đích | Việc một API trả `Flux<T>` không tự chứng minh hỗ trợ repository `Window<T>` hoặc khả năng lưu vị trí tiếp tục |
| Spring Data Elasticsearch, query API | API 5.0.3 | Có cấu hình `searchAfter` và point in time; cần sử dụng theo hợp đồng của Elasticsearch |

Các giới hạn JPA trong bảng được mô tả tại [JPA 3.5 — Scrolling Large Query Results](https://docs.spring.io/spring-data/jpa/reference/3.5/jpa/query-methods.html#jpa.query-methods.scrolling). Không áp dụng kết luận này cho mọi bản phát hành tương lai.

### 3.1. MongoDB: document thiếu field cũng là vấn đề

Đối với template MongoDB, phải giới hạn số phần tử và cấu hình vị trí phù hợp. Với keyset, các field sort phải có giá trị khác null; document thiếu field cũng không đáp ứng điều kiện này. Javadoc giải thích việc dựng điều kiện tiếp tục bằng các phép so sánh `$gt`/`$lt` không xử lý được trường hợp đó theo yêu cầu keyset. Xem [MongoOperations 4.1.0 — scroll](https://docs.spring.io/spring-data/mongodb/docs/4.1.0/api/org/springframework/data/mongodb/core/MongoOperations.html#scroll(org.springframework.data.mongodb.core.query.Query,java.lang.Class)).

Ứng dụng không nên chỉ dựa vào kiểu Java `Instant` để cho rằng mọi document đều có `createdAt`. Dữ liệu cũ có thể chưa được backfill. Với một luồng xuất dữ liệu cần keyset, hãy chuẩn hóa dữ liệu trước hoặc chọn khóa sắp xếp đã được bảo đảm tồn tại.

### 3.2. JDBC: SQL khai báo có giới hạn riêng

Tài liệu JDBC 3.5 nêu rằng string-based queries không hỗ trợ pagination và không nhận `Sort`, `PageRequest`, `Limit` theo cách tự viết lại truy vấn. Khi cần giới hạn, phải thể hiện trong SQL và bind tham số phù hợp. Điều này minh họa vì sao không thể chỉ thêm tham số đặc biệt vào một câu SQL bất kỳ rồi kỳ vọng framework tự biến đổi nó. Xem [JDBC 3.5 — Query Methods](https://docs.spring.io/spring-data/relational/reference/3.5/jdbc/query-methods.html).

Đây là giới hạn của đường query được nêu, không phải kết luận rằng mọi cách đọc theo lô bằng JDBC đều bị cấm.

### 3.3. Cơ chế của store không đồng nghĩa với hợp đồng Commons

Elasticsearch có `searchAfter` và point in time trong query API của phiên bản 5.0.3. Sự tồn tại của chúng cho thấy store có cơ chế tiếp tục truy vấn riêng; nó không tự biến chữ ký `Window<T>` ở một repository bất kỳ thành hợp lệ. Xem [BaseQuery 5.0.3](https://docs.spring.io/spring-data/elasticsearch/docs/5.0.3/api/org/springframework/data/elasticsearch/core/query/BaseQuery.html).

Tương tự, nếu dùng Redis, Cassandra hoặc store khác, phải xác định API repository/template thực tế được tài liệu hỗ trợ. Đừng đưa store vào nhóm “có keyset” hoặc “không có keyset” chỉ vì thấy một trang tài liệu chung được nhúng trong reference của store.

## 4. Giới hạn theo loại query

### 4.1. Derived query là một đường thực thi cụ thể

Ví dụ sau dành cho repository JPA trong phạm vi đã được tài liệu hỗ trợ:

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.repository.Repository;

interface AccountRepository extends Repository<Account, Long> {

    Window<Account>
    findFirst200ByTenantIdAndEnabledTrueOrderByCreatedAtAscIdAsc(
            String tenantId,
            ScrollPosition position);
}
```

Giả sử entity `Account` đã ánh xạ các thuộc tính `id`, `tenantId`, `enabled`, `createdAt`; `id` là khóa chính, `createdAt` khác null. Tên phương thức thể hiện bộ lọc tenant, trạng thái, giới hạn 200 và thứ tự tăng dần.

Khi chuyển ví dụ sang store khác, phải kiểm tra lại cả derived-query parser, toán tử của store và kiểu trả về. Cùng một tên phương thức không thay thế được bước đó.

### 4.2. Query by Example và Querydsl cần đúng API

“Có hỗ trợ Query by Example” chưa cho biết mọi phương thức của executor đều trả về cửa sổ. Cần chọn đúng fluent query hoặc đường thực thi có thao tác scroll trong phiên bản đích.

Đặc biệt:

- `ExampleMatcher` mô tả cách khớp thuộc tính, không thay cho giới hạn và thứ tự.
- Predicate Querydsl mô tả điều kiện; vẫn cần một API thực thi hỗ trợ scrolling.
- Khả năng biểu đạt điều kiện của từng store có thể khác nhau.
- Projection và sort vẫn phải giữ được các khóa cần dùng để tiếp tục.

### 4.3. Chuỗi JPQL, native SQL và stored procedure

Trong phạm vi JPA 3.5 ở trên, không dùng khai báo sau làm mẫu được hỗ trợ:

```java
// Ví dụ minh họa tổ hợp không được hỗ trợ trong JPA 3.5.
@Query("select a from Account a where a.tenantId = :tenantId")
Window<Account> loadDeclaredQuery(
        @Param("tenantId") String tenantId,
        ScrollPosition position);
```

Native SQL cũng là một đường khai báo bằng chuỗi; không lấy việc một truy vấn native trả `Page<T>` chạy được để suy ra tổ hợp trả `Window<T>` chạy được.

Nếu nghiệp vụ bắt buộc dùng SQL riêng, có thể viết repository fragment tự thực thi điều kiện tiếp tục, sort và giới hạn bằng API phù hợp. Khi đó, trách nhiệm nằm ở phần triển khai custom: đổi kiểu trả về thành `Window<T>` hoặc tự bọc một danh sách không làm phát sinh hỗ trợ keyset ở tầng dưới.

### 4.4. Projection, join và aggregation thay đổi bài toán

Với keyset, projection phải cung cấp các thuộc tính sort cần thiết để lấy vị trí tiếp tục. Commons mô tả cơ chế bổ sung khóa chính để phân biệt kết quả; khi thiết kế projection, cần giữ các khóa mà đường thực thi store sử dụng. Xem [Commons — Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html).

Ví dụ một projection dành cho thứ tự `createdAt, id`:

```java
import java.time.Instant;

interface AccountRow {
    Long getId();
    Instant getCreatedAt();
    String getUsername();
}
```

Nếu DTO chỉ còn `username`, ứng dụng đã bỏ dữ liệu dùng làm mốc. Việc lô đầu hiển thị đúng username không chứng minh lô sau có thể tiếp tục.

Với join một-nhiều, cần xác định đơn vị được giới hạn là hàng join hay entity gốc. Một tài khoản có năm địa chỉ có thể tạo năm hàng SQL. Nếu giới hạn tại mức hàng rồi gom thành tài khoản, số tài khoản trong một lô có thể khác dự kiến.

Với `GROUP BY`, `DISTINCT` hoặc aggregation, một phần tử đầu ra có thể không còn tương ứng với một entity và khóa chính ban đầu. Khi đó cần thiết kế thứ tự cùng khóa của chính kết quả tổng hợp, thay vì gắn một cursor entity vào kết quả mới.

Đây là các vấn đề mô hình hóa cần đánh giá riêng; không phải tuyên bố rằng mọi query có join hoặc aggregation đều bị từ chối.

## 5. Offset và keyset có giới hạn khác nhau

| Khía cạnh | Offset | Keyset |
|---|---|---|
| Mốc tiếp tục | Vị trí trong kết quả | Bộ giá trị khóa đã đọc |
| Khi đi sâu | Có thể phải bỏ qua nhiều hàng | Có thể tận dụng điều kiện tìm tiếp và index phù hợp |
| Khóa sort null | Phụ thuộc query và cách store sắp xếp null | Không phù hợp với điều kiện keyset Commons mô tả |
| Chèn/xóa trước mốc | Có thể làm dịch vị trí | Không dịch theo số lượng hàng, nhưng vẫn chịu ảnh hưởng khi dữ liệu hoặc khóa sort thay đổi |
| Nhảy đến trang bất kỳ | Phù hợp hơn với nhu cầu đánh số trang | Thường cần có mốc tương ứng trước đó |

Đây là so sánh về cách hoạt động, không phải lời hứa hiệu năng cho mọi database. Cần xem kế hoạch thực thi và index của truy vấn thực tế.

Khởi tạo offset cần phân biệt `ScrollPosition.offset()` với `ScrollPosition.offset(0)`: dạng đầu bắt đầu trước phần tử đầu tiên; dạng có số 0 chỉ vị trí phần tử đầu tiên và việc tiếp tục sẽ bỏ qua nó. Các factory được định nghĩa trong [ScrollPosition 3.1.0](https://docs.spring.io/spring-data/commons/docs/3.1.0/api/org/springframework/data/domain/ScrollPosition.html).

### 5.1. Thứ tự phải xác định được mốc

Giả sử có dữ liệu:

| id | createdAt | username |
|---|---|---|
| 41 | 2026-01-10T08:00:00Z | an |
| 42 | 2026-01-10T08:00:00Z | binh |
| 43 | 2026-01-10T08:01:00Z | chi |

Nếu chỉ lưu `createdAt` làm mốc sau bản ghi 41, điều kiện `createdAt > :lastCreatedAt` sẽ bỏ sót bản ghi 42. Với thứ tự tăng dần `createdAt, id`, điều kiện tiếp tục tương đương về mặt logic là:

```sql
WHERE tenant_id = :tenantId
  AND enabled = true
  AND (
       created_at > :lastCreatedAt
       OR (created_at = :lastCreatedAt AND id > :lastId)
  )
ORDER BY created_at ASC, id ASC
LIMIT :batchSize
```

Đây là SQL minh họa cho dialect có `LIMIT` và cách bind named parameter phù hợp; không phải chuỗi JPQL hay cam kết SQL mà Spring Data luôn sinh ra.

Nếu đổi thành `createdAt DESC, id ASC`, hướng so sánh cũng phải thay đổi theo từng thành phần. Không tái sử dụng nguyên điều kiện tăng dần.

Một index ứng viên cho tình huống này là `(tenant_id, enabled, created_at, id)`. Đây là điểm bắt đầu để đánh giá trên database đích, không phải bảo đảm rằng optimizer sẽ chọn index đó trong mọi dữ liệu.

### 5.2. Khóa mutable làm mất ổn định hành trình

Nếu một tài khoản đã đọc được đổi `createdAt` sang phía sau mốc, nó có thể xuất hiện lại. Nếu một tài khoản chưa đọc bị đổi sang phía trước mốc, nó có thể bị bỏ sót.

Điều này đặc biệt đáng chú ý với field auditing như `lastModifiedDate`: field được cập nhật tự động không có nghĩa nó thích hợp làm khóa duyệt ổn định.

Với xuất dữ liệu, có thể chọn khóa ít thay đổi và cố định điều kiện nghiệp vụ ngay từ đầu. Nếu cần dữ liệu đúng tại một thời điểm, phải thiết kế snapshot hoặc cơ chế nhất quán tương ứng của store. Chỉ thêm điều kiện `createdAt <= :cutoff` vẫn không đóng băng các cập nhật lên bản ghi cũ.

## 6. Ví dụ đọc nhiều cửa sổ mà không tự tính mốc

Với `AccountRepository` ở phần 4, có thể viết phần điều phối đồng bộ như sau. `handler` xử lý từng tài khoản; việc đọc và xử lý nằm trong ranh giới transaction phù hợp do ứng dụng thiết kế.

```java
import java.util.function.Consumer;

import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

static void consumeAccounts(
        AccountRepository repository,
        String tenantId,
        Consumer<Account> handler) {

    ScrollPosition position = ScrollPosition.keyset();

    while (true) {
        Window<Account> window =
                repository
                    .findFirst200ByTenantIdAndEnabledTrueOrderByCreatedAtAscIdAsc(
                            tenantId, position);

        if (window.isEmpty()) {
            return;
        }

        for (Account account : window) {
            handler.accept(account);
        }

        if (!window.hasNext()) {
            return;
        }

        position = window.positionAt(window.size() - 1);
    }
}
```

Ví dụ cố ý dùng giới hạn tĩnh để không phụ thuộc thêm vào API `Limit`. Vị trí được lấy từ cửa sổ thực tế; không tự tăng số offset trong một luồng keyset.

Đoạn mã chưa triển khai checkpoint bền vững. Nếu chương trình dừng giữa lô, lần chạy sau cần biết bắt đầu lại từ đâu. Nếu lưu checkpoint trước khi xử lý xong, có thể mất dữ liệu; nếu lưu sau khi xử lý xong nhưng tiến trình chết trước khi lưu, có thể xử lý lặp.

Một thiết kế xuất dữ liệu thường cần thao tác đích idempotent hoặc cơ chế phối hợp checkpoint với kết quả xử lý. Đây là trách nhiệm của luồng nghiệp vụ, ngoài hợp đồng `Window<T>`.

## 7. Giới hạn theo phiên bản

### 7.1. Các mốc API độc lập

| Mốc | Ý nghĩa | Điều cần tránh suy diễn |
|---|---|---|
| Commons 3.1 | `ScrollPosition` xuất hiện từ phiên bản này | Mọi store cùng thời điểm đều hỗ trợ mọi dạng query |
| Commons 3.2 | `Limit` xuất hiện từ phiên bản này | Mã dùng `Limit` có thể biên dịch trên Commons 3.1 |
| MongoDB module 4.1 | `MongoOperations.scroll` được ghi nhận từ mốc này | Mốc 4.1 là phiên bản MongoDB server hoặc Commons |
| JPA nhánh 3.5 | Có giới hạn theo loại query đã nêu | Giới hạn đó chắc chắn giữ nguyên ở nhánh khác |

Nguồn cho hai mốc Commons là [ScrollPosition 3.1.0](https://docs.spring.io/spring-data/commons/docs/3.1.0/api/org/springframework/data/domain/ScrollPosition.html) và [Limit 3.2.3](https://docs.spring.io/spring-data/commons/docs/3.2.3/api/org/springframework/data/domain/Limit.html). Mốc API cần tách khỏi số phiên bản của database server.

Khi học từ ví dụ mới hơn dự án, có thể phải dùng `First`/`Top` thay cho tham số `Limit`, hoặc dùng API khác được hỗ trợ. Đổi chữ ký chỉ là một phần; vẫn cần xác nhận store xử lý chữ ký mới đó.

### 7.2. Dùng phiên bản được resolve thực tế

Trong dự án dùng Spring Boot, dependency management thường quyết định bộ phiên bản. Tên phiên bản Boot không phải số phiên bản của từng module Spring Data.

Quy trình áp dụng vào dự án:

1. Xác định phiên bản thực tế của Commons và module store sau khi dependency được resolve.
2. Đọc reference/Javadoc tương ứng, gồm giới hạn của đúng loại query.
3. Đối chiếu release notes khi nâng cấp qua các nhánh.
4. Kiểm chứng lại đường thực thi có dữ liệu, thay vì chỉ biên dịch.
5. Giữ sự tương thích của toàn bộ bộ thư viện do BOM quản lý hoặc tự xác nhận đầy đủ khi override.

Chỉ nâng Commons để import được một lớp mới có thể làm lệch bộ thư viện với store module. Những lỗi như `NoSuchMethodError` cần được điều tra ở dependency runtime trước khi quy về lỗi truy vấn.

Đường dẫn tài liệu `current`, `latest` hoặc snapshot có thể thay đổi. Khi ghi nhận quyết định kỹ thuật, nên lưu phiên bản đã đối chiếu, đường API và giả định dữ liệu. Một cursor được lưu lâu dài cũng nên có schema version riêng; không mặc định object nội bộ của thư viện là định dạng giao tiếp bền vững.

## 8. Cách thiết kế phương án thay thế

| Vướng mắc | Hướng xử lý hợp lý | Chi phí cần đánh giá |
|---|---|---|
| Chưa có bằng chứng store hỗ trợ chữ ký `Window<T>` cần dùng | Chọn API template hoặc cơ chế tiếp tục được store công bố | Phải quản lý token, giới hạn và vòng đời tài nguyên tương ứng |
| Query khai báo bằng chuỗi không được Scroll API hỗ trợ | Chuyển sang đường query được hỗ trợ hoặc viết repository fragment | Tự chịu trách nhiệm về điều kiện tìm tiếp và mapping |
| Khóa sort null/thiếu field | Chuẩn hóa dữ liệu, đổi khóa hoặc dùng cách đọc khác | Công việc migration và thay đổi ngữ nghĩa thứ tự |
| Projection thiếu khóa | Bổ sung field trong projection nội bộ, rồi ánh xạ sang DTO xuất ra | Tăng một ít dữ liệu đọc và mapping |
| Nghiệp vụ cần tổng số và nhảy đến trang | Cân nhắc `Page<T>` | Chi phí đếm và offset sâu nếu có |
| Nghiệp vụ chỉ cần lô tiếp theo, không cần keyset | Cân nhắc `Slice<T>` nếu store/query hỗ trợ | Vẫn phải đánh giá chi phí và biến động dữ liệu |
| Nghiệp vụ cần snapshot xuất dữ liệu | Chọn cơ chế nhất quán của store hoặc tập dữ liệu xuất riêng | Tài nguyên, thời gian giữ snapshot và vận hành |

`Stream<T>` hoặc `Flux<T>` có thể phù hợp cho một đường đọc khác, nhưng cần kiểm tra riêng cách lấy dữ liệu và giải phóng tài nguyên. Backpressure phía ứng dụng không tự trở thành checkpoint để tiếp tục sau khi tiến trình khởi động lại.

## 9. Các tình huống nên kiểm chứng khi áp dụng

Đây là các tình huống thực hành cho dự án đích, không phải khẳng định rằng chỉ cần chạy một unit test là xác nhận được khả năng của store.

| Tình huống | Điều cần quan sát |
|---|---|
| Không có dữ liệu | Kết thúc ngay, không lấy vị trí ở index âm |
| Có ít hơn một lô | Xử lý đủ dữ liệu và dừng |
| Dữ liệu đúng bằng kích thước một lô | Không suy đoán có lô tiếp chỉ từ số phần tử |
| Có nhiều hơn hai lô | Mỗi ID xuất hiện đúng như mong đợi trong tập dữ liệu tĩnh |
| Nhiều bản ghi có cùng `createdAt` | Đi qua được ranh giới giữa các bản ghi trùng khóa thời gian |
| Sort field null hoặc document thiếu field | Xác định và xử lý điều kiện không hợp lệ trước khi dùng keyset |
| Projection bỏ `id` hoặc field sort | Phát hiện tổ hợp không giữ được dữ liệu mốc |
| Đổi tenant, bộ lọc hoặc sort giữa hành trình | Không tái dùng cursor cũ cho một ngữ cảnh truy vấn khác |
| Chèn, xóa, cập nhật giữa hai lô | Ghi rõ kết quả theo mức nhất quán đã chọn |
| Nâng phiên bản thư viện | Xác nhận lại repository, lô thứ hai và việc tiếp tục từ checkpoint nếu có |

Với dữ liệu tĩnh nhỏ, có thể đối chiếu danh sách ID đã duyệt với danh sách kỳ vọng theo cùng sort. Với dữ liệu thay đổi đồng thời, cần định nghĩa kết quả mong đợi trước; không dùng kỳ vọng snapshot cho một luồng không được thiết kế có snapshot.

## 10. Tình huống áp dụng: xuất tài khoản theo tenant

Giả sử cần xuất một triệu tài khoản đang hoạt động. Mỗi tenant có nhiều tài khoản, `createdAt` khác null và ít thay đổi; một số tài khoản có cùng thời điểm tạo.

Một lựa chọn có căn cứ là:

1. Dùng đường derived query JPA đã xác nhận hỗ trợ trên bộ phiên bản của ứng dụng.
2. Cố định tenant và điều kiện `enabled` trong suốt hành trình.
3. Sắp xếp theo `createdAt, id`; giữ đủ hai khóa trong dữ liệu đọc.
4. Đọc mỗi lô 200 phần tử và lấy vị trí từ cửa sổ.
5. Thiết kế checkpoint và ghi dữ liệu đích sao cho chịu được xử lý lại.
6. Nếu báo cáo yêu cầu “đúng tại thời điểm bắt đầu”, bổ sung cơ chế nhất quán thay vì chỉ dựa vào cursor.

Nếu chuyển sang MongoDB, phải kiểm tra dữ liệu cũ có thiếu `createdAt` không và chọn đường repository/template được phiên bản MongoDB module hỗ trợ. Nếu chuyển sang query tổng hợp số tài khoản theo ngày, phải thiết kế khóa cho kết quả theo ngày; cursor của entity tài khoản không còn là mô hình phù hợp.

Tiêu chí hoàn thành về mặt thiết kế là nêu được **store nào, phiên bản nào, query nào, khóa nào và mức nhất quán nào**. Những thông tin đó biến lựa chọn scrolling thành một quyết định có thể kiểm chứng và bảo trì.

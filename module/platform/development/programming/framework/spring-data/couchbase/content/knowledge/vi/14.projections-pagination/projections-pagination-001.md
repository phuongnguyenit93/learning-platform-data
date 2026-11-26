# Chỉ lấy các trường cần dùng thay vì đọc toàn bộ entity

Trong **Spring Data Couchbase**, một document có thể chứa thông tin hồ sơ, địa chỉ, lịch sử mua hàng, cấu hình và nhiều cấu trúc lồng nhau. Tuy nhiên, trang danh sách khách hàng có thể chỉ cần tên và email. Trả về cả document cho mỗi dòng vừa tăng dữ liệu truyền qua mạng, vừa tăng công việc giải mã JSON và ánh xạ đối tượng của ứng dụng.

Mục tiêu của bài học thuộc chương **Chiếu và phân trang** là chọn đúng dữ liệu mà từng chức năng cần, sử dụng projection của Spring Data và SQL++ có chọn trường, đồng thời phân biệt rõ **đối tượng Java chỉ lộ vài thuộc tính** với **truy vấn Couchbase thật sự chỉ lấy vài trường**.

Sau bài này, bạn có thể:

- Thiết kế giao diện projection và DTO phù hợp với màn hình hoặc API.
- Viết truy vấn SQL++ chỉ `SELECT` các trường cần thiết, bao gồm ID document khi cần.
- Chọn giữa repository, truy vấn SQL++, KV và sub-document API theo kiểu truy cập.
- Kiểm tra truy vấn thực tế và kế hoạch thực thi để xác nhận tối ưu hóa có hiệu lực.
- Nhận diện những vấn đề về index, phân trang, dữ liệu lồng nhau, tính nhất quán và metadata.

## 1. Bài toán: màn hình cần ít hơn document lưu trữ

Giả sử collection `customers` chứa document có khóa `customer::1042` và nội dung:

~~~json
{
  "fullName": "Nguyễn An",
  "email": "an@example.test",
  "active": true,
  "address": {
    "city": "Hà Nội",
    "street": "..."
  },
  "preferences": {
    "language": "vi",
    "notifications": true
  },
  "purchaseHistory": [
    { "orderId": "O-001", "amount": 1250000 }
  ]
}
~~~

Các chức năng có nhu cầu khác nhau:

| Chức năng | Dữ liệu thật sự cần |
| --- | --- |
| Danh sách khách hàng | ID, tên, email |
| Chi tiết hồ sơ | ID, tên, email, địa chỉ, tùy chọn |
| Kiểm tra trạng thái hoạt động | ID và `active` |
| Cập nhật có kiểm soát đồng thời | Dữ liệu cần thay đổi và CAS/metadata thích hợp |

Một API danh sách trả về nguyên đối tượng `Customer` có thể vô tình đưa cả địa chỉ và lịch sử giao dịch ra ngoài. Ngay cả khi lớp controller sau đó chuyển `Customer` thành DTO nhỏ, dữ liệu thừa **có thể đã được đọc từ Couchbase**.

Với giả định 1.000 document, mỗi document khoảng 15 KB còn ba trường hiển thị khoảng 250 B, dung lượng nội dung JSON cần truyền có thể giảm từ khoảng 15 MB xuống 0,25 MB. Đây chỉ là ví dụ định lượng; mức tiết kiệm thực tế còn phụ thuộc truy vấn, index, nén, kích thước trường và cách ánh xạ.

## 2. Ba mức độ “chỉ lấy trường cần dùng”

Điểm then chốt là xác định **việc giảm trường diễn ra ở đâu**.

| Cách làm | Điều được bảo đảm | Điều cần kiểm chứng |
| --- | --- | --- |
| Entity đầy đủ rồi ánh xạ sang DTO | API chỉ xuất các trường DTO | Couchbase vẫn có thể đã trả toàn bộ document |
| Repository trả interface/DTO projection | Mã gọi nhận dạng dữ liệu gọn hơn | Truy vấn sinh ra có thực sự chỉ `SELECT` các trường đó không |
| SQL++ `SELECT` danh sách trường tường minh | Kết quả truy vấn chỉ chứa các biểu thức đã chọn | Query Engine có còn phải đọc document từ Data Service không |
| KV sub-document `lookupIn` | Đọc các đường dẫn cụ thể theo document key | Có xử lý đúng trường bị thiếu, kiểu dữ liệu và quyền truy cập không |

Hai chiều tối ưu hóa cần phân biệt:

1. **Ít dữ liệu trả về:** SQL++ chỉ chiếu vài trường giúp giảm payload và công việc ánh xạ.
2. **Ít đọc dữ liệu lưu trữ:** nếu các trường được bao phủ bởi index (covering index), Query Engine có thể lấy dữ liệu trực tiếp từ index mà không cần bước `Fetch` document. Nếu chưa có index phù hợp, hệ thống vẫn có thể phải đọc document để trả ra vài trường.

Projection vì vậy là **hình dạng dữ liệu được trả về**, còn covering index quyết định một phần **chi phí thực thi truy vấn**.

## 3. Interface projection với Spring Data repository

Giả sử ứng dụng dùng bucket `app`, scope `crm` và collection `customers`. Entity Spring Data ánh xạ document có thể được khai báo:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("crm")
@Collection("customers")
public class Customer {
    @Id
    private String id;

    private String fullName;
    private String email;
    private boolean active;
    private Address address;

    // Constructor, getter/setter cần thiết cho cơ chế mapping đang dùng.
}
~~~

Một **closed interface projection** chỉ khai báo các accessor cần sử dụng:

~~~java
public interface CustomerSummary {
    String getId();
    String getFullName();
    String getEmail();
}
~~~

Repository có thể yêu cầu trả về kiểu projection thay vì entity:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    List<CustomerSummary> findByActiveTrue();

    <T> List<T> findByActive(boolean active, Class<T> projectionType);
}
~~~

Ở đây:

- `findByActiveTrue()` là truy vấn dẫn xuất trả về interface projection.
- Phương thức tổng quát nhận `Class<T>` minh họa **dynamic projection**; caller có thể chọn kiểu kết quả khi gọi.
- Getter phải khớp thuộc tính được ánh xạ. Nếu tên trường lưu trong JSON khác tên thuộc tính Java, cần kiểm tra `@Field` và alias của SQL++.
- Không nên dùng đối tượng projection như entity có thể `save`: đây là góc nhìn dữ liệu cho tác vụ đọc, không phải bản đầy đủ để cập nhật.

**Lưu ý về hiệu năng:** các phiên bản Spring Data Couchbase và từng loại phương thức repository có thể xây dựng truy vấn khác nhau. Chỉ nhìn kiểu trả về `CustomerSummary` **chưa đủ** để kết luận rằng Couchbase đã bỏ các trường dư từ phía server. Hãy bật log truy vấn phù hợp và kiểm tra biểu thức `SELECT` sinh ra; nếu cần kiểm soát chính xác dữ liệu truyền về, hãy viết SQL++ có danh sách trường tường minh.

### Khi nào dùng DTO hoặc record?

DTO phù hợp khi muốn ranh giới API rõ ràng, đối tượng bất biến hoặc cấu trúc không trùng tên entity:

~~~java
public record CustomerCardDto(
        String id,
        String fullName,
        String email
) {}
~~~

Có thể chuyển từ projection sang DTO ở tầng service:

~~~java
List<CustomerCardDto> cards = repository.findByActiveTrue()
    .stream()
    .map(p -> new CustomerCardDto(
        p.getId(), p.getFullName(), p.getEmail()))
    .toList();
~~~

Cách chuyển đổi này làm rõ hợp đồng dữ liệu trả về, **nhưng tự nó không quyết định truy vấn ở Couchbase**. Nếu sử dụng class-based/record projection do Spring Data trực tiếp ánh xạ, cần kiểm tra tương thích giữa constructor, tên thuộc tính, alias và phiên bản Spring Data đang dùng.

Không nên dùng **open projection** dựa trên biểu thức SpEL truy cập `target` để khẳng định rằng mọi trường không được sử dụng sẽ bị loại khỏi truy vấn: framework có thể cần thêm dữ liệu nguồn để tính biểu thức. Với giá trị tính toán đơn giản từ các getter đã chọn, có thể cân nhắc default method trên interface; vẫn phải xác minh câu SQL++ thực tế.

## 4. Chủ động chiếu trường bằng SQL++

Khi cần bảo đảm Query Service trả về đúng hình dạng cho màn hình, hãy khai báo các trường ngay trong SQL++:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `app`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName, META(c).id
LIMIT 20 OFFSET 0;
~~~

Kết quả là các đối tượng dạng:

~~~json
[
  {
    "id": "customer::1042",
    "fullName": "Nguyễn An",
    "email": "an@example.test"
  }
]
~~~

Các điểm cần nhớ:

- `META(c).id` lấy **document key**; key không tự động nằm trong body JSON. Đặt `AS id` nếu projection có `getId()`.
- `AS fullName` và `AS email` giúp tên trong result khớp getter/DTO. Việc ánh xạ còn phụ thuộc cấu hình converter và các annotation của entity.
- `SELECT c.*` hoặc `SELECT c` có thể kéo theo toàn bộ trường trong document; `SELECT *` cũng không phải lựa chọn cho API chỉ cần ba trường.
- Tránh `SELECT RAW` nếu lớp ánh xạ đang trông đợi một object chứa các alias vì `RAW` thay đổi hình dạng kết quả.
- `ORDER BY` gồm tên và ID để thứ tự có điểm phân xử khi nhiều khách hàng trùng tên. Điều này đặc biệt hữu ích khi phân trang, dù dữ liệu thêm/xóa giữa các lần truy vấn vẫn có thể làm `OFFSET` bị trôi.

### Đưa SQL++ vào repository

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.Query;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    @Query("""
        SELECT META(c).id AS id,
               c.fullName AS fullName,
               c.email AS email
        FROM `app`.`crm`.`customers` AS c
        WHERE c.active = $1
        ORDER BY c.fullName, META(c).id
        LIMIT $2 OFFSET $3
        """)
    List<CustomerSummary> findSummaries(
            boolean active, long limit, long offset);
}
~~~

Ví dụ `findSummaries(true, 20, 0)` sử dụng tham số vị trí `$1`, `$2` và `$3`. Với dự án thực tế, thay đường dẫn keyspace bằng cấu hình bucket/scope/collection của ứng dụng; nếu một collection chứa nhiều kiểu document, bảo đảm điều kiện phân loại kiểu phù hợp với chiến lược discriminator của Spring Data (thường liên quan trường `_class`). Một truy vấn viết tay có thể cần bổ sung điều kiện đó.

Khi dùng `@Query` tùy biến, cần kiểm tra bằng integration test rằng kết quả map được sang projection/DTO của **phiên bản Spring Data Couchbase thực tế**. Đặc biệt chú ý tên alias, trường `id`, thuộc tính lồng nhau, giá trị `null` và các annotation ánh xạ.

### Với ứng dụng reactive

Nếu hệ thống sử dụng WebFlux hoặc pipeline bất đồng bộ, repository reactive có thể giữ cùng kiểu projection:

~~~java
import reactor.core.publisher.Flux;
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    @Query("""
        SELECT META(c).id AS id,
               c.fullName AS fullName,
               c.email AS email
        FROM `app`.`crm`.`customers` AS c
        WHERE c.active = TRUE
        """)
    Flux<CustomerSummary> findActiveSummaries();
}
~~~

`Flux` giúp tiêu thụ kết quả trong pipeline reactive; **reactive không tự động giảm số trường hay làm truy vấn nhẹ hơn**. Phần tiết kiệm payload ở ví dụ này đến từ `SELECT` tường minh. Với dữ liệu lớn, vẫn phải giới hạn số kết quả hoặc phân trang và cân nhắc cơ chế backpressure, timeout.

## 5. Truy cập một document bằng khóa: cân nhắc sub-document

Đối với trường hợp đã có document key, truy cập KV thường phù hợp hơn truy vấn SQL++ theo điều kiện. Tuy nhiên, một lời gọi KV lấy document đầy đủ sẽ đọc body document dù lớp Java chỉ cần hai trường.

Couchbase Java SDK cung cấp **sub-document lookup** để lấy các đường dẫn cụ thể:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.LookupInResult;
import com.couchbase.client.java.kv.LookupInSpec;
import java.util.List;

LookupInResult result = collection.lookupIn(
    "customer::1042",
    List.of(
        LookupInSpec.get("fullName"),
        LookupInSpec.get("email")
    )
);

String fullName = result.contentAs(0, String.class);
String email = result.contentAs(1, String.class);
~~~

`collection` ở đây là đối tượng của **Couchbase Java SDK**, không phải annotation `@Collection` của Spring Data. Đây là lựa chọn hữu ích khi muốn lấy vài field theo key mà không cần Query Service hay secondary index. Đổi lại, ứng dụng phải quản lý SDK/result mapping trực tiếp hoặc bọc lời gọi trong custom repository/service.

Nếu đường dẫn không tồn tại hoặc có kiểu khác kỳ vọng, cần xử lý lỗi đọc sub-document thích hợp. Với truy cập mảng, map lớn hoặc đường dẫn lồng nhau, số byte thực tế phụ thuộc cấu trúc và các path được yêu cầu.

## 6. Index quyết định liệu có phải đọc body document

Ví dụ tạo một secondary index phục vụ điều kiện lọc và hai trường xuất ra:

~~~sql
CREATE INDEX ix_customer_active_name_email
ON `app`.`crm`.`customers` (active, fullName, email);
~~~

Sau đó kiểm tra kế hoạch:

~~~sql
EXPLAIN
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `app`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName, META(c).id
LIMIT 20;
~~~

Nếu index bao phủ biểu thức lọc và các trường truy vấn cần, Query Engine **có thể** dùng covering index. Trong kết quả `EXPLAIN`, tìm thông tin `covers`/index scan và kiểm tra có bước `Fetch` hay không. Đừng suy ra một index đang cover chỉ vì các trường được liệt kê trong lệnh `CREATE INDEX`: biểu thức `WHERE`, `ORDER BY`, metadata, phân vùng và lựa chọn của optimizer đều ảnh hưởng kế hoạch.

Cũng không nên tạo index bao hết mọi cột cho mọi API. Index rộng hơn tốn lưu trữ, chi phí cập nhật và có thể giảm hiệu năng ghi. Chỉ thêm index khi có tần suất truy vấn, kế hoạch thực thi và số liệu đo chứng minh nhu cầu.

| Trường hợp | Phần việc có thể tiết kiệm | Giới hạn |
| --- | --- | --- |
| `SELECT` ba field, chưa covering | Mạng và ánh xạ JSON kết quả | Có thể vẫn cần `Fetch` document |
| `SELECT` ba field, có covering | Mạng, ánh xạ và có thể tránh `Fetch` | Tăng chi phí duy trì secondary index |
| KV get document đầy đủ | Đường truy cập theo key nhanh, đơn giản | Vẫn truyền body đầy đủ |
| KV `lookupIn` hai path | Truyền/đọc hai giá trị theo key | Không hỗ trợ tìm kiếm theo điều kiện tùy ý |

## 7. Phân trang khi dữ liệu đã được chiếu gọn

Projection giảm kích thước **mỗi hàng**; nó không tự hạn chế **số hàng**. Cần kết hợp với giới hạn bản ghi:

- `LIMIT` và `OFFSET` dễ dùng cho trang nhỏ, nhưng `OFFSET` lớn có thể khiến engine xử lý nhiều bản ghi trước khi trả trang.
- Với danh sách dài, cân nhắc **keyset pagination** dựa trên cặp trường sắp xếp ổn định, chẳng hạn `fullName` và document key. Điều kiện trang sau phải khớp đúng `ORDER BY` và được hỗ trợ bởi index phù hợp.
- Nếu giao diện chỉ cần nút “Xem thêm”, lấy `pageSize + 1` bản ghi để biết còn trang sau có thể tránh chi phí một truy vấn `COUNT(*)` tách riêng. Nếu yêu cầu tổng số trang thì vẫn phải tính toán chi phí lấy tổng.
- Dữ liệu được ghi đồng thời có thể thay đổi giữa các lần lấy trang. Projection không tự giải quyết hiện tượng trùng/bỏ sót dòng, và index scan consistency của SQL++ có thể ảnh hưởng tính mới của dữ liệu sau ghi.

Ví dụ ý tưởng cho trang tiếp theo theo cặp (`lastName`, `lastId`):

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `app`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND (
       c.fullName > $lastName
       OR (
           c.fullName = $lastName
           AND META(c).id > $lastId
       )
  )
ORDER BY c.fullName, META(c).id
LIMIT $pageSize;
~~~

Đây là **mẫu ý tưởng SQL++**; cách bind tham số tên, chiến lược index và các giá trị `NULL`/`MISSING` cần được thống nhất theo SDK/framework dùng trong dự án. Với tập dữ liệu thay đổi liên tục, keyset thường ổn định hơn offset nhưng không tự tạo snapshot nhất quán giữa các lần gọi.

## 8. Các lỗi thường gặp và cách xử lý

### “Trả interface projection là đã query ít field”

Chưa chắc. Hãy kiểm tra SQL++ được sinh ra. Với yêu cầu tối ưu payload cần dự đoán được, dùng `SELECT` tường minh và xác nhận kết quả trên môi trường chạy thật.

### “Chỉ SELECT hai field thì chắc chắn không đọc document”

Không đúng. Nếu thiếu covering index, hệ thống có thể đọc document trước khi chiếu kết quả. Dùng `EXPLAIN`/query profiling và theo dõi độ trễ, số lượng bản ghi quét cùng chi phí index.

### “Trường ID nằm trong JSON”

Document key nằm ở metadata. Khi viết SQL++ thủ công, lấy bằng `META(alias).id` nếu cần. CAS, expiration/TTL và metadata khác cũng không tự xuất hiện trong projection dữ liệu; các luồng cập nhật dựa trên CAS phải thu thập metadata phù hợp, không suy từ projection đọc thông thường.

### “Projection có thể lưu ngược thành entity”

Không nên. Projection thường là bản xem không đầy đủ; `save` từ một đối tượng thiếu trường có thể gây ghi thiếu dữ liệu hoặc làm mất thông tin nếu được ánh xạ sai. Hãy dùng entity/cập nhật có điều kiện, sub-document mutation và CAS đúng nghiệp vụ.

### “Field thiếu và field null là như nhau”

Trong SQL++ có sự khác nhau giữa `MISSING` và `NULL`. Một alias có thể không xuất hiện trong kết quả nếu biểu thức là `MISSING`; getter hoặc DTO dùng kiểu nguyên thủy có thể gặp lỗi hoặc nhận giá trị mặc định khó nhận ra. Thử dữ liệu thực tế có cả trường thiếu, `null` và sai kiểu; dùng fallback rõ ràng nếu hợp đồng API yêu cầu.

### “Projection cũng thay thế kiểm soát truy cập”

Không. Chỉ xuất vài trường giúp hạn chế dữ liệu vô tình lộ ra nhưng không thay quyền bucket/scope/collection, kiểm soát truy cập ở tầng service hay quyền được thực thi truy vấn. Tránh trả trường nhạy cảm qua projection chỉ vì getter được khai báo.

### “Reactive projection luôn nhanh hơn”

Reactive chủ yếu thay đổi cách tiêu thụ kết quả và quản lý luồng xử lý. Tối ưu IO phía Couchbase vẫn đến từ chọn đúng đường truy cập, `SELECT`, index và kích thước trang.

## 9. Quy trình áp dụng và xác minh

1. **Xác định hợp đồng dữ liệu:** liệt kê trường mà màn hình hoặc API thực sự cần, kể cả ID và trường dùng để sắp xếp.
2. **Chọn công cụ:** repository projection khi ưu tiên biểu diễn Java; SQL++ có `SELECT` tường minh khi cần kiểm soát payload; `lookupIn` khi đã có key và chỉ cần ít path.
3. **Kiểm tra kết quả mapping:** alias khớp getter/constructor; thử field thiếu, giá trị `null`, nested object và document key.
4. **Quan sát truy vấn đã chạy:** kiểm tra danh sách trường trong `SELECT` thực tế, số lượng bản ghi, thời gian chạy và response size.
5. **Phân tích index:** dùng `EXPLAIN`/profiling để xác định `Fetch`, `covers` và nguyên nhân truy vấn chậm; chỉ thêm index khi có bằng chứng.
6. **Đo theo cùng workload:** so sánh độ trễ p95, dữ liệu truyền, tài nguyên ứng dụng, số bản ghi quét và chi phí ghi trước/sau thay đổi.
7. **Kiểm tra tính đúng đắn:** phân trang ổn định, dữ liệu mới sau ghi (scan consistency thích hợp), quyền dữ liệu và trường hợp cập nhật dựa trên CAS.

**Ví dụ quyết định thực tế:** một trang liệt kê 20 khách hàng dùng SQL++ chọn ID, tên, email và `LIMIT 20`; một trang chi tiết có thể đọc entity đầy đủ; còn một tác vụ tra email bằng document key nên xem xét sub-document lookup. Mỗi cách phục vụ một nhu cầu đọc khác nhau.

> **Ghi nhớ:** Projection định nghĩa *mình muốn nhìn thấy dữ liệu gì*. SQL++ `SELECT` định nghĩa *server trả ra những trường gì*. Covering index và KV sub-document quyết định *có thể tránh đọc document đầy đủ ở mức truy cập dữ liệu hay không*. Kiểm tra cả ba mức này trước khi kết luận ứng dụng đã được tối ưu.

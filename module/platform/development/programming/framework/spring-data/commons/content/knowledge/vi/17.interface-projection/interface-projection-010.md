# Kiểm chứng dữ liệu thực sự được tải ở store

Một interface chỉ có hai getter chưa chứng minh database chỉ trả về hai trường. Một response JSON nhỏ cũng chưa chứng minh ứng dụng không tải cả entity, document lớn hoặc các quan hệ liên quan trước khi tạo response.

Trong Spring Data Commons, interface projection cung cấp hợp đồng nhìn vào một phần dữ liệu. Module của từng kho dữ liệu quyết định cách lấy dữ liệu và tạo đối tượng projection. Muốn xác nhận hiệu quả, phải quan sát truy vấn, kết quả truyền về, cách ánh xạ và các truy vấn phát sinh trong toàn bộ quá trình sử dụng projection.

Bài học này hướng dẫn thiết kế phép kiểm chứng cho projection. Các đoạn cấu hình và mã là ví dụ để áp dụng trong dự án tương ứng, không phải báo cáo một phép đo đã được thực hiện.

Sau bài học, bạn có thể:

- Tách dữ liệu ứng dụng nhìn thấy khỏi dữ liệu store thực sự truy xuất và trả về.
- Kiểm tra select list hoặc field projection thay vì suy từ getter.
- So sánh closed projection, open projection và projection lồng nhau bằng bằng chứng thực thi.
- Nhận biết ảnh hưởng của cache, lazy loading, serialization và ánh xạ alias.
- Lập một phép kiểm chứng có thể lặp lại trên module và driver đang dùng.

## 1. “Được tải” có nhiều tầng ý nghĩa

Trước khi kết luận projection có tối ưu hay không, phải xác định đang nói đến tầng nào.

| Tầng quan sát | Câu hỏi cần trả lời | Bằng chứng phù hợp |
|---|---|---|
| Hợp đồng Java | Projection cho phép gọi getter nào? | Interface, kiểu trả về repository |
| Lệnh gửi store | Query yêu cầu cột, field, quan hệ nào? | SQL, command, query options |
| Kết quả store trả về | Những giá trị nào đi từ server về driver? | Result metadata, command projection, quan sát driver khi cần |
| Ánh xạ trong ứng dụng | Hạ tầng tạo tuple, entity, document hay proxy nào? | Mapping, thống kê provider, quan sát đối tượng trong ngữ cảnh |
| Sử dụng kết quả | Đọc getter hoặc serialize có tải thêm không? | Truy vấn và tín hiệu quan sát ở từng pha |
| Công việc vật lý của store | Store đọc bao nhiêu page, document hoặc mục index? | Kế hoạch thực thi và số liệu của store |

Ví dụ, SQL chỉ chọn `id` và `display_name` có thể chứng minh select list nhỏ. Nó chưa chứng minh engine chỉ đọc hai giá trị từ thiết bị lưu trữ: kho lưu theo hàng có thể vẫn phải đọc các page chứa toàn bộ hàng.

Ngược lại, việc storage engine đọc một page rộng không có nghĩa mọi cột trên page được truyền về ứng dụng. Giảm dữ liệu trả về và giảm I/O vật lý là hai mục tiêu liên quan nhưng cần bằng chứng riêng.

Không dùng một phép đo để thay thế mọi tầng còn lại. Số truy vấn ít chưa chứng minh số cột ít; JSON nhỏ chưa chứng minh ít dữ liệu được tải.

## 2. Viết kỳ vọng trước khi quan sát

Giả sử hệ thống có khách hàng với các thuộc tính:

| Thuộc tính | Vai trò trong ví dụ |
|---|---|
| `id` | Định danh |
| `tenantId` | Phạm vi lọc |
| `displayName` | Tên cần hiển thị |
| `email` | Dữ liệu không cần ở danh sách này |
| `profileText` | Nội dung có thể lớn |
| `address` | Quan hệ hoặc cấu trúc lồng nhau, tùy store |

Màn hình danh sách chỉ cần `id` và `displayName`. Một kỳ vọng kiểm chứng rõ ràng là:

```text
Đúng khách hàng của tenant đã chọn
+ thứ tự kết quả xác định
+ truy vấn nội dung chỉ yêu cầu các trường cần thiết theo mapping
+ không tải profileText chỉ để tạo projection
+ không phát sinh truy vấn quan hệ ngoài dự kiến khi đọc/serialize
```

Đây là kỳ vọng để đối chiếu với thực tế, chưa phải một bảo đảm tự động của Commons.

### 2.1. Bộ dữ liệu nên làm lộ việc tải thừa

Một bộ dữ liệu kiểm chứng nhỏ nhưng có chủ đích có thể gồm:

- Khách hàng có `profileText` dài và có giá trị nhận biết rõ.
- Nhiều khách hàng để nhận diện số truy vấn tăng theo số kết quả.
- Khách hàng không có địa chỉ và khách hàng có địa chỉ đầy đủ.
- Trường tùy chọn có null, và với document store có trường bị thiếu nếu mapping cho phép.
- Hai tenant có dữ liệu khác nhau để kiểm tra bộ lọc.

Nếu mọi trường không cần thiết đều rỗng hoặc rất nhỏ, một phép đo bộ nhớ hay kích thước phản hồi dễ che mất vấn đề. Dù vậy, không cần tạo tập dữ liệu khổng lồ chỉ để xác nhận select list có chứa một cột hay không.

### 2.2. Ghi môi trường cùng với kết quả

Kết quả cần gắn với module Spring Data, phiên bản, provider/driver, kiểu query, mapping, fetch plan, cấu hình cache và dữ liệu thử.

Cùng một interface có thể được xử lý khác nhau giữa JPA, MongoDB hoặc custom repository. Không suy rộng kết luận của một module sang mọi kho dữ liệu chỉ vì cùng dùng `Repository` và interface projection.

## 3. Bắt đầu bằng closed projection đơn giản

### 3.1. Interface chỉ có các accessor cần thiết

Ví dụ trong Spring Data JPA, giả sử `Customer` là entity đã được ánh xạ:

```java
public interface CustomerSummary {
    Long getId();
    String getDisplayName();
}
```

Repository dùng một derived query riêng:

```java
import java.util.List;
import org.springframework.data.repository.Repository;

public interface CustomerRepository
        extends Repository<Customer, Long> {

    List<CustomerSummary> findFirst50ByTenantIdOrderByIdAsc(
        String tenantId
    );
}
```

`CustomerSummary` là closed projection khi các accessor tương ứng với thuộc tính domain và không có biểu thức mở cần truy cập tùy ý vào target.

Trong module có khả năng tối ưu trường hợp này, hạ tầng có thể dùng thông tin projection để giảm dữ liệu cần chọn. Chính query sinh ra mới xác nhận điều đó đã xảy ra.

Tên phương thức riêng cũng giúp phân biệt truy vấn projection với phương thức CRUD cơ sở. Không mặc định việc khai báo lại một phương thức CRUD với ý định “trả projection” sẽ làm mọi module chuyển nó thành projection query; cần tôn trọng chữ ký và cơ chế phương thức cơ sở của module.

### 3.2. Đối chiếu SQL, không chỉ đối chiếu kiểu trả về

Một SQL mong đợi có thể có dạng:

```sql
SELECT c.id, c.display_name
FROM customer c
WHERE c.tenant_id = ?
ORDER BY c.id ASC
LIMIT ?;
```

Đây là SQL minh họa; alias, tên cột và cú pháp giới hạn phụ thuộc mapping và dialect.

Khi kiểm tra, ghi nhận:

- Select list có `profile_text`, `email` hoặc cột ngoài dự kiến không?
- Có join vào bảng địa chỉ hoặc bảng khác không?
- Có thêm truy vấn nội dung, đếm hoặc truy vấn quan hệ không?
- Có phải SQL quan sát được thuộc đúng lời gọi repository đang thử không?

Các cột dùng trong `WHERE` hoặc `ORDER BY` không nhất thiết phải được trả về như cột kết quả. Vì vậy, thấy `tenant_id` trong SQL chưa đủ để nói nó đã được tải vào projection; cần xem nó nằm ở select list hay chỉ ở điều kiện lọc.

Một số query cần chọn thêm trường cho định danh, sort hoặc cơ chế tiếp tục. Nếu có trường bổ sung, phải xác định lý do và hỗ trợ của module, thay vì chỉ so số getter với số cột rồi đánh dấu sai.

### 3.3. Có getter đúng chưa chắc có giá trị đúng

Ngoài số trường, cần xác minh giá trị:

```java
List<CustomerSummary> summaries = repository
    .findFirst50ByTenantIdOrderByIdAsc(tenantId);

for (CustomerSummary summary : summaries) {
    Long id = summary.getId();
    String name = summary.getDisplayName();
    consume(id, name);
}
```

`consume` là thao tác kiểm tra hoặc xử lý của ứng dụng. Cần đọc getter thực sự trong phạm vi quan sát, vì một proxy có thể trì hoãn một phần hành vi đến lúc gọi accessor.

Nếu một getter trả null dù dữ liệu nguồn có giá trị, có thể là lỗi alias, tên thuộc tính hoặc mapping kiểu. Null không chứng minh store đã không đọc cột đó. Ngược lại, giá trị getter đúng cũng chưa chứng minh không có cột thừa trong query.

## 4. Quan sát JPA theo từng pha

### 4.1. Bật công cụ phù hợp với provider

Ví dụ với Hibernate có hỗ trợ các category và thuộc tính bên dưới:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Cấu hình này là ví dụ provider-specific. Nếu dự án dùng provider hoặc phiên bản khác, cần dùng category tương ứng. Không có một logger do Spring Data Commons cung cấp để chứng minh mọi loại store chỉ tải đúng các getter của projection.

SQL giúp xem select list; bind logging giúp liên hệ tham số với truy vấn. Giá trị bind không cho biết đầy đủ dữ liệu trả về và không cần được ghi lại nếu chỉ đang kiểm tra danh sách cột.

Cần biết nguồn log là SQL do provider sinh, SQL đi qua datasource hay số liệu từ server. Mỗi nguồn phản ánh một đoạn khác nhau của đường đi; các logger trùng nhau có thể in cùng một câu lệnh nhiều lần.

### 4.2. Tách truy vấn khỏi việc đọc và serialize

Một lần kiểm chứng nên chia thành:

```text
Pha A: gọi repository
Pha B: đọc các getter mà nghiệp vụ sử dụng
Pha C: tạo DTO hoặc serialize đúng đường đi của ứng dụng
Pha D: đối chiếu query, entity load và dữ liệu quan sát được
```

Nếu pha A có một query nhưng pha B phát sinh thêm 20 query địa chỉ, kết luận “projection chỉ chạy một query” là thiếu phạm vi.

Nếu chỉ serialize sau khi transaction đã kết thúc, có thể xuất hiện lỗi lazy loading thay vì query bổ sung. Nếu tầng web giữ persistence context lâu hơn, serialization lại có thể tải thêm dữ liệu. Cả hai đều là hành vi cần ghi nhận, không phải lý do để bỏ qua pha serialize.

### 4.3. Thống kê Hibernate là bằng chứng bổ trợ

Ví dụ quan sát thống kê trong một môi trường kiểm chứng có kiểm soát:

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory = entityManagerFactory
    .unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();
statistics.setStatisticsEnabled(true);
statistics.clear();

List<CustomerSummary> summaries = repository
    .findFirst50ByTenantIdOrderByIdAsc(tenantId);

long statementsAfterQuery = statistics.getPrepareStatementCount();
long entitiesAfterQuery = statistics.getEntityLoadCount();

for (CustomerSummary summary : summaries) {
    consume(summary.getId(), summary.getDisplayName());
}

long statementsAfterGetters = statistics.getPrepareStatementCount();
long entitiesAfterGetters = statistics.getEntityLoadCount();
```

Đoạn mã giả định `entityManagerFactory`, `repository`, `tenantId` và `consume` đã có trong ngữ cảnh kiểm chứng. Các số liệu phải được đọc cùng SQL và giá trị getter, không dùng riêng lẻ để suy toàn bộ hành vi.

Lưu ý khi diễn giải:

- Thống kê thường thuộc phạm vi SessionFactory, nên hoạt động đồng thời có thể làm nhiễu phép đo.
- Số prepared statement không phải số byte mạng hay số page vật lý được đọc.
- `entityLoadCount` bằng 0 không chứng minh không có dữ liệu được trả về; query scalar/tuple vẫn có kết quả.
- Entity load ít không chứng minh query không chọn cột lớn.
- Provider khác có công cụ và chỉ số khác; đây không phải API thống kê chung của Commons.

### 4.4. Kiểm soát cache và dữ liệu chuẩn bị

Một lần thử sau khi vừa tải toàn bộ entity có thể dùng lại dữ liệu trong persistence context hoặc cache. Khi đó, “không thấy query” không chứng minh projection đã tạo một truy vấn tối ưu.

Một quy trình rõ ràng là:

1. Chuẩn bị và lưu fixture trước pha đo.
2. Hoàn tất hoặc flush các thay đổi cần thiết theo thiết kế thử nghiệm.
3. Dùng persistence context mới hoặc clear context ở ranh giới phù hợp.
4. Xác định trạng thái cache tầng hai và query cache nếu được bật.
5. Bắt đầu ghi nhận truy vấn và reset số liệu quan sát.
6. Gọi đúng một đường đọc rồi tiêu thụ kết quả.

`clear()` của persistence context không đồng nghĩa xóa cache tầng hai, cũng không làm cache database trở nên lạnh. Khi đo hiệu năng, cần báo trạng thái cache riêng; khi kiểm tra select list, chỉ cần bảo đảm đã quan sát đúng query cần kiểm tra.

Không để SQL ghi fixture, chạy migration hoặc query nền lẫn vào số truy vấn của projection.

## 5. Các biến thể cần kiểm chứng riêng

### 5.1. Default method dựa trên các accessor đã khai báo

```java
public interface CustomerSummary {
    Long getId();
    String getDisplayName();

    default String getNormalizedName() {
        String name = getDisplayName();
        return name == null ? "" : name.strip();
    }
}
```

Default method này chỉ tính từ dữ liệu accessor đã có. Trong cơ chế hỗ trợ closed projection, nó không tự đòi thêm `email` hoặc `profileText` từ target.

Dù vậy, vẫn cần kiểm tra query và đường serialization thực tế. Việc thêm một getter mới trong tương lai có thể thay đổi hợp đồng dữ liệu mà hạ tầng sử dụng.

### 5.2. Open projection dùng biểu thức

```java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerLabel {
    Long getId();

    @Value("#{target.displayName + ' <' + target.email + '>'}")
    String getLabel();
}
```

Ở đây, `getLabel()` cần dữ liệu từ target thông qua biểu thức. Hạ tầng không thể chỉ suy mọi nhu cầu dữ liệu từ tên getter như với closed projection đơn giản.

Không kỳ vọng cùng khả năng giảm trường chỉ vì interface vẫn có ít phương thức. Module có thể cần target đầy đủ hơn; biểu thức gọi bean khác cũng có thể thực hiện thêm công việc khi getter được gọi.

Cần quan sát cả query đầu tiên lẫn thời điểm đọc `getLabel()`. Một giá trị nhãn được tạo đúng chỉ chứng minh biểu thức có đủ dữ liệu, chưa chứng minh dữ liệu được tải tối thiểu.

### 5.3. Projection lồng nhau và join

```java
public interface CustomerWithAddress {
    Long getId();
    String getDisplayName();
    AddressView getAddress();

    interface AddressView {
        String getCity();
    }
}
```

Người đọc có thể kỳ vọng chỉ có ba cột khách hàng và một cột thành phố. Với JPA, một thuộc tính lồng nhau có thể dẫn đến join và materialize dữ liệu của quan hệ rộng hơn dự kiến. Trong cách truy cập khác, getter có thể kích hoạt tải quan hệ riêng.

Do đó, cần kiểm tra:

- Join nào xuất hiện trong SQL?
- Select list của bảng liên quan gồm những cột nào?
- Đọc `getAddress().getCity()` có phát sinh query mới không?
- Quan hệ null được biểu diễn ra sao?
- Nếu mở rộng sang collection, số query hoặc số hàng kết quả tăng như thế nào?

Không mặc định nested projection tương đương một truy vấn chọn đúng từng field lá trong mọi store. Mapping của association trong JPA và embedded document trong MongoDB có cơ chế khác nhau.

### 5.4. Fetch plan và query tự khai báo

Entity graph, eager association, fetch join, query native hoặc custom repository có thể thay đổi dữ liệu được lấy. Một projection được sử dụng ở cuối không tự xóa những yêu cầu tải dữ liệu đã được query hoặc code trước đó áp đặt.

Nếu custom repository tải entity rồi mới gọi projection factory, số getter của proxy chỉ giới hạn giao diện nhìn thấy; việc tải entity đã diễn ra. Tương tự, tải `List<Customer>` đầy đủ rồi map sang DTO không chứng minh truy vấn ban đầu đã giảm cột.

## 6. Kiểm chứng field projection trong MongoDB

### 6.1. Tách interface projection khỏi field projection gửi server

Một interface có thể được tạo từ một document đầy đủ hoặc từ một kết quả đã được server giới hạn field. Hai trường hợp có thể cho cùng giá trị getter nhưng khác lượng dữ liệu truyền và ánh xạ.

Ví dụ độc lập với mapping MongoDB, giả sử `CustomerDocument` có id kiểu `String`:

```java
public interface CustomerDocumentSummary {
    String getId();
    String getDisplayName();
}
```

Một query khai báo tường minh các field:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface CustomerDocumentRepository
        extends MongoRepository<CustomerDocument, String> {

    @Query(
        value = "{ 'tenantId': ?0 }",
        fields = "{ '_id': 1, 'displayName': 1 }"
    )
    List<CustomerDocumentSummary> findSummaries(String tenantId);
}
```

Đoạn mã tập trung minh họa trường trả về, không phải một API đã thiết kế đầy đủ cho số lượng dữ liệu lớn. Giới hạn, sort và cách đọc nhiều kết quả phải được bổ sung theo nhu cầu thực tế.

Trong ví dụ, `_id` được khai báo tường minh và mapping cần chuyển nó sang thuộc tính id. Nếu domain đổi tên field bằng mapping, command ở server có thể dùng tên khác với tên accessor Java.

### 6.2. Quan sát command thực tế

Có thể dùng logging phù hợp của module hoặc command monitoring của MongoDB driver để xác định:

```text
filter:     tenantId bằng giá trị đang thử
projection: _id và displayName được chọn
sort:       nếu query có yêu cầu thứ tự
limit:      nếu query có giới hạn
```

Đừng chỉ xem query filter: phần quyết định trường trả về nằm trong projection hoặc các stage tương ứng của aggregation.

Nếu dùng aggregation, cần đọc pipeline thực tế. Một `$project` ở cuối có thể làm nhỏ kết quả trả về, nhưng các stage trước vẫn có thể đọc, join hoặc xử lý nhiều dữ liệu. Cần kiểm tra stage như `$lookup` và vị trí của chúng nếu đang đánh giá tổng công việc.

Đối với trường hợp không khai báo `fields` tường minh mà dựa vào khả năng suy ra projection của module, càng cần quan sát command để biết module có thực sự giảm field ở server hay chỉ tạo proxy sau khi đọc document.

### 6.3. Phân biệt field được trả về với document được đọc

Một projection server-side có thể giảm kích thước BSON trả về và chi phí giải mã. Nó không bảo đảm storage engine không đọc document đầy đủ bên trong.

Để đánh giá công việc của MongoDB, có thể xem kế hoạch và thống kê thực thi của query tương đương, gồm các thông tin như:

- Số document trả về.
- Số document được xem xét.
- Số mục index được xem xét.
- Có phải đọc document ngoài index hay không.
- Index có bao phủ được filter, thứ tự và field trả về trong trường hợp cụ thể không.

Khi dựng query phục vụ giải thích kế hoạch, giữ tương đương filter, projection, sort và limit. Một query chỉ cùng filter nhưng thiếu projection không thay thế được phép kiểm chứng đang làm.

`explain` giúp hiểu kế hoạch và công việc; command của lời gọi repository giúp xác nhận query thực sự được gửi. Cần dùng chúng bổ sung cho nhau.

### 6.4. Batch của driver không tự là N+1

Đọc một cursor có thể gồm lệnh ban đầu và các lần lấy thêm batch, chẳng hạn `getMore`. Không nên đếm mỗi batch là một truy vấn quan hệ N+1.

Ngược lại, nếu đọc từng kết quả lại phát sinh một query khác để lấy đối tượng tham chiếu, cần tách các query đó khỏi việc lấy batch của cùng cursor.

Nhận diện loại command và mục đích của nó quan trọng hơn việc chỉ cộng số dòng log.

## 7. Query tự khai báo, alias và module reactive

### 7.1. Query có select list tường minh vẫn cần kiểm tra mapping

Với JPQL hoặc native SQL, phải đối chiếu ba thứ:

```text
Biểu thức được chọn
    → alias/metadata kết quả
    → accessor của projection
```

Ví dụ, một accessor `getDisplayName()` cần được mapping đúng với thuộc tính hoặc alias mà module dùng. Cột `display_name` được database trả về không tự bảo đảm mọi driver và query path đều ánh xạ nó sang cùng một alias Java.

Nếu getter bị null hoặc sai kiểu, kiểm tra tên alias, quy tắc chữ hoa/thường, chuyển đổi kiểu và dữ liệu thực tế. Không kết luận rằng lỗi đó chứng minh projection đã loại cột khỏi truy vấn.

Đồng thời, một query `SELECT *` vẫn có thể được ánh xạ thành interface ít getter. Interface nhỏ không làm select list tường minh rộng trở nên hẹp một cách tự động.

### 7.2. Không dùng entity làm bước trung gian mà bỏ qua chi phí

So sánh hai đường đi:

```text
Đường A:
store chọn các giá trị cần thiết
  → tuple/document giới hạn
  → interface projection

Đường B:
store trả entity/document đầy đủ
  → ứng dụng tạo projection hoặc DTO
```

Cả hai có thể cho cùng response. Khi mục tiêu là giảm tải ở store, cần nhận biết đang chạy đường nào.

Một projection factory được gọi bằng tay có thể hữu ích để tạo một view trong ứng dụng. Nó không chứng minh đã có pushdown xuống query. Tương tự, annotation serialization chỉ điều khiển dữ liệu xuất ra theo cơ chế serializer, không tự thay đổi query trước đó.

### 7.3. Reactive repository cần được tiêu thụ trong phạm vi quan sát

Với module reactive, việc tạo publisher thông thường chưa đồng nghĩa query đã thực thi. Nếu chỉ gọi repository rồi dừng thu thập log trước subscription, có thể kết luận nhầm rằng query không cần dữ liệu.

Một phép kiểm chứng cần:

1. Chuẩn bị môi trường và bắt đầu ghi nhận.
2. Tạo và đăng ký publisher theo cơ chế phù hợp.
3. Tiêu thụ các giá trị/getter cần kiểm tra.
4. Chờ hoàn tất hoặc lỗi trong phạm vi kiểm chứng.
5. Sau đó mới tổng hợp command, mapping và truy vấn phát sinh.

Không thêm `block()` vào đường chạy production chỉ để có log thuận tiện. Công cụ kiểm chứng có thể sở hữu subscription, còn code ứng dụng cần giữ mô hình thực thi của nó.

Nếu subscriber hủy sớm sau vài phần tử, số liệu chỉ phản ánh phần đã thực thi cùng khả năng buffer/prefetch. Không dùng nó để khẳng định toàn bộ nguồn sẽ luôn tải cùng lượng dữ liệu.

## 8. Lập ma trận kiểm chứng thay vì thử một trường hợp

Một ma trận hữu ích có thể bắt đầu như sau:

| Trường hợp | Nội dung cần quan sát | Kết luận chỉ đưa ra sau khi có bằng chứng |
|---|---|---|
| Closed projection với scalar getter | Select list/field projection, giá trị getter | Có giảm trường ở query path này không |
| Default method dùng accessor sẵn có | Query trước và sau gọi default method | Có thêm dữ liệu hoặc query không |
| Open projection với biểu thức | Target cần thiết, truy vấn khi đọc getter | Tối ưu trường có còn như closed projection không |
| Nested projection | Join, cột/document lồng nhau, query phụ | Quan hệ được tải rộng đến đâu |
| Query native hoặc tự khai báo | Select list, alias và kiểu dữ liệu | Kết quả ánh xạ có đúng không |
| Custom projection factory | Nguồn target trước khi tạo proxy | Projection diễn ra trước hay sau khi tải đầy đủ |
| Cache lạnh/ấm theo định nghĩa thử nghiệm | Query thực sự chạy và cache được dùng | Bằng chứng có bị cache che khuất không |
| Serialize theo đường ứng dụng | Getter được gọi và query phát sinh | Response nhỏ có đi cùng truy xuất gọn không |

Không cần chạy mọi ô cho mọi thay đổi nhỏ. Chọn những biến thể có mặt trong đường đọc đang đánh giá, rồi ghi rõ phần chưa được kiểm chứng.

### 8.1. Tránh thay nhiều yếu tố cùng lúc

Nếu muốn đánh giá ảnh hưởng của projection, nên giữ tương đương:

- Bộ lọc và tham số.
- Thứ tự và giới hạn.
- Dữ liệu nguồn.
- Fetch plan, index và cấu hình quan trọng.
- Trạng thái cache theo kịch bản đã chọn.
- Công việc xử lý sau khi nhận kết quả.

Nếu một bên đọc 50 khách hàng còn bên kia đọc 5.000 khách hàng, khác biệt thời gian không chỉ đến từ projection. Nếu một bên serialize cả quan hệ còn bên kia chỉ đọc id, cần báo rõ sự khác biệt về đường tiêu thụ.

### 8.2. Tách count query và query phụ

Một phương thức trả `Page<Projection>` có thể cần query đếm. Điều đó khác với tải thừa một trường lớn trong query nội dung và cũng khác N+1 do quan hệ.

Khi báo số truy vấn, nên phân loại:

```text
Query nội dung
Query đếm nếu có
Query nạp quan hệ
Query hoặc command lấy batch
Hoạt động ngoài phạm vi phép thử
```

Không áp một kỳ vọng “phải đúng một query” cho mọi loại store, kiểu trả về và mapping. Chọn kỳ vọng theo hợp đồng, rồi kiểm tra đúng phần công việc cần ngăn tăng ngoài dự kiến.

## 9. Từ bằng chứng đến kết luận

### 9.1. Mẫu ghi nhận một lần kiểm chứng

```text
Repository và phương thức:
Module/provider/driver và phiên bản:
Loại projection:
Dữ liệu, filter, sort, limit:
Trạng thái cache và transaction:

Pha gọi repository:
  Query/command nội dung:
  Select list hoặc field projection:
  Query phụ và lý do:

Pha đọc getter:
  Getter đã gọi:
  Query phát sinh:
  Giá trị/mapping có đúng không:

Pha serialize hoặc tạo DTO:
  Đường xử lý đã dùng:
  Query phát sinh:

Kế hoạch và công việc của store nếu đã đo:
Kết luận trong phạm vi đã quan sát:
Những điều chưa được chứng minh:
```

Mẫu này giúp phân biệt bằng chứng thực thi với suy luận từ code. Không cần lưu toàn bộ dữ liệu trả về nếu mục tiêu chỉ là xác định trường, số query và mapping.

### 9.2. Các kết luận có phạm vi rõ ràng

Một kết luận phù hợp có thể là:

> Với derived query và mapping đang dùng, query nội dung chỉ chọn id và tên hiển thị. Việc đọc hai getter và serialize đường đã thử không phát sinh query quan hệ. Chưa có số liệu để kết luận về I/O vật lý của storage engine.

Một kết luận khác có thể là:

> Interface trả đúng hai giá trị, nhưng query thực tế vẫn chọn cột profile lớn. Projection hiện chỉ làm nhỏ giao diện ứng dụng trong đường đọc này; cần thay query path hoặc cơ chế được module hỗ trợ nếu muốn giảm dữ liệu trả từ store.

Đây là các mẫu cách diễn đạt, không phải kết quả đã đo cho những đoạn code trong bài.

Tránh kết luận “projection không tải entity ở mọi nơi” chỉ từ một trường hợp closed projection. Open projection, nested projection, query tự khai báo và custom repository có thể đi theo đường khác.

### 9.3. Phân biệt đúng dữ liệu với nhanh hơn

Một query chọn ít trường hơn có thể giảm payload và chi phí ánh xạ. Thời gian tổng vẫn có thể bị chi phối bởi lọc, sort, join, mạng hoặc công việc khác.

Ngược lại, một query nhanh hơn trong một lần thử chưa chứng minh giảm field. Cache hoặc kế hoạch truy vấn khác có thể tạo ra khác biệt đó.

Nếu mục tiêu là hiệu năng, đo riêng độ trễ, số byte hoặc kích thước kết quả khi quan sát được, bộ nhớ, entity load và công việc store. Giữ bằng chứng về trường đã chọn để giải thích nguyên nhân thay vì chỉ báo một con số thời gian.

## 10. Chẩn đoán những dấu hiệu dễ gây hiểu nhầm

| Dấu hiệu | Chưa thể kết luận | Hướng kiểm tra |
|---|---|---|
| JSON không có `profileText` | Store không tải profile | Select list/field projection và query phụ |
| Getter trả null | Cột đã được loại khỏi query | Alias, mapping, kiểu dữ liệu, giá trị nguồn |
| Không có SQL mới | Projection không cần truy vấn | Cache, subscription, phạm vi logger và context |
| Chỉ có một SQL | Query chỉ lấy ít dữ liệu | Số cột, số hàng, join và độ rộng kết quả |
| Không có entity load | Không có dữ liệu được tải | Tuple/scalar/document và kết quả trả về |
| Có nhiều command | Chắc chắn N+1 | Phân biệt query phụ, count và cursor batch |
| Interface chỉ có nested city | Store chỉ lấy field city | Join hoặc projection của cấu trúc lồng nhau |
| Query có `tenant_id` | Tenant id được trả về | Phân biệt SELECT với WHERE/ORDER BY |
| Truy vấn nhanh ở fixture nhỏ | Projection đã tối ưu ở quy mô thật | Kế hoạch, dữ liệu lớn và chi phí ánh xạ |
| Không thấy query lúc tạo Flux | Không cần truy cập store | Subscription và thời điểm hoàn tất |

Projection giúp thiết kế shape dữ liệu. Nó không thay thế bộ lọc phạm vi, phân quyền hoặc chính sách truy cập dữ liệu ở đường repository. Khi chỉnh query để giảm trường, vẫn phải giữ nguyên điều kiện nghiệp vụ cần thiết.

## 11. Duy trì kiểm chứng khi code thay đổi

Sau khi đã hiểu query path, có thể thêm kiểm chứng hồi quy có mục tiêu trong dự án tương ứng. Những điều đáng giữ là:

- Getter trả đúng giá trị với dữ liệu đặc trưng.
- Query nội dung không chọn cột lớn ngoài hợp đồng ở đường đã kiểm chứng.
- Đọc hoặc serialize không tạo số query quan hệ tăng ngoài dự kiến.
- Alias và chuyển đổi kiểu tiếp tục đúng với query tự khai báo.
- Nested projection và trường null được xử lý theo hợp đồng đã chọn.

Tránh so sánh nguyên văn toàn bộ SQL có alias do provider sinh chỉ để bảo vệ hai cột cần thiết. Alias, khoảng trắng hoặc cú pháp giới hạn có thể đổi mà hành vi không đổi. Phép kiểm tra nên tập trung vào điều quan trọng đối với đường đọc, dùng công cụ capture/quan sát phù hợp với store.

Những thay đổi cần xem lại bằng chứng gồm thêm getter, thêm `@Value`, thêm nested projection, sửa fetch plan, đổi loại query hoặc nâng cấp module/provider. Đây là các thay đổi có thể làm khác query path, không chỉ khác giao diện Java.

## 12. Bài tập vận dụng

### Bài tập 1: Hai getter nhưng SQL rộng

`CustomerSummary` chỉ có id và tên. SQL lại chọn cả email và profile lớn, còn JSON chỉ có hai trường. Điều gì đã được chứng minh?

**Gợi ý lời giải:** Response được giới hạn và getter có thể đúng, nhưng truy vấn chưa giảm cột như kỳ vọng. Cần xem projection được tạo từ entity đầy đủ, open projection hay custom query/path nào đang được dùng.

### Bài tập 2: Một query trước khi đọc getter

Một phép thử đếm được một query ngay sau lời gọi repository. Khi serializer chạy, mỗi khách hàng lại có thêm một query địa chỉ. Báo cáo ban đầu thiếu gì?

**Gợi ý lời giải:** Phạm vi quan sát chưa bao gồm tiêu thụ projection. Cần ghi nhận query ở pha getter và serialize, rồi phân tích nested projection, lazy association hoặc biểu thức liên quan.

### Bài tập 3: MongoDB chỉ trả hai field

Command có projection `_id` và `displayName`. Có thể kết luận storage engine không đọc document đầy đủ không?

**Gợi ý lời giải:** Chưa. Command giúp xác nhận field được yêu cầu trả về. Công việc vật lý cần xem kế hoạch và thống kê thực thi, nhất là việc có cần fetch document ngoài index hay không.

### Bài tập 4: Getter bị null trong native query

Database có tên hiển thị nhưng projection trả null. Một người cho rằng đó là bằng chứng cột không được tải. Cần kiểm tra gì?

**Gợi ý lời giải:** Kiểm tra select list trước, sau đó alias, quy tắc tên/case, kiểu dữ liệu và cách module ánh xạ accessor. Null do mapping không tương đương việc database không chọn cột.

### Bài tập 5: Cache che mất query

Trước khi đo projection, test vừa tải toàn bộ khách hàng trong cùng persistence context. Không thấy SQL mới. Có thể kết luận projection không gây tải dữ liệu không?

**Gợi ý lời giải:** Không. Dữ liệu có thể đã có sẵn. Cần tách fixture, dùng context/cache theo kịch bản rõ ràng và quan sát một lần thực thi phù hợp trước khi kết luận về query sinh ra.

## 13. Những điều cần ghi nhớ

- Interface ít getter là hợp đồng nhìn dữ liệu, chưa phải bằng chứng store chỉ trả ít field.
- Kiểm chứng theo các tầng: query, dữ liệu trả về, mapping, sử dụng getter/serialize và công việc vật lý của store.
- Closed projection tạo cơ hội tối ưu trong module hỗ trợ; query thực tế xác nhận cơ hội đó có được sử dụng không.
- Open projection, nested projection, fetch plan và custom repository cần được kiểm tra riêng.
- Cache, query đếm, cursor batch và hoạt động nền có thể làm sai cách đọc số liệu nếu không phân loại.
- Query ít cột, payload nhỏ, entity load thấp và I/O vật lý thấp là những kết luận khác nhau.
- Gắn kết luận với module, phiên bản, mapping và đường tiêu thụ đã thử; không suy rộng một kết quả cho mọi store.

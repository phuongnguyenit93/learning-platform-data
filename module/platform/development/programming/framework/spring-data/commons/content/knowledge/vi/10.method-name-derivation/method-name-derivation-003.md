# count, exists, delete và remove

Không phải mọi phương thức repository đều cần trả về entity. Khi nghiệp vụ chỉ cần biết có bao nhiêu bản ghi, một bản ghi có tồn tại hay không, hoặc cần xóa dữ liệu theo điều kiện, Spring Data cung cấp các subject tương ứng trong tên phương thức suy diễn: `count`, `exists`, `delete` và `remove`.

Trong chương **Suy diễn tên phương thức** của **SPRING_DATA_COMMONS**, bài này giải thích cách đọc các subject đó, thiết kế chữ ký phù hợp và phân biệt ý nghĩa chung với cách thực thi của từng kho dữ liệu. Đặc biệt, tên `deleteBy...` không phải một lời cam kết rằng framework sẽ phát đúng một câu lệnh bulk delete.

## 1. Subject quyết định loại thao tác, predicate quyết định điều kiện

Cấu trúc điển hình của một tên phương thức suy diễn là:

```text
<subject>By<predicate>

count  By TenantIdAndStatus
exists By TenantIdAndExternalCode
delete By TenantIdAndStatusAndCreatedAtBefore
remove By TenantIdAndStatusAndCreatedAtBefore
```

`By` phân tách phần mô tả thao tác với phần điều kiện. Những thành phần sau `By` được giải quyết theo thuộc tính domain, keyword và quy tắc kết hợp điều kiện mà module lưu trữ hỗ trợ.

| Subject | Câu hỏi hoặc hành động | Kiểu trả về đồng bộ điển hình |
| --- | --- | --- |
| `count…By` | Có bao nhiêu kết quả khớp điều kiện? | `long` |
| `exists…By` | Có ít nhất một kết quả khớp điều kiện không? | `boolean` |
| `delete…By` | Xóa các kết quả khớp điều kiện | `void` hoặc số lượng xóa, nếu module hỗ trợ |
| `remove…By` | Cùng nhóm thao tác xóa như `delete…By` | Theo khả năng của module, không có hợp đồng riêng chỉ vì đổi subject |

Spring Data Commons cung cấp nền tảng phân tích và metadata dùng chung. Module tích hợp kho dữ liệu quyết định toán tử nào được thực thi, chữ ký nào hợp lệ, truy vấn được tối ưu ra sao và transaction có ý nghĩa gì.

Các quy tắc đặt tên ở đây áp dụng khi phương thức **thực sự được giải quyết như một derived query**. Phương thức đã có implementation từ repository cơ sở, fragment tùy biến hoặc có truy vấn khai báo riêng cần được xét theo nguồn implementation/truy vấn đang được chọn.

## 2. Mô hình ví dụ và phạm vi truy vấn

Giả sử domain `PurchaseOrder` có các thuộc tính Java:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh đơn hàng |
| `tenantId` | `String` | Phạm vi tổ chức sở hữu dữ liệu |
| `externalCode` | `String` | Mã đơn hàng do hệ thống bên ngoài cung cấp |
| `status` | `OrderStatus` | Trạng thái nghiệp vụ |
| `createdAt` | `Instant` | Thời điểm tạo |
| `customerEmail` | `String` | Email khách hàng |

```java
public enum OrderStatus {
    NEW, PAID, CANCELLED
}
```

Các ví dụ đồng bộ chính bên dưới sử dụng **Spring Data JPA**, với `PurchaseOrder` là một entity đã được ánh xạ đầy đủ. Bảng thuộc tính là mô hình để đọc chữ ký; phần cấu hình persistence, constructor, accessor và mapping chi tiết được lược bỏ. Nếu chuyển sang module khác, cần dùng metadata ánh xạ phù hợp với module đó.

`tenantId` được đưa vào điều kiện để phạm vi dữ liệu thể hiện ngay trên phương thức. Trong ứng dụng thực tế, tầng gọi cần cung cấp phạm vi hợp lệ từ ngữ cảnh đã xác định. Một tham số `null` không có nghĩa phổ quát là “bỏ qua bộ lọc”; ngữ nghĩa tham số rỗng phụ thuộc toán tử và module.

## 3. count: đếm kết quả mà không yêu cầu tải entity

### 3.1. Ví dụ chữ ký

```java
import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    long countByTenantIdAndStatus(
            String tenantId,
            OrderStatus status);
}
```

Tên phương thức được đọc thành: đếm các đơn hàng có `tenantId` tương ứng **và** có `status` tương ứng.

Ví dụ gọi:

```java
long paidOrders = repository.countByTenantIdAndStatus(
        "tenant-a", OrderStatus.PAID);
```

Kết quả là số lượng khớp điều kiện tại thời điểm truy vấn quan sát dữ liệu theo cơ chế nhất quán và transaction của kho dữ liệu. Nếu không có kết quả, truy vấn đếm thông thường trả `0`, không phải một danh sách rỗng hay một entity giả.

`long` là lựa chọn rõ ràng cho hợp đồng đếm. Không chọn `int` chỉ vì dữ liệu thử hiện có ít hàng; một tập dữ liệu thực tế có thể vượt giới hạn của kiểu đó.

### 3.2. count khác với tải danh sách rồi lấy size

```java
// Chỉ cần số lượng nhưng lại yêu cầu tải các entity.
int count = repository.findByTenantIdAndStatus(tenantId, status).size();
```

Đoạn trên giả định đã có thêm một phương thức trả danh sách. Nó có thể làm ứng dụng đọc và materialize nhiều entity chỉ để lấy một con số.

Một phương thức `countBy...` biểu đạt đúng nhu cầu ở hợp đồng repository và cho phép module thực hiện truy vấn đếm phù hợp. Tuy vậy, “không tải entity” không có nghĩa “đếm luôn rẻ”: chi phí vẫn phụ thuộc điều kiện lọc, chỉ mục, phân bố dữ liệu và công nghệ lưu trữ.

### 3.3. count toàn bộ khác với count theo điều kiện

Khi kế thừa `CrudRepository`, phương thức cơ sở `count()` đếm toàn bộ tập entity thuộc repository theo ngữ nghĩa của implementation. Nó không tự biết tenant hiện tại hoặc trạng thái mà caller muốn xét.

```java
long total = repository.count();
```

Dòng trên chỉ khả dụng nếu interface đã công bố hoặc kế thừa phương thức cơ sở đó. Interface chỉ `extends Repository<PurchaseOrder, Long>` trong các ví dụ tối giản không tự có đầy đủ các phương thức CRUD.

Nếu yêu cầu là đếm đơn `PAID` trong một tenant, hãy dùng hợp đồng có điều kiện tương ứng, chẳng hạn `countByTenantIdAndStatus(...)`, thay vì dùng tổng toàn bộ rồi điều chỉnh bằng suy luận ở caller.

### 3.4. Cẩn thận với countDistinct

Ví dụ Spring Data JPA:

```java
long countDistinctByTenantIdAndStatus(
        String tenantId,
        OrderStatus status);
```

Không đọc tên này thành “đếm số trạng thái khác nhau”. Trong trường hợp JPA suy diễn đếm distinct theo định danh entity, một truy vấn dạng này có thể có cùng kết quả với đếm các entity khớp điều kiện vì định danh vốn là duy nhất.

Nếu yêu cầu là đếm email khách hàng khác nhau, cần diễn đạt trực tiếp đối tượng được đếm. Ví dụ JPQL trong Spring Data JPA:

```java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    select count(distinct o.customerEmail)
    from PurchaseOrder o
    where o.tenantId = :tenantId
    """)
long countDistinctCustomerEmails(@Param("tenantId") String tenantId);
```

Theo ngữ nghĩa phép đếm giá trị của JPQL, `null` không được tính như một email riêng trong biểu thức này. Cần xác định rõ nghiệp vụ muốn đếm entity, giá trị khác nhau hay nhóm kết quả; không chỉ thêm từ `Distinct` vào tên rồi mặc định framework hiểu đúng đơn vị đếm.

## 4. exists: kiểm tra tồn tại thay vì hỏi tổng số

### 4.1. Ví dụ chữ ký

```java
boolean existsByTenantIdAndExternalCode(
        String tenantId,
        String externalCode);
```

Ví dụ sử dụng:

```java
boolean alreadyKnown = repository.existsByTenantIdAndExternalCode(
        tenantId, externalCode);
```

Kết quả trả lời một câu hỏi nhị phân: có ít nhất một entity khớp điều kiện hay không. Nó không cho biết tổng số, không trả entity đại diện và không khẳng định bộ dữ liệu chỉ có một kết quả.

Khi chỉ cần kiểm tra tồn tại, `existsBy...` làm ý định rõ hơn việc gọi `countBy... > 0` hoặc tải một danh sách rồi kiểm tra rỗng. Module có thể chọn cách thực thi phù hợp với phép kiểm tra tồn tại.

Tuy nhiên, không cam kết rằng mọi module đều tạo SQL `EXISTS`, mọi provider đều dừng sau đúng một hàng, hoặc `existsBy...` luôn nhanh hơn một truy vấn đếm trên mọi dữ liệu. Commons cung cấp ý nghĩa thao tác, không quy định một execution plan duy nhất.

### 4.2. exists không phải khóa chống trùng

Mẫu mã sau có một khoảng thời gian giữa kiểm tra và ghi:

```java
if (!repository.existsByTenantIdAndExternalCode(tenantId, code)) {
    // Tạo và lưu một đơn hàng có cùng cặp tenantId / externalCode.
}
```

Hai request có thể cùng thấy `false` rồi cùng thử tạo. `exists` không đặt ra một ràng buộc duy nhất và không tự tạo khóa liên request.

Nếu nghiệp vụ yêu cầu cặp `(tenantId, externalCode)` là duy nhất, cần ràng buộc phù hợp trong kho dữ liệu hoặc một cơ chế ghi nguyên tử tương đương mà kho dữ liệu hỗ trợ. Kiểm tra `exists` có thể phục vụ trải nghiệm hoặc nhánh nghiệp vụ, còn tính duy nhất phải được bảo đảm ở nơi có thể xử lý cạnh tranh đúng.

Tương tự, `exists == true` không bảo đảm entity vẫn tồn tại ở một lần đọc sau: một thao tác đồng thời có thể xóa hoặc thay đổi dữ liệu giữa hai lần truy cập.

## 5. delete và remove: hai subject cùng nhóm thao tác xóa

### 5.1. Ví dụ derived delete trong Spring Data JPA

```java
import java.time.Instant;
import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    long deleteByTenantIdAndStatusAndCreatedAtBefore(
            String tenantId,
            OrderStatus status,
            Instant cutoff);
}
```

Tên phương thức diễn đạt việc xóa đơn hàng thỏa cả ba điều kiện:

```text
tenantId = tenantId truyền vào
AND status = status truyền vào
AND createdAt < cutoff
```

`Before` là điều kiện nhỏ hơn trong ví dụ thời gian này; bản ghi đúng tại `cutoff` không thuộc tập cần xóa. Nếu nghiệp vụ muốn lấy cả thời điểm biên, cần chọn toán tử được hỗ trợ có ngữ nghĩa tương ứng.

Một tên dùng subject `remove` có cùng ý định:

```java
long removeByTenantIdAndStatusAndCreatedAtBefore(
        String tenantId,
        OrderStatus status,
        Instant cutoff);
```

Hai chữ ký là hai phương án minh họa. Thông thường chỉ cần công bố một tên thống nhất trong repository để tránh hai API đồng nghĩa không cần thiết.

### 5.2. Không suy diễn khác biệt nghiệp vụ từ từ delete hoặc remove

Trong cơ chế suy diễn tên, `delete` và `remove` cùng thuộc nhóm thao tác xóa. Không có quy tắc chung rằng:

- `delete` là xóa cứng còn `remove` là xóa mềm.
- `delete` chạy một câu bulk SQL còn `remove` xóa từng entity.
- `remove` tự kích hoạt auditing còn `delete` bỏ qua auditing.
- Một tên giữ quan hệ còn tên kia xóa cascade.

Soft delete, callback, cascade, transaction và cách thực thi phụ thuộc mapping, implementation và module. Nếu ứng dụng muốn chuyển `status` hoặc đánh dấu một cờ thay vì xóa, cần triển khai đúng thao tác cập nhật hoặc cơ chế soft delete đã chọn; đổi subject sang `remove` không tạo ra hành vi đó.

### 5.3. Không có bản ghi phù hợp là một kết quả bình thường

Một derived delete trả số lượng thường trả `0` nếu không có entity phù hợp. Đó không phải dấu hiệu “không tìm thấy câu truy vấn”.

Cần phân biệt:

- **Không phân giải được phương thức:** sai tên thuộc tính, thiếu nguồn truy vấn hoặc chữ ký không được hỗ trợ.
- **Có truy vấn hợp lệ nhưng không khớp dữ liệu:** thao tác có thể kết thúc bình thường với số lượng bằng `0`.
- **Có lỗi trong quá trình xóa:** callback, ràng buộc dữ liệu, transaction hoặc kết nối có thể làm thao tác thất bại.

## 6. Kiểu trả về của thao tác xóa phải theo module

Các hình dạng thường cần phân biệt:

| Hình dạng | Ý định | Phạm vi cần xác nhận |
| --- | --- | --- |
| `void deleteBy...(...)` | Không cần nhận số lượng hoặc entity | Kiểm tra module có hỗ trợ chữ ký này |
| `long deleteBy...(...)` | Cần nhận số entity được xử lý theo hợp đồng xóa | Phù hợp với ví dụ derived delete JPA trong bài; không tự áp dụng sang mọi module |
| `List<PurchaseOrder> removeBy...(...)` | Nhận các entity thuộc thao tác xóa | Là một khả năng của derived delete trong Spring Data JPA, không phải hợp đồng phổ quát của Commons |
| Kiểu reactive, như `Mono<Void>` | Biểu diễn việc hoàn tất bất đồng bộ | Phụ thuộc module reactive, kiểu trả về được hỗ trợ và subscription |

Ví dụ riêng của Spring Data JPA:

```java
import java.util.List;

List<PurchaseOrder> removeByTenantIdAndStatus(
        String tenantId,
        OrderStatus status);
```

Danh sách là các đối tượng gắn với thao tác xóa trong implementation đó, không phải một kiểu “bản ghi đã xóa” dùng thống nhất cho mọi kho dữ liệu. Không nên tiếp tục coi chúng là các entity còn được lưu bình thường để cập nhật nghiệp vụ sau đó.

Chọn danh sách chỉ khi caller cần dữ liệu đó và kích thước tập kết quả phù hợp. Việc nhận thêm entity có thể tăng tải bộ nhớ và làm hợp đồng API lớn hơn nhu cầu thực tế.

Một số kho dữ liệu có API xóa-trả-về riêng hoặc chỉ hỗ trợ kết quả đếm. Chúng không trở thành tương đương nhau chỉ vì phương thức đều bắt đầu bằng `removeBy`.

## 7. Derived delete trong JPA khác với bulk delete

Đây là khác biệt quan trọng vì nó ảnh hưởng callback, bộ nhớ và trạng thái persistence context.

### 7.1. Derived delete JPA có thể chọn entity rồi xóa từng entity

Với Spring Data JPA, derived delete điển hình truy vấn các entity khớp điều kiện rồi thực hiện xóa từng entity theo cơ chế JPA. Cách này cho phép các lifecycle callback như `@PreRemove` được gọi theo vòng đời entity.

Hệ quả cần hiểu:

- Không nên coi `long deleteBy...` là một lệnh `DELETE WHERE ...` duy nhất chỉ vì kết quả trả về là số lượng.
- Entity phù hợp có thể được tải vào bộ nhớ và giữ trong persistence context trong thời gian transaction.
- Cascade remove và các liên hệ được xử lý theo mapping và cơ chế của provider.
- Một tập xóa lớn có thể tạo nhiều công việc hơn việc nhìn vào chữ ký phương thức.

Đây là hành vi của JPA module trong trường hợp đang mô tả, không phải thuật toán xóa bắt buộc cho repository MongoDB, JDBC, R2DBC hoặc những kho khác.

### 7.2. Bulk delete JPA được khai báo riêng

Ví dụ một phương thức bulk JPQL, không còn là derived delete:

```java
import java.time.Instant;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

@Modifying
@Query("""
    delete from PurchaseOrder o
    where o.tenantId = :tenantId
      and o.status = :status
      and o.createdAt < :cutoff
    """)
int deleteExpiredInBulk(
        @Param("tenantId") String tenantId,
        @Param("status") OrderStatus status,
        @Param("cutoff") Instant cutoff);
```

`@Modifying` thuộc Spring Data JPA và cho biết một truy vấn khai báo như trên là thao tác sửa đổi dữ liệu. Derived delete không cần thêm `@Modifying` chỉ để parser hiểu subject `delete`.

Với bulk update/delete JPA, kiểu trả về được hỗ trợ là hợp đồng riêng của cơ chế modifying query; ví dụ này dùng `int`. Không sao chép `long` từ derived delete sang mọi phương thức `@Modifying` rồi mặc định nó hợp lệ.

### 7.3. So sánh hành vi

| Khía cạnh | Derived delete trong ví dụ JPA | Bulk JPQL delete |
| --- | --- | --- |
| Nguồn mô tả truy vấn | Tên phương thức | Chuỗi JPQL khai báo |
| Cách xử lý điển hình | Tìm entity rồi xóa qua vòng đời entity | Gửi thao tác bulk tới provider/cơ sở dữ liệu |
| `@PreRemove` theo từng entity | Có thể được thực hiện qua cơ chế xóa entity | Không đi qua callback remove của từng entity theo cách đó |
| Cascade kiểu vòng đời JPA | Theo mapping xóa entity | Không tự có cùng hành vi như gọi remove từng entity |
| Bộ nhớ cho entity khớp | Có thể đáng kể khi tập kết quả lớn | Không cần tải từng entity mục tiêu chỉ để thực hiện câu lệnh bulk |
| Entity đã có trong persistence context | Tham gia cơ chế quản lý vòng đời | Có thể trở nên không đồng bộ với dữ liệu sau bulk |

Bulk delete không tự làm các entity đang được quản lý trong persistence context biến mất hoặc được cập nhật đúng trạng thái. Cần thiết kế ranh giới transaction, flush và việc clear/refresh khi phù hợp. Nếu dùng các tùy chọn tự clear/flush của `@Modifying`, phải hiểu tác động tới toàn bộ persistence context liên quan, không chỉ những entity mà caller đang nhìn vào.

Cơ sở dữ liệu vẫn có thể có foreign key cascade hoặc trigger. Chúng là cơ chế khác với cascade và callback của JPA; không dùng số lượng trả về để suy ra toàn bộ số dòng phụ đã bị trigger/cascade tác động.

### 7.4. Top hoặc First không phải cam kết giới hạn xóa theo lô

Không suy từ khả năng `findTop100By...` sang kết luận rằng `deleteTop100By...` sẽ xóa đúng tối đa 100 entity trên mọi module. Việc hỗ trợ giới hạn cho thao tác xóa và ngữ nghĩa thứ tự phải được xác nhận riêng.

Nếu cần dọn dữ liệu lớn theo lô, hãy thiết kế thuật toán và API phù hợp với kho dữ liệu: xác định một tập định danh hữu hạn, xử lý cạnh tranh, transaction và cách tiếp tục giữa các lô. Đó là một quyết định triển khai, không tự có từ một subject trong tên.

## 8. Transaction và thời điểm có hiệu lực

Ví dụ **Spring Data JPA**, tầng service đặt ranh giới transaction cho derived delete:

```java
import java.time.Instant;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCleanupService {
    private final PurchaseOrderRepository repository;

    public OrderCleanupService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public long deleteOldCancelledOrders(String tenantId, Instant cutoff) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }
        Objects.requireNonNull(cutoff, "cutoff is required");

        return repository.deleteByTenantIdAndStatusAndCreatedAtBefore(
                tenantId, OrderStatus.CANCELLED, cutoff);
    }
}
```

Ví dụ giả định lời gọi đi qua service bean do Spring quản lý để transaction advice có hiệu lực. Hạ tầng transaction manager và JPA phải được cấu hình phù hợp.

Các query method do ứng dụng khai báo không nên bị mặc định là đã có đúng transaction chỉ vì những phương thức CRUD cơ sở có cấu hình transaction riêng trong implementation. Với thao tác xóa JPA, cần bảo đảm transaction ghi có hiệu lực; có thể đặt ở service như trên hoặc ở phạm vi repository thích hợp theo thiết kế.

Không để thao tác xóa nằm trong một transaction đã được thiết kế chỉ để đọc rồi kỳ vọng mọi môi trường vẫn xử lý như transaction ghi. Các gợi ý `readOnly` và cách thực thi cụ thể còn phụ thuộc transaction manager/provider.

### 8.1. Số lượng trả về không phải bằng chứng commit độc lập

Một phương thức xóa có thể xử lý một tập entity rồi trả số lượng, nhưng transaction bao ngoài vẫn còn đang chạy. Nếu phần việc sau đó gây rollback hoặc commit thất bại, kết quả cuối cùng trong kho dữ liệu khác với việc “đã xóa vĩnh viễn từng ấy hàng”.

Vì vậy, cần đọc số lượng theo hợp đồng thao tác trong transaction hiện tại. Không dùng nó làm bằng chứng duy nhất để phát một thông báo bên ngoài đòi hỏi dữ liệu đã commit mà bỏ qua ranh giới transaction của ứng dụng.

### 8.2. Không đếm trước để suy ra chắc chắn số lượng sẽ xóa

```java
long before = repository.countByTenantIdAndStatus(tenantId, status);
// Một thao tác đồng thời có thể thay đổi dữ liệu ở đây.
long removed = repository.deleteByTenantIdAndStatusAndCreatedAtBefore(
        tenantId, status, cutoff);
```

Ngay ở ví dụ này, hai predicate còn khác nhau vì phép đếm chưa lọc `createdAt`. Nhưng kể cả khi predicate giống nhau, thay đổi đồng thời và mức cô lập transaction vẫn có thể làm hai số khác nhau.

Nếu cần biết số lượng của chính thao tác xóa, hãy dùng kết quả thao tác theo hợp đồng module, thay vì coi một phép đếm trước đó là kết quả chắc chắn.

## 9. Phân biệt subject suy diễn với phương thức CRUD cơ sở

Khi kế thừa `CrudRepository`, các phương thức như `count()`, `existsById(ID)`, `deleteById(ID)` và `deleteAll()` đã có ý nghĩa cơ sở. Không nên phân tích lại chúng như những tên tùy ý của ứng dụng.

| Phương thức | Cách hiểu |
| --- | --- |
| `count()` | Thao tác đếm cơ sở, không có predicate nghiệp vụ trong tên |
| `existsById(id)` | Kiểm tra theo định danh của entity |
| `deleteById(id)` | Xóa theo định danh của entity |
| `deleteAll()` | Thao tác xóa toàn bộ tập entity theo hợp đồng repository cơ sở |
| `countByTenantIdAndStatus(...)` | Phương thức suy diễn có predicate cụ thể |
| `deleteByTenantIdAndStatus(...)` | Phương thức suy diễn có phạm vi cụ thể |

Tên `existsById` và `deleteById` là những tên cơ sở đặc biệt. Nếu định danh thật có tên thuộc tính là `pk`, còn domain đồng thời có một thuộc tính thông thường tên `id`, các phương thức cơ sở vẫn nhắm tới định danh thật, không tự đổi sang thuộc tính thông thường chỉ vì nó tên `id`.

Muốn truy vấn một thuộc tính có tên dễ nhầm với tên cơ sở, cần thiết kế tên phương thức rõ ràng và kiểm tra cơ chế phân giải của module. Cũng cần xác định phương thức đó có đang override một method cơ sở hoặc được fragment cung cấp implementation hay không.

Tên bắt đầu bằng `delete` cũng không thay thế nội dung của một truy vấn đã khai báo. Chẳng hạn, với Spring Data JPA, nếu muốn một `@Query` là bulk delete thì chính chuỗi JPQL phải là câu delete và phải có cấu hình modifying thích hợp; tên Java đơn thuần không sửa một chuỗi `select` thành thao tác xóa.

## 10. Hình dạng reactive cần hợp đồng riêng

Với một module reactive có hỗ trợ các phép suy diễn tương ứng, hình dạng chữ ký có thể là:

```java
Mono<Long> countByTenantIdAndStatus(
        String tenantId, OrderStatus status);

Mono<Boolean> existsByTenantIdAndExternalCode(
        String tenantId, String externalCode);

Mono<Void> deleteByTenantIdAndStatus(
        String tenantId, OrderStatus status);
```

Đây là minh họa cách biểu diễn kết quả bất đồng bộ; cần đối chiếu module thực tế để chọn kiểu trả về xóa được hỗ trợ, đặc biệt nếu muốn nhận số lượng hoặc entity bị xóa. Các chữ ký này không được đặt vào repository JPA đồng bộ rồi coi là có hỗ trợ reactive.

`Mono<Void>` biểu diễn hoàn tất hoặc lỗi mà không phát một giá trị đếm. Không thể đọc nó như `Mono<Long>` có số lượng bị xóa.

Ngoài ra, với publisher dạng cold thường gặp, chỉ tạo publisher chưa có nghĩa thao tác đã được thực thi:

```java
Mono<Void> deletion = repository.deleteByTenantIdAndStatus(
        tenantId, OrderStatus.CANCELLED);
```

Tầng ứng dụng cần đưa publisher vào chuỗi xử lý được framework đăng ký và tiêu thụ. Không tự thêm một lệnh `subscribe()` tách rời chỉ để “chắc chắn xóa”, vì điều đó có thể tách lỗi, vòng đời và transaction khỏi luồng nghiệp vụ cần quản lý.

Một tên sai có thể bị phát hiện từ lúc repository khởi tạo, trong khi lỗi truy cập dữ liệu có thể đến sau subscription. Kiểu publisher không làm mất đi nhu cầu kiểm tra metadata và hành vi của truy vấn.

## 11. Chọn subject theo nhu cầu thật của caller

| Nhu cầu | Lựa chọn khởi đầu | Điều cần tránh |
| --- | --- | --- |
| Hiển thị số đơn theo trạng thái | `countBy...` | Tải toàn bộ entity chỉ để lấy kích thước |
| Biết mã bên ngoài đã xuất hiện chưa | `existsBy...` | Coi kiểm tra tồn tại là ràng buộc chống trùng |
| Xóa dữ liệu khớp điều kiện, không cần kết quả | Derived delete có chữ ký trả `void` được module hỗ trợ | Giả định mọi module tự có cùng transaction |
| Xóa và cần số lượng | Chữ ký đếm xóa được module hỗ trợ | Dùng phép đếm trước để thay cho kết quả xóa |
| Xóa JPA và cần callback theo entity | Xem xét derived delete hoặc cơ chế remove entity phù hợp | Thay bằng bulk delete mà không đánh giá thay đổi vòng đời |
| Xóa JPA tập lớn theo câu lệnh bulk | Truy vấn modifying được thiết kế riêng | Mặc định `deleteBy...` đã là bulk |
| Chuyển đơn sang trạng thái không hoạt động | Thao tác cập nhật nghiệp vụ thích hợp | Đổi `delete` thành `remove` để kỳ vọng soft delete |

Nếu caller cần một trang dữ liệu cùng tổng số, hợp đồng `Page<T>` có thể đã cung cấp thông tin tổng theo cơ chế của module. Không nên gọi thêm một `countBy...` khác điều kiện rồi hiển thị tổng đó như metadata của trang.

Nếu chỉ cần projection, đừng chọn phép đếm hoặc phép tồn tại rồi kỳ vọng nhận thêm các trường dữ liệu. Subject, kiểu kết quả và mapping projection là những quyết định cần khớp nhau.

## 12. Các lỗi dễ gặp và hướng kiểm tra

| Biểu hiện | Nguyên nhân có thể có | Hướng kiểm tra |
| --- | --- | --- |
| Không tạo được truy vấn đếm/xóa | Sai tên thuộc tính hoặc toán tử không được hỗ trợ | So với model Java và khả năng module |
| Đếm sai phạm vi | Thiếu tenant, trạng thái hoặc điều kiện thời gian | Đối chiếu predicate với yêu cầu nghiệp vụ |
| `exists` trả `true` nhưng lần đọc sau không thấy | Dữ liệu thay đổi giữa hai thao tác | Xem lại nhu cầu nhất quán thay vì coi đó là lỗi parser |
| Dữ liệu vẫn bị trùng dù đã kiểm tra `exists` | Có cạnh tranh giữa kiểm tra và ghi | Xem ràng buộc duy nhất hoặc thao tác ghi nguyên tử |
| Derived delete JPA tốn nhiều bộ nhớ | Tập entity khớp lớn, có bước tải và quản lý entity | Đánh giá khối lượng, transaction và chiến lược xóa phù hợp |
| Callback không chạy sau bulk delete | Bulk không đi qua vòng đời remove từng entity | So lại yêu cầu callback với cách thực thi |
| Chữ ký xóa trả `long` không hợp lệ | Đang dùng một loại query/module có hợp đồng trả về khác | Phân biệt derived delete, modifying query và module cụ thể |
| Xóa thành công nhưng entity trong bộ nhớ vẫn cũ | Bulk tác động trực tiếp trong khi context còn giữ state cũ | Xem ranh giới flush/clear/refresh và transaction |
| Publisher xóa được tạo nhưng dữ liệu chưa đổi | Chưa có subscription hoặc chuỗi chưa được thực thi | Kiểm tra vòng đời reactive và việc tiêu thụ tín hiệu |

Khi có lỗi, hãy xác định phương thức đang được thực hiện bởi repository cơ sở, truy vấn suy diễn, annotation khai báo hay fragment. Chỉ nhìn subject sẽ không đủ để biết nguồn truy vấn và thuật toán thực thi thực tế.

## 13. Bài tập thực hành

### Bài 1: Chọn chữ ký đúng nhu cầu

Viết chữ ký cho ba yêu cầu trên domain đã cho:

1. Đếm đơn `PAID` của một tenant.
2. Kiểm tra một mã bên ngoài đã tồn tại trong tenant đó chưa.
3. Xóa đơn `CANCELLED` trước một mốc thời gian, nhận số lượng theo hợp đồng derived delete JPA.

Gợi ý:

```java
long countByTenantIdAndStatus(String tenantId, OrderStatus status);

boolean existsByTenantIdAndExternalCode(String tenantId, String externalCode);

long deleteByTenantIdAndStatusAndCreatedAtBefore(
        String tenantId, OrderStatus status, Instant cutoff);
```

Hai phương thức đầu không hard-code trạng thái trong tên; caller truyền enum thích hợp. Phương thức thứ ba cần được sử dụng trong ranh giới transaction ghi phù hợp khi triển khai bằng JPA.

### Bài 2: Xác định kết quả và biên thời gian

Trong `tenant-a`, có hai đơn `CANCELLED` trước `cutoff` và một đơn đúng tại `cutoff`. Trong `tenant-b`, có thêm một đơn `CANCELLED` trước mốc đó.

Khi xóa theo `tenant-a`, trạng thái `CANCELLED` và `CreatedAtBefore`:

- Tập mục tiêu là hai đơn của `tenant-a` nằm trước mốc.
- Đơn đúng tại mốc được giữ lại vì điều kiện là `<`.
- Đơn của `tenant-b` nằm ngoài phạm vi.
- Với ví dụ derived delete JPA trả số lượng, kết quả kỳ vọng là `2` nếu thao tác và transaction hoàn tất như dự kiến.

Khi tích hợp kiểm tra, cần xác nhận trạng thái dữ liệu và ranh giới transaction, không chỉ assert số lượng trả về.

### Bài 3: Chọn derived delete hay bulk delete JPA

Một tác vụ cần xóa lượng lớn đơn cũ. Mapping có callback `@PreRemove` thực hiện một bước nghiệp vụ bắt buộc.

**Phân tích:** không thể thay derived delete bằng bulk JPQL chỉ dựa trên mục tiêu giảm số câu lệnh rồi mặc định callback vẫn chạy. Cần quyết định giữ xử lý theo entity, tổ chức lại theo lô, hoặc thiết kế lại bước nghiệp vụ để tương thích với cách xóa bulk. Đồng thời phải đánh giá cascade và persistence context.

### Bài 4: Tìm lỗi trong suy luận về exists

Hai request cùng chạy `existsByTenantIdAndExternalCode(...)`, cùng nhận `false`, rồi cùng ghi dữ liệu.

**Phân tích:** bản thân hai phép kiểm tra có thể đều đúng tại thời điểm thực hiện. Sai sót nằm ở việc coi kết quả kiểm tra là một bảo đảm độc quyền cho lần ghi sau. Cần ràng buộc duy nhất hoặc cơ chế nguyên tử tương ứng ở kho dữ liệu và xử lý trường hợp ghi cạnh tranh theo nghiệp vụ.

## 14. Các điểm cần nhớ

- `count` biểu đạt phép đếm, `exists` biểu đạt phép kiểm tra tồn tại, còn `delete` và `remove` cùng thuộc nhóm thao tác xóa trong cơ chế suy diễn tên.
- Phần sau `By` vẫn dựa trên thuộc tính domain và khả năng toán tử của module; subject không thay thế điều kiện lọc.
- `exists` không tạo tính duy nhất, phép đếm không bảo đảm số lượng của một lần xóa sau đó và số lượng xóa không phải bằng chứng commit độc lập.
- Derived delete JPA và bulk delete khác nhau về vòng đời entity, callback, bộ nhớ và persistence context.
- Kiểu trả về, transaction, reactive execution và khả năng trả entity bị xóa cần được xác nhận theo module; Commons không áp đặt cùng một thuật toán cho mọi kho dữ liệu.

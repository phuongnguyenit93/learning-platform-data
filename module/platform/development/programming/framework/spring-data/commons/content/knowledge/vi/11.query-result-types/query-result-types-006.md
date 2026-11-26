# Giá trị scalar, projection và kết quả không có entity

Repository không bắt buộc luôn trả về entity. Một màn hình có thể chỉ cần tổng tiền, một cờ tồn tại, danh sách mã tham chiếu hoặc các dòng báo cáo gồm vài trường. Chọn đúng kiểu kết quả giúp biểu đạt chính xác dữ liệu cần lấy và tránh mang theo hợp đồng của entity khi bài toán chỉ cần dữ liệu đọc.

Trong chương **Kiểu kết quả truy vấn** của module `SPRING_DATA_COMMONS`, bài này phân biệt scalar, projection và các kết quả khác không phải entity; giải thích cách kết hợp chúng với số lượng kết quả, nullability và cơ chế ánh xạ của từng store.

Commons cung cấp abstraction repository và metadata kết quả dùng chung. Việc chọn trường, tính toán tổng hợp, tạo projection hoặc chuyển kiểu cụ thể vẫn cần sự hỗ trợ của module như JPA, MongoDB hay một store khác. Các ví dụ có JPQL và `@Query` của JPA bên dưới được ghi rõ phạm vi, không phải cú pháp truy vấn chung cho mọi Spring Data repository.

## 1. Nhìn kiểu kết quả theo hai chiều

Một kiểu trả về chứa ít nhất hai thông tin khác nhau:

1. **Một phần tử là gì?** Entity, scalar hay một dạng projection.
2. **Có bao nhiêu phần tử và truy cập thế nào?** Một kết quả, tối đa một kết quả, collection, trang hoặc luồng.

| Khai báo minh họa | Dạng phần tử | Hình dạng kết quả |
| --- | --- | --- |
| `Purchase` | Entity | Một kết quả theo hợp đồng nullability |
| `Optional<Purchase>` | Entity | Tối đa một kết quả |
| `long` | Scalar số | Một giá trị |
| `Optional<BigDecimal>` | Scalar số tiền | Tối đa một giá trị có mặt |
| `List<String>` | Scalar chuỗi | Nhiều phần tử |
| `List<PurchaseSummary>` | Projection | Nhiều phần tử |
| `Page<PurchaseRow>` | DTO projection | Một trang có metadata tổng số |

`List` hoặc `Optional` không quyết định phần tử bên trong có phải entity hay không. Ngược lại, một DTO không quyết định query trả một hay nhiều dòng.

Vì vậy, khi đọc chữ ký repository, cần tách wrapper khỏi kiểu phần tử. `Optional<PurchaseSummary>` và `List<PurchaseSummary>` có thể cùng mô tả một dạng dữ liệu đọc, nhưng khác hợp đồng số lượng.

## 2. Mô hình dùng trong các ví dụ

Giả sử có `Purchase` với các property Java:

```text
Purchase
  id: Long
  reference: String
  customerId: Long
  status: PurchaseStatus
  total: BigDecimal
  currency: String
```

Và enum:

```java
enum PurchaseStatus {
    NEW,
    PAID,
    CANCELLED
}
```

Trong các ví dụ JPA, giả định `Purchase` là entity có entity name `Purchase`, `id` là định danh, `status` được ánh xạ phù hợp và những property còn lại có thể dùng trong JPQL. `total` có thể thiếu giá trị để minh họa hành vi aggregate với `null`.

Các đoạn mã là những phần khai báo cần cho chủ đề, chưa gồm toàn bộ cấu hình persistence, entity, package scanning hoặc transaction của một ứng dụng. Những interface repository ở các phần khác nhau có thể được ghép lại khi tên method và kiểu trả về không xung đột.

Vì số tiền đi kèm đơn vị tiền tệ, các ví dụ cộng tổng đều lọc theo `currency`. Một kiểu `BigDecimal` hợp lệ không tự làm phép cộng nhiều loại tiền trở nên đúng về nghiệp vụ.

## 3. Scalar: một giá trị đơn thay vì một đối tượng miền

Scalar là một giá trị như số, chuỗi, boolean hoặc một kiểu giá trị đơn được store và cơ chế chuyển đổi hỗ trợ. Ví dụ thường gặp:

- Số bản ghi phù hợp điều kiện.
- Cờ có tồn tại dữ liệu hay không.
- Mã tham chiếu của một giao dịch.
- Tổng tiền hoặc giá trị lớn nhất.
- Một mốc thời gian được query chọn ra.

### 3.1. count và exists có ý nghĩa riêng

Ví dụ derived query, giả định store hỗ trợ các subject tương ứng:

```java
import org.springframework.data.repository.Repository;

interface PurchaseRepository extends Repository<Purchase, Long> {

    long countByStatus(PurchaseStatus status);

    boolean existsByCustomerIdAndStatus(
        Long customerId,
        PurchaseStatus status
    );
}
```

`countByStatus` biểu đạt số lượng, còn `existsByCustomerIdAndStatus` biểu đạt sự tồn tại. Chúng không yêu cầu ứng dụng tải danh sách entity rồi tự tính `size()` hoặc kiểm tra `isEmpty()`.

Cách store thực hiện hai thao tác có thể khác nhau. Không suy một method `exists` luôn chạy đúng cùng query với `count` rồi so sánh kết quả lớn hơn không; đây là hợp đồng kết quả, còn thuật toán thuộc implementation.

### 3.2. Một property đơn cần được chọn ra đúng cách

Ví dụ riêng cho Spring Data JPA:

```java
import java.util.Optional;

import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

interface PurchaseReferenceRepository extends Repository<Purchase, Long> {

    @Query("select p.reference from Purchase p where p.id = :purchaseId")
    Optional<String> findReferenceByPurchaseId(
        @Param("purchaseId") Long purchaseId
    );
}
```

Query chọn `p.reference`, vì vậy một phần tử kết quả là `String`, không phải `Purchase`. Điều kiện theo định danh bảo đảm tối đa một entity phù hợp trong mô hình này.

Có hai việc cùng phải khớp:

```text
SELECT chọn ra gì?          -> p.reference
Repository mong nhận gì?   -> Optional<String>
```

Chỉ đổi return type mà vẫn chọn `p` không tự biến query entity thành query lấy một property.

### 3.3. Tên mô tả trước By không phải mệnh đề SELECT

Không có quy tắc chung trong Commons rằng:

```java
List<String> findReferenceByStatus(PurchaseStatus status);
```

sẽ tự chọn property `reference` chỉ vì có từ `Reference` trong tên. Phần mô tả của subject không phải một ngôn ngữ chọn cột tùy ý.

Nếu muốn lấy scalar thuộc tính, cần dùng cơ chế mà module hỗ trợ, chẳng hạn query khai báo rõ biểu thức chọn, cấu hình field projection hoặc một projection phù hợp. Không dựa vào việc tên method trông có vẻ mô tả đúng dữ liệu để kết luận store sẽ chọn đúng trường.

## 4. Giá trị aggregate: đúng số lượng và đúng kiểu số

Ví dụ JPA tính tổng:

```java
import java.math.BigDecimal;
import java.util.Optional;

@Query("""
    select sum(p.total)
    from Purchase p
    where p.status = :status and p.currency = :currency
    """)
Optional<BigDecimal> sumTotalByStatusAndCurrency(
    @Param("status") PurchaseStatus status,
    @Param("currency") String currency
);
```

Đoạn method này giả định nằm trong một repository JPA của `Purchase`, dùng các import `@Query` và `@Param` ở phần trước. Text block yêu cầu mức Java phù hợp.

### 4.1. Kiểu số được quyết định bởi biểu thức query

Trong JPQL, một số quy tắc điển hình là:

| Biểu thức | Kiểu kết quả điển hình theo JPQL |
| --- | --- |
| `count(p)` | `Long` |
| `sum(p.total)` với `total` là `BigDecimal` | `BigDecimal` |
| `avg` trên giá trị số | `Double` |
| `min` hoặc `max` trên một property hợp lệ | Kiểu của property được chọn |

Bảng này thuộc ngữ nghĩa JPQL. Query native SQL, aggregation của document store và các API khác có thể trả những kiểu số khác tùy cơ sở dữ liệu, driver và cơ chế mapping.

Không ép mọi kết quả số thành `Long`, cũng không mặc định `SUM` luôn có cùng kiểu với mọi kiểu property số đầu vào. Ví dụ tổng trên một property số nguyên không nhất thiết giữ nguyên kiểu số nguyên nhỏ đó.

Nếu cần chuyển kiểu, phải kiểm tra miền giá trị, độ chính xác và quy tắc làm tròn. Thay `BigDecimal` bằng `double` chỉ để ép kiểu dễ hơn có thể làm thay đổi hợp đồng số tiền.

### 4.2. COUNT bằng 0 khác SUM bằng null

Với một aggregate không có `GROUP BY`:

- `COUNT` trên tập không có dữ liệu phù hợp cho kết quả `0`.
- `SUM`, `AVG`, `MIN`, `MAX` có thể cho `null` khi không có giá trị đầu vào phù hợp.
- Các giá trị property `null` không tham gia phép tính aggregate theo ngữ nghĩa JPQL thông thường.

Vì vậy, `Optional<BigDecimal>` là một cách biểu đạt rằng tổng có thể không có giá trị trong ví dụ JPA trên. Một kiểu primitive không biểu diễn được `null`; không nên dùng primitive cho biểu thức có thể trả `null` mà chưa xử lý rõ trường hợp đó.

### 4.3. Không tự đánh đồng thiếu dữ liệu với số 0

Ứng dụng có thể chọn:

```java
BigDecimal total = repository
    .sumTotalByStatusAndCurrency(PurchaseStatus.PAID, "VND")
    .orElse(BigDecimal.ZERO);
```

Cách này phù hợp khi nghiệp vụ muốn biểu diễn tổng của tập rỗng bằng `0`. Nó cũng làm mất khả năng phân biệt một số tình huống không có giá trị aggregate.

Chẳng hạn, “không có giao dịch” và “có giao dịch nhưng mọi giá trị total đều null” có thể cùng dẫn tới aggregate `null`. Nếu cần phân biệt, hãy lấy thêm số bản ghi hoặc số giá trị không-null, thay vì chỉ nhìn kết quả `SUM`.

Có thể xử lý giá trị thay thế ngay trong query nếu store hỗ trợ. Khi đó vẫn cần bảo đảm kiểu của biểu thức thay thế tương thích với kiểu kết quả, đặc biệt với số tiền và query native.

## 5. Projection interface: một góc nhìn có tên cho dữ liệu đọc

Giả sử màn hình chỉ cần mã tham chiếu và số tiền:

```java
import java.math.BigDecimal;

interface PurchaseAmounts {
    String getReference();
    BigDecimal getTotal();
}
```

Ví dụ JPA với các alias rõ ràng:

```java
@Query("""
    select p.reference as reference, p.total as total
    from Purchase p
    where p.status = :status
    """)
List<PurchaseAmounts> findAmountsByStatus(
    @Param("status") PurchaseStatus status
);
```

Các alias tương ứng với tên property của projection:

```text
reference -> getReference()
total     -> getTotal()
```

Đây là cách trả một dòng gồm nhiều giá trị có tên, thay vì trả entity đầy đủ hoặc để caller nhớ chỉ số trong một mảng.

### 5.1. Closed projection

Một interface có các accessor tương ứng với property của domain type có thể là closed projection:

```java
interface PurchaseSummary {
    Long getId();
    String getReference();
    BigDecimal getTotal();
}
```

Khai báo derived query minh họa:

```java
List<PurchaseSummary> findByStatus(PurchaseStatus status);
```

Khi module hỗ trợ, metadata của closed projection có thể giúp tối ưu dữ liệu cần chọn. Tuy nhiên, không coi đó là bảo đảm rằng mọi query chỉ đọc đúng các cột nhìn thấy trên interface.

Query khai báo sẵn, nested projection, quan hệ và implementation của store đều ảnh hưởng đến việc có tải entity hoặc dữ liệu bổ sung hay không. Với nested projection trong một số đường query, một quan hệ có thể được join hoặc materialize rộng hơn điều người đọc interface hình dung.

### 5.2. Open projection

Một projection có accessor được tính bằng biểu thức, chẳng hạn SpEL trong cơ chế projection của Spring Data, không còn đơn giản chỉ là danh sách property cần chọn.

Ví dụ ý tưởng:

```java
@Value("#{target.reference + ' / ' + target.currency}")
String getLabel();
```

Đây là accessor trong một projection dùng `org.springframework.beans.factory.annotation.Value`, không phải một method repository độc lập. Biểu thức cần dữ liệu từ target nên không có cùng giả định tối ưu truy vấn như closed projection.

Không suy một interface chỉ có một accessor `getLabel()` nghĩa là store chỉ cần đọc đúng một trường. Việc tính toán tại projection cũng khác với chọn một biểu thức đã được database tính ngay trong query.

### 5.3. Projection không đồng nghĩa chắc chắn không có entity bên trong

Caller nhận một interface projection không có nghĩa implementation chưa từng tạo hoặc sử dụng entity. Một projection có thể được dựng từ tuple các giá trị, hoặc bọc một target khác, tùy query và store.

Cần phân biệt:

```text
Kiểu dữ liệu public trả cho caller
và
Dữ liệu được tải, ánh xạ hoặc quản lý bên trong
```

Nếu mục tiêu là giảm dữ liệu tải, phải xem query thực tế và cách module xử lý projection. Chỉ nhìn return type chưa đủ để kết luận về số cột, số query hay trạng thái managed của dữ liệu nội bộ.

## 6. DTO projection: biểu diễn kết quả bằng một kiểu dữ liệu riêng

DTO hữu ích khi muốn một hợp đồng dữ liệu cụ thể, có constructor và không phụ thuộc caller vào entity.

Ví dụ record dùng Java 17 trở lên:

```java
package com.example.reporting;

import java.math.BigDecimal;

public record PurchaseRow(
    Long id,
    String reference,
    BigDecimal total
) {
}
```

Với JPA, có thể dùng constructor expression tường minh:

```java
@Query("""
    select new com.example.reporting.PurchaseRow(
        p.id, p.reference, p.total
    )
    from Purchase p
    where p.status = :status
    """)
List<PurchaseRow> findRowsByStatus(
    @Param("status") PurchaseStatus status
);
```

Ví dụ giả định repository đã import `com.example.reporting.PurchaseRow`, `java.util.List` và các annotation query. JPQL cần tên lớp đầy đủ trong constructor expression; thứ tự và kiểu đối số phải phù hợp với constructor.

### 6.1. Constructor expression khác alias của interface projection

Trong ví dụ interface trước đó, query dùng:

```text
p.reference as reference
p.total as total
```

để biểu diễn tên các giá trị cho accessor. Trong constructor expression JPQL, dữ liệu được truyền theo các đối số constructor:

```text
new PurchaseRow(p.id, p.reference, p.total)
```

Không sao chép các alias `as reference` hoặc `as total` vào bên trong danh sách đối số của constructor expression như một quy tắc chung. Hai cơ chế có cách ánh xạ khác nhau.

Một số module và phiên bản có thể hỗ trợ DTO projection từ derived query hoặc viết lại query. Bài dùng constructor expression tường minh để chỉ rõ phần chọn dữ liệu; không giả định mọi store tự thực hiện cùng một phép viết lại.

### 6.2. DTO không tự có vòng đời entity

`PurchaseRow` không phải `Purchase` được đổi tên. Nó không tự trở thành entity managed chỉ vì có component `id`.

Các hệ quả thực tế:

- Với DTO mutable, đổi dữ liệu không đồng nghĩa thay đổi được tự ghi xuống store.
- Repository `save` cho entity `Purchase` không tự nhận một DTO bất kỳ làm đối tượng thay thế.
- Callback hoặc auditing của entity không tự chạy chỉ vì tạo một dòng báo cáo.
- Nếu DTO cần dữ liệu mà query không cung cấp hoặc constructor không nhận được, việc ánh xạ có thể thất bại.

Một DTO vẫn có thể chứa entity nếu chính query chọn và truyền entity vào constructor. Vì vậy, muốn một kết quả hoàn toàn bằng giá trị đọc, cần xem cả cấu trúc DTO lẫn các biểu thức query chọn, không chỉ xem annotation của lớp DTO.

## 7. Dynamic projection: chọn dạng kết quả ở từng lời gọi

Trong phạm vi module hỗ trợ, repository có thể khai báo:

```java
<T> List<T> findByStatus(PurchaseStatus status, Class<T> type);
```

Caller chọn dạng dữ liệu:

```java
List<PurchaseSummary> summaries = repository.findByStatus(
    PurchaseStatus.PAID,
    PurchaseSummary.class
);

List<Purchase> entities = repository.findByStatus(
    PurchaseStatus.PAID,
    Purchase.class
);
```

Đây là cùng một dạng điều kiện nhưng hai kiểu phần tử được yêu cầu. Truyền `Purchase.class` có thể yêu cầu kết quả entity; truyền một projection hợp lệ yêu cầu dạng projection tương ứng.

`Class<T>` được nhận diện là tham số dynamic projection khi đáp ứng các quy tắc metadata của Spring Data. Nó không mặc định là một giá trị cần bind vào điều kiện truy vấn. Ngược lại, không phải mọi tham số `Class` xuất hiện trong mọi method đều mang vai trò projection.

Dynamic projection không có nghĩa caller có thể truyền tùy ý một lớp không liên quan rồi framework tự tìm cách tạo nó. Constructor, accessor, property và query vẫn phải phù hợp với cơ chế của store.

Đặc biệt, việc truyền `String.class` không phải một ngôn ngữ chọn property: framework không thể biết caller muốn `reference`, `currency` hay chuỗi nào khác chỉ từ lớp `String`.

## 8. Báo cáo theo nhóm: mỗi dòng kết quả không phải một entity

Một báo cáo tổng hợp theo trạng thái có thể trả những dòng không tương ứng một-một với `Purchase`.

Projection:

```java
interface PurchaseStatusReport {
    PurchaseStatus getStatus();
    Long getPurchaseCount();
    BigDecimal getGrossTotal();
}
```

Query JPA:

```java
@Query("""
    select p.status as status,
           count(p) as purchaseCount,
           sum(p.total) as grossTotal
    from Purchase p
    where p.currency = :currency
    group by p.status
    """)
List<PurchaseStatusReport> summarizeByStatus(
    @Param("currency") String currency
);
```

Mỗi dòng đại diện cho **một nhóm trạng thái** trong đơn vị tiền tệ được chọn. Không cần gán một định danh entity giả cho dòng báo cáo chỉ để trả nó qua repository.

### 8.1. COUNT trên nhóm khác tổng số nhóm

`count(p)` trong một dòng báo cáo đếm số `Purchase` của nhóm đó. Nó không đếm số dòng báo cáo.

Nếu kết quả có hai nhóm `NEW` và `PAID`, tổng số dòng báo cáo là hai, dù các nhóm chứa hàng nghìn giao dịch.

Khi phân trang báo cáo nhóm, metadata tổng số phần tử cần nói về số nhóm phù hợp. Một count query đếm toàn bộ giao dịch có thể tạo metadata sai cho trang báo cáo. Không giả định framework luôn tự sinh count query đúng cho mọi query nhóm phức tạp.

### 8.2. GROUP BY có thể làm thay đổi số dòng

Một aggregate toàn bộ không có `GROUP BY` như `count(p)` cho một giá trị, kể cả khi giá trị đó là `0`.

Với `GROUP BY`, mỗi nhóm có dữ liệu tạo một dòng. Nếu không có dữ liệu phù hợp thì có thể không có nhóm nào, do đó collection báo cáo rỗng. Không có quy tắc tự tạo một dòng `count = 0` cho mọi enum trạng thái.

Nếu màn hình cần hiển thị đủ tất cả trạng thái dù không có giao dịch, phải thiết kế query hoặc bước bổ sung dữ liệu phù hợp. Kiểu projection không tự tạo các nhóm còn thiếu.

### 8.3. COUNT entity và COUNT property không giống nhau

Trong JPQL, `count(p)` đếm các entity phù hợp; `count(p.total)` chỉ đếm các giá trị `total` không-null.

Một nhóm có ba giao dịch nhưng chỉ hai giao dịch có `total` sẽ có hai con số này khác nhau. Alias và tên accessor nên mô tả đúng loại số lượng đang trả, chẳng hạn `purchaseCount` khác `totalValueCount`.

## 9. Số lượng kết quả và nullability là hợp đồng riêng

| Kiểu khai báo | Khi không có kết quả | Khi có nhiều kết quả |
| --- | --- | --- |
| `T` cho kết quả đơn | Phụ thuộc hợp đồng nullability và cơ chế repository | Thường báo lỗi nếu vượt số lượng cho phép |
| `Optional<T>` | `Optional.empty()` | Thường báo lỗi nếu vượt số lượng cho phép |
| `List<T>` | Collection rỗng theo hợp đồng collection của repository | Chứa các phần tử kết quả |
| Primitive như `long` | Cần query tạo được giá trị hợp lệ, chẳng hạn count bằng `0` | Không dùng để biểu diễn nhiều dòng |

Bảng không thay thế ngữ nghĩa query. Một query chọn `SUM` có thể có một dòng nhưng giá trị trong dòng là `null`; một query chọn property có thể không có dòng nào; một query nhóm có thể có nhiều dòng.

### 9.1. Optional không che lỗi quá nhiều dòng

Nếu một query scalar hoặc projection có thể trả nhiều dòng, đổi return type thành `Optional` không làm nó tự chọn dòng đầu tiên.

Nếu cần nhiều kết quả, dùng collection hoặc wrapper nhiều phần tử được hỗ trợ. Nếu thật sự cần một kết quả đầu tiên, phải thể hiện giới hạn và thứ tự theo cơ chế thích hợp, hoặc bảo đảm điều kiện là duy nhất trong dữ liệu.

Không dựa vào việc nhiều bản ghi tình cờ có cùng giá trị scalar để coi query là duy nhất. Cần thiết kế rõ query và ràng buộc dữ liệu phù hợp với hợp đồng một kết quả.

### 9.2. Không có dòng và giá trị null có thể bị gộp lại

Với query lấy `reference` theo định danh:

```text
Không có Purchase phù hợp             -> không có reference
Có Purchase nhưng reference là null   -> cũng không có giá trị reference
```

Một kết quả `Optional<String>` có thể không giữ đủ thông tin để phân biệt hai trường hợp này.

Nếu cần phân biệt, hãy chọn thêm định danh không-null cùng giá trị nullable trong một projection hoặc DTO. Khi đó caller có thể giữ thông tin rằng dòng thực sự tồn tại, dù một property của dòng chưa có giá trị.

### 9.3. Collection không-null không làm mọi property thành không-null

Một repository trả `List<PurchaseAmounts>` rỗng khi không có dữ liệu không có nghĩa `getTotal()` của từng phần tử luôn khác `null`.

Tương tự, collection không-null và từng giá trị được chọn không-null là hai hợp đồng khác nhau. Dùng kiểu boxed hoặc wrapper nullable phù hợp cho dữ liệu có thể thiếu, đồng thời xác định nullability của accessor và DTO constructor.

Các quy ước annotation về nullability phụ thuộc phiên bản và cấu hình package. Không kết luận mọi method trả `T` đều được phép trả `null` chỉ vì không dùng `Optional`.

## 10. Object[], tuple và Map: kết quả thô cần hợp đồng rõ

Một số query và adapter store có thể trả nhiều giá trị dưới dạng mảng, tuple hoặc map. Đây không phải một kiểu kết quả đa cột mặc định áp dụng giống nhau cho mọi module Commons.

Những điểm cần xác định gồm:

| Dạng kết quả | Điều caller phải biết |
| --- | --- |
| `Object[]` | Thứ tự từng biểu thức và kiểu thực tế của mỗi vị trí |
| Tuple | API tuple, alias và khả năng hỗ trợ của provider |
| Map | Quy tắc tên khóa, alias và kiểu giá trị do adapter trả |

Ví dụ, đổi thứ tự biểu thức chọn trong query có thể làm đoạn code đọc `row[0]` sai nghĩa dù code vẫn biên dịch. Query native còn có thể trả kiểu số khác với dự kiến của một phép cast trực tiếp.

Khi kết quả được dùng ổn định bởi nhiều nơi, interface projection hoặc DTO có tên thường giúp thể hiện hợp đồng rõ hơn. Nếu dùng kết quả thô cho báo cáo linh hoạt, vẫn cần ghi rõ alias, kiểu số, nullability và thứ tự; không chuyển trách nhiệm mapping sang caller mà bỏ mất hợp đồng đó.

## 11. Số dòng bị tác động và void không phải query SELECT thông thường

Kết quả không có entity còn có thể đến từ thao tác thay đổi dữ liệu.

Ví dụ riêng cho JPA:

```java
@Modifying
@Query("""
    update Purchase p
    set p.status = :nextStatus
    where p.status = :previousStatus
    """)
int changeStatus(
    @Param("previousStatus") PurchaseStatus previousStatus,
    @Param("nextStatus") PurchaseStatus nextStatus
);
```

Đoạn này dùng `org.springframework.data.jpa.repository.Modifying` và các annotation query của JPA. Operation cần chạy trong transaction phù hợp, thường được tổ chức ở service hoặc cấu hình transaction tương ứng.

Giá trị `int` biểu diễn số lượng bị tác động theo hợp đồng update của API, không phải một scalar được chọn từ `SELECT`, cũng không phải danh sách entity đã đổi trạng thái.

JPA bulk update có ngữ nghĩa khác với tải từng entity rồi gọi setter. Trạng thái entity đã có trong persistence context và các callback/auditing theo vòng đời từng entity cần được xem xét riêng; một con số trả về không chứng minh những cơ chế đó đã được chạy theo cách của thao tác từng entity.

Một method `void` có thể phù hợp khi thao tác cho phép bỏ qua kết quả. Nó không tự biến một query đọc nhiều cột thành một operation hợp lệ chỉ bằng cách che return type. Cần chọn đúng loại operation, annotation và contract mà module hỗ trợ.

## 12. Kết hợp với collection, phân trang và luồng

Sau khi chọn kiểu phần tử, chọn wrapper theo nhu cầu truy cập dữ liệu:

| Nhu cầu | Dạng kết quả cần cân nhắc |
| --- | --- |
| Một giá trị tổng hợp | Scalar hoặc wrapper tùy khả năng null |
| Tối đa một dòng dữ liệu đọc | `Optional<Projection>` hoặc `Optional<DTO>` |
| Danh sách dữ liệu đọc | `List<Projection>` hoặc `List<DTO>` |
| Trang có tổng số phần tử | `Page<Projection>` hoặc `Page<DTO>` |
| Chỉ cần biết còn phần tiếp theo | `Slice` trong phạm vi store hỗ trợ |
| Xử lý theo luồng | Kiểu stream/reactive mà store hỗ trợ |

Một query projection trả `Page` vẫn cần metadata phân trang đúng. Query đếm bổ sung có thể cần thiết, nhưng không phải mọi lời gọi đều buộc chạy đúng hai query; hạ tầng có thể suy ra tổng trong những trường hợp hợp lệ.

Một projection nhỏ không làm cho `List` tự phân trang. Ngược lại, đổi sang stream không tự biến một query thành không dùng tài nguyên: một stream gắn với tài nguyên store có thể cần transaction và phải được đóng đúng vòng đời.

Với repository reactive, cần dùng wrapper và kiểu kết quả được module reactive hỗ trợ. Không bọc một API đồng bộ tùy ý rồi coi đó là khả năng reactive của store, cũng không suy tất cả các tổ hợp như `Page`, projection và publisher đều được hỗ trợ như nhau.

## 13. Bộ dữ liệu thực hành để phân biệt các trường hợp

Giả sử có dữ liệu:

| `id` | `reference` | `customerId` | `status` | `total` | `currency` |
| --- | --- | --- | --- | --- | --- |
| 1 | `P-001` | 7 | `PAID` | 100.00 | `VND` |
| 2 | `P-002` | 8 | `PAID` | 250.00 | `VND` |
| 3 | `P-003` | 7 | `NEW` | `null` | `VND` |
| 4 | `P-004` | 7 | `PAID` | 9.00 | `USD` |

Các giá trị số tiền được hiểu theo kiểu thập phân của mô hình. Khi tạo dữ liệu bằng Java, có thể dùng chuỗi thập phân như `new BigDecimal("100.00")` để thể hiện giá trị mong muốn.

### 13.1. Scalar và tính tồn tại

| Lời gọi | Kết quả cần kiểm chứng |
| --- | --- |
| `countByStatus(PAID)` | `3` |
| `existsByCustomerIdAndStatus(7L, CANCELLED)` | `false` |
| `findReferenceByPurchaseId(1L)` | Có giá trị `P-001` |
| `findReferenceByPurchaseId(999L)` | Rỗng |

Trong bảng, `PAID` và `CANCELLED` là cách viết ngắn của các hằng `PurchaseStatus` tương ứng.

### 13.2. Tổng tiền và giá trị thiếu

| Điều kiện tính tổng | Kết quả query SUM |
| --- | --- |
| `PAID`, `VND` | 350.00 |
| `PAID`, `USD` | 9.00 |
| `NEW`, `VND` | `null` vì không có giá trị total không-null |
| `CANCELLED`, `VND` | `null` vì không có dữ liệu phù hợp |

Với return type `Optional<BigDecimal>`, hai dòng cuối có thể cùng được biểu diễn bằng `Optional.empty()`. Nếu nghiệp vụ cần phân biệt chúng, kết quả SUM đơn lẻ chưa đủ.

Không cộng 350.00 VND với 9.00 USD chỉ vì cả hai đều là `BigDecimal`. Query phải giữ đúng phạm vi đơn vị tiền tệ, hoặc sử dụng một quy tắc quy đổi được thiết kế riêng.

### 13.3. Projection báo cáo

`summarizeByStatus("VND")` có hai nhóm:

| `status` | `purchaseCount` | `grossTotal` |
| --- | --- | --- |
| `NEW` | 1 | `null` |
| `PAID` | 2 | 350.00 |

Không có nhóm `CANCELLED` tự động với số lượng bằng không. Trong nhóm `NEW`, `count(p)` là 1 nhưng `count(p.total)` sẽ là 0.

Các bảng trên mô tả tập kết quả mong đợi, không bảo đảm thứ tự khi query không có `ORDER BY`. Đây là kịch bản thiết kế thực hành, không phải kết quả của một bộ test đã được chạy trong bài.

## 14. Chẩn đoán lỗi theo hợp đồng kết quả

Khi một method trả scalar hoặc projection thất bại, cần kiểm tra cả query và return type thay vì chỉ thay một kiểu Java cho đến khi hết lỗi.

| Dấu hiệu | Điều cần đối chiếu |
| --- | --- |
| Query chọn entity nhưng method mong `String` | Biểu thức SELECT có thật sự chọn property scalar không |
| Accessor projection không có giá trị mong đợi | Tên alias, property và cách module tạo projection |
| Không tạo được DTO | Tên lớp, constructor, thứ tự và kiểu đối số |
| Không chuyển được kiểu số | Kiểu aggregate/native result thực tế và kiểu khai báo |
| Primitive không nhận được kết quả | Biểu thức có thể trả null hay không |
| Lỗi nhiều kết quả cho method đơn | Điều kiện, GROUP BY, tính duy nhất và giới hạn |
| Page báo tổng không đúng | Count query đang đếm entity, giá trị distinct hay nhóm |
| Projection nhỏ nhưng truy cập store vẫn nhiều | Query thực tế, nested projection và cách tải dữ liệu |

Một trình tự đọc hữu ích:

1. Xác định chính xác những biểu thức được query chọn.
2. Xác định có bao nhiêu dòng và mỗi dòng có bao nhiêu giá trị.
3. Xác định kiểu runtime và khả năng null của từng giá trị.
4. Đối chiếu với scalar, accessor hoặc constructor được khai báo.
5. Đối chiếu wrapper một/nhiều kết quả cùng quy tắc của module store.

Nếu dùng query native, cần kiểm tra alias và kiểu do driver/provider trả về. Không dùng quy tắc kiểu của JPQL làm bằng chứng rằng một giá trị native chắc chắn có cùng lớp Java.

## 15. Chọn hợp đồng theo mục đích sử dụng

| Mục đích | Lựa chọn thường phù hợp |
| --- | --- |
| Chỉ cần số lượng | Query count trả scalar số |
| Chỉ cần biết có dữ liệu hay không | Query exists trả boolean |
| Chỉ cần một property | Query chọn scalar rõ ràng |
| Màn hình danh sách với vài trường | Closed projection hoặc DTO theo khả năng store |
| Kết quả đọc cần cấu trúc ổn định | DTO có constructor phù hợp |
| Báo cáo nhiều aggregate và khóa nhóm | Projection/DTO có tên từng giá trị |
| Cần làm việc với trạng thái và vòng đời entity | Trả entity trong phạm vi nghiệp vụ và store phù hợp |

Không chọn một projection chỉ vì nó trông nhẹ hơn trên chữ ký, rồi mặc định đã đạt mục tiêu hiệu năng. Cũng không tải entity chỉ để lấy một số lượng nếu store có query aggregate phù hợp.

Với truy vấn phức tạp, có thể cần query khai báo hoặc custom repository fragment. Các abstraction như Query by Example giúp biểu diễn một số loại điều kiện trong phạm vi hỗ trợ, nhưng không tự cung cấp ngôn ngữ SELECT hay GROUP BY tổng quát cho mọi store.

## 16. Tự kiểm tra mức độ hiểu

1. `List<String>` khác `Optional<String>` ở số lượng như thế nào, và query phải chọn dữ liệu gì để có scalar chuỗi?
2. Vì sao `findReferenceByStatus` không tự bảo đảm chọn property `reference` trong mọi module Commons?
3. Trong JPQL, COUNT trên tập rỗng khác SUM trên tập không có giá trị đầu vào ra sao?
4. Khi nào `Optional<BigDecimal>` làm mất khả năng phân biệt hai tình huống nghiệp vụ?
5. Alias của interface projection khác đối số constructor DTO ở điểm nào?
6. Vì sao một interface projection không chứng minh rằng entity chưa từng được tải?
7. Số giao dịch trong nhóm khác số dòng báo cáo như thế nào khi phân trang?
8. Điều gì cần kiểm tra lại khi chuyển một query từ JPQL sang native SQL hoặc sang store khác?

Một hợp đồng kết quả rõ ràng phải nối được **biểu thức dữ liệu được chọn**, **kiểu của một phần tử**, **số lượng kết quả** và **cách xử lý giá trị thiếu**. Khi bốn phần này khớp nhau, repository có thể phục vụ scalar, projection và báo cáo mà không cần trả entity cho mọi nhu cầu đọc.

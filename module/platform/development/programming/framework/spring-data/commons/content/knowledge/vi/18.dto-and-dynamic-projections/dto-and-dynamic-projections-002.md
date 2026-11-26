# Java record cho mô hình đọc bất biến

Trong chương **DTO và projection động** của Spring Data Commons (`SPRING_DATA_COMMONS`), Java record là một cách khai báo kiểu dữ liệu đọc có cấu trúc rõ ràng. Một record có thể biểu diễn vài trường cần cho màn hình, một dòng báo cáo hoặc kết quả query, thay vì đưa toàn bộ aggregate cho caller.

Điểm quan trọng là **record giữ cố định các component của chính nó, nhưng không tự làm mọi đối tượng được tham chiếu trở thành bất biến**. Để có một mô hình đọc ổn định, cần chọn kiểu component, constructor và cách truy vấn phù hợp.

Ví dụ trong bài dùng Java 17. Các query JPA được ghi rõ là ví dụ của Spring Data JPA; Commons cung cấp abstraction projection, còn việc chọn trường và tạo kết quả phụ thuộc module store.

## 1. Mô hình đọc nên biểu diễn nhu cầu sử dụng

Giả sử một hệ thống có aggregate `PurchaseOrder` với:

| Thuộc tính | Kiểu Java | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh đơn. |
| `tenantId` | `String` | Phạm vi tenant. |
| `orderNumber` | `String` | Số đơn hiển thị. |
| `total` | `BigDecimal` | Tổng tiền. |
| `createdAt` | `Instant` | Thời điểm tạo. |
| Các quan hệ và dữ liệu khác | Tùy domain | Phục vụ xử lý nghiệp vụ. |

Màn hình danh sách chỉ cần ID, số đơn, tổng tiền và thời điểm tạo. Một mô hình đọc có thể khai báo:

```java
package example.order.read;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderSummary(
    Long id,
    String orderNumber,
    BigDecimal total,
    Instant createdAt
) {}
```

Record không cần giữ tenant, collection dòng hàng hoặc entity khách hàng nếu caller không cần đọc chúng. Điều kiện tenant vẫn thuộc query; việc bỏ component tenant khỏi DTO không thay thế điều kiện chọn dữ liệu.

Có thể hình dung đường đọc:

```text
Store
  -> query chọn dữ liệu cho use case
  -> constructor OrderSummary
  -> caller đọc giá trị đã nhận
```

Đường ghi có thể dùng aggregate và các quy tắc nghiệp vụ riêng. Cùng một ID không có nghĩa hai kiểu dữ liệu phải có cùng cấu trúc hay trách nhiệm.

## 2. Record cung cấp sẵn những gì?

Với khai báo trên, Java cung cấp các thành phần tiêu biểu:

| Thành phần | Ví dụ |
| --- | --- |
| Field `private final` cho mỗi component | Field lưu `orderNumber`. |
| Canonical constructor | `new OrderSummary(id, number, total, createdAt)`. |
| Accessor theo tên component | `summary.orderNumber()`. |
| So sánh và mã băm theo component | `equals(...)`, `hashCode()`. |
| Biểu diễn chuỗi chứa tên và giá trị component | `toString()`. |

Record class là final. Accessor được sinh có tên `id()`, `total()`, không phải `getId()` hay `getTotal()` theo kiểu JavaBean.

Những quy tắc ngôn ngữ này được trình bày trong [Java 17: Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html).

Ví dụ sử dụng:

```java
OrderSummary summary = new OrderSummary(
    42L,
    "PO-0042",
    new BigDecimal("125000.00"),
    Instant.parse("2026-01-10T09:00:00Z")
);

System.out.println(summary.orderNumber());
System.out.println(summary.total());
```

Không có setter do compiler sinh ra. Nếu cần một kết quả khác, ứng dụng tạo instance mới theo hợp đồng của mô hình đọc; record không tự cung cấp method `withTotal(...)` hoặc cơ chế cập nhật store.

Một method thuần tính toán có thể đặt trong record nếu nó chỉ dựa vào các component. Tuy nhiên, không nên biến DTO đọc thành nơi điều phối repository hoặc các tác động nghiệp vụ.

## 3. Bất biến nông khác với bất biến của toàn bộ object graph

[API java.lang.Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html) mô tả record là một kiểu chứa dữ liệu bất biến nông. Field final ngăn thay tham chiếu sau khi instance được tạo; nó không ngăn đối tượng mà field trỏ tới thay đổi.

Ví dụ chưa đạt mục tiêu:

```java
import java.util.ArrayList;
import java.util.List;

record OrderTags(Long id, List<String> tags) {}

List<String> input = new ArrayList<>();
input.add("priority");

OrderTags tags = new OrderTags(42L, input);

input.add("manual-review");

System.out.println(tags.tags().size()); // 2
```

Không có setter nào được gọi trên `OrderTags`, nhưng trạng thái quan sát được vẫn đổi vì record và caller cùng giữ một list có thể sửa.

Caller còn có thể sửa trực tiếp qua accessor:

```java
tags.tags().clear();
```

Với mô hình đọc bất biến, cần xét cả các thành phần lồng bên trong:

| Kiểu component | Điều cần xác định |
| --- | --- |
| `String`, `Long`, `Instant`, `BigDecimal` | Là các kiểu giá trị phù hợp cho ví dụ bất biến này. |
| `List<T>`, `Map<K, V>` | Có cần snapshot collection và hạn chế sửa không? Phần tử có mutable không? |
| `byte[]` hoặc một mảng khác | Caller có thể sửa nội dung; final chỉ giữ nguyên tham chiếu mảng. |
| Entity hoặc đối tượng domain có trạng thái thay đổi | Record có thể vẫn phụ thuộc object graph đang sống và quan hệ lazy. |

Vì vậy, record chứa toàn bộ entity không có cùng tính chất với record chứa các scalar đã được đọc đầy đủ.

## 4. Bảo vệ collection bằng compact constructor

Có thể sửa hợp đồng của `OrderTags` để constructor giữ một snapshot không cho sửa collection:

```java
import java.util.List;
import java.util.Objects;

public record OrderTags(
    Long id,
    List<String> tags
) {

    public OrderTags {
        Objects.requireNonNull(id, "id");
        tags = List.copyOf(
            Objects.requireNonNull(tags, "tags")
        );
    }
}
```

Đây là phiên bản thay thế cho record đơn giản ở phần trước. Trong compact constructor, Java tự gán các tham số component vào field sau khi phần thân hoàn tất. Dòng `tags = ...` thay giá trị tham số sẽ được gán; không cần viết `this.tags = ...`.

Theo hợp đồng [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)), list kết quả không cho thêm, xóa hoặc thay phần tử và không phản ánh các thay đổi sau đó của collection đầu vào. Method này không nhận phần tử null.

Với bản thay thế:

```java
List<String> input = new ArrayList<>();
input.add("priority");

OrderTags snapshot = new OrderTags(42L, input);

input.clear();

System.out.println(snapshot.tags().size()); // 1

// Ném UnsupportedOperationException:
// snapshot.tags().add("new-tag");
```

Không cần giả định `copyOf` luôn cấp phát một list mới; điều cần dựa vào là hợp đồng snapshot và không cho sửa.

Đây vẫn là sao chép nông các phần tử. Nếu `T` là một đối tượng mutable, việc sửa một phần tử có thể tiếp tục làm dữ liệu quan sát được thay đổi.

Một mô hình đọc có collection nên chọn cả phần tử theo hướng giá trị:

```java
import java.math.BigDecimal;

public record LineRow(
    String productCode,
    int quantity,
    BigDecimal unitPrice
) {}
```

```java
import java.util.List;
import java.util.Objects;

public record OrderLines(
    Long orderId,
    List<LineRow> lines
) {

    public OrderLines {
        Objects.requireNonNull(orderId, "orderId");
        lines = List.copyOf(
            Objects.requireNonNull(lines, "lines")
        );
    }
}
```

Trong thiết kế này, `LineRow` chỉ chứa giá trị không đổi, còn collection được bảo vệ tại constructor. Nếu sau đó thêm một component mutable vào `LineRow`, cần đánh giá lại giả định bất biến của toàn bộ mô hình.

## 5. Constructor diễn đạt hợp đồng null và dữ liệu hợp lệ

Record đơn giản không tự cấm null. Có thể viết:

```java
new OrderSummary(null, null, null, null);
```

Nếu đó không phải một kết quả hợp lệ cho use case, constructor cần diễn đạt rõ. Phiên bản sau thay cho `OrderSummary` ban đầu, với giả định bốn giá trị là bắt buộc:

```java
package example.order.read;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

public record OrderSummary(
    Long id,
    String orderNumber,
    BigDecimal total,
    Instant createdAt
) {

    public OrderSummary {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(orderNumber, "orderNumber");
        Objects.requireNonNull(total, "total");
        Objects.requireNonNull(createdAt, "createdAt");

        if (orderNumber.isBlank()) {
            throw new IllegalArgumentException(
                "orderNumber must not be blank"
            );
        }
    }
}
```

Compact constructor vẫn là canonical constructor theo cùng danh sách component; không phải một constructor rỗng cần được framework gọi trước rồi mới điền field.

Quy tắc này cần khớp query:

- Nếu query dùng left join và giá trị có thể thiếu, component hoặc mô hình kết quả phải cho phép tình huống đó.
- Nếu một scalar nullable được map vào primitive như `long`, primitive không biểu diễn được null.
- Không tự đổi null thành số không nếu nghiệp vụ phân biệt “không có dữ liệu” với “giá trị bằng không”.
- Nếu constructor từ chối dữ liệu, việc tạo DTO từ kết quả query có thể thất bại.

Constructor của DTO bảo vệ hợp đồng kết quả đọc. Nó không thay thế validation đầy đủ của một lệnh tạo hoặc sửa aggregate.

Cũng cần thận trọng với chuẩn hóa dữ liệu trong constructor. Việc tự cắt chuỗi hoặc đổi scale có thể làm mô hình không còn phản ánh chính xác giá trị query; chỉ làm khi đó là quy tắc đã chọn cho use case.

## 6. Record phù hợp với class-based projection của Spring Data

Class-based projection nhận dữ liệu bằng constructor, thay vì tạo proxy triển khai interface đọc. Record thường thuận tiện vì khai báo component cung cấp một canonical constructor và ngữ nghĩa giá trị rõ ràng.

Ví dụ repository, trong module có hỗ trợ class-based projection tương ứng:

```java
import java.util.List;

import org.springframework.data.repository.Repository;

public interface OrderReadRepository
        extends Repository<PurchaseOrder, Long> {

    List<OrderSummary> findByTenantIdOrderByCreatedAtDescIdDesc(
        String tenantId
    );
}
```

Ví dụ giả định `OrderSummary` được import từ `example.order.read`; các component `id`, `orderNumber`, `total`, `createdAt` khớp thuộc tính root của `PurchaseOrder`.

Tên và kiểu đầu vào constructor có vai trò trong việc xác định dữ liệu projection. Đổi tên component thành `displayNumber` trong khi entity chỉ có `orderNumber` không tự tạo một phép đổi tên cho derived query.

Cơ chế class-based projection và cách chọn trường theo constructor được mô tả trong [Spring Data Commons: Class-based Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html#projections.dtos).

Với ví dụ đơn giản, không cần thêm constructor không tham số hoặc setter để “giúp framework điền DTO”. Giữ đường tạo dữ liệu rõ ràng bằng constructor phù hợp.

Nếu sử dụng nhiều constructor, factory hoặc cơ chế mapping tùy biến, phải kiểm tra quy tắc chọn constructor ở module và đường query cụ thể. Không thêm `@PersistenceCreator` theo thói quen mà chưa xác định nó cần giải quyết điều gì.

## 7. Ví dụ JPA với selection và constructor tường minh

Trong JPA, có thể viết JPQL constructor expression để chỉ rõ dữ liệu tạo record:

```java
import java.util.List;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface JpaOrderReadRepository
        extends Repository<PurchaseOrder, Long> {

    @Query("""
        select new example.order.read.OrderSummary(
            o.id,
            o.orderNumber,
            o.total,
            o.createdAt
        )
        from PurchaseOrder o
        where o.tenantId = :tenantId
        order by o.createdAt desc, o.id desc
        """)
    List<OrderSummary> findRows(
        @Param("tenantId") String tenantId,
        Pageable pageable
    );
}
```

Entity name của ví dụ là `PurchaseOrder`. Constructor expression dùng tên đầy đủ của record và thứ tự tham số đúng với canonical constructor. Kiểu của các biểu thức select cần tương thích với kiểu tham số.

Một lời gọi lấy phần kết quả có giới hạn:

```java
import org.springframework.data.domain.PageRequest;

List<OrderSummary> rows = repository.findRows(
    "ACME",
    PageRequest.of(0, 20)
);
```

Danh sách trả về không mang metadata tổng số như `Page`. Ví dụ dùng thứ tự trong JPQL và một `PageRequest` không bổ sung sort.

Không thêm alias `as ...` vào từng đối số bên trong constructor expression để kỳ vọng nó đổi tên component. Các cân nhắc cho constructor expression và DTO projection được trình bày tại [Spring Data JPA: Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html#projections.jpa).

Record là đối tượng kết quả Java. Nó không tự sửa kiểu trả về của một biểu thức aggregate, không làm mọi native query có thể map tùy ý và không tự biến tên cột thành tên component trong mọi cơ chế mapping.

Nếu thay JPQL bằng native SQL hoặc query của store khác, cần xác định lại thứ tự, kiểu, tên trường và cách module tạo DTO.

## 8. Projection trực tiếp khác với map entity thành record

Hai đường sau có thể cho cùng dữ liệu cuối nhưng khác lượng dữ liệu phải tải:

```text
Đường A:
query trả đúng các giá trị cần
  -> tạo OrderSummary

Đường B:
query trả entity
  -> có thể tải thêm trạng thái hoặc quan hệ
  -> ứng dụng đọc getter
  -> new OrderSummary(...)
```

Chuyển một entity đã tải đầy đủ thành record ở cuối không làm query trước đó nhỏ lại.

Khi cần lắp mô hình đọc từ entity, hãy lấy các giá trị cần thiết trong phạm vi tài nguyên phù hợp. Ví dụ một hàm chuyển đổi:

```java
private OrderSummary toSummary(PurchaseOrder order) {
    return new OrderSummary(
        order.getId(),
        order.getOrderNumber(),
        order.getTotal(),
        order.getCreatedAt()
    );
}
```

Nếu thay các scalar bằng `Customer` entity hoặc một collection lazy, kết quả record vẫn có thể phụ thuộc persistence context. Muốn một kết quả đọc tự chứa, nên chuyển dữ liệu liên quan thành các giá trị hoặc record con đã tạo đầy đủ.

Trong JPA, có thể đặt đơn vị công việc đọc tại service có giao dịch phù hợp rồi trả kết quả giá trị. Cách xác định phạm vi service được giải thích trong [Spring Data JPA: Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html).

Bản thân từ khóa `record` không mở giao dịch và không giải quyết việc getter entity cần thêm truy vấn.

## 9. Record lồng nhau cần cách tạo dữ liệu rõ ràng

Có thể khai báo mô hình đọc Java gồm record con:

```java
public record CustomerLabel(
    Long id,
    String name
) {}
```

```java
public record OrderCard(
    Long id,
    String orderNumber,
    CustomerLabel customer
) {}
```

Đây là cấu trúc Java hợp lệ. Tuy nhiên, không suy ra repository tự dựng `CustomerLabel` theo cùng cơ chế proxy đệ quy của interface projection.

Ứng dụng có thể truy vấn một kết quả phẳng rồi tạo cây giá trị:

```java
CustomerLabel customer = customerId == null
    ? null
    : new CustomerLabel(customerId, customerName);

OrderCard card = new OrderCard(
    orderId,
    orderNumber,
    customer
);
```

Các biến trong ví dụ đại diện cho scalar đã được query hoặc mapping lấy ra. Nếu dữ liệu khách hàng là tùy chọn, quy tắc phân biệt “không có khách hàng” cần được thiết kế, chẳng hạn dựa vào ID.

Một record con không chứa entity giúp hợp đồng dữ liệu rõ hơn, nhưng số lượng root và phần tử collection vẫn cần giới hạn theo use case. Tính bất biến không phải giới hạn số byte hoặc số phần tử trong kết quả.

## 10. Equality của record là equality của toàn bộ component

Record không mặc định so sánh chỉ theo ID nghiệp vụ. Với cùng một ID, hai snapshot có giá trị khác vẫn là hai giá trị khác nhau:

```java
Instant createdAt = Instant.parse("2026-01-10T09:00:00Z");

OrderSummary before = new OrderSummary(
    42L,
    "PO-0042",
    new BigDecimal("100.00"),
    createdAt
);

OrderSummary after = new OrderSummary(
    42L,
    "PO-0042",
    new BigDecimal("110.00"),
    createdAt
);

System.out.println(before.equals(after)); // false
```

Điều đó phù hợp với nhiều mô hình đọc: kết quả thay đổi khi một component thay đổi. Nếu cần lập bảng theo định danh, có thể dùng ID làm key thay vì coi toàn bộ record là identity của aggregate.

Với `BigDecimal`, `equals` còn xét scale. Chẳng hạn `10.0` và `10.00` so sánh bằng nhau về giá trị số qua `compareTo`, nhưng `equals` trả false. Quy tắc này được nêu trong [API BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).

Vì equality của record dựa trên component, hai record chứa hai giá trị tiền đó cũng có thể khác nhau. Nếu nghiệp vụ muốn một dạng tiền chuẩn, hãy xác định cách chuẩn hóa nhất quán thay vì giả định record tự bỏ qua scale.

Collection mutable còn có thể làm nội dung tham gia `equals` và `hashCode` thay đổi sau khi instance được đưa vào map hoặc set. Với mảng, equality mặc định của component cũng không tự trở thành phép so sánh sâu nội dung mảng.

Những điểm đó là lý do chọn component bất biến và hợp đồng giá trị rõ ràng ngay từ đầu.

## 11. Record cũng có thể làm kiểu đích của projection động

Một method có thể cho caller chọn kiểu đọc, nếu module hỗ trợ dynamic projection cho query đó:

```java
import java.util.List;

import org.springframework.data.repository.Repository;

public interface DynamicOrderReadRepository
        extends Repository<PurchaseOrder, Long> {

    <T> List<T> findByTenantId(
        String tenantId,
        Class<T> projectionType
    );
}
```

Caller chọn record:

```java
List<OrderSummary> summaries = repository.findByTenantId(
    "ACME",
    OrderSummary.class
);
```

Chọn kiểu đích không thay đổi điều kiện tenant của query và không cho phép yêu cầu một record tùy ý có component không khớp dữ liệu nguồn.

Phần generic `T` và `Class<T>` nối kiểu trả về với kiểu đích. Không truyền raw `Class` rồi ép kiểu collection để che một hợp đồng mapping không phù hợp.

Dynamic projection chỉ là cách lựa chọn mô hình đọc khi gọi repository. Một service vẫn có thể công bố một phương thức có kiểu trả về cố định `List<OrderSummary>` cho use case cụ thể.

## 12. Phân biệt DTO record với kiểu persistent của từng store

Trong các ví dụ JPA, `OrderSummary` là DTO kết quả query; `PurchaseOrder` là kiểu persistent riêng. Sửa dữ liệu bằng cách tạo một record mới không tự cập nhật entity hoặc database.

Nếu caller muốn đổi tổng tiền của đơn, đó là một lệnh nghiệp vụ: xác định aggregate, quyền thao tác, quy tắc tính tiền và yêu cầu đồng thời. DTO đọc có thể cung cấp ID cho bước tiếp theo nhưng không thay thế giao thức ghi.

Ở các module tự thực hiện object mapping, Spring Data có quy tắc nhận diện canonical constructor của record. Tuy nhiên, tài liệu [Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html) nêu rõ phạm vi đó khác với JPA, nơi mapping được giao cho provider.

Vì vậy, cần tách hai câu hỏi:

| Câu hỏi | Nội dung cần kiểm tra |
| --- | --- |
| Record có thể làm DTO projection cho query này không? | Cơ chế projection và tạo kết quả của module. |
| Record có thể làm kiểu domain được lưu trong store này không? | Quy tắc mapping, ID, quan hệ và cập nhật của module. |

Không lấy việc record hoạt động tốt làm DTO JPA để kết luận nó thay trực tiếp mọi entity. Cũng không áp các giới hạn của một ORM cho tất cả document store hoặc module khác.

Một DTO bất biến còn chỉ phản ánh dữ liệu được đọc tại một lần thực hiện query. Nó không bảo đảm các lần đọc sau giống hệt, không tự tạo snapshot transaction cho nhiều query và không chứa cơ chế phát hiện cập nhật đồng thời nếu hợp đồng chưa có thông tin đó.

## 13. Thay component là thay hợp đồng của mô hình đọc

Một record công khai có nhiều điểm phụ thuộc vào danh sách component:

- Constructor và các nơi tạo instance.
- Accessor mà caller sử dụng.
- Query dùng constructor expression hoặc suy luận trường.
- Equality, hash code và biểu diễn chuỗi được sinh.
- Mapping hoặc định dạng trao đổi mà ứng dụng đã cấu hình.

Ví dụ đổi `total` thành `displayTotal` không chỉ đổi nhãn hiển thị. Nó có thể làm derived projection không còn khớp thuộc tính entity và làm caller không còn gọi được `total()`.

Thêm một component cũng không tự có dữ liệu trong một JPQL constructor expression cũ. Cần cập nhật đường tạo record tương ứng.

`toString()` hữu ích cho quan sát khi phát triển, nhưng không nên được coi là định dạng lưu trữ hoặc giao thức trao đổi ổn định của use case. Nó còn đưa giá trị component vào biểu diễn chuỗi, nên chỉ đưa vào mô hình đọc những trường thực sự thuộc hợp đồng cần công bố.

Không thêm setter hoặc framework annotation không liên quan chỉ để làm record giống một JavaBean mutable. Nếu use case cần thay đổi từng phần của một đối tượng lâu sống, hãy đánh giá lại kiểu mô hình thay vì làm mờ hợp đồng dữ liệu.

## 14. Thực hành kiểm tra hợp đồng của record đọc

Bắt đầu bằng `OrderSummary` và `OrderTags` có constructor bảo vệ dữ liệu:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Tạo hai `OrderSummary` cùng component | Equality theo giá trị cho cùng kiểu record. |
| Giữ ID, đổi total | Hai snapshot không còn bằng nhau. |
| Đổi total từ `10.0` sang `10.00` | Xét tác động của equality `BigDecimal`. |
| Truyền null vào component bắt buộc | Constructor từ chối theo hợp đồng đã khai báo. |
| Sửa list đầu vào sau khi tạo `OrderTags` | Snapshot collection giữ nội dung ban đầu. |
| Sửa collection lấy qua accessor | Bị từ chối với list đã bảo vệ. |
| Thay phần tử String bằng đối tượng mutable | Cần đánh giá lại bất biến sâu của mô hình. |

Với repository trong một môi trường tích hợp có store thật, xác định thêm:

1. Tên component có khớp thuộc tính hoặc đường mapping của query không?
2. Constructor nhận đúng số lượng, thứ tự và kiểu giá trị không?
3. Giá trị nullable từ query có khớp hợp đồng constructor không?
4. Kết quả là các giá trị tự chứa hay còn giữ entity và quan hệ lazy?
5. Query lấy trường cần thiết trực tiếp hay ứng dụng chỉ chuyển entity thành record sau khi đã tải?
6. Số dòng đầu ra và kích thước collection có được giới hạn theo use case không?

Một record đọc hữu ích khi nó thể hiện được dữ liệu caller cần, đường tạo instance và mức bất biến thực tế. Kết hợp các component giá trị, constructor rõ ràng và query phù hợp giúp mô hình đọc dễ sử dụng mà vẫn tôn trọng khả năng của từng module Spring Data.

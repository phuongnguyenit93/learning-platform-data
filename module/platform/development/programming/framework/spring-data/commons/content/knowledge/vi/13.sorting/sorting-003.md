# ignoreCase, nullHandling và mức hỗ trợ của store

Trong chương **Sắp xếp** của Spring Data Commons (`SPRING_DATA_COMMONS`), `Sort.Order` mô tả nhiều hơn tên thuộc tính và hướng tăng hoặc giảm. Nó còn có thể mang yêu cầu so sánh không phân biệt hoa thường và gợi ý vị trí của giá trị null.

Commons cung cấp mô hình biểu đạt chung. Module store, cách xây query, phiên bản persistence API, provider và cơ sở dữ liệu quyết định cách chuyển mô hình đó thành thứ tự thực tế. Vì vậy, cần phân biệt **metadata đã được khai báo** với **hành vi đã được kho dữ liệu thực hiện**.

## 1. Một Order gồm những thông tin nào?

Giả sử mô hình `Customer` có các thuộc tính Java:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất, không null trong các ví dụ. |
| `displayName` | `String` | Tên hiển thị, có thể vắng mặt. |
| `region` | `String` | Mã khu vực để lọc dữ liệu. |

Có thể tạo yêu cầu sắp xếp:

```java
import org.springframework.data.domain.Sort;

Sort.Order byName = Sort.Order.asc("displayName")
    .ignoreCase()
    .nullsLast();

Sort sort = Sort.by(
    byName,
    Sort.Order.asc("id")
);
```

Ý định của ví dụ:

1. So sánh tên theo hướng tăng dần.
2. Bỏ qua khác biệt hoa/thường theo cách store thực hiện được.
3. Đưa những giá trị tên null về cuối.
4. Dùng ID tăng dần để phân định các bản ghi có tên được coi là bằng nhau.

Có thể quan sát metadata:

```java
System.out.println(byName.getProperty());     // displayName
System.out.println(byName.getDirection());    // ASC
System.out.println(byName.isIgnoreCase());    // true
System.out.println(byName.getNullHandling()); // NULLS_LAST
```

Đoạn kiểm tra này chứng minh Order đang mang những cờ mong muốn. Nó chưa kiểm chứng query được tạo, collation hay thứ tự bản ghi trả về.

Các phương thức như `ignoreCase()`, `nullsFirst()`, `nullsLast()` trả về Order mới. Vì vậy, cần giữ giá trị trả về. Xem [API Sort.Order](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Sort.Order.html).

Ví dụ giá trị trả về bị bỏ quên:

```java
Sort.Order order = Sort.Order.asc("displayName");

order.ignoreCase();
order.nullsLast();
```

Trong đoạn này, biến `order` vẫn trỏ tới cấu hình ban đầu. Cách viết đúng là gán lại hoặc nối chuỗi như ví dụ đầu.

## 2. ignoreCase tác động đến so sánh khi sắp xếp

`ignoreCase()` thể hiện yêu cầu sắp xếp không phân biệt hoa/thường đối với thuộc tính thích hợp, thường là chuỗi.

Ví dụ một store có thể chuyển yêu cầu đó thành so sánh dựa trên:

```text
lower(displayName)
```

Một store khác có thể cần cấu hình collation. Không nên đồng nhất cờ Commons với một cú pháp SQL cố định trong mọi module.

### Không phải một điều kiện lọc

Hai yêu cầu sau khác nhau:

```java
List<Customer> findByDisplayNameIgnoreCase(String displayName);
```

và:

```java
Sort.Order.asc("displayName").ignoreCase();
```

Ở method đầu, `IgnoreCase` nằm trong predicate của derived query và liên quan đến việc khớp giá trị, nếu module hỗ trợ.

Ở Order thứ hai, cờ liên quan đến cách so sánh thứ tự. Nó không tự thêm điều kiện tìm kiếm và không làm query chỉ chọn những tên bằng nhau.

### Không tự chuẩn hóa dữ liệu lưu trữ

Đặt `ignoreCase()` không có nghĩa:

- Tên trong database được đổi thành chữ thường.
- Giá trị entity trả về được đổi cách viết.
- Chuỗi được trim hoặc bỏ dấu.
- Mọi quy tắc Unicode và mọi ngôn ngữ được xử lý giống nhau.
- Cờ này có ý nghĩa thích hợp với kiểu số, thời điểm hoặc mọi kiểu tùy chỉnh.

Với tên tiếng Việt, cần xác định riêng yêu cầu về hoa/thường, dấu và thứ tự ngôn ngữ. Chỉ một cờ ignoreCase chưa mô tả đầy đủ các lựa chọn đó.

## 3. nullHandling là gợi ý về vị trí null

`Sort.NullHandling` có ba giá trị:

| Giá trị | Ý định |
| --- | --- |
| `NATIVE` | Để store quyết định cách đặt null. |
| `NULLS_FIRST` | Yêu cầu null đứng trước các giá trị không null. |
| `NULLS_LAST` | Yêu cầu null đứng sau các giá trị không null. |

Các cách khai báo tương ứng:

```java
Sort.Order nativeOrder =
    Sort.Order.asc("displayName").nullsNative();

Sort.Order nullsFirst =
    Sort.Order.asc("displayName").nullsFirst();

Sort.Order nullsLast =
    Sort.Order.asc("displayName").nullsLast();
```

API gọi đây là các **hint**. Khả năng thực hiện phụ thuộc datastore và đường xử lý query. Xem [API Sort.NullHandling](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Sort.NullHandling.html).

`NATIVE` không có nghĩa bật native SQL query. Nó chỉ giao chính sách vị trí null cho store trong ngữ cảnh truy vấn hiện tại.

### Hướng sort và vị trí null là hai lựa chọn riêng

Nếu được hỗ trợ đúng theo yêu cầu:

```java
Sort.Order.desc("displayName").nullsLast();
```

biểu đạt các tên không null theo hướng giảm dần, rồi mới tới những bản ghi có tên null.

Không suy rằng null luôn đứng cuối khi ASC hoặc luôn đứng đầu khi DESC trên mọi store. Đó có thể là mặc định của một hệ cụ thể, không phải quy tắc chung của Commons.

### Không loại bỏ bản ghi null

`nullsLast()` thay đổi vị trí mong muốn của bản ghi có giá trị null; nó không thêm điều kiện `IS NOT NULL`.

Trong Java, null, chuỗi rỗng `""` và chuỗi chỉ có khoảng trắng là các giá trị khác nhau. Việc store hoặc mapping có chuẩn hóa chúng hay không cần được xét riêng. Không dùng nullHandling như một cơ chế dọn dữ liệu.

Các annotation nullability trong mã Java cũng không quyết định vị trí null khi sort.

## 4. Kết hợp ignoreCase, nullHandling và tiêu chí phụ

Dùng tập dữ liệu cố định:

| id | displayName |
| --- | --- |
| 11 | An |
| 12 | an |
| 13 | Binh |
| 14 | null |
| 15 | BINH |
| 16 | an |

Giả sử môi trường thực hiện đúng hợp đồng sau:

```text
Tên tăng dần không phân biệt hoa/thường.
Tên null đứng cuối.
Các tên được coi là bằng nhau được phân định bằng id tăng dần.
```

Kỳ vọng thứ tự ID:

```text
11, 12, 16, 13, 15, 14
```

Nhóm `An/an` có ba phần tử; nhóm `Binh/BINH` có hai phần tử. Tiêu chí ID tạo thứ tự bên trong mỗi nhóm.

Nếu đổi riêng hướng tên thành DESC nhưng vẫn giữ `NULLS_LAST` và ID ASC:

```java
Sort sort = Sort.by(
    Sort.Order.desc("displayName").ignoreCase().nullsLast(),
    Sort.Order.asc("id")
);
```

thì kỳ vọng trong mô hình so sánh này là:

```text
13, 15, 11, 12, 16, 14
```

Không đơn giản đảo ngược toàn bộ danh sách ASC: tiêu chí ID vẫn tăng dần và null vẫn được yêu cầu đứng cuối.

Các thứ tự trên là kỳ vọng cho bộ dữ liệu ASCII đã nêu và hợp đồng so sánh giả định. Với dữ liệu có dấu hoặc ký tự ngôn ngữ khác, phải xác định collation tương ứng trước khi chốt kỳ vọng.

## 5. Mức hỗ trợ phụ thuộc cả phiên bản và đường xây query

Có thể hình dung các bước:

```text
Sort.Order
  -> module nhận Sort
  -> chuyển thành Criteria, chuỗi query hoặc lệnh của store
  -> provider/driver xử lý
  -> store so sánh theo kiểu dữ liệu và collation
```

Một hạn chế ở bất kỳ bước nào đều có thể làm yêu cầu bị từ chối hoặc không có hiệu lực như người viết mong đợi.

### Ví dụ cụ thể ở đường Criteria của Spring Data JPA

Trong nhánh mã nguồn Spring Data JPA `3.5.x`, `QueryUtils.toJpaOrder(...)` từ chối null handling khác `NATIVE` bằng `UnsupportedOperationException`. Cùng đường xử lý đó áp dụng ignoreCase bằng biểu thức lower khi thuộc tính là String. Xem [QueryUtils của nhánh 3.5.x](https://github.com/spring-projects/spring-data-jpa/blob/3.5.x/spring-data-jpa/src/main/java/org/springframework/data/jpa/repository/query/QueryUtils.java).

Ở tag `4.1.0`, đường Criteria tương ứng chuyển hint sang `jakarta.persistence.criteria.Nulls` và truyền vào các overload của CriteriaBuilder; biểu thức String có ignoreCase vẫn đi qua lower. Xem [QueryUtils tại tag 4.1.0](https://github.com/spring-projects/spring-data-jpa/blob/4.1.0/spring-data-jpa/src/main/java/org/springframework/data/jpa/repository/query/QueryUtils.java).

Hai ví dụ cho thấy không nên kết luận chung rằng “JPA luôn hỗ trợ” hoặc “JPA luôn không hỗ trợ” từ một kinh nghiệm ở một phiên bản.

| Bằng chứng quan sát | Kết luận có thể rút ra |
| --- | --- |
| Tạo Order thành công | Metadata Commons đã được biểu đạt. |
| Một phiên bản chuyển hint vào Criteria API | Có đường chuyển tiếp ở phiên bản đó; vẫn cần môi trường provider tương thích. |
| Một đường Criteria từ chối hint | Đường đó không đáp ứng yêu cầu bằng hint này. |
| Một native query chạy đúng | Query và store cụ thể có thể thực hiện thứ tự đã viết. |
| Một test trên store khác chạy đúng | Chưa đủ chứng minh môi trường đang triển khai có cùng hành vi. |

Không suy khả năng của declared JPQL, native query và derived query chỉ từ một đường Criteria. Khi chẩn đoán, ghi rõ phiên bản, loại query và provider thay vì chỉ ghi tên module.

## 6. Collation mô tả nhiều hơn bỏ qua hoa/thường

Collation quy định cách so sánh chuỗi. Tùy store và cấu hình, nó có thể liên quan đến:

- Ngôn ngữ hoặc locale.
- Phân biệt hoa/thường.
- Phân biệt dấu.
- Cách xử lý khoảng trắng, dấu câu hoặc chuỗi số.
- Chuẩn hóa và so sánh ký tự Unicode.

Vì vậy, hai môi trường đều được mô tả là “case-insensitive” vẫn có thể cho thứ tự khác nhau ở một số dữ liệu.

### Ví dụ ở MongoDB

Spring Data MongoDB có abstraction `Collation` cho những quy tắc so sánh chuỗi của MongoDB. Có thể áp dụng qua tùy chọn query/operation và những cơ chế repository mà module hỗ trợ.

Điểm cần chú ý là collation áp dụng cho cả operation, không phải một cờ tùy ý trên từng field. Nếu đổi collation để phục vụ sort, cần xét cả ảnh hưởng đến các phép so sánh chuỗi trong operation đó.

Collation của index cũng phải phù hợp với operation để index phục vụ những phép so sánh cần thiết. Xem [Spring Data MongoDB — Collations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/collation.html).

Không mặc định rằng `Sort.Order.ignoreCase()` được dịch thành mọi cấu hình collation cần cho nghiệp vụ. Với store có cơ chế riêng, hãy dùng và kiểm chứng cơ chế của module.

### Với dữ liệu tiếng Việt

Nếu sản phẩm yêu cầu sắp xếp tên theo quy tắc tiếng Việt, cần ghi rõ những trường hợp cần phân biệt, chẳng hạn:

```text
An, an, Án
Dang, Đặng
Chuỗi có dấu được biểu diễn bằng các dạng Unicode khác nhau
```

Không chốt thứ tự các giá trị này chỉ từ tên cờ ignoreCase. Chọn quy tắc so sánh rồi xây bộ dữ liệu kiểm chứng phù hợp.

## 7. Áp dụng Sort vào repository khi đường truy vấn hỗ trợ

Repository minh họa:

```java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<Customer> findByRegion(String region, Sort sort);

    Page<Customer> findByRegion(
        String region,
        Pageable pageable
    );
}
```

Với môi trường đã xác nhận hỗ trợ hợp đồng sort đang chọn:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
    Sort.Order.asc("displayName").ignoreCase().nullsLast(),
    Sort.Order.asc("id")
);

Pageable request = PageRequest.of(0, 3, sort);

Page<Customer> page = repository.findByRegion("SOUTH", request);
```

Tên `displayName` là thuộc tính Java của mô hình. Không tự thay bằng tên cột SQL `display_name` trong Sort của derived query.

Với query có `Pageable`, đặt Sort vào Pageable. Không thêm một tham số Sort riêng bên cạnh Pageable trong cùng query method.

Các cờ được đặt trên từng Order. `ignoreCase()` ở Order của displayName không có nghĩa mọi tiêu chí khác, chẳng hạn ID, cũng được chuyển sang so sánh chuỗi.

### Phân trang cần thứ tự đầy đủ

Khi bỏ qua hoa/thường, nhiều giá trị tên khác cách viết có thể nằm trong cùng nhóm so sánh. Tiêu chí ID giúp tạo thứ tự đầy đủ cho bộ dữ liệu đang xét.

Nó không đóng băng dữ liệu giữa hai yêu cầu trang. Nếu dữ liệu thay đổi, cơ chế phân trang và mức nhất quán vẫn cần được thiết kế theo yêu cầu nghiệp vụ.

## 8. Khi cần biểu đạt thứ tự trực tiếp tại store

Nếu đường query đang dùng chưa đáp ứng hợp đồng bằng các hint, một lựa chọn là khai báo truy vấn hoặc triển khai custom repository theo đúng khả năng store.

Ví dụ SQL **riêng cho PostgreSQL**, giả sử bảng có các cột `id`, `display_name`, `region`:

```sql
SELECT id, display_name, region
FROM customer
ORDER BY lower(display_name) ASC NULLS LAST,
         id ASC;
```

Query viết trực tiếp ba quyết định:

- Dùng lower của PostgreSQL làm biểu thức so sánh tên.
- Đặt null cuối.
- Phân định các giá trị bằng nhau bằng ID.

PostgreSQL cho phép chỉ định `NULLS FIRST` hoặc `NULLS LAST` cho từng biểu thức ORDER BY. Xem [PostgreSQL — Sorting Rows](https://www.postgresql.org/docs/current/queries-order.html).

Hàm lower của PostgreSQL hoạt động theo quy tắc locale của database. Không xem nó là một phép bỏ dấu hoặc case folding toàn diện cho mọi Unicode. Xem [PostgreSQL — String Functions](https://www.postgresql.org/docs/current/functions-string.html).

Đây là phương án theo store cụ thể. Khi đưa vào Spring Data JPA native query hoặc một adapter khác, cần cấu hình binding, mapping và kiểu kết quả tương ứng.

Nếu query còn có điều kiện lọc, phân trang hoặc query đếm riêng, phải giữ hợp đồng nhất quán giữa các phần đó. Việc chuyển sang query tường minh không tự giải quyết mọi vấn đề mapping và hiệu năng.

## 9. Java Comparator có phạm vi sử dụng khác với sort ở store

Với một tập dữ liệu nhỏ đã được chủ động tải đầy đủ, có thể sắp xếp trong bộ nhớ:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

Comparator<Customer> comparator = Comparator
    .comparing(
        Customer::getDisplayName,
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
    )
    .thenComparing(Customer::getId);

List<Customer> sorted = new ArrayList<>(customers);
sorted.sort(comparator);
```

Giả định `customers` là toàn bộ tập cần sắp xếp và ID không null.

Comparator này thực hiện quy tắc Java đã chọn; nó không bảo đảm giống collation của database.

### Không sort lại từng trang để thay thế sort toàn bộ tập

Nếu database đã chọn một trang theo thứ tự khác, sort nội dung của riêng trang đó không đưa những bản ghi thuộc trang khác về vị trí đúng.

Ví dụ, trang đầu đã lấy một bản ghi null nhưng bỏ lại một tên không null ở trang sau. Đưa null xuống cuối trang đầu vẫn không làm thứ tự toàn bộ kết quả đáp ứng “null đứng cuối”.

Vì vậy, lựa chọn xử lý Java cần được gắn với hợp đồng rõ ràng: dữ liệu đầy đủ trong bộ nhớ, hoặc một cơ chế tổng hợp khác đã được thiết kế có chủ đích.

### Đảo hướng và null cần giữ đúng thứ tự thao tác

Nếu muốn giảm dần tên nhưng null vẫn cuối trong Comparator, đảo comparator của các giá trị không null trước khi bọc:

```java
Comparator<String> namesDescendingWithNullLast =
    Comparator.nullsLast(
        String.CASE_INSENSITIVE_ORDER.reversed()
    );
```

Đảo toàn bộ một comparator đã bọc nullsLast sẽ đảo cả vị trí null. Đây là một ví dụ cho thấy hướng của giá trị thường và vị trí null phải được đọc riêng ở từng API.

## 10. Kiểm chứng metadata và kiểm chứng store trả lời hai câu hỏi khác nhau

Một kiểm tra metadata có thể xác nhận:

```text
property     = displayName
direction    = ASC
ignoreCase   = true
nullHandling = NULLS_LAST
```

Để xác nhận hành vi, cần gọi query thật trên module và môi trường store phù hợp.

Một tập ca đại diện:

| Ca dữ liệu hoặc cấu hình | Điều cần quan sát |
| --- | --- |
| An và an | Có được coi như cùng nhóm so sánh theo hợp đồng không. |
| Hai giá trị tên bằng nhau | Tiêu chí ID có phân định thứ tự đúng không. |
| Null cùng tên không null | Null có đứng theo vị trí đã công bố không. |
| DESC kết hợp NULLS_LAST | Null có vẫn ở cuối hay chỉ bị đảo theo mặc định store. |
| Chuỗi rỗng, khoảng trắng, null | Có bị nhập nhằng bởi mapping hoặc quy tắc store không. |
| Tên có dấu và khác dạng Unicode | Collation có đáp ứng quy tắc ngôn ngữ đã chọn không. |
| Lấy nhiều trang từ dữ liệu cố định | Thứ tự xuyên trang có nhất quán với query chung không. |
| Hint chưa được hỗ trợ | Ứng dụng có phản ánh đúng giới hạn thay vì âm thầm đổi hợp đồng không. |

Khi môi trường sử dụng JPA, cần ghi nhận phiên bản JPA module, provider và loại query. Khi dùng MongoDB, ghi nhận collation và cấu hình index liên quan. Một test chỉ in Sort không thay thế được các kiểm chứng này.

Nếu dùng database thay thế trong kiểm thử, cần đánh giá những khác biệt về null ordering và collation trước khi dùng kết quả đó để kết luận cho môi trường triển khai.

## 11. Thiết kế hợp đồng sắp xếp và xử lý giới hạn hỗ trợ

Một yêu cầu đủ rõ có thể viết:

```text
Trong tập khách hàng của khu vực được chọn:
- tên tăng dần theo quy tắc so sánh đã xác định;
- không phân biệt hoa/thường theo quy tắc đó;
- tên null ở cuối;
- ID tăng dần khi tên được coi là bằng nhau.
```

Sau đó chọn một cách thực hiện đáp ứng hợp đồng trên môi trường thực tế.

Nếu store hoặc đường query không hỗ trợ, các lựa chọn có thể là:

1. Dùng query tường minh hoặc API store phù hợp.
2. Thiết kế một khóa sắp xếp được chuẩn hóa theo quy tắc nghiệp vụ và quản lý đồng bộ với dữ liệu gốc.
3. Xử lý trong bộ nhớ khi quy mô và phạm vi dữ liệu cho phép.
4. Công bố một chính sách fallback khác nếu sản phẩm chấp nhận và phía gọi hiểu được thay đổi.

Không nên bắt một lỗi “không hỗ trợ”, bỏ ignoreCase/nullHandling rồi tiếp tục như thể đã thực hiện đầy đủ yêu cầu ban đầu.

Về hiệu năng, biểu thức so sánh, collation và thứ tự null có thể ảnh hưởng cách store dùng index hoặc thực hiện sort. Kiểm tra query và kế hoạch thực thi thực tế; không suy rằng thêm cờ luôn miễn phí hoặc luôn làm mất index.

## 12. Thực hành với bộ dữ liệu trong bài

Với các ID 11 đến 16 đã nêu, hãy viết và đối chiếu ba yêu cầu:

**Yêu cầu A:** tên ASC, không phân biệt hoa/thường, null cuối, ID ASC.

```text
Kỳ vọng theo mô hình so sánh đã chọn:
11, 12, 16, 13, 15, 14
```

**Yêu cầu B:** tên DESC, không phân biệt hoa/thường, null cuối, ID ASC.

```text
Kỳ vọng:
13, 15, 11, 12, 16, 14
```

**Yêu cầu C:** tên ASC, không phân biệt hoa/thường, null đầu, ID ASC.

```text
Kỳ vọng:
14, 11, 12, 16, 13, 15
```

Với mỗi yêu cầu, trả lời riêng:

- Đối tượng Sort có mang đúng các cờ không?
- Đường query và phiên bản đang dùng có tiếp nhận được chúng không?
- Thứ tự kết quả thực tế có đáp ứng hợp đồng không?
- Các kết luận có còn đúng khi thêm tên có dấu hoặc đổi store không?

Bộ câu hỏi này giữ rõ trách nhiệm của Commons, module và quy tắc so sánh tại store khi triển khai sắp xếp có ignoreCase và nullHandling.

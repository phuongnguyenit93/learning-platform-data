# PartTree và cách kiểm tra tên phương thức trước khi quy lỗi cho cơ sở dữ liệu

Một repository không tạo được query chưa chắc đã gặp lỗi SQL, schema hoặc kết nối. Với derived query, tên phương thức phải được phân tích và đối chiếu với mô hình Java trước khi module có thể xây truy vấn cho kho dữ liệu.

Trong chương **Suy diễn tên phương thức** của Spring Data Commons (`SPRING_DATA_COMMONS`), bài này dùng `PartTree` để quan sát bước phân tích đó. Mục tiêu là khoanh vùng lỗi bằng bằng chứng: tên được hiểu thành cấu trúc nào, thuộc tính nào không phân giải được và phần nào còn cần kiểm chứng qua repository thực tế.

## 1. PartTree kiểm tra điều gì?

`PartTree` thuộc package:

```java
org.springframework.data.repository.query.parser
```

Đầu vào cơ bản là một chuỗi tên và một domain class:

```java
PartTree tree = new PartTree(methodName, Ticket.class);
```

Đối tượng kết quả mô tả những thông tin như các nhánh điều kiện, đường dẫn thuộc tính, toán tử, cờ distinct, loại thao tác và sort tĩnh. Constructor nhận domain class để phân giải các thuộc tính được tham chiếu. Xem [API PartTree](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/parser/PartTree.html).

Cần phân biệt các tầng sau:

| Tầng | Câu hỏi |
| --- | --- |
| Phân tích tên | Tên được hiểu thành điều kiện và sort nào? Thuộc tính Java có tồn tại không? |
| Hợp đồng query method | Tham số, kiểu kết quả và tham số đặc biệt có hợp lệ không? |
| Xây truy vấn theo module | Mapping và toán tử có thể chuyển thành truy vấn của store không? |
| Thực thi | Kết nối, quyền, schema, dữ liệu và kế hoạch truy vấn có đáp ứng không? |

Gọi `new PartTree(...)` trực tiếp trên một POJO thông thường không cần mở kết nối database. Nhưng parser thành công chỉ cung cấp bằng chứng ở tầng phân tích tên, không chứng minh tất cả các tầng còn lại đều đúng.

Commons cung cấp abstraction dùng chung. JPA, MongoDB và các module khác bổ sung cách xây và thực thi truy vấn theo khả năng riêng.

## 2. Trước khi parse, xác định method có thật sự dùng name derivation

Không nên đưa mọi method của repository vào `PartTree` rồi coi mọi lỗi là lỗi ứng dụng.

| Loại method | Cách xử lý khi chẩn đoán |
| --- | --- |
| Derived query thực sự được chọn | Phân tích tên cùng domain class tương ứng. |
| Method dùng declared query có hiệu lực | Đọc định nghĩa query được chọn và kiểm tra binding. |
| Method CRUD cơ sở | Kiểm tra hợp đồng method cơ sở và metadata định danh. |
| Default method hoặc custom fragment | Kiểm tra phần thân hoặc phần triển khai của method. |

Ví dụ, một method có tên tự do có thể hoạt động nhờ `@Query` của module. Parse riêng tên tự do đó không chứng minh khai báo query sai.

Một ví dụ khác là `findById`: chữ ký CRUD cơ sở truy vấn theo thuộc tính được mapping làm identifier. Thuộc tính ấy có thể tên `pk`, không phải `id`.

Nếu domain class chỉ có `pk`, parse thủ công chuỗi `findById` có thể thất bại vì không thấy thuộc tính Java `id`, trong khi lời gọi CRUD cơ sở vẫn hợp lệ với mapping của module.

Vì vậy, bước đầu là xác định đường thực thi và query lookup strategy có hiệu lực. Tên “trông giống derived query” chưa đủ để kết luận nguồn query đang dùng.

## 3. Một chương trình kiểm tra tối thiểu, không cần database

Ví dụ dưới đây dùng POJO chỉ phục vụ phân tích tên. Nó không khai báo entity, bảng hay collection.

Trong dự án đã có Spring Data Commons và các dependency cần thiết, có thể đặt mã sau trong một lớp Java để quan sát cấu trúc:

```java
import java.time.Instant;

import org.springframework.data.repository.query.parser.Part;
import org.springframework.data.repository.query.parser.PartTree;

public class PartTreeProbe {

    public static void main(String[] args) {
        String methodName =
            "findTop3ByStatusAndQueueCodeOrderByCreatedAtDescIdDesc";

        PartTree tree = new PartTree(methodName, Ticket.class);

        System.out.println("distinct=" + tree.isDistinct());
        System.out.println("count=" + tree.isCountProjection());
        System.out.println("exists=" + tree.isExistsProjection());
        System.out.println("delete=" + tree.isDelete());
        System.out.println("maxResults=" + tree.getMaxResults());

        int groupIndex = 0;

        for (PartTree.OrPart group : tree) {
            System.out.println("OR group " + groupIndex++);

            for (Part part : group) {
                System.out.printf(
                    "  %s | %s | args=%d%n",
                    part.getProperty().toDotPath(),
                    part.getType().name(),
                    part.getNumberOfArguments()
                );
            }
        }

        tree.getSort().forEach(order ->
            System.out.printf(
                "sort: %s %s%n",
                order.getProperty(),
                order.getDirection()
            )
        );
    }

    static class Ticket {
        Long id;
        String tenantId;
        String queueCode;
        TicketStatus status;
        TicketPriority priority;
        Instant createdAt;
    }

    enum TicketStatus {
        OPEN, CLOSED
    }

    enum TicketPriority {
        LOW, HIGH
    }
}
```

Các thông tin cần thấy:

```text
distinct=false
count=false
exists=false
delete=false
maxResults=3
OR group 0
  status | SIMPLE_PROPERTY | args=1
  queueCode | SIMPLE_PROPERTY | args=1
sort: createdAt DESC
sort: id DESC
```

Cách đọc:

- Đây là query lấy dữ liệu, không phải count, exists hoặc delete.
- `Top3` tạo giới hạn tối đa ba kết quả.
- Chỉ có một nhánh OR, gồm hai điều kiện nối bằng AND.
- `status` và `queueCode` là hai đường dẫn được phân giải.
- Mỗi phép so sánh bằng cần một đối số nghiệp vụ.
- Sort tĩnh có hai tiêu chí, không tạo thêm đối số điều kiện.

Các phương thức `getProperty()`, `getType()`, `getNumberOfArguments()` thuộc `Part`. Xem [API Part](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/parser/Part.html).

Với tên không có giới hạn, `getMaxResults()` trả null. Nếu sử dụng API mới hơn như `getResultLimit()`, cần đối chiếu phiên bản Commons của dự án; không nên đổi dependency chỉ để phục vụ một đoạn chẩn đoán.

## 4. Dùng lỗi thuộc tính để khoanh vùng vấn đề

Đổi tên cần kiểm tra thành:

```java
new PartTree(
    "findByQueuCode",
    PartTreeProbe.Ticket.class
);
```

Mô hình có `queueCode`, còn tên method thiếu một chữ `e`. Đây là lỗi phân giải thuộc tính Java; sửa dữ liệu trong bảng không làm thuộc tính `queuCode` xuất hiện trên class.

Một chuỗi lỗi khi tạo repository có thể có dạng minh họa:

```text
BeanCreationException: không tạo được repository bean
  ...
QueryCreationException: không tạo được query cho method
  ...
PropertyReferenceException:
  No property 'queuCode' found for type 'Ticket'
```

Thông báo và các lớp bọc có thể khác theo module, phiên bản và cách bootstrap. Điều cần đọc là nguyên nhân cụ thể kèm tên thuộc tính và kiểu đang được phân giải.

### Đọc thông tin từ exception

```java
import org.springframework.data.mapping.PropertyReferenceException;
import org.springframework.data.repository.query.parser.PartTree;

try {
    new PartTree(
        "findByQueuCode",
        PartTreeProbe.Ticket.class
    );
} catch (PropertyReferenceException ex) {
    System.out.println("missingProperty=" + ex.getPropertyName());
    System.out.println(
        "declaringType=" + ex.getType().getType().getSimpleName()
    );
}
```

`PropertyReferenceException` có thông tin về tên không tìm thấy, kiểu được xét và phần đường dẫn đã phân giải được. Xem [mã nguồn PropertyReferenceException, nhánh Commons 3.5.x](https://github.com/spring-projects/spring-data-commons/blob/3.5.x/src/main/java/org/springframework/data/mapping/PropertyReferenceException.java).

Khi có lỗi này, kiểm tra:

1. Chính tả thuộc tính trong tên method.
2. Domain class có đúng với repository đang xét không.
3. Thuộc tính đã bị đổi tên nhưng query method chưa cập nhật chưa.
4. Có nhầm tên cột hoặc field lưu trữ với tên thuộc tính Java không.
5. Lỗi xảy ra ở thuộc tính gốc hay ở một đoạn đường dẫn lồng nhau.

Không kết luận toàn bộ hệ thống chưa từng truy cập database chỉ từ một đoạn stack trace. Kết luận hẹp hơn là nguyên nhân đang thấy liên quan đến phân giải thuộc tính, nên cần xử lý đúng tầng đó.

## 5. Kiểm tra đường dẫn lồng nhau và chỗ tách mơ hồ

Giả sử một mô hình khác có:

```java
class Shipment {
    Address address;
    String addressZip;
}

class Address {
    String zipCode;
}
```

Bạn muốn lọc theo `address.zipCode` và đặt tên:

```text
findByAddressZipCode
```

Phép phân giải có thể chọn `addressZip` trước, rồi tìm phần `code` bên trong kiểu của thuộc tính đó. Trong mô hình này, `addressZip` là String và không có đường dẫn `code` như dự định.

Đây là một tình huống tên thuộc tính tồn tại nhưng điểm tách không theo ý người viết.

Có thể biểu đạt rõ ranh giới traversal:

```java
PartTree tree = new PartTree(
    "findByAddress_ZipCode",
    Shipment.class
);

for (Part part : tree.getParts()) {
    System.out.println(part.getProperty().toDotPath());
}
```

Đường dẫn cần thấy:

```text
address.zipCode
```

Dấu gạch dưới ở ví dụ xác định điểm đi qua thuộc tính; nó không phải ký hiệu tên cột SQL và cũng không phải ngoặc Boolean.

Cơ chế ưu tiên đường dẫn và cách dùng dấu gạch dưới được trình bày trong [Spring Data Commons — Property Expressions](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.query-methods.query-property-expressions).

Khi kiểm tra đường dẫn thực tế, dùng domain class thực của query method. Một POJO được viết lại nhưng thiếu thuộc tính gây mơ hồ có thể cho kết quả khác mô hình ứng dụng.

## 6. Parse thành công vẫn có thể sai nghiệp vụ

Xét:

```java
PartTree tree = new PartTree(
    "findByTenantIdAndStatusOrPriority",
    PartTreeProbe.Ticket.class
);
```

Tất cả thuộc tính đều tồn tại. Khi duyệt theo từng `OrPart`, sẽ thấy:

```text
Nhánh 0:
  tenantId
  status

Nhánh 1:
  priority
```

Cấu trúc là:

```text
(tenantId khớp AND status khớp)
OR
priority khớp
```

Nó không phải:

```text
tenantId khớp
AND
(status khớp OR priority khớp)
```

`PartTree` chấp nhận cấu trúc hợp lệ; nó không biết yêu cầu nghiệp vụ rằng mọi nhánh phải thuộc cùng tenant.

Nếu chỉ dùng `getParts()` để lấy danh sách phẳng các thuộc tính, bạn có thể thấy đủ `tenantId`, `status`, `priority` nhưng bỏ lỡ vấn đề nhóm. Khi cần kiểm tra AND/OR, hãy duyệt `PartTree` theo từng `OrPart`.

Tương tự:

```text
findOpenTicketsByQueueCode
```

có thể parse thành một điều kiện duy nhất trên `queueCode`. Từ `OpenTickets` ở phần chủ thể không tự thêm điều kiện `status = OPEN`.

Vì vậy, tiêu chí “không ném exception” khác với tiêu chí “cây điều kiện khớp yêu cầu”.

## 7. Những vấn đề PartTree không tự xác nhận

Constructor chỉ nhận tên và domain class. Nó không nhận đối tượng `Method`, danh sách đối số thực tế, kiểu trả về hay cấu hình repository.

### Thiếu tham số cho toán tử

```java
PartTree tree = new PartTree(
    "findByCreatedAtBetween",
    PartTreeProbe.Ticket.class
);
```

Parser có thể phân giải `createdAt` cùng toán tử `BETWEEN`, và `Part` tương ứng báo cần hai đối số.

Nhưng chữ ký sau vẫn thiếu một giá trị:

```java
// Sai hợp đồng tham số cho BETWEEN.
List<Ticket> findByCreatedAtBetween(Instant from);
```

Muốn kết luận chữ ký đúng, phải kiểm tra đủ hai đầu khoảng cùng kiểu phù hợp:

```java
List<Ticket> findByCreatedAtBetween(
    Instant from,
    Instant to
);
```

### Tổ hợp tham số đặc biệt không hợp lệ

Tên `findByStatus` có thể parse được, nhưng chữ ký query method sau có vấn đề:

```java
Page<Ticket> findByStatus(
    TicketStatus status,
    Pageable pageable,
    Sort sort
);
```

`Pageable` đã mang thông tin sort. Hạ tầng query method không cho kết hợp riêng `Pageable` và `Sort` theo cách này. Một lần parse tên không nhìn thấy tổ hợp đó.

### Mapping và hỗ trợ của module

Một thuộc tính tồn tại trong class chưa chắc là thuộc tính có thể truy vấn theo mapping đang dùng. Tương tự, việc parser nhận ra một toán tử không bảo đảm mọi store đều chuyển được toán tử đó thành truy vấn hợp lệ.

| Parser đã cho thấy | Phần vẫn phải xác minh |
| --- | --- |
| Đường dẫn Java phân giải được | Mapping persistence và khả năng truy vấn đường dẫn đó. |
| Toán tử được nhận diện | Module hỗ trợ toán tử với kiểu thuộc tính đang dùng. |
| Số đối số cần cho từng Part | Chữ ký thực tế có đủ tham số bindable với kiểu phù hợp. |
| Sort tĩnh trong tên | Khả năng áp sort theo query và store. |
| Cờ count, exists, delete, distinct | Kiểu trả về và ngữ nghĩa thực thi của module. |
| Giới hạn kết quả | Dữ liệu được chọn có đúng thứ tự và ý định nghiệp vụ. |

Tài liệu Commons cũng phân biệt khả năng chung của parser với khả năng theo datastore; xem [Defining Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html).

## 8. Thêm kiểm thử cấu trúc cho hợp đồng cần giữ ổn định

Một tên query dài có thể vẫn biên dịch sau khi bị sửa sai ý nghĩa. Kiểm thử cấu trúc giúp ghi lại những phần quan trọng của hợp đồng, như giới hạn, điều kiện và sort.

Ví dụ dùng JUnit 5, đặt cùng package với lớp `PartTreeProbe` ở phần trước:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Sort;
import org.springframework.data.mapping.PropertyReferenceException;
import org.springframework.data.repository.query.parser.PartTree;

class DerivedQueryStructureTest {

    @Test
    void newestTicketsKeepTheirLimitAndOrder() {
        PartTree tree = new PartTree(
            "findTop3ByStatusAndQueueCodeOrderByCreatedAtDescIdDesc",
            PartTreeProbe.Ticket.class
        );

        List<String> paths = tree.getParts().stream()
            .map(part -> part.getProperty().toDotPath())
            .collect(Collectors.toList());

        assertEquals(
            Arrays.asList("status", "queueCode"),
            paths
        );

        assertEquals(Integer.valueOf(3), tree.getMaxResults());

        assertEquals(
            Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
            ),
            tree.getSort()
        );
    }

    @Test
    void misspelledQueuePropertyIsRejected() {
        assertThrows(
            PropertyReferenceException.class,
            () -> new PartTree(
                "findByQueuCode",
                PartTreeProbe.Ticket.class
            )
        );
    }
}
```

Các kiểm thử này không cần khởi tạo repository hoặc datasource. Chúng xác minh phần cấu trúc được chọn, không xác minh dữ liệu trả về.

Nếu dùng chúng cho dự án thật, nên lấy đúng tên method và đúng domain class của repository cần bảo vệ. Một chuỗi được sao chép vào test có thể bị bỏ quên khi method thật đổi tên. Có thể lấy tên qua reflection khi phù hợp, đồng thời vẫn giữ kỳ vọng nghiệp vụ độc lập về điều kiện, giới hạn và thứ tự.

Không cần viết kiểm thử parser cho mọi method CRUD đơn giản. Hãy ưu tiên những tên có rủi ro đổi đường dẫn, đổi nhóm hoặc đổi giới hạn ngoài ý muốn.

## 9. Quy trình khoanh vùng khi repository báo lỗi

### Bước 1: Thu lại đúng method và đúng nguyên nhân

Ghi nhận chữ ký đầy đủ, domain type, module store và đoạn nguyên nhân có ý nghĩa trong chuỗi exception.

Một `BeanCreationException` chỉ nói bean không tạo được. Một `QueryCreationException` cho biết quá trình tạo query thất bại nhưng tự nó chưa phân biệt lỗi thuộc tính, binding hay query của module.

Không chỉ đọc tên exception ngoài cùng; cũng không chỉ lấy dòng cuối cùng mà bỏ mất method và đường dẫn liên quan.

### Bước 2: Xác định nguồn truy vấn

Kiểm tra method đang dùng suy diễn tên, named query, annotation query, CRUD cơ sở hay fragment. Áp dụng `PartTree` khi đúng là đường name derivation.

### Bước 3: Kiểm tra cấu trúc tên trên mô hình Java

Quan sát:

- Các đường dẫn của từng `Part`.
- Nhóm `OrPart` và các điều kiện AND trong mỗi nhóm.
- Loại toán tử và số đối số cần bind.
- Sort tĩnh, giới hạn, cờ count/exists/delete/distinct.

Nếu sai đường dẫn, sửa tên hoặc mô hình theo hợp đồng dự định trước khi xem SQL.

### Bước 4: Đối chiếu chữ ký

Kiểm tra số và kiểu đối số nghiệp vụ, các tham số đặc biệt như `Pageable`, `Sort`, cùng kiểu trả về.

Không tính một tham số đặc biệt như một giá trị điều kiện chỉ vì nó xuất hiện trong danh sách đối số Java.

### Bước 5: Kiểm tra mapping và query do module tạo

Nếu tên cùng chữ ký đã phù hợp, xem khả năng của module, mapping entity/document, conversion và lỗi provider có liên quan.

Thời điểm phát hiện lỗi có thể khác nhau theo module và chế độ bootstrap. Không mặc định mọi lỗi query đều xuất hiện lúc khởi động hoặc đều chờ đến lần gọi đầu tiên.

### Bước 6: Đánh giá lỗi thực thi khi có bằng chứng tương ứng

Khi lỗi chỉ ra kết nối, câu lệnh của store, schema, quyền hoặc ràng buộc dữ liệu, kiểm tra những phần đó. Khi truy vấn chạy nhưng chậm, cần xem query thực tế và kế hoạch thực thi; `PartTree` không đo hiệu năng.

Với kiểm thử tích hợp, sử dụng module cùng loại kho dữ liệu phù hợp với ứng dụng để xác minh hành vi cần bảo đảm. Parser test và integration test trả lời những câu hỏi khác nhau.

## 10. Một ca chẩn đoán xuyên suốt

Giả sử service không khởi tạo được vì repository khai báo:

```java
List<Ticket> findByQueuCodeAndStatus(
    String queueCode,
    TicketStatus status
);
```

Domain class có `queueCode`, còn stack trace nêu lỗi không tìm thấy `queuCode`.

### Bằng chứng đầu tiên

Parse tên đó cùng domain class gây lỗi phân giải thuộc tính. Điều này giải thích được lỗi đang quan sát mà chưa cần giả thiết bảng thiếu cột.

Sửa tên:

```java
List<Ticket> findByQueueCodeAndStatus(
    String queueCode,
    TicketStatus status
);
```

### Bằng chứng tiếp theo

Cây cần có một nhánh với hai phần:

```text
queueCode | SIMPLE_PROPERTY | args=1
status    | SIMPLE_PROPERTY | args=1
```

Chữ ký cần hai đối số nghiệp vụ theo thứ tự tương ứng. Sau đó mới dùng repository thực để xác minh mapping và kết quả.

### Điều kiện để khẳng định hành vi

Bộ dữ liệu tích hợp nên có ít nhất:

| Ticket | queueCode | status | Khi tìm SUPPORT và OPEN |
| --- | --- | --- | --- |
| A | SUPPORT | OPEN | Được chọn. |
| B | SUPPORT | CLOSED | Bị loại. |
| C | BILLING | OPEN | Bị loại. |

Ba bản ghi giúp phân biệt đúng hai điều kiện với trường hợp vô tình bỏ một điều kiện hoặc đổi `And` thành `Or`.

Nếu parser đã đúng nhưng query tích hợp vẫn lỗi, tiếp tục từ nguyên nhân mới của module hoặc database. Không dùng kết quả parse thành công để khép lại việc xác minh toàn bộ truy vấn.

## 11. Thực hành đọc bằng chứng

Với các thuộc tính trong `PartTreeProbe.Ticket`, hãy dự đoán trước khi thử:

| Tên cần kiểm tra | Điều có thể kết luận ở tầng parser |
| --- | --- |
| `findByQueueCode` | Có điều kiện trên `queueCode`, cần một đối số. |
| `findByQueuCode` | Không phân giải được thuộc tính đúng như mô hình đã nêu. |
| `findByCreatedAtBetween` | Nhận diện khoảng trên `createdAt`, cần hai đối số. |
| `findTop3ByOrderByCreatedAtDescIdDesc` | Không có điều kiện lọc; có giới hạn ba và sort tĩnh. |
| `findByTenantIdAndStatusOrPriority` | Hai nhánh OR; tenant chỉ có trong nhánh cùng status. |
| `findOpenTicketsByQueueCode` | Chỉ có điều kiện `queueCode`; không tự thêm trạng thái OPEN. |

Sau mỗi dự đoán, tự tách hai câu trả lời:

1. Parser đã chứng minh được điều gì về tên và mô hình Java?
2. Còn phải kiểm tra điều gì qua chữ ký, module và kho dữ liệu?

Cách ghi nhận này giúp sửa đúng nguyên nhân trước mắt, đồng thời giữ rõ giới hạn của một kiểm tra không truy cập database.

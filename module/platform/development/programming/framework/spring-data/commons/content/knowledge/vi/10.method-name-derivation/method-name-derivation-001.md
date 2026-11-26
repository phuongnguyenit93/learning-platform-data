# Tách phần chủ thể và điều kiện tại từ khóa By

Trong chương **Suy diễn tên phương thức** của Spring Data Commons (`SPRING_DATA_COMMONS`), bước đầu tiên khi đọc một derived query là xác định tên phương thức chia thành những phần nào. Nếu đặt sai ranh giới, người đọc có thể nhầm một từ mô tả thành điều kiện lọc, hoặc nhầm thông tin sắp xếp thành một tham số nghiệp vụ.

Bài này dùng các abstraction repository của Commons để giải thích quy tắc phân tích tên. Việc chuyển cấu trúc đó thành truy vấn cụ thể, hỗ trợ toán tử, projection và kiểu kết quả thuộc module kho dữ liệu. Các ví dụ giả định module đang dùng hỗ trợ những dạng derived query được minh họa.

## 1. Mô hình đọc tên: chủ thể, By và phần phía sau

Xét tên phương thức:

```text
findTicketsByStatusAndQueueCodeOrderByCreatedAtDesc
```

Có thể đánh dấu:

```text
findTickets | By | StatusAndQueueCodeOrderByCreatedAtDesc
     │        │                    │
  chủ thể  ranh giới        phần predicate
```

Trong cách trình bày của bài, cột **chủ thể** không viết kèm dấu phân cách `By`, để nhìn rõ vị trí tách. Tài liệu Spring Data cũng thường mô tả phần mở đầu dưới dạng `find…By`, `exists…By`.

Ba phần có vai trò:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Chủ thể, hay subject | Đây là thao tác tìm, đếm, kiểm tra tồn tại hay xóa? Có cờ hoặc giới hạn kết quả nào được hỗ trợ không? |
| `By` phân cách | Từ đâu bắt đầu phần diễn đạt điều kiện? |
| Phần phía sau, hay predicate | Thuộc tính nào tham gia điều kiện, dùng toán tử gì, có sắp xếp tĩnh không? |

Trong ví dụ, `findTickets` mở đầu một thao tác tìm. `StatusAndQueueCode` diễn đạt điều kiện trên hai thuộc tính. `OrderByCreatedAtDesc` diễn đạt sắp xếp tĩnh, không phải một điều kiện so sánh.

Với mẫu derived query có tiền tố hợp lệ, `By` đầu tiên làm dấu phân cách để bắt đầu phần tiêu chí. Quy tắc subject/predicate được mô tả trong [Spring Data Commons — Query Creation](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.query-methods.query-creation).

## 2. Mô hình dữ liệu dùng trong các ví dụ

Giả sử `Ticket` đã được ánh xạ theo module kho dữ liệu, có các thuộc tính Java:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh ticket. |
| `status` | `TicketStatus` | Ví dụ `OPEN`, `CLOSED`. |
| `queueCode` | `String` | Mã hàng đợi xử lý. |
| `createdAt` | `Instant` | Thời điểm tạo. |
| `archived` | `boolean` | Ticket đã được lưu trữ hay chưa. |

Repository minh họa:

```java
import java.util.List;

import org.springframework.data.repository.CrudRepository;

public interface TicketRepository extends CrudRepository<Ticket, Long> {

    List<Ticket> findTicketsByStatus(TicketStatus status);

    List<Ticket> findByStatusAndQueueCode(
        TicketStatus status,
        String queueCode
    );

    long countByStatus(TicketStatus status);

    boolean existsByQueueCode(String queueCode);
}
```

Đây là hợp đồng repository, chưa phải toàn bộ ứng dụng chạy độc lập. Mapping của `Ticket`, enum `TicketStatus` và cấu hình kết nối thuộc phần thiết lập module.

Các tên `Status`, `QueueCode` trong predicate được phân giải từ thuộc tính của mô hình. Không mặc nhiên dùng tên cột SQL như `queue_code` để đặt derived method.

Domain type ở đây đến từ `CrudRepository<Ticket, Long>`. Từ `Tickets` trong `findTicketsByStatus` không phải cơ chế để chọn bảng hoặc collection.

## 3. Chủ thể bắt đầu bằng loại thao tác

Các dạng tiền tố thường gặp có thể đọc như sau:

| Dạng tên | Ý định ở mức phân tích tên |
| --- | --- |
| `find…By`, `read…By`, `get…By`, `query…By`, `search…By`, `stream…By` | Nhóm thao tác truy vấn dữ liệu. |
| `count…By` | Đếm kết quả phù hợp. |
| `exists…By` | Kiểm tra có kết quả phù hợp hay không. |
| `delete…By`, `remove…By` | Xóa theo điều kiện. |

Không suy từ bảng rằng mọi tiền tố chấp nhận mọi kiểu trả về trên mọi module. Chẳng hạn, hỗ trợ kết quả streaming và cách thực thi xóa cần tuân theo hợp đồng của module.

So sánh:

```java
List<Ticket> findByStatus(TicketStatus status);

long countByStatus(TicketStatus status);

boolean existsByStatus(TicketStatus status);
```

Cả ba có cùng phần `Status` sau `By`, nhưng không có cùng kết quả:

- Method đầu yêu cầu các ticket phù hợp.
- Method thứ hai yêu cầu số lượng phù hợp.
- Method thứ ba chỉ yêu cầu biết có ít nhất một ticket phù hợp hay không.

Không đọc toàn bộ tên như một điều kiện duy nhất. `count` và `exists` không phải thuộc tính của `Ticket` trong các chữ ký này.

Tương tự, một derived method bắt đầu bằng `delete` là thao tác thay đổi dữ liệu. Không đổi `find` thành `delete` như một cách đổi cách diễn đạt mà vẫn kỳ vọng chỉ đọc dữ liệu.

## 4. Văn bản mô tả trong chủ thể không tự tạo điều kiện

Một nhầm lẫn dễ xảy ra:

```java
List<Ticket> findOpenTicketsByQueueCode(String queueCode);
```

Người đọc có thể hiểu thành “tìm ticket đang mở theo hàng đợi”. Nhưng phép tách là:

```text
findOpenTickets | By | QueueCode
```

`OpenTickets` nằm trong phần chủ thể. Với tên này, nó là văn bản mô tả, không tự sinh điều kiện `status = OPEN`.

Trong ví dụ, chữ ký trên không diễn đạt thêm điều kiện trạng thái so với:

```java
List<Ticket> findTicketsByQueueCode(String queueCode);
```

Nếu cần lọc trạng thái, đưa thuộc tính đó vào phần điều kiện:

```java
List<Ticket> findByStatusAndQueueCode(
    TicketStatus status,
    String queueCode
);
```

Sau đó gọi:

```java
List<Ticket> tickets = repository.findByStatusAndQueueCode(
    TicketStatus.OPEN,
    "SUPPORT"
);
```

Điều kiện `OPEN` lúc này được biểu đạt bằng thuộc tính `status` và giá trị truyền vào. Không có bước dịch tự động từ từ tiếng Anh `Open` trong chủ thể sang một giá trị enum.

Cùng nguyên tắc ấy, tên:

```text
findQueueCodeByStatus
```

không tự yêu cầu chỉ chọn cột hay thuộc tính `queueCode`. Văn bản `QueueCode` trước `By` không thay thế cơ chế projection. Nếu cần kết quả projection, phải khai báo kiểu trả về và áp dụng khả năng projection đúng với module.

Một phần mô tả có thể giúp tên rõ nghĩa; nó không phải một ngôn ngữ nghiệp vụ tự do mà parser sẽ hiểu theo ý người viết.

## 5. Một số thành phần trong chủ thể có ý nghĩa đặc biệt

Không phải mọi nội dung trước `By` đều chỉ để mô tả. Những từ khóa như `Distinct`, `Top`, `First` có vai trò riêng khi được đặt theo mẫu được hỗ trợ.

### 5.1. Distinct là một cờ truy vấn

```java
List<Ticket> findDistinctByStatus(TicketStatus status);
```

Cách tách:

```text
findDistinct | By | Status
```

`Distinct` thuộc chủ thể và yêu cầu ngữ nghĩa distinct theo module. `Status` vẫn là phần điều kiện.

Không đọc `Distinct` như một thuộc tính tên `distinct`, cũng không coi nó là lời hứa luôn loại trùng theo một thuộc tính tùy ý. Hiệu quả thực tế còn phụ thuộc truy vấn và dạng kết quả được chọn.

### 5.2. Top hoặc First giới hạn số kết quả

```java
List<Ticket> findTop3ByStatusOrderByCreatedAtDescIdDesc(
    TicketStatus status
);
```

Có thể đọc:

```text
Chủ thể:       findTop3
Điều kiện:     Status
Sắp xếp tĩnh:  CreatedAt giảm dần, rồi id giảm dần
```

Ở đây, `3` là giới hạn tối đa của kết quả; nó không phải một tham số cần truyền cho điều kiện `status`.

Một ví dụ lấy tối đa một kết quả:

```java
Optional<Ticket> findFirstByStatusOrderByCreatedAtAscIdAsc(
    TicketStatus status
);
```

`Optional` trong ví dụ là `java.util.Optional`. Với dạng giới hạn được hỗ trợ, bỏ con số sau `First` hoặc `Top` biểu đạt giới hạn một kết quả.

Nếu nghiệp vụ hỏi ticket “mới nhất” hay “sớm nhất”, cần biểu đạt thứ tự tương ứng. Chỉ giới hạn số lượng không định nghĩa ticket nào đứng đầu.

### 5.3. Đặt từ khóa đúng cấu trúc

Đọc `Top3` hoặc `Distinct` theo ngữ pháp đặt tên được hỗ trợ, không coi chúng là các từ có thể đặt tùy ý ở mọi vị trí.

Ví dụ:

```text
findTop3ByStatus
```

đặt giới hạn trong chủ thể, còn:

```text
findByTop3Status
```

đặt `Top3Status` sang phía predicate. Tên thứ hai không phải cách khác để yêu cầu ba ticket theo trạng thái; trong mô hình đã nêu, nó không chỉ tới một thuộc tính phù hợp.

## 6. Phần sau By cần được đọc tiếp thành cấu trúc

Với:

```text
findByStatusAndQueueCodeOrderByCreatedAtDesc
```

bước tách tại `By` mới chỉ cho ra:

```text
Chủ thể:          find
Phần phía sau:   StatusAndQueueCodeOrderByCreatedAtDesc
```

Sau đó tiếp tục phân tích:

```text
Status
  And
QueueCode

OrderBy
  CreatedAt Desc
```

Trong mô hình đang dùng:

- `Status` và `QueueCode` là hai biểu thức thuộc tính với phép so sánh bằng mặc định.
- `And` kết hợp hai điều kiện.
- `OrderBy` bắt đầu phần sắp xếp tĩnh.
- `CreatedAt` là thuộc tính dùng để sắp xếp; `Desc` là hướng giảm dần.

`OrderBy` không yêu cầu thêm một giá trị `createdAt` để bind. Nếu cần lọc thời điểm, phải có biểu thức điều kiện riêng cho thời điểm đó.

Commons có lớp `PartTree` để biểu diễn thông tin phân tích như các phần điều kiện, sort, cờ count/exists và giới hạn. API này cũng nhận domain class để kiểm tra biểu thức thuộc tính. Xem [API PartTree](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/parser/PartTree.html).

Mô hình tư duy hữu ích là một cấu trúc truy vấn, không phải thao tác lấy tên Java rồi thay vài chữ thành SQL bằng chuỗi.

## 7. Số tham số không bằng số từ sau By

Xét các ví dụ độc lập:

```java
List<Ticket> findByStatusAndQueueCode(
    TicketStatus status,
    String queueCode
);

List<Ticket> findByArchivedFalse();

List<Ticket> findByCreatedAtBetween(
    Instant from,
    Instant to
);

List<Ticket> findByStatusOrderByCreatedAtDesc(
    TicketStatus status
);
```

Với các toán tử được module hỗ trợ:

| Phần predicate | Giá trị nghiệp vụ cần truyền trong ví dụ |
| --- | --- |
| `StatusAndQueueCode` | Hai giá trị: trạng thái và mã hàng đợi. |
| `ArchivedFalse` | Không có giá trị: phép kiểm tra false đã nằm trong tên. |
| `CreatedAtBetween` | Hai giá trị: hai đầu của khoảng. |
| `StatusOrderByCreatedAtDesc` | Một giá trị trạng thái; sort không nhận thêm giá trị. |

`Instant` trong chữ ký là `java.time.Instant`. Không thể đếm các đoạn camel case rồi suy ra số đối số.

Một method còn có thể nhận tham số đặc biệt:

```java
Page<Ticket> findByStatus(
    TicketStatus status,
    Pageable pageable
);
```

Trong chữ ký này, `Page` và `Pageable` thuộc `org.springframework.data.domain`. `Pageable` điều khiển việc lấy kết quả; nó không tương ứng với điều kiện thứ hai sau `Status`.

Vì vậy, khi xem chữ ký, cần đối chiếu cả tên, toán tử, kiểu và vai trò của từng tham số. Bản thân ranh giới `By` không cung cấp toàn bộ thông tin bind.

## 8. Phân tích trọn vẹn một method thực tế

Xét hợp đồng:

```java
List<Ticket> findTop3ByStatusAndQueueCodeOrderByCreatedAtDescIdDesc(
    TicketStatus status,
    String queueCode
);
```

Đọc lần lượt:

1. `find`: đây là truy vấn lấy dữ liệu.
2. `Top3`: yêu cầu tối đa ba kết quả.
3. `By`: kết thúc phần chủ thể.
4. `StatusAndQueueCode`: yêu cầu khớp cả trạng thái lẫn hàng đợi.
5. `OrderByCreatedAtDescIdDesc`: sắp xếp thời điểm giảm dần, rồi định danh giảm dần.
6. `List<Ticket>`: dạng kết quả nhiều ticket, chịu giới hạn đã nêu.

Giả sử dữ liệu cố định như sau; thời điểm cùng ngày, cùng múi giờ:

| id | status | queueCode | createdAt |
| --- | --- | --- | --- |
| 105 | OPEN | SUPPORT | 10:05 |
| 104 | CLOSED | SUPPORT | 10:04 |
| 103 | OPEN | BILLING | 10:03 |
| 102 | OPEN | SUPPORT | 10:02 |
| 101 | OPEN | SUPPORT | 10:01 |
| 100 | OPEN | SUPPORT | 10:00 |

Gọi:

```java
List<Ticket> tickets =
    repository.findTop3ByStatusAndQueueCodeOrderByCreatedAtDescIdDesc(
        TicketStatus.OPEN,
        "SUPPORT"
    );
```

Tập khớp điều kiện gồm 105, 102, 101, 100. Sau sắp xếp và giới hạn, kết quả là 105, 102, 101.

Những quan sát cần tách rõ:

- Ticket 104 bị loại do trạng thái, dù thuộc đúng hàng đợi.
- Ticket 103 bị loại do hàng đợi, dù có đúng trạng thái.
- Ticket 100 thỏa điều kiện nhưng nằm ngoài giới hạn ba kết quả.
- Nếu chỉ có hai ticket phù hợp, kết quả có hai phần tử; `Top3` không tạo thêm dữ liệu.

Nếu thay chủ thể bằng `findOpenTickets` nhưng bỏ `Status` khỏi predicate, ticket đóng có thể tham gia kết quả. Một tên nghe hợp lý về ngôn ngữ tự nhiên vẫn có thể diễn đạt sai ý định nghiệp vụ.

## 9. Hai lần xuất hiện By không có cùng vai trò

Tên:

```text
findByStatusOrderByCreatedAtDesc
```

chứa chữ `By` ở hai vị trí:

```text
find | By | Status OrderBy CreatedAt Desc
       ↑              ↑
  ranh giới      một phần của từ khóa OrderBy
```

Không dùng ý tưởng “cứ gặp chuỗi By là tách thành một query khác”. Trong tên này chỉ có một phần chủ thể; `OrderBy` nằm trong phần còn lại để mô tả sort.

Tương tự:

```java
List<Ticket> findAllByOrderByCreatedAtDescIdDesc();
```

Tên được đọc là:

```text
Chủ thể:        findAll
Điều kiện lọc:  không có
Sắp xếp tĩnh:   createdAt DESC, id DESC
```

Một dạng khác:

```java
List<Ticket> findTop3ByOrderByCreatedAtDescIdDesc();
```

Ở đây có giới hạn ba kết quả và sắp xếp, nhưng không có điều kiện lọc nghiệp vụ. Cụm `ByOrderBy` không phải lỗi chỉ vì hai đoạn `By` đứng gần nhau.

Chi tiết parser phân biệt phần tiền tố, phần predicate và `OrderBy` có thể xem trong [mã nguồn PartTree của Spring Data Commons](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/repository/query/parser/PartTree.java).

### Viết đúng chữ hoa và cấu trúc

Tên derived query dùng các keyword có cách viết cụ thể:

```text
findByStatus
```

Không thay thành:

```text
findbyStatus
```

rồi kỳ vọng tiền tố vẫn được phân tích như cũ. Việc Java cho phép khai báo một tên method không có nghĩa tên ấy diễn đạt được cấu trúc derived query dự định.

## 10. Ngoại lệ quan trọng: chữ ký CRUD đã được dành riêng

Quy tắc đọc derived query không thay thế hợp đồng của những method cơ sở như `findById`.

Giả sử một mô hình khác, `LegacyTicket`, được mapping như sau:

| Thuộc tính | Vai trò |
| --- | --- |
| `pk` kiểu `Long` | Được module nhận diện là định danh kỹ thuật. |
| `id` kiểu `Long` | Một thuộc tính nghiệp vụ thông thường. |

Repository:

```java
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

public interface LegacyTicketRepository
        extends CrudRepository<LegacyTicket, Long> {

    Optional<LegacyTicket> findByPk(Long pk);

    Optional<LegacyTicket> findLegacyTicketById(Long businessId);
}
```

Khi đó:

```java
repository.findById(10L);
```

là lời gọi CRUD cơ sở theo định danh kỹ thuật, tức `pk` trong mapping giả định.

Còn:

```java
repository.findLegacyTicketById(10L);
```

là derived query có văn bản mô tả `LegacyTicket` trong chủ thể, tránh trùng tên dành riêng; phần `Id` được phân giải về thuộc tính nghiệp vụ `id`.

Việc thêm văn bản mô tả ở đây có ích cho việc phân biệt tên method, dù văn bản đó không sinh thêm điều kiện. Những chữ ký dành riêng theo ID còn có `existsById`, `deleteById`; không suy rằng chúng luôn nhắm vào thuộc tính có tên Java đúng bằng `id`.

## 11. Đừng áp quy tắc By cho mọi đường thực thi repository

Trước khi phân tích một tên, xác định method thuộc đường thực thi nào:

| Loại method | Cách đọc phù hợp |
| --- | --- |
| Method CRUD cơ sở | Đọc hợp đồng của repository cơ sở. |
| Query method thực sự được suy từ tên | Áp dụng quy tắc subject, `By`, predicate. |
| Method dùng declared query có hiệu lực | Đọc định nghĩa truy vấn được module chọn. |
| Default method hoặc custom fragment có triển khai | Đọc phần thân hoặc phần triển khai tương ứng. |

Ví dụ `findAll()` được kế thừa từ `CrudRepository` không cần có `By` để hoạt động. Không dùng điều đó làm bằng chứng rằng mọi tên bắt đầu bằng `find` đều có thể bỏ `By`.

Trong mô hình `Ticket` đã nêu, tên tự đặt:

```java
List<Ticket> findTicketsForQueue(String queueCode);
```

không diễn đạt điều kiện `queueCode` theo quy tắc derived query đang học. Parser không tự dịch cụm `ForQueue` sang `ByQueueCode`. Nếu không có khai báo hoặc triển khai phù hợp, tên như vậy có thể không được giải quyết thành truy vấn mong muốn.

Chiến lược query lookup có thể chọn một declared query thay vì suy từ tên. Vì thế, khi điều tra hành vi thực tế, việc thấy một tên “trông như derived query” chưa đủ để kết luận truy vấn đang chạy được tạo từ tên đó.

## 12. Cách tự kiểm tra một tên phương thức

Khi thêm query method, có thể kiểm tra hợp đồng bằng chuỗi câu hỏi sau:

1. Method có thực sự dùng name derivation hay được xử lý bởi một đường khác?
2. Tiền tố mở đầu có phù hợp với loại thao tác mong muốn không?
3. Ranh giới `By` nằm ở đâu?
4. Văn bản trước ranh giới chỉ để mô tả hay có keyword đặc biệt?
5. Các thuộc tính sau ranh giới có tồn tại trong domain model không?
6. `OrderBy` đã được tách khỏi điều kiện lọc chưa?
7. Số và kiểu tham số nghiệp vụ có khớp các toán tử không?
8. Kiểu kết quả và những tham số đặc biệt có được module hỗ trợ không?

Các lỗi có biểu hiện khác nhau:

| Biểu hiện | Hướng xem xét |
| --- | --- |
| Không phân giải được thuộc tính | Kiểm tra predicate, chính tả thuộc tính và mapping mô hình. |
| Query chạy nhưng thiếu điều kiện | Kiểm tra điều kiện có bị đặt vào phần mô tả trước `By` không. |
| Số đối số không khớp | Tách toán tử điều kiện, sort và tham số đặc biệt trước khi đếm. |
| Tìm nhầm ID | Kiểm tra chữ ký dành riêng và thuộc tính được mapping làm identifier. |
| Đổi phần mô tả nhưng kết quả không đổi | Xác định phần vừa đổi có thực sự tham gia điều kiện hay không. |

Không phải mọi sai lệch đều gây lỗi khi tạo repository. `findOpenTicketsByQueueCode` có thể là một derived query hợp lệ nhưng thiếu điều kiện trạng thái mà người viết mong muốn. Vì vậy, đọc đúng ngữ pháp chỉ là một phần; cần đối chiếu cả ý định nghiệp vụ.

## 13. Thực hành tách tên

Với mô hình `Ticket` của bài, hãy tự đánh dấu chủ thể, điều kiện và sort trước khi đọc bảng giải thích:

| Tên method | Chủ thể | Điều kiện | Sắp xếp tĩnh |
| --- | --- | --- | --- |
| `findTicketsByStatus` | `findTickets` | `status` bằng giá trị truyền vào. | Không có. |
| `countByQueueCode` | `count` | `queueCode` bằng giá trị truyền vào. | Không có. |
| `existsByStatusAndQueueCode` | `exists` | Cả trạng thái và hàng đợi cùng khớp. | Không có. |
| `findTop3ByStatusOrderByCreatedAtDescIdDesc` | `findTop3` | Trạng thái khớp. | `createdAt DESC, id DESC`. |
| `findOpenTicketsByQueueCode` | `findOpenTickets` | Chỉ mã hàng đợi khớp. | Không có. |
| `findAllByOrderByCreatedAtDesc` | `findAll` | Không có điều kiện lọc. | `createdAt DESC`. |

Cuối cùng, đối chiếu hai yêu cầu:

**Yêu cầu A:** lấy ticket của hàng đợi `SUPPORT`, không ràng buộc trạng thái.

```java
List<Ticket> findTicketsByQueueCode(String queueCode);
```

**Yêu cầu B:** chỉ lấy ticket đang mở của hàng đợi `SUPPORT`.

```java
List<Ticket> findByStatusAndQueueCode(
    TicketStatus status,
    String queueCode
);
```

Với B, phía gọi truyền `TicketStatus.OPEN`. Sự khác biệt nghiệp vụ được đặt trong predicate và giá trị tham số, nên có thể đọc và kiểm chứng trực tiếp từ hợp đồng repository.

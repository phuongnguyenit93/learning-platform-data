# Sequence, kích thước cấp phát và nguy cơ lệch cấu hình với cơ sở dữ liệu trong Hibernate

Khi một entity được lưu, Hibernate cần xác định **khóa chính** để phân biệt entity ấy với các entity khác. Với cơ sở dữ liệu quan hệ hỗ trợ **sequence**, Hibernate có thể xin giá trị từ sequence trước khi thực hiện câu lệnh `INSERT`, hoặc xin một giá trị để cấp phát cả **dải ID** cho nhiều entity. Cách thứ hai giảm số lần phải gọi cơ sở dữ liệu, nhưng đòi hỏi cấu hình phía Hibernate và cấu hình sequence phía database tương thích.

Một lỗi dễ gặp khi triển khai ứng dụng là đặt:

```java
@SequenceGenerator(
    name = "order_id_generator",
    sequenceName = "purchase_order_id_seq",
    allocationSize = 50
)
```

trong khi database lại có:

```sql
CREATE SEQUENCE purchase_order_id_seq
    START WITH 1
    INCREMENT BY 1;
```

Hai con số `50` và `1` **không mô tả cùng một cách cấp phát**. Với optimizer dạng pooled, sự khác biệt có thể làm Hibernate từ chối khởi động khi kiểm tra schema, hoặc trong cấu hình không kiểm tra đầy đủ có thể khiến các dải ID bị chồng lấn, gây lỗi trùng khóa chính khi ghi dữ liệu.

Bài học giải thích sequence vận hành như thế nào; ý nghĩa của `allocationSize`, `INCREMENT BY` và `CACHE`; các chiến lược tối ưu cấp phát; cũng như cách thiết kế và thay đổi cấu hình một cách nhất quán.

## 1. Sequence là gì và Hibernate sử dụng nó để làm gì?

**Database sequence** là đối tượng do hệ quản trị cơ sở dữ liệu quản lý nhằm cấp các giá trị số, thường dùng làm khóa chính. Nó độc lập với bảng: nhiều câu lệnh hoặc nhiều kết nối có thể cùng xin giá trị từ một sequence mà không phải đọc `MAX(id)` từ bảng.

Ví dụ với PostgreSQL:

```sql
CREATE SEQUENCE purchase_order_id_seq
    START WITH 1
    INCREMENT BY 1;

SELECT nextval('purchase_order_id_seq'); -- 1
SELECT nextval('purchase_order_id_seq'); -- 2
SELECT nextval('purchase_order_id_seq'); -- 3
```

`nextval(...)` là thao tác **tiêu thụ giá trị sequence**: mỗi lời gọi tiến sequence theo quy tắc đã định. Đây không phải một cách kiểm tra trạng thái vô hại; ngay cả trong buổi thực hành, gọi thêm `nextval` cũng làm thay đổi các giá trị cấp phát tiếp theo.

Khi dùng `GenerationType.SEQUENCE`, Hibernate có thể lấy số từ sequence rồi gán cho khóa chính của entity. Do Hibernate đã có ID, nó có thể đưa ID vào câu lệnh `INSERT`:

```text
Java:
  new PurchaseOrder()
          |
          v
  persist(order)
          |
          v
Hibernate:
  lấy/cấp phát ID từ sequence
          |
          v
  order.id = <giá trị đã cấp>
          |
          v
  INSERT INTO purchase_orders(id, ...)
          |
          v
Database:
  lưu hàng với khóa chính đó
```

Thời điểm thực hiện `INSERT` còn phụ thuộc flush, transaction và hành vi của provider. Việc entity đã có ID **không đồng nghĩa** transaction đã commit hoặc hàng dữ liệu đã tồn tại với trạng thái được commit.

### Sequence khác `IDENTITY` thế nào?

| Đặc điểm | `SEQUENCE` | `IDENTITY` |
|---|---|---|
| Nguồn sinh khóa | Sequence riêng của database | Cơ chế auto-increment/identity gắn với cột |
| Hibernate có thể biết ID trước `INSERT`? | Có, nhờ lấy hoặc cấp phát từ sequence | Thường cần thực hiện insert để lấy ID do DB sinh |
| Có thể cấp phát cả dải ID phía Hibernate? | Có, nếu dùng optimizer phù hợp | Không theo cơ chế sequence pooling này |
| Khả năng gom JDBC insert batch | Thường thuận lợi hơn | Phụ thuộc cách Hibernate lấy khóa; `IDENTITY` thường hạn chế batching insert |
| Phụ thuộc database | Cần DB/dialect hỗ trợ sequence | Cần DB/dialect hỗ trợ identity |

Không phải database nào cũng hỗ trợ sequence giống nhau. Hibernate dialect quyết định những thao tác sequence có thể thực hiện. Phần SQL minh họa trong bài chủ yếu dùng PostgreSQL; với Oracle, SQL Server hay các hệ quản trị khác cần đối chiếu cú pháp tương ứng.

## 2. Ánh xạ sequence bằng Jakarta Persistence

Một entity sử dụng `@Id`, `@GeneratedValue` và `@SequenceGenerator`:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_id_generator"
    )
    @SequenceGenerator(
        name = "purchase_order_id_generator",
        sequenceName = "purchase_order_id_seq",
        allocationSize = 50
    )
    private Long id;

    private String referenceCode;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String referenceCode) {
        this.referenceCode = referenceCode;
    }

    public Long getId() {
        return id;
    }
}
```

Ý nghĩa các thuộc tính quan trọng:

- `@Id`: thuộc tính định danh entity.
- `strategy = GenerationType.SEQUENCE`: yêu cầu dùng chiến lược sequence.
- `generator` trong `@GeneratedValue`: tham chiếu đến tên **generator logic** đã khai báo.
- `name` trong `@SequenceGenerator`: tên **generator logic** ở tầng persistence; nó không nhất thiết là tên đối tượng trong database.
- `sequenceName`: tên sequence vật lý mà generator sử dụng.
- `allocationSize`: số ID Hibernate dự kiến cấp phát trong một lần lấy một giá trị nguồn theo chiến lược cấp phát tương ứng.

Trong khai báo `@SequenceGenerator` theo Jakarta Persistence, giá trị mặc định của `allocationSize` là **50**. Vì vậy, bỏ thuộc tính này **không đồng nghĩa** cấp phát từng ID một. Nếu dự án cần dùng giá trị khác, hãy chỉ rõ thay vì dựa vào mặc định.

Ví dụ mức ánh xạ đơn giản nhất, cấp phát từng giá trị:

```java
@SequenceGenerator(
    name = "purchase_order_id_generator",
    sequenceName = "purchase_order_id_seq",
    allocationSize = 1
)
```

Cách này thường dễ hiểu khi học và khi tích hợp với một sequence hiện hữu có `INCREMENT BY 1`. Đổi lại, số lượt yêu cầu sequence qua JDBC có thể tăng khi chèn nhiều entity.

### `initialValue` dùng để làm gì?

`@SequenceGenerator` còn có thuộc tính `initialValue`, biểu thị giá trị khởi đầu khi tạo sequence theo metadata ánh xạ. Ví dụ:

```java
@SequenceGenerator(
    name = "purchase_order_id_generator",
    sequenceName = "purchase_order_id_seq",
    initialValue = 1,
    allocationSize = 50
)
```

**Không nên hiểu** `initialValue = 1` là câu lệnh đặt lại sequence đang có dữ liệu mỗi lần ứng dụng chạy. Khi schema được quản lý bằng migration, đối tượng sequence đã tồn tại trong database và trạng thái hiện tại của nó mới quyết định giá trị được cấp tiếp theo. Việc chỉnh annotation không tự động sửa an toàn một sequence production đã có dữ liệu.

## 3. Ba tham số dễ nhầm: `allocationSize`, `INCREMENT BY` và `CACHE`

Ba thông số đều liên quan đến hiệu năng hoặc cách sequence phát số, nhưng hoạt động ở **những lớp khác nhau**.

| Thông số | Định nghĩa | Thuộc lớp | Điều gì thay đổi? |
|---|---|---|---|
| `allocationSize` | Số ID Hibernate dự kiến sử dụng từ một lần lấy giá trị nguồn theo generator/optimizer | Mapping Hibernate/JPA | Cách Hibernate cấp ID cho entity |
| `INCREMENT BY` | Bước nhảy của giá trị sequence mỗi lần gọi hàm sinh giá trị | Database sequence | Các giá trị trực tiếp nhận từ sequence |
| `CACHE` | Số giá trị sequence mà database có thể dự trữ nội bộ để giảm chi phí quản lý sequence | Database sequence | Cách DB tối ưu việc phát giá trị sequence |

Ví dụ:

```sql
CREATE SEQUENCE purchase_order_id_seq
    START WITH 1
    INCREMENT BY 50
    CACHE 20;
```

Ở đây:

- Lời gọi trực tiếp đến sequence nhận lần lượt `1`, `51`, `101`, `151`, … nếu không có lời gọi khác xen vào.
- `INCREMENT BY 50` xác định **bước nhảy** giữa các giá trị mà database phát ra.
- `CACHE 20` là cơ chế database có thể giữ trước các giá trị sequence để phát nhanh hơn. Nó **không có nghĩa** Hibernate nhận 20 ID mỗi lần gọi.
- Nếu Hibernate dùng optimizer tương thích với việc phân bổ dải 50 ID, một lần xin giá trị nguồn có thể phục vụ nhiều lần `persist` tiếp theo.

**Điểm then chốt:** `CACHE 50` không thay thế cho `INCREMENT BY 50`. Một sequence có `INCREMENT BY 1 CACHE 50` vẫn phát các giá trị trực tiếp tăng `1, 2, 3, ...` theo bước 1; nó không tự bảo đảm an toàn cho Hibernate pooled generator cấp phát 50 ID mỗi dải.

### Bảng ba cấu hình minh họa

| Hibernate | Database sequence | Nhận xét |
|---|---|---|
| `allocationSize = 1` | `INCREMENT BY 1` | Cấu hình cơ bản dễ hiểu; mỗi giá trị nguồn thường dùng cho một ID |
| `allocationSize = 50` với pooled optimizer | `INCREMENT BY 50` | Cấu hình pool tương thích khi mọi thành phần liên quan dùng cùng quy ước |
| `allocationSize = 50` với pooled optimizer | `INCREMENT BY 1` | Sai lệch cần xử lý; có thể bị validation báo lỗi hoặc cấp dải trùng |

Các hàng trên áp dụng cho **nhóm optimizer dạng pooled** cần database sequence có bước nhảy tương ứng. Hibernate có các optimizer khác với cách diễn giải giá trị nguồn khác nhau; không thể suy ra yêu cầu chính xác của mọi optimizer chỉ từ tên `allocationSize`.

## 4. Cơ chế cấp phát từng ID so với cấp phát theo dải

### 4.1. Không pooling: một giá trị sequence cho một ID

Cấu hình điển hình:

```java
@SequenceGenerator(
    name = "order_seq",
    sequenceName = "purchase_order_id_seq",
    allocationSize = 1
)
```

Database:

```sql
CREATE SEQUENCE purchase_order_id_seq
    START WITH 1
    INCREMENT BY 1;
```

Luồng đơn giản:

```text
persist(order A) -> nextval(...) = 1 -> ID 1
persist(order B) -> nextval(...) = 2 -> ID 2
persist(order C) -> nextval(...) = 3 -> ID 3
```

Ở mô hình này, để cấp ID cho 1.000 entity mới, Hibernate có thể phải yêu cầu sequence khoảng 1.000 lần. Chi phí đi lại qua JDBC/database có thể đáng kể khi tạo số lượng lớn entity, dù `CACHE` của database đã tối ưu công việc bên trong database.

### 4.2. Pooling: cấp phát nhiều ID từ một giá trị nguồn

Mục tiêu của pooling là:

> Một lần yêu cầu sequence từ database cho phép Hibernate cấp ID cho **nhiều entity**, giảm số lượt gọi sequence.

Với kích thước dải 50, mỗi lần lấy giá trị nguồn Hibernate có thể dùng dải 50 ID cho các entity mới trong phạm vi generator của nó. Khi dải hết, Hibernate xin giá trị nguồn tiếp theo.

Sơ đồ ý tưởng:

```text
Database sequence
        |
        | nextval
        v
+--------------------------+
| Hibernate ID optimizer   |
|  dải ID đã được cấp      |
|                          |
|  lấy ID cho entity A     |
|  lấy ID cho entity B     |
|  ...                     |
|  lấy ID cho entity cuối  |
+------------+-------------+
             |
     dải ID cạn
             |
             v
    yêu cầu nextval mới
```

Khi không có dải dự trữ, các lời gọi sinh ID phát sinh yêu cầu DB. Khi dải còn giá trị, Hibernate cấp ID từ bộ nhớ của generator mà không phải thực hiện một yêu cầu sequence mới cho từng entity.

Điểm khác biệt này giúp giảm overhead của thao tác sinh khóa, đặc biệt khi insert nhiều bản ghi.

### 4.3. Pooled và pooled-lo

Hibernate có nhiều **optimizer** dành cho identifier generator. Hai optimizer phổ biến:

- **`pooled`**: giá trị lấy từ sequence được hiểu theo một quy ước về **giới hạn phía trên** của dải ID. Cách xử lý giá trị đầu và các dải kế tiếp tuân theo quy tắc của optimizer.
- **`pooled-lo`**: giá trị lấy từ sequence được hiểu như **giới hạn phía dưới** của dải ID. Với kích thước 50, giá trị nguồn `1` có thể đại diện dải `1..50`, giá trị nguồn `51` đại diện dải `51..100`.

Minh họa riêng cho **pooled-lo**, giả định sequence bắt đầu ở 1, bước nhảy 50, không có tiến trình khác tiêu thụ sequence:

| Lần lấy từ database | Giá trị `nextval` | Dải ID do optimizer pooled-lo sử dụng |
|---|---:|---|
| 1 | 1 | 1–50 |
| 2 | 51 | 51–100 |
| 3 | 101 | 101–150 |

Với `pooled`, cách tính dải từ giá trị nguồn **khác** `pooled-lo`; không nên áp bảng trên vào `pooled`. Hibernate có thể lựa chọn optimizer dựa trên cấu hình và phiên bản; `@SequenceGenerator(allocationSize = 50)` tự nó không mô tả đầy đủ mọi chi tiết về dải đầu tiên.

Tuy khác cách diễn giải đầu mút, khi dùng cơ chế pooled chuẩn, **bước tăng của sequence phía database phải tương thích với kích thước phân bổ** mà optimizer kỳ vọng.

### 4.4. Hi/lo trong lịch sử Hibernate

Một cách tiếp cận khác là thuật toán *hi/lo*: dùng giá trị từ database làm phần `hi`, còn giá trị `lo` được tăng trong bộ nhớ để tạo nhiều ID. Tùy optimizer, database sequence có thể tăng từng đơn vị trong khi Hibernate cấp nhiều ID.

Vì vậy, quy tắc “`INCREMENT BY` luôn bằng `allocationSize`” **không phải định luật áp dụng cho tất cả generator trong mọi version**. Nó là kỳ vọng của các cơ chế pooled hiện đại thường gặp. Khi đọc hệ thống cũ hoặc cấu hình `hilo`, cần xác định **generator và optimizer thực tế**, thay vì đổi sequence chỉ dựa vào một annotation.

## 5. Ví dụ cấu hình nhất quán với PostgreSQL

Giả sử ứng dụng mới dùng Hibernate với sequence cấp phát theo dải 50.

### 5.1. Tạo schema bằng migration

Ví dụ SQL dành cho PostgreSQL, áp dụng với **database mới**:

```sql
CREATE SEQUENCE purchase_order_id_seq
    START WITH 1
    INCREMENT BY 50
    MINVALUE 1
    NO CYCLE
    CACHE 20;

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    reference_code VARCHAR(80) NOT NULL UNIQUE
);
```

Trong ví dụ này, khóa chính được Hibernate tạo trước rồi đưa vào `INSERT`, nên cột `id` không bắt buộc phải có `DEFAULT nextval(...)`. Nếu còn một ứng dụng khác chèn dữ liệu trực tiếp, cần quy định rõ cách ứng dụng đó dùng sequence để không phá vỡ chiến lược cấp phát toàn hệ thống.

`NO CYCLE` thể hiện mục tiêu không quay lại giá trị cũ khi sequence đạt giới hạn. Nếu sequence được cấu hình `CYCLE` mà dữ liệu cũ còn tồn tại, việc dùng lại ID có thể xung đột với primary key.

### 5.2. Ánh xạ entity

```java
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_generator"
    )
    @SequenceGenerator(
        name = "purchase_order_generator",
        sequenceName = "purchase_order_id_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(name = "reference_code", nullable = false, length = 80)
    private String referenceCode;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String referenceCode) {
        this.referenceCode = referenceCode;
    }

    public Long getId() {
        return id;
    }
}
```

Nếu Hibernate dùng optimizer pooled thông dụng, sequence có `INCREMENT BY 50` tương ứng với `allocationSize = 50`. Cần kiểm tra cấu hình thực tế của Hibernate version đang dùng, đặc biệt nếu dự án có custom identifier generator hoặc cấu hình optimizer riêng.

### 5.3. Sử dụng trong một transaction

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;

public void createOrders(EntityManager em) {
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        for (int i = 1; i <= 100; i++) {
            PurchaseOrder order = new PurchaseOrder("PO-" + i);
            em.persist(order);
        }

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
```

Đoạn mã giả định `EntityManager` có cấu hình **resource-local transaction**. Nếu sử dụng JTA hoặc Spring `@Transactional`, transaction thường do môi trường quản lý và code không gọi `getTransaction()` theo cách này.

Với dải cấp phát 50, việc tạo 100 entity có thể cần số lượt xin sequence ít hơn nhiều so với khi cấp một ID mỗi lần. Số lần truy cập chính xác và thời điểm xin giá trị phụ thuộc optimizer, giá trị dải đang được giữ từ trước và cách Hibernate thực thi.

## 6. Vì sao `allocationSize = 50` nhưng database `INCREMENT BY 1` nguy hiểm?

Đây là lỗi nền tảng cần hiểu rõ.

Giả sử optimizer **pooled-lo** được cấu hình để cấp 50 ID, nhưng database sequence vẫn tăng một đơn vị.

```text
Hibernate: allocationSize = 50
Database:  INCREMENT BY 1

Lần 1: nextval = 1
  => Hibernate cho rằng có thể sử dụng dải [1..50]

Lần 2: nextval = 2
  => Hibernate cho rằng có thể sử dụng dải [2..51]
                                         ^^^^^
                            Hai dải chồng lấn rất lớn
```

Đây là minh họa cách sai lệch có thể gây ra **trùng ID**, dù database không bao giờ trả hai giá trị `nextval` giống nhau. Lỗi không nằm ở tính duy nhất của giá trị sequence nguồn; lỗi nằm ở việc ứng dụng **mở rộng giá trị nguồn thành dải ID theo quy tắc không phù hợp với bước tăng thực tế**.

Với hai tiến trình ứng dụng hoặc hai Hibernate `SessionFactory` cùng sinh ID từ một sequence:

```text
App A lấy giá trị nguồn 1 -> tin rằng giữ dải 1..50
App B lấy giá trị nguồn 2 -> tin rằng giữ dải 2..51

App A có thể cấp ID 2
App B cũng có thể cấp ID 2
-> Một trong hai INSERT có thể thất bại vì vi phạm PRIMARY KEY
```

Ví dụ giả định `pooled-lo`; cách tính của `pooled` khác nhưng **bản chất rủi ro chồng dải vẫn tồn tại** nếu cấu hình không tương thích.

### Hibernate có thể báo lỗi trước khi INSERT

Ở các cấu hình và phiên bản Hibernate có cơ chế kiểm tra increment của sequence, framework có thể phát hiện sequence trong DB có increment là 1 nhưng mapping kỳ vọng 50. Khi bật schema validation, hệ thống có thể lỗi khi khởi động hoặc khi khởi tạo generator, thay vì đợi đến lỗi trùng ID khi ghi dữ liệu.

Thông điệp có thể nêu sequence thực tế `increment-size = 1` và giá trị kỳ vọng `50`. Loại exception và thời điểm báo lỗi phụ thuộc phiên bản, cách bootstrap và cấu hình mismatch strategy.

**Không nên coi việc ứng dụng khởi động được là bằng chứng rằng cấu hình an toàn**. Có môi trường không bật validation, có generator không dùng pooled hoặc có cấu hình đặc biệt làm hành vi khác đi. Vẫn phải đối chiếu mapping, optimizer và database sequence thực tế.

## 7. Nếu dùng `allocationSize = 1` nhưng database `INCREMENT BY 50` thì sao?

Đây là tình huống ngược lại:

```text
Hibernate cấp một ID từ mỗi lần nextval.
Database sequence trả 1, 51, 101, 151, ...
-> Các ID mới có khoảng cách lớn.
```

Nếu mỗi giá trị sequence nguồn chỉ được dùng đúng một lần, sự khác biệt này thường không tạo chồng dải theo cơ chế đơn giản đó, nhưng **gây các khoảng trống lớn và có thể bị bước validation phát hiện**. Không nên coi đây là cấu hình mục tiêu chỉ vì chưa thấy duplicate key.

Nếu hệ thống còn nhiều ứng dụng sử dụng cùng sequence với các optimizer khác nhau, phân tích sẽ phức tạp hơn. Phải bảo đảm tất cả thành phần cấp ID hiểu đúng ranh giới dải và không dùng lại giá trị thuộc dải đã cấp cho thành phần khác.

### Một sequence dùng chung bởi nhiều ứng dụng

Một sequence là đối tượng chung của database, trong khi mỗi ứng dụng có thể có mã và cấu hình Hibernate riêng.

Rủi ro tăng nếu:

- Một service dùng `allocationSize = 50`, service khác dùng `allocationSize = 1` nhưng cùng một sequence.
- Bản triển khai mới đổi optimizer trong khi bản cũ vẫn chạy.
- Script nhập dữ liệu tự tạo ID theo công thức riêng.
- Tác vụ migration reset hoặc `RESTART` sequence trong lúc ứng dụng đang ghi.
- Nhiều entity/generator dùng chung sequence nhưng giả định các cách chia dải khác nhau.

Cách an toàn là thống nhất **một hợp đồng sinh ID trên toàn bộ các producer** sử dụng sequence đó, bao gồm hệ thống chạy song song, job nền và script vận hành.

## 8. Khoảng trống ID không có nghĩa dữ liệu bị mất

Một sequence thường được thiết kế để cấp giá trị **không trùng trong phạm vi quy tắc vận hành**, chứ không bảo đảm các ID của bản ghi đã commit là một dãy số liên tục.

### 8.1. Rollback không trả ID về sequence

Ví dụ:

```text
Transaction A:
  lấy ID 101
  INSERT vào bảng
  ROLLBACK

Transaction B:
  lấy ID 102 hoặc một ID từ dải khác
  INSERT
  COMMIT
```

ID 101 có thể không xuất hiện trong bảng. Đây là hành vi bình thường vì các hệ quản trị thường không rollback trạng thái phát số của sequence theo cùng cách rollback dữ liệu hàng. Nếu sequence tự động lùi khi transaction rollback, việc cấp khóa đồng thời giữa nhiều transaction sẽ khó bảo đảm không trùng và làm giảm hiệu năng.

### 8.2. Pool cấp phát nhưng chưa dùng hết

Giả sử Hibernate đã dự trữ một dải 50 ID, mới dùng 12 ID rồi tiến trình ứng dụng kết thúc. Các giá trị còn lại trong dải đó có thể **không bao giờ được ghi thành hàng**.

```text
Dải được cấp: 1..50
Đã dùng:       1..12
Ứng dụng tắt:  13..50 có thể bỏ trống
Dải sau:       có thể bắt đầu ở mốc khác theo optimizer
```

Điều này không đồng nghĩa generator sai hay mất bản ghi. Nó là đánh đổi của việc dự trữ dải để giảm round-trip tới DB.

### 8.3. Database `CACHE` cũng có thể tạo lỗ hổng

Database có thể dự trữ trước giá trị sequence. Nếu database restart hoặc failover trước khi dùng hết cache, một số giá trị chưa sử dụng có thể bị bỏ qua, tùy hệ quản trị và cấu hình.

**Kết luận:** ID kỹ thuật nên dùng để định danh và tham chiếu; **không nên dùng để suy ra số lượng đơn hàng, thứ tự commit tuyệt đối hoặc số chứng từ không được phép thiếu số**.

Nếu nghiệp vụ cần số hóa đơn liên tục theo quy định, hãy thiết kế một cơ chế cấp số nghiệp vụ riêng có transaction và quy tắc tương ứng. Không nên ép primary key từ sequence phải “không có khoảng trống”.

## 9. `allocationSize` và hiệu năng khi chèn số lượng lớn

Một trong các lý do quan trọng để dùng optimizer pooled là giảm lượt truy cập database để xin ID.

Giả sử cần tạo `N = 10.000` entity mới và dải cấp phát `A = 50`.

Với một generator mới chưa có ID dự trữ, số lượt yêu cầu giá trị nguồn có thể vào cỡ:

```text
allocationSize = 1:
  xấp xỉ 10.000 lần lấy sequence

allocationSize = 50, pooled:
  xấp xỉ 10.000 / 50 = 200 lần lấy sequence
```

Đây là phép tính về **số lần lấy sequence**, không phải số câu `INSERT`. Thời điểm request, dải còn lại và chi tiết thuật toán có thể làm số thực tế khác.

Hibernate vẫn phải insert 10.000 hàng nếu có 10.000 entity được lưu. Nhưng biết trước ID thường giúp Hibernate thuận lợi hơn khi **batch JDBC insert** so với một số chiến lược cần chờ DB trả ID sau insert.

### Cấp ID nhanh không tự động làm `INSERT` nhanh

Hiệu năng insert còn phụ thuộc:

- Batching JDBC có được bật không và batch size bao nhiêu.
- Flush và quản lý persistence context.
- Network latency tới DB.
- Index, constraint, trigger và quy tắc khóa trên bảng.
- Cấu hình connection pool và khả năng xử lý đồng thời.
- Số hàng được quản lý trong một Session.

Ví dụ hai thông số dễ bị nhầm:

```properties
hibernate.jdbc.batch_size=50
```

và:

```java
@SequenceGenerator(
    name = "order_seq",
    sequenceName = "purchase_order_id_seq",
    allocationSize = 50
)
```

**`hibernate.jdbc.batch_size`** điều chỉnh batch các thao tác JDBC đủ điều kiện; **`allocationSize`** điều chỉnh cách sinh identifier. Cả hai có thể có giá trị 50 nhưng **không phải cùng một cơ chế** và không cần luôn đặt bằng nhau.

### Chọn kích thước cấp phát thế nào?

- Ứng dụng nhỏ, ít insert hoặc ưu tiên dễ hiểu: `allocationSize = 1` thường đơn giản.
- Ứng dụng insert nhiều hoặc có latency giữa app và DB: cân nhắc allocation lớn hơn, dùng pooled optimizer.
- Ứng dụng thường xuyên restart hoặc có nhiều instance: allocation lớn tăng khả năng bỏ trống ID đã dự trữ khi tiến trình kết thúc.
- Hệ thống nhiều producer dùng chung sequence: ưu tiên cấu hình thống nhất và tính an toàn; không tối ưu chỉ ở một service riêng lẻ.

Không có con số “tốt nhất cho mọi dự án”. Bắt đầu từ nhu cầu throughput và giới hạn quản lý, đo chi phí thực tế rồi chọn dải phù hợp.

## 10. Làm thế nào biết cấu hình sequence hiện tại?

Có ba nguồn thông tin cần đối chiếu:

1. **Metadata entity/generator trong mã Java hoặc cấu hình Hibernate:** `sequenceName`, `allocationSize`, strategy và optimizer thực tế.
2. **Đối tượng sequence hiện hữu trong database:** tên/schema, `INCREMENT BY`, `MINVALUE`, `MAXVALUE`, `CYCLE`, `CACHE` và trạng thái hiện tại.
3. **Cách ứng dụng bootstrap Hibernate:** phiên bản, dialect, cấu hình generator và schema validation/mismatch behavior.

### Xem sequence trong PostgreSQL mà không tiêu thụ giá trị

Ví dụ:

```sql
SELECT
    schemaname,
    sequencename,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle,
    cache_size
FROM pg_sequences
WHERE sequencename = 'purchase_order_id_seq';
```

Truy vấn này đọc metadata và không gọi `nextval`. Trong thực tế, nếu nhiều schema có sequence trùng tên, phải lọc cả `schemaname`.

Có thể xem khóa chính hiện có:

```sql
SELECT MAX(id) AS largest_existing_id
FROM purchase_orders;
```

Tuy nhiên, **`MAX(id)` không chứng minh được giá trị tiếp theo của sequence là bao nhiêu**. Sequence có thể đã dự trữ các dải chưa dùng, có concurrent transaction, hoặc có cache chưa tiêu thụ. Tương tự, trạng thái `last_value` có thể phản ánh cache/reservation, không nhất thiết là ID cuối cùng đã insert.

Khi điều tra lỗi, phải đặt các số này trong bối cảnh các generator còn sống và transaction đồng thời.

### Không dùng `nextval` chỉ để “kiểm tra”

```sql
-- Không phải thao tác kiểm tra trạng thái thuần đọc:
SELECT nextval('purchase_order_id_seq');
```

Lời gọi trên làm sequence tiến tới giá trị mới. Nếu chạy nhiều lần trong môi trường vận hành, bạn đang **tiêu thụ** các giá trị có thể dùng sau đó. Để xem cấu hình, dùng catalog/database metadata thích hợp.

### Xem log SQL

Để nhận biết có pooling hay không, có thể quan sát tần suất SQL xin giá trị sequence so với số lần persist entity. Ví dụ trên PostgreSQL, Hibernate thường dùng lệnh tương đương `select nextval('...')`; dạng SQL và cách logging tùy version/dialect.

Nếu Hibernate lấy sequence gần như một lần cho mỗi entity trong một use case lớn, có thể đang chạy generator không pooling hoặc pool được cấu hình khác dự kiến. Nếu chỉ có một số ít lời gọi sequence cho hàng trăm entity, pooling có thể đang hoạt động.

Không nên dựa riêng vào số lượng log để xác định an toàn: cần đọc metadata và cấu hình database.

## 11. Sai lệch được biểu hiện bằng những lỗi nào?

| Triệu chứng | Nguyên nhân cần xem xét | Hướng điều tra |
|---|---|---|
| Ứng dụng không khởi động, báo increment mismatch | Mapping `allocationSize` khác bước tăng sequence với optimizer yêu cầu tương ứng | Đối chiếu annotation, generator và `INCREMENT BY` |
| `Duplicate key` khi chèn entity | Dải ID chồng lấn; sequence bị reset; nhiều producer dùng quy tắc khác | Kiểm tra cấu hình tất cả producer và lịch sử migration |
| ID nhảy xa hoặc thiếu nhiều số | Pool chưa dùng hết, rollback, restart, DB cache, producer khác | Phân biệt khoảng trống bình thường với lỗi chồng dải |
| Hibernate liên tục xin giá trị sequence | Không pooling, `allocationSize = 1`, hoặc generator/optimizer không như mong đợi | Kiểm tra mapping, SQL log và version |
| Lỗi “sequence does not exist” | Sai tên sequence, schema, quyền DB hoặc naming strategy | Kiểm tra tên vật lý, schema và quyền truy cập |
| Bản cũ chạy được, bản mới báo lỗi | Thay đổi version Hibernate, naming strategy, optimizer/mismatch validation | Đọc migration guide và schema metadata |
| Sau khi import dữ liệu, insert mới bị trùng ID | ID thủ công lớn hơn trạng thái cấp phát an toàn của sequence | Lập kế hoạch đồng bộ sequence có kiểm soát |

### Lỗi trùng khóa không phải lúc nào do sequence

Cũng cần xem liệu ứng dụng có tự gán ID cho entity lẽ ra được sinh tự động, dữ liệu migration bị trùng, bảng có trigger ghi ID, hoặc logic insert/upsert sai. Sequence mismatch là **một nguyên nhân có khả năng gây lỗi**, không phải lời giải thích duy nhất cho mọi `Duplicate key`.

## 12. Xử lý sequence khi database đã tồn tại

Có hai hướng cấu hình cơ bản. Chọn theo nhu cầu nghiệp vụ và cách dữ liệu đang được ghi.

### Hướng A: giữ sequence `INCREMENT BY 1`, giảm `allocationSize` về 1

Nếu hệ thống đã có sequence tăng một đơn vị và lượng insert không lớn, có thể dùng:

```java
@SequenceGenerator(
    name = "purchase_order_generator",
    sequenceName = "purchase_order_id_seq",
    allocationSize = 1
)
```

Database:

```sql
-- Thể hiện cấu hình đích:
-- purchase_order_id_seq INCREMENT BY 1
```

Ưu điểm là quy tắc đơn giản và không yêu cầu đổi bước tăng sequence chỉ để sử dụng pooling. Hạn chế là phải lấy sequence thường xuyên hơn.

Nếu ứng dụng vẫn đang chạy phiên bản trước sử dụng pooled generator thì không thể chỉ đổi một instance rồi coi như hoàn tất: phải xem xét các dải còn được giữ bởi instance khác và cách triển khai đồng thời.

### Hướng B: giữ `allocationSize = 50`, dùng database sequence `INCREMENT BY 50`

Nếu muốn tối ưu cấp phát theo dải, cấu hình phải tương thích:

```java
@SequenceGenerator(
    name = "purchase_order_generator",
    sequenceName = "purchase_order_id_seq",
    allocationSize = 50
)
```

Một migration PostgreSQL có thể cần thao tác dạng:

```sql
ALTER SEQUENCE purchase_order_id_seq
    INCREMENT BY 50;
```

**Đây chỉ là cú pháp minh họa cho việc đổi bước tăng**, không phải quy trình migration đầy đủ để chạy ngay trên hệ thống đang ghi dữ liệu. Thay đổi `INCREMENT BY` không tự xác nhận giá trị cấp tiếp theo đã đủ xa tất cả ID hiện có và tất cả dải Hibernate đã dự trữ.

Trong production, cần tính cả trạng thái sequence, ID hiện hữu, ID các instance đã giữ trong bộ nhớ, traffic đồng thời, trạng thái triển khai song song và khả năng rollback.

### Lưu ý về `RESTART` và `setval`

PostgreSQL cho phép các thao tác quản trị như `ALTER SEQUENCE ... RESTART WITH ...` hoặc `setval(...)`, nhưng dùng sai có thể làm sequence phát lại giá trị đang tồn tại hoặc giá trị mà một Hibernate process đã dự trữ.

Đừng áp dụng công thức máy móc như “`MAX(id) + 1`” cho pooled generator trong khi nhiều instance còn hoạt động. Một giá trị lớn hơn ID đã commit **vẫn có thể nằm trong dải ID mà ứng dụng khác đã dự trữ nhưng chưa insert**.

## 13. Chiến lược migration an toàn khi đổi kích thước cấp phát

Ví dụ tình huống: hệ thống đang chạy `allocationSize = 1`, database `INCREMENT BY 1`. Nhóm muốn chuyển sang dải 50 để giảm round-trip.

Một kế hoạch triển khai có kiểm soát thường gồm:

**Bước 1 — Kiểm kê các producer cấp ID.** Tìm tất cả ứng dụng, worker, batch job, lệnh SQL/ETL và framework đang dùng sequence. Xác định chúng sinh ID qua Hibernate, qua `DEFAULT nextval` hay bằng cách khác.

**Bước 2 — Xác định cấu hình đích.** Chọn allocation size, optimizer và bước tăng database. Với pooled/pooled-lo hiện đại, đảm bảo có hợp đồng tương thích rõ ràng. Không chỉ đổi annotation của một service.

**Bước 3 — Kiểm tra dữ liệu và trạng thái đang chạy.** Ghi nhận ID lớn nhất đã commit, cấu hình sequence, số lượng instance và khả năng tồn tại dải ID còn giữ trong bộ nhớ. Cần phân biệt dữ liệu trong bảng và reservation chưa được dùng.

**Bước 4 — Lên thời điểm cutover.** Với hệ thống không chấp nhận rủi ro trùng ID, thường cần dừng hoặc chặn có kiểm soát các producer đang cấp ID, để không có hai kiểu generator khác nhau cấp chồng dải trong giai đoạn chuyển đổi.

**Bước 5 — Thực hiện migration sequence và triển khai ứng dụng đồng bộ.** Điều chỉnh `INCREMENT BY` và nếu cần điều chỉnh mốc phát số theo đúng trạng thái an toàn, với công thức được kiểm chứng cho optimizer đã chọn. Không reset sequence xuống mốc thấp hơn vùng ID còn có thể được sử dụng.

**Bước 6 — Bật kiểm tra schema và quan sát.** Xác minh startup không có mismatch, insert qua các producer hoạt động bình thường, số lần lấy sequence và hành vi rollback/restart phù hợp kỳ vọng.

**Bước 7 — Có phương án rollback kiến trúc.** Nếu quay về `allocationSize = 1`, vẫn phải cân nhắc dải đã được dự trữ, bước sequence hiện tại và migration ngược. Chỉ rollback code mà không phối hợp trạng thái DB có thể tạo sai lệch lần nữa.

Quy trình chính xác tùy database, optimizer, yêu cầu không downtime và số lượng producer. Không thể cung cấp một câu `ALTER SEQUENCE` áp dụng an toàn cho mọi hệ thống production.

## 14. Nhiều instance Hibernate cùng dùng một sequence

Một lợi ích của sequence là có thể phục vụ nhiều kết nối và tiến trình cạnh tranh. Khi cấu hình pooling đúng, mỗi instance Hibernate xin một giá trị nguồn và giữ **dải ID riêng**, nhờ đó tránh tranh chấp từng ID trong bộ nhớ.

Ví dụ ý tưởng theo `pooled-lo`, sequence tăng 50:

```text
                        Database
                  purchase_order_id_seq
                       INCREMENT 50
                        /         \
                 nextval()     nextval()
                    1              51
                    |              |
                  App A          App B
                  1..50          51..100
```

Trong thực tế, thứ tự các instance xin sequence không cố định, và một instance có thể xin nhiều dải nếu workload cao. Database đảm bảo các giá trị nguồn tăng theo cơ chế sequence; optimizer đúng sẽ biến các giá trị nguồn đó thành dải không chồng lấn.

Đây là lý do cấu hình nhất quán của mọi instance rất quan trọng.

### Điều gì xảy ra nếu hai instance chạy hai version khác nhau?

Giả sử A dùng `allocationSize = 50` và B dùng `allocationSize = 1`. Nếu có một thay đổi bước sequence hoặc optimizer chưa được phối hợp, A và B có thể hiểu các giá trị nguồn khác nhau. Tùy combination, hệ thống có thể phát sinh khoảng trống lớn, validation failure hoặc chồng dải.

**Rolling deployment** không phải lúc nào an toàn khi đồng thời đổi chiến lược sinh khóa. Cần xem migration như thay đổi giao thức cấp ID giữa các producer, không chỉ là sửa một property của ứng dụng.

## 15. Không nên dùng khóa chính làm mã nghiệp vụ có thứ tự

Một yêu cầu phổ biến là “mã đơn hàng phải là 1, 2, 3, 4… không được thiếu”. Dùng sequence ID kỹ thuật để thỏa yêu cầu này dễ thất bại vì:

- Transaction rollback có thể bỏ số.
- Pooled allocation có thể bỏ dải khi ứng dụng restart.
- DB cache có thể tạo lỗ hổng sau crash.
- Thứ tự xin ID không nhất thiết là thứ tự commit transaction.
- Trong hệ thống phân tán, các instance có thể được cấp dải khác nhau.

Một mô hình tách bạch:

```java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "order_seq")
private Long id;

@Column(name = "business_order_number", unique = true)
private String businessOrderNumber;
```

`id` phục vụ định danh, quan hệ khóa ngoại và truy cập nội bộ. `businessOrderNumber` phục vụ hiển thị hoặc ràng buộc riêng của nghiệp vụ. Nếu số nghiệp vụ phải liên tục, tính năng cấp số cần thiết kế cơ chế đồng bộ, thời điểm chốt số và xử lý hủy chứng từ theo quy định cụ thể.

Việc tách này cũng giúp ứng dụng linh hoạt khi đổi generator hoặc chuyển dữ liệu mà không làm thay đổi mã người dùng nhìn thấy.

## 16. Những hiểu lầm thường gặp

### “`allocationSize = 50` nghĩa là Hibernate insert 50 hàng trong một lệnh”

Không. Nó liên quan đến **cấp phát ID**, không quy định số hàng trong một JDBC batch. Batch insert và sequence allocation là hai tối ưu độc lập.

### “DB `CACHE 50` nghĩa là Hibernate được dùng 50 ID”

Không. `CACHE` là tối ưu nội bộ của database sequence. Hibernate cần generator/optimizer và giá trị nguồn tương ứng để giữ dải ID phía ứng dụng.

### “Hibernate sẽ tự sửa sequence hiện có theo annotation”

Không nên giả định. Cấu hình tạo schema có thể thực hiện DDL trong một số môi trường, nhưng hệ thống dùng migration và schema production hiện hữu cần một thay đổi database riêng. Hibernate không thể tự suy ra cutover an toàn khi nhiều tiến trình đang giữ các dải ID.

### “Nếu các giá trị nextval không trùng thì primary key chắc chắn không trùng”

Không. Khi ứng dụng **suy ra nhiều ID từ một giá trị sequence**, hai dải suy ra vẫn có thể chồng lấn dù giá trị nguồn khác nhau. Đó là cốt lõi của lỗi mismatch với pooled allocation.

### “ID không liên tục nghĩa là database mất dữ liệu”

Không. Rollback, sequence cache, pooling và restart đều có thể tạo khoảng trống bình thường. Đối chiếu dữ liệu nghiệp vụ và audit thay vì đánh giá tính đúng dựa vào sự liền mạch của ID.

### “Đổi `allocationSize` chỉ ảnh hưởng hiệu năng”

Không. Với pooled optimizer, nó liên quan trực tiếp tới quy tắc biến giá trị sequence nguồn thành dải ID. Đổi giá trị ấy có thể đòi hỏi migration DB và phối hợp deployment.

### “Mọi phiên bản Hibernate dùng cùng optimizer mặc định”

Không. Các đời Hibernate và cấu hình generator có khác biệt. Cần xem version, mapping hiện hành và các thuộc tính optimizer nếu có. Đặc biệt với code legacy, không tự thay optimizer rồi chỉ kiểm tra một vài insert thành công.

## 17. Thực hành quan sát sự khác biệt

Để hiểu cơ chế khi học với một database thử nghiệm riêng, có thể tiến hành theo hai cấu hình **tách biệt**:

**Thử nghiệm A — một sequence value cho một ID**

- Tạo database/test schema với sequence `INCREMENT BY 1`.
- Đặt `allocationSize = 1`.
- Persist một loạt entity trong transaction rồi xem SQL log xem số lần Hibernate lấy sequence.
- Rollback một transaction và quan sát ID có thể bị bỏ trống.

**Thử nghiệm B — pooled allocation**

- Tạo schema thử nghiệm mới với `INCREMENT BY 50`.
- Đặt `allocationSize = 50` và bảo đảm generator sử dụng pooled optimizer tương thích.
- Persist 100 entity rồi so sánh tần suất lấy sequence với thử nghiệm A.
- Restart ứng dụng khi còn ID chưa cấp hết để quan sát khả năng xuất hiện khoảng trống.

Không đổi `INCREMENT BY` trên cùng sequence đang được dùng đồng thời bởi thí nghiệm khác, vì mục tiêu là hiểu từng chiến lược trong trạng thái nhất quán.

### Phân tích kết quả đúng cách

- Số lượt gọi sequence phản ánh cách **sinh khóa**.
- Số câu `INSERT` phản ánh số entity thực sự được đưa vào database.
- Giá trị ID cuối cùng không nhất thiết bằng số hàng.
- Dữ liệu đã commit trong bảng mới quyết định hàng nào tồn tại.
- Trạng thái sequence có thể lớn hơn rất nhiều so với `MAX(id)` mà vẫn bình thường.

## 18. Ghi nhớ khi thiết kế generator trong dự án

1. **Sequence là nguồn phát giá trị**, còn Hibernate generator có thể biến một giá trị nguồn thành **một dải ID**.
2. **`allocationSize` thuộc phía Hibernate; `INCREMENT BY` thuộc phía database; `CACHE` tối ưu nội bộ sequence của DB.** Ba giá trị không thể hoán đổi cho nhau.
3. Với **pooled/pooled-lo** thông thường, cần bảo đảm bước tăng database sequence **tương thích với kích thước cấp phát** mà optimizer kỳ vọng.
4. `@SequenceGenerator` mặc định `allocationSize = 50` nếu không chỉ rõ; không nên mặc định đó là 1.
5. Một sequence tăng từng đơn vị trong khi pooled optimizer giả định dải 50 có thể tạo **dải ID chồng lấn**, gây lỗi trùng khóa hoặc validation mismatch.
6. Pooling giúp giảm số lần xin sequence, nhưng không làm giảm số hàng phải insert và không phải cùng cơ chế với JDBC batching.
7. **Khoảng trống ID là bình thường** khi có rollback, restart, cache hoặc dải chưa dùng; primary key không phải bộ đếm chứng từ liên tục.
8. Mọi service, job và script cùng tiêu thụ sequence phải dùng một quy ước cấp ID có thể cùng tồn tại an toàn.
9. Thay đổi generator trong production là thay đổi **phối hợp giữa ứng dụng và trạng thái database**, cần kế hoạch cutover và migration rõ ràng.
10. Kiểm tra cả mapping, optimizer, database metadata và SQL thực tế; không suy ra an toàn chỉ từ một annotation hay vài lần insert thành công.

**Thông điệp cốt lõi:** `allocationSize` là một quyết định kiến trúc liên quan đến cả tính đúng đắn lẫn hiệu năng. Hibernate chỉ cấp ID an toàn theo dải khi cách diễn giải giá trị sequence của nó phù hợp với cách database phát số và với tất cả thành phần khác cùng dùng sequence.

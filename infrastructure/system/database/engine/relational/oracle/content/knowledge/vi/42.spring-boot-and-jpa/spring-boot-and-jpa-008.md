# Sequence generator, allocationSize và phối hợp với sequence phía Oracle

Trong ứng dụng Spring Boot dùng Spring Data JPA/Hibernate với Oracle Database, khóa chính có thể được sinh bằng Oracle sequence. JPA mô tả cơ chế này qua annotation SequenceGenerator và GeneratedValue; Hibernate quyết định cách lấy giá trị sequence và cách phân bổ ID cho các entity.

Điểm cần phối hợp là allocationSize trong mapping Java và INCREMENT BY của sequence Oracle. Nếu Hibernate dùng pooled optimizer để lấy một dải ID, database sequence phải cấp các mốc theo đúng kích thước block mà Hibernate mong đợi. Cấu hình lệch có thể khiến ứng dụng khởi động thất bại do Hibernate phát hiện mismatch, hoặc trong một số cấu hình cũ/đã tắt kiểm tra có thể dẫn tới vùng ID bị chồng lấn.

Ngoài ra, allocationSize không giống CACHE của Oracle:

- allocationSize cho phép Hibernate lấy một giá trị sequence rồi cấp nhiều ID trong bộ nhớ ứng dụng.
- CACHE cho phép Oracle cache nhiều giá trị sequence trong database instance để giảm chi phí sinh sequence.

Hai cơ chế hoạt động ở hai tầng khác nhau và có thể dùng đồng thời. Muốn thiết kế đúng, cần thống nhất mapping JPA, optimizer Hibernate, DDL Oracle, mọi writer khác cùng sử dụng sequence, và quy trình thay đổi cấu hình khi ứng dụng đang chạy.

## 1. Oracle sequence và JPA sequence generator

### 1.1. Oracle sequence là gì?

Sequence là database object tạo ra dãy số theo cấu hình. Nhiều session và nhiều application instance có thể gọi cùng sequence để nhận các giá trị khác nhau mà không cần khóa một bảng counter dùng chung.

Ví dụ tạo sequence:

```sql
CREATE SEQUENCE APP.ORDERS_SEQ
    START WITH 1
    INCREMENT BY 1
    CACHE 100
    NOCYCLE;
```

Lấy giá trị:

```sql
SELECT APP.ORDERS_SEQ.NEXTVAL
FROM DUAL;
```

Trong một session, sau khi đã gọi NEXTVAL, có thể đọc CURRVAL:

```sql
SELECT APP.ORDERS_SEQ.CURRVAL
FROM DUAL;
```

CURRVAL chưa được xác định trong session cho tới khi session đó gọi NEXTVAL ít nhất một lần. Giá trị NEXTVAL được cấp không bị hoàn lại khi transaction rollback.

### 1.2. JPA generator và database sequence là hai tên khác nhau

Trong SequenceGenerator:

- name là tên logic của generator trong persistence unit.
- sequenceName là tên sequence object thực tế trong database.
- schema xác định schema chứa sequence khi được khai báo.
- allocationSize mô tả số ID mà provider có thể cấp trong một lần allocation.
- initialValue mô tả giá trị ban đầu mà provider dùng khi tạo schema theo metadata; nó không tự reset một sequence đã tồn tại.

Không nhầm name với sequenceName. Generator name phải duy nhất trong phạm vi persistence unit theo quy tắc JPA; database sequence name phải khớp object Oracle.

### 1.3. Entity dùng sequence

Ví dụ một entity:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "ORDERS", schema = "APP")
@SequenceGenerator(
    name = "orders_id_generator",
    sequenceName = "ORDERS_SEQ",
    schema = "APP",
    allocationSize = 1
)
public class Order {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "orders_id_generator"
    )
    @Column(name = "ORDER_ID")
    private Long id;

    // Các thuộc tính nghiệp vụ khác.
}
```

Với Spring Boot 2 dùng Java EE/JPA namespace cũ, import thường là javax.persistence.*; Spring Boot 3 trở lên dùng jakarta.persistence.*. Chọn namespace theo phiên bản Spring Boot/JPA thực tế.

### 1.4. Cấu hình Oracle tương ứng với allocationSize = 1

Với ví dụ trên:

```sql
CREATE SEQUENCE APP.ORDERS_SEQ
    START WITH 1
    INCREMENT BY 1
    CACHE 100
    NOCYCLE;
```

Đây là cấu hình đơn giản: Hibernate lấy một giá trị sequence cho mỗi ID. CACHE 100 vẫn có thể được dùng để giảm chi phí tạo giá trị sequence ở Oracle; nó không làm Hibernate tự phân bổ 100 ID trong JVM.

### 1.5. Dùng allocationSize lớn hơn 1

Khi cần giảm số lần round-trip tới database, có thể đặt:

```java
@SequenceGenerator(
    name = "orders_id_generator",
    sequenceName = "ORDERS_SEQ",
    schema = "APP",
    initialValue = 1,
    allocationSize = 50
)
```

Với Hibernate sử dụng pooled hoặc pooled-lo optimizer, sequence Oracle thường cần được định nghĩa:

```sql
CREATE SEQUENCE APP.ORDERS_SEQ
    START WITH 1
    INCREMENT BY 50
    CACHE 100
    NOCYCLE;
```

Khi provider lấy được một sequence value, Hibernate dùng optimizer để quản lý block ID theo quy tắc của optimizer. Giá trị đầu/cuối block cụ thể phụ thuộc pooled hay pooled-lo và cách khởi tạo generator; điều quan trọng là database sequence increment phải khớp allocation protocol mà provider đang dùng.

Không đổi annotation thành 50 rồi giữ nguyên sequence increment 1 mà không xác nhận optimizer và mismatch strategy. Đây là một trong những nguyên nhân thường gặp khi ứng dụng Hibernate chuyển từ cấu hình cũ sang mapping mới.

## 2. GenerationType.SEQUENCE và SequenceGenerator

### 2.1. GenerationType.SEQUENCE

GenerationType.SEQUENCE yêu cầu persistence provider dùng database sequence để sinh identifier. Oracle hỗ trợ sequence native, vì vậy đây thường là lựa chọn tự nhiên cho entity cần ID numeric.

Khác với GenerationType.IDENTITY, sequence có thể được gọi trước câu INSERT. Provider biết ID trước khi insert entity, nhờ đó Hibernate có thể phối hợp với persistence context và JDBC batching thuận lợi hơn.

### 2.2. GenerationType.IDENTITY

Oracle hỗ trợ identity columns từ các release có tính năng này. Nếu dùng identity column, mapping thường dùng:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Không khai báo SequenceGenerator cho cột identity theo cùng cách như ví dụ sequence. Identity column được database quản lý bằng cơ chế identity nội bộ. Lựa chọn IDENTITY hay SEQUENCE cần dựa trên schema, Oracle release, Hibernate dialect và yêu cầu batching.

### 2.3. Vì sao khai báo generator tường minh?

Không phụ thuộc vào tên sequence mặc định do Hibernate tự suy ra. Khai báo rõ generator giúp:

- Dùng tên Oracle sequence được quản lý bằng migration script.
- Đồng nhất tên giữa Java và database.
- Kiểm soát allocationSize.
- Tránh vô tình tạo nhiều sequence không cần thiết.
- Dễ review khi nhiều service cùng truy cập schema.

### 2.4. Generator có thể đặt ở cấp entity hoặc package

SequenceGenerator có thể đặt trên entity hoặc package theo JPA mapping. Khi nhiều entity chia sẻ generator, bảo đảm chúng thực sự cần chung một sequence và có cùng allocation protocol. Không dùng chung sequence giữa entity có cấu hình allocationSize khác nhau nếu không có thiết kế cụ thể đã kiểm thử.

### 2.5. Dùng schema trong annotation

Nếu sequence nằm ở schema APP nhưng ứng dụng kết nối bằng user APP_RUNTIME, có thể khai báo schema và cấp quyền phù hợp. Nếu ứng dụng kết nối trực tiếp bằng owner APP, schema có thể không cần thiết về mặt quyền nhưng vẫn giúp mapping rõ ràng.

## 3. allocationSize là gì?

### 3.1. Ý nghĩa

allocationSize là kích thước allocation mà JPA provider sử dụng khi sinh identifier. Khi giá trị lớn hơn 1 và Hibernate dùng optimizer phù hợp, provider có thể lấy một mốc từ Oracle rồi sinh nhiều ID trong bộ nhớ trước khi cần truy cập sequence lần nữa.

Ví dụ với allocationSize 50:

1. Hibernate cần ID cho entity mới.
2. Hibernate lấy một giá trị từ Oracle sequence.
3. Optimizer xác định block ID tương ứng.
4. Hibernate cấp ID từ block đó cho các entity tiếp theo.
5. Khi block hết, Hibernate lấy sequence value tiếp theo.

Kết quả là số lần gọi NEXTVAL có thể giảm đáng kể so với việc gọi một lần cho mỗi INSERT.

### 3.2. allocationSize = 1

Đây là cấu hình dễ phối hợp nhất:

- Mỗi ID cần một lần gọi sequence.
- Oracle sequence thường dùng INCREMENT BY 1.
- Không có block ID lớn nằm trong bộ nhớ ứng dụng.
- Dễ phối hợp với các chương trình khác gọi NEXTVAL trực tiếp.
- Có thêm database round-trip khi tạo nhiều entity.

Nên dùng khi số lượng insert vừa phải, cần đơn giản hóa tương tác với nhiều writer hoặc đang chuyển đổi từ hệ thống cũ chưa thể đồng bộ allocation protocol.

### 3.3. allocationSize lớn hơn 1

Ưu điểm:

- Giảm số lần gọi sequence qua database.
- Giảm network round-trip giữa application và Oracle.
- Hỗ trợ throughput insert cao.
- Giảm áp lực lấy sequence value trong workload nhiều node.

Đánh đổi:

- Có thể bỏ phí các ID chưa sử dụng khi JVM restart hoặc process crash.
- Sequence increment phải phù hợp với optimizer.
- Mọi application instance phải dùng allocation protocol tương thích.
- Thay đổi allocationSize cần phối hợp deployment và database DDL.
- ID được cấp trong bộ nhớ có thể không theo đúng thứ tự commit.

### 3.4. Giá trị mặc định

Trong JPA, SequenceGenerator.allocationSize có mặc định là 50. Không nên bỏ qua thuộc tính này trong hệ thống có nhiều service hoặc sequence đã tồn tại; hãy khai báo rõ giá trị và tạo DDL tương ứng.

### 3.5. allocationSize không phải batch size

Hai khái niệm khác nhau:

- allocationSize: số identifier có thể được cấp từ một lần allocation sequence.
- Hibernate JDBC batch size: số câu lệnh DML được gom trong một JDBC batch.

Ví dụ allocationSize 50 và JDBC batch size 25 có thể dùng cùng nhau: Hibernate dự trữ ID theo block 50 nhưng gửi INSERT theo batch 25. Tăng một tham số không tự động tăng tham số còn lại.

## 4. Hibernate sequence optimizers

### 4.1. Vì sao cần optimizer?

JPA định nghĩa allocationSize ở mức provider. Hibernate hiện thực việc phân bổ ID bằng các optimizer. Optimizer quyết định ý nghĩa của giá trị NEXTVAL và cách biến nó thành một hoặc nhiều entity IDs.

Các optimizer thường gặp:

| Optimizer | Ý tưởng | Quan hệ với database sequence |
|---|---|---|
| none | Lấy một giá trị cho mỗi ID | Thường dùng increment 1 |
| hilo | Dùng giá trị high từ sequence để tạo một dải low values | Cơ chế legacy thường dùng sequence tăng 1 |
| pooled | Giá trị sequence đại diện cho ranh giới block theo quy tắc pooled | Sequence increment phải khớp block size |
| pooled-lo | Giá trị sequence đại diện cho đầu block theo quy tắc pooled-lo | Sequence increment phải khớp block size |

Chi tiết khởi tạo, ranh giới block và optimizer mặc định phụ thuộc Hibernate version, generator mapping và cấu hình. Không suy luận optimizer chỉ từ annotation; xác nhận version Hibernate và startup logs.

### 4.2. none

Optimizer none gọi sequence cho mỗi identifier. Với sequence increment 1, mỗi NEXTVAL cung cấp một ID. Cách này đơn giản và dễ tương tác với native SQL hoặc ứng dụng khác.

### 4.3. hilo

Hi/lo là thuật toán phân bổ identifier dùng một giá trị sequence làm high component và tạo nhiều low values trong bộ nhớ. Các mapping legacy có thể dùng sequence increment 1 dù allocation block lớn hơn 1.

Đây là lý do không thể khẳng định mọi cấu hình allocationSize lớn đều bắt buộc sequence INCREMENT BY đúng bằng allocationSize mà không biết optimizer. Với Hibernate hiện đại, pooled/pooled-lo thường là cách tiếp cận phổ biến; legacy hilo có semantics khác.

### 4.4. pooled

Pooled optimizer dùng sequence values làm ranh giới của các block. Database sequence increment phải khớp allocation size mà optimizer mong đợi để các block giữa các lần cấp phát không chồng lấn.

### 4.5. pooled-lo

Pooled-lo coi sequence value là giá trị thấp của block. Với allocation size 50, một lần cấp phát có thể tạo một dải 50 ID bắt đầu tại mốc đó. Lần cấp tiếp theo lấy mốc sequence tiếp theo, cách nhau 50 nếu Oracle sequence được cấu hình tương ứng.

### 4.6. Không tự ép optimizer khi chưa hiểu mapping

Hibernate có các thuộc tính để chọn pooled optimizer hoặc điều chỉnh behavior generator. Cấu hình legacy và thuộc tính Hibernate 5/6 có thể khác. Nếu cần đổi optimizer, thử trên môi trường staging với nhiều application instance và kiểm tra unique IDs trước khi deploy.

### 4.7. Kiểm tra sequence increment mismatch

Hibernate có thể phát hiện increment size trong mapping khác với increment của sequence database khi khởi động. Tùy version và cấu hình, mismatch có thể được xử lý theo strategy như EXCEPTION, FIX, LOG hoặc NONE.

Không dùng strategy bỏ qua kiểm tra như một cách che lỗi DDL. Xác nhận sequence increment, mapping và optimizer. Nếu Hibernate báo mismatch, dừng rollout và sửa cho thống nhất.

## 5. Phối hợp allocationSize với Oracle INCREMENT BY

### 5.1. Quy tắc thực tế cho pooled optimizers

Nếu Hibernate dùng pooled hoặc pooled-lo optimizer với allocationSize 50, cấu hình Oracle thường là:

```sql
CREATE SEQUENCE APP.ORDERS_SEQ
    START WITH 1
    INCREMENT BY 50
    CACHE 100
    NOCYCLE;
```

Nếu allocationSize là 1 và dùng optimizer none, cấu hình đơn giản là:

```sql
CREATE SEQUENCE APP.ORDERS_SEQ
    START WITH 1
    INCREMENT BY 1
    CACHE 100
    NOCYCLE;
```

Đây là mẫu cho Hibernate pooled/pooled-lo và none tương ứng; kiểm tra optimizer thực tế và Hibernate version trước khi áp dụng.

### 5.2. Ví dụ allocationSize 50

Giả sử mapping:

```java
@SequenceGenerator(
    name = "invoice_seq_gen",
    sequenceName = "INVOICE_SEQ",
    schema = "APP",
    allocationSize = 50
)
```

DDL cho pooled optimizer:

```sql
CREATE SEQUENCE APP.INVOICE_SEQ
    START WITH 1
    INCREMENT BY 50
    CACHE 100
    NOCYCLE;
```

Hibernate lấy các mốc sequence và cấp ID từ block theo optimizer. Application không cần gọi NEXTVAL cho từng invoice; nó chỉ lấy mốc khi block hiện tại cạn.

### 5.3. Ví dụ allocationSize 100

Java:

```java
@SequenceGenerator(
    name = "payment_seq_gen",
    sequenceName = "PAYMENT_SEQ",
    schema = "APP",
    allocationSize = 100
)
```

Oracle:

```sql
CREATE SEQUENCE APP.PAYMENT_SEQ
    START WITH 1
    INCREMENT BY 100
    CACHE 50
    NOCYCLE;
```

CACHE 50 ở đây là 50 sequence values trong cache của Oracle, không phải 50 entity IDs của Hibernate. Vì sequence increment 100, mỗi cached sequence value cách nhau 100 đơn vị theo sequence.

### 5.4. Mismatch allocationSize 50 với INCREMENT BY 1

Ví dụ:

- Mapping Java: allocationSize 50.
- Hibernate dùng pooled-lo.
- Oracle sequence: INCREMENT BY 1.

Sequence có thể trả các mốc liên tiếp 1, 2, 3... trong khi Hibernate coi mỗi mốc là đầu một block 50. Các block có thể chồng lấn. Hibernate hiện đại thường phát hiện mismatch và từ chối khởi động theo default strategy; nếu validation bị tắt hoặc legacy behavior khác, nguy cơ duplicate ID là nghiêm trọng.

### 5.5. Mismatch allocationSize 1 với INCREMENT BY 50

Mapping và physical sequence không cùng protocol. Tùy optimizer/version, Hibernate có thể báo lỗi increment mismatch, tạo khoảng trống lớn hoặc dùng sequence theo cách không như dự kiến. Không chấp nhận mismatch chỉ vì một vài insert thử nghiệm chưa gặp duplicate.

### 5.6. Tất cả writer phải hiểu cùng sequence

Nếu cùng một sequence được dùng bởi:

- Spring Boot service A.
- Spring Boot service B.
- Batch process.
- Stored procedure.
- Native SQL insert.

thì phải xác định cách mỗi writer lấy ID. Không để một service dùng pooled allocation trong khi service khác giả định sequence tăng 1 mà không có thiết kế tương thích. Nếu khó kiểm soát nhiều writer, cân nhắc allocationSize 1 hoặc tách sequence theo miền sở hữu.

## 6. Oracle CACHE và allocationSize khác nhau thế nào?

### 6.1. allocationSize ở application

Hibernate lấy một sequence marker rồi sử dụng block ID trong bộ nhớ JVM. Block đó thuộc về application process và có thể còn ID chưa sử dụng khi process dừng.

### 6.2. CACHE ở Oracle

Oracle sequence CACHE lưu trước một số sequence values trong memory của database instance để giảm chi phí tạo sequence value. Khi database instance bị crash hoặc shutdown bất thường, các giá trị cache chưa dùng có thể bị bỏ qua.

Ví dụ:

```sql
CREATE SEQUENCE APP.ORDERS_SEQ
    START WITH 1
    INCREMENT BY 50
    CACHE 100
    NOCYCLE;
```

Oracle cache 100 sequence values; mỗi value tăng 50. Hibernate lại dùng allocationSize 50 để quản lý các ID của entity. Đây là hai tầng allocation khác nhau.

### 6.3. So sánh

| Thuộc tính | JPA allocationSize | Oracle CACHE |
|---|---|---|
| Nơi quản lý | Application/Hibernate | Oracle Database instance |
| Đối tượng được cấp | Entity IDs trong block | Sequence values |
| Giảm chi phí nào? | Giảm round-trip lấy sequence từ app | Giảm chi phí sinh sequence values |
| Khi JVM restart | Block chưa dùng bị bỏ phí | Không ảnh hưởng cache Oracle trực tiếp |
| Khi DB instance restart | Block đang giữ trong JVM có thể còn nhưng kết nối/transaction cần xử lý | Cached sequence values có thể bị mất |
| Cần khớp allocationSize? | Có với pooled optimizer theo protocol | CACHE không cần bằng allocationSize |

### 6.4. CACHE bao nhiêu?

Chọn CACHE theo tần suất sử dụng sequence, số instance, yêu cầu hiệu năng và khả năng chấp nhận gaps. CACHE lớn thường giảm chi phí sequence generation; nó không bảo đảm ID liên tục.

### 6.5. NOCACHE không tạo sequence gapless

NOCACHE có thể giảm một nguồn gap do mất cache, nhưng NEXTVAL vẫn không transactional. Rollback, process failure, block allocation và các tình huống khác vẫn tạo khoảng trống. Không dùng NOCACHE để cam kết số hóa đơn liên tục.

## 7. ID gaps, thứ tự và tính duy nhất

### 7.1. Gaps là bình thường

Sequence đảm bảo cấp giá trị theo cơ chế của nó, không đảm bảo không có khoảng trống. Gaps có thể xuất hiện khi:

- Transaction gọi NEXTVAL rồi rollback.
- Application lấy block 50 ID nhưng chỉ dùng một phần trước khi restart.
- Oracle sequence cache bị mất khi instance failure.
- Một batch lấy ID nhưng không insert hết.
- Sequence được tăng để vượt qua vùng ID đã sử dụng.

Không xem gaps là dấu hiệu migration mất dữ liệu nếu không có bằng chứng khác.

### 7.2. Sequence không bảo đảm thứ tự commit

ID được cấp trước khi transaction commit. Transaction A có thể lấy ID nhỏ hơn nhưng commit sau transaction B. Khi dùng pooled allocation, các application instance có thể giữ các block khác nhau và insert theo tốc độ riêng.

Không dùng ID sequence để suy ra chính xác thứ tự nghiệp vụ hoặc thời điểm giao dịch.

### 7.3. CACHE và ORDER

- CACHE điều khiển số sequence values Oracle lưu trước.
- ORDER yêu cầu sequence values được cấp theo thứ tự yêu cầu trong phạm vi Oracle hỗ trợ.
- NOORDER thường phù hợp cho khóa chính khi chỉ cần tính duy nhất.

ORDER không làm sequence gapless và không bảo đảm thứ tự commit. Trong RAC, ORDER có thể tăng chi phí đồng bộ; chỉ bật nếu nghiệp vụ thực sự cần thứ tự cấp phát và đã đo hiệu năng.

### 7.4. NOCYCLE cho primary key

Sequence dùng cho primary key thường phải NOCYCLE. Nếu CYCLE, sequence có thể quay lại giá trị cũ sau MAXVALUE/MINVALUE và gây duplicate key.

### 7.5. Sequence không phải business document number

Nếu nghiệp vụ yêu cầu số chứng từ liên tục, có thể cần một quy trình numbering có transaction serialization, lock và audit riêng. Sequence không đáp ứng gapless numbering chỉ bằng cách đặt NOCACHE/ORDER.

## 8. Spring Boot và Hibernate configuration

### 8.1. Entity mapping

Ví dụ cấu hình allocationSize 50:

```java
@Entity
@Table(name = "INVOICE", schema = "APP")
@SequenceGenerator(
    name = "invoice_seq_gen",
    sequenceName = "INVOICE_SEQ",
    schema = "APP",
    initialValue = 1,
    allocationSize = 50
)
public class Invoice {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "invoice_seq_gen"
    )
    @Column(name = "INVOICE_ID")
    private Long id;

    // Các field nghiệp vụ.
}
```

Đảm bảo sequence INVOICE_SEQ được tạo bằng migration script với increment phù hợp optimizer Hibernate.

### 8.2. Spring Boot application properties

Ví dụ cấu hình production-oriented:

```yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//dbhost:1521/APP_SERVICE
    username: APP_RUNTIME
  jpa:
    hibernate:
      ddl-auto: validate
    properties:
      hibernate:
        format_sql: true
```

Inject password bằng secret management của môi trường; không commit credential vào source.

### 8.3. Dùng Flyway hoặc Liquibase quản lý sequence

Trong production, nên tạo/đổi sequence bằng migration versioned:

```sql
CREATE SEQUENCE APP.INVOICE_SEQ
    START WITH 1
    INCREMENT BY 50
    CACHE 100
    NOCYCLE;
```

Không phụ thuộc spring.jpa.hibernate.ddl-auto=update để tự đồng bộ sequence increment. Schema migration tool giúp review DDL, thứ tự rollout và rollback plan.

### 8.4. ddl-auto

- create/create-drop: phù hợp một số môi trường test, có thể xóa/tạo schema.
- update: Hibernate cố thay đổi schema; không nên dùng như cơ chế migration production có kiểm soát.
- validate: kiểm tra một số mapping/schema compatibility nhưng không thay thế kiểm tra toàn bộ sequence optimizer, quyền và behavior runtime.
- none: không tự quản lý schema.

Chọn chiến lược theo môi trường; production thường để Flyway/Liquibase quản lý DDL và Hibernate validate mapping.

### 8.5. Hibernate version

Spring Boot quản lý phiên bản Hibernate theo dependency management của release. Khi nâng Spring Boot, Hibernate có thể đổi generator behavior, optimizer defaults hoặc schema validation. Ghi lại version thực tế:

```text
mvn dependency:tree
```

Hoặc dùng Gradle dependency insight để xem Hibernate ORM version được resolve. Không chỉ đọc version ghi trong build file nếu dependency có thể bị override.

### 8.6. Sequence increment mismatch strategy

Hibernate có property liên quan sequence increment mismatch strategy trong các phiên bản hỗ trợ. Một số strategy thường gặp:

- EXCEPTION: báo lỗi khi increment của sequence không khớp mapping.
- FIX: điều chỉnh cách Hibernate diễn giải increment theo strategy được hỗ trợ.
- LOG: ghi cảnh báo.
- NONE: không thực hiện kiểm tra mismatch.

Tên property/giá trị và default phụ thuộc Hibernate version. Không đặt NONE để che mismatch. Ưu tiên sửa DDL và mapping cho khớp; chỉ chọn strategy khác khi hiểu rõ optimizer và đã chứng minh không có overlap.

## 9. Quyền truy cập Oracle sequence

### 9.1. Cùng schema

Nếu application database user sở hữu sequence, user có thể truy cập sequence của mình theo quyền sở hữu.

### 9.2. Khác schema

Nếu sequence nằm trong APP và ứng dụng kết nối bằng APP_RUNTIME, cấp quyền:

```sql
GRANT SELECT ON APP.ORDERS_SEQ TO APP_RUNTIME;
```

Trong Oracle, quyền SELECT trên sequence cho phép sử dụng NEXTVAL/CURRVAL. Có thể tạo synonym để mapping ngắn hơn, nhưng synonym không cấp quyền:

```sql
CREATE SYNONYM APP_RUNTIME.ORDERS_SEQ
FOR APP.ORDERS_SEQ;
```

### 9.3. Kiểm tra quyền

```sql
SELECT owner,
       table_name,
       grantee,
       privilege
FROM all_tab_privs
WHERE owner = 'APP'
  AND table_name = 'ORDERS_SEQ';
```

Kiểm tra synonym:

```sql
SELECT owner, synonym_name, table_owner, table_name, db_link
FROM all_synonyms
WHERE synonym_name = 'ORDERS_SEQ';
```

### 9.4. Lỗi quyền

Các lỗi thường gặp:

- ORA-02289: sequence does not exist; có thể do tên/schema sai hoặc thiếu quyền.
- ORA-01031: insufficient privileges.
- ORA-00942 khi truy vấn object liên quan có thể do tên hoặc quyền.

Xác định user runtime thực tế, current schema và object resolution; đừng chỉ kiểm tra bằng DBA account vì quyền DBA có thể che lỗi của application user.

## 10. Nhiều application instance và nhiều writer

### 10.1. Spring Boot chạy nhiều replica

Trong Kubernetes hoặc application cluster, nhiều JVM có thể cùng dùng một sequence Oracle. Oracle sequence cấp các giá trị khác nhau giữa các session; Hibernate mỗi JVM có thể giữ block ID riêng.

Ví dụ khái niệm:

```text
JVM A reserves block A
JVM B reserves block B
JVM C reserves block C

Each JVM allocates IDs locally until its block is exhausted.
```

Block size và sequence increment phải thống nhất. Không dựa vào việc mỗi pod có một generator name khác nhau để tránh collision; uniqueness đến từ database sequence và allocation protocol.

### 10.2. Scale-out và restart

Khi pod restart, block chưa dùng của pod đó bị bỏ phí. Đây là hành vi bình thường. Khi tăng số pod, số lần lấy block tăng nhưng vẫn ít hơn số insert nếu workload sử dụng hết block.

### 10.3. Rolling deployment

Không deploy đồng thời hai phiên bản ứng dụng có allocationSize/optimizer khác nhau lên cùng sequence nếu chưa thiết kế tương thích. Các instance cũ có thể đang giữ block trong bộ nhớ khi instance mới bắt đầu lấy block theo quy tắc mới.

Khi thay đổi allocation protocol, dùng coordinated rollout:

1. Dừng hoặc drain toàn bộ writer.
2. Chờ transaction đang chạy hoàn tất.
3. Đảm bảo không còn JVM giữ block cũ.
4. Thực hiện DDL sequence.
5. Deploy đồng nhất mapping mới.
6. Khởi động lại toàn bộ writer.
7. Chạy test insert song song và kiểm tra unique constraints.

### 10.4. Native SQL và stored procedure

Nếu một stored procedure cũng gọi NEXTVAL, xác nhận nó dùng cùng sequence và không tự giả định increment 1 khi Hibernate đang pooled. Nếu procedure chỉ gọi NEXTVAL một lần cho một row, sequence allocation protocol phải vẫn tương thích với pooled optimizer.

### 10.5. Bulk load

Import dữ liệu có thể mang ID đã tồn tại nhưng không tự cập nhật sequence theo MAX(primary key). Sau bulk load, sequence có thể nằm dưới vùng ID đã import. Phải đồng bộ sequence trước khi mở write traffic.

### 10.6. Tách sequence theo service

Nếu các service có vòng đời và release độc lập, tách sequence theo domain/service có thể giảm coupling. Nhưng nếu các service cùng insert vào một bảng hoặc cần ID toàn cục duy nhất, phải có thiết kế key space thống nhất.

## 11. Oracle RAC và sequence behavior

### 11.1. Sequence trên RAC

Oracle RAC cho phép nhiều instance cùng truy cập database. Sequence có cơ chế quản lý để cấp giá trị khác nhau trên các instance. CACHE giúp giảm hoạt động đồng bộ, trong khi ORDER có thể yêu cầu thứ tự cấp phát chặt hơn.

### 11.2. NOORDER

NOORDER là lựa chọn phổ biến khi chỉ cần uniqueness. Giá trị cấp ra trên các RAC instances có thể không tăng theo thứ tự thời gian request nhìn từ ứng dụng. Điều đó không ảnh hưởng uniqueness của sequence.

### 11.3. ORDER

ORDER yêu cầu thứ tự cấp sequence theo request order trong phạm vi Oracle đảm bảo. Nó không bảo đảm thứ tự commit, không loại bỏ gaps và có thể tăng overhead. Chỉ bật nếu yêu cầu nghiệp vụ thực sự cần thứ tự cấp sequence.

### 11.4. Application allocation vẫn có thứ tự riêng

Ngay cả khi Oracle sequence dùng ORDER, Hibernate có thể cấp các ID từ block đã dự trữ trong từng JVM. ID được insert/commit không nhất thiết theo thứ tự toàn cục. Nếu cần chronological ordering, lưu timestamp/business sequence riêng.

## 12. Kiểm tra Oracle sequence metadata

### 12.1. ALL_SEQUENCES

```sql
SELECT sequence_owner,
       sequence_name,
       min_value,
       max_value,
       increment_by,
       cycle_flag,
       order_flag,
       cache_size,
       last_number
FROM all_sequences
WHERE sequence_owner = 'APP'
ORDER BY sequence_name;
```

DBA_SEQUENCES cung cấp phạm vi rộng hơn nếu có quyền DBA. ALL_SEQUENCES chỉ hiện các sequence mà user có quyền nhìn thấy.

### 12.2. LAST_NUMBER

LAST_NUMBER có thể phản ánh giá trị cache/giá trị tiếp theo được ghi trong dictionary chứ không nhất thiết là giá trị NEXTVAL tiếp theo thực tế khi sequence cache đang hoạt động. Không dùng LAST_NUMBER làm số ID chính xác cuối cùng đã cấp.

### 12.3. Kiểm tra sequence của entity

Đối chiếu:

- sequenceName trong annotation.
- Schema khai báo.
- Oracle object thực tế.
- INCREMENT_BY.
- CACHE_SIZE.
- CYCLE_FLAG.
- Optimizer và allocationSize trong Hibernate.
- User runtime có quyền SELECT hay không.

### 12.4. Thử NEXTVAL

Có thể thử NEXTVAL trong môi trường test hoặc quy trình kiểm tra có kiểm soát. Trên production, nhớ rằng NEXTVAL tiêu thụ giá trị không rollback. Ghi nhận việc thử và không xem một lần NEXTVAL là thao tác read-only.

## 13. Sequence sau migration hoặc import dữ liệu

### 13.1. Vấn đề phổ biến

Data Pump có thể import bảng và dữ liệu có primary key nhưng sequence không được đồng bộ như kỳ vọng với MAX(primary key). Khi ứng dụng insert tiếp, sequence phát ra giá trị đã tồn tại và gây ORA-00001.

### 13.2. Kiểm tra MAX(id)

```sql
SELECT MAX(order_id) AS max_order_id
FROM app.orders;
```

Lấy metadata sequence:

```sql
SELECT increment_by,
       cache_size,
       cycle_flag,
       order_flag,
       last_number
FROM all_sequences
WHERE sequence_owner = 'APP'
  AND sequence_name = 'ORDERS_SEQ';
```

Đừng chỉ so sánh MAX(id) với LAST_NUMBER vì optimizer pooled có thể cần một mốc block và Oracle cache làm LAST_NUMBER không phản ánh NEXTVAL thực tế.

### 13.3. Quy trình đồng bộ an toàn

1. Xác định mọi bảng/entity sử dụng sequence.
2. Xác định optimizer đang dùng và allocationSize.
3. Dừng tất cả writer và drain transaction.
4. Xác nhận không còn JVM giữ block ID.
5. Tính mốc tiếp theo phù hợp optimizer, vượt mọi ID đã import.
6. Điều chỉnh sequence bằng phương pháp được Oracle release hỗ trợ.
7. Khôi phục INCREMENT BY đúng allocation protocol.
8. Xóa cache cũ theo quy trình/DDL phù hợp nếu cần.
9. Khởi động các application instance đồng nhất.
10. Thử insert và kiểm tra không có unique violation.

### 13.4. ALTER SEQUENCE RESTART

Một số Oracle release hỗ trợ cú pháp restart sequence; khả năng và syntax phụ thuộc release. Nếu dùng, kiểm tra tài liệu chính thức của phiên bản và bảo đảm giá trị restart đúng với optimizer.

Với release không hỗ trợ restart trực tiếp, có thể cần quy trình điều chỉnh increment có kiểm soát để advance sequence, sau đó khôi phục increment mong muốn. Không chạy script tổng quát trên production vì pooled và pooled-lo có cách diễn giải mốc khác nhau.

### 13.5. Tại sao phải dừng tất cả application instances?

Một JVM có thể còn giữ các ID chưa dùng trong block đã cấp trước khi sequence được reset. Nếu reset sequence xuống vùng đó hoặc thay increment, các block cũ và block mới có thể chồng lấn. Dừng writer và restart toàn bộ instance giúp loại bỏ state allocation trong memory.

### 13.6. Không reset sequence thấp hơn dữ liệu

Không đặt sequence START WITH 1 hoặc restart về giá trị nhỏ khi bảng đã có dữ liệu. Không xóa sequence rồi tạo lại trong khi ứng dụng đang chạy. Sequence reset là một thao tác migration cần maintenance window và kiểm tra rollback.

## 14. Thay đổi allocationSize trong hệ thống đang chạy

### 14.1. Thay từ 1 lên 50

Thay đổi này yêu cầu đồng bộ:

- Annotation allocationSize.
- Oracle INCREMENT BY.
- Hibernate optimizer behavior.
- Mọi application instance đang chạy.
- Stored procedures hoặc external writers sử dụng sequence.

### 14.2. Thay từ 50 xuống 1

Giảm allocationSize cũng là thay đổi protocol. Các JVM cũ có thể đang giữ block. Không chỉ sửa annotation rồi rolling restart từng pod trong khi sequence increment đã đổi.

### 14.3. Deployment hai giai đoạn

Một rollout an toàn thường cần:

1. Chuẩn bị DDL và release mapping mới.
2. Lên kế hoạch dừng/drain writer đồng thời.
3. Thực hiện thay đổi sequence.
4. Deploy toàn bộ application instance với mapping mới.
5. Khởi động và xác minh.

Nếu không thể dừng toàn bộ writer, thiết kế compatibility protocol riêng hoặc dùng sequence mới cho phiên bản mới; không giả định hai allocation sizes luôn tương thích khi chạy song song.

### 14.4. Version control

Đặt DDL sequence trong Flyway/Liquibase migration và mapping Java trong cùng pull request/release. Review hai thay đổi như một đơn vị. Ghi rõ thứ tự chạy migration và thời điểm restart app.

## 15. Hiệu năng và chọn allocationSize

### 15.1. Khi nào chọn 1?

Chọn allocationSize 1 khi:

- Lưu lượng insert vừa phải.
- Nhiều writer khác nhau cần dùng sequence trực tiếp.
- Ưu tiên đơn giản hóa vận hành.
- Cần tránh thay đổi optimizer trong giai đoạn migration.
- Chưa có số liệu chứng minh allocation block lớn mang lại lợi ích.

### 15.2. Khi nào chọn 20, 50 hoặc 100?

Block lớn hơn có thể giảm sequence round-trips. Chọn theo:

- Insert throughput.
- Số application instances.
- Network latency giữa app và database.
- Số entity được tạo trước khi process restart.
- Tốc độ scale up/down.
- Mức chấp nhận gaps.
- Số writer dùng chung sequence.

Không có một allocationSize tối ưu cho mọi ứng dụng. Giá trị 50 là mặc định JPA phổ biến, không phải quy tắc hiệu năng cho mọi workload.

### 15.3. Benchmark

Đo ít nhất:

- Insert throughput (rows/second).
- P50/P95/P99 insert transaction latency.
- Số lần SELECT NEXTVAL.
- Database round-trips.
- CPU/network utilization.
- JDBC batch effectiveness.
- Unique constraint violations.
- Behavior khi restart application.

Giữ cùng dataset, schema, indexes, transaction size và concurrency khi so sánh.

### 15.4. Sequence cache tuning

Tách benchmark allocationSize và Oracle CACHE. Thử một tham số mỗi lần để biết hiệu quả đến từ application block allocation hay database sequence cache. Không tăng CACHE lên rất lớn chỉ vì allocationSize lớn.

### 15.5. Hiệu năng khi nhiều node

Pooled allocation giảm số lần mỗi node gọi NEXTVAL. Nhưng số node tăng cũng có thể làm nhiều block chưa dùng bị bỏ phí khi autoscaling. Cân bằng block size với vòng đời pod và số insert thực tế.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| ORA-02289 sequence does not exist | Sai schema/tên hoặc thiếu quyền | ALL_SEQUENCES, grants, synonym |
| ORA-01031 insufficient privileges | Runtime user thiếu SELECT trên sequence | Kiểm tra bằng đúng application user |
| ORA-00001 unique constraint violated | Sequence thấp hơn MAX(id), block mismatch hoặc writer protocol sai | Kiểm tra MAX(id), increment, optimizer và mọi writer |
| Hibernate báo sequence increment mismatch | allocationSize khác INCREMENT BY | So sánh mapping, Hibernate version, ALL_SEQUENCES |
| ID nhảy số lớn | Allocation block, rollback, restart hoặc Oracle CACHE | Xem optimizer và lifecycle |
| Pod restart tạo gaps | Block ID chưa dùng bị bỏ | Hành vi bình thường của pooled allocation |
| Sequence hết MAXVALUE | MAXVALUE thấp hoặc CYCLE/limit không phù hợp | ALL_SEQUENCES, sequence design |
| Insert native SQL gây conflict | Native writer không tuân thủ protocol pooled | Kiểm tra shared sequence usage |
| Ứng dụng chạy được một node nhưng lỗi nhiều node | Mỗi node mapping/optimizer khác hoặc schema khác | So sánh config/runtime version trên mọi pod |
| Sau import phát sinh duplicate ID | Sequence chưa advance qua dữ liệu import | Kiểm tra MAX(PK), reset sequence có kiểm soát |
| Schema validation không phát hiện lỗi runtime | validate không kiểm tra mọi sequence behavior/permission | Test NEXTVAL bằng runtime user và integration test |

### 16.1. ORA-00001 sau cutover

Không chỉ tăng sequence ngay lập tức. Trước tiên:

1. Xác định constraint và bảng gây lỗi.
2. Xem ID bị duplicate.
3. Kiểm tra MAX(primary key).
4. Xác định sequence generator và optimizer.
5. Kiểm tra sequence increment và cache.
6. Kiểm tra các JVM có block cũ không.
7. Xác định native writer hoặc service khác.
8. Dừng writer và đồng bộ sequence theo đúng protocol.

### 16.2. Hibernate mismatch khi startup

Ghi nhận:

- Hibernate ORM version.
- Annotation allocationSize.
- Physical sequence INCREMENT_BY.
- Optimizer thực tế.
- Increment mismatch strategy.

Sửa DDL hoặc mapping trong migration. Không tắt validation trước khi xác định nguyên nhân.

## 17. Kiểm thử integration và concurrency

### 17.1. Kiểm thử một instance

Tạo nhiều entity, flush/commit, xác nhận:

- ID không NULL.
- Primary key unique.
- Sequence object đúng schema.
- Không có lỗi privilege.
- ID generator hoạt động sau transaction rollback.

### 17.2. Kiểm thử nhiều instance

Chạy ít nhất hai Spring Boot instances cùng kết nối Oracle test schema. Tạo nhiều entity đồng thời, commit theo nhiều transaction và xác nhận không có duplicate ID.

### 17.3. Kiểm thử restart

1. Cho instance A reserve một block.
2. Tạo một phần entity.
3. Dừng instance A trước khi dùng hết block.
4. Khởi động lại A và tiếp tục insert.
5. Xác nhận không có duplicate; gaps được chấp nhận.

### 17.4. Kiểm thử rollback

Tạo entity và lấy ID rồi rollback transaction. Lần insert sau có thể nhận ID khác, không tái sử dụng ID đã cấp. Test phải coi đây là behavior bình thường.

### 17.5. Kiểm thử native writer

Nếu có native SQL hoặc procedure gọi sequence, chạy song song với Hibernate writers. Xác nhận cùng sequence protocol không gây overlap. Kiểm tra cả trường hợp application restart và block chưa dùng.

### 17.6. Kiểm thử migration

Import dataset có ID lớn hơn sequence hiện tại, sau đó chạy sequence reconciliation trước cutover. Thử insert bằng đúng application runtime user và nhiều node.

## 18. Ví dụ hoàn chỉnh: Spring Boot + Oracle

### 18.1. DDL

Chọn allocationSize 50 và pooled optimizer tương ứng:

```sql
CREATE TABLE APP.ORDERS (
    ORDER_ID NUMBER(19) NOT NULL,
    CUSTOMER_ID NUMBER(19) NOT NULL,
    ORDER_STATUS VARCHAR2(30 CHAR) NOT NULL,
    TOTAL_AMOUNT NUMBER(18, 2) NOT NULL,
    CONSTRAINT PK_ORDERS PRIMARY KEY (ORDER_ID)
);

CREATE SEQUENCE APP.ORDERS_SEQ
    START WITH 1
    INCREMENT BY 50
    CACHE 100
    NOCYCLE;
```

Nếu runtime user khác APP:

```sql
GRANT SELECT ON APP.ORDERS_SEQ TO APP_RUNTIME;
GRANT SELECT, INSERT, UPDATE, DELETE ON APP.ORDERS TO APP_RUNTIME;
```

### 18.2. Entity

```java
@Entity
@Table(name = "ORDERS", schema = "APP")
@SequenceGenerator(
    name = "orders_seq_gen",
    sequenceName = "ORDERS_SEQ",
    schema = "APP",
    initialValue = 1,
    allocationSize = 50
)
public class Order {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "orders_seq_gen"
    )
    @Column(name = "ORDER_ID")
    private Long id;

    @Column(name = "CUSTOMER_ID", nullable = false)
    private Long customerId;

    @Column(name = "ORDER_STATUS", nullable = false)
    private String status;

    @Column(name = "TOTAL_AMOUNT", nullable = false)
    private BigDecimal totalAmount;

    protected Order() {
    }
}
```

### 18.3. Repository

```java
public interface OrderRepository extends JpaRepository<Order, Long> {
}
```

### 18.4. Service

```java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long createOrder(
            Long customerId,
            BigDecimal amount
    ) {
        Order order = new Order();
        // Gán các thuộc tính nghiệp vụ qua constructor/factory hoặc setter.
        return repository.save(order).getId();
    }
}
```

Đoạn service minh họa vị trí gọi repository; entity production cần constructor/factory và validation phù hợp. Việc lấy ID có thể xảy ra trước commit, vì vậy ID đã cấp vẫn có thể bị bỏ nếu transaction rollback.

### 18.5. Kiểm tra sequence

```sql
SELECT sequence_owner,
       sequence_name,
       increment_by,
       cache_size,
       cycle_flag,
       order_flag,
       last_number
FROM all_sequences
WHERE sequence_owner = 'APP'
  AND sequence_name = 'ORDERS_SEQ';
```

Đối chiếu INCREMENT_BY với allocationSize 50 và optimizer của Hibernate.

### 18.6. Kiểm tra dữ liệu

```sql
SELECT COUNT(*) AS row_count,
       MIN(order_id) AS min_id,
       MAX(order_id) AS max_id
FROM app.orders;
```

MAX_ID là căn cứ để kiểm tra sequence sau import, nhưng cách tính next boundary phải dựa trên optimizer. Không dùng LAST_NUMBER như giá trị chính xác.

## 19. Runbook thay đổi sequence allocation

### Trước thay đổi

- Xác định mọi entity và service dùng sequence.
- Ghi lại allocationSize và Hibernate version của từng service.
- Xác định optimizer.
- Ghi Oracle INCREMENT BY, CACHE, ORDER, CYCLE.
- Tìm các stored procedure/native writers.
- Xác định MAX(primary key) của mọi bảng liên quan.
- Chuẩn bị DDL và rollback/forward-fix plan.

### Trong thay đổi

1. Đưa ứng dụng vào maintenance/drain mode.
2. Dừng tất cả writer và đợi transaction kết thúc.
3. Xác nhận không còn process giữ allocation blocks.
4. Thực hiện sequence DDL theo Oracle release.
5. Deploy mapping đồng nhất.
6. Khởi động application instances.
7. Chạy test insert và kiểm tra constraints.

### Sau thay đổi

- Kiểm tra Hibernate startup logs.
- Kiểm tra runtime user có SELECT sequence.
- Kiểm tra nhiều pod cùng insert.
- Kiểm tra sequence increment và cache.
- Theo dõi ORA-00001, ORA-02289 và insert latency.
- Ghi lại cấu hình mới trong runbook.

## 20. Checklist thiết kế

- [ ] Đã chọn GenerationType.SEQUENCE hoặc IDENTITY theo schema và Hibernate version.
- [ ] Đã khai báo rõ generator name và physical sequenceName.
- [ ] Đã xác định schema chứa sequence.
- [ ] Đã đặt allocationSize tường minh.
- [ ] Đã xác định Hibernate optimizer thực tế.
- [ ] Oracle INCREMENT BY khớp allocation protocol.
- [ ] Không nhầm allocationSize với Oracle CACHE.
- [ ] Sequence dùng NOCYCLE cho primary key.
- [ ] Đã cân nhắc ORDER/NOORDER theo yêu cầu thật.
- [ ] Runtime user có quyền SELECT sequence.
- [ ] Synonym không bị nhầm với privilege.
- [ ] Mọi application instance dùng mapping tương thích.
- [ ] Native SQL/stored procedure writers đã được kiểm kê.
- [ ] DDL sequence được quản lý bằng Flyway/Liquibase.
- [ ] Production không phụ thuộc Hibernate ddl-auto update để sửa sequence.
- [ ] Có kế hoạch sequence reconciliation sau import.
- [ ] Có quy trình coordinated rollout khi đổi allocationSize.
- [ ] Đã test nhiều application instances đồng thời.
- [ ] Đã test rollback, restart và block chưa dùng.
- [ ] Đã xác nhận gaps là chấp nhận được với khóa surrogate.
- [ ] Không dùng sequence làm gapless business document number.

## 21. Câu hỏi tự kiểm tra

1. Oracle sequence giải quyết vấn đề gì khi nhiều session cùng tạo khóa?
2. name và sequenceName trong SequenceGenerator khác nhau ra sao?
3. allocationSize có mặc định JPA là bao nhiêu?
4. Vì sao nên khai báo allocationSize tường minh?
5. GenerationType.SEQUENCE khác GenerationType.IDENTITY như thế nào?
6. allocationSize khác JDBC batch size ở điểm nào?
7. Hibernate optimizer none, hilo, pooled và pooled-lo khác nhau ra sao?
8. Vì sao không thể suy ra INCREMENT BY chỉ từ allocationSize mà không biết optimizer?
9. Khi dùng pooled/pooled-lo với allocationSize 50, Oracle sequence thường cần increment thế nào?
10. Mismatch increment có thể gây lỗi startup hoặc ID overlap ra sao?
11. Vì sao không nên tắt sequence increment mismatch validation để che lỗi?
12. Oracle CACHE khác JPA allocationSize ở tầng nào?
13. Vì sao NOCACHE không bảo đảm sequence gapless?
14. Transaction rollback ảnh hưởng NEXTVAL như thế nào?
15. Vì sao ID sequence không bảo đảm thứ tự commit?
16. ORDER và NOORDER khác nhau ở điểm nào?
17. Vì sao sequence primary key thường dùng NOCYCLE?
18. Nhiều Spring Boot replicas chia sẻ sequence cần thống nhất điều gì?
19. Vì sao rolling deploy thay allocationSize có thể nguy hiểm?
20. Native SQL writer phải phối hợp với Hibernate pooled generator như thế nào?
21. Cần quyền nào để runtime user gọi sequence ở schema khác?
22. Vì sao synonym không tự cấp quyền sequence?
23. ALL_SEQUENCES.LAST_NUMBER có phải NEXTVAL kế tiếp chính xác không?
24. Vì sao phải dừng mọi writer trước khi reset sequence?
25. Sequence reset sau Data Pump import cần dựa vào những thông tin nào?
26. Vì sao sequence allocation block chưa dùng bị mất khi JVM restart?
27. Cần test gì để chứng minh ID unique trên nhiều application instances?
28. Vì sao sequence không phù hợp cho số chứng từ bắt buộc liên tục?
29. Flyway/Liquibase và Hibernate ddl-auto nên phân chia trách nhiệm ra sao?
30. Khi ORA-00001 xảy ra sau cutover, cần điều tra theo thứ tự nào?

**Nguyên tắc cần nhớ:** SequenceGenerator.name là tên logic, sequenceName là Oracle object; allocationSize là block ID do JPA provider quản lý, còn CACHE là cache sequence values ở Oracle. Với Hibernate pooled/pooled-lo, INCREMENT BY phải khớp allocation protocol và mọi writer phải phối hợp. Gaps sau rollback/restart là bình thường; sequence không bảo đảm gapless hoặc commit order. Khi thay allocationSize hay reset sequence sau migration, dừng toàn bộ writer, loại bỏ block cũ trong JVM, đổi DDL và mapping đồng bộ, rồi kiểm thử nhiều instance trước khi mở traffic.

# Kiểm tra tương thích khi ứng dụng nhiều phiên bản cùng chạy

Trong hệ thống sử dụng JPA và cơ sở dữ liệu quan hệ, việc cập nhật ứng dụng thường không diễn ra tức thời. Khi triển khai rolling update, canary release hoặc blue-green deployment, **phiên bản cũ và mới có thể đồng thời đọc, ghi vào cùng một schema và cùng một tập dữ liệu**. Đây là giai đoạn dễ xảy ra lỗi vì mỗi phiên bản có thể giả định cấu trúc bảng, ý nghĩa giá trị và quy tắc cập nhật khác nhau.

Bài học này trình bày cách xác định hợp đồng tương thích, thiết kế migration theo từng bước và kiểm tra các đường đọc/ghi khi nhiều phiên bản cùng tồn tại. Trọng tâm là quan hệ giữa **ứng dụng, JPA entity mapping, SQL, transaction và dữ liệu thực** trong quá trình vận hành, di trú.

## 1. Hiểu đúng bài toán nhiều phiên bản cùng chạy

Giả sử hệ thống đặt hàng có hai phiên bản:

- **V1**: 10 instance đang phục vụ khách hàng, dùng entity và schema hiện tại.
- **V2**: triển khai canary trên 2 instance, bổ sung trường mới, thay đổi truy vấn và logic cập nhật.
- **Database chung**: mọi instance kết nối cùng một cơ sở dữ liệu.
- **Worker nền**: consumer, scheduled job hoặc batch có thể vẫn chạy V1 dù HTTP service đã nâng lên V2.

Trong giai đoạn chuyển tiếp, một yêu cầu có thể đi qua V2, nhưng bản ghi được tạo từ V1; ngược lại V1 có thể đọc dữ liệu do V2 vừa ghi. Các sự kiện bất đồng bộ do V2 phát ra cũng có thể được V1 xử lý. Vì vậy, chỉ kiểm thử V2 với schema mới và bộ dữ liệu mới là chưa đủ.

~~~text
                 Load balancer
                       |
            +----------+----------+
            |                     |
        App V1 x 10            App V2 x 2
        (old JPA)              (new JPA)
            |                     |
            +----------+----------+
                       |
                  Shared DB
                 schema S1/S2
                       |
             +---------+---------+
             |                   |
         Job V1             Consumer V2
~~~

Tình huống tương tự xảy ra khi rollback: ứng dụng V1 được khởi động lại sau khi V2 đã tạo dữ liệu bằng một định dạng hoặc trạng thái mới. Do đó, cần phân biệt:

1. **Schema compatibility:** các câu SQL và mapping entity của từng phiên bản vẫn làm việc với schema sau migration.
2. **Data compatibility:** từng phiên bản hiểu và xử lý được mọi giá trị mà các phiên bản còn sống có thể ghi.
3. **Behavior compatibility:** các thao tác đồng thời không làm mất dữ liệu, vi phạm ràng buộc hoặc tạo kết quả trái hợp đồng.
4. **Operational compatibility:** migration, cache, transaction dài, background job, replication, rollback và feature flag hoạt động đúng trong giai đoạn chồng phiên bản.

Một thay đổi có thể tương thích về schema nhưng **không tương thích về dữ liệu**. Ví dụ thêm giá trị enum mới vào cột chuỗi thường không làm thay đổi bảng, nhưng V1 dùng @Enumerated(EnumType.STRING) có thể không đọc được giá trị mà V2 vừa ghi.

## 2. Lập ma trận phiên bản ứng dụng và phiên bản schema

Gọi:

- **A1** là ứng dụng hiện tại; **A2** là ứng dụng mới.
- **S1** là schema hiện tại; **S2** là schema mở rộng để hỗ trợ A2.
- **D1/D2** là dạng dữ liệu mà các phiên bản có thể tạo ra.

Một lộ trình an toàn thường đòi hỏi:

| Tổ hợp | Mục tiêu kiểm tra |
| --- | --- |
| A1 + S1 + D1 | Baseline đang chạy tốt trước migration |
| A1 + S2 + D1 | A1 vẫn chạy sau khi mở rộng schema |
| A2 + S2 + D1 | A2 đọc và xử lý được dữ liệu lịch sử |
| A2 + S2 + D2 | A2 xử lý dữ liệu do chính mình tạo |
| A1 + S2 + dữ liệu do A2 ghi | A1 vẫn đọc/ghi được trong cửa sổ rolling deployment |
| A1 và A2 đồng thời + S2 | Cạnh tranh ghi, transaction và side effect cùng tồn tại |
| Rollback từ A2 về A1 + S2 | A1 tiếp tục hoạt động với schema và dữ liệu đã bị thay đổi |

Ma trận này **không mặc định rằng A1 phải chạy với mọi schema tương lai**. Nó mô tả chính xác những cặp phiên bản được cam kết hỗ trợ trong từng giai đoạn triển khai. Chỉ triển khai migration phá tương thích sau khi đã xác nhận không còn A1 hoặc thành phần phụ thuộc A1.

Ví dụ, khi chuyển tên cột từ customer_name sang full_name, A1 còn dùng customer_name thì S2 **phải tiếp tục giữ customer_name**. Dù code A2 biên dịch và chạy được với full_name, việc xóa customer_name ngay lập tức sẽ làm A1 lỗi khi đọc/ghi.

## 3. Ba giai đoạn Expand → Migrate → Contract

Mô hình phổ biến cho thay đổi schema không gián đoạn là:

~~~text
S1 / A1
   |
   v
EXPAND: thêm schema mới, giữ nguyên khả năng đọc/ghi cũ
   |
   v
MIGRATE: triển khai A2 tương thích, backfill và chuyển luồng dùng dữ liệu
   |
   v
CONTRACT: xác nhận không còn phụ thuộc cũ, rồi bỏ cột/ràng buộc cũ
   |
   v
S3 / A3
~~~

### Giai đoạn Expand: thay đổi cộng dồn

Các thao tác thường phù hợp:

- Thêm cột **nullable**, có thể giữ giá trị null cho dữ liệu cũ.
- Thêm bảng mới mà phiên bản cũ chưa sử dụng.
- Thêm chỉ mục bằng phương pháp ít khóa phù hợp với DBMS và phiên bản đang chạy.
- Thêm một dạng dữ liệu hay cột song song để chuẩn bị thay thế cột cũ.
- Bổ sung cấu hình và logic tương thích nhưng chưa bật hành vi mới.

**Không nên** ngay lập tức xóa/đổi tên cột mà A1 đang đọc, đổi kiểu dữ liệu theo hướng A1 không hiểu hoặc thêm NOT NULL không có giá trị phù hợp cho các lệnh INSERT của A1.

### Giai đoạn Migrate: chuyển dữ liệu và hành vi

Sau khi schema đã sẵn sàng, triển khai A2 với cơ chế đọc/ghi tương thích. Backfill dữ liệu cũ theo batch, quan sát tiến độ và xử lý các bản ghi thay đổi trong lúc backfill. Khi mọi ứng dụng đã lên A2, mới chuyển sang logic chỉ đọc dữ liệu mới nếu không còn đường ghi cũ.

### Giai đoạn Contract: dọn hợp đồng cũ

Khi đã xác minh **không còn ứng dụng, job, consumer, migration script, truy vấn báo cáo hoặc quy trình rollback cần cột cũ**, mới dừng ghi dữ liệu cũ và xóa cấu trúc không sử dụng. Contract thường được thực hiện ở một lần phát hành sau, không gộp cùng bước Expand.

Độ dài mỗi giai đoạn phụ thuộc quy mô hệ thống và khả năng rollback. Đây là **quy trình thay đổi hợp đồng**, không đơn thuần là ba migration SQL.

## 4. Ví dụ xuyên suốt: đổi tên cột khi V1 và V2 cùng hoạt động

Giả sử bảng orders có cột customer_note:

~~~sql
-- Schema ban đầu
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_note VARCHAR(500),
    created_at TIMESTAMP NOT NULL
);
~~~

V1 mapping:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;

    @Column(name = "customer_note", length = 500)
    private String customerNote;

    // các thuộc tính khác và accessor
}
~~~

Yêu cầu mới là đổi thành delivery_note và về sau bỏ customer_note. Nếu dùng:

~~~sql
ALTER TABLE orders RENAME COLUMN customer_note TO delivery_note;
~~~

ngay trong đợt A2, A1 có thể lỗi vì SQL mà JPA provider sinh ra vẫn tham chiếu customer_note. Thay vào đó, triển khai từng pha.

### Bước 1. Expand schema

Ví dụ PostgreSQL:

~~~sql
ALTER TABLE orders
    ADD COLUMN delivery_note VARCHAR(500);
~~~

Đừng sửa hoặc xóa customer_note. Cột mới cho phép null để các INSERT của A1 vẫn hợp lệ.

### Bước 2. Phiên bản tương thích vẫn coi cột cũ là nguồn chuẩn

A2 có thể mapping cả hai cột trong một entity:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;

    @Column(name = "customer_note", length = 500)
    private String customerNote;

    @Column(name = "delivery_note", length = 500)
    private String deliveryNote;

    public String getEffectiveNote() {
        return customerNote;
    }

    public void updateNoteDuringTransition(String value) {
        this.customerNote = value;
        this.deliveryNote = value;
    }

    // các thuộc tính khác và accessor
}
~~~

Trong cửa sổ A1/A2 cùng chạy, **customer_note vẫn là nguồn chuẩn**, vì A1 chỉ ghi được cột đó. A2 tiếp tục đọc customer_note và cập nhật cả hai cột khi thực hiện nghiệp vụ thay đổi ghi chú. Đoạn ví dụ giả định đường cập nhật ghi chú của A2 gọi updateNoteDuringTransition; mọi đường ghi khác cần tuân thủ cùng quy tắc.

**Điểm dễ sai:** nếu A2 đọc ưu tiên delivery_note ngay trong khi A1 vẫn có thể cập nhật customer_note, A2 sẽ trả về dữ liệu cũ vì delivery_note chưa được cập nhật. Việc dual-write chỉ ở A2 không tự đồng bộ được các lệnh ghi từ A1.

Trong trường hợp không thể dùng customer_note làm nguồn chuẩn suốt giai đoạn overlap, phải có cơ chế đồng bộ đáng tin cậy (ví dụ trigger có semantics và kiểm thử rõ ràng, hoặc CDC có xử lý thứ tự sự kiện) hay giới hạn đồng thời ghi theo cách đã được chấp nhận. Hai chiều đồng bộ không có kiểm soát có thể tạo vòng lặp hoặc ghi đè dữ liệu.

### Bước 3. Backfill sau khi đã xác định nguồn chuẩn

Trong thời gian overlap, có thể backfill delivery_note từ customer_note theo batch. Tuy nhiên, A1 vẫn có thể thay đổi customer_note sau một batch backfill; kết quả này chỉ là một snapshot tạm thời.

Ví dụ PostgreSQL để minh họa một batch giới hạn theo khóa:

~~~sql
UPDATE orders
SET delivery_note = customer_note
WHERE id >= :from_id
  AND id < :to_id;
~~~

Đây là bản SQL minh họa để chạy thông qua cơ chế bind parameter của job migration. Trong production, cần quy định commit từng batch, kiểm soát tốc độ, kiểm tra khóa, retry và đảm bảo không ghi đè các thay đổi mới hơn một cách sai lệch. Nếu dữ liệu tiếp tục thay đổi, cần có đợt đồng bộ cuối sau khi mọi A1 đã dừng ghi.

### Bước 4. Chuyển nguồn đọc sau khi V1 đã ngừng hoạt động

Khi xác nhận không còn A1 và mọi đường ghi đã sử dụng A2 trở lên:

1. Ngăn đường ghi cũ hoạt động trở lại ngoài kế hoạch (job cũ, rollback ngoài cửa sổ, client phụ thuộc).
2. Đồng bộ lần cuối các giá trị customer_note sang delivery_note theo chính sách đã định.
3. Kiểm tra giá trị hai cột, xử lý bản ghi bất thường và độ trễ job.
4. Bật phiên bản/feature flag đọc delivery_note.
5. Quan sát lỗi và chênh lệch trước khi bỏ cột cũ.

Đường đọc mới có thể là:

~~~java
public String getEffectiveNote() {
    return deliveryNote;
}
~~~

Khi chuyển, đừng để một A2 cũ còn đọc customer_note trong khi phiên bản mới đã ngừng ghi cột đó, trừ khi có cơ chế giữ hai cột đồng bộ cho tới khi A2 cũ được rút hết.

### Bước 5. Contract

Chỉ sau khi thời hạn rollback V1 kết thúc, tất cả thành phần đã chuyển đọc/ghi delivery_note và dữ liệu đã được đối soát mới dùng migration:

~~~sql
ALTER TABLE orders DROP COLUMN customer_note;
~~~

Cú pháp và đặc điểm khóa phụ thuộc DBMS. Thao tác này sẽ làm các binary còn tham chiếu customer_note lỗi; vì vậy phải là bước riêng với điều kiện rõ ràng.

## 5. Những thay đổi schema thường phá tương thích

| Thay đổi | Rủi ro khi V1 vẫn chạy | Hướng triển khai |
| --- | --- | --- |
| Thêm cột nullable | Thường ít ảnh hưởng, trừ SQL kiểu SELECT * và mapping đặc thù | Expand trước; kiểm tra câu native SQL và mapper |
| Thêm cột NOT NULL không default | INSERT của V1 thiếu giá trị sẽ lỗi | Thêm nullable, triển khai writers, backfill rồi siết constraint |
| Rename/drop cột | V1 phát sinh SQL với tên cũ | Thêm cột mới, bridge dữ liệu, contract sau |
| Đổi kiểu cột | Giá trị/mapping JDBC khác, dữ liệu có thể không chuyển được | Cột song song, chuyển đổi và đối soát |
| Giảm chiều dài VARCHAR hoặc precision | Ghi bị từ chối hoặc dữ liệu bị cắt/không hợp lệ | Quan sát dữ liệu thực; kiểm soát writer trước |
| Thêm unique constraint | Dữ liệu lịch sử trùng hoặc các phiên bản vẫn tạo trùng | Dọn dữ liệu, chỉnh tất cả writer, tạo constraint sau |
| Thêm foreign key | Ghi không còn hợp lệ nếu đường cũ tạo record mồ côi | Đối soát và đảm bảo writer tương thích |
| Đổi quy tắc default | V1 không truyền cột, kết quả mới có thể khác giả định cũ | Xác định rõ contract của mọi writer |
| Đổi tên bảng hoặc sequence | Entity mapping, native query, generator của V1 lỗi | Duy trì cả hai đường trong giai đoạn chuyển |
| Thêm/chỉnh index | Có thể giữ khóa lâu, ảnh hưởng latency | Chọn phương thức online phù hợp DBMS, quan sát lock |

Một số hành vi cần biết:

- Với Hibernate/JPA, **hạn chế để hbm2ddl.auto=update hoặc ddl-auto=update tự thay schema** trên nhiều instance khi production deploy. Nên có công cụ migration có lịch sử phiên bản và một bước chạy được kiểm soát.
- Trên PostgreSQL, CREATE INDEX CONCURRENTLY cho phép giảm mức khóa ghi so với CREATE INDEX thông thường nhưng có các điều kiện thực thi riêng, ví dụ không được chạy trong transaction block thông thường. Cần cấu hình Flyway/Liquibase hoặc migration runner phù hợp.
- Với Oracle, khả năng tạo index online, sửa cột và validate constraint phụ thuộc edition, version, kiểu bảng và cú pháp được hỗ trợ. Không dùng một script PostgreSQL nguyên văn trên Oracle.
- Một migration DDL có thể lấy lock hoặc gây recompile/reparse, dù thay đổi đó tương thích về mặt schema. Đánh giá cả khả năng thực thi trong thời gian hoạt động cao.

## 6. Tương thích JPA entity mapping và provider

### Thêm cột và mapping entity

A1 thường bỏ qua cột mới nếu chỉ chọn các cột entity đã mapping. Nhưng native query SELECT * hoặc mapping constructor theo thứ tự cột có thể nhạy với thứ tự/kiểu dữ liệu. Vì vậy cần kiểm tra cả các lệnh SQL thủ công, không chỉ repository dùng JPQL.

Trong A2, một field mới khai báo:

~~~java
@Column(name = "delivery_note")
private String deliveryNote;
~~~

chỉ hoạt động sau khi cột delivery_note đã tồn tại. Việc deploy A2 trước migration có thể khiến các lệnh SELECT/INSERT/UPDATE lỗi ngay cả khi code nghiệp vụ chưa sử dụng field mới, bởi provider có thể đưa field được mapping vào SQL.

### Enum lưu bằng STRING

~~~java
public enum PaymentStatus {
    PENDING, PAID, CANCELLED
}

@Enumerated(EnumType.STRING)
@Column(name = "status")
private PaymentStatus status;
~~~

Nếu A2 bổ sung REFUNDED và bắt đầu ghi trạng thái mới, A1 không định nghĩa REFUNDED có thể không hydrate entity được. Đây là lỗi **data compatibility** dù schema không đổi.

Quy trình an toàn: phát hành phiên bản có khả năng hiểu/đọc trạng thái mới (hoặc có chính sách unknown state rõ ràng), chờ các phiên bản cũ không còn hoạt động, sau đó mới bật feature tạo trạng thái mới. Với Java enum mapping mặc định của JPA, không thể giả định unknown string sẽ tự ánh xạ thành OTHER; phải có converter hoặc mô hình dữ liệu được thiết kế cho hành vi đó.

Tránh dùng @Enumerated(EnumType.ORDINAL) khi danh sách enum có thể thêm, xóa hoặc đổi thứ tự. Đổi thứ tự có thể khiến cùng một giá trị integer mang ý nghĩa khác nhau giữa hai phiên bản.

### Renaming entity, table hoặc quan hệ

Đổi tên class Java không nhất thiết làm đổi tên bảng nếu @Table và @Column được chỉ định ổn định. Ngược lại, đổi naming strategy hoặc provider có thể làm thay đổi SQL được sinh ra nếu dựa vào tên ngầm định. Cần so sánh schema mà các phiên bản thực sự sử dụng.

Khi tách bảng hay quan hệ, không chỉ so sánh cột đơn. Phải xét cascade, orphanRemoval, FetchType, unique constraint, join column và đường ghi vào bảng liên kết. A2 thay đổi cách cascade delete trong khi A1 vẫn đọc quan hệ có thể dẫn đến dữ liệu biến mất ngoài dự kiến.

### @Version và optimistic locking

~~~java
@Version
@Column(name = "row_version")
private long version;
~~~

Optimistic locking hữu ích để tránh lost update khi các writer đều tuân thủ điều kiện version. Nhưng **thêm @Version vào chỉ A2 không bảo vệ khỏi A1**, vì A1 có thể UPDATE không kiểm tra/tăng row_version. Nếu yêu cầu concurrency thay đổi, hãy thiết kế quá trình nâng cấp sao cho mọi writer đang hoạt động cùng tuân thủ một cơ chế kiểm soát tương thích, hoặc dùng biện pháp bảo vệ ở DB phù hợp.

Việc thêm một cột version không null cho các bản ghi cũ cần khởi tạo giá trị và ràng buộc đúng thứ tự. Test cả update entity cũ, batch update và native SQL vì các câu UPDATE trực tiếp không nhất thiết tham gia cơ chế @Version của JPA.

### Entity lifecycle, converter và fetch behavior

Sự khác biệt giữa provider/version Hibernate, EclipseLink, JDBC driver hoặc cấu hình bytecode enhancement có thể làm thay đổi SQL, lazy loading, flush timing và cách converter xử lý null. Khi nhiều phiên bản cùng chạy, phải đối chiếu hành vi đọc/ghi và transaction dựa trên DBMS thực; không coi việc compile thành công là bằng chứng tương thích.

## 7. Dữ liệu mới phải được phiên bản cũ hiểu

Ngay cả khi không đổi schema, việc sửa **ngữ nghĩa** của một cột có thể gây vấn đề:

- Đổi đơn vị từ cents sang dollars hoặc từ milliseconds sang seconds.
- Đổi cách biểu diễn timezone, thời gian hết hạn hoặc boolean.
- Đổi các mã trạng thái và cách tính tổng tiền.
- Đổi cấu trúc JSON lưu trong một cột mà V1 vẫn parse.
- Đổi ý nghĩa của NULL, chuỗi rỗng và default.
- Đổi chiến lược sinh ID khiến V1 giả định sai thứ tự hoặc uniqueness.

Ví dụ nếu V2 ghi tổng tiền theo đơn vị cents vào cột mà V1 hiểu là dollars, cả V1 và V2 vẫn SELECT/UPDATE được, nhưng **kết quả nghiệp vụ sai**. Với thay đổi như vậy, nên thêm cột mới có tên mang đơn vị, chuyển đổi ở ranh giới và áp dụng Expand–Migrate–Contract.

Đối với JSON có schema riêng, có thể bổ sung trường optional mà V1 bỏ qua nếu parser được cấu hình như vậy; không được giả định mọi decoder cũ đều chấp nhận trường mới. Nếu cần thay đổi không tương thích, dùng version field trong payload hoặc cấu trúc song song và chuyển reader/writer theo giai đoạn.

## 8. Tương thích giao dịch khi V1 và V2 cạnh tranh ghi

Hai phiên bản có thể chạy thành công từng thao tác nhưng lỗi khi thao tác đồng thời:

~~~text
T1 (A1): SELECT stock = 10
T2 (A2): SELECT stock = 10
T1 (A1): UPDATE stock = 9
T2 (A2): UPDATE stock = 8
~~~

Nếu cả hai thao tác đọc–sửa–ghi không kiểm soát cạnh tranh, kết quả cuối có thể không phản ánh đầy đủ các hành động đã thực hiện. Không thể giải quyết chỉ bằng việc thêm field mới hoặc thay đổi Repository.

Các lựa chọn tùy yêu cầu:

1. **Atomic SQL update**: UPDATE inventory SET stock = stock - :amount WHERE id = :id AND stock >= :amount; kiểm tra số hàng cập nhật.
2. **Optimistic locking**: dùng version hoặc điều kiện so sánh trước khi UPDATE; mọi writer phải tuân thủ.
3. **Pessimistic locking**: SELECT ... FOR UPDATE hoặc LockModeType.PESSIMISTIC_WRITE; xác định thứ tự khóa, timeout và isolation.
4. **Serialization ở cấp nghiệp vụ**: phân vùng tác vụ theo khóa, hàng đợi hoặc ownership để giảm ghi đồng thời.

Việc chọn giải pháp phải dựa trên yêu cầu consistency. Ví dụ atomic SQL có thể tương thích giữa các phiên bản nếu V1 và V2 đều dùng cùng câu UPDATE, nhưng một phiên bản còn lưu entity managed cũ rồi flush toàn bộ bản ghi về cuối transaction có thể ghi đè thay đổi từ câu UPDATE khác. Phải kiểm tra persistence context, bulk update và lệnh flush.

### Các hiện tượng cần thử

| Hiện tượng | Kiểm tra thực tế |
| --- | --- |
| Lost update | Hai phiên bản sửa cùng một dòng và commit khác thứ tự |
| Deadlock | Hai transaction lấy khóa theo thứ tự khác nhau |
| Unique race | Hai instance cùng tạo bản ghi với khóa nghiệp vụ giống nhau |
| Phantom/read skew | Truy vấn lặp giữa các transaction theo isolation hiện hành |
| Lock wait/timeout | Migration hoặc batch làm tăng thời gian chờ ghi |
| Write skew | Hai giao dịch riêng đều quan sát điều kiện còn đúng rồi cập nhật các dòng khác nhau |
| Retry duplicate side effect | Một request bị retry sau khi DB commit nhưng client chưa nhận response |

Cần chỉ rõ isolation dùng ở production, đặc biệt sự khác biệt giữa mặc định của PostgreSQL và Oracle. Kết quả ở H2 hoặc database in-memory không đại diện đầy đủ cho hệ DBMS đang vận hành.

## 9. Migration data khi ứng dụng vẫn ghi liên tục

Backfill có thể chạy lâu hàng giờ với bảng lớn. Nếu migration đọc một bản ghi rồi cập nhật sau đó, dữ liệu có thể đã được A1/A2 sửa trong khoảng giữa.

Ví dụ nguy cơ:

~~~text
12:00 Migration đọc customer_note = "A"
12:01 A1 ghi customer_note = "B"
12:02 Migration ghi delivery_note = "A"
~~~

Nếu V2 đã xem delivery_note là nguồn chuẩn, hệ thống mất cập nhật B trên đường đọc mới. Để tránh:

- Xác định cột nào là nguồn chuẩn trong từng pha.
- Không chuyển reader sang cột mới cho đến khi mọi writer cũ đã ngừng và phần đồng bộ cuối đạt yêu cầu.
- Dùng batch nhỏ với checkpoint tiến độ theo khóa ổn định, giới hạn thời gian transaction và theo dõi số hàng lỗi.
- Thiết kế job idempotent để retry an toàn; phân biệt backfill, cập nhật mới và xóa dữ liệu.
- Nếu chuyển đổi phức tạp, dùng change capture, trigger hoặc event log với thứ tự và cơ chế xử lý xung đột được thiết kế trước.
- Đối soát kết quả bằng count, null count, checksum hoặc truy vấn so sánh theo từng nhóm; xét dữ liệu vẫn chuyển động trong lúc đo.

Nếu migration cần thay đổi từng dòng theo logic application, sử dụng một worker kiểm soát rate limit, batch size, transaction và visibility thay vì bắt tất cả instance khởi động đều tự chạy. Đảm bảo có phương án tạm dừng và tiếp tục từ checkpoint.

### SQL phát hiện chênh lệch sau khi đã đóng đường ghi cũ

Ví dụ trên PostgreSQL:

~~~sql
SELECT COUNT(*) AS mismatch_count
FROM orders
WHERE customer_note IS DISTINCT FROM delivery_note;
~~~

IS DISTINCT FROM xử lý so sánh NULL theo cách rõ ràng trong PostgreSQL. Với Oracle, tùy phiên bản và khả năng SQL, cần dùng biểu thức tương đương hỗ trợ NULL (chẳng hạn điều kiện riêng cho cả hai trường hợp một bên NULL) hoặc công cụ đối soát trong ứng dụng; không giả định tất cả DBMS hỗ trợ cùng cú pháp.

Nếu dữ liệu cần transform (ví dụ trim, normalize Unicode, chuyển đơn vị), đối soát theo **quy tắc chuyển đổi đã định nghĩa**, không bắt buộc so sánh chuỗi gốc từng byte.

## 10. Tương thích khi phát hành tính năng mới bằng feature flag

Feature flag giúp tách thời điểm **deploy code** khỏi thời điểm **đổi hành vi có thể tạo dữ liệu mới**.

Một quy trình:

~~~text
S2 được migrate trước
      |
Deploy A2 (đọc/ghi dữ liệu cũ tương thích)
      |
Quan sát A1 và A2 hoạt động cùng nhau
      |
100% A1 + job A1 đã dừng
      |
Hoàn thành backfill/đối soát
      |
Bật đọc mới -> bật ghi dữ liệu mới nếu contract cho phép
      |
Theo dõi -> bỏ đường cũ ở release sau
~~~

Các flag thường gặp:

- read_new_column: chọn dữ liệu từ cột mới sau khi đủ điều kiện.
- emit_new_status: bật việc ghi thêm giá trị enum mới.
- use_new_query: chuyển truy vấn sang chiến lược mới.
- require_new_field: áp dụng validation mới khi mọi writer đã nâng cấp.

Không nên dùng flag như giải pháp duy nhất cho một migration không tương thích. Nếu nhiều instance có trạng thái flag khác nhau, phải kiểm tra **khả năng cùng tồn tại của chính các trạng thái flag đó**. Cần xét cả độ trễ cập nhật cấu hình và việc rollback flag khi dữ liệu mới đã được ghi.

## 11. Kiểm tra background job, cache và message

### Background job và consumer

Một lỗi vận hành thường gặp là đã nâng HTTP API lên V2 nhưng vẫn còn:

- scheduled task V1 chạy trên pod chưa bị dừng;
- consumer V1 chưa được nâng hoặc vẫn tiêu thụ message mới;
- batch V1 chạy theo lịch hàng đêm;
- ETL/reporting query tham chiếu cột cũ;
- công cụ quản trị bên ngoài ghi trực tiếp vào bảng.

Mọi thành phần này đều là **writer/reader có thể tạo phụ thuộc tương thích**. Trước Contract, inventory cần bao gồm cả job và truy vấn ngoài service chính.

### Cache cấp ứng dụng và second-level cache của JPA

Nếu V1/V2 dùng chung cache keys, Redis keys hoặc Hibernate second-level cache, đổi format object, serializer hay region name có thể khiến phiên bản cũ không deserialize được. Hai phiên bản Hibernate khác nhau cũng có thể không được hỗ trợ cùng chia sẻ cơ chế cache nội bộ.

Giải pháp là xác định hợp đồng cache, version key/prefix hoặc tách region khi định dạng không tương thích, bảo đảm TTL/invalidation và quan sát miss rate. Một bản ghi đã update trên DB nhưng còn cache cũ có thể làm kiểm thử chỉ trên JPA Repository đánh giá sai.

### Message, event và outbox

Sự kiện CustomerUpdated do V2 phát ra có thể được consumer V1 đọc. Cần đánh giá cùng các vấn đề data compatibility: field mới, enum mới, thay đổi ý nghĩa, serialization và khả năng retry.

Outbox giúp gắn ghi bản ghi nghiệp vụ và ghi sự kiện vào cùng transaction DB, nhưng **không tự tạo tương thích schema message**. Trong quá trình rolling release, publisher và consumer cần chấp nhận các phiên bản sự kiện cùng tồn tại, có idempotency key và quy tắc xử lý trùng.

## 12. Lập kiểm thử tương thích thực tế

Nên có môi trường kiểm thử chạy **đồng thời** binary A1 và A2 trên cùng một database đã áp dụng S2. Dùng database cùng loại và phiên bản chính với production; Testcontainers hỗ trợ nhiều trường hợp cho integration test, nhưng kiểm thử online DDL hoặc môi trường Oracle thực có thể cần hạ tầng riêng.

### Bộ test tối thiểu

1. **Baseline:** A1 trên S1 đọc/ghi bình thường.
2. **Schema expand:** áp dụng S2 khi A1 đang hoạt động; tiếp tục chạy các đường ghi, truy vấn, background job A1.
3. **New app with legacy data:** A2 trên S2 phải đọc/ghi được bản ghi tạo bởi A1.
4. **Old app with new writes:** sau khi A2 ghi, A1 phải xử lý được mọi dữ liệu nằm trong phạm vi hỗ trợ.
5. **Concurrent mixed writes:** A1/A2 cùng update các dòng quan trọng; kiểm tra transaction, lock, uniqueness, retry và event.
6. **Backfill while live:** thêm dữ liệu và cập nhật giữa các batch; dừng/chạy lại backfill; kiểm tra không mất cập nhật.
7. **Rollback:** đưa traffic về A1 với S2 và dữ liệu đã ghi bởi A2; đo lỗi và side effect.
8. **Contract gate:** xác minh bằng telemetry rằng không còn query, service, job hay rollback path dùng schema cũ trước khi xóa.

Ví dụ một kịch bản test mức hệ thống:

~~~text
Arrange:
  - Khởi động database S1 và App A1
  - Tạo order #101 với customer_note = "old"
Act:
  - Chạy migration Expand sang S2 trong lúc A1 vẫn hoạt động
  - Khởi động A2 cạnh A1
  - Gửi update qua A1: customer_note = "from-v1"
  - Đọc qua A2, phải nhìn thấy "from-v1"
  - Gửi update qua A2: customer_note = "from-v2"
  - Đọc qua A1, phải nhìn thấy "from-v2"
  - Dừng A1, chạy backfill cuối, bật read_new_column
Assert:
  - Không có lỗi SQL thiếu cột hoặc deserialize
  - Không có trạng thái ghi chú bị lùi do backfill
  - Dữ liệu và thứ tự event đúng hợp đồng
  - Phân tích các request lỗi và lock/timeout
~~~

Đây là kịch bản phối hợp nhiều service, không thể thay bằng unit test mock Repository.

### Một mẫu test JPA hẹp để nhận diện lỗi entity

~~~java
@DataJpaTest
class OrderJpaMappingTest {

    @Autowired
    private TestEntityManager em;

    @Test
    void canPersistAndReadLegacyFields() {
        OrderEntity order = new OrderEntity();
        order.setId(101L);
        order.setCustomerNote("legacy");

        em.persistAndFlush(order);
        em.clear();

        OrderEntity reloaded = em.find(OrderEntity.class, 101L);
        assertThat(reloaded.getCustomerNote())
            .isEqualTo("legacy");
    }
}
~~~

Ví dụ dùng Spring Boot test API và giả định các phương thức accessor, ID assignment, entity mapping đã được khai báo phù hợp với ứng dụng. @DataJpaTest cần được cấu hình sử dụng DBMS mục tiêu nếu muốn kiểm tra hành vi vendor. Test này chỉ xác nhận một đường mapping ở một phiên bản; bộ test hỗn hợp A1/A2 ở trên mới kiểm tra khả năng vận hành nhiều phiên bản cùng lúc.

### Ma trận kiểm thử theo hướng đọc/ghi

| Writer | Reader | Trường hợp kiểm thử |
| --- | --- | --- |
| A1 | A1 | Không thoái lui nghiệp vụ cũ |
| A1 | A2 | A2 hiểu dữ liệu lịch sử và cập nhật mới từ A1 |
| A2 | A1 | A1 không lỗi khi đọc dữ liệu A2 tạo |
| A2 | A2 | Tính năng mới đúng sau migration |
| Backfill | A1/A2 | Job không làm hỏng dữ liệu đang được cập nhật |
| A1 và A2 | A1/A2 | Concurrency, uniqueness, optimistic/pessimistic locking |
| A2 trước rollback | A1 sau rollback | Dữ liệu và trạng thái mới không khiến A1 mất khả năng phục vụ |

Khi có nhiều DBMS được hỗ trợ, lặp lại các kiểm thử quan trọng theo từng DBMS/dialect; test trên H2 không xác nhận được concurrency, schema lock hoặc SQL dialect của PostgreSQL/Oracle.

## 13. Cổng kiểm tra trước khi triển khai

Cần định nghĩa **điều kiện đạt** ở mỗi điểm chuyển giai đoạn, thay vì chỉ dựa vào việc migration tool chạy thành công.

### Trước Expand

- Đã có danh sách các phiên bản ứng dụng và job còn hoạt động, cùng thời gian rolling/rollback dự kiến.
- Đã liệt kê các câu truy vấn native SQL, entity mapping, job ETL và schema object bị ảnh hưởng.
- Migration có bước chạy xác định, quyền truy cập phù hợp và phương án xử lý lỗi.
- Đã đánh giá lock, kích thước bảng, thời gian backfill và cách quan sát database.
- Đã xác nhận A1 chạy được trên schema mở rộng trong thử nghiệm.

### Trước bật hành vi mới

- Tất cả reader/writer còn hoạt động tương thích với định dạng và giá trị mà hành vi mới có thể tạo ra.
- Backfill hoàn tất theo tiêu chí đã định nghĩa; chênh lệch dữ liệu còn lại đã được xử lý.
- Đã kiểm tra traffic qua A1/A2 đồng thời và lỗi xử lý transaction/event.
- Có thể tắt feature flag mà không vi phạm nghĩa dữ liệu hoặc đã xác định giới hạn rollback.

### Trước Contract

- Không còn instance, consumer, batch hoặc ứng dụng bên ngoài cần schema cũ.
- Cửa sổ rollback về A1 đã đóng, hoặc có kế hoạch phục hồi dữ liệu/schema được kiểm chứng.
- Metrics/logs cho thấy đường truy vấn cũ không còn được sử dụng qua một khoảng quan sát phù hợp.
- Đã có bản sao lưu và phương án restore; thời gian khôi phục thỏa mục tiêu vận hành.
- Đã thử migration phá tương thích trên dữ liệu có quy mô và phân bố gần production.

Contract nên là một thay đổi rõ ràng với tiêu chí triển khai riêng, thường ở bản phát hành tiếp theo.

## 14. Quan sát thực tế trong lúc rolling deployment

Các dấu hiệu nên theo dõi theo **app_version** và **schema/migration version** nếu hệ thống có nhãn:

| Nhóm quan sát | Tín hiệu |
| --- | --- |
| SQL/JPA | SQLGrammarException, lỗi missing column/table, mapping/conversion exception |
| Giao dịch | deadlock, serialization failure, optimistic lock conflict, transaction timeout |
| Hiệu năng | p95/p99 DB latency, số connection chờ, thời gian giữ lock, slow query |
| Dữ liệu | số dòng chưa backfill, mismatch giữa cột cũ/mới, dữ liệu null bất thường |
| Ghi | unique constraint violation, foreign key violation, conflict/retry rate |
| Xử lý nền | consumer lag, retry/dead-letter message, job chạy từ phiên bản cũ |
| Triển khai | tỷ lệ instance A1/A2, tỷ lệ traffic theo version, thời gian kết thúc job cũ |

Nên đo trên cùng một khoảng thời gian trước/sau thay đổi, kết hợp log và distributed tracing để thấy lỗi đến từ version nào. Một metric tổng hợp có thể che giấu việc A2 lỗi 100% nhưng mới nhận 1% traffic.

Khi phát hiện sai lệch, dừng rollout và phân loại lỗi:

- **Code lỗi nhưng schema vẫn tương thích:** có thể quay traffic về A1 nếu A1 hiểu dữ liệu A2 đã ghi.
- **Dữ liệu mới không tương thích với A1:** rollback binary đơn thuần có thể làm tình hình xấu hơn; cần tắt đường tạo dữ liệu mới và thực hiện kế hoạch phục hồi/đồng bộ.
- **DDL phá tương thích đã chạy:** rollback code không khôi phục cột hay dữ liệu bị xóa; phải theo kế hoạch migration phục hồi đã được chuẩn bị, nếu khả thi.

## 15. Các trường hợp đặc biệt trong vận hành

### Deploy nhiều vùng hoặc nhiều cụm

Blue-green deployment không đảm bảo hai môi trường tách biệt nếu vẫn dùng cùng DB. Một cụm xanh đã chạy A2 có thể phát sinh trạng thái mà cụm lam A1 không đọc được. Cần xem mọi môi trường chia sẻ nguồn dữ liệu như các version writer/reader trong cùng ma trận.

### Replica và độ trễ replication

Nếu hệ thống đọc từ read replica, cần xét replica đã áp dụng schema migration và dữ liệu mới đến đâu. Một instance A2 ghi primary rồi lập tức đọc replica có thể thấy dữ liệu cũ. Cần xác định read-your-writes, routing và giới hạn lag; migration công cụ chỉ báo thành công trên primary chưa chứng minh mọi đường đọc đã sẵn sàng.

### Long-running transaction và connection pool

Transaction kéo dài có thể giữ snapshot/lock hoặc tiếp tục dùng prepared statement/schema metadata đã cache trong connection. Khi thay schema lớn, cần đánh giá thời gian giao dịch, cache prepared statement, việc recycle connection và restart job phù hợp. Không dựa vào việc tất cả request HTTP đã kết thúc để kết luận worker và transaction nền đã dừng.

### Sequence và chiến lược sinh khóa

Khi đổi @GeneratedValue(strategy = ...), sequence allocationSize hay table generator, V1 và V2 có thể cấp ID theo các quy tắc khác nhau. Cần kiểm tra uniqueness và vùng giá trị của mọi writer. Một batch V2 dùng pooled sequence không bảo đảm tương thích nếu V1 tự tính ID theo MAX(id) + 1 hoặc một generator cũ dùng sequence khác.

### Thay đổi version của Hibernate

Nâng Hibernate/JPA provider có thể thay SQL được sinh, tên alias, xử lý batch, kiểu JSON/time hoặc default naming strategy. Trong quá trình rolling upgrade, V1 và V2 dùng hai provider version với cùng schema; vì thế cần kiểm tra mapping, SQL chạy thực tế và data compatibility tương tự như khi đổi ứng dụng.

## 16. Quy trình áp dụng cho một thay đổi mới

Ví dụ đội phát triển muốn thêm cột normalized_email và sau đó chuyển unique constraint từ email sang normalized_email:

1. **Định nghĩa yêu cầu:** quy tắc normalize email, độ dài, xử lý null, collation và tính duy nhất có khác email cũ không?
2. **Inventory:** xác định API, batch, report, consumer và mọi phiên bản còn ghi email.
3. **Expand:** thêm normalized_email nullable, chưa áp UNIQUE mới nếu dữ liệu lịch sử còn trùng theo quy tắc normalize.
4. **Deploy reader/writer tương thích:** mọi phiên bản đang hoạt động tiếp tục truy cập email cũ; bản mới có thể shadow-write normalized_email và ghi log chênh lệch.
5. **Backfill:** tính normalized_email theo batch, xác định trùng và xử lý ngoại lệ có chủ đích.
6. **Đóng đường ghi cũ:** nâng hết writer; chạy đồng bộ cuối để normalized_email không bỏ sót cập nhật.
7. **Bật hành vi mới:** chuyển các truy vấn/validation sang normalized_email, có cơ chế theo dõi race/unique conflict.
8. **Siết constraint:** chỉ khi dữ liệu và mọi writer bảo đảm quy tắc mới; kiểm soát đặc điểm lock của DBMS.
9. **Contract:** bỏ logic và chỉ mục cũ sau khi hết cửa sổ rollback và tất cả downstream đã đổi.

Điểm quan trọng là **tính tương thích phải được đo bằng các tổ hợp phiên bản thực sự tồn tại trong thời gian triển khai**, gồm cả dữ liệu, transaction và các công việc nền. Với JPA, entity mapping chạy đúng trên schema mới chỉ là bước đầu; thay đổi chỉ an toàn khi phiên bản cũ và mới có thể cùng đọc/ghi mà vẫn bảo toàn ý nghĩa nghiệp vụ, và việc bỏ hợp đồng cũ diễn ra sau một cổng xác minh riêng.

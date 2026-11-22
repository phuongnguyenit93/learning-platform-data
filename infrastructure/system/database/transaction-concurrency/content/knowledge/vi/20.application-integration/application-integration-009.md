# Thứ tự cập nhật hàng do ORM phát sinh và ảnh hưởng đến bế tắc

ORM giúp ứng dụng làm việc với entity và object thay vì tự viết từng câu SQL. Khi transaction thay đổi nhiều entity, ORM thường theo dõi các thay đổi trong persistence context rồi phát sinh INSERT, UPDATE và DELETE vào thời điểm flush. Thứ tự các câu SQL được phát ra do ORM và cấu hình của nó quyết định; thứ tự gọi setter hoặc thứ tự duyệt collection trong Java không nhất thiết là thứ tự database nhận các câu UPDATE.

Nếu hai transaction cập nhật cùng một tập hàng nhưng theo thứ tự khác nhau, chúng có thể tạo ra deadlock. Ví dụ, T1 khóa hàng A rồi chờ hàng B, trong khi T2 khóa hàng B rồi chờ hàng A. Việc ORM sắp xếp UPDATE không nhất quán giữa các transaction có thể góp phần tạo ra tình huống này.

Để giảm nguy cơ, cần hiểu cách ORM flush thay đổi, quy tắc sắp xếp SQL của provider, cách database lấy lock và thứ tự tài nguyên mà toàn bộ ứng dụng sử dụng. Các giải pháp thường gồm:

- Thống nhất thứ tự truy cập tài nguyên trong mọi luồng nghiệp vụ.
- Khóa các hàng theo một thứ tự ổn định trước khi thay đổi entity.
- Dùng tính năng sắp xếp UPDATE theo khóa chính của ORM nếu provider hỗ trợ.
- Giữ transaction ngắn, kiểm tra execution plan và index, đồng thời xử lý deadlock bằng retry toàn bộ transaction khi phù hợp.

## 1. ORM không nhất thiết phát SQL ngay khi ứng dụng sửa entity

Với ORM theo mô hình Unit of Work như Hibernate/JPA, ứng dụng thường tải entity vào persistence context, thay đổi trạng thái object rồi để provider phát hiện thay đổi khi flush.

Ví dụ:

~~~java
@Transactional
public void renameProducts() {
    Product first = entityManager.find(Product.class, 10L);
    Product second = entityManager.find(Product.class, 20L);

    first.setName("Keyboard");
    second.setName("Mouse");

    // SQL UPDATE có thể chưa được gửi ngay tại đây.
}
~~~

Trong quá trình thực thi, ORM thường:

1. Theo dõi entity đã được tải hoặc đưa vào persistence context.
2. Phát hiện entity nào thay đổi (dirty checking).
3. Tạo các action cần thực hiện khi flush.
4. Sắp xếp hoặc nhóm các action theo quy tắc của provider.
5. Gửi SQL qua JDBC, có thể theo từng câu hoặc theo batch.
6. Database thực thi SQL và lấy lock cần thiết.

Flush có thể xảy ra khi transaction commit, khi ứng dụng gọi flush rõ ràng hoặc trước một truy vấn cần nhìn thấy các thay đổi đang chờ theo flush mode. Vì vậy, thời điểm và thứ tự SQL xuất hiện có thể khác với vị trí các lệnh thay đổi object trong mã Java.

Cần phân biệt ba thứ tự:

- **Thứ tự thay đổi object:** thứ tự ứng dụng gọi setter hoặc thao tác collection.
- **Thứ tự phát SQL:** thứ tự ORM gửi các câu INSERT/UPDATE/DELETE trong quá trình flush.
- **Thứ tự lấy lock nội bộ:** thứ tự database thực sự khóa hàng, index entry, page hoặc tài nguyên khác khi thực thi plan.

Thứ tự thứ nhất không bảo đảm hai thứ tự còn lại. Ngay cả khi ORM gửi UPDATE theo thứ tự khóa chính, database vẫn có thể truy cập thêm index, kiểm tra foreign key, chạy trigger hoặc lấy lock khác theo kế hoạch thực thi.

## 2. Deadlock xuất hiện khi các transaction lấy lock theo thứ tự khác nhau

Giả sử có hai hàng tài khoản:

| account_id | balance |
|---:|---:|
| 10 | 1.000.000 |
| 20 | 2.000.000 |

Hai transaction chuyển tiền theo hai chiều ngược nhau:

- T1 chuyển tiền từ tài khoản 10 sang 20.
- T2 chuyển tiền từ tài khoản 20 sang 10.

Nếu T1 cập nhật hàng 10 trước rồi hàng 20, trong khi T2 cập nhật hàng 20 trước rồi hàng 10, có thể xảy ra:

~~~text
Transaction T1                  Transaction T2
---------------                 ---------------
UPDATE account 10
Lấy lock trên hàng 10
                                UPDATE account 20
                                Lấy lock trên hàng 20
UPDATE account 20
Chờ lock của T2
                                UPDATE account 10
                                Chờ lock của T1

T1 chờ T2                      T2 chờ T1
       \                         /
        +------ DEADLOCK -------+
~~~

Database phát hiện chu trình chờ và chọn một transaction làm deadlock victim. Transaction bị chọn thường bị rollback; transaction còn lại có thể tiếp tục sau khi lock được giải phóng.

Deadlock không nhất thiết do hai câu UPDATE cùng một bảng. Nó có thể xảy ra giữa nhiều bảng, index, khóa ngoại, bảng liên kết many-to-many hoặc tài nguyên mà trigger truy cập.

## 3. Thứ tự trong mã Java có thể khác thứ tự UPDATE do ORM phát ra

Hãy xét một service thay đổi hai entity:

~~~java
@Transactional
public void changeTwoAccounts(Long firstId, Long secondId) {
    Account first = entityManager.find(Account.class, firstId);
    Account second = entityManager.find(Account.class, secondId);

    first.setStatus(AccountStatus.REVIEW);
    second.setStatus(AccountStatus.ACTIVE);
}
~~~

Một luồng gọi với firstId = 10, secondId = 20. Luồng khác gọi với firstId = 20, secondId = 10.

Có thể ứng dụng đã thay đổi entity theo hai thứ tự khác nhau. Tuy nhiên, ORM không bắt buộc phải phát UPDATE đúng theo thứ tự gọi setter. Provider có thể giữ action trong một hàng đợi nội bộ, nhóm theo entity type, hoặc sắp xếp trước khi gửi SQL.

Vì thế, không nên suy luận thứ tự lấy lock chỉ bằng cách đọc thứ tự các lệnh setter.

Một số yếu tố ảnh hưởng thứ tự SQL:

- Thứ tự entity được đưa vào persistence context.
- Cách provider thực hiện dirty checking.
- Action queue hoặc cơ chế Unit of Work của ORM.
- Cascade persist, merge, remove và orphan removal.
- Thứ tự xử lý collection và bảng liên kết.
- Cấu hình sắp xếp INSERT/UPDATE.
- Cấu hình JDBC batching.
- Các lần flush tự động trước truy vấn.
- Bulk JPQL hoặc native SQL được thực thi ngoài cơ chế dirty checking thông thường.

Chi tiết cụ thể phụ thuộc ORM và phiên bản. JPA định nghĩa hành vi persistence và flush ở mức API, nhưng không quy định một thứ tự UPDATE phổ quát để mọi provider phải phát SQL giống nhau.

## 4. Hibernate có thể sắp xếp UPDATE theo entity type và khóa chính

Hibernate cung cấp cấu hình provider-specific:

~~~properties
hibernate.order_updates=true
~~~

Khi bật, Hibernate sắp xếp các câu UPDATE theo entity type và khóa chính trước khi thực thi. Mục tiêu là:

- Tăng khả năng gom các câu UPDATE tương tự vào JDBC batch.
- Làm thứ tự cập nhật hàng ổn định hơn trong nhiều tình huống.
- Giảm khả năng các transaction cập nhật cùng tập hàng theo thứ tự đối nghịch.
- Giảm một số deadlock phát sinh từ thứ tự cập nhật không nhất quán.

Với Spring Boot và Hibernate, có thể cấu hình:

~~~properties
spring.jpa.properties.hibernate.order_updates=true
spring.jpa.properties.hibernate.jdbc.batch_size=50
~~~

Có thể cân nhắc thêm:

~~~properties
spring.jpa.properties.hibernate.order_inserts=true
~~~

Tùy workload, Hibernate có thể sắp xếp INSERT theo entity type và khóa chính để hỗ trợ batching. Cấu hình order_inserts không thay thế order_updates; hai thuộc tính áp dụng cho các loại action khác nhau.

Các điểm cần hiểu:

- Đây là cấu hình của Hibernate, không phải thuộc tính chuẩn của JPA.
- Sắp xếp UPDATE có thể phát sinh thêm chi phí sắp xếp trong bộ nhớ.
- Hiệu quả batching phụ thuộc số lượng câu lệnh cùng dạng, driver và cấu hình JDBC.
- Cấu hình không bảo đảm loại bỏ mọi deadlock.
- Cần xác nhận thứ tự SQL thực tế qua log hoặc công cụ quan sát của ứng dụng.

Hibernate thường mặc định không bật order_updates; hãy kiểm tra tài liệu và cấu hình đúng phiên bản đang sử dụng trước khi dựa vào giả định về mặc định.

## 5. Vì sao sắp xếp theo khóa chính giúp giảm deadlock?

Giả sử cả T1 và T2 đều cần cập nhật hai hàng có khóa chính 10 và 20.

Nếu mỗi transaction cập nhật theo thứ tự riêng:

~~~text
T1: 10 -> 20
T2: 20 -> 10
~~~

Hai transaction có thể khóa hàng đầu tiên rồi chờ hàng thứ hai, tạo chu trình chờ.

Nếu cả hai transaction đều cập nhật theo cùng thứ tự tăng dần:

~~~text
T1: 10 -> 20
T2: 10 -> 20
~~~

T1 có thể lấy lock hàng 10 trước. T2 chờ tại hàng 10 và chưa giữ lock hàng 20. Sau khi T1 cập nhật hàng 20 và commit, T2 tiếp tục lấy lock hàng 10 rồi hàng 20. Hai transaction vẫn phải chờ nhau, nhưng không hình thành chu trình chờ do hai hàng này theo thứ tự đã thống nhất.

Sơ đồ:

~~~text
T1                                  T2
|                                   |
|-- Lock row 10                     |-- Xin lock row 10
|                                   |   Chờ T1
|-- Lock row 20                     |
|-- COMMIT                          |
|                                   |-- Lấy lock row 10
|                                   |-- Lock row 20
|                                   |-- COMMIT
~~~

Đây là nguyên tắc **canonical lock ordering**: mọi transaction cần nhiều tài nguyên cùng loại phải lấy chúng theo một thứ tự toàn cục nhất quán.

Sắp xếp theo khóa chính là một cách phổ biến để tạo thứ tự đó. Có thể dùng một thứ tự khác, miễn mọi luồng nghiệp vụ tuân thủ cùng quy tắc.

## 6. Dùng Hibernate order_updates có đủ không?

Không. Cấu hình order_updates chỉ xử lý một phần thứ tự UPDATE do Hibernate quản lý. Deadlock vẫn có thể xuất hiện nếu các transaction:

- Cập nhật các entity type khác nhau theo thứ tự khác nhau.
- Cập nhật bảng cha và bảng con theo thứ tự không nhất quán.
- Thay đổi collection làm phát sinh INSERT/DELETE trong bảng liên kết.
- Kích hoạt trigger cập nhật thêm bảng khác.
- Vi phạm thứ tự lock qua foreign key hoặc unique index.
- Dùng native SQL hoặc bulk update ngoài action queue thông thường.
- Có locking read lấy lock trước khi flush.
- Truy cập các index hoặc phạm vi dữ liệu theo execution plan khác nhau.

Ví dụ, một transaction thực hiện:

~~~text
UPDATE account
UPDATE ledger
~~~

Trong khi transaction khác thực hiện:

~~~text
UPDATE ledger
UPDATE account
~~~

Ngay cả khi Hibernate sắp xếp các UPDATE của từng entity type, sự khác nhau giữa thứ tự truy cập hai loại tài nguyên vẫn có thể tạo deadlock.

Do đó, cần xác định thứ tự ở cấp nghiệp vụ và toàn bộ tài nguyên được truy cập, không chỉ một bảng.

## 7. Thiết kế thứ tự khóa ổn định trong ứng dụng

Một cách rõ ràng là sắp xếp ID trước khi lấy pessimistic lock. Với JPA, có thể dùng LockModeType.PESSIMISTIC_WRITE để yêu cầu provider lấy lock ghi trên từng entity.

Ví dụ chuyển tiền:

~~~java
@Transactional
public void transfer(
        Long sourceId,
        Long targetId,
        BigDecimal amount) {

    if (sourceId.equals(targetId)) {
        throw new IllegalArgumentException(
            "Source and target accounts must differ"
        );
    }

    List<Long> ids = Stream.of(sourceId, targetId)
        .sorted()
        .toList();

    Map<Long, Account> lockedAccounts = new HashMap<>();

    for (Long id : ids) {
        Account account = entityManager.find(
            Account.class,
            id,
            LockModeType.PESSIMISTIC_WRITE
        );

        if (account == null) {
            throw new AccountNotFoundException(id);
        }

        lockedAccounts.put(id, account);
    }

    Account source = lockedAccounts.get(sourceId);
    Account target = lockedAccounts.get(targetId);

    if (source.getBalance().compareTo(amount) < 0) {
        throw new InsufficientBalanceException();
    }

    source.debit(amount);
    target.credit(amount);
}
~~~

Cả hai chiều chuyển tiền đều lấy lock theo account ID tăng dần, dù source và target khác nhau. Sau khi lấy đủ lock, ứng dụng mới thực hiện kiểm tra và thay đổi số dư.

Ưu điểm:

- Thứ tự lấy lock được thể hiện rõ trong code.
- Mọi luồng chuyển tiền có thể dùng cùng một quy tắc.
- Không phụ thuộc vào thứ tự setter hoặc thứ tự duyệt collection.
- Có thể kiểm soát thời điểm lấy lock trước khi thay đổi entity.

Chi phí:

- Có thể phát sinh nhiều round trip nếu khóa từng entity riêng.
- Transaction phải giữ các lock đến khi kết thúc theo quy tắc của engine.
- Mọi use case khác cập nhật cùng tài khoản cũng cần tuân thủ cùng thứ tự nếu chúng khóa nhiều tài khoản.
- Phải xử lý account không tồn tại, trùng ID và retry deadlock/timeout.

JPA provider có thể ánh xạ PESSIMISTIC_WRITE thành SQL locking khác nhau tùy database. Cần kiểm tra SQL thực tế và loại lock được tạo ra.

### Có thể khóa nhiều dòng trong một truy vấn không?

Có thể dùng repository query với danh sách ID và thứ tự:

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id IN (10, 20)
ORDER BY account_id
FOR UPDATE;
~~~

Truy vấn này thường tiện hơn việc gửi nhiều câu SELECT riêng. Tuy nhiên, không nên giả định mọi database sẽ lấy lock vật lý đúng theo thứ tự hàng trả về chỉ vì có ORDER BY. Cách thực thi và quy tắc locking phụ thuộc engine, optimizer và isolation level. Nếu thứ tự lock là yêu cầu quan trọng, cần xác minh hành vi trên database đích bằng plan và thử nghiệm đồng thời.

Một số hệ thống có thể khóa từng dòng theo thứ tự định trước hoặc dùng stored procedure để tập trung quy tắc. Cách chọn cần cân bằng số round trip và mức bảo đảm về thứ tự.

## 8. Thứ tự khóa phải bao phủ nhiều loại tài nguyên

Trong nghiệp vụ phức tạp, transaction có thể cập nhật nhiều bảng:

- Account.
- Ledger entry.
- Transfer.
- Audit record.
- Account summary.

Cần định nghĩa một thứ tự truy cập thống nhất, chẳng hạn:

~~~text
1. Transfer request
2. Account rows (theo account_id tăng dần)
3. Ledger rows
4. Account summary
~~~

Mọi luồng nghiệp vụ cần cùng tuân thủ thứ tự này. Nếu một luồng khóa account trước rồi ledger, còn luồng khác khóa ledger trước rồi account, deadlock vẫn có thể xảy ra.

Thứ tự tài nguyên cần xét cả:

- Bảng và hàng được cập nhật trực tiếp.
- Bảng liên kết many-to-many.
- Index unique và foreign key.
- Trigger và stored procedure.
- Tài nguyên được lấy qua cascade.
- Khóa logic hoặc advisory lock.
- Các tài nguyên được giữ bởi transaction khác.

Một quy tắc hữu ích là định nghĩa lock hierarchy trong tầng service hoặc repository, rồi tái sử dụng thay vì để từng use case tự chọn thứ tự.

## 9. Flush timing có thể làm thay đổi thứ tự lấy lock

Một điểm dễ bỏ sót là Hibernate/JPA có thể flush trước khi chạy truy vấn tùy FlushModeType.

Ví dụ:

~~~java
@Transactional
public void updateAndRead(Long firstId, Long secondId) {
    Account first = entityManager.find(Account.class, firstId);
    first.setStatus(AccountStatus.REVIEW);

    // JPQL query có thể kích hoạt AUTO flush trước khi chạy.
    List<Account> accounts = entityManager.createQuery(
        "select a from Account a where a.status = :status",
        Account.class
    )
    .setParameter("status", AccountStatus.ACTIVE)
    .getResultList();

    Account second = entityManager.find(Account.class, secondId);
    second.setStatus(AccountStatus.REVIEW);
}
~~~

Nếu truy vấn cần nhìn thấy thay đổi đang chờ, provider có thể flush trước khi thực hiện query. UPDATE của hàng firstId vì thế có thể được gửi trước khi ứng dụng lấy các lock khác mà nó dự định lấy theo thứ tự.

Điều này đặc biệt quan trọng khi muốn áp dụng lock ordering thủ công.

Cách tổ chức an toàn hơn thường là:

1. Xác định toàn bộ tài nguyên cần khóa.
2. Sắp xếp tài nguyên theo thứ tự chung.
3. Lấy các lock cần thiết trước khi sửa entity.
4. Sau khi đã có lock, thực hiện kiểm tra và thay đổi object.
5. Flush/commit theo ranh giới transaction đã chọn.

Nếu persistence context đã có thay đổi chưa flush, một truy vấn tiếp theo có thể làm phát sinh SQL ngoài dự kiến. Cần thiết kế transaction sao cho không có pending update chen vào trước bước lấy lock theo thứ tự.

Không nên tùy tiện chuyển FlushModeType.AUTO sang COMMIT chỉ để né flush. Thay đổi flush mode có thể làm truy vấn không nhìn thấy thay đổi đang chờ theo cách ứng dụng mong muốn và làm thay đổi semantics. Hãy kiểm soát rõ thứ tự thao tác và kiểm tra hành vi của provider.

## 10. JDBC batching và thứ tự UPDATE

Hibernate có thể gom nhiều câu SQL cùng dạng thành JDBC batch khi cấu hình batch size:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_updates=true
~~~

Thay vì gửi từng câu UPDATE với một round trip riêng, provider có thể gom các câu lệnh tương tự rồi thực thi theo batch.

Ví dụ logic cập nhật 100 sản phẩm:

~~~text
Không batching:
    UPDATE product 1
    UPDATE product 2
    UPDATE product 3
    ...
    UPDATE product 100

Có batching:
    Batch 1: UPDATE product 1..50
    Batch 2: UPDATE product 51..100
~~~

Batching giảm số lần giao tiếp giữa ứng dụng và database. Khi kết hợp order_updates, các UPDATE tương tự có thể được nhóm và sắp xếp hiệu quả hơn.

Tuy nhiên:

- Batch không tạo ra transaction độc lập cho từng câu; transaction boundary vẫn do ứng dụng quản lý.
- Lock đã lấy trong transaction thường vẫn được giữ đến commit/rollback theo quy tắc lock của engine.
- Batch không tự giải quyết deadlock do các bảng, index hoặc trigger khác.
- JDBC driver và database có thể thực thi batch theo chi tiết riêng.
- Cần kiểm tra generated SQL, thứ tự batch và số lượng batch thực tế.

Nếu batch quá lớn, transaction có thể giữ nhiều lock lâu và làm tăng cạnh tranh. Nếu quá nhỏ, overhead round trip vẫn cao. Nên đo theo workload thực tế.

## 11. Bulk update và native SQL nằm ngoài thứ tự dirty checking thông thường

JPQL bulk update, native SQL và stored procedure có thể thực thi trực tiếp ở database, không đi qua quy trình cập nhật từng managed entity như dirty checking thông thường.

Ví dụ:

~~~java
entityManager.createQuery("""
    update Account a
       set a.status = :status
     where a.region = :region
""")
.setParameter("status", AccountStatus.REVIEW)
.setParameter("region", "NORTH")
.executeUpdate();
~~~

Câu lệnh bulk có thể cập nhật nhiều hàng bằng một SQL statement. Hibernate không sắp xếp từng entity update trong persistence context cho câu lệnh đó theo cách giống các entity dirty được flush.

Cần lưu ý:

- SQL statement có thể tác động nhiều hàng và database tự quyết định cách xử lý theo execution plan.
- Thứ tự các hàng trong WHERE IN hoặc collection parameter không bảo đảm thứ tự lock.
- Bulk update có thể làm persistence context chứa entity cũ, vì các managed object chưa tự động phản ánh thay đổi bulk.
- Nếu dùng version column, câu bulk update cần tự cập nhật version nếu nghiệp vụ yêu cầu.
- Native SQL cần tự quản lý thứ tự truy cập, transaction và các điều kiện đồng bộ.

Sau bulk update, có thể cần flush trước khi chạy và clear hoặc refresh persistence context sau khi chạy, tùy trạng thái entity và cách ứng dụng sử dụng chúng.

Nếu câu lệnh bulk cập nhật nhiều hàng nóng và có nguy cơ deadlock, cần xem plan, index và cách database lấy lock; bật order_updates không tự sắp xếp các hàng bên trong một câu UPDATE duy nhất.

## 12. Foreign key, unique index và trigger cũng có thể tham gia deadlock

ORM có thể chỉ phát một UPDATE trên bảng account, nhưng database phải thực hiện thêm công việc để bảo đảm toàn vẹn:

- Kiểm tra foreign key.
- Duy trì unique index.
- Duy trì secondary index.
- Thực thi trigger.
- Cập nhật bảng audit hoặc bảng liên quan.
- Kiểm tra cascade hoặc quan hệ tham chiếu.

Ví dụ, một transaction cập nhật order trước rồi payment; transaction khác cập nhật payment trước rồi order. Trigger trên payment có thể cập nhật order summary. Dù code Java chỉ gọi một vài setter, database có thể truy cập tài nguyên theo đường đi rộng hơn.

Khi phân tích deadlock, cần đọc deadlock graph hoặc thông tin tương đương để biết chính xác:

- Transaction nào đang giữ lock.
- Transaction nào đang chờ.
- Tên bảng, index hoặc tài nguyên.
- Loại lock và mode.
- SQL statement tương ứng.
- Trigger, foreign key hoặc constraint có liên quan.

Không nên kết luận deadlock chỉ do thứ tự UPDATE của ORM nếu chưa xem tài nguyên trong chu trình chờ.

## 13. Optimistic locking có thay thế lock ordering không?

Không hoàn toàn.

Optimistic locking dùng version để phát hiện dữ liệu đã thay đổi kể từ khi transaction đọc. Ví dụ:

~~~sql
UPDATE accounts
SET balance = ?,
    version = version + 1
WHERE account_id = ?
  AND version = ?;
~~~

Nếu version không còn khớp, UPDATE ảnh hưởng 0 dòng hoặc ORM ném OptimisticLockException. Cơ chế này giúp tránh ghi đè thay đổi cũ.

Tuy nhiên, khi transaction cập nhật nhiều hàng và database cần lấy lock ghi trên các hàng đó, deadlock vẫn có thể xảy ra trước khi ứng dụng nhận ra xung đột version.

So sánh:

| Cơ chế | Giải quyết vấn đề gì? | Có loại bỏ deadlock không? |
|---|---|---|
| Optimistic locking | Phát hiện update dựa trên version cũ | Không bảo đảm |
| Pessimistic locking | Lấy lock trước khi thay đổi | Không, nếu lấy nhiều lock theo thứ tự khác nhau |
| Canonical lock ordering | Giảm chu trình chờ do thứ tự lấy lock khác nhau | Giảm nguy cơ, không loại bỏ mọi deadlock |
| Hibernate order_updates | Sắp xếp UPDATE do Hibernate phát sinh theo entity type và khóa chính | Giảm một số deadlock, không bảo đảm tuyệt đối |
| SERIALIZABLE | Bảo đảm lịch tương đương thực thi tuần tự theo engine | Có thể abort/retry; không có nghĩa không bao giờ có deadlock |

Chọn optimistic hay pessimistic locking theo mô hình xung đột và yêu cầu nghiệp vụ. Nếu transaction thường xuyên cập nhật nhiều tài nguyên chung, cần lock ordering rõ ràng dù đã dùng @Version.

## 14. Xử lý deadlock victim đúng cách

Deadlock là lỗi concurrency có thể phục hồi nếu transaction được thiết kế phù hợp. Database thường chọn một transaction làm victim và rollback transaction đó.

Ứng dụng nên:

1. Nhận diện lỗi deadlock bằng vendor error code hoặc SQLSTATE của database.
2. Rollback hoặc kết thúc transaction bị hủy.
3. Bắt đầu transaction mới.
4. Đọc lại trạng thái hiện tại.
5. Thực hiện lại toàn bộ logic nghiệp vụ nếu thao tác còn hợp lệ.
6. Giới hạn số lần retry và dùng backoff có jitter.
7. Ghi log transaction, SQL, tài nguyên và số lần retry.

Không nên chỉ retry câu UPDATE cuối cùng vì các lần đọc trước có thể đã lỗi thời.

Với Spring/JPA, exception có thể được bọc qua nhiều lớp như DataAccessException, PessimisticLockingFailureException hoặc exception cụ thể của provider. Nên phân loại dựa trên nguyên nhân gốc và vendor code, không chỉ tên exception ngoài cùng.

Không retry mù quáng mọi lỗi transaction. Constraint violation hoặc lỗi dữ liệu không tự biến mất khi chạy lại cùng yêu cầu. Nếu transaction đã gọi API hoặc gửi email trước khi deadlock xảy ra, retry có thể lặp side effect bên ngoài; nên tách các side effect bằng Transactional Outbox và idempotency.

## 15. Cách quan sát thứ tự SQL và deadlock

Khi nghi ngờ ORM phát UPDATE theo thứ tự gây deadlock, cần thu thập SQL thực tế thay vì chỉ nhìn code Java.

### 15.1. Bật SQL logging

Với Hibernate, có thể bật log SQL và bind parameter theo cấu hình phù hợp môi trường:

~~~properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Tên logger cho bind parameter có thể khác giữa các phiên bản Hibernate. Không nên bật log bind nhạy cảm trong production nếu payload chứa dữ liệu cá nhân, thông tin thanh toán hoặc bí mật.

Cần ghi nhận:

- Thứ tự UPDATE được gửi.
- Entity/table và khóa chính tương ứng.
- Transaction/correlation ID.
- Thời điểm flush và commit.
- Số câu lệnh trong JDBC batch.
- SQL được phát sinh từ cascade, trigger hoặc native query nếu có thể quan sát.

### 15.2. Dùng công cụ theo database

| Database | Nguồn quan sát deadlock và lock |
|---|---|
| PostgreSQL | Server log với log_lock_waits/deadlock, pg_stat_activity, pg_locks |
| MySQL/InnoDB | SHOW ENGINE INNODB STATUS, performance_schema.data_locks, data_lock_waits |
| SQL Server | Extended Events với xml_deadlock_report, deadlock graph, DMVs |
| Oracle | Trace/deadlock information, V$LOCK, V$SESSION và công cụ chẩn đoán phù hợp |

Deadlock graph thường cho thấy chu trình chờ rõ hơn log SQL đơn lẻ. Ghép graph với SQL log để biết câu lệnh ORM nào đang giữ và xin lock.

### 15.3. So sánh trước và sau khi bật order_updates

Khi thử bật order_updates:

1. Ghi nhận deadlock rate và transaction latency trước thay đổi.
2. Thu thập SQL log hoặc deadlock graph để xác định thứ tự UPDATE hiện tại.
3. Bật cấu hình trong môi trường kiểm thử.
4. Chạy lại workload có hai transaction cập nhật cùng tập hàng theo thứ tự đầu vào khác nhau.
5. Xác nhận Hibernate phát UPDATE theo thứ tự mới.
6. Đo batching, throughput, latency và deadlock rate.
7. Kiểm tra các luồng cập nhật bảng liên quan và native SQL.
8. Chỉ triển khai khi kết quả trên workload thực tế cho thấy cải thiện.

Không nên kết luận cấu hình có hiệu quả chỉ vì một test đơn lẻ không còn deadlock. Cần lặp lại với nhiều transaction đồng thời và các luồng truy cập khác nhau.

## 16. Ví dụ kiểm thử hai transaction cập nhật ngược thứ tự

Một kiểm thử có thể mô phỏng hai request cùng cập nhật hai tài khoản. Nếu không có thứ tự thống nhất, hai transaction có thể giữ lock trên hai hàng theo thứ tự ngược nhau.

Pseudocode kiểm thử:

~~~text
Khởi tạo account 10 và account 20

Thread A:
    BEGIN
    load account 10
    thay đổi account 10
    barrier.await
    load/update account 20
    COMMIT

Thread B:
    BEGIN
    load account 20
    thay đổi account 20
    barrier.await
    load/update account 10
    COMMIT

Quan sát:
    deadlock graph
    transaction victim
    SQL UPDATE order
~~~

Sau khi áp dụng thứ tự ID tăng dần:

~~~text
Thread A:
    BEGIN
    lock account 10
    lock account 20
    update cả hai
    COMMIT

Thread B:
    BEGIN
    lock account 10
    lock account 20
    update cả hai
    COMMIT
~~~

Thread B có thể phải chờ Thread A, nhưng không tạo chu trình chờ do hai hàng được lấy theo cùng thứ tự.

Khi kiểm thử ORM, cần xác nhận barrier đặt đúng thời điểm. Nếu ORM chỉ phát UPDATE lúc flush/commit, việc thay đổi object trước barrier không đồng nghĩa hàng đã bị database khóa trước barrier. Muốn kiểm thử thứ tự lock, cần quan sát SQL và đặt đồng bộ tại ranh giới phù hợp.

## 17. Checklist thiết kế cho ứng dụng ORM

Khi transaction cập nhật nhiều entity, hãy xác định:

1. Các entity hoặc hàng nào có thể bị nhiều transaction cập nhật cùng lúc?
2. ORM flush vào thời điểm nào trong use case?
3. Provider có sắp xếp UPDATE theo entity type và khóa chính không?
4. Cấu hình order_updates có hỗ trợ và có phù hợp workload không?
5. Mọi luồng nghiệp vụ có lấy lock theo cùng thứ tự không?
6. Có cascade, collection table, trigger hoặc foreign key mở rộng phạm vi lock không?
7. Có bulk update hoặc native SQL nằm ngoài action queue không?
8. Có query nào kích hoạt AUTO flush trước khi lấy đủ lock không?
9. JDBC batch size có phù hợp với transaction size không?
10. Deadlock exception có được retry toàn bộ transaction với giới hạn không?
11. Side effect bên ngoài có được tách khỏi transaction và bảo vệ bằng idempotency không?
12. Deadlock graph và SQL log có đủ thông tin để xác định blocker, waiter và tài nguyên không?

## Kết luận

ORM quản lý thay đổi entity trong persistence context và thường phát SQL khi flush. Vì provider có thể sắp xếp, nhóm hoặc batch các action, thứ tự setter trong Java không bảo đảm thứ tự UPDATE được database thực thi. Nếu các transaction cập nhật cùng tập hàng theo thứ tự ngược nhau, chúng có thể tạo chu trình chờ và deadlock.

Hibernate có cấu hình order_updates để sắp xếp UPDATE theo entity type và khóa chính, giúp giảm một số deadlock và cải thiện batching. Tuy nhiên, cấu hình này không bao phủ mọi tài nguyên mà transaction truy cập. Cách bảo vệ mạnh hơn là định nghĩa thứ tự khóa nhất quán ở cấp nghiệp vụ, lấy lock theo thứ tự đó trước khi thay đổi entity, và kiểm tra SQL thực tế cùng deadlock graph.

Khi deadlock vẫn xảy ra, cần rollback và retry toàn bộ transaction với trạng thái mới, có giới hạn và backoff. Hãy đánh giá cả flush timing, JDBC batching, bulk/native SQL, cascade, foreign key, trigger và execution plan. Chỉ khi hiểu toàn bộ đường đi của lock mới có thể xác định liệu thứ tự UPDATE do ORM phát sinh có thực sự là nguyên nhân và giải pháp nào phù hợp.

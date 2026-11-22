# Kiểu trả về và số hàng bị tác động của truy vấn thay đổi dữ liệu

Trong Spring Data R2DBC, một repository có thể khai báo SQL trực tiếp bằng **@Query**. Khi câu SQL làm thay đổi dữ liệu như **INSERT**, **UPDATE** hoặc **DELETE**, kiểu trả về cần thể hiện đúng điều mà ứng dụng quan tâm: chỉ cần biết thao tác đã hoàn tất, hay cần biết có bao nhiêu hàng bị tác động.

Với truy vấn thay đổi dữ liệu khai báo bằng **@Query**, **@Modifying** đánh dấu phương thức là thao tác ghi. Một kiểu trả về dạng số có thể biểu diễn số hàng bị ảnh hưởng; kiểu **Mono<Void>** phù hợp khi chỉ cần tín hiệu hoàn tất hoặc lỗi. Nếu SQL cần trả về các hàng dữ liệu, ví dụ dùng **RETURNING** của PostgreSQL, đó là một dạng kết quả khác và cần chọn API đọc kết quả tương ứng.

## 1. Truy vấn khai báo và truy vấn thay đổi dữ liệu

Spring Data R2DBC cho phép khai báo câu SQL ngay trên phương thức repository:

~~~java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {

    @Query("SELECT * FROM person WHERE status = :status")
    Flux<Person> findByStatus(String status);
}
~~~

Đối với câu **SELECT**, phương thức thường trả về **Mono<T>** hoặc **Flux<T>**, tùy số lượng kết quả. Spring Data đọc các hàng và ánh xạ chúng thành kiểu Java.

Với câu lệnh thay đổi dữ liệu, mục tiêu thường là thực thi SQL và nhận số hàng bị ảnh hưởng:

~~~sql
UPDATE person
SET status = 'INACTIVE'
WHERE last_seen < CURRENT_TIMESTAMP - INTERVAL '1 year';
~~~

Không có entity nào nhất thiết phải được trả về từ câu lệnh này. Database có thể chỉ cung cấp số hàng đã cập nhật. Vì vậy, kiểu trả về cần mô tả kết quả cập nhật thay vì khai báo **Mono<Person>** như một truy vấn đọc thông thường.

## 2. Vai trò của @Modifying

**@Query** khai báo SQL cần chạy. Với truy vấn thay đổi dữ liệu, **@Modifying** cho Spring Data biết phương thức đó là modifying query:

~~~java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {

    @Modifying
    @Query("UPDATE person SET status = :status WHERE id = :id")
    Mono<Integer> updateStatus(Long id, String status);
}
~~~

Trong ví dụ:

- **@Query** chứa câu SQL update.
- **@Modifying** đánh dấu đây là thao tác thay đổi dữ liệu.
- **Mono<Integer>** phát ra số hàng bị tác động sau khi câu lệnh thực thi.

Với phương thức truy vấn khai báo, hãy dùng annotation đúng với mục đích. Không nên khai báo một câu UPDATE rồi kỳ vọng Spring Data xử lý nó như truy vấn SELECT trả về entity.

Các tham số đặt tên như :id và :status được bind từ tham số phương thức. Nếu dự án không lưu tên tham số trong bytecode hoặc muốn khai báo rõ ràng, có thể dùng **@Param**:

~~~java
@Modifying
@Query("UPDATE person SET status = :status WHERE id = :id")
Mono<Integer> updateStatus(
        @Param("id") Long id,
        @Param("status") String status
);
~~~

Không nối giá trị đầu vào trực tiếp vào SQL. Bind tham số giúp truyền giá trị an toàn và tách dữ liệu khỏi cấu trúc câu lệnh.

## 3. Kiểu trả về biểu diễn số hàng bị tác động

Với modifying query, kiểu trả về dạng số cho biết số hàng database báo đã bị tác động. Một khai báo thường gặp:

~~~java
@Modifying
@Query("UPDATE inventory SET quantity = :quantity WHERE id = :id")
Mono<Integer> updateQuantity(
        @Param("id") Long id,
        @Param("quantity") int quantity
);
~~~

Khi publisher phát ra:

- **1**: một hàng đã được cập nhật.
- **0**: không có hàng nào khớp điều kiện hoặc không có hàng nào được báo là đã tác động theo ngữ nghĩa của driver/database.
- Giá trị lớn hơn **1**: nhiều hàng bị tác động, thường xảy ra khi điều kiện WHERE khớp nhiều bản ghi.

Số hàng không phải entity đã cập nhật. Nó cũng không tự giải thích vì sao số hàng bằng 0. Ứng dụng phải diễn giải giá trị theo hợp đồng nghiệp vụ và điều kiện SQL.

Một số phiên bản/API có thể hỗ trợ kiểu số khác như **Long** cho số lượng lớn hơn. Hãy dùng kiểu được phiên bản Spring Data R2DBC đang sử dụng hỗ trợ cho modifying query; không giả định mọi kiểu số đều được chấp nhận như nhau.

## 4. Khi chỉ cần biết thao tác hoàn tất: Mono<Void>

Nếu tầng gọi không cần biết số hàng, có thể khai báo publisher không mang giá trị:

~~~java
@Modifying
@Query("DELETE FROM session_token WHERE expires_at < :cutoff")
Mono<Void> deleteExpiredTokens(@Param("cutoff") Instant cutoff);
~~~

**Mono<Void>** biểu diễn một thao tác có thể hoàn tất hoặc kết thúc bằng lỗi. Nó không phát số hàng bị xóa. Khi publisher hoàn tất bình thường, tầng gọi biết câu lệnh đã thực thi thành công theo hợp đồng driver; nếu SQL, kết nối hoặc transaction thất bại, publisher phát lỗi.

Chọn **Mono<Void>** khi số hàng không ảnh hưởng đến quyết định nghiệp vụ. Nếu cần phân biệt “không tìm thấy bản ghi” với “đã cập nhật một bản ghi”, hãy dùng kiểu trả về số hàng.

## 5. Phân biệt zero rows với lỗi

Số hàng bị tác động bằng 0 thường là một kết quả hợp lệ, không nhất thiết là lỗi database.

Ví dụ:

~~~sql
UPDATE person
SET status = 'ACTIVE'
WHERE id = 999999;
~~~

Nếu không có người nào mang ID đó, câu lệnh vẫn hợp lệ nhưng không tác động hàng nào. Database có thể trả số hàng bằng 0 và publisher hoàn tất bình thường.

Ngược lại, các tình huống sau thường phát tín hiệu lỗi:

- SQL sai cú pháp.
- Bảng hoặc cột không tồn tại.
- Người dùng database không có quyền cập nhật.
- Giá trị vi phạm constraint.
- Kết nối bị ngắt hoặc timeout.
- Transaction bị rollback hoặc gặp lỗi.

Vì vậy, cần phân biệt:

| Kết quả | Ý nghĩa |
| --- | --- |
| **Mono<Integer>** phát **0** rồi complete | SQL thực thi nhưng không có hàng được báo là tác động |
| **Mono<Integer>** phát số dương rồi complete | SQL thực thi và database báo số hàng bị tác động |
| **Mono<Void>** complete | Thao tác hoàn tất; không có số hàng để diễn giải |
| Publisher phát error | Thao tác thất bại do SQL, driver, database hoặc transaction |

Không dùng **onErrorResume** để chuyển mọi lỗi thành số 0 nếu nghiệp vụ cần biết database đang gặp sự cố. Làm vậy sẽ biến lỗi hạ tầng thành kết quả “không có hàng” và khiến chẩn đoán khó hơn.

## 6. Diễn giải số hàng trong service

Service có thể chuyển số hàng thành kết quả nghiệp vụ:

~~~java
public Mono<Void> activatePerson(Long id) {
    return personRepository.updateStatus(id, "ACTIVE")
            .flatMap(rowsUpdated -> {
                if (rowsUpdated == 1) {
                    return Mono.empty();
                }

                if (rowsUpdated == 0) {
                    return Mono.error(new PersonNotFoundException(id));
                }

                return Mono.error(new IllegalStateException(
                        "Expected one row to be updated, got " + rowsUpdated
                ));
            });
}
~~~

Ở đây, nghiệp vụ mong đợi đúng một người được cập nhật. Số hàng bằng 0 được chuyển thành lỗi không tìm thấy; số hàng lớn hơn một cho thấy điều kiện hoặc giả định duy nhất có vấn đề.

Không phải use case nào cũng nên coi số 0 là lỗi. Ví dụ một thao tác dọn dữ liệu hết hạn có thể hợp lệ khi không có hàng nào cần xóa. Cách diễn giải phải xuất phát từ yêu cầu nghiệp vụ.

## 7. Ví dụ UPDATE với số hàng bị tác động

Một repository có thể khai báo nhiều thao tác ghi:

~~~java
public interface AccountRepository
        extends ReactiveCrudRepository<Account, Long> {

    @Modifying
    @Query("UPDATE account SET status = :status WHERE id = :id")
    Mono<Integer> changeStatus(
            @Param("id") Long id,
            @Param("status") String status
    );

    @Modifying
    @Query("UPDATE account SET balance = balance - :amount WHERE id = :id")
    Mono<Integer> debit(
            @Param("id") Long id,
            @Param("amount") BigDecimal amount
    );
}
~~~

Service có thể xác nhận một hàng được cập nhật:

~~~java
public Mono<Void> debitAccount(Long accountId, BigDecimal amount) {
    if (amount.signum() <= 0) {
        return Mono.error(new IllegalArgumentException(
                "Amount must be positive"
        ));
    }

    return accountRepository.debit(accountId, amount)
            .flatMap(rows -> {
                if (rows == 1) {
                    return Mono.empty();
                }
                if (rows == 0) {
                    return Mono.error(new AccountNotFoundException(accountId));
                }
                return Mono.error(new IllegalStateException(
                        "Unexpected affected row count: " + rows
                ));
            });
}
~~~

Ví dụ này chỉ minh họa việc đọc số hàng. Trong hệ thống tài chính, câu lệnh trừ tiền cần thêm điều kiện như **balance >= :amount**, kiểm soát concurrency, transaction và quy tắc idempotency. Nếu không có điều kiện kiểm tra số dư, câu lệnh có thể làm số dư âm.

Một câu lệnh có thể gộp điều kiện nghiệp vụ vào SQL:

~~~sql
UPDATE account
SET balance = balance - :amount
WHERE id = :id
  AND balance >= :amount;
~~~

Khi số hàng bằng 0, có thể là tài khoản không tồn tại hoặc số dư không đủ. Nếu cần phân biệt hai trường hợp, phải thiết kế thêm truy vấn/kiểu kết quả hoặc dùng câu lệnh trả về thông tin chi tiết phù hợp với database.

## 8. Ví dụ DELETE và số hàng bị xóa

Với truy vấn xóa, số hàng giúp xác định có bao nhiêu bản ghi khớp điều kiện:

~~~java
public interface SessionRepository
        extends ReactiveCrudRepository<Session, Long> {

    @Modifying
    @Query("DELETE FROM session WHERE user_id = :userId")
    Mono<Integer> deleteSessionsByUserId(@Param("userId") Long userId);
}
~~~

Service có thể dùng số hàng để ghi nhận kết quả:

~~~java
public Mono<Integer> revokeAllSessions(Long userId) {
    return sessionRepository.deleteSessionsByUserId(userId);
}
~~~

Nếu publisher phát ra **5**, database báo năm hàng session bị xóa. Nếu phát ra **0**, không có session nào khớp. Đây không phải lỗi nếu người dùng chưa từng có session hoặc các session đã được thu hồi trước đó.

Với thao tác dọn dẹp chạy định kỳ, **Mono<Integer>** hoặc kiểu số tương ứng hữu ích để ghi metric. Với thao tác chỉ cần hoàn tất, **Mono<Void>** có thể đơn giản hơn.

## 9. INSERT và sự khác biệt giữa số hàng với dữ liệu được sinh

Một câu **INSERT** cũng là modifying query:

~~~java
@Modifying
@Query("INSERT INTO tag (name) VALUES (:name)")
Mono<Integer> insertTag(@Param("name") String name);
~~~

Kết quả số hàng có thể cho biết có bao nhiêu hàng được insert. Tuy nhiên, nó không trả ID tự sinh hay toàn bộ entity đã insert.

Nếu cần ID được sinh hoặc các cột do database tạo, cần dùng API có thể đọc kết quả trả về. Với PostgreSQL, **RETURNING** có thể trả dữ liệu:

~~~sql
INSERT INTO tag (name)
VALUES (:name)
RETURNING id, name;
~~~

Trong trường hợp cần ánh xạ hàng trả về, dùng **DatabaseClient** hoặc API phù hợp với kết quả dạng row:

~~~java
public Mono<Tag> insertTag(String name) {
    return databaseClient.sql("""
            INSERT INTO tag (name)
            VALUES (:name)
            RETURNING id, name
            """)
            .bind("name", name)
            .map((row, metadata) -> new Tag(
                    row.get("id", Long.class),
                    row.get("name", String.class)
            ))
            .one();
}
~~~

**RETURNING** là tính năng của PostgreSQL và một số database khác có cú pháp riêng. Không nên giả định mọi database hoặc mọi modifying repository method đều hỗ trợ trả về entity theo cùng cách.

## 10. Dùng DatabaseClient.rowsUpdated() khi cần kiểm soát SQL

Khi cần SQL tùy chỉnh hoặc muốn chủ động đọc số hàng bị ảnh hưởng, **DatabaseClient** cung cấp **rowsUpdated()**:

~~~java
public Mono<Long> updateStatus(Long id, String status) {
    return databaseClient.sql("""
            UPDATE person
            SET status = :status
            WHERE id = :id
            """)
            .bind("id", id)
            .bind("status", status)
            .fetch()
            .rowsUpdated();
}
~~~

API này trả publisher số hàng cập nhật theo kiểu số mà phiên bản Spring Framework đang dùng cung cấp. Cần giữ đúng kiểu được khai báo bởi thư viện; không chuyển sang **Integer** hoặc **Long** tùy tiện nếu không cần.

So sánh:

| Cách truy cập | Khi phù hợp |
| --- | --- |
| **@Query** + **@Modifying** | SQL thay đổi dữ liệu được khai báo ngay trong repository |
| **DatabaseClient.fetch().rowsUpdated()** | Cần xây dựng SQL linh hoạt hoặc xử lý kết quả cập nhật trực tiếp |
| **R2dbcEntityTemplate.update(...)** | Muốn cập nhật theo entity metadata và **Query**/**Update** |
| **repository.save(entity)** | Lưu entity theo trạng thái mới/cũ của Spring Data |

## 11. Kiểu trả về của truy vấn thay đổi dữ liệu và transaction

Một modifying query có thể chạy bên trong reactive transaction. Ví dụ:

~~~java
@Transactional
public Mono<Void> transferStatus(Long fromId, Long toId) {
    return accountRepository.changeStatus(fromId, "TRANSFERRED")
            .flatMap(sourceRows -> {
                if (sourceRows != 1) {
                    return Mono.error(new IllegalStateException(
                            "Source account was not updated"
                    ));
                }

                return accountRepository.changeStatus(toId, "ACTIVE")
                        .flatMap(targetRows -> targetRows == 1
                                ? Mono.empty()
                                : Mono.error(new IllegalStateException(
                                        "Target account was not updated"
                                )));
            });
}
~~~

Nếu một bước phát lỗi và publisher được quản lý trong cùng reactive transaction, transaction manager có thể rollback các thay đổi trước đó theo cấu hình và quy tắc rollback. Không gọi **subscribe()** bên trong phương thức; hãy trả publisher để transaction interceptor quản lý toàn bộ vòng đời.

Số hàng bị tác động không tự tạo transaction. Nó chỉ là kết quả của câu lệnh. Tính nguyên tử của nhiều câu lệnh phụ thuộc transaction boundary và database.

## 12. Số hàng bị tác động và optimistic locking

Optimistic locking dùng **@Version** để phát hiện entity đã thay đổi kể từ lúc được đọc. Khi dùng thao tác save được Spring Data quản lý, một update không khớp version thường được chuyển thành lỗi optimistic locking thay vì âm thầm ghi đè.

Với modifying query tự viết, nếu muốn áp dụng optimistic locking, SQL cần đưa version hiện tại vào điều kiện và tăng version:

~~~sql
UPDATE inventory
SET quantity = :quantity,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Phương thức có thể trả số hàng:

~~~java
@Modifying
@Query("""
        UPDATE inventory
        SET quantity = :quantity,
            version = version + 1
        WHERE id = :id
          AND version = :expectedVersion
        """)
Mono<Integer> updateQuantity(
        @Param("id") Long id,
        @Param("quantity") int quantity,
        @Param("expectedVersion") Long expectedVersion
);
~~~

Nếu kết quả bằng **1**, hàng đã được cập nhật theo version mong đợi. Nếu bằng **0**, hàng có thể không tồn tại hoặc version đã thay đổi. Ứng dụng cần quyết định có truy vấn lại để phân biệt hay trả lỗi xung đột.

Một modifying query viết tay không tự động có toàn bộ hành vi optimistic locking như thao tác save entity được Spring Data quản lý. Câu SQL phải thể hiện rõ điều kiện version và cập nhật version.

## 13. Số hàng được báo có thể khác cách diễn giải nghiệp vụ

Số hàng bị tác động là thông tin do database/driver báo cho thao tác thực thi. Cách đếm cụ thể có thể phụ thuộc hệ quản trị, trigger, câu lệnh, driver và chế độ thực thi.

Ví dụ:

- Một câu UPDATE có thể khớp một hàng nhưng gán lại đúng giá trị cũ. Database có thể báo số hàng khớp hoặc số hàng thực sự thay đổi tùy hệ quản trị.
- Trigger có thể thực hiện thêm thao tác trên bảng khác; số hàng trả về của câu lệnh chính không nhất thiết là tổng mọi thay đổi phát sinh từ trigger.
- Câu lệnh có nhiều phần hoặc batch có thể trả số lượng theo từng result tùy API và driver.
- Một câu DELETE có thể bị cascade xóa các hàng liên quan; số lượng trả về của lệnh chính không nên được hiểu là tổng mọi hàng bị cascade nếu database không định nghĩa như vậy.

Vì thế, hãy xem affected row count là kết quả thực thi của câu lệnh theo semantics của database. Nếu nghiệp vụ cần biết chính xác danh sách entity thay đổi hoặc tổng thay đổi qua cascade, cần thiết kế query/audit riêng thay vì suy ra từ một số đếm.

## 14. Trường hợp cần trả về hàng dữ liệu thay vì số hàng

Một số database hỗ trợ câu lệnh DML trả về dữ liệu:

~~~sql
UPDATE person
SET status = 'ACTIVE'
WHERE id = 42
RETURNING id, status;
~~~

Kết quả này là các hàng dữ liệu, không chỉ là affected row count. Với PostgreSQL, **RETURNING** hữu ích khi cần lấy giá trị mới hoặc ID sinh mà không phải thực hiện truy vấn SELECT riêng.

Khi cần dữ liệu trả về, sử dụng **DatabaseClient.map(...).all()** hoặc API thích hợp để ánh xạ row. Không khai báo kiểu trả về số hàng nếu tầng gọi thực sự cần các cột từ **RETURNING**.

Ví dụ:

~~~java
public Mono<PersonStatus> activate(Long id) {
    return databaseClient.sql("""
            UPDATE person
            SET status = 'ACTIVE'
            WHERE id = :id
            RETURNING id, status
            """)
            .bind("id", id)
            .map((row, metadata) -> new PersonStatus(
                    row.get("id", Long.class),
                    row.get("status", String.class)
            ))
            .one();
}
~~~

Kiểm tra cú pháp và khả năng hỗ trợ của database mục tiêu trước khi dùng **RETURNING**. Nếu database không hỗ trợ, có thể cần transaction và truy vấn đọc tiếp theo.

## 15. Những lỗi thường gặp

1. **Quên @Modifying trên truy vấn DML khai báo.** Spring Data cần biết đây là truy vấn thay đổi dữ liệu.
2. **Khai báo Mono<Entity> cho câu UPDATE chỉ trả số hàng.** Chọn kiểu trả về phù hợp với kết quả thực tế.
3. **Dùng Mono<Void> nhưng lại cần phân biệt 0 và 1 hàng.** Dùng kiểu số khi count có ý nghĩa nghiệp vụ.
4. **Coi số 0 luôn là lỗi.** Không có hàng khớp có thể là kết quả hợp lệ.
5. **Coi số dương là toàn bộ nghiệp vụ đã thành công.** Affected count không thay thế validation, transaction hoặc kiểm tra các bước khác.
6. **Nuốt lỗi thành số 0.** Lỗi kết nối hoặc SQL phải được giữ như lỗi, không giả làm không tìm thấy.
7. **Nhầm affected rows với số hàng cascade.** Count của câu lệnh chính không nhất thiết bao gồm mọi tác động phụ.
8. **Dùng modifying query để upsert mà không có SQL upsert.** @Modifying không tự tạo semantics insert-or-update.
9. **Quên kiểm tra điều kiện WHERE.** Một câu update/delete thiếu điều kiện có thể tác động rất nhiều hàng.
10. **Cho rằng @Modifying trả entity sau UPDATE.** Muốn nhận hàng từ DML cần API và cú pháp trả hàng phù hợp như RETURNING.
11. **Cho rằng affected count có cùng semantics trên mọi database.** Hãy kiểm tra driver và hệ quản trị mục tiêu.
12. **Tự subscribe trong service transactional.** Trả publisher để transaction manager điều phối hoàn tất và rollback.

## Quy tắc lựa chọn nhanh

- Dùng **@Query** để khai báo SQL và **@Modifying** để đánh dấu câu lệnh thay đổi dữ liệu.
- Dùng **Mono<Integer>** hoặc kiểu số được phiên bản hỗ trợ khi cần số hàng bị tác động.
- Dùng **Mono<Void>** khi chỉ quan tâm thao tác hoàn tất hay lỗi.
- Xử lý số 0 theo quy tắc nghiệp vụ; nó không tự động là lỗi database.
- Dùng **DatabaseClient.fetch().rowsUpdated()** khi cần SQL tùy chỉnh và affected count.
- Dùng **RETURNING** cùng API ánh xạ row nếu cần dữ liệu sau INSERT/UPDATE/DELETE và database hỗ trợ.
- Đưa điều kiện version vào SQL khi tự viết modifying query có optimistic locking.
- Dùng reactive transaction khi nhiều thao tác phải commit/rollback cùng nhau.
- Kiểm tra semantics affected count trên đúng database và driver đang triển khai.

Kiểu trả về của truy vấn thay đổi dữ liệu là một phần hợp đồng giữa repository và tầng service. Số hàng bị tác động cho biết database báo đã cập nhật, chèn hoặc xóa bao nhiêu hàng; **Mono<Void>** chỉ cho biết thao tác hoàn tất hay gặp lỗi. Khi cần entity hoặc dữ liệu mới sau DML, hãy dùng API trả về hàng thay vì suy diễn từ count. Phân biệt rõ các kết quả này giúp service xử lý đúng trường hợp không có hàng khớp, xung đột đồng thời và lỗi thực thi.

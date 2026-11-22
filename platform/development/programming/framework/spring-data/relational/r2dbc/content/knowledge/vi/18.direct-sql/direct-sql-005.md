# Nhận số hàng thay đổi bằng rowsUpdated

Khi thực thi câu lệnh INSERT, UPDATE hoặc DELETE qua Spring R2DBC, ứng dụng thường cần biết database đã tác động tới bao nhiêu hàng. API **rowsUpdated()** của Spring R2DBC cung cấp số hàng được báo cáo là đã thay đổi bởi thao tác SQL. Giá trị này hữu ích để xác nhận một lệnh cập nhật có tìm thấy bản ghi, kiểm tra thao tác xóa, xử lý optimistic locking hoặc ghi nhận kết quả của một lệnh ghi.

Với **DatabaseClient**, cách dùng phổ biến là:

~~~java
Mono<Long> affectedRows = databaseClient
    .sql("UPDATE customer SET active = :active WHERE id = :id")
    .bind("active", false)
    .bind("id", customerId)
    .fetch()
    .rowsUpdated();
~~~

Kết quả là một publisher reactive kiểu Mono<Long>. DatabaseClient thực thi SQL khi publisher được subscribe và phát ra số hàng mà driver/database báo cáo cho câu lệnh. Đây là số lượng hàng bị tác động, không phải entity được cập nhật hay ID mới sinh.

## 1. rowsUpdated() dùng để làm gì?

rowsUpdated() trả về số hàng được báo cáo là đã cập nhật bởi câu lệnh SQL. Trong ngữ cảnh DML, có thể dùng cho:

- INSERT: số hàng được insert.
- UPDATE: số hàng được update theo kết quả mà driver/database báo cáo.
- DELETE: số hàng được xóa.

Ví dụ, nếu câu lệnh UPDATE có điều kiện WHERE id = :id và chỉ một hàng khớp, kết quả thường là 1. Nếu không có hàng nào khớp, kết quả thường là 0.

Số lượng này giúp ứng dụng đưa ra quyết định tiếp theo:

- **1**: thao tác tác động đúng một hàng như mong đợi.
- **0**: không có hàng nào bị tác động; có thể bản ghi không tồn tại, điều kiện không khớp hoặc version đã cũ.
- **Lớn hơn 1**: điều kiện có thể rộng hơn dự kiến hoặc nghiệp vụ cho phép cập nhật nhiều hàng.

Cần nhớ rằng rowsUpdated là kết quả do database/driver cung cấp. Với một số hệ quản trị, khái niệm “affected rows” và “rows whose values actually changed” có thể khác nhau, nhất là khi UPDATE gán lại giá trị vốn đã có. Nếu nghiệp vụ phụ thuộc vào khác biệt này, hãy kiểm tra hành vi của database và driver mục tiêu.

## 2. Dùng rowsUpdated() với DatabaseClient

DatabaseClient thuộc Spring R2DBC. Nó cung cấp API thực thi SQL, bind tham số và đọc kết quả. Khi chỉ cần số hàng tác động, dùng fetch().rowsUpdated() thay vì ánh xạ từng Row.

Ví dụ service cập nhật trạng thái khách hàng:

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class CustomerSqlRepository {

    private final DatabaseClient databaseClient;

    public CustomerSqlRepository(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<Long> deactivate(Long customerId) {
        return databaseClient.sql("""
                UPDATE customer
                SET active = FALSE
                WHERE id = :id
                """)
            .bind("id", customerId)
            .fetch()
            .rowsUpdated();
    }
}
~~~

Phương thức trả về Mono<Long>. Caller có thể kết hợp kết quả với logic nghiệp vụ:

~~~java
return customerSqlRepository.deactivate(customerId)
    .map(rows -> rows == 1);
~~~

Nếu chỉ cần biết thao tác có tác động đúng một hàng hay không, có thể chuyển count thành Boolean. Nếu cần phân biệt không tìm thấy, thành công và cập nhật quá nhiều hàng, hãy xử lý count cụ thể thay vì chỉ chuyển thành true/false.

### 2.1. Cú pháp tổng quát

~~~java
Mono<Long> count = databaseClient
    .sql("DML SQL có tham số")
    .bind("parameterName", parameterValue)
    .fetch()
    .rowsUpdated();
~~~

Các bước:

1. sql(...) cung cấp câu lệnh.
2. bind(...) gắn giá trị vào named parameter.
3. fetch() chọn API đọc kết quả thực thi.
4. rowsUpdated() yêu cầu số hàng được tác động.

Không nối dữ liệu đầu vào trực tiếp vào chuỗi SQL. Bind parameter giúp tách dữ liệu khỏi cú pháp SQL và tránh các lỗi quoting cũng như nguy cơ SQL injection.

### 2.2. Bind giá trị NULL

Không truyền null trực tiếp vào bind(name, value). Khi tham số có thể null, dùng bindNull và chỉ rõ kiểu Java:

~~~java
Mono<Long> clearEmail(Long customerId) {
    return databaseClient.sql("""
            UPDATE customer
            SET email = :email
            WHERE id = :id
            """)
        .bindNull("email", String.class)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated();
}
~~~

Việc khai báo kiểu giúp driver biết kiểu dữ liệu cần bind ngay cả khi giá trị là null. Kiểu Java phải tương thích với cột và khả năng của driver.

## 3. Đếm số hàng khi INSERT

Với INSERT thông thường, rowsUpdated() cho biết số hàng mà driver báo cáo đã được insert.

~~~java
Mono<Long> insertCustomer(String fullName, String email) {
    return databaseClient.sql("""
            INSERT INTO customer (full_name, email, active)
            VALUES (:fullName, :email, TRUE)
            """)
        .bind("fullName", fullName)
        .bind("email", email)
        .fetch()
        .rowsUpdated();
}
~~~

Nếu lệnh insert một hàng thành công và driver báo số lượng, kết quả thường là 1.

Tuy nhiên, rowsUpdated() không trả về ID tự sinh. Nếu cần ID, hãy dùng cơ chế trả về generated values được driver hỗ trợ hoặc cú pháp SQL như RETURNING trên các database có hỗ trợ.

Ví dụ PostgreSQL:

~~~java
Mono<Long> insertAndGetId(String fullName, String email) {
    return databaseClient.sql("""
            INSERT INTO customer (full_name, email, active)
            VALUES (:fullName, :email, TRUE)
            RETURNING id
            """)
        .bind("fullName", fullName)
        .bind("email", email)
        .map((row, metadata) -> row.get("id", Long.class))
        .one();
}
~~~

Ở ví dụ này, ứng dụng đọc giá trị ID từ result row. Đây là một truy vấn trả dữ liệu, khác với việc chỉ lấy số hàng bằng rowsUpdated(). RETURNING là cú pháp phụ thuộc hệ quản trị; hãy kiểm tra driver/database đang sử dụng.

## 4. Đếm số hàng khi UPDATE

Ví dụ cập nhật email theo ID:

~~~java
Mono<Long> updateEmail(Long customerId, String email) {
    return databaseClient.sql("""
            UPDATE customer
            SET email = :email
            WHERE id = :id
            """)
        .bind("email", email)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated();
}
~~~

Kết quả thường được hiểu như sau:

| Giá trị | Ý nghĩa có thể xảy ra |
|---:|---|
| 0 | Không có hàng nào được báo cáo là update |
| 1 | Một hàng được báo cáo là update |
| Lớn hơn 1 | Nhiều hàng được báo cáo là update |

Nếu id là primary key, kết quả mong đợi thường là 0 hoặc 1. Nếu kết quả lớn hơn 1, cần xem lại schema hoặc câu lệnh vì điều kiện theo primary key không nên tác động nhiều hàng.

Nếu UPDATE không có điều kiện đủ chặt, nhiều hàng có thể bị tác động. Hãy luôn xác định rõ phạm vi update và cân nhắc ràng buộc UNIQUE/PRIMARY KEY cho các cột định danh.

### 4.1. Gán lại cùng một giá trị

Một câu lệnh như:

~~~sql
UPDATE customer
SET active = TRUE
WHERE id = 10
~~~

có thể tìm thấy hàng nhưng giá trị active đã là TRUE. Số lượng được báo cáo có thể phụ thuộc semantics của database/driver: một số hệ quản trị báo hàng khớp, một số chế độ báo hàng có giá trị thực sự thay đổi.

Do đó, không nên dùng rowsUpdated như bằng chứng portable rằng giá trị trong database chắc chắn đã đổi từ giá trị cũ sang giá trị mới. Nếu nghiệp vụ cần biết trạng thái trước/sau, cần thiết kế truy vấn hoặc điều kiện so sánh rõ ràng.

### 4.2. Chỉ update khi giá trị khác

Có thể thêm điều kiện để bỏ qua hàng đã có giá trị mong muốn:

~~~java
Mono<Long> activateIfInactive(Long customerId) {
    return databaseClient.sql("""
            UPDATE customer
            SET active = TRUE
            WHERE id = :id
              AND active = FALSE
            """)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated();
}
~~~

Khi đó, count 1 nghĩa là hàng thỏa cả ID và trạng thái inactive đã được update; count 0 nghĩa là không có hàng nào thỏa toàn bộ điều kiện. Nó vẫn không phân biệt riêng bản ghi không tồn tại với bản ghi đã active.

## 5. Đếm số hàng khi DELETE

DELETE cũng có thể dùng rowsUpdated():

~~~java
Mono<Long> deleteCustomer(Long customerId) {
    return databaseClient.sql("""
            DELETE FROM customer
            WHERE id = :id
            """)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated();
}
~~~

Kết quả thường là:

- 1: một hàng bị xóa.
- 0: không có hàng nào khớp điều kiện.
- Lớn hơn 1: điều kiện xóa tác động nhiều hàng.

Nếu customer được các bảng khác tham chiếu bằng foreign key, database có thể từ chối DELETE do RESTRICT/NO ACTION hoặc áp dụng ON DELETE CASCADE/SET NULL theo schema. Khi constraint vi phạm, publisher phát lỗi thay vì chỉ trả về count 0.

rowsUpdated() không che giấu lỗi constraint. Cần xử lý lỗi theo ngữ nghĩa nghiệp vụ, ví dụ không cho xóa khách hàng đang có đơn hàng.

## 6. Phân biệt 0 hàng và lỗi SQL

Đây là hai kết quả khác nhau:

- **Count bằng 0**: câu SQL thực thi nhưng không có hàng nào được báo cáo là tác động.
- **Publisher phát lỗi**: câu lệnh không thực thi thành công, ví dụ vi phạm constraint, sai cú pháp, lỗi kết nối hoặc lỗi bind.

Ví dụ:

~~~java
return deleteCustomer(customerId)
    .flatMap(rows -> {
        if (rows == 0) {
            return Mono.error(
                new CustomerNotFoundException(customerId)
            );
        }

        return Mono.just(rows);
    });
~~~

Đoạn code trên chuyển count 0 thành lỗi nghiệp vụ. Nếu database phát lỗi trước khi có count, lỗi đó đi theo nhánh onError và không chạy phần flatMap thành công.

Không nên dùng onErrorReturn(0L) một cách chung chung để biến mọi lỗi database thành count 0. Làm vậy sẽ đánh đồng bản ghi không tồn tại với lỗi kết nối, lỗi constraint hoặc lỗi SQL, khiến ứng dụng báo sai kết quả.

## 7. Xử lý count theo kỳ vọng nghiệp vụ

Nhiều thao tác có số hàng kỳ vọng cụ thể. Có thể viết helper để xác nhận đúng một hàng:

~~~java
private Mono<Void> requireOneRow(Mono<Long> rowsUpdated) {
    return rowsUpdated.flatMap(rows -> {
        if (rows == 1) {
            return Mono.empty();
        }

        if (rows == 0) {
            return Mono.error(
                new IllegalStateException("No row was updated")
            );
        }

        return Mono.error(
            new IllegalStateException(
                "Expected one row, but affected " + rows
            )
        );
    });
}
~~~

Sử dụng:

~~~java
public Mono<Void> renameCustomer(Long id, String newName) {
    Mono<Long> rows = databaseClient.sql("""
            UPDATE customer
            SET full_name = :name
            WHERE id = :id
            """)
        .bind("name", newName)
        .bind("id", id)
        .fetch()
        .rowsUpdated();

    return requireOneRow(rows);
}
~~~

Helper này phù hợp khi nghiệp vụ yêu cầu đúng một hàng. Với thao tác batch hoặc update nhiều bản ghi, hãy xác định một quy tắc khác, chẳng hạn count tối thiểu, count chính xác hoặc chỉ ghi nhận tổng số hàng.

Trong hệ thống thực tế, nên dùng exception domain có ý nghĩa hơn IllegalStateException, ví dụ CustomerNotFoundException hoặc ConcurrentCustomerUpdateException.

## 8. rowsUpdated() và optimistic locking

Optimistic locking dùng version để phát hiện hai thao tác cùng cập nhật một bản ghi dựa trên trạng thái cũ.

Giả sử bảng customer có cột version. Một câu update thủ công có thể viết:

~~~java
Mono<Long> updateWithVersion(
        Long id,
        Long expectedVersion,
        String newName) {

    return databaseClient.sql("""
            UPDATE customer
            SET full_name = :name,
                version = version + 1
            WHERE id = :id
              AND version = :expectedVersion
            """)
        .bind("name", newName)
        .bind("id", id)
        .bind("expectedVersion", expectedVersion)
        .fetch()
        .rowsUpdated();
}
~~~

Cách diễn giải:

- Count 1: hàng có ID và version đúng đã được update.
- Count 0: không có hàng thỏa điều kiện. Bản ghi có thể không tồn tại hoặc version đã thay đổi do một thao tác khác.
- Count lớn hơn 1: điều kiện không đủ định danh duy nhất hoặc schema không như mong đợi.

Nếu dùng Spring Data R2DBC entity với @Version, cơ chế persistence có thể tự thêm điều kiện version và cập nhật version. Khi optimistic locking thất bại, Spring Data thường báo lỗi optimistic locking thay vì yêu cầu caller tự diễn giải count. Với SQL trực tiếp qua DatabaseClient, ứng dụng tự chịu trách nhiệm kiểm tra rowsUpdated và chuyển count 0 thành lỗi xung đột hoặc không tìm thấy theo chính sách nghiệp vụ.

Không tăng version ở cả service và câu SQL nếu Spring Data đã quản lý version cho cùng thao tác. Tránh tăng version hai lần hoặc bỏ qua điều kiện version.

## 9. rowsUpdated() với UPDATE/DELETE trong R2dbcEntityTemplate

Nếu thao tác ở mức entity và muốn tận dụng mapping của Spring Data, có thể dùng R2dbcEntityTemplate. Các fluent operation update/delete trả về số hàng tác động dưới dạng publisher số lượng theo API tương ứng.

Ví dụ update theo Criteria:

~~~java
Query query = Query.query(
    Criteria.where("id").is(customerId)
);

Update update = Update.update("active", false);

Mono<Long> rowsUpdated =
    template.update(Customer.class)
        .matching(query)
        .apply(update);
~~~

Ví dụ delete theo điều kiện:

~~~java
Mono<Long> rowsDeleted =
    template.delete(Customer.class)
        .matching(query)
        .all();
~~~

Template phù hợp khi điều kiện được xây dựng động bằng Query/Criteria và muốn Spring Data xử lý entity mapping, conversion và dialect. DatabaseClient phù hợp khi muốn viết SQL trực tiếp.

Cần phân biệt API trả count với repository CRUD thông thường. Ví dụ, ReactiveCrudRepository.deleteById(id) thường trả về Mono<Void> để báo hoàn tất hoặc lỗi, không cung cấp count hàng bị xóa. Nếu cần count, chọn API có kết quả số lượng như template hoặc DatabaseClient, hoặc thiết kế custom repository query phù hợp.

## 10. rowsUpdated() và R2DBC SPI Result

Ở tầng thấp hơn Spring DatabaseClient là R2DBC SPI. Một thao tác thực thi Statement trả về các Result. R2DBC Result cung cấp getRowsUpdated() để đọc số hàng được cập nhật bởi result đó.

Về ý tưởng:

~~~java
Publisher<? extends Result> results =
    connection.createStatement(
        "UPDATE customer SET active = FALSE WHERE id = 10"
    ).execute();
~~~

Mỗi Result có thể cung cấp publisher số hàng:

~~~java
Publisher<Long> countPublisher =
    result.getRowsUpdated();
~~~

Spring DatabaseClient bọc quy trình thực thi và chuyển kết quả thành Reactor type quen thuộc, nên ứng dụng thường dùng:

~~~java
Mono<Long> count =
    databaseClient.sql(
        "UPDATE customer SET active = FALSE WHERE id = :id"
    )
    .bind("id", 10L)
    .fetch()
    .rowsUpdated();
~~~

Khi dùng trực tiếp SPI, ứng dụng phải tự quản lý connection, statement, result và việc đóng connection. DatabaseClient giảm phần boilerplate đó và tích hợp với các tiện ích Spring.

Một statement có thể tạo nhiều Result hoặc driver có cách báo update count khác nhau tùy dạng lệnh. Nếu thực thi batch hoặc nhiều statement, hãy kiểm tra cách driver phát các count và cách API tổng hợp chúng; không suy diễn count của một lệnh đơn thành quy tắc cho mọi batch.

## 11. rowsUpdated() không phải số hàng SELECT trả về

rowsUpdated() dùng cho số hàng được tác động bởi câu lệnh ghi. Nó không phải API đếm số hàng SELECT trả về.

Nếu cần đọc dữ liệu, dùng map/fetch:

~~~java
Flux<Customer> customers =
    databaseClient.sql("""
            SELECT id, full_name, email
            FROM customer
            WHERE active = TRUE
            """)
        .map((row, metadata) ->
            new Customer(
                row.get("id", Long.class),
                row.get("full_name", String.class),
                row.get("email", String.class),
                null,
                true,
                null
            )
        )
        .all();
~~~

Nếu cần đếm số hàng thỏa một điều kiện SELECT, dùng COUNT(*):

~~~java
Mono<Long> countCustomers =
    databaseClient.sql("""
            SELECT COUNT(*)
            FROM customer
            WHERE active = TRUE
            """)
        .map((row, metadata) -> row.get(0, Long.class))
        .one();
~~~

Khác biệt:

| Nhu cầu | API phù hợp |
|---|---|
| Biết UPDATE tác động bao nhiêu hàng | fetch().rowsUpdated() |
| Biết DELETE xóa bao nhiêu hàng | fetch().rowsUpdated() |
| Biết INSERT tạo bao nhiêu hàng | fetch().rowsUpdated() |
| Đọc các hàng SELECT | map(...).all() |
| Đọc một hàng SELECT | map(...).one() hoặc first() |
| Đếm số hàng thỏa điều kiện SELECT | SELECT COUNT(*) và map kết quả |

Với SQL có RETURNING, nếu cần các giá trị trả về như ID hoặc trạng thái mới, hãy map result row. Không dùng count thay cho dữ liệu được trả về.

## 12. Reactive execution: khi nào câu SQL thực sự chạy?

DatabaseClient trả về Mono/Flux theo mô hình reactive. Các publisher thường là lazy: câu SQL được thực thi khi publisher được subscribe, trực tiếp hoặc thông qua một subscriber ở tầng framework.

Ví dụ:

~~~java
Mono<Long> rows =
    databaseClient.sql("""
            DELETE FROM customer
            WHERE id = :id
            """)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated();
~~~

Tại thời điểm gán biến rows, ứng dụng mới xây dựng publisher. Câu SQL chưa nhất thiết được gửi xuống database. Khi controller, service hoặc framework subscribe vào publisher, thao tác mới được thực thi.

Không nên gọi subscribe() bên trong service chỉ để lấy count rồi tiếp tục xử lý. Hãy trả publisher hoặc kết hợp bằng map/flatMap:

~~~java
public Mono<String> deleteMessage(Long id) {
    return deleteCustomer(id)
        .map(rows -> rows == 1
            ? "Customer deleted"
            : "Customer not found"
        );
}
~~~

Cách này giữ lỗi, kết quả và transaction trong cùng reactive chain.

## 13. Transaction và ý nghĩa của count

rowsUpdated cho biết kết quả của câu lệnh, nhưng không tự đảm bảo transaction chứa câu lệnh đã commit.

Ví dụ một transaction có hai thao tác:

1. UPDATE customer.
2. INSERT audit_log.

Nếu bước 1 trả count 1 nhưng bước 2 thất bại, transaction có thể rollback. Sau rollback, thay đổi customer không còn được giữ trong database dù publisher rowsUpdated đã từng phát ra 1 bên trong transaction.

Có thể phối hợp nhiều thao tác trong reactive transaction:

~~~java
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Transactional
public Mono<Long> deactivateAndAudit(Long customerId) {
    return databaseClient.sql("""
            UPDATE customer
            SET active = FALSE
            WHERE id = :id
            """)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated()
        .flatMap(rows -> {
            if (rows == 0) {
                return Mono.error(
                    new CustomerNotFoundException(customerId)
                );
            }

            return databaseClient.sql("""
                    INSERT INTO audit_log (entity_id, action)
                    VALUES (:id, 'DEACTIVATE')
                    """)
                .bind("id", customerId)
                .fetch()
                .rowsUpdated()
                .thenReturn(rows);
        });
}
~~~

Ví dụ giả định cả hai thao tác dùng cùng ConnectionFactory và reactive transaction manager. Nếu insert audit thất bại, lỗi được truyền qua cùng publisher chain để transaction có thể rollback.

Không gọi block() hoặc subscribe() bên trong phương thức transactional. Không tách thao tác thành publisher chạy độc lập nếu muốn chúng tham gia cùng transaction context.

## 14. Xử lý lỗi và ghi log

Có thể ghi nhận số hàng sau khi thao tác hoàn tất:

~~~java
return updateEmail(customerId, email)
    .doOnNext(rows ->
        log.info("Updated customer rows: {}", rows)
    );
~~~

Chỉ log dữ liệu cần thiết. Không log mật khẩu, token hoặc giá trị nhạy cảm được bind vào SQL.

Có thể chuyển lỗi kỹ thuật thành lỗi nghiệp vụ:

~~~java
return updateWithVersion(id, expectedVersion, newName)
    .flatMap(rows -> {
        if (rows == 1) {
            return Mono.just("Updated");
        }
        if (rows == 0) {
            return Mono.error(
                new ConcurrentCustomerUpdateException(id)
            );
        }
        return Mono.error(
            new IllegalStateException(
                "Unexpected affected row count: " + rows
            )
        );
    });
~~~

Trong thực tế, count 0 có thể là bản ghi không tồn tại hoặc version không còn khớp. Nếu API cần phân biệt hai trường hợp, phải có bước kiểm tra bổ sung hoặc thiết kế lỗi/điều kiện update rõ ràng. Bước kiểm tra sau đó cũng cần cân nhắc race condition.

## 15. Những lỗi thường gặp

### 15.1. Dùng rowsUpdated() cho SELECT

SELECT trả về dữ liệu hàng, không phải số hàng được tác động bởi DML. Dùng map(...).all(), one(), first() hoặc SELECT COUNT(*).

### 15.2. Nghĩ count 0 là lỗi SQL

Count 0 thường là một kết quả hợp lệ: câu lệnh chạy thành công nhưng không có hàng nào khớp. Chỉ chuyển thành lỗi nếu nghiệp vụ yêu cầu phải có hàng được tác động.

### 15.3. Nghĩ count 1 có nghĩa transaction đã commit

Count là kết quả statement. Transaction có thể rollback sau đó do một thao tác khác thất bại.

### 15.4. Nghĩ rowsUpdated trả về ID được sinh

Count chỉ là số hàng. Muốn ID, dùng generated values hoặc SQL RETURNING và map cột ID.

### 15.5. Bỏ qua count khi cần xác nhận một hàng

Nếu update theo ID phải tác động đúng một hàng, đừng chỉ bỏ qua kết quả. Kiểm tra count để phát hiện không tìm thấy hoặc điều kiện không đúng.

### 15.6. Chuyển mọi lỗi thành 0

Không dùng onErrorReturn(0L) chung chung. Lỗi kết nối, constraint và cú pháp SQL không đồng nghĩa không có hàng khớp.

### 15.7. Không dùng bind parameter

Nối giá trị đầu vào vào SQL có thể gây lỗi cú pháp và SQL injection. Dùng bind/bindNull cho mọi giá trị dữ liệu.

### 15.8. Dùng count để suy luận giá trị đã thay đổi

Database/driver có thể định nghĩa affected-row count khác nhau khi UPDATE gán cùng giá trị cũ. Nếu nghiệp vụ cần biết thay đổi thực sự, phải kiểm tra semantics của hệ quản trị hoặc thiết kế câu lệnh khác.

## 16. Chọn API phù hợp

| Nhu cầu | API nên dùng |
|---|---|
| SQL trực tiếp và cần count | DatabaseClient.fetch().rowsUpdated() |
| Update/delete theo entity mapping và cần count | R2dbcEntityTemplate |
| CRUD repository đơn giản, chỉ cần hoàn tất | ReactiveCrudRepository |
| Repository query tùy chỉnh cần count | Custom query method theo kiểu trả về được hỗ trợ bởi phiên bản |
| Cần ID hoặc giá trị sau INSERT/UPDATE | Generated values, RETURNING và map result |
| Cần đếm hàng SELECT | SELECT COUNT(*) |
| Cần đọc nội dung SELECT | map(...).all()/one()/first() |

Nếu chỉ cần biết deleteById hoàn tất hay phát lỗi, repository CRUD là đủ. Nếu cần số hàng thực sự được báo cáo là tác động, dùng API trả count như DatabaseClient hoặc R2dbcEntityTemplate.

## 17. Ghi nhớ

rowsUpdated() của Spring R2DBC trả về Mono<Long> biểu diễn số hàng mà database/driver báo cáo đã bị tác động bởi một thao tác ghi. Dùng nó với INSERT, UPDATE và DELETE khi cần kiểm tra count; dùng map/fetch cho dữ liệu SELECT và RETURNING; dùng COUNT(*) khi cần đếm kết quả truy vấn.

Count bằng 0 không tự động là lỗi, count bằng 1 thường phù hợp với thao tác theo ID, còn count lớn hơn 1 cần được đánh giá theo điều kiện và nghiệp vụ. Count không phải ID sinh ra và cũng không chứng minh transaction đã commit. Hãy bind tham số, xử lý lỗi riêng với count 0, kiểm tra optimistic locking khi cần và giữ các publisher trong cùng reactive transaction chain.


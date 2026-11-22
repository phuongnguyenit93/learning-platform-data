# Không suy luận thành công toàn nghiệp vụ chỉ từ khóa vừa được tạo

Một `INSERT` có thể trả về khóa chính mới (`id`) rất sớm, ngay khi câu lệnh được cơ sở dữ liệu xử lý. **Khóa được sinh ra là thông tin định danh của một thao tác ghi; tự nó không chứng minh giao dịch đã commit, mọi quy tắc nghiệp vụ đều thỏa, hay các hệ thống bên ngoài đã hoàn thành công việc.** Đây là ranh giới cần giữ rõ khi dùng Spring JDBC, `JdbcTemplate`, `KeyHolder` hoặc bất kỳ API lưu dữ liệu nào trả về ID.

## 1. Tình huống điển hình

Giả sử một ứng dụng nhận yêu cầu đặt mua hai cuốn sách. Luồng xử lý dự kiến:

1. `INSERT purchase_order` với trạng thái `PENDING`, database sinh `order_id = 501`.
2. Giảm tồn kho bằng câu lệnh `UPDATE inventory ... WHERE available >= 2`.
3. Ghi các bản ghi liên quan và xác nhận trạng thái nghiệp vụ.
4. Commit giao dịch cơ sở dữ liệu; những bước cần hệ thống ngoài (thanh toán, gửi thông báo...) có quy trình riêng.

Nếu tại bước 2 không đủ hàng, lệnh `UPDATE` ảnh hưởng **0 hàng** và service ném ngoại lệ để rollback. Ứng dụng **đã từng nhìn thấy** khóa 501, nhưng bản ghi đơn hàng vừa chèn có thể không tồn tại sau rollback. Một cơ chế cấp ID như sequence/identity vẫn có thể tiêu thụ giá trị 501, tạo khoảng trống trong dãy ID. Không nên dựa vào khoảng trống hay tính liên tiếp của ID để phán đoán giao dịch thành công hoặc thất bại.

Ví dụ thông báo sai: “Đơn hàng 501 đã thanh toán thành công” ngay khi `KeyHolder.getKey()` trả về 501. Thông báo đúng tại thời điểm đó chỉ là “Lệnh chèn đã trả về một ID tạm dùng trong luồng xử lý”. Trạng thái cuối cùng phải được quyết định sau khi kiểm tra các điều kiện nghiệp vụ thích hợp và kết quả transaction/khâu tích hợp.

## 2. Phân biệt năm mức bằng chứng

| Dấu hiệu quan sát được | Điều có thể kết luận | Điều **chưa** thể kết luận |
| --- | --- | --- |
| `KeyHolder` chứa khóa mới | JDBC driver trả về giá trị cột được sinh theo cấu hình câu lệnh | Commit thành công; đơn hàng hợp lệ; thanh toán thành công |
| `JdbcTemplate.update(...)` trả `1` | Câu lệnh đó báo ảnh hưởng một hàng | Toàn bộ các câu lệnh khác đều thành công; transaction đã commit |
| Đọc thấy bản ghi ngay trong transaction | Transaction hiện tại nhìn thấy dữ liệu do chính nó ghi | Giao dịch đã bền vững đối với transaction khác |
| Transaction commit thành công | Các thay đổi thuộc **transaction cơ sở dữ liệu đó** đã được chấp nhận, theo bảo đảm của DB | API thanh toán, broker, email và các transaction độc lập đã thành công |
| Trạng thái nghiệp vụ được kiểm chứng | Những điều kiện ứng với trạng thái ấy đã được hoàn tất và ghi nhận | Những bước tương lai chưa diễn ra cũng sẽ thành công |

Một hệ thống có thể tạo tài nguyên `PENDING` thành công, nhưng **chưa** hoàn tất đơn hàng ở trạng thái `PAID` hoặc `DELIVERED`. “Tạo đơn hàng thành công” và “thanh toán thành công” là hai mệnh đề khác nhau, dù dùng chung một `order_id`.

## 3. Spring JDBC thực sự trả về điều gì?

Ví dụ phương thức chỉ chèn một hàng và lấy ID bằng `JdbcTemplate`:

```java
// Phương thức nằm trong một lớp đang có JdbcTemplate jdbc.
long insertPendingOrder(JdbcTemplate jdbc, String sku, int quantity) {
    KeyHolder holder = new GeneratedKeyHolder();

    int affected = jdbc.update(connection -> {
        PreparedStatement statement = connection.prepareStatement(
            "INSERT INTO purchase_order (sku, quantity, status) VALUES (?, ?, ?)",
            new String[] { "ID" }
        );
        statement.setString(1, sku);
        statement.setInt(2, quantity);
        statement.setString(3, "PENDING");
        return statement;
    }, holder);

    if (affected != 1) {
        throw new IllegalStateException("INSERT_NOT_ONE_ROW");
    }

    Number generated = holder.getKey();
    if (generated == null) {
        throw new IllegalStateException("GENERATED_KEY_MISSING");
    }

    return generated.longValue();
}
```

Ở đây:

- `connection.prepareStatement(sql, new String[] {"ID"})` yêu cầu JDBC driver trả về cột khóa được sinh. Cách khai báo cột và khả năng hỗ trợ phụ thuộc driver/database.
- `JdbcTemplate.update(PreparedStatementCreator, KeyHolder)` trả **số hàng chịu tác động** và nạp các khóa mà driver cung cấp vào `KeyHolder`. Đó là hai thông tin kỹ thuật của câu lệnh `INSERT`.
- `GeneratedKeyHolder.getKey()` phù hợp khi ta kỳ vọng **một khóa số duy nhất**. Nếu trả về nhiều cột hoặc nhiều hàng, phải làm việc với `getKeys()` hoặc `getKeyList()` theo cấu trúc thực tế; không giả định `getKey()` luôn hợp lệ.
- Thiếu khóa, khóa không phải kiểu số, `affected != 1`, hoặc `DataAccessException` cần được xử lý theo hợp đồng của thao tác ghi. **Không** tự nâng kết quả `affected == 1 && id != null` thành cờ `businessSuccess = true`.
- Các API khác như `SimpleJdbcInsert.executeAndReturnKey(...)` cũng không đổi ý nghĩa transaction hay tiêu chí nghiệp vụ: có ID vẫn chỉ là một tín hiệu trong quy trình.

Nếu phương thức này chạy bên trong `@Transactional`, việc lấy được ID xảy ra **trước thời điểm transaction commit**. Một thao tác tiếp theo lỗi hoặc một ràng buộc bị kiểm tra lúc commit có thể làm cả transaction thất bại.

## 4. Ví dụ Java 17+ chạy được: có ID rồi vẫn rollback

Để quan sát chính xác sự khác nhau, ví dụ dùng Spring JDBC, `TransactionTemplate` và cơ sở dữ liệu H2 chạy trong bộ nhớ. Nghiệp vụ ví dụ là **giữ tồn kho** cho một đơn hàng; ví dụ không mô phỏng thanh toán hay giao hàng.

Tạo `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'GeneratedKeyDemo'
}
```

Tạo `src/main/java/GeneratedKeyDemo.java`:

```java
import java.sql.PreparedStatement;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.transaction.support.TransactionTemplate;

public class GeneratedKeyDemo {
    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:key_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        TransactionTemplate transaction = new TransactionTemplate(
            new DataSourceTransactionManager(dataSource)
        );

        jdbc.execute(
            "CREATE TABLE inventory (" +
            "sku VARCHAR(32) PRIMARY KEY, available INT NOT NULL)"
        );
        jdbc.execute(
            "CREATE TABLE purchase_order (" +
            "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, " +
            "sku VARCHAR(32) NOT NULL, quantity INT NOT NULL, " +
            "status VARCHAR(16) NOT NULL)"
        );
        jdbc.update(
            "INSERT INTO inventory (sku, available) VALUES (?, ?)",
            "BOOK", 1
        );

        try {
            reserve(jdbc, transaction, "BOOK", 2);
        } catch (IllegalStateException exception) {
            System.out.println("Request failed: " + exception.getMessage());
        }
        System.out.println(
            "Orders after rollback: " +
            jdbc.queryForObject("SELECT COUNT(*) FROM purchase_order", Integer.class)
        );

        long committedId = reserve(jdbc, transaction, "BOOK", 1);
        System.out.println("Reservation committed: " + (committedId > 0));
        System.out.println(
            "Orders after commit: " +
            jdbc.queryForObject("SELECT COUNT(*) FROM purchase_order", Integer.class)
        );
        System.out.println(
            "Remaining inventory: " +
            jdbc.queryForObject(
                "SELECT available FROM inventory WHERE sku = ?",
                Integer.class, "BOOK"
            )
        );
    }

    private static long reserve(
        JdbcTemplate jdbc,
        TransactionTemplate transaction,
        String sku,
        int quantity
    ) {
        Long id = transaction.execute(status -> {
            KeyHolder holder = new GeneratedKeyHolder();

            int inserted = jdbc.update(connection -> {
                PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO purchase_order (sku, quantity, status) " +
                    "VALUES (?, ?, ?)",
                    new String[] { "ID" }
                );
                statement.setString(1, sku);
                statement.setInt(2, quantity);
                statement.setString(3, "PENDING");
                return statement;
            }, holder);

            if (inserted != 1) {
                throw new IllegalStateException("INSERT_NOT_ONE_ROW");
            }
            Number rawKey = holder.getKey();
            if (rawKey == null) {
                throw new IllegalStateException("GENERATED_KEY_MISSING");
            }
            long orderId = rawKey.longValue();
            System.out.println("Generated key obtained: " + (orderId > 0));

            int reserved = jdbc.update(
                "UPDATE inventory SET available = available - ? " +
                "WHERE sku = ? AND available >= ?",
                quantity, sku, quantity
            );
            if (reserved != 1) {
                throw new IllegalStateException("OUT_OF_STOCK");
            }

            int marked = jdbc.update(
                "UPDATE purchase_order SET status = ? WHERE id = ?",
                "RESERVED", orderId
            );
            if (marked != 1) {
                throw new IllegalStateException("STATE_UPDATE_FAILED");
            }
            return orderId;
        });

        return Objects.requireNonNull(id);
    }
}
```

Với JDK 17+ và Gradle đã cài (hoặc Gradle Wrapper của dự án), chạy `gradle run` (hoặc `./gradlew run`). Bỏ qua log của Gradle, **stdout của chương trình** là:

```text
Generated key obtained: true
Request failed: OUT_OF_STOCK
Orders after rollback: 0
Generated key obtained: true
Reservation committed: true
Orders after commit: 1
Remaining inventory: 0
```

Giải thích theo đúng thứ tự:

1. Yêu cầu đầu tiên tạo hàng `purchase_order` trạng thái `PENDING` và nhận được ID. Sau đó lệnh trừ hai sản phẩm trả `0` vì tồn kho chỉ có một. Ngoại lệ `OUT_OF_STOCK` làm `TransactionTemplate` rollback cả lệnh chèn: đếm đơn hàng từ kết nối ngoài transaction được `0`.
2. Yêu cầu thứ hai chèn đơn, trừ một sản phẩm và cập nhật trạng thái `RESERVED` trong **cùng transaction**. Khi `transaction.execute(...)` trả về ở ví dụ này, commit đã hoàn tất vì không có outer transaction nào đang bao quanh. Sau đó mới báo “Reservation committed”.
3. Không so sánh ID của hai lần chèn, vì cơ chế cấp khóa có thể để lại khoảng trống sau rollback. Điều được kiểm chứng là **số hàng thực tồn tại và trạng thái/tồn kho**, không phải giá trị hay thứ tự ID.
4. Ví dụ sử dụng `DriverManagerDataSource` chỉ để đơn giản hóa chạy thử; ứng dụng thực tế thường dùng connection pool được cấu hình và quản lý theo môi trường triển khai.

Bài học cốt lõi của đoạn code: **Một dòng log “Generated key obtained: true” có thể đi liền ngay sau đó với rollback và không có đơn hàng nào được lưu.**

## 5. Đặt ranh giới transaction ở đâu?

Với một nhóm thao tác dữ liệu **cùng một cơ sở dữ liệu**, cần chọn ranh giới transaction bao trùm những bước phải thành công hoặc thất bại cùng nhau: chèn đơn, kiểm tra/trừ tồn, chèn chi tiết đơn, ghi outbox, cập nhật trạng thái... Không được gọi chúng như các thao tác rời rạc có auto-commit rồi chỉ dựa vào ID đầu tiên để tuyên bố thành công.

Ví dụ với Spring service:

```java
@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderApplicationService(
        OrderRepository orders,
        InventoryRepository inventory
    ) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public long reserveOrder(PlaceOrder command) {
        long id = orders.insertPending(command); // Đã có key, vẫn chưa commit.

        boolean reserved = inventory.tryReserve(
            command.sku(), command.quantity()
        );
        if (!reserved) {
            throw new IllegalStateException("OUT_OF_STOCK");
        }

        orders.markReserved(id);
        return id; // Spring còn phải hoàn tất transaction ở proxy.
    }
}
```

Đây là **mã minh họa cấu trúc service**, phụ thuộc các lớp `OrderRepository`, `InventoryRepository` và `PlaceOrder` của ứng dụng; đoạn demo H2 ở trên mới là chương trình độc lập.

Những điểm cần tránh nhầm:

- `@Transactional` theo cơ chế proxy mặc định chỉ áp dụng với lời gọi đi **qua Spring proxy**. Một phương thức trong cùng object tự gọi phương thức `@Transactional` khác (`this.method()`) không kích hoạt advice transaction cho lời gọi nội bộ ấy.
- Mặc định, `@Transactional` thường rollback khi `RuntimeException` hoặc `Error` thoát khỏi phương thức; ngoại lệ checked có thể cần `rollbackFor` hoặc cấu hình quy tắc rollback riêng. **Bắt ngoại lệ rồi im lặng trả về success** có thể vô tình cho phép commit trạng thái chưa hợp lệ.
- Với propagation mặc định `REQUIRED`, nếu service tham gia một **outer transaction**, lúc phương thức service trả về vẫn chưa chắc outer transaction đã commit. Chỉ tầng sở hữu ranh giới transaction ngoài cùng mới có thể kết luận kết quả commit của toàn bộ đơn vị công việc đó.
- Commit vẫn có thể phát sinh lỗi (ví dụ một số ràng buộc deferred hoặc sự cố kết nối); không coi ID đã có trước commit là bằng chứng commit thành công.
- Transaction JDBC thông thường **không bao trùm tự động** HTTP API, payment gateway, email hay message broker. Chỉ được tuyên bố một bước bên ngoài hoàn tất khi có bằng chứng tương ứng theo hợp đồng của bước ấy.

## 6. Thiết kế kết quả nghiệp vụ dựa trên bất biến và trạng thái

Nên đặt tên kết quả theo đúng điều thực sự đã hoàn thành, ví dụ:

| Trạng thái | Điều kiện tối thiểu để công bố |
| --- | --- |
| `PENDING` | Yêu cầu được ghi nhận hợp lệ theo hợp đồng tạo đơn; các bước tiếp theo đang chờ |
| `RESERVED` | Đã giữ tồn kho theo quy tắc nghiệp vụ và ghi nhận thành công trong transaction liên quan |
| `PAID` | Có xác nhận thanh toán hợp lệ đã được đối chiếu với đơn và cập nhật trạng thái đúng quy trình |
| `COMPLETED` | Tất cả tiêu chí hoàn tất mà sản phẩm quy định đã được kiểm chứng, có thể bao gồm giao hàng/hậu kiểm |

Không có quy tắc chung “cứ có ID thì trạng thái là `COMPLETED`”. Bản ghi vừa tạo có thể là một yêu cầu đang chờ, một giao dịch cần xác minh, hoặc một tác vụ đã tiếp nhận.

Ví dụ contract API có thể dùng response:

```json
{
  "orderId": 501,
  "status": "PENDING_PAYMENT",
  "message": "Đã tạo đơn; chưa xác nhận thanh toán"
}
```

Đây là ví dụ **biểu diễn trạng thái**, không phải lời hứa rằng ID 501 có thể tồn tại sau một transaction chưa commit. API nên tạo response thành công sau khi ranh giới transaction cần thiết đã được xử lý, và tách trạng thái tạo tài nguyên khỏi trạng thái hoàn tất quy trình. HTTP `201 Created` có thể phù hợp cho tài nguyên đã được tạo; nó không mặc nhiên đồng nghĩa `PAID`. Với xử lý bất đồng bộ, có thể dùng `202 Accepted` khi API chỉ nhận yêu cầu và chưa hoàn tất xử lý.

Nếu hệ thống hỗ trợ gửi lại request, cần có **idempotency key/unique constraint** và kiểm tra trạng thái hiện có để tránh tạo hai đơn cho một yêu cầu; generated ID mới trên mỗi lần gọi không giải quyết vấn đề lặp nghiệp vụ.

## 7. Ranh giới với sự kiện và hệ thống ngoài

Giả sử giữ hàng đã commit nhưng cần gửi sự kiện `OrderReserved` cho một hệ thống khác. Có ba khả năng thường gặp:

- Gửi sự kiện **trước commit**: consumer có thể xử lý một đơn cuối cùng bị rollback.
- Gửi sự kiện **sau commit**: tránh phát sự kiện cho transaction đã rollback, nhưng process có thể chết sau commit và trước khi gửi; vì thế “đã commit” vẫn không bảo đảm event được chuyển đi.
- Ghi **transactional outbox** trong cùng transaction với đơn hàng và có publisher đọc/gửi lại outbox: làm giảm nguy cơ mất sự kiện trong khoảng giữa commit và publish. Consumer vẫn nên idempotent vì có thể nhận trùng.

Spring hỗ trợ `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` để chạy listener khi commit thành công; đó là **điểm móc theo phase**, không phải cam kết giao hàng bền vững đến message broker. Chọn outbox, retry và đối soát theo yêu cầu độ tin cậy thực tế. Các quy trình nhiều hệ thống thường cần điều phối trạng thái, retry, bù trừ hoặc saga; không thể suy ra “toàn nghiệp vụ thành công” từ kết quả một `INSERT` cục bộ.

## 8. Kiểm chứng đúng bằng test và log

Một bộ kiểm thử có giá trị cần kiểm chứng **trạng thái cuối sau transaction**, thay vì chỉ assert `id != null`:

1. **Đủ tồn kho:** transaction trả về thành công; có đúng một đơn, trạng thái `RESERVED`, tồn kho giảm chính xác.
2. **Không đủ tồn kho:** đã lấy được generated key bên trong transaction nhưng service ném `OUT_OF_STOCK`; sau rollback không có đơn mới, tồn kho không đổi.
3. **Lỗi sau `INSERT`:** chèn chi tiết/outbox thất bại; toàn bộ dữ liệu thuộc cùng transaction rollback theo cấu hình. Kiểm tra bằng kết nối/transaction kiểm chứng độc lập.
4. **Lỗi khi commit:** caller nhận lỗi transaction; không phát thông báo hoàn tất chỉ vì trước đó đã log một ID.
5. **Tích hợp ngoài bị timeout:** duy trì trạng thái trung gian có thể đối soát, không đánh dấu `PAID` chỉ dựa vào việc đã sinh `order_id`.
6. **Request gửi lại:** ràng buộc idempotency bảo vệ không tạo các giao dịch nghiệp vụ trùng nhau.

Logging nên gắn **correlation/request ID**, generated entity ID, phase, số hàng ảnh hưởng, transaction outcome khi quan sát được, và trạng thái nghiệp vụ. Ví dụ hai log `orderId=501 created` và `orderId=501 transaction rolled back` diễn tả điều có thể xảy ra; không tự rút kết luận từ log đầu.

## 9. Những ngộ nhận cần loại bỏ

- **“`getKey() != null` nghĩa là database đã lưu vĩnh viễn.”** Sai: khóa có thể xuất hiện trước commit và transaction có thể rollback.
- **“`update() == 1` nghĩa là toàn bộ workflow thành công.”** Sai: đó là số hàng của **một câu lệnh**.
- **“Đã `SELECT` thấy đơn trong cùng transaction nên chắc chắn đã commit.”** Sai: đọc của chính transaction có thể thấy dữ liệu chưa commit.
- **“ID không liên tiếp nghĩa là mất dữ liệu.”** Không nhất thiết: sequence/identity và rollback, cache, cạnh tranh đồng thời đều có thể gây khoảng trống.
- **“Có `@Transactional` là cả API ngoài và message broker cùng rollback.”** Sai: transaction DB không tự tạo một giao dịch phân tán với các hệ thống ấy.
- **“Method `@Transactional` trả ID là commit xong trong mọi trường hợp.”** Sai khi lời gọi tham gia outer transaction chưa kết thúc; ngoài ra phải thực sự đi qua proxy để được áp dụng advice.
- **“Listener `AFTER_COMMIT` đảm bảo sự kiện không thể mất.”** Sai: listener theo phase không thay cho outbox/bảo đảm phát lại.

## 10. Quy tắc dùng ngay khi thiết kế

Trước khi trả về “thành công”, hãy xác định thành công **của thao tác nào**. Kiểm tra: (a) câu lệnh SQL và row count, (b) khóa được sinh đúng kiểu và được dùng đúng chỗ, (c) mọi bất biến thuộc transaction đã đạt, (d) transaction thực sự kết thúc theo kết quả mong đợi ở ranh giới sở hữu nó, (e) trạng thái nghiệp vụ được công bố khớp với bằng chứng, (f) các bước tích hợp có cơ chế xác nhận/khôi phục riêng. Không dùng một ID để thay thế bất kỳ bước kiểm chứng nào.

**Ghi nhớ:** `generated key` trả lời **“dòng dữ liệu này được định danh như thế nào?”**, còn **“toàn nghiệp vụ đã thành công chưa?”** phải được trả lời bằng kết quả transaction, các bất biến nghiệp vụ, trạng thái và bằng chứng từ các hệ thống liên quan.

### Tài liệu tham khảo

- [Spring Framework – JdbcTemplate API, update với KeyHolder](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework – Transaction propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework – Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)

# Sử dụng inConnection và inConnectionMany khi cần truy cập Connection

## 1. Khi nào cần truy cập trực tiếp Connection?

Trong Spring Data Relational R2DBC, phần lớn thao tác dữ liệu có thể thực hiện qua repository, R2dbcEntityTemplate hoặc DatabaseClient. Các abstraction này giúp viết truy vấn, bind tham số và ánh xạ kết quả mà không phải quản lý Connection trực tiếp.

Tuy nhiên, có những tình huống cần truy cập đối tượng io.r2dbc.spi.Connection:

- Dùng trực tiếp R2DBC SPI để tạo Statement, đọc Result hoặc thực hiện một chuỗi thao tác mức thấp.
- Đọc metadata của connection hoặc database.
- Thiết lập một tùy chọn cấp phiên mà driver hoặc hệ quản trị cung cấp.
- Dùng tính năng riêng của driver hoặc database chưa được abstraction cấp cao biểu diễn.
- Thực hiện nhiều lệnh trên cùng một connection trong một phạm vi xử lý có kiểm soát.

DatabaseClient cung cấp hai phương thức hỗ trợ việc này:

- **inConnection(...):** thực hiện callback với một Connection và trả về Mono cho kết quả đơn.
- **inConnectionMany(...):** thực hiện callback với một Connection và trả về Flux cho luồng kết quả.

Hai phương thức cho phép dùng R2DBC SPI trong khi vẫn để Spring quản lý việc lấy và giải phóng connection. Bạn có thể truy cập connection trực tiếp mà không phải tự viết lại toàn bộ vòng đời tài nguyên.

## 2. Connection và vòng đời tài nguyên trong R2DBC

### 2.1. Connection là tài nguyên có trạng thái

io.r2dbc.spi.Connection đại diện cho một phiên làm việc với database. Từ connection, bạn có thể tạo statement, đọc metadata, quản lý transaction hoặc gọi các thao tác cấp phiên mà driver hỗ trợ.

Một connection không phải đối tượng Java thông thường để giữ lâu dài trong service. Nó có thể được lấy từ connection pool, có trạng thái phiên và cần được giải phóng sau khi publisher hoàn tất.

Thông thường, ứng dụng không nên tự gọi ConnectionFactory.create() cho từng thao tác nghiệp vụ nếu đã dùng DatabaseClient. Hãy để DatabaseClient lấy connection theo cơ chế Spring quản lý.

### 2.2. DatabaseClient quản lý việc lấy và giải phóng connection

Với thao tác thông thường:

~~~java
Mono<Customer> customer =
    databaseClient.sql("""
        SELECT id, full_name
        FROM customers
        WHERE id = :id
        """)
        .bind("id", customerId)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("full_name", String.class)
        ))
        .one();
~~~

DatabaseClient chịu trách nhiệm lấy connection, thực thi statement, đọc kết quả và giải phóng connection khi thao tác kết thúc hoặc bị hủy. Nếu dùng connection pool, việc giải phóng thường trả connection về pool để tái sử dụng.

Khi cần truy cập SPI, inConnection và inConnectionMany cung cấp chính connection mà DatabaseClient đã lấy cho callback. Khi publisher do callback trả về kết thúc, lỗi hoặc bị cancel, Spring hoàn tất vòng đời connection theo ConnectionFactory và transaction context đang áp dụng.

Vì vậy, trong callback:

- Không tự gọi connection.close() như thể bạn tự acquire connection từ factory.
- Không lưu Connection vào field, singleton hoặc biến dùng chung giữa request.
- Không trả Connection ra ngoài callback để dùng sau.
- Không gọi subscribe() hoặc block() bên trong callback.
- Hãy trả về publisher đại diện cho toàn bộ công việc cần thực hiện trên connection.

### 2.3. inConnection không tự động mở transaction

Có một điểm rất dễ nhầm: dùng cùng một Connection không đồng nghĩa các câu lệnh tự động nằm trong một transaction.

inConnection và inConnectionMany quản lý phạm vi sử dụng connection cho callback. Nếu không có reactive transaction đang hoạt động, các câu lệnh vẫn tuân theo chế độ transaction/autocommit của connection và database. Không nên giả định nhiều câu SQL trong callback sẽ tự động commit hoặc rollback như một đơn vị nguyên tử.

Nếu nhiều thao tác phải cùng thành công hoặc cùng thất bại, hãy cấu hình R2DBC transaction manager và dùng @Transactional hoặc TransactionalOperator. Khi transaction reactive đang hoạt động trên cùng ConnectionFactory, DatabaseClient có thể sử dụng connection đã được gắn với transaction context.

## 3. Phân biệt inConnection và inConnectionMany

Hai phương thức có mục đích tương tự nhưng khác kiểu kết quả:

| Phương thức | Kiểu kết quả | Dùng khi |
|---|---|---|
| inConnection | Mono<T> | Callback tạo ra một kết quả đơn hoặc chỉ cần báo hoàn tất |
| inConnectionMany | Flux<T> | Callback phát ra không, một hoặc nhiều phần tử |

Có thể hình dung:

~~~text
DatabaseClient
     |
     +-- inConnection(connection -> Mono<T>)
     |          |
     |          +-- một kết quả hoặc hoàn tất rỗng
     |
     +-- inConnectionMany(connection -> Publisher<T>)
                |
                +-- luồng 0..N phần tử
~~~

Cả hai đều cung cấp Connection cho callback. Khác biệt nằm ở cardinality của publisher mà callback trả về và kiểu reactive mà phương thức ngoài phát ra.

Không chọn phương thức theo số câu SQL. Một callback inConnection có thể thực hiện nhiều câu lệnh nhưng cuối cùng chỉ trả một kết quả Mono. Một callback inConnectionMany có thể đọc một truy vấn nhiều hàng và phát từng hàng qua Flux.

## 4. Dùng inConnection cho một kết quả

### 4.1. Cấu trúc cơ bản

Ví dụ tìm khách hàng theo ID bằng R2DBC SPI:

~~~java
public Mono<CustomerView> findCustomer(Long customerId) {
    return databaseClient.inConnection(connection ->
        Flux.from(
            connection.createStatement("""
                SELECT id, full_name
                FROM customers
                WHERE id = $1
                """)
                .bind(0, customerId)
                .execute()
        )
        .concatMap(result ->
            Flux.from(result.map((row, metadata) ->
                new CustomerView(
                    row.get("id", Long.class),
                    row.get("full_name", String.class)
                )
            ))
        )
        .singleOrEmpty()
    );
}
~~~

Ví dụ này dùng cú pháp bind marker PostgreSQL $1. Cú pháp marker trong Connection.createStatement() phụ thuộc driver; cần đổi theo database đang sử dụng.

Luồng xử lý:

1. inConnection lấy Connection do DatabaseClient quản lý.
2. createStatement(...) tạo statement trực tiếp từ R2DBC SPI.
3. bind(0, customerId) gắn giá trị vào marker đầu tiên.
4. execute() trả về publisher của Result.
5. result.map(...) chuyển mỗi Row thành CustomerView.
6. singleOrEmpty() biến luồng kết quả thành Mono, phù hợp với truy vấn theo khóa chính.
7. Khi publisher hoàn tất, lỗi hoặc bị cancel, vòng đời connection được DatabaseClient xử lý.

Nếu không tìm thấy khách hàng, singleOrEmpty() phát Mono.empty(). Nếu truy vấn trả về nhiều hơn một hàng, singleOrEmpty() phát lỗi cardinality. Với truy vấn theo primary key, điều này thường giúp phát hiện schema hoặc query không như kỳ vọng.

### 4.2. Khi callback chỉ cần trả về kết quả đếm hoặc trạng thái

Không phải callback nào cũng trả entity. Ví dụ, thực hiện một câu UPDATE và trả về số hàng bị ảnh hưởng:

~~~java
public Mono<Long> updateCustomerName(
        Long customerId,
        String newName) {

    return databaseClient.inConnection(connection ->
        Flux.from(
            connection.createStatement("""
                UPDATE customers
                SET full_name = $1
                WHERE id = $2
                """)
                .bind(0, newName)
                .bind(1, customerId)
                .execute()
        )
        .concatMap(result -> Flux.from(result.getRowsUpdated()))
        .singleOrEmpty()
        .defaultIfEmpty(0L)
    );
}
~~~

Result.getRowsUpdated() phát số hàng được cập nhật theo driver. singleOrEmpty() gom kết quả thành Mono; defaultIfEmpty(0L) biểu diễn trường hợp không có kết quả cập nhật bằng 0 trong ví dụ này.

Kiểu và số lượng giá trị mà getRowsUpdated() phát ra có thể phụ thuộc driver, đặc biệt với batch hoặc nhiều result. Với một UPDATE đơn giản, cách viết trên minh họa trường hợp thông thường.

### 4.3. Khi cần thực hiện nhiều thao tác nhưng chỉ trả một giá trị

Một callback inConnection có thể nối nhiều thao tác tuần tự và trả kết quả cuối cùng:

~~~java
public Mono<String> updateAndReadStatus(Long orderId) {
    return databaseClient.inConnection(connection -> {
        Mono<Long> updated = executeUpdate(connection, orderId);

        Mono<String> status = updated.then(
            readStatus(connection, orderId)
        );

        return status;
    });
}
~~~

executeUpdate và readStatus ở đây là các phương thức hỗ trợ trả publisher và sử dụng connection được truyền vào. then(...) bảo đảm bước đọc chỉ chạy sau khi bước cập nhật hoàn tất.

Cùng một callback connection không có nghĩa transaction được tự động mở. Nếu cập nhật và đọc phải được bảo vệ bởi một transaction có tính nguyên tử, hãy đặt publisher này trong reactive transaction được cấu hình phù hợp.

## 5. Dùng inConnectionMany cho nhiều kết quả

### 5.1. Cấu trúc cơ bản

Khi truy vấn có thể trả về nhiều hàng, dùng inConnectionMany:

~~~java
public Flux<CustomerView> findCustomersByStatus(String status) {
    return databaseClient.inConnectionMany(connection ->
        Flux.from(
            connection.createStatement("""
                SELECT id, full_name
                FROM customers
                WHERE status = $1
                ORDER BY id
                """)
                .bind(0, status)
                .execute()
        )
        .concatMap(result ->
            Flux.from(result.map((row, metadata) ->
                new CustomerView(
                    row.get("id", Long.class),
                    row.get("full_name", String.class)
                )
            ))
        )
    );
}
~~~

Callback trả về Publisher<CustomerView>. DatabaseClient phát kết quả qua Flux<CustomerView>. Mỗi Row được chuyển thành một đối tượng CustomerView.

Không cần gọi collectList() nếu tầng gọi có thể xử lý từng phần tử. Flux cho phép xử lý theo luồng và hỗ trợ backpressure. Nếu gom thành List, toàn bộ phần tử sẽ được giữ trong bộ nhớ cho đến khi publisher hoàn tất.

### 5.2. Một Connection được giữ trong suốt thời gian Flux hoạt động

Với inConnectionMany, callback trả về một publisher có thể phát nhiều phần tử. Connection phải còn khả dụng trong thời gian publisher đó được tiêu thụ.

Điều này có nghĩa:

- Khi Flux hoàn tất, connection được giải phóng theo cơ chế quản lý của DatabaseClient.
- Khi Flux phát lỗi, quá trình xử lý kết thúc và connection được giải phóng.
- Khi subscriber cancel, cleanup được thực hiện theo cơ chế reactive.
- Nếu subscriber đọc chậm hoặc không tiêu thụ hết luồng, connection có thể bị giữ lâu hơn.

Vì vậy, không dùng inConnectionMany để tạo một Flux vô hạn hoặc chờ một sự kiện bên ngoài database trong khi vẫn giữ connection. Connection là tài nguyên hữu hạn của pool; giữ nó quá lâu có thể khiến request khác phải chờ.

### 5.3. Khi cần phát nhiều kết quả từ nhiều Result

Statement.execute() trả về Publisher<Result>. Một statement thông thường có thể trả một Result, nhưng API cho phép biểu diễn nhiều result trong một số trường hợp. Có thể xử lý các Result tuần tự bằng concatMap:

~~~java
return databaseClient.inConnectionMany(connection ->
    Flux.from(connection.createStatement(sql).execute())
        .concatMap(result ->
            Flux.from(result.map((row, metadata) ->
                mapCustomer(row)
            ))
        )
);
~~~

concatMap giữ thứ tự xử lý từng Result và từng publisher con. Đây là lựa chọn dễ kiểm soát khi các kết quả phụ thuộc cùng một connection.

## 6. Bind tham số trực tiếp qua R2DBC Statement

Khi dùng databaseClient.sql(...), bạn có thể dùng named binding:

~~~java
databaseClient.sql("""
    SELECT id
    FROM customers
    WHERE email = :email
    """)
    .bind("email", email);
~~~

Nhưng khi tạo statement trực tiếp từ Connection, bạn đang làm việc với R2DBC SPI. Cú pháp placeholder và cách bind do driver quyết định. API SPI tiêu chuẩn có bind(int index, Object value) và bindNull(int index, Class<?> type).

### 6.1. Bind theo vị trí

Ví dụ với PostgreSQL:

~~~java
connection.createStatement("""
    SELECT id, full_name
    FROM customers
    WHERE email = $1
      AND status = $2
    """)
    .bind(0, email)
    .bind(1, status);
~~~

Chỉ số trong bind(index, value) của R2DBC SPI bắt đầu từ 0. Trong ví dụ:

- $1 nhận giá trị từ bind(0, email).
- $2 nhận giá trị từ bind(1, status).

Cú pháp marker cụ thể không giống nhau ở mọi driver. Hãy kiểm tra tài liệu R2DBC driver cho database đang dùng và không sao chép $1 sang một hệ quản trị dùng marker khác.

### 6.2. Bind giá trị NULL

Không nên gọi bind(index, null) vì R2DBC SPI yêu cầu dùng bindNull để cung cấp kiểu Java của giá trị null.

~~~java
Statement statement = connection.createStatement("""
    INSERT INTO customers (id, full_name, email)
    VALUES ($1, $2, $3)
    """)
    .bind(0, customerId)
    .bind(1, fullName)
    .bindNull(2, String.class);
~~~

Kiểu trong bindNull giúp driver biết kiểu dữ liệu cần bind. Kiểu này phải tương thích với cột SQL.

Nếu giá trị không null, dùng bind(index, value). Nếu null, dùng bindNull(index, type).

### 6.3. Bind nhiều lần hoặc dùng Statement.add()

R2DBC SPI có API Statement cho phép thêm tập giá trị để thực thi nhiều lần với cùng cấu trúc statement, tùy khả năng driver. Tuy nhiên, cách hỗ trợ và hiệu quả của batch/bind set phụ thuộc driver.

Nếu cần batch insert/update, hãy kiểm tra tài liệu driver và cân nhắc DatabaseClient hoặc repository API trước. Không giả định mọi driver đều có cùng hành vi batching hoặc cùng mức tối ưu.

### 6.4. Parameter binding không thay thế identifier động

Bind marker dành cho giá trị, không dành cho tên bảng, tên cột hoặc từ khóa SQL.

Không thể dùng:

~~~sql
SELECT * FROM $1
~~~

với kỳ vọng $1 sẽ được thay bằng tên bảng. Nếu cần chọn bảng hoặc cột động, hãy dùng whitelist các identifier được phép và xây dựng cấu trúc SQL từ code tin cậy. Không nối nguyên văn dữ liệu do client gửi vào câu SQL.

## 7. Truy cập metadata của Connection

Một số thao tác cần thông tin phiên hoặc database. R2DBC Connection cung cấp getMetadata() để đọc metadata của connection.

Ví dụ:

~~~java
public Mono<String> getDatabaseProductName() {
    return databaseClient.inConnection(connection ->
        Mono.just(
            connection.getMetadata().getDatabaseProductName()
        )
    );
}
~~~

Metadata có thể cung cấp tên sản phẩm database và thông tin liên quan theo API của driver. Phần lớn thao tác metadata là truy cập trực tiếp trên đối tượng Connection và không nhất thiết phát sinh một câu SQL.

Không nên dùng metadata để thay thế cấu hình ứng dụng hoặc tự suy đoán toàn bộ khả năng SQL. Nếu cần tính năng riêng, hãy kiểm tra tài liệu driver và database tương ứng.

## 8. Dùng Connection cho các thao tác cấp phiên

Một số database cung cấp lệnh thiết lập trạng thái cấp session, ví dụ cấu hình schema hiện tại, timezone hoặc một biến phiên. Có thể cần chạy lệnh trên connection cụ thể rồi thực hiện truy vấn phụ thuộc trạng thái đó trong cùng callback.

Ví dụ minh họa PostgreSQL đặt search_path:

~~~java
public Mono<CustomerView> findCustomerInSchema(
        String schema,
        Long customerId) {

    if (!ALLOWED_SCHEMAS.contains(schema)) {
        return Mono.error(
            new IllegalArgumentException("Schema không được phép")
        );
    }

    return databaseClient.inConnection(connection ->
        Flux.from(connection.createStatement(
                "SET search_path TO " + schema
            ).execute())
            .concatMap(result -> Flux.from(result.getRowsUpdated()))
            .then(Mono.defer(() ->
                Flux.from(connection.createStatement("""
                        SELECT id, full_name
                        FROM customers
                        WHERE id = $1
                        """)
                    .bind(0, customerId)
                    .execute())
                    .concatMap(result -> Flux.from(result.map((row, metadata) ->
                        new CustomerView(
                            row.get("id", Long.class),
                            row.get("full_name", String.class)
                        )
                    )))
                    .singleOrEmpty()
            ))
    );
}
~~~

Ví dụ trên chỉ minh họa việc giữ hai thao tác trong cùng callback connection. Tên schema là SQL identifier nên không thể bind như giá trị; do đó phải kiểm tra bằng whitelist cố định trước khi ghép vào SQL. Cú pháp SET và cách quản lý schema phụ thuộc database.

Một rủi ro quan trọng là connection pool có thể tái sử dụng connection vật lý sau khi callback kết thúc. Nếu trạng thái phiên không được reset, trạng thái đó có thể ảnh hưởng đến request tiếp theo. Hãy ưu tiên cấu hình ở mức connection pool/connection initialization được driver hỗ trợ, hoặc bảo đảm trạng thái được khôi phục trước khi callback kết thúc. Không dựa vào việc pool luôn reset mọi thiết lập session tùy ý.

Nếu dùng @Transactional, cần kiểm tra cách thiết lập session và reset trạng thái tương thích với transaction. Một lệnh SET có thể có semantics riêng theo hệ quản trị và isolation/transaction mode.

## 9. Kết hợp inConnection với reactive transaction

### 9.1. Transaction được quản lý bởi Spring

Spring R2DBC có thể quản lý transaction reactive bằng R2dbcTransactionManager và TransactionalOperator hoặc @Transactional.

Khi transaction đang hoạt động, connection được gắn vào Reactor Context. Các thao tác truy cập dữ liệu qua cùng ConnectionFactory và cơ chế quản lý connection của Spring có thể sử dụng connection thuộc transaction đó.

Ví dụ:

~~~java
@Transactional
public Mono<CustomerView> updateCustomer(Long id, String name) {
    return databaseClient.inConnection(connection ->
        Mono.from(connection.createStatement("""
                UPDATE customers
                SET full_name = $1
                WHERE id = $2
                """)
            .bind(0, name)
            .bind(1, id)
            .execute())
            .flatMap(updateResult ->
                Mono.from(updateResult.getRowsUpdated())
            )
            .then(
                Mono.from(connection.createStatement("""
                        SELECT id, full_name
                        FROM customers
                        WHERE id = $1
                        """)
                    .bind(0, id)
                    .execute())
                    .flatMap(result ->
                        Mono.from(result.map((row, metadata) ->
                            new CustomerView(
                                row.get("id", Long.class),
                                row.get("full_name", String.class)
                            )
                        ))
                    )
            )
    );
}
~~~

Ví dụ thể hiện hai câu lệnh dùng cùng Connection được truyền vào callback. Với transaction reactive được cấu hình đúng, thao tác cập nhật và đọc thuộc cùng transaction.

Để điều này hoạt động như mong đợi:

1. Transaction manager phải là R2DBC reactive transaction manager.
2. Transaction manager và DatabaseClient phải dùng cùng ConnectionFactory.
3. Phương thức trả về publisher reactive để transaction context được truyền xuyên suốt.
4. Không tự subscribe hoặc block bên trong callback.
5. Không tự close connection, commit hoặc rollback transaction do Spring quản lý.

### 9.2. Không tự begin/commit khi Spring đang quản lý transaction

Khi dùng @Transactional hoặc TransactionalOperator, không tự gọi beginTransaction(), commitTransaction() hoặc rollbackTransaction() trên connection thuộc transaction context của Spring.

Spring transaction manager chịu trách nhiệm bắt đầu, commit và rollback. Nếu code tự thao tác transaction ở mức Connection, trạng thái transaction có thể xung đột với manager và làm hỏng tính nguyên tử của nghiệp vụ.

Nếu không dùng transaction manager và có nhu cầu tự quản lý transaction ở mức SPI, cần chịu trách nhiệm đầy đủ cho begin, commit, rollback, lỗi và cancel. Trong ứng dụng Spring thông thường, ưu tiên transaction abstraction của Spring để tránh quản lý thủ công.

### 9.3. inConnectionMany trong transaction

inConnectionMany có thể trả Flux nằm trong transaction reactive. Transaction thường chỉ hoàn tất khi publisher kết thúc. Nếu subscriber tiêu thụ chậm, transaction và connection có thể bị giữ lâu.

Không nên stream hàng triệu dòng trong một transaction dài nếu không có yêu cầu rõ ràng. Hãy cân nhắc phân trang, chia lô, hoặc tách phần đọc dài khỏi transaction ghi.

## 10. Tuần tự hóa các thao tác trên cùng Connection

Một connection là tài nguyên có trạng thái. Không nên mặc định driver hỗ trợ thực thi đồng thời nhiều statement độc lập trên cùng một connection.

Ví dụ dễ gây khó kiểm soát:

~~~java
return databaseClient.inConnection(connection ->
    Mono.when(
        updateCustomer(connection, customerId),
        insertAudit(connection, customerId)
    ).then()
);
~~~

Mono.when đăng ký các publisher con cùng lúc. Nếu cả hai dùng chung một connection, các lệnh có thể cạnh tranh trên cùng phiên. Hành vi cụ thể tùy driver và giao thức; không nên giả định mọi thao tác đồng thời đều được hỗ trợ.

Nếu thứ tự quan trọng hoặc driver yêu cầu dùng tuần tự, nối các publisher bằng then():

~~~java
return databaseClient.inConnection(connection ->
    updateCustomer(connection, customerId)
        .then(insertAudit(connection, customerId))
);
~~~

Với một tập phần tử, dùng concatMap khi cần thực thi tuần tự:

~~~java
return databaseClient.inConnection(connection ->
    Flux.fromIterable(customerIds)
        .concatMap(id -> updateCustomer(connection, id))
        .then()
);
~~~

concatMap giữ thứ tự thực thi. flatMap có thể tạo concurrency. Chỉ sử dụng song song khi đã xác nhận driver và cách quản lý connection hỗ trợ tình huống đó. Nếu cần nhiều thao tác thực sự độc lập chạy đồng thời, thường để mỗi pipeline acquire connection riêng thông qua abstraction quản lý, thay vì ép nhiều lệnh lên cùng một connection.

## 11. Backpressure, cancellation và thời gian giữ Connection

inConnectionMany trả Flux nên việc tiêu thụ có thể bị điều khiển bởi backpressure. Connection vẫn cần tồn tại khi publisher còn thực hiện công việc.

Các tình huống cần lưu ý:

- Client đọc chậm khiến kết quả được tiêu thụ chậm và connection bị giữ lâu.
- Publisher không bao giờ hoàn tất khiến connection không được giải phóng theo vòng đời bình thường.
- Subscriber cancel thì cleanup cần được thực hiện qua cơ chế reactive.
- Một thao tác blocking bên trong callback có thể giữ connection và thread lâu hơn dự kiến.
- Chờ HTTP service, message broker hoặc thao tác người dùng trong callback làm tăng thời gian chiếm connection.

Hãy giữ callback tập trung vào thao tác database. Xử lý dữ liệu bên ngoài nên thực hiện sau khi đã kết thúc phạm vi cần giữ connection, trừ khi nghiệp vụ yêu cầu rõ ràng một transaction bao trùm các bước đó.

Không nên dùng publishOn hoặc subscribeOn như cách sửa lỗi quản lý connection. Scheduler không tự biến connection thành thread-safe và không thay thế transaction context.

## 12. Khi nào nên dùng DatabaseClient thông thường thay vì inConnection?

inConnection và inConnectionMany là API mức thấp hơn. Nếu chỉ cần SQL, bind tham số và map kết quả, DatabaseClient.sql(...) thường rõ ràng hơn.

| Nhu cầu | Cách nên cân nhắc |
|---|---|
| SELECT đơn giản và map entity/DTO | DatabaseClient.sql(...).map(...).one()/all() |
| INSERT/UPDATE/DELETE thông thường | DatabaseClient.sql(...).fetch().rowsUpdated() |
| CRUD theo entity | Repository hoặc R2dbcEntityTemplate |
| Dùng trực tiếp R2DBC Connection/Statement | inConnection hoặc inConnectionMany |
| Đọc metadata của Connection | inConnection |
| Nhiều lệnh cần dùng cùng connection trong một callback | inConnection/inConnectionMany, kết hợp transaction nếu cần tính nguyên tử |
| Transaction nhiều repository hoặc nhiều abstraction | @Transactional hoặc TransactionalOperator |

Không dùng inConnection chỉ để thay .bind() hoặc .map() của DatabaseClient. Truy cập SPI trực tiếp làm code phụ thuộc nhiều hơn vào driver, bind marker, kiểu Row và chi tiết Result. Hãy dùng khi cần kiểm soát đó thực sự có giá trị.

## 13. Xử lý lỗi và giải phóng tài nguyên

Khi callback trả về publisher, DatabaseClient có thể theo dõi vòng đời của publisher đó. Nếu publisher hoàn tất, lỗi hoặc bị cancel, Spring giải phóng connection theo cơ chế quản lý connection đang sử dụng.

Ví dụ xử lý lỗi ở ngoài phạm vi connection:

~~~java
public Mono<CustomerView> loadCustomer(Long id) {
    return databaseClient.inConnection(connection ->
        executeCustomerQuery(connection, id)
    )
    .onErrorMap(error ->
        new CustomerReadException("Không thể đọc khách hàng", error)
    );
}
~~~

Cách này giúp chuyển lỗi sang exception nghiệp vụ ở tầng phù hợp. Không nên nuốt lỗi bên trong callback rồi trả kết quả thành công giả, vì điều đó có thể che giấu lỗi database.

Nếu cần fallback:

~~~java
return databaseClient.inConnection(connection ->
        executeCustomerQuery(connection, id)
    )
    .onErrorResume(DatabaseException.class, error ->
        Mono.error(new CustomerReadException("Lỗi truy vấn", error))
    );
~~~

Tên exception cụ thể phụ thuộc driver và cách Spring bọc lỗi. Hãy phân biệt lỗi SQL, lỗi kết nối, lỗi chuyển đổi và lỗi nghiệp vụ khi thiết kế xử lý.

Không tự close connection trong doFinally, doOnTerminate hoặc callback cleanup nếu DatabaseClient đã quản lý connection. Đóng thủ công có thể làm hỏng connection mà transaction manager hoặc pool vẫn đang sử dụng.

## 14. So sánh với việc tự dùng ConnectionFactory

Có thể lấy connection trực tiếp từ ConnectionFactory:

~~~java
Mono.usingWhen(
    Mono.from(connectionFactory.create()),
    connection -> executeQuery(connection),
    connection -> Mono.from(connection.close()),
    (connection, error) -> Mono.from(connection.close()),
    connection -> Mono.from(connection.close())
);
~~~

usingWhen quản lý cleanup bất đồng bộ khi publisher hoàn tất, phát lỗi hoặc bị cancel. Ví dụ giả định executeQuery trả về Mono và không tham gia connection đã được Spring gắn với transaction. Tự acquire connection vẫn đòi hỏi bạn phối hợp đúng với transaction context và giải phóng tài nguyên trong mọi trường hợp.

Trong ứng dụng Spring, nếu muốn truy cập connection hiện đang được quản lý bởi Spring transaction, hãy dùng ConnectionFactoryUtils hoặc các abstraction Spring tương ứng thay vì gọi trực tiếp ConnectionFactory.create().

Khi chỉ cần truy cập connection trong một phạm vi callback, DatabaseClient.inConnection hoặc inConnectionMany thường là lựa chọn đơn giản hơn. Chúng giữ code ở reactive model và để DatabaseClient xử lý vòng đời connection.

## 15. Các lỗi thường gặp

| Lỗi hoặc nhầm lẫn | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ inConnection tự mở transaction | Nhiều câu lệnh có thể vẫn chạy theo autocommit | Dùng transaction manager nếu cần atomicity |
| Tự gọi connection.close() trong callback | Có thể đóng connection mà Spring/pool/transaction còn quản lý | Để DatabaseClient giải phóng |
| Lưu Connection vào field service | Có thể dùng đồng thời, dùng sau khi đã release hoặc làm cạn pool | Chỉ dùng trong callback và publisher tương ứng |
| Dùng inConnection cho kết quả nhiều hàng | Kiểu Mono không thể biểu diễn luồng nhiều phần tử | Dùng inConnectionMany |
| Dùng inConnectionMany cho một kết quả đơn | Không sai nhưng làm API kém rõ ràng | Dùng inConnection nếu kết quả là Mono |
| Gọi subscribe() trong callback | Tạo subscription tách rời khỏi vòng đời callback/transaction | Trả publisher từ callback |
| Gọi block() để lấy kết quả | Chặn thread reactive và có thể gây deadlock | Kết hợp Mono/Flux |
| Dùng marker SQL của driver khác | Statement không bind được tham số | Kiểm tra cú pháp marker theo driver |
| Gọi bind(index, null) | R2DBC SPI không dùng cách này cho null | Dùng bindNull(index, type) |
| Giả định bind marker thay tên bảng | Database hiểu marker là giá trị, không phải identifier | Whitelist và xây dựng identifier tin cậy |
| Chạy nhiều statement song song trên cùng connection | Driver có thể không hỗ trợ hoặc thứ tự khó đoán | Dùng then()/concatMap khi cần tuần tự |
| Giữ Flux vô hạn trong inConnectionMany | Connection bị giữ lâu, pool có thể cạn | Giới hạn publisher và thời gian giữ tài nguyên |
| Đổi trạng thái session mà không reset | Request sau có thể nhận lại connection mang trạng thái cũ | Khôi phục trạng thái hoặc cấu hình pool phù hợp |
| Tự commit/rollback trong @Transactional | Xung đột với transaction manager | Để Spring quản lý transaction |

## 16. Quy trình sử dụng inConnection hoặc inConnectionMany

Khi cần truy cập Connection trực tiếp, hãy làm theo trình tự:

1. Xác định vì sao repository, R2dbcEntityTemplate hoặc DatabaseClient SQL thông thường chưa đáp ứng nhu cầu.
2. Chọn inConnection nếu callback trả về một kết quả Mono; chọn inConnectionMany nếu callback trả về Publisher nhiều phần tử.
3. Viết callback nhận Connection và trả publisher bao trùm toàn bộ thao tác.
4. Tạo Statement bằng cú pháp SQL và bind marker phù hợp driver.
5. Dùng bind(index, value) cho giá trị có dữ liệu và bindNull(index, type) cho null.
6. Map Result/Row sang DTO hoặc kiểu cần thiết.
7. Nối nhiều thao tác bằng then() hoặc concatMap nếu cần thứ tự.
8. Không tự subscribe, block, close, commit hoặc rollback connection do DatabaseClient quản lý.
9. Nếu cần atomicity, bao bọc pipeline trong reactive transaction dùng cùng ConnectionFactory.
10. Giới hạn thời gian giữ connection và tránh công việc ngoài database trong callback.
11. Kiểm thử cả hoàn tất, lỗi và cancel trên driver/database thực tế.
12. Theo dõi pool khi query dài hoặc Flux phát nhiều hàng.

## 17. Bài tập tự kiểm tra

### Bài 1: Chọn API

Một truy vấn tìm khách hàng theo ID và trả về tối đa một hàng. Nên dùng inConnection hay inConnectionMany?

Gợi ý: inConnection vì kết quả phù hợp với Mono. Nếu truy vấn có thể phát nhiều hàng, dùng inConnectionMany.

### Bài 2: Đọc danh sách

Bạn cần đọc tất cả đơn hàng của một khách hàng bằng R2DBC Statement và trả từng OrderView. Hãy mô tả cấu trúc callback.

Gợi ý: Dùng inConnectionMany, tạo Statement, bind ID, gọi execute(), chuyển từng Result thành publisher Row qua map(), rồi phát các OrderView trong Flux.

### Bài 3: Bind NULL

Bạn cần insert email NULL bằng Statement. Nên dùng API nào?

Gợi ý: Dùng bindNull(index, String.class) với index đúng vị trí và kiểu tương thích cột.

### Bài 4: Transaction

Một callback cập nhật đơn hàng rồi ghi audit log. Nếu ghi audit thất bại, cả hai thao tác phải rollback. Chỉ dùng inConnection có đủ không?

Gợi ý: Không. inConnection giữ cùng connection trong callback nhưng không tự mở transaction. Hãy dùng reactive transaction manager và bao bọc publisher bằng @Transactional hoặc TransactionalOperator.

### Bài 5: Trạng thái phiên

Một callback đặt session schema rồi truy vấn bảng. Vì sao cần chú ý sau khi callback kết thúc?

Gợi ý: Connection vật lý có thể được trả về pool và tái sử dụng. Trạng thái session có thể ảnh hưởng request tiếp theo nếu không được reset.

### Bài 6: Nhiều thao tác

Bạn có ba câu lệnh cần chạy tuần tự trên cùng Connection. Nên dùng Mono.when hay then?

Gợi ý: Dùng then() để nối tuần tự. Mono.when có thể subscribe đồng thời vào các publisher và tạo cạnh tranh trên cùng connection.

### Bài 7: Hủy subscription

Một client ngừng đọc Flux được trả về từ inConnectionMany. Điều gì cần xảy ra?

Gợi ý: Subscription bị cancel; publisher phải kết thúc và cơ chế quản lý của DatabaseClient giải phóng connection. Không tự giữ connection hoặc tạo subscription tách rời.

## 18. Ghi nhớ

- inConnection cung cấp Connection cho callback và trả kết quả dưới dạng Mono.
- inConnectionMany cung cấp Connection cho callback và trả kết quả dưới dạng Flux.
- Hai phương thức quản lý vòng đời connection trong phạm vi publisher; không cần tự close connection.
- Truy cập cùng Connection không tự động tạo transaction. Dùng reactive transaction manager khi cần commit/rollback nguyên tử.
- Khi dùng R2DBC SPI trực tiếp, cú pháp bind marker phụ thuộc driver; bind index bắt đầu từ 0.
- Dùng bindNull(index, type) cho giá trị null.
- Dùng Result.map() để chuyển Row thành DTO hoặc kiểu kết quả.
- Không giữ Connection trong field, không subscribe hoặc block bên trong callback.
- Nối các thao tác tuần tự bằng then() hoặc concatMap khi cần tránh chạy đồng thời trên cùng connection.
- inConnectionMany có thể giữ connection trong suốt thời gian Flux được tiêu thụ; cần chú ý backpressure, cancellation và thời gian giữ tài nguyên.
- Nếu thay đổi trạng thái cấp phiên, phải có kế hoạch khôi phục trước khi connection được tái sử dụng.
- Chỉ dùng API mức thấp khi cần khả năng của Connection; với SQL thông thường, ưu tiên DatabaseClient, repository hoặc R2dbcEntityTemplate.

Khi cần truy cập Connection trong Spring Data Relational R2DBC, hãy để DatabaseClient mở phạm vi sử dụng qua inConnection hoặc inConnectionMany, rồi trả về publisher chứa toàn bộ thao tác. Cách này cho phép dùng R2DBC SPI mà vẫn phối hợp với vòng đời connection, connection pool và reactive transaction của Spring.


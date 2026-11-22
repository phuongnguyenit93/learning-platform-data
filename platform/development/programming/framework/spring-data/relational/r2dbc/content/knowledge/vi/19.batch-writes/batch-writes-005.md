# Chia dữ liệu thành nhóm theo số hàng hoặc số tham số

## 1. Vì sao phải chia dữ liệu thành nhóm?

Khi ghi nhiều bản ghi bằng Spring Data Relational R2DBC, việc gửi từng thao tác nhỏ riêng lẻ có thể tạo nhiều lần round-trip giữa ứng dụng và database. Với một tập dữ liệu lớn, chi phí tạo statement, gửi request, chờ response và quản lý transaction có thể chiếm phần đáng kể thời gian xử lý.

Chia dữ liệu thành nhóm (chunking) giúp giới hạn lượng dữ liệu đưa vào mỗi lần ghi. Một nhóm có thể được xác định theo:

- **Số hàng tối đa:** mỗi nhóm chứa không quá N bản ghi.
- **Số tham số tối đa:** tổng số bind parameter của câu lệnh không vượt giới hạn đã chọn.
- **Cả hai điều kiện:** nhóm kết thúc khi đạt giới hạn hàng hoặc giới hạn tham số, tùy điều kiện nào đến trước.

Ví dụ, một lần import có 12.000 dòng. Nếu chọn 400 hàng mỗi nhóm, pipeline tạo 30 nhóm. Nếu mỗi hàng cần 8 tham số và câu SQL có thêm 2 tham số cố định, một câu multi-row INSERT gồm 400 hàng cần 3.202 tham số. Nếu driver hoặc database có giới hạn thấp hơn, cần giảm số hàng mỗi câu.

Mục tiêu không phải tạo nhóm lớn nhất có thể. Nhóm quá lớn có thể vượt giới hạn bind parameter, tăng memory, tạo statement dài, giữ transaction lâu hoặc khiến một lỗi làm mất nhiều công việc hơn. Nhóm quá nhỏ lại làm tăng số round-trip và chi phí điều phối.

Cần phân biệt ba khái niệm:

1. **Chunking ở tầng ứng dụng:** chia một Flux hoặc collection thành các nhóm.
2. **Batch ở tầng R2DBC:** gửi nhiều bộ giá trị cho cùng một prepared statement qua Statement.add().
3. **Multi-row SQL:** tạo một câu lệnh có nhiều nhóm VALUES trong cùng statement.

Ba kỹ thuật có thể kết hợp, nhưng chúng không đồng nghĩa.

## 2. Vị trí của chunking trong luồng ghi

Một pipeline ghi dữ liệu có thể được tổ chức như sau:

~~~text
Input stream
    |
    v
Validate / normalize
    |
    v
Buffer into chunks
(max rows / max parameters)
    |
    v
Write one chunk
    |
    v
R2DBC Statement / SQL
    |
    v
Database
    |
    v
Commit chunk or transaction
    |
    v
Process next chunk
~~~

Chunking kiểm soát lượng dữ liệu đang được giữ trong bộ nhớ và số hàng được đưa vào một lần ghi. Nó không tự bảo đảm một nhóm tương ứng với một SQL statement hoặc một transaction.

Ví dụ, buffer(500) tạo nhóm tối đa 500 object trong Reactor. Nếu sau đó gọi saveAll(batch), implementation repository có thể phát ra nhiều thao tác insert/update riêng. Nếu muốn batch statement thực sự, cần dùng API/driver hỗ trợ batch và xác nhận SQL được gửi như mong đợi.

Tương tự, chia thành nhóm 500 hàng không có nghĩa mỗi nhóm được commit riêng. Nếu bọc toàn bộ pipeline bằng một transaction, tất cả nhóm vẫn nằm trong một transaction dài.

## 3. Chọn tiêu chí theo số hàng

Giới hạn theo số hàng là cách dễ hiểu và dễ vận hành nhất khi mỗi bản ghi có cấu trúc tương đối giống nhau.

Ví dụ:

~~~java
Flux.fromIterable(customers)
        .buffer(500)
        .concatMap(batch -> writeBatch(batch));
~~~

buffer(500) phát ra một List<Customer> khi có đủ 500 phần tử và phát nhóm cuối cùng nếu còn ít hơn 500 phần tử khi nguồn hoàn tất.

Nếu nguồn là một Flux vô hạn hoặc không hoàn tất, nhóm chưa đủ 500 phần tử có thể không được phát. Khi đó cần cân nhắc flush theo thời gian:

~~~java
Flux.fromIterable(customers)
        .bufferTimeout(500, Duration.ofSeconds(2))
        .concatMap(batch -> writeBatch(batch));
~~~

bufferTimeout phát nhóm khi đạt số phần tử hoặc khi hết thời gian chờ, tùy điều kiện đến trước. Đây là cách hữu ích cho consumer nhận dữ liệu liên tục. Cần kiểm tra Reactor version và API đang dùng.

### 3.1. Khi nào giới hạn theo hàng phù hợp?

Giới hạn theo số hàng phù hợp khi:

- Mỗi hàng có số cột ghi gần như cố định.
- Kích thước mỗi row tương đối đồng đều.
- Database/driver có thể xử lý số hàng trong nhóm dự kiến.
- Nghiệp vụ cần checkpoint theo số record.
- Muốn dễ theo dõi tiến độ import/export.

Ví dụ, bảng product_prices có 5 cột cần ghi cho mỗi row. Một nhóm 200 hàng có kích thước tham số khá dễ dự đoán. Nếu mỗi row chứa JSON lớn hoặc BLOB, giới hạn hàng đơn thuần có thể không đủ vì kích thước payload khác nhau đáng kể.

### 3.2. Chọn batch size ban đầu

Không có một batch size đúng cho mọi database. Có thể bắt đầu thử với các nhóm như 50, 100, 250 hoặc 500 hàng, sau đó đo:

- Thời gian ghi mỗi nhóm.
- Số hàng mỗi giây.
- Kích thước payload.
- Thời gian giữ connection.
- Transaction duration.
- Memory của ứng dụng.
- Lock wait và query latency.
- Tỷ lệ timeout/lỗi.

Các con số này chỉ là điểm bắt đầu để thử nghiệm. Một bảng có row nhỏ và index ít có thể chấp nhận nhóm lớn hơn bảng có nhiều index, trigger hoặc dữ liệu lớn.

Tăng batch size theo từng bước và giữ nguyên workload khi so sánh. Khi throughput không tăng nhưng latency, memory hoặc lock wait tăng, nhóm đã có thể vượt điểm hiệu quả.

## 4. Chọn tiêu chí theo số bind parameter

Database và driver thường đặt giới hạn cho số tham số của một statement hoặc một lần thực thi. Giới hạn cụ thể phụ thuộc engine, giao thức, driver và phiên bản.

Một multi-row INSERT có dạng:

~~~sql
INSERT INTO inventory (sku, quantity, warehouse_id)
VALUES
    (:sku0, :quantity0, :warehouse0),
    (:sku1, :quantity1, :warehouse1),
    (:sku2, :quantity2, :warehouse2);
~~~

Mỗi hàng cần 3 tham số. Với N hàng, câu lệnh cần khoảng 3 × N tham số, chưa tính tham số cố định khác.

Nếu một câu lệnh có:

- P tham số cho mỗi hàng.
- F tham số cố định dùng chung.
- M là giới hạn tham số an toàn của statement.

Thì số hàng tối đa theo tham số là:

\[
N_{max} = \left\lfloor \frac{M-F}{P} \right\rfloor
\]

Giới hạn thực tế nên lấy nhỏ hơn giữa cấu hình theo hàng và giới hạn theo tham số:

\[
N_{chunk} = \min(N_{configured}, N_{max})
\]

Ví dụ minh họa: mỗi hàng cần 7 tham số, câu lệnh có 2 tham số cố định và cấu hình an toàn cho statement là 2.000 tham số:

\[
N_{max} = \left\lfloor \frac{2000-2}{7} \right\rfloor = 285
\]

Nếu cấu hình batch theo hàng là 500, nhóm cho câu multi-row INSERT phải giảm xuống tối đa 285 hàng theo ngân sách tham số này.

Đây là phép tính giới hạn, không phải bảo đảm rằng 285 hàng là batch size tối ưu. Có thể cần giới hạn thấp hơn vì payload, thời gian thực thi hoặc transaction.

## 5. Xác định số tham số thực tế trên mỗi hàng

Không phải mọi row đều có cùng số tham số. Một thao tác ghi có thể cần:

- Giá trị của các cột nghiệp vụ.
- Tenant ID hoặc owner ID.
- Audit actor và timestamp nếu được bind trong SQL.
- Version cho optimistic locking.
- Giá trị filter hoặc điều kiện bổ sung.
- Tham số dùng chung trong WHERE clause.

Nếu SQL có 6 tham số cho mỗi hàng và 3 tham số chung, tổng số parameter của câu multi-row statement là:

~~~text
parameter_count = row_count × 6 + 3
~~~

Với dữ liệu có cột tùy chọn, số tham số có thể thay đổi theo shape của từng row. Có hai cách:

1. Dùng một SQL shape thống nhất và bind NULL cho field không có giá trị, nếu schema/semantics cho phép.
2. Nhóm các row cùng shape để mỗi statement có cùng cấu trúc tham số.

Không được bỏ qua parameter chỉ vì giá trị là null. Nếu bind null, cần dùng API bind null với kiểu Java/SQL phù hợp, ví dụ bindNull(index, String.class), theo API driver và Spring Data đang dùng.

Đối với multi-row SQL, tính tổng tham số của tất cả row trong statement. Đối với R2DBC batch dùng Statement.add(), mỗi binding set có cùng số parameter của một lần thực thi; số parameter không đơn giản nhân với số row như một câu multi-row. Hai chiến lược này cần được tính riêng.

## 6. Phân biệt R2DBC Statement batch và multi-row INSERT

Hai kỹ thuật thường bị gọi chung là batch insert nhưng có cách gửi dữ liệu khác nhau.

### 6.1. Statement.add(): nhiều bộ giá trị cho cùng SQL

R2DBC SPI có Statement.add() để thêm binding set hiện tại vào batch của cùng statement. Mỗi lần thực thi dùng cùng SQL và một bộ tham số khác.

Ví dụ khái quát với PostgreSQL:

~~~java
Statement statement = connection.createStatement(
        "INSERT INTO inventory (sku, quantity) VALUES ($1, $2)"
);

statement.bind(0, "SKU-001")
        .bind(1, 10)
        .add();

statement.bind(0, "SKU-002")
        .bind(1, 20);

Publisher<? extends Result> results = statement.execute();
~~~

Trong ví dụ:

- SQL chỉ có hai placeholder.
- Mỗi binding set có hai tham số.
- add() đưa bộ giá trị hiện tại vào batch.
- Bộ bind cuối cùng được giữ để thực thi cùng batch.
- Chỉ số bind trong R2DBC SPI là zero-based; cú pháp placeholder trong SQL phụ thuộc driver.

Statement.add() phù hợp khi cùng một câu INSERT/UPDATE được áp dụng cho nhiều row. Driver có thể tối ưu cách gửi batch, nhưng không nên giả định nó luôn biến thành một câu multi-row SQL duy nhất hoặc một round-trip duy nhất. Hành vi cụ thể cần kiểm tra với driver đang dùng.

### 6.2. Multi-row INSERT: nhiều VALUES trong một SQL

Multi-row INSERT tạo một câu SQL có nhiều tuple:

~~~sql
INSERT INTO inventory (sku, quantity)
VALUES
    ($1, $2),
    ($3, $4),
    ($5, $6);
~~~

Với 3 hàng và 2 cột, statement có 6 parameter. Khi tăng số hàng, số placeholder tăng theo số hàng.

Ưu điểm là một statement thể hiện nhiều row trong cùng câu SQL. Nhược điểm là câu SQL dài hơn và tổng parameter tăng tuyến tính theo số hàng.

Cú pháp placeholder, giới hạn statement và khả năng trả generated value phụ thuộc database/driver. Không copy $1 của PostgreSQL sang H2, SQL Server hoặc driver khác mà không điều chỉnh.

### 6.3. So sánh

| Tiêu chí | Statement.add() batch | Multi-row INSERT |
|---|---|---|
| SQL | Một mẫu SQL cố định | SQL có nhiều VALUES |
| Parameter count | Theo một binding set | Tăng theo số hàng |
| Kích thước SQL | Thường cố định | Tăng theo số hàng |
| Số row mỗi lần gửi | Nhiều binding set | Nhiều tuple trong một statement |
| Generated values | Phụ thuộc driver và từng Result | Phụ thuộc RETURNING/generated-value support |
| Khả năng driver | Phải hỗ trợ batch add() | Phải hỗ trợ cú pháp multi-row |
| Dùng khi | Lặp cùng một thao tác cho nhiều row | Muốn tạo một câu INSERT nhiều tuple |

Không có kỹ thuật nào luôn nhanh hơn. Hãy benchmark trên đúng driver/database, schema và kích thước row của ứng dụng.

## 7. saveAll() không đồng nghĩa một bulk SQL statement

Spring Data R2DBC repository cung cấp saveAll() để nhận nhiều entity dưới dạng Publisher hoặc Iterable. API này thuận tiện cho việc xử lý nhiều entity reactive, nhưng không nên mặc định nó luôn phát ra một câu INSERT nhiều VALUES hoặc một Statement.add() batch.

Tùy implementation và version, việc lưu có thể được thực hiện qua các thao tác save cho từng entity. Với một số trường hợp, mỗi row có thể tạo một statement riêng. Hãy xem SQL thực tế hoặc tài liệu/version của Spring Data đang dùng trước khi đưa ra kết luận về batching.

Ví dụ:

~~~java
Flux<Customer> saved =
        customerRepository.saveAll(
                Flux.fromIterable(batch)
        );
~~~

Đoạn code này biểu diễn luồng lưu nhiều entity. Nó không tự nói rõ database sẽ nhận một multi-row INSERT, một batch statement hay nhiều statement riêng.

Nếu cần bảo đảm cách gửi cụ thể, dùng API batch/SQL tường minh phù hợp và kiểm tra với driver thật. Không nên dùng số lượng entity truyền vào saveAll() làm bằng chứng về số statement được gửi.

## 8. Chia nhóm theo cả số hàng và số tham số

Trong hệ thống thực tế, nên áp dụng đồng thời giới hạn hàng và tham số. Với row có shape cố định, có thể tính trước số hàng tối đa:

~~~java
int rowsByParameters =
        (maxParameters - fixedParameters) / parametersPerRow;

int effectiveBatchSize =
        Math.min(configuredMaxRows, rowsByParameters);
~~~

Cần kiểm tra rowsByParameters lớn hơn 0. Nếu một row riêng lẻ đã vượt ngân sách parameter, không thể giải quyết bằng cách giảm số row; phải thay đổi SQL shape hoặc cách ghi.

Với row có số parameter biến đổi, xây chunk theo ngân sách tích lũy:

~~~text
current_batch = []
current_parameters = fixed_parameters

for each row:
    row_parameters = count_parameters(row)

    if row_parameters + fixed_parameters > max_parameters:
        reject row or use another SQL shape

    if current_batch is not empty and
       (row_count + 1 > max_rows or
        current_parameters + row_parameters > max_parameters):
        flush current_batch
        start a new batch

    append row
    increase current_parameters

flush the final non-empty batch
~~~

Đây là pseudocode mô tả thuật toán. Khi triển khai, cần tính lại tham số cố định cho mỗi statement và xử lý row lỗi riêng theo chính sách import.

### 8.1. Ví dụ tính batch động

Giả sử:

- Tối đa 300 hàng theo cấu hình.
- Ngân sách 1.800 bind parameter cho một statement.
- Mỗi hàng bình thường có 5 parameter.
- Có 3 parameter cố định.

Khi đó:

\[
N_{max} = \left\lfloor \frac{1800-3}{5} \right\rfloor = 359
\]

Giới hạn theo hàng là 300, nên batch size hiệu lực là 300.

Nếu mỗi hàng có 8 parameter:

\[
N_{max} = \left\lfloor \frac{1800-3}{8} \right\rfloor = 224
\]

Batch size hiệu lực giảm còn 224.

Đối với Statement.add() batch, mỗi binding set chỉ có 8 parameter trong ví dụ này. Khi đó phải tuân theo giới hạn parameter trên một execution set và giới hạn batch/payload của driver, thay vì nhân 8 với số row để suy ra một statement có 8 × N bind parameter.

## 9. Chunking bằng Reactor buffer

Một pipeline đơn giản theo số hàng:

~~~java
public Mono<Void> importCustomers(Flux<CustomerInput> input) {
    return input
            .map(this::toCustomer)
            .buffer(250)
            .concatMap(batch -> writeBatch(batch))
            .then();
}
~~~

buffer(250) phát một nhóm tối đa 250 hàng. concatMap xử lý từng batch tuần tự và chờ batch hiện tại hoàn tất trước khi chuyển sang batch kế tiếp. Cách này giúp giới hạn số batch đang chạy trong subscription ở mức một và giữ thứ tự nhóm.

Nếu cần flush theo số hàng hoặc thời gian:

~~~java
public Mono<Void> importCustomers(Flux<CustomerInput> input) {
    return input
            .map(this::toCustomer)
            .bufferTimeout(250, Duration.ofSeconds(1))
            .concatMap(this::writeBatch)
            .then();
}
~~~

Cần cân nhắc rằng bufferTimeout phù hợp với stream dài hoặc liên tục. Với một collection hữu hạn đã có sẵn, buffer(maxRows) thường đủ.

### 9.1. Tránh collectList cho toàn bộ input lớn

Không nên:

~~~java
return input.collectList()
        .flatMap(this::writeAll);
~~~

Cách này giữ toàn bộ input trong bộ nhớ trước khi ghi. Nếu dữ liệu có hàng triệu row, heap có thể tăng mạnh hoặc hết bộ nhớ.

Dùng buffer để chỉ giữ một chunk đang xử lý. Tuy nhiên, nếu downstream chạy song song nhiều chunk, mỗi chunk có thể vẫn nằm trong memory cùng lúc. Vì vậy concurrency cũng cần giới hạn.

### 9.2. Giới hạn số batch chạy đồng thời

Nếu các batch độc lập và database chịu được concurrency, có thể dùng flatMap với concurrency hữu hạn:

~~~java
return input
        .map(this::toCustomer)
        .buffer(200)
        .flatMap(batch -> writeBatch(batch), 2)
        .then();
~~~

Trong ví dụ, tối đa hai inner publisher ghi batch có thể được subscribe đồng thời trong subscription này. Đây không phải giới hạn toàn ứng dụng; nhiều request/import job có thể cùng chạy và nhân tổng concurrency.

Dùng concatMap khi cần thứ tự và kiểm soát đơn giản. Dùng flatMap có giới hạn khi batch độc lập, có thể chạy song song và đã đo được database capacity. Tránh flatMap không giới hạn với nguồn lớn.

## 10. Tách batch size khỏi transaction size

Chunk size và transaction boundary là hai quyết định riêng.

### 10.1. Một transaction cho toàn bộ import

~~~java
Mono<Void> work =
        input.buffer(250)
                .concatMap(this::writeBatch)
                .then();

return transactionalOperator.transactional(work);
~~~

Ở đây mỗi chunk được xử lý tuần tự nhưng tất cả cùng nằm trong một transaction. Nếu chunk cuối lỗi, toàn bộ import có thể rollback.

Ưu điểm:

- Tính atomic của toàn bộ import.
- Không có trạng thái commit một phần nếu transaction rollback thành công.

Hạn chế:

- Transaction có thể rất dài.
- Connection được giữ trong toàn bộ quá trình.
- Lock/snapshot có thể tồn tại lâu.
- Rollback có thể tốn kém.
- Một lỗi muộn làm mất công xử lý trước đó.
- Transaction log/WAL và tài nguyên database có thể tăng.

Chỉ dùng khi nghiệp vụ thật sự yêu cầu tất cả dữ liệu cùng commit hoặc cùng rollback.

### 10.2. Một transaction cho mỗi chunk

~~~java
Flux<Void> chunks =
        input.buffer(250)
                .concatMap(batch ->
                        writeBatch(batch)
                                .as(transactionalOperator::transactional)
                                .then()
                );

return chunks.then();
~~~

Mỗi chunk được xử lý trong transaction riêng. Khi một chunk thành công, nó được commit trước khi xử lý nhóm tiếp theo.

Ưu điểm:

- Transaction ngắn hơn.
- Connection được trả sau mỗi chunk.
- Giảm phạm vi rollback.
- Dễ checkpoint và tiếp tục từ nhóm chưa hoàn tất.

Hạn chế:

- Import có thể commit một phần.
- Cần lưu tiến độ hoặc thiết kế idempotency.
- Nếu nhóm sau lỗi, nhóm trước vẫn tồn tại.
- Cần quy định cách retry chunk thất bại.

Đây thường là lựa chọn thực tế cho import lớn nếu nghiệp vụ chấp nhận partial progress.

### 10.3. Nhiều chunk chạy song song với transaction riêng

~~~java
return input.buffer(200)
        .flatMap(
                batch -> writeBatch(batch)
                        .as(transactionalOperator::transactional),
                2
        )
        .then();
~~~

Mỗi inner publisher có transaction riêng. Có thể có tối đa hai chunk đang xử lý trong subscription này. Thứ tự hoàn tất không nhất thiết giống thứ tự input.

Chỉ dùng khi các chunk độc lập về dữ liệu hoặc database đã có cơ chế xử lý conflict. Nếu hai chunk cập nhật cùng một row, có thể phát sinh race, lock wait hoặc deadlock.

Không đặt flatMap song song bên trong một transaction duy nhất rồi giả định mỗi nhánh có một connection riêng. Các thao tác trong cùng transaction thường chia sẻ connection được bind cho transaction; nhiều driver không hỗ trợ nhiều statement đồng thời trên một connection.

## 11. Chọn chunk size theo payload, không chỉ số hàng

Hai nhóm đều có 100 row nhưng kích thước dữ liệu có thể khác nhau rất nhiều:

- Nhóm A: mỗi row có 4 cột ngắn.
- Nhóm B: mỗi row có JSON lớn hoặc text dài.
- Nhóm C: một số row có binary payload.

Ngoài row count và parameter count, cần cân nhắc:

- Tổng byte của payload.
- Kích thước câu SQL sinh ra.
- Kích thước message/packet của driver và database.
- Bộ nhớ dùng để giữ chunk.
- Thời gian serialize/bind.
- Thời gian transaction.
- Giới hạn request/message broker đầu vào.

Nếu row size biến động mạnh, có thể thêm maxBytes vào thuật toán chunk. Điều này tránh một chunk có ít row nhưng payload quá lớn.

Không đặt một giới hạn byte tùy ý mà chưa xem driver/protocol và database. Đo kích thước thực tế bằng dữ liệu đại diện và đặt safety margin.

## 12. Batch insert với R2DBC SPI

Đối với thao tác lặp lại cùng một SQL, có thể sử dụng Statement.add() trực tiếp. Ví dụ dưới đây minh họa cách dùng Spring ConnectionFactoryUtils để lấy connection có thể tham gia reactive transaction hiện tại:

~~~java
public Flux<Integer> insertBatch(List<InventoryRow> rows) {
    String sql = """
            INSERT INTO inventory (sku, quantity)
            VALUES ($1, $2)
            """;

    return Flux.usingWhen(
            ConnectionFactoryUtils.getConnection(connectionFactory),
            connection -> {
                Statement statement = connection.createStatement(sql);

                for (int i = 0; i < rows.size(); i++) {
                    InventoryRow row = rows.get(i);

                    statement.bind(0, row.sku())
                            .bind(1, row.quantity());

                    if (i < rows.size() - 1) {
                        statement.add();
                    }
                }

                return Flux.from(statement.execute())
                        .concatMap(result ->
                                Mono.from(result.getRowsUpdated())
                        );
            },
            connection ->
                    ConnectionFactoryUtils.releaseConnection(
                            connection, connectionFactory),
            (connection, error) ->
                    ConnectionFactoryUtils.releaseConnection(
                            connection, connectionFactory),
            connection ->
                    ConnectionFactoryUtils.releaseConnection(
                            connection, connectionFactory)
    );
}
~~~

Đây là ví dụ cho PostgreSQL placeholder. Driver khác có thể dùng placeholder khác; R2DBC bind index vẫn là zero-based. Cần import ConnectionFactoryUtils, ConnectionFactory, Statement, Mono, Flux và kiểu dữ liệu tương ứng.

Các điểm cần lưu ý:

- ConnectionFactoryUtils.getConnection có thể lấy connection đã bind trong reactive transaction hiện tại.
- releaseConnection tôn trọng connection được transaction manager quản lý; không tự đóng connection đang thuộc transaction.
- Nếu dùng raw connectionFactory.create() trong code nằm trong Spring transaction, có nguy cơ lấy connection độc lập ngoài transaction-bound resource.
- Statement.add() là API batch của R2DBC SPI, nhưng driver cần hỗ trợ đúng hành vi.
- getRowsUpdated() có kiểu reactive; số result và cách báo affected rows phụ thuộc driver.
- Generated ID không tự được trả về chỉ vì gọi getRowsUpdated().

Đối với code production, cần kiểm tra behavior của driver và xử lý lỗi/cleanup theo đúng phiên bản Spring Framework và R2DBC SPI đang sử dụng. Không sao chép ví dụ mà bỏ qua transaction resource management.

### 12.1. Batch với bind null

Nếu row có giá trị null, dùng bindNull với kiểu Java phù hợp:

~~~java
statement.bind(0, row.sku());

if (row.description() == null) {
    statement.bindNull(1, String.class);
} else {
    statement.bind(1, row.description());
}
~~~

Không bind null như một giá trị Java thông thường nếu API yêu cầu chỉ rõ type. Type cần tương thích với column và driver.

### 12.2. Batch update

Cùng cơ chế có thể dùng cho UPDATE lặp lại:

~~~sql
UPDATE inventory
SET quantity = $1
WHERE sku = $2
~~~

Mỗi binding set cung cấp quantity và sku khác nhau. Hãy xem kết quả rows updated để phát hiện row không tồn tại hoặc version conflict nếu nghiệp vụ cần.

## 13. Multi-row INSERT và giới hạn parameter

Nếu dùng một câu multi-row INSERT, có thể tạo placeholder theo số row. Ví dụ ba row, mỗi row hai cột:

~~~sql
INSERT INTO inventory (sku, quantity)
VALUES
    ($1, $2),
    ($3, $4),
    ($5, $6)
~~~

Tổng số parameter là 6. Với 300 row và 8 cột, số parameter có thể là 2.400, chưa tính tham số cố định.

Cần xây câu SQL từ cấu trúc cố định và bind mọi giá trị. Không đưa giá trị input vào chuỗi SQL. Tên bảng/cột phải là identifier được định nghĩa trong code, không lấy trực tiếp từ người dùng.

Một cách tạo placeholder khái quát:

~~~text
for each row i:
    create one tuple with P placeholders
    bind row[i] values to the corresponding parameter indexes

join all tuples with commas
execute the statement
~~~

Cú pháp placeholder cụ thể là dialect/driver-specific. Hãy dùng SQL builder hoặc helper được kiểm thử thay vì nối chuỗi placeholder rải rác trong nhiều service.

### 13.1. Giới hạn tham số là theo statement hay theo batch?

Đây là điểm quan trọng:

- Với multi-row INSERT, mọi tuple nằm trong cùng statement. Parameter count tăng theo số row.
- Với Statement.add(), mỗi binding set có số parameter riêng; nhiều set được đưa vào batch. Giới hạn số parameter của một lần thực thi không nhất thiết bằng tổng parameter của toàn batch.

Dù Statement.add() không nhân parameter count theo số row như multi-row SQL, batch vẫn có giới hạn về số binding set, payload, memory, thời gian thực thi và khả năng driver. Cần đo và xác nhận giới hạn thực tế.

Không lấy một giới hạn của database cho loại statement này rồi áp dụng máy móc cho loại batch khác.

## 14. Các giới hạn database và driver

Giới hạn parameter có thể khác giữa engine và version. Ví dụ, SQL Server thường có giới hạn số parameter cho một stored procedure/batch, SQLite có giới hạn host parameter phụ thuộc version/build, còn PostgreSQL chịu giới hạn từ protocol và driver. Các giới hạn này có thể thay đổi theo phiên bản và cách driver gửi statement.

Khi đánh giá, kiểm tra:

- Database engine/version.
- R2DBC driver/version.
- Giới hạn placeholder của driver.
- Giới hạn bind parameter của statement.
- Giới hạn packet/message.
- Giới hạn chiều dài SQL.
- Giới hạn số row hoặc batch item.
- Khả năng trả generated value.
- Timeout và transaction behavior.

Không nên hard-code một số tối đa chung cho mọi môi trường. Đặt cấu hình an toàn thấp hơn giới hạn được xác nhận và kiểm tra lại khi nâng database/driver.

## 15. Xử lý lỗi và partial success

Một chunk có thể thất bại vì:

- Unique constraint.
- Foreign key.
- Not-null/check constraint.
- Dữ liệu sai kiểu hoặc vượt độ dài.
- Deadlock hoặc lock timeout.
- Connection reset.
- Query/statement timeout.
- Parameter limit.
- Database unavailable.

Cần xác định chính sách theo từng loại lỗi:

| Loại lỗi | Hướng xử lý thường gặp |
|---|---|
| Validation lỗi một row | Loại row hoặc đưa vào error report |
| Duplicate key | Skip, update/upsert hoặc reject theo nghiệp vụ |
| Foreign key chưa tồn tại | Retry sau khi dependency được ghi hoặc reject |
| Deadlock/serialization failure | Retry có giới hạn nếu transaction idempotent |
| Parameter limit | Chia nhóm nhỏ hơn |
| Payload quá lớn | Giảm max bytes hoặc xử lý riêng |
| Database unavailable | Backoff/retry theo deadline |
| Lỗi schema/type | Dừng batch và sửa mapping/schema |

Nếu một batch statement chạy ngoài transaction và driver/database không bảo đảm atomicity cho toàn batch, có thể có partial success. Không giả định tất cả row đều được ghi hoặc tất cả đều thất bại.

Nếu cần atomic cho một chunk, bao writeBatch trong reactive transaction. Khi lỗi, để error đi qua transaction boundary để rollback. Nếu lỗi được onErrorResume thành complete bên trong transaction, transaction có thể commit các thay đổi đã thực hiện.

### 15.1. Không retry cả import một cách mù quáng

Nếu 20 chunk đầu đã commit và chunk 21 lỗi, retry toàn bộ import có thể ghi trùng hoặc cập nhật lại dữ liệu. Thiết kế idempotency:

- Business key duy nhất.
- Upsert có semantics rõ.
- Import job ID và chunk sequence.
- Checkpoint các chunk đã commit.
- Deduplication key.
- Retry chỉ chunk thất bại nếu dữ liệu cho phép.

Đối với thao tác tạo dữ liệu không idempotent, cần khóa chống trùng hoặc kiểm tra trạng thái trước khi retry.

### 15.2. Error report theo row

Khi một chunk chứa hàng trăm row và chỉ một row sai, cần xác định muốn rollback cả chunk hay chấp nhận các row hợp lệ.

Hai chiến lược:

- **Atomic chunk:** một row lỗi làm rollback toàn chunk. Đơn giản, dễ bảo đảm nhất quán.
- **Per-row isolation:** tách row lỗi, ghi các row hợp lệ. Cần nhiều lần thực thi hơn và quy tắc xử lý rõ.

Có thể validate dữ liệu trước khi gửi database để loại lỗi định dạng sớm. Tuy nhiên, validation ứng dụng không thay thế constraint database vì dữ liệu có thể xung đột do concurrent write.

## 16. Thứ tự dữ liệu và quan hệ khóa ngoại

Chia chunk có thể làm thay đổi thứ tự xử lý nếu dùng flatMap song song.

Nếu bảng con tham chiếu bảng cha, cần bảo đảm row cha được tạo trước khi ghi row con, hoặc database có constraint/deferred semantics phù hợp.

Ví dụ:

~~~text
Chunk 1: Orders 1..200
Chunk 2: Order lines 1..800
~~~

Không nên chạy song song cả hai loại chunk nếu order line có thể được ghi trước khi order tương ứng tồn tại.

Có thể tổ chức theo phase:

1. Ghi parent rows.
2. Thu thập/mapping generated IDs.
3. Ghi child rows theo batch.
4. Commit theo transaction boundary đã chọn.

Nếu dữ liệu được phân vùng theo key, có thể đảm bảo các row cùng aggregate đi vào cùng chunk để tránh cập nhật cùng một aggregate song song.

Với flatMapSequential, thứ tự phát kết quả được giữ nhưng các inner publisher vẫn chạy đồng thời. Nó không tự bảo đảm thứ tự thực thi SQL ở database.

## 17. Generated ID và kết quả từ batch

Một batch insert có thể cần trả generated ID cho từng row để tạo bảng con hoặc response.

Không giả định Statement.add() cùng getRowsUpdated() trả generated key cho từng binding set. Cách lấy generated values phụ thuộc driver, SQL dialect và khả năng RETURNING/generated values.

Các lựa chọn:

- Dùng ID do application tạo trước, ví dụ UUID.
- Dùng multi-row INSERT với RETURNING nếu database/driver hỗ trợ.
- Chèn parent rows rồi truy vấn lại theo business key duy nhất.
- Dùng insert từng row khi cần generated key theo cách driver hỗ trợ rõ.
- Thiết kế batch API trả mapping business key → generated ID.

Không truy vấn lại chỉ bằng tên hoặc field không unique. Cần business key có constraint để map chính xác kết quả.

Nếu cần generated ID và ordering của batch, viết integration test với đúng database/driver để xác nhận thứ tự Result và mapping từng row. Không suy luận thứ tự từ một driver khác.

## 18. Chọn transaction boundary cho import lớn

Một import lớn có thể gồm hàng chục nghìn chunk. Cần cân nhắc:

| Chiến lược | Atomicity | Thời gian transaction | Khả năng resume |
|---|---|---|---|
| Một transaction toàn import | Toàn bộ import cùng commit/rollback | Dài | Khó nếu lỗi muộn |
| Một transaction mỗi chunk | Atomic theo chunk | Ngắn hơn | Dễ checkpoint |
| Một transaction mỗi row | Atomic từng row | Nhiều transaction | Dễ cô lập lỗi nhưng tốn round-trip |
| Không transaction tường minh | Tùy driver/database/autocommit | Khó dự đoán | Có thể partial success |

Với import hàng triệu row, transaction toàn bộ thường tạo áp lực lớn lên database. Một transaction mỗi chunk thường dễ vận hành hơn nếu nghiệp vụ chấp nhận kết quả từng phần.

Nếu nghiệp vụ yêu cầu người dùng chỉ nhìn thấy toàn bộ import sau khi hoàn tất, có thể ghi dữ liệu vào staging table theo job ID rồi validate/promote trong transaction hoặc bằng trạng thái publication. Đây là thiết kế nghiệp vụ riêng, không nên cố giữ một transaction khổng lồ chỉ để che dữ liệu chưa hoàn tất.

## 19. Backpressure và memory khi chia nhóm

buffer(maxRows) tạo một collection cho mỗi chunk. Nó giúp tránh giữ toàn bộ nguồn, nhưng memory vẫn phụ thuộc:

- Số row mỗi chunk.
- Kích thước object.
- Số chunk đang chạy đồng thời.
- Prefetch ở các operator upstream/downstream.
- Retry queue và backlog.
- Các buffer của driver và connection pool.

Nếu dùng concurrency C và mỗi chunk có B row, ứng dụng có thể giữ xấp xỉ C × B row trong các chunk đang hoạt động, chưa tính buffer khác. Đây là ước lượng đơn giản để nhận diện áp lực memory.

Ví dụ, chunk 500 row và concurrency 4 có thể giữ khoảng 2.000 row trong các batch đang xử lý. Nếu mỗi row chứa JSON 100 KB, lượng dữ liệu đã có thể rất lớn.

Giới hạn cả batch size và concurrency. Với nguồn vô hạn, dùng bufferTimeout hoặc windowing phù hợp để nhóm không bị giữ mãi. Khi downstream chậm, Reactor backpressure có thể điều tiết demand trong chain, nhưng nhiều subscription độc lập vẫn có thể tạo tải tổng lớn.

## 20. Timeout và retry ở cấp chunk

Đặt timeout theo đặc tính của chunk. Một batch 500 row có thể cần nhiều thời gian hơn một insert đơn lẻ.

Ví dụ:

~~~java
Mono<Integer> writeChunk(List<Customer> batch) {
    return writeBatch(batch)
            .timeout(Duration.ofSeconds(10));
}
~~~

Timeout là ví dụ; giá trị thực tế phải dựa trên latency distribution và deadline của import. Khi timeout xảy ra trong transaction, cần xác nhận cancellation/rollback behavior trên driver/database.

Retry ở cấp chunk:

~~~java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(3));

return writeBatch(batch)
        .retryWhen(retryPolicy);
~~~

Chỉ retry lỗi tạm thời và thao tác có thể lặp an toàn. Nếu batch có thể đã commit nhưng client không nhận được kết quả, retry có thể tạo duplicate. Dùng idempotency key hoặc upsert có semantics rõ.

Không retry lỗi validation, constraint không thể tự phục hồi hoặc lỗi SQL syntax. Parameter limit cần giảm batch size, không retry nguyên nhóm.

## 21. Metrics để chọn batch size

Theo dõi metrics theo nhóm:

| Metric | Ý nghĩa |
|---|---|
| Rows per chunk | Số row thực tế mỗi nhóm |
| Parameters per statement | Tổng bind parameter của statement |
| Chunk duration | Thời gian ghi một nhóm |
| Rows per second | Throughput |
| Chunks per second | Tần suất hoàn tất nhóm |
| Batch error count | Số nhóm thất bại |
| Retry count | Số lần thử lại |
| Pool acquire duration | Thời gian chờ connection |
| Transaction duration | Thời gian transaction |
| Heap / allocation | Áp lực memory |
| DB lock wait / CPU / I/O | Tác động lên database |

Ghi batch_size như histogram/distribution hoặc metric có bucket. Không dùng một tag động cho mỗi batch ID hoặc import ID vì cardinality tăng không kiểm soát.

So sánh batch size 50, 100, 250, 500... trên cùng dữ liệu và concurrency. Quan sát p95/p99, throughput, DB resource và error rate. Chọn điểm cân bằng, không chỉ chọn cấu hình có throughput cao nhất trong một lần chạy.

## 22. Kiểm thử chunking và batch behavior

Nên có các test riêng:

### 22.1. Test thuật toán chia nhóm

Với input 1.001 row và maxRows 250, kỳ vọng các nhóm:

~~~text
250, 250, 250, 250, 1
~~~

Kiểm tra:

- Không mất row.
- Không duplicate row.
- Thứ tự được giữ nếu yêu cầu.
- Nhóm cuối không rỗng.
- Input rỗng không tạo statement.
- Row có parameter count lớn được xử lý đúng.

### 22.2. Test giới hạn tham số

Với mỗi row có P parameter và giới hạn M, xác nhận:

- Không statement nào vượt M.
- Tham số cố định được tính.
- Row có shape khác được đếm đúng.
- Một row vượt giới hạn được reject hoặc dùng SQL shape khác.
- Bind null có type chính xác.

### 22.3. Integration test với R2DBC driver

Dùng database/driver thật để xác nhận:

- Statement.add() được hỗ trợ.
- Multi-row SQL đúng cú pháp.
- Rows updated được báo đúng.
- Generated values được trả đúng nếu cần.
- Constraint lỗi làm batch/transaction có kết quả đúng.
- Transaction rollback đúng khi một row lỗi.
- Timeout/cancellation giải phóng connection.
- Kích thước batch lớn không vượt giới hạn driver.

H2 có thể kiểm tra một số SQL relational phổ thông, nhưng test batch production-specific nên chạy trên đúng engine và driver.

### 22.4. Test partial progress và resume

Nếu mỗi chunk commit riêng, test:

1. Tạo input nhiều chunk.
2. Cho chunk đầu thành công.
3. Làm chunk tiếp theo thất bại.
4. Xác nhận chunk trước vẫn tồn tại.
5. Retry job bằng cùng import ID.
6. Xác nhận không tạo duplicate và có thể tiếp tục đúng checkpoint.

Không dùng mock để tuyên bố database batch atomic. Cần integration test cho transaction behavior.

## 23. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Batch lớn lỗi parameter limit | Multi-row statement có quá nhiều placeholder | Tính rows × paramsPerRow + fixedParams |
| saveAll chậm dù đã truyền List lớn | Repository vẫn thực thi save theo từng entity | Kiểm tra SQL thực tế; dùng batch API khi cần |
| Batch có 500 row nhưng memory tăng cao | Row payload lớn hoặc nhiều chunk chạy song song | Giảm batch size/concurrency, thêm max bytes |
| Chunk cuối không được ghi | Nguồn không complete và chỉ dùng buffer theo count | Dùng bufferTimeout/flush policy |
| Một lỗi làm mất toàn bộ import | Tất cả chunk nằm trong một transaction | Xem xét transaction theo chunk và checkpoint |
| Import commit một phần khó resume | Không có idempotency/checkpoint | Thêm job ID, chunk state và unique key |
| Duplicate khi retry | Write không idempotent hoặc response mất sau commit | Dùng idempotency key/upsert |
| Generated ID không map đúng | Driver không trả generated value theo giả định | Test RETURNING hoặc truy vấn lại bằng business key |
| Batch update ảnh hưởng sai row | Parameter binding hoặc thứ tự bind sai | Test binding và dùng helper rõ ràng |
| Các row liên quan bị lỗi FK | Chunk xử lý sai thứ tự parent/child | Tách phase hoặc nhóm theo aggregate |
| Pool pending tăng | Chunk concurrency quá cao hoặc transaction dài | Giảm concurrency, đo acquire/hold time |
| SQL rất dài và parse chậm | Multi-row statement quá lớn | Giảm row count hoặc dùng Statement.add |
| Một row lỗi làm cả nhóm rollback | Atomic chunk là chính sách hiện tại | Quyết định reject cả nhóm hay cô lập row |
| Driver không hỗ trợ add() | Batch capability khác nhau | Dùng multi-row SQL hoặc fallback có kiểm soát |

## 24. Quy trình chọn kích thước nhóm

Một quy trình thực tế:

1. Xác định số cột/parameter của mỗi row.
2. Xác định parameter cố định của statement.
3. Kiểm tra giới hạn database và R2DBC driver.
4. Chọn maxRows ban đầu theo kích thước row và workload.
5. Tính maxRows theo parameter budget.
6. Chọn min của hai giới hạn.
7. Nếu row shape biến đổi, đếm parameter tích lũy khi tạo chunk.
8. Nếu row size biến động, thêm giới hạn payload bytes.
9. Chọn transaction boundary: toàn import hay mỗi chunk.
10. Chọn concurrency cho chunk theo ngân sách connection/database.
11. Chạy load test trên đúng database/driver.
12. So sánh throughput, p95/p99, memory, pool wait và lock.
13. Kiểm tra lỗi giữa batch và khả năng resume.
14. Ghi cấu hình vào một nơi có thể điều chỉnh theo môi trường.
15. Đo lại sau khi nâng driver hoặc database version.

Không hard-code một batch size duy nhất nếu nhiều loại dữ liệu có đặc tính khác nhau. Có thể có cấu hình riêng cho import customer, insert event, update inventory và batch reporting.

## 25. Checklist triển khai

- [ ] Xác định chunking theo row count, parameter count hay cả hai.
- [ ] Phân biệt chunk ở Reactor với batch statement ở driver.
- [ ] Không mặc định saveAll() là một SQL bulk statement.
- [ ] Tính parameter count cho mỗi row và tham số cố định.
- [ ] Dùng giới hạn an toàn đã xác nhận cho database/driver.
- [ ] Xử lý row có parameter shape khác nhau.
- [ ] Bind null với type phù hợp.
- [ ] Dùng Statement.add() chỉ khi driver hỗ trợ.
- [ ] Dùng placeholder theo dialect/driver.
- [ ] Giới hạn payload bytes khi row size biến động.
- [ ] Giới hạn số chunk đang chạy đồng thời.
- [ ] Xác định transaction boundary rõ ràng.
- [ ] Có checkpoint/idempotency nếu commit theo chunk.
- [ ] Xử lý generated ID theo khả năng driver.
- [ ] Bảo đảm thứ tự parent/child và aggregate.
- [ ] Có timeout/retry theo chính sách an toàn.
- [ ] Đo rows/sec, chunk duration, pool wait và transaction duration.
- [ ] Test parameter limit, partial success và resume.
- [ ] Chạy integration test trên đúng database production.

## 26. Kết luận

Chia dữ liệu thành nhóm theo số hàng hoặc số tham số là cách kiểm soát kích thước thao tác ghi trong Spring Data Relational R2DBC. Giới hạn theo số hàng dễ triển khai với Reactor buffer, trong khi giới hạn theo parameter cần tính số bind value của từng row và tham số cố định. Với multi-row INSERT, số parameter tăng theo số hàng; với R2DBC Statement.add(), mỗi binding set có số parameter riêng nhưng batch vẫn chịu giới hạn về payload, memory và driver.

Hãy phân biệt chunking ở tầng ứng dụng, batch statement và multi-row SQL. saveAll() là API lưu nhiều entity, không phải cam kết một bulk SQL statement. Chọn batch size bằng cách lấy giới hạn nhỏ hơn giữa max rows và parameter budget, bổ sung giới hạn payload khi cần, rồi đo trên database/driver thật.

Cuối cùng, tách chunk size khỏi transaction size. Một transaction cho toàn import bảo đảm atomicity nhưng có thể rất dài; transaction theo chunk dễ resume hơn nhưng cho phép partial progress. Kết hợp backpressure, concurrency hữu hạn, idempotency, checkpoint, metrics và integration test để batch ghi nhanh mà vẫn kiểm soát được memory, connection, lỗi và tính nhất quán dữ liệu.


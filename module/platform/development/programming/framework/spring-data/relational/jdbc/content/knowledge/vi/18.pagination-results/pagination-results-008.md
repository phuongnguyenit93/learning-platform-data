# Stream kết quả và đóng tài nguyên bằng try-with-resources

## 1. Khi nào cần đọc kết quả dưới dạng Stream?

Một repository method thường trả về `List<T>` hoặc `Page<T>`. Cách này thuận tiện khi số hàng có giới hạn: truy vấn chạy, kết quả được ánh xạ thành các object, rồi ứng dụng xử lý collection trong bộ nhớ.

Nhưng hãy tưởng tượng cần xuất một triệu giao dịch ra file, tính tổng hợp dữ liệu lớn hoặc chạy một tác vụ kiểm tra trên toàn bộ khách hàng. Nếu tải tất cả thành `List<T>`, ứng dụng phải giữ một lượng lớn object cùng lúc. Bộ nhớ có thể tăng cao, thời gian chờ trước khi xử lý phần tử đầu tiên cũng dài.

Với truy vấn JDBC phù hợp, Spring Data JDBC có thể trả về `Stream<T>` để caller xử lý từng phần tử theo một pipeline Java Stream. Stream có thể gắn với những tài nguyên JDBC như connection, statement và result set. Vì vậy, **đóng Stream đúng cách là một phần của việc giải phóng tài nguyên database**.

Điểm cần nhớ ngay từ đầu:

- `Stream<T>` là một cách tiêu thụ kết quả, không tự động bảo đảm database driver luôn dùng server-side cursor hoặc không tải trước dữ liệu.
- Một stream dựa trên JDBC có thể giữ connection và result set mở trong suốt thời gian tiêu thụ.
- Phải đóng stream, kể cả khi xử lý lỗi hoặc dừng sớm.
- Dùng `try-with-resources` để bảo đảm `close()` được gọi.
- Transaction phải còn hiệu lực trong lúc stream được đọc; thường đặt transaction ở service đang tiêu thụ stream.
- Nếu cần phân trang, checkpoint, retry hoặc xử lý độc lập theo lô, `Page`, `Slice` hay truy vấn theo keyset có thể phù hợp hơn.

## 2. Stream<T> trong repository của Spring Data JDBC

Một query method có thể khai báo kiểu trả về `Stream<T>` khi module, phiên bản Spring Data JDBC và driver hỗ trợ kiểu thực thi đó. Ví dụ:

```java
import java.util.stream.Stream;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.Repository;

public interface CustomerRepository
        extends Repository<Customer, Long> {

    @Query("""
        SELECT id, name, email
        FROM customers
        ORDER BY id
        """)
    Stream<Customer> streamAllCustomers();
}
```

Khi gọi method, repository cung cấp một Stream để caller duyệt các customer. Tên bảng, cột và mapping trong ví dụ cần khớp schema thực tế. `ORDER BY id` tạo thứ tự ổn định cho việc xử lý; SQL không bảo đảm thứ tự hàng nếu không có `ORDER BY`.

Nếu repository đã kế thừa `CrudRepository`, method stream vẫn có thể được khai báo cùng các phương thức CRUD:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    @Query("""
        SELECT id, name, email
        FROM customers
        ORDER BY id
        """)
    Stream<Customer> streamAllCustomers();
}
```

Không nhầm `Stream<T>` với `Flux<T>`:

| Kiểu | Mô hình | Đặc điểm |
| --- | --- | --- |
| `List<T>` | Collection đồng bộ | Kết quả thường được materialize thành danh sách trước khi caller xử lý. |
| `Stream<T>` | Pipeline Java Stream | Duyệt tuần tự/lười theo abstraction Stream; cần đóng nếu gắn với tài nguyên JDBC. |
| `Page<T>` | Một trang kết quả + metadata | Thường cần truy vấn dữ liệu trang và có thể có thêm truy vấn đếm. |
| `Slice<T>` | Một lát kết quả | Cho biết còn trang tiếp theo hay không, thường tránh tổng số hàng. |
| `Flux<T>` | Reactive Streams | API reactive có backpressure; không phải kiểu trả về JDBC blocking thông thường. |

## 3. Vì sao Stream phải được đóng?

Một stream từ truy vấn JDBC có thể dựa trên các tài nguyên sau:

```text
Application code
      |
      v
Java Stream<Customer>
      |
      v
ResultSet  -------- cursor / current row
      |
      v
PreparedStatement
      |
      v
JDBC Connection
      |
      v
Connection pool / Database
```

Khi caller duyệt stream, JDBC cần đọc các hàng và ánh xạ chúng thành object. Nếu stream không được đóng, những tài nguyên liên quan có thể không được giải phóng đúng lúc:

- Connection có thể tiếp tục bị giữ trong pool, làm giảm số connection sẵn sàng cho request khác.
- Result set và statement có thể còn mở.
- Database có thể phải giữ cursor hoặc trạng thái truy vấn.
- Transaction có thể kéo dài lâu hơn dự kiến.

Không nên chờ garbage collector giải phóng các tài nguyên này. Garbage collection không phải cơ chế đóng JDBC resource có thời điểm xác định.

Java `Stream` mở rộng `AutoCloseable`. Vì vậy có thể dùng trực tiếp với `try-with-resources`:

```java
try (Stream<Customer> customers = repository.streamAllCustomers()) {
    customers.forEach(this::process);
}
```

Khi rời khỏi block, Java gọi `close()` trên stream. Điều này vẫn xảy ra nếu thân block kết thúc bình thường hoặc ném exception.

## 4. Dùng try-with-resources để đóng Stream

Đây là cách dùng cơ bản nên ưu tiên:

```java
try (Stream<Customer> customers = repository.streamAllCustomers()) {
    customers.forEach(customer -> {
        System.out.println(customer.id() + " - " + customer.name());
    });
}
```

`try-with-resources` bảo đảm `close()` được gọi. Không cần tự viết `finally` để đóng stream trong trường hợp thông thường.

### 4.1. Xử lý một phần tử mỗi lần

Ví dụ xử lý từng customer:

```java
try (Stream<Customer> customers = repository.streamAllCustomers()) {
    customers.forEach(customer -> {
        customerService.recalculate(customer.id());
    });
}
```

Pipeline không tạo một `List<Customer>` chứa toàn bộ kết quả. Tuy nhiên, cách này chỉ giảm việc giữ collection kết quả trong bộ nhớ; nó không chứng minh driver/database không buffer dữ liệu ở tầng thấp hơn. Hãy kiểm tra driver, fetch size và cách cấu hình nếu cần streaming thật sự với tập dữ liệu lớn.

### 4.2. Đóng stream khi xử lý lỗi

Giả sử một phần tử gây exception:

```java
try (Stream<Customer> customers = repository.streamAllCustomers()) {
    customers.forEach(customer -> {
        if (customer.email() == null) {
            throw new IllegalStateException("Customer has no email");
        }
        sendNotification(customer);
    });
}
```

Khi exception thoát khỏi block, `try-with-resources` vẫn gọi `close()`. Nếu cả thân block và `close()` cùng ném exception, Java giữ exception chính và ghi nhận exception phát sinh khi đóng dưới dạng suppressed exception.

Đừng viết:

```java
Stream<Customer> customers = repository.streamAllCustomers();
customers.forEach(this::process);
// Không có close(): tài nguyên có thể bị giữ lại.
```

Đoạn code trên bỏ qua trách nhiệm giải phóng resource.

### 4.3. Dừng sớm vẫn phải đóng

Một pipeline có thể không duyệt hết dữ liệu:

```java
try (Stream<Customer> customers = repository.streamAllCustomers()) {
    customers
            .filter(customer -> customer.name().startsWith("A"))
            .findFirst()
            .ifPresent(this::process);
}
```

`findFirst()` là short-circuit terminal operation: nó có thể dừng sau khi tìm được phần tử đầu tiên phù hợp. Nhưng điều đó **không tự động thay thế việc đóng stream**. `try-with-resources` vẫn cần thiết.

Tương tự, các terminal operation như `anyMatch`, `allMatch`, `limit(...).forEach(...)` có thể dừng trước khi đọc hết dữ liệu. Hãy giữ stream trong phạm vi tài nguyên rõ ràng.

## 5. Transaction phải bao trùm thời gian tiêu thụ Stream

Đây là điểm đặc biệt quan trọng với Spring Data JDBC. Một stream từ JDBC có thể cần connection và result set trong suốt quá trình duyệt. Nếu transaction hoặc connection scope kết thúc trước khi caller đọc dữ liệu, stream có thể không còn tài nguyên hợp lệ để tiếp tục.

Một cách tổ chức an toàn là đặt `@Transactional(readOnly = true)` ở **service method tiêu thụ stream**, rồi mở và đóng stream ngay bên trong method đó:

```java
package com.example.customer;

import java.util.stream.Stream;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerExportService {

    private final CustomerRepository customers;

    public CustomerExportService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public void exportAll() {
        try (Stream<Customer> stream = customers.streamAllCustomers()) {
            stream.forEach(this::writeRow);
        }
    }

    private void writeRow(Customer customer) {
        // Ghi một dòng vào output đã được quản lý bởi service.
        System.out.println(customer.id() + "," + customer.name());
    }
}
```

Luồng thực thi:

1. Spring mở transaction khi gọi service qua proxy.
2. Repository chạy query trong transaction hiện tại.
3. Service tiêu thụ stream khi connection/transaction vẫn còn hiệu lực.
4. `try-with-resources` đóng stream sau khi xử lý xong hoặc khi có lỗi.
5. Service kết thúc; transaction interceptor hoàn tất transaction.

### Không trả Stream ra khỏi transactional service

Tránh cách viết:

```java
@Transactional(readOnly = true)
public Stream<Customer> streamCustomers() {
    return customers.streamAllCustomers();
}
```

Nếu transaction được mở bởi proxy của phương thức này, transaction có thể kết thúc ngay khi phương thức trả về Stream. Caller bắt đầu duyệt stream sau đó, khi phạm vi transaction đã đóng. Tùy implementation và driver, việc đọc có thể thất bại hoặc không còn được bảo đảm.

Thay vào đó, để service vừa mở transaction vừa tiêu thụ stream như ví dụ `exportAll()`. Nếu API thực sự cần trả kết quả cho caller, hãy cân nhắc trả `List`, `Page`, `Slice`, DTO hoặc thiết kế một abstraction có vòng đời tài nguyên được quản lý rõ ràng.

### Transactional annotation phải đi qua Spring proxy

`@Transactional` hoạt động thông qua cơ chế proxy/AOP trong cấu hình Spring thông thường. Gọi một phương thức transactional từ phương thức khác cùng instance (`this.someTransactionalMethod()`) có thể không đi qua proxy, vì vậy không kích hoạt transaction như kỳ vọng. Đặt ranh giới transaction tại public service method được gọi từ bean khác hoặc dùng cấu trúc phù hợp với transaction management của ứng dụng.

## 6. Stream không đồng nghĩa với server-side cursor

Đừng suy luận rằng khai báo `Stream<T>` tự động khiến database gửi từng hàng qua mạng mà không buffer. Có nhiều tầng ảnh hưởng:

- Spring Data JDBC query execution.
- Spring JDBC và cách xử lý `ResultSet`.
- JDBC driver.
- Cấu hình fetch size.
- Autocommit và transaction.
- Database server và dialect.

Một số driver có thể mặc định tải nhiều hoặc toàn bộ kết quả về client; một số driver hỗ trợ cursor/fetch theo lô khi cấu hình đúng. Hành vi phụ thuộc database và driver.

### 6.1. Fetch size

JDBC có khái niệm fetch size, cho phép gợi ý số hàng driver nên lấy mỗi lần từ database. Đây là một **hint**; không phải mọi driver đều thực hiện giống nhau.

Với một số driver, fetch size mặc định bằng 0 có thể khiến driver đọc toàn bộ kết quả. Với driver khác, fetch size chỉ có hiệu lực trong điều kiện transaction/autocommit cụ thể. Vì vậy, nếu export hàng triệu dòng:

1. Đọc tài liệu của JDBC driver đang dùng.
2. Kiểm tra cách cấu hình fetch size mà phiên bản Spring Data JDBC/Spring JDBC hỗ trợ.
3. Xác nhận điều kiện transaction và autocommit của driver.
4. Đo bộ nhớ và lượng dữ liệu được đọc qua một tập dữ liệu đủ lớn.

Không đặt một giá trị fetch size tùy ý rồi mặc định nó có tác dụng trên mọi database.

### 6.2. Fetch size không phải page size

Hai khái niệm khác nhau:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| Fetch size | Gợi ý cho JDBC driver cách lấy hàng từ result set theo lô. |
| Page size | Số hàng ứng dụng yêu cầu trong một trang truy vấn. |

Fetch size không làm query trở thành nhiều câu SQL phân trang. Page size thường tham gia vào giới hạn truy vấn và có thể khiến ứng dụng gọi repository nhiều lần.

## 7. Stream và các cách xử lý kết quả khác

Không phải truy vấn lớn nào cũng cần `Stream<T>`. Chọn cách trả về theo yêu cầu của use case:

| Nhu cầu | Lựa chọn phù hợp | Vì sao |
| --- | --- | --- |
| Vài chục/vài trăm hàng để hiển thị | `List<T>` | Đơn giản, dễ dùng sau khi query hoàn tất. |
| Giao diện có trang tiếp theo và cần tổng số | `Page<T>` | Cung cấp content, số trang và total metadata; có thể cần count query. |
| Chỉ cần biết còn kết quả tiếp theo không | `Slice<T>` | Tránh chi phí tính tổng số hàng nếu không cần. |
| Duyệt tập lớn trong một phạm vi tài nguyên liên tục | `Stream<T>` | Caller xử lý dần và đóng stream khi xong. |
| Chạy theo từng batch có checkpoint/retry | Phân trang hoặc keyset/chunk | Mỗi lô có ranh giới và có thể lưu tiến độ. |
| Dữ liệu reactive end-to-end | R2DBC với `Flux<T>` | API reactive không chặn, có backpressure; cần driver và toàn bộ pipeline hỗ trợ. |

### 7.1. Page

`Page<T>` phù hợp cho giao diện cần biết tổng số kết quả và số trang:

```java
Page<Customer> findByStatus(
        CustomerStatus status,
        Pageable pageable
);
```

Thông thường, framework cần truy vấn dữ liệu của trang và có thể thực hiện thêm count query để tính tổng. Với tập dữ liệu rất lớn, count query có thể đắt.

### 7.2. Slice

`Slice<T>` phù hợp khi giao diện chỉ cần biết có trang tiếp theo:

```java
Slice<Customer> findByStatus(
        CustomerStatus status,
        Pageable pageable
);
```

Nó tránh yêu cầu tổng số hàng. Ứng dụng thường lấy thêm một hàng để xác định còn dữ liệu tiếp theo hay không; chi tiết phụ thuộc cách thực thi.

### 7.3. Keyset/chunk processing

Với batch lớn, thay vì giữ một result set mở hàng giờ, có thể đọc theo từng lô:

```sql
SELECT id, name, email
FROM customers
WHERE id > :lastSeenId
ORDER BY id
LIMIT :batchSize;
```

Sau khi xử lý một lô, lưu ID cuối cùng rồi truy vấn lô tiếp theo. Đây là mô hình keyset pagination. Nó có thể giảm thời gian giữ connection và hỗ trợ resume sau lỗi, nhưng cần khóa sắp xếp ổn định, index phù hợp và semantics rõ khi dữ liệu thay đổi trong lúc chạy.

## 8. Xử lý Stream theo pipeline Java

Stream hỗ trợ các thao tác trung gian và terminal operation quen thuộc:

```java
try (Stream<Customer> stream = customers.streamAllCustomers()) {
    long activeCount = stream
            .filter(Customer::active)
            .peek(customer -> logCustomer(customer.id()))
            .count();

    System.out.println("Active customers: " + activeCount);
}
```

Một số lưu ý:

- Intermediate operation như `filter`, `map`, `sorted` thường không tiêu thụ dữ liệu ngay.
- Terminal operation như `forEach`, `collect`, `count`, `findFirst` kích hoạt việc duyệt.
- Stream chỉ có thể được tiêu thụ một lần.
- `sorted()` thường cần giữ dữ liệu để sắp xếp toàn bộ; dùng nó trên stream JDBC lớn có thể làm mất lợi ích về bộ nhớ.
- `collect(toList())` biến kết quả thành collection và có thể đưa toàn bộ dữ liệu vào heap.
- `peek()` nên dùng cho quan sát/debug đơn giản, không nên giấu side effect quan trọng trong đó.

### 8.1. Map sang DTO

Nếu cần xuất dữ liệu nhẹ hơn entity:

```java
try (Stream<Customer> stream = customers.streamAllCustomers()) {
    stream
            .map(customer -> new CustomerExportRow(
                    customer.id(),
                    customer.name(),
                    customer.email()
            ))
            .forEach(csvWriter::write);
}
```

Tuy nhiên, nếu query chỉ cần ba cột, cân nhắc projection/DTO query để database chỉ trả các cột cần thiết thay vì tải toàn bộ aggregate. Khả năng mapping projection cụ thể cần theo API của phiên bản Spring Data JDBC.

### 8.2. Không dùng parallel stream với JDBC result set

Không nên gọi:

```java
try (Stream<Customer> stream = customers.streamAllCustomers()) {
    stream.parallel().forEach(this::process);
}
```

Một stream dựa trên JDBC result set thường không được thiết kế để nhiều thread cùng đọc một cursor/connection. Parallel execution còn có thể khiến thứ tự xử lý thay đổi và làm tăng tải đồng thời lên database. Nếu cần xử lý song song, hãy đọc theo batch độc lập, đóng query hiện tại, rồi gửi các batch tới worker pool theo giới hạn tải đã thiết kế.

## 9. Đừng giữ connection mở trong lúc làm việc chậm bên ngoài

Ví dụ:

```java
try (Stream<Customer> stream = customers.streamAllCustomers()) {
    stream.forEach(customer -> {
        remoteApi.send(customer);
    });
}
```

Nếu `remoteApi.send` mất vài giây cho mỗi hàng, connection và transaction có thể bị giữ trong thời gian rất dài. Điều này có thể:

- Làm cạn connection pool.
- Giữ snapshot/transaction lâu, ảnh hưởng vacuum hoặc lock tùy database.
- Làm batch dễ thất bại giữa chừng do network.
- Khiến việc retry khó xác định phần tử nào đã được xử lý.

Với tích hợp bên ngoài, nên cân nhắc đọc theo batch, đóng transaction đọc trước khi gọi API từ xa, rồi ghi checkpoint. Nếu yêu cầu một transaction xuyên suốt, phải hiểu rõ chi phí và giới hạn của database/connection pool.

## 10. Một ví dụ service xuất CSV có quản lý tài nguyên

Giả sử có một writer đã được tạo và đóng ở tầng gọi. Service dùng stream trong transaction:

```java
package com.example.customer;

import java.io.BufferedWriter;
import java.io.IOException;
import java.util.stream.Stream;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerCsvExportService {

    private final CustomerRepository customers;

    public CustomerCsvExportService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public void writeCsv(BufferedWriter writer) throws IOException {
        writer.write("id,name,email");
        writer.newLine();

        try (Stream<Customer> stream = customers.streamAllCustomers()) {
            stream.forEach(customer -> {
                try {
                    writer.write(csv(customer.id()));
                    writer.write(",");
                    writer.write(csv(customer.name()));
                    writer.write(",");
                    writer.write(csv(customer.email()));
                    writer.newLine();
                } catch (IOException ex) {
                    throw new CsvWriteException(ex);
                }
            });
        }
    }

    private String csv(Object value) {
        if (value == null) {
            return "";
        }
        String text = value.toString();
        return "\"" + text.replace("\"", "\"\"") + "\"";
    }

    private static class CsvWriteException extends RuntimeException {
        CsvWriteException(IOException cause) {
            super(cause);
        }
    }
}
```

Ví dụ chỉ minh họa phạm vi đóng stream; xử lý file production còn cần quyết định ai sở hữu `BufferedWriter`, ai đóng writer, encoding, escaping CSV và cách xử lý file tạm khi transaction đọc thất bại. Không để một service đóng tài nguyên do caller sở hữu nếu hợp đồng không quy định điều đó.

Nếu exception được bọc thành runtime exception, Spring transaction mặc định thường rollback khi nó thoát khỏi transactional method. Đây là transaction đọc nên rollback không thay đổi dữ liệu, nhưng connection/resource vẫn cần được đóng.

## 11. Vòng đời tài nguyên và thứ tự đóng

Với try-with-resources:

```java
try (Stream<Customer> stream = repository.streamAllCustomers()) {
    // consume stream
}
```

Java gọi `stream.close()` khi rời block. Stream từ Spring Data JDBC/Spring JDBC có thể đăng ký hành động đóng để giải phóng result set, statement và các resource liên quan theo implementation. Caller không cần tự đóng `ResultSet` hoặc `Connection` nếu repository là bên sở hữu chúng.

Nếu caller mở thêm resource:

```java
try (
        Stream<Customer> stream = repository.streamAllCustomers();
        BufferedWriter writer = Files.newBufferedWriter(path)
) {
    stream.forEach(customer -> write(writer, customer));
}
```

Các resource được đóng theo thứ tự ngược với thứ tự khai báo: writer đóng trước, stream đóng sau. Hãy cân nhắc thứ tự này nếu việc ghi output còn cần stream hoạt động; trong ví dụ, cả hai chỉ được sử dụng trong block và đều được giải phóng khi thoát.

Nếu stream được bọc qua các thao tác Java Stream, close handler của stream nguồn được truyền theo pipeline; đóng stream cuối cùng sẽ đóng nguồn. Tránh tạo stream dẫn xuất rồi bỏ quên stream gốc mà không có một phạm vi sở hữu rõ ràng.

## 12. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Connection pool cạn sau batch | Stream không được đóng hoặc được giữ quá lâu | Dùng try-with-resources và giới hạn thời gian tiêu thụ. |
| Stream lỗi khi bắt đầu đọc | Transaction/connection scope đã kết thúc trước khi stream được tiêu thụ | Đặt transaction ở service tiêu thụ stream; không trả stream ra ngoài transactional method. |
| Dữ liệu lớn vẫn dùng nhiều heap | Driver buffer toàn bộ, fetch size không hiệu lực, hoặc pipeline dùng `collect`/`sorted` | Kiểm tra driver, fetch size, transaction và các intermediate/terminal operation. |
| Chỉ đọc vài hàng rồi dừng nhưng resource vẫn mở | `findFirst`, `limit` hoặc `anyMatch` không tự đóng stream | Bao stream trong try-with-resources. |
| Xử lý song song gây lỗi JDBC | Dùng parallel stream trên nguồn dựa vào cursor/connection | Duyệt tuần tự hoặc đọc batch độc lập trước khi xử lý song song. |
| Batch giữ transaction quá lâu | Gọi API/file/network chậm ngay trong pipeline | Chia chunk, đóng query giữa các lô và checkpoint tiến độ. |
| Kết quả thay đổi thứ tự giữa lần chạy | Query không có `ORDER BY` | Thêm thứ tự xác định, thường kèm khóa duy nhất làm tiêu chí phụ. |
| Query trả Stream không được hỗ trợ | Phiên bản/module/driver không hỗ trợ cách thực thi hoặc kiểu trả về | Kiểm tra tài liệu đúng phiên bản; dùng JDBC template hoặc phân trang nếu cần. |

## 13. Quy trình chọn Stream hay phân trang

Trước khi dùng `Stream<T>`, hãy xác định:

1. **Số lượng dữ liệu:** vài trăm hàng hay hàng triệu hàng?
2. **Cách xử lý:** xử lý liên tục, hay cần lưu checkpoint sau mỗi nhóm?
3. **Thời gian xử lý:** mỗi hàng xử lý nhanh hay có I/O bên ngoài chậm?
4. **Transaction:** có thể giữ một transaction đọc trong suốt quá trình không?
5. **Driver:** có hỗ trợ streaming/cursor và fetch size như mong muốn không?
6. **Khả năng retry:** nếu job chết ở giữa, có cần chạy lại từ vị trí cuối?
7. **Thứ tự:** cần thứ tự xác định để resume hoặc xuất dữ liệu không?

Chọn `Stream<T>` khi có một lượt đọc tuần tự trong phạm vi tài nguyên ngắn, caller có thể tiêu thụ và đóng stream rõ ràng, và driver được cấu hình phù hợp. Chọn phân trang/chunk khi cần thời gian xử lý dài, checkpoint, retry, giới hạn transaction hoặc xử lý độc lập.

## 14. Bài tập tự thực hành

**Bài tập 1 — Stream cơ bản.** Tạo query method trả về `Stream<Customer>`, gọi trong một service và duyệt bằng try-with-resources. Xác nhận dữ liệu được đọc đúng.

**Bài tập 2 — Short-circuit.** Dùng `findFirst()` hoặc `limit(5)` để chỉ đọc một phần kết quả. Giữ try-with-resources và giải thích vì sao terminal operation không tự đóng resource.

**Bài tập 3 — Cố ý không đóng.** Viết một ví dụ không dùng try-with-resources trong môi trường thử nghiệm, quan sát trạng thái connection pool hoặc resource metrics, sau đó sửa lại. Không thực hiện thí nghiệm gây cạn pool trên môi trường dùng chung.

**Bài tập 4 — Transaction scope.** Tạo một service trả stream từ phương thức có `@Transactional`, sau đó tiêu thụ ở caller. So sánh với service tự tiêu thụ stream bên trong transaction và giải thích khác biệt về vòng đời connection.

**Bài tập 5 — Fetch size.** Dùng database/driver thực tế của dự án, cấu hình fetch size theo hướng dẫn driver. Đo heap và thời gian trên tập dữ liệu lớn; so sánh với `List<T>`.

**Bài tập 6 — Chunking.** Thay stream dài bằng keyset pagination theo ID, xử lý mỗi batch rồi lưu checkpoint. Mô tả cách tiếp tục khi job dừng giữa hai batch.

**Bài tập 7 — Parallel stream.** Giải thích vì sao không nên gọi `parallel()` trực tiếp trên stream gắn với JDBC result set. Thiết kế phương án đọc batch rồi xử lý song song với giới hạn worker.

## 15. Ghi nhớ

`Stream<T>` là lựa chọn hữu ích để tiêu thụ kết quả truy vấn theo pipeline Java, nhưng với Spring Data JDBC, stream có thể giữ các tài nguyên JDBC mở trong lúc đọc. Hãy đóng nó bằng `try-with-resources`, tiêu thụ trong phạm vi transaction còn hiệu lực và tránh trả stream ra khỏi service đã kết thúc transaction.

Stream không tự bảo đảm driver dùng server-side cursor hoặc không buffer dữ liệu; fetch size và hành vi thực tế phụ thuộc driver, database và transaction. Với xử lý dài, cần checkpoint hoặc retry, phân trang/chunk thường dễ quản lý hơn. Hãy chọn theo vòng đời tài nguyên và yêu cầu vận hành của use case, không chỉ theo số dòng dữ liệu.

### Tài liệu tham khảo

- [Spring Data Relational – Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Data Commons – Repository Query Return Types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html)
- [Java 21 – Stream API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html)
- [Java 21 – AutoCloseable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html)

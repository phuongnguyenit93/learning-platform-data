# Giao dịch Spanner và lựa chọn cách đọc dữ liệu

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, Spring Boot tích hợp các dịch vụ managed của AWS, Azure và Google Cloud để truy cập dữ liệu, storage, messaging và quản lý danh tính/quyền. Trên Google Cloud, **Cloud Spanner** cung cấp cơ sở dữ liệu quan hệ phân tán với giao dịch ACID và tính nhất quán mạnh. Khi xây dựng ứng dụng, lựa chọn cách đọc và transaction ảnh hưởng trực tiếp đến độ mới dữ liệu, latency, contention, chi phí và khả năng phục hồi.

Bài học tập trung vào cách đọc/ghi dữ liệu trong Spanner và cách Spring Boot sử dụng các cơ chế đó:

1. Phân biệt single-use read, read-only transaction và read-write transaction.
2. Hiểu strong read, exact staleness, max staleness và read timestamp.
3. Chọn đọc theo primary key, KeySet hay SQL query/index.
4. Sử dụng snapshot nhất quán khi một use case cần nhiều lần đọc.
5. Dùng read-write transaction cho nghiệp vụ cần đọc rồi ghi nguyên tử.
6. Phân biệt DML, mutation, batch DML và Partitioned DML.
7. Hiểu transaction retry, abort và cách tránh side effect lặp.
8. Tích hợp transaction với Spring Data Spanner và kiểm thử trên emulator/sandbox.

> **Phạm vi:** Ví dụ sử dụng GoogleSQL interface, Cloud Spanner Java client và Spring Data Spanner. Spanner có semantics transaction riêng; không áp dụng máy móc các giả định JDBC/JPA như isolation level tùy chọn, nested transaction hoặc HikariCP.

## 1. Vì sao cần chọn đúng cách đọc?

Một API đọc chi tiết đơn hàng, một dashboard thống kê và một luồng thanh toán có yêu cầu dữ liệu khác nhau.

- Màn hình chi tiết thường cần kết quả mới nhất và đọc theo primary key.
- Dashboard có thể chấp nhận dữ liệu chậm hơn vài giây để giảm latency.
- Một báo cáo đọc nhiều bảng cần thấy các bảng tại cùng một snapshot.
- Luồng thanh toán cần đọc trạng thái rồi cập nhật trong một transaction để tránh hai request cùng xử lý một đơn.
- Batch cleanup có thể cập nhật hàng triệu row và cần cơ chế phù hợp với Partitioned DML.

Nếu mọi truy vấn đều dùng strong read hoặc mọi thao tác đều bọc trong read-write transaction, ứng dụng có thể tạo độ trễ và contention không cần thiết. Ngược lại, dùng stale read cho quyết định nghiệp vụ nhạy cảm có thể khiến ứng dụng hành động dựa trên dữ liệu cũ.

### 1.1. Các câu hỏi trước khi viết query

| Câu hỏi | Ví dụ lựa chọn |
| --- | --- |
| Cần dữ liệu mới đến mức nào? | Strong, exact staleness hoặc max staleness |
| Đọc một row hay nhiều row? | Primary key, KeySet hoặc SQL |
| Có nhiều lần đọc phải cùng snapshot không? | Single-use read hoặc read-only transaction |
| Có cần đọc rồi ghi nguyên tử không? | Read-write transaction |
| Ghi một nhóm row đã biết hay cập nhật theo điều kiện? | Mutation hoặc DML |
| Tác vụ có thể chạy trên nhiều partition độc lập không? | Cân nhắc Partitioned DML |
| Nếu transaction bị abort, callback có an toàn khi chạy lại không? | Idempotency và không có side effect ngoài |

## 2. Các loại thao tác và transaction trong Spanner

### 2.1. Bảng tổng quan

| Cơ chế | Có đọc? | Có ghi? | Snapshot/atomicity | Use case điển hình |
| --- | --- | --- | --- | --- |
| Single-use read | Có | Không | Một thao tác đọc với read timestamp theo TimestampBound | Đọc một row hoặc một query |
| Read-only transaction | Có | Không | Nhiều lần đọc trên cùng snapshot | Báo cáo cần nhiều query nhất quán |
| Read-write transaction | Có | Có | Đọc/ghi nguyên tử, có thể bị abort và retry | Cập nhật đơn hàng, tồn kho |
| Mutation commit | Không cần đọc trước | Có | Một commit chứa các mutation được commit cùng nhau | Ghi các row đã biết |
| DML | Có thể có predicate | Có | Chạy trong read-write transaction | UPDATE/DELETE theo điều kiện |
| Partitioned DML | Không cần transaction ứng dụng bao quanh | Có | Nhiều partition; không atomic trên toàn câu lệnh | Backfill/cleanup quy mô lớn |

Spanner client quản lý transaction và session qua gRPC. Ứng dụng không cần tự mở JDBC connection cho từng thao tác.

### 2.2. Sơ đồ lựa chọn

~~~mermaid
flowchart TD
    START["Use case cần truy cập dữ liệu"] --> WRITE{"Có cần ghi dữ liệu?"}
    WRITE -->|"Không"| SNAP{"Nhiều lần đọc phải cùng snapshot?"}
    SNAP -->|"Có"| RO["Read-only transaction"]
    SNAP -->|"Không"| FRESH{"Cần dữ liệu mới nhất?"}
    FRESH -->|"Có"| STRONG["Single-use strong read"]
    FRESH -->|"Không"| STALE["Stale read với TimestampBound"]
    WRITE -->|"Có"| READFIRST{"Cần đọc trạng thái rồi quyết định ghi?"}
    READFIRST -->|"Có"| RW["Read-write transaction"]
    READFIRST -->|"Không"| BULK{"Cập nhật/xóa trên phạm vi lớn?"}
    BULK -->|"Có, có thể chia partition"| PDML["Partitioned DML"]
    BULK -->|"Không"| MUT["Mutation commit hoặc DML"]
~~~

Đây là hướng dẫn lựa chọn ban đầu. Cần kiểm tra thêm giới hạn engine, transaction semantics, tính idempotent và yêu cầu nghiệp vụ.

## 3. Strong read và stale read

### 3.1. Strong read

Strong read trả về dữ liệu đã commit mới nhất tại thời điểm đọc theo consistency guarantee của Spanner. Đây là lựa chọn mặc định an toàn khi nghiệp vụ cần dữ liệu mới nhất.

Ví dụ:

- Đọc trạng thái đơn hàng trước khi cho phép hủy.
- Kiểm tra tồn kho trước khi xác nhận một bước ghi.
- Đọc cấu hình điều khiển hành vi cần cập nhật ngay.
- Đọc dữ liệu vừa được ghi trong một request tiếp theo.

Strong read có thể cần chờ để đảm bảo dữ liệu nhất quán theo vị trí replica và timestamp. Latency phụ thuộc region, topology và tải. Không nên tự động thay strong read bằng stale read chỉ vì thấy một query chậm; trước tiên hãy kiểm tra index, số row đọc và vị trí workload.

### 3.2. Stale read

Stale read cho phép đọc snapshot tại một thời điểm trong quá khứ. Ứng dụng đánh đổi độ mới dữ liệu để có thể giảm thời gian chờ trong một số workload.

Ví dụ phù hợp:

- Dashboard số lượng đơn theo giờ.
- Trang phân tích không yêu cầu thấy thay đổi vừa commit.
- Báo cáo tổng hợp chấp nhận trễ vài giây.
- Cache refresh hoặc tác vụ đồng bộ có SLA độ mới rõ ràng.

Ví dụ không phù hợp nếu chưa có thiết kế bổ sung:

- Quyết định thanh toán.
- Trừ tồn kho.
- Chuyển trạng thái đơn cần chống cập nhật cạnh tranh.
- Kiểm tra quyền hoặc trạng thái bảo mật cần hiệu lực ngay.

Stale read không phải dữ liệu ngẫu nhiên hoặc không nhất quán. Nó là một snapshot nhất quán tại timestamp cũ hơn hiện tại.

### 3.3. TimestampBound

Cloud Spanner Java client biểu diễn read consistency bằng `TimestampBound`. Các lựa chọn quan trọng:

| Kiểu | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `TimestampBound.strong()` | Đọc dữ liệu mới nhất theo strong consistency | API nghiệp vụ thông thường |
| `TimestampBound.ofExactStaleness(n, unit)` | Đọc snapshot có độ cũ chính xác theo khoảng chỉ định | Cần tái lập snapshot với độ trễ đã định |
| `TimestampBound.ofMaxStaleness(n, unit)` | Cho phép snapshot cũ tối đa một khoảng; Spanner có thể chọn timestamp mới hơn | Dashboard cần giới hạn độ trễ nhưng ưu tiên latency |
| `TimestampBound.ofReadTimestamp(timestamp)` | Đọc tại một timestamp cụ thể | Nhiều service cần đọc cùng mốc snapshot |

Các phương thức trên là API của Cloud Spanner Java client. Chọn overload thời gian tương thích với phiên bản thư viện trong BOM của dự án.

### 3.4. Exact staleness và max staleness khác nhau

Giả sử ứng dụng đang chạy lúc 10:00 và đặt độ trễ 15 giây:

- Exact staleness yêu cầu snapshot tại thời điểm 09:59:45.
- Max staleness cho phép snapshot không cũ hơn 09:59:45; Spanner có thể dùng snapshot mới hơn nếu khả thi.

Exact staleness phù hợp khi cần cùng một mốc dữ liệu. Max staleness hữu ích khi chấp nhận snapshot mới hơn để tối ưu latency.

Không đặt khoảng stale quá lớn chỉ để giảm tải. Chọn độ trễ tối đa theo nghiệp vụ, ví dụ dashboard có thể chấp nhận 10 giây nhưng màn hình trạng thái thanh toán thì không.

### 3.5. Ví dụ single-use read với strong consistency

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.Key;
import com.google.cloud.spanner.ReadContext;
import com.google.cloud.spanner.TimestampBound;
import com.google.cloud.spanner.Struct;

import java.util.Arrays;

public String readOrderStatus(DatabaseClient databaseClient, String orderId) {
    ReadContext context = databaseClient.singleUse(TimestampBound.strong());

    Struct row = context.readRow(
            "Orders",
            Key.of(orderId),
            Arrays.asList("OrderId", "Status"));

    return row == null ? null : row.getString("Status");
}
~~~

Đọc theo primary key phù hợp khi đã biết chính xác khóa. Chỉ chọn các cột cần dùng để giảm dữ liệu truyền và mapping. Với code production, nên biểu diễn trường hợp không tồn tại bằng `Optional<String>` hoặc kiểu kết quả rõ ràng thay vì trả `null` nếu convention của service yêu cầu.

### 3.6. Ví dụ stale read cho dashboard

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.ReadContext;
import com.google.cloud.spanner.Statement;
import com.google.cloud.spanner.TimestampBound;
import com.google.cloud.spanner.ResultSet;

import java.util.concurrent.TimeUnit;

public long countRecentOrders(DatabaseClient databaseClient) {
    ReadContext context = databaseClient.singleUse(
            TimestampBound.ofMaxStaleness(15, TimeUnit.SECONDS));

    Statement statement = Statement.newBuilder(
            "SELECT COUNT(*) AS total " +
            "FROM Orders WHERE Status = @status")
        .bind("status").to("CONFIRMED")
        .build();

    try (ResultSet resultSet = context.executeQuery(statement)) {
        return resultSet.next() ? resultSet.getLong("total") : 0L;
    }
}
~~~

Dashboard có thể chấp nhận số liệu trễ tối đa 15 giây. Nếu yêu cầu báo cáo thay đổi, hãy điều chỉnh khoảng staleness theo SLA và kiểm thử latency thực tế.

## 4. Single-use read và read-only transaction

### 4.1. Single-use read

Single-use read thực hiện một lần đọc hoặc một query bằng một `TimestampBound`. Khi kết thúc thao tác, không giữ transaction để thực hiện nhiều truy vấn khác.

Dùng khi:

- Đọc một row theo primary key.
- Chạy một query độc lập.
- Mỗi endpoint chỉ cần một snapshot riêng.
- Không cần các query khác nhau nhìn cùng một trạng thái dữ liệu.

Nếu gọi hai single-use read liên tiếp, hai lần đọc có thể quan sát hai snapshot khác nhau. Đây không phải lỗi; đó là semantics của hai thao tác độc lập.

### 4.2. Read-only transaction

Read-only transaction cho phép thực hiện nhiều lần đọc trên cùng một snapshot. Đây là lựa chọn khi một response cần ghép nhiều query nhưng phải nhất quán tại một thời điểm.

Ví dụ, màn hình tổng quan đơn hàng đọc:

1. Thông tin order.
2. Danh sách order items.
3. Tổng số lần thanh toán.
4. Bản ghi audit mới nhất.

Nếu dùng bốn single-use read riêng biệt, dữ liệu có thể thay đổi giữa các lần đọc. Dùng một read-only transaction để các query cùng nhìn một snapshot.

### 4.3. Ví dụ read-only transaction

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.ReadOnlyTransaction;
import com.google.cloud.spanner.ResultSet;
import com.google.cloud.spanner.Statement;
import com.google.cloud.spanner.Struct;
import com.google.cloud.spanner.TimestampBound;

public OrderSummary loadSummary(DatabaseClient databaseClient, String orderId) {
    try (ReadOnlyTransaction transaction =
            databaseClient.readOnlyTransaction(TimestampBound.strong())) {

        Statement itemStatement = Statement.newBuilder(
                "SELECT ItemId, ProductId, Quantity " +
                "FROM OrderItems WHERE OrderId = @orderId")
            .bind("orderId").to(orderId)
            .build();

        Struct order = transaction.readRow(
                "Orders",
                com.google.cloud.spanner.Key.of(orderId),
                java.util.Arrays.asList("OrderId", "Status", "CustomerId"));

        if (order == null) {
            return null;
        }

        try (ResultSet items = transaction.executeQuery(itemStatement)) {
            // Map rows to the response DTO.
            while (items.next()) {
                String itemId = items.getString("ItemId");
                // Add item to the summary.
            }
        }

        return new OrderSummary(
                order.getString("OrderId"),
                order.getString("Status"),
                order.getString("CustomerId"));
    }
}
~~~

Đoạn code minh họa nhiều lần đọc trong cùng transaction. Phần mapping item vào DTO được rút gọn để tập trung vào snapshot semantics. Nếu DTO cần chứa item list, hãy thêm collection và map từng row trong vòng lặp.

### 4.4. Chọn timestamp cho snapshot

Có thể dùng `TimestampBound.ofReadTimestamp(timestamp)` để nhiều thao tác hoặc nhiều service đọc tại cùng một timestamp đã thống nhất. Đây là cách hữu ích cho báo cáo nhiều phần hoặc xử lý phân tán cần cùng mốc dữ liệu.

Timestamp phải là timestamp hợp lệ mà Spanner có thể phục vụ. Không tự tạo timestamp tương lai hoặc chọn timestamp tùy ý mà không có nguồn timestamp và chính sách retention phù hợp.

### 4.5. Khi nào không cần read-only transaction?

Không bọc một query đơn giản trong transaction nhiều thao tác nếu single-use read đã đủ. Read-only transaction cần lifecycle rõ ràng và phải đóng sau khi hoàn tất.

Tránh giữ transaction trong khi chờ người dùng, gọi HTTP service hoặc stream dữ liệu không giới hạn. Hãy đọc dữ liệu cần thiết, đóng transaction, rồi xử lý phần còn lại.

## 5. Read-write transaction

### 5.1. Khi nào cần?

Read-write transaction phù hợp khi kết quả ghi phụ thuộc vào dữ liệu vừa đọc và các thay đổi phải commit nguyên tử.

Ví dụ xác nhận đơn hàng:

1. Đọc trạng thái hiện tại.
2. Kiểm tra trạng thái là `PENDING`.
3. Đọc/kiểm tra điều kiện tồn kho.
4. Cập nhật trạng thái đơn.
5. Ghi audit hoặc thay đổi dữ liệu liên quan.
6. Commit tất cả thay đổi cùng nhau.

Nếu hai request cùng xác nhận một đơn, transaction semantics của Spanner giúp phát hiện xung đột và bảo đảm kết quả phù hợp với isolation/serializability của database.

### 5.2. Read-write transaction với Java client

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.Key;
import com.google.cloud.spanner.Mutation;
import com.google.cloud.spanner.Struct;

import java.util.Arrays;

public void confirmOrder(DatabaseClient databaseClient, String orderId) {
    databaseClient.readWriteTransaction().run(transaction -> {
        Struct order = transaction.readRow(
                "Orders",
                Key.of(orderId),
                Arrays.asList("OrderId", "Status"));

        if (order == null) {
            throw new IllegalArgumentException("Order not found");
        }

        if (!"PENDING".equals(order.getString("Status"))) {
            throw new IllegalStateException("Order is not pending");
        }

        Mutation update = Mutation.newUpdateBuilder("Orders")
                .set("OrderId").to(orderId)
                .set("Status").to("CONFIRMED")
                .build();

        transaction.buffer(update);
        return null;
    });
}
~~~

Transaction đọc trạng thái và buffer mutation trong cùng unit of work. Khi callback kết thúc thành công, client commit transaction. Nếu transaction bị abort do xung đột, client có thể chạy lại callback theo retry policy của thư viện.

Đây là ví dụ tối giản. Nghiệp vụ thực tế cần kiểm tra tồn kho, idempotency key và audit record trong cùng transaction nếu các dữ liệu đó cần atomicity.

### 5.3. Transaction có thể chạy lại

Spanner có thể abort một read-write transaction khi phát hiện xung đột hoặc điều kiện transient. Client library tự retry transaction theo cơ chế của nó.

Vì callback có thể được thực thi nhiều lần:

- Không gửi email bên trong callback.
- Không gọi payment gateway bên trong callback.
- Không publish message trực tiếp từ callback.
- Không tăng counter bên ngoài database theo cách không idempotent.
- Không sửa mutable state bên ngoài rồi giả định callback chỉ chạy một lần.

Chỉ đặt thao tác database và tính toán thuần trong callback. Ghi event/outbox trong cùng transaction, sau commit worker mới gửi message hoặc gọi hệ thống ngoài.

### 5.4. Ví dụ transaction với DML

Có thể thực hiện câu DML trong transaction khi muốn cập nhật theo điều kiện:

~~~java
import com.google.cloud.spanner.Statement;

long updatedRows = databaseClient.readWriteTransaction().run(transaction -> {
    Statement statement = Statement.newBuilder(
            "UPDATE Orders SET Status = @newStatus " +
            "WHERE OrderId = @orderId AND Status = @oldStatus")
        .bind("orderId").to(orderId)
        .bind("oldStatus").to("PENDING")
        .bind("newStatus").to("CONFIRMED")
        .build();

    return transaction.executeUpdate(statement);
});
~~~

Điều kiện `Status = @oldStatus` giúp thao tác chỉ cập nhật khi trạng thái vẫn là PENDING tại transaction. Giá trị row count giúp phát hiện trường hợp không có row phù hợp. Trong nghiệp vụ cần phân biệt không tìm thấy và sai trạng thái, có thể đọc row trong transaction rồi quyết định kết quả rõ ràng.

### 5.5. Không dùng read-write transaction cho mọi thao tác

Read-write transaction có chi phí điều phối, lock và khả năng abort/retry. Nếu chỉ ghi một nhóm row đã biết mà không cần đọc trước, mutation commit có thể phù hợp hơn.

Nếu chỉ đọc dữ liệu, dùng read context hoặc read-only transaction. Chọn transaction theo invariant nghiệp vụ thay vì bọc tất cả repository methods trong một transaction lớn.

## 6. Mutation, DML và Partitioned DML

### 6.1. Mutation commit

Mutation mô tả thay đổi row: insert, update, replace hoặc delete. Có thể gửi một nhóm mutation trong một commit:

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.Mutation;

import java.util.Arrays;
import java.util.List;

public void createOrderRows(DatabaseClient databaseClient, String orderId) {
    Mutation order = Mutation.newInsertBuilder("Orders")
            .set("OrderId").to(orderId)
            .set("Status").to("PENDING")
            .build();

    Mutation audit = Mutation.newInsertBuilder("OrderAudit")
            .set("OrderId").to(orderId)
            .set("Action").to("CREATED")
            .build();

    List<Mutation> mutations = Arrays.asList(order, audit);
    databaseClient.write(mutations);
}
~~~

Các mutation trong một commit được áp dụng nguyên tử. Cơ chế này phù hợp khi ứng dụng đã biết row cần ghi và không cần đọc dữ liệu hiện tại trước khi quyết định.

### 6.2. Mutation và DML khác nhau thế nào?

| Tiêu chí | Mutation | DML |
| --- | --- | --- |
| Mô tả | Thay đổi row cụ thể | Câu SQL INSERT/UPDATE/DELETE |
| Chọn row | Dựa trên primary key trong mutation | Dựa trên điều kiện SQL |
| Đọc/ghi trong transaction | Có thể buffer cùng read-write transaction | Có thể execute trong transaction |
| Dùng cho | Ghi row đã biết | Cập nhật theo predicate hoặc biểu thức |
| Tính năng SQL | Không phải SQL query | Dùng GoogleSQL DML |

Mutation thường rõ ràng và gọn khi đã có đầy đủ key/value. DML phù hợp khi điều kiện cập nhật được biểu đạt tự nhiên bằng SQL.

### 6.3. At-least-once mutation

Java client có API `writeAtLeastOnce` cho một số tình huống cần giảm overhead transaction. Semantics at-least-once nghĩa là ứng dụng phải chấp nhận mutation có thể được áp dụng lại khi có retry.

Chỉ dùng với thao tác idempotent. Ví dụ cập nhật một cột thành một giá trị cố định có thể idempotent; tăng số dư bằng phép cộng hoặc thêm bản ghi mới có thể tạo kết quả lặp nếu request được áp dụng nhiều lần.

Không dùng `writeAtLeastOnce` cho thanh toán, trừ tiền hoặc thao tác cộng dồn nếu chưa có thiết kế deduplication/unique key.

### 6.4. Batch DML

Batch DML cho phép chạy nhiều câu DML trong cùng read-write transaction. Các câu lệnh cùng transaction commit hoặc rollback cùng nhau.

Dùng khi một nghiệp vụ cần nhiều câu UPDATE/DELETE có quan hệ và muốn commit nguyên tử. Nếu batch có nhiều thao tác độc lập trên phạm vi lớn, hãy cân nhắc chia nhỏ hoặc dùng Partitioned DML nếu semantics cho phép.

### 6.5. Partitioned DML

Partitioned DML chia một câu DML phù hợp thành nhiều partition để xử lý trên quy mô lớn. Ví dụ cleanup bản ghi hết hạn:

~~~sql
DELETE FROM OrderAudit
WHERE CreatedAt < @cutoff;
~~~

Đây chỉ là SQL minh họa; câu lệnh thực tế cần dùng cú pháp/parameter được API hỗ trợ. Partitioned DML không phải một transaction nguyên tử bao trùm toàn bộ bảng. Các partition có thể commit riêng, nên lỗi giữa chừng có thể để lại một phần công việc đã hoàn thành.

Chỉ dùng khi:

- Tác vụ cập nhật/xóa có thể chia thành các partition độc lập.
- Không cần atomicity toàn bộ câu lệnh.
- Thao tác có thể chạy lại an toàn.
- Không phụ thuộc vào side effect bên ngoài trong lúc thực hiện.
- Đã kiểm tra giới hạn DML và execution behavior của phiên bản client.

Không dùng Partitioned DML cho quy trình thanh toán hoặc chuyển tiền cần nhiều thay đổi commit nguyên tử.

## 7. Spring Data Spanner và transaction boundary

### 7.1. Dùng @Transactional ở service layer

Với Spring Data Spanner, có thể đặt transaction ở service để bao trùm nhiều repository operation:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final OrderItemRepository itemRepository;

    public OrderApplicationService(
            OrderRepository orderRepository,
            OrderItemRepository itemRepository) {
        this.orderRepository = orderRepository;
        this.itemRepository = itemRepository;
    }

    @Transactional(transactionManager = "spannerTransactionManager")
    public void createOrder(Order order, List<OrderItem> items) {
        orderRepository.save(order);
        itemRepository.saveAll(items);
    }
}
~~~

Ví dụ giả định starter đã cấu hình Spanner transaction manager và repository tương ứng. Nếu ứng dụng chỉ có một transaction manager, có thể không cần chỉ định tên; nếu có thêm JPA/Cloud SQL, hãy chỉ định manager đúng để tránh transaction chạy trên datasource khác.

### 7.2. Transaction manager và native client

Spring transaction manager phù hợp với transaction boundary ở tầng service. Khi cần chọn `TimestampBound`, read timestamp hoặc API transaction đặc thù, có thể dùng Cloud Spanner Java client `DatabaseClient` trực tiếp.

Không mở một read-write transaction thủ công bên trong một method đã có `@Transactional` trên cùng database. Chọn một cơ chế quản lý transaction cho mỗi unit of work để tránh nested transaction hoặc transaction boundary khó dự đoán.

### 7.3. readOnly=true không phải stale read

`@Transactional(readOnly = true)` là metadata/hint ở tầng Spring. Không giả định annotation này tự chọn exact staleness, max staleness hoặc timestamp snapshot.

Nếu nghiệp vụ cần độ cũ dữ liệu cụ thể, hãy cấu hình `TimestampBound` qua Spanner client API hoặc cơ chế được phiên bản Spring Cloud GCP hỗ trợ rõ ràng. Ghi rõ SLA độ mới dữ liệu ở service/use case.

### 7.4. Isolation level và semantics Spanner

Spanner cung cấp transaction semantics mạnh và external consistency cho các transaction được commit. Không xem thuộc tính `isolation = READ_COMMITTED` hay `REPEATABLE_READ` như cách thay đổi tùy ý semantics nội bộ của Spanner theo mô hình JDBC thông thường.

Read-write transaction của Spanner có thể bị abort do contention. Read-only transaction cung cấp snapshot. Stale read là lựa chọn consistency/timestamp riêng. Thiết kế theo các semantics này thay vì cố ép Spanner hoạt động như một database JDBC truyền thống.

### 7.5. Không hỗ trợ nested transaction như JDBC savepoint

Không dựa vào nested transaction hoặc savepoint để chia nhỏ transaction Spanner. Nếu nghiệp vụ có nhiều bước độc lập, hãy chia thành nhiều transaction có trạng thái trung gian, idempotency key và cơ chế bù trừ phù hợp.

## 8. Chọn cách đọc theo use case

### 8.1. Ma trận lựa chọn

| Use case | Cách đọc đề xuất | Lý do |
| --- | --- | --- |
| Chi tiết đơn theo ID | Strong single-use key read | Một row, cần dữ liệu mới nhất |
| Danh sách đơn theo customer | Strong SQL query hoặc index phù hợp | Có filter/sort theo nhiều cột |
| Dashboard thống kê | Max staleness | Chấp nhận dữ liệu trễ trong SLA |
| Báo cáo đọc nhiều bảng | Read-only transaction | Các query cùng snapshot |
| Export tại một mốc dữ liệu | Read-only transaction với read timestamp cố định | Kết quả nhất quán qua nhiều query |
| Kiểm tra trạng thái rồi cập nhật | Read-write transaction | Đọc và ghi nguyên tử |
| API list phân trang | Query có index và keyset/cursor | Tránh offset lớn và thứ tự không ổn định |
| Cache refresh | Stale read nếu nghiệp vụ chấp nhận | Tối ưu độ trễ và tải |

### 8.2. Đọc theo primary key

Khi biết primary key đầy đủ, dùng read API hoặc repository `findById`. Đây thường là cách trực tiếp nhất để lấy một row.

Với composite key, phải truyền đầy đủ các thành phần theo đúng thứ tự. Không truy vấn bằng một phần composite key như thể đó là khóa đơn; nếu cần tìm theo prefix, dùng KeySet/range hoặc SQL query phù hợp.

### 8.3. Đọc theo KeySet hoặc key range

KeySet hữu ích khi đọc một tập key đã biết hoặc một range theo thứ tự primary key. Cách đọc này có thể giảm nhu cầu parse SQL cho use case key-based.

Không dùng KeySet để biểu đạt điều kiện theo cột không thuộc primary key. Với filter theo CustomerId, Status hoặc CreatedAt, cần secondary index hoặc SQL query.

### 8.4. SQL query và secondary index

Dùng SQL khi cần lọc, join, aggregate, sort hoặc projection. Đảm bảo query pattern được hỗ trợ bởi primary key hoặc secondary index phù hợp.

Ví dụ:

~~~sql
SELECT OrderId, Status, CreatedAt
FROM Orders
WHERE CustomerId = @customerId
ORDER BY CreatedAt DESC
LIMIT 50;
~~~

Nếu query cần filter theo CustomerId và sort CreatedAt, secondary index có key order tương ứng có thể giảm scan. Xem query plan và số row/byte đọc trước khi thêm index.

### 8.5. Pagination

Không dùng offset lớn cho bảng tăng trưởng nhanh nếu có thể dùng keyset pagination. Lưu cursor từ row cuối trang trước, sau đó truy vấn các row tiếp theo theo thứ tự key/index ổn định.

Ví dụ logic:

~~~sql
SELECT OrderId, CreatedAt, Status
FROM Orders
WHERE CustomerId = @customerId
  AND CreatedAt < @lastCreatedAt
ORDER BY CreatedAt DESC
LIMIT 50;
~~~

Nếu nhiều row có cùng CreatedAt, cần thêm tie-breaker ổn định như OrderId trong index và điều kiện cursor. Nếu dữ liệu thay đổi giữa các request trang, keyset pagination vẫn có thể thấy thay đổi mới; nếu cần snapshot nhất quán cho toàn bộ export, giữ một read-only transaction hoặc timestamp snapshot phù hợp và cân nhắc thời gian giữ snapshot.

### 8.6. Streaming kết quả

Với query trả về nhiều row, đọc theo stream/cursor và đóng `ResultSet` đúng cách. Tránh load toàn bộ bảng vào List khi không cần; giới hạn page size, projection và thời gian xử lý.

Không giữ read-only transaction trong khi gửi dữ liệu chậm tới client. Hãy đọc theo batch có giới hạn, đóng resource sớm và tiếp tục bằng cursor nếu use case cho phép.

## 9. Consistent snapshot và báo cáo nhiều bước

### 9.1. Vấn đề nhiều query khác snapshot

Giả sử báo cáo đọc tổng số đơn, tổng số item và tổng thanh toán. Nếu mỗi query là single-use read, một đơn hàng có thể chuyển trạng thái giữa các query. Báo cáo có thể cộng các phần dữ liệu không cùng một thời điểm.

Read-only transaction giải quyết vấn đề này bằng cách dùng một snapshot nhất quán cho các lần đọc trong transaction.

### 9.2. Read timestamp dùng chung

Nếu nhiều thành phần độc lập cần cùng một snapshot, hệ thống có thể truyền một read timestamp hợp lệ và dùng `TimestampBound.ofReadTimestamp(timestamp)` ở từng reader.

Cần kiểm soát:

- Nguồn timestamp được tạo từ Spanner hoặc quy trình snapshot đã thống nhất.
- Tất cả query dùng cùng timestamp.
- Timestamp còn nằm trong phạm vi Spanner có thể phục vụ.
- Các service không tự chọn timestamp khác nhau rồi tuyên bố cùng snapshot.

### 9.3. Export dài và giới hạn vòng đời

Không giữ một transaction mở quá lâu chỉ để tạo file export lớn. Transaction kéo dài làm tăng thời gian giữ session/tài nguyên và có thể ảnh hưởng vận hành.

Với export dài, cân nhắc:
- Chọn read timestamp cố định.
- Chia dữ liệu theo primary key range.
- Ghi cursor/checkpoint để resume.
- Giới hạn số worker đồng thời.
- Đo read throughput và chi phí.
- Xác định chính sách nếu timestamp snapshot không còn khả dụng.

## 10. Transaction contention, abort và retry

### 10.1. Vì sao transaction bị abort?

Các read-write transaction có thể xung đột khi nhiều request đồng thời đọc/ghi cùng dữ liệu hoặc các key range liên quan. Spanner có thể abort một transaction để duy trì consistency.

Dấu hiệu thường gặp:
- Lỗi transaction aborted hoặc status `ABORTED`.
- Retry count tăng.
- Latency tăng khi tải đồng thời.
- Nhiều request cập nhật cùng một row/counter.
- Transaction dài, đọc nhiều rồi mới ghi.

### 10.2. Giảm contention

- Giữ transaction ngắn.
- Chỉ đọc các row cần thiết.
- Thiết kế primary key phân phối ghi hợp lý.
- Tránh một row counter trở thành điểm ghi nóng.
- Gộp thao tác có liên quan vào một transaction ngắn.
- Tách batch lớn thành phần việc độc lập khi nghiệp vụ cho phép.
- Dùng optimistic application logic có version/condition phù hợp.

### 10.3. Retry an toàn

Client library có retry cho read-write transaction. Ứng dụng nên:
- Giữ callback deterministic và có thể chạy lại.
- Không thực hiện I/O ngoài database trong callback.
- Không tạo ID hoặc side effect ngoài theo cách thay đổi kết quả giữa lần retry nếu ID phải ổn định.
- Dùng idempotency key cho request nghiệp vụ.
- Log số lần retry, latency và lỗi cuối cùng.
- Đặt deadline/time budget cho request.

### 10.4. Outbox pattern

Nếu transaction phải cập nhật đơn hàng và phát sự kiện, ghi một outbox row trong cùng transaction:

~~~java
databaseClient.readWriteTransaction().run(transaction -> {
    transaction.buffer(
        Mutation.newUpdateBuilder("Orders")
            .set("OrderId").to(orderId)
            .set("Status").to("CONFIRMED")
            .build());

    transaction.buffer(
        Mutation.newInsertBuilder("Outbox")
            .set("EventId").to(eventId)
            .set("AggregateId").to(orderId)
            .set("EventType").to("ORDER_CONFIRMED")
            .build());

    return null;
});
~~~

Worker riêng đọc outbox, publish message và đánh dấu đã xử lý bằng idempotency/deduplication. Cần thiết kế worker để chịu được publish lặp hoặc crash sau publish nhưng trước khi cập nhật trạng thái.

## 11. Kiểm thử transaction và consistency

### 11.1. Kiểm thử trên Spanner Emulator

Emulator hữu ích để kiểm tra:
- Cú pháp SQL và parameter binding cơ bản.
- Insert/update/delete.
- Mapping repository/template.
- Transaction commit/rollback.
- Logic retry và xử lý lỗi ở tầng ứng dụng.
- Read-only transaction trong một số kịch bản được emulator hỗ trợ.

Emulator không mô phỏng đầy đủ latency đa vùng, contention ở quy mô production, IAM, quota, hiệu năng index và mọi consistency/performance behavior. Không dùng kết quả emulator để kết luận capacity production.

### 11.2. Test cases nên có

| Test | Kỳ vọng |
| --- | --- |
| Strong read sau commit | Thấy dữ liệu đã commit |
| Stale read với max staleness | Kết quả có thể cũ trong giới hạn cấu hình |
| Hai query trong read-only transaction | Cùng snapshot |
| Read-write transaction commit | Mọi thay đổi liên quan cùng xuất hiện |
| Exception trước commit | Không có thay đổi chưa commit |
| Transaction abort/retry | Callback chạy lại mà không lặp side effect |
| Mutation commit | Nhóm mutation được commit cùng nhau |
| Partitioned DML | Không giả định toàn câu lệnh atomic |
| Keyset pagination | Không lặp/bỏ row khi thứ tự và cursor được thiết kế đúng |
| IAM/network integration | Runtime principal và network path thật hoạt động |

### 11.3. Kiểm thử cạnh tranh

Tạo hai request cùng cố cập nhật trạng thái một đơn. Xác minh chỉ một request có thể chuyển trạng thái từ PENDING sang CONFIRMED theo invariant. Request còn lại nhận kết quả conflict/business state phù hợp, không ghi đè dữ liệu đã xác nhận.

Không chỉ test một request đơn lẻ; transaction correctness chỉ lộ rõ khi có concurrency.

### 11.4. Kiểm thử stale-read SLA

Với dashboard, đo:
- Độ trễ dữ liệu thực tế.
- Query latency.
- Tỷ lệ query dùng stale timestamp.
- Mức chênh số liệu so với strong read.
- Hành vi khi traffic tăng.

Đặt giới hạn staleness theo yêu cầu sản phẩm. Nếu người dùng cần số liệu cập nhật tức thời, stale read không còn là tối ưu phù hợp.

## 12. Quan sát và vận hành

### 12.1. Metrics

Theo dõi:
- Query latency p50/p95/p99.
- Read bytes/rows và query plan.
- Read/write throughput.
- Transaction abort/retry count.
- Commit latency.
- Session pool usage/exhaustion.
- Partitioned DML progress và affected rows.
- Error rate theo status code và operation type.

Kết hợp metric ứng dụng với Cloud Monitoring/Spanner metrics để xác định bottleneck ở query, transaction contention, session pool hay hạ tầng.

### 12.2. Log có ích

Ghi:
- Operation name/use case.
- Request/correlation ID.
- Query category hoặc statement identifier.
- Read mode (strong/stale) và staleness bound.
- Transaction duration và retry count.
- Error code/status.
- Số row trả về hoặc bị ảnh hưởng nếu an toàn.

Không log giá trị parameter nhạy cảm, access token, service account key hoặc toàn bộ payload khách hàng.

### 12.3. Cảnh báo

- Transaction abort tăng đột biến.
- P95 commit latency vượt SLA.
- Query scan/read bytes tăng sau release.
- Session pool cạn.
- Partitioned DML lỗi hoặc tiến độ không tăng.
- Stale-read age vượt ngưỡng nghiệp vụ.
- Strong read latency tăng theo region/traffic.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Đọc thấy dữ liệu cũ | Đang dùng stale read hoặc timestamp cũ | Kiểm tra TimestampBound/read timestamp |
| Báo cáo các bảng lệch nhau | Nhiều single-use read độc lập | Dùng read-only transaction hoặc timestamp chung |
| Transaction aborted | Contention, transaction dài hoặc key nóng | Rút ngắn transaction, thiết kế key và retry an toàn |
| Gửi email lặp sau retry | Side effect nằm trong transaction callback | Dùng outbox và worker idempotent |
| Update không thay đổi row | Predicate DML không khớp trạng thái hiện tại | Kiểm tra row count và business state |
| Partitioned DML chạy dở | Một số partition đã commit trước lỗi | Thiết kế thao tác idempotent và khả năng resume |
| Read query chậm | Thiếu index hoặc đọc quá nhiều cột/row | Xem query plan, projection và index |
| Export làm session pool cạn | Giữ transaction/session quá lâu hoặc concurrency quá cao | Chia range, giới hạn worker, đóng resource sớm |
| Kết quả pagination trùng/lọt row | Sort không ổn định hoặc cursor thiếu tie-breaker | Dùng thứ tự duy nhất và keyset cursor |
| Transaction manager không đúng | Ứng dụng có nhiều transaction manager | Chỉ định Spanner transaction manager đúng |

## 14. Bài tập thực hành

### Bài A — Strong read và stale read

Tạo đơn hàng rồi đọc trạng thái bằng strong read. Thực hiện thay đổi trạng thái và thử đọc bằng max staleness 10 giây. So sánh độ mới và latency, giải thích use case nào chấp nhận stale read.

### Bài B — Single-use và read-only snapshot

Viết hai query độc lập đọc Orders và OrderItems bằng single-use read. Tạo thay đổi đồng thời giữa hai query để quan sát khả năng khác snapshot. Sau đó dùng read-only transaction và so sánh kết quả.

### Bài C — Read-write transaction

Viết service chuyển trạng thái đơn từ PENDING sang CONFIRMED. Hai request chạy đồng thời; xác minh chỉ một request thành công theo invariant. Ghi audit row trong cùng transaction.

### Bài D — Mutation và DML

Tạo hai row đã biết bằng mutation commit. Sau đó cập nhật nhiều row theo predicate bằng DML. So sánh code, row count và khả năng đọc dữ liệu trước khi ghi.

### Bài E — Partitioned DML

Tạo bảng audit test với dữ liệu hết hạn. Chạy Partitioned DML để cleanup. Cố ý dừng job trong sandbox và thiết kế cách chạy lại mà không gây sai dữ liệu.

### Bài F — Outbox và retry

Tạo transaction cập nhật Orders và insert Outbox. Giả lập callback bị retry; xác minh không publish message từ bên trong transaction và worker xử lý event idempotent.

### Bài G — Snapshot export

Chọn một read timestamp và chạy nhiều query trong các reader dùng chung timestamp. Kiểm tra báo cáo nhìn cùng snapshot và thiết kế checkpoint để export có thể resume.

### Câu hỏi tự kiểm tra

1. Strong read khác stale read ở điểm nào?
2. Exact staleness và max staleness khác nhau như thế nào?
3. Khi nào nên dùng single-use read?
4. Vì sao nhiều query độc lập có thể nhìn thấy snapshot khác nhau?
5. Read-only transaction giải quyết vấn đề gì?
6. Khi nào cần read timestamp dùng chung giữa nhiều service?
7. Vì sao thao tác đọc rồi ghi cần read-write transaction?
8. Spanner có thể abort transaction trong trường hợp nào?
9. Vì sao transaction callback phải an toàn khi chạy lại?
10. Mutation khác DML ở cách xác định row cần thay đổi như thế nào?
11. Khi nào Partitioned DML phù hợp và vì sao nó không atomic trên toàn câu lệnh?
12. Khi nào nên đọc theo primary key, KeySet hoặc SQL query?
13. Vì sao keyset pagination cần tie-breaker ổn định?
14. Vì sao không nên giữ read-only transaction trong lúc stream dữ liệu chậm cho client?
15. `@Transactional(readOnly = true)` có tự chọn stale timestamp không?
16. Làm thế nào tránh gửi email hoặc publish message lặp khi transaction retry?
17. Emulator có thể xác minh những gì và không thay thế được kiểm thử nào?
18. Metric nào giúp phát hiện transaction contention và query scan tăng?

**Kết quả mong đợi:** người học lựa chọn đúng read consistency và transaction type cho từng use case, dùng single-use/read-only/read-write transaction, mutation và DML đúng semantics, thiết kế stale read có SLA, xử lý abort/retry an toàn, và kiểm thử được tính nhất quán của dữ liệu trong ứng dụng Spring Boot tích hợp Cloud Spanner.

## Tài liệu tham khảo

- [Spanner transactions](https://docs.cloud.google.com/spanner/docs/transactions)
- [Read data with Spanner](https://docs.cloud.google.com/spanner/docs/reads)
- [Read data using SQL](https://docs.cloud.google.com/spanner/docs/query-data-sql)
- [Spanner read consistency](https://docs.cloud.google.com/spanner/docs/reads#read_consistency)
- [Mutations and commits](https://docs.cloud.google.com/spanner/docs/modify-mutation-api)
- [Partitioned DML](https://docs.cloud.google.com/spanner/docs/dml-partitioned)
- [Spring Framework on Google Cloud reference](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/)


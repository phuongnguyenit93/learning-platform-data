# Writer xử lý partial failure

Trong Spring Batch, `ItemWriter` nhận một nhóm item của chunk và ghi kết quả đến đích như database, file hoặc message broker. Một tình huống khó xử lý là **partial failure**: writer đã ghi được một phần item nhưng gặp lỗi trước khi hoàn tất toàn bộ chunk.

Cách khôi phục phụ thuộc vào nơi writer ghi dữ liệu và transaction có bao phủ thao tác đó hay không. Nếu mọi thao tác ghi cùng tham gia một transaction, rollback có thể hoàn tác toàn bộ chunk. Nếu writer ghi ra hệ thống bên ngoài transaction, một phần dữ liệu có thể đã tồn tại dù Step báo lỗi. Khi đó, retry có thể tạo dữ liệu trùng hoặc làm kết quả không nhất quán.

Thiết kế writer cần xác định rõ ranh giới transaction, cách xử lý exception, khả năng retry/skip và tính idempotent của thao tác ghi. Không nên giả định Spring Batch có thể tự hoàn tác mọi side effect mà writer đã thực hiện.

## 1. Partial failure trong ItemWriter là gì?

Trong chunk-oriented processing, Spring Batch gom các item, xử lý chúng rồi gọi `ItemWriter` để ghi kết quả. Ví dụ, commit interval là 100 nên writer nhận một chunk gồm 100 đơn hàng.

Giả sử writer ghi tuần tự từng đơn hàng:

```text
Chunk gồm 100 đơn hàng
       |
       +--> Ghi order 1..40 thành công
       |
       +--> Ghi order 41 gặp lỗi
       |
       +--> Writer ném exception
```

Writer đã thực hiện một phần công việc trước khi lỗi xảy ra. Kết quả cuối cùng phụ thuộc vào cách các thao tác ghi được quản lý:

- Nếu 40 thao tác ghi tham gia cùng transaction với Step, transaction có thể rollback và hủy cả 40 thay đổi.
- Nếu mỗi thao tác đã commit riêng, hoặc dữ liệu được gửi đến hệ thống không hỗ trợ rollback, 40 thay đổi đầu có thể vẫn còn.
- Nếu writer bắt exception rồi trả về bình thường, Spring Batch có thể coi lần ghi chunk đã thành công và commit transaction, dù chỉ một phần item được ghi.

Vì vậy, partial failure không chỉ là exception. Đó là tình huống trạng thái thực tế của đích ghi có thể không khớp với trạng thái mà Spring Batch ghi nhận cho chunk.

## 2. ItemWriter được gọi trong transaction của chunk

Với chunk-oriented Step, Spring Batch thường thực hiện đọc, xử lý và ghi trong ranh giới transaction của chunk. Khi writer ném exception làm chunk thất bại, transaction manager rollback transaction hiện tại theo cấu hình.

Ví dụ cấu hình Step:

```java
@Bean
public Step writeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("writeOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

`chunk(100, transactionManager)` xác định transaction manager mà Step sử dụng cho chunk. Để rollback có tác dụng với dữ liệu writer ghi, các thao tác ghi phải tham gia transaction đó. Ví dụ, `JdbcTemplate` dùng cùng `DataSource` được transaction manager quản lý thường tham gia transaction hiện tại thông qua cơ chế transaction synchronization của Spring.

### Ví dụ ghi database cùng transaction

```java
public class JdbcOrderWriter implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            jdbcTemplate.update(
                    "insert into imported_order(order_id, amount) values (?, ?)",
                    order.getId(),
                    order.getAmount()
            );
        }
    }
}
```

Nếu thao tác insert thứ 41 ném exception và mọi insert dùng cùng transaction, các insert trước đó trong chunk cũng được rollback. Khi đó, lần chạy lại chunk không tạo ra bản ghi trùng từ 40 insert đã rollback.

Điều này chỉ đúng khi các thao tác thực sự tham gia cùng transaction. Nếu repository mở transaction `REQUIRES_NEW` cho từng item, writer gọi một datasource khác, hoặc tự commit connection, các thay đổi đó có thể tồn tại sau khi transaction của chunk rollback.

## 3. Khi rollback không thể hoàn tác partial write

Transaction của database không tự động bao phủ mọi loại đích ghi. Các ví dụ sau thường cần chiến lược riêng:

| Đích ghi | Khả năng rollback từ transaction của Step | Rủi ro khi writer thất bại giữa chừng |
|---|---|---|
| Database cùng transaction manager | Có thể rollback toàn bộ thay đổi trong transaction | Thấp hơn nếu mọi thao tác cùng transaction và không có commit độc lập |
| File hoặc object storage | Không tự động rollback theo transaction database | File có thể chứa một phần dữ liệu hoặc đã được publish |
| HTTP API hoặc dịch vụ bên ngoài | Không tự động rollback lời gọi đã được dịch vụ chấp nhận | Gửi lại có thể tạo giao dịch hoặc bản ghi trùng |
| Message broker | Phụ thuộc transaction của broker và cách tích hợp | Một phần message có thể đã được publish |
| Nhiều database hoặc nhiều resource | Chỉ atomic nếu có cơ chế transaction phối hợp phù hợp | Một resource commit trong khi resource khác rollback |

Ví dụ, writer gửi 40 message thành công lên broker rồi message thứ 41 gặp lỗi. Transaction database của Step rollback không thể thu hồi 40 message đã được broker nhận, trừ khi writer và broker được tích hợp với cơ chế transaction có khả năng rollback phù hợp.

Tương tự, writer gọi một API tạo hóa đơn cho từng item. Nếu API đã tạo 40 hóa đơn rồi request thứ 41 thất bại, retry toàn chunk có thể gửi lại 40 request trước. Nếu API không hỗ trợ idempotency, kết quả có thể là hóa đơn trùng.

## 4. Không nuốt exception sau khi ghi một phần

Một lỗi nguy hiểm là writer bắt exception, ghi log rồi tiếp tục hoặc kết thúc method bình thường:

```java
@Override
public void write(Chunk<? extends Order> chunk) {
    for (Order order : chunk) {
        try {
            externalClient.send(order);
        } catch (RuntimeException ex) {
            log.error("Could not send order {}", order.getId(), ex);
            // Trả về bình thường dù item chưa được gửi.
        }
    }
}
```

Vì method kết thúc bình thường, Spring Batch có thể xem lần ghi chunk thành công. Framework không biết item nào đã thất bại nếu writer không báo lỗi hoặc trả kết quả riêng theo một contract do ứng dụng thiết kế. Step có thể hoàn tất với dữ liệu bị thiếu.

Nếu lỗi phải làm chunk thất bại, hãy để exception được truyền ra ngoài writer hoặc bọc nó trong exception phù hợp:

```java
@Override
public void write(Chunk<? extends Order> chunk) {
    for (Order order : chunk) {
        try {
            externalClient.send(order);
        } catch (ExternalServiceException ex) {
            throw new ItemWriteFailureException(
                    "Failed to send order " + order.getId(), ex
            );
        }
    }
}
```

Nếu nghiệp vụ cho phép một số item thất bại nhưng vẫn tiếp tục, hãy biểu diễn kết quả thành công/thất bại một cách tường minh, lưu danh sách lỗi hoặc dùng skip policy phù hợp. Không nên biến lỗi thành thành công bằng cách bỏ qua exception.

## 5. Retry và nguy cơ ghi trùng

Retry hữu ích với lỗi tạm thời như deadlock, lock contention hoặc dịch vụ bên ngoài mất kết nối trong thời gian ngắn. Nhưng nếu writer đã ghi một phần dữ liệu trước khi ném exception, retry có thể gọi lại writer với item đã được xử lý ở lần trước.

Trong database transaction được rollback toàn bộ, retry chunk thường có thể ghi lại an toàn vì những thay đổi của lần trước đã bị hủy. Với side effect không rollback được, writer cần idempotent để cùng một item được gửi nhiều lần vẫn tạo ra một kết quả nghiệp vụ duy nhất.

### Thiết kế writer idempotent

Một thao tác ghi là idempotent khi thực hiện lặp lại với cùng định danh nghiệp vụ không tạo thêm hiệu ứng ngoài ý muốn. Một số cách thường dùng:

- Dùng business key ổn định và unique constraint ở database.
- Dùng `UPSERT` hoặc thao tác cập nhật theo khóa nghiệp vụ thay vì insert mù trong trường hợp phù hợp.
- Gửi idempotency key đến API bên ngoài nếu dịch vụ hỗ trợ.
- Lưu trạng thái gửi và kết quả theo từng item để có thể đối soát.
- Đặt request ID hoặc message ID ổn định để consumer phát hiện message trùng.

Ví dụ, API nhận lệnh tạo hóa đơn có thể nhận `orderId` làm idempotency key. Khi writer gửi lại cùng `orderId`, dịch vụ trả về kết quả của giao dịch đã tạo trước đó thay vì tạo hóa đơn mới. Khả năng này phải được API đích hỗ trợ; chỉ gửi một header tùy ý không tự tạo ra idempotency.

### Cấu hình retry có giới hạn

Với lỗi transient trong writer, có thể cấu hình retry ở Step:

```java
return new StepBuilder("writeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Retry cần có giới hạn và chỉ áp dụng cho lỗi có khả năng tự phục hồi. Không nên retry vô hạn một lỗi dữ liệu không hợp lệ hoặc một lỗi cấu hình cố định. Nếu writer ghi đến hệ thống ngoài transaction, cần bảo đảm thao tác retry an toàn trước khi bật retry.

## 6. Skip khi một item không thể ghi

Skip phù hợp với lỗi thuộc về một item và được nghiệp vụ cho phép bỏ qua, chẳng hạn dữ liệu vi phạm một quy tắc cụ thể. Khi writer ném exception và Step được cấu hình write-skip, Spring Batch có thể rollback chunk rồi thực hiện các bước xử lý bổ sung để xác định item gây lỗi và bỏ qua theo skip policy.

Ví dụ cấu hình:

```java
return new StepBuilder("writeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
```

Khi xử lý write-skip, framework có thể gọi writer lại với tập item nhỏ hơn hoặc từng item để xác định phần tử gây lỗi. Chi tiết đường đi phụ thuộc loại lỗi và cơ chế fault-tolerance của phiên bản Spring Batch. Vì vậy, writer phải chịu được việc được gọi lại và không tạo side effect trùng.

Không nên skip lỗi hạ tầng như database unavailable, hết connection hoặc broker ngừng hoạt động. Những lỗi này thường ảnh hưởng đến nhiều item và cần retry có giới hạn, dừng Step hoặc khôi phục hạ tầng. Skip chỉ nên dùng khi bỏ qua item là một quyết định nghiệp vụ được chấp nhận và được ghi nhận.

## 7. Phân biệt retry, skip và rollback

| Cơ chế | Mục tiêu | Hành vi chính |
|---|---|---|
| Rollback | Đưa resource có transaction về trạng thái trước chunk | Hủy thay đổi chưa commit trong transaction đó |
| Retry | Thử lại thao tác có khả năng thành công sau lỗi tạm thời | Gọi lại xử lý hoặc ghi theo cơ chế fault-tolerance |
| Skip | Bỏ qua item lỗi được cho phép | Tiếp tục với các item khác và ghi nhận skip |
| Restart | Tiếp tục JobInstance sau khi execution thất bại/dừng | Tạo JobExecution mới và khôi phục checkpoint đã lưu |

Các cơ chế có thể kết hợp. Ví dụ, một lỗi ghi tạm thời có thể làm chunk rollback rồi retry. Một lỗi dữ liệu không thể khắc phục có thể làm rollback chunk và sau đó được skip nếu cấu hình cho phép. Nếu retry vượt giới hạn hoặc lỗi không được skip, Step có thể kết thúc `FAILED`.

Rollback chỉ tác động đến resource tham gia transaction. Nó không xóa một HTTP request đã được xử lý, không thu hồi một email đã gửi và không tự xóa file đã được publish.

## 8. Ghi file và xử lý partial failure

File writer có thể gặp lỗi giữa lúc ghi chunk do hết dung lượng, lỗi I/O hoặc process bị dừng. Khi đó file có thể chứa một phần nội dung của chunk. Transaction database của Step không thể tự hoàn tác byte đã ghi xuống file.

Với file output, hãy dùng writer tích hợp sẵn của Spring Batch khi phù hợp, vì các implementation như `FlatFileItemWriter` hỗ trợ `ItemStream` và cơ chế lưu trạng thái để phục vụ restart. Cần đặt tên writer ổn định, cấu hình `saveState` phù hợp và giữ quy tắc append/overwrite nhất quán với chiến lược restart.

Với custom file writer, cần thiết kế rõ:

- Vị trí hoặc byte offset đã commit được lưu vào ExecutionContext.
- `open()` khôi phục vị trí và kiểm tra file hiện tại có đúng file của lần chạy trước không.
- `update()` ghi checkpoint tại thời điểm framework yêu cầu.
- `close()` giải phóng stream và tài nguyên.
- Khi rollback hoặc restart, writer có thể cắt bỏ phần chưa commit hoặc tạo lại file theo một quy trình an toàn.

Một chiến lược phổ biến là ghi vào file tạm theo execution hoặc business key, hoàn tất và xác nhận file sau khi Job thành công, rồi mới publish/rename thành file chính thức. Nếu file đích đã tồn tại, cần quy định rõ ghi đè, version hóa hay từ chối. Không nên để consumer đọc một file đang được ghi dở.

## 9. Gửi message hoặc gọi API từ writer

Ghi message hoặc gọi API thường là side effect ngoài transaction của database. Nếu writer gửi nhiều message rồi gặp lỗi, các message đã được broker nhận có thể không bị thu hồi khi chunk rollback.

Các hướng thiết kế:

**Transactional producer:** dùng transaction của broker nếu broker hỗ trợ, để nhóm message có thể commit hoặc abort cùng nhau trong phạm vi transaction của broker. Điều này không tự động làm transaction database và broker trở thành một transaction duy nhất.

**Idempotent consumer hoặc API:** gắn ID ổn định cho từng message/request; bên nhận lưu ID đã xử lý và loại bỏ yêu cầu lặp. Đây là lựa chọn hữu ích khi retry có thể gửi lại item.

**Outbox pattern:** writer ghi dữ liệu nghiệp vụ và bản ghi outbox vào cùng transaction database. Một publisher riêng đọc outbox và gửi message; publisher đánh dấu trạng thái gửi hoặc retry theo một định danh ổn định. Consumer vẫn nên idempotent vì message có thể được gửi lại nếu publisher gặp lỗi sau khi broker nhận message nhưng trước khi cập nhật trạng thái outbox.

Ví dụ mô hình outbox:

```text
Chunk transaction
       |
       +--> Ghi order vào bảng orders
       |
       +--> Ghi event vào bảng outbox
       |
       +--> Commit cả hai thay đổi

Publisher riêng
       |
       +--> Đọc event chưa gửi trong outbox
       +--> Publish message có eventId ổn định
       +--> Cập nhật trạng thái gửi
```

Outbox giúp tránh tình huống database đã commit order nhưng ứng dụng dừng trước khi gửi event. Nó không biến việc gửi message thành exactly-once tuyệt đối; cần thiết kế xử lý trùng ở consumer hoặc broker.

## 10. Listener và quan sát lỗi ghi

`ItemWriteListener` cung cấp callback để ghi nhận hoạt động của writer:

| Callback | Thời điểm và mục đích |
|---|---|
| `beforeWrite` | Trước khi writer ghi chunk |
| `afterWrite` | Sau khi lời gọi writer hoàn tất bình thường |
| `onWriteError` | Khi lời gọi writer ném exception |

Ví dụ listener:

```java
public class OrderWriteListener implements ItemWriteListener<Order> {

    @Override
    public void beforeWrite(Chunk<? extends Order> items) {
        log.info("Writing {} orders", items.size());
    }

    @Override
    public void afterWrite(Chunk<? extends Order> items) {
        log.info("Writer call completed for {} orders", items.size());
    }

    @Override
    public void onWriteError(Exception exception,
                             Chunk<? extends Order> items) {
        log.error("Writer failed for chunk of {} orders", items.size(), exception);
    }
}
```

`afterWrite` cho biết lời gọi writer kết thúc bình thường; nó không tự chứng minh transaction của chunk đã commit. Một lỗi ở bước sau trong chunk có thể làm transaction rollback dù callback này đã được gọi. Vì vậy, log hoặc metric trong listener nên mô tả đúng sự kiện, ví dụ “writer call succeeded”, thay vì khẳng định dữ liệu đã commit.

Để quan sát kết quả cuối cùng, kết hợp listener với trạng thái `StepExecution`, counter đọc/ghi/skip/rollback và metadata sau khi Step kết thúc. Tránh gửi thông báo thành công không thể thu hồi từ `afterWrite` nếu transaction chưa commit.

## 11. Chiến lược xử lý partial failure theo loại đích ghi

| Đích ghi | Chiến lược ưu tiên | Điều cần tránh |
|---|---|---|
| Database trong cùng transaction | Để exception truyền ra; rollback toàn chunk; retry transient có giới hạn | Commit riêng từng item nếu muốn atomic theo chunk |
| Database với nhiều transaction manager | Xác định rõ resource nào cùng transaction; cân nhắc outbox hoặc transaction phối hợp | Giả định rollback của một manager hoàn tác database khác |
| File | Dùng writer có hỗ trợ state hoặc file tạm rồi publish khi hoàn tất | Cho consumer đọc file đang ghi dở |
| HTTP API | Idempotency key, lưu kết quả theo item, retry có giới hạn | Gửi lại request không có khóa chống trùng |
| Message broker | Transaction của broker, outbox và consumer idempotent | Giả định rollback database thu hồi message đã publish |

Một lựa chọn khác là chia writer thành các bước: ghi dữ liệu vào staging trước, xác nhận số lượng và tính hợp lệ, sau đó promote sang bảng hoặc vị trí chính thức. Staging giúp điều tra và chạy lại phần chưa hoàn tất dễ hơn, đặc biệt khi đích ghi không hỗ trợ transaction chung với Spring Batch.

## 12. Những nhầm lẫn thường gặp

**Cho rằng exception luôn hoàn tác mọi item đã ghi.** Rollback chỉ hoàn tác thay đổi trong resource tham gia transaction. Side effect bên ngoài vẫn có thể tồn tại.

**Bắt exception rồi bỏ qua.** Spring Batch có thể xem writer thành công và commit chunk dù một số item chưa được ghi. Hãy truyền exception hoặc biểu diễn kết quả thất bại rõ ràng.

**Bật retry mà không kiểm tra idempotency.** Writer có thể được gọi lại sau khi đã tạo side effect. Cần bảo đảm ghi lặp không tạo dữ liệu trùng.

**Dùng skip cho lỗi hạ tầng.** Database hoặc broker ngừng hoạt động không phải lỗi riêng của một item. Dừng hoặc retry theo chính sách phù hợp thay vì âm thầm bỏ dữ liệu.

**Coi `afterWrite` là sau commit.** Callback xác nhận lời gọi writer thành công, không xác nhận transaction chunk đã commit.

**Tách transaction cho từng item nhưng kỳ vọng atomic theo chunk.** Nếu từng item commit độc lập, lỗi ở item sau không thể rollback các item trước bằng transaction chunk.

## 13. Cách thiết kế writer có khả năng phục hồi

Trước khi triển khai writer, hãy xác định đích ghi có tham gia transaction của Step hay không. Với database trong cùng transaction, để exception làm rollback chunk và chỉ retry các lỗi transient. Với file, API hoặc broker, thiết kế checkpoint, idempotency key, outbox hoặc quy trình staging để xử lý phần đã ghi trước khi lỗi.

Writer nên có hành vi rõ ràng khi không thể ghi toàn bộ chunk: báo exception phù hợp, để Spring Batch áp dụng rollback/retry/skip theo cấu hình, và cung cấp log đủ để xác định item hoặc chunk gặp lỗi. Thiết kế như vậy giúp hệ thống phục hồi sau partial failure mà không âm thầm mất dữ liệu hoặc tạo hiệu ứng trùng khi chạy lại.

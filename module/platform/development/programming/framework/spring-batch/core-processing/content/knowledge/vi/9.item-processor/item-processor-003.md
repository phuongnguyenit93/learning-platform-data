# Processor ném exception khi item sai

Trong chunk-oriented processing, `ItemProcessor` nhận từng item từ reader để kiểm tra, chuẩn hóa hoặc chuyển đổi trước khi writer ghi dữ liệu. Khi một item vi phạm quy tắc nghiệp vụ, processor có thể ném exception để báo rằng item không thể được xử lý theo hợp đồng hiện tại.

Spring Batch xem exception phát sinh trong processor là lỗi của bước xử lý item. Tùy cấu hình fault tolerance, exception có thể làm chunk thất bại, được retry hoặc được xem là một item bị skip. Vì vậy, cần chọn loại exception và chính sách xử lý phù hợp với ý nghĩa lỗi.

Điểm quan trọng là phân biệt dữ liệu không hợp lệ có thể loại bỏ với lỗi hệ thống cần dừng job. Nếu skip quá rộng, batch có thể hoàn thành nhưng âm thầm bỏ mất dữ liệu quan trọng. Nếu mọi lỗi dữ liệu đều làm job dừng, một vài bản ghi xấu có thể ngăn cả lô dữ liệu được xử lý.

## 1. Khi nào processor nên ném exception?

Processor nên ném exception khi không thể tạo ra một item đầu ra hợp lệ từ item đầu vào theo quy tắc đã xác định. Ví dụ:

- Thiếu mã định danh bắt buộc của đơn hàng.
- Số lượng hoặc giá trị tiền tệ nằm ngoài miền nghiệp vụ cho phép.
- Trạng thái nguồn không được hỗ trợ.
- Dữ liệu tham chiếu bắt buộc không tồn tại.
- Một điều kiện nghiệp vụ khiến item không thể được chuyển đổi an toàn.

Ví dụ processor kiểm tra đơn hàng:

```java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

@Bean
ItemProcessor<OrderRow, Order> orderProcessor() {
    return row -> {
        if (row.orderId() == null || row.orderId().isBlank()) {
            throw new InvalidOrderException("Order ID is required");
        }

        if (row.quantity() <= 0) {
            throw new InvalidOrderException(
                "Quantity must be greater than zero for " + row.orderId());
        }

        return new Order(
            row.orderId().trim(),
            row.productCode().trim(),
            row.quantity()
        );
    };
}
```

Khi điều kiện không hợp lệ được phát hiện, processor ném `InvalidOrderException`. Item đó không được chuyển tới writer trong lần xử lý này. Step sẽ áp dụng chính sách exception đã cấu hình để quyết định tiếp tục, retry, skip hay thất bại.

## 2. Chọn exception theo ý nghĩa lỗi

Nên tạo exception nghiệp vụ có tên cụ thể thay vì ném `RuntimeException` chung cho mọi tình huống. Loại exception là đầu vào để Spring Batch phân loại lỗi và áp dụng skip hoặc retry.

| Loại lỗi | Ví dụ | Hướng xử lý thường phù hợp |
|---|---|---|
| Dữ liệu không hợp lệ, có thể loại bỏ | Thiếu trường bắt buộc, quantity âm | Skip có giới hạn và ghi nhận item lỗi |
| Lỗi nghiệp vụ cần xử lý thủ công | Mã khách hàng không tồn tại, trạng thái không được phép | Tùy yêu cầu: skip có audit hoặc dừng job |
| Lỗi tạm thời của hạ tầng | Timeout, deadlock, dịch vụ tham chiếu tạm thời không khả dụng | Retry có giới hạn |
| Lỗi cấu hình hoặc hợp đồng hệ thống | Sai schema, thiếu cấu hình bắt buộc, mapping sai hàng loạt | Thường dừng job để điều tra |

Không nên dùng một exception cho cả lỗi validation và lỗi kết nối. Nếu tất cả đều là `RuntimeException` chung, cấu hình skip/retry khó phân biệt trường hợp nào an toàn để tiếp tục.

Ví dụ định nghĩa exception riêng:

```java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

public class ReferenceServiceUnavailableException extends RuntimeException {
    public ReferenceServiceUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

`InvalidOrderException` có thể đại diện cho dữ liệu không hợp lệ, còn `ReferenceServiceUnavailableException` biểu diễn lỗi tạm thời khi gọi dịch vụ tham chiếu. Hai loại lỗi có thể được cấu hình khác nhau.

## 3. Mặc định: exception làm step thất bại

Nếu step không khai báo chính sách skip hoặc retry phù hợp, exception không được xử lý trong processor sẽ làm step thất bại. Chunk hiện tại không hoàn tất như một chunk thành công; transaction được rollback theo cấu hình transaction của step.

Ví dụ flow cơ bản:

```text
Reader -> Processor -> Writer
                 |
                 +-- exception
                       |
                       v
                 Chunk rollback
                       |
                       v
                  Step FAILED
```

Đây thường là hành vi an toàn khi lỗi cho thấy dữ liệu hoặc cấu hình không thể được xử lý đáng tin cậy. Job dừng để người vận hành điều tra và sửa nguyên nhân trước khi restart.

Khi một exception xảy ra trong processor, writer không nhận item bị lỗi. Các item khác trong cùng chunk có thể đã được đọc hoặc xử lý trước khi lỗi được phát hiện, nhưng transaction chunk chưa commit sẽ được rollback. Với reader có trạng thái, Spring Batch có thể khôi phục checkpoint theo cơ chế restart.

## 4. Cho phép skip item không hợp lệ

Khi một loại lỗi dữ liệu được xác định là có thể bỏ qua, có thể cấu hình fault tolerance và skip policy cho exception đó.

Ví dụ theo API builder của Spring Batch 5:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> orderReader,
        ItemProcessor<OrderRow, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
}
```

Trong ví dụ này, `InvalidOrderException` được xem là lỗi có thể skip. Step có thể tiếp tục xử lý các item còn lại miễn là số skip chưa vượt giới hạn. Những exception khác không nằm trong skip policy vẫn có thể làm step thất bại.

### Skip limit được tính như thế nào?

`skipLimit(n)` đặt giới hạn tổng số item được phép skip trong step execution. Giới hạn này được tính chung cho lỗi ở các giai đoạn đọc, xử lý và ghi, không phải một hạn mức độc lập cho từng giai đoạn.

Ví dụ `skipLimit(50)` cho phép tối đa 50 lần skip theo chính sách. Khi phát sinh lần skip vượt quá giới hạn, step thất bại. Giới hạn hữu ích để một file có quá nhiều bản ghi lỗi không bị xử lý như một batch thành công bình thường.

Không nên đặt skip limit quá lớn chỉ để job luôn hoàn thành. Nếu 40% dữ liệu bị loại, đó có thể là dấu hiệu file nguồn sai định dạng, mapping thay đổi hoặc lỗi upstream ảnh hưởng hàng loạt. Nên theo dõi cả số lượng và tỷ lệ item bị skip.

## 5. Chỉ skip exception cụ thể

Chính sách skip nên allow-list những exception thật sự đại diện cho item có thể loại bỏ. Tránh cấu hình skip mọi exception:

```java
// Không nên: có thể che giấu lỗi lập trình và lỗi hạ tầng
.faultTolerant()
.skip(Exception.class)
.skipLimit(100000)
```

Cấu hình rộng có thể biến lỗi kết nối database, lỗi cấu hình, lỗi lập trình hoặc lỗi hợp đồng dữ liệu thành các item bị bỏ qua. Job có thể báo hoàn thành dù kết quả nghiệp vụ không đáng tin cậy.

Thay vào đó, khai báo loại lỗi nghiệp vụ cụ thể:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skip(MissingOptionalReferenceException.class)
.noSkip(CriticalBatchConfigurationException.class)
.skipLimit(50)
```

`noSkip` có thể dùng để loại trừ một exception khỏi chính sách skip tổng quát. Nếu có thể, hãy tránh khai báo skip quá rộng ngay từ đầu để cấu hình dễ hiểu hơn. Đặc biệt, lỗi schema, cấu hình hoặc lỗi hệ thống không nên bị bỏ qua chỉ vì chúng được bọc trong một exception chung.

## 6. Phân biệt ném exception với filter bằng null

Processor có hai cách phổ biến để không gửi item tới writer, nhưng ý nghĩa khác nhau:

| Cách xử lý | Ý nghĩa | Có tính là skip? |
|---|---|---|
| Trả về `null` | Chủ động filter item theo quy tắc nghiệp vụ | Không |
| Ném exception được skip policy chấp nhận | Item lỗi được loại bỏ theo chính sách fault tolerance | Có |
| Ném exception không được skip | Lỗi làm step thất bại | Không được xem là skip thành công |

Ví dụ filter:

```java
ItemProcessor<OrderRow, Order> processor = row -> {
    if (row.isCancelled()) {
        return null; // Bỏ qua có chủ đích
    }
    return convert(row);
};
```

Ví dụ skip:

```java
ItemProcessor<OrderRow, Order> processor = row -> {
    if (row.quantity() <= 0) {
        throw new InvalidOrderException("Invalid quantity");
    }
    return convert(row);
};
```

Filter thường dành cho trường hợp item không thuộc tập dữ liệu cần xử lý nhưng vẫn hợp lệ theo quy tắc, chẳng hạn đơn đã hủy hoặc bản ghi không nằm trong phạm vi báo cáo. Skip dành cho item không thể xử lý do lỗi được cho phép loại bỏ và cần được thống kê hoặc audit.

Không nên trả `null` để che giấu lỗi validation. Khi đó số liệu skip không phản ánh các bản ghi lỗi và người vận hành khó phân biệt dữ liệu được lọc hợp lệ với dữ liệu bị loại vì sai.

## 7. Ghi nhận item bị skip bằng SkipListener

Khi cần lưu lại bản ghi bị loại, có thể dùng `SkipListener`. Với lỗi trong processor, callback phù hợp là `onSkipInProcess(item, throwable)`.

```java
public class OrderSkipListener implements SkipListener<OrderRow, Order> {

    private static final Logger log =
        LoggerFactory.getLogger(OrderSkipListener.class);

    @Override
    public void onSkipInProcess(OrderRow item, Throwable error) {
        log.warn("Skipping order {}: {}", item.orderId(), error.getMessage());
    }

    @Override
    public void onSkipInRead(Throwable error) {
        log.warn("Skipping unreadable input: {}", error.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable error) {
        log.warn("Skipping order {} during write: {}", item.orderId(), error.getMessage());
    }
}
```

Đăng ký listener trong step:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(50)
.listener(orderSkipListener)
```

`onSkipInProcess` nhận item đầu vào của processor, ở đây là `OrderRow`. `onSkipInWrite` nhận item đầu ra `Order`. Điều này giúp phân biệt dữ liệu nguồn lỗi với lỗi phát sinh khi ghi dữ liệu đích.

Listener hữu ích để ghi log, metric hoặc lưu thông tin reject. Nếu listener ghi vào database hay gọi dịch vụ bên ngoài, cần thiết kế transaction và idempotency cẩn thận. Không nên để lỗi trong cơ chế ghi reject làm mất khả năng xử lý chính của job hoặc tạo side effect trùng khi retry/restart.

Với dữ liệu lỗi cần được xử lý lại, có thể ghi một reject record gồm mã nguồn, số dòng, khóa nghiệp vụ, loại exception và lý do. Tránh lưu toàn bộ payload nhạy cảm nếu không cần thiết; áp dụng chính sách bảo vệ dữ liệu tương ứng.

## 8. Retry dành cho lỗi tạm thời

Skip và retry giải quyết hai tình huống khác nhau. Skip loại item ra khỏi pipeline; retry thử lại thao tác có khả năng thành công nếu lỗi tạm thời biến mất.

Ví dụ processor gọi dịch vụ tra cứu địa chỉ. Timeout có thể chỉ là lỗi tạm thời, trong khi địa chỉ sai định dạng là lỗi dữ liệu không thể sửa bằng cách thử lại.

```java
return new StepBuilder("enrichOrders", jobRepository)
    .<OrderRow, EnrichedOrder>chunk(100, transactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderWriter)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(50)
    .build();
```

Đoạn code minh họa retry có giới hạn cho lỗi tạm thời và skip cho lỗi dữ liệu cụ thể. Hãy phân loại exception rõ ràng; không cấu hình cùng một lỗi vừa retry vừa skip nếu chưa xác định chính xác hành vi mong muốn khi hết số lần retry.

Retry có thể khiến processor được gọi lại cho cùng một item. Vì vậy, processor nên tránh side effect không idempotent. Nếu processor ghi dữ liệu hoặc gọi API bên ngoài, lần thử lại có thể thực hiện thao tác đó nhiều lần.

## 9. Chunk rollback và hành vi khi skip

Trong chunk processing, các item được đọc và xử lý trước khi writer ghi nhóm item đầu ra trong transaction của step. Khi processor ném exception, Spring Batch có thể rollback chunk rồi áp dụng retry/skip theo cấu hình fault tolerance.

```text
Chunk bắt đầu
  read A -> process A -> hợp lệ
  read B -> process B -> InvalidOrderException
                         |
                         v
              rollback / recovery
                         |
                         v
              phân loại exception
                  /          \
               skip          fail
                |              |
                v              v
       tiếp tục item sau   Step FAILED
```

Chi tiết số lần reader/processor được gọi lại phụ thuộc vào reader, transaction, retry/skip policy và cơ chế recovery của step. Không nên giả định một item luôn chỉ được đọc hoặc xử lý đúng một lần.

Khi exception được skip, item lỗi không được đưa vào writer. Các item hợp lệ còn lại có thể được ghi trong những chunk tiếp theo. Nếu skip limit bị vượt hoặc exception không được phép skip, step kết thúc thất bại.

## 10. Lỗi phát sinh ở reader khác với lỗi trong processor

Không phải mọi lỗi dữ liệu đều xảy ra trong processor. Ví dụ dòng CSV không thể parse thành số có thể phát sinh ngay trong reader. Khi đó exception được phân loại là lỗi read, không phải lỗi process.

| Giai đoạn | Ví dụ | Callback skip tương ứng |
|---|---|---|
| Read | Dòng CSV lỗi định dạng khi parse | `onSkipInRead(Throwable)` |
| Process | Quantity bằng 0 hoặc thiếu mã nghiệp vụ | `onSkipInProcess(item, Throwable)` |
| Write | Vi phạm constraint khi ghi bản ghi đầu ra | `onSkipInWrite(item, Throwable)` |

Chọn đúng giai đoạn giúp log và audit chỉ ra nguồn gốc lỗi. Nếu parser ném exception trong reader, thêm skip policy cho exception đó nếu muốn bỏ qua dòng lỗi. Không nên chuyển mọi lỗi đọc thành lỗi processor chỉ để gom xử lý vào một nơi.

## 11. Không skip lỗi diện rộng hoặc lỗi hợp đồng

Có những lỗi nhìn bề ngoài xuất hiện trên từng item nhưng thực chất phản ánh vấn đề toàn hệ thống. Ví dụ:

- Tất cả bản ghi đều thiếu một cột vì file nguồn đã đổi schema.
- Dịch vụ tham chiếu trả lỗi xác thực do credential hết hạn.
- Mapping mới đọc sai timezone cho toàn bộ dữ liệu.
- Writer không thể kết nối database.
- Một thay đổi code khiến mọi item bị ném cùng một exception.

Những trường hợp này thường cần dừng job thay vì skip từng item. Nếu tiếp tục, job có thể tạo ra một kết quả hoàn thành với phần lớn dữ liệu bị loại hoặc thiếu.

Có thể đặt ngưỡng skip theo cả số lượng và tỷ lệ bằng custom `SkipPolicy` nếu yêu cầu nghiệp vụ cần giới hạn tỷ lệ lỗi. Với chính sách tỷ lệ, cần xác định cách tính mẫu số, vì số item đã đọc có thể thay đổi và skip ở read/process/write có ý nghĩa khác nhau.

## 12. Những lỗi thường gặp khi cấu hình processor exception

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Ném `RuntimeException` chung cho mọi lỗi | Khó phân biệt dữ liệu sai với lỗi hệ thống | Dùng exception theo miền lỗi cụ thể |
| Không cấu hình skip nhưng kỳ vọng job tự bỏ qua | Step thất bại ngay khi exception thoát khỏi processor | Khai báo skip policy có giới hạn nếu nghiệp vụ cho phép |
| Skip `Exception.class` | Có thể che giấu lỗi hệ thống hoặc lỗi lập trình | Chỉ skip các exception dữ liệu đã xác định |
| Dùng `null` để báo lỗi | Item bị filter và không được thống kê như skip | Ném exception hoặc trả kiểu kết quả rõ ràng |
| Đặt skip limit quá cao | Job có thể hoàn thành với dữ liệu thiếu đáng kể | Chọn ngưỡng theo chất lượng dữ liệu và cảnh báo tỷ lệ lỗi |
| Không ghi nhận item bị skip | Không thể điều tra hoặc sửa dữ liệu lỗi | Dùng SkipListener, log và reject store phù hợp |
| Retry lỗi validation không thể tự hết | Tốn thời gian và tải mà không cải thiện kết quả | Chỉ retry lỗi có khả năng tạm thời |
| Processor có side effect không idempotent | Retry có thể lặp thao tác | Chuyển side effect sang writer hoặc dùng idempotency/outbox |

## 13. Quy trình chọn cách xử lý exception

Khi processor phát hiện một item sai, hãy quyết định theo các bước:

1. Xác định lỗi là lỗi dữ liệu của riêng item hay lỗi hạ tầng/hợp đồng ảnh hưởng nhiều item.
2. Nếu item không thuộc phạm vi xử lý nhưng vẫn hợp lệ, cân nhắc trả về `null` để filter.
3. Nếu item không hợp lệ và được phép loại bỏ, ném exception nghiệp vụ cụ thể và cấu hình skip limit.
4. Nếu lỗi có thể tạm thời biến mất, cấu hình retry có giới hạn cho exception tương ứng.
5. Nếu lỗi nghiêm trọng hoặc vượt ngưỡng chất lượng, để step thất bại và yêu cầu điều tra.
6. Ghi nhận item bị skip, nguyên nhân và số lượng; không để dữ liệu lỗi biến mất âm thầm.
7. Bảo đảm processor an toàn khi được gọi lại và writer có thể xử lý retry/restart theo quy tắc idempotent.

## Kết luận

Processor ném exception khi item không thể được chuyển đổi an toàn theo hợp đồng dữ liệu. Nếu không có chính sách fault tolerance phù hợp, exception làm step thất bại. Khi lỗi đại diện cho một item có thể loại bỏ, cấu hình skip cho exception cụ thể với giới hạn hợp lý và dùng `SkipListener` để ghi nhận. Với lỗi tạm thời, dùng retry có giới hạn; với lỗi hệ thống hoặc lỗi hợp đồng diện rộng, nên dừng job để điều tra.

Phân biệt exception với filter bằng `null`, chọn đúng loại exception và bảo đảm processor không tạo side effect lặp sẽ giúp batch xử lý dữ liệu lỗi có kiểm soát mà vẫn giữ được tính đúng đắn khi retry hoặc restart.

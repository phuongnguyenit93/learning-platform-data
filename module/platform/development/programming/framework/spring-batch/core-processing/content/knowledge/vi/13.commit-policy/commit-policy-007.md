# Commit nhỏ giảm rollback scope

Trong chunk-oriented processing, Spring Batch gom nhiều item thành một chunk và xử lý chunk đó trong một transaction. Khi writer và các tài nguyên nghiệp vụ tham gia cùng transaction, các thay đổi trong chunk được commit cùng nhau. Nếu một lỗi làm transaction rollback, các thay đổi chưa commit của chunk hiện tại được hoàn tác.

`commit interval` (thường cũng được gọi là chunk size) quyết định số item reader cần đọc để hình thành một chunk trước khi Spring Batch ghi và commit. Chọn chunk nhỏ làm giảm số item nằm trong một transaction, từ đó thu hẹp phạm vi dữ liệu có thể bị rollback khi lỗi xảy ra. Đổi lại, hệ thống phải thực hiện nhiều transaction và commit hơn.

## 1. Chunk và commit boundary

Một chunk là một đơn vị xử lý gồm các item được đọc, xử lý và ghi trong cùng một transaction của step. Khi chunk hoàn tất thành công, transaction được commit. Sau đó step tiếp tục với chunk kế tiếp.

```text
Chunk 1: read -> process -> write -> COMMIT
Chunk 2: read -> process -> write -> COMMIT
Chunk 3: read -> process -> write -> COMMIT
                         |
                         +-- nếu lỗi trước commit: ROLLBACK chunk 3
```

Ví dụ commit interval bằng 100:

- Spring Batch đọc và xử lý một nhóm tối đa 100 item cho chunk.
- Writer ghi các item đầu ra của chunk.
- Nếu xử lý thành công, transaction commit.
- Step tiếp tục với nhóm item kế tiếp.

Các chunk đã commit là những đơn vị giao dịch riêng. Nếu chunk 8 thất bại, những thay đổi đã commit ở chunk 1 đến chunk 7 thường vẫn tồn tại. Spring Batch không mở một transaction duy nhất bao trùm toàn bộ job để hoàn tác tất cả dữ liệu đã ghi từ đầu.

## 2. Commit interval điều khiển kích thước transaction

Trong Spring Batch 5, commit interval được khai báo trên chunk builder:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(50, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

Với giá trị `50`, step thường xử lý tối đa 50 item đầu vào cho một chunk trước khi ghi và commit. Chunk cuối có thể nhỏ hơn nếu nguồn dữ liệu đã hết. Nếu processor filter item bằng cách trả về `null`, writer nhận ít item hơn số item reader đã đọc.

Không nên hiểu commit interval là số dòng chắc chắn được writer ghi trong mỗi lần gọi. Đây là kích thước nhóm item đầu vào mà chunk provider thu thập; filter, skip và chunk cuối có thể làm số item đầu ra nhỏ hơn.

## 3. Vì sao chunk nhỏ thu hẹp phạm vi rollback?

Giả sử một job nhập 1.000 đơn hàng. So sánh hai cấu hình:

| Cấu hình | Số chunk ước tính | Số item tối đa trong một chunk |
|---|---:|---:|
| Commit interval = 1.000 | 1 | 1.000 |
| Commit interval = 100 | 10 | 100 |
| Commit interval = 20 | 50 | 20 |

Giả sử lỗi xảy ra khi xử lý chunk cuối cùng:

```text
Commit interval = 1000
  [ 1.000 item đang trong một transaction ]
  lỗi trước commit -> rollback tối đa toàn bộ chunk

Commit interval = 100
  [100] COMMIT [100] COMMIT ... [100 đang xử lý]
                                         lỗi -> rollback chunk hiện tại
```

Với chunk nhỏ, ít item hơn nằm trong transaction chưa commit. Vì vậy, lượng dữ liệu cần rollback hoặc xử lý lại thường giảm. Các chunk trước đã commit không bị rollback chỉ vì chunk sau gặp lỗi.

Điều này hữu ích khi:

- Writer thực hiện nhiều thao tác database trong một chunk.
- Một item lỗi có thể làm cả chunk hiện tại rollback.
- Transaction dài giữ lock hoặc connection lâu.
- Chi phí xử lý lại chunk sau lỗi lớn.
- Cần checkpoint thường xuyên hơn để restart từ tiến độ gần nhất đã commit.

## 4. Ví dụ lỗi giữa một batch lớn

Giả sử writer ghi 100 đơn hàng trong một transaction. Nó ghi được một số bản ghi rồi gặp lỗi constraint ở item thứ 80. Nếu exception làm transaction rollback, các thay đổi database thuộc transaction đó sẽ bị hoàn tác, kể cả những lệnh insert đã chạy thành công trước khi lỗi xảy ra.

Với commit interval 100, tối đa 100 item đầu vào của chunk hiện tại thuộc phạm vi transaction đang rollback. Với commit interval 10, lỗi ở chunk chứa item 71–80 chỉ ảnh hưởng đến transaction của nhóm đó; các chunk 1–10 đến 61–70 đã commit trước đó vẫn được giữ lại.

| Thời điểm lỗi | Commit interval 100 | Commit interval 10 |
|---|---|---|
| Chunk hiện tại | Item 1–100 | Item 71–80 |
| Thay đổi trong transaction hiện tại | Rollback theo transaction | Rollback theo transaction |
| Chunk trước đã commit | Không có trong ví dụ | Item 1–70 vẫn đã commit |
| Khối lượng cần xử lý lại khi restart | Có thể lên đến 100 item | Thường tối đa 10 item trong chunk hiện tại |

Đây là minh họa cho database transaction cục bộ. Nếu writer đã gọi API ngoài hoặc ghi sang hệ thống không tham gia transaction, side effect bên ngoài có thể không rollback. Chunk nhỏ không tự bảo đảm các thao tác ngoài database được hoàn tác.

## 5. Commit nhỏ và checkpoint/restart

Ở ranh giới chunk, Spring Batch có thể lưu metadata và trạng thái cần thiết cho restart thông qua `JobRepository` và `ExecutionContext`. Khi một chunk commit thành công, tiến độ đã commit có thể được dùng làm điểm tiếp tục nếu execution sau đó thất bại.

```text
Chunk 1 -> xử lý -> commit + checkpoint
Chunk 2 -> xử lý -> commit + checkpoint
Chunk 3 -> xử lý -> lỗi trước commit

Restart cùng JobInstance:
  khôi phục trạng thái đã commit ở chunk 2
  tiếp tục phần việc từ checkpoint tương ứng
```

Chunk nhỏ thường tạo checkpoint thường xuyên hơn. Khi job thất bại, phần công việc chưa commit có thể được thực hiện lại từ checkpoint gần nhất thay vì phải xử lý lại một nhóm lớn hơn.

Khả năng restart chính xác phụ thuộc reader/writer có lưu trạng thái, JobRepository có metadata bền vững, transaction manager và cách các tài nguyên được phối hợp. Một reader không lưu trạng thái hoặc một side effect ngoài transaction có thể cần chiến lược phục hồi riêng.

Không nên chỉ giảm chunk size rồi cho rằng restart đã an toàn. Cần xác định dữ liệu nào đã commit, trạng thái reader nào được lưu và thao tác nào có thể bị gọi lại.

## 6. Đổi lại: nhiều transaction hơn

Chunk nhỏ làm tăng số lần bắt đầu và commit transaction. Mỗi transaction có chi phí điều phối, ghi log, đồng bộ và cập nhật metadata. Nếu chunk quá nhỏ, overhead có thể chiếm phần đáng kể thời gian chạy.

Ví dụ với 10.000 item:

| Commit interval | Số chunk ước tính | Đặc điểm chính |
|---:|---:|---|
| 1 | 10.000 | Transaction rất ngắn nhưng overhead lớn |
| 10 | 1.000 | Rollback scope nhỏ, số commit tăng |
| 100 | 100 | Cân bằng trong nhiều workload |
| 1.000 | 10 | Ít commit hơn nhưng transaction lớn hơn |

Các con số chỉ minh họa số chunk khi không có filter/skip và nguồn có đủ item. Giá trị phù hợp phụ thuộc vào thời gian xử lý mỗi item, database, writer và tải đồng thời.

## 7. Ảnh hưởng tới lock, connection và bộ nhớ

Transaction dài có thể giữ lock lâu hơn, giữ connection lâu hơn và làm tăng khả năng contention với các giao dịch khác. Chunk nhỏ thường rút ngắn thời gian một transaction, giúp giảm thời gian giữ tài nguyên và thu hẹp phạm vi rollback.

Chunk nhỏ cũng thường giữ ít item trong bộ nhớ hơn. Tuy nhiên, tổng mức sử dụng bộ nhớ còn phụ thuộc vào reader, processor, writer, cache và các đối tượng tham chiếu được giữ lại.

Không có bảo đảm rằng giảm commit interval luôn làm throughput tăng. Nếu bottleneck là network, API ngoài, CPU hoặc truy vấn kém hiệu quả, thay đổi chunk size có thể không giải quyết nguyên nhân chính. Cần đo thời gian xử lý, thời gian commit, lock wait và connection usage để lựa chọn.

## 8. Commit interval và processor filter/skip

Chunk được hình thành dựa trên item đầu vào, nhưng writer chỉ nhận những item còn lại sau processor và chính sách skip.

Ví dụ commit interval là 5:

```text
Reader:      A  B  C  D  E
Processor:   A  B  null D  E
Writer:      [A, B, D, E]
Commit:      transaction của chunk hoàn tất
```

Nếu processor trả về `null`, item được filter và không được gửi tới writer. Nếu processor ném exception được skip policy chấp nhận, item đó cũng không được ghi. Trong cả hai trường hợp, writer có thể nhận chunk ít hơn commit interval.

Vì vậy, commit interval không phải giới hạn chính xác số bản ghi ghi thành công. Khi đo chất lượng dữ liệu, hãy theo dõi read count, write count, filter count và skip count riêng.

## 9. Chọn commit interval theo workload

Không có một giá trị chunk size phù hợp cho mọi job. Hãy cân nhắc các yếu tố sau:

1. **Chi phí mỗi item:** processor nặng hoặc writer thực hiện nhiều câu SQL có thể cần chunk nhỏ hơn để giới hạn thời gian transaction.
2. **Khả năng batch của writer:** JDBC batch writer thường tận dụng tốt nhóm item lớn hơn, nhưng cần cân bằng với lock và rollback scope.
3. **Transaction timeout:** chunk phải hoàn thành trong thời gian cho phép của transaction manager và database.
4. **Lock contention:** nếu job tranh chấp bảng với ứng dụng online, chunk nhỏ có thể giúp rút ngắn thời gian giữ lock.
5. **Bộ nhớ:** item lớn hoặc processor tạo object lớn có thể yêu cầu chunk nhỏ để giới hạn memory footprint.
6. **Restart và lỗi:** nếu chi phí xử lý lại cao, checkpoint thường xuyên hơn có thể hữu ích.
7. **Throughput:** transaction/commit quá thường xuyên có thể làm giảm tốc độ tổng thể.
8. **Tải đồng thời:** nhiều step hoặc partition chạy cùng lúc có thể làm tăng tổng số transaction và áp lực lên database.

Có thể bắt đầu với một giá trị vừa phải, chẳng hạn 50 hoặc 100, rồi đo trên dữ liệu gần với production. Đây chỉ là điểm khởi đầu để benchmark, không phải quy tắc bắt buộc.

## 10. Khi nào nên dùng chunk rất nhỏ?

Commit interval nhỏ, thậm chí bằng 1, có thể phù hợp khi:

- Mỗi item là một đơn vị ghi độc lập và cần commit ngay sau khi xử lý.
- Thời gian xử lý mỗi item dài và không muốn giữ transaction cho nhiều item.
- Một item có khả năng gây lỗi cao và chi phí rollback nhóm lớn là đáng kể.
- Tài nguyên database có contention cao và cần transaction ngắn.
- Yêu cầu vận hành ưu tiên khả năng phục hồi chi tiết hơn hiệu năng tối đa.

Tuy nhiên, commit interval bằng 1 có nghĩa một transaction cho mỗi item. Với hàng triệu bản ghi, số transaction lớn có thể làm giảm hiệu năng đáng kể. Nếu có thể, hãy dùng chunk lớn hơn và xử lý lỗi bằng skip/retry phù hợp.

## 11. Khi nào chunk lớn phù hợp hơn?

Chunk lớn có thể phù hợp khi:

- Database và writer xử lý batch hiệu quả.
- Mỗi item nhẹ và transaction hoàn thành nhanh.
- Không có nhiều giao dịch online tranh chấp tài nguyên.
- Overhead transaction/commit đang là bottleneck.
- Hệ thống có đủ bộ nhớ và transaction timeout đủ rộng.

Chunk lớn làm giảm số lần commit và thường cải thiện throughput cho thao tác batch database. Tuy nhiên, transaction kéo dài hơn, có thể giữ lock lâu hơn và khi rollback sẽ phải xử lý lại nhiều item hơn.

## 12. Commit nhỏ không thay thế idempotency

Các chunk trước đã commit vẫn tồn tại khi chunk sau thất bại. Khi restart, job tiếp tục từ checkpoint nếu reader hỗ trợ. Nhưng với side effect ngoài transaction, một item có thể đã được xử lý ở hệ thống ngoài dù transaction database của chunk rollback.

Ví dụ writer gọi API giao hàng cho 10 đơn hàng, API đã nhận 6 đơn rồi request bị timeout. Database transaction rollback không thể hủy 6 yêu cầu đã được hệ thống giao hàng chấp nhận. Khi retry, writer có thể gửi lại những yêu cầu đó.

Để xử lý an toàn:

- Dùng idempotency key theo mã đơn hàng hoặc mã nghiệp vụ.
- Ghi yêu cầu ra outbox trong transaction database rồi phát đi sau commit.
- Thiết kế API đích có khả năng nhận biết request trùng.
- Đối soát trạng thái sau timeout trước khi gửi lại.

Chunk nhỏ giúp giảm phạm vi rollback của transaction mà nó quản lý. Nó không biến toàn bộ pipeline thành exactly-once và không tự rollback side effect bên ngoài.

## 13. Mối quan hệ với skip, retry và rollback

Khi bật fault tolerance, Spring Batch có thể rollback chunk để thử lại hoặc xác định item gây lỗi. Kích thước chunk ảnh hưởng đến số item nằm trong đơn vị xử lý cần recovery.

- **Retry:** lỗi tạm thời có thể khiến thao tác được thử lại. Chunk nhỏ thường giới hạn số item liên quan đến lần recovery, nhưng số lần gọi lại cụ thể còn phụ thuộc retry policy và reader/writer.
- **Skip:** item lỗi được loại khỏi pipeline theo skip policy. Writer nhận các item còn lại; skip limit vẫn cần được thiết lập hợp lý.
- **Rollback:** các thay đổi trong transaction chunk chưa commit được hoàn tác nếu tài nguyên tham gia transaction đó.
- **Restart:** execution mới có thể tiếp tục từ checkpoint đã commit của JobInstance nếu metadata và state được lưu phù hợp.

Không nên bắt exception trong writer rồi bỏ qua chỉ để tránh rollback. Làm vậy có thể khiến Spring Batch coi chunk đã thành công dù dữ liệu chưa được ghi đầy đủ.

## 14. Transaction timeout và commit interval

Transaction timeout giới hạn thời gian transaction có thể tồn tại theo cấu hình của transaction manager và database. Chunk quá lớn hoặc processor/writer chậm có thể khiến transaction vượt timeout.

Có thể cấu hình timeout trên step:

```java
return new StepBuilder("importOrders", jobRepository)
    .<OrderRow, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .transactionAttribute(new DefaultTransactionAttribute() {{
        setTimeout(120);
    }})
    .build();
```

Đoạn code minh họa ý tưởng cấu hình transaction timeout (giá trị tính bằng giây); trong code production, nên tạo và cấu hình `DefaultTransactionAttribute` trong một bean/phương thức riêng thay vì dùng double-brace initialization. Timeout của database/driver cũng cần tương thích.

Nếu chunk thường xuyên vượt timeout, có thể giảm commit interval, tối ưu truy vấn hoặc giảm thời gian xử lý mỗi item. Đừng chỉ tăng timeout mà không xác định nguyên nhân transaction kéo dài.

## 15. Ví dụ so sánh hai cấu hình

Giả sử job nhập 5.000 giao dịch, mỗi item cần validate và ghi một bản ghi vào database.

**Cấu hình A: chunk 1.000**

```java
.<TransactionRow, Transaction>chunk(1000, transactionManager)
```

- Khoảng 5 transaction nếu không có filter/skip.
- Mỗi transaction xử lý nhóm lớn.
- Ít overhead commit hơn.
- Một lỗi trong chunk có thể khiến tối đa 1.000 item đầu vào thuộc transaction hiện tại phải recovery.

**Cấu hình B: chunk 100**

```java
.<TransactionRow, Transaction>chunk(100, transactionManager)
```

- Khoảng 50 transaction nếu không có filter/skip.
- Transaction ngắn hơn trong nhiều workload.
- Rollback scope của một chunk nhỏ hơn.
- Tăng số lần commit và cập nhật metadata.

Chọn cấu hình bằng benchmark với dữ liệu đại diện, đồng thời kiểm tra thời gian chạy, tỷ lệ lỗi, số lần rollback, lock wait, throughput và khả năng restart.

## 16. Những lỗi thường gặp khi chọn commit interval

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chọn chunk quá lớn chỉ để giảm số commit | Transaction dài, lock lâu và rollback scope rộng | Đo và giảm chunk nếu transaction kéo dài hoặc recovery đắt |
| Chọn chunk bằng 1 cho mọi job | Overhead transaction lớn, throughput thấp | Dùng kích thước phù hợp với writer và workload |
| Cho rằng chunk trước sẽ rollback nếu chunk sau lỗi | Hiểu sai transaction boundary | Nhớ rằng mỗi chunk đã commit là transaction riêng |
| Cho rằng commit interval bằng số item writer luôn nhận | Sai khi có filter, skip hoặc chunk cuối | Theo dõi read/write/filter/skip count riêng |
| Bỏ qua transaction timeout | Chunk có thể thất bại khi chạy lâu | Đo thời gian chunk và cấu hình timeout phù hợp |
| Dựa vào commit nhỏ để bảo vệ API ngoài | Side effect ngoài transaction vẫn có thể lặp | Dùng idempotency key, outbox hoặc đối soát |
| Không benchmark dưới tải đồng thời | Chọn chunk không phù hợp khi production | Kiểm thử với concurrency và dữ liệu gần thực tế |

## 17. Quy trình chọn và điều chỉnh chunk size

Khi thiết kế hoặc tối ưu commit policy, có thể thực hiện theo trình tự:

1. Xác định transaction manager và datasource mà step sử dụng.
2. Đo thời gian trung bình và phân vị cao của mỗi chunk với dữ liệu đại diện.
3. Theo dõi số item đọc, ghi, filter và skip để hiểu kích thước thực tế của writer input.
4. Quan sát lock wait, connection usage, transaction timeout và thời gian commit.
5. Chọn một commit interval khởi đầu phù hợp với yêu cầu rollback và throughput.
6. Thử nghiệm khi có lỗi giữa chunk để xác nhận rollback và restart hoạt động đúng.
7. Điều chỉnh từng bước và so sánh số liệu thay vì thay đổi nhiều yếu tố cùng lúc.
8. Kiểm tra side effect ngoài transaction và bảo đảm chúng idempotent khi retry/restart.

Commit interval là một phần của thiết kế transaction, không chỉ là tham số hiệu năng. Hãy chọn nó dựa trên phạm vi rollback chấp nhận được, thời gian giữ tài nguyên và khả năng ghi batch của hệ thống.

## Kết luận

Commit interval xác định kích thước chunk và do đó ảnh hưởng đến phạm vi transaction của step. Chunk nhỏ giới hạn số item nằm trong transaction chưa commit, thường giúp giảm lượng công việc phải rollback hoặc xử lý lại khi lỗi xảy ra. Các chunk trước đã commit vẫn được giữ lại khi chunk sau thất bại.

Đổi lại, chunk nhỏ làm tăng số transaction, commit và cập nhật metadata, có thể giảm throughput. Hãy cân bằng khả năng phục hồi, thời gian giữ lock/connection, bộ nhớ và hiệu năng bằng cách đo trên workload thực tế. Với side effect ngoài transaction, vẫn cần idempotency hoặc outbox; commit nhỏ tự nó không bảo đảm exactly-once.

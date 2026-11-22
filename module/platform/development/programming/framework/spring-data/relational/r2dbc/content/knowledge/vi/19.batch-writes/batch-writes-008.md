# Chọn giao dịch cho toàn bộ dữ liệu hay từng nhóm

Khi ghi nhiều bản ghi bằng Spring Data R2DBC, cần quyết định phạm vi transaction: toàn bộ lần nhập dữ liệu là một đơn vị nguyên tử, hay mỗi nhóm bản ghi được commit độc lập. Hai lựa chọn này ảnh hưởng đến tính nhất quán, thời gian giữ connection, lock, khả năng phục hồi khi lỗi và cách tiếp tục một tiến trình nhập dữ liệu bị gián đoạn.

Một transaction cho toàn bộ dữ liệu bảo đảm tất cả thay đổi trong lần nhập cùng commit hoặc cùng rollback. Transaction theo từng nhóm (batch) rút ngắn thời gian mỗi transaction và cho phép giữ lại các nhóm đã commit khi nhóm sau thất bại, nhưng dữ liệu tổng thể có thể ở trạng thái hoàn thành một phần. Không có lựa chọn đúng cho mọi hệ thống; phạm vi transaction phải phản ánh quy tắc nghiệp vụ.

## 1. Phân biệt batch ghi và phạm vi transaction

Batch và transaction là hai khái niệm khác nhau:

- **Batch** xác định số bản ghi được gom lại để xử lý trong một lượt. Ví dụ `buffer(500)` tạo các nhóm tối đa 500 phần tử.
- **Transaction** xác định ranh giới commit/rollback. Nhiều batch có thể nằm trong cùng một transaction, hoặc mỗi batch có thể chạy trong transaction riêng.

Ví dụ, một file có 10.000 dòng có thể được chia thành 20 nhóm, mỗi nhóm 500 dòng. Có hai cách tổ chức:

1. Mở một transaction bên ngoài toàn bộ pipeline, xử lý lần lượt 20 nhóm rồi mới commit. Nếu nhóm thứ 20 thất bại, toàn bộ thay đổi của 20 nhóm được rollback.
2. Mỗi nhóm mở một transaction riêng. Khi nhóm thứ 1 đến 10 đã commit và nhóm thứ 11 thất bại, dữ liệu của 10 nhóm đầu vẫn còn trong database.

`buffer(500)` chỉ kiểm soát số phần tử được gom trong bộ nhớ. Nó không tự tạo transaction và cũng không tự commit dữ liệu. Phạm vi transaction được quyết định bởi vị trí áp dụng `TransactionalOperator` hoặc ranh giới `@Transactional`.

## 2. Khi nào nên dùng một transaction cho toàn bộ dữ liệu?

Chọn transaction toàn bộ khi nghiệp vụ yêu cầu tất cả bản ghi phải xuất hiện cùng nhau hoặc không có bản ghi nào được ghi. Ví dụ:

- Nạp một bộ dữ liệu tham chiếu nhỏ mà các bảng phụ thuộc cần đồng bộ cùng lúc.
- Cập nhật một tập dữ liệu tạo thành một trạng thái nghiệp vụ duy nhất.
- Ghi nhiều hàng mà các ràng buộc nghiệp vụ chỉ đúng khi toàn bộ tập thay đổi cùng commit.
- Thay thế một snapshot dữ liệu và không chấp nhận người đọc nhìn thấy trạng thái mới chỉ một phần.

Ưu điểm chính là tính nguyên tử: khi một thao tác trong transaction thất bại, các thay đổi đã thực hiện trong transaction có thể được rollback. Các reader khác nhìn thấy dữ liệu theo quy tắc isolation của database, thay vì nhìn thấy từng batch đã commit độc lập.

Đổi lại, transaction có thể kéo dài trong suốt quá trình đọc, chuyển đổi và ghi toàn bộ dữ liệu. Connection bị giữ lâu hơn; lock và phiên bản dữ liệu cũ có thể tồn tại lâu hơn; log transaction/WAL hoặc vùng undo có thể tăng; rollback sau khi xử lý nhiều hàng có thể tốn thời gian. Nếu pipeline đọc dữ liệu từ file, mạng hoặc dịch vụ khác, thời gian chờ nguồn dữ liệu cũng có thể kéo dài transaction.

Với dữ liệu rất lớn, transaction toàn bộ có thể gây áp lực lên database và ảnh hưởng các workload khác. Không nên chọn chỉ vì muốn “an toàn hơn”; cần cân nhắc chi phí vận hành và yêu cầu atomicity thật sự.

## 3. Khi nào nên commit theo từng nhóm?

Transaction theo batch phù hợp khi mỗi nhóm có thể được xem là đơn vị hoàn thành độc lập. Ví dụ:

- Import dữ liệu lớn, có thể tiếp tục từ nhóm cuối cùng đã commit.
- Đồng bộ danh mục hoặc lịch sử mà các bản ghi không cần cùng xuất hiện trong một thời điểm.
- Tác vụ xử lý nền có thể ghi nhận tiến độ sau mỗi nhóm.
- Xóa hoặc cập nhật dữ liệu cũ theo từng nhóm để giảm thời gian lock và lượng công việc trong mỗi transaction.

Mỗi batch commit độc lập nên connection và transaction được giải phóng sớm hơn. Nếu batch tiếp theo lỗi, các batch đã commit không bị rollback. Có thể ghi checkpoint, đánh dấu tiến độ hoặc retry đúng batch bị lỗi.

Nhược điểm là trạng thái hoàn thành một phần trở thành một phần của thiết kế. Nếu người dùng hoặc service khác đọc dữ liệu trong lúc import, họ có thể thấy một phần dữ liệu mới. Nếu các hàng giữa nhiều batch có ràng buộc nghiệp vụ xuyên suốt, commit riêng từng batch có thể để lại trạng thái không hợp lệ khi tiến trình dừng giữa chừng.

Để dùng batch transaction an toàn, cần xác định cách phát hiện tiến trình chưa hoàn tất, cách tiếp tục, cách xử lý dữ liệu trùng khi retry và cách ngăn người dùng sử dụng dữ liệu chưa được công bố.

## 4. So sánh hai chiến lược

| Tiêu chí | Một transaction cho toàn bộ dữ liệu | Một transaction cho mỗi batch |
|---|---|---|
| Atomicity | Toàn bộ lần ghi cùng commit hoặc rollback | Chỉ từng batch là nguyên tử |
| Khi batch cuối thất bại | Rollback mọi thay đổi của lần import | Giữ các batch đã commit; batch lỗi rollback riêng |
| Thời gian transaction | Có thể rất dài | Ngắn hơn, giới hạn theo thời gian xử lý một batch |
| Connection | Có thể giữ connection trong toàn bộ import | Giải phóng connection sau mỗi batch |
| Lock và log transaction | Có thể tăng theo toàn bộ tập dữ liệu | Thường giới hạn theo batch |
| Khả năng tiếp tục | Thường phải chạy lại toàn bộ hoặc dùng cơ chế staging | Có thể tiếp tục từ checkpoint đã commit |
| Trạng thái dữ liệu một phần | Không lộ các thay đổi chưa commit theo isolation thông thường | Có thể nhìn thấy các batch đã commit trước khi import hoàn tất |
| Phù hợp | Tập thay đổi nhỏ/vừa, yêu cầu tất cả hoặc không gì cả | Import lớn, xử lý nền, mỗi nhóm độc lập |

Điểm quyết định không phải số lượng bản ghi tuyệt đối mà là mối quan hệ nghiệp vụ giữa các bản ghi, tải database và cách hệ thống xử lý trạng thái dở dang.

## 5. Dùng Reactive TransactionalOperator

Với ứng dụng reactive, `TransactionalOperator` cho phép xác định rõ phạm vi transaction quanh một `Mono` hoặc `Flux`. Spring cần có `ReactiveTransactionManager` phù hợp với `ConnectionFactory`.

Ví dụ khai báo operator trong cấu hình thủ công:

```java
@Bean
TransactionalOperator transactionalOperator(
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
```

Nếu Spring Boot đã cung cấp transaction manager và ứng dụng không cần tùy chỉnh, có thể inject bean hiện có thay vì tạo một transaction manager trùng lặp. Tên bean và cách cấu hình cần phù hợp với ứng dụng có một hay nhiều `ConnectionFactory`.

`TransactionalOperator.transactional(publisher)` bắt đầu transaction khi reactive chain được subscribe, truyền transaction context trong pipeline, rồi commit khi publisher hoàn tất thành công hoặc rollback khi có lỗi/hủy theo semantics của transaction manager và driver.

## 6. Một transaction bao quanh toàn bộ dữ liệu

Giả sử nguồn nhập là `Flux<ImportRow>`, mỗi hàng được ghi bằng repository. Có thể gom thành nhóm để kiểm soát bộ nhớ nhưng đặt transaction bên ngoài toàn bộ pipeline:

```java
public Mono<Void> importAtomically(Flux<ImportRow> source) {
    return transactionalOperator.transactional(
        source
            .buffer(500)
            .concatMap(batch ->
                Flux.fromIterable(batch)
                    .concatMap(importRepository::save)
            )
            .then()
    );
}
```

Ở đây:

- `buffer(500)` chia nguồn thành các nhóm tối đa 500 hàng.
- `concatMap` xử lý từng nhóm và từng hàng tuần tự, giúp kiểm soát thứ tự và tránh tạo quá nhiều thao tác ghi đồng thời.
- `transactionalOperator.transactional(...)` bao toàn bộ pipeline, vì vậy mọi lần `save` trong chuỗi tham gia cùng transaction reactive nếu repository dùng đúng hạ tầng kết nối được quản lý.
- `.then()` chuyển kết quả thành `Mono<Void>` vì service chỉ quan tâm import hoàn tất hay lỗi.

Mặc dù dữ liệu được xử lý theo nhóm 500, tất cả nhóm vẫn nằm trong một transaction. Nếu một lần `save` phát lỗi, publisher lỗi và transaction được rollback. `buffer` không làm transaction commit sau mỗi nhóm.

Không gọi `subscribe()` bên trong service để tự khởi chạy pipeline. Hãy trả về publisher cho framework hoặc caller subscribe; nếu tự subscribe ở giữa, transaction có thể kết thúc trước khi các thao tác ghi hoàn thành hoặc lỗi không được truyền về caller.

## 7. Một transaction cho từng batch

Nếu mỗi nhóm được phép commit độc lập, đặt `TransactionalOperator` bên trong `concatMap`:

```java
public Mono<Void> importPerBatch(Flux<ImportRow> source) {
    return source
        .buffer(500)
        .concatMap(batch -> transactionalOperator.transactional(
            Flux.fromIterable(batch)
                .concatMap(importRepository::save)
                .then()
        ))
        .then();
}
```

Trong cấu trúc này, mỗi lần `concatMap` xử lý một batch sẽ subscribe vào một transaction riêng. Batch chỉ được xem là hoàn tất khi các thao tác save trong batch hoàn tất và transaction commit thành công. `concatMap` chờ batch hiện tại xong trước khi xử lý batch kế tiếp.

Nếu batch thứ 8 thất bại, transaction của batch đó rollback. Các batch từ 1 đến 7 đã commit vẫn được giữ lại. Publisher bên ngoài mặc định phát lỗi và dừng; các batch sau không tự động chạy tiếp. Service cần quyết định fail-fast, ghi nhận lỗi và tiếp tục, hoặc đưa batch lỗi vào hàng đợi xử lý riêng.

Để theo dõi tiến độ, có thể ghi một bản ghi import job hoặc checkpoint trong cùng transaction với dữ liệu của batch:

```java
private Mono<Void> persistBatch(UUID jobId, int batchNumber,
                                List<ImportRow> batch) {
    return transactionalOperator.transactional(
        Flux.fromIterable(batch)
            .concatMap(importRepository::save)
            .then(importJobRepository.markBatchCompleted(jobId, batchNumber))
            .then()
    );
}
```

Checkpoint phải commit cùng batch dữ liệu. Nếu checkpoint được ghi ở một transaction khác, có thể xảy ra trường hợp dữ liệu đã commit nhưng checkpoint chưa được cập nhật, hoặc ngược lại. Khi retry, hãy thiết kế thao tác ghi có thể nhận biết và xử lý lại an toàn.

## 8. Dùng @Transactional cho reactive method

Spring cũng hỗ trợ khai báo transaction bằng `@Transactional` trên phương thức trả về reactive publisher. Transaction manager được chọn phải là reactive transaction manager tương ứng với R2DBC.

```java
@Transactional
public Mono<Void> importAtomically(Flux<ImportRow> source) {
    return source
        .buffer(500)
        .concatMap(batch ->
            Flux.fromIterable(batch)
                .concatMap(importRepository::save)
        )
        .then();
}
```

Với phương thức reactive, Spring gắn transaction vào reactive context của publisher được trả về. Không chuyển phương thức thành `void` rồi khởi chạy một `subscribe()` nội bộ; làm vậy khiến proxy transaction không quản lý được vòng đời publisher như mong đợi.

Nếu cần transaction theo từng batch, có thể đặt lời gọi đến một bean service khác có phương thức transactional cho từng batch, hoặc dùng `TransactionalOperator` quanh publisher của mỗi batch. Chú ý cơ chế proxy của Spring: self-invocation (một phương thức gọi trực tiếp phương thức khác trong cùng object) thường không đi qua proxy nên có thể không kích hoạt annotation như mong muốn.

## 9. Chọn concurrency: concatMap hay flatMap?

Trong reactive flow, `concatMap` xử lý tuần tự và chỉ chuyển sang phần tử tiếp theo khi publisher con hoàn tất. `flatMap` có thể chạy nhiều publisher con đồng thời.

Với một transaction bao toàn bộ import, nên bắt đầu bằng `concatMap` để thao tác ghi diễn ra tuần tự trên transaction context. Không giả định mọi driver hoặc connection đều hỗ trợ nhiều statement đồng thời trên cùng một connection. Nếu cần tối ưu song song, phải xác minh khả năng của driver, transaction manager và database; đồng thời đo ảnh hưởng lên pool và lock.

Với transaction riêng từng batch, có thể dùng `flatMap(batch -> transactionalOperator.transactional(...), concurrency)` nếu các batch độc lập và database đủ năng lực xử lý đồng thời. Khi tăng concurrency, mỗi batch có thể cần một connection riêng. Giá trị concurrency phải phù hợp với pool size, giới hạn connection của database và tải của các service khác.

Ví dụ chạy tối đa ba batch song song:

```java
return source
    .buffer(500)
    .flatMap(batch -> transactionalOperator.transactional(
        Flux.fromIterable(batch)
            .concatMap(importRepository::save)
            .then()
    ), 3)
    .then();
```

Thứ tự commit có thể khác thứ tự batch đầu vào khi chạy song song. Nếu thứ tự là yêu cầu nghiệp vụ, dùng `concatMap` hoặc thiết kế sequence/checkpoint phù hợp. Không tăng concurrency chỉ để làm import nhanh hơn nếu database đã bão hòa hoặc pool bắt đầu có pending acquire cao.

## 10. Kích thước batch và thời gian transaction

Kích thước batch cần cân bằng giữa overhead và tài nguyên:

- **Batch quá nhỏ:** tăng số lần mở/commit transaction, tăng round-trip và overhead quản lý tiến độ.
- **Batch quá lớn:** tăng bộ nhớ tạm, thời gian xử lý mỗi transaction, lượng lock và chi phí rollback.
- **Batch có kích thước phù hợp:** giới hạn số hàng và thời gian xử lý ở mức database chịu được, đồng thời không tạo quá nhiều transaction nhỏ.

Không có con số mặc định phù hợp cho mọi database. Bắt đầu với một kích thước vừa phải, đo thời gian mỗi batch, số connection active, pending acquire, lock wait, transaction log và tỷ lệ lỗi. Sau đó điều chỉnh dựa trên kích thước hàng, index, constraint, độ trễ mạng và tải đồng thời.

`buffer(500)` cũng có thể phát batch cuối nhỏ hơn 500 khi nguồn hoàn tất. Nếu nguồn vô hạn, cần có cơ chế flush theo thời gian hoặc ranh giới khác; nếu chỉ dùng `buffer(size)`, batch chưa đủ kích thước có thể chờ mãi. Đối với import từ file hữu hạn, batch cuối sẽ được phát khi publisher hoàn tất.

## 11. Lỗi giữa chừng và chính sách tiếp tục

Với một transaction toàn bộ, lỗi ở bất kỳ bước nào thường làm rollback toàn bộ publisher. Cách phục hồi là sửa nguyên nhân và chạy lại toàn bộ hoặc dùng staging/snapshot để thay thế dữ liệu một cách có kiểm soát.

Với transaction theo batch, lỗi ở một batch làm rollback batch đó; các batch trước giữ nguyên. Có thể chọn một trong các chính sách:

1. **Fail-fast:** dừng ngay khi một batch lỗi, ghi trạng thái job thất bại và yêu cầu vận hành xử lý.
2. **Retry có giới hạn:** thử lại batch lỗi nếu lỗi tạm thời và thao tác idempotent.
3. **Ghi nhận batch lỗi rồi tiếp tục:** chỉ phù hợp khi các batch độc lập và nghiệp vụ cho phép kết quả một phần; phải có báo cáo các hàng lỗi.
4. **Đưa bản ghi lỗi vào dead-letter/reject store:** lưu dữ liệu và nguyên nhân để xử lý sau, không âm thầm bỏ qua.

Không nên dùng `onErrorResume(error -> Mono.empty())` chung chung quanh cả pipeline. Nó có thể biến lỗi database thành thành công giả và làm mất dấu batch chưa được ghi.

## 12. Retry và tính idempotent

Retry có thể khiến cùng một batch được gửi lại sau khi lỗi mạng hoặc timeout. Ứng dụng phải xử lý tình huống không biết chắc server đã commit hay chưa. Nếu lần đầu đã commit nhưng client mất phản hồi, retry một lệnh insert thông thường có thể tạo dữ liệu trùng hoặc lỗi unique constraint.

Các biện pháp hỗ trợ retry an toàn gồm:

- Dùng khóa nghiệp vụ hoặc ID ổn định từ nguồn để nhận diện một bản ghi.
- Tạo unique constraint để database ngăn insert trùng.
- Dùng upsert hoặc thao tác insert/update có semantics rõ ràng theo database.
- Ghi checkpoint cùng transaction với dữ liệu batch.
- Chỉ retry lỗi được xác định là tạm thời; không retry lỗi validation hoặc vi phạm constraint một cách vô hạn.

Ví dụ về retry quanh transaction của từng batch:

```java
return transactionalOperator.transactional(saveBatch(batch))
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
        .filter(this::isTransientDatabaseFailure));
```

Khi retry, publisher được subscribe lại; transaction mới cần được tạo cho lần thực thi mới. Đặt retry bên ngoài publisher transaction giúp mỗi lần thử có thể đi qua vòng đời transaction mới. Cần xác minh phân loại lỗi và tính idempotent trước khi bật retry.

## 13. Ràng buộc xuyên nhiều batch

Nếu dữ liệu có ràng buộc giữa các batch, transaction riêng từng batch có thể không đủ. Ví dụ, import tài khoản và số dư phải bảo đảm tổng số dư đối chiếu với tổng giao dịch sau khi tất cả batch hoàn tất. Một batch có thể hợp lệ riêng nhưng tập dữ liệu chưa hoàn chỉnh vẫn không hợp lệ.

Một số chiến lược:

- **Staging table:** ghi từng batch vào bảng staging, kiểm tra toàn bộ tập dữ liệu rồi chuyển sang bảng chính trong một bước commit phù hợp.
- **Trạng thái import job:** dữ liệu gắn với `job_id` và chỉ được sử dụng khi job chuyển sang `COMPLETED`.
- **Snapshot/version:** ghi dữ liệu phiên bản mới, sau đó đổi con trỏ phiên bản đang hoạt động khi toàn bộ dữ liệu sẵn sàng.
- **Validation trước commit:** kiểm tra count, checksum, khóa trùng, tổng hợp và quan hệ tham chiếu trước khi công bố dữ liệu.

Những cách này cho phép ghi theo batch để giảm transaction dài nhưng vẫn kiểm soát thời điểm dữ liệu được xem là hoàn chỉnh. Bước chuyển trạng thái cuối cùng thường cần transaction ngắn và có điều kiện rõ ràng.

## 14. Tác động của transaction đến nguồn dữ liệu và side effect bên ngoài

Transaction R2DBC chỉ quản lý tài nguyên database tham gia transaction. Nó không tự rollback việc đọc file, gọi HTTP, gửi email hoặc publish message đến broker bên ngoài.

Tránh giữ transaction mở trong khi chờ dịch vụ bên ngoài phản hồi. Có thể đọc và validate dữ liệu trước, sau đó chỉ mở transaction trong giai đoạn ghi. Với import lớn theo batch, đọc một nhóm từ nguồn rồi mở transaction cho nhóm đó giúp giới hạn thời gian giữ connection.

Nếu cần phát sự kiện cho mỗi batch sau khi commit, không publish trước khi commit thành công. Nếu cần bảo đảm sự kiện không bị mất giữa commit và publish, dùng transactional outbox: ghi dữ liệu và outbox row trong cùng transaction, sau đó một publisher riêng gửi sự kiện và đánh dấu đã xử lý.

## 15. Ví dụ service có checkpoint theo batch

Một service có thể xử lý từng batch tuần tự và lưu tiến độ trong cùng transaction:

```java
public Mono<Void> importWithCheckpoint(
        UUID jobId, Flux<ImportRow> source) {

    AtomicInteger batchNumber = new AtomicInteger(0);

    return source
        .buffer(500)
        .concatMap(batch -> {
            int currentBatch = batchNumber.incrementAndGet();

            return transactionalOperator.transactional(
                Flux.fromIterable(batch)
                    .concatMap(importRepository::save)
                    .then(importJobRepository.markBatchCompleted(
                        jobId, currentBatch, batch.size()))
                    .then()
            );
        })
        .then();
}
```

Ví dụ minh họa việc cập nhật checkpoint cùng transaction. Trong ứng dụng thực tế, số batch nên được xác định ổn định từ nguồn hoặc lưu trong database để có thể tiếp tục sau restart. `AtomicInteger` trong bộ nhớ chỉ đếm trong một lần chạy process; nó không phải checkpoint bền vững. Nếu chạy lại job, cần đọc batch đã hoàn tất từ database và xác định batch tiếp theo bằng khóa ổn định.

Nếu nhiều worker có thể chạy cùng một job, cần cơ chế claim/lease để chỉ một worker xử lý một batch tại một thời điểm hoặc dùng khóa duy nhất/optimistic locking trên checkpoint. Nếu không, hai worker có thể ghi cùng batch đồng thời.

## 16. Theo dõi và vận hành

Để chọn đúng phạm vi transaction, cần quan sát cả ứng dụng và database:

| Chỉ số | Điều cần quan sát |
|---|---|
| Thời gian transaction | Transaction dài bất thường có thể giữ connection và lock lâu. |
| Thời gian mỗi batch | Giúp chọn batch size và phát hiện batch dữ liệu bất thường. |
| Số hàng commit/rollback | Xác định tiến độ thực tế và mức độ thất bại. |
| Active/pending connections | Phát hiện pool cạn khi nhiều batch chạy song song. |
| Lock wait/deadlock | Cho biết batch cạnh tranh cùng hàng hoặc index. |
| Transaction log/WAL/undo | Phát hiện áp lực do transaction lớn hoặc lượng ghi cao. |
| Checkpoint và job state | Cho biết có thể tiếp tục từ đâu sau restart. |
| Retry count và rejected rows | Theo dõi lỗi tạm thời và dữ liệu không hợp lệ. |

Khi import chậm, không nên mặc định tăng batch size hoặc concurrency. Kiểm tra query plan, index, constraint, độ rộng bản ghi, lock và thời gian chờ connection trước. Một transaction lớn hơn có thể làm throughput giảm nếu database phải giữ nhiều tài nguyên trong thời gian dài.

## 17. Quy trình lựa chọn phạm vi transaction

Trước khi triển khai ghi nhiều bản ghi, hãy trả lời:

1. Các bản ghi có bắt buộc cùng xuất hiện hoặc cùng biến mất không?
2. Người đọc có chấp nhận nhìn thấy dữ liệu đã commit theo từng phần không?
3. Nếu batch thứ N lỗi, có thể giữ các batch trước và tiếp tục không?
4. Có ràng buộc nghiệp vụ xuyên nhiều batch cần kiểm tra trước khi công bố không?
5. Transaction toàn bộ có giữ connection/lock quá lâu hoặc tạo log quá lớn không?
6. Batch có idempotent và có checkpoint bền vững để retry không?
7. Concurrency của batch có phù hợp với connection pool và giới hạn database không?
8. Các side effect bên ngoài có cần outbox hoặc xử lý sau commit không?

Chọn transaction toàn bộ khi yêu cầu atomicity áp dụng cho toàn bộ tập dữ liệu và chi phí transaction dài có thể chấp nhận. Chọn transaction theo batch khi mỗi nhóm có thể commit độc lập, hệ thống có cơ chế theo dõi tiến độ và có thể xử lý trạng thái một phần. Trong cả hai trường hợp, dùng reactive transaction manager đúng với `ConnectionFactory`, giữ thao tác database trong reactive chain và đo tải thực tế để điều chỉnh batch size/concurrency.

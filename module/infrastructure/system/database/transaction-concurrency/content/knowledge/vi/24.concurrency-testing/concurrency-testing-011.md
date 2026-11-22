# Giới hạn của kiểm thử ngẫu nhiên và kiểm chứng theo một số lần chạy

Kiểm thử đồng thời thường phải đối mặt với một vấn đề khó: cùng một tập câu lệnh có thể chạy theo nhiều thứ tự xen kẽ khác nhau. Một lỗi chỉ xuất hiện khi hai transaction chạm đúng một cửa sổ thời gian hẹp, lấy khóa theo một thứ tự nhất định hoặc gặp một trạng thái dữ liệu hiếm. Chạy lại test vài lần có thể không tái hiện được lỗi; chạy hàng nghìn lần cũng không chứng minh rằng mọi lịch thực thi đều an toàn.

Kiểm thử ngẫu nhiên (randomized testing) và stress testing rất hữu ích để tìm những interleaving mà người viết test không nghĩ đến. Tuy nhiên, mỗi lần chạy chỉ quan sát một số lịch thực thi trong một không gian có thể rất lớn. **Không thấy lỗi trong N lần chạy chỉ chứng minh rằng N lần chạy đã thực hiện không phát hiện lỗi theo các điều kiện đã thử.** Nó không chứng minh rằng hệ thống không có race condition, deadlock, lost update, write skew hoặc vi phạm bất biến.

Để tăng độ tin cậy, cần kết hợp nhiều phương pháp: tạo dữ liệu và thao tác có kiểm soát, ghi lại seed và lịch thực thi, kiểm tra bất biến sau mỗi run, dùng barrier để tái tạo interleaving quan trọng, kiểm tra lịch sử giao dịch, chạy stress test đủ lâu và dùng bounded/model checking khi phạm vi mô hình cho phép.

Bài này tập trung vào kiểm thử concurrency của database transaction. Ví dụ sử dụng SQL và Java ở mức khái niệm, với MySQL InnoDB và PostgreSQL làm hệ quản trị tham chiếu. Các kết quả luôn phụ thuộc phiên bản, isolation level, schema, execution plan, dữ liệu và cấu hình môi trường.

## 1. Vì sao kiểm thử đồng thời khó hơn kiểm thử tuần tự?

Trong kiểm thử tuần tự, chương trình thường có một thứ tự thao tác rõ ràng:

```text
Đọc dữ liệu -> kiểm tra -> cập nhật -> commit
```

Khi nhiều transaction chạy đồng thời, các bước của chúng có thể xen kẽ:

```text
T1: đọc số dư A
T2: đọc số dư A
T1: tính số dư mới
T2: tính số dư mới
T1: cập nhật A
T2: cập nhật A
T1: commit
T2: commit hoặc bị lỗi
```

Một lỗi có thể phụ thuộc vào vị trí xen kẽ rất cụ thể. Ví dụ, lost update có thể xảy ra khi cả hai transaction đọc cùng giá trị cũ trước khi một transaction ghi. Deadlock có thể chỉ xảy ra khi T1 lấy khóa hàng X trước hàng Y còn T2 lấy Y trước X. Write skew có thể xuất hiện khi hai transaction đọc cùng một tập dữ liệu rồi cập nhật hai hàng khác nhau dựa trên cùng một điều kiện tổng hợp.

Với hai transaction, số thứ tự xen kẽ hợp lệ đã có thể tăng nhanh theo số bước của mỗi transaction. Khi tăng số transaction, số thao tác, số hàng và các nhánh điều kiện, không gian trạng thái lớn hơn nhiều. Một test đơn giản thường chỉ khám phá một phần rất nhỏ của không gian đó.

## 2. Phân biệt các phương pháp kiểm thử

Các phương pháp sau bổ sung cho nhau nhưng không có cùng mục tiêu:

| Phương pháp | Cách hoạt động | Điểm mạnh | Giới hạn chính |
|---|---|---|---|
| Test theo lịch xác định (deterministic schedule) | Điều phối các session đi qua một thứ tự cụ thể bằng barrier hoặc hook | Tái hiện chính xác một interleaving đã biết | Chỉ kiểm tra các lịch được thiết kế |
| Randomized testing | Sinh ngẫu nhiên thao tác, tham số, thứ tự hoặc độ trễ | Khám phá nhiều tổ hợp không được viết tay | Kết quả phụ thuộc seed và phân phối sinh; không bao phủ hết lịch |
| Stress testing | Chạy tải đồng thời lớn hoặc lâu | Phát hiện vấn đề dưới tải, contention, timeout và resource pressure | Có thể tạo nhiều tải nhưng vẫn bỏ lỡ interleaving hiếm |
| Property-based testing | Sinh input và kiểm tra các thuộc tính/bất biến thay vì chỉ so kết quả cố định | Kiểm tra nhiều dữ liệu và tìm phản ví dụ | Chất lượng phụ thuộc property và generator |
| History/model checking | So sánh lịch sử quan sát với mô hình hoặc kiểm tra các lịch trong phạm vi giới hạn | Có thể phát hiện lịch sử không phù hợp với đặc tả | Cần mô hình đúng; state space có thể bùng nổ |
| Fault injection | Chủ động làm chậm, ngắt kết nối, crash hoặc tạo lỗi ở điểm xác định | Kiểm tra cửa sổ phục hồi và rollback | Không tự động bao phủ mọi lỗi hoặc mọi thời điểm |

Một chiến lược tốt không chọn duy nhất một loại test. Deterministic test bảo vệ những interleaving quan trọng; randomized/stress test mở rộng tìm kiếm; property và history checking đánh giá tính đúng; fault injection kiểm tra phục hồi.

## 3. Giới hạn toán học của số lần chạy hữu hạn

Giả sử một lỗi chỉ xuất hiện với xác suất (p) trong một lần chạy độc lập. Xác suất không thấy lỗi sau (N) lần chạy là:

\[
P(\text{không thấy lỗi})=(1-p)^N
\]

Do đó, xác suất phát hiện ít nhất một lần là:

\[
P(\text{phát hiện})=1-(1-p)^N
\]

Ví dụ minh họa nếu xác suất xuất hiện lỗi trong một run thực sự là 1% và các run độc lập:

| Số lần chạy N | Xác suất phát hiện ít nhất một lần |
|---:|---:|
| 10 | khoảng 9,6% |
| 50 | khoảng 39,5% |
| 100 | khoảng 63,4% |
| 300 | khoảng 95,1% |
| 500 | khoảng 99,3% |

Ngay cả khi chạy 300 lần, vẫn còn khoảng 4,9% khả năng không quan sát thấy lỗi trong giả định này. Nếu lỗi chỉ xuất hiện với xác suất 0,01%, số lần chạy cần thiết còn lớn hơn nhiều.

Quan trọng hơn, trong kiểm thử concurrency, giả định các lần chạy độc lập và có cùng xác suất (p) thường không hoàn toàn đúng. Seed có thể tạo ra cùng chuỗi thao tác; máy có tải ổn định; scheduler có xu hướng lặp lại một số lịch; test harness có barrier cố định. Một nghìn run giống nhau không tương đương một nghìn lịch thực thi độc lập.

Không nên dùng công thức trên để tuyên bố một mức bảo đảm tuyệt đối. Nó chỉ giúp hiểu rằng số lần chạy hữu hạn luôn có giới hạn thống kê, và khả năng phát hiện phụ thuộc xác suất thực tế của lỗi trong phân phối test.

## 4. Không gian interleaving lớn hơn số thứ tự được viết trong test

Giả sử T1 có ba thao tác quan sát được và T2 cũng có ba thao tác:

```text
T1: A1 -> A2 -> A3
T2: B1 -> B2 -> B3
```

Nếu mỗi transaction giữ nguyên thứ tự nội bộ, số cách xen kẽ bảo toàn thứ tự của từng transaction là:

\[
\binom{6}{3}=20
\]

Với 5 thao tác mỗi transaction:

\[
\binom{10}{5}=252
\]

Với 10 thao tác mỗi transaction:

\[
\binom{20}{10}=184756
\]

Đây chỉ là số interleaving ở mức thao tác đơn giản. Trong database thực tế còn có nhiều yếu tố:

- Mỗi SQL statement có thể đọc hoặc ghi nhiều hàng và index record.
- Optimizer có thể chọn access path khác.
- Transaction có thể chờ lock, timeout, deadlock hoặc bị hủy.
- Commit/rollback và crash tạo thêm nhánh trạng thái.
- Trigger, foreign key, cascade và stored procedure tạo thêm thao tác nội bộ.
- Nhiều transaction có thể chạy trên nhiều connection và nhiều node.

Vì vậy, một test chạy 100 lần không có nghĩa đã kiểm tra 100 lịch khác nhau, càng không có nghĩa đã duyệt hết các lịch có thể xảy ra.

## 5. Randomized testing tìm lỗi như thế nào?

Một randomized concurrency test có thể sinh:

- Các thao tác nghiệp vụ như mở tài khoản, chuyển tiền, đặt hàng, trừ tồn kho hoặc xác nhận đơn.
- Định danh hàng, số tiền, số lượng, trạng thái và version.
- Số worker và số connection.
- Thứ tự gửi các thao tác vào worker.
- Khoảng delay trước/sau câu SQL hoặc trước commit.
- Isolation level, timeout và kích thước batch.
- Thời điểm hủy query hoặc ngắt connection trong môi trường thử nghiệm.

Ví dụ, test chuyển tiền có thể tạo ngẫu nhiên nhiều lệnh chuyển giữa một tập tài khoản. Sau khi tất cả request kết thúc, test kiểm tra tổng số dư không đổi và không tài khoản nào có số dư âm nếu nghiệp vụ cấm điều đó.

Randomization có ích vì nó tạo ra nhiều tổ hợp input và lịch thực thi mà người viết test không cần mô tả từng trường hợp. Tuy nhiên, generator phải tạo ra dữ liệu hợp lệ và đủ thiên về các vùng dễ xung đột. Nếu luôn sinh account ID khác nhau, test có thể chạy rất nhiều lần mà không bao giờ tranh chấp cùng một hàng.

## 6. Seed giúp tái lập input, nhưng chưa chắc tái lập lịch chạy

Một bộ sinh ngẫu nhiên có seed cho phép tạo lại cùng chuỗi giá trị đầu vào:

```java
long seed = 20261114L;
Random random = new Random(seed);

long fromId = 1 + random.nextInt(5);
long toId = 1 + random.nextInt(5);
int amount = 1 + random.nextInt(100);
```

Nếu cùng thuật toán generator và cùng seed, test có thể tái tạo cùng các tham số. Nhưng seed không đảm bảo scheduler chạy thread theo cùng thứ tự. Lịch thực thi còn phụ thuộc:

- Tốc độ CPU và số core.
- Tải máy và các process khác.
- Connection pool và thời điểm lấy connection.
- Network latency, disk I/O và database background tasks.
- Query plan, lock contention và thời gian chờ.
- Phiên bản JVM, driver và database.
- Timing của barrier, timeout và thread scheduler.

Do đó, **seed tái lập chuỗi input; nó không tự động tái lập toàn bộ interleaving**. Khi phát hiện lỗi, lưu cả seed lẫn lịch sự kiện đã quan sát. Nếu test harness có thể điều phối từng bước, lưu schedule hoặc trace barrier để replay chính xác hơn.

## 7. Thiết kế generator để tạo cạnh tranh có chủ đích

Random test kém hiệu quả nếu dữ liệu và thao tác hiếm khi chạm cùng tài nguyên. Có thể tăng khả năng phát hiện bằng cách phân phối input có chủ đích:

- Chọn một nhóm nhỏ khóa nóng (hot keys) để nhiều worker cùng cập nhật.
- Trộn thao tác đọc, cập nhật, xóa và chèn trên cùng phạm vi index.
- Sinh các giá trị biên như số dư bằng đúng số tiền chuyển, tồn kho bằng 0 hoặc version sát ngưỡng.
- Tạo cả giao dịch ngắn và giao dịch nhiều bước.
- Thay đổi thứ tự truy cập hai hoặc nhiều hàng.
- Tạo các predicate range có thể gặp gap/next-key locking.
- Đưa một tỷ lệ nhỏ thao tác thất bại, timeout hoặc retry vào workload.

Ví dụ phân phối account ID:

```java
long chooseAccountId(Random random) {
    // Phần lớn request truy cập nhóm hot accounts.
    if (random.nextDouble() < 0.80) {
        return 1 + random.nextInt(5);
    }

    // Một phần nhỏ truy cập tập rộng hơn.
    return 6 + random.nextInt(95);
}
```

Phân phối lệch này tạo contention nhiều hơn phân phối đều trên hàng triệu ID. Tỷ lệ 80% chỉ là ví dụ; workload cần phản ánh hoặc cố ý làm nặng hơn đặc điểm cần kiểm tra.

Hãy ghi generator version và cấu hình phân phối. Khi thay đổi generator, cùng seed có thể sinh dữ liệu khác nên seed đơn lẻ không còn đủ để tái lập.

## 8. Kiểm tra bất biến thay vì chỉ kiểm tra không có exception

Một test concurrency có thể chạy hết mà không ném lỗi nhưng vẫn làm sai dữ liệu. Vì vậy, cần xác định các bất biến nghiệp vụ có thể kiểm tra sau mỗi run.

Ví dụ với chuyển tiền:

- Tổng số dư của tất cả tài khoản không đổi nếu không có phí hoặc nạp/rút bên ngoài.
- Số dư không âm nếu nghiệp vụ cấm âm.
- Mỗi yêu cầu chuyển tiền thành công chỉ được ghi nhận một lần.
- Bản ghi debit và credit của một transfer phải cùng tồn tại hoặc cùng không tồn tại.
- Mọi transfer đã commit phải có trạng thái hoàn tất phù hợp.

Với tồn kho:

- Số lượng không âm.
- Không thể reserve vượt số lượng khả dụng.
- Tổng lượng đã reserve không vượt lượng nhập, sau khi tính cả hoàn/hủy theo quy tắc nghiệp vụ.

Với đơn hàng:

- Trạng thái chỉ chuyển theo các cạnh được phép trong state machine.
- Không thể vừa `CANCELLED` vừa `SHIPPED` nếu hai trạng thái loại trừ nhau.
- Event xác nhận chỉ tồn tại khi thay đổi trạng thái tương ứng đã commit.

Ví dụ kiểm tra tổng số dư:

```sql
SELECT SUM(balance) AS total_balance
FROM accounts;
```

Không chỉ kiểm tra một vài hàng được cập nhật. Một lỗi lost update có thể giữ từng hàng ở trạng thái hợp lệ nhưng làm tổng số dư sai.

## 9. So sánh với mô hình tuần tự tham chiếu

Với một workload có thể mô tả bằng các thao tác nghiệp vụ, hãy xây dựng một mô hình tuần tự đơn giản trong bộ nhớ. Mô hình áp dụng từng operation theo một thứ tự xác định và tạo ra trạng thái kỳ vọng.

Ví dụ:

```java
final class LedgerModel {
    private final Map<Long, Long> balances = new HashMap<>();

    void transfer(long from, long to, long amount) {
        long fromBalance = balances.get(from);
        long toBalance = balances.get(to);

        if (fromBalance < amount) {
            throw new InsufficientFundsException();
        }

        balances.put(from, fromBalance - amount);
        balances.put(to, toBalance + amount);
    }
}
```

Sau khi test concurrency hoàn tất, có thể so sánh trạng thái database với một hoặc nhiều thứ tự tuần tự hợp lệ của các operation đã được chấp nhận.

Điểm khó là khi request chạy đồng thời, không phải mọi thứ tự tuần tự đều hợp lệ với lịch sử thực tế. Một phép kiểm tra đơn giản như tổng số dư không đổi có thể bỏ sót việc một transfer bị áp dụng hai lần và một transfer khác bị mất nếu tổng tình cờ vẫn bằng nhau. Cần giữ lịch sử operation và kết quả trả về để kiểm tra các quy tắc mạnh hơn.

## 10. Kiểm tra lịch sử giao dịch (history checking)

Một history ghi lại invocation và response của mỗi operation, cùng quan hệ thời gian thực giữa chúng:

```text
request-1: invoke transfer(A, B, 10)
request-2: invoke transfer(B, C, 5)
request-1: response success
request-2: response success
```

Nếu operation 1 hoàn tất trước khi operation 2 bắt đầu, mọi thứ tự tuần tự hợp lệ phải giữ thứ tự đó. Nếu hai operation chồng lấn thời gian, checker có thể xem xét nhiều thứ tự tuần tự, miễn vẫn thỏa các ràng buộc thời gian thực và đặc tả nghiệp vụ.

Với yêu cầu linearizability, mỗi operation phải có thể xem như xảy ra tại một điểm duy nhất giữa invocation và response, đồng thời lịch sử phải tương đương một thực thi tuần tự hợp lệ. Với yêu cầu serializability của database, câu hỏi là kết quả các transaction có tương đương một thứ tự tuần tự hay không; đây là khái niệm về transaction và dependency, không đồng nhất với việc mọi API call có linearizable response.

History checker cần biết:

- Input của từng operation.
- Thời điểm bắt đầu và kết thúc.
- Response thành công, từ chối nghiệp vụ, timeout hay lỗi.
- Transaction nào đã commit hoặc rollback nếu quan sát được.
- Đặc tả trạng thái và quy tắc nghiệp vụ.

Nếu client timeout, không biết server đã commit hay chưa, checker phải coi kết quả là không xác định cho đến khi đối soát. Không tự xem timeout là thất bại chắc chắn.

## 11. Deterministic schedule: tái tạo interleaving quan trọng

Randomized testing có thể tìm thấy một lỗi nhưng rất khó tái hiện nếu không biết thứ tự chính xác. Deterministic schedule cho phép test dừng tại các điểm được chọn rồi điều phối session tiếp tục.

Ví dụ lost update với hai session:

```text
Session A                         Session B
---------                         ---------
BEGIN                             BEGIN
SELECT balance -> 100             SELECT balance -> 100
        |                                  |
        +---- barrier: cả hai đã đọc -----+
UPDATE balance = 90               UPDATE balance = 80
COMMIT                            COMMIT hoặc conflict
```

Nếu ứng dụng dùng read-modify-write không có khóa/version và isolation semantics cho phép, lịch này có thể làm một cập nhật ghi đè cập nhật kia. Barrier đảm bảo cả hai transaction đã đọc trước khi một bên ghi.

Không dùng `Thread.sleep(100)` để giả định transaction kia đã đến một bước. Sleep chỉ trì hoãn; nó không chứng minh trạng thái. Dùng `CountDownLatch`, `CyclicBarrier`, semaphore, channel hoặc test hook để đồng bộ chính xác.

Ví dụ Java:

```java
CountDownLatch bothRead = new CountDownLatch(2);
CountDownLatch allowWrite = new CountDownLatch(1);

Runnable worker = () -> {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        long balance = readBalance(connection, accountId);

        bothRead.countDown();
        bothRead.await();
        allowWrite.await();

        writeBalance(connection, accountId, balance - debit);
        connection.commit();
    } catch (Exception e) {
        throw new RuntimeException(e);
    }
};
```

Test coordinator cần chờ cả hai worker đến barrier rồi mới mở `allowWrite`. Trong triển khai thật, cần xử lý timeout và exception để một worker lỗi không khiến worker còn lại chờ vô hạn; đồng thời rollback và đóng connection trong mọi nhánh.

## 12. Kiểm tra các anomaly cụ thể

Không nên chỉ chạy một workload chung rồi hy vọng nó phát hiện mọi anomaly. Tạo test nhắm vào từng hành vi:

| Anomaly | Lịch/điều kiện cần tạo | Bằng chứng cần kiểm tra |
|---|---|---|
| Dirty read | T1 ghi nhưng chưa commit; T2 đọc cùng hàng | T2 có thấy giá trị chưa commit hay không |
| Non-repeatable read | T1 đọc; T2 cập nhật và commit; T1 đọc lại | Hai lần đọc của T1 có khác nhau theo isolation level không |
| Phantom | T1 range read; T2 chèn hàng thỏa predicate; T1 đọc lại hoặc locking read | Hàng mới có xuất hiện/bị chặn không |
| Lost update | T1 và T2 cùng đọc giá trị; sau đó ghi dựa trên giá trị cũ | Một thay đổi có bị ghi đè mà không phát hiện không |
| Write skew | Hai transaction đọc cùng điều kiện tổng hợp rồi cập nhật các hàng khác nhau | Bất biến tổng hợp có bị vi phạm không |
| Deadlock | T1 khóa X rồi chờ Y; T2 khóa Y rồi chờ X | Deadlock report, nạn nhân và rollback |
| Duplicate effect | Consumer commit hiệu ứng nhưng crash trước ACK; broker giao lại | Effect có bị tạo hai lần không |

Mỗi anomaly cần có fixture và schedule riêng. Randomized test sau đó mở rộng các biến thể của chúng.

## 13. Bounded verification và model checking

Model checking kiểm tra các trạng thái hoặc lịch thực thi của một mô hình theo quy tắc được mô tả. Bounded model checking giới hạn phạm vi, ví dụ số transaction, số bước, số hàng hoặc độ sâu lịch thực thi.

Ưu điểm là trong phạm vi mô hình và giới hạn đã chọn, công cụ có thể khám phá một cách có hệ thống nhiều trạng thái hơn kiểm thử thủ công. Nếu tìm thấy phản ví dụ, nó thường cung cấp một chuỗi bước cụ thể để giải thích vi phạm.

Nhưng bounded verification cũng có giới hạn:

- Chỉ kiểm tra mô hình đã viết; mô hình có thể bỏ sót hành vi database hoặc ứng dụng thật.
- Giới hạn số bước không bao phủ transaction dài hơn hoặc số lượng worker lớn hơn.
- Không gian trạng thái tăng nhanh theo số biến, transaction và lựa chọn scheduling.
- Các giả định về crash, network, timeout, isolation và storage engine phải được mô hình hóa đúng.
- Kết quả “không tìm thấy phản ví dụ trong bound này” không chứng minh mọi thực thi không giới hạn đều an toàn.

Model checking hữu ích để kiểm tra protocol nhỏ, state machine, retry/outbox/inbox hoặc quy tắc cập nhật. Sau đó vẫn cần integration test với database thực để kiểm tra semantics của engine, driver, transaction manager và execution plan.

## 14. Property-based testing cho transaction

Property-based testing tập trung vào thuộc tính phải luôn đúng với nhiều input được sinh tự động. Một test generator có thể tạo danh sách thao tác và đưa chúng vào nhiều worker đồng thời.

Ví dụ properties:

- Tổng số dư không đổi sau các transfer thành công.
- Không có tài khoản âm.
- Mỗi idempotency key chỉ tạo một payment record.
- Mỗi order chỉ có một chuyển trạng thái hợp lệ từ `PENDING` sang `CONFIRMED`.
- Số lượng reserve không vượt số lượng available.
- Mỗi outbox event tham chiếu đến một thay đổi nghiệp vụ đã commit.

Property phải tính đến các kết quả từ chối hợp lệ. Ví dụ, transfer bị từ chối vì không đủ tiền không làm thay đổi số dư; không nên coi mọi request đều phải thành công.

### Shrinking để tìm test nhỏ nhất

Một generator tốt có thể giảm input sau khi tìm thấy lỗi: giảm số transaction, giảm số thao tác, thu hẹp số account, giảm amount hoặc bỏ các bước không cần thiết. Kết quả là một counterexample ngắn dễ hiểu hơn.

Ví dụ workload 500 thao tác phát hiện tổng số dư sai. Shrinking có thể tìm ra chỉ cần hai transaction cùng đọc một hàng và ghi theo thứ tự cụ thể đã đủ tái hiện. Đây là một lợi ích lớn của property-based testing so với stress test chỉ báo lỗi ở cuối.

Không phải framework nào cũng hỗ trợ shrinking lịch thread/database tự động. Có thể cần ghi trace và xây dựng reducer riêng để loại dần thao tác trong khi giữ được failure.

## 15. Randomized testing cần lưu những gì để tái hiện lỗi?

Khi một run thất bại, tối thiểu lưu:

- Seed và phiên bản generator.
- Số worker, số operation và số vòng lặp.
- Input đã sinh hoặc cách tái sinh input.
- Isolation level và autocommit từng connection.
- Database version, schema, index và fixture.
- Connection ID/PID và transaction ID nếu có.
- Trace invocation/response và thứ tự sự kiện được quan sát.
- SQL thực tế, bind parameters, row count và SQLSTATE/vendor code.
- Lock/wait evidence và deadlock report.
- Timeout, retry và các lần thử đã xảy ra.
- Trạng thái dữ liệu trước/sau và kết quả property checker.

Seed một mình không đủ nếu scheduling không deterministic. Trace một mình cũng có thể chưa đủ nếu không biết fixture hoặc schema. Hãy đóng gói các artifact theo một `run_id` và giữ nguyên log gốc.

Ví dụ metadata:

```yaml
run_id: concurrency-random-20261114-0042
seed: 202611140042
generator_version: 3
workers: 8
operations_per_worker: 500
database: mysql
database_version: "8.0.x"
engine: InnoDB
isolation: REPEATABLE READ
autocommit: false
schema_revision: test-schema-7
result: invariant_violation
trace_file: trace.jsonl
fixture_file: fixture.sql
```

Đây là ví dụ định dạng; thay bằng giá trị thực của run. Không ghi mật khẩu, token hoặc dữ liệu thật nhạy cảm vào artifact.

## 16. Kiểm tra tính độc lập và chất lượng của các lần chạy

Nếu test dùng cùng một seed và cùng lịch cố định trong mọi lần chạy, số lần chạy lớn không mở rộng coverage. Ngược lại, nếu mỗi run thay đổi mọi yếu tố cùng lúc, khó xác định nguyên nhân khi kết quả khác.

Nên tổ chức các lớp run:

1. **Regression deterministic:** lịch đã từng gây lỗi, chạy ổn định trong CI.
2. **Seeded randomized:** một danh sách seed cố định để tái lập tập test mỗi build.
3. **Rotating random seeds:** bổ sung seed mới theo ngày/build để khám phá thêm.
4. **Stress profile:** số worker, thời lượng và tỷ lệ hot key đại diện cho tải dự kiến.
5. **Adversarial profile:** cố ý tập trung contention, timeout, duplicate và các giá trị biên.
6. **Fault-injection profile:** crash hoặc ngắt kết nối ở những điểm xác định.

Giữ một số seed ổn định cho regression, đồng thời có seed thay đổi để mở rộng khám phá. Khi tìm được lỗi, chuyển nó thành deterministic regression test với lịch cụ thể hoặc trace rút gọn.

## 17. Không dùng thời gian chạy làm thước đo duy nhất

Một test chạy 30 phút có thể khám phá ít interleaving hơn một test chạy 2 phút nếu nó luôn dùng cùng một lịch hoặc không tạo contention. Thời lượng chỉ là một chỉ số.

Các chỉ số hữu ích hơn:

- Số seed khác nhau đã chạy.
- Số workload/input khác nhau.
- Số transaction và operation được thực hiện.
- Số cặp transaction có khả năng xung đột.
- Tỷ lệ truy cập hot key và range overlap.
- Số lịch/barrier schedule đã thực thi.
- Số deadlock, lock timeout, serialization failure và retry.
- Số property/history check đã hoàn thành.
- Số failure được shrink và tái lập thành công.
- Tỷ lệ run hoàn tất bình thường so với run timeout/harness error.

Không phải mọi chỉ số đều đo trực tiếp coverage của không gian trạng thái. Chúng giúp hiểu test đang khám phá loại hoạt động nào và phát hiện khi workload quá ít cạnh tranh.

## 18. Timeout và lỗi của test harness có thể che giấu nguyên nhân

Khi một test bị timeout, có thể do:

- Database đang chờ lock đúng như kịch bản.
- Deadlock detector hoặc lock timeout chưa trả lỗi.
- Connection pool cạn vì test không đóng connection.
- Thread bị kẹt ở barrier do một worker đã lỗi trước đó.
- Query thực sự chạy chậm.
- Network hoặc database test container bị treo.
- Cleanup chờ transaction chưa kết thúc.

Không gộp tất cả thành “concurrency bug”. Test harness cần timeout riêng cho từng bước và ghi trạng thái worker, connection, query, transaction trước khi kết thúc test.

Khi timeout, cố gắng thu thập evidence trước khi hủy session: thread dump, process list, `pg_stat_activity`, `data_locks`, `data_lock_waits`, transaction age và server log. Sau đó rollback/terminate các session thử nghiệm và reset fixture.

## 19. Kiểm thử với database thật, không chỉ mock

Mock repository có thể kiểm tra logic ứng dụng nhưng không mô phỏng đầy đủ:

- Lock manager và deadlock detector.
- MVCC visibility và undo/version storage.
- Gap/next-key lock hoặc predicate lock.
- Optimizer và index access path.
- Transaction boundary của JDBC driver/connection pool.
- Timeout, isolation level và semantics commit/rollback.

Vì vậy, kiểm thử concurrency của database cần integration test với đúng engine hoặc môi trường tương đương production. Có thể dùng container database để tạo môi trường cô lập, nhưng phải cố định image/version, cấu hình và schema.

Không dùng H2 hoặc một database khác làm bằng chứng thay thế cho MySQL/PostgreSQL locking behavior nếu production chạy InnoDB/PostgreSQL. Các hệ quản trị có semantics khác nhau dù SQL tương tự.

## 20. Kiểm tra kết quả theo mức bảo đảm

Một bộ kiểm thử có thể cung cấp nhiều mức bằng chứng:

| Mức | Điều có thể kết luận | Điều chưa thể kết luận |
|---|---|---|
| Một deterministic schedule thành công | Lịch cụ thể này không vi phạm property được kiểm tra trong điều kiện run | Lịch khác cũng an toàn |
| N randomized runs không lỗi | N run đã thực hiện không phát hiện lỗi | Không có lỗi trong mọi interleaving |
| Stress test đạt SLA | Workload và môi trường đã thử đạt ngưỡng đo được | Tải hoặc phân phối khác cũng đạt |
| History checker chấp nhận trace | Trace quan sát phù hợp với mô hình/đặc tả checker | Mô hình và checker bao phủ mọi hành vi thực tế |
| Bounded model checking không có counterexample | Không tìm thấy vi phạm trong phạm vi bound và giả định đã mô hình hóa | Hệ thống không giới hạn bước/worker luôn đúng |
| Formal proof trên mô hình đầy đủ | Thuộc tính được chứng minh với mô hình và giả định đã nêu | Mọi chi tiết implementation/infra đều khớp mô hình nếu chưa được chứng minh |

Khi báo cáo kết quả, hãy nêu rõ phạm vi: số run, seed, số worker, database version, isolation level, workload, properties và giới hạn. Tránh dùng câu “đã chứng minh không có race condition” chỉ dựa trên stress test.

## 21. Quy trình xây dựng bộ kiểm thử đồng thời

1. Viết các bất biến nghiệp vụ và xác định anomaly cần phát hiện.
2. Xây dựng fixture nhỏ, ổn định và có script reset.
3. Viết deterministic schedule cho các interleaving quan trọng như lost update, deadlock, phantom hoặc duplicate effect.
4. Tạo mô hình tuần tự tham chiếu hoặc history checker cho các operation cần bảo vệ.
5. Thiết kế generator có hot key, dữ liệu biên và nhiều loại thao tác.
6. Lưu seed, generator version, cấu hình session và input của mỗi run.
7. Chạy randomized/stress test trên database đúng engine/version.
8. Kiểm tra invariant và history sau mỗi run, không chỉ kiểm tra exception.
9. Khi thất bại, lưu trace, SQL, bind values, lock evidence và trạng thái dữ liệu.
10. Shrink/replay failure để tạo một lịch deterministic ngắn.
11. Đưa lịch gây lỗi vào regression suite.
12. Bổ sung fault injection và bounded verification cho protocol hoặc state machine có phạm vi phù hợp.
13. Báo cáo coverage và giới hạn của từng lớp test.

## 22. Ví dụ chiến lược test cho chuyển tiền

Giả sử hệ thống có bảng:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(14,2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CHECK (balance >= 0)
) ENGINE = InnoDB;
```

Một chiến lược nhiều lớp có thể là:

### Deterministic test

- Hai transaction cùng đọc một account trước khi ghi.
- Hai transaction chuyển tiền ngược chiều, truy cập account theo thứ tự khác nhau để thử deadlock.
- Một transaction đọc số dư, transaction khác cập nhật và commit, transaction đầu đọc lại ở từng isolation level.
- Kiểm tra rollback khi một trong hai update thất bại.

### Randomized test

- Tạo 10 account với tổng số dư cố định.
- Sinh hàng trăm transfer giữa các account, tập trung 80% request vào một nhóm nhỏ account.
- Chạy 4-16 worker với connection riêng.
- Mỗi transfer có ID duy nhất và ghi debit/credit trong cùng transaction.
- Randomize amount, hướng chuyển, delay và thứ tự lấy khóa.

### Properties sau run

```sql
SELECT SUM(balance) AS total_balance,
       MIN(balance) AS minimum_balance
FROM accounts;
```

- Tổng số dư bằng tổng ban đầu nếu không có phí.
- Minimum balance không âm.
- Mỗi transfer thành công có đúng một debit và một credit.
- Transfer bị rollback không có ledger entry thành công.
- Không có transfer ID trùng tạo nhiều hiệu ứng.

### Replay

Nếu phát hiện tổng số dư sai, lưu seed, trace và transaction log. Thu nhỏ workload đến số transfer tối thiểu, xác định thứ tự đọc/ghi gây lỗi, rồi viết deterministic regression test. Không chỉ tăng số lần chạy cho đến khi lỗi xuất hiện lần nữa.

## 23. Những kết luận không nên rút ra từ kiểm thử hữu hạn

| Quan sát | Kết luận quá mức | Kết luận phù hợp |
|---|---|---|
| 100 run không deadlock | Hệ thống không thể deadlock | 100 run này không phát hiện deadlock với workload/config đã dùng |
| Random seed không tìm ra lost update | Lost update không tồn tại | Generator hoặc lịch đã thử chưa tạo được điều kiện gây lost update |
| Stress test chạy 1 giờ không lỗi | Mọi tải production đều an toàn | Profile tải đó đạt kết quả trong môi trường và thời gian thử |
| Một schedule được kiểm tra thành công | Mọi interleaving đều đúng | Schedule cụ thể đó thỏa property được kiểm tra |
| Không có exception | Dữ liệu đúng | Cần kiểm tra state invariants và history; lỗi logic có thể không ném exception |
| Mock test qua | Database thật có cùng locking behavior | Mock chỉ kiểm tra logic trong phạm vi mock; cần integration test với engine thật |
| Cùng seed chạy lại không tái hiện | Lỗi đã biến mất | Input có thể giống nhưng lịch scheduler/database khác; cần lưu trace và barrier schedule |

## 24. Tự kiểm tra

**Nếu một lỗi có xác suất xuất hiện 0,1% trong mỗi run, chạy 100 lần không thấy lỗi có chứng minh hệ thống an toàn không?**

Không. Ngay cả trong giả định độc lập với xác suất cố định, vẫn có xác suất đáng kể không bắt gặp lỗi. Trong concurrency test, các run còn có thể tương quan và không khám phá lịch đa dạng.

**Seed có tái tạo chính xác interleaving của thread không?**

Không nhất thiết. Seed tái tạo chuỗi input ngẫu nhiên; scheduler, I/O, connection pool và database timing vẫn có thể tạo lịch khác. Cần lưu trace hoặc dùng deterministic schedule để replay.

**Vì sao random generator nên ưu tiên hot key?**

Nếu mọi worker luôn thao tác trên các hàng khác nhau, contention thấp và nhiều lỗi khóa/đồng thời khó xuất hiện. Hot key làm tăng xác suất các transaction cạnh tranh cùng tài nguyên.

**Không có exception có đủ chứng minh dữ liệu đúng không?**

Không. Lost update, duplicate effect hoặc vi phạm bất biến có thể xảy ra mà mọi câu lệnh đều trả thành công. Cần kiểm tra invariant và lịch sử nghiệp vụ.

**Khi random test tìm được lỗi, nên làm gì tiếp theo?**

Lưu seed, generator version, fixture, cấu hình, trace, SQL và trạng thái cuối; sau đó shrink/replay để tìm lịch nhỏ nhất và chuyển thành deterministic regression test.

**Bounded model checking không tìm thấy lỗi có nghĩa mọi lịch thực thi đều an toàn không?**

Không. Kết quả chỉ áp dụng cho mô hình, giả định và giới hạn số bước/trạng thái đã kiểm tra. Cần nêu rõ bound và những hành vi không được mô hình hóa.

**Vì sao cần chạy integration test với đúng database engine?**

Vì mock hoặc database khác có thể không mô phỏng đúng MVCC, lock manager, gap lock, deadlock detector, optimizer và transaction semantics của engine production.

Kiểm thử ngẫu nhiên và kiểm chứng hữu hạn là công cụ tìm lỗi, không phải lời chứng nhận tuyệt đối rằng mọi lịch đồng thời đều an toàn. Hãy kết hợp **lịch xác định cho các trường hợp quan trọng, random/stress để mở rộng khám phá, invariant/history checking để đánh giá kết quả và trace/replay để biến lỗi thành regression test**. Khi báo cáo, luôn nêu số run, seed, cấu hình, workload và phạm vi đã kiểm tra; sự rõ ràng về giới hạn giúp kết quả có giá trị kỹ thuật và có thể tái lập.

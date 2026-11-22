# Giảm lịch thực thi lỗi thành ca kiểm thử tối thiểu

Khi một lỗi tương tranh xuất hiện, log thường cho thấy nhiều request, thread, câu SQL và transaction chạy xen kẽ. Một lần chạy có thể thất bại, nhưng lần chạy tiếp theo lại thành công vì thứ tự thread thay đổi. Muốn hiểu và ngăn lỗi, cần biến lịch thực thi phức tạp đó thành một **ca kiểm thử tối thiểu có thể tái hiện** (*minimal reproducible concurrency test*).

Giảm lịch thực thi là quá trình loại bỏ những thao tác, transaction, hàng dữ liệu và yếu tố môi trường không cần thiết, trong khi vẫn giữ được quan hệ thứ tự gây ra lỗi. Kết quả mong muốn là một test nhỏ, chạy trên nhiều connection thật, điều khiển được các điểm giao nhau và thất bại theo cùng một điều kiện có ý nghĩa.

Điều quan trọng nhất là giữ nguyên **nguyên nhân tương tranh**. Nếu lỗi xảy ra vì `T1` đọc trước khi `T2` ghi, rồi `T1` ghi dựa trên giá trị cũ, test rút gọn phải giữ được thứ tự đó. Chỉ xóa bớt dòng SQL cho đến khi test “có vẻ đơn giản” có thể vô tình loại bỏ race condition hoặc tạo ra một lỗi khác.

## 1. Lịch thực thi là gì?

Một lịch thực thi (*execution schedule*) mô tả thứ tự các thao tác của nhiều transaction. Các thao tác trong cùng transaction vẫn giữ thứ tự chương trình, nhưng thao tác của những transaction khác nhau có thể xen kẽ.

Giả sử hai transaction cùng đọc và cập nhật số dư:

```text
T1: BEGIN
T1: READ balance = 100
T1: tính newBalance = 110
T1: WRITE balance = 110
T1: COMMIT

T2: BEGIN
T2: READ balance = 100
T2: tính newBalance = 80
T2: WRITE balance = 80
T2: COMMIT
```

Nếu chạy lần lượt như trên, `T2` có thể đọc giá trị sau commit của `T1` và tính toán dựa trên `110`. Nhưng lịch lỗi có thể xen kẽ:

```text
T1: BEGIN
T1: READ balance = 100

T2: BEGIN
T2: READ balance = 100

T1: WRITE balance = 110
T1: COMMIT

T2: WRITE balance = 80
T2: COMMIT
```

Hai transaction cùng dựa trên `100`; cập nhật của `T1` bị ghi đè. Nếu cả hai ý định là cộng `10` và trừ `20`, kết quả đúng khi áp dụng cả hai là `90`, nhưng lịch lỗi để lại `80`.

Có thể ký hiệu rút gọn:

```text
T1: R(x) ---------------- W(x=110) -- C
T2:       R(x) ---------------------- W(x=80) -- C
```

Trong đó `R` là đọc, `W` là ghi và `C` là commit. Lịch thực thi mô tả thứ tự thực tế; nó không nhất thiết là thứ tự mà test code đã dự định nếu test không có cơ chế đồng bộ.

## 2. Phân biệt lịch lỗi với triệu chứng lỗi

Một test rút gọn cần biết chính xác điều gì được xem là thất bại. Các triệu chứng có thể là:

- Giá trị cuối không thỏa bất biến, ví dụ số dư cuối không bằng kết quả của cả hai phép cập nhật.
- Hai transaction cùng cập nhật một version nhưng cả hai đều báo thành công.
- Hai worker cùng claim một job hoặc cùng xử lý một đơn hàng.
- Một transaction đọc dữ liệu chưa commit của transaction khác.
- Một transaction bị chặn quá thời gian quy định.
- Database phát hiện deadlock hoặc serialization failure.
- Một lịch đọc tạo ra kết hợp dữ liệu chưa từng tồn tại nhất quán.
- Một transaction bị từ chối nhưng ứng dụng lại tiếp tục tạo tác dụng phụ.

Không nên định nghĩa oracle đơn giản là “test có exception”. Exception có thể là lỗi mong đợi, chẳng hạn optimistic lock conflict hoặc deadlock victim. Cần xác định đúng hợp đồng:

| Tình huống | Oracle nên kiểm tra |
|---|---|
| Lost update | Giá trị cuối phải phản ánh tất cả phép cập nhật đã được chấp nhận. |
| Optimistic locking | Với cùng expected version, tối đa một transaction cập nhật thành công. |
| Pessimistic locking | Transaction thứ hai phải chờ hoặc nhận timeout theo cấu hình cho đến khi khóa được nhả. |
| Deadlock | Có một transaction bị chọn làm victim, transaction còn lại có thể tiếp tục và dữ liệu cuối vẫn hợp lệ. |
| Unique constraint race | Chỉ một hàng có khóa duy nhất đó được commit. |
| Write skew | Trạng thái cuối không được vi phạm bất biến liên hàng. |
| Retry | Toàn bộ transaction được chạy lại theo chính sách và không nhân đôi tác dụng phụ. |

Oracle nên kiểm tra cả kết quả của từng worker, exception hoặc row count, trạng thái cuối trong database và các tác dụng phụ quan trọng như history/outbox. Chỉ kiểm tra trạng thái thread hoặc thời gian chờ không đủ để chứng minh tính đúng đắn.

## 3. Bắt đầu từ bằng chứng của một lần chạy lỗi

Trước khi rút gọn, cần lưu lại đủ thông tin để biết lịch nào đã xảy ra. Nếu chỉ có thông báo “đôi khi bị deadlock”, chưa có đủ dữ liệu để tạo test có chủ đích.

Thu thập những thông tin sau:

1. **Database và phiên bản:** engine, version, storage engine/table type, cấu hình row versioning và các tùy chọn liên quan.
2. **Transaction context:** isolation level, autocommit, transaction boundary và timeout.
3. **Session identity:** connection/session ID của từng worker.
4. **Statement:** SQL thực tế, bind values, thứ tự gọi và row count.
5. **Thời điểm:** lúc bắt đầu transaction, lúc đọc, lúc yêu cầu ghi/khóa, lúc commit/rollback và lúc nhận lỗi.
6. **Lock/wait evidence:** lock mode, resource, owner, waiter, blocking session hoặc deadlock graph nếu có.
7. **Dữ liệu đầu vào:** hàng và giá trị ban đầu liên quan đến lỗi.
8. **Kết quả:** trạng thái cuối, lỗi của từng transaction và tác dụng phụ đã phát sinh.

Không cần ghi toàn bộ payload nhạy cảm. Có thể dùng ID giả, giá trị đã ẩn danh và chỉ giữ những cột ảnh hưởng đến điều kiện tương tranh. Tuy nhiên, không được xóa các trường tham gia predicate, index, constraint hoặc quyết định nghiệp vụ nếu chúng có thể thay đổi lock footprint.

### Dùng trace ID và transaction label

Mỗi worker nên có tên dễ nhận diện như `worker-A`, `worker-B`, một request ID hoặc correlation ID. Gắn nhãn vào log và test output để ghép các câu SQL thành đúng transaction.

Ví dụ bảng lịch:

| Thứ tự quan sát | Worker | Session | Transaction | Thao tác | Kết quả |
|---:|---|---|---|---|---|
| 1 | A | 81 | T1 | `BEGIN` | OK |
| 2 | A | 81 | T1 | Đọc account 10 | `100` |
| 3 | B | 94 | T2 | `BEGIN` | OK |
| 4 | B | 94 | T2 | Đọc account 10 | `100` |
| 5 | A | 81 | T1 | Ghi `110` | OK |
| 6 | B | 94 | T2 | Ghi `80` | OK |
| 7 | A/B | ... | ... | Commit | Cả hai thành công |

Bảng này là ví dụ minh họa. Với deadlock, cần ghi cả tài nguyên đang giữ và đang chờ; thứ tự log từ nhiều thread có thể không phản ánh chính xác thứ tự database cấp khóa. Dùng database wait metadata hoặc deadlock graph để xác minh.

## 4. Giữ nguyên quan hệ happens-before

Khi rút gọn lịch, cần giữ các quan hệ thứ tự bắt buộc và những điểm giao nhau làm lỗi xuất hiện.

**Happens-before** là quan hệ cho biết một thao tác phải xảy ra trước một thao tác khác. Trong test, quan hệ này có thể đến từ:

- Thứ tự các câu lệnh trong cùng transaction.
- Một worker báo đã đọc xong trước khi worker khác được phép ghi.
- Một transaction lấy khóa trước khi transaction khác yêu cầu khóa.
- Một commit hoàn tất trước khi transaction khác đọc trạng thái đã commit.
- Một message được lưu vào database trước khi consumer ACK.

Ví dụ, test lost update cần giữ hai quan hệ:

```text
T1: READ(x)  happens-before  T1: WRITE(x)
T2: READ(x)  happens-before  T2: WRITE(x)
```

và tạo overlap để:

```text
T1: READ(x)  happens-before  T2: WRITE(x)
T2: READ(x)  happens-before  T1: WRITE(x)
```

Hai transaction đều đọc trước khi bất kỳ transaction nào ghi. Barrier sau hai câu đọc là cách thể hiện trực tiếp quan hệ này.

Ngược lại, nếu test deadlock cần `T1` giữ khóa A và `T2` giữ khóa B trước khi yêu cầu khóa còn lại, barrier phải nằm sau hai lần lấy khóa đầu tiên. Đặt barrier sau lần yêu cầu khóa thứ hai sẽ sai: một worker có thể bị block và không tới được barrier.

## 5. Tách lịch thực thi khỏi thời gian ngẫu nhiên

Một lần chạy lỗi có thể xảy ra vì scheduler tình cờ sắp xếp thread theo thứ tự phù hợp. Rút gọn tốt là chuyển sự trùng hợp về thời gian thành các điểm đồng bộ rõ ràng.

Không nên dùng:

```java
Thread.sleep(100);
```

để giả định transaction kia đã đọc hoặc đã lấy khóa. Thời gian sleep không tạo ra quan hệ happens-before giữa hai thao tác. Máy CI nhanh/chậm, tải CPU và scheduler có thể làm kết quả thay đổi.

Thay vào đó, dùng:

- `CountDownLatch` để báo một worker đã đến điểm xác định.
- `CyclicBarrier` để buộc một nhóm worker cùng vượt qua điểm đồng bộ.
- `Phaser` cho lịch có nhiều pha.
- `Semaphore` để giới hạn số worker được tiếp tục.
- `Future.get(timeout, unit)` để chờ kết quả với giới hạn.

Ví dụ rút gọn cho lost update:

```java
CyclicBarrier bothRead = new CyclicBarrier(2);

// Trong từng worker, sau khi SELECT và đóng ResultSet:
BigDecimal oldValue = readBalance(connection);
bothRead.await(5, TimeUnit.SECONDS);
writeAbsoluteBalance(connection, oldValue.add(delta));
```

Barrier chỉ có ý nghĩa khi mỗi worker đã dùng connection riêng và transaction vẫn mở. Nếu `readBalance` chạy ở autocommit rồi connection được trả về pool trước khi ghi, test không còn giữ cùng transaction như lịch đã mô tả.

## 6. Rút gọn theo từng chiều

Không nên cùng lúc xóa nhiều transaction, bảng và câu lệnh vì khi test không còn tái hiện, sẽ không biết thay đổi nào đã loại bỏ nguyên nhân. Giảm từng chiều và chạy lại oracle sau mỗi thay đổi.

### Giảm số transaction

Bắt đầu với toàn bộ transaction tham gia lỗi. Sau đó thử bỏ từng transaction không nằm trong chu trình hoặc không ảnh hưởng đến bất biến. Nếu lỗi vẫn tái hiện, transaction đó không cần cho test tối thiểu.

Ví dụ một deadlock graph có năm transaction nhưng chu trình chỉ gồm `T1`, `T2` và `T3`. Có thể thử loại `T4`, `T5` trước. Nếu lỗi vẫn còn, giữ lại ba transaction trong test. Không mặc định chỉ hai transaction mới tạo được mọi deadlock; chu trình có thể cần ba hoặc nhiều transaction.

### Giảm số statement

Trong mỗi transaction, bỏ từng statement rồi chạy lại test. Giữ lại những câu lệnh tạo hoặc giữ lock, đọc dữ liệu dùng cho quyết định, ghi dữ liệu hoặc kết thúc transaction. Các câu log, truy vấn hiển thị và thao tác không liên quan có thể loại bỏ.

Với mỗi statement bị xóa, hỏi:

- Nó có lấy hoặc nhả khóa không?
- Nó có thay đổi index entry hoặc kích hoạt constraint/trigger không?
- Nó có ảnh hưởng đến snapshot hoặc transaction state không?
- Nó có tạo giá trị mà câu lệnh sau dùng để tính toán không?
- Nó có thay đổi thứ tự truy cập bảng/hàng không?

Một `SELECT` tưởng như chỉ để log vẫn có thể thiết lập snapshot hoặc làm thay đổi lịch khóa trong một số hệ thống. Không xóa theo tên gọi; xác minh vai trò thực tế.

### Giảm số hàng và dữ liệu fixture

Giảm fixture xuống những hàng cần thiết để tái hiện lỗi. Với deadlock hai hàng, có thể chỉ cần hai hàng khóa A và B. Với unique conflict, có thể chỉ cần một khóa duy nhất và hai transaction insert cùng giá trị. Với write skew, cần giữ đủ hàng để thể hiện bất biến liên hàng.

Giữ nguyên:

- Giá trị nằm trong predicate `WHERE`.
- Các cột thuộc index được sử dụng.
- Khóa chính, unique key và foreign key có liên quan.
- Trạng thái nguồn và điều kiện nghiệp vụ.
- Kiểu dữ liệu, collation hoặc giá trị `NULL` nếu chúng ảnh hưởng đến semantics.

Có thể thay dữ liệu nghiệp vụ phức tạp bằng giá trị nhỏ như `id = 1`, `balance = 100`, nhưng đừng thay schema hoặc index nếu chúng là một phần của nguyên nhân.

### Giảm số thread và worker phụ

Một test có 20 worker có thể được giảm xuống 2 hoặc 3 nếu chỉ có từng ấy transaction trong chu trình lỗi. Nhưng cần phân biệt worker xử lý nghiệp vụ với worker observer. Observer có thể cần connection thứ ba để đọc lock metadata; nếu bỏ nó, test vẫn có thể tái hiện nhưng mất khả năng chứng minh database đang chờ.

### Giảm thời gian và timeout

Timeout dài có thể được giảm để test chạy nhanh hơn, nhưng không được thấp đến mức cắt ngang lịch hợp lệ trước khi database có cơ hội phát hiện lỗi. Tách rõ:

- Barrier timeout: thời gian chờ worker khác tới điểm đồng bộ.
- Pool acquisition timeout: thời gian chờ mượn connection.
- Lock timeout: thời gian chờ tài nguyên khóa.
- Statement/query timeout: giới hạn câu SQL.
- Test deadline: giới hạn toàn bộ ca kiểm thử.

Một test timeout vì pool cạn không chứng minh có database deadlock. Một test timeout khi barrier thiếu participant cũng không phải lỗi transaction.

## 7. Delta debugging: loại bỏ từng phần có kiểm soát

Delta debugging là kỹ thuật chia đầu vào hoặc chuỗi thao tác thành các phần, thử loại bỏ một phần rồi kiểm tra xem lỗi còn xuất hiện không.

Quy trình đơn giản:

1. Lưu một lịch lỗi đã tái hiện được.
2. Chia danh sách thao tác thành các nhóm.
3. Bỏ một nhóm và chạy lại test.
4. Nếu lỗi vẫn còn, giữ phiên bản đã rút gọn.
5. Nếu lỗi biến mất, khôi phục nhóm đó và thử nhóm khác hoặc chia nhỏ hơn.
6. Lặp lại cho đến khi không thể loại thêm thao tác nào mà vẫn giữ cùng lỗi.

Ví dụ, một transaction có 16 statement. Có thể thử bỏ nửa sau, rồi nửa đầu, sau đó từng nhóm nhỏ hơn. Tuy nhiên, với concurrency, không chỉ đầu vào mà cả quan hệ thứ tự cũng quan trọng. Khi xóa một thao tác, phải xem nó có thay đổi vị trí tương đối của các thao tác còn lại hay không.

Một lịch có thể biểu diễn thành các sự kiện:

```text
e1 = T1 BEGIN
e2 = T1 READ(A)
e3 = T2 BEGIN
e4 = T2 READ(A)
e5 = T1 WRITE(A)
e6 = T1 COMMIT
e7 = T2 WRITE(A)
e8 = T2 COMMIT
```

Delta debugging thử bỏ từng sự kiện không bắt buộc, nhưng phải giữ thứ tự nội bộ của mỗi transaction. Nếu bỏ `e2` mà `T1` không còn tính giá trị từ snapshot cũ, test không còn là cùng lỗi.

### Không nhầm “minimal” với “ít dòng nhất”

Một test tối thiểu không nhất thiết có ít dòng code nhất. Nó là test không còn thành phần nào có thể bỏ mà vẫn giữ cùng điều kiện lỗi và oracle. Một vài dòng setup hoặc barrier có thể cần thiết để làm lịch lặp lại được, dù chúng không xuất hiện trong lịch production.

## 8. Giữ nguyên môi trường database khi rút gọn

Lỗi concurrency có thể phụ thuộc vào chi tiết triển khai của database. Rút gọn test bằng cách đổi engine, isolation level hoặc index có thể làm lỗi biến mất vì đã thay đổi hệ thống đang được kiểm tra.

Giữ lại hoặc ghi rõ:

- Database engine và phiên bản.
- Isolation level từng transaction.
- Autocommit và transaction boundary.
- Schema, index, constraint và trigger liên quan.
- Kiểu dữ liệu và collation của cột tham gia predicate.
- Driver và cấu hình connection pool khi chúng ảnh hưởng hành vi.
- Row versioning, gap lock, predicate lock hoặc các tùy chọn engine liên quan.

Ví dụ, một deadlock InnoDB liên quan đến gap lock có thể biến mất nếu đổi isolation level hoặc thêm index. Điều đó có thể hữu ích khi thiết kế giải pháp, nhưng không phải là một phép rút gọn trung tính. Test tối thiểu để tái hiện nguyên nhân phải giữ điều kiện tạo gap lock.

Tương tự, test trên H2 không thay thế được test trên PostgreSQL, MySQL InnoDB hoặc SQL Server khi cần xác nhận lock semantics cụ thể. Rút gọn code harness, không tùy tiện thay đổi hệ quản trị đang là một phần của lỗi.

## 9. Ví dụ rút gọn lỗi lost update

Giả sử hệ thống thật có nhiều bảng, audit, cache, message và 8 worker. Log cho thấy hai request cập nhật cùng tài khoản. Để tìm nguyên nhân, rút gọn theo các bước.

### Bước 1: xác định bất biến

Hai lệnh nghiệp vụ là cộng `10` và trừ `20`. Nếu cả hai được chấp nhận, số dư cuối phải là `90` so với ban đầu `100`.

### Bước 2: giữ hai transaction liên quan

Loại các worker không chạm tài khoản này. Còn `T1` và `T2`, mỗi transaction có connection riêng.

### Bước 3: giữ phần đọc và ghi gây race

Rút gọn SQL thành:

```sql
SELECT balance FROM accounts WHERE id = 1;
UPDATE accounts SET balance = :computedValue WHERE id = 1;
```

Giữ logic tính `computedValue` ở ứng dụng từ giá trị đã đọc. Không thay bằng `balance = balance + :delta`, vì câu lệnh đó loại bỏ chính mẫu đọc-sửa-ghi gây lost update.

### Bước 4: điều khiển lịch bằng barrier

```text
T1 đọc 100 ----+
               +---- barrier ---- cả hai được phép ghi
T2 đọc 100 ----+
```

Sau barrier, T1 ghi `110`, T2 ghi `80`. Không cần `sleep` hoặc tải lớn để tạo race.

### Bước 5: giữ oracle

Đọc bằng connection mới sau khi cả hai transaction kết thúc. Test lỗi nếu một kết quả đã được chấp nhận nhưng giá trị cuối không bằng `90`.

### Bước 6: tạo test đối chứng

Thay cập nhật tuyệt đối bằng:

```sql
UPDATE accounts
SET balance = balance + :delta
WHERE id = 1;
```

Giữ nguyên hai connection và barrier tương đương. Kết quả mong đợi là `90`. Test đối chứng cho thấy thay đổi câu SQL giải quyết mẫu lost update trong tình huống này.

## 10. Ví dụ rút gọn deadlock

Giả sử deadlock production xảy ra trong một use case cập nhật nhiều bảng, deadlock graph cho thấy chu trình chỉ giữa hai transaction và hai hàng `A`, `B`.

Lịch tối thiểu có thể là:

```text
T1: BEGIN
T1: UPDATE row A        -- giữ X(A)

T2: BEGIN
T2: UPDATE row B        -- giữ X(B)

T1: UPDATE row B        -- chờ T2
T2: UPDATE row A        -- chờ T1
```

Test harness:

1. Dùng hai connection độc lập.
2. T1 khóa hàng A; T2 khóa hàng B.
3. Mỗi worker báo latch sau khi lấy khóa đầu tiên.
4. Test runner đợi cả hai latch.
5. Cho T1 và T2 yêu cầu khóa còn lại.
6. Chờ database chọn victim trong timeout hữu hạn.
7. Xác nhận transaction còn lại hoàn tất sau khi victim rollback.

Không assert worker cụ thể luôn là victim. Không dùng barrier sau hai câu UPDATE thứ hai vì một worker sẽ bị chặn và không tới được barrier. Khi rút gọn từ deadlock graph, giữ index hoặc foreign key nếu resource thực tế là index key thay vì chỉ là row lock.

## 11. Ví dụ rút gọn write skew

Giả sử quy tắc là luôn có ít nhất một bác sĩ trực. Hai transaction cùng đọc hai hàng đang trực, sau đó mỗi transaction tắt một hàng khác nhau.

```text
Ban đầu: doctor A = on_call, doctor B = on_call

T1: đọc COUNT(on_call) = 2
T2: đọc COUNT(on_call) = 2
             barrier
T1: UPDATE doctor A -> off_call
T2: UPDATE doctor B -> off_call
T1: COMMIT
T2: COMMIT

Kết quả: không còn ai trực
```

Để tối thiểu hóa test, có thể bỏ các bảng không liên quan và chỉ giữ hai hàng bác sĩ. Nhưng không thể bỏ một trong hai hàng hoặc bỏ truy vấn kiểm tra tổng, vì khi đó không còn cùng bất biến và phụ thuộc đọc-ghi tạo write skew.

Oracle phải kiểm tra `COUNT(*) WHERE on_call = TRUE >= 1` sau khi cả hai transaction kết thúc. Nếu mục tiêu là chứng minh Serializable ngăn write skew, chạy cùng lịch trên mức Serializable của engine và xác nhận ít nhất một transaction bị từ chối hoặc kết quả cuối giữ bất biến.

## 12. Rút gọn một lỗi blocking hoặc timeout

Nếu lỗi là request chờ quá lâu, trước tiên phân loại nơi chờ:

- Chờ lấy connection từ pool.
- Chờ database lock.
- Chờ barrier/latch trong ứng dụng.
- Chờ I/O hoặc network.
- Chờ thread scheduler hoặc executor queue.

Không rút gọn một pool exhaustion thành “database lock timeout”. Hai lỗi có nguyên nhân và giải pháp khác nhau.

Để tạo test tối thiểu cho blocking:

1. Một transaction A lấy khóa trên đúng hàng hoặc phạm vi.
2. A giữ transaction mở bằng latch điều khiển.
3. Transaction B trên connection khác yêu cầu khóa xung đột.
4. Observer xác nhận B đang chờ đúng resource của A.
5. A commit/rollback.
6. B tiếp tục hoặc nhận timeout theo policy.

Nếu test chỉ kiểm tra `Future` của B chưa hoàn tất, cần thêm bằng chứng B đã vào database và đang chờ lock. Nếu B còn chưa mượn được connection, test đang kiểm tra pool chứ không phải blocking trong database.

## 13. Giữ lại các điều kiện môi trường tối thiểu

Một test tối thiểu vẫn cần môi trường đủ để tái hiện cùng semantics:

| Thành phần | Giữ lại điều gì? | Có thể loại bỏ điều gì? |
|---|---|---|
| Database | Đúng engine/version cần kiểm tra | Các service phụ không liên quan |
| Schema | Bảng, cột, index, constraint và trigger tham gia lỗi | Bảng không nằm trong đường truy cập hoặc bất biến |
| Dữ liệu | Số hàng tối thiểu và giá trị kích hoạt predicate | Dữ liệu lịch sử không ảnh hưởng |
| Transaction | Isolation, autocommit, begin/commit/rollback | Các bước không liên quan đến lịch lỗi |
| Connection | Một connection cho mỗi transaction độc lập | Connection của các worker không tham gia lỗi |
| Đồng bộ | Barrier/latch tạo đúng quan hệ thứ tự | Sleep và tải ngẫu nhiên không cần thiết |
| Oracle | Kết quả database và lỗi có ý nghĩa | Log/metric không cần cho xác định kết quả, nhưng có thể giữ để chẩn đoán |
| Hạ tầng ứng dụng | Pool đủ connection và transaction manager cần thiết | Cache, UI, gateway nếu không ảnh hưởng lỗi |

Nếu index hoặc constraint là nguyên nhân, nó thuộc phần schema tối thiểu và không được bỏ chỉ để bảng đơn giản hơn. Nếu connection pool không phải nguyên nhân, có thể thay pool production bằng pool nhỏ cho test nhưng vẫn phải cấp đủ connection đồng thời.

## 14. Phân biệt rút gọn test với sửa lỗi

Trong quá trình giảm lịch, có thể thử một thay đổi để xác định nguyên nhân: thêm conditional update, đổi thứ tự khóa, bật Serializable hoặc thêm unique constraint. Nhưng cần giữ riêng hai phiên bản:

- **Reproducer:** ca kiểm thử tối thiểu vẫn thể hiện lỗi ban đầu.
- **Regression test:** ca kiểm thử cùng lịch hoặc cùng bất biến nhưng xác nhận giải pháp mới ngăn lỗi.

Không chỉnh sửa reproducer đến mức nó không còn tái hiện lỗi rồi kết luận đã hiểu nguyên nhân. Hãy giữ một test có thể thất bại trên implementation cũ và pass trên implementation đã sửa, nếu có thể chạy cả hai phiên bản.

Ví dụ lost update:

| Phiên bản | Câu cập nhật | Kết quả mong đợi |
|---|---|---|
| Reproducer cũ | `SET balance = :computedFromOldRead` | Có thể mất một cập nhật theo lịch đã đồng bộ. |
| Regression mới | `SET balance = balance + :delta` hoặc optimistic version | Cả hai thay đổi được áp dụng hoặc một transaction bị từ chối có kiểm soát. |

Với deadlock, test regression có thể xác nhận thứ tự khóa mới loại bỏ chu trình đã tái hiện, nhưng vẫn nên xử lý deadlock còn có thể phát sinh ở những lịch khác.

## 15. Làm test ổn định trong CI

Một test chỉ chạy được trên laptop của người phát triển chưa đủ. Để giảm flaky test:

- Dùng barrier/latch thay cho sleep.
- Dùng timeout cho barrier, pool acquisition, query, lock và toàn test.
- Đặt tên worker/session rõ ràng.
- Dùng fixture có ID riêng cho mỗi test.
- Commit fixture trước khi worker mở transaction.
- Đảm bảo pool có đủ connection cho worker và observer.
- Dùng database engine/version tương thích với môi trường cần xác nhận.
- Cleanup transaction và connection trong mọi nhánh, kể cả khi assertion thất bại.
- Thu thập lock graph hoặc wait metadata khi test timeout/deadlock.
- Không assert thứ tự winner/victim nếu engine không cam kết thứ tự đó.
- Chạy test lặp lại nhiều lần để phát hiện race còn phụ thuộc scheduler.

Có thể chạy test stress nhiều lần sau khi đã có reproducer tối thiểu. Stress test giúp tìm thêm lịch lỗi, nhưng không thay thế test deterministic. Một reproducer nhỏ nên xác định rõ điểm đồng bộ và oracle để thất bại có thể giải thích.

## 16. Mẫu checklist giảm lịch thực thi

Khi nhận một lỗi concurrency, hãy tiến hành theo trình tự:

1. **Chốt triệu chứng:** bất biến nào bị phá, transaction nào thất bại hoặc request nào bị chặn?
2. **Thu thập lịch:** session ID, SQL, transaction boundary, isolation level, lock/wait graph và dữ liệu ban đầu.
3. **Xác định chu trình hoặc race:** thao tác đọc/ghi nào tạo phụ thuộc, tài nguyên nào bị tranh chấp?
4. **Tạo harness nhiều connection:** mỗi worker có connection và transaction riêng.
5. **Thay timing ngẫu nhiên bằng đồng bộ:** đặt barrier/latch đúng điểm đọc, lấy khóa hoặc yêu cầu ghi.
6. **Thiết lập oracle:** kiểm tra row count, exception, trạng thái cuối và tác dụng phụ.
7. **Giảm transaction:** bỏ worker không tham gia lỗi, nhưng giữ đủ transaction trong chu trình.
8. **Giảm statement:** loại từng câu không cần thiết, chạy lại sau mỗi thay đổi.
9. **Giảm fixture/schema:** bỏ hàng/bảng không ảnh hưởng, giữ index/constraint/predicate liên quan.
10. **Giữ môi trường:** đúng engine, version, isolation và cấu hình cần thiết.
11. **Kiểm tra tính lặp lại:** chạy nhiều lần và xác nhận cùng lỗi/điều kiện thất bại.
12. **Tạo regression test:** giữ reproducer cũ và xác nhận giải pháp mới bảo vệ bất biến.

Sau mỗi bước giảm, chỉ giữ thay đổi nếu cùng lỗi vẫn xuất hiện. Nếu lỗi biến mất, khôi phục phần vừa bỏ và chia nhỏ hơn. Ghi lại những giả định và giới hạn môi trường để người khác có thể chạy lại.

## 17. Những sai lầm thường gặp

- **Xóa thao tác mà không kiểm tra quan hệ thứ tự:** test không còn tái hiện cùng race.
- **Dùng sleep để ép lịch:** thời gian không bảo đảm worker đã đọc hoặc lấy khóa.
- **Chia sẻ một connection giữa nhiều thread:** không còn nhiều transaction độc lập.
- **Rút gọn bằng cách đổi database engine:** semantics khóa có thể thay đổi, lỗi biến mất vì môi trường khác.
- **Bỏ index hoặc constraint có liên quan:** lock footprint và thứ tự kiểm tra thay đổi.
- **Chỉ giữ exception làm oracle:** có thể nhầm lỗi mong đợi với lỗi thực sự.
- **Assert cứng deadlock victim:** lựa chọn victim thường không phải hợp đồng ổn định.
- **Không đặt timeout:** test có thể treo khi barrier thiếu participant hoặc transaction chờ khóa.
- **Bỏ observer rồi kết luận worker đang chờ database:** worker có thể đang chờ pool hoặc executor.
- **Rút gọn fixture quá mức:** bỏ hàng thứ hai hoặc predicate có thể làm mất write skew/range conflict.
- **Sửa reproducer trong khi đang giảm lịch:** không còn biết thay đổi nào làm lỗi biến mất.
- **Chỉ chạy một lần:** một lịch tình cờ thành công không chứng minh test ổn định.

## 18. Kết luận

Giảm lịch thực thi lỗi là quá trình tìm tập thao tác nhỏ nhất vẫn giữ nguyên quan hệ tương tranh và điều kiện thất bại. Bắt đầu bằng việc ghi lại session, transaction, SQL, isolation level, lock/wait evidence và trạng thái dữ liệu. Sau đó chuyển lịch ngẫu nhiên thành lịch có thể điều khiển bằng barrier/latch, mỗi transaction dùng một connection thật.

Giảm từng chiều: số transaction, statement, hàng dữ liệu và thành phần hạ tầng không liên quan. Sau mỗi thay đổi, chạy lại cùng oracle và chỉ giữ phần đã bỏ nếu lỗi vẫn tái hiện. Giữ nguyên engine, isolation level, index, constraint và các quan hệ happens-before có liên quan. Một ca kiểm thử tối thiểu tốt phải chạy lặp lại được, chứng minh có các session độc lập, kiểm tra trạng thái cuối và có thể làm regression test sau khi sửa lỗi. Mục tiêu là biến một sự cố khó tái hiện thành một lịch ngắn, có giải thích và có thể tự động chạy trong CI.

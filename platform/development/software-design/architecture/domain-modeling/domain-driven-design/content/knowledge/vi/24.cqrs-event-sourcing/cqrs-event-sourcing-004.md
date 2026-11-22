# Event Sourcing: lưu chuỗi sự kiện để khôi phục trạng thái

Trong một hệ thống ngân hàng, số dư tài khoản hiện tại có thể là 1.500.000 VND. Chỉ nhìn con số này, ta không biết tài khoản được mở khi nào, đã nhận tiền từ đâu, đã rút bao nhiêu, giao dịch nào bị hoàn lại hoặc vì sao số dư thay đổi. Nếu hệ thống lưu lại các sự việc như tài khoản được mở, tiền được nạp, tiền được rút và giao dịch được điều chỉnh, ta có thể dựng lại trạng thái tài khoản bằng cách áp dụng lần lượt các sự kiện đó.

**Event Sourcing** là cách tổ chức lưu trữ trong đó chuỗi sự kiện đã xảy ra được xem là nguồn dữ liệu có thẩm quyền. Thay vì chỉ ghi đè trạng thái mới nhất, hệ thống append các sự kiện bất biến vào một event stream. Trạng thái hiện tại được tái tạo bằng cách đọc và áp dụng các sự kiện theo đúng thứ tự. Có thể tạo snapshot để tăng tốc quá trình khôi phục, nhưng snapshot chỉ là bản tối ưu; chuỗi sự kiện vẫn là lịch sử có thẩm quyền.

Trong Domain-Driven Design (DDD), Event Sourcing có thể giúp lưu lại lịch sử thay đổi của Aggregate, hỗ trợ giải thích quyết định và xây dựng nhiều mô hình đọc. Tuy nhiên, đây là một lựa chọn kiến trúc có chi phí đáng kể: phải quản lý version của event, concurrency, replay, schema evolution, projection, idempotency và dữ liệu nhạy cảm. Không phải hệ thống nào cũng cần lưu mọi thay đổi dưới dạng event.

Sau bài học này, bạn có thể:

- Giải thích Event Sourcing và cách khôi phục trạng thái từ event stream.
- Phân biệt Event Sourcing với audit log, event-driven architecture và CQRS.
- Thiết kế event stream theo Aggregate và append event có expected version.
- Tái tạo Aggregate bằng cách áp dụng event theo thứ tự.
- Sử dụng snapshot để giảm chi phí replay.
- Quản lý thay đổi schema event và dữ liệu lịch sử.
- Xây dựng projection/read model và xử lý replay, duplicate, ordering.
- Nhận diện giới hạn của Event Sourcing với transaction, tích hợp, quyền riêng tư và vận hành.

## 1. Ý tưởng cốt lõi của Event Sourcing

Trong mô hình lưu trạng thái truyền thống, hệ thống thường cập nhật bản ghi để phản ánh kết quả mới nhất:

~~~text
Account
  account_id = ACC-01
  balance = 1,500,000
~~~

Sau một lần nạp tiền, cột balance được cập nhật. Giá trị cũ có thể không còn trong bảng chính. Muốn biết vì sao số dư là 1.500.000, hệ thống phải dựa vào bảng giao dịch, audit log hoặc một nguồn lịch sử khác.

Với Event Sourcing, hệ thống lưu các sự việc làm thay đổi trạng thái:

~~~text
AccountOpened       openingBalance = 1,000,000
MoneyDeposited      amount = 800,000
MoneyWithdrawn      amount = 200,000
MoneyDeposited      amount = 100,000
MoneyWithdrawn      amount = 200,000
~~~

Trạng thái hiện tại được tính bằng cách áp dụng tuần tự:

~~~text
1,000,000
  + 800,000
  - 200,000
  + 100,000
  - 200,000
  = 1,500,000 VND
~~~

Event stream giữ lại các sự việc đã được ghi nhận. Khi cần trạng thái hiện tại, ứng dụng đọc stream và áp dụng các sự kiện theo thứ tự. Khi cần giải thích lịch sử, hệ thống có thể xem từng event và metadata tương ứng.

### Event là sự thật đã xảy ra

Một event nên mô tả một sự việc đã xảy ra trong domain, thường được đặt tên ở thì quá khứ:

- AccountOpened
- MoneyDeposited
- MoneyWithdrawn
- OrderPlaced
- PaymentCaptured
- StockReserved
- SubscriptionCancelled

Event không phải yêu cầu trong tương lai. DepositMoney là command yêu cầu nạp tiền; MoneyDeposited là sự việc xác nhận tiền đã được nạp. Không được ghi MoneyDeposited trước khi quy tắc nghiệp vụ chấp nhận command và thao tác append event thành công.

### Event stream là lịch sử của một Aggregate

Trong nhiều thiết kế DDD, mỗi Aggregate có một stream riêng được nhận diện bằng Aggregate ID:

~~~text
Stream: account-ACC-01
  version 1: AccountOpened
  version 2: MoneyDeposited
  version 3: MoneyWithdrawn
  version 4: MoneyDeposited
~~~

Các event trong một stream có thứ tự rõ ràng. Version/sequence tăng theo từng event được append thành công. Một event thuộc stream nào và có version nào là thông tin quan trọng để tái tạo trạng thái và phát hiện ghi đồng thời.

Event store thường cung cấp thao tác append-only: thêm event mới vào cuối stream. Event đã ghi không được sửa tùy tiện như một bản ghi trạng thái thông thường.

## 2. Event Sourcing khác gì lưu trạng thái hiện tại?

Hai cách lưu trữ có mục tiêu khác nhau.

| Tiêu chí | State-based persistence | Event Sourcing |
|---|---|---|
| Dữ liệu có thẩm quyền | Trạng thái hiện tại | Chuỗi sự kiện |
| Cập nhật | Thường ghi đè field hoặc row | Append event mới |
| Lịch sử | Cần audit/history riêng nếu muốn giữ | Được biểu diễn trực tiếp bằng event stream |
| Khôi phục trạng thái | Đọc trạng thái đã lưu | Replay event, có thể bắt đầu từ snapshot |
| Truy vấn hiện tại | Thường trực tiếp | Thường qua projection hoặc snapshot |
| Thay đổi mô hình | Migration dữ liệu trạng thái | Phải quản lý schema và ý nghĩa event lịch sử |
| Độ phức tạp vận hành | Thường thấp hơn | Cao hơn: stream, replay, projection, versioning |

State-based persistence phù hợp với nhiều ứng dụng CRUD và domain có lịch sử đơn giản. Event Sourcing có giá trị khi lịch sử sự việc là một phần quan trọng của domain, cần tái dựng trạng thái, giải thích quyết định hoặc tạo nhiều cách nhìn từ cùng một nguồn sự thật.

Không nên chọn Event Sourcing chỉ vì muốn có audit trail. Một audit log riêng, bảng lịch sử hoặc temporal table có thể đáp ứng yêu cầu đơn giản hơn nếu không cần tái tạo Aggregate từ event.

## 3. Phân biệt Event Sourcing, audit log và event-driven architecture

Ba khái niệm thường xuất hiện cùng nhau nhưng không đồng nghĩa.

### Event Sourcing

Chuỗi event là nguồn dữ liệu có thẩm quyền. Trạng thái được dựng từ các event. Nếu xóa toàn bộ projection, hệ thống có thể xây dựng lại chúng từ event stream.

### Audit log

Audit log ghi ai đã làm gì, vào lúc nào và có thể ghi giá trị trước/sau. Nó phục vụ kiểm toán, điều tra hoặc tuân thủ. Hệ thống vẫn có thể dùng bảng trạng thái hiện tại làm nguồn dữ liệu chính. Audit log không nhất thiết đủ thông tin hoặc được thiết kế để replay thành Aggregate.

### Event-driven architecture

Event-driven architecture (EDA) là phong cách giao tiếp trong đó thành phần phát và nhận event để phối hợp. Hệ thống EDA vẫn có thể lưu trạng thái hiện tại bằng relational database. Ngược lại, một ứng dụng Event Sourcing có thể replay event nội bộ mà không cần broker phân tán.

| Câu hỏi | Event Sourcing | Audit log | Event-driven architecture |
|---|---|---|---|
| Nguồn sự thật là gì? | Event stream | Có thể là bảng trạng thái khác | Không quy định |
| Có thể dựng lại trạng thái từ event không? | Có, đó là nguyên tắc cốt lõi | Không nhất thiết | Không nhất thiết |
| Có cần message broker không? | Không bắt buộc | Không | Thường có trong hệ phân tán nhưng không bắt buộc |
| Mục tiêu chính | Lưu lịch sử domain và khôi phục trạng thái | Kiểm toán và truy vết | Phối hợp các thành phần qua event |

Một hệ thống có thể kết hợp cả ba: dùng Event Sourcing làm nguồn sự thật, audit metadata cho truy cập và thay đổi nhạy cảm, rồi phát Integration Event cho các context khác.

## 4. Event Sourcing không đồng nghĩa với CQRS

CQRS tách mô hình xử lý command (ghi) và query (đọc). Event Sourcing lưu chuỗi event làm nguồn dữ liệu có thẩm quyền. Hai kỹ thuật có thể kết hợp nhưng độc lập về mặt khái niệm.

- Có thể dùng CQRS mà không dùng Event Sourcing: command cập nhật relational database, projection được cập nhật riêng.
- Có thể dùng Event Sourcing mà không tách hẳn CQRS: ứng dụng replay stream để dựng Aggregate rồi cung cấp một số truy vấn đơn giản.
- Có thể kết hợp cả hai: command append event; projection consumer tạo read model tối ưu cho từng query.

Ví dụ:

~~~text
Command
  |
  v
Load Aggregate from Event Stream
  |
  v
Validate and Decide
  |
  v
Append New Events
  |
  +------------------------------+
                                 |
                                 v
                         Event Stream
                                 |
                   +-------------+-------------+
                   |             |             |
                   v             v             v
              Account View   Daily Report   Risk Projection
                   |             |             |
                   +-------------+-------------+
                                 |
                                 v
                              Queries
~~~

Event stream là nguồn dữ liệu ghi. Các read model là projection có thể được xây dựng lại. Query không nhất thiết phải replay stream mỗi lần; làm như vậy thường quá tốn kém.

## 5. Cấu trúc của một event

Một event lưu trữ thường có hai phần: payload nghiệp vụ và metadata phục vụ lưu trữ, truy vết, versioning.

Ví dụ payload:

~~~json
{
  "accountId": "ACC-01",
  "amount": "800000",
  "currency": "VND",
  "depositReference": "DEP-2026-00042"
}
~~~

Metadata có thể gồm:

~~~json
{
  "eventId": "evt-01J...",
  "streamId": "account-ACC-01",
  "streamVersion": 2,
  "eventType": "MoneyDeposited",
  "schemaVersion": 1,
  "occurredAt": "2026-11-18T09:30:00Z",
  "recordedAt": "2026-11-18T09:30:01Z",
  "correlationId": "cmd-...",
  "causationId": "cmd-deposit-..."
}
~~~

Các metadata thường hữu ích:

| Trường | Ý nghĩa |
|---|---|
| eventId | Định danh duy nhất của event |
| streamId / aggregateId | Stream hoặc Aggregate sở hữu event |
| streamVersion | Vị trí của event trong stream |
| eventType | Tên loại sự kiện |
| schemaVersion | Phiên bản cấu trúc payload |
| occurredAt | Thời điểm sự việc xảy ra theo domain |
| recordedAt | Thời điểm event được event store ghi nhận |
| correlationId | Nhóm các thao tác cùng một flow |
| causationId | Command hoặc event trực tiếp gây ra event này |
| actor/source | Người dùng hoặc thành phần khởi tạo, nếu cần và được phép lưu |

Không nên nhầm occurredAt với streamVersion. Đồng hồ giữa các máy có thể lệch; thứ tự trong một stream phải dựa vào sequence/version do event store bảo đảm.

### Payload nên ghi điều gì?

Event nên chứa đủ dữ liệu để diễn đạt sự việc đã xảy ra và để các consumer cần thiết xử lý mà không phải suy đoán từ trạng thái hiện tại đã thay đổi.

Ví dụ MoneyDeposited nên chứa amount, currency và reference giao dịch. Nếu event chỉ chứa accountId, consumer phải truy vấn một nguồn khác để biết khoản tiền nào đã được nạp; dữ liệu nguồn có thể đã thay đổi hoặc không còn sẵn sàng.

Tuy nhiên, không nên sao chép toàn bộ Aggregate vào mọi event. Payload cần đủ cho ý nghĩa event, lịch sử và các consumer đã xác định. Dữ liệu cá nhân hoặc dữ liệu nhạy cảm phải được tối thiểu hóa.

## 6. Luồng xử lý command trong Event Sourcing

Event Sourcing không có nghĩa command được biến thành event ngay khi nhận request. Ứng dụng cần khôi phục trạng thái hiện tại, áp dụng quy tắc domain để quyết định event nào được phép phát sinh, rồi append các event đó.

Luồng tổng quát:

1. Nhận command, ví dụ WithdrawMoney.
2. Đọc event stream của Account.
3. Khôi phục Aggregate bằng cách áp dụng các event theo thứ tự.
4. Gọi hành vi domain để kiểm tra command trên trạng thái hiện tại.
5. Aggregate tạo ra một hoặc nhiều event mới nếu command hợp lệ.
6. Event store append các event với expected version.
7. Nếu append thành công, command được ghi nhận.
8. Projection cập nhật read model từ các event mới.

~~~text
WithdrawMoney(accountId, amount)
        |
        v
Event Store: load stream
        |
        v
Account Aggregate: rehydrate
        |
        v
Account.withdraw(amount)
        |
        +--> InsufficientFunds -> reject command
        |
        +--> MoneyWithdrawn event
                    |
                    v
             append(expectedVersion)
                    |
           +--------+--------+
           |                 |
        success            conflict
           |                 |
           v                 v
      command accepted   reload and decide again
~~~

Một event chỉ được xem là sự thật đã lưu khi append thành công. Nếu command bị từ chối, không ghi một event giả như MoneyWithdrawn. Có thể ghi một audit/security event riêng cho việc từ chối nếu domain hoặc chính sách vận hành yêu cầu, nhưng cần phân biệt nó với event thể hiện thay đổi trạng thái thành công.

## 7. Tái tạo Aggregate từ event stream

Quá trình đọc event stream và áp dụng lần lượt các event để dựng trạng thái hiện tại thường được gọi là rehydration.

Giả sử Account bắt đầu với số dư 1.000.000 VND:

~~~text
v1 AccountOpened(openingBalance = 1,000,000)
v2 MoneyDeposited(amount = 800,000)
v3 MoneyWithdrawn(amount = 200,000)
v4 MoneyDeposited(amount = 100,000)
~~~

Hệ thống dựng trạng thái:

~~~text
state0 = empty
state1 = apply(state0, AccountOpened)      -> balance 1,000,000
state2 = apply(state1, MoneyDeposited)      -> balance 1,800,000
state3 = apply(state2, MoneyWithdrawn)      -> balance 1,600,000
state4 = apply(state3, MoneyDeposited)      -> balance 1,700,000
~~~

Đây là trạng thái sau event v4. Nếu cần xử lý command tiếp theo, Aggregate phải được dựng từ một trạng thái đã phản ánh tất cả event đã commit trong stream.

### Apply event khác với quyết định phát event

Nên tách hai việc:

- **Decide:** kiểm tra command trên trạng thái hiện tại và quyết định event nào sẽ được tạo.
- **Apply:** áp dụng một event đã được ghi nhận để chuyển trạng thái.

Decide có thể từ chối command. Apply phải tái tạo đúng trạng thái từ một event đã tồn tại. Không nên để Apply gọi API, đọc đồng hồ hiện tại hoặc sinh số ngẫu nhiên vì replay cùng event sẽ tạo kết quả khác nhau.

Ví dụ:

~~~java
public final class Account {
    private AccountId id;
    private Money balance;
    private AccountStatus status;

    public List<AccountEvent> decide(WithdrawMoney command) {
        if (status != AccountStatus.OPEN) {
            throw new AccountNotOpenException();
        }
        if (command.amount().isZeroOrNegative()) {
            throw new InvalidAmountException();
        }
        if (balance.isLessThan(command.amount())) {
            throw new InsufficientFundsException();
        }

        return List.of(new MoneyWithdrawn(
            id, command.amount(), command.reference()
        ));
    }

    public void apply(AccountEvent event) {
        switch (event) {
            case AccountOpened e -> {
                id = e.accountId();
                balance = e.openingBalance();
                status = AccountStatus.OPEN;
            }
            case MoneyDeposited e -> balance = balance.add(e.amount());
            case MoneyWithdrawn e -> balance = balance.subtract(e.amount());
            case AccountClosed e -> status = AccountStatus.CLOSED;
        }
    }
}
~~~

Đây là code minh họa theo Java có hỗ trợ pattern matching cho sealed hierarchy. Cần định nghĩa các event và kiểu domain tương ứng. Trong triển khai thực tế, Aggregate thường có phương thức tạo mới từ event history và một cơ chế rõ ràng để lấy pending events.

### Apply phải xác định và có tính lặp lại

Khi replay cùng một stream với cùng phiên bản logic event, trạng thái dựng lại phải giống nhau. Vì vậy, apply handler nên là phép chuyển trạng thái xác định:

- Không gọi dịch vụ tỷ giá hiện tại khi áp dụng MoneyConverted nếu event đã ghi tỷ giá được sử dụng.
- Không lấy thời gian hiện tại để quyết định thời điểm gia hạn nếu event chưa lưu ngày hiệu lực.
- Không gửi email hoặc gọi payment provider khi replay.
- Không sinh event mới một cách ngầm định trong quá trình apply lịch sử.

Các tác dụng phụ chỉ chạy trong command handling hoặc projection/integration pipeline có kiểm soát, không chạy lại mỗi lần dựng Aggregate.

## 8. Event Store và event stream

Event Store là thành phần lưu trữ và truy xuất event stream. Nó thường cần các khả năng:

- Tạo hoặc đọc stream theo Aggregate ID.
- Trả event theo thứ tự sequence/version.
- Append một nhóm event vào cuối stream.
- Kiểm tra expected version để phát hiện ghi đồng thời.
- Lưu metadata và schema version.
- Hỗ trợ đọc từ vị trí hoặc subscription/checkpoint cho projection.
- Bảo đảm event đã append được lưu bền vững theo durability contract.

Event Store không đơn thuần là một bảng log mà mọi service có thể tùy ý insert/update/delete. Cần một contract rõ để bảo vệ thứ tự và tính append-only của stream.

### Một schema lưu trữ minh họa

~~~sql
CREATE TABLE event_streams (
    stream_id VARCHAR(200) PRIMARY KEY,
    current_version BIGINT NOT NULL
);

CREATE TABLE stored_events (
    event_id UUID PRIMARY KEY,
    stream_id VARCHAR(200) NOT NULL,
    stream_version BIGINT NOT NULL,
    event_type VARCHAR(200) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    metadata JSONB NOT NULL,
    recorded_at TIMESTAMP NOT NULL,
    UNIQUE (stream_id, stream_version)
);
~~~

Đây chỉ là một cách tổ chức minh họa. Event Store chuyên dụng có thể dùng cấu trúc khác. Nếu tự xây trên relational database, việc cập nhật current_version và insert các event phải nằm trong transaction, có cơ chế chống append đồng thời và ràng buộc unique trên (stream_id, stream_version).

Không nên chỉ đọc current_version rồi insert event mà không khóa hoặc compare-and-swap. Hai writer có thể cùng đọc version 10 và cùng cố ghi event version 11. Event Store phải bảo đảm chỉ một append thành công.

## 9. Expected version và ghi đồng thời

Giả sử hai command cùng tải Account ở version 8. Cả hai quyết định phát event dựa trên cùng trạng thái:

~~~text
Writer A: expectedVersion = 8
Writer B: expectedVersion = 8
~~~

Writer A append thành công, stream chuyển sang version 9. Writer B phải bị từ chối vì expected version 8 không còn đúng.

Một API event store có thể có dạng:

~~~java
public interface EventStore {
    EventStream read(StreamId streamId);

    AppendResult append(
        StreamId streamId,
        long expectedVersion,
        List<NewEvent> events
    );
}
~~~

Quy ước trong ví dụ: stream rỗng có version 0; event đầu tiên được ghi ở version 1. Khi append, expectedVersion là version cuối cùng mà caller đã đọc. Nếu version hiện tại không khớp, Event Store trả concurrency conflict.

SQL compare-and-swap có thể được minh họa như sau:

~~~sql
UPDATE event_streams
SET current_version = :new_version
WHERE stream_id = :stream_id
  AND current_version = :expected_version;
~~~

Ứng dụng cần kiểm tra số hàng được cập nhật và insert event trong cùng transaction. Nếu không cập nhật được version, toàn bộ append phải rollback.

### Xung đột phải được xử lý bằng cách tải lại và quyết định lại

Không nên append lại các event cũ với version mới mà không đánh giá lại command. Trạng thái đã thay đổi; một command trước đó hợp lệ có thể không còn hợp lệ.

Ví dụ hai người cùng rút tiền:

- A rút 80, số dư ban đầu 100.
- B rút 50, cũng đọc số dư 100.
- A append MoneyWithdrawn(80), thành công.
- B append theo expected version cũ, bị conflict.
- B tải lại stream, số dư còn 20.
- B chạy lại quyết định rút 50 và bị từ chối vì thiếu tiền.

Expected version bảo vệ thứ tự append cho một stream. Nó không tự bảo vệ invariant trải qua nhiều Aggregate, chẳng hạn hai tài khoản cùng sử dụng một hạn mức tổng ở một Aggregate khác.

## 10. Snapshot để tăng tốc khôi phục

Một stream dài có thể chứa hàng triệu event. Replay toàn bộ stream mỗi lần xử lý command có thể tốn thời gian và tài nguyên. Snapshot lưu trạng thái đã được dựng đến một version cụ thể để lần đọc tiếp theo chỉ cần áp dụng các event mới hơn.

Ví dụ:

~~~text
Event stream:
  v1 ... v5000
  v5001
  v5002
  v5003

Snapshot:
  state at version 5000

Rehydrate:
  load snapshot v5000
  apply events v5001, v5002, v5003
~~~

Snapshot là bản cache/checkpoint của trạng thái. Nó không thay thế event stream và không phải nguồn sự thật độc lập. Nếu snapshot hỏng hoặc không tương thích, hệ thống có thể bỏ snapshot và dựng lại từ event nếu còn đủ lịch sử.

### Snapshot nên chứa gì?

Snapshot thường cần:

- Aggregate ID/stream ID.
- Version cuối cùng đã áp dụng.
- Trạng thái cần thiết để tiếp tục xử lý command.
- Schema version của snapshot.
- Thời điểm tạo và metadata cần thiết.

Ví dụ:

~~~json
{
  "streamId": "account-ACC-01",
  "streamVersion": 5000,
  "snapshotSchemaVersion": 2,
  "state": {
    "balance": "1500000",
    "currency": "VND",
    "status": "OPEN"
  }
}
~~~

Khi đọc, phải chắc chắn snapshot version thực sự tương ứng với trạng thái trong snapshot. Sau đó chỉ replay event có sequence lớn hơn version đó.

### Khi nào tạo snapshot?

Không có ngưỡng cố định cho mọi hệ thống. Có thể tạo snapshot:

- Sau một số lượng event nhất định.
- Khi stream được đọc thường xuyên và replay trở nên tốn kém.
- Theo lịch hoặc khi có tác vụ bảo trì.
- Khi một Aggregate đạt mốc nghiệp vụ phù hợp.

Snapshot quá thường xuyên làm tăng chi phí ghi và quản lý. Snapshot quá thưa khiến replay dài. Hãy đo thời gian rehydrate, độ dài stream và tần suất command trước khi chọn chiến lược.

### Snapshot phải có thể kiểm chứng

Nên có test so sánh:

1. Replay toàn bộ stream từ đầu.
2. Load snapshot ở version N rồi replay phần còn lại.
3. So sánh hai trạng thái cuối.

Nếu kết quả khác nhau, snapshot hoặc apply logic có lỗi. Không nên sửa event lịch sử chỉ để khớp một snapshot sai.

## 11. Projection và read model

Event stream được tối ưu cho việc tái tạo Aggregate theo stream. Nó thường không tối ưu cho các truy vấn như:

- Tìm tất cả tài khoản có số dư lớn hơn một ngưỡng.
- Báo cáo tổng số tiền nạp/rút theo ngày.
- Tìm đơn hàng theo tên khách và trạng thái giao.
- Tính doanh thu theo khu vực, nhóm sản phẩm hoặc tháng.

Projection là quá trình đọc event và cập nhật một mô hình đọc phù hợp với query. Ví dụ, projection Account Balance duy trì một row cho mỗi account với balance hiện tại; projection Daily Transactions duy trì tổng hợp theo ngày.

~~~text
Event Store
    |
    +--> Account Balance Projection
    |
    +--> Transaction History Projection
    |
    +--> Daily Cashflow Projection
    |
    +--> Risk Analytics Projection
~~~

Các projection có thể có cấu trúc khác nhau vì mỗi query cần một cách nhìn khác. Chúng là dữ liệu dẫn xuất, có thể rebuild từ event stream nếu thiết kế và retention cho phép.

### Projection có thể trễ

Consumer có thể cập nhật read model sau khi event đã append. Trong khoảng thời gian đó, command side đã ghi thành công nhưng query side chưa phản ánh event mới. Đây là eventual consistency.

Nếu UI cần hiển thị trạng thái mới ngay sau command, có thể:

- Trả trạng thái hoặc kết quả từ command response.
- Đọc trực tiếp Aggregate/event stream cho một truy vấn cụ thể.
- Chờ projection đạt checkpoint cần thiết.
- Dùng read-your-writes token/version để client biết projection đã bắt kịp.

Không nên giả định mọi projection cập nhật tức thời chỉ vì event đã được lưu.

## 12. Replay và rebuild projection

Một lợi ích của Event Sourcing là có thể replay event để tạo lại read model hoặc áp dụng một cách nhìn mới.

Ví dụ, ban đầu hệ thống chỉ có projection Account Balance. Sau này đội phát triển cần báo cáo số tiền nạp và rút theo từng ngày. Có thể xây projection mới bằng cách đọc lại lịch sử:

~~~text
Event Store
    |
    v
Replay events from checkpoint 0
    |
    v
Daily Cashflow Projection
    |
    v
Read model populated
~~~

Replay projection không được phát lại tác dụng phụ bên ngoài. Nếu consumer vừa cập nhật read model vừa gửi email, replay có thể gửi lại hàng triệu email. Hãy tách projection handler khỏi notification handler và chỉ replay những consumer có thể xử lý lặp an toàn.

### Rebuild projection trong khi hệ thống vẫn chạy

Một quy trình rebuild an toàn thường cần:

1. Tạo projection version mới hoặc bảng đích riêng.
2. Chọn checkpoint/position bắt đầu.
3. Replay lịch sử đến một vị trí xác định.
4. Tiếp tục nhận event mới trong khi kiểm soát khoảng trống giữa replay và live.
5. Đảm bảo không bỏ sót event và không áp dụng trùng gây sai kết quả.
6. Kiểm tra số liệu và chuyển query sang projection mới.
7. Giữ projection cũ trong một khoảng thời gian để rollback nếu cần.

Không nên xóa projection đang phục vụ production rồi replay trực tiếp nếu thời gian rebuild dài hoặc không có cơ chế phục hồi.

## 13. Idempotency và checkpoint của projection

Event delivery thường có thể lặp. Consumer có thể nhận cùng event nhiều lần do retry, process crash hoặc broker redelivery. Projection handler cần idempotent hoặc lưu checkpoint/processed event để không cộng trùng.

Ví dụ, projection cộng tổng tiền nạp:

~~~text
MoneyDeposited(amount = 100)
~~~

Nếu event được xử lý hai lần, tổng tiền có thể tăng thành 200. Một cơ chế deduplication theo eventId hoặc xử lý tuần tự theo stream version giúp ngăn lỗi này.

### Checkpoint

Checkpoint ghi nhận vị trí consumer đã xử lý đến đâu. Có thể là global position do event store cấp, partition offset của broker hoặc version theo stream tùy hệ thống.

Khi cập nhật projection và checkpoint trong cùng một transactional resource, chúng có thể được commit cùng nhau. Nếu projection nằm ở một database và checkpoint ở một nơi khác, cần cơ chế đảm bảo không mất hoặc áp dụng sai event.

### Duplicate và gap

Consumer nên xử lý:

- Event có eventId đã xử lý: bỏ qua hoặc trả kết quả idempotent.
- Event có version thấp hơn version đã áp dụng: bỏ qua theo policy nếu đã xác nhận là duplicate/cũ.
- Event có version cao hơn version kế tiếp mong đợi: phát hiện gap, chờ event thiếu hoặc rebuild từ nguồn.
- Event cùng version nhưng payload khác: coi là lỗi dữ liệu nghiêm trọng và điều tra.

Không nên chỉ dựa vào timestamp để deduplicate hoặc xác định thứ tự.

## 14. Event schema evolution

Event đã lưu có thể tồn tại nhiều năm. Trong thời gian đó, domain model và cấu trúc code thay đổi. Một event cũ có thể thiếu field mà code mới cần, tên field có thể thay đổi hoặc ý nghĩa một khái niệm có thể được làm rõ.

Đây là một trong những thách thức lớn nhất của Event Sourcing: hệ thống mới phải đọc được lịch sử đã ghi bằng các phiên bản schema trước.

Ví dụ event cũ:

~~~json
{
  "eventType": "MoneyDeposited",
  "schemaVersion": 1,
  "amount": "100000"
}
~~~

Phiên bản mới cần thêm currency và deposit channel:

~~~json
{
  "eventType": "MoneyDeposited",
  "schemaVersion": 2,
  "amount": "100000",
  "currency": "VND",
  "channel": "BANK_TRANSFER"
}
~~~

Không thể giả định mọi event lịch sử tự động có field mới.

### Các chiến lược phổ biến

**Giữ tương thích ngược:** thêm field tùy chọn có default rõ ràng, giữ nguyên ý nghĩa field cũ và không đổi tên tùy tiện.

**Upcasting:** chuyển event schema cũ sang dạng mà code hiện tại hiểu khi đọc. Upcaster thường là phép biến đổi thuần, xác định và không sửa event gốc.

**Event versioning:** lưu schema version hoặc event type version để serializer biết cách đọc.

**New event type:** khi ý nghĩa nghiệp vụ thay đổi đáng kể, tạo event mới thay vì dùng lại tên cũ với semantics khác.

**Migration có kiểm soát:** chỉ khi có lý do mạnh, có thể chuyển đổi lịch sử bằng một quy trình có backup, kiểm chứng và audit. Không sửa event lịch sử trực tiếp theo cách không thể truy vết.

### Upcaster

Ví dụ event version 1 thiếu currency, nhưng domain cũ đảm bảo mọi account của stream chỉ dùng một currency mặc định:

~~~java
public MoneyDepositedV2 upcast(MoneyDepositedV1 oldEvent) {
    return new MoneyDepositedV2(
        oldEvent.accountId(),
        oldEvent.amount(),
        CurrencyCode.VND,
        DepositChannel.UNKNOWN
    );
}
~~~

Chỉ được dùng default như VND nếu quy tắc lịch sử thật sự bảo đảm điều đó. Không được tự suy đoán dữ liệu thiếu. Nếu không thể xác định giá trị đúng, cần giữ trạng thái unknown, truy xuất nguồn dữ liệu khác hoặc thực hiện migration có xác nhận.

Upcaster không nên gọi API bên ngoài hoặc phụ thuộc dữ liệu hiện tại, vì cùng event lịch sử phải được chuyển đổi nhất quán ở mọi lần replay.

## 15. Thay đổi ý nghĩa nghiệp vụ khó hơn thay đổi schema

Thêm một field có thể xử lý bằng upcaster. Nhưng nếu ý nghĩa nghiệp vụ thay đổi, việc replay lịch sử theo rule mới có thể cho kết quả khác với quyết định đã được chấp nhận tại thời điểm cũ.

Ví dụ, trước đây phí rút tiền được tính theo tỷ lệ 1%. Từ một ngày mới, policy thay đổi thành 1,5%. Nếu event chỉ lưu MoneyWithdrawn(amount) và khi replay hệ thống tự tính phí bằng policy hiện tại, lịch sử sẽ bị diễn giải sai.

Event cần lưu những dữ kiện cần thiết để giải thích sự việc đã xảy ra:

- Số tiền đã tính.
- Currency.
- Policy/rate hoặc phiên bản policy được áp dụng nếu cần.
- Ngày hiệu lực.
- Reference giao dịch.

Không phải mọi event phải lưu toàn bộ rule engine. Nhưng event phải đủ dữ liệu để khôi phục sự thật đã được chấp nhận, không tái tính lịch sử bằng policy hiện tại nếu điều đó làm thay đổi kết quả.

## 16. Event bất biến và dữ liệu nhạy cảm

Event Sourcing lưu lịch sử lâu dài, nên dữ liệu cá nhân hoặc nhạy cảm cần được cân nhắc ngay từ thiết kế.

Nếu event chứa tên, email, địa chỉ, số giấy tờ hoặc dữ liệu thanh toán, việc sửa hoặc xóa sau này có thể khó vì event stream được thiết kế append-only.

Một số hướng thiết kế:

- Chỉ lưu dữ liệu tối thiểu cần thiết cho ý nghĩa domain.
- Dùng reference đến hồ sơ nhạy cảm được quản lý ở một nơi có chính sách retention phù hợp.
- Mã hóa dữ liệu nhạy cảm và quản lý khóa riêng.
- Tách payload nhạy cảm khỏi phần event không nhạy cảm.
- Dùng token thay cho số thẻ hoặc bí mật thanh toán.
- Có quy trình xóa/ẩn danh phù hợp với nghĩa vụ pháp lý và yêu cầu sản phẩm.
- Xem xét crypto-shredding khi kiến trúc mã hóa cho phép vô hiệu hóa khả năng giải mã dữ liệu của một chủ thể.

Crypto-shredding không tự động giải quyết mọi nghĩa vụ xóa dữ liệu. Cần kiểm tra bản sao, snapshot, projection, backup, log, message broker và hệ thống downstream. Không nên lưu dữ liệu cá nhân vào event chỉ vì nó tiện cho projection.

## 17. Event Sourcing và transaction

Trong một command, việc append các event mới cho một Aggregate phải là thao tác nguyên tử: hoặc toàn bộ nhóm event được append, hoặc không event nào được append. Nếu một command tạo hai event liên quan, không nên để chỉ event thứ nhất được lưu.

Ví dụ một lệnh rút tiền có thể phát:

~~~text
MoneyWithdrawn
WithdrawalFeeCharged
~~~

Nếu hai event cùng mô tả một quyết định domain cần được ghi nhận như một đơn vị, Event Store phải append chúng atomically vào stream. Nếu event thứ hai thất bại nhưng event thứ nhất đã tồn tại, Aggregate có thể rơi vào trạng thái không mong muốn.

Event Store thường cung cấp append nhiều event trong một lần với expected version. Nếu tự triển khai trên relational database, việc kiểm tra version, cập nhật stream version và insert tất cả event phải nằm trong cùng database transaction.

### Một stream không phải transaction toàn hệ thống

Atomic append cho một stream không đảm bảo append đồng thời nhiều stream là nguyên tử. Nếu một use case cần ghi event cho hai Aggregate, phải quyết định:

- Có thể đặt hai stream trong cùng transaction database không?
- Có cần một Aggregate sở hữu invariant chung không?
- Có thể chấp nhận eventual consistency và điều phối bằng Saga không?
- Có cần một command/Process Manager ghi nhận tiến trình?

Không nên giả định Event Store hỗ trợ transaction xuyên mọi stream nếu contract của nó không nói rõ điều đó.

## 18. Event Sourcing và Integration Event

Event trong event stream thường phục vụ việc tái tạo Aggregate bên trong Bounded Context. Integration Event là contract công bố để context khác phản ứng. Hai loại event có thể liên quan nhưng không nhất thiết giống nhau.

Ví dụ:

~~~text
Internal stream event:
  OrderPlaced
    - orderId
    - buyerAccountId
    - pricingPolicyVersion
    - internalDiscountBreakdown

Published integration event:
  SalesOrderAccepted
    - orderReference
    - acceptedAt
    - fulfillmentLines
    - deliveryAddressSnapshot
~~~

Fulfillment không cần biết toàn bộ chi tiết pricing nội bộ của Sales. Context nguồn nên ánh xạ event nội bộ sang contract công bố có version và dữ liệu tối thiểu.

### Công bố event đáng tin cậy

Nếu Event Store và message broker là hai hệ thống riêng, append event thành công nhưng publish thất bại có thể làm consumer không nhận được thông tin. Ngược lại, publish trước khi append thành công có thể gửi một sự việc chưa được ghi nhận.

Có thể dùng:

- Subscription/change feed của Event Store nếu nó bảo đảm đọc được mọi event đã append.
- Transactional Outbox nếu event store và outbox có thể ghi cùng transaction.
- Một relay bền vững có checkpoint và retry.
- Consumer idempotency để xử lý giao lặp.

Chọn cơ chế dựa trên khả năng thực tế của Event Store. Không thể giả định mọi Event Store có thể tham gia transaction với broker.

## 19. Event Sourcing không tự giải quyết distributed transaction

Event Sourcing giúp lưu lịch sử trong một stream. Nó không tự bảo đảm một quy trình đi qua Sales, Payment, Inventory và Fulfillment được commit nguyên tử.

Ví dụ đặt hàng:

1. Sales append OrderPlaced.
2. Payment nhận yêu cầu và xử lý thanh toán.
3. Inventory nhận yêu cầu reserve stock.
4. Fulfillment bắt đầu chuẩn bị hàng.

Mỗi context có event stream và transaction riêng. Quy trình cần theo dõi kết quả, duplicate, timeout, retry và compensation. Process Manager/Saga có thể điều phối:

~~~text
OrderPlaced
    |
    +--> PaymentRequested
    |       +--> PaymentCaptured
    |       +--> PaymentFailed
    |
    +--> StockReservationRequested
            +--> StockReserved
            +--> StockUnavailable
~~~

Nếu payment thành công nhưng stock không còn, hệ thống có thể void/refund theo policy. Compensation là một sự việc nghiệp vụ mới, không phải xóa event cũ hoặc rollback xuyên các context.

## 20. Thiết kế Event Store và projection cho khả năng phục hồi

Một thiết kế vận hành được cần xác định:

- Stream được phân vùng hoặc lưu trữ theo Aggregate ID thế nào.
- Cách đọc một stream hoặc một khoảng version.
- Cách append nhiều event atomically.
- Cách phát hiện expected version conflict.
- Cách consumer theo dõi global position hoặc per-stream version.
- Cách tạo và kiểm tra snapshot.
- Cách rebuild projection mà không làm gián đoạn query.
- Cách lưu schema version và upcaster.
- Cách backup, restore và kiểm tra tính toàn vẹn.
- Cách archive hoặc xử lý retention theo policy.

### Global position và stream version

Stream version là thứ tự event trong một Aggregate. Global position là vị trí event trong toàn Event Store hoặc một phân vùng/subscription. Không phải Event Store nào cũng cung cấp một global order tuyệt đối.

Projection tổng hợp nhiều stream có thể cần global position, partition offset hoặc checkpoint theo nguồn. Không nên dùng stream version của Aggregate A để so sánh trực tiếp với version của Aggregate B.

### Phân vùng và truy vấn

Event Store thường tối ưu cho đọc stream theo ID và append event. Các truy vấn phân tích nhiều Aggregate nên chạy trên projection hoặc data warehouse. Tránh scan toàn bộ event store trong request đồng bộ của người dùng.

## 21. Kiểm thử Event Sourcing

Event Sourcing cần test cả quyết định domain lẫn khả năng khôi phục từ lịch sử.

### Test command-to-event

Cho một trạng thái được dựng từ lịch sử, khi nhận command hợp lệ, Aggregate phát đúng event. Khi command không hợp lệ, không có event mới.

Ví dụ:

~~~text
Given:
  AccountOpened(1000)
  MoneyDeposited(500)

When:
  WithdrawMoney(300)

Then:
  MoneyWithdrawn(300)
~~~

Và:

~~~text
Given:
  AccountOpened(1000)

When:
  WithdrawMoney(1500)

Then:
  InsufficientFunds
  no new event
~~~

### Test replay

Với một stream event cố định, trạng thái sau replay phải đúng với kết quả mong đợi. Cùng một stream được replay nhiều lần phải cho cùng kết quả.

### Test expected version

Hai writer cùng đọc version N; chỉ một append với expected version N được thành công. Writer còn lại nhận conflict và phải tải lại.

### Test snapshot

Replay từ đầu và replay từ snapshot + phần event còn lại phải cho cùng trạng thái.

### Test schema evolution

Các event lịch sử của những schema version được hỗ trợ phải deserialize/upcast thành dạng hiện tại mà không mất ý nghĩa.

### Test projection

Projection xử lý duplicate an toàn, phát hiện gap/version cũ và có thể rebuild từ nguồn.

## 22. Những sai lầm thường gặp

**Xem event như một audit log tùy chọn.** Trong Event Sourcing, event stream là nguồn dữ liệu có thẩm quyền và phải đủ để tái tạo trạng thái.

**Ghi event theo tên command.** DepositMoney là yêu cầu; MoneyDeposited là sự việc đã xảy ra. Chỉ append event sau khi domain chấp nhận command.

**Sửa hoặc xóa event lịch sử tùy tiện.** Điều đó làm mất khả năng giải thích và replay. Sửa sai bằng event điều chỉnh hoặc migration có kiểm soát.

**Đặt logic nghiệp vụ vào projection handler.** Projection có thể được rebuild; không nên để logic quyết định command phụ thuộc vào một read model trễ.

**Gọi API hoặc gửi email trong apply/replay.** Replay sẽ lặp tác dụng phụ. Apply chỉ tái tạo state một cách xác định.

**Không kiểm tra expected version.** Hai writer có thể ghi event dựa trên cùng trạng thái và phá invariant.

**Dùng timestamp làm thứ tự stream.** Sequence/version do Event Store quản lý mới là thứ tự có thẩm quyền trong stream.

**Coi snapshot là nguồn sự thật.** Snapshot là checkpoint có thể dựng lại; event stream mới là lịch sử có thẩm quyền.

**Thay schema event mà không có chiến lược đọc lịch sử.** Event cũ sẽ không deserialize được hoặc bị diễn giải sai.

**Tính lại lịch sử bằng policy hiện tại.** Event phải lưu dữ kiện cần thiết để giữ đúng kết quả đã được chấp nhận tại thời điểm xảy ra.

**Giả định exactly-once delivery.** Publisher và broker có thể giao lặp; consumer cần idempotency/deduplication.

**Coi Event Sourcing là distributed transaction.** Mỗi stream có ranh giới append riêng; quy trình qua nhiều context cần coordination và compensation.

**Lưu quá nhiều dữ liệu cá nhân trong event.** Event khó sửa/xóa; hãy tối thiểu hóa, mã hóa và có retention/privacy strategy.

**Dùng Event Sourcing cho mọi Aggregate.** Chi phí schema evolution, replay, projection và vận hành có thể lớn hơn giá trị nhận được.

## 23. Quy trình quyết định có nên dùng Event Sourcing

Trước khi chọn Event Sourcing, hãy trả lời:

**Bước 1: Lịch sử có giá trị nghiệp vụ không?** Hệ thống có cần giải thích vì sao trạng thái hiện tại hình thành, hay chỉ cần trạng thái hiện tại?

**Bước 2: Có cần replay không?** Có nhu cầu dựng lại Aggregate, tạo projection mới hoặc tái tính dữ liệu lịch sử không?

**Bước 3: Domain có sự kiện rõ ràng không?** Chuyên gia có thể diễn đạt các sự việc có ý nghĩa bằng event ổn định không?

**Bước 4: Có thể giữ event đủ lâu và đủ dữ liệu không?** Có yêu cầu privacy, retention, archive hoặc xóa dữ liệu nào cần giải quyết?

**Bước 5: Ai sở hữu stream?** Stream gắn với Aggregate nào, version ra sao, command nào có quyền append?

**Bước 6: Có thể quản lý schema evolution không?** Đội có khả năng duy trì event version và đọc dữ liệu lịch sử qua nhiều lần thay đổi không?

**Bước 7: Query cần gì?** Những projection nào phải xây dựng, cập nhật và rebuild?

**Bước 8: Concurrency và consistency thế nào?** Expected version bảo vệ stream; invariant liên Aggregate cần cơ chế riêng.

**Bước 9: Vận hành ra sao?** Backup, restore, replay, monitoring, outbox, dead-letter và retention có được thiết kế không?

**Bước 10: So sánh với lựa chọn đơn giản hơn.** State-based persistence + audit log có đáp ứng yêu cầu với chi phí thấp hơn không?

## 24. Checklist triển khai

- [ ] Event mô tả sự việc domain đã xảy ra, không phải command.
- [ ] Event stream có owner và Aggregate ID rõ ràng.
- [ ] Mỗi event có eventId, event type, schema version và stream version.
- [ ] Append nhiều event cho một command có tính nguyên tử.
- [ ] Expected version được kiểm tra trong thao tác append.
- [ ] Decide và Apply được tách biệt.
- [ ] Apply/replay xác định, không gọi side effect bên ngoài.
- [ ] Event chứa đủ dữ kiện để giữ ý nghĩa lịch sử.
- [ ] Snapshot lưu version và có thể kiểm chứng bằng replay.
- [ ] Projection có checkpoint và xử lý duplicate/gap.
- [ ] Schema evolution có version/upcaster và test dữ liệu lịch sử.
- [ ] Integration Event được ánh xạ từ contract nội bộ có chủ đích.
- [ ] Publish message có cơ chế bền vững như subscription/outbox.
- [ ] Consumer có idempotency/deduplication.
- [ ] Invariant liên Aggregate hoặc liên context có cơ chế bảo vệ riêng.
- [ ] Dữ liệu nhạy cảm được tối thiểu hóa và có privacy/retention strategy.
- [ ] Có backup, restore, replay và monitoring.
- [ ] Đã so sánh lợi ích với state-based persistence và audit log.

## 25. Bài tập tự kiểm tra

Một nền tảng ví điện tử quản lý Wallet. Các sự việc có thể xảy ra:

- Wallet được mở với currency cụ thể.
- Người dùng nạp tiền.
- Người dùng rút tiền.
- Một giao dịch được hoàn lại.
- Ví bị khóa.
- Một khoản phí được thu.

Hãy thiết kế Event Sourcing cho Wallet và trả lời:

1. Event stream nên được nhận diện bằng khóa nào?
2. Event nào được tạo khi command rút tiền hợp lệ? Nếu số dư không đủ thì sao?
3. Làm thế nào để khôi phục số dư và trạng thái ví từ event stream?
4. Nếu stream có hàng trăm nghìn event, snapshot nên chứa những gì?
5. Hai command rút tiền cùng đọc version 20; expected version bảo vệ ra sao?
6. Nếu schema MoneyWithdrawn thay đổi để thêm transaction reference, event cũ được đọc thế nào?
7. Projection lịch sử giao dịch nhận cùng event hai lần cần xử lý ra sao?
8. Nếu payment provider timeout sau khi đã nhận lệnh nạp tiền, có nên phát MoneyDeposited ngay không?
9. Nếu một event cũ chứa dữ liệu cá nhân không còn cần thiết, hệ thống cần cân nhắc những nơi lưu bản sao nào?
10. Khi nào một bảng trạng thái và audit log sẽ là lựa chọn đơn giản hơn?

Gợi ý:

| Câu hỏi | Hướng trả lời |
|---|---|
| Stream identity | Một Wallet Aggregate có WalletId riêng; event được append vào stream của Wallet |
| Rút tiền | Command được đánh giá trên state hiện tại; chỉ phát MoneyWithdrawn nếu ví hoạt động và đủ số dư |
| Khôi phục | Replay WalletOpened, MoneyDeposited, MoneyWithdrawn, MoneyRefunded, WalletLocked... theo stream version |
| Snapshot | WalletId, version, balance, currency, status và các state cần cho command tiếp theo |
| Expected version | Chỉ một append theo expected version 20 thành công; request còn lại tải lại và quyết định lại |
| Schema | Upcast event cũ hoặc hỗ trợ nhiều schema version; không tự bịa dữ liệu thiếu |
| Duplicate projection | Deduplicate theo eventId hoặc checkpoint/stream version |
| Provider timeout | Kết quả chưa xác định; tra cứu/retry cùng idempotency key, chỉ phát event khi có bằng chứng nghiệp vụ đã hoàn tất |
| Privacy | Kiểm tra event stream, snapshot, projection, backup, log, broker và downstream |
| Lựa chọn đơn giản | Nếu chỉ cần trạng thái hiện tại và audit cơ bản, state persistence cùng audit log có thể đủ |

## Kết luận

Event Sourcing lưu chuỗi sự kiện đã xảy ra làm nguồn dữ liệu có thẩm quyền. Aggregate được khôi phục bằng cách áp dụng event theo thứ tự; command chỉ tạo event sau khi domain chấp nhận yêu cầu và Event Store append thành công với expected version. Snapshot giúp tăng tốc replay, còn projection tạo các mô hình đọc phù hợp với truy vấn.

Giá trị của Event Sourcing nằm ở khả năng giữ lịch sử domain, giải thích trạng thái và tái tạo các mô hình dẫn xuất. Đổi lại, đội phát triển phải quản lý concurrency, schema evolution, replay, projection, idempotency, tích hợp và dữ liệu nhạy cảm trong thời gian dài. Hãy chọn kỹ thuật này khi lịch sử sự việc thực sự có giá trị và tổ chức sẵn sàng vận hành nó; nếu nhu cầu chỉ là lưu trạng thái hiện tại cùng audit trail đơn giản, một mô hình persistence truyền thống có thể phù hợp hơn.

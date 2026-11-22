# Phân biệt đồng thời, song song và giao dịch phân tán

Trong một hệ thống có nhiều người dùng, các yêu cầu có thể đến cùng lúc, được xử lý trên nhiều lõi CPU hoặc đi qua nhiều dịch vụ và cơ sở dữ liệu. Ba tình huống ấy thường xuất hiện cùng nhau, nhưng mô tả **ba khía cạnh khác nhau**:

- **Đồng thời (concurrency):** nhiều công việc có khoảng thời gian thực hiện chồng lấn; các bước của chúng có thể xen kẽ.
- **Song song (parallelism):** nhiều công việc thực sự được thực thi tại cùng một thời điểm trên các tài nguyên xử lý khác nhau.
- **Giao dịch phân tán (distributed transaction):** một thay đổi nghiệp vụ đòi hỏi phối hợp việc ghi hoặc quyết định giao dịch trên nhiều nút, cơ sở dữ liệu hay hệ thống quản lý tài nguyên.

Đối với cơ sở dữ liệu, câu hỏi quan trọng lần lượt là: **các giao dịch tương tác với nhau như thế nào**, **chúng được thực thi bằng tài nguyên nào**, và **ai chịu trách nhiệm duy trì tính nhất quán khi dữ liệu nằm ở nhiều nơi**.

## 1. Đồng thời: nhiều giao dịch có thể xen kẽ

Hãy xét hai giao dịch `T1` và `T2` cùng mua sản phẩm cuối cùng trong kho. Cả hai bắt đầu trước khi giao dịch kia hoàn tất. Hệ quản trị cơ sở dữ liệu (DBMS) có thể sắp xếp các thao tác đọc, ghi, khóa và chờ của chúng theo một **lịch thực thi (schedule)**.

Ví dụ một lịch xen kẽ:

```text
Thời gian →
T1: BEGIN ── đọc tồn kho ───────── cập nhật ── COMMIT
T2: ───────── BEGIN ── đọc tồn kho ────────── cập nhật ── COMMIT
```

Đây là xử lý **đồng thời** dù tại từng thời điểm chỉ có một thao tác thực sự chiếm CPU. Hai giao dịch cùng tồn tại và kết quả có thể phụ thuộc vào thứ tự xen kẽ.

Một trường hợp ngược lại là **tuần tự (serial)**: toàn bộ thao tác của `T1` kết thúc trước khi `T2` bắt đầu, hoặc ngược lại. Lịch tuần tự dễ suy luận hơn nhưng thường làm giảm khả năng phục vụ nhiều yêu cầu.

### Đồng thời không tự động bảo đảm dữ liệu đúng

Giả sử tồn kho ban đầu là `quantity = 1`. Ứng dụng có quy trình đọc tồn kho, kiểm tra lớn hơn 0 rồi ghi số lượng mới:

| Thời điểm | Giao dịch T1 | Giao dịch T2 |
|---|---|---|
| 1 | Đọc `quantity = 1` | |
| 2 | | Đọc `quantity = 1` |
| 3 | Chấp nhận đơn A; ghi `quantity = 0`; commit | |
| 4 | | Từ giá trị đã đọc, chấp nhận đơn B; ghi `quantity = 0`; commit |

Sau hai giao dịch, cơ sở dữ liệu có thể vẫn hiển thị `quantity = 0` nhưng hệ thống đã nhận **hai đơn cho một sản phẩm**. Việc chỉ xem giá trị cuối cùng không phát hiện được vi phạm quy tắc nghiệp vụ. Đây là ví dụ về quyết định dựa trên dữ liệu cũ và cập nhật bị ghi đè (*lost update* hoặc *stale read–modify–write*, tùy cách triển khai).

Với PostgreSQL, một cách xử lý trường hợp cạnh tranh trên **cùng một dòng** là đưa điều kiện kiểm tra vào chính lệnh cập nhật:

```sql
-- quantity ban đầu là 1
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42
  AND quantity > 0
RETURNING quantity;
```

Nếu hai phiên cùng chạy lệnh này, PostgreSQL dùng khóa ghi trên dòng liên quan. Sau khi giao dịch đi trước hoàn tất, lệnh đang chờ sẽ đánh giá lại điều kiện trên phiên bản dòng phù hợp; chỉ một giao dịch trừ được sản phẩm cuối cùng. Ứng dụng **chỉ xác nhận đặt hàng khi cập nhật trả về đúng một dòng**, đồng thời ghi đơn hàng trong cùng giao dịch cục bộ nếu chúng thuộc cùng cơ sở dữ liệu.

Điểm mấu chốt: vấn đề ở đây là **điều khiển đồng thời (concurrency control)**, không phải số lượng CPU hoặc số lượng dịch vụ.

### ACID và mức cô lập xử lý vấn đề gì?

Một giao dịch cơ sở dữ liệu thường được mô tả qua ACID:

| Thuộc tính | Ý nghĩa trong tình huống đồng thời |
|---|---|
| **Atomicity** | Các thay đổi của một giao dịch cục bộ được commit cùng nhau hoặc rollback theo khả năng của hệ quản trị |
| **Consistency** | Giao dịch phải bảo toàn các ràng buộc và bất biến nghiệp vụ đã được biểu diễn, kiểm tra đúng |
| **Isolation** | Giới hạn cách giao dịch nhìn thấy và chịu ảnh hưởng từ thao tác chưa kết thúc của giao dịch khác |
| **Durability** | Sau commit thành công, dữ liệu được lưu bền theo cam kết của hệ quản trị |

**Isolation** là thuộc tính trực tiếp nhất khi bàn về concurrency. Các mức cô lập thường gặp:

| Mức cô lập | Ý tưởng | Lưu ý |
|---|---|---|
| `READ UNCOMMITTED` | Cho phép mức cách ly yếu nhất trong mô hình SQL | Hành vi thực tế tùy DBMS; PostgreSQL xử lý tương đương `READ COMMITTED` |
| `READ COMMITTED` | Mỗi lần đọc chỉ thấy dữ liệu đã commit theo quy tắc của DBMS | Hai câu `SELECT` trong một giao dịch có thể thấy kết quả khác nhau |
| `REPEATABLE READ` | Duy trì góc nhìn ổn định hơn trong suốt giao dịch | Cơ chế và các bất thường còn có thể xảy ra khác nhau giữa các DBMS |
| `SERIALIZABLE` | Kết quả phải tương đương với một thứ tự thực thi tuần tự hợp lệ | Có thể phải chờ hoặc hủy và thử lại giao dịch khi xảy ra xung đột |

Một số bất thường cần phân biệt:

- **Dirty read:** đọc thay đổi chưa commit của giao dịch khác.
- **Non-repeatable read:** đọc lại một dòng trong cùng giao dịch nhưng nhận giá trị khác vì giao dịch khác đã commit.
- **Phantom:** chạy lại truy vấn theo điều kiện nhưng tập dòng khớp điều kiện thay đổi.
- **Lost update:** một thao tác ghi làm mất tác dụng cập nhật của giao dịch khác.
- **Write skew:** hai giao dịch cùng dựa vào trạng thái chung để sửa các dòng khác nhau, mỗi giao dịch có vẻ hợp lệ nhưng tổng thể vi phạm bất biến.

Không thể suy ra mức cô lập chỉ từ tên mức SQL: cần kiểm tra cơ chế **khóa, MVCC (Multi-Version Concurrency Control), ràng buộc dữ liệu** và tài liệu của DBMS đang dùng. Với PostgreSQL ở mức `SERIALIZABLE`, ứng dụng phải chuẩn bị thực hiện lại **toàn bộ giao dịch** khi nhận lỗi serialization failure (`SQLSTATE 40001`).

## 2. Song song: công việc thực sự chạy cùng một thời điểm

**Parallelism** đề cập đến cách cấp phát tài nguyên thực thi. Hai tác vụ chạy trên hai lõi CPU, hai worker hoặc hai nút xử lý có thể thực sự tiến hành đồng thời về mặt vật lý.

```text
Một lõi CPU, xử lý đồng thời bằng cách xen kẽ:
Thời gian:  |  t1  |  t2  |  t3  |  t4  |
CPU 1:     |  T1  |  T2  |  T1  |  T2  |

Hai lõi CPU, thực thi song song:
Thời gian:  |  t1  |  t2  |  t3  |  t4  |
CPU 1:     |  T1  |  T1  |  T1  |  T1  |
CPU 2:     |  T2  |  T2  |  T2  |  T2  |
```

Ở sơ đồ đầu, `T1` và `T2` **đồng thời nhưng không song song** tại một thời điểm. Ở sơ đồ sau, chúng **vừa đồng thời vừa song song**.

Trong hệ thống cơ sở dữ liệu, có hai ví dụ dễ nhầm:

1. **Hai giao dịch trên hai kết nối DB được chạy trên các worker khác nhau.** Chúng có thể thực sự song song, nhưng vẫn cần điều khiển đồng thời nếu cùng đụng đến dữ liệu.
2. **Một truy vấn của một giao dịch sử dụng parallel scan/parallel join.** Nhiều worker cùng thực hiện một truy vấn, tạo ra tính song song bên trong **một** giao dịch; không vì vậy mà có hai giao dịch cạnh tranh nhau.

Thêm CPU, tăng kích thước connection pool hoặc tăng số worker có thể nâng thông lượng với khối lượng phù hợp, nhưng không sửa được điều kiện tranh chấp dữ liệu. Thậm chí tăng số yêu cầu đang chạy cùng lúc có thể làm tăng đợi khóa, deadlock hoặc số lần phải retry.

## 3. Giao dịch phân tán: ranh giới dữ liệu vượt qua một nơi lưu trữ

Xét hệ thống bán hàng có ba thành phần:

```text
Client
  |
Order Service ── Order DB
  |
  +──────────── Payment Service ── Payment DB / cổng thanh toán
  |
  +──────────── Inventory Service ── Inventory DB
```

Một yêu cầu đặt hàng cần tạo đơn, ghi nhận thanh toán và giữ hàng. Mỗi dịch vụ có thể commit vào cơ sở dữ liệu của riêng mình. Nếu Order DB commit thành công nhưng Payment Service thất bại, hệ thống có thể rơi vào trạng thái **đơn đã tạo nhưng chưa thanh toán**.

Đây là vấn đề của **phối hợp thay đổi qua nhiều ranh giới tài nguyên và lỗi**. Khác với tranh chấp giữa các giao dịch trong một DB, ứng dụng giờ đây còn phải đối mặt với:

- Kết nối mạng có thể chậm, đứt hoặc trả lời không rõ kết quả.
- Một dịch vụ có thể lỗi sau khi đã commit cục bộ.
- Không có lệnh `ROLLBACK` cục bộ nào tự động hoàn tác được giao dịch đã commit ở hệ thống khác.
- Một yêu cầu gửi lại có thể thực thi thao tác thanh toán hoặc giữ hàng lần thứ hai nếu thiếu cơ chế chống trùng.
- Dữ liệu giữa các dịch vụ có thể lệch nhau trong một khoảng thời gian, kể cả khi từng DB riêng lẻ vẫn đúng theo ACID.

**Phân tán** mô tả phạm vi phối hợp; **đồng thời** mô tả sự chồng lấn giao dịch; **song song** mô tả sự thực thi cùng thời điểm. Quy trình phân tán hoàn toàn có thể gọi từng dịch vụ **tuần tự**. Ngược lại, hàng nghìn giao dịch chạy đồng thời trên một PostgreSQL đơn lẻ chưa phải là giao dịch phân tán giữa nhiều hệ quản lý tài nguyên.

Cần phân biệt thêm:

- **Hệ thống phân tán** chỉ nói rằng có nhiều tiến trình/nút giao tiếp qua mạng; không phải mọi yêu cầu trong đó đều là giao dịch phân tán.
- **Giao dịch phân tán theo nghĩa ACID mạnh** yêu cầu một quyết định commit/rollback được phối hợp trên nhiều tài nguyên có tham gia giao thức giao dịch.
- **Quy trình nghiệp vụ phân tán** có thể được tổ chức bằng các giao dịch cục bộ và hành động bù (Saga); cách này thường đạt nhất quán cuối cùng chứ không có atomicity toàn cục như một giao dịch ACID.
- **DB phân mảnh (sharded database)** có thể thực hiện giao dịch phân tán bên trong nó nếu một giao dịch chạm nhiều shard. Việc ứng dụng chỉ thấy một kết nối không quyết định liệu phần triển khai bên dưới có phân tán hay không.

## 4. Ba khái niệm đặt trên các trục độc lập

| Tình huống | Đồng thời? | Song song? | Giao dịch phân tán? |
|---|---|---|---|
Một giao dịch cập nhật hai bảng trong một DB đơn | Không cần | Không cần | Không |
Hai giao dịch xen kẽ trên một worker | Có | Không | Không |
Hai giao dịch thực thi trên hai lõi, cùng cập nhật một DB | Có | Có | Không |
Một truy vấn trong một giao dịch dùng nhiều worker CPU | Không cần có giao dịch khác | Có | Không, nếu chỉ dùng một DB cục bộ |
Một nghiệp vụ lần lượt ghi hai DB độc lập qua mạng | Không nhất thiết | Không nhất thiết | Có vấn đề phối hợp giao dịch phân tán |
Nhiều đơn hàng được xử lý trên các service và DB khác nhau | Có | Có thể | Có thể, tùy ranh giới commit và thiết kế nghiệp vụ |

Đặc biệt, **nhiều kết nối**, **nhiều thread**, **nhiều CPU** và **nhiều DB** không phải bốn cách gọi khác nhau của cùng một khái niệm.

## 5. Phối hợp commit trong hệ thống phân tán

Nếu nghiệp vụ đòi hỏi các tài nguyên tham gia phải **cùng commit hoặc cùng rollback**, một họ giải pháp là **Two-Phase Commit (2PC)**. Khi các hệ thống không hỗ trợ giao thức giao dịch chung hoặc cần tránh giữ tài nguyên trong lúc chờ mạng, người ta thường chọn **Saga** cho quy trình nghiệp vụ.

### 5.1. Two-Phase Commit (2PC)

2PC giả định có **coordinator** và các **participant/resource manager** hỗ trợ chuẩn bị giao dịch và quyết định commit phân tán.

**Pha 1 — Prepare:** coordinator yêu cầu từng participant chuẩn bị. Mỗi bên xác nhận có thể commit, lưu trạng thái cần thiết để phục hồi và có thể phải giữ khóa/tài nguyên.

**Pha 2 — Decision:** nếu tất cả đồng ý, coordinator ghi nhận quyết định `COMMIT` và gửi cho các bên; nếu có bên từ chối, coordinator quyết định `ROLLBACK`. Các bên thực hiện quyết định và thông báo kết quả.

```text
             Coordinator
                 |
          PREPARE? / \ PREPARE?
                  /   \
              DB A     DB B
                |       |
              YES      YES
                  \   /
             COMMIT decision
                  /   \
             COMMIT   COMMIT
```

Điểm mạnh của 2PC là khả năng điều phối **atomic commit** giữa những participant thực sự hỗ trợ giao thức. Đổi lại, các participant đã chuẩn bị có thể bị **chặn** trong tình huống coordinator lỗi hoặc mất kết nối trước khi biết quyết định cuối cùng. Hệ thống phải có nhật ký phục hồi, xử lý giao dịch đang ở trạng thái *in-doubt*, cơ chế timeout và vận hành phù hợp.

**2PC không đồng nghĩa với replication, consensus hay parallelism.** Raft/Paxos có thể phục vụ việc đạt đồng thuận và lưu quyết định trong các hệ thống nhất định, nhưng đó là bài toán khác với giao thức atomic commit của nhiều tài nguyên. Cổng thanh toán HTTP thông thường cũng không mặc nhiên hỗ trợ `PREPARE`/`COMMIT`; không thể đưa nó vào 2PC chỉ bằng cách bọc lời gọi API trong `BEGIN TRANSACTION`.

### 5.2. Saga: chuỗi giao dịch cục bộ và hành động bù

Saga mô hình hóa quy trình bằng nhiều bước, mỗi bước commit **cục bộ**. Khi bước sau thất bại, hệ thống thực hiện các hành động **bù (compensation)** cho những bước đã thành công, nếu nghiệp vụ cho phép.

Ví dụ:

```text
1. Order Service:     tạo đơn PENDING       → commit Order DB
2. Inventory Service: giữ hàng              → commit Inventory DB
3. Payment Service:   thu tiền               → thất bại
4. Inventory Service: hủy giữ hàng           → commit Inventory DB
5. Order Service:     đánh dấu PAYMENT_FAILED → commit Order DB
```

Trong khoảng giữa bước 1 và bước 5, các dịch vụ không có cùng một ảnh chụp trạng thái. Saga phải thiết kế rõ các trạng thái trung gian, thời hạn xử lý và khả năng khôi phục khi bước bù cũng thất bại.

Hành động bù **không tương đương rollback vật lý**: hoàn tiền là một giao dịch mới, không xóa lịch sử đã thu tiền; email đã gửi không thể “unsend” một cách đáng tin cậy. Vì thế, khi có tác dụng phụ khó đảo ngược, nên thiết kế theo hướng đặt giữ/chờ xác nhận trước, thực hiện hành động cuối cùng ở thời điểm phù hợp, hoặc có quy trình xử lý thủ công.

Saga thường được điều phối theo một trong hai cách:

- **Orchestration:** một bộ điều phối giữ trạng thái quy trình và gọi/ra lệnh cho các dịch vụ.
- **Choreography:** dịch vụ phản ứng với các sự kiện của nhau, không có một bộ điều phối trung tâm cho toàn bộ luồng.

Cả hai đều cần quản lý retry, timeout, idempotency và khả năng quan sát trạng thái. Saga cung cấp **nhất quán nghiệp vụ theo quy trình**, không tự đem lại isolation hoặc atomicity toàn cục giống một giao dịch ACID.

### 5.3. Outbox và idempotency giải quyết các lỗ hổng thực tế

Giả sử Order Service commit đơn hàng rồi mới phát sự kiện `OrderCreated`. Nếu tiến trình chết giữa hai bước, DB đã có đơn nhưng hệ thống khác không nhận sự kiện. **Transactional Outbox** lưu dữ liệu nghiệp vụ và bản ghi sự kiện dự kiến gửi trong **cùng một giao dịch cục bộ**:

```sql
BEGIN;

INSERT INTO orders (id, status)
VALUES (1001, 'PENDING');

INSERT INTO outbox (event_id, event_type, aggregate_id, payload)
VALUES (
    'order-1001-created',
    'OrderCreated',
    1001,
    '{"orderId":1001}'
);

COMMIT;
```

Một tiến trình chuyển tiếp đọc outbox rồi công bố sự kiện; nếu gửi thất bại, nó thử lại. Cách này tránh khoảng trống “commit DB thành công nhưng chưa lưu ý định phát sự kiện”, nhưng **không bảo đảm sự kiện chỉ được giao đúng một lần**. Consumer cần kiểm tra `event_id` hoặc khóa idempotency để xử lý lặp một cách an toàn.

Trong thanh toán, idempotency key còn giúp một yêu cầu gửi lại không bị thu tiền hai lần. Các bước xử lý phải làm rõ trường hợp **không biết yêu cầu trước đã thành công hay chưa** trước khi retry hoặc phát lệnh bù.

Outbox, Saga và idempotency là những thành phần phối hợp một quy trình phân tán; chúng không thay thế khóa, ràng buộc hay isolation cần thiết **bên trong từng DB**.

## 6. Cùng một nghiệp vụ có thể gặp cả ba vấn đề

Giả sử hệ thống bán vé có 100 lượt đặt hàng đến gần như cùng lúc, chạy trên 8 worker và gồm dịch vụ Vé, Thanh toán, Thông báo.

**Tầng đồng thời:** nhiều lượt đặt cùng tranh chấp số ghế còn lại. DB cần bảo toàn bất biến “một ghế không được bán cho hai đơn”, chẳng hạn bằng unique constraint, lệnh cập nhật có điều kiện, khóa hay transaction isolation thích hợp.

**Tầng song song:** 8 worker thực thi những yêu cầu khác nhau cùng lúc. Việc tăng worker có thể giúp xử lý các yêu cầu độc lập, nhưng cũng làm tăng áp lực lên các dòng dữ liệu đang tranh chấp. Đây là câu chuyện thông lượng và tài nguyên.

**Tầng phân tán:** một vé đã giữ thành công nhưng thanh toán lỗi hoặc phản hồi mạng bị mất. Hệ thống cần một quy trình xác nhận/giải phóng chỗ, retry và đối soát trạng thái trên nhiều dịch vụ. Đây là câu chuyện phối hợp commit và xử lý lỗi từng phần.

Có thể mô tả một thiết kế theo các lớp trách nhiệm:

```text
Request đặt vé
  |
  +-- Parallel workers: nhiều request được chạy cùng lúc
  |
  +-- Ticket DB: unique constraint / locking / isolation
  |                 để kiểm soát cạnh tranh cùng một ghế
  |
  +-- Business workflow: giữ chỗ → thanh toán → xác nhận
                    | thất bại
                    └→ hủy giữ chỗ / hoàn tiền theo quy tắc
```

Không có một thiết lập `SERIALIZABLE` trên Ticket DB nào tự rollback được lệnh thu tiền đã commit ở bên ngoài. Cũng không có một Saga nào tự sửa được lỗi hai giao dịch cùng vượt qua điều kiện kiểm tra ghế nếu khâu giữ chỗ cục bộ sai.

## 7. Chọn giải pháp theo đúng loại vấn đề

| Dấu hiệu | Cần giải quyết | Kỹ thuật thường cân nhắc |
|---|---|---|
Hai giao dịch cùng sửa một dòng, cập nhật chồng lên nhau | Cạnh tranh ghi cục bộ | Atomic conditional update, row lock, optimistic concurrency/version |
Nhiều giao dịch cùng thay đổi các dòng khác nhau nhưng vi phạm một bất biến chung | Tính đúng đắn của lịch đồng thời | Ràng buộc DB, thiết kế khóa/bất biến, `SERIALIZABLE` kèm retry |
Truy vấn tốn CPU và có thể chia nhiều phần độc lập | Tốc độ thực thi | Parallel query, partitioning công việc, worker phù hợp |
Thông lượng tăng nhưng DB thường xuyên chờ khóa | Mức tranh chấp khi chạy đồng thời | Giảm thời gian giữ transaction, giảm hot row, giảm concurrency khi cần |
Một quyết định commit phải có tính nguyên tử trên nhiều resource manager có hỗ trợ giao thức | Atomic commit phân tán | 2PC/XA hoặc cơ chế giao dịch phân tán do nền tảng DB cung cấp, sau khi đánh giá chi phí |
Quy trình nhiều microservice/cổng thanh toán, có thao tác bù theo nghiệp vụ | Phối hợp trạng thái và lỗi từng phần | Saga, state machine, idempotency, retry và đối soát |
Ghi DB thành công nhưng sự kiện có thể bị mất trước khi gửi | Tính tin cậy của phát sự kiện | Transactional outbox và consumer xử lý trùng |

### Các ngộ nhận thường gặp

**“Có hai request cùng lúc nghĩa là chúng chạy song song.”** Không nhất thiết. Chúng có thể chỉ xen kẽ trên một luồng hay bị chờ I/O/khóa.

**“Có nhiều thread là dữ liệu sẽ nhất quán.”** Thread chỉ tạo thêm khả năng chạy; ràng buộc và giao thức điều khiển đồng thời mới quyết định tính đúng.

**“Dùng microservices thì mặc nhiên cần 2PC.”** Không. Nhiều luồng nghiệp vụ dùng giao dịch cục bộ cùng Saga hoặc các thiết kế khác; 2PC yêu cầu participant tương thích và có chi phí riêng.

**“Một giao dịch DB bao quanh lời gọi HTTP sẽ rollback cả dịch vụ bên kia.”** Không. DB transaction chỉ kiểm soát tài nguyên mà DB/giao thức giao dịch đó quản lý; side effect bên ngoài không tự thuộc phạm vi rollback.

**“Saga bảo đảm các DB luôn nhất quán ở mọi thời điểm.”** Không. Trạng thái trung gian và nhất quán cuối cùng là một phần của mô hình.

**“Tăng mức isolation là có thể bỏ qua lỗi mạng.”** Không. Isolation giải quyết sự can thiệp giữa các giao dịch trong phạm vi hệ quản trị; sự cố mạng, commit chưa rõ kết quả và xử lý lặp vẫn cần thiết kế riêng.

## 8. Tự đối chiếu bằng ba tình huống

**Tình huống A.** Hai người cùng rút tiền từ một tài khoản trên một cơ sở dữ liệu; máy chủ chỉ có một lõi CPU. Nếu hai giao dịch xen kẽ, hệ thống có **concurrency** dù không có **parallelism**. Cần kiểm soát số dư bằng transaction và thao tác ghi có điều kiện hoặc khóa thích hợp.

**Tình huống B.** Một truy vấn phân tích dùng bốn worker để quét dữ liệu cho một giao dịch duy nhất. Đây là **parallelism**; không có bằng chứng rằng đang xảy ra tranh chấp giữa nhiều giao dịch hay rằng giao dịch trải qua nhiều hệ quản lý tài nguyên.

**Tình huống C.** Hệ thống tạo đơn trong Order DB, gọi cổng thanh toán rồi cập nhật trạng thái từ phản hồi. Các bước có thể được thực hiện tuần tự, nhưng vẫn có **vấn đề giao dịch/nghiệp vụ phân tán**: mỗi bên có điểm commit và khả năng thất bại riêng. Phải chọn giao thức hỗ trợ atomic commit nếu thực sự khả thi, hoặc thiết kế Saga/đối soát cho quá trình không có atomicity toàn cục.

Khi phân tích một kiến trúc thực tế, hãy tách riêng ba câu hỏi:

1. **Có những thao tác nào chồng lấn và chia sẻ dữ liệu?** Từ đó chọn cách điều khiển đồng thời.
2. **Những thao tác nào thực sự chạy cùng thời điểm trên tài nguyên độc lập?** Từ đó đánh giá song song và thông lượng.
3. **Một kết quả nghiệp vụ phải phối hợp qua bao nhiêu ranh giới commit/lỗi?** Từ đó quyết định cơ chế giao dịch phân tán, trạng thái trung gian, bù trừ và phục hồi.

Việc trả lời ba câu hỏi độc lập giúp tránh dùng một kỹ thuật để giải quyết sai loại vấn đề.

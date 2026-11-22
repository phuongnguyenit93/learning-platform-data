# Fencing token để ngăn tiến trình cũ tiếp tục ghi kết quả

Trong hệ thống dùng lease hoặc distributed lock, quyền sở hữu khóa thường có thời hạn. Nếu worker A bị treo lâu hơn thời hạn lease, hệ thống có thể cấp quyền cho worker B để công việc không bị đình trệ. Vấn đề là A có thể tỉnh lại sau đó và tiếp tục chạy như thể nó vẫn sở hữu tài nguyên. Nếu A ghi kết quả sau B, trạng thái mới có thể bị ghi đè bởi một tiến trình đã mất quyền.

**Fencing token** giải quyết vấn đề này bằng một số thứ tự tăng đơn điệu được cấp cho mỗi lần nhận quyền sở hữu. Mỗi lần một chủ thể mới lấy lease, nó nhận token lớn hơn token của lần sở hữu trước. Tài nguyên được bảo vệ lưu token lớn nhất đã chấp nhận và từ chối mọi thao tác mang token nhỏ hơn.

Điểm quyết định là nơi nhận kết quả phải kiểm tra token. Chỉ cấp token ở lock service mà không bắt database, object store hoặc dịch vụ đích kiểm tra token thì chưa bảo vệ được dữ liệu. Một tiến trình cũ vẫn có thể tiếp tục gửi lệnh; fencing token khiến tài nguyên đích nhận ra lệnh đó đến từ một thế hệ sở hữu cũ và từ chối nó.

## 1. Vì sao lease hết hạn chưa đủ?

Distributed lock thường dùng lease có thời hạn thay vì khóa vô thời hạn. Chủ sở hữu phải gia hạn lease định kỳ. Nếu worker chết, mất mạng hoặc không gia hạn được, lease hết hạn để worker khác có thể tiếp quản.

Tuy nhiên, lease chỉ cho lock service biết quyền sở hữu đã hết hạn. Nó không tự dừng tiến trình cũ, thu hồi CPU, hủy câu lệnh đang chạy ở hệ thống khác hay xóa thông điệp đã nằm trên mạng.

Ví dụ một worker xử lý tác vụ đồng bộ:

```text
Thời gian ---------------------------------------------------------->

Worker A: lấy lease ------------------ bị pause ---------------- tỉnh lại
          xử lý dữ liệu                (GC/network)                 ghi kết quả

Lease A:  [------------- còn hạn ------ hết hạn ]

Worker B:                               lấy lease mới
                                         xử lý và ghi kết quả
```

Nếu A bị pause lâu hơn lease, B có thể lấy quyền và hoàn tất công việc. Khi A tỉnh lại, nó không nhất thiết biết lease đã hết hạn. Nó có thể tiếp tục ghi dữ liệu cũ sau kết quả của B.

Các nguyên nhân thường gặp:

- Stop-the-world garbage collection hoặc tiến trình bị suspend.
- Máy ảo/container bị pause, host quá tải hoặc process bị scheduler trì hoãn.
- Network partition khiến worker không liên lạc được với lock service nhưng vẫn liên lạc được với database.
- Timeout hoặc lỗi gia hạn lease bị xử lý sai ở ứng dụng.
- Request ghi đã gửi trước khi lease hết hạn nhưng đến tài nguyên đích muộn.

Việc A tự kiểm tra “lease của tôi còn hạn không?” ngay trước khi ghi cũng chưa đủ. A có thể kiểm tra thành công, sau đó bị pause; lease hết hạn, B nhận lease mới và ghi; cuối cùng A tỉnh lại và gửi lệnh đã chuẩn bị. Cần một cơ chế mà tài nguyên đích có thể kiểm tra thứ tự quyền sở hữu tại chính thời điểm ghi.

## 2. Fencing token là gì?

Fencing token là một giá trị có thứ tự, thường là số nguyên 64-bit, được tăng mỗi khi lock service cấp một lần sở hữu mới cho cùng tài nguyên logic.

Ví dụ:

| Lần sở hữu | Chủ thể | Fencing token |
|---|---|---:|
| 1 | Worker A | 41 |
| 2 | Worker B | 42 |
| 3 | Worker C | 43 |

Token không phải mật khẩu hay UUID ngẫu nhiên. Tài nguyên đích có thể so sánh token mới với token đã chấp nhận:

```text
last_token = 41

request(token = 42) -> chấp nhận, cập nhật last_token = 42
request(token = 41) -> từ chối vì 41 < 42
request(token = 43) -> chấp nhận, cập nhật last_token = 43
```

Token cho biết request thuộc thế hệ sở hữu nào. Nó không cần liên tiếp tuyệt đối; có thể có khoảng trống nếu một lần cấp token không dẫn đến ghi dữ liệu. Điều quan trọng là token của lần sở hữu mới phải luôn lớn hơn token của mọi lần sở hữu trước cho cùng tài nguyên được bảo vệ.

Fencing token thường gắn với một lock key hoặc tài nguyên logic, chẳng hạn `inventory-sync:warehouse-7`, `report:2026-11` hoặc `account-reconciliation:branch-12`. Hai tài nguyên độc lập có thể dùng hai dãy token riêng nếu phạm vi bảo vệ không giao nhau. Nếu một token bảo vệ nhiều tài nguyên, tất cả nơi nhận ghi phải hiểu cùng một thứ tự token.

## 3. Timeline: tiến trình cũ bị chặn như thế nào?

Giả sử lease của A hết hạn và B nhận lease mới:

```text
1. A lấy lease cho job-7, nhận token 41.
2. A đọc dữ liệu và bắt đầu tính toán.
3. A bị pause lâu hơn TTL; lease hết hạn.
4. B lấy lease mới cho job-7, nhận token 42.
5. B hoàn tất và ghi kết quả kèm token 42.
6. Tài nguyên đích lưu last_token = 42.
7. A tỉnh lại và gửi kết quả cũ kèm token 41.
8. Tài nguyên đích thấy 41 < 42 và từ chối ghi.
```

Không cần lock service chủ động tìm và giết A. A có thể vẫn chạy, nhưng nó không thể ghi đè kết quả mới tại tài nguyên đã triển khai kiểm tra fencing.

```text
A: token 41       Lease hết hạn        B: token 42
------------┐          |               +--------------
xử lý       +-- pause -+---------------+ xử lý, ghi 42
            |                          | last_token=42
            +--------------------------+
                 A gửi ghi token 41
                        |
                        v
                  41 < 42: REJECT
```

Đây là lý do fencing token thường được dùng cùng lease: lease giúp chuyển quyền khi worker không còn hoạt động đúng hạn; token bảo vệ tài nguyên trước các request đến muộn từ chủ sở hữu cũ.

## 4. Ba thành phần cần có

Một thiết kế fencing token cần ít nhất ba phần:

1. **Lock/lease authority:** cấp quyền sở hữu và phát token tăng đơn điệu cho mỗi lần cấp mới.
2. **Worker/client:** đính token được cấp vào mọi thao tác ghi thuộc phạm vi lease.
3. **Protected resource:** lưu token lớn nhất đã chấp nhận và từ chối request mang token cũ hơn.

```text
              acquire / renew
Worker A --------------------------> Lock service
   ^                                      |
   |                                      | grant lease + token 41
   +--------------------------------------+
   |
   | write(value, token=41)
   v
Protected resource
   - đọc last_token
   - so sánh token của request
   - chỉ ghi nếu token không cũ hơn
```

Nếu thiếu bước kiểm tra tại protected resource, token chỉ là metadata để log. Nếu worker không gửi token, tài nguyên không có cơ sở để phân biệt request cũ và mới. Nếu token có thể quay về giá trị thấp sau khi lock service restart hoặc restore backup, cơ chế so sánh cũng mất tác dụng.

## 5. Cấp token tăng đơn điệu

Token phải được cấp theo thứ tự của các lần cấp quyền sở hữu thành công. Không nên tạo token bằng:

- UUID ngẫu nhiên: có thể duy nhất nhưng không có thứ tự lớn/nhỏ phản ánh lần sở hữu.
- Đồng hồ máy worker: đồng hồ có thể lệch, nhảy lùi hoặc không đồng bộ.
- Thời điểm hiện tại tính bằng millisecond: hai lần cấp có thể cùng timestamp, đồng hồ có thể điều chỉnh và độ phân giải không bảo đảm thứ tự.
- Bộ đếm cục bộ trong process: mất giá trị khi process restart và không phối hợp giữa nhiều máy.

Các lựa chọn phù hợp gồm:

- Sequence/counter bền vững trong database nếu database đó cũng đóng vai trò authority cấp lease.
- Revision hoặc version tăng đơn điệu do một hệ thống điều phối có tính nhất quán mạnh cấp.
- Counter được cập nhật nguyên tử cùng thao tác grant lease trong một dịch vụ điều phối có bảo đảm về thứ tự và durability.

Token mới có thể nhảy từ 41 lên 45. Không có yêu cầu phải tăng đúng một đơn vị; yêu cầu là không cấp lại một token cũ cho một lần sở hữu mới.

### 5.1. Ví dụ dùng database làm lease authority

Nếu database là nơi cấp lease, có thể dùng sequence bền vững. Bảng lease cần được tạo trước cho mỗi lock key:

```sql
CREATE SEQUENCE fencing_token_seq AS BIGINT START WITH 1;

CREATE TABLE job_lease (
    lock_name    VARCHAR(200) PRIMARY KEY,
    owner_id     VARCHAR(200),
    lease_until  TIMESTAMP,
    fence_token  BIGINT NOT NULL DEFAULT 0
);
```

Khi lease đang rảnh hoặc đã hết hạn, một transaction thử cấp quyền và token:

```sql
UPDATE job_lease
SET owner_id = :worker_id,
    lease_until = clock_timestamp() + INTERVAL '30 seconds',
    fence_token = nextval('fencing_token_seq')
WHERE lock_name = :lock_name
  AND (owner_id IS NULL OR lease_until < clock_timestamp())
RETURNING fence_token, lease_until;
```

Nếu trả về một dòng, worker nhận lease và token mới. Nếu không có dòng, lease đang do worker khác giữ hoặc lock key chưa được tạo. Ứng dụng phải commit việc cấp lease trước khi bắt đầu công việc; không giữ transaction database mở trong suốt thời gian xử lý.

Đây là ví dụ minh họa cho PostgreSQL. Cần xử lý trường hợp lease được gia hạn, owner tự nhả khóa, transaction cấp lease rollback và clock của database. Việc gia hạn cùng owner thường giữ nguyên token của lần sở hữu hiện tại; một lần cấp quyền mới sau khi lease hết hạn phải nhận token lớn hơn.

### 5.2. Token phải thuộc cùng một thứ tự cấp quyền

Không đủ nếu lock service cấp lease bằng một hệ thống còn token lấy từ một counter độc lập có thể chạy lệch thứ tự. Ví dụ, B nhận lease sau A nhưng do race ở counter lại nhận token nhỏ hơn A; protected resource sẽ không nhận ra B là owner mới.

Thao tác grant lease và tạo token phải được phối hợp sao cho token phản ánh thứ tự grant. Một counter có thể tăng ngay cả khi lần thử grant thất bại; điều đó chỉ tạo khoảng trống và không làm hỏng thứ tự. Điều không được phép là hai lần grant khác nhau nhận cùng token hoặc lần grant mới nhận token thấp hơn lần trước.

Token cũng không phải cơ chế xác thực. Nếu một client không đáng tin có thể tự gửi một số rất lớn, nó có thể đẩy `last_fencing_token` lên cao và khiến các owner hợp lệ tiếp theo bị từ chối. Protected resource vẫn phải xác thực caller, kiểm tra caller được phép dùng token đó và ràng buộc token với lock key/owner do authority cấp.

## 6. Kiểm tra token ngay tại tài nguyên đích

Tài nguyên đích phải nhớ token lớn nhất đã chấp nhận. Khi nhận một ghi mới, nó so sánh token request với token đã lưu và cập nhật dữ liệu cùng token trong một thao tác nguyên tử.

Ví dụ một bảng chứa trạng thái job:

```sql
CREATE TABLE job_result (
    job_id             BIGINT PRIMARY KEY,
    result_payload     TEXT,
    last_fencing_token BIGINT NOT NULL DEFAULT 0,
    updated_at         TIMESTAMP NOT NULL
);
```

Một lệnh ghi có điều kiện theo token:

```sql
UPDATE job_result
SET result_payload = :payload,
    last_fencing_token = :fence_token,
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = :job_id
  AND last_fencing_token <= :fence_token;
```

Nếu số dòng được cập nhật là 1, request được chấp nhận. Nếu số dòng là 0, token cũ hơn token đã được tài nguyên chấp nhận hoặc job không tồn tại; ứng dụng cần phân biệt hai trường hợp nếu nghiệp vụ cần.

Điều kiện `<=` cho phép cùng một owner gửi nhiều lần ghi với cùng token, đồng thời từ chối token nhỏ hơn. Khi token 42 đã được chấp nhận, request token 41 không thể ghi đè nó. Trong cùng một transaction, việc so sánh và cập nhật phải được DBMS thực hiện nguyên tử trên dòng/guard record.

### 6.1. Ví dụ diễn biến

| Thao tác | Token gửi lên | Token đã lưu trước thao tác | Kết quả | Token sau thao tác |
|---|---:|---:|---|---:|
| A ghi lần đầu | 41 | 0 | Chấp nhận | 41 |
| B ghi sau khi nhận lease mới | 42 | 41 | Chấp nhận | 42 |
| A tỉnh lại và ghi tiếp | 41 | 42 | Từ chối | 42 |
| B ghi lần nữa | 42 | 42 | Chấp nhận | 42 |
| C nhận lease kế tiếp và ghi | 43 | 42 | Chấp nhận | 43 |

Việc từ chối phải xảy ra ở nơi dữ liệu được thay đổi. Nếu ứng dụng chỉ kiểm tra token trong bộ nhớ worker rồi gửi một `UPDATE` không có điều kiện, tiến trình cũ vẫn có thể ghi.

### 6.2. Token và optimistic version là hai thứ khác nhau

Fencing token phân biệt các thế hệ sở hữu lease. Nó không tự giải quyết hai thao tác ghi đồng thời của cùng một owner.

Nếu hai thread của worker B cùng dùng token 42 và cùng đọc một giá trị rồi ghi đè lẫn nhau, cả hai request đều có token hợp lệ. Để tránh lost update trong cùng một thế hệ, có thể cần thêm version của bản ghi, compare-and-swap, row lock hoặc tuần tự hóa thao tác trong worker.

Ví dụ kết hợp fencing token và optimistic version:

```sql
UPDATE job_result
SET result_payload = :payload,
    last_fencing_token = :fence_token,
    row_version = row_version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = :job_id
  AND last_fencing_token <= :fence_token
  AND row_version = :expected_version;
```

Điều kiện token bảo vệ khỏi owner cũ; điều kiện `row_version` bảo vệ khỏi việc ghi dựa trên phiên bản dữ liệu cũ trong cùng thế hệ. Hai cơ chế có mục đích khác nhau và có thể cần dùng cùng nhau.

## 7. Một chi tiết quan trọng: token mới đã được cấp nhưng chưa ghi thì sao?

Fencing token bảo đảm thứ tự tại tài nguyên đã quan sát token mới. Giả sử B đã nhận token 42 từ lock service nhưng chưa gửi bất kỳ lệnh nào tới database. Database vẫn đang lưu `last_fencing_token = 41`. Nếu A tỉnh lại và gửi ghi token 41 trước khi database nhìn thấy token 42, lệnh của A có thể vẫn được chấp nhận.

Vì vậy, bảo đảm cơ bản của fencing là: **sau khi tài nguyên đã chấp nhận token mới, mọi request mang token cũ hơn sẽ bị từ chối**. Nó không tự động tạo một thao tác thu hồi tức thời xuyên qua hai hệ thống độc lập vào đúng thời điểm lock service cấp lease mới.

Nếu yêu cầu nghiệp vụ là ngay khi B nhận lease thì A tuyệt đối không được ghi thêm dù B chưa ghi dữ liệu, cần thêm một bước đồng bộ: B phải đăng ký/đẩy token mới vào guard record của tài nguyên trước khi xử lý, và chỉ bắt đầu phần việc được bảo vệ sau khi thao tác đăng ký thành công. Khi guard đã lưu 42, các ghi token 41 tiếp theo bị từ chối.

```text
B nhận lease token 42
          |
          v
B đăng ký token 42 tại protected resource
          |
          v
Resource lưu last_token = 42
          |
          v
B mới bắt đầu ghi kết quả

A gửi token 41 ----------------------> bị từ chối
```

Ngay cả cách này cũng cần định nghĩa rõ thời điểm chuyển quyền có hiệu lực: trước hay sau khi guard được cập nhật. Nếu việc cập nhật guard thất bại, B chưa được coi là đã sẵn sàng thực hiện công việc có tác dụng. Với yêu cầu cần tính nguyên tử xuyên nhiều hệ thống, phải dùng một giao thức phối hợp phù hợp; không thể đạt atomic revocation chỉ bằng một counter độc lập.

## 8. Bảo vệ nhiều bảng hoặc nhiều tài nguyên

Một công việc có thể ghi nhiều bảng: trạng thái job, kết quả, lịch sử và bảng tổng hợp. Nếu chỉ một bảng kiểm tra token còn các bảng khác ghi tự do, worker cũ vẫn có thể làm sai một phần dữ liệu.

Có hai hướng thường dùng:

### 8.1. Guard row chung trong cùng database

Tạo một dòng guard cho mỗi lock key, lưu token lớn nhất đã được đăng ký. Mọi transaction ghi dữ liệu được bảo vệ phải khóa hoặc cập nhật guard và thực hiện các thay đổi nghiệp vụ trong cùng transaction:

```sql
BEGIN;

UPDATE resource_guard
SET last_fencing_token = :fence_token
WHERE resource_key = :resource_key
  AND last_fencing_token <= :fence_token;

-- Ứng dụng yêu cầu row count = 1.
-- Nếu bằng 0: ROLLBACK và báo stale owner.

UPDATE job_result
SET result_payload = :payload
WHERE job_id = :job_id;

INSERT INTO job_history (...)
VALUES (...);

COMMIT;
```

Guard và các bảng nghiệp vụ phải nằm trong cùng transaction database. Nếu guard được cập nhật ở transaction riêng rồi dữ liệu nghiệp vụ ghi ở transaction khác, tiến trình có thể bị dừng giữa hai bước và để lại trạng thái dở dang. Nếu có nhiều lock key, phải cập nhật guard theo thứ tự ổn định để tránh deadlock.

### 8.2. Mỗi tài nguyên đích tự kiểm tra token

Nếu dữ liệu nằm ở nhiều dịch vụ hoặc storage khác nhau, mỗi nơi có thể duy trì token lớn nhất đã chấp nhận cho resource tương ứng. Worker phải gửi token trong mọi request và mỗi dịch vụ phải kiểm tra nó trước khi thay đổi trạng thái.

Đây là yêu cầu xuyên suốt: database kiểm tra token không bảo vệ object store nếu object store vẫn nhận lệnh ghi không có token; API kiểm tra token không bảo vệ message broker nếu consumer downstream bỏ qua token. Mọi điểm có thể tạo tác dụng phụ cần có cách từ chối thao tác cũ hoặc nhận sự kiện theo một giao thức có thứ tự.

## 9. Fencing token trong worker queue

Một queue có thể giao cùng một job cho worker khác khi visibility timeout hoặc lease hết hạn. Worker cũ có thể vẫn đang xử lý sau khi queue đã cho phép giao lại.

Ví dụ:

```text
Job J được giao cho Worker A
  A nhận token 100
  A bắt đầu tạo báo cáo

Visibility timeout hết hạn
  Queue giao lại J cho Worker B
  B nhận token 101
  B hoàn tất báo cáo và lưu kết quả với token 101

Worker A hoàn tất muộn
  A gửi kết quả với token 100
  Storage thấy 100 < 101
  Storage từ chối ghi
```

Trong queue-based system, cần tách ba thao tác:

- **Nhận việc:** queue/lease authority cấp quyền và token mới.
- **Ghi kết quả:** storage kiểm tra token và chỉ nhận token không cũ hơn token đã thấy.
- **Ack job:** worker xác nhận hoàn thành sau khi kết quả đã được lưu thành công. Nếu ack thất bại, job có thể được giao lại; idempotency và fencing vẫn cần thiết.

Không nên ack job trước khi kết quả được commit, vì worker có thể mất việc trong khi dữ liệu chưa được lưu. Cũng không nên coi ack là hàng rào bảo vệ dữ liệu: queue biết trạng thái giao việc, còn storage mới là nơi cần từ chối ghi cũ.

## 10. Fencing token không thay thế idempotency

Hai cơ chế xử lý hai vấn đề khác nhau:

| Cơ chế | Ngăn vấn đề gì? | Ví dụ |
|---|---|---|
| Fencing token | Owner cũ tiếp tục ghi sau khi quyền đã chuyển sang owner mới | Worker A token 41 không thể ghi sau khi resource đã chấp nhận token 42 |
| Idempotency key | Cùng một yêu cầu bị xử lý nhiều lần do retry hoặc message giao lại | Hai lần nhận cùng payment request key chỉ tạo một kết quả nghiệp vụ |
| Optimistic version | Ghi đè dựa trên phiên bản dữ liệu cũ, kể cả cùng owner | Chỉ update nếu `row_version` vẫn bằng version đã đọc |
| Lease/heartbeat | Phát hiện owner không gia hạn và cho phép chủ thể khác tiếp quản | Worker B nhận việc sau khi lease của A hết hạn |

Một worker hợp lệ có token 42 vẫn có thể xử lý cùng một message hai lần nếu code retry không có idempotency key. Ngược lại, idempotency key không nhất thiết ngăn một worker cũ ghi một payload khác vào resource sau khi worker mới đã hoàn tất. Hệ thống có thể cần cả hai.

## 11. Những lỗi triển khai thường gặp

**Dùng UUID làm fencing token.** UUID có thể định danh lần sở hữu nhưng không cho biết token nào mới hơn. Cần một giá trị tăng đơn điệu có thứ tự.

**Dùng timestamp của worker.** Đồng hồ máy có thể lệch hoặc nhảy lùi. Token phải do authority cấp theo thứ tự grant, không lấy từ thời gian cục bộ.

**Chỉ kiểm tra lease ở worker.** Worker có thể bị pause sau lần kiểm tra. Tài nguyên đích phải kiểm tra token tại thời điểm ghi.

**Không lưu token lớn nhất đã chấp nhận.** Nếu resource không nhớ token trước đó, nó không thể phát hiện request cũ đến muộn.

**Cập nhật token và dữ liệu trong hai transaction riêng.** Tiến trình có thể bị dừng giữa hai thao tác. Guard và dữ liệu nghiệp vụ cần được thay đổi nguyên tử tại cùng resource khi có thể.

**Chỉ bảo vệ một trong nhiều hệ thống ghi.** Một dịch vụ có thể từ chối token cũ trong khi object store hoặc downstream API vẫn nhận lệnh cũ. Phải xác định toàn bộ điểm có tác dụng phụ.

**Reset counter khi restart hoặc restore.** Token mới có thể thấp hơn token resource đã lưu. Counter phải bền vững, không tái sử dụng giá trị và có kế hoạch phục hồi nhất quán.

**Cho rằng token mới được cấp là đã thu hồi tức thời token cũ ở mọi nơi.** Bảo đảm có hiệu lực khi resource quan sát token mới; nếu cần ranh giới chuyển quyền chặt hơn, phải đăng ký token mới tại resource trước khi xử lý.

**Cho phép nhiều thread cùng ghi bằng một token mà không có versioning.** Fencing chỉ phân biệt thế hệ owner, không tuần tự hóa mọi thao tác bên trong cùng owner.

## 12. Vận hành và quan sát

Để chẩn đoán, log nên ghi nhận:

- Lock key hoặc resource key.
- Owner ID và fencing token được cấp.
- Thời điểm lấy lease, thời điểm gia hạn và thời điểm hết hạn.
- Request ID/job ID và token đính kèm mỗi lần ghi.
- Token lớn nhất resource đang lưu khi từ chối.
- Lý do từ chối: token cũ, lease không hợp lệ, version dữ liệu không khớp hay lỗi khác.
- Số lần retry, số lần lease hết hạn và số request stale bị chặn.

Các metric hữu ích gồm tỷ lệ lease timeout, số lần worker phải tiếp quản, số stale write bị từ chối, thời gian từ lúc cấp token đến lần ghi đầu tiên và độ trễ xử lý job. Nếu stale write bị từ chối tăng đột biến, có thể worker bị pause quá lâu, TTL quá ngắn, network bất ổn hoặc thời gian xử lý không phù hợp với lease.

Không ghi payload nhạy cảm hoặc thông tin xác thực của lock service vào log. Owner ID, token, resource key đã chuẩn hóa và request ID thường đủ để liên kết sự kiện.

## 13. Quy trình thiết kế fencing cho một tác vụ

Khi áp dụng fencing token, hãy xác định rõ:

1. Resource key nào cần bảo vệ và phạm vi token áp dụng là một job, một tài khoản, một partition hay một tài nguyên khác?
2. Thành phần nào là authority duy nhất cấp lease và token?
3. Token được tăng đơn điệu và lưu bền vững bằng cơ chế nào?
4. Token có được cấp trong cùng thao tác nguyên tử với grant lease không?
5. Worker nhận token ở đâu và đính nó vào mọi request ghi như thế nào?
6. Tài nguyên đích lưu token lớn nhất đã chấp nhận ở đâu?
7. So sánh token và ghi dữ liệu có nguyên tử tại resource không?
8. Nếu có nhiều bảng/dịch vụ, mỗi điểm ghi có thực thi fencing không?
9. Owner mới cần đăng ký token tại resource trước khi bắt đầu xử lý hay chấp nhận bảo đảm theo lần ghi đầu tiên?
10. Cùng owner có cần optimistic version hoặc tuần tự hóa riêng để tránh lost update không?
11. Request gửi lặp có idempotency key không?
12. Counter và token state được khôi phục thế nào sau failover, backup restore hoặc disaster recovery?

Một bài kiểm thử quan trọng là cố ý pause worker A sau khi nhận token 41, để lease hết hạn, cho B nhận token 42 và ghi thành công, rồi cho A chạy tiếp. Kết quả mong đợi là resource từ chối mọi ghi mang token 41 sau khi đã lưu token 42. Cũng cần kiểm thử tình huống B đã nhận 42 nhưng chưa đăng ký nó ở resource để xác nhận ranh giới bảo đảm của hệ thống.

## 14. Kết luận

Lease giúp hệ thống thu hồi quyền sở hữu khi worker không gia hạn đúng hạn, nhưng không thể tự dừng tiến trình cũ hoặc thu hồi request đã gửi. Fencing token bổ sung một thứ tự thế hệ: mỗi lần cấp quyền mới nhận token lớn hơn, worker gửi token kèm thao tác ghi và tài nguyên đích từ chối token nhỏ hơn token lớn nhất đã chấp nhận.

Để cơ chế có tác dụng, token phải tăng đơn điệu và bền vững, grant lease phải được phối hợp với việc cấp token, còn so sánh token phải xảy ra tại chính nơi thay đổi dữ liệu. Khi nhiều bảng hoặc dịch vụ tham gia, mọi điểm có thể ghi tác dụng phụ đều phải thực thi cùng quy tắc. Fencing bảo vệ khỏi owner cũ; idempotency bảo vệ khỏi request lặp; optimistic version bảo vệ khỏi cập nhật dựa trên dữ liệu cũ trong cùng một thế hệ. Kết hợp đúng các cơ chế này giúp worker queue và tác vụ phân tán duy trì kết quả đúng ngay cả khi lease hết hạn, tiến trình bị pause hoặc thông điệp đến muộn.

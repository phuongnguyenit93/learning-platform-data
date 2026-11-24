# Expired record cleanup — Dọn dẹp bản ghi hết hạn

Trong luồng khôi phục tài khoản, mỗi yêu cầu có thể tạo token đặt lại mật khẩu, challenge xác minh quyền sở hữu, phiên recovery giới hạn hoặc yêu cầu thay thế MFA/passkey. Những bản ghi này cần được lưu đủ lâu để xử lý đúng nghiệp vụ, rồi được dọn theo chính sách lưu giữ dữ liệu.

**Thời điểm bản ghi hết quyền sử dụng và thời điểm được phép xóa là hai mốc khác nhau.** Một token đã hết hạn phải bị từ chối ngay cả khi tác vụ cleanup đang ngừng hoạt động. Ngược lại, token không còn sử dụng được vẫn có thể cần lưu dấu vết tối thiểu để phát hiện phát lại, xử lý sự cố hoặc hoàn tất công việc liên quan.

Bài học này tập trung vào persistence của account recovery: xác định bản ghi đủ điều kiện xóa, xử lý đồng thời với luồng xác thực, dọn theo lô và theo dõi tồn đọng. Các thời lượng và kích thước lô trong ví dụ chỉ phục vụ minh họa thiết kế.

## 1. Hết hạn phải có hiệu lực trong luồng xử lý yêu cầu

Giả sử một liên kết đặt lại mật khẩu hết hạn lúc `10:15:00Z`, còn cleanup chạy lần tiếp theo lúc `10:20:00Z`.

Tại `10:17:00Z`, bản ghi vẫn có thể tồn tại trong cơ sở dữ liệu. Điều đó không làm token hợp lệ. Endpoint phải kiểm tra thời hạn cùng các điều kiện khác trước khi cho phép thay đổi tài khoản.

Có thể mô tả điều kiện hợp lệ của một challenge như sau:

```text
đúng tenant và đúng tài khoản trong ngữ cảnh xử lý
AND đúng mục đích recovery
AND bằng chứng token khớp
AND trạng thái là PENDING
AND thời điểm kiểm tra < expires_at
AND các điều kiện rủi ro/chính sách còn thỏa mãn
```

Tại đúng `expires_at`, challenge đã hết hạn. Hai phía dùng cùng quy ước:

```text
Hợp lệ theo thời gian: now < expires_at
Hết hạn theo thời gian: expires_at <= now
```

OWASP yêu cầu token đặt lại mật khẩu được lưu an toàn, dùng một lần và hết hạn sau một khoảng phù hợp. Chính sách cleanup cần giữ được các tính chất đó khi bản ghi vẫn còn trong kho lưu trữ. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Không dùng logic “tìm thấy token thì cho phép”. Không coi việc scheduler đã chạy hay chưa là điều kiện cấp quyền recovery.

## 2. Ba khái niệm cần tách trong mô hình dữ liệu

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Expiration | Bằng chứng hoặc phiên không còn quyền sử dụng sau một mốc thời gian | Token đặt lại mật khẩu hết hạn |
| Invalidation | Quyền sử dụng bị chấm dứt bởi một sự kiện | Token đã dùng, bị thu hồi hoặc bị thay thế |
| Purge eligibility | Dữ liệu đã thỏa điều kiện để xóa khỏi kho hoạt động | Đã qua thời hạn lưu giữ và không có công việc phụ thuộc |

Một token được sử dụng thành công lúc `10:05Z` có thể hết hạn tự nhiên lúc `10:15Z`, nhưng bản ghi chỉ được xóa sau đó theo chính sách. Tác vụ cleanup không cần chờ đến ngày xóa mới ngăn lần sử dụng thứ hai.

Trạng thái `PENDING` cũng không đủ để kết luận token còn hiệu lực: một bản ghi `PENDING` có thể đã quá `expires_at`. Có thể biểu diễn trạng thái hết hạn bằng điều kiện thời gian, không bắt buộc cập nhật hàng loạt mọi dòng sang `EXPIRED`.

Nếu cần phát sinh sự kiện khi hết hạn, việc chuyển trạng thái và phát sự kiện phải có thiết kế riêng. Một lệnh xóa trực tiếp không thay thế được quy trình nghiệp vụ đó.

## 3. Xây dựng chính sách xóa theo loại dữ liệu

Không áp một TTL duy nhất cho mọi bảng có liên quan đến recovery.

| Loại dữ liệu | Điều kiện cần xem xét trước khi dọn | Sai lầm cần tránh |
| --- | --- | --- |
| Token hoặc challenge recovery tạm thời | Hết quyền sử dụng, qua thời hạn lưu giữ, không còn phụ thuộc | Giữ token còn hiệu lực chỉ vì job chưa chạy |
| Phiên recovery giới hạn | Hết hạn hoặc đã bị thu hồi; tác vụ phụ thuộc đã xử lý | Xóa phiên recovery rồi mặc định phiên đăng nhập khác cũng bị thu hồi |
| Dấu chặn phát lại hoặc thu hồi | Mọi bằng chứng mà dấu chặn bảo vệ đã hết khả năng được chấp nhận | Xóa dấu chặn trong khi token tự chứa còn hạn |
| Dữ liệu chống lạm dụng | Cửa sổ đếm, thời gian khóa và chính sách lưu giữ đã kết thúc | Reset bộ đếm bằng cleanup token |
| Audit sự kiện recovery | Theo chính sách audit riêng; chỉ giữ thông tin cần thiết | Cascade xóa mất bằng chứng điều tra |
| Hồ sơ xác minh danh tính | Theo chính sách dữ liệu nhạy cảm và trạng thái hồ sơ | Giữ ảnh giấy tờ chỉ vì token còn trong bảng |
| Credential MFA/passkey đang đăng ký | Theo vòng đời credential | Xóa credential vì challenge dùng để đăng ký nó đã hết hạn |

Trong thiết kế minh họa của bài, `purge_after` là thời điểm sớm nhất có thể xem xét xóa một challenge. Giá trị này không phải thời hạn hiệu lực mới của token.

```text
expires_at  = thời điểm cuối cùng trước đó token có thể được chấp nhận
purge_after = thời điểm sớm nhất bản ghi có thể đủ điều kiện xóa
```

Ví dụ chọn lưu bản ghi challenge đến sau `expires_at` một khoảng để hỗ trợ vận hành là một quyết định thiết kế. Khoảng giữ thêm không được cộng vào thời hạn chấp nhận token.

Nếu có nhiều ràng buộc lưu giữ, `purge_after` phải phản ánh mốc cần giữ lâu nhất. Các phụ thuộc như hồ sơ điều tra đang mở hoặc sự kiện outbox chưa xử lý còn có thể chặn xóa dù mốc thời gian đã qua. Chính sách cần có chủ sở hữu và được rà soát để tránh giữ dữ liệu vô thời hạn.

## 4. Mô hình bảng minh họa

Ví dụ dưới đây dùng PostgreSQL và chỉ mô tả bảng challenge phục vụ bài học:

```sql
CREATE TABLE recovery_challenge (
    tenant_id     uuid        NOT NULL,
    id            uuid        NOT NULL,
    account_id    uuid        NOT NULL,
    purpose       text        NOT NULL,
    token_digest  bytea       NOT NULL,
    state         text        NOT NULL
                              CHECK (state IN ('PENDING', 'USED', 'REVOKED')),
    issued_at     timestamptz NOT NULL,
    expires_at    timestamptz NOT NULL,
    used_at       timestamptz,
    purge_after   timestamptz NOT NULL,
    cleanup_hold  boolean     NOT NULL DEFAULT false,

    PRIMARY KEY (tenant_id, id),
    CHECK (expires_at > issued_at),
    CHECK (purge_after >= expires_at),
    CHECK (
        (state = 'USED' AND used_at IS NOT NULL)
        OR
        (state <> 'USED' AND used_at IS NULL)
    )
);

CREATE INDEX recovery_challenge_cleanup_idx
    ON recovery_challenge (tenant_id, purge_after, id)
    WHERE cleanup_hold = false;
```

Các lựa chọn trong mô hình này có ý nghĩa cụ thể:

- `token_digest` chứa giá trị kiểm chứng phù hợp, không chứa token bearer nguyên bản. Cách bảo vệ mã OTP ít entropy cần được thiết kế riêng; đặt tên cột là “digest” không tự làm mã ngắn an toàn.
- `purpose` ngăn dùng bằng chứng cho sai thao tác, chẳng hạn dùng token đặt lại mật khẩu để thay MFA.
- `tenant_id` là một phần của định danh và của mọi điều kiện truy cập trong ví dụ.
- `purge_after >= expires_at` là chính sách bảo thủ của bảng minh họa: giữ bản ghi ít nhất đến khi hết hạn tự nhiên, kể cả khi đã dùng hoặc bị thu hồi sớm.
- `cleanup_hold` chặn xóa theo một quy trình quản lý lưu giữ riêng. Quyền bật/tắt cờ này không thuộc tùy ý scheduler.

Hệ thống thực tế có thể cho phép xóa sớm phần bí mật của bản ghi đã dùng và chỉ giữ một dấu vết tối thiểu. Khi đó phải mô hình hóa vòng đời dữ liệu khác với bảng trên, thay vì bỏ ràng buộc mà không xác định ảnh hưởng đến chống phát lại.

Không thêm khóa ngoại `ON DELETE CASCADE` từ challenge đến audit chỉ để lệnh cleanup dễ chạy. Những bảng có vòng đời khác nhau cần được thiết kế quan hệ và thứ tự dọn rõ ràng.

## 5. Chọn thời gian tham chiếu nhất quán

Các mốc được lưu dưới dạng thời điểm tuyệt đối; giao diện có thể hiển thị theo múi giờ người dùng. Không dựa vào ngày theo giờ địa phương hoặc đồng hồ từ trình duyệt để quyết định token còn hạn.

Trong PostgreSQL:

- `CURRENT_TIMESTAMP` và `now()` lấy thời điểm bắt đầu transaction.
- `statement_timestamp()` lấy thời điểm bắt đầu câu lệnh.
- `clock_timestamp()` lấy thời gian thực lúc gọi, có thể thay đổi trong một câu lệnh.

Đây là khác biệt ngữ nghĩa cần cân nhắc khi transaction kéo dài. [PostgreSQL: Date/Time Functions](https://www.postgresql.org/docs/16/functions-datetime.html)

Với cleanup, có thể lấy một `cutoff` từ đồng hồ cơ sở dữ liệu cho mỗi lô rồi truyền cùng giá trị vào toàn bộ điều kiện của lô. Khi đó việc chọn ứng viên và việc xóa dùng chung một ranh giới.

```text
expires_at <= cutoff
AND purge_after <= cutoff
AND cleanup_hold = false
```

Giá trị `cutoff` phải do backend tin cậy xác định. Không nhận nó từ tham số API của người dùng. Một lô dùng cutoff cũ có thể dọn chậm; một cutoff sai nằm quá xa trong tương lai có thể xóa cả challenge đang cần sử dụng.

Giám sát sai lệch đồng hồ vẫn cần thiết. Dùng thời gian cơ sở dữ liệu giúp thống nhất quyết định giữa các node, nhưng không bảo vệ hệ thống khỏi một đồng hồ nguồn bị cấu hình sai.

## 6. Bảo đảm cleanup không tạo cuộc đua cấp quyền

### 6.1. Tiêu thụ challenge bằng một thay đổi có điều kiện

Không thực hiện chuỗi “SELECT thấy còn hạn → xử lý lâu → UPDATE không có điều kiện”. Trong khoảng giữa hai thao tác, challenge có thể bị dùng bởi yêu cầu khác hoặc không còn hợp lệ.

Ví dụ dưới đây minh họa bước tiêu thụ challenge; các tham số có dấu `:` là tham số bind, không phải chuỗi được nối vào SQL:

```sql
UPDATE recovery_challenge
SET state = 'USED',
    used_at = statement_timestamp()
WHERE tenant_id = :tenant_id
  AND id = :challenge_id
  AND purpose = :expected_purpose
  AND token_digest = :presented_token_digest
  AND state = 'PENDING'
  AND expires_at > statement_timestamp()
RETURNING account_id;
```

Chỉ một dòng được cập nhật mới là tín hiệu tiêu thụ thành công. Không có dòng trả về thì không được tiếp tục đổi mật khẩu hay thay phương thức xác thực.

Trong ví dụ, thời hạn được xét tại thời điểm bắt đầu câu lệnh tiêu thụ. Nếu chính sách yêu cầu kiểm tra tại thời điểm sau khi lấy khóa hoặc ngay trước thay đổi tài khoản, phải bổ sung bước kiểm tra tại ranh giới đó; câu lệnh trên không chứng minh token còn hạn tại thời điểm commit.

Bước tiêu thụ và thay đổi tài khoản cần nằm trong transaction nghiệp vụ phù hợp. Những điều kiện khác như quyền của phiên recovery, trạng thái tài khoản và chính sách rủi ro vẫn phải được kiểm tra. Một câu UPDATE thành công không thay thế toàn bộ xác minh danh tính.

Nếu thu hồi session được chuyển sang một hệ thống khác, phải có cơ chế giao việc bền vững và ranh giới cấp quyền phù hợp. Không để cleanup xóa bản ghi mà tiến trình thu hồi session vẫn cần đọc.

### 6.2. Khi cleanup chạy đồng thời

Xét một challenge đã đủ điều kiện dọn:

- Nếu cleanup xóa trước, bước tiêu thụ không tìm thấy challenge và phải từ chối.
- Nếu yêu cầu nghiệp vụ đang giữ khóa dòng, cleanup có thể bỏ qua dòng đó để xử lý sau.
- Nếu một yêu cầu tiêu thụ đã hoàn tất, cleanup có thể xóa theo chính sách; việc xóa không được phục hồi hay thực hiện lại thay đổi tài khoản.
- Nếu có công việc kéo dài qua nhiều transaction và còn cần bản ghi, hệ thống phải thể hiện phụ thuộc bền vững để chặn xóa. Khóa dòng chỉ bảo vệ trong transaction đang giữ khóa.

Không xử lý “bản ghi đã bị cleanup” bằng cách tự tái tạo challenge từ dữ liệu token do client gửi lên. Với luồng dựa trên bản ghi cho phép, bản ghi không tồn tại phải dẫn đến từ chối.

## 7. Dọn theo lô có khóa dòng

Một lệnh xóa toàn bộ dữ liệu cũ trong một transaction lớn có thể giữ khóa lâu, tạo nhiều WAL và cạnh tranh tài nguyên với endpoint recovery. Cách triển khai minh họa là xử lý một số lượng giới hạn mỗi transaction.

```sql
WITH candidates AS MATERIALIZED (
    SELECT tenant_id, id
    FROM recovery_challenge
    WHERE tenant_id = :tenant_id
      AND cleanup_hold = false
      AND expires_at <= :cutoff
      AND purge_after <= :cutoff
    ORDER BY purge_after, id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
DELETE FROM recovery_challenge AS target
USING candidates
WHERE target.tenant_id = candidates.tenant_id
  AND target.id = candidates.id
  AND target.cleanup_hold = false
  AND target.expires_at <= :cutoff
  AND target.purge_after <= :cutoff;
```

`DELETE ... USING` là cú pháp PostgreSQL cho phép chọn dòng xóa thông qua bảng hoặc tập kết quả khác; số dòng bị xóa được trả về qua command result. [PostgreSQL: DELETE](https://www.postgresql.org/docs/16/sql-delete.html)

Trong ví dụ:

1. CTE chọn tối đa `batch_size` ứng viên trong đúng tenant.
2. Thứ tự `purge_after, id` ưu tiên bản ghi cũ và có khóa phụ phân định thứ tự.
3. Khóa dòng được lấy ngay trong CTE.
4. Lệnh DELETE giữ lại các điều kiện bảo vệ thay vì chỉ xóa theo danh sách ID.
5. Transaction kết thúc sau một lô để giải phóng tài nguyên sớm.

`SKIP LOCKED` bỏ qua dòng không thể khóa ngay, phù hợp với cách nhiều tiến trình cùng lấy công việc. Nó cung cấp một góc nhìn không đầy đủ và không loại bỏ mọi loại chờ khóa. [PostgreSQL: SELECT — Locking Clause](https://www.postgresql.org/docs/16/sql-select.html)

Vì vậy, một lô xóa được `0` dòng chỉ cho biết lần thử đó không xóa được dòng nào. Nó không chứng minh toàn bộ backlog đã hết: có thể các dòng cần dọn đều đang bị khóa.

`batch_size` phải là số nguyên dương có giới hạn phía backend. Không cho cấu hình NULL biến thao tác thành quét không giới hạn. Giá trị như 500 dòng có thể là điểm bắt đầu để đo đạc, không phải kích thước đúng cho mọi hệ thống.

Mẫu SQL này giả định bản ghi đã đủ điều kiện nghiệp vụ để xóa. Nếu có outbox, bảng con hoặc hồ sơ điều tra phụ thuộc, điều kiện và quy trình phải được mở rộng trước khi áp dụng.

## 8. Vòng chạy scheduler có ngân sách

Một lượt cleanup nên có giới hạn thời gian và số lô, thay vì cố đuổi đến khi bảng hoàn toàn sạch trong giờ cao điểm.

Mã giả:

```text
xác định tenant hoặc phân vùng được giao
kiểm tra batch_size và ngân sách lượt chạy

lặp khi chưa hết ngân sách và chưa vượt số lô:
    lấy cutoff từ đồng hồ cơ sở dữ liệu
    mở transaction ngắn
    xóa một lô bằng cutoff và phạm vi đã xác định
    commit
    ghi nhận số dòng đã commit và thời gian xử lý

    nếu không xóa được dòng nào:
        kết thúc lượt hiện tại

    nếu cơ sở dữ liệu đang quá tải:
        dừng hoặc giảm tốc theo chính sách

lên lịch lượt tiếp theo theo cơ chế vận hành
```

Ngân sách thời gian chạy có thể đo bằng đồng hồ đơn điệu của tiến trình. Các mốc nghiệp vụ `expires_at` và `purge_after` vẫn dùng thời gian tuyệt đối đã thống nhất.

Khi gặp timeout hoặc deadlock, rollback lô hiện tại. Chỉ retry lỗi tạm thời với số lần giới hạn và khoảng chờ có jitter. Lỗi quyền truy cập, sai schema hoặc vi phạm quan hệ dữ liệu cần được xử lý theo nguyên nhân; không tăng tốc retry.

Không đánh dấu tiến độ xóa trước commit. Nếu mất kết nối và không rõ commit thành công hay chưa, lần chạy kế tiếp dùng lại điều kiện xóa để tìm phần còn lại, không suy diễn rằng mọi ứng viên cũ đều còn tồn tại.

## 9. Nhiều instance và tính lặp lại an toàn

Cleanup cần chịu được việc scheduler chạy trùng, tiến trình bị khởi động lại và thông báo công việc được giao nhiều lần.

Với thao tác chỉ xóa những dòng còn tồn tại và vẫn đủ điều kiện:

```text
lượt thứ nhất: xóa một số dòng đủ điều kiện
lượt lặp lại: chỉ còn các dòng chưa xóa hoặc mới đủ điều kiện
```

Đó là tính lặp lại an toàn của thao tác xóa theo điều kiện. Nó không có nghĩa mọi side effect đi kèm tự động xảy ra đúng một lần.

Nếu mỗi dòng bị xóa còn phải tạo audit, cập nhật thống kê nghiệp vụ hoặc gửi sự kiện, cần thiết kế transaction/outbox và định danh sự kiện để tránh mất hoặc nhân đôi side effect.

Có thể chọn một trong hai cách điều phối:

| Cách điều phối | Điểm cần kiểm soát |
| --- | --- |
| Một tiến trình được giao mỗi tenant hoặc phân vùng | Gia hạn, hết hạn và chuyển quyền sở hữu công việc |
| Nhiều tiến trình cùng lấy lô có khóa dòng | Kích thước lô, giới hạn đồng thời, dòng bị bỏ qua nhiều lần |

Vẫn cần lượt quét lại. Một dòng bị khóa trong nhiều lần chạy không được biến thành dữ liệu bị bỏ quên vĩnh viễn. Đo độ tuổi bản ghi đủ điều kiện nhưng còn tồn tại để phát hiện trường hợp này.

## 10. Cache, outbox và dấu chặn thu hồi

### Cache không được kéo dài quyền sử dụng

Nếu bản ghi challenge được cache, cache phải giữ thời điểm hết hạn tuyệt đối và trạng thái cần thiết. TTL cache chỉ quản lý vòng đời bản sao.

Một token đã dùng trong cơ sở dữ liệu không được chấp nhận lại từ cache cũ. Bước thay đổi tài khoản cuối cùng cần kiểm tra nguồn quyền có tính nhất quán phù hợp, chẳng hạn câu UPDATE có điều kiện ở trên.

Cleanup bản ghi trong cơ sở dữ liệu cũng không bảo đảm mọi bản sao cache được xóa tức thì. Thiết kế cache phải chịu được bản sao cũ mà vẫn từ chối bằng chứng không còn hợp lệ.

### Outbox phải có đủ dữ liệu để hoàn tất công việc

Nếu consumer nhận sự kiện rồi tra lại challenge đã bị xóa, công việc có thể thất bại. Có thể chọn một trong các thiết kế:

- Sự kiện chứa snapshot tối thiểu cần thiết, tránh sao chép token hoặc thông tin nhạy cảm không cần dùng.
- Bản ghi được giữ cho đến khi phụ thuộc bền vững đã hoàn tất.
- Dữ liệu công việc dài hạn nằm trong bảng riêng có vòng đời rõ ràng.

Không đặt quan hệ khóa ngoại ngược khiến việc xóa challenge tự động xóa cả sự kiện outbox chưa gửi.

### Dấu chặn có thể cần tồn tại lâu hơn challenge

Với token tự chứa, việc xóa một bản ghi recovery bất kỳ không tự làm token mất hiệu lực ở mọi nơi chấp nhận nó.

Đặc biệt, nếu sự tồn tại của một bản ghi biểu thị “token này đã bị thu hồi”, xóa bản ghi quá sớm có thể làm một token còn hạn được chấp nhận trở lại. Chính sách giữ dấu chặn phải bao phủ thời gian token còn có thể được chấp nhận, kể cả độ lệch đồng hồ được hệ thống cho phép.

Phải phân biệt hai ý nghĩa:

```text
Bản ghi cho phép: không tìm thấy thì từ chối
Bản ghi chặn: không tìm thấy có thể không còn chặn
```

Cleanup không được áp cùng một quy tắc xóa cho hai loại dữ liệu này.

## 11. Xóa logic, xóa vật lý và bản sao lưu

`DELETE` khỏi bảng hoạt động không đồng nghĩa mọi byte dữ liệu đã biến mất khỏi mọi phương tiện lưu trữ.

Trong PostgreSQL, phiên bản dòng cũ có thể còn tồn tại do MVCC; VACUUM giúp thu hồi không gian để tái sử dụng. VACUUM thông thường không bảo đảm trả toàn bộ dung lượng về hệ điều hành. [PostgreSQL: Routine Vacuuming](https://www.postgresql.org/docs/16/routine-vacuuming.html)

Với bảng recovery có tỷ lệ tạo/xóa cao, cần theo dõi dead tuples, autovacuum, độ trễ replica và dung lượng. Không coi VACUUM FULL sau mỗi lượt cleanup là thao tác mặc định vì nó có tác động khóa và tài nguyên riêng.

Ngoài cơ sở dữ liệu hoạt động, cần xác định vòng đời của backup, log, dữ liệu xuất và bản sao phân tích. Giảm dữ liệu nhạy cảm được tạo ngay từ đầu thường hiệu quả hơn việc cố xóa hàng loạt bản sao về sau.

Quy trình khôi phục backup phải tính đến dữ liệu recovery và trạng thái thu hồi cũ. Đánh giá mốc thời gian, phiên bản credential/session và các dấu chặn cần phục hồi trước khi mở lại chức năng recovery. Khôi phục dữ liệu không được trở thành cách tái kích hoạt quyền đã bị thu hồi.

## 12. Quan sát cleanup bằng tín hiệu phù hợp

Các tín hiệu vận hành nên phản ánh việc xóa đã commit và tác động lên dịch vụ:

| Tín hiệu | Câu hỏi được trả lời |
| --- | --- |
| Số dòng đã xóa theo lượt | Cleanup có thực sự xử lý được dữ liệu không? |
| Thời điểm lượt thành công gần nhất | Scheduler có ngừng chạy hoặc lỗi kéo dài không? |
| Số bản ghi đủ điều kiện còn tồn tại | Backlog có tăng liên tục không? |
| Độ trễ so với `purge_after` cũ nhất | Có bản ghi bị bỏ lại quá lâu không? |
| Thời gian một lô, timeout và lỗi khóa | Cleanup có tranh tài nguyên quá mức không? |
| Độ trễ endpoint recovery và replica | Dọn dữ liệu có gây tác động lên đường xử lý chính không? |
| Số dòng bị giữ theo từng lý do | Dữ liệu đang được giữ có chủ đích hay do quy trình bị quên? |

Khi đo backlog, tách bản ghi có hold khỏi bản ghi thực sự đủ điều kiện xóa. Một hồ sơ đang được giữ theo chính sách không nên bị báo nhầm là scheduler xử lý chậm.

Không đưa token, URL recovery, digest, OTP, ảnh giấy tờ hoặc email vào log cleanup. Hạn chế label có độ phân biệt quá cao như ID challenge hoặc ID tài khoản trong hệ thống metrics.

Nếu cleanup dừng, cảnh báo mô tả đúng hậu quả: dữ liệu tồn đọng, tăng dung lượng hoặc vượt thời hạn lưu giữ. Hệ thống vẫn phải từ chối token hết hạn trong luồng xác thực. Nếu việc dừng cleanup làm token tiếp tục dùng được, lỗi nằm ở ranh giới cấp quyền.

## 13. Tình huống minh họa

Một challenge có:

```text
issued_at   = 2026-11-24T10:00:00Z
expires_at  = 2026-11-24T10:15:00Z
purge_after = 2026-11-25T10:15:00Z
state       = PENDING
cleanup_hold = false
```

Khoảng lưu thêm một ngày chỉ là lựa chọn của ví dụ.

| Thời điểm/sự kiện | Kết quả mong đợi |
| --- | --- |
| Người dùng gửi bằng chứng hợp lệ lúc 10:10Z | Có thể tiêu thụ nếu mọi điều kiện nghiệp vụ khác đạt |
| Token đã dùng được gửi lại | Bị từ chối dù bản ghi vẫn tồn tại |
| Challenge chưa dùng được gửi lúc đúng 10:15Z | Bị từ chối do hết hạn |
| Cleanup chạy lúc 11:00Z cùng ngày | Giữ bản ghi vì chưa đến `purge_after` |
| Cleanup chạy sau `purge_after` và không còn phụ thuộc | Có thể xóa |
| Sau đó người dùng gửi lại token | Không tìm thấy bản ghi cho phép; từ chối |
| Cleanup ngừng hai ngày | Dữ liệu tồn đọng; thời hạn token vẫn giữ nguyên |

Nếu challenge thuộc quy trình thay MFA hoặc đăng ký passkey mới, việc dọn challenge chỉ kết thúc vòng đời dữ liệu tạm thời đó. Credential đã đăng ký, thông báo an ninh và trạng thái session có vòng đời riêng.

## 14. Những lựa chọn dễ gây sai lệch

| Lựa chọn | Hậu quả | Cách thiết kế phù hợp hơn |
| --- | --- | --- |
| Chỉ kiểm tra token có tồn tại | Token còn dùng được khi job trễ | Kiểm tra hạn và trạng thái trong bước cấp quyền |
| Xóa theo `issued_at` bằng một TTL chung | Không phản ánh hạn hoặc phụ thuộc của từng loại | Dùng điều kiện vòng đời và mốc xóa được xác định |
| Xóa hết token cũ trong một transaction | Giữ tài nguyên lâu, khó kiểm soát tải | Chia lô, commit ngắn và giới hạn ngân sách |
| Thấy lô xóa 0 dòng thì tuyên bố sạch dữ liệu | Bỏ sót dòng đang bị khóa | Quét lại và theo dõi backlog độc lập |
| Xóa dấu chặn trước khi token được bảo vệ hết hạn | Nguy cơ chấp nhận lại token bị thu hồi | Giữ dấu chặn đủ thời gian cần bảo vệ |
| Cascade xóa audit hoặc outbox | Mất bằng chứng hoặc công việc chưa hoàn tất | Tách vòng đời và thể hiện phụ thuộc rõ ràng |
| Gia hạn token để bù job cleanup bị trễ | Tăng cửa sổ chiếm đoạt tài khoản | Giữ nguyên thời hạn; khắc phục scheduler và tải |

Thiết kế cleanup đạt mục đích khi dữ liệu tạm thời được dọn có kiểm soát, còn quyết định khôi phục tài khoản luôn dựa trên bằng chứng còn hiệu lực tại ranh giới nghiệp vụ đã xác định. Bản ghi hết hạn có thể còn trong kho một thời gian; quyền sử dụng của nó phải kết thúc đúng hạn.
# Quota overrun handling: xử lý vượt quota mà vẫn giữ đúng nghiệp vụ

## 1. Vượt quota là tình huống cần một quy trình xử lý

Trong chương **Quota Management**, quota giới hạn mức sử dụng một tài nguyên theo chủ thể, phạm vi và khoảng thời gian. Ví dụ: một tenant được sử dụng tối đa 1.000 đơn vị xử lý trong kỳ, một dự án được lưu trữ một lượng dữ liệu nhất định hoặc một người dùng được tạo một số tác vụ theo chương trình đã cấp.

**Quota overrun handling** là cách hệ thống phản ứng khi mức sử dụng hoặc mức cam kết vượt ngưỡng được phép. Nó không chỉ là trả lỗi cho request tiếp theo. Hệ thống còn phải xác định phần tài nguyên đã tiêu thụ, xử lý tác vụ đang chạy, ngăn phát sinh thêm, đối soát số liệu và phục hồi theo thẩm quyền.

Ví dụ xuyên suốt:

~~~text
Tenant ACME có quota xử lý cho một kỳ:
  Quota cơ bản: 1.000 đơn vị
  Đã sử dụng được xác nhận: 900
  Đang giữ chỗ cho các tác vụ: 80
  Còn có thể nhận thêm theo chế độ hard limit: 20
~~~

Một request cần giữ chỗ 30 đơn vị phải bị chặn trước khi tác vụ bắt đầu. Nhưng nếu một tác vụ đã chạy lại báo mức tiêu thụ thực tế cao hơn lượng giữ chỗ, hệ thống phải ghi nhận sự thật đó và xử lý phần vượt; không thể chỉ trả lỗi rồi coi tài nguyên chưa từng được dùng.

Bài học tập trung vào business invariants, state machine, phân quyền theo đối tượng, transaction, idempotency và các tình huống lạm dụng logic. Quota ở đây là quyền sử dụng tài nguyên nghiệp vụ, không chỉ là giới hạn bộ nhớ hoặc tốc độ của hạ tầng.

## 2. Phân biệt hết quota, vượt quota và vượt mềm có chủ đích

### 2.1. Các đại lượng cần tách rõ

Xét một quota window trong cùng tenant, chủ thể, loại tài nguyên và đơn vị:

- `L`: quota cơ bản được cấp.
- `H`: trần tiếp nhận có hiệu lực theo chính sách.
- `C`: mức sử dụng thực tế đã được xác nhận.
- `R`: tổng lượng còn đang giữ chỗ cho công việc chưa quyết toán.
- `E = C + R`: tổng mức đã dùng và đã cam kết.
- `x`: lượng cần giữ chỗ cho một lệnh mới.

Điều kiện nhận thêm theo trần:

~~~text
x > 0
C >= 0
R >= 0
C + R + x <= H
~~~

Phần có thể cấp tiếp:

~~~text
available = max(0, H - C - R)
~~~

Các phép tính phải dùng kiểu đủ lớn và kiểm tra tràn. Việc hiển thị available bằng 0 khi hết quota không có nghĩa được xóa hoặc làm tròn mất phần sử dụng vượt trần.

### 2.2. Ba tình huống khác nhau

| Tình huống | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Request không còn chỗ | `E = 980`, `H = 1.000`, yêu cầu `x = 30` | Từ chối lệnh mới; chưa có nghĩa số liệu hiện tại đã vượt |
| Đã chạm trần | `E = H` | Không nhận thêm lượng dương |
| Đã vượt trần | `E > H` | Có cam kết hoặc mức dùng ngoài trần; cần xử lý nguyên nhân và trạng thái |

Có thể cần theo dõi riêng:

~~~text
actual_overrun = max(0, C - H)
committed_overrun = max(0, C + R - H)
~~~

Nếu committed overrun dương nhưng actual overrun bằng 0, một phần vấn đề còn nằm ở cam kết đang mở. Không được giả định rằng có thể hủy mọi cam kết ngay, vì công việc liên quan có thể đã chạy.

### 2.3. Soft limit phải có giới hạn cụ thể

Trong chế độ hard limit:

~~~text
H = L
~~~

Trong chế độ cho phép vượt mềm có kiểm soát:

~~~text
H = L + G
~~~

`G` là ngân sách vượt mềm được cấp có thẩm quyền, có phạm vi và thời hạn. Vượt `L` nhưng chưa vượt `H` có thể là hành vi đã được chính sách cho phép; vượt `H` là một tình huống khác.

Không triển khai soft limit bằng câu “nếu hết quota thì cho thêm một ít” ở từng request. Nếu mỗi lần retry đều nhận thêm một khoảng, người dùng có thể biến ngân sách hữu hạn thành vô hạn.

Nếu hệ thống chỉ cảnh báo và không có hard ceiling, phải nói rõ đó là quota tư vấn hoặc đo lường. Không quảng bá bảo đảm “không bao giờ vượt” trong khi chỉ tổng hợp sử dụng sau khi công việc đã chạy.

### 2.4. Quota không phải rate limit

Rate limit thường điều chỉnh tốc độ yêu cầu trong một khoảng ngắn. Quota nghiệp vụ quản lý quyền tiêu thụ tài nguyên và có thể phụ thuộc kỳ, hợp đồng, dự án hoặc người dùng.

Một kẻ gửi ít request nhưng mỗi request rất đắt vẫn có thể vượt quota. Ngược lại, nhiều request nhỏ có thể bị rate limit dù tổng tài nguyên còn đủ.

Hai cơ chế bổ trợ nhau; chặn tần suất không thay thế việc giữ chỗ và quyết toán tài nguyên.

## 3. Business invariants khi bình thường và khi đã vượt

### 3.1. Bảo toàn mức sử dụng và cam kết

Trong luồng giữ chỗ nghiêm ngặt, khi mọi tác vụ tiêu thụ không quá lượng đã được giữ:

~~~text
C >= 0
R >= 0
C + R <= H
~~~

Khi giữ chỗ `q`:

~~~text
Điều kiện: q > 0 và C + R + q <= H
R' = R + q
~~~

Khi một tác vụ giữ `q` được quyết toán với mức dùng thực tế `a`:

~~~text
Điều kiện bình thường: 0 <= a <= q
C' = C + a
R' = R - q
E' = E - q + a
~~~

Nếu `a <= q`, mức đã dùng cộng giữ chỗ không tăng qua trần chỉ vì quyết toán. Phần `q - a` không còn bị giữ nên trở thành dung lượng có thể nhận tiếp.

Khi hủy một tác vụ chắc chắn chưa tiêu thụ:

~~~text
R' = R - q
C' = C
~~~

Không thực hiện công thức hủy này cho tác vụ có thể đã chạy nhưng chưa báo kết quả.

### 3.2. Ghi nhận thực tế ngay cả khi nó là phần vượt

Nếu xác nhận đáng tin cậy cho biết `a > q`, kết quả thực tế là:

~~~text
C' = C + a
R' = R - q
E' = E + (a - q)
~~~

Kết quả có thể vượt `H`. Hệ thống phải giữ bằng chứng mức dùng, chặn thêm theo chính sách và đưa tình huống vào xử lý. Không lưu `min(a, q)` để số dư trông hợp lệ.

Có thể tách kho sự kiện sử dụng gốc khỏi phép chiếu quota. Điều quan trọng là thông tin tiêu thụ đã được nhận bền vững và được đối soát; một lỗi cập nhật không được làm mất sự kiện thực tế.

Nếu mô hình lưu số đếm không đủ miền giá trị, cần đường tiếp nhận bằng chứng và cảnh báo riêng để không mất số liệu. Giới hạn kiểu dữ liệu không phải lý do được bỏ qua phần tiêu thụ.

### 3.3. Không xóa tiêu thụ để “sửa” vượt trần

Các thao tác sau thường che lỗi thay vì giải quyết:

- Đặt `C = H` khi mức dùng thực tế lớn hơn.
- Đặt lại `C = 0` khi nhận cảnh báo.
- Xóa reservation còn đang chạy để làm available tăng.
- Xóa event trùng mà không phân biệt event trùng với lần dùng thật.
- Gộp sử dụng sang tenant hoặc kỳ khác để tránh cảnh báo.

Nếu phép đo thực sự sai, sửa bằng một điều chỉnh có thẩm quyền, lý do và tham chiếu tới bằng chứng gốc. Nếu cấp thêm quota hợp lệ, thay đổi ngân sách được phép theo chính sách; không giả rằng tài nguyên đã dùng chưa từng tồn tại.

### 3.4. Phân biệt điều kiện nhận thêm và khả năng lưu trạng thái vượt

Một cơ sở dữ liệu phục vụ xử lý sự cố cần biểu diễn được `C + R > H` khi:

- Trần bị giảm hợp lệ xuống dưới mức đã cam kết.
- Phép đo đến muộn phát hiện tiêu thụ vượt ước lượng.
- Đối soát phát hiện một đường thực thi trước đó đã bỏ qua kiểm tra.

Vì vậy không nên mặc định đặt constraint `C + R <= H` trên mọi hàng rồi làm cho hệ thống không thể ghi nhận sự thật. Có thể giữ các kiểm tra không âm, còn điều kiện không vượt được bảo vệ tại luồng **tiếp nhận công việc mới**.

Nếu sản phẩm chọn mô hình cứng không lưu trạng thái vượt trong bảng quota, vẫn cần một sổ sử dụng hoặc hàng đợi ngoại lệ bền vững và một cổng chặn mới tương ứng. Không được chỉ từ chối lưu telemetry.

## 4. Nguyên nhân vượt quota và ranh giới tin cậy

### 4.1. Lạm dụng đầu vào và đường thực thi

Client không được tự xác nhận:

~~~json
{
  "tenantId": "tenant-khac",
  "currentUsage": 0,
  "actualCost": 0,
  "quotaLimit": 999999,
  "isTrusted": true,
  "ignoreQuota": true
}
~~~

Tenant và subject lấy từ ngữ cảnh có thẩm quyền. Hạn mức lấy từ chính sách hiện hành. Mức sử dụng thực tế đến từ hệ thống đo lường đã xác thực, không từ khai báo tùy ý của người gọi.

Client có thể chọn tác vụ hoặc tham số đầu vào. Server cần quy đổi chúng thành một lượng giữ chỗ theo công thức hoặc ngân sách đã được kiểm soát.

Nếu không thể biết trần chi phí trước, cần cấp từng phần, kiểm tra ở checkpoint hoặc chấp nhận một mức rủi ro vượt đã được định nghĩa. Chỉ giữ một “chi phí dự đoán” mà không giới hạn thực thi không tạo ra bảo đảm hard limit.

### 4.2. Các đường gây vượt thường gặp

| Nguyên nhân | Cách phát sinh | Kiểm soát cần có |
| --- | --- | --- |
| Đọc rồi ghi không nguyên tử | Hai request cùng thấy còn quota | Transaction, khóa hoặc cập nhật có điều kiện |
| Retry tạo thêm công việc | Client không biết lệnh trước đã thành công | Idempotency và operation identity |
| Quyết toán trùng | Cùng usage event được nhận nhiều lần | Khóa duy nhất và chuyển trạng thái có điều kiện |
| Giá trị âm | Reservation âm làm tăng available | Kiểm tra miền ở API và cơ sở dữ liệu |
| Một endpoint bỏ qua quota | Luồng cũ hoặc tác vụ nội bộ không giữ chỗ | Ranh giới lệnh chung cho mọi đường tạo hiệu ứng |
| Chi phí thực vượt giữ chỗ | Job dùng nhiều hơn ngân sách được giao | Cưỡng chế ở executor hoặc cấp thêm từng phần |
| Telemetry trễ | Dùng xong mới cộng số | Giữ chỗ trước hoặc mô hình vượt có giới hạn |
| Giảm hạn mức | Gói mới thấp hơn mức đang dùng | Workflow giảm trần và xử lý trạng thái vượt |
| Hết kỳ sai cách | Reset hàng đang có job chưa quyết toán | Danh tính kỳ bất biến và quy tắc quy thuộc |
| Timeout rồi giải phóng sớm | Job vẫn chạy nhưng reservation đã bị trả | Trạng thái không chắc chắn và cơ chế ngăn worker cũ |

### 4.3. Phân quyền theo quota và đối tượng

Một actor được quản lý dự án P1 không tự được tăng quota của tenant hoặc giải phóng reservation của dự án P2.

Mỗi thao tác cần kiểm tra:

- Quota thuộc đúng tenant, subject và loại tài nguyên.
- Actor được tạo công việc trên tài nguyên đích.
- Actor có quyền hủy tác vụ đó nếu yêu cầu hủy.
- Nguồn telemetry được phép báo mức sử dụng cho đúng loại công việc.
- Việc tăng trần, bật grace hoặc sửa số đo có đúng thẩm quyền và phê duyệt.

Role service không phải giấy phép bỏ qua quota. Service vẫn phải hoạt động trong tenant và phạm vi nhiệm vụ được giao.

## 5. Cổng tiếp nhận và state machine của reservation

### 5.1. Tách trạng thái số học khỏi cổng điều khiển

Có thể dùng một cổng tiếp nhận:

~~~text
OPEN         : được đánh giá để nhận thêm nếu đủ phần còn lại
BLOCK_NEW    : chặn công việc tiêu thụ mới
RECONCILING  : đang đối soát; vẫn chặn mới
CLOSED       : không nhận mới trong phạm vi/kỳ này
~~~

`OPEN` không có nghĩa mọi request đều thành công; điều kiện `C + R + x <= H` vẫn bắt buộc.

`BLOCK_NEW` không có nghĩa chặn mọi API. Hệ thống thường vẫn phải cho phép xem trạng thái, quyết toán, xác nhận hủy, giải phóng hợp lệ và các thao tác khắc phục theo quyền. Chặn quyết toán sẽ làm số liệu mắc kẹt và gây khó phục hồi.

Một mô hình chuyển trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> OPEN
    OPEN --> BLOCK_NEW: Phát hiện vượt hoặc cần khoanh vùng
    BLOCK_NEW --> RECONCILING: Bắt đầu đối soát
    RECONCILING --> OPEN: Đã khắc phục và kiểm tra đủ điều kiện
    RECONCILING --> BLOCK_NEW: Vẫn chưa đủ điều kiện
    OPEN --> CLOSED: Kết thúc nhận mới
    BLOCK_NEW --> CLOSED: Đóng phạm vi
~~~

Trạng thái hết quota thông thường có thể suy từ số liệu mà không phải tạo một sự cố. Tuy nhiên một cảnh báo vượt thực tế có thể cần chặn mới ngay cả khi số đếm đang được đối soát.

### 5.2. Reservation phải có định danh và vòng đời

~~~mermaid
stateDiagram-v2
    [*] --> HELD: Giữ chỗ thành công
    HELD --> RUNNING: Executor nhận quyền bắt đầu
    HELD --> CANCELLED: Xác nhận chưa chạy và hủy an toàn
    RUNNING --> SETTLED: Ghi mức dùng thực tế
    RUNNING --> UNCERTAIN: Chưa rõ kết quả
    UNCERTAIN --> SETTLED: Xác định mức dùng
    UNCERTAIN --> CANCELLED: Chứng minh không có tiêu thụ
    SETTLED --> [*]
    CANCELLED --> [*]
~~~

Trong mô hình một lần quyết toán của bài, reservation ở `HELD`, `RUNNING` hoặc `UNCERTAIN` vẫn đóng góp lượng giữ chỗ vào `R`. Sau `SETTLED` hoặc `CANCELLED`, lượng đó không còn trong `R`.

Nếu cho phép quyết toán từng phần, cần mô hình riêng cho tổng đã quyết toán và phần còn giữ. Không lặp phép trừ toàn bộ reservation mỗi khi nhận một phần usage.

### 5.3. Timeout không chứng minh tác vụ chưa chạy

Sau timeout khi gọi executor, có thể xảy ra:

~~~text
Executor đã nhận lệnh và chạy.
Response bị mất.
Server tưởng chưa chạy rồi giải phóng reservation.
Client gửi lại một công việc khác dùng phần quota vừa được trả.
~~~

Kết quả là cùng một phần quota bảo chứng cho hai công việc.

Khi chưa rõ kết quả, giữ trạng thái `UNCERTAIN` và thực hiện tra cứu hoặc đối soát. Không giải phóng chỉ vì một khoảng thời gian đã qua.

Muốn hủy một hold hết hạn an toàn, phải bảo đảm executor không còn có thể bắt đầu theo quyền cũ. Có thể cần kiểm tra chuyển trạng thái trước khi chạy, lease có thế hệ và cơ chế fencing được thực thi tại nơi tiêu thụ tài nguyên. Chỉ ghi “lease hết hạn” trong cơ sở dữ liệu không ngăn một worker cũ vẫn gọi hệ thống ngoài.

### 5.4. Không lấy khả năng hủy làm giả định cho mọi tác vụ

Một job đã bắt đầu có thể chỉ dừng ở checkpoint, hoặc không thể hủy ngay. Nếu hủy được, vẫn cần quyết toán phần thực tế đã tiêu thụ trước khi trả phần giữ thừa.

Một thao tác “yêu cầu hủy” không đồng nghĩa “đã hủy và dùng 0”. Hệ thống cần phân biệt hai kết quả này trong API và audit.

## 6. Ngăn phát sinh thêm bằng transaction

### 6.1. Giữ chỗ trước khi cho chạy

Một luồng an toàn cho hard quota:

1. Xác thực actor, tenant và quyền trên tài nguyên.
2. Tính lượng giữ chỗ theo chính sách server.
3. Mở transaction và nhận quyền xử lý idempotency.
4. Khóa quota window và các hạn mức liên quan theo thứ tự ổn định.
5. Kiểm tra kỳ, trạng thái cổng, trần hiện hành và phần còn lại.
6. Tăng `R`, tạo reservation, ghi audit/outbox.
7. Commit rồi mới cho executor nhận công việc.

Nếu outbox được gửi nhiều lần, executor phải nhận diện cùng operation hoặc reservation để không chạy hai công việc cho một lần giữ chỗ.

Không giữ khóa SQL trong lúc đợi executor hoặc dịch vụ ngoài trả kết quả. Transaction cục bộ không thể rollback tài nguyên đã tiêu thụ ở hệ thống khác.

### 6.2. Lược đồ quota window tối thiểu

~~~sql
CREATE TABLE quota_window (
    tenant_id UUID NOT NULL,
    quota_id UUID NOT NULL,
    window_id UUID NOT NULL,
    subject_id UUID NOT NULL,
    meter_code TEXT NOT NULL,
    unit_code TEXT NOT NULL,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    base_limit_units BIGINT NOT NULL CHECK (base_limit_units >= 0),
    hard_limit_units BIGINT NOT NULL CHECK (hard_limit_units >= 0),
    used_units BIGINT NOT NULL DEFAULT 0 CHECK (used_units >= 0),
    reserved_units BIGINT NOT NULL DEFAULT 0 CHECK (reserved_units >= 0),
    admission_gate TEXT NOT NULL CHECK (
        admission_gate IN ('OPEN', 'BLOCK_NEW', 'RECONCILING', 'CLOSED')
    ),
    revision BIGINT NOT NULL CHECK (revision > 0),
    PRIMARY KEY (tenant_id, quota_id, window_id),
    CHECK (period_end > period_start),
    CHECK (hard_limit_units >= base_limit_units)
);
~~~

Lược đồ minh họa cho chính sách `H >= L`. Nếu sản phẩm có một trần cưỡng chế khác thấp hơn quyền cơ bản, cần mô hình riêng thay vì bỏ qua ý nghĩa hai trường này.

Không có constraint tổng `used + reserved <= hard_limit` vì bảng phải biểu diễn được trạng thái vượt đã phát hiện. Các khóa ngoại tới chủ thể, reservation và nguồn chính sách vẫn cần được bổ sung trong triển khai đầy đủ.

Nếu hai quota window khác ID nhưng thực chất đại diện cùng một phạm vi và kỳ, người dùng có thể được cấp gấp đôi. Luồng tạo window cần khóa nghiệp vụ duy nhất phù hợp với cách định danh quota và kỳ của sản phẩm.

### 6.3. Cập nhật có điều kiện

Sau khi khóa và đánh giá kỳ bằng thời gian tin cậy, có thể tăng giữ chỗ:

~~~sql
UPDATE quota_window
SET reserved_units = reserved_units + :units,
    revision = revision + 1
WHERE tenant_id = :tenant_id
  AND quota_id = :quota_id
  AND window_id = :window_id
  AND admission_gate = 'OPEN'
  AND :units > 0
  AND (
      used_units::NUMERIC
      + reserved_units::NUMERIC
      + CAST(:units AS NUMERIC)
  ) <= hard_limit_units::NUMERIC
RETURNING reserved_units, revision;
~~~

Dùng kiểu số đủ lớn cho phép cộng điều kiện để một trạng thái vượt lớn không làm biểu thức kiểm tra tràn. Với giới hạn hàng thuộc `BIGINT`, phép gán giữ chỗ cũng phải nằm trong miền được phép.

Phải có đúng một hàng cập nhật. Nếu không, rollback và trả lỗi phù hợp; không tạo reservation hoặc gửi job sau khi câu cập nhật thất bại.

Việc tạo reservation, bản ghi idempotency, audit và outbox phải cùng transaction. Unique theo operation reference ngăn hai HTTP key khác nhau tạo hai reservation cho cùng một công việc nghiệp vụ.

Nếu có quota tenant, quota dự án và quota người dùng, tất cả điều kiện phải được bảo vệ. Khi cùng cơ sở dữ liệu, có thể khóa các hàng theo thứ tự ổn định và cập nhật trong một transaction; một cấp thất bại thì rollback toàn bộ.

## 7. Quyết toán khi mức dùng vượt lượng giữ

### 7.1. Chấp nhận số đo có thẩm quyền

Một usage event cần liên kết với:

- Tenant và reservation hoặc operation.
- Meter, đơn vị và quota window.
- Định danh nguồn đo, tham chiếu phép đo và phiên bản kết quả.
- Lượng sử dụng thực tế cùng bằng chứng cần đối soát.

Không lấy `actualUnits` từ client thường rồi giảm chi phí theo ý họ. Nếu nguồn ngoài gửi event, xác thực nguồn vẫn chưa đủ: phải kiểm tra event thuộc đúng công việc, tenant và mục đích.

Mô hình tham chiếu giả định một kết quả cuối cùng cho mỗi reservation. Nếu nguồn sửa kết quả về sau, đó là luồng điều chỉnh riêng có lịch sử, không phải ghi đè tùy ý.

### 7.2. Thuật toán quyết toán

Trong một transaction:

1. Khóa quota window rồi reservation theo thứ tự chung.
2. Kiểm tra event hoặc business reference đã được áp dụng chưa.
3. Nếu reservation đã quyết toán, so nội dung rồi trả kết quả cũ hoặc báo xung đột.
4. Xác minh mức dùng thực tế và trạng thái cho phép quyết toán.
5. Tăng `C` theo thực tế, giảm `R` đúng lượng giữ của reservation.
6. Đánh dấu reservation `SETTLED` và ghi ledger.
7. Nếu tổng mới vượt `H`, đóng cổng nhận mới theo chính sách và ghi sự cố/outbox.
8. Commit toàn bộ.

Phác thảo mã giả:

~~~java
SettlementResult settle(TrustedMeasurement measurement) {
    return transactions.required(() -> {
        QuotaWindow quota = quotas.lock(measurement.quotaKey());
        Reservation reservation = reservations.lock(
            measurement.tenant(), measurement.reservationId()
        );

        measurementPolicy.requireMatches(reservation, measurement);

        if (reservation.isSettled()) {
            return settlements.requireSameAndReplay(reservation, measurement);
        }

        settlementPolicy.requireFinalizable(reservation, measurement);

        long actual = measurement.actualUnits();
        long held = reservation.heldUnits();

        long newUsed = Math.addExact(quota.usedUnits(), actual);
        long newReserved = Math.subtractExact(quota.reservedUnits(), held);
        if (newReserved < 0) {
            throw new ReconciliationRequired();
        }

        quotas.recordSettlement(quota, newUsed, newReserved);
        reservations.markSettled(reservation, measurement);
        ledger.appendUsage(measurement, held);

        if (exposure.exceeds(newUsed, newReserved, quota.hardLimitUnits())) {
            quotas.blockNewWork(quota, "ACTUAL_USAGE_OVERRUN");
            outbox.appendQuotaOverrun(quota, reservation);
        }

        return SettlementResult.recorded(reservation.id());
    });
}
~~~

`exposure.exceeds` phải dùng phép tính không tràn. Số đo đã tiếp nhận phải có cơ chế lưu bền vững nếu transaction không thể quyết toán, để đối soát không mất dữ liệu.

Đoạn mã không đại diện cho mọi kiểm tra quyền hoặc lược đồ. Nó nhấn mạnh rằng **ghi nhận mức dùng thật và chặn phần phát sinh tiếp theo** là hai việc cùng cần làm.

### 7.3. Ví dụ mức dùng lớn hơn reservation

~~~text
Trước quyết toán:
  H = 1.000
  C = 900
  R = 80, trong đó reservation Q giữ 60
  E = 980

Q báo mức dùng cuối cùng là 100:
  C' = 900 + 100 = 1.000
  R' = 80 - 60 = 20
  E' = 1.020

actual_overrun = 0
committed_overrun = 20
~~~

Đã dùng chưa vượt trần, nhưng còn 20 cam kết không còn được trần hiện tại bảo chứng. Hệ thống phải chặn lệnh mới và xác định trạng thái cam kết còn lại.

Nếu cam kết đó thực sự chưa chạy và hủy an toàn được, có thể trả giữ chỗ theo workflow. Nếu đã chạy, cần quyết toán thực tế. Không giả rằng việc đặt available bằng 0 đã giải quyết xong.

### 7.4. Giữ hard limit khi chi phí chưa biết trước

Có ba hướng cần cân nhắc theo loại tài nguyên:

- Giữ trước một giới hạn trên có thể cưỡng chế tại executor.
- Chia công việc thành các đoạn; mỗi đoạn phải có ngân sách được cấp trước khi chạy.
- Dùng chính sách cho phép vượt có giới hạn, ghi nhận rõ phần rủi ro và cách xử lý.

Giữ một giá trị ước lượng thấp rồi cho job chạy không giới hạn không phải hard quota. Nếu job có thể làm bất kỳ lượng công việc nào sau khi được mở cửa, độ chính xác của counter không ngăn được vượt tài nguyên.

## 8. Quy trình xử lý khi phát hiện vượt trần

### 8.1. Bước 1 — Khoanh vùng đúng phạm vi

Xác định tenant, subject, meter, đơn vị và quota window đang vượt. Chặn việc tiếp nhận mới trong phạm vi cần bảo vệ, không mặc nhiên đình chỉ mọi tenant hoặc mọi tính năng.

Ví dụ vượt quota xử lý của dự án P1 không nhất thiết ngăn người dùng đọc kết quả đã tạo, xem hóa đơn hoặc xóa dữ liệu của chính mình theo quyền.

Nếu đường tính số dư không còn đáng tin cậy, có thể giữ cổng ở `RECONCILING`. Không tiếp tục cấp tài nguyên mới chỉ vì cache gần nhất từng báo còn quota.

### 8.2. Bước 2 — Giữ bằng chứng và một ảnh chụp nhất quán

Thu thập:

- Phiên bản chính sách và lịch sử thay đổi trần.
- Counter đã dùng, đang giữ và revision.
- Reservation đang mở cùng trạng thái executor.
- Các usage event đã nhận, đã áp dụng và đang chờ xử lý.
- Ledger, idempotency record và operation reference.
- Các lệnh đang chạy hoặc chưa rõ kết quả.

Khi so sánh nhiều bảng, đọc trong một snapshot nhất quán hoặc qua một giao thức đối soát có mốc rõ ràng. Nếu mỗi bảng được đọc ở thời điểm khác nhau, một transaction đang commit có thể tạo báo động giả.

Đừng xóa dữ liệu để giảm kích thước sự cố trước khi xác định phần nào là bằng chứng cần giữ.

### 8.3. Bước 3 — Phân loại nguyên nhân

| Nhóm nguyên nhân | Câu hỏi cần trả lời | Hướng khắc phục chính |
| --- | --- | --- |
| Số liệu trùng | Có cùng hiệu ứng nghiệp vụ được tính hai lần không? | Điều chỉnh có bằng chứng và sửa chống lặp |
| Mức dùng thật cao hơn dự kiến | Executor có thực thi vượt ngân sách không? | Ghi nhận thực tế, chặn mới, sửa cơ chế cấp ngân sách |
| Trần bị giảm | Thay đổi có được phê duyệt và đúng thời điểm không? | Workflow giảm quota hoặc bổ sung ngân sách hợp lệ |
| Cam kết không rõ | Tác vụ đã bắt đầu hoặc tiêu thụ chưa? | Tra executor, giữ trạng thái UNCERTAIN |
| Đường bỏ qua quota | Endpoint hoặc service nào tạo tài nguyên không giữ chỗ? | Khoanh đường ghi và đưa về ranh giới lệnh chung |
| Quy thuộc sai | Event có đúng tenant, meter, đơn vị, kỳ không? | Sửa phép quy thuộc bằng điều chỉnh truy vết được |
| Dữ liệu vật chất hóa sai | Ledger và counter có lệch nhau không? | Khôi phục phép chiếu theo quy trình có kiểm soát |

Không sửa số đếm giống nhau cho mọi nguyên nhân. Một sự kiện trùng và một tác vụ thực sự dùng quá mức đòi hỏi hai cách xử lý khác nhau.

### 8.4. Bước 4 — Giải quyết công việc đang mở

Với từng reservation:

- `HELD` và được chứng minh chưa thể bắt đầu: có thể hủy qua cơ chế an toàn.
- `RUNNING`: yêu cầu dừng nếu chính sách và executor cho phép, rồi quyết toán phần đã dùng.
- `UNCERTAIN`: truy vấn hoặc đối soát, không tự gán mức dùng bằng 0.
- `SETTLED`: không hoàn giữ chỗ lần nữa.
- Có event không khớp: giữ vào luồng đối soát, không gắn đại vào quota của người gửi.

Không thể thu hồi tài nguyên đã tiêu thụ bằng cách chỉ đổi trạng thái database. Nếu tài nguyên còn tồn tại như dung lượng lưu trữ, việc giảm sử dụng cần một workflow trên tài nguyên thật, theo quyền sở hữu và chính sách bảo vệ dữ liệu.

### 8.5. Bước 5 — Chọn biện pháp được ủy quyền

Các phương án có thể gồm:

- Chờ sang một kỳ mới theo chính sách cấp quota.
- Tăng ngân sách hoặc cấp grace có giới hạn và phê duyệt.
- Hủy an toàn phần công việc chưa thực hiện.
- Dừng hoặc thu nhỏ công việc còn lại tại checkpoint.
- Sửa số liệu bằng bút toán điều chỉnh khi có bằng chứng sai.
- Giữ chặn mới cho đến khi mức cam kết phù hợp.

Một sự cố do lỗi hệ thống không phải lý do để trao quyền tăng quota cho client. Người dùng được yêu cầu xem xét hoặc nâng gói không đồng nghĩa được tự gửi một `newLimit` có hiệu lực.

Cũng không được tự động xóa dữ liệu của người dùng để làm mức sử dụng giảm. Với tài nguyên có giá trị hoặc nghĩa vụ lưu giữ, quyết định đó cần đúng chính sách và thẩm quyền.

### 8.6. Bước 6 — Mở lại có điều kiện

Chỉ mở lại sau khi:

1. Nguyên nhân gây cấp sai đã được khoanh hoặc sửa.
2. Các nguồn có thẩm quyền và đối soát cần thiết đã rõ.
3. Counter, ledger và reservation khớp theo mô hình.
4. Chính sách hiện hành cho phép nhận mới.
5. Mọi trạng thái chặn bắt buộc đã được giải quyết.

Cập nhật mở cổng phải có điều kiện theo revision và được kiểm tra lại trong transaction. Một lệnh “resume” được phê duyệt trên ảnh chụp cũ không được bỏ qua mức sử dụng vừa tăng.

Ngay cả khi cổng chuyển về `OPEN`, mỗi request mới vẫn cần kiểm tra dung lượng còn lại. `E = H` là trạng thái có thể nhất quán nhưng vẫn không nhận thêm lượng dương.

Thông báo cho người dùng và hệ thống giám sát nên thể hiện rõ đang bị chặn, đã được bổ sung ngân sách hay đang đối soát. Không báo “đã khôi phục” chỉ vì job xử lý sự cố đã chạy xong.

## 9. Giảm trần, chuyển kỳ và môi trường phân tán

### 9.1. Giảm hạn mức dưới mức đã cam kết

Giả sử:

~~~text
C = 700
R = 200
H cũ = 1.000
H đích = 600
~~~

Không có cách sửa counter hợp lệ để làm 900 trở thành nhỏ hơn 600 nếu tài nguyên và cam kết vẫn tồn tại.

Hai chính sách thường có thể thiết kế:

- Lên lịch áp dụng trần thấp hơn khi điều kiện sử dụng phù hợp.
- Áp dụng trần mới ngay, giữ số liệu thật và chặn mới trong trạng thái vượt.

Nếu chọn cách thứ hai, committed overrun là 300 tại thời điểm thay đổi. Đó có thể là hệ quả chính sách được dự kiến, không nhất thiết là hành vi tấn công, nhưng vẫn cần xử lý công việc và trải nghiệm người dùng.

Không tự nâng trần thành `max(H_đích, C + R)` rồi tuyên bố đã hạ quota. Nếu giữ một giới hạn chuyển tiếp, hãy biểu diễn nó như chính sách chuyển tiếp có thời hạn và căn cứ rõ ràng.

Khi grace hết hạn, việc `H` giảm trở lại cũng cần cùng phân tích này. Không reset grace theo mỗi lần người dùng gửi yêu cầu mới.

### 9.2. Mỗi kỳ có danh tính bất biến

Không nên đặt lại cùng một hàng counter về 0 khi vẫn còn tác vụ kỳ cũ chờ quyết toán.

Mô hình tham chiếu cho tác vụ tính theo lần tiếp nhận:

- Reservation gắn với window tại lúc được cấp.
- Usage cuối cùng quyết toán về đúng window của reservation.
- Window đã đóng nhận mới vẫn cho phép ghi quyết toán và điều chỉnh hợp lệ.
- Kỳ mới có window ID và ngân sách riêng.
- Không dùng ngày nhận telemetry để tự chuyển mức dùng cũ sang kỳ mới.

Nếu tài nguyên được tính theo thời gian sử dụng thực tế, chẳng hạn mỗi khoảng chạy cần ngân sách riêng, phải chia theo quy tắc đo và kỳ tương ứng. Không dùng quy tắc “mọi thứ thuộc kỳ lúc bắt đầu” để kéo một tác vụ vô hạn qua các kỳ.

Mọi endpoint nhận mới phải kiểm tra thời gian kỳ bằng đồng hồ tin cậy. Một client giữ window ID cũ không được tiếp tục tạo reservation sau khi kỳ đã đóng.

### 9.3. Counter cục bộ không tự bảo vệ quota toàn cục

Khóa `synchronized` trong một tiến trình Java không ngăn instance khác cấp tài nguyên. Một bộ đếm ở mỗi node cũng có thể cùng cho phép dùng phần quota chung.

Nếu mỗi node dùng cache “còn 100”, nhiều node có thể cùng cấp 100 mà không biết nhau. Muốn có hard limit toàn cục cần:

- Một điểm cập nhật nguyên tử có thẩm quyền; hoặc
- Phân bổ ngân sách con/lease theo một giao thức bảo toàn tổng ngân sách.

Với ngân sách con, bộ cấp trung tâm phải giữ hoặc trừ toàn bộ phần đã giao trước khi node tiêu thụ. Tổng ngân sách chưa quyết toán không được bị quên chỉ vì node mất kết nối.

Lease phải có identity, giới hạn, thế hệ và quy tắc thu hồi. Không cấp lại cùng phần cho node khác khi node cũ vẫn có khả năng sử dụng mà không bị fencing.

### 9.4. Đo bất đồng bộ cần mô hình rủi ro cụ thể

Nếu công việc được cho chạy rồi telemetry mới đến, hệ thống có thể tiêu thụ thêm trong thời gian chưa nhìn thấy số liệu. Mức vượt phụ thuộc giới hạn tốc độ tiêu thụ, công việc đang chạy và ngân sách đã được cấp nhưng chưa báo.

Không thể suy một cận trên hữu hạn chỉ từ việc “đồng bộ mỗi 10 giây” nếu số tài nguyên có thể chạy trong 10 giây đó không bị giới hạn.

Nếu chấp nhận mô hình này, cần mô tả rõ:

- Những nguồn có thể tiêu thụ.
- Ngân sách hoặc tốc độ tối đa được cưỡng chế tại từng nguồn.
- Phần sử dụng chưa được quan sát.
- Cách khoanh vùng khi mất liên lạc.
- Điều kiện ngừng nhận thêm và khôi phục.

Đối với quota cần ngăn vượt chặt, ưu tiên giữ chỗ hoặc ngân sách được cưỡng chế trước khi tạo hiệu ứng.

## 10. Idempotency, ledger và các sự kiện

### 10.1. Các danh tính giải quyết các vấn đề khác nhau

| Danh tính | Bảo vệ |
| --- | --- |
| HTTP idempotency key | Retry cùng yêu cầu của client |
| Operation reference | Một công việc nghiệp vụ không được tạo lặp bằng key khác |
| Reservation ID | Liên kết ngân sách được giữ với công việc |
| Usage/settlement reference | Một kết quả tiêu thụ không được áp dụng nhiều lần |
| Event ID | Nhận diện một lần phát sự kiện kỹ thuật |
| Adjustment reference | Một điều chỉnh không được ghi lại khi retry |

Chỉ unique theo event ID không đủ nếu hai event ID khác nhau mô tả cùng kết quả cuối cùng của một reservation.

Cùng key nhưng khác nội dung phải bị từ chối. Cùng settlement reference nhưng khác số đo cần đi vào xung đột hoặc quy trình sửa số đo, không âm thầm lấy giá trị đến cuối.

### 10.2. Ghi bền vững cùng hiệu ứng

Một lần giữ chỗ cần liên kết:

~~~text
Operation accepted
Reservation created
Quota reserved increased
Idempotency result stored
Audit/outbox appended
~~~

Tất cả cùng transaction cục bộ. Một lần quyết toán tương tự phải gắn mức dùng, giảm phần giữ, trạng thái reservation và bằng chứng chống lặp.

Nếu consumer đánh dấu event “đã xử lý” trước rồi transaction cập nhật quota thất bại, retry có thể bỏ qua số liệu. Nếu ghi inbox trước để xử lý sau, inbox cần trạng thái và cơ chế phục hồi rõ ràng.

Outbox giúp phát tác vụ hoặc thông báo sau commit. Consumer vẫn phải chịu được phát lại; không suy “exactly once” toàn hệ thống chỉ vì có outbox.

### 10.3. Ledger phải giữ được nguyên nhân thay đổi

Có thể ghi các loại nghiệp vụ:

~~~text
RESERVE
SETTLE
CANCEL_CONFIRMED
LIMIT_CHANGED
GRACE_GRANTED
USAGE_CORRECTED
GATE_BLOCKED
GATE_REOPENED
~~~

Mỗi mục cần tenant, quota/window, operation hoặc reservation, actor/source, lượng thay đổi, revision liên quan và lý do.

Sửa một phép đo sai có thể làm phép chiếu usage giảm, nhưng phải có nguồn có thẩm quyền và tham chiếu tới bản ghi gốc. Một yêu cầu “refund quota” từ người dùng không tự chứng minh phép đo ban đầu sai.

Nếu ưu đãi bổ sung tài nguyên là chính sách bồi hoàn, có thể thể hiện bằng cấp thêm ngân sách riêng. Không biến nó thành thao tác xóa lịch sử tiêu thụ thật.

### 10.4. Đối soát các phương trình

Trong mô hình quyết toán một lần:

~~~text
quota.reserved_units
  = SUM(held_units của reservation đang HELD, RUNNING hoặc UNCERTAIN)

quota.used_units
  = SUM(mức dùng đã quyết toán
        cộng/trừ điều chỉnh được phê duyệt theo mô hình)

Mỗi operation hợp lệ
  → tối đa một reservation theo chính sách

Mỗi reservation SETTLED
  → có đúng kết quả quyết toán cuối cùng hoặc lịch sử sửa hợp lệ
~~~

Tổng có thể cần kiểu lớn hơn cột số lượng từng hàng. Kết quả đối soát phải mang phạm vi tenant, meter, đơn vị và window; cộng lẫn chúng có thể tạo một tổng trông đúng nhưng sai nghiệp vụ.

Cần phân biệt bất biến hỏng với một trạng thái vượt được ghi nhận trung thực. Counter và ledger có thể hoàn toàn khớp trong khi `C + R > H`; vấn đề khi đó là mức cam kết hoặc chính sách, không phải nhất thiết lỗi cộng số.

## 11. Hợp đồng API và hành vi khi bị chặn

### 11.1. Trả kết quả đủ để client hành động

Ví dụ response cho một lệnh mới không đủ quota:

~~~json
{
  "code": "QUOTA_EXHAUSTED",
  "meter": "PROCESSING_UNITS",
  "windowId": "window-123",
  "requestedUnits": 30,
  "availableUnits": 20,
  "admission": "DENIED",
  "nextAction": "REDUCE_WORK_OR_WAIT_FOR_CONFIRMED_CAPACITY"
}
~~~

Không cam kết client chắc chắn thành công khi retry sau một khoảng tùy ý. Phần quota có thể được giải phóng khi job kết thúc, nhưng thời điểm đó chưa chắc biết trước.

Chỉ trả thông tin số dư khi actor được phép đọc quota đó. Đối với đối tượng ngoài tenant, không tiết lộ mức dùng, giới hạn hoặc reservation của người khác.

### 11.2. Phân biệt lỗi nghiệp vụ với trạng thái chưa rõ

| Mã minh họa | Ý nghĩa |
| --- | --- |
| `QUOTA_EXHAUSTED` | Không đủ phần còn lại cho lệnh mới |
| `QUOTA_OVERRUN_BLOCKED` | Đang chặn mới do vượt trần hoặc xử lý sự cố |
| `QUOTA_RECONCILING` | Cần đối soát trước khi tiếp nhận |
| `RESERVATION_RESULT_UNCERTAIN` | Chưa xác định được tác vụ có tiêu thụ hay không |
| `SETTLEMENT_CONFLICT` | Kết quả quyết toán không khớp bằng chứng đã lưu |
| `IDEMPOTENCY_KEY_REUSED` | Key cũ bị dùng cho nội dung khác |
| `QUOTA_WINDOW_CLOSED` | Kỳ không còn nhận công việc mới |
| `QUOTA_STATE_UNAVAILABLE` | Chưa đọc được trạng thái có thẩm quyền |

Có thể dùng `409` cho xung đột nghiệp vụ hoặc `429` cho một chính sách giới hạn theo thời gian nếu đó là hợp đồng API đã chọn. Không mặc định mọi quota đều có một thời điểm retry chắc chắn hoặc phải dùng cùng mã với rate limit.

Một lỗi hệ thống khiến chưa xác định được quota không nên được trình bày là “hết quota” nếu sự thật chưa biết. Có thể trả lỗi tạm thời và giữ an toàn cho việc tiếp nhận mới.

### 11.3. Retry không được làm tình huống nặng hơn

Client cần giữ cùng key và cùng nội dung khi kết quả tiếp nhận chưa rõ. Server phát lại reservation/operation đã có thay vì tạo công việc mới.

Nếu lệnh tiếp nhận trước đó thành công nhưng job đang `UNCERTAIN`, retry không được chuyển nó về `HELD` và gửi chạy lại như một job mới.

Lệnh khắc phục như tăng trần, cấp grace, sửa số đo hoặc mở cổng cũng cần chống lặp. Một nút “Thử lại” trong giao diện quản trị không được cấp thêm ngân sách mỗi lần bấm.

### 11.4. Quan sát theo ảnh hưởng nghiệp vụ

Các chỉ báo hữu ích gồm:

- Mức vượt thực tế và mức vượt đã cam kết.
- Số reservation ở trạng thái không chắc chắn và tuổi của chúng.
- Số lần quyết toán thực tế vượt lượng giữ.
- Tần suất xung đột idempotency hoặc operation reference.
- Độ trễ telemetry, outbox và đối soát.
- Đường thực thi không có reservation tương ứng.
- Lần tăng grace hoặc đổi trần gần thời điểm vượt.
- Số lệnh mới bị từ chối theo tenant/meter.
- Thời gian từ phát hiện vượt tới khoanh vùng và phục hồi.

Không đặt token, bí mật nguồn đo hoặc dữ liệu nhạy cảm không cần thiết vào log. Thông báo và audit phải có correlation ID để tái dựng được chuỗi hành động.

## 12. Kiểm thử các tình huống tấn công logic

Kiểm tra cả response và trạng thái đã commit. Trả lỗi đúng trong khi quota vẫn bị trừ hoặc executor vẫn chạy là một thất bại.

### 12.1. Miền dữ liệu và phân quyền

| Ca kiểm thử | Hành vi | Kết quả cần chứng minh |
| --- | --- | --- |
| Giữ chỗ âm hoặc 0 | Gửi trực tiếp payload | Không làm tăng available hoặc tạo job tiêu thụ |
| Giá trị quá lớn | Dùng số sát giới hạn kiểu, gây tổng vượt miền | Không tràn thành số âm hoặc bỏ kiểm tra |
| Quota tenant khác | Thay quota/window ID | Không đọc hoặc sửa phạm vi ngoài quyền |
| Reservation người khác | Gửi yêu cầu hủy/settle trái quyền | Không giải phóng hoặc gán mức dùng sai đối tượng |
| Giả actual cost | Client gửi mức dùng bằng 0 | Không thay thế số đo có thẩm quyền |
| Giả ignoreQuota | Thêm cờ nội bộ vào payload | Không bỏ qua chính sách |
| Endpoint cũ | Tạo cùng loại tài nguyên qua đường khác | Không tạo hiệu ứng mà thiếu ngân sách hợp lệ |
| Giả phê duyệt grace | Gửi mức tăng và approved flag | Không cấp trần mới từ khai báo client |

### 12.2. Hai request tranh chấp phần còn lại

~~~text
Ban đầu:
  H = 100
  C = 0
  R = 0
  Cổng OPEN

Hai operation khác nhau cùng giữ 80.

Kỳ vọng:
  Đúng một reservation 80 thành công.
  Reservation còn lại bị từ chối.
  R = 80, C = 0.
  Chỉ một ý định thực thi được commit.
~~~

Chạy trên cơ sở dữ liệu có semantics transaction như môi trường triển khai. Dùng barrier/latch để tạo tranh chấp; mock repository hoặc gọi tuần tự không chứng minh được tính nguyên tử.

Nếu có hạn mức tenant và dự án, tạo tình huống cấp dự án đủ nhưng tenant không đủ. Không được giữ quota ở một cấp rồi thất bại ở cấp khác mà không rollback.

### 12.3. Retry và quyết toán trùng

**Cùng key, cùng nội dung:** chỉ một reservation và một công việc. Mọi kết quả tiếp nhận thành công trỏ cùng identity.

**Cùng key, khác nội dung:** báo xung đột, không nhận thêm.

**Khác key, cùng operation:** chỉ một reservation theo danh tính nghiệp vụ.

**Cùng usage event lặp:** `C` chỉ tăng một lần và `R` chỉ giảm một lần.

**Khác event ID, cùng kết quả reservation:** không áp dụng lần hai.

**Cùng settlement reference, khác actual units:** không ghi đè tùy ý; đưa vào luồng xung đột hoặc điều chỉnh.

Không dùng `R = max(0, R - q)` để che việc quyết toán hoặc hủy lặp. Assertion không âm phải đi cùng bằng chứng rằng phép chuyển chỉ xảy ra một lần.

### 12.4. Vượt lượng giữ và thay đổi trần

**Ca A — Mức dùng thật vượt giữ chỗ**

Dùng ví dụ `H = 1.000, C = 900, R = 80`; quyết toán reservation 60 với actual 100.

Kỳ vọng:

- `C = 1.000, R = 20`.
- Mức cam kết vượt là 20.
- Ledger giữ đúng actual 100.
- Cổng chặn lệnh mới theo chính sách.
- Có sự kiện hoặc hồ sơ xử lý vượt tương ứng.

**Ca B — Giảm trần dưới exposure**

Giảm `H` từ 1.000 xuống 600 khi `C + R = 900` qua một quyết định hợp lệ. Số liệu không bị cắt xuống 600; trạng thái tiếp nhận và xử lý đúng chính sách.

**Ca C — Grace được phát lại**

Gửi cùng quyền cấp grace nhiều lần bằng key hoặc event khác nhau. Trần chỉ tăng theo đúng số lần được phê duyệt; không cộng lại cùng quyền lợi.

**Ca D — Hết grace khi còn job**

Cho grace kết thúc trong lúc công việc còn chạy. Không xóa tiêu thụ hoặc reservation; áp dụng workflow chuyển trần và chặn mới đã thiết kế.

### 12.5. Timeout và hủy tranh chấp

~~~text
Server gửi lệnh chạy.
Executor bắt đầu nhưng response bị mất.
Luồng xử lý timeout chạy.
Client gửi lại hoặc yêu cầu hủy.
~~~

Kỳ vọng:

- Reservation được giữ hoặc chuyển `UNCERTAIN`.
- Không tự trả toàn bộ quota chỉ vì timeout.
- Không tạo công việc thứ hai cho cùng operation.
- Nếu executor đã tiêu thụ, có đường quyết toán thực tế.
- Chỉ giải phóng sau khi xác định trạng thái an toàn.

Cho lệnh hủy và lệnh bắt đầu chạy tranh chấp cùng reservation. Nếu hủy thắng, executor cũ không được tiếp tục theo quyền đã mất. Nếu thực thi thắng, lệnh hủy không được khẳng định mức dùng bằng 0 khi chưa có bằng chứng.

### 12.6. Sự kiện muộn và chuyển kỳ

- Usage kỳ cũ đến sau khi kỳ mới mở: ghi đúng window, không trừ nhầm ngân sách mới.
- Window đã `CLOSED`: vẫn quyết toán hợp lệ được cho công việc cũ.
- Client gửi window ID cũ để nhận việc mới: bị chặn theo thời gian và trạng thái.
- Event không khớp reservation: không bị bỏ mất hoặc gắn vào quota tùy ý.
- Tác vụ chạy qua ranh giới kỳ: quy thuộc theo chính sách đo lường đã chọn.
- Worker mở lại cổng bằng revision cũ: không bỏ qua mức dùng hoặc chính sách mới.

### 12.7. Lỗi giữa các bước

Chèn lỗi tại các vị trí:

1. Sau tăng giữ chỗ, trước insert reservation.
2. Sau insert reservation, trước ghi outbox.
3. Sau commit tiếp nhận, trước response.
4. Sau executor đã nhận lệnh, trước lưu kết quả cục bộ.
5. Sau tăng used, trước giảm reserved hoặc kết thúc reservation.
6. Sau ghi sự kiện vượt, trước commit.
7. Sau cấp grace, trước hoàn tất kết quả idempotency.
8. Sau outbox được phát nhưng trước đánh dấu đã phát.

Với lỗi trước commit, không có trạng thái một phần. Với lỗi sau commit hoặc kết quả ngoài hệ thống chưa rõ, retry phải tìm lại identity cũ hoặc vào đối soát. Consumer nhận sự kiện trùng không tạo thêm hiệu ứng.

Kiểm tra trạng thái thực của executor hoặc môi trường tích hợp khi cần; chỉ kiểm tra số hàng database không chứng minh không có công việc ngoài hệ thống bị chạy trùng.

### 12.8. Kiểm thử chuỗi hành động và bất biến

Có thể sinh chuỗi:

~~~text
Reserve → retry → start → timeout → reconcile → settle
→ reduce limit → grant grace → duplicate event
→ close window → late usage → reopen attempt
~~~

Sau từng bước đã commit, kiểm tra:

- `C` và `R` không âm, đúng ledger.
- Tổng reservation mở khớp `R`.
- Không tiếp nhận vượt trần khi áp dụng hard policy.
- Mức dùng thật không bị xóa để che overrun.
- Một operation không tạo nhiều hiệu ứng.
- Kỳ, tenant, meter và đơn vị không bị trộn.
- Mọi mở cổng hoặc tăng trần có căn cứ hiện hành.
- Lệnh thất bại không để lại side effect dở dang.

Trong mô hình nghiêm ngặt, nếu bắt đầu từ `C + R <= H`, không giảm trần và mọi actual không vượt lượng giữ, các thao tác reserve/settle/cancel hợp lệ phải giữ được bất biến đó. Đây là một thuộc tính hữu ích cho kiểm thử dựa trên mô hình.

## 13. Các lỗi thiết kế cần nhận ra khi review

| Thiết kế có vấn đề | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Kiểm tra ở UI rồi cho API chạy | Client có thể bỏ qua | Thực thi điều kiện ở ranh giới lệnh server |
| Đọc remaining rồi ghi số mới | Race hoặc mất cập nhật | Transaction và cập nhật nguyên tử |
| Chỉ cộng usage sau khi job xong | Không thấy tài nguyên đang cam kết | Reservation hoặc ngân sách được cưỡng chế |
| Timeout là tự động hoàn quota | Công việc cũ và mới dùng chung ngân sách | UNCERTAIN, tra cứu và fencing phù hợp |
| Actual vượt thì từ chối lưu | Mất sự thật tiêu thụ | Tiếp nhận bền vững, quyết toán và xử lý vượt |
| Cắt used bằng limit | Che mức vượt | Giữ actual, điều chỉnh có bằng chứng |
| Quyết toán bị chặn vì quota đã vượt | Không thể kết thúc hoặc đối soát | Tách nhận mới và ghi nhận công việc cũ |
| Mỗi retry cho thêm grace | Tăng trần vô hạn | Định danh quyền lợi và ngân sách hữu hạn |
| Reset cùng counter đầu kỳ | Event cũ làm sai số dư mới | Window identity bất biến |
| Cache hoặc lock từng process bảo vệ quota chung | Nhiều instance cấp trùng | Điểm nguyên tử toàn cục hoặc ngân sách con bảo toàn |
| Mở cổng chỉ theo cờ “sự cố đã xong” | Bỏ qua trạng thái hiện tại | Kiểm tra chính sách, số liệu và revision dưới transaction |
| Xóa dữ liệu người dùng để giảm usage | Mất tài nguyên ngoài quyết định hợp lệ | Workflow tài nguyên theo quyền và chính sách |

## 14. Tiêu chí hoàn thành thiết kế

Một cơ chế xử lý vượt quota cần trả lời rõ:

- Quota đo tài nguyên nào, cho ai, theo đơn vị và kỳ nào?
- Quota cơ bản và trần cưỡng chế khác nhau thế nào?
- Tài nguyên đang chạy được bảo chứng bằng reservation hoặc ngân sách nào?
- Khi actual vượt lượng giữ, bằng chứng được ghi và cổng tiếp nhận được đổi ra sao?
- Timeout, hủy và kết quả chưa rõ có giải phóng quota an toàn không?
- Retry ở từng bước được chống lặp bằng identity nào?
- Giảm trần và hết grace có xử lý các cam kết đang tồn tại không?
- Sự kiện đến muộn được quy về window nào?
- Ai được tăng quota, sửa số đo hoặc mở lại cổng?
- Có thể đối soát ledger, counter và trạng thái executor mà không xóa mất sự thật không?

Xử lý overrun an toàn cần **ngăn cam kết mới sai chính sách, giữ đúng mức tiêu thụ thực tế và phục hồi theo thẩm quyền**. Transaction và idempotency bảo vệ các lần chuyển trạng thái; reservation làm rõ phần đã cam kết; đối soát giải quyết kết quả chưa rõ và phần vượt mà không biến việc sửa số dư thành một đường lạm dụng mới.

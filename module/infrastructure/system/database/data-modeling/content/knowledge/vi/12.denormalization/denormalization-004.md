# Bảng tổng hợp, bộ đếm và kết quả tính sẵn

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **bảng tổng hợp (aggregate table)**, **bộ đếm lưu sẵn (stored counter)** và **kết quả tính sẵn (precomputed result)** theo mục đích, đơn vị dữ liệu và cách cập nhật.
- Thiết kế khóa, hạt dữ liệu (*grain*), công thức, đơn vị đo, mốc thời gian và ràng buộc cho một bảng tổng hợp có thể kiểm chứng.
- Chọn giữa tính khi đọc, materialized view, cập nhật đồng bộ trong giao dịch và cập nhật bất đồng bộ từ sự kiện.
- Tránh các lỗi đếm trùng, mất cập nhật, ghi nhận sai ngày, cộng sai đơn vị tiền, xử lý sự kiện lặp và sửa số liệu lịch sử.
- Đo lợi ích đọc cùng chi phí ghi, khóa, lưu trữ, độ trễ đồng bộ, đối soát và khả năng tái dựng trước khi phi chuẩn hóa.

Bài nằm trong chương **Phi chuẩn hóa** của **DATABASE_DATA_MODELING**. Đây là phần thực hành chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, ràng buộc, khóa, chỉ mục và lược đồ vật lý; đồng thời đối chiếu cách dùng cấu trúc quan hệ, document, đồ thị và phân tích sao cho dữ liệu đúng, có thể thay đổi và có thể kiểm chứng.

## 1. Ba cách lưu trước kết quả: giống mục tiêu nhưng khác bản chất

Một hệ thống có bảng **orders** và **order_items**. Ứng dụng có thể cần hiển thị tổng một đơn, số đơn của khách hoặc doanh số mỗi ngày. Các giá trị này có thể **tính từ dữ liệu chi tiết** nhưng đôi khi được lưu thêm để rút ngắn đường đọc.

| Dạng | Ví dụ | Hạt dữ liệu | Cách đọc được cải thiện |
| --- | --- | --- | --- |
| **Kết quả tính sẵn** | **orders.items_subtotal** | Một giá trị trên mỗi đơn | Xem danh sách đơn không cần SUM nhiều dòng hàng |
| **Bộ đếm** | **user_stats.follower_count** | Một giá trị trên mỗi người dùng | Hiển thị số người theo dõi mà không COUNT các quan hệ |
| **Bảng tổng hợp** | **daily_capture_summary** | Một dòng cho mỗi ngày × loại tiền | Dashboard không phải tổng hợp từng giao dịch |
| **Materialized view** | Tổng lượt thanh toán theo ngày được refresh | Một dòng cho mỗi nhóm trong câu SELECT | Truy vấn kết quả đã tính ở thời điểm làm mới |

Các dạng này đều có thể là **phi chuẩn hóa có chủ đích** nếu có yêu cầu đọc được đo, ý nghĩa rõ ràng và cơ chế bảo đảm tính đúng đắn. Chúng trở thành dư thừa ngoài kiểm soát nếu nhiều bản sao được tự cập nhật mà không biết nơi nào là nguồn chuẩn.

**Không phải mọi dữ liệu trông có vẻ “tổng hợp” đều là bản sao.** Chẳng hạn giá bán đã chốt trên dòng hóa đơn là sự thật lịch sử có ngữ nghĩa riêng, khác với giá sản phẩm hiện hành. Trước khi quyết định lưu hoặc tính lại, cần xác định dữ liệu là sự thật nguồn, bản chụp lịch sử hay kết quả dẫn xuất.

## 2. Bắt đầu bằng câu hỏi nghiệp vụ và hạt dữ liệu

Giả sử dashboard cần trả lời: “Mỗi ngày có bao nhiêu **lần ghi nhận thanh toán thành công**, tổng số tiền ghi nhận là bao nhiêu, theo từng loại tiền?”.

Cần quy định chính xác:

- **Sự kiện được đếm:** một *capture* thành công, không mặc nhiên là một đơn hàng. Một đơn có thể có nhiều lần capture nếu nghiệp vụ cho phép.
- **Số tiền:** tổng **amount** của các capture; **không phải** số tiền ròng sau hoàn tiền.
- **Thời gian:** ngày theo múi giờ **Asia/Ho_Chi_Minh** dựa trên thời điểm ghi nhận capture. Một capture đến hệ thống muộn vẫn thuộc ngày xảy ra sự kiện.
- **Loại tiền:** tổng tiền VND và USD phải nằm ở **hai nhóm khác nhau**; không cộng trực tiếp nếu chưa quy đổi với tỷ giá và quy tắc rõ.
- **Trạng thái:** một sự kiện capture đã được xác nhận là bất biến. Việc hoàn tiền sẽ tạo sự kiện refund riêng, không âm thầm sửa thành capture khác.
- **Tính duy nhất:** mỗi event được nhận diện bằng **event_id** ổn định; sự kiện trùng phải được bỏ qua hoặc xác nhận giống dữ liệu đã lưu.

Với giả định này, **grain** của bảng tổng hợp là **(capture_day, currency)**. Mỗi cặp ngày và tiền tệ có tối đa một dòng, nên cặp ấy phải được ràng buộc bằng khóa chính hoặc unique constraint.

~~~text
payment_events (nguồn sự kiện chi tiết)
  event_id
  payment_id
  captured_at
  currency
  amount
          |
          | COUNT và SUM theo (ngày địa phương, loại tiền)
          v
daily_capture_summary (bảng dẫn xuất)
  capture_day
  currency
  capture_count
  captured_total
~~~

Nếu hệ thống phục vụ nhiều tổ chức, **tenant_id** có thể phải trở thành một phần của grain và mọi khóa liên quan: **(tenant_id, capture_day, currency)**. Nếu dashboard cần phân chia theo kênh, địa điểm hoặc sản phẩm, không thể tự giả định rằng bảng tổng hợp chỉ theo ngày đã đủ chi tiết để dựng mọi phân tích. **Chọn grain quá thô sẽ làm mất khả năng truy vấn chiều không được lưu.**

### 2.1. Grain phải khớp với câu hỏi được phép trả lời

| Báo cáo | Grain phù hợp | Điều không thể suy ra an toàn |
| --- | --- | --- |
| Số capture theo ngày, tiền tệ | Ngày × tiền tệ | Số **khách hàng duy nhất** nếu không lưu thêm cách đếm khác |
| Doanh số theo cửa hàng/ngày | Cửa hàng × ngày × tiền tệ | Doanh số theo sản phẩm nếu đã gộp mọi sản phẩm |
| Số lượt xem bài theo giờ | Bài viết × giờ | Thời điểm chính xác của từng lượt xem |
| Giá trị giỏ hàng hiện hành | Giỏ hàng | Lịch sử biến động nếu chỉ giữ giá trị cuối |
| Số lượng đơn **đang ở trạng thái PAID** | Khách hàng hoặc ngày × trạng thái hiện hành | Số lần một đơn từng chuyển sang PAID |

**COUNT(*) không giống COUNT(DISTINCT user_id).** Nếu phải đếm người dùng duy nhất qua các ngày, việc cộng các con số distinct của từng ngày có thể đếm cùng người nhiều lần. Một thiết kế đúng phải lưu dữ liệu đủ để hợp nhất hoặc nêu rõ kết quả là xấp xỉ.

## 3. Đọc trực tiếp từ bảng nguồn trước khi lưu tổng

Ví dụ lược đồ PostgreSQL cho các capture:

~~~sql
CREATE TABLE payment_events (
    event_id TEXT PRIMARY KEY,
    payment_id BIGINT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    currency TEXT NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    amount NUMERIC(18, 2) NOT NULL CHECK (amount > 0)
);

CREATE INDEX idx_payment_events_captured_at
    ON payment_events (captured_at);
~~~

**payment_events** là nguồn chuẩn trong ví dụ. Cột **amount** được giả định đã chuẩn hóa đúng đơn vị nhỏ của loại tiền trước khi lưu; thực tế có loại tiền có số chữ số thập phân khác nhau, do đó quy ước **NUMERIC(18, 2)** chỉ để minh họa. Với hệ thống thanh toán thật, cần một quy tắc biểu diễn số tiền và làm tròn phù hợp từng loại tiền.

Truy vấn tổng hợp trực tiếp:

~~~sql
SELECT
    (captured_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS capture_day,
    currency,
    COUNT(*)::BIGINT AS capture_count,
    SUM(amount) AS captured_total
FROM payment_events
WHERE captured_at >= $1
  AND captured_at < $2
GROUP BY
    (captured_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
    currency
ORDER BY capture_day, currency;
~~~

Trong đó **$1** và **$2** là các mốc thời gian có múi giờ được ứng dụng truyền vào, thường để giới hạn khoảng dữ liệu. Dùng điều kiện khoảng thời gian trên **captured_at** giúp bộ tối ưu có cơ hội sử dụng chỉ mục theo cột gốc. Nếu đầu vào là ngày địa phương, cần đổi ranh giới đầu và cuối ngày sang thời điểm phù hợp trước khi truy vấn; không nên mặc định mọi ngày ở mọi múi giờ luôn có 24 giờ.

Nếu bảng nguồn chưa lớn hoặc dashboard hiếm khi chạy, truy vấn trên có thể **đủ nhanh và đơn giản nhất**. Đừng tạo bảng tổng hợp chỉ vì cú pháp SUM/COUNT xuất hiện. Hãy đo tần suất, p95/p99, CPU/I/O, thời gian quét và ảnh hưởng tới workload ghi.

## 4. Phương án A: materialized view làm mới theo lịch

Nếu nhiều dashboard đọc cùng một kết quả tổng hợp và có thể chấp nhận dữ liệu trễ, PostgreSQL **materialized view** lưu kết quả của câu SELECT và làm mới khi được yêu cầu.

~~~sql
CREATE MATERIALIZED VIEW daily_capture_mv AS
SELECT
    (captured_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS capture_day,
    currency,
    COUNT(*)::BIGINT AS capture_count,
    SUM(amount) AS captured_total
FROM payment_events
GROUP BY
    (captured_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
    currency
WITH NO DATA;

-- Lần làm mới đầu tiên để view có dữ liệu:
REFRESH MATERIALIZED VIEW daily_capture_mv;

-- Chỉ mục duy nhất trên grain, không phải partial/expression index:
CREATE UNIQUE INDEX ux_daily_capture_mv_grain
    ON daily_capture_mv (capture_day, currency);

-- Các lần làm mới sau có thể dùng chế độ concurrent:
REFRESH MATERIALIZED VIEW CONCURRENTLY daily_capture_mv;
~~~

Cần hiểu rõ:

1. PostgreSQL **không tự cập nhật** materialized view khi chèn một capture mới. Cần job gọi **REFRESH** hoặc quy trình tương ứng.
2. **CONCURRENTLY** có những điều kiện riêng, trong đó view phải đã được nạp và có unique index phù hợp. Nó giúp giảm chặn đọc so với refresh thường, nhưng vẫn tiêu tốn tài nguyên và không biến refresh thành miễn phí.
3. Một lần **REFRESH** xây kết quả dựa trên snapshot của bảng nguồn tại thời điểm thực thi. Khi xong, dữ liệu vẫn có thể đã cũ so với các giao dịch vừa commit.
4. Nếu bảng nguồn rất lớn, quét và tính lại toàn bộ dữ liệu mỗi vài phút có thể vượt giới hạn thời gian, I/O hoặc tài nguyên. Khi đó cần đánh giá bảng tổng hợp cập nhật tăng dần.

**Độ tươi** phải đo từ thời điểm sự kiện được ghi ở nguồn đến khi giá trị mới xuất hiện trên đường đọc. Ví dụ, “refresh mỗi 5 phút” không bảo đảm độ trễ tối đa 5 phút nếu mỗi lượt refresh kéo dài, bị xếp hàng hoặc thất bại.

## 5. Phương án B: bảng tổng hợp cập nhật tăng dần trong cùng DB

Để tránh quét lại mọi capture, bảng tổng hợp có thể được tăng bằng phần đóng góp của **mỗi sự kiện mới thực sự được chấp nhận**.

~~~sql
CREATE TABLE daily_capture_summary (
    capture_day DATE NOT NULL,
    currency TEXT NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    capture_count BIGINT NOT NULL DEFAULT 0
        CHECK (capture_count >= 0),
    captured_total NUMERIC(24, 2) NOT NULL DEFAULT 0
        CHECK (captured_total >= 0),
    PRIMARY KEY (capture_day, currency)
);
~~~

Khóa chính bảo đảm một dòng trên mỗi grain, đồng thời hỗ trợ **INSERT ... ON CONFLICT**. Dùng kiểu **NUMERIC** thích hợp cho số tiền và cân nhắc khả năng tràn giá trị khi hệ thống phát triển.

### 5.1. Chỉ cộng khi sự kiện nguồn được ghi thành công

Ví dụ nhận một capture mới:

~~~sql
WITH accepted AS (
    INSERT INTO payment_events (
        event_id, payment_id, captured_at, currency, amount
    )
    VALUES (
        'capture-2026-0001',
        9001,
        TIMESTAMPTZ '2026-11-22 08:00:00+07',
        'VND',
        150000.00
    )
    ON CONFLICT (event_id) DO NOTHING
    RETURNING captured_at, currency, amount
)
INSERT INTO daily_capture_summary (
    capture_day, currency, capture_count, captured_total
)
SELECT
    (captured_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
    currency,
    COUNT(*)::BIGINT,
    SUM(amount)
FROM accepted
GROUP BY 1, 2
ON CONFLICT (capture_day, currency)
DO UPDATE
SET capture_count =
        daily_capture_summary.capture_count
        + EXCLUDED.capture_count,
    captured_total =
        daily_capture_summary.captured_total
        + EXCLUDED.captured_total;
~~~

Đây là **một câu lệnh PostgreSQL**, nên việc thêm sự kiện và cập nhật tổng nằm trong cùng giao dịch của câu lệnh. Nếu thao tác thất bại, cả hai phần đều được hoàn tác.

- Nếu **event_id** chưa tồn tại, CTE **accepted** trả về một hàng: tổng tăng **1 capture** và **150.000 VND**.
- Nếu cùng **event_id** được gửi lại, **ON CONFLICT DO NOTHING** không trả hàng: câu lệnh cuối không cộng lại. Điều này giúp bảo đảm hiệu ứng một lần **theo event_id**.
- Nếu hai giao dịch cùng tăng nhóm **(ngày, VND)**, nhánh **DO UPDATE** cộng vào giá trị hiện tại dưới cơ chế khóa hàng của PostgreSQL, tránh lỗi cả hai cùng đọc một số cũ rồi ghi đè.

Điều kiện quan trọng: mọi thao tác tạo sự kiện nguồn phải đi qua giao thức này hoặc một cơ chế tương đương. Nếu có tác nhân **INSERT** trực tiếp vào **payment_events** mà không cập nhật tổng, bất biến sẽ hỏng.

**Idempotency không chỉ là bỏ qua event_id trùng.** Nếu hai yêu cầu sử dụng cùng ID nhưng khác số tiền, thời điểm hoặc loại tiền, hệ thống phải phát hiện lỗi dữ liệu thay vì xem chúng như hai bản sao tương đương. Ngoài ra, nếu một thanh toán bị phát thành **hai event_id khác nhau**, ràng buộc event_id không phát hiện được nghiệp vụ đếm trùng; cần khóa duy nhất theo định danh giao dịch ở nguồn nếu nghiệp vụ đòi hỏi.

### 5.2. Bất biến cần được phát biểu công khai

Với mỗi **(capture_day, currency)**:

> **daily_capture_summary.capture_count** = số hàng capture hợp lệ trong **payment_events** thuộc ngày và tiền tệ đó.

> **daily_capture_summary.captured_total** = tổng **payment_events.amount** của chính các hàng đó.

Hai bất biến áp dụng cho nguồn **bất biến** được định nghĩa ở phần 2. Nếu hệ thống cho phép sửa hoặc xóa capture đã ghi, phải thiết kế cách bù chính xác. Không thể chỉ cộng mãi và vẫn tuyên bố bảng phản ánh trạng thái hiện tại.

## 6. Bộ đếm: nhỏ về dữ liệu, dễ sai ở đường ghi

Bộ đếm thường là một trường duy nhất: **follower_count**, **unread_count**, **items_in_cart**, **open_ticket_count**. Đọc rất nhanh, nhưng cần xác định **đếm những gì**:

- **follower_count:** số quan hệ theo dõi còn tồn tại, hay tổng số lần đã bấm theo dõi?
- **unread_count:** thông báo chưa đọc tại thời điểm hiện tại, hay thông báo chưa mở một lần nào?
- **open_ticket_count:** có gồm ticket tạm hoãn hoặc ticket được mở lại không?
- **view_count:** đếm mọi request, mỗi phiên hay mỗi người dùng duy nhất?

Một bộ đếm không rõ ngữ nghĩa có thể tăng và giảm đúng về mặt SQL nhưng vẫn sai về mặt nghiệp vụ.

### 6.1. Ví dụ bộ đếm người theo dõi chính xác

Trong một database PostgreSQL, giả sử mỗi cặp **(follower_id, followee_id)** chỉ có tối đa một quan hệ theo dõi:

~~~sql
CREATE TABLE user_stats (
    user_id BIGINT PRIMARY KEY,
    follower_count BIGINT NOT NULL DEFAULT 0
        CHECK (follower_count >= 0)
);

CREATE TABLE follows (
    follower_id BIGINT NOT NULL,
    followee_id BIGINT NOT NULL REFERENCES user_stats(user_id),
    PRIMARY KEY (follower_id, followee_id),
    CHECK (follower_id <> followee_id)
);
~~~

**user_stats** được tạo khi tài khoản tương ứng được tạo. Nếu cần bảo đảm cả **follower_id** hợp lệ, cần thêm khóa ngoại tới bảng tài khoản thực; đoạn lược đồ trên chỉ tối thiểu cho ví dụ cập nhật bộ đếm.

Khi theo dõi:

~~~sql
WITH new_follow AS (
    INSERT INTO follows (follower_id, followee_id)
    VALUES (101, 205)
    ON CONFLICT (follower_id, followee_id) DO NOTHING
    RETURNING followee_id
)
UPDATE user_stats AS us
SET follower_count = us.follower_count + 1
FROM new_follow
WHERE us.user_id = new_follow.followee_id;
~~~

Khóa duy nhất ngăn tạo trùng quan hệ; chỉ **INSERT** thực sự được chấp nhận mới làm tăng bộ đếm. **UPDATE ... SET follower_count = follower_count + 1** tránh mô hình nguy hiểm là hai request cùng đọc số **N** rồi cùng ghi **N+1**. PostgreSQL xử lý cập nhật hàng có tranh chấp qua khóa hàng và kiểm soát giao dịch.

Khi bỏ theo dõi phải thực hiện **DELETE ... RETURNING** và chỉ giảm khi quan hệ thực sự bị xóa, trong cùng giao dịch. Cần kiểm thử các tình huống follow/unfollow đồng thời, thay đổi quan hệ, tài khoản bị xóa và retry. Nếu dùng event bất đồng bộ, còn phải tính đến thứ tự sự kiện và độ trễ của bộ đếm.

### 6.2. Bộ đếm có thể tạo “điểm nóng”

Một tài khoản có lượng theo dõi rất lớn có thể nhận hàng nghìn sự kiện mỗi giây. Nếu mọi sự kiện đều **UPDATE user_stats** trên cùng một hàng, hàng đó trở thành điểm tranh chấp khóa. Các lựa chọn gồm:

- Chấp nhận chi phí nếu tần suất thực tế nhỏ và p95 ghi vẫn đạt yêu cầu.
- Gom các thay đổi thành lô khi nghiệp vụ cho phép bộ đếm trễ.
- Chia bộ đếm thành nhiều nhóm (*sharded counter*) rồi cộng các shard khi đọc hoặc qua một bước tổng hợp.
- Dùng nền tảng xử lý luồng/read model cho bộ đếm phục vụ hiển thị, còn nguồn quan hệ là nơi quyết định đúng/sai.

**Sharded counter** giảm tranh chấp trên một hàng nhưng tăng số hàng cần đọc, độ phức tạp đối soát và xử lý sự kiện lặp. Nó không tự tạo tính đúng đắn; phải có hợp đồng nhất quán và cơ chế tái dựng.

## 7. Kết quả tính sẵn: một hàng, nhiều hàng và generated column

Không phải mọi kết quả tính sẵn đều cần bảng tổng hợp riêng.

Giả sử mỗi dòng đơn có **quantity** và **unit_price_at_purchase**. Thành tiền dòng là phép tính **trong cùng một hàng**:

~~~sql
CREATE TABLE example_order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_purchase NUMERIC(14, 2) NOT NULL
        CHECK (unit_price_at_purchase >= 0),
    line_total NUMERIC(18, 2)
        GENERATED ALWAYS AS
        (quantity * unit_price_at_purchase) STORED
);
~~~

Một cột generated dạng **STORED** được PostgreSQL tính từ các cột cùng hàng khi ghi; ứng dụng không tự gán giá trị ấy. Biểu thức phải tuân thủ giới hạn của generated column (chẳng hạn chỉ dùng các phép tính cho phép và hàm phù hợp). Nhờ đó, **line_total** không bị quên cập nhật khi **quantity** đổi.

Tổng tiền **của cả đơn** lại phụ thuộc **nhiều dòng**, nên không thể giải quyết bằng generated column tính tổng xuyên các hàng theo cách tương tự. Các phương án gồm:

- Tính **SUM(line_total)** khi đọc nếu số dòng nhỏ hoặc yêu cầu đọc không quá lớn.
- Lưu **orders.items_subtotal** và cập nhật thêm/sửa/xóa dòng trong giao dịch.
- Dựng read model/bảng tổng hợp khi dữ liệu ở kho khác hoặc cho phép trễ.
- Dùng materialized view cho truy vấn tổng hợp theo lô với lịch refresh rõ ràng.

Nếu tổng tiền còn bao gồm giảm giá, thuế, vận chuyển, hoàn tiền hay làm tròn, phải định nghĩa **công thức và thứ tự tính toán** trước khi lưu kết quả. Không lấy một cột **total** chưa rõ ý nghĩa làm nguồn cho tất cả quyết định thanh toán.

### 7.1. Các phép tổng hợp không giống nhau khi cập nhật

| Phép tổng hợp | Khi có bản ghi mới | Khi sửa/xóa dữ liệu cũ |
| --- | --- | --- |
| **COUNT** | Có thể cộng phần tăng nếu biết sự kiện mới duy nhất | Cần trừ đúng một lần hoặc tái tính |
| **SUM** | Có thể cộng giá trị mới | Cần bù chênh lệch giá trị cũ/mới |
| **AVG** | Nên lưu **SUM** và **COUNT** rồi chia khi đọc | Phải điều chỉnh cả tổng và số lượng |
| **MIN/MAX** | Giá trị mới có thể thay cực trị | Khi xóa cực trị, thường phải tìm cực trị tiếp theo |
| **COUNT(DISTINCT)** | Phải biết phần tử đã xuất hiện trong nhóm chưa | Không thể cộng/trừ mù quáng các số distinct từ nhóm con |
| **Median/percentile** | Thường cần dữ liệu phân bố hoặc cấu trúc hỗ trợ | Có thể phải tính lại hoặc dùng thuật toán xấp xỉ |

Ví dụ, trung bình của hai trung bình ngày có thể sai nếu mỗi ngày có số đơn khác nhau. Để tính trung bình toàn tháng đúng, lưu **sum_amount** và **order_count**, rồi chia **tổng các sum_amount / tổng các order_count**. Nếu lưu chỉ số gần đúng như HyperLogLog hoặc sketch percentile, cần công bố sai số và trường hợp không được dùng để ra quyết định chính xác tuyệt đối.

## 8. Sự kiện đến muộn, chỉnh sửa và hoàn tiền

Bảng tổng hợp theo thời gian đặc biệt dễ sai khi dữ liệu không đến theo thứ tự.

**Sự kiện đến muộn:** capture xảy ra lúc 23:58 hôm trước nhưng được ghi vào hệ thống lúc 00:03 hôm sau. Nếu grain dựa trên **captured_at**, sự kiện phải cộng vào nhóm **ngày hôm trước**, không phải ngày worker nhận được.

**Sửa lỗi thời gian hoặc số tiền:** nếu dữ liệu nguồn cho phép chỉnh sửa, phải trừ đóng góp cũ ở nhóm cũ và cộng đóng góp mới ở nhóm mới, trong ranh giới nhất quán phù hợp. Chỉ cộng một số chênh lệch vào nhóm mới có thể bỏ sót việc chuyển từ ngày hoặc loại tiền trước đó.

**Hoàn tiền:** một refund không nhất thiết làm giảm **captured_total**. Nếu chỉ số là “tổng capture được ghi nhận”, phải giữ nguyên lịch sử capture, lưu refund riêng và có thể tạo chỉ số **net_amount = captured_total - refunded_total** theo ngữ nghĩa đã thống nhất. Tùy nghiệp vụ, ngày ghi refund khác ngày ghi capture; nên định nghĩa rõ báo cáo theo **ngày phát sinh dòng tiền** hay phân bổ về **ngày đơn gốc**.

**Đổi trạng thái:** chỉ số “số đơn hiện đang PAID” khác với “số lần chuyển sang PAID”. Khi đơn từ PAID sang REFUNDED, chỉ số trạng thái hiện tại có thể giảm, còn số lần từng chuyển sang PAID có thể giữ nguyên. Cần mô hình hóa vòng đời trạng thái và phép bù thay vì đặt tên cả hai là **paid_count**.

**Xóa dữ liệu nguồn:** nếu có chính sách xóa/ẩn dữ liệu, việc giữ lại bản tổng hợp có thể được phép hoặc không tùy dữ liệu và chính sách cụ thể. Cần xác định liệu phải điều chỉnh bản tổng hợp, có còn được tái dựng từ nguồn hay không, và có cần xóa cả bản sao hay không.

## 9. Đồng bộ bất đồng bộ giữa nguồn và bảng tổng hợp

Khi dữ liệu nguồn nằm ở hệ thống giao dịch còn bảng tổng hợp ở data warehouse, search service hay document database, một giao dịch SQL thường không bảo đảm cập nhật cả hai nơi. Khi đó có thể dùng luồng sự kiện:

~~~text
Transaction ghi nghiệp vụ + outbox (cùng database)
                 |
                 v
         Publisher / stream
                 |
                 v
    Consumer kiểm tra ID, phiên bản và thứ tự
                 |
                 v
        Bảng tổng hợp / read model
                 |
                 v
      Đối soát và khả năng phát lại
~~~

Một bản thiết kế cần trả lời:

1. **Làm sao không mất sự kiện?** Ghi outbox trong cùng giao dịch với thay đổi nguồn, hoặc dùng cơ chế phát sự kiện có bảo đảm tương đương.
2. **Làm sao không đếm trùng?** Lưu định danh sự kiện đã xử lý hoặc sử dụng logic idempotent gắn với định danh nghiệp vụ.
3. **Làm sao xử lý sai thứ tự?** Dùng phiên bản nguồn, thứ tự theo aggregate hoặc mô hình bù/truy hồi đủ rõ.
4. **Làm sao biết số liệu mới đến đâu?** Theo dõi watermark, độ tuổi sự kiện chưa xử lý, backlog và thời gian cuối cùng projection đã cập nhật.
5. **Làm sao sửa số liệu hỏng?** Có nguồn chuẩn, có thể replay hoặc backfill, đối soát và dừng chuyển đường đọc khi sai vượt ngưỡng.

**At-least-once delivery** có thể giao sự kiện lặp. “Exactly once” ở tầng truyền tải không tự đồng nghĩa hiệu ứng nghiệp vụ chính xác một lần xuyên nhiều thành phần. Với SUM và COUNT, việc áp dụng lại một delta dương là lỗi dữ liệu thực sự, nên idempotency phải được thiết kế tại nơi cập nhật tổng.

**Nhất quán cuối cùng (eventual consistency)** chỉ phù hợp khi nghiệp vụ chấp nhận một cửa sổ dữ liệu cũ. Cần quy định ngưỡng cụ thể và hành vi khi vượt ngưỡng: hiển thị “cập nhật đến lúc…”, tạm ngừng chỉ số quan trọng, hoặc truy vấn nguồn khi cần số liệu tức thời.

## 10. Đối soát phải phát hiện cả nhóm thiếu và nhóm thừa

Giả sử dùng bảng **daily_capture_summary** trong PostgreSQL. Ta tính lại từ sự kiện nguồn và so sánh với giá trị lưu sẵn:

~~~sql
WITH expected AS (
    SELECT
        (captured_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS capture_day,
        currency,
        COUNT(*)::BIGINT AS capture_count,
        SUM(amount) AS captured_total
    FROM payment_events
    GROUP BY
        (captured_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
        currency
)
SELECT
    COALESCE(a.capture_day, e.capture_day) AS capture_day,
    COALESCE(a.currency, e.currency) AS currency,
    a.capture_count AS stored_count,
    e.capture_count AS expected_count,
    a.captured_total AS stored_total,
    e.captured_total AS expected_total
FROM daily_capture_summary AS a
FULL OUTER JOIN expected AS e
    ON a.capture_day = e.capture_day
   AND a.currency = e.currency
WHERE a.capture_day IS NULL
   OR e.capture_day IS NULL
   OR a.capture_count IS DISTINCT FROM e.capture_count
   OR a.captured_total IS DISTINCT FROM e.captured_total
ORDER BY capture_day, currency;
~~~

**FULL OUTER JOIN** phát hiện cả grain có ở nguồn nhưng chưa có trong bảng tổng hợp và grain tồn tại thừa trong bảng tổng hợp. **IS DISTINCT FROM** so sánh an toàn cả trường hợp NULL. Truy vấn này giả định cùng một snapshot nguồn trong câu lệnh, cùng công thức tính ngày, cùng phạm vi sự kiện và cùng quy tắc tiền tệ.

Với projection bất đồng bộ, không nên đối chiếu ngay mọi sự kiện mới commit rồi kết luận bản sao sai: hãy đối soát trên **cùng watermark/phiên bản đã xử lý**, hoặc chỉ so những nhóm đã vượt thời gian trễ được cam kết. Đối soát định kỳ cần ghi số nhóm lệch, tổng sai lệch, thời gian sai lâu nhất và tỷ lệ lỗi, rồi có quy trình tính lại từ nguồn.

**Một CHECK constraint trên hàng tổng hợp không thể tự xác nhận SUM/COUNT với bảng nguồn.** Nó chỉ bảo đảm điều kiện cục bộ như count không âm; vì vậy phép đối soát và cơ chế sửa sai vẫn cần thiết.

### 10.1. Rebuild và backfill không được phá cập nhật mới

Nếu bảng tổng hợp đang hoạt động mà phải tính lại toàn bộ lịch sử, không nên tùy tiện chạy **TRUNCATE** rồi nạp lại trong lúc consumer vẫn cập nhật. Các lựa chọn phụ thuộc kiến trúc:

- Tính vào bảng mới từ một **mốc snapshot/watermark** xác định.
- Áp dụng tiếp những thay đổi phát sinh sau mốc ấy, đúng thứ tự và không trùng.
- Đối soát giữa bản mới và nguồn ở cùng mốc.
- Chuyển đường đọc bằng một bước kiểm soát; theo dõi và có thể quay lại.
- Chỉ bỏ dữ liệu cũ khi đã xác minh không còn phụ thuộc.

Khi backfill theo từng nhóm, cần điều kiện chống một tác vụ cũ ghi đè kết quả vừa được cập nhật. Nếu dữ liệu gốc thay đổi lịch sử, phải biết cần tính lại nhóm nào và theo quy tắc nào.

## 11. Đo hiệu năng trước và sau phi chuẩn hóa

Để chọn phương án, ghi **mẫu truy cập thực**: truy vấn theo khóa hay theo khoảng ngày, số nhóm trả về, tần suất dashboard, số sự kiện ghi/giây, mức đồng thời và giới hạn độ trễ.

Ví dụ bảng dưới chỉ là **số liệu giả định dùng để thực hành quyết định**, không phải benchmark thật:

| Chỉ tiêu | Tổng hợp khi đọc | Materialized view 5 phút/lần | Bảng tăng dần mỗi sự kiện |
| --- | ---: | ---: | ---: |
| Dashboard p95 | 1.800 ms | 95 ms | 70 ms |
| Mục tiêu p95 | ≤ 250 ms | ≤ 250 ms | ≤ 250 ms |
| Độ tuổi dữ liệu lớn nhất quan sát | Gần thời điểm đọc | 9 phút | 18 giây |
| Giới hạn độ tươi yêu cầu | ≤ 2 phút | ≤ 2 phút | ≤ 2 phút |
| Chi phí ghi bổ sung | Không có | Tải chạy refresh | UPDATE nhóm mỗi sự kiện |
| Rủi ro chính | Đọc lịch sử lớn | Refresh vượt thời hạn | Khóa hàng nóng, sự kiện trùng |
| Đối soát/tái tạo | Truy vấn trực tiếp nguồn | REFRESH từ nguồn | Cần xử lý bù, đối soát và rebuild |

Theo giả định này, **materialized view chưa đạt yêu cầu độ tươi 2 phút**, dù dashboard đọc nhanh. Bảng tổng hợp tăng dần là ứng viên nếu có thể duy trì mức trễ, đảm bảo đúng và không làm đường ghi quá tải; nhưng vẫn cần đo thêm p95/p99 ghi, hàng đợi khóa, throughput và độ tăng trưởng. Nếu dashboard cho phép chậm 10 phút, materialized view lại có thể đơn giản và phù hợp hơn.

Cần đo:

- **Đọc:** p50/p95/p99, tốc độ trả kết quả, CPU, block đọc, truy vấn trong một request.
- **Ghi:** p95/p99 INSERT/UPDATE/DELETE, WAL, số hàng bị cập nhật, khóa chờ, deadlock và retry.
- **Dữ liệu:** số nhóm lệch, số sự kiện trùng, số liệu đến muộn, độ tuổi bản tổng hợp, khả năng tính lại.
- **Tài nguyên:** kích thước bảng/chỉ mục, chi phí refresh/rebuild, backlog của worker, tăng trưởng dữ liệu.
- **Tải đại diện:** giờ bình thường và cao điểm, dữ liệu phân bố lệch, vài grain cực nóng, trường hợp sửa/xóa dữ liệu lịch sử.

Một bảng tăng dần có thể biến việc quét hàng triệu sự kiện lúc đọc thành một **hàng bị cập nhật hàng nghìn lần/giây** lúc ghi. Nếu toàn bộ sự kiện cùng cập nhật grain **(hôm nay, VND)**, row lock có thể thành nút thắt. Có thể cần chia shard, gom theo lô, chuyển sang stream aggregation hoặc thay đổi độ chi tiết của grain; mỗi lựa chọn phải đo lại tính đúng đắn và độ tươi.

## 12. Bản đồ lựa chọn theo workload

| Nhu cầu nghiệp vụ | Phương án nên thử trước | Khi nào cân nhắc cấu trúc dẫn xuất |
| --- | --- | --- |
| Tính tổng vài dòng trên một đơn | Truy vấn SUM có chỉ mục theo order_id | Đường đọc rất nóng sau khi đã tối ưu, có cơ chế cập nhật giao dịch |
| Đếm quan hệ người theo dõi | COUNT có chỉ mục/quan hệ nguồn | Đọc cực thường xuyên, count lớn; có xử lý follow/unfollow chính xác |
| Dashboard theo ngày trên hàng triệu sự kiện | Lọc đúng khoảng, chỉ mục, kho phân tích | Đọc lặp nhiều và aggregate trực tiếp không đạt SLO |
| Dashboard chấp nhận dữ liệu trễ vài phút | Materialized view/refresh theo lịch | Khi refresh toàn bộ quá đắt hoặc độ tươi không đạt |
| Dashboard cần gần tức thời, ghi liên tục | Bảng tổng hợp tăng dần hoặc stream aggregation | Khi đã kiểm chứng idempotency, watermark, bù trừ, độ trễ |
| Số lượt xem mang tính tham khảo | Bộ đếm bất đồng bộ, gom lô hoặc xấp xỉ | Cần định nghĩa rõ đếm request, phiên hay người duy nhất |
| Số tiền dùng để quyết định thanh toán | Nguồn nghiệp vụ và giao dịch nhất quán | Chỉ lưu bản tổng khi đồng bộ và đối soát đáp ứng yêu cầu |
| Phân tích đa chiều lịch sử dài | Fact/dimension theo grain, OLAP | Pre-aggregation hoặc materialized view cho nhóm truy vấn lặp |

Trong mô hình **document**, có thể lưu **comment_count** cạnh document bài viết để trả về danh sách nhanh, nhưng mọi thao tác tạo/xóa/ẩn bình luận cần cập nhật tương ứng. Trong mô hình **graph**, có thể lưu số cạnh đi vào mỗi đỉnh để phục vụ thống kê nhanh, nhưng thêm/xóa cạnh phải thay đổi bộ đếm. Trong hệ **analytics**, có thể dùng bảng fact tổng hợp theo ngày và dimension; cần quản lý grain, dimension thay đổi theo thời gian và dữ liệu đến muộn.

Không mô hình nào tự động loại bỏ bài toán **nguồn chuẩn – cập nhật – nhất quán – đối soát**. Lựa chọn đúng là lựa chọn phục vụ truy vấn cần thiết với chi phí và độ đúng đo được.

## 13. Quy trình thiết kế và triển khai

1. **Nêu use case và ngữ nghĩa:** diễn giải câu hỏi bằng ngôn ngữ nghiệp vụ, phân biệt số sự kiện, số thực thể duy nhất, trạng thái hiện hành và lịch sử.
2. **Xác định nguồn chuẩn và grain:** chọn khóa duy nhất cho từng nhóm, đơn vị tiền, timezone, trạng thái, tenant và khoảng thời gian.
3. **Viết truy vấn nguồn chuẩn:** định nghĩa công thức có thể chạy lại để tính ra kết quả đúng; tránh dựa vào bản tổng khi đối soát chính nó.
4. **Đo baseline:** xem EXPLAIN, chỉ mục, thời gian API, tần suất và tải ghi; thử tối ưu đơn giản.
5. **Chọn cơ chế cập nhật:** cùng giao dịch, materialized view, job theo lô hay event/outbox; xác định độ tươi tối đa.
6. **Liệt kê mọi thay đổi:** thêm, sửa, xóa, hủy, hoàn tiền, chuyển trạng thái, retry, ghi trùng, dữ liệu đến muộn và tăng trưởng.
7. **Thiết kế idempotency và đối soát:** khóa nghiệp vụ, phiên bản/watermark, số liệu quan sát, phương án tái dựng và xử lý sai lệch.
8. **Backfill có kiểm soát:** nạp lịch sử, theo kịp dữ liệu mới và kiểm tra tính đúng đắn trước khi chuyển đường đọc.
9. **So sánh dưới tải đại diện:** đọc, ghi, lock contention, dung lượng, độ trễ và khả năng phục hồi.
10. **Đánh giá lại định kỳ:** nếu chỉ số ít được dùng, JOIN/SUM đã đủ nhanh hoặc pipeline quá tốn kém, cân nhắc bỏ cấu trúc dẫn xuất.

Một hợp đồng cho bảng **daily_capture_summary** nên ghi ít nhất: **nguồn = payment_events; grain = capture_day Asia/Ho_Chi_Minh × currency; count = số capture duy nhất; amount = tổng capture theo tiền tệ; hình thức đồng bộ = cùng DB và giao dịch; khóa chống trùng = event_id + định danh nghiệp vụ phù hợp; đối soát = COUNT/SUM lại từ nguồn; cách phục hồi = tính lại theo mốc nhất quán**.

## 14. Bài tập tình huống

### Bài 1 — Cộng trung bình có đúng không?

Ngày A có 2 đơn, giá trị lần lượt 100 và 300. Ngày B có 8 đơn, mỗi đơn giá trị 50. Dashboard lưu trung bình ngày A = 200 và trung bình ngày B = 50. Nhóm lấy **(200 + 50) / 2 = 125** làm trung bình của 10 đơn.

**Câu hỏi:** Phép tính sai ở đâu? Nên lưu gì trong bảng tổng hợp?

### Bài 2 — Bộ đếm bị tăng hai lần

Ứng dụng xử lý event **FollowCreated** bằng **UPDATE follower_count = follower_count + 1**. Consumer bị ngắt kết nối và nhận lại cùng sự kiện sau khi đã commit lần đầu.

**Câu hỏi:** Vì sao bộ đếm sai và cơ chế tối thiểu để khắc phục là gì?

### Bài 3 — Dashboard theo ngày và hai loại tiền

Bảng tổng hợp chỉ có khóa **capture_day** và một cột **captured_total**. Ngày 22/11 có capture 200.000 VND và 30 USD. Dashboard cộng thành **200.030** và gọi là “doanh thu trong ngày”.

**Câu hỏi:** Mô hình thiếu chiều nào? Nếu cần một số tiền quy đổi, phải thêm quy tắc gì?

### Bài 4 — Hai phương án đều nhanh khi đọc

Một materialized view làm mới mỗi 5 phút có p95 đọc 90 ms, nhưng dữ liệu cũ tới 11 phút khi refresh kéo dài. Bảng tổng hợp tăng dần có p95 65 ms và dữ liệu cũ tối đa 40 giây, nhưng khi cùng một ngày nhận nhiều giao dịch, p99 ghi tăng vượt SLO. Dashboard chấp nhận dữ liệu cũ tối đa 15 phút.

**Câu hỏi:** Nên chọn ngay bảng tăng dần chỉ vì độ tươi tốt hơn không? Cần đo gì để đưa ra quyết định?

### Gợi ý lời giải

1. Trung bình các trung bình **không có trọng số theo số đơn**. Tổng A là 400, tổng B là 400; trung bình đúng của 10 đơn là **800/10 = 80**. Nên lưu **sum_amount** và **order_count** hoặc đủ dữ liệu để tính trung bình có trọng số.
2. Consumer đã áp dụng cùng đóng góp hai lần. Cần định danh sự kiện ổn định, ghi nhận/đối chiếu việc đã xử lý **trong cùng ranh giới giao dịch** với cập nhật tổng hoặc cách idempotent tương đương; đồng thời xử lý trường hợp hai ID khác nhau cho cùng thao tác nghiệp vụ.
3. Thiếu **currency** trong grain. Phải nhóm riêng theo loại tiền; nếu cần quy đổi, phải xác định tỷ giá, thời điểm áp dụng, nguồn tỷ giá, đơn vị đích và quy tắc làm tròn.
4. **Chưa nên chọn bảng tăng dần** khi nó vi phạm SLO ghi. Materialized view có thể phù hợp nếu mức trễ 11 phút vẫn nằm trong 15 phút và refresh ổn định dưới tải đại diện. Cần đo độ trễ xấu nhất, p95/p99 ghi, refresh overlap, lock contention, khả năng phục hồi và độ đúng; sau đó chọn phương án đơn giản nhất đáp ứng mọi điều kiện.

## 15. Ghi nhớ

**Bảng tổng hợp, bộ đếm và kết quả tính sẵn đều là hợp đồng giữa dữ liệu nguồn và dữ liệu dẫn xuất.** Thiết kế đúng bắt đầu từ **grain**, đơn vị, định nghĩa đếm/tổng, thời điểm hiệu lực và khóa duy nhất; sau đó mới chọn cách lưu và cập nhật.

Muốn đọc nhanh bằng SUM/COUNT lưu sẵn, cần trả lời được ba câu hỏi: **“Đang tính điều gì?”, “Khi dữ liệu nguồn thay đổi, giá trị này đổi theo quy tắc nào?”, và “Làm sao tính lại, phát hiện sai và phục hồi?”** Không trả lời được cả ba thì tối ưu truy vấn trước sẽ an toàn hơn việc tạo một bảng tổng hợp khó kiểm soát.

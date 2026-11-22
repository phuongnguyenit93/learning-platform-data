# Bản ghi theo phiên bản với khoảng hiệu lực rõ ràng

## 1. Vì sao phải phiên bản hóa theo khoảng hiệu lực?

Trong mô hình dữ liệu, lưu giá trị mới nhất của một thực thể thường rất đơn giản: một hàng có khóa chính, các thuộc tính và cột `updated_at`. Nhưng khi nghiệp vụ hỏi **“giá trị nào được áp dụng vào ngày X?”**, hàng mới nhất không còn đủ. Một thuộc tính có thể thay đổi nhiều lần, mỗi giá trị chỉ đúng trong một khoảng thời gian xác định.

Ví dụ nền tảng thuê bao có gói dịch vụ `STANDARD` và cần lưu mức phí theo ngày hiệu lực:

| Phiên bản giá | Khoảng có hiệu lực | Phí tháng |
|---|---|---:|
| P1 | Từ 01/01/2026 đến trước 01/07/2026 | 100.000 VND |
| P2 | Từ 01/07/2026 đến trước 01/10/2026 | 120.000 VND |
| P3 | Từ 01/10/2026 trở đi | 130.000 VND |

Khi lập hóa đơn cho tháng 08/2026, hệ thống phải dùng **120.000 VND**; khi hiển thị mức phí áp dụng tại 15/11/2026, kết quả là **130.000 VND**. Nếu chỉ ghi đè `monthly_fee` ở bản ghi gói dịch vụ, mức phí 100.000 và 120.000 sẽ biến mất khỏi mô hình nghiệp vụ.

Bài **“Bản ghi theo phiên bản với khoảng hiệu lực rõ ràng”**, thuộc chương **Thời gian và lịch sử** của module **DATABASE_DATA_MODELING**, tập trung vào cách biến yêu cầu ấy thành mô hình có thể kiểm chứng: xác định khóa nghiệp vụ, chia khoảng thời gian, ràng buộc không chồng lấn, xử lý thay đổi và thiết kế truy vấn. Đây là một phần quan trọng của kỹ năng chuyển yêu cầu kinh doanh thành lược đồ dữ liệu rõ ràng, dễ tiến hóa.

Sau bài học, người học cần làm được bốn việc:

1. Phân biệt **thực thể logic** với các **phiên bản của thực thể** và xác định khoảng thời gian mỗi phiên bản có hiệu lực.
2. Chọn quy ước biên thời gian, độ chính xác, thời điểm bắt đầu/kết thúc và quy tắc khoảng trống.
3. Thiết kế khóa, ràng buộc, chỉ mục và giao dịch để không xuất hiện hai phiên bản hợp lệ cùng lúc ngoài chủ đích.
4. Trả lời truy vấn **as-of** và kiểm thử các trường hợp chuyển tiếp, sửa sai, thay đổi tương lai, dữ liệu hồi tố.

## 2. Thực thể, phiên bản và khoảng hiệu lực là ba khái niệm khác nhau

**Thực thể logic** là đối tượng mà nghiệp vụ nhận diện xuyên suốt thời gian, ví dụ gói thuê bao `STANDARD`, một hợp đồng, một nhân viên hoặc một tuyến vận chuyển. Khóa nhận diện thực thể phải ổn định kể cả khi các thuộc tính của nó thay đổi.

**Bản ghi phiên bản** là một tập giá trị được gắn với một giai đoạn hiệu lực. Một thực thể có thể có nhiều phiên bản. Phiên bản cần được định danh riêng để có thể tham chiếu, theo dõi và sửa theo quy trình.

**Khoảng hiệu lực** (*validity interval* hoặc *valid-time period*) cho biết các thuộc tính trong phiên bản đúng theo quy tắc nghiệp vụ từ khi nào đến khi nào. Trong ví dụ giá thuê bao, mỗi phiên bản cần có giá tiền và khoảng ngày áp dụng. Không phải mọi cột đều cần phiên bản hóa: tên gói có thể ổn định trong khi phí gói thay đổi theo thời gian; phạm vi phiên bản phụ thuộc vào các thuộc tính có cùng chu kỳ thay đổi.

Có thể hình dung quan hệ:

~~~mermaid
erDiagram
    SERVICE_PLAN ||--o{ PLAN_PRICE_VERSION : "có các phiên bản giá"
    SERVICE_PLAN {
        bigint plan_id PK
        text plan_name
    }
    PLAN_PRICE_VERSION {
        bigint version_id PK
        bigint plan_id FK
        text currency_code
        decimal monthly_fee
        daterange valid_period
        text source_decision_id
    }
~~~

`plan_id` định danh gói dịch vụ; `version_id` định danh từng phiên bản giá. **Một phiên bản mới không nhất thiết là một thực thể mới.** Khi tính phí, nghiệp vụ trước hết xác định gói, đơn vị tiền tệ và ngày áp dụng, sau đó chọn phiên bản phù hợp.

### 2.1. Khóa nghiệp vụ của phiên bản phải đủ phạm vi

Giả sử gói `STANDARD` có phí bằng VND và USD. Nếu ràng buộc cấm mọi khoảng trùng nhau chỉ trên `plan_id`, hệ thống sẽ không cho tồn tại đồng thời hai mức phí theo hai loại tiền tệ, dù đây là dữ liệu hợp lệ.

Phạm vi của một phiên bản giá có thể là:

~~~text
(plan_id, currency_code) + valid_period
~~~

Nếu còn khác nhau theo **khu vực**, **nhóm khách hàng**, **loại kênh bán** hoặc **loại giá**, các thuộc tính ấy có thể phải tham gia khóa nghiệp vụ và ràng buộc chống trùng. Không thêm thuộc tính vào khóa một cách máy móc: cần hỏi **“hai giá trị này có được phép cùng tồn tại tại một thời điểm hay không?”**

### 2.2. ID của phiên bản không phải thứ tự thời gian hiệu lực

Một khóa `version_id` dạng số tăng dần thường phản ánh thứ tự **bản ghi được tạo**, không bảo đảm là thứ tự **ngày có hiệu lực**. Hệ thống có thể ghi trước một mức giá sẽ áp dụng tháng 12 rồi hôm sau mới thêm một quyết định có hiệu lực hồi tố từ tháng 8.

Do đó:

- Dùng `version_id` để **định danh** và tham chiếu phiên bản.
- Dùng `valid_from` hoặc `lower(valid_period)` để **sắp xếp theo hiệu lực nghiệp vụ**.
- Dùng mốc ghi nhận hoặc số thứ tự thay đổi **riêng** nếu cần biết phiên bản nào được hệ thống nhập trước.

Không suy ra “giá mới nhất đang có hiệu lực” bằng `MAX(version_id)`.

## 3. Quy ước khoảng hiệu lực: `[from, to)`

Một quy ước được sử dụng rộng rãi là khoảng **đầu đóng, cuối mở**:

~~~text
[valid_from, valid_to)
~~~

Nghĩa là:

~~~text
valid_from <= thời_điểm_cần_hỏi < valid_to
~~~

Ví dụ:

~~~text
P1: [2026-01-01, 2026-07-01) → 100.000 VND
P2: [2026-07-01, 2026-10-01) → 120.000 VND
P3: [2026-10-01, +∞)          → 130.000 VND
~~~

Ngày **01/07** thuộc P2 và không còn thuộc P1. Ngày **01/10** thuộc P3 và không còn thuộc P2. Hai phiên bản kế tiếp có thể có **`valid_to` của bản trước bằng `valid_from` của bản sau** mà không trùng nhau.

| Ngày truy vấn | Phiên bản đúng | Giải thích |
|---|---|---|
| 31/12/2025 | Không có | Chưa tới `valid_from` của P1 |
| 01/01/2026 | P1 | Bao gồm biên đầu |
| 30/06/2026 | P1 | Chưa tới biên cuối |
| 01/07/2026 | P2 | P1 đã hết hiệu lực |
| 30/09/2026 | P2 | Ngày cuối cùng trước 01/10 |
| 01/10/2026 | P3 | Bao gồm biên đầu của P3 |

### 3.1. Tại sao không dùng hai biên đều bao gồm?

Nếu lưu P1 đến **01/07** và P2 cũng bắt đầu **01/07**, hai phiên bản có thể cùng đúng trong một ngày. Một số nhóm giải quyết bằng cách kết thúc P1 lúc **23:59:59** ngày 30/06, nhưng cách này phụ thuộc độ chính xác giây, mili giây hoặc micro giây, dễ tạo lỗi khi hệ thống nâng cấp kiểu thời gian.

Khoảng nửa mở tránh phải trừ đi một đơn vị thời gian nhỏ nhất. Với cột kiểu **ngày** (`date`), khoảng `[2026-07-01, 2026-10-01)` gồm các ngày từ 01/07 đến 30/09. Với kiểu **thời điểm** (`timestamptz`), khoảng gồm mọi thời điểm từ mốc đầu đến trước mốc cuối.

### 3.2. Biên kết thúc chưa xác định

Đối với phiên bản đang có hiệu lực vô thời hạn theo thông tin hiện tại, có thể dùng **biên trên không giới hạn**:

~~~text
[2026-10-01, +∞)
~~~

Trong mô hình hai cột, một quy ước là `valid_to IS NULL` nghĩa là “chưa có ngày kết thúc”. Trong PostgreSQL, kiểu `daterange` có thể biểu diễn biên trên *unbounded*. Không nên chọn một ngày tùy ý như `9999-12-31` trừ khi toàn hệ thống đã định nghĩa và bảo đảm rằng đó là giá trị sentinel.

**Không giới hạn biên trên** không có nghĩa là nghiệp vụ cam kết giá sẽ tồn tại mãi mãi; nó chỉ có nghĩa là chưa có quyết định kết thúc hiệu lực trong dữ liệu hiện tại.

### 3.3. Chọn `date` hay timestamp

Nếu yêu cầu nói **“mức phí áp dụng theo ngày tại Việt Nam”**, kiểu ngày địa phương có thể phù hợp. Nếu yêu cầu nói **“quyền truy cập có hiệu lực chính xác lúc 14:30 UTC”**, cần thời điểm có múi giờ.

| Ngữ nghĩa nghiệp vụ | Biểu diễn phù hợp | Điều phải thống nhất |
|---|---|---|
| Hợp đồng có hiệu lực từ **ngày** 01/07 | `date` hoặc `daterange` | Ngày tính theo lịch/khu vực nào |
| Quyền truy cập mở tại **thời điểm** 14:30 | `timestamptz` hoặc `tstzrange` | Mốc thời gian, múi giờ hiển thị |
| Khung giờ lặp vào thứ hai hằng tuần | Mô hình quy tắc lịch, đôi khi kèm timezone | DST, ngoại lệ, ngày nghỉ |
| “Đầu quý sau” chưa chốt ngày | Quy tắc hoặc trạng thái kế hoạch riêng | Không bịa timestamp khi chưa xác định |

Không thể giải quyết đầy đủ một lịch lặp vô hạn bằng cách tự sinh một hàng cho từng thời điểm nếu nghiệp vụ thực chất định nghĩa **quy tắc lặp**. Với loại đó, cần mô hình recurrence và ngoại lệ hoặc bảng các lần xảy ra khi thật sự cần.

## 4. Các bất biến nghiệp vụ cần làm rõ

Một mô hình phiên bản tốt trước tiên phải trả lời các câu hỏi sau:

1. **Tối đa một hay nhiều?** Tại ngày X, trong cùng `plan_id` và `currency_code`, có được phép có hai giá cùng có hiệu lực không?
2. **Có bắt buộc liên tục?** Mọi ngày từ khi gói được phát hành có phải có một giá, hay có thể có các giai đoạn không bán?
3. **Có cho ghi trước?** Có được thêm phiên bản tháng 12 khi tháng 8 vẫn đang áp dụng giá cũ?
4. **Có cho sửa hồi tố?** Khi nhập sai giá tháng 5 vào tháng 9, có được sửa lịch sử hiệu lực không?
5. **Có cần biết hệ thống từng ghi nhận gì?** Có phải trả lời “ngày 10/08, hệ thống lúc đó tin mức giá tháng 7 là bao nhiêu” không?
6. **Có cần giữ bằng chứng của giao dịch đã chốt?** Giá dùng cho hóa đơn đã phát hành có được thay đổi theo thông tin điều chỉnh không?
7. **Phiên bản trùng giá trị có nên gộp?** Hai quyết định khác nhau cùng ra giá 120.000 VND có cần hai bản ghi để lưu căn cứ nghiệp vụ không?

Các câu trả lời dẫn tới các bất biến phổ biến:

| Bất biến | Cách kiểm chứng |
|---|---|
| Mỗi phiên bản có khoảng hiệu lực hợp lệ, không rỗng | `CHECK` hoặc validator |
| Trong cùng khóa nghiệp vụ, không có hai khoảng hiệu lực chồng lấn trái phép | Ràng buộc loại trừ hoặc kiểm tra được bảo vệ bằng transaction |
| Nếu bắt buộc liên tục, khoảng mới nối tiếp khoảng cũ | Kiểm tra dải ngày, khoảng trống và quy tắc phát hành |
| Mỗi phiên bản có nguồn quyết định | Cột bắt buộc và khóa tham chiếu/định danh nguồn |
| Mọi thay đổi nhiều hàng là nguyên tử | Transaction |
| Ghi đồng thời không tạo lịch thời gian mâu thuẫn | Khóa hoặc phiên bản lạc quan, kết hợp ràng buộc dữ liệu |
| Hóa đơn đã chốt vẫn có căn cứ về giá đã dùng | Lưu giá thực tính và tham chiếu/snapshot quyết định giá |

**Không chồng lấn** và **không có khoảng trống** là hai điều kiện khác nhau. Một constraint cấm giao nhau không bảo đảm rằng ngày nào cũng có một phiên bản. Việc **có cần phủ kín thời gian hay không** phải do nghiệp vụ quyết định.

## 5. Thiết kế lược đồ vật lý trong PostgreSQL

Phần này xây dựng bảng giá theo phiên bản với một trục **thời gian có hiệu lực** (*valid time*). Đây là ví dụ để thực hành trên PostgreSQL; các hệ quản trị khác có thể cần cấu trúc và cơ chế chống overlap riêng.

### 5.1. Hai bảng: thực thể gốc và phiên bản giá

~~~sql
-- Cung cấp toán tử so sánh bằng cho bigint/text trong chỉ mục GiST.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE service_plan (
    plan_id    bigint PRIMARY KEY,
    plan_name  text NOT NULL
);

CREATE TABLE plan_price_version (
    version_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id            bigint NOT NULL
                       REFERENCES service_plan(plan_id),
    currency_code      text NOT NULL
                       CHECK (currency_code ~ '^[A-Z]{3}$'),
    monthly_fee        numeric(14, 2) NOT NULL
                       CHECK (monthly_fee >= 0),
    valid_period       daterange NOT NULL,
    source_decision_id text NOT NULL,
    recorded_at        timestamptz NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT ck_valid_period
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    CONSTRAINT ex_plan_price_nonoverlap
        EXCLUDE USING gist (
            plan_id WITH =,
            currency_code WITH =,
            valid_period WITH &&
        )
);

CREATE INDEX ix_plan_price_start
    ON plan_price_version (
        plan_id, currency_code, lower(valid_period)
    );
~~~

Giải thích các quyết định chính:

- **`service_plan.plan_id`** định danh gói ổn định qua thời gian; **`plan_price_version.version_id`** định danh từng bản ghi phiên bản.
- **`monthly_fee numeric(14,2)`** tránh sai số nhị phân thường gặp khi dùng `float` cho giá tiền. Nếu tiền tệ không có chữ số thập phân, kiểu và quy tắc làm tròn có thể được chọn khác.
- **`valid_period daterange`** lưu trọn một khoảng ngày; toán tử `@>` kiểm tra chứa một ngày, `&&` kiểm tra hai khoảng giao nhau.
- **`source_decision_id`** liên kết mức phí với quyết định có thẩm quyền. Trong hệ thống thật có thể cần khóa ngoại tới bảng quyết định giá.
- **`recorded_at`** cung cấp dấu mốc nhập bản ghi để quan sát. Nó **không tự làm bảng trở thành bitemporal** và không đủ để khôi phục mọi cách hiểu trong quá khứ khi khoảng được sửa.
- **`ck_valid_period`** yêu cầu khoảng không rỗng, có điểm bắt đầu hữu hạn, bao gồm điểm bắt đầu và không bao gồm điểm kết thúc.
- **`ex_plan_price_nonoverlap`** ngăn hai hàng cùng gói, cùng tiền tệ có ngày hiệu lực giao nhau. PostgreSQL thực thi ràng buộc bằng chỉ mục GiST; extension `btree_gist` giúp so sánh bằng các cột thông thường trong cùng ràng buộc.

Ràng buộc loại trừ hoạt động cả với khoảng có biên trên vô hạn: một phiên bản mới không thể bắt đầu trong khi phiên bản hiện tại vẫn kéo dài đến vô hạn. Cần đóng khoảng hiện tại trước khi chèn khoảng kế tiếp trong cùng transaction.

**Giới hạn:** một giá có thể áp dụng cho nhiều nhóm khách, khu vực hoặc kênh bán. Nếu thực thể cần có nhiều giá đồng thời theo các chiều đó, phải thêm chính xác các chiều vào bảng và ràng buộc. Ngược lại, nếu một gói chỉ có một giá hợp lệ cho mọi loại tiền tệ, khóa nghiệp vụ phải phản ánh điều kiện khác. DDL ở đây là một hợp đồng nghiệp vụ cụ thể, không phải mẫu áp dụng nguyên trạng cho mọi hệ thống.

### 5.2. Khởi tạo ba phiên bản có hiệu lực nối tiếp

~~~sql
INSERT INTO service_plan (plan_id, plan_name)
VALUES (7, 'STANDARD');

INSERT INTO plan_price_version (
    plan_id, currency_code, monthly_fee,
    valid_period, source_decision_id
)
VALUES
(
    7, 'VND', 100000,
    daterange(DATE '2026-01-01', DATE '2026-07-01', '[)'),
    'PRICING-2026-Q1'
),
(
    7, 'VND', 120000,
    daterange(DATE '2026-07-01', DATE '2026-10-01', '[)'),
    'PRICING-2026-Q3'
),
(
    7, 'VND', 130000,
    daterange(DATE '2026-10-01', NULL, '[)'),
    'PRICING-2026-Q4'
);
~~~

`NULL` được truyền làm biên trên của `daterange` để biểu diễn khoảng không giới hạn; điều này khác với việc đặt toàn bộ `valid_period` bằng SQL `NULL` — cột khoảng vẫn luôn **NOT NULL**.

Với các hàng trên, ràng buộc loại trừ chấp nhận mọi cặp vì khoảng hiệu lực không giao nhau. Nếu vô tình thêm giá 125.000 VND có hiệu lực `[2026-09-01, 2026-11-01)`, PostgreSQL sẽ từ chối vì khoảng này giao với cả P2 và P3.

## 6. Truy vấn phiên bản đúng theo ngày nghiệp vụ

### 6.1. Truy vấn *as-of* một ngày

~~~sql
SELECT
    version_id,
    plan_id,
    currency_code,
    monthly_fee,
    valid_period,
    source_decision_id
FROM plan_price_version
WHERE plan_id = 7
  AND currency_code = 'VND'
  AND valid_period @> DATE '2026-08-15';
~~~

Kết quả theo dữ liệu ví dụ là mức phí **120.000 VND**. Toán tử `@>` có nghĩa “khoảng ở vế trái chứa ngày ở vế phải”.

Nếu nghiệp vụ quy định tối đa một mức phí tại ngày truy vấn, kết quả hợp lệ có **0 hoặc 1 hàng**. Một hàng nghĩa là tìm thấy giá; không có hàng nghĩa là ngày đó **chưa có giá trong dữ liệu**. Không tự chọn hàng có `valid_from` gần nhất khi truy vấn as-of không khớp.

Câu SQL tương đương khi dùng hai cột `valid_from`/`valid_to`:

~~~sql
SELECT monthly_fee
FROM plan_price_version_columns
WHERE plan_id = 7
  AND currency_code = 'VND'
  AND valid_from <= DATE '2026-08-15'
  AND (
      valid_to IS NULL
      OR DATE '2026-08-15' < valid_to
  );
~~~

Đoạn này minh họa **một lược đồ thay thế** có hai cột riêng, không phải truy vấn chạy trên bảng `plan_price_version` sử dụng `daterange` ở phần 5. Quy tắc nửa mở vẫn giữ nguyên khi đổi cách lưu.

### 6.2. Xem toàn bộ timeline

~~~sql
SELECT
    version_id,
    monthly_fee,
    lower(valid_period) AS valid_from,
    upper(valid_period) AS valid_to
FROM plan_price_version
WHERE plan_id = 7
  AND currency_code = 'VND'
ORDER BY lower(valid_period), version_id;
~~~

Trong PostgreSQL, `lower()` và `upper()` lấy biên của khoảng. Với biên trên không giới hạn, `upper(valid_period)` trả `NULL`, nên UI có thể hiển thị **“chưa có ngày kết thúc”** thay vì xuất chữ `NULL` thô.

Không sắp xếp timeline theo `recorded_at` khi mục tiêu là trình bày **thứ tự hiệu lực nghiệp vụ**: một phiên bản có hiệu lực trong quá khứ có thể được nhập hoặc chỉnh sau các phiên bản tương lai.

### 6.3. Tìm các phiên bản giao một kỳ báo cáo

~~~sql
SELECT
    version_id,
    monthly_fee,
    valid_period
FROM plan_price_version
WHERE plan_id = 7
  AND currency_code = 'VND'
  AND valid_period
      && daterange(DATE '2026-06-15', DATE '2026-07-15', '[)')
ORDER BY lower(valid_period);
~~~

Kỳ báo cáo **15/06–trước 15/07** giao cả P1 và P2. Nếu hệ thống tính tiền theo khoảng ngày, đây là tín hiệu phải **chia kỳ tính** thành các đoạn theo hiệu lực, rồi áp dụng quy tắc prorate hoặc tính phí đã được nghiệp vụ phê duyệt. Chọn một giá duy nhất chỉ dựa trên ngày bắt đầu kỳ có thể sai.

**Tách khoảng thời gian** và **tính tiền** là hai trách nhiệm: mô hình phiên bản chỉ chỉ ra những mức giá giao với kỳ; công thức tính phí, ngày quy đổi, làm tròn và thuế phải được định nghĩa riêng.

## 7. Thêm phiên bản tương lai mà không làm mất khoảng hiện tại

Tháng 11/2026, bộ phận giá phê duyệt mức **140.000 VND** bắt đầu ngày **01/12/2026**. P3 hiện có hiệu lực từ 01/10 về sau, nên không thể chỉ chèn phiên bản mới `[01/12, +∞)`: hai khoảng sẽ chồng nhau.

Ta cần biến đổi:

~~~text
Trước:
P3: [01/10/2026, +∞) → 130.000 VND

Sau:
P3: [01/10/2026, 01/12/2026) → 130.000 VND
P4: [01/12/2026, +∞)          → 140.000 VND
~~~

Với điều kiện biết dữ liệu đầu vào đúng như ví dụ, các thao tác có thể cùng nằm trong một transaction:

~~~sql
BEGIN;

UPDATE plan_price_version
SET valid_period = daterange(
    lower(valid_period),
    DATE '2026-12-01',
    '[)'
)
WHERE plan_id = 7
  AND currency_code = 'VND'
  AND lower(valid_period) < DATE '2026-12-01'
  AND upper_inf(valid_period)
RETURNING version_id, valid_period;

-- Ứng dụng phải kiểm tra UPDATE trả về đúng một hàng.
-- Nếu không, ROLLBACK và đọc lại dữ liệu trước khi quyết định.

INSERT INTO plan_price_version (
    plan_id, currency_code, monthly_fee,
    valid_period, source_decision_id
)
VALUES (
    7, 'VND', 140000,
    daterange(DATE '2026-12-01', NULL, '[)'),
    'PRICING-2026-DEC'
);

COMMIT;
~~~

`RETURNING` giúp ứng dụng xác minh bản bị rút ngắn. Nếu `UPDATE` tác động **0 hàng**, ứng dụng phải **ROLLBACK**, thay vì mặc nhiên tiếp tục và cho rằng giá cũ đã được đóng thành công. Mẫu trên là minh họa các thao tác phải phối hợp; để ứng dụng kiểm soát hoàn toàn điều kiện giữa UPDATE và INSERT, triển khai nên đặt transaction trong một service/stored procedure có kiểm tra số hàng.

Cần bảo vệ transaction khỏi các yêu cầu cùng điều chỉnh kế hoạch giá. Có thể khóa hàng gốc `service_plan` cho gói 7, dùng optimistic version trên hàng gốc, hoặc áp dụng chiến lược transaction/isolation nhất quán. Ràng buộc `EXCLUDE` là lớp bảo vệ cuối cùng chống giao khoảng; nó không tự giải quyết mọi xung đột nghiệp vụ.

### 7.1. Ghi trước nhiều lần thay đổi tương lai

Doanh nghiệp có thể quyết định ngay từ tháng 11 rằng:

- Từ 01/12 đến trước 01/03 năm sau: 140.000 VND.
- Từ 01/03 năm sau: 150.000 VND.

Cả hai phiên bản có thể được **ghi vào cơ sở dữ liệu trước khi có hiệu lực**, miễn các khoảng hiệu lực không chồng lấn và mọi truy vấn hiện tại đều lọc theo ngày nghiệp vụ.

Điều này cho thấy **phiên bản được ghi mới nhất** chưa chắc là **phiên bản có hiệu lực hôm nay**. API giá hiện tại phải hỏi `valid_period @> CURRENT_DATE` theo lịch nghiệp vụ, không đơn giản `ORDER BY recorded_at DESC LIMIT 1`.

Nếu ngày nghiệp vụ được xác định theo múi giờ chi nhánh, `CURRENT_DATE` của database chỉ phù hợp khi session timezone và quy tắc ngày đã được đồng bộ. Một ứng dụng đa múi giờ nên truyền ngày nghiệp vụ đã tính rõ ràng vào truy vấn.

## 8. Chèn phiên bản giữa lịch sử và xử lý điều chỉnh hồi tố

Giả sử sau khi đã lưu P2 `[01/07, 01/10)` ở giá 120.000 VND, bộ phận tài chính phát hiện một quyết định đã được phê duyệt yêu cầu giá **125.000 VND trong tháng 08**, còn tháng 07 và tháng 09 giữ giá 120.000 VND.

Cần **chia khoảng đang có** thành ba đoạn:

~~~text
Trước:
[01/07, 01/10) → 120.000

Sau:
[01/07, 01/08) → 120.000
[01/08, 01/09) → 125.000
[01/09, 01/10) → 120.000
~~~

Một phép biến đổi minh họa:

~~~sql
BEGIN;

UPDATE plan_price_version
SET valid_period =
    daterange(DATE '2026-07-01', DATE '2026-08-01', '[)')
WHERE plan_id = 7
  AND currency_code = 'VND'
  AND valid_period =
    daterange(DATE '2026-07-01', DATE '2026-10-01', '[)')
RETURNING version_id;

-- Yêu cầu đúng một phiên bản được chia; nếu không thì ROLLBACK.

INSERT INTO plan_price_version (
    plan_id, currency_code, monthly_fee,
    valid_period, source_decision_id
)
VALUES
(
    7, 'VND', 125000,
    daterange(DATE '2026-08-01', DATE '2026-09-01', '[)'),
    'CORRECTION-2026-AUG'
),
(
    7, 'VND', 120000,
    daterange(DATE '2026-09-01', DATE '2026-10-01', '[)'),
    'CORRECTION-2026-AUG'
);

COMMIT;
~~~

Đây là **bài toán chia khoảng**, không đơn thuần UPDATE một cột giá. Trong hệ thống thực, đoạn cần sửa có thể giao nhiều phiên bản, nằm ở biên hoặc nằm ngoài phạm vi hiện đã lưu. Service phải tính các đoạn còn lại từ dữ liệu đang tồn tại, loại bỏ đoạn rỗng và áp dụng quyết định mới theo thứ tự được nghiệp vụ cho phép.

### 8.1. Vì sao sửa lịch sử hiệu lực cần thận trọng?

Bảng chỉ có `valid_period` như trên phản ánh **lịch hiệu lực đang được hệ thống chấp nhận hiện nay**. Khi sửa P2, khoảng hiệu lực cũ `[01/07, 01/10)` không còn nguyên vẹn trong bảng. Dù có `recorded_at`, ta vẫn chưa chắc tái dựng được câu trả lời của hệ thống **trước khi ghi nhận bản đính chính**.

Cần phân biệt:

- **Lịch sử hiệu lực (valid-time versions):** giá trị nào hiện được coi là đúng cho một ngày nghiệp vụ.
- **Lịch sử kiến thức hệ thống (recorded/system-time versions):** hệ thống đã tin điều gì vào một thời điểm ghi nhận trong quá khứ.
- **Lịch sử sự kiện/điều chỉnh:** ai quyết định, dựa vào tài liệu nào và vì sao việc sửa xảy ra.

Nếu nghiệp vụ phải trả lời cả **“giá nào áp dụng ngày 15/08?”** và **“trước khi chỉnh ngày 20/09, hệ thống từng tin giá 15/08 là gì?”**, cần thiết kế **hai trục thời gian (bitemporal)**, hoặc lưu chuỗi sự kiện đầy đủ có thể tái dựng diễn biến kiến thức. Chỉ giữ một dấu thời gian `recorded_at` trên hàng sau UPDATE không thay thế được mô hình đó.

### 8.2. Hóa đơn đã chốt không nên âm thầm đổi giá

Một hóa đơn đã phát hành vào 15/08 có thể từng áp dụng giá 120.000 VND. Sau khi sửa lịch hiệu lực, truy vấn giá theo ngày 15/08 trả về 125.000 VND. Nếu UI hóa đơn tính lại giá bằng cách JOIN bảng phiên bản hiện tại, hóa đơn cũ sẽ hiện sai số tiền đã thu.

Thiết kế hóa đơn cần lưu dữ liệu đã áp dụng lúc chốt, chẳng hạn:

~~~text
invoice_line
  invoice_line_id
  invoice_id
  service_period
  plan_id
  charged_amount
  currency_code
  pricing_decision_ref
  price_version_ref (nếu có)
  finalized_at
~~~

**`charged_amount`** là số tiền thực chốt theo quy tắc tính phí; **`pricing_decision_ref`** liên kết đến căn cứ. Nếu tham chiếu `price_version_ref` tới một hàng có khoảng hiệu lực có thể bị UPDATE hồi tố, không được coi tham chiếu đó một mình là bằng chứng bất biến về cách tính ban đầu. Có thể lưu snapshot các tham số tính phí hoặc một tập phiên bản được đóng băng để đối soát.

Điều chỉnh hồi tố thường dẫn đến một nghiệp vụ riêng: hoàn tiền, ghi bù hoặc phát hành chứng từ điều chỉnh. Nó không tự động cho phép ghi đè giao dịch tài chính đã chốt.

## 9. Phát hiện khoảng trống, chồng lấn và phiên bản không hợp lệ

### 9.1. Chồng lấn (overlap)

Hai khoảng `A` và `B` chồng lấn nếu chúng có ít nhất một ngày chung. Với khoảng nửa mở có biên hữu hạn, điều kiện tương đương là:

~~~text
A.from < B.to AND B.from < A.to
~~~

Với biên vô hạn phải xử lý riêng; trong PostgreSQL có thể sử dụng toán tử `&&` của `daterange` để tránh phải tự viết từng nhánh.

~~~sql
SELECT
    daterange(DATE '2026-07-01', DATE '2026-10-01', '[)')
    &&
    daterange(DATE '2026-09-01', DATE '2026-12-01', '[)')
    AS overlaps;
-- true
~~~

Trong DDL đã xây dựng, `ex_plan_price_nonoverlap` ngăn hai khoảng chồng nhau cho cùng `plan_id` và `currency_code`. Không thể thay bằng `UNIQUE(plan_id, currency_code, lower(valid_period))`: hai khoảng bắt đầu ở ngày khác nhau vẫn có thể giao nhau.

### 9.2. Khoảng trống (gap)

Giả sử giá P1 hết hiệu lực 01/07 nhưng P2 bắt đầu 03/07. Các ngày 01/07 và 02/07 không có giá hợp lệ. Đây có thể là lỗi hoặc là chủ đích tạm dừng bán.

Một truy vấn rà soát các khoảng **ở giữa hai phiên bản liên tiếp**:

~~~sql
WITH ordered_prices AS (
    SELECT
        plan_id,
        currency_code,
        upper(valid_period) AS current_end,
        LEAD(lower(valid_period)) OVER (
            PARTITION BY plan_id, currency_code
            ORDER BY lower(valid_period)
        ) AS next_start
    FROM plan_price_version
)
SELECT
    plan_id, currency_code, current_end, next_start
FROM ordered_prices
WHERE current_end IS NOT NULL
  AND next_start IS NOT NULL
  AND current_end < next_start;
~~~

Kết quả chỉ tìm **khoảng trống nằm giữa các hàng đang có**. Nó không thể biết liệu có thiếu giá trước phiên bản đầu tiên hoặc sau phiên bản cuối cùng hay không nếu không có thêm quy tắc về **thời điểm gói bắt đầu/kết thúc được bán**. Nếu nghiệp vụ yêu cầu phủ kín toàn bộ khoảng bán, kiểm thử phải so sánh timeline giá với khoảng hoạt động của gói.

### 9.3. Liền kề và giá trị bằng nhau

Hai phiên bản liền kề có `previous.valid_to = next.valid_from`. Nếu giá trị của chúng bằng nhau, về mặt truy vấn giá chúng có thể được **gộp khoảng**. Tuy nhiên, đừng gộp khi cần giữ riêng nguồn quyết định, hợp đồng, phạm vi áp dụng hoặc lý do điều chỉnh.

Ví dụ hai lần duyệt đều cho giá 120.000 VND nhưng có hiệu lực ở hai quý khác nhau: gộp thành một hàng có thể làm mất bằng chứng rằng hai quyết định giá khác nhau từng được đưa ra. Quy tắc gộp là quyết định về ngữ nghĩa và kiểm toán, không chỉ tối ưu dung lượng.

### 9.4. Các khoảng lỗi khác

Cần từ chối hoặc xử lý rõ:

- **Khoảng rỗng:** `[01/07, 01/07)` không có ngày nào.
- **Bắt đầu sau kết thúc:** `[01/10, 01/07)`; công cụ tạo range có thể trả lỗi hoặc khoảng không có nghĩa, không nên chấp nhận như phiên bản hợp lệ.
- **Không biết ngày bắt đầu:** không tự gán một ngày rất xa trong quá khứ nếu dữ liệu cũ thiếu bằng chứng.
- **Sai độ phân giải:** biểu diễn một quyền hiệu lực theo phút bằng `date` khiến mất thông tin.
- **Sai múi giờ:** ngày hiệu lực địa phương bị chuyển thành ngày khác khi tính toán UTC mà không có quy tắc chung.

## 10. Ràng buộc và giao dịch trong môi trường nhiều người cập nhật

Một bảng lịch sử đẹp về cấu trúc chưa đủ nếu hai yêu cầu đồng thời có thể thay đổi lịch giá của cùng một gói.

Giả sử nhân viên A lên kế hoạch tăng giá từ 01/12, còn nhân viên B đồng thời thêm chiến dịch giảm giá từ 15/11 đến 15/12. Cả hai đọc cùng timeline lúc đầu và tính khoảng mới từ dữ liệu cũ. Nếu không kiểm soát, một giao dịch có thể mất thay đổi của giao dịch kia, hoặc một transaction thất bại vì tạo overlap.

### 10.1. Các lớp bảo vệ cần phối hợp

- **Ràng buộc database:** `EXCLUDE` chống những khoảng giao nhau không hợp lệ ngay cả khi một đường ghi bỏ qua lớp ứng dụng.
- **Transaction:** đóng phiên bản cũ và tạo các phiên bản mới thành một đơn vị nguyên tử.
- **Khóa theo thực thể:** khóa hàng gốc `service_plan` hoặc tài nguyên đại diện cho `plan_id + currency_code` trong thời gian tính toán. Nếu một gói có nhiều tiền tệ cập nhật độc lập, chọn phạm vi khóa tương ứng để tránh chặn nhau không cần thiết.
- **Kiểm soát phiên bản lạc quan:** dùng revision của lịch giá để từ chối lệnh xây dựng từ một timeline đã cũ.
- **Idempotency:** cùng một quyết định được gửi lại do retry không được tạo thêm phiên bản trùng hoặc lặp vô hạn thao tác chia khoảng.
- **Lỗi rõ ràng:** khi thao tác không cập nhật đúng số hàng dự kiến, phải rollback và đọc lại; không cố chèn bản mới dựa trên giả định cũ.

Ràng buộc loại trừ giúp bảo vệ bất biến dữ liệu, nhưng không quyết định **quyết định nào được ưu tiên** nếu hai yêu cầu cạnh tranh. Thứ tự phê duyệt, quyền sửa hồi tố và giải quyết tranh chấp là quy tắc nghiệp vụ phải được định nghĩa riêng.

### 10.2. Dữ liệu đến muộn và thứ tự bản ghi

Dịch vụ giá có thể ghi trước mức phí tháng 12 vào tháng 8, rồi tháng 9 nhận một quyết định có hiệu lực tháng 7. Không thể dùng `MAX(version_id)` hoặc `ORDER BY recorded_at DESC` để chọn “giá hiện tại”.

Cần phân biệt rõ:

- **Thứ tự ghi vào hệ thống:** phiên bản nào được nhập trước.
- **Thứ tự hiệu lực:** khoảng nào nằm trước trong dòng thời gian nghiệp vụ.
- **Thứ tự ưu tiên quyết định:** trong trường hợp xung đột, quyết định nào đã được phê duyệt và có thẩm quyền.

Dữ liệu đến muộn không nhất thiết sai, nhưng nó phải đi qua quy trình xem xét lại các khoảng bị ảnh hưởng và các giao dịch đã chốt.

## 11. Chỉ mục và truy vấn ở quy mô lớn

Bảng phiên bản có thể tăng rất nhanh khi một thực thể đổi nhiều lần, nhất là nếu lưu giá theo nhiều khu vực, loại tiền tệ hoặc nhóm khách hàng.

### 11.1. Tối ưu theo mẫu truy vấn

| Mẫu truy vấn | Cột/kiểu lọc chính | Hướng tối ưu |
|---|---|---|
| Giá của gói X tại ngày D | `plan_id`, `currency_code`, `valid_period @> D` | Chỉ mục theo khóa và range; đo kế hoạch thực thi |
| Timeline giá của gói X | `plan_id`, `currency_code`, sắp xếp ngày bắt đầu | B-tree theo `lower(valid_period)` nếu có lợi |
| Các giá giao tháng M trên nhiều gói | `valid_period && kỳ_tháng` | Range index; cân nhắc điều kiện lọc khác |
| Báo cáo lịch sử trên hàng triệu phiên bản | Nhiều gói, nhiều ngày, phép kết hợp với hóa đơn | Partitioning/kho phân tích tùy workload |
| Giá đang có hiệu lực hôm nay cho mọi gói | `valid_period @> ngày_hôm_nay` | Projection hoặc bảng hiện tại được đồng bộ, nếu đo thấy cần thiết |

Chỉ mục GiST do ràng buộc `EXCLUDE` tạo ra có thể giúp các truy vấn trên range, nhưng lợi ích thực tế phụ thuộc độ chọn lọc và phân bố dữ liệu. Không lập chỉ mục mọi cột để “phòng hờ”: mỗi chỉ mục làm tăng chi phí ghi, cập nhật và lưu trữ.

### 11.2. Khi cần bảng hiện tại hoặc cache

Nếu trang danh mục thường xuyên hiển thị hàng triệu giá đang áp dụng, có thể duy trì một bảng/projection `current_price` để đọc nhanh. Khi đó phải chỉ rõ bảng nào là **nguồn sự thật**; các lần chuyển hiệu lực theo lịch, điều chỉnh hồi tố và giao dịch đồng thời phải cập nhật projection đúng quy tắc.

Một quy trình đối soát có thể lấy giá theo truy vấn `valid_period @> ngày_nghiệp_vụ` từ bảng phiên bản, rồi so sánh với giá trong projection. Không gán “hiện tại” đơn thuần là bản có ngày bắt đầu lớn nhất, vì có thể tồn tại bản bắt đầu trong tương lai.

### 11.3. Phân vùng và lưu giữ

Partitioning có thể hữu ích khi bảng có nhiều triệu phiên bản, nhưng phạm vi chia phải phù hợp truy vấn và cách bảo vệ ràng buộc. Nếu hai khoảng của cùng một gói nằm ở hai phân vùng khác nhau, ràng buộc chống chồng lấn **không tự động có hiệu lực xuyên mọi phân vùng** trên mọi phiên bản/cấu hình PostgreSQL. Cần kiểm chứng phương án cụ thể hoặc bảo vệ overlap theo khóa nghiệp vụ bằng một cơ chế toàn cục thích hợp.

Retention cần cân bằng khả năng tra cứu lịch sử, nghĩa vụ kiểm toán, dữ liệu cá nhân và chi phí lưu. Nếu xóa các phiên bản cũ, API as-of phải công bố phạm vi còn dữ liệu, tránh trả “không có phiên bản” như thể nghiệp vụ chưa từng tồn tại.

## 12. Chuyển ý tưởng sang document, graph và kho phân tích

Ngữ nghĩa **một thực thể có nhiều phiên bản, mỗi phiên bản có khoảng hiệu lực** không phụ thuộc vào hệ quản trị quan hệ.

| Mô hình | Cách lưu phiên bản | Thách thức chính |
|---|---|---|
| **Quan hệ** | Bảng phiên bản, khóa ngoại, range/biên đầu-cuối | Ràng buộc không chồng lấn, giao dịch chia khoảng, chỉ mục |
| **Document** | Nhiều document theo `entityId` với `validFrom`/`validTo` | Tránh lịch sử nhúng tăng vô hạn; đảm bảo cập nhật nhiều document nhất quán |
| **Graph** | Phiên bản của node hoặc edge với khoảng hiệu lực | Truy vấn quan hệ tại D phải lọc cả đỉnh lẫn cạnh theo D |
| **Kho phân tích** | Dimension **SCD Type 2**, khóa thay thế và khoảng hiệu lực | Join fact theo thời điểm, late-arriving data, lịch sử tải dữ liệu |
| **Event store** | Chuỗi quyết định/sự kiện và projection phiên bản hiệu lực | Tái dựng đúng quy tắc khi sự kiện đến muộn, thay đổi hồi tố, replay |

Ví dụ một document phiên bản giá:

~~~json
{
  "versionId": "price-7-2026-07",
  "planId": 7,
  "currencyCode": "VND",
  "monthlyFee": 120000,
  "validFrom": "2026-07-01",
  "validTo": "2026-10-01",
  "sourceDecisionId": "PRICING-2026-Q3"
}
~~~

Mốc `validTo` vẫn là **biên loại trừ**, dù biểu diễn bằng chuỗi ngày thay vì kiểu range. Nhiều document có thể có cùng `planId`; phải xác định cơ chế chống overlap dưới ghi đồng thời. Chỉ tạo unique index trên `validFrom` chưa giải quyết vấn đề.

Với **graph**, nếu nhân viên thuộc nhóm A `[01/01, 01/04)` rồi thuộc nhóm B `[01/04, +∞)`, các **cạnh thành viên** phải mang khoảng hiệu lực. Chỉ phiên bản hóa thuộc tính của node nhân viên không đủ để trả lời “ngày 15/03 nhân viên thuộc nhóm nào?”.

Với **SCD Type 2**, mỗi hàng dimension lưu một phiên bản giá trị và khoảng hiệu lực, thường kèm surrogate key. Khi JOIN dữ liệu giao dịch, cần quyết định có dùng **khóa phiên bản đã được chốt tại thời điểm nghiệp vụ** hay thực hiện temporal join theo ngày. Nếu fact đã phát hành bị ảnh hưởng bởi chỉnh sửa hồi tố của dimension, phải bảo vệ dữ liệu gốc và thực hiện nghiệp vụ điều chỉnh rõ ràng.

## 13. Bộ kiểm thử bắt buộc cho bản ghi theo khoảng hiệu lực

Dùng các phiên bản P1, P2, P3 ở phần 1 làm dữ liệu chuẩn. Bảng dưới kiểm thử việc chọn phiên bản:

| Trường hợp | Dữ liệu cần hỏi | Kết quả mong đợi |
|---|---|---|
| Trước ngày hiệu lực đầu tiên | 31/12/2025 | Không có phiên bản |
| Đúng biên bắt đầu P1 | 01/01/2026 | P1, 100.000 |
| Ngay trước biên kết thúc P1 | 30/06/2026 | P1, 100.000 |
| Đúng biên chuyển P1 → P2 | 01/07/2026 | P2, 120.000 |
| Ngay trước biên chuyển P2 → P3 | 30/09/2026 | P2, 120.000 |
| Đúng biên chuyển P2 → P3 | 01/10/2026 | P3, 130.000 |
| Sau P3 với biên trên vô hạn | 15/12/2026 | P3, 130.000 nếu chưa lên lịch phiên bản mới |
| Khoảng kỳ qua hai phiên bản | 15/06–trước 15/07 | Giao P1 và P2 |
| Thử chèn khoảng trùng | 01/09–trước 01/11 | Database phải từ chối cùng gói/tiền tệ |
| Hai khoảng liền kề | P1 kết thúc 01/07, P2 bắt đầu 01/07 | Không bị coi là chồng lấn |

Các kiểm thử sau phản ánh lỗi vận hành khó thấy hơn:

1. **Ghi tương lai:** thêm P4 bắt đầu 01/12, xác minh ngày 30/11 vẫn trả P3 và ngày 01/12 trả P4.
2. **Chia khoảng:** chèn giá điều chỉnh cho tháng 8, xác minh tháng 7, 8, 9 trả đúng; không mất phần đầu/cuối của khoảng cũ.
3. **Rollback:** cố ý khiến INSERT bản mới thất bại, xác minh phần UPDATE đóng khoảng cũ cũng bị rollback.
4. **Ghi đồng thời:** hai phiên chỉnh cùng một gói không thể cùng commit các khoảng chồng lấn; ứng dụng phản hồi hoặc retry đúng theo quy tắc.
5. **Idempotency:** gửi lại cùng quyết định giá không tạo thêm phiên bản trùng hoặc chia khoảng lần hai.
6. **Khoảng trống:** kiểm tra nghiệp vụ cho phép hoặc từ chối ngày không có giá, thay vì tự suy diễn mức giá.
7. **Thời gian và timezone:** với timestamp, kiểm thử chuyển ngày và múi giờ; với date, kiểm tra đúng ngày địa phương.
8. **Dữ liệu đã chốt:** sửa lịch giá hiệu lực trong quá khứ không làm thay đổi ngầm số tiền của hóa đơn cũ.
9. **Nguồn quyết định:** từng hàng có thể truy được quyết định có thẩm quyền; không sinh phiên bản không có căn cứ.

**Kiểm thử ranh giới** đặc biệt quan trọng: nếu sai điều kiện `<=`/`<` ở biên, hệ thống dễ chọn nhầm giá đúng ngày tăng phí dù tất cả truy vấn ở giữa kỳ đều thành công.

## 14. Bài thực hành: mô hình hóa phân công nhân sự theo giai đoạn

Một doanh nghiệp yêu cầu:

> “Chúng tôi cần tra nhân viên thuộc bộ phận nào ở mỗi ngày, được phép lập kế hoạch chuyển bộ phận trong tương lai, và không được có hai bộ phận chính cùng hiệu lực cho một nhân viên.”

Hãy chuyển yêu cầu này thành thiết kế:

1. Xác định **employee** là thực thể ổn định, còn **department_assignment_version** là quan hệ có phiên bản. Mỗi phiên bản mang `employee_id`, `department_id`, `valid_period`, `decision_ref`.
2. Mô tả bất biến: với cùng `employee_id`, các khoảng phân công **bộ phận chính** không được chồng lấn; nếu có kiêm nhiệm, cần bổ sung `assignment_type` và quy tắc riêng.
3. Biểu diễn: nhân viên 42 ở phòng A từ 01/01 đến trước 01/04, sau đó ở phòng B từ 01/04 trở đi.
4. Viết truy vấn as-of cho 31/03 và 01/04; kết quả lần lượt phải là A và B.
5. Mô tả giao dịch nếu kế hoạch chuyển sang phòng C từ 01/06: đóng khoảng B tại 01/06 rồi thêm C từ 01/06.
6. Xác định có cho khoảng trống giữa hai phân công không. Nếu nhân viên nghỉ không lương nhưng vẫn thuộc phòng A, “trạng thái làm việc” và “phòng ban” nên là hai thuộc tính/quan hệ khác nhau thay vì dùng gap với nghĩa mơ hồ.
7. Nếu cần trả lời “tháng 3 hệ thống từng nghĩ nhân viên sẽ vào phòng nào trong tháng 6”, nêu vì sao phải bổ sung lịch sử ghi nhận hoặc bitemporal.

Bài thực hành nhấn mạnh rằng kỹ thuật **phiên bản theo khoảng** có thể áp dụng cho thuộc tính của thực thể (giá) và **quan hệ giữa các thực thể** (phân công nhân viên – phòng ban). Tùy mô hình quan hệ hay đồ thị, nơi lưu khoảng có thể khác nhau, nhưng điều kiện “một giá trị đúng tại thời điểm D” vẫn phải nhất quán.

## 15. Checklist trước khi phê duyệt thiết kế

- **Khóa:** thực thể logic, khóa phiên bản và phạm vi nghiệp vụ chống trùng đã tách bạch chưa?
- **Thời gian:** chọn `date` hay timestamp, quy ước `[from, to)`, múi giờ và biên chưa kết thúc đã thống nhất chưa?
- **Toàn vẹn:** có ngăn khoảng rỗng, khoảng chồng lấn và kiểm tra gap khi nghiệp vụ yêu cầu không?
- **Truy vấn:** as-of một ngày, timeline, tìm giao kỳ và xử lý ngày không có phiên bản đã rõ chưa?
- **Ghi dữ liệu:** thêm phiên bản tương lai, sửa hồi tố, chia khoảng, rollback và ghi đồng thời đã được định nghĩa chưa?
- **Chứng cứ:** bản ghi có nguồn quyết định; dữ liệu giao dịch đã chốt có lưu giá/giá trị thực áp dụng không?
- **Lịch sử hệ thống:** nếu cần biết điều gì từng được hệ thống ghi nhận, mô hình có thêm recorded time hoặc event history đủ để tái dựng chưa?
- **Hiệu năng và tiến hóa:** chỉ mục, phân vùng, vòng đời dữ liệu và quy tắc nâng cấp schema đã được kiểm tra bằng truy vấn thực tế chưa?

Một bản ghi theo phiên bản chỉ thực sự có ích khi **khoảng hiệu lực của nó rõ nghĩa và được bảo vệ bằng ràng buộc có thể kiểm chứng**. Hãy bắt đầu từ câu hỏi nghiệp vụ “giá trị nào đúng vào ngày D?”, sau đó thiết kế thực thể, phiên bản, khoảng nửa mở, khóa và transaction. Khi yêu cầu tiến tới “hệ thống đã biết điều gì vào thời điểm K?”, bổ sung trục lịch sử ghi nhận tương ứng, thay vì để một cột `updated_at` gánh cả hai vai trò.

# Biên đóng, biên mở và quy tắc ngăn khoảng hiệu lực chồng lấp

## 1. Khi hai phiên bản cùng chạm một mốc thời gian, giá trị nào đúng?

Trong module **DATABASE_DATA_MODELING**, một phần quan trọng của việc chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu là xác định **khi nào** một quan hệ hoặc giá trị có hiệu lực. Chương **Thời gian và lịch sử** đặt ra câu hỏi không thể giải quyết chỉ bằng khóa chính và cột ngày cập nhật: nếu hai phiên bản liên tiếp cùng có mốc chuyển đổi là ngày 01/07, phiên bản nào được phép áp dụng vào chính ngày 01/07?

Xét một dịch vụ có bảng giá:

| Phiên bản | Giá | Diễn giải nghiệp vụ |
|---|---:|---|
| A | 100.000 VND | Từ 01/01 đến hết tháng 6 |
| B | 120.000 VND | Bắt đầu từ 01/07 |
| C | 125.000 VND | Dự kiến áp dụng từ 15/07 |

Nếu dùng các điều kiện không nhất quán như **valid_from <= ngay_truy_van <= valid_to**, ngày 01/07 có thể khớp cả A và B. Nếu bỏ qua ngày bắt đầu hoặc ngày kết thúc trong một nhánh khác, hệ thống lại có thể không tìm thấy phiên bản nào. Cả hai lỗi đều nghiêm trọng khi dữ liệu dùng để xác định giá, hợp đồng, quyền truy cập, phân công hoặc trạng thái hiệu lực.

Bài học này giải quyết ba câu hỏi:

1. **Biên đóng và biên mở nghĩa là gì?** Vì sao quy ước khoảng nửa mở **[from, to)** thường giúp loại bỏ tranh chấp ở mốc chuyển tiếp?
2. **Hai khoảng thế nào là chồng lấp?** Làm sao phân biệt chồng lấp với chỉ tiếp giáp, khoảng trống, bao chứa và khoảng không giới hạn?
3. **Làm sao biến quy tắc thành ràng buộc dữ liệu?** Cách sử dụng khóa nghiệp vụ, kiểu range, exclusion constraint, giao dịch và kiểm thử để chống dữ liệu mâu thuẫn ngay cả khi có ghi đồng thời.

Mục tiêu là có thể đọc một yêu cầu như **“một gói dịch vụ chỉ có một mức giá VND có hiệu lực tại mỗi ngày”**, thiết kế được lược đồ phù hợp và chứng minh lược đồ giữ bất biến đó. Các nguyên tắc cũng áp dụng khi chuyển từ cơ sở dữ liệu quan hệ sang document, graph hoặc kho phân tích, dù cơ chế kỹ thuật khác nhau.

## 2. Mô hình toán học đơn giản của khoảng thời gian

Cho hai mốc thời gian **a** và **b**, với **a < b**. Một khoảng có thể bao gồm hoặc loại trừ từng biên:

| Ký hiệu | Có chứa a? | Có chứa b? | Đọc thành lời |
|---|---|---|---|
| **[a, b]** | Có | Có | Đóng cả hai đầu |
| **[a, b)** | Có | Không | Đóng trái, mở phải |
| **(a, b]** | Không | Có | Mở trái, đóng phải |
| **(a, b)** | Không | Không | Mở cả hai đầu |

Ví dụ với giờ làm việc:

~~~text
A = [09:00, 10:00)
B = [10:00, 11:00)

09:00 thuộc A.
09:59:59 thuộc A.
10:00 không thuộc A nhưng thuộc B.
11:00 không thuộc B.
~~~

Hai khoảng **A** và **B** chỉ tiếp giáp tại mốc 10:00, nhưng **không cùng chứa mốc 10:00**. Vì thế một tài nguyên có thể được gán cho A đến trước 10:00 và cho B từ đúng 10:00 mà không có thời điểm bị gán hai lần.

Ngược lại, nếu A là **[09:00, 10:00]** và B là **[10:00, 11:00]**, cả hai đều chứa 10:00, nên có một điểm chồng lấp. Khác biệt chỉ ở dấu ngoặc nhưng thay đổi hoàn toàn kết quả truy vấn và ràng buộc.

### 2.1. Khoảng và điểm thời gian không phải một

**Khoảng** biểu diễn hiệu lực kéo dài. **Điểm thời gian** biểu diễn một sự kiện hay một mốc duy nhất.

- “Khách hàng thuộc nhóm VIP từ ngày 01/03 đến trước 01/06”: dùng khoảng.
- “Khách hàng gửi yêu cầu lúc 09:20:13”: dùng thời điểm sự kiện.
- “Phiếu thanh toán được ghi nhận lúc 09:20:15”: là một thời điểm ghi nhận, không tự biểu diễn khoảng quyền lợi.
- “Quyền VIP bị dừng lúc 01/06 00:00”: là mốc **kết thúc khoảng**, không có nghĩa quyền vẫn còn tại đúng thời điểm ấy.

Dữ liệu thực tế có thể cần cả thời điểm sự kiện và khoảng hiệu lực. Không nên thay thế chúng cho nhau vì tên cột nghe gần giống.

### 2.2. Khoảng rỗng và khoảng không hợp lệ

Với khoảng nửa mở **[a, a)**, không tồn tại điểm nào vừa lớn hơn hoặc bằng a vừa nhỏ hơn a. Đây là **khoảng rỗng**. Nó không phải một khoảng “có hiệu lực trong tích tắc”.

Nếu yêu cầu ghi sự kiện đúng tại a, hãy lưu một event tại a. Nếu yêu cầu lưu một phiên bản có hiệu lực trong khoảng thời gian, phải chọn mốc kết thúc **sau** mốc bắt đầu, hoặc có biên trên chưa xác định.

Một giá trị như **[20/07, 10/07)** còn có thứ tự biên sai: bắt đầu sau kết thúc. API không được coi đây là một giai đoạn hợp lệ và âm thầm đảo hai mốc.

## 3. Vì sao nên dùng quy ước [from, to)?

Một quy ước được dùng rộng rãi cho thời gian hiệu lực là:

~~~text
[valid_from, valid_to)

Điều kiện để thời điểm t nằm trong khoảng:
valid_from <= t AND t < valid_to
~~~

Điểm mạnh của cách biểu diễn này là **kết thúc của phiên bản trước có thể bằng bắt đầu của phiên bản sau**. Không cần tạo “khoảng đệm”, trừ đi một giây hoặc một microsecond để tránh trùng mốc.

### 3.1. Dòng thời gian của bảng giá

~~~text
          01/01                 01/07               01/10
            |                     |                   |
  [--------- A -------------------)
                                  [-------- B --------)
                                                      [--- C --->

A: [2026-01-01, 2026-07-01) = 100.000 VND
B: [2026-07-01, 2026-10-01) = 120.000 VND
C: [2026-10-01, không giới hạn) = 130.000 VND
~~~

| Ngày được hỏi | Phiên bản đúng | Vì sao |
|---|---|---|
| 31/12/2025 | Không có | Trước điểm bắt đầu của A |
| 01/01/2026 | A | Biên trái của A được bao gồm |
| 30/06/2026 | A | Vẫn trước biên phải 01/07 |
| 01/07/2026 | B | A loại trừ biên phải, B bao gồm biên trái |
| 30/09/2026 | B | Vẫn trước biên phải 01/10 |
| 01/10/2026 | C | B đã hết, C bắt đầu |
| 15/11/2026 | C | C chưa có mốc kết thúc |

Khi thiết kế bằng hai cột **valid_from** và **valid_to**, điều kiện tra cứu thường là:

~~~sql
SELECT monthly_fee
FROM plan_price_version_columns
WHERE plan_id = 7
  AND currency_code = 'VND'
  AND valid_from <= DATE '2026-07-01'
  AND (
      valid_to IS NULL
      OR DATE '2026-07-01' < valid_to
  );
~~~

**plan_price_version_columns** là tên bảng minh họa cho mô hình hai cột, không phải bảng sẽ tạo trong ví dụ PostgreSQL dùng kiểu range ở phần 7.

### 3.2. Vì sao cách “đến 23:59:59” dễ sai?

Giả sử giá A áp dụng “đến hết ngày 30/06”. Một cách làm thiếu an toàn là lưu **30/06 23:59:59** làm mốc kết thúc. Nhưng nếu hệ thống hỗ trợ mili giây hay microsecond, có nhiều thời điểm sau 23:59:59 và trước 01/07 00:00 vẫn không thuộc khoảng A. Khi đổi độ chính xác đồng hồ, mã nguồn dễ phát sinh khoảng trống.

Với mô hình theo ngày, hãy lưu **valid_to = 01/07** và dùng phép so sánh **t < valid_to**. Với mô hình theo timestamp, cũng sử dụng mốc đầu của phiên bản kế tiếp làm biên phải loại trừ. Cách làm này không phụ thuộc vào “đơn vị thời gian nhỏ nhất” của mỗi hệ thống.

### 3.3. [from, to) là quy ước, không phải định luật bắt buộc

Một số nghiệp vụ được mô tả bằng khoảng **đóng cả hai đầu**; ví dụ “khách được ở phòng từ 01 đến hết 03/07” theo **ngày trọn vẹn**. Có thể chuyển về dạng nửa mở **[01/07, 04/07)**, với điều kiện ngày 04/07 được hiểu là **không còn hiệu lực**.

Nhưng quy đổi này chỉ đúng khi đã biết độ phân giải là **ngày lịch**. Không tự thêm một ngày để chuyển dấu ngoặc cho khoảng timestamp liên tục hoặc khi mốc kết thúc không rõ nghĩa. Phải thống nhất nghiệp vụ trước khi chuẩn hóa dữ liệu.

## 4. Ngăn chồng lấp: định nghĩa chính xác điều đang cấm

Hai khoảng **chồng lấp** nếu chúng chia sẻ **ít nhất một thời điểm thuộc cả hai khoảng**. Với các khoảng **không rỗng, nửa mở, biên hữu hạn**:

~~~text
A = [a_start, a_end)
B = [b_start, b_end)

A và B chồng lấp khi:
a_start < b_end AND b_start < a_end

A kết thúc đúng lúc B bắt đầu:
a_end = b_start  =>  không chồng lấp
~~~

Điều kiện trên dùng **dấu nhỏ hơn nghiêm ngặt (<)**, không phải **<=**. Nếu dùng **<=**, hai khoảng chỉ chạm nhau ở biên cũng bị xem là chồng lấp dù cùng áp dụng quy ước nửa mở.

### 4.1. Các quan hệ cần phân biệt

| Khoảng A | Khoảng B | Quan hệ | Có chồng lấp? |
|---|---|---|---|
| [01/01, 01/03) | [01/03, 01/06) | Tiếp giáp | Không |
| [01/01, 01/04) | [01/03, 01/06) | Giao một phần | Có |
| [01/01, 01/07) | [01/03, 01/05) | A chứa B | Có |
| [01/03, 01/05) | [01/01, 01/07) | A nằm trong B | Có |
| [01/01, 01/03) | [01/05, 01/07) | Có khoảng trống | Không |
| [01/01, 01/05) | [01/01, 01/05) | Trùng hoàn toàn | Có |
| [01/01, vô hạn) | [01/07, 01/08) | A chứa B | Có |

Một lỗi phổ biến là chỉ kiểm tra **“ngày bắt đầu của B có nằm trong A không?”**. Cách này có thể bỏ sót trường hợp **B bắt đầu trước A nhưng kết thúc sau A**, tức B bao trọn A. Muốn phát hiện mọi dạng chồng lấp, phải dùng điều kiện giao khoảng tổng quát hoặc toán tử range được hệ quản trị hỗ trợ.

### 4.2. “Không chồng lấp” phải gắn với khóa nghiệp vụ

Giả sử một hệ thống có mức giá theo **gói** và **loại tiền tệ**. Hai giá VND và USD có thể cùng hiệu lực từ 01/07; đó không phải xung đột nếu chúng thuộc hai phạm vi giá khác nhau.

Bất biến cần viết rõ:

> Với một cặp **(plan_id, currency_code)**, tại mỗi ngày nghiệp vụ không được tồn tại hơn một phiên bản giá có hiệu lực.

Về mặt logic:

~~~text
Với hai hàng A, B bất kỳ:
Nếu A.plan_id = B.plan_id
   và A.currency_code = B.currency_code
   và A.id khác B.id
thì A.valid_period và B.valid_period phải KHÔNG giao nhau.
~~~

Nếu còn phân biệt **khu vực** hoặc **nhóm khách hàng**, khóa nghiệp vụ cần xét thêm những chiều ấy. Nếu cùng một thực thể có nhiều loại quan hệ hợp lệ đồng thời, không được áp một quy tắc một phiên bản cho tất cả.

Ngược lại, **khóa chính riêng trên version_id không ngăn được chồng lấp**: hai bản ghi khác ID vẫn có thể nói rằng cùng một gói có hai mức giá vào ngày 01/07.

## 5. Biên thời gian: ngày lịch, thời điểm và múi giờ

Một khoảng có hai biên đúng về mặt toán học vẫn có thể sai nghiệp vụ nếu kiểu dữ liệu không phù hợp.

### 5.1. Thời gian theo ngày — date

Dùng ngày khi yêu cầu nói “giá áp dụng từ ngày 01/07 theo lịch nghiệp vụ”, “hợp đồng có hiệu lực từ đầu tháng” hoặc “thành viên được hưởng quyền lợi trong một số ngày”.

~~~text
[2026-07-01, 2026-08-01)
= toàn bộ các ngày từ 01/07 đến 31/07.
~~~

Các mốc là **ngày**, không phải timestamp 00:00 UTC. Nếu lịch nghiệp vụ được tính theo ngày Việt Nam, việc chuyển ngày đó thành một timestamp phải dùng timezone đã thống nhất; không âm thầm dùng múi giờ của máy chủ.

### 5.2. Thời gian theo thời điểm — timestamp with time zone

Nếu yêu cầu chính xác theo phút hoặc giây, ví dụ “phòng họp được đặt từ 09:00 đến 10:00”, dùng timestamp với ngữ nghĩa thời điểm tuyệt đối. PostgreSQL hỗ trợ **timestamptz** và **tstzrange**.

~~~sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-11-22 09:00:00+07',
    TIMESTAMPTZ '2026-11-22 10:00:00+07',
    '[)'
) AS reservation_period;
~~~

Mốc **09:00+07** và **02:00+00** là cùng một thời điểm tuyệt đối. Hiển thị theo múi giờ có thể khác nhau, nhưng phép giao khoảng phải so sánh trên cùng trục thời gian.

Nếu nghiệp vụ đặt lịch theo **giờ địa phương lặp lại vào những ngày cụ thể**, cần lưu thêm quy tắc múi giờ. Tại nơi có chuyển giờ mùa hè (DST), một giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần; việc tạo timestamp phải xử lý rõ trường hợp mơ hồ. Chỉ lưu chuỗi “01:30” không đủ định danh một thời điểm tuyệt đối.

### 5.3. Không trộn date và timestamp bằng quy tắc ngầm

Ví dụ “giá VND áp dụng từ 01/07” và “giao dịch xảy ra lúc 00:30+07 ngày 01/07” cần ánh xạ **ngày nghiệp vụ theo timezone đã định** trước khi chọn phiên bản giá. Nếu ứng dụng chuyển 00:30+07 sang UTC rồi lấy ngày UTC là 30/06, phép JOIN theo ngày UTC có thể dùng giá cũ một cách sai lầm.

Một quy tắc rõ ràng có thể là:

~~~text
business_date =
    ngày lịch của thời điểm giao dịch
    trong timezone của thị trường áp dụng giá
~~~

Sau khi xác định **business_date**, mới truy vấn khoảng **daterange**.

## 6. Biên vô hạn, NULL và các trạng thái chưa xác định

Nhiều lịch sử phiên bản có một bản ghi hiện còn hiệu lực mà **chưa biết ngày kết thúc**. Có hai cách thường gặp:

- Hai cột **valid_from**, **valid_to**, với quy ước **valid_to IS NULL** nghĩa là chưa xác định biên kết thúc.
- Một cột kiểu range, chẳng hạn **daterange**, có **biên trên không giới hạn**.

Ví dụ:

~~~sql
SELECT daterange(
    DATE '2026-10-01',
    NULL,
    '[)'
) AS open_ended_period;
~~~

Đây là một **giá trị daterange không NULL**, có biên trên không giới hạn. Cần phân biệt với việc đặt cả cột **valid_period = NULL**, vì một cột range NULL làm mất hoàn toàn thông tin về khoảng.

Với PostgreSQL, có thể kiểm tra:

~~~sql
SELECT
    lower(daterange(DATE '2026-10-01', NULL, '[)')) AS begins_on,
    upper_inf(daterange(DATE '2026-10-01', NULL, '[)')) AS no_upper_bound;
-- begins_on = 2026-10-01; no_upper_bound = true
~~~

**Không giới hạn biên** và **giá trị thời gian đặc biệt infinity** là hai khái niệm khác nhau trong PostgreSQL. Biên range *unbounded* không đồng nghĩa với một đầu mút hữu hạn được đặt bằng một giá trị “rất xa trong tương lai”, cũng không nhất thiết giống việc dùng giá trị timestamp/date đặc biệt **infinity**.

Đối với API hoặc dữ liệu chuyển từ hệ thống khác, phải thống nhất rõ cách biểu diễn “chưa kết thúc”; đừng cho phép cả NULL, 9999-12-31, infinity và chuỗi rỗng mang cùng nghĩa mà không có quy tắc chuẩn hóa.

### 6.1. Không biết lúc bắt đầu thì sao?

Nếu một hồ sơ cũ chỉ nói “áp dụng từ khoảng cuối quý II”, không tự tạo một ngày chính xác để thỏa mãn NOT NULL. Có thể cần trường **date_precision**, **source_confidence** hoặc vùng thời gian không chắc chắn, và một quy trình xác minh trước khi xem phiên bản là có hiệu lực chính thức.

Khoảng vô hạn một bên không dùng để che giấu sự thiếu thông tin. **“Có hiệu lực từ trước khi hệ thống ra đời”** và **“không biết ngày bắt đầu”** là hai phát biểu nghiệp vụ khác nhau.

## 7. Chuyển quy tắc thành ràng buộc PostgreSQL

PostgreSQL có kiểu range và toán tử giao khoảng, giúp định nghĩa bất biến không chồng lấp trực tiếp tại database. Ví dụ sau giả định **mỗi gói và loại tiền tệ có tối đa một mức giá đang có hiệu lực cho cùng một ngày**.

### 7.1. Lược đồ có phạm vi giá rõ ràng

Ta tạo một thực thể **price_scope** để định danh duy nhất tổ hợp gói và tiền tệ. Mỗi khoảng hiệu lực của mức giá tham chiếu tới phạm vi đó.

~~~sql
-- Cung cấp so sánh = cho bigint trong chỉ mục GiST của EXCLUDE.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE price_scope (
    scope_id      bigint PRIMARY KEY,
    plan_id       bigint NOT NULL,
    currency_code text NOT NULL
                  CHECK (currency_code ~ '^[A-Z]{3}$'),
    UNIQUE (plan_id, currency_code)
);

CREATE TABLE plan_price_period (
    period_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scope_id       bigint NOT NULL REFERENCES price_scope(scope_id),
    monthly_fee    numeric(14, 2) NOT NULL CHECK (monthly_fee >= 0),
    valid_period   daterange NOT NULL,
    decision_ref   text NOT NULL,
    recorded_at    timestamptz NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT ck_price_period_bounds
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    CONSTRAINT ex_one_price_at_a_time
        EXCLUDE USING gist (
            scope_id WITH =,
            valid_period WITH &&
        )
);
~~~

Các ràng buộc có trách nhiệm khác nhau:

| Cơ chế | Điều bảo vệ |
|---|---|
| **PRIMARY KEY(period_id)** | Mỗi bản ghi phiên bản có ID riêng |
| **FOREIGN KEY(scope_id)** | Phiên bản thuộc một phạm vi giá tồn tại |
| **UNIQUE(plan_id, currency_code)** | Không có hai định danh phạm vi cho cùng gói và loại tiền |
| **NOT NULL** trên scope và period | Tránh giá trị NULL khiến kiểm tra giao khoảng không xác định |
| **CHECK NOT isempty(valid_period)** | Không chấp nhận khoảng rỗng |
| **CHECK lower_inc và NOT upper_inc** | Bảo đảm cách diễn giải biên là **[from, to)** |
| **CHECK NOT lower_inf** | Mỗi phiên bản phải có ngày bắt đầu cụ thể |
| **EXCLUDE USING gist** | Với cùng scope, hai khoảng hiệu lực không được giao nhau |

Trong PostgreSQL, **daterange** là kiểu range rời rạc được chuẩn hóa về dạng thích hợp (thường **[)**); điều kiện biên vẫn được ghi rõ để nêu bất biến thiết kế. Với các kiểu range khác hoặc khi port sang hệ quản trị khác, không được giả định cùng quy tắc chuẩn hóa.

**CREATE EXTENSION** yêu cầu quyền và chính sách triển khai phù hợp; trong hệ thống thực tế, thao tác ấy thuộc migration do đội vận hành database quản lý.

### 7.2. Dữ liệu mẫu và kiểm tra biên

~~~sql
INSERT INTO price_scope (scope_id, plan_id, currency_code)
VALUES (17, 7, 'VND');

INSERT INTO plan_price_period (
    scope_id, monthly_fee, valid_period, decision_ref
)
VALUES
(
    17, 100000,
    daterange(DATE '2026-01-01', DATE '2026-07-01', '[)'),
    'PRICE-2026-H1'
),
(
    17, 120000,
    daterange(DATE '2026-07-01', DATE '2026-10-01', '[)'),
    'PRICE-2026-Q3'
),
(
    17, 130000,
    daterange(DATE '2026-10-01', NULL, '[)'),
    'PRICE-2026-Q4'
);
~~~

Kiểm tra giá đúng vào ngày chuyển đổi:

~~~sql
SELECT monthly_fee
FROM plan_price_period
WHERE scope_id = 17
  AND valid_period @> DATE '2026-07-01';
-- 120000.00, đúng một hàng
~~~

Toán tử **@>** có nghĩa là khoảng phía trái **chứa** ngày phía phải. PostgreSQL hiểu chính xác biên đã được định nghĩa; không cần tự viết điều kiện **>=** và **<** trong mọi truy vấn.

Kiểm tra cấm chồng lấp:

~~~sql
INSERT INTO plan_price_period (
    scope_id, monthly_fee, valid_period, decision_ref
)
VALUES (
    17, 125000,
    daterange(DATE '2026-09-15', DATE '2026-10-15', '[)'),
    'BAD-OVERLAPPING-DECISION'
);
-- Bị từ chối vì khoảng giao với các phiên bản đang có.
~~~

Ở môi trường ứng dụng, lỗi constraint phải được bắt và chuyển thành thông báo xung đột hoặc cơ chế retry hợp lý. Không được bỏ qua lỗi rồi trả về “đã lưu thành công”.

### 7.3. Chỉ kiểm tra trùng ngày bắt đầu là chưa đủ

Nếu dùng:

~~~sql
UNIQUE (scope_id, valid_from)
~~~

thì hai hàng **[01/07, 01/10)** và **[15/08, 15/09)** vẫn có ngày bắt đầu khác nhau, dù chồng lấp toàn bộ tháng 9. Khóa duy nhất chỉ giải quyết **trùng một giá trị**, trong khi bài toán cần loại trừ **giao nhau giữa hai khoảng**.

Trong hệ quản trị không có native range/exclusion, có thể lưu hai cột biên và kiểm tra giao khoảng bằng transaction kết hợp khóa phù hợp. Tuy nhiên, một truy vấn **SELECT kiểm tra rồi INSERT** ở mức cô lập mặc định chưa đủ an toàn khi có hai giao dịch đồng thời; cần khóa phạm vi nghiệp vụ, Serializable phù hợp hoặc cơ chế database khác bảo đảm bất biến.

## 8. Chồng lấp, tiếp giáp và khoảng trống là ba quy tắc khác nhau

Giả sử đối với scope 17 có ba phiên bản:

~~~text
P1: [01/01, 01/07)
P2: [01/07, 01/10)
P3: [01/10, vô hạn)
~~~

**Không chồng lấp:** Không có ngày nào thuộc từ hai phiên bản trở lên.

**Tiếp giáp:** Biên phải của P1 bằng biên trái của P2; hai phiên bản có thể nối liền mà không chồng.

**Không có khoảng trống:** Trong toàn bộ thời gian dịch vụ yêu cầu có giá, luôn tồn tại ít nhất một phiên bản hợp lệ.

Ràng buộc **EXCLUDE** ở phần 7 bảo đảm **không chồng lấp**, nhưng **không bảo đảm không có khoảng trống**. Ví dụ hai khoảng **[01/01, 01/07)** và **[03/07, 01/10)** vẫn không chồng lấp, dù hai ngày 01 và 02/07 thiếu giá.

### 8.1. Khi nào khoảng trống hợp lệ?

Một nền tảng thương mại có thể chủ động không bán sản phẩm từ 01 đến 02/07. Khi ấy ngày không có giá có thể là trạng thái nghiệp vụ hợp lệ. Ngược lại, hệ thống tính phí thuê bao liên tục có thể bắt buộc có giá cho **mọi ngày hợp đồng còn hiệu lực**.

Vì vậy cần phân biệt hai bất biến:

- **At most one (tối đa một):** không chồng lấp; có thể không có phiên bản.
- **Exactly one (đúng một):** không chồng lấp **và** bao phủ đầy đủ khoảng thời gian yêu cầu.

Nếu nghiệp vụ nói “đúng một”, định nghĩa còn phải có **phạm vi thời gian bắt buộc bao phủ**, ví dụ từ ngày mở bán đến ngày ngừng bán. Không thể chứng minh “đúng một giá ở mọi ngày” nếu không định nghĩa miền ngày quan tâm.

### 8.2. Tìm khoảng trống giữa các bản ghi

Giả định các khoảng đã không chồng lấp, có thể tìm khoảng trống **nội bộ** bằng hàm cửa sổ:

~~~sql
WITH timeline AS (
    SELECT
        scope_id,
        upper(valid_period) AS end_of_current,
        LEAD(lower(valid_period)) OVER (
            PARTITION BY scope_id
            ORDER BY lower(valid_period)
        ) AS start_of_next
    FROM plan_price_period
)
SELECT
    scope_id,
    end_of_current AS gap_from,
    start_of_next AS gap_to
FROM timeline
WHERE end_of_current IS NOT NULL
  AND start_of_next IS NOT NULL
  AND end_of_current < start_of_next;
~~~

Kết quả là các khoảng trống dạng **[gap_from, gap_to)** giữa hai phiên bản liên tiếp.

Truy vấn này **không phát hiện** phần thiếu trước phiên bản đầu tiên hoặc sau phiên bản cuối cùng. Để kiểm tra bao phủ đầy đủ, cần so với khoảng hoạt động của gói và quy tắc bắt đầu/kết thúc dịch vụ.

### 8.3. Gộp khoảng khi cùng giá trị

Giả sử:

~~~text
[01/01, 01/04) → 100000
[01/04, 01/07) → 100000
~~~

Về mặt truy vấn giá, có thể gộp thành **[01/01, 01/07)**. Tuy nhiên, nếu hai khoảng xuất phát từ hai quyết định giá khác nhau, việc gộp có thể làm mất khả năng liên kết với văn bản phê duyệt. Quy tắc gộp phải xét **căn cứ nghiệp vụ và nhu cầu lịch sử**, không chỉ giá trị bằng nhau.

## 9. Ngăn chồng lấp khi có nhiều người cập nhật

Giả sử nhân viên A lên kế hoạch tăng giá từ 01/07, trong khi nhân viên B cùng lúc lên kế hoạch giảm giá từ 15/06 đến 15/07. Hai người có thể đọc timeline ban đầu giống nhau rồi tạo hai lịch giá xung đột.

Một lỗi phổ biến là:

~~~text
1. SELECT kiểm tra chưa có khoảng giao nhau.
2. Nếu không có, INSERT bản ghi mới.
~~~

Khi A và B thực hiện đồng thời, cả hai có thể cùng nhìn thấy “chưa có bản ghi khác” trước khi bất kỳ transaction nào commit. Nếu database không có ràng buộc hoặc cơ chế khóa đủ chặt, hai bản ghi trùng hiệu lực có thể cùng được lưu.

### 9.1. Kết hợp transaction, khóa và constraint

Thiết kế ở phần 7 có bảng **price_scope** với một hàng ổn định cho mỗi phạm vi giá. Có thể khóa hàng này khi sửa lịch:

~~~sql
BEGIN;

SELECT scope_id
FROM price_scope
WHERE scope_id = 17
FOR UPDATE;

-- Đọc timeline hiện hành của scope 17.
-- Xác thực quyết định và tính lại các khoảng bị ảnh hưởng.
-- UPDATE/INSERT/DELETE theo quy tắc nghiệp vụ và kiểm tra kết quả.

COMMIT;
~~~

Hàng **price_scope** là điểm đồng bộ cho các yêu cầu cùng phạm vi. Khi tất cả đường ghi đều dùng giao thức khóa này, hai lần sửa cùng scope được xử lý có thứ tự. Ràng buộc **EXCLUDE** vẫn cần thiết vì nó bảo vệ dữ liệu khi có lỗi chương trình hoặc một đường ghi bỏ qua lớp kiểm tra.

Cần giới hạn quyền ghi bảng lịch sử hoặc gom thao tác vào service/stored procedure để bảo đảm các đường cập nhật dùng chung quy tắc. Không nên chỉ dựa vào kiểm tra phía giao diện.

### 9.2. Thay đổi một phiên bản đang mở

Trước khi áp dụng giá mới từ 01/12, phiên bản hiện tại là:

~~~text
[01/10, vô hạn) → 130.000 VND
~~~

Muốn thêm phiên bản:

~~~text
[01/12, vô hạn) → 140.000 VND
~~~

phải rút ngắn khoảng cũ:

~~~text
[01/10, 01/12) → 130.000 VND
[01/12, vô hạn) → 140.000 VND
~~~

Một transaction minh họa với dữ liệu đã xác định:

~~~sql
BEGIN;

SELECT scope_id
FROM price_scope
WHERE scope_id = 17
FOR UPDATE;

UPDATE plan_price_period
SET valid_period = daterange(
    DATE '2026-10-01',
    DATE '2026-12-01',
    '[)'
)
WHERE scope_id = 17
  AND valid_period =
      daterange(DATE '2026-10-01', NULL, '[)')
RETURNING period_id;

-- Ứng dụng/stored procedure phải kiểm tra đúng 1 hàng được cập nhật.
-- Nếu không, ROLLBACK và đọc lại timeline thay vì tiếp tục.

INSERT INTO plan_price_period (
    scope_id, monthly_fee, valid_period, decision_ref
)
VALUES (
    17, 140000,
    daterange(DATE '2026-12-01', NULL, '[)'),
    'PRICE-2026-DEC'
);

COMMIT;
~~~

Nếu lệnh INSERT thất bại do constraint, transaction phải được **rollback** để không để lại hàng cũ đã bị rút ngắn nhưng không có hàng mới. Câu lệnh UPDATE và INSERT nằm trong cùng transaction không tự bảo đảm ứng dụng đã kiểm tra đúng **số hàng ảnh hưởng**, vì vậy giao thức nghiệp vụ phải kiểm tra trước khi commit.

### 9.3. Khi nào cần constraint DEFERRABLE?

Một số phép đổi cấu trúc nhiều khoảng có thể tạo chồng lấp **tạm thời trong nội bộ transaction** dù trạng thái cuối hợp lệ, ví dụ cần đổi vị trí hai khoảng mà không có thứ tự cập nhật đơn giản. PostgreSQL cho phép định nghĩa **exclusion constraint** là **DEFERRABLE**, rồi tạm hoãn kiểm tra tới cuối transaction khi có lý do cụ thể:

~~~sql
-- Minh họa thuộc tính trên một constraint được tạo mới:
CONSTRAINT ex_one_price_at_a_time
    EXCLUDE USING gist (
        scope_id WITH =,
        valid_period WITH &&
    )
    DEFERRABLE INITIALLY IMMEDIATE
~~~

Nếu dùng thuộc tính đó, trong transaction có thể thực hiện:

~~~sql
SET CONSTRAINTS ex_one_price_at_a_time DEFERRED;
~~~

Tuy nhiên, **trạng thái cuối cùng tại COMMIT vẫn phải hợp lệ**. Trì hoãn kiểm tra không có nghĩa là bỏ ràng buộc và không thay thế kiểm soát ghi đồng thời. Nó còn ảnh hưởng cách database kiểm tra lỗi và thời điểm ứng dụng phát hiện lỗi; chỉ sử dụng khi một kịch bản cập nhật thực sự cần.

DDL đầy đủ ở phần 7 tạo constraint kiểm tra ngay; muốn thực hành DEFERRABLE cần định nghĩa đúng từ lúc tạo constraint hoặc tạo lại theo quy trình migration tương ứng. Hai đoạn minh họa ở đây không hàm ý lệnh SET sẽ làm một constraint không DEFERRABLE tự trở thành DEFERRABLE.

## 10. Những trường hợp khó: hồi tố, dữ liệu đến muộn và lịch sử ghi nhận

### 10.1. Chèn một đoạn nằm bên trong phiên bản cũ

Giả sử giá 120.000 áp dụng **[01/07, 01/10)**, rồi đến tháng 9 có quyết định giá 115.000 chỉ áp dụng **[01/08, 01/09)**. Quy tắc chống chồng lấp từ chối chèn đoạn mới nếu chưa điều chỉnh bản cũ. Thiết kế cần chia:

~~~text
Trước:
[01/07, 01/10) → 120000

Sau:
[01/07, 01/08) → 120000
[01/08, 01/09) → 115000
[01/09, 01/10) → 120000
~~~

Việc chia phải giữ các đoạn không bị thay đổi, có cùng quy ước biên và không bỏ sót ngày. Nếu phạm vi chỉnh sửa giao nhiều bản ghi, phải tính lại **toàn bộ các đoạn giao nhau**, không chỉ hàng có ngày bắt đầu gần nhất.

### 10.2. Chỉ dùng valid time không đủ để biết “hồi đó hệ thống biết gì”

Một bảng chỉ có khoảng hiệu lực biểu diễn **lịch hiệu lực mà hệ thống hiện chấp nhận**. Khi điều chỉnh một khoảng cũ, dữ liệu sau sửa có thể không còn cho biết hệ thống **đã từng lưu điều gì** trước khi đính chính.

Phân biệt:

- **Valid time:** giá trị được coi là đúng cho ngày nghiệp vụ nào.
- **Recorded/system time:** hệ thống ghi nhận phiên bản đó trong giai đoạn nào.
- **Event time:** quyết định hoặc hành động thực tế xảy ra khi nào.

Nếu cần trả lời cả **“giá có hiệu lực ngày 15/08 là gì?”** và **“ngày 16/08 hệ thống đã cho rằng giá của ngày 15/08 là gì?”**, phải bổ sung trục recorded/system time hoặc lưu sự kiện có đủ dữ liệu để tái dựng. Khi đó một cặp phiên bản có thể giao nhau về **valid time** nhưng **không giao nhau trong cùng một thời kỳ recorded time**.

**Điểm đặc biệt:** với bitemporal, quy tắc chống chồng lấp phải áp vào **cả hai chiều**. Không được cấm mọi khoảng valid giao nhau giữa các phiên bản thuộc **hai trạng thái kiến thức khác nhau**, bởi như vậy sẽ làm mất khả năng ghi nhận điều chỉnh hồi tố.

Ví dụ một ràng buộc bitemporal ở mức khái niệm:

~~~sql
EXCLUDE USING gist (
    entity_id WITH =,
    valid_period WITH &&,
    known_period WITH &&
)
~~~

Nghĩa là với cùng thực thể, hai hàng không được đồng thời chồng nhau ở **cả valid time và known time**. Việc thiết kế bảng đầy đủ còn yêu cầu quy tắc mở/đóng known interval, ghi nhận nguồn và transaction.

### 10.3. Dữ liệu đã chốt phải có chứng cứ độc lập

Giả sử hóa đơn phát hành ngày 16/08 đã tính 120.000 VND, còn điều chỉnh hồi tố khiến lịch giá hiện hành cho 15/08 thành 115.000 VND. Hóa đơn không được tự thay số tiền mỗi lần truy vấn bảng giá mới nhất.

Cần lưu **số tiền thực tính**, kỳ áp dụng và nguồn quyết định/phiên bản giá đã dùng khi chốt hóa đơn; khi cần, phát hành nghiệp vụ điều chỉnh riêng. Khóa ngoại tới một hàng có thể bị chỉnh không tự thay thế được bằng chứng bất biến về số tiền đã tính.

## 11. Kiểm thử biên bằng dữ liệu mẫu và phép giao khoảng

Trong PostgreSQL, toán tử **&&** kiểm tra chồng lấp của hai range:

~~~sql
SELECT
    daterange(DATE '2026-01-01', DATE '2026-07-01', '[)')
    &&
    daterange(DATE '2026-07-01', DATE '2026-10-01', '[)')
    AS adjacent_overlap;
-- false
~~~

~~~sql
SELECT
    daterange(DATE '2026-01-01', DATE '2026-07-02', '[)')
    &&
    daterange(DATE '2026-07-01', DATE '2026-10-01', '[)')
    AS real_overlap;
-- true
~~~

Toán tử **@>** kiểm tra chứa một điểm; **&&** kiểm tra hai khoảng có giao nhau. Khi xác thực **không chồng lấp**, dùng toán tử phù hợp với kiểu dữ liệu và biên đã chuẩn hóa, thay vì chỉ so sánh ngày bắt đầu với nhau.

### 11.1. Ma trận kiểm thử biên

| Trường hợp | Khoảng A | Khoảng B / điểm t | Kỳ vọng |
|---|---|---|---|
| Chạm đầu cuối | [01/01, 01/07) | [01/07, 01/10) | Không chồng |
| Giao 1 ngày | [01/01, 02/07) | [01/07, 01/10) | Chồng |
| B nằm trong A | [01/01, 01/10) | [01/04, 01/06) | Chồng |
| B bao trọn A | [01/04, 01/06) | [01/01, 01/10) | Chồng |
| Trùng hoàn toàn | [01/01, 01/07) | [01/01, 01/07) | Chồng |
| Cách nhau 2 ngày | [01/01, 01/07) | [03/07, 01/10) | Không chồng; có gap |
| Không có biên trên | [01/10, vô hạn) | [01/12, 01/01 năm sau) | Chồng |
| Kiểm tra biên trái | [01/07, 01/10) | t = 01/07 | Có chứa |
| Kiểm tra biên phải | [01/07, 01/10) | t = 01/10 | Không chứa |
| Khoảng rỗng | [01/07, 01/07) | Bất kỳ điểm t | Phải bị từ chối |

Thêm các thử nghiệm vận hành:

1. **Ghi đồng thời:** hai transaction cùng thêm các khoảng giao nhau cho một scope. Cuối cùng không được có hai hàng xung đột đã commit.
2. **Lỗi giữa transaction:** rút ngắn khoảng cũ rồi làm chèn khoảng mới thất bại; rollback phải phục hồi khoảng cũ.
3. **Ghi tương lai:** phiên bản được nhập hôm nay nhưng bắt đầu tháng sau; truy vấn hôm nay không chọn nhầm nó.
4. **Đổi thời gian hiệu lực hồi tố:** cần chia đủ đầu và cuối khoảng, bảo toàn dữ liệu giao dịch đã chốt.
5. **Khác phạm vi:** hai hàng cùng khoảng nhưng khác scope có thể tồn tại đồng thời.
6. **Múi giờ:** timestamp cùng một thời điểm với hai offset khác nhau phải so sánh bằng nhau về thời gian tuyệt đối.
7. **Dữ liệu cũ:** kiểm tra khoảng NULL, rỗng, sai thứ tự, phạm vi thiếu khóa và các cách dùng sentinel khác nhau trước migration.
8. **Retention:** khi xóa lịch sử cũ theo chính sách, truy vấn as-of phải có cách thông báo phạm vi dữ liệu còn giữ.

**Không chồng lấp** là bất biến có thể kiểm chứng tự động. Nhưng kết quả “không chồng” chỉ có nghĩa đúng nếu phạm vi khóa và quy ước thời gian đã được người phụ trách nghiệp vụ xác nhận.

## 12. Di chuyển từ hai cột thời gian sang kiểu range

Một hệ thống hiện có:

~~~text
plan_id | currency_code | valid_from | valid_to | price
~~~

Muốn chuyển sang một cột **valid_period daterange**, cần làm rõ:

- **valid_to hiện tại là ngày cuối cùng được bao gồm hay ngày đầu tiên bị loại trừ?** Nếu dữ liệu cũ lưu “hết ngày 30/06” thì chuyển về biên nửa mở **01/07** chỉ khi độ phân giải là ngày và ngày cuối đã được xác nhận.
- **NULL đang có nghĩa gì?** “Vô hạn”, “chưa xác minh”, “chưa nhập” có thể bị trộn trong cùng một cột; phải phân loại.
- **Các khoảng có trùng nhau không?** Phải sửa dữ liệu mâu thuẫn trước khi áp constraint.
- **Có khoảng trống không?** Khoảng trống có thể là quy tắc tạm dừng bán, không nên tự lấp nếu không có yêu cầu.
- **Có cần giữ lịch sử các bản ghi trước migration không?** Khi thay đổi ngữ nghĩa biên, cần chứng minh truy vấn kỳ cũ vẫn trả đúng kết quả.

Nếu **valid_to** của dữ liệu nguồn đã là **biên loại trừ** và NULL nghĩa là không giới hạn, có thể tạo giá trị range:

~~~sql
SELECT daterange(valid_from, valid_to, '[)')
FROM legacy_price;
~~~

Đây là **ví dụ chuyển đổi biểu diễn** từ một bảng giả định tên **legacy_price**; không được chạy máy móc khi chưa kiểm tra cách hiểu biên ở dữ liệu gốc.

### 12.1. Phát hiện xung đột trước khi bật constraint

Với một bảng range đã nạp tạm, truy vấn tự JOIN để tìm cặp chồng lấp:

~~~sql
SELECT
    a.scope_id,
    a.period_id AS first_period_id,
    b.period_id AS second_period_id,
    a.valid_period AS first_range,
    b.valid_period AS second_range
FROM plan_price_period a
JOIN plan_price_period b
  ON a.scope_id = b.scope_id
 AND a.period_id < b.period_id
 AND a.valid_period && b.valid_period;
~~~

Khi bảng đã có exclusion constraint, truy vấn sẽ không tìm thấy cặp vi phạm trong dữ liệu hợp lệ. Nó đặc biệt hữu ích **trên bảng staging/migration chưa bật constraint** để phát hiện lỗi dữ liệu nguồn trước khi chuyển hệ thống.

Không tự động chọn một trong hai bản ghi chồng nhau chỉ vì **recorded_at** mới hơn. Cần biết quyết định nào có thẩm quyền, quyền điều chỉnh hồi tố và các giao dịch đã sử dụng từng phiên bản.

## 13. Áp dụng tương tự trong document, graph và kho phân tích

Nguyên tắc khoảng hiệu lực phải giữ nguyên khi lựa chọn mô hình lưu trữ khác; điều thay đổi là cách bảo vệ bất biến.

| Kiểu mô hình | Biểu diễn thường gặp | Cách kiểm soát chồng lấp |
|---|---|---|
| **Quan hệ** | Cặp biên hoặc kiểu range; khóa phiên bản, khóa ngoại | Exclusion constraint nếu DB hỗ trợ, transaction, khóa |
| **Document** | Tài liệu phiên bản chứa validFrom và validTo, liên kết bằng entityId | Giao dịch/khóa theo thực thể hoặc cơ chế ghi một tài liệu có điều kiện |
| **Graph** | Node/edge phiên bản với thuộc tính khoảng thời gian | Kiểm tra quan hệ và các cạnh cạnh tranh cùng có hiệu lực |
| **Kho phân tích** | Dimension SCD Type 2 với effectiveFrom/effectiveTo | Kiểm thử pipeline, ràng buộc dữ liệu, kiểm tra giao khoảng theo khóa dimension |
| **Event store** | Sự kiện quyết định và projection phiên bản hiệu lực | Quy tắc dựng timeline, idempotency, kiểm soát conflict khi replay |

### 13.1. Document: không phụ thuộc vào phép sort đầu tiên

Ví dụ một tài liệu giá:

~~~json
{
  "planId": 7,
  "currency": "VND",
  "monthlyFee": 120000,
  "validFrom": "2026-07-01",
  "validTo": "2026-10-01",
  "boundaryConvention": "[)"
}
~~~

Nếu truy vấn chỉ chọn tài liệu có **validFrom** lớn nhất không vượt ngày D, vẫn có thể chọn sai khi tồn tại **gap** hoặc khi tài liệu hết hạn trước D. Cần thêm điều kiện **D < validTo** hoặc **validTo là unbounded**, đồng thời kiểm tra xung đột dưới ghi đồng thời.

### 13.2. Graph: quan hệ cũng có hiệu lực theo thời gian

Một nhân viên có thể thuộc nhóm A từ 01/01 đến trước 01/04, rồi thuộc nhóm B từ 01/04. Hai **cạnh MEMBER_OF** phải được gắn khoảng hiệu lực. Nếu quy tắc nói “tối đa một nhóm chính tại một thời điểm”, cần chống chồng lấp **các cạnh phân công chính**, không chỉ các phiên bản thuộc tính của node nhân viên.

### 13.3. Kho phân tích: SCD Type 2 cần biên rõ ràng

Dimension khách hàng theo **SCD Type 2** có thể có:

~~~text
customer_sk | customer_id | segment | effective_from | effective_to
     101    |    501      | SILVER  | 2026-01-01     | 2026-07-01
     102    |    501      | GOLD    | 2026-07-01     | NULL
~~~

Khi JOIN fact tại ngày D, phải áp dụng đúng quy ước **[from, to)**. Nếu pipeline tạo cả hai phiên bản có hiệu lực tại D, kết quả JOIN có thể nhân đôi bản ghi giao dịch và làm sai báo cáo. Một khóa surrogate duy nhất không ngăn được việc này; cần kiểm chứng bất biến theo **customer_id** và khoảng hiệu lực.

## 14. Bài thực hành: thiết kế phân công phòng họp

Một công ty xây tính năng đặt phòng họp. Yêu cầu:

> “Mỗi phòng chỉ được có tối đa một cuộc họp tại cùng thời điểm. Cuộc họp kế tiếp được phép bắt đầu đúng lúc cuộc họp trước kết thúc.”

Chọn hai đặt lịch:

~~~text
R1: phòng 3, [2026-11-22 09:00+07, 10:00+07)
R2: phòng 3, [2026-11-22 10:00+07, 11:00+07)
~~~

R1 và R2 **không chồng lấp**. Nếu một người thêm R3:

~~~text
R3: phòng 3, [2026-11-22 09:30+07, 10:30+07)
~~~

R3 **chồng lấp cả R1 lẫn R2**, nên phải bị từ chối hoặc yêu cầu chọn phòng/giờ khác.

Một phác thảo PostgreSQL phù hợp:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_booking (
    booking_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id    bigint NOT NULL,
    time_slot  tstzrange NOT NULL,
    title      text NOT NULL,

    CONSTRAINT ck_room_booking_time
        CHECK (
            NOT isempty(time_slot)
            AND NOT lower_inf(time_slot)
            AND NOT upper_inf(time_slot)
            AND lower_inc(time_slot)
            AND NOT upper_inc(time_slot)
        ),

    CONSTRAINT ex_room_booking_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            time_slot WITH &&
        )
);
~~~

Ở đây **không cho phép khoảng đặt phòng vô hạn**, khác với bảng giá. Điều này phản ánh nhu cầu nghiệp vụ: một lịch đặt phòng phải có cả thời điểm bắt đầu lẫn kết thúc. **CHECK** và **EXCLUDE** cùng bảo đảm quy tắc tại database.

Thử hai trường hợp:

~~~sql
INSERT INTO room_booking (room_id, time_slot, title)
VALUES
(
    3,
    tstzrange(
        TIMESTAMPTZ '2026-11-22 09:00+07',
        TIMESTAMPTZ '2026-11-22 10:00+07',
        '[)'
    ),
    'Họp nhóm A'
),
(
    3,
    tstzrange(
        TIMESTAMPTZ '2026-11-22 10:00+07',
        TIMESTAMPTZ '2026-11-22 11:00+07',
        '[)'
    ),
    'Họp nhóm B'
);
-- Cả hai hợp lệ vì chỉ tiếp giáp ở 10:00.
~~~

~~~sql
INSERT INTO room_booking (room_id, time_slot, title)
VALUES (
    3,
    tstzrange(
        TIMESTAMPTZ '2026-11-22 09:30+07',
        TIMESTAMPTZ '2026-11-22 10:30+07',
        '[)'
    ),
    'Họp nhóm C'
);
-- Bị từ chối vì chồng lấp lịch của phòng 3.
~~~

Để hoàn thiện bài tập, hãy trả lời:

1. Nếu phòng 3 được đặt **[10:00, 11:00)** nhưng lịch [09:00, 10:00) đã kết thúc, vì sao không có xung đột?
2. Nếu phòng 4 có lịch **[09:30, 10:30)**, có xung đột với phòng 3 không? Khóa nghiệp vụ quy định điều gì?
3. Nếu công ty cần **15 phút dọn phòng giữa hai cuộc họp**, điều kiện chống chồng lấp đơn thuần đã đủ chưa? Hãy mô hình hóa khoảng đệm hoặc thời gian chiếm dụng thực tế.
4. Nếu một cuộc họp bị hủy, nên xóa bản ghi hay lưu trạng thái hủy để làm bằng chứng? Một phiên bản “hủy” có còn chiếm phòng không? Ràng buộc phải phản ánh đúng các trạng thái được coi là giữ chỗ.
5. Nếu hai người đặt cùng lúc, giao thức transaction và lỗi exclusion constraint phải được xử lý thế nào?

Câu hỏi 3 cho thấy **không chồng lấp chỉ bảo đảm không có hai khoảng cùng chứa một thời điểm**. Nó không tự bảo đảm khoảng nghỉ tối thiểu. Câu hỏi 4 cho thấy trạng thái hiệu lực có thể phụ thuộc vào nhiều thuộc tính, chẳng hạn đặt lịch còn hoạt động hay đã hủy. Mô hình phải xác định phạm vi những hàng tham gia ràng buộc.

## 15. Checklist phê duyệt thiết kế và nguyên tắc chốt

Trước khi đưa một bảng phiên bản theo khoảng hiệu lực vào sử dụng, hãy kiểm tra:

- **Ngữ nghĩa:** valid time là ngày hay thời điểm tuyệt đối; timezone nghiệp vụ được định nghĩa ở đâu?
- **Biên:** thống nhất **[from, to)** hay một quy ước khác; các API, báo cáo và migration có cùng hiểu biết không?
- **Độ chính xác:** có tránh mô hình “23:59:59” và mốc giả khi dữ liệu dùng microsecond hoặc chuyển múi giờ không?
- **Khoảng hợp lệ:** loại trừ khoảng rỗng, sai thứ tự và những giá trị không xác định chưa được phân loại chưa?
- **Khóa nghiệp vụ:** hai phiên bản nào phải được xem là cạnh tranh, và những chiều nào được phép tồn tại đồng thời?
- **Chồng lấp:** database có một cơ chế bảo vệ bất biến dưới ghi đồng thời, thay vì chỉ kiểm tra SELECT phía ứng dụng không?
- **Tiếp giáp/gap:** nghiệp vụ cần “tối đa một” hay “đúng một” giá trị; khoảng trống hợp lệ đến mức nào?
- **Giao dịch:** sửa khoảng hiện hành, chèn ở giữa lịch sử, rollback và retry có xử lý nguyên tử không?
- **Lịch sử:** có cần biết hệ thống từng tin gì trước khi điều chỉnh hồi tố; có lưu nguồn quyết định và chứng cứ giao dịch đã chốt không?
- **Kiểm thử:** đã thử đúng biên đầu/cuối, giao một phần, bao chứa, vô hạn, khác scope, múi giờ và ghi đồng thời chưa?
- **Tiến hóa:** kiểu range, chỉ mục, constraint và chính sách lưu giữ có đáp ứng được truy vấn thực tế ở quy mô dự kiến không?

**Quy tắc đáng nhớ:** một khoảng **[from, to)** chứa biên trái và loại trừ biên phải; hai khoảng **tiếp giáp** khi kết thúc của bản trước bằng bắt đầu của bản sau thì không chồng lấp. Quy tắc **không chồng lấp** chỉ có ý nghĩa khi gắn với **khóa nghiệp vụ đúng** và được thực thi an toàn trong database dưới ghi đồng thời. Khi yêu cầu vượt ra ngoài một dòng thời gian hiệu lực, hãy bổ sung lịch sử ghi nhận một cách tường minh để bảo đảm mô hình vẫn giải thích được các quyết định trong quá khứ.

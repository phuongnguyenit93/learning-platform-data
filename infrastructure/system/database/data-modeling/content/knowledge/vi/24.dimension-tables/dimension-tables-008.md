# Gom các cờ hoặc mã ít giá trị thành chiều phụ (junk dimension)

Một bảng dữ kiện trong kho dữ liệu thường mang hàng triệu dòng, nhưng mỗi dòng lại chứa vài cờ **Có/Không**, mã trạng thái ngắn hoặc nhãn phân loại chỉ có vài giá trị. Ví dụ, tại thời điểm đặt hàng, hệ thống ghi nhận **có gói quà không**, **có áp dụng mã giảm giá không** và **phương thức nhận hàng là giao tận nơi hay nhận tại cửa hàng**. Các cờ này có giá trị phân tích rõ ràng, nhưng mỗi cờ thường quá nhỏ để tạo một bảng chiều riêng.

**Chiều phụ (junk dimension)** là một kỹ thuật mô hình chiều (*dimensional modeling*) gom **một nhóm thuộc tính phân loại có số giá trị ít** thành một bảng dimension chứa **những tổ hợp giá trị**, rồi để fact table tham chiếu bằng **một khóa thay thế (surrogate key)**. Tên *junk* không có nghĩa dữ liệu vô ích: đây là những thuộc tính có ý nghĩa nghiệp vụ nhưng chưa đủ nội dung để trở thành các chiều chuyên biệt.

Bài thuộc chương **Bảng chiều** của mô-đun **DATABASE_DATA_MODELING**. Ta sẽ đi từ câu hỏi nghiệp vụ tới grain, lược đồ sao, SQL PostgreSQL, quy trình nạp dữ liệu, chất lượng, lịch sử và các đánh đổi vật lý. Mục tiêu là hiểu **khi nào gom cờ giúp mô hình phân tích rõ ràng hơn, và khi nào không nên gom**.

## 1. Vấn đề: quá nhiều cờ và mã nhỏ trên fact

Giả sử kho phân tích cần mô hình hóa một sự kiện **đơn được đặt thành công**. Nguồn vận hành gửi:

~~~text
order_number
placed_on
customer_id
is_gift_wrap
is_coupon_applied
fulfillment_mode
merchandise_total_vnd
~~~

Ba thuộc tính phân loại:

- **is_gift_wrap**: Có gói quà khi đặt không? Nhận **TRUE/FALSE**.
- **is_coupon_applied**: Có ít nhất một ưu đãi bằng coupon **đã được áp dụng thành công** khi chốt đơn không? Nhận **TRUE/FALSE**.
- **fulfillment_mode**: Cách nhận hàng **được chọn khi đặt**, gồm **SHIP** (giao hàng) hoặc **PICKUP** (nhận tại cửa hàng).

Chúng khác các số đo như **merchandise_total_vnd**, vì không cộng cờ TRUE trên nhiều đơn như cộng số tiền. Muốn biết số đơn có gói quà, ta **đếm các đơn** đáp ứng điều kiện.

### 1.1. Ba cách tổ chức ban đầu

| Cách lưu | Cấu trúc ý tưởng | Điểm mạnh | Hạn chế |
| --- | --- | --- | --- |
| **Giữ cờ trực tiếp trên fact** | Fact có ba cột cờ/mã | Đơn giản, lọc trực tiếp, dễ hiểu ở quy mô nhỏ | Nhiều cột mô tả nhỏ làm bảng fact cồng kềnh và khó quản trị nhãn phân loại thống nhất |
| **Tạo từng dimension nhỏ** | dim_gift_wrap, dim_coupon, dim_fulfillment | Rõ từng khái niệm riêng | Fact có nhiều khóa ngoại; thêm nhiều bảng chỉ chứa 2–3 hàng có thể là quá mức |
| **Gom thành junk dimension** | dim_order_junk(gift_wrap, coupon, fulfillment), fact chỉ lưu junk_key | Một nơi diễn đạt tổ hợp, dễ nhóm theo nhiều cờ | Cần JOIN, quản lý số tổ hợp và xử lý nạp dữ liệu/historization |

**Không có cách nào đúng trong mọi hệ thống.** Nếu chỉ có hai cờ và engine cột nén các giá trị lặp rất tốt, giữ trực tiếp trên fact có thể đơn giản và nhanh. Junk dimension là **lựa chọn có chủ đích**, không phải yêu cầu bắt buộc để đạt 3NF hoặc BCNF.

### 1.2. Điều gì được gọi là một junk dimension?

Trong bài này, junk dimension chứa:

~~~text
dim_order_junk(
    junk_key,
    is_gift_wrap,
    is_coupon_applied,
    fulfillment_mode
)
~~~

Ví dụ các tổ hợp hợp lệ hoặc đã quan sát:

| junk_key | is_gift_wrap | is_coupon_applied | fulfillment_mode |
| ---: | --- | --- | --- |
| 1 | FALSE | FALSE | SHIP |
| 2 | TRUE | FALSE | SHIP |
| 3 | FALSE | TRUE | PICKUP |
| 4 | TRUE | TRUE | SHIP |
| 5 | FALSE | FALSE | PICKUP |

Fact tham chiếu **junk_key**. Nhờ đó, một giá trị như **junk_key = 4** cho biết tại lúc đặt đơn: **có gói quà, có coupon áp dụng và chọn giao hàng**.

**junk_key không phải một mã nghiệp vụ có ý nghĩa cố định**. Trong ví dụ, các số 1–5 chỉ là ID minh họa. Hệ thống thực tế nên tra tổ hợp bằng các cột thuộc tính, không viết quy tắc như “junk_key = 4 nghĩa là đơn có coupon” vì surrogate key có thể được cấp khác ở môi trường khác.

## 2. Chốt grain trước khi gom cờ

**Grain** là phát biểu chính xác một hàng fact biểu diễn điều gì. Nếu không làm rõ grain, junk dimension có thể làm sai cả số đếm lẫn nghĩa của cờ.

Trong ví dụ:

> Một hàng của **fact_order_placed** biểu diễn **một đơn được đặt thành công tại thời điểm placed_on**. Các cờ thể hiện lựa chọn/điều kiện **ngay tại lúc đặt**, không phải trạng thái hiện hành về sau.

Ta phân biệt:

| Thuộc tính | Grain và thời điểm | Có hợp vào junk dimension đơn đặt không? |
| --- | --- | --- |
| Có gói quà khi đặt | Một đơn tại lúc đặt | **Có** |
| Coupon được áp dụng khi chốt đơn | Một đơn tại lúc đặt | **Có** |
| Cách nhận hàng được chọn khi đặt | Một đơn tại lúc đặt | **Có** |
| Sản phẩm trên một dòng đơn | Một dòng đơn | **Không**: liên quan product dimension của line fact |
| Khách hàng của đơn | Một khách hàng, nhiều thuộc tính mô tả | **Không**: nên dùng dim_customer |
| Mã đơn | Một đơn, nhiều giá trị duy nhất | **Không**: thường là *degenerate dimension* trên fact |
| Giá trị hàng hóa của đơn | Một số đo tại grain đơn | **Không**: lưu trong fact dưới dạng measure |
| Đơn đã giao thành công tính đến hôm nay | Trạng thái hiện hành có thể thay đổi sau khi đặt | **Không** với event fact bất biến như ví dụ |

Nếu thay bằng **fact_order_line** với grain mỗi dòng, không thể mặc nhiên suy **một hàng = một đơn**. Khi đó các cờ cấp đơn có thể lặp lại trên nhiều dòng: **COUNT(*)** sẽ đếm dòng, không đếm đơn. Có thể hợp thức hóa cách lưu ở line fact nếu cờ áp dụng cho mọi dòng và phép phân tích được định nghĩa rõ; để đếm đơn phải sử dụng khóa đơn duy nhất hoặc fact cấp đơn.

### 2.1. Phân biệt cờ, thuộc tính mô tả và số đo

- **Cờ/nhãn phân loại** trả lời “thuộc nhóm nào?”: có gói quà, coupon được áp dụng, loại nhận hàng.
- **Thuộc tính dimension nhiều thông tin** trả lời “đối tượng nào và đặc điểm gì?”: khách hàng, sản phẩm, cửa hàng, chiến dịch.
- **Số đo** trả lời “bao nhiêu?”: số tiền, số lượng, chi phí.
- **Định danh giao dịch** trả lời “sự kiện nào?”: order_number, transaction_id.

Đừng gom **amount**, **product_id** hay **order_number** vào junk dimension chỉ vì chúng đang nằm cạnh các cờ trên cùng bản tin nguồn.

## 3. Chọn các cờ và mã nào để gom

Một ứng viên phù hợp thường đáp ứng nhiều điều kiện:

1. **Cardinality thấp:** số giá trị riêng ít, chẳng hạn BOOLEAN hoặc mã phân loại có vài trạng thái.
2. **Cùng grain và cùng ngữ nghĩa thời gian** với fact hoặc snapshot mà nó mô tả.
3. **Thiếu hệ thuộc tính phong phú riêng**: không có mô tả, phân cấp, lịch sử, chủ sở hữu và khóa nghiệp vụ đáng để tạo dimension chuyên biệt.
4. **Được dùng như bộ lọc/nhóm** trong báo cáo.
5. **Số tổ hợp thực tế có thể quản lý được**: không tạo ra hàng trăm nghìn hoặc hàng triệu kết hợp khó duy trì.

### 3.1. Ví dụ nên và không nên gom

| Thuộc tính | Kết luận gợi ý | Lý do |
| --- | --- | --- |
| is_gift_wrap | Cân nhắc gom | Hai giá trị, mô tả lựa chọn đơn |
| is_coupon_applied | Cân nhắc gom | Hai giá trị, điều kiện được xác nhận lúc đặt |
| fulfillment_mode = SHIP/PICKUP | Cân nhắc gom | Mã ít giá trị, nếu không có hệ phân cấp/vòng đời phức tạp |
| promotion_id / coupon_code | **Không gom** | Có thể nhiều giá trị và có thuộc tính riêng, phù hợp dimension hoặc quan hệ khuyến mại |
| customer_id | **Không gom** | Thực thể độc lập, nhiều thuộc tính và lịch sử |
| payment_amount | **Không gom** | Measure số lượng tiền |
| transaction_id | **Không gom** | Định danh giá trị cao, thường degenerate dimension |
| product_category | Tùy mô hình | Có thể thuộc dim_product hoặc dim_category với phân cấp và lịch sử |
| current_delivery_status | Thường **không gom với cờ đặt hàng bất biến** | Thời gian cập nhật khác và có máy trạng thái riêng |

**Chữ “junk” chỉ nói tới vai trò của các cờ nhỏ trong mô hình chiều**, không phủ nhận giá trị nghiệp vụ. Một mã ít giá trị vẫn có thể cần dimension riêng nếu nó có định nghĩa, mô tả đa ngôn ngữ, phân cấp, hiệu lực hoặc quy tắc quản lý độc lập.

### 3.2. Gom các mã có tương quan có được không?

**Được**, nếu các tổ hợp có **ngữ nghĩa hợp lệ** và được kiểm tra. Các cờ không bắt buộc độc lập thống kê. Ví dụ, một số phương thức nhận hàng có thể hạn chế một loại dịch vụ; dimension có thể chỉ chứa những tổ hợp được phép.

Nhưng tránh gom các cờ có **ràng buộc ngầm không ai kiểm chứng**. Nếu hệ thống cho phép:

~~~text
fulfillment_mode = PICKUP
is_home_delivery_requested = TRUE
~~~

thì hai thuộc tính đó có vẻ mâu thuẫn theo định nghĩa thường gặp. Phải hỏi nghiệp vụ: cờ “home delivery requested” là yêu cầu từng có, yêu cầu hiện hành hay lựa chọn đã chốt? Nếu tổ hợp thực sự bị cấm, có thể chặn ở bước nạp hoặc thêm **CHECK** trên dimension; không nên chỉ hy vọng dữ liệu nguồn không tạo ra nó.

## 4. Ước lượng số tổ hợp: tránh bùng nổ cardinality

Với các cột phân loại có lần lượt **c₁, c₂, …, cₙ** giá trị, số tổ hợp **tối đa** có thể là:

\[
N_{\max} = \prod_{i=1}^{n} c_i
\]

Nếu có **b cờ nhị phân độc lập về tập giá trị**, con số tối đa là:

\[
N_{\max} = 2^b
\]

| Số cờ nhị phân | Tổ hợp tối đa |
| ---: | ---: |
| 3 | 8 |
| 8 | 256 |
| 12 | 4.096 |
| 16 | 65.536 |
| 20 | 1.048.576 |

Với **3 cờ** trong ví dụ (2 × 2 × 2), có tối đa **8 tổ hợp**. Mẫu chỉ đang dùng **5 tổ hợp**. Có thể tạo tất cả 8 nếu tất cả hợp lệ và số lượng nhỏ, nhưng không có yêu cầu phải tạo hàng cho những tổ hợp chưa từng xảy ra.

Nếu một cờ được mở rộng từ **TRUE/FALSE** thành **YES/NO/UNKNOWN**, tám cờ như vậy có thể tạo **3⁸ = 6.561** tổ hợp; **12 cờ ba trạng thái** có thể tạo **3¹² = 531.441** tổ hợp.

### 4.1. Tổ hợp lý thuyết khác tổ hợp hợp lệ và đã quan sát

Có ba tập cần phân biệt:

- **Tổ hợp lý thuyết:** tích Descartes của mọi mã/cờ được liệt kê.
- **Tổ hợp hợp lệ:** những tổ hợp nghiệp vụ thực sự cho phép.
- **Tổ hợp đã quan sát:** những tổ hợp xuất hiện trong các fact đã nạp.

Quan hệ thường gặp là:

~~~text
tổ hợp đã quan sát ⊆ tổ hợp hợp lệ ⊆ tổ hợp lý thuyết
~~~

Khi nguồn dữ liệu đúng và quy tắc đầy đủ, không phải chiều junk nào cũng cần nạp trước toàn bộ tổ hợp hợp lệ. Hai chính sách phổ biến là **prepopulate** những tổ hợp nhỏ đã được phê duyệt hoặc **insert-on-demand** khi lần đầu nhận một tổ hợp hợp lệ.

Để tránh số hàng chiều tăng không kiểm soát, có thể **chia thành vài junk dimensions có chủ đề** (chẳng hạn cờ giao nhận và cờ khuyến mại) hoặc giữ các thuộc tính trực tiếp trên fact, tùy workload. Không nên gom 20 cờ chỉ vì tất cả đều là BOOLEAN.

## 5. Mô hình sao cho đơn đã đặt

Sơ đồ sau biểu diễn fact mức một đơn tại thời điểm đặt, tham chiếu dimension thời gian, khách hàng và chiều phụ:

~~~mermaid
erDiagram
    DIM_DATE ||--o{ FACT_ORDER_PLACED : "ngày đặt"
    DIM_CUSTOMER ||--o{ FACT_ORDER_PLACED : "khách đặt"
    DIM_ORDER_JUNK ||--o{ FACT_ORDER_PLACED : "phân loại"
    DIM_DATE {
        integer date_key PK
        date full_date
    }
    DIM_CUSTOMER {
        bigint customer_key PK
        varchar customer_code
        varchar customer_name
    }
    DIM_ORDER_JUNK {
        bigint junk_key PK
        boolean is_gift_wrap
        boolean is_coupon_applied
        varchar fulfillment_mode
    }
    FACT_ORDER_PLACED {
        bigint order_fact_key PK
        varchar order_number UK
        integer date_key FK
        bigint customer_key FK
        bigint junk_key FK
        bigint merchandise_total_vnd
    }
~~~

**fact_order_placed** có một số đo **merchandise_total_vnd**, nhưng **dim_order_junk không có measure**; nó chỉ chứa các thuộc tính phân loại. **order_number** là định danh giao dịch (degenerate dimension) ở fact; **junk_key** là khóa đại diện cho tổ hợp giá trị.

### 5.1. SQL PostgreSQL: dimension và fact

~~~sql
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE
);

CREATE TABLE dim_customer (
    customer_key BIGINT PRIMARY KEY,
    customer_code VARCHAR(20) NOT NULL UNIQUE,
    customer_name VARCHAR(100) NOT NULL
);

CREATE TABLE dim_order_junk (
    junk_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    is_gift_wrap BOOLEAN NOT NULL,
    is_coupon_applied BOOLEAN NOT NULL,
    fulfillment_mode VARCHAR(10) NOT NULL
        CHECK (fulfillment_mode IN ('SHIP', 'PICKUP')),
    UNIQUE (
        is_gift_wrap,
        is_coupon_applied,
        fulfillment_mode
    )
);

CREATE TABLE fact_order_placed (
    order_fact_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(20) NOT NULL UNIQUE,
    date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    customer_key BIGINT NOT NULL REFERENCES dim_customer(customer_key),
    junk_key BIGINT NOT NULL REFERENCES dim_order_junk(junk_key),
    merchandise_total_vnd BIGINT NOT NULL
        CHECK (merchandise_total_vnd >= 0)
);
~~~

Một số điểm quan trọng của thiết kế:

- **junk_key** do database cấp, không phải mã mang nghĩa nghiệp vụ.
- **UNIQUE(is_gift_wrap, is_coupon_applied, fulfillment_mode)** chặn hai hàng dimension có cùng tổ hợp, giúp ETL ánh xạ một-một.
- **NOT NULL** cùng **CHECK** ở dimension làm mã rõ nghĩa trong ví dụ; chính sách **UNKNOWN/NOT_APPLICABLE** được bàn riêng ở mục 9.
- Fact giữ **một khóa ngoại junk_key**, thay cho ba thuộc tính phân loại trực tiếp trên fact.
- **UNIQUE(order_number)** phù hợp vì fact chỉ lưu **một sự kiện đặt** trên một đơn. Nếu fact ghi nhiều sự kiện mỗi đơn, phải thay grain và khóa.
- Khóa ngoại và khóa duy nhất bảo vệ một số bất biến của quan hệ, nhưng không tự xác minh định nghĩa cờ có đúng lịch sử giao dịch hay không.

### 5.2. Nạp dimension và dữ liệu mẫu

~~~sql
INSERT INTO dim_date (date_key, full_date) VALUES
    (20261119, DATE '2026-11-19'),
    (20261120, DATE '2026-11-20'),
    (20261121, DATE '2026-11-21');

INSERT INTO dim_customer
    (customer_key, customer_code, customer_name)
VALUES
    (1, 'C01', 'An'),
    (2, 'C02', 'Bình'),
    (3, 'C03', 'Chi');

INSERT INTO dim_order_junk
    (is_gift_wrap, is_coupon_applied, fulfillment_mode)
VALUES
    (FALSE, FALSE, 'SHIP'),
    (TRUE,  FALSE, 'SHIP'),
    (FALSE, TRUE,  'PICKUP'),
    (TRUE,  TRUE,  'SHIP'),
    (FALSE, FALSE, 'PICKUP');
~~~

**Không nên giả định** ID được cấp lần lượt theo đúng thứ tự VALUES hoặc có cùng giá trị qua nhiều môi trường. Khi nạp fact, tra tổ hợp theo **giá trị cờ/mã** và lấy **junk_key** thực tế:

~~~sql
INSERT INTO fact_order_placed
    (order_number, date_key, customer_key,
     junk_key, merchandise_total_vnd)
SELECT
    src.order_number,
    src.date_key,
    src.customer_key,
    junk.junk_key,
    src.merchandise_total_vnd
FROM (
    VALUES
        ('O1001', 20261119, 1::BIGINT,
         FALSE, FALSE, 'SHIP',   120000::BIGINT),
        ('O1002', 20261119, 2::BIGINT,
         TRUE,  FALSE, 'SHIP',   230000::BIGINT),
        ('O1003', 20261120, 1::BIGINT,
         FALSE, TRUE,  'PICKUP', 150000::BIGINT),
        ('O1004', 20261120, 3::BIGINT,
         TRUE,  TRUE,  'SHIP',   320000::BIGINT),
        ('O1005', 20261121, 2::BIGINT,
         FALSE, FALSE, 'SHIP',   180000::BIGINT),
        ('O1006', 20261121, 3::BIGINT,
         FALSE, FALSE, 'PICKUP',  90000::BIGINT)
) AS src(
    order_number, date_key, customer_key,
    is_gift_wrap, is_coupon_applied, fulfillment_mode,
    merchandise_total_vnd
)
JOIN dim_order_junk AS junk
  ON junk.is_gift_wrap = src.is_gift_wrap
 AND junk.is_coupon_applied = src.is_coupon_applied
 AND junk.fulfillment_mode = src.fulfillment_mode;
~~~

Khi nạp xong, fact có **6 đơn** với tổng số tiền hàng là **1.090.000 VND**. Các truy vấn tiếp theo giả định chưa chạy bước nạp thêm ở mục 8.

## 6. Phân tích bằng junk dimension

### 6.1. Đếm và cộng số tiền theo phương thức nhận hàng

~~~sql
SELECT
    junk.fulfillment_mode,
    COUNT(*) AS order_count,
    SUM(f.merchandise_total_vnd) AS merchandise_total_vnd
FROM fact_order_placed AS f
JOIN dim_order_junk AS junk
  ON junk.junk_key = f.junk_key
GROUP BY junk.fulfillment_mode
ORDER BY junk.fulfillment_mode;
~~~

Kết quả theo mẫu:

| fulfillment_mode | order_count | merchandise_total_vnd |
| --- | ---: | ---: |
| PICKUP | 2 | 240000 |
| SHIP | 4 | 850000 |

Phép JOIN không làm nhân hàng vì mỗi **junk_key** trên fact chỉ khớp **một** hàng dimension (khóa chính của dim_order_junk). Từ một thuộc tính trong chiều, có thể phân nhóm các fact mà không cần viết điều kiện IF trên nhiều mã kỹ thuật.

### 6.2. Đếm đơn có gói quà hoặc coupon

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE junk.is_gift_wrap)
        AS gift_wrap_orders,
    COUNT(*) FILTER (WHERE junk.is_coupon_applied)
        AS coupon_orders,
    COUNT(*) FILTER (
        WHERE junk.is_gift_wrap AND junk.is_coupon_applied
    ) AS both_flags_orders,
    SUM(f.merchandise_total_vnd) FILTER (
        WHERE junk.is_coupon_applied
    ) AS coupon_order_merchandise_vnd
FROM fact_order_placed AS f
JOIN dim_order_junk AS junk
  ON junk.junk_key = f.junk_key;
~~~

Kết quả:

| all_orders | gift_wrap_orders | coupon_orders | both_flags_orders | coupon_order_merchandise_vnd |
| ---: | ---: | ---: | ---: | ---: |
| 6 | 2 | 2 | 1 | 470000 |

Hai cờ TRUE có thể cùng xuất hiện trên một đơn, vì vậy **2 đơn có gói quà + 2 đơn có coupon** không có nghĩa là **4 đơn khác nhau** có ít nhất một trong hai điều kiện. Nếu cần số đơn thỏa ít nhất một cờ, dùng điều kiện **OR**:

~~~sql
SELECT COUNT(*) AS orders_with_either_flag
FROM fact_order_placed AS f
JOIN dim_order_junk AS junk
  ON junk.junk_key = f.junk_key
WHERE junk.is_gift_wrap OR junk.is_coupon_applied;
-- Kết quả: 3 đơn (O1002, O1003, O1004).
~~~

### 6.3. Phân tích đồng thời nhiều cờ theo ngày

~~~sql
SELECT
    d.full_date,
    junk.fulfillment_mode,
    junk.is_coupon_applied,
    COUNT(*) AS order_count,
    SUM(f.merchandise_total_vnd) AS total_vnd
FROM fact_order_placed AS f
JOIN dim_date AS d ON d.date_key = f.date_key
JOIN dim_order_junk AS junk
  ON junk.junk_key = f.junk_key
GROUP BY
    d.full_date,
    junk.fulfillment_mode,
    junk.is_coupon_applied
ORDER BY d.full_date, junk.fulfillment_mode, junk.is_coupon_applied;
~~~

**Chỉ số đếm đúng** vì grain của fact là một đơn. Nếu sau này fact lưu **nhiều lần cập nhật trạng thái mỗi đơn**, truy vấn này sẽ đếm sự kiện cập nhật chứ không còn đếm số đơn duy nhất. Cách sửa không đơn giản là đặt DISTINCT tùy ý; cần đặt lại định nghĩa grain và metric.

### 6.4. Nhãn báo cáo có thể do dimension cung cấp

Nếu nhiều báo cáo dùng chung tên tiếng Việt cho fulfillment_mode, có thể bổ sung cột mô tả đã được kiểm soát trong dimension, chẳng hạn **fulfillment_label_vi**, hoặc tra một bảng mã chuyên biệt nếu nhãn có đa ngôn ngữ/metadata riêng.

Ví dụ projection không làm thay đổi grain:

~~~sql
SELECT
    CASE junk.fulfillment_mode
        WHEN 'SHIP' THEN 'Giao hàng'
        WHEN 'PICKUP' THEN 'Nhận tại cửa hàng'
    END AS fulfillment_label_vi,
    COUNT(*) AS order_count
FROM fact_order_placed AS f
JOIN dim_order_junk AS junk
  ON junk.junk_key = f.junk_key
GROUP BY junk.fulfillment_mode;
~~~

Đây là biểu thức trình bày ngắn trong truy vấn minh họa. Với mô hình lớn, nhãn cần quản trị tập trung, tránh mỗi dashboard định nghĩa một kiểu. Nếu mã phân loại có hệ mô tả phong phú, đa cấp hoặc nhiều ngôn ngữ, cân nhắc dimension riêng thay vì nhồi tất cả metadata vào junk dimension.

## 7. Một junk dimension nên chứa tất cả tổ hợp hay chỉ tổ hợp đã dùng?

### 7.1. Prepopulate toàn bộ tổ hợp hợp lệ

Khi số tổ hợp ít và ổn định, có thể nạp trước tất cả **tổ hợp hợp lệ**. Ví dụ bài này có tối đa 8 tổ hợp, nên prepopulate cả 8 thường không khó.

Ưu điểm:

- Mọi fact hợp lệ có thể tra khóa mà không cần thêm hàng dimension.
- Có thể rà soát và phê duyệt từng tổ hợp trước khi nạp fact.
- Giảm xung đột nạp lần đầu đối với một tổ hợp mới.

Hạn chế:

- Tồn tại hàng dimension chưa có fact nào tham chiếu.
- Nếu sinh tổ hợp bằng **CROSS JOIN**, có thể tạo những kết hợp **không được nghiệp vụ cho phép**.
- Với nhiều cờ/mã, tập tích Descartes có thể lớn hơn số tổ hợp thực tế rất nhiều.

### 7.2. Nạp tổ hợp khi xuất hiện (insert-on-demand)

Khi số tổ hợp hợp lệ lớn nhưng chỉ ít tổ hợp xuất hiện:

1. Nhận dữ liệu fact ở staging.
2. Chuẩn hóa cờ/mã theo từ điển nghiệp vụ.
3. Lấy danh sách **DISTINCT các tổ hợp** từ staging.
4. Bổ sung tổ hợp hợp lệ chưa có trong dim_order_junk.
5. Tra **junk_key** bằng toàn bộ thuộc tính tổ hợp.
6. Nạp fact, đồng thời đối chiếu số dòng và kiểm tra tổ hợp chưa ánh xạ.

Ưu điểm là dimension nhỏ theo tập đã quan sát, tránh tạo hàng cho mọi khả năng lý thuyết. Hạn chế là pipeline phải xử lý tổ hợp mới, khóa trùng, lỗi mã và ghi đồng thời. Ràng buộc **UNIQUE trên bộ cờ/mã** là chốt chặn quan trọng.

### 7.3. So sánh hai cách

| Tiêu chí | Prepopulate hợp lệ | Insert-on-demand |
| --- | --- | --- |
| Số tổ hợp rất ít, ổn định | Thường thuận tiện | Vẫn dùng được |
| Có nhiều kết hợp lý thuyết không hợp lệ | Phải lọc trước khi sinh | Phải kiểm tra từng tổ hợp mới |
| Gặp tổ hợp mới trong ETL | Thường đã có khóa | Cần cấp khóa mới |
| Dễ quản lý khóa và kiểm tra domain | Thuận lợi nếu bảng mã ổn định | Cần logic chuẩn hóa, nạp và đối soát |
| Tăng số tổ hợp theo thời gian | Phải mở rộng tập hợp lệ | Tăng theo dữ liệu quan sát |

Không có lợi ích khi giữ những tổ hợp không hợp lệ chỉ để “đủ mọi hàng”; điều đó có thể khiến ETL vô tình chấp nhận dữ liệu sai.

## 8. Pipeline nạp dữ liệu: chuẩn hóa, upsert tổ hợp, tra khóa

Giả sử có hai đơn mới với tổ hợp **(FALSE, TRUE, SHIP)** chưa được nạp trong bảng chiều mẫu trước đó. Bước dưới đây cho thấy **tổ hợp được tạo một lần** rồi cả hai đơn cùng sử dụng khóa tương ứng.

**Điều kiện chạy:** đã thực thi DDL và dữ liệu mẫu của mục 5; các ngày, khách hàng tham chiếu tồn tại. Đoạn ETL dưới đây là giao dịch riêng; số lượng và tổng tiền fact **sau khi nạp** khác kết quả mục 6.

~~~sql
BEGIN;

CREATE TEMP TABLE staged_orders (
    order_number VARCHAR(20) PRIMARY KEY,
    date_key INTEGER NOT NULL,
    customer_key BIGINT NOT NULL,
    is_gift_wrap BOOLEAN NOT NULL,
    is_coupon_applied BOOLEAN NOT NULL,
    fulfillment_mode VARCHAR(10) NOT NULL,
    merchandise_total_vnd BIGINT NOT NULL
) ON COMMIT DROP;

INSERT INTO staged_orders (
    order_number, date_key, customer_key,
    is_gift_wrap, is_coupon_applied, fulfillment_mode,
    merchandise_total_vnd
) VALUES
    ('O1007', 20261121, 1,
     FALSE, TRUE, 'SHIP', 70000),
    ('O1008', 20261121, 2,
     FALSE, TRUE, 'SHIP', 80000);

-- Khử trùng tổ hợp; khóa UNIQUE của dimension xử lý trùng.
INSERT INTO dim_order_junk (
    is_gift_wrap, is_coupon_applied, fulfillment_mode
)
SELECT DISTINCT
    is_gift_wrap, is_coupon_applied, fulfillment_mode
FROM staged_orders
ON CONFLICT (
    is_gift_wrap, is_coupon_applied, fulfillment_mode
) DO NOTHING;

-- Không suy diễn junk_key = max(junk_key) + 1.
-- Tra lại khóa bằng bộ giá trị cờ/mã.
INSERT INTO fact_order_placed (
    order_number, date_key, customer_key,
    junk_key, merchandise_total_vnd
)
SELECT
    src.order_number,
    src.date_key,
    src.customer_key,
    junk.junk_key,
    src.merchandise_total_vnd
FROM staged_orders AS src
JOIN dim_order_junk AS junk
  ON junk.is_gift_wrap = src.is_gift_wrap
 AND junk.is_coupon_applied = src.is_coupon_applied
 AND junk.fulfillment_mode = src.fulfillment_mode
WHERE TRUE
ON CONFLICT (order_number) DO NOTHING;

COMMIT;
~~~

Ở ví dụ này, **dim_order_junk** tăng từ **5 lên 6 tổ hợp**, fact tăng từ **6 lên 8 đơn**. Bảng dimension không tăng thêm hai hàng cho hai đơn vì hai đơn có cùng bộ giá trị.

### 8.1. Vì sao dùng UNIQUE và ON CONFLICT?

Hai pipeline chạy đồng thời có thể cùng gặp tổ hợp mới và cùng định INSERT. Nếu chỉ **SELECT kiểm tra chưa có** rồi **INSERT** mà không có ràng buộc, chúng có thể tạo hai hàng tương đương với hai junk_key khác nhau. Ràng buộc **UNIQUE trên toàn tổ hợp** bảo vệ điều này ở cơ sở dữ liệu; **ON CONFLICT DO NOTHING** giúp một luồng bỏ qua hàng đã được luồng khác nạp.

**ON CONFLICT (order_number) DO NOTHING** chỉ phù hợp khi đơn đã được nạp thì không muốn ghi trùng. Nếu hệ thống cần sửa **merchandise_total_vnd** hoặc tái xử lý sự kiện thay đổi, phải có **chính sách hiệu chỉnh/upsert fact rõ ràng**; bỏ qua mọi xung đột có thể che giấu dữ liệu nguồn đã được sửa.

### 8.2. Kiểm soát hàng staging không ánh xạ được

Ví dụ truy vấn kiểm tra những tổ hợp staging chưa tìm thấy trong dimension:

~~~sql
SELECT
    src.order_number,
    src.is_gift_wrap,
    src.is_coupon_applied,
    src.fulfillment_mode
FROM staged_orders AS src
LEFT JOIN dim_order_junk AS junk
  ON junk.is_gift_wrap = src.is_gift_wrap
 AND junk.is_coupon_applied = src.is_coupon_applied
 AND junk.fulfillment_mode = src.fulfillment_mode
WHERE junk.junk_key IS NULL;
~~~

**Lưu ý:** staged_orders trong ví dụ được tạo với **ON COMMIT DROP**, vì vậy câu truy vấn trên chỉ chạy được **bên trong giao dịch trước COMMIT**, hoặc cần đổi sang staging bền vững/không tự hủy. Đây là bước **kiểm thử/giám sát ETL**; không nên để một **INNER JOIN** loại âm thầm các fact bị thiếu tổ hợp rồi kết luận quá trình nạp thành công.

Trong hệ thống sản xuất, quy trình thường có thêm **raw zone/staging bền vững, nhật ký lỗi, watermark nguồn, kiểm tra row count**, và cơ chế khôi phục. Ví dụ SQL tối giản chỉ minh họa sự hình thành và tra cứu junk_key.

### 8.3. Đối chiếu số dòng và khóa nguồn

Một pipeline nên kiểm tra:

~~~text
số đơn nguồn đủ điều kiện nạp
  = số đơn đã nạp mới + số đơn đã có (nếu cho phép bỏ qua)
    + số đơn bị từ chối có lý do được ghi rõ
~~~

Không thể chỉ so sánh tổng bản ghi vì **mất một đơn và nạp trùng một đơn khác** có thể khiến số lượng vẫn bằng nhau. Phải đối chiếu **order_number**, cột ngày, khách hàng, số tiền và bộ cờ/mã. Khi điều kiện nghiệp vụ yêu cầu giữ lịch sử sửa, nên ghi phiên bản thay đổi và sự kiện hiệu chỉnh thay vì overwrite tùy tiện.

## 9. UNKNOWN, NOT APPLICABLE và NULL: đừng đánh đồng với FALSE

Trong dữ liệu thực, một cờ có thể không có giá trị rõ ràng:

- **FALSE/NO:** nghiệp vụ xác nhận điều kiện **không đúng**.
- **UNKNOWN:** chưa nhận được dữ liệu, nguồn thiếu hoặc chưa thể kết luận.
- **NOT_APPLICABLE (N/A):** điều kiện **không áp dụng** đối với loại sự kiện này.
- **TRUE/YES:** điều kiện đã được xác nhận là đúng.

Ví dụ **is_coupon_applied = FALSE** có nghĩa không có coupon áp dụng thành công. Nhưng nếu hệ thống thanh toán chưa gửi thông tin coupon, suy **NULL → FALSE** sẽ khiến báo cáo đánh giá thấp tỷ lệ dùng coupon.

### 9.1. Hai chính sách thường gặp

**Chính sách A — từ chối hoặc tạm giữ dữ liệu không đầy đủ:** phù hợp khi các cờ là bắt buộc để công bố số liệu và có thể xử lý lại. Fact chưa được nạp vào bảng phân tích chính; hàng lỗi ở staging/quarantine với lý do rõ ràng.

**Chính sách B — biểu diễn trạng thái chưa rõ bằng mã tường minh:** phù hợp khi vẫn cần thấy fact, nhưng phải phân biệt chưa biết và phủ định. Thay BOOLEAN bằng mã trạng thái có miền như:

~~~text
gift_wrap_state  ∈ {YES, NO, UNKNOWN}
coupon_state     ∈ {YES, NO, UNKNOWN, NOT_APPLICABLE}
fulfillment_mode ∈ {SHIP, PICKUP, UNKNOWN}
~~~

Trong chính sách B, dimension có thể lưu:

| gift_wrap_state | coupon_state | fulfillment_mode | Ý nghĩa |
| --- | --- | --- | --- |
| YES | NO | SHIP | Có gói quà, không áp dụng coupon, giao hàng |
| UNKNOWN | YES | SHIP | Chưa rõ gói quà, xác nhận có coupon, giao hàng |
| NO | NOT_APPLICABLE | PICKUP | Không gói quà, coupon không áp dụng theo loại giao dịch |

**Mã UNKNOWN/N/A phải có định nghĩa**. Không nên dùng duy nhất một junk_key đặc biệt cho **mọi trường hợp** nếu muốn phân tích xem **cờ nào thiếu** trong khi những cờ khác đã biết.

### 9.2. Vì sao ví dụ SQL dùng NOT NULL?

Trong mục 5, ba cột cờ/mã của junk dimension là **NOT NULL**, vì bài toán mẫu giả định nguồn đã cung cấp đầy đủ và hợp lệ. Khi bổ sung UNKNOWN, phải thay **mô hình miền giá trị** chứ không chỉ cho phép SQL NULL tùy tiện.

Nếu một trong ba thành phần tổ hợp cho phép **NULL**, thao tác:

~~~sql
UNIQUE (is_gift_wrap, is_coupon_applied, fulfillment_mode)
~~~

trên nhiều cấu hình PostgreSQL có thể **không ngăn các hàng có NULL được xem như trùng nhau**, vì NULL có ngữ nghĩa khác giá trị bình thường. Tương tự, điều kiện JOIN bằng dấu **=** không khớp hai NULL. Có những cơ chế SQL xử lý NULL tường minh, nhưng mô hình hóa **UNKNOWN/NOT_APPLICABLE bằng giá trị miền được định nghĩa** thường dễ kiểm soát và dễ giải thích hơn cho chiều phụ.

Không nên biến mọi giá trị thiếu thành một nhãn UNKNOWN rồi bỏ qua điều tra chất lượng nguồn. Báo cáo phải có khả năng đo **tỷ lệ hàng chưa biết** và nguyên nhân.

## 10. Ý nghĩa lịch sử: cờ tại thời điểm đặt khác trạng thái hiện tại

Junk dimension chỉ lưu tổ hợp giá trị; **thời điểm mà tổ hợp đó đúng thuộc về grain và quy tắc nạp fact**.

Với fact_order_placed:

~~~text
is_coupon_applied = TRUE
~~~

nghĩa là **coupon đã áp dụng tại thời điểm đơn được đặt**. Nếu một tháng sau đơn được hoàn tiền, không nên sửa cờ này thành FALSE chỉ để biến nó thành “đã nhận ưu đãi ròng đến hôm nay”, vì như vậy sẽ thay đổi sự thật lịch sử và định nghĩa của báo cáo.

### 10.1. Trạng thái có thể đổi phải có mô hình thời gian phù hợp

| Câu hỏi | Mô hình gợi ý |
| --- | --- |
| Đơn chọn phương thức nhận nào lúc đặt? | Cờ/mã snapshot trong **fact_order_placed** và junk dimension |
| Trạng thái giao hàng **hiện tại** là gì? | Bảng operational status, accumulating snapshot hoặc mô hình trạng thái hiện hành có nguồn và thời điểm rõ |
| Đơn đã trải qua những trạng thái giao nào? | Fact sự kiện trạng thái với **event timestamp** và loại sự kiện |
| Tại ngày 20/11 hệ thống đã biết gì về giao hàng? | Fact/snapshot có thời điểm ghi nhận hoặc mô hình lịch sử đủ để truy vấn **as-of** |
| Có bao nhiêu đơn bị hoàn tiền sau khi đặt? | Fact hoàn tiền/điều chỉnh hoặc sự kiện nghiệp vụ riêng, không phải tái định nghĩa cờ đặt hàng |

**Không nhất thiết dùng SCD Type 2 cho mọi junk dimension.** Một tổ hợp **(TRUE, FALSE, SHIP)** mang ngữ nghĩa ổn định; nếu muốn thêm tổ hợp **(TRUE, TRUE, SHIP)** thì tạo **hàng tổ hợp mới**. Lịch sử ở đây chủ yếu được bảo vệ bằng **fact giữ đúng junk_key đã chọn lúc sự kiện xảy ra**.

Nếu tên hiển thị của SHIP đổi từ “Giao hàng” sang “Giao tận nơi” nhưng mã và ý nghĩa giữ nguyên, có thể cập nhật nhãn (theo chính sách quản lý mô tả), không cần tự động tạo phiên bản lịch sử tổ hợp. Nếu **ý nghĩa nghiệp vụ của mã thay đổi**, cần đổi mã/phiên bản hoặc có cơ chế lịch sử; sửa nhãn để che thay đổi ý nghĩa sẽ làm sai báo cáo quá khứ.

### 10.2. Thay đổi cờ do hiệu chỉnh dữ liệu khác thay đổi trạng thái nghiệp vụ

Giả sử nguồn gửi nhầm **is_coupon_applied = FALSE** cho đơn O1003, trong khi coupon thực tế đã áp dụng lúc chốt. Đây là **sửa một sự thật lịch sử bị ghi sai**. Quy trình có thể:

1. Ghi nhận phiếu hiệu chỉnh, giá trị cũ và mới.
2. Tìm tổ hợp đúng trong dim_order_junk; tạo tổ hợp nếu chưa có.
3. Cập nhật **junk_key** của fact theo chính sách sửa số liệu đã công bố.
4. Lưu dấu vết và kích hoạt tính lại các bảng tổng hợp/đối soát bị ảnh hưởng.

Ngược lại, nếu coupon bị **hoàn lại** sau thời điểm đặt, cần mô hình một sự kiện hoàn/điều chỉnh đúng ngữ nghĩa, không biến cờ “được áp dụng khi đặt” thành “đang còn hiệu lực hôm nay”.

### 10.3. Cẩn thận khi dimension khách hàng là SCD Type 2

Trong ví dụ, **dim_customer** là dimension đơn giản, có một hàng cho mỗi customer_code. Nếu sau này quản lý SCD Type 2 để biết khách thuộc phân khúc nào **khi đặt đơn**, bảng có thể có nhiều **customer_key** cho cùng customer_code.

Fact phải tham chiếu **phiên bản customer_key phù hợp với thời điểm đặt**. Không được JOIN fact qua customer_code với mọi phiên bản rồi nhân số đơn và doanh thu. Đây là vấn đề dimension lịch sử **khác** với junk dimension, nhưng rất dễ làm sai phép tổng hợp khi cùng dùng trong star schema.

## 11. Những đánh đổi thực tế: có phải junk dimension luôn tốt hơn cờ trên fact?

### 11.1. Lợi ích chính

- **Fact gọn về mặt cấu trúc:** nhiều cờ được thay bằng một khóa ngoại; thuận lợi nếu fact rất rộng hoặc có nhiều cờ cần quản trị chung.
- **Phân loại nhất quán:** các báo cáo dùng chung tên mã, nhãn và tổ hợp được phép.
- **Tổ hợp hiện diện rõ ràng:** truy vấn dimension giúp kiểm tra những kết hợp nào xuất hiện và có thể mô tả được.
- **Dễ thống kê theo nhiều điều kiện:** JOIN một dimension nhỏ để lọc/nhóm theo cờ và mã.
- **Đối soát tổ hợp ở nguồn:** một hàng chiều có thể giúp tìm lỗi khi nguồn gửi mã lạ hoặc kết hợp không hợp lệ.

### 11.2. Chi phí và giới hạn

- **Thêm JOIN:** truy vấn lọc một cờ có thể cần JOIN, tùy cơ chế tối ưu của hệ phân tích.
- **Cardinality có thể tăng theo tích:** quá nhiều thuộc tính trong một junk dimension khiến bảng chiều không còn nhỏ.
- **Quản lý ETL:** phải tạo/tra tổ hợp, xử lý giá trị lạ, NULL, dữ liệu đến trễ và khóa trùng.
- **Đánh đổi nén dữ liệu:** trong kho dữ liệu dạng cột, vài cột BOOLEAN/mã ít giá trị có thể được nén rất tốt; chuyển sang một junk_key **không mặc nhiên tiết kiệm hơn**.
- **Khả năng lọc sargable/pruning:** cờ trực tiếp trên fact đôi khi thuận tiện cho predicate pushdown hoặc phân vùng; phải xem query plan thực tế.
- **Tính diễn giải:** nếu người làm báo cáo chỉ thấy junk_key mà thiếu dimension/semantic layer, họ không hiểu nghĩa của giá trị.

| Điều kiện hệ thống | Gợi ý cân nhắc |
| --- | --- |
| Nhiều cờ thấp cardinality, thường phân tích chung, ít tổ hợp thực tế | Junk dimension có thể phù hợp |
| Chỉ 1–2 cờ, engine cột tối ưu tốt | Giữ cờ trực tiếp trên fact thường đủ |
| Một mã có hierarchy và metadata quan trọng | Tạo dimension chuyên biệt |
| Nhiều cờ ở grain/thời điểm khác nhau | Không gom tùy tiện; tách theo đúng sự thật |
| Tổ hợp lý thuyết rất lớn | Chia nhiều nhóm, giảm thuộc tính hoặc giữ trực tiếp |
| Các mã thay đổi với lịch sử cần kiểm toán | Thiết kế SCD, event hay snapshot phù hợp trước |

### 11.3. Khi nào tách một junk dimension thành nhiều nhóm?

Giả sử bảng fact có 12 cờ: 4 cờ liên quan **khuyến mại**, 4 cờ liên quan **giao nhận**, 4 cờ liên quan **rủi ro thanh toán**. Gom tất cả thành một bảng có thể tạo tối đa **2¹² = 4.096 tổ hợp** nếu đều nhị phân.

Có thể cân nhắc:

~~~text
dim_promotion_flags   : 4 cờ -> tối đa 16 tổ hợp
dim_fulfillment_flags : 4 cờ -> tối đa 16 tổ hợp
dim_risk_flags        : 4 cờ -> tối đa 16 tổ hợp

fact:
    promotion_flags_key
    fulfillment_flags_key
    risk_flags_key
~~~

Tổng hàng dimension lý thuyết tối đa là **16 + 16 + 16 = 48**, thay vì **4.096** trong một bảng duy nhất; đổi lại fact có **ba khóa ngoại** và một số truy vấn phải JOIN nhiều bảng hơn.

Đây là ví dụ về **phân nhóm theo chủ đề**, không phải chứng minh rằng tách ba bảng luôn tối ưu. Cần so sánh số tổ hợp thực tế, độ rộng khóa/cột, nhóm người dùng và workload. Nếu cờ rủi ro chỉ có ý nghĩa sau khi thanh toán nhưng cờ khuyến mại ghi lúc đặt, khác biệt **thời gian hiệu lực** còn là lý do mạnh hơn để không gom chung.

### 11.4. Quan hệ với chuẩn hóa và các mô hình dữ liệu khác

Trong **OLTP quan hệ**, các cờ có thể nằm trên bảng orders, hoặc được lưu theo quan hệ nghiệp vụ chuyên biệt nếu có lịch sử/quy tắc riêng. Không nhất thiết áp dụng junk dimension để sửa bảng giao dịch.

Trong **mô hình sao phân tích**, mục tiêu của junk dimension là giúp **tổ chức bộ lọc phân loại và giảm độ rộng mô tả của fact**, chứ không phải một bước bắt buộc của chuẩn hóa đến 3NF. Có thể coi đây là **một lựa chọn cấu trúc phục vụ truy vấn và quản trị chiều**.

Trong **document database**, một sự kiện đặt hàng có thể nhúng trực tiếp vài cờ và mã trong document; không có lý do tạo “junk dimension” theo đúng cơ chế relational star nếu workload không cần. Trong **graph database**, các cờ có thể là thuộc tính cạnh/nút hoặc các quan hệ độc lập tùy nghiệp vụ; vẫn cần grain và thời điểm hiệu lực.

Dù chọn cách lưu nào, **định nghĩa nghiệp vụ phải nhất quán**: cờ “coupon được áp dụng” không được hiểu khác giữa nguồn giao dịch, bảng phân tích và dashboard.

## 12. Kiểm thử chất lượng dữ liệu và hiệu năng

### 12.1. Kiểm tra mỗi tổ hợp chiều là duy nhất

Trong lược đồ mẫu, ràng buộc **UNIQUE** đã chặn trùng. Nếu nhận dữ liệu dimension từ file cũ hoặc muốn đối soát, có thể dùng:

~~~sql
SELECT
    is_gift_wrap,
    is_coupon_applied,
    fulfillment_mode,
    COUNT(*) AS duplicate_count
FROM dim_order_junk
GROUP BY is_gift_wrap, is_coupon_applied, fulfillment_mode
HAVING COUNT(*) > 1;
~~~

Truy vấn phải không có kết quả. Nếu có hai junk_key cho cùng tổ hợp, một số báo cáo có thể gộp vẫn ra tổng đúng khi nhóm theo các cờ, nhưng dimension không còn ánh xạ một-một, việc nạp mới và truy vấn theo surrogate key trở nên khó kiểm soát.

### 12.2. Kiểm tra fact không trỏ tới chiều thiếu

Với **FOREIGN KEY** đang bật, fact không thể tham chiếu junk_key không tồn tại. Nếu ETL tắt ràng buộc trong một vùng nạp lớn hoặc báo cáo dùng nguồn ngoài không có FK, cần kiểm tra:

~~~sql
SELECT f.order_number, f.junk_key
FROM fact_order_placed AS f
LEFT JOIN dim_order_junk AS junk
  ON junk.junk_key = f.junk_key
WHERE junk.junk_key IS NULL;
~~~

Truy vấn phải rỗng. Trong kho phân tích có chính sách dùng hàng **UNKNOWN** hợp lệ, việc trỏ tới junk_key của hàng UNKNOWN không phải lỗi tham chiếu; khi đó kiểm tra thêm tỷ lệ UNKNOWN và ngữ nghĩa gán.

### 12.3. Kiểm tra số đơn trước và sau JOIN

~~~sql
SELECT COUNT(*) AS fact_count
FROM fact_order_placed;

SELECT COUNT(*) AS joined_count
FROM fact_order_placed AS f
JOIN dim_order_junk AS junk
  ON junk.junk_key = f.junk_key;
~~~

Trên dữ liệu mẫu ban đầu, cả hai bằng **6**. Nếu nạp thêm ở mục 8, cả hai bằng **8**. Kết quả đếm bằng nhau là một kiểm tra hữu ích nhưng **không đủ** để chứng minh các cờ của từng đơn được ánh xạ đúng: cần đối chiếu từng đơn và tổ hợp nguồn, đặc biệt khi dữ liệu có thể bị sửa.

### 12.4. Lọc theo dimension và chỉ mục

Một hệ PostgreSQL có thể dùng khóa ngoại của fact để JOIN tới junk dimension; khóa chính của dim_order_junk đã có chỉ mục. Nếu thường xuyên lọc/nhóm theo junk_key trên fact rất lớn, cân nhắc:

~~~sql
CREATE INDEX idx_fact_order_placed_junk_date
ON fact_order_placed (junk_key, date_key);
~~~

Đây là **gợi ý**, không phải quy tắc luôn đúng. Phải kiểm tra mức chọn lọc của junk_key, số lượng fact, kiểu engine, phương thức lưu trữ, thống kê, partition, chi phí index khi ghi và kế hoạch truy vấn. Một dimension chỉ có vài tổ hợp có thể có **selectivity thấp**, khiến full scan hoặc chiến lược khác phù hợp hơn chỉ mục B-tree.

Với hệ lưu trữ dạng cột hoặc kho dữ liệu cloud, cơ chế nén, clustering, partition pruning và xử lý JOIN có thể khác PostgreSQL OLTP. Không kết luận junk dimension tiết kiệm không gian hay tăng tốc truy vấn khi chưa đo.

### 12.5. Test tối thiểu cho pipeline

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| Nạp hai đơn mới có cùng tổ hợp chưa từng xuất hiện | Tạo **một** hàng junk mới, cả hai fact cùng trỏ tới hàng ấy |
| Nạp lại cùng order_number | Không tạo fact trùng; hành vi sửa/ghi đè theo chính sách được kiểm chứng |
| Nhận fulfillment_mode không thuộc SHIP/PICKUP | Bị từ chối hoặc đưa vào quy trình chuẩn hóa/UNKNOWN theo chính sách |
| Nguồn thiếu cờ coupon | Không tự biến thành FALSE nếu chưa xác nhận |
| Tạo hai tổ hợp trùng trong các luồng nạp đồng thời | Chỉ có một hàng theo UNIQUE |
| Nguồn đưa tổ hợp nghiệp vụ không hợp lệ | Có lỗi chất lượng rõ ràng, không âm thầm tạo hàng junk |
| Thay đổi tình trạng đơn sau thời điểm đặt | Không làm thay đổi cờ snapshot cũ, trừ quy trình hiệu chỉnh đúng nghĩa |
| JOIN fact với chiều | Không nhân hoặc làm mất các hàng fact hợp lệ |

## 13. Quy trình ra quyết định sử dụng junk dimension

1. **Xác định câu hỏi báo cáo và grain fact:** một hàng là đơn, dòng hàng, sự kiện thanh toán hay snapshot ngày?
2. **Lập từ điển cờ/mã:** mỗi cờ TRUE/FALSE nghĩa gì, có UNKNOWN/N/A không, áp dụng ở thời điểm nào?
3. **Loại bỏ ứng viên không phù hợp:** ID giá trị cao, số đo, thuộc tính có hệ phân cấp riêng, trạng thái ở grain khác.
4. **Tính cardinality lý thuyết và thực tế:** bao nhiêu kết hợp có thể có, bao nhiêu hợp lệ, bao nhiêu đã xuất hiện?
5. **Chia nhóm hợp lý:** nếu một dimension quá lớn hoặc chứa cờ không cùng thời gian, tách thành nhóm chuyên đề.
6. **Xác định phương án nạp:** prepopulate hay insert-on-demand, quy tắc cấp surrogate key, khử trùng và kiểm tra dữ liệu lạ.
7. **Thiết kế ràng buộc:** UNIQUE cho bộ giá trị, NOT NULL/mã UNKNOWN rõ ràng, FK từ fact, kiểm tra tổ hợp bị cấm.
8. **Xác định lịch sử:** giữ cờ snapshot của fact, xử lý thay đổi trạng thái và hiệu chỉnh quá khứ thế nào?
9. **Kiểm chứng metric:** số đơn, giá trị hàng hóa, số đơn có cờ, phân tích theo thời gian không bị nhân hàng.
10. **Đo hiệu năng và chi phí vận hành:** so với việc giữ cờ trực tiếp trên fact hoặc dùng nhiều dimension nhỏ.

### 13.1. Một nguyên tắc thực dụng

Nếu cần thay đổi một định nghĩa cờ, một mã hay một thành phần trong nhóm, hãy hỏi:

> Việc thay đổi này có buộc thiết kế lại grain fact, sửa dữ liệu lịch sử hay thay đổi quan hệ với đối tượng nghiệp vụ khác không?

Nếu **có**, đó có thể không còn là một “cờ nhỏ” phù hợp để gom vào junk dimension. Chẳng hạn khi coupon chuyển từ **đã áp dụng hay chưa** sang phân tích **nhiều coupon, thứ tự áp dụng và số tiền giảm theo từng coupon**, cần quan hệ chi tiết hoặc fact khuyến mại riêng, thay vì chỉ thêm mã coupon vào junk dimension.

## 14. Bài tập vận dụng

### Bài 1 — Tính số tổ hợp và phân nhóm

Một fact đơn hàng có bốn thuộc tính phân loại: **is_gift_wrap** (2 giá trị), **is_coupon_applied** (2 giá trị), **customer_order_type** (3 giá trị: FIRST, REPEAT, UNKNOWN) và **fulfillment_mode** (2 giá trị).

**Yêu cầu:**

1. Tính số tổ hợp lý thuyết tối đa.
2. Nếu quy tắc nghiệp vụ cấm gói quà cho đơn PICKUP, số tổ hợp hợp lệ tối đa còn bao nhiêu?
3. Có bắt buộc prepopulate toàn bộ tổ hợp hợp lệ không?
4. Vì sao không thể dựa vào việc bảng nguồn chỉ xuất hiện 5 tổ hợp để khẳng định mã sẽ không bao giờ phát sinh tổ hợp thứ sáu?

<details>
<summary>Gợi ý lời giải bài 1</summary>

Số tổ hợp lý thuyết: **2 × 2 × 3 × 2 = 24**.

Với từng cặp (coupon, customer_order_type) có **2 × 3 = 6** cách. Khi **SHIP**, gift_wrap có 2 cách nên có **12** tổ hợp. Khi **PICKUP**, gift_wrap chỉ được FALSE nên có **6** tổ hợp. Tổng tối đa **18 tổ hợp hợp lệ**, nếu không có quy tắc cấm bổ sung.

Có thể prepopulate 18 tổ hợp khi nhỏ và ổn định, hoặc chỉ nạp các tổ hợp xuất hiện theo cơ chế insert-on-demand. Năm tổ hợp quan sát chỉ mô tả dữ liệu đến thời điểm đó, không chứng minh những tổ hợp hợp lệ khác sẽ không xuất hiện.

</details>

### Bài 2 — Đọc đúng chỉ số từ dữ liệu mẫu

Dùng sáu đơn **O1001–O1006** ở mục 5.

**Yêu cầu:**

1. Đếm số đơn có gói quà.
2. Đếm số đơn có coupon áp dụng và tổng giá trị hàng hóa của các đơn này.
3. Đếm số đơn có ít nhất một trong hai cờ TRUE.
4. Đếm số đơn SHIP và tổng số tiền hàng tương ứng.
5. Giải thích vì sao tổng số đơn có gói quà cộng tổng số đơn có coupon có thể lớn hơn số đơn thuộc hợp của hai tập.

<details>
<summary>Gợi ý lời giải bài 2</summary>

- Có gói quà: **2 đơn** (O1002, O1004).
- Có coupon: **2 đơn** (O1003, O1004), tổng tiền hàng **470.000 VND**.
- Ít nhất một cờ TRUE: **3 đơn** (O1002, O1003, O1004).
- SHIP: **4 đơn**, tổng tiền hàng **850.000 VND**.
- O1004 có **cả gói quà lẫn coupon**, nên nếu cộng số đơn của hai nhóm mà không trừ giao nhau thì O1004 bị đếm hai lần. Công thức: **|A ∪ B| = |A| + |B| − |A ∩ B| = 2 + 2 − 1 = 3**.

</details>

### Bài 3 — Nguồn có cờ bị thiếu

Một batch có:

~~~text
order | gift_wrap | coupon_applied | fulfillment
------+-----------+----------------+------------
O2001 | FALSE     | FALSE          | SHIP
O2002 | TRUE      | UNKNOWN        | SHIP
O2003 | FALSE     | TRUE           | PICKUP
O2004 | FALSE     | NOT_APPLICABLE | PICKUP
~~~

**Yêu cầu:**

1. Vì sao không chuyển UNKNOWN thành FALSE?
2. Nếu cần nạp cả bốn đơn, mô hình junk dimension ở mục 5 phải thay đổi ra sao?
3. Nếu có báo cáo “tỷ lệ đơn áp dụng coupon”, nên xử lý UNKNOWN và NOT_APPLICABLE trong mẫu số thế nào?

<details>
<summary>Gợi ý lời giải bài 3</summary>

**UNKNOWN** nghĩa là chưa biết có áp dụng coupon hay không, trong khi **FALSE** là đã xác nhận không áp dụng. Chuyển đổi tùy tiện làm sai kết quả.

Thay cột BOOLEAN về coupon bằng **coupon_state** có miền giá trị **YES, NO, UNKNOWN, NOT_APPLICABLE**, giữ NOT NULL và UNIQUE theo tất cả thành phần tổ hợp; hoặc áp dụng chính sách quarantine cho hàng chưa đủ dữ liệu.

Mẫu số phải được **định nghĩa theo nghiệp vụ**. Ví dụ, nếu đo tỷ lệ trong những đơn **đủ điều kiện dùng coupon và đã biết kết quả**, loại **UNKNOWN** và **NOT_APPLICABLE** khỏi mẫu số, đồng thời báo cáo số lượng bị loại. Nếu đo tỷ lệ trên **tất cả đơn đã đặt**, kết quả có thể cần dạng khoảng ước lượng hoặc tỷ lệ trên dữ liệu đã biết kèm độ bao phủ. Không có công thức duy nhất trước khi xác nhận định nghĩa chỉ số.

</details>

### Bài 4 — Grain sai làm số đếm sai

Fact cấp dòng hàng có dữ liệu:

~~~text
order_number | line_no | is_gift_wrap
-------------+---------+-------------
O3001        | 1       | TRUE
O3001        | 2       | TRUE
O3001        | 3       | TRUE
O3002        | 1       | FALSE
~~~

Các cờ ở đây thuộc **đơn**, nhưng được lặp xuống từng dòng để tiện truy vấn.

**Yêu cầu:** **COUNT(*)** sau khi lọc is_gift_wrap = TRUE trả bao nhiêu? Có bao nhiêu **đơn** gói quà thực sự? Nên thay đổi truy vấn hoặc mô hình như thế nào?

<details>
<summary>Gợi ý lời giải bài 4</summary>

**COUNT(*) = 3 dòng**, nhưng chỉ có **1 đơn gói quà** là O3001. Nếu dữ liệu giữ mỗi dòng một hàng, có thể dùng:

~~~sql
SELECT COUNT(DISTINCT order_number)
FROM fact_order_line
WHERE is_gift_wrap = TRUE;
~~~

Một giải pháp mô hình rõ grain hơn là dùng **fact_order_placed** ở cấp đơn và gắn junk_key cấp đơn tại đó; còn fact_order_line phục vụ số lượng và tiền theo dòng. Nếu đã chọn lặp cờ trên line fact, phải bảo đảm các dòng của cùng đơn dùng cùng giá trị và phép đếm luôn khớp grain câu hỏi.

</details>

### Bài 5 — Tổ hợp mới và nạp lặp

Dimension có năm tổ hợp như ở mục 5. Hai đơn mới **O1007** và **O1008** đều có **(FALSE, TRUE, SHIP)**.

**Yêu cầu:**

1. Nạp hai đơn cần tạo bao nhiêu hàng mới trong junk dimension?
2. Điều gì xảy ra nếu hai job cùng phát hiện tổ hợp mới và cùng tạo hàng?
3. Ràng buộc nào bảo đảm một tổ hợp không ứng với hai junk_key?
4. Có nên tính khóa mới bằng **MAX(junk_key) + 1** không?

**Hướng giải:** chỉ cần **một hàng chiều mới**. **UNIQUE(is_gift_wrap, is_coupon_applied, fulfillment_mode)** bảo vệ khỏi nạp trùng do cạnh tranh; ETL có thể sử dụng upsert/ON CONFLICT phù hợp. Không dùng MAX + 1 vì hai transaction có thể tính cùng một giá trị và tạo xung đột; dùng cơ chế cấp ID/sequence của DB, rồi tra khóa theo bộ giá trị.

### Bài 6 — Sửa một sự thật đã chốt

O1004 có **coupon_applied = TRUE** khi đặt. Hai tuần sau, đơn bị hoàn tiền. Nhóm báo cáo đề xuất cập nhật cờ coupon về FALSE trên fact_order_placed để “không còn tính đơn coupon”.

**Yêu cầu:** đề xuất cách mô hình hóa vừa giữ đúng sự thật lúc đặt vừa phục vụ báo cáo “coupon có giá trị ròng sau hoàn tiền”.

**Hướng giải:** giữ **coupon_applied_at_order = TRUE** trong sự kiện đặt. Ghi sự kiện hoàn tiền/điều chỉnh với thời điểm, số tiền, lý do và liên kết tới đơn. Từ các fact gốc, xây dựng chỉ số **giá trị ròng** theo chính sách doanh nghiệp thay vì ghi đè bản chất của sự kiện đặt hàng. Nếu nguồn ban đầu thực sự ghi sai tại lúc đặt, đó là **hiệu chỉnh lịch sử** có kiểm toán, khác với hoàn tiền sau đó.

## 15. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Junk dimension chứa dữ liệu vô giá trị.” | Nó chứa các **cờ và mã ít giá trị nhưng có ý nghĩa phân tích**. |
| “Hễ có BOOLEAN phải gom vào junk.” | Cần xét số cờ, grain, thời gian, workload và chi phí JOIN. |
| “Tất cả tổ hợp lý thuyết đều phải có trong dimension.” | Chỉ cần tổ hợp hợp lệ theo chính sách prepopulate/insert-on-demand. |
| “Các cờ trong junk phải độc lập nhau.” | Không bắt buộc; phải quản lý **các tổ hợp hợp lệ**, kể cả ràng buộc giữa cờ. |
| “junk_key = 4 luôn có nghĩa là coupon TRUE.” | Surrogate key **không mang nghĩa toàn cục**; phải JOIN với dimension. |
| “UNKNOWN và FALSE đều là không có coupon.” | UNKNOWN là **chưa biết**, FALSE là phủ định đã xác nhận. |
| “Thay đổi trạng thái đơn thì sửa mọi cờ đặt hàng.” | Cờ snapshot thuộc thời điểm đặt, sự kiện về sau có grain và thời gian riêng. |
| “Đổi một nhãn phải tạo SCD Type 2.” | Sửa nhãn cùng nghĩa có thể là cập nhật mô tả; thay đổi ý nghĩa phải có chính sách lịch sử. |
| “JOIN junk dimension sẽ làm tăng số đơn.” | Với khóa chính junk_key, mỗi fact chỉ khớp một hàng dimension; tăng hàng thường do JOIN sai hoặc trùng dữ liệu. |
| “Dùng junk dimension luôn tiết kiệm dung lượng.” | Engine cột có thể nén cờ trực tiếp tốt; cần đo. |
| “Một cờ có nhiều giá trị hơn thì cứ mở rộng junk.” | Mã giàu metadata hoặc cardinality cao có thể cần dimension chuyên biệt. |
| “COUNT(*) từ line fact là số đơn.” | COUNT(*) đếm **hàng ở grain fact**; muốn số đơn cần mô hình hoặc metric phù hợp. |

## 16. Ghi nhớ

**Junk dimension** gom các cờ và mã ít giá trị ở **cùng grain và ngữ nghĩa thời gian** vào một dimension chứa các **tổ hợp phân loại**. Mỗi fact tham chiếu tổ hợp thông qua một **surrogate key**. Cách này hữu ích khi một fact có nhiều thuộc tính phân loại nhỏ, cần quản trị nhãn thống nhất và số tổ hợp thực tế đủ nhỏ để duy trì.

Khi thiết kế, hãy **chốt grain trước**, làm rõ ý nghĩa TRUE/FALSE/UNKNOWN/N/A, ước lượng cardinality theo **tích các miền giá trị**, dùng **UNIQUE trên tổ hợp**, tra khóa bằng thuộc tính chứ không đoán ID, và kiểm tra kết quả JOIN không nhân hoặc mất hàng. Các cờ snapshot tại lúc giao dịch **không được biến thành trạng thái hiện hành** do cập nhật về sau.

Không phải mọi cờ đều nên gom: dimension giàu thuộc tính, ID giá trị cao, measure, trạng thái thay đổi theo thời gian khác nhau hoặc quá nhiều cờ sẽ làm mô hình sai nghĩa hoặc quá phức tạp. Một junk dimension có chất lượng là kết quả của **định nghĩa nghiệp vụ rõ → lựa chọn cờ hợp lý → thiết kế tổ hợp và khóa → nạp dữ liệu có kiểm chứng → đo chi phí truy vấn và vận hành**.

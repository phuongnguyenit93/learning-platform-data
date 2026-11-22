# Số đo cộng được, cộng được theo một số chiều và không cộng được

## Mục tiêu học tập

Trong **DATABASE_DATA_MODELING**, một bảng dữ kiện (*fact table*) không chỉ là tập hợp những cột số. Người thiết kế cần biết **một dòng đại diện cho điều gì**, **mỗi số đo mang nghĩa gì**, và đặc biệt: **có được phép cộng số đo đó theo những chiều phân tích nào hay không?** Nếu không, cùng một tập dữ liệu có thể tạo ra báo cáo đúng ở cấp ngày nhưng sai ở cấp tháng, đúng ở cấp sản phẩm nhưng sai ở cấp khách hàng.

Bài học thuộc chương **Bảng dữ kiện** tập trung vào ba nhóm số đo:

1. **Additive measures** — số đo cộng được trên các chiều phù hợp.
2. **Semi-additive measures** — số đo chỉ cộng được theo một số chiều, thường không cộng được theo thời gian.
3. **Non-additive measures** — số đo không thể được tổng hợp có ý nghĩa bằng phép cộng trực tiếp.

Sau bài này, bạn có thể:

- Phân loại số đo dựa trên **ý nghĩa nghiệp vụ và độ hạt** (*grain*), thay vì dựa vào kiểu `INTEGER` hay `DECIMAL`.
- Phân biệt số đo **luồng phát sinh trong kỳ** với số đo **trạng thái tại một thời điểm**.
- Tính đúng tổng doanh số, tồn kho cuối kỳ, số dư, giá bình quân, tỷ lệ chuyển đổi và số khách duy nhất.
- Nhận ra lỗi **JOIN fanout**, trộn đơn vị/tiền tệ, cộng nhầm giữa các kỳ và cộng nhầm các kết quả `COUNT(DISTINCT)`.
- Thiết kế fact table, SQL truy vấn, bảng tổng hợp và phép thử chất lượng dữ liệu phù hợp.
- Giải thích vì sao lựa chọn star schema, bảng rộng, document hay mô hình phân tích dạng cột không làm biến mất quy tắc tổng hợp số đo.

## 1. Bước đầu tiên: xác định độ hạt trước khi nhìn số đo

**Độ hạt** (*grain*) là lời khẳng định chính xác về **một dòng trong fact table**.

Ví dụ:

~~~text
FACT_ORDER_LINES
    Một dòng = một dòng hàng (order_id, line_no)
    tại thời điểm đơn được xác nhận.

FACT_INVENTORY_DAILY
    Một dòng = một sản phẩm tại một kho
    ở thời điểm chốt tồn kho của một ngày.

FACT_SESSION_DAILY
    Một dòng = một ngày × một kênh
    trong phạm vi các phiên truy cập đủ điều kiện.
~~~

Ba bảng có thể cùng có `date_key`, `product_key` hoặc các cột kiểu số, nhưng **không được tổng hợp giống nhau**.

- `order_line_amount` là **giá trị của một sự kiện đặt hàng**: cộng các sự kiện hợp lệ để có tổng giá trị kỳ.
- `on_hand_units` là **số lượng đang còn tại thời điểm chốt**: cộng cuối thứ Hai với cuối thứ Ba sẽ đếm lại cùng lượng hàng nhiều lần.
- `conversion_rate` là **tỷ lệ được tạo từ tử số và mẫu số**: cộng 10% với 20% không cho tỷ lệ 30% của toàn bộ dữ liệu.

Một nguyên tắc thực hành:

> **Trước khi viết `SUM(measure)`, phải trả lời hai câu hỏi: “một dòng là gì?” và “những dòng được cộng có phải là những phần rời nhau của cùng một đại lượng không?”**

### “Chiều” là gì?

**Dimension** (*chiều phân tích*) là cách phân nhóm hoặc lọc sự kiện: ngày, tháng, sản phẩm, cửa hàng, khách hàng, quốc gia, kênh bán, tiền tệ... Khi nói số đo “cộng được theo chiều sản phẩm” tức là có thể lấy các nhóm sản phẩm **không chồng nhau** và cộng số đo để ra tổng của tập đó.

Tên chiều không tự bảo đảm tính cộng được. Ví dụ một doanh nghiệp có hai cửa hàng cùng sở hữu một lô hàng trong cùng hệ thống ghi nhận: nếu cả hai kho đều báo **toàn bộ lô chung**, cộng theo cửa hàng sẽ đếm trùng. Vì vậy, tính cộng được đòi hỏi **ngữ nghĩa phân bổ và khóa** đúng.

## 2. Ba loại số đo — bảng phân biệt

| Loại số đo | Ý nghĩa | Có thể dùng `SUM` trực tiếp? | Ví dụ điển hình |
|---|---|---|---|
| **Additive** — cộng được | Các dòng hợp lệ biểu diễn những phần không chồng nhau của cùng đại lượng | Có, trên các chiều và phạm vi đo **tương thích** | Giá trị dòng hàng, số lượng bán, số lần nhấp ở mức sự kiện |
| **Semi-additive** — cộng theo một số chiều | Có thể cộng theo vài chiều, nhưng **không** theo tất cả, thường là thời gian | Chỉ theo những chiều được phép và tại cùng một mốc đo | Tồn kho cuối ngày, số dư cuối ngày, lượng người đang hoạt động tại một thời điểm |
| **Non-additive** — không cộng được | Là đơn giá, tỷ lệ, số trung bình, chỉ số phân vị hoặc lượng không thể cộng trực tiếp | Không; cần công thức tổng hợp hoặc dữ liệu gốc | Đơn giá, biên lợi nhuận %, tỷ lệ chuyển đổi, giá bình quân, số khách duy nhất khi nhóm chồng nhau |

Phân loại này **không gắn cứng với kiểu dữ liệu**. `DECIMAL(18,2)` có thể chứa `line_amount` (additive), `account_balance` (semi-additive) hoặc `unit_price` (non-additive). Tương tự, cột `INTEGER` có thể chứa số lượt sự kiện hoặc số dư tồn kho.

**Điều kiện chung:** ngay cả số đo additive vẫn chỉ cộng được khi các dòng được tính **đúng một lần**, có đơn vị và phạm vi tương thích, và cùng định nghĩa KPI. Doanh thu bằng VND và USD không thể cộng như hai số thuần túy mà không có quy tắc chuyển đổi tiền tệ.

## 3. Additive measures — số đo cộng được

### 3.1. Ví dụ giá trị dòng hàng

Giả sử `FACT_ORDER_LINES` ghi **một lần** cho mỗi dòng của đơn đã xác nhận:

| order_id | line_no | confirmed_day | product | quantity | unit_price | discount | booked_amount |
|---|---:|---|---|---:|---:|---:|---:|
| D01 | 1 | 2026-11-01 | Sách A | 2 | 100.000 | 0 | 200.000 |
| D01 | 2 | 2026-11-01 | Bút B | 1 | 50.000 | 10.000 | 40.000 |
| D02 | 1 | 2026-11-02 | Sách A | 1 | 150.000 | 0 | 150.000 |

Giả định tất cả giá trị tiền ở **VND**; `discount` là tổng giảm giá cấp dòng; không có thuế và phí vận chuyển trong số đo này. Khi đó:

\[
\text{booked\_amount}
=\text{quantity}\times\text{unit\_price}
-\text{discount}.
\]

Tổng giá trị hàng được đặt sau giảm giá:

\[
200.000+40.000+150.000=390.000\text{ VND}.
\]

Ta có thể cộng theo:

- **Ngày:** ngày 01/11 là 240.000; ngày 02/11 là 150.000.
- **Sản phẩm:** Sách A là 350.000; Bút B là 40.000.
- **Tháng:** tháng 11 là 390.000.

Với fact ghi **mỗi dòng hàng đúng một lần**, các phép cộng trên cho cùng tổng khi cộng mọi nhóm của **một phân hoạch không chồng nhau**.

### 3.2. “Cộng được” không có nghĩa là muốn cộng gì cũng được

Một số điều kiện phải giữ:

1. **Cùng đơn vị đo:** `quantity` theo “cái”, “kg” và “lít” không nên cộng thành một số lượng chung vô nghĩa. Có thể nhóm theo `unit_of_measure` hoặc quy đổi khi có quy tắc.
2. **Cùng tiền tệ:** VND và USD cần tách nhóm hoặc quy đổi theo tỷ giá, thời điểm và loại tỷ giá đã thống nhất.
3. **Không nhân bản dòng qua JOIN:** mỗi dòng fact phải góp phần đúng một lần vào phép cộng, trừ khi có cơ chế phân bổ hợp lệ.
4. **Cùng nghĩa KPI:** giá trị hàng được đặt không đồng nghĩa doanh thu kế toán, số tiền đã thu hoặc giá trị sau hoàn trả.
5. **Không cộng hai tầng tổng hợp chồng nhau:** không cộng “toàn quốc” với tổng từng miền nếu “toàn quốc” đã bao gồm các miền.

Ví dụ với `quantity`, cộng số chiếc bán theo từng sản phẩm rồi theo tháng là phù hợp nếu cùng đơn vị “chiếc”. Cộng **10 kg gạo + 5 chiếc áo = 15 đơn vị hàng** có thể phục vụ một KPI rất đặc biệt về “số đơn vị theo quy ước”, nhưng không phải tổng khối lượng hoặc tổng số chiếc có nghĩa.

### 3.3. Các đại lượng luồng (*flow*) thường cộng được

Những đại lượng biểu diễn **lượng phát sinh trong một khoảng thời gian** thường có tính cộng được nếu đo lường không chồng nhau:

~~~text
số tiền thu trong từng giao dịch capture
số hàng được bán trong từng dòng giao dịch
số kiện được bàn giao ở từng sự kiện gửi hàng
số kWh điện tiêu thụ trong từng khoảng không chồng lấn
số lượt nhấp khi mỗi event_id được ghi đúng một lần
~~~

**Không đồng nhất flow với số dư:** số tiền thu trong ngày là **lượng tiền phát sinh trong ngày**; số dư tài khoản cuối ngày là **trạng thái tích lũy tại một thời điểm**.

## 4. Semi-additive measures — cộng được theo một số chiều

### 4.1. Tồn kho tại một thời điểm

Một bảng snapshot cuối ngày:

~~~text
FACT_INVENTORY_DAILY(
    snapshot_date,
    warehouse_id,
    product_id,
    on_hand_units
)
~~~

Độ hạt là **một `(snapshot_date, warehouse_id, product_id)` tại thời điểm chốt kho đã định nghĩa**.

Giả sử sản phẩm P01 được đo theo đơn vị “cái”:

| Ngày chốt | Kho HN | Kho HCM | Tổng tồn P01 trong ngày |
|---|---:|---:|---:|
| 2026-11-01 | 10 | 20 | 30 |
| 2026-11-02 | 9 | 25 | 34 |

Ở **cùng ngày 01/11**, nếu hai kho nắm các phần tồn riêng biệt:

\[
10+20=30\text{ cái}.
\]

Ở **cùng ngày 02/11**:

\[
9+25=34\text{ cái}.
\]

Nhưng:

\[
30+34=64
\]

**không phải** tồn kho hai ngày cộng lại theo nghĩa nghiệp vụ thông thường: nhiều sản phẩm đang tồn ngày 01 vẫn còn được ghi trong tồn ngày 02. Đây là **đếm cùng một trạng thái qua thời gian**.

### 4.2. Các kiểu tổng hợp thời gian phù hợp

Nếu câu hỏi là “tồn kho **cuối tháng**”, chọn snapshot tại **mốc chốt cuối tháng** rồi cộng theo kho và sản phẩm phù hợp.

Nếu câu hỏi là “tồn kho **bình quân ngày trong tháng**”, có thể:

1. Tính tổng tồn của **mỗi ngày** trên các kho cần xét.
2. Tính trung bình của các tổng ngày, với kỳ và thời điểm chốt được định nghĩa.

Với hai ngày ví dụ:

\[
\text{average daily on-hand}
=\frac{30+34}{2}=32.
\]

**Điều kiện:** hai ngày là hai snapshot đầy đủ của phạm vi cần xét, mỗi ngày có trọng số như nhau. Nếu dữ liệu thiếu ngày, thiếu kho hoặc các ảnh chụp cách nhau không đều, phép `AVG` trên những dòng hiện có **không tự cho bình quân đúng**. Khi quan sát không đều, có thể cần bình quân **theo thời lượng** (*time-weighted average*) hoặc tái tạo trạng thái tại các mốc đã xác nhận.

Các câu hỏi khác cần cách tính khác:

- **Tồn cao nhất trong tháng:** lấy `MAX` của tổng tồn hằng ngày.
- **Tồn thấp nhất:** lấy `MIN` của tổng tồn hằng ngày.
- **Mức thay đổi tồn từ đầu đến cuối kỳ:** lấy **cuối kỳ trừ đầu kỳ**.
- **Tổng lượng nhập/xuất trong kỳ:** tính từ **sự kiện luồng nhập/xuất**, không từ tổng snapshot.

### 4.3. Số dư tài khoản

`FACT_ACCOUNT_BALANCE_DAILY(date,account_id,balance_amount,currency_code)` lưu **số dư tại cuối ngày**.

- Có thể tổng số dư **của các tài khoản phù hợp tại cùng thời điểm**, khi các số dư không chồng lấn và cùng đơn vị tiền tệ hoặc đã quy đổi đúng.
- Không cộng số dư ngày 01 và ngày 02 để gọi là “tổng tiền hai ngày”.
- Muốn tính **dòng tiền vào/ra** giữa hai mốc, nên dùng fact giao dịch hoặc phép chênh số dư **có xét điều chỉnh, phí, lãi và các dòng tiền liên quan**.

Ví dụ tài khoản có 100 triệu vào ngày 01, 110 triệu vào ngày 02: tổng 210 triệu qua hai ngày không phải số dư; chênh 10 triệu là **biến thiên số dư**, chưa nhất thiết bằng doanh thu hoặc lợi nhuận.

### 4.4. Bảng xác định chiều được cộng

| Số đo | Cộng theo chiều thực thể | Cộng theo thời gian | Phương pháp thời gian thường phù hợp |
|---|---|---|---|
| Số lượng tồn cuối ngày | Có, theo kho/sản phẩm cùng thời điểm và cùng đơn vị, không trùng sở hữu | **Không** | Cuối kỳ, min/max, bình quân có định nghĩa |
| Số dư tài khoản cuối ngày | Có điều kiện: cùng tiền tệ, không trùng phạm vi | **Không** | Cuối kỳ, mức thay đổi, bình quân có trọng số thời gian |
| Số người đang sử dụng dịch vụ lúc 00:00 | Có điều kiện: các nhóm thực sự không chồng nhau | **Không** | Chọn mốc thời gian, peak hoặc trung bình |
| Doanh số phát sinh trong ngày | Có theo nhóm không chồng nhau | **Có** | `SUM` qua các ngày của kỳ |

**Đặc điểm cốt lõi của semi-additive:** phải **nêu rõ chiều nào không được cộng** và quy tắc tổng hợp thay thế. Nếu chỉ gắn nhãn “semi-additive” mà không viết cách tính cuối tháng, dashboard vẫn dễ sai.

## 5. Non-additive measures — không cộng trực tiếp

### 5.1. Đơn giá

Với hai dòng:

~~~text
Dòng A: quantity = 1, unit_price = 100
Dòng B: quantity = 9, unit_price = 10
~~~

`unit_price` không phải “lượng tiền của cả dòng”; cộng `100+10=110` không trả lời một câu hỏi nghiệp vụ về doanh số.

Nếu muốn **giá bán bình quân theo số lượng**, cần:

\[
\text{weighted average price}
=\frac{\sum_i q_i p_i}{\sum_i q_i}
=\frac{1\times100+9\times10}{1+9}
=19.
\]

Trong khi trung bình số học đơn giản của **hai giá theo dòng** là:

\[
\frac{100+10}{2}=55.
\]

Hai kết quả khác nhau vì chúng trả lời hai câu hỏi khác nhau: **giá bình quân mỗi dòng** và **giá bình quân mỗi đơn vị bán**. Cần định nghĩa rõ có tính giảm giá, hoàn tiền, thuế và quy đổi tiền tệ hay không.

### 5.2. Tỷ lệ chuyển đổi, tỷ lệ lỗi, biên lợi nhuận

Giả sử tỷ lệ chuyển đổi được định nghĩa là:

\[
\text{conversion rate}
=\frac{\text{số phiên truy cập đủ điều kiện có ít nhất một chuyển đổi}}
{\text{tổng số phiên truy cập đủ điều kiện}}.
\]

Hai kênh có:

| Kênh | Phiên đủ điều kiện | Phiên có chuyển đổi | Tỷ lệ |
|---|---:|---:|---:|
| A | 100 | 10 | 10% |
| B | 10 | 5 | 50% |

Tỷ lệ chung:

\[
\frac{10+5}{100+10}=\frac{15}{110}\approx13{,}64\%.
\]

**Không** cộng \(10\%+50\%\) và cũng không dùng trung bình đơn giản \((10\%+50\%)/2=30\%\). Kênh A có **mẫu số lớn gấp mười lần** kênh B.

Tương tự:

\[
\text{gross margin rate}
=\frac{\text{revenue}-\text{cost}}{\text{revenue}}
\]

phải được tính từ **tổng revenue và tổng cost tương thích**, không cộng tỷ lệ của từng dòng hoặc từng cửa hàng. Nếu tổng revenue bằng 0, cần quy tắc xử lý mẫu số bằng 0 (ví dụ `NULL`/“không xác định”), không mặc định 0% hay 100%.

### 5.3. Trung bình, phần trăm vị, trung vị

`AVG(duration_ms)`, percentile p95 và median đều không cộng được trực tiếp.

- Trung bình chung có thể tính từ **tổng giá trị** và **số lượng quan sát**: \(\bar x=\sum x/n\).
- Muốn gộp trung bình từ các nhóm rời nhau cần **trọng số theo số quan sát**.
- Median/p95 của toàn bộ dữ liệu **không suy ra được nói chung** chỉ từ median/p95 của từng nhóm. Cần dữ liệu gốc, phân phối đủ thông tin hoặc phương pháp xấp xỉ có sai số được công bố.

Ví dụ, nhóm A có 100 lần đo, p95 = 300 ms và nhóm B có 10 lần đo, p95 = 500 ms. **Không** thể khẳng định p95 toàn hệ thống là 800 ms, 400 ms hay trung bình có trọng số của hai con số đó.

### 5.4. Số khách hàng duy nhất (`COUNT(DISTINCT)`)

Giả sử:

~~~text
Ngày 01: khách {KH01, KH02} => 2 khách
Ngày 02: khách {KH02, KH03} => 2 khách
~~~

Tổng khách **duy nhất trong hai ngày** là \(\{KH01,KH02,KH03\}\), tức **3**, không phải \(2+2=4\).

\[
|A\cup B|=|A|+|B|-|A\cap B|.
\]

`COUNT(DISTINCT customer_id)` trả một **số lượng theo tập**; các tổng số theo ngày, kênh hoặc sản phẩm **không cộng được** khi có thể có khách xuất hiện ở nhiều nhóm.

Nếu phải tính distinct ở quy mô lớn, có thể dùng cấu trúc thống kê/hợp tập hoặc **ước lượng xấp xỉ** như HyperLogLog nếu công nghệ và độ sai số cho phép. Nhưng chỉ cộng các **giá trị đếm distinct đã tính** không đủ để loại trùng.

## 6. Tỷ lệ, trung bình và chỉ số dẫn xuất: nên lưu gì trong fact?

Với một tỷ lệ:

\[
\text{rate}=\frac{n}{d},
\]

cách thiết kế thường đáng tin cậy là giữ **tử số \(n\)** và **mẫu số \(d\)** ở grain phù hợp. Khi báo cáo gộp các nhóm **không chồng nhau**:

\[
\text{rate}_{\text{combined}}
=\frac{\sum_i n_i}{\sum_i d_i}.
\]

Ví dụ:

~~~text
fact_channel_daily(
    event_date,
    channel_id,
    eligible_sessions,
    converted_sessions
)
~~~

Ở đây `eligible_sessions` và `converted_sessions` có thể cộng theo **ngày/kênh** khi mỗi phiên được **gán đúng một nhóm** theo quy tắc attribution đã xác nhận. `conversion_rate` được tính từ hai tổng. Nếu một phiên có thể thuộc hai kênh, tính cộng được theo kênh **không còn tự động đúng**.

### Vì sao không nên chỉ lưu tỷ lệ?

Nếu một bảng chỉ có:

~~~text
channel_id | conversion_rate
A          | 0.10
B          | 0.50
~~~

thì không thể tính tỷ lệ toàn bộ một cách chính xác **nếu không biết mẫu số và định nghĩa tập quan sát**. Giá trị 10% của 100 phiên khác hẳn 10% của 10 triệu phiên.

Vì vậy, trong một số data mart phục vụ báo cáo, có thể **lưu tỷ lệ đã tính** để hiển thị nhanh, nhưng vẫn cần định nghĩa và khả năng truy ngược về các **thành phần có thể tổng hợp** của nó.

### Không phải mọi số đo dẫn xuất đều cần lưu

`booked_amount = quantity × unit_price - line_discount` có thể được **tính lúc truy vấn**, **lưu sẵn trong fact** hoặc **materialize vào aggregate** tùy hiệu năng và yêu cầu audit. Nếu lưu cùng các thành phần, phải kiểm tra chúng tuân theo **công thức, quy tắc làm tròn và tiền tệ đã thống nhất**; tránh hai nguồn chân lý độc lập cho cùng một con số.

## 7. Thiết kế một mô hình dữ kiện minh họa

Ta dùng ba fact phục vụ ba dạng đo:

~~~mermaid
flowchart TD
    D["dim_date"] --> O["fact_order_lines<br/>booked_amount, quantity"]
    P["dim_product"] --> O
    P --> I["fact_inventory_daily<br/>on_hand_units"]
    D --> I
    W["dim_warehouse"] --> I
    D --> C["fact_channel_daily<br/>eligible_sessions, converted_sessions"]
    CH["dim_channel"] --> C
~~~

*Sơ đồ thể hiện các dimension dùng chung, không hàm ý có thể nối trực tiếp ba fact chi tiết vào nhau.*

### 7.1. Khai báo grain và khóa

| Fact | Grain chính xác | Khóa nghiệp vụ minh họa | Loại measure |
|---|---|---|---|
| `fact_order_lines` | Một dòng hàng của một đơn đã xác nhận | `(order_id,line_no)` | `booked_amount`, `quantity`: additive có điều kiện |
| `fact_inventory_daily` | Một sản phẩm × một kho × một ngày chốt | `(snapshot_date,warehouse_id,product_id)` | `on_hand_units`: semi-additive |
| `fact_channel_daily` | Một kênh × một ngày, tính theo tập phiên được gán duy nhất | `(event_date,channel_id)` | Tử số/mẫu số additive có điều kiện; tỷ lệ non-additive |

**Chú ý:** các khóa và grain trên là **giả định của ví dụ**. Nếu một đơn có thể tạo nhiều phiên bản dòng, một snapshot có nhiều thời điểm chốt trong ngày hoặc cùng một phiên được gán nhiều kênh, phải làm rõ và **đổi grain/khóa** trước khi triển khai.

### 7.2. DDL PostgreSQL đơn giản

Ví dụ sau cố ý giữ dimension tối giản; trong hệ thật có thể cần surrogate key cho dimension lịch sử SCD Type 2, phân vùng thời gian, kiểm soát tenant/currency và quy tắc quyền truy cập.

~~~sql
CREATE TABLE dim_date (
    date_key DATE PRIMARY KEY
);

CREATE TABLE dim_product (
    product_id VARCHAR(40) PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL,
    unit_of_measure VARCHAR(30) NOT NULL
);

CREATE TABLE dim_warehouse (
    warehouse_id VARCHAR(40) PRIMARY KEY,
    warehouse_name VARCHAR(200) NOT NULL
);

CREATE TABLE dim_channel (
    channel_id VARCHAR(40) PRIMARY KEY,
    channel_name VARCHAR(100) NOT NULL
);

CREATE TABLE fact_order_lines (
    order_id VARCHAR(40) NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    confirmed_date DATE NOT NULL REFERENCES dim_date(date_key),
    product_id VARCHAR(40) NOT NULL REFERENCES dim_product(product_id),
    quantity NUMERIC(18,3) NOT NULL CHECK (quantity > 0),
    booked_amount NUMERIC(18,2) NOT NULL,
    currency_code CHAR(3) NOT NULL,
    PRIMARY KEY (order_id, line_no)
);

CREATE TABLE fact_inventory_daily (
    snapshot_date DATE NOT NULL REFERENCES dim_date(date_key),
    warehouse_id VARCHAR(40) NOT NULL REFERENCES dim_warehouse(warehouse_id),
    product_id VARCHAR(40) NOT NULL REFERENCES dim_product(product_id),
    on_hand_units NUMERIC(18,3) NOT NULL,
    PRIMARY KEY (snapshot_date, warehouse_id, product_id)
);

CREATE TABLE fact_channel_daily (
    event_date DATE NOT NULL REFERENCES dim_date(date_key),
    channel_id VARCHAR(40) NOT NULL REFERENCES dim_channel(channel_id),
    eligible_sessions BIGINT NOT NULL CHECK (eligible_sessions >= 0),
    converted_sessions BIGINT NOT NULL CHECK (converted_sessions >= 0),
    PRIMARY KEY (event_date, channel_id),
    CHECK (converted_sessions <= eligible_sessions)
);
~~~

Giải thích các quyết định:

- `on_hand_units` có thể âm trong một số hệ thống quản lý tồn âm được phê duyệt; ví dụ không đặt `CHECK >= 0` khi chưa xác nhận chính sách. Nếu nghiệp vụ cấm tồn âm, cần thêm ràng buộc phù hợp.
- `booked_amount` được giả định là giá trị hàng đặt sau điều chỉnh cấp dòng; bản ghi âm có thể là giao dịch điều chỉnh nếu grain có định nghĩa đó. Trong ví dụ fact gốc chỉ chứa dòng xác nhận, cần kiểm soát việc tạo số âm theo hợp đồng KPI.
- `currency_code` buộc mỗi dòng có đơn vị tiền tệ nhưng **không ngăn việc cộng lẫn tiền tệ** trong truy vấn. Báo cáo phải GROUP BY currency hoặc quy đổi.
- `dim_date(date_key)` giúp minh họa khóa ngoại; `DATE` có thể được thay bằng integer date key hoặc cách mã hóa khác theo thiết kế kho dữ liệu.
- Khóa ngoại có thể không được hệ phân tích thực thi trong mọi công nghệ; khi đó pipeline cần phép thử tính toàn vẹn tương ứng.

### 7.3. SQL cho số đo additive

Giá trị hàng đặt theo tháng **và tiền tệ**:

~~~sql
SELECT
    DATE_TRUNC('month', confirmed_date)::date AS order_month,
    currency_code,
    SUM(booked_amount) AS booked_amount
FROM fact_order_lines
GROUP BY
    DATE_TRUNC('month', confirmed_date)::date,
    currency_code
ORDER BY order_month, currency_code;
~~~

Việc GROUP BY `currency_code` ngăn báo cáo cộng VND và USD như cùng một đại lượng. Nếu cần một đơn vị tiền tệ báo cáo, phải có tỷ giá/loại tỷ giá, thời điểm quy đổi và chính sách làm tròn.

### 7.4. SQL đúng cho semi-additive: tồn tại ngày chốt

Tổng tồn theo sản phẩm tại **một ngày cụ thể**, cộng qua các kho không chồng lấn:

~~~sql
SELECT
    product_id,
    SUM(on_hand_units) AS on_hand_units_at_close
FROM fact_inventory_daily
WHERE snapshot_date = DATE '2026-11-30'
GROUP BY product_id;
~~~

Nếu cần **tổng tồn toàn hệ thống vào cuối tháng 11**, phải xác nhận snapshot ngày 30/11 hoàn chỉnh. Không tự dùng `SUM(on_hand_units)` trên cả 30 ngày.

Một bảng periodic snapshot có thể **bỏ vắng** dòng của kho–sản phẩm khi tồn bằng 0 hoặc khi pipeline lỗi; hai trường hợp phải được phân biệt. Khi thiếu snapshot, tổng tồn ngày có thể bị thiếu mà không có cảnh báo. Cần chính sách tạo **dense snapshot** (đầy đủ mọi tổ hợp bắt buộc) hoặc quy tắc biểu diễn giá trị không có bản ghi.

### 7.5. SQL cho bình quân tồn theo ngày

Giả sử bảng có dữ liệu chốt đầy đủ cho từng ngày, và cần bình quân **tổng tồn P01 trên tất cả kho** trong khoảng thời gian:

~~~sql
WITH daily_totals AS (
    SELECT
        snapshot_date,
        SUM(on_hand_units) AS total_units
    FROM fact_inventory_daily
    WHERE product_id = 'P01'
      AND snapshot_date >= DATE '2026-11-01'
      AND snapshot_date <  DATE '2026-12-01'
    GROUP BY snapshot_date
)
SELECT AVG(total_units) AS average_daily_on_hand
FROM daily_totals;
~~~

Đây là **bình quân của các ngày có dữ liệu**. Để gọi là bình quân của **toàn tháng**, phải bảo đảm có đủ ngày/kho theo quy tắc snapshot hoặc **xử lý ngày thiếu** đúng ngữ nghĩa. Không tự coi ngày thiếu là 0 vì có thể pipeline chưa nạp; cũng không tự giả định tồn không đổi nếu nguồn không xác nhận.

### 7.6. SQL cho non-additive: tính tỷ lệ từ các thành phần

~~~sql
SELECT
    DATE_TRUNC('month', event_date)::date AS event_month,
    SUM(eligible_sessions) AS eligible_sessions,
    SUM(converted_sessions) AS converted_sessions,
    SUM(converted_sessions)::numeric
        / NULLIF(SUM(eligible_sessions), 0) AS conversion_rate
FROM fact_channel_daily
GROUP BY DATE_TRUNC('month', event_date)::date
ORDER BY event_month;
~~~

Kết quả `conversion_rate` ở dạng **tỷ lệ từ 0 đến 1**, có thể nhân 100 để hiển thị phần trăm. `NULLIF` tránh chia cho 0; nếu không có phiên đủ điều kiện, tỷ lệ **không xác định**, không mặc nhiên là 0%.

Truy vấn chỉ đúng nếu các kênh tạo **phân hoạch không chồng nhau của tập phiên đủ điều kiện**. Nếu một phiên được ghi vào nhiều kênh, `SUM(eligible_sessions)` cũng đếm trùng và phải thay đổi quy tắc attribution hoặc grain.

## 8. Vì sao `SUM(DISTINCT amount)` không sửa được phép JOIN sai?

Giả sử:

~~~text
fact_order_lines:
(D01, line 1, amount 100)
(D01, line 2, amount 100)

fact_payment_transactions:
(D01, payment P1)
(D01, payment P2)
~~~

Nếu JOIN hai fact chi tiết chỉ theo `order_id`, sẽ có:

\[
2\text{ dòng hàng}\times2\text{ giao dịch thanh toán}=4\text{ dòng nối}.
\]

Khi đó `SUM(booked_amount)` trên dữ liệu JOIN cho **400**, dù giá trị dòng hàng thực tế là **200**.

Thử `SUM(DISTINCT booked_amount)` cũng sai: vì cả hai dòng đều có giá trị 100, tổng chỉ còn **100**. `DISTINCT` trên số tiền loại nhầm **hai giao dịch thật có cùng giá trị**.

### Cách đúng: tổng hợp từng fact ở grain chung

~~~sql
WITH booked_by_order AS (
    SELECT order_id, SUM(booked_amount) AS booked_amount
    FROM fact_order_lines
    GROUP BY order_id
),
paid_by_order AS (
    SELECT order_id, SUM(payment_amount) AS paid_amount
    FROM fact_payment_transactions
    WHERE transaction_type = 'CAPTURE'
    GROUP BY order_id
)
SELECT
    b.order_id,
    b.booked_amount,
    p.paid_amount
FROM booked_by_order AS b
LEFT JOIN paid_by_order AS p
    ON p.order_id = b.order_id;
~~~

`fact_payment_transactions`, `payment_amount` và `transaction_type` là **bảng/cột minh họa bổ sung**, không thuộc DDL trước đó. Các khoản hoàn tiền, thanh toán thất bại, tiền tệ và nhiều lần capture cần được định nghĩa riêng trước khi gọi tổng là “đã thanh toán”.

**Nguyên tắc:** đối với hai bảng fact có grain khác nhau, hãy **tổng hợp mỗi bên về một grain có ý nghĩa chung trước khi JOIN**. Không coi việc có cùng `order_id` là bằng chứng rằng có thể nối trực tiếp từng dòng fact.

### Fanout còn có thể đến từ dimension

Một sản phẩm có nhiều thẻ khuyến mãi, một khách có nhiều địa chỉ hoặc một dimension có nhiều phiên bản SCD Type 2 đều có thể nhân bản dòng fact nếu JOIN thiếu điều kiện:

- Dimension Type 1: JOIN theo khóa đảm bảo một bản ghi tương ứng.
- Dimension SCD Type 2: JOIN theo surrogate key đã resolve **đúng phiên bản** hoặc theo khoảng hiệu lực không chồng lấn.
- Quan hệ nhiều-nhiều: dùng bridge table và quy tắc phân bổ khi cần; nếu chỉ lọc theo việc có quan hệ, dùng phép kiểm tra **tồn tại** (*semijoin/EXISTS*) thay vì nhân dòng.

Ngay cả số đo additive cũng trở nên sai sau một phép JOIN làm trùng hạt.

## 9. Dữ liệu tiền tệ, đơn vị và thời gian là một phần của định nghĩa measure

### 9.1. Tiền tệ

Tổng:

~~~text
100 USD + 100 VND
~~~

không phải **200 đơn vị tiền tệ báo cáo**. Nếu phải quy đổi, cần định nghĩa:

- Tiền tệ gốc và tiền tệ báo cáo.
- Tỷ giá tại thời điểm nào: lúc giao dịch, chốt kỳ, bình quân kỳ, hay chính sách kế toán khác.
- Cách làm tròn và trường hợp thiếu tỷ giá.
- Có được viết lại số tiền lịch sử khi tỷ giá đổi không.

Một số đo tiền chỉ additive **trong cùng đơn vị** hoặc sau khi chuyển đổi theo một quy tắc nhất quán.

### 9.2. Đơn vị đo

`quantity` có thể là kg, chiếc, mét hoặc lít; `unit_of_measure` và **đơn vị cơ sở** phải được mô hình hóa rõ. Tổng số lượng trên nhiều sản phẩm chỉ có nghĩa khi các đơn vị tương thích hoặc phép quy đổi được xác nhận.

Tương tự, số cuộc gọi, số người dùng và số phiên truy cập **không thể cộng thành “tổng hoạt động”** nếu chưa có định nghĩa KPI đặc biệt.

### 9.3. Vai trò của chiều thời gian

Một fact có thể có nhiều thời điểm:

~~~text
confirmed_date
paid_date
shipped_date
refund_date
snapshot_date
ingested_at
~~~

`confirmed_date` dùng tính giá trị **được đặt** trong kỳ; `paid_date` dùng tính tiền **thu**; `snapshot_date` xác định **trạng thái tại mốc chốt**. Thời gian tải `ingested_at` không tự thay thế thời gian nghiệp vụ.

Với số đo semi-additive, phải nói “cuối **kỳ nào**” và quy định mốc lấy snapshot. Chọn “dòng mới nhất có sẵn” có thể khác với chốt cuối tháng nếu bản ghi mới đến trễ hoặc thiếu một số kho.

## 10. Phân loại tính cộng được trong bảng tổng hợp và semantic layer

Nhiều công cụ BI cho phép khai báo `SUM`, `AVG`, `COUNT_DISTINCT` hoặc metric dựa trên biểu thức. Lựa chọn hàm chỉ là **phần kỹ thuật**; quan trọng hơn là quy tắc ngữ nghĩa.

Một bản mô tả measure nên gồm:

| Thuộc tính | Ví dụ `booked_amount` | Ví dụ `on_hand_units` | Ví dụ `conversion_rate` |
|---|---|---|---|
| Grain nguồn | Dòng hàng tại xác nhận đơn | Ngày chốt × kho × sản phẩm | Ngày × kênh |
| Đơn vị | VND theo chính sách KPI | Cái, kg... theo sản phẩm | Tỷ lệ không đơn vị |
| Loại | Additive có điều kiện | Semi-additive | Non-additive |
| Cộng theo thời gian | Có với sự kiện không trùng | Không | Không |
| Cách tổng hợp thời gian | `SUM` | Cuối kỳ, bình quân/ngày có định nghĩa | Tổng tử số / tổng mẫu số |
| Cách tổng hợp theo thực thể | `SUM` khi nhóm rời nhau | `SUM` ở cùng mốc và đơn vị | Tính lại từ thành phần |
| Phạm vi loại trừ | Thuế, ship, hoàn trả (theo ví dụ) | Kho đang kiểm kê, tồn ký gửi...? | Phiên bot, phiên thiếu attribution...? |
| Quy tắc thiếu dữ liệu | Quarantine hoặc cảnh báo | Không mặc nhiên coi thiếu là 0 | Mẫu số 0 → `NULL` |

Một khai báo metric trong **semantic layer** có thể diễn đạt ở mức ý tưởng:

~~~text
metric: booked_amount
source: fact_order_lines
aggregation: sum
grain: order_id + line_no
groupable_by: confirmed_date, product, store
constraints: same currency or approved FX conversion

metric: ending_inventory
source: fact_inventory_daily
aggregation:
    time: select approved end-of-period snapshot
    warehouse/product: sum at same instant and same unit

metric: conversion_rate
source: fact_channel_daily
formula: sum(converted_sessions) / sum(eligible_sessions)
constraints: one eligible session belongs to one attribution group
~~~

Đây là **mã giả mô tả ngữ nghĩa**, không phải cú pháp YAML của một công cụ cụ thể. Khi triển khai, cần ánh xạ đúng khả năng của nền tảng BI/semantic layer và kiểm thử truy vấn sinh ra.

### Một số measure có thể tổng hợp “theo công thức”, dù bản thân non-additive

Tỷ lệ là ví dụ rõ nhất: bản thân `conversion_rate` **không additive**, nhưng **tử số và mẫu số** có thể additive trong ngữ cảnh đúng. Điều này thường được gọi là tổng hợp qua **thành phần đủ** (*sufficient components*).

Trung bình cũng vậy: lưu `sum_value` và `observation_count` giúp tính `SUM(sum_value)/SUM(observation_count)`. Với variance hoặc độ lệch chuẩn, cần các thành phần phù hợp hơn (và thuật toán ổn định số học) thay vì trung bình các variance/standard deviation của từng nhóm.

**Median và percentile** nói chung không thể khôi phục chính xác chỉ từ các giá trị percentile của từng nhóm; có thể cần dữ liệu gốc, histogram phù hợp hoặc cấu trúc tóm tắt được hỗ trợ để gộp với giới hạn sai số đã biết.

## 11. Kiểm thử tính đúng ngay trong pipeline dữ liệu

### 11.1. Không có dòng trùng tại grain

Với `fact_order_lines`:

~~~sql
SELECT order_id, line_no, COUNT(*) AS occurrences
FROM fact_order_lines
GROUP BY order_id, line_no
HAVING COUNT(*) > 1;
~~~

Nếu `PRIMARY KEY` được thực thi, truy vấn thường không có kết quả; kiểm tra này đặc biệt hữu ích trên **staging** hoặc kho phân tích không cưỡng chế khóa.

Với snapshot:

~~~sql
SELECT snapshot_date, warehouse_id, product_id, COUNT(*) AS occurrences
FROM fact_inventory_daily
GROUP BY snapshot_date, warehouse_id, product_id
HAVING COUNT(*) > 1;
~~~

Trùng snapshot có thể dẫn tới cộng đôi tồn kho ngay ở **cùng một ngày**.

### 11.2. Đối chiếu dòng phát sinh với nguồn

Ví dụ, với giả định nguồn dòng hàng xác nhận đã được làm sạch và cùng grain, đối soát:

~~~sql
SELECT
    confirmed_date,
    currency_code,
    COUNT(*) AS line_count,
    SUM(booked_amount) AS booked_amount
FROM fact_order_lines
GROUP BY confirmed_date, currency_code;
~~~

Đối chiếu hai chỉ số này với nguồn ở **cùng ngày nghiệp vụ, trạng thái, tiền tệ và thời điểm chốt**. Chỉ so tổng tiền có thể bỏ sót việc hai lỗi cộng trừ triệt tiêu nhau; nên so cả số dòng và khóa nghiệp vụ khi cần.

### 11.3. Đảm bảo snapshot đầy đủ

Snapshot cuối ngày cần kiểm tra:

- Mỗi tổ hợp `(snapshot_date,warehouse_id,product_id)` bắt buộc có **đúng một dòng**, hoặc có quy tắc rõ cho tổ hợp vắng mặt.
- Mỗi ngày chốt có trạng thái tải hoàn chỉnh ở tất cả kho thuộc phạm vi báo cáo.
- Tồn được đo ở **cùng thời điểm chuẩn**, không trộn chốt giờ địa phương khác nhau mà chưa quy đổi.
- Số lượng có đơn vị phù hợp; số âm có được phép hay không đã được xác nhận.

Một bảng chỉ có khóa duy nhất vẫn có thể **thiếu toàn bộ dữ liệu của một kho**. Vì vậy cần kiểm tra tính đầy đủ theo manifest, expected keys hoặc danh sách kho–sản phẩm hợp lệ, không chỉ kiểm tra trùng.

### 11.4. Kiểm tra tử số và mẫu số

~~~sql
SELECT event_date, channel_id,
       eligible_sessions, converted_sessions
FROM fact_channel_daily
WHERE eligible_sessions < 0
   OR converted_sessions < 0
   OR converted_sessions > eligible_sessions;
~~~

Trong ví dụ, `CHECK` ở DDL đã cưỡng chế các bất biến này. Tuy nhiên **bất biến số học không chứng minh được attribution đúng**: nếu một phiên được đếm hai lần ở hai kênh, các điều kiện vẫn có thể đều đạt nhưng tỷ lệ toàn bộ sai.

### 11.5. Kiểm tra JOIN không nhân grain

Trước và sau khi JOIN dimension, so:

~~~text
COUNT(fact rows before join)
COUNT(rows after join)
COUNT(DISTINCT fact business key after join)
SUM(additive measure before join)
SUM(additive measure after join)
~~~

Nếu JOIN dimension được kỳ vọng **mỗi fact khớp đúng một dòng**, số dòng và tổng additive phải giữ nguyên. Nếu chúng thay đổi, kiểm tra:

- Thiếu dimension làm mất fact.
- Nhiều phiên bản dimension SCD Type 2 cùng khớp.
- JOIN vào bảng một-nhiều như địa chỉ, tag, campaign.
- Dùng khóa nghiệp vụ không có `tenant_id`/phạm vi.

Không cố che sự sai khác bằng `SUM(DISTINCT measure)`.

## 12. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| `SUM(balance)` qua 30 ngày rồi gọi là số dư tháng | Cộng lặp trạng thái cùng tiền qua nhiều thời điểm | Lấy cuối kỳ, biến thiên, hoặc bình quân theo quy tắc |
| Cộng `on_hand_units` theo nhiều ngày | Đếm cùng hàng nhiều lần | Giữ ngày chốt cố định trước khi cộng kho/sản phẩm |
| `AVG(conversion_rate)` của các kênh | Không xét mẫu số khác nhau | `SUM(converted)/SUM(eligible)` |
| `SUM(unit_price)` | Đơn giá không phải lượng tiền của cả dòng | Tính tổng tiền rồi chia tổng số lượng nếu cần giá bình quân |
| Cộng `COUNT(DISTINCT customers)` theo ngày | Khách lặp giữa các ngày | Tính distinct trên toàn kỳ hoặc gộp tập/sketch phù hợp |
| `SUM(amount)` sau JOIN với bảng địa chỉ một-nhiều | Fact bị nhân dòng | Sửa grain JOIN hoặc tổng hợp/bridge có trọng số |
| `SUM(DISTINCT amount)` để chữa fanout | Hai giao dịch hợp lệ có thể có cùng số tiền | Không `DISTINCT` trên giá trị measure |
| Cộng tiền VND và USD | Đơn vị không tương thích | GROUP BY currency hoặc quy đổi có kiểm soát |
| Cộng kg và cái | Số lượng không cùng đơn vị | Nhóm theo unit hoặc chuyển đổi phù hợp |
| Lấy snapshot mới nhất có sẵn làm cuối tháng | Có thể thiếu ngày chốt hoặc thiếu kho | Kiểm tra mốc snapshot được phê duyệt và tính đầy đủ |
| Trung bình của trung bình từng nhóm | Trọng số quan sát khác nhau | Lưu tổng và số quan sát để tính lại |
| Cộng p95 của từng vùng | Percentile không cộng được | Dùng phân phối/dữ liệu gốc hoặc thuật toán xấp xỉ hợp lệ |
| Trộn booked, paid và refunded trong cùng `amount` không phân loại | KPI không còn nghĩa rõ | Tách sự kiện, dùng cột loại và định nghĩa rõ phép tổng |
| Coi số đo additive bất kể dữ liệu trùng | Trùng sự kiện tạo tổng sai | Khóa nghiệp vụ, idempotency và đối soát |

## 13. Liên hệ với các mô hình dữ liệu khác

### Quan hệ và star schema

Trong một star schema, fact thể hiện **sự kiện hoặc trạng thái tại grain xác định**, dimension cung cấp ngữ cảnh. Tính additive/semi-additive/non-additive quyết định **công thức truy vấn** và cách thiết kế bảng tổng hợp. Một cấu trúc đạt dạng chuẩn nào đó không tự bảo đảm `SUM` đúng khi JOIN làm nhân dòng.

### Document

Một document đơn hàng có thể chứa nhiều dòng hàng. Nếu cần tính tổng `booked_amount` theo sản phẩm, phải **trải mảng dòng hàng thành đúng grain** và chỉ tính giá trị cấp dòng. Nếu đem `order_total` cấp đơn lặp trên mỗi phần tử mảng, số tiền có thể bị nhân lên.

### Đồ thị

Các cạnh có thể biểu diễn giao dịch hoặc quan hệ; truy vấn đồ thị đếm **đường đi** có thể cho số lớn hơn số giao dịch, vì một sự kiện có thể được truy cập qua nhiều đường đi. Trước khi tính KPI, cần xác định một đối tượng đo duy nhất: event, edge, node hay đường đi có định nghĩa.

### Kho phân tích dạng cột và data lake

Engine lưu trữ cột thường phù hợp `SUM`/quét dữ liệu lớn, nhưng **hiệu năng của phép tổng không sửa được lỗi ngữ nghĩa**. Phân vùng theo ngày giúp lọc snapshot hoặc sự kiện, nhưng hệ thống vẫn cần:

- Quy tắc chọn **ngày chốt** cho semi-additive.
- Quy tắc xử lý **đơn vị/tiền tệ**.
- Phân vùng và grain bảo vệ khỏi **trùng sự kiện khi nạp lại**.
- Dữ liệu hỗ trợ **tính lại tỷ lệ và distinct** đúng phạm vi.

Một materialized aggregate chỉ an toàn khi biết phép tổng hợp nào có thể được gộp tiếp. Tổng `booked_amount` theo ngày có thể cộng thành tháng; tỷ lệ chuyển đổi theo ngày **không thể** cộng trực tiếp thành tỷ lệ tháng.

## 14. Bài luyện tập có lời giải

### Bài 1 — Phân loại ba số đo

Một kho dữ liệu có `sales_amount` cho mỗi dòng bán, `on_hand_units` cuối ngày và `conversion_rate` theo kênh. Hãy phân loại.

**Lời giải:** `sales_amount` là **additive** với các chiều/phạm vi thích hợp nếu các dòng không trùng và tiền tệ đồng nhất. `on_hand_units` **semi-additive**: cộng qua kho/sản phẩm ở cùng thời điểm, không cộng qua ngày. `conversion_rate` **non-additive**: cần tổng tử số chia tổng mẫu số theo định nghĩa phiên.

### Bài 2 — Tồn kho cuối kỳ

Ngày 01: kho A có 10, kho B có 20. Ngày 02: kho A có 9, kho B có 25. Cả hai đều là snapshot đầy đủ cuối ngày. Tổng tồn cuối ngày 02 là bao nhiêu? Có được gọi `10+20+9+25=64` là tồn trong hai ngày không?

**Lời giải:** Cuối ngày 02 là \(9+25=34\) đơn vị. \(64\) là tổng **bốn quan sát snapshot**, không phải một lượng tồn kho có nghĩa. Nếu cần bình quân tổng tồn hai ngày với trọng số ngày bằng nhau, kết quả \((30+34)/2=32\).

### Bài 3 — Tỷ lệ chuyển đổi toàn bộ

Kênh A có 100 phiên, 10 phiên chuyển đổi; kênh B có 10 phiên, 5 phiên chuyển đổi. Tỷ lệ tổng?

**Lời giải:** \((10+5)/(100+10)=15/110\approx13{,}64\%\). Không lấy trung bình \((10\%+50\%)/2=30\%\).

### Bài 4 — Đơn giá bình quân

Một dòng bán 1 sản phẩm giá 100; dòng khác bán 9 sản phẩm giá 10. Tính giá bình quân **theo số lượng**.

**Lời giải:** \((1\times100+9\times10)/(1+9)=19\). Trung bình theo **dòng hàng** là 55, nhưng đó là chỉ số khác.

### Bài 5 — Đếm khách duy nhất

Ngày 1 có `{KH1, KH2}`; ngày 2 có `{KH2, KH3}`. Mỗi ngày có hai khách duy nhất. Tháng có mấy khách duy nhất?

**Lời giải:** **3** khách: `KH1, KH2, KH3`. Không thể cộng \(2+2=4\) vì `KH2` thuộc cả hai ngày.

### Bài 6 — Cộng tiền khác đơn vị

Fact bán hàng chứa hai dòng: `100 USD` và `100 VND`. Có thể báo “tổng 200” không?

**Lời giải:** Không. Giữ hai tổng theo tiền tệ, hoặc chuyển đổi sang một đồng tiền báo cáo theo tỷ giá, thời điểm và chính sách làm tròn đã xác nhận. `SUM(amount)` không có `currency_code` là sai ý nghĩa.

### Bài 7 — Nhân dòng khi JOIN hai fact

Đơn D01 có hai dòng hàng, mỗi dòng `amount=100`, và có hai lần thanh toán. JOIN theo `order_id` cho bao nhiêu dòng? Vì sao `SUM(DISTINCT amount)` sai?

**Lời giải:** Có \(2\times2=4\) dòng. `SUM(amount)` cho 400 thay vì 200. `SUM(DISTINCT amount)` chỉ cho 100 vì hai dòng thật cùng giá trị 100. Đúng hơn là tổng hợp riêng tiền đặt và thanh toán theo đơn trước khi JOIN.

### Bài 8 — Bình quân tồn thiếu snapshot

Trong tháng 30 ngày, kho chỉ có dữ liệu snapshot của 25 ngày. Có nên dùng `AVG(on_hand_units)` trên 25 bản ghi và gọi đó là “tồn bình quân tháng” không?

**Lời giải:** Không mặc định. Chỉ có thể gọi đó là bình quân **của 25 ngày được quan sát**. Phải xác định vì sao thiếu năm ngày: không có tồn, chưa nạp, ngừng hoạt động hay snapshot theo sự kiện. Nếu cần bình quân toàn tháng, phải có chính sách tái tạo/ghi nhận số liệu cho tất cả ngày hợp lệ và cách xử lý ngày thiếu.

### Bài 9 — Trung bình của các nhóm

Nhóm A có tổng thời gian xử lý 1.000 ms từ 10 yêu cầu; nhóm B có tổng 18.000 ms từ 90 yêu cầu. Thời gian xử lý bình quân toàn bộ là bao nhiêu?

**Lời giải:** \((1.000+18.000)/(10+90)=190\) ms. Bình quân nhóm A là 100 ms, nhóm B là 200 ms; lấy trung bình đơn giản hai nhóm cho 150 ms và **sai** vì hai nhóm có số yêu cầu khác nhau. Công thức đúng dùng **tổng thời gian chia tổng số yêu cầu**.

### Bài 10 — Cộng doanh thu theo danh mục nhưng đếm đơn

Đơn D01 có dòng ở danh mục A và B; đơn D02 chỉ có danh mục A. `COUNT(DISTINCT order_id)` cho từng danh mục là A = 2, B = 1. Có được suy tổng số đơn toàn hệ thống là 3 không?

**Lời giải:** Không. Tổng số đơn duy nhất là **2** (`D01,D02`). Phần khách/đơn thuộc nhiều nhóm bị đếm lại khi cộng các `COUNT(DISTINCT)` theo danh mục. Trong khi đó **giá trị hàng cấp dòng** vẫn có thể cộng theo các danh mục nếu mỗi dòng được gán đúng một danh mục tại thời điểm báo cáo.

### Bài 11 — Phân loại một bảng ratio đã tổng hợp

`fact_channel_daily` lưu `eligible_sessions`, `converted_sessions` và `conversion_rate` theo ngày/kênh. Khi làm báo cáo tháng có nên dùng `SUM(conversion_rate)`?

**Lời giải:** Không. Giữ hoặc tính lại từ hai thành phần: `SUM(converted_sessions)/NULLIF(SUM(eligible_sessions),0)`. Chỉ đúng khi các tập phiên được gán kênh không chồng nhau và có cùng định nghĩa chuyển đổi.

## 15. Checklist trước khi dùng số đo trong dashboard

- [ ] Đã xác định **độ hạt của fact** bằng một câu rõ ràng và có khóa tương ứng.
- [ ] Mỗi measure có **tên, đơn vị, quy tắc tính, thời điểm và phạm vi nghiệp vụ**.
- [ ] Đã phân loại **additive / semi-additive / non-additive** cho từng measure.
- [ ] Với additive: chỉ cộng những dòng **không trùng**, không chồng lấn và **cùng đơn vị**.
- [ ] Với semi-additive: quy định **chiều không được cộng** và công thức cuối kỳ/bình quân/biến thiên.
- [ ] Với tỷ lệ/trung bình: giữ được **tử số, mẫu số, tổng và số quan sát** phù hợp để tổng hợp lại.
- [ ] Với distinct count: không cộng số distinct của các tập **có thể chồng nhau**.
- [ ] Không dùng `SUM(DISTINCT measure)` để che một phép JOIN nhân bản dòng.
- [ ] Các JOIN fact–dimension và fact–fact đã được kiểm tra **cardinality**.
- [ ] Tiền tệ/đơn vị đo và cách quy đổi được ghi rõ; không trộn số liệu không tương thích.
- [ ] Snapshot có **ngày chốt, phạm vi đầy đủ** và quy tắc xử lý ngày thiếu.
- [ ] Đã phân biệt `booked`, `paid`, `refunded`, `balance`, `flow` và các thời điểm của chúng.
- [ ] Có kiểm thử trùng khóa, số dòng, missing dimension, snapshot completeness và đối soát nguồn.
- [ ] Những metric materialized được kiểm tra khả năng **gộp tiếp** qua ngày, tháng và chiều.
- [ ] Truy vấn thực tế đã được thử trên dữ liệu phản ví dụ và kiểm tra kết quả với người sở hữu KPI.

**Ghi nhớ:** **Additive** có thể cộng các phần rời nhau của cùng đại lượng; **semi-additive** chỉ cộng trên những chiều phù hợp, thường không qua thời gian; **non-additive** cần công thức thay thế, dữ liệu gốc hoặc các thành phần tổng hợp đủ thông tin. Muốn xây báo cáo đúng, hãy bắt đầu từ **grain, ngữ nghĩa của measure, phạm vi và đơn vị**, rồi mới chọn `SUM`, `AVG`, `COUNT(DISTINCT)` hay một phép tổng hợp khác.

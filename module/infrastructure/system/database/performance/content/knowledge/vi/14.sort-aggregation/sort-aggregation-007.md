# Hàm cửa sổ: phân vùng, sắp xếp và kích thước khung tính toán

## Hàm cửa sổ giải quyết bài toán gì?

Hàm cửa sổ (window function) tính toán trên một tập hàng có liên quan đến hàng hiện tại nhưng vẫn giữ từng hàng đầu vào trong kết quả. Khác với GROUP BY, phép tổng hợp nhóm thường gom nhiều hàng thành một hàng cho mỗi nhóm; hàm cửa sổ bổ sung kết quả tính toán vào từng hàng mà không làm mất chi tiết ban đầu.

Ví dụ, báo cáo đơn hàng có thể cần hiển thị từng giao dịch, tổng doanh thu của khách hàng, thứ hạng đơn hàng trong từng khách hàng và tổng lũy kế theo thời gian. Nếu chỉ dùng GROUP BY, truy vấn sẽ gom các đơn hàng và không còn từng giao dịch. Hàm cửa sổ cho phép giữ chi tiết đơn hàng đồng thời tính tổng hoặc thứ hạng trên nhóm liên quan.

Trong tối ưu hiệu năng cơ sở dữ liệu, hàm cửa sổ cần được xem xét cùng ba thành phần của mệnh đề OVER:

- **PARTITION BY:** chia tập hàng thành các phân vùng độc lập để tính toán.
- **ORDER BY:** xác định thứ tự hàng bên trong mỗi phân vùng cho các hàm phụ thuộc thứ tự.
- **Frame clause:** xác định tập con hàng mà hàm hiện tại được phép xem xét tại mỗi hàng.

Cách chọn phân vùng, thứ tự và kích thước khung có ảnh hưởng trực tiếp đến tính đúng đắn, số lượng phép sắp xếp, bộ nhớ làm việc, khả năng đọc tuần tự và nguy cơ tràn ra vùng lưu trữ tạm. Một truy vấn cửa sổ có thể ngắn nhưng phải sắp xếp hàng triệu bản ghi hoặc giữ một phân vùng rất lớn trong bộ nhớ.

Bài học này hướng dẫn cách hiểu PARTITION BY, ORDER BY và các loại frame ROWS, RANGE, GROUPS; cách tránh lỗi do giá trị đồng hạng và frame mặc định; đồng thời chỉ ra cách đọc execution plan và tối ưu chi phí sort, aggregate và bộ nhớ.

## Cấu trúc cơ bản của OVER

Một hàm cửa sổ có dạng tổng quát:

~~~sql
function_name(expression) OVER (
    PARTITION BY partition_expression
    ORDER BY sort_expression
    frame_clause
)
~~~

Các thành phần không bắt buộc đều phải xuất hiện. Ví dụ:

~~~sql
SELECT
    order_id,
    customer_id,
    order_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY customer_id
    ) AS customer_total
FROM orders;
~~~

Truy vấn trên tính tổng amount cho từng customer_id và hiển thị tổng đó trên mọi hàng của khách hàng. Không có ORDER BY nên frame mặc định của nhiều hệ quản trị là toàn bộ phân vùng; với phép tổng hợp này, mỗi hàng cùng khách hàng nhận cùng một tổng.

Nếu thêm ORDER BY:

~~~sql
SELECT
    order_id,
    customer_id,
    order_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY customer_id
        ORDER BY order_date
    ) AS running_total
FROM orders;
~~~

Mục tiêu thường là tổng lũy kế theo thời gian. Tuy nhiên, nếu nhiều đơn có cùng order_date, kết quả còn phụ thuộc frame mặc định và cách hệ quản trị xử lý các hàng đồng hạng (peers). Khi cần tổng lũy kế theo từng hàng, nên khai báo frame và thứ tự ổn định một cách tường minh.

### PARTITION BY: chia nhóm tính toán

PARTITION BY chia các hàng thành các phân vùng. Mỗi phân vùng được xử lý độc lập; hàm cửa sổ không nhìn sang phân vùng khác.

Ví dụ:

~~~sql
SELECT
    department_id,
    employee_id,
    salary,
    AVG(salary) OVER (
        PARTITION BY department_id
    ) AS department_avg_salary
FROM employees;
~~~

Mỗi nhân viên nhận mức lương trung bình của phòng ban tương ứng. Nếu bỏ PARTITION BY, hàm sẽ tính trên toàn bộ tập hàng mà cửa sổ áp dụng.

Có thể dùng nhiều cột trong PARTITION BY, ví dụ tenant_id và customer_id. Điều này tạo một phân vùng cho mỗi cặp giá trị. Cần chọn đúng khóa nghiệp vụ; bỏ tenant_id trong hệ thống đa tenant có thể khiến các hàng của nhiều tenant bị tính chung.

PARTITION BY không đồng nghĩa với bảng đã được partition vật lý. Đây là nhóm logic của hàm cửa sổ. Bảng có thể không được phân vùng lưu trữ, và ngược lại một bảng được partition vật lý vẫn có thể dùng PARTITION BY khác trong truy vấn.

### ORDER BY: xác định thứ tự trong phân vùng

ORDER BY bên trong OVER quyết định thứ tự mà hàm cửa sổ sử dụng. Nó không nhất thiết quyết định thứ tự cuối cùng mà truy vấn trả về cho người dùng. Muốn kết quả hiển thị có thứ tự, vẫn cần ORDER BY ở cấp truy vấn ngoài.

Ví dụ:

~~~sql
SELECT
    order_id,
    customer_id,
    order_date,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY order_date, order_id
    ) AS order_sequence
FROM orders
ORDER BY customer_id, order_date, order_id;
~~~

ORDER BY bên trong cửa sổ đánh số đơn hàng theo từng khách hàng. ORDER BY bên ngoài sắp xếp kết quả trả về. Hai mệnh đề có mục đích riêng và có thể không giống nhau.

Nếu cột sắp xếp không duy nhất, thứ tự giữa các hàng đồng hạng có thể không xác định. Với ROW_NUMBER, hãy thêm khóa duy nhất làm tiêu chí phụ khi cần kết quả lặp lại ổn định. Với RANK hoặc DENSE_RANK, không thêm khóa phụ nếu nghiệp vụ muốn các hàng có cùng điểm hoặc cùng thời gian giữ chung thứ hạng.

## Các nhóm hàm cửa sổ phổ biến

### Hàm xếp hạng

| Hàm | Cách hoạt động | Ví dụ sử dụng |
|---|---|---|
| ROW_NUMBER() | Đánh số liên tiếp từng hàng, không đồng hạng | Chọn một bản ghi mới nhất theo nhóm |
| RANK() | Các hàng đồng hạng nhận cùng hạng; hạng kế tiếp có khoảng nhảy | Xếp hạng cuộc thi có đồng điểm |
| DENSE_RANK() | Các hàng đồng hạng nhận cùng hạng; hạng kế tiếp không có khoảng nhảy | Xếp hạng mức lương khác nhau |
| NTILE(n) | Chia hàng thành n nhóm gần bằng nhau | Chia khách hàng thành các phân vị |

Ví dụ:

~~~sql
SELECT
    department_id,
    employee_id,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    ) AS row_no,
    RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC
    ) AS salary_rank,
    DENSE_RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC
    ) AS dense_salary_rank
FROM employees;
~~~

Giả sử một phòng ban có mức lương 100, 90, 90 và 80:

- ROW_NUMBER có thể trả 1, 2, 3, 4; thứ tự giữa hai người lương 90 cần tiêu chí phụ ổn định.
- RANK trả 1, 2, 2, 4.
- DENSE_RANK trả 1, 2, 2, 3.

### Hàm tổng hợp dạng cửa sổ

Các hàm SUM, AVG, COUNT, MIN và MAX có thể dùng với OVER để tính trên phân vùng hoặc frame.

~~~sql
SELECT
    order_id,
    customer_id,
    order_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY customer_id
    ) AS customer_total,
    AVG(amount) OVER (
        PARTITION BY customer_id
    ) AS customer_average
FROM orders;
~~~

Không có GROUP BY nên kết quả vẫn có một hàng cho mỗi đơn hàng đầu vào. Tổng và trung bình được lặp lại trên các hàng cùng khách hàng.

### Hàm truy cập hàng lân cận

LAG và LEAD đọc giá trị từ hàng trước hoặc hàng sau theo thứ tự cửa sổ. Chúng hữu ích cho so sánh kỳ trước, phát hiện thay đổi và tính chênh lệch.

~~~sql
SELECT
    account_id,
    transaction_time,
    balance,
    LAG(balance) OVER (
        PARTITION BY account_id
        ORDER BY transaction_time, transaction_id
    ) AS previous_balance,
    balance - LAG(balance) OVER (
        PARTITION BY account_id
        ORDER BY transaction_time, transaction_id
    ) AS balance_change
FROM account_transactions;
~~~

LAG/LEAD không cần frame trong nhiều hệ quản trị; chúng dựa vào thứ tự phân vùng. Nếu timestamp trùng nhau, thêm khóa giao dịch để xác định thứ tự. Có thể truyền giá trị offset và giá trị mặc định, nhưng cú pháp chi tiết tùy hệ quản trị.

### Hàm lấy giá trị đầu/cuối

FIRST_VALUE và LAST_VALUE lấy giá trị ở đầu hoặc cuối frame hiện tại, không nhất thiết là đầu/cuối toàn bộ phân vùng.

~~~sql
SELECT
    customer_id,
    order_date,
    order_id,
    amount,
    FIRST_VALUE(amount) OVER (
        PARTITION BY customer_id
        ORDER BY order_date, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_order_amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY customer_id
        ORDER BY order_date, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_order_amount
FROM orders;
~~~

Một lỗi phổ biến là dùng LAST_VALUE với ORDER BY nhưng không chỉ định frame. Frame mặc định thường kết thúc ở hàng hiện tại hoặc nhóm peer hiện tại; vì vậy LAST_VALUE có thể trả giá trị của hàng hiện tại hoặc hàng cuối của nhóm đồng hạng thay vì giá trị cuối toàn phân vùng. Khi muốn giá trị cuối toàn phân vùng, hãy chỉ định rõ frame từ UNBOUNDED PRECEDING đến UNBOUNDED FOLLOWING hoặc frame tương đương được hệ quản trị hỗ trợ.

## Frame là gì?

Frame là cửa sổ con bên trong phân vùng, được xác định tương đối với hàng hiện tại. Nó quyết định những hàng nào tham gia phép tính ở hàng đó. Frame thường quan trọng với hàm tổng hợp, FIRST_VALUE, LAST_VALUE và một số hàm khác; một số hàm xếp hạng hoặc LAG/LEAD có quy tắc riêng và không sử dụng frame theo cùng cách.

Cấu trúc frame phổ biến:

~~~sql
{ ROWS | RANGE | GROUPS }
BETWEEN frame_start AND frame_end
~~~

Các biên thường gặp:

- UNBOUNDED PRECEDING: bắt đầu từ đầu phân vùng.
- n PRECEDING: lùi n hàng, giá trị hoặc nhóm peer tùy loại frame.
- CURRENT ROW: hàng hiện tại; với RANGE/GROUPS có thể bao gồm các hàng đồng hạng.
- n FOLLOWING: tiến n hàng, giá trị hoặc nhóm peer.
- UNBOUNDED FOLLOWING: kết thúc ở cuối phân vùng.

Frame có thể chỉ định một biên hoặc dùng BETWEEN để chỉ rõ cả hai. Không phải mọi hệ quản trị đều hỗ trợ mọi dạng offset của RANGE/GROUPS giống nhau; cần kiểm tra cú pháp và kiểu dữ liệu được hỗ trợ.

### ROWS: đếm hàng vật lý trong thứ tự cửa sổ

ROWS xác định frame bằng số hàng trước hoặc sau hàng hiện tại theo thứ tự cửa sổ.

Ví dụ tổng của 3 hàng gần nhất, gồm hàng hiện tại:

~~~sql
SELECT
    account_id,
    transaction_time,
    transaction_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY transaction_time, transaction_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_3_transactions
FROM account_transactions;
~~~

Mỗi hàng tính tổng của tối đa ba giao dịch: hai hàng đứng trước và hàng hiện tại. Ở đầu phân vùng, frame tự thu hẹp vì không có đủ hàng trước.

ROWS phù hợp khi yêu cầu được diễn đạt theo số lượng bản ghi, ví dụ 7 giao dịch gần nhất hoặc 10 sự kiện gần nhất. Nếu ORDER BY không duy nhất, thứ tự của các hàng đồng hạng có thể không ổn định. Với ROWS, điều này có thể làm thay đổi hàng nào nằm trong frame. Hãy thêm khóa phân định thứ tự khi nghiệp vụ yêu cầu.

### RANGE: xác định frame theo giá trị sắp xếp và peer

RANGE xác định frame dựa trên giá trị của biểu thức ORDER BY và nhóm peer có cùng giá trị sắp xếp. Với RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW, frame bao gồm từ đầu phân vùng đến giá trị hiện tại, gồm mọi hàng có cùng giá trị ORDER BY với hàng hiện tại.

Ví dụ:

~~~sql
SELECT
    customer_id,
    order_date,
    order_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY customer_id
        ORDER BY order_date
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_by_date
FROM orders;
~~~

Nếu một khách hàng có nhiều đơn cùng ngày, tất cả đơn của ngày đó có thể nhận cùng tổng lũy kế đến hết ngày, vì chúng là peer theo order_date. Đây có thể là kết quả mong muốn nếu nghiệp vụ tính theo ngày.

Một số hệ quản trị hỗ trợ RANGE với offset giá trị, chẳng hạn khoảng thời gian hoặc số học trên giá trị ORDER BY; cú pháp và giới hạn khác nhau. Ví dụ PostgreSQL có thể hỗ trợ frame theo khoảng thời gian với một cột ORDER BY phù hợp:

~~~sql
-- Ví dụ PostgreSQL: tổng trong 7 ngày tính đến thời điểm hiện tại
SELECT
    account_id,
    event_time,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY event_time
        RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW
    ) AS rolling_7_days
FROM account_events;
~~~

Cần xác nhận kiểu ORDER BY, quy tắc biên thời gian và hỗ trợ của phiên bản. Với timestamp có múi giờ, hãy xác định rõ “7 ngày” theo thời gian lịch hay khoảng thời lượng thực tế.

### GROUPS: đếm nhóm peer

GROUPS xác định frame theo số nhóm peer trước hoặc sau nhóm hiện tại. Các hàng có cùng giá trị ở toàn bộ biểu thức ORDER BY được xem là một nhóm peer.

Ví dụ:

~~~sql
SELECT
    department_id,
    salary,
    employee_id,
    SUM(salary) OVER (
        PARTITION BY department_id
        ORDER BY salary
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS current_and_previous_salary_group
FROM employees;
~~~

Frame gồm nhóm lương hiện tại và nhóm lương thấp hơn liền trước theo thứ tự tăng dần. Nếu một nhóm có nhiều nhân viên cùng mức lương, tất cả họ cùng thuộc một peer group. GROUPS hữu ích khi nghiệp vụ muốn tính theo mức giá trị khác nhau thay vì số hàng riêng lẻ.

GROUPS được hỗ trợ ở một số hệ quản trị hiện đại nhưng không có ở mọi sản phẩm hoặc phiên bản. Nếu không được hỗ trợ, có thể phải tạo nhóm giá trị trước bằng DENSE_RANK hoặc phép tổng hợp rồi nối lại, nhưng cần kiểm tra ngữ nghĩa và chi phí.

## Frame mặc định và lỗi thường gặp

### Frame mặc định khi có ORDER BY

Khi có ORDER BY nhưng không ghi frame, nhiều hệ quản trị sử dụng frame mặc định tương đương:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Điều này có nghĩa phép tổng hợp thường tính từ đầu phân vùng đến hàng hiện tại và tất cả hàng peer có cùng giá trị ORDER BY. Chi tiết mặc định có thể phụ thuộc hệ quản trị và loại hàm; hãy đọc tài liệu phiên bản đang dùng.

Ví dụ:

~~~sql
SELECT
    event_time,
    amount,
    SUM(amount) OVER (ORDER BY event_time) AS running_total
FROM events;
~~~

Nếu có nhiều sự kiện cùng event_time, các hàng cùng thời điểm có thể nhận cùng tổng. Nếu muốn tổng lũy kế theo từng hàng riêng biệt, dùng thứ tự xác định và ROWS:

~~~sql
SELECT
    event_time,
    event_id,
    amount,
    SUM(amount) OVER (
        ORDER BY event_time, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total_by_event
FROM events;
~~~

### Không có ORDER BY

Nếu không có ORDER BY, frame mặc định của nhiều hệ quản trị là toàn bộ phân vùng. Với SUM hoặc AVG, kết quả thường giống nhau trên mọi hàng trong phân vùng.

Không nên dựa vào thứ tự vật lý của bảng để suy ra thứ tự cửa sổ. Nếu kết quả phụ thuộc thứ tự, phải khai báo ORDER BY.

### Peers và tie handling

Peer là các hàng có cùng giá trị ở tất cả biểu thức ORDER BY trong cửa sổ. Với RANK, DENSE_RANK và RANGE/GROUPS, peers có ý nghĩa trực tiếp. Với ROW_NUMBER, các hàng đồng hạng vẫn nhận số khác nhau, nhưng thứ tự giữa chúng không được bảo đảm nếu thiếu tiêu chí phân định.

Ví dụ, nếu xếp hạng nhân viên theo salary giảm dần, không thêm employee_id vào ORDER BY của RANK nếu hai người cùng lương phải đồng hạng. Có thể dùng một ORDER BY riêng cho ROW_NUMBER nếu cần chọn duy nhất một người trong nhóm.

### Frame không đúng làm sai LAST_VALUE

Ví dụ sau thường không trả mức lương cao nhất cuối phân vùng như người viết mong đợi:

~~~sql
LAST_VALUE(salary) OVER (
    PARTITION BY department_id
    ORDER BY salary
)
~~~

Do frame mặc định kết thúc tại hàng hiện tại hoặc peer hiện tại, kết quả thường là giá trị cuối của frame hiện thời. Nếu mục tiêu là mức lương cuối theo thứ tự tăng dần trong toàn phòng ban:

~~~sql
LAST_VALUE(salary) OVER (
    PARTITION BY department_id
    ORDER BY salary, employee_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
~~~

Nếu mục tiêu thực sự là mức lương lớn nhất, MAX(salary) OVER (PARTITION BY department_id) thường đơn giản và rõ ý hơn. Chọn hàm theo nghiệp vụ, không dùng LAST_VALUE chỉ vì muốn lấy “giá trị cuối”.

## Các mẫu truy vấn thực tế

### Tổng lũy kế theo tài khoản

~~~sql
SELECT
    account_id,
    transaction_time,
    transaction_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY transaction_time, transaction_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS balance_change_to_date
FROM account_transactions;
~~~

Đây là tổng lũy kế các khoản thay đổi. Nếu cần số dư thực, phải cộng số dư đầu kỳ hoặc dùng dữ liệu số dư đúng theo mô hình nghiệp vụ. Cửa sổ phải có thứ tự xác định; transaction_id được dùng làm tiêu chí phụ khi thời điểm trùng nhau.

### Trung bình trượt theo 7 hàng

~~~sql
SELECT
    sensor_id,
    measured_at,
    reading,
    AVG(reading) OVER (
        PARTITION BY sensor_id
        ORDER BY measured_at, measurement_id
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_average_7_rows
FROM sensor_readings;
~~~

Frame này là tối đa 7 bản ghi, không phải 7 ngày. Nếu cảm biến gửi dữ liệu không đều, bảy hàng có thể bao phủ vài phút hoặc nhiều ngày. Để tính 7 ngày, cần frame theo RANGE trên biểu thức thời gian nếu hệ quản trị hỗ trợ, hoặc lọc/ghép theo khoảng thời gian bằng chiến lược khác.

### Chọn bản ghi mới nhất trong mỗi nhóm

~~~sql
WITH ranked AS (
    SELECT
        customer_id,
        address_id,
        updated_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY updated_at DESC, address_id DESC
        ) AS rn
    FROM customer_addresses
)
SELECT customer_id, address_id, updated_at
FROM ranked
WHERE rn = 1;
~~~

Truy vấn dùng ROW_NUMBER để chọn một địa chỉ mới nhất cho mỗi khách hàng. Tiêu chí phụ address_id giúp kết quả ổn định khi updated_at trùng. Nếu có quy tắc ưu tiên khác như is_primary hoặc trạng thái hiệu lực, phải đưa quy tắc đó vào ORDER BY.

### So sánh với kỳ trước

~~~sql
SELECT
    product_id,
    month_start,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY product_id
        ORDER BY month_start
    ) AS previous_month_revenue,
    revenue - LAG(revenue) OVER (
        PARTITION BY product_id
        ORDER BY month_start
    ) AS revenue_change
FROM monthly_product_revenue;
~~~

LAG lấy hàng trước theo thứ tự tháng. Nếu thiếu tháng trong dữ liệu, “hàng trước” có thể là tháng gần nhất có bản ghi chứ không nhất thiết là tháng lịch liền kề. Nếu nghiệp vụ cần so sánh đúng tháng trước, cần tạo lịch tháng đầy đủ hoặc nối với calendar table.

## Chi phí hiệu năng của hàm cửa sổ

### Sort là chi phí thường gặp

Để thực hiện một hàm cửa sổ, hệ quản trị thường cần dữ liệu theo thứ tự PARTITION BY và ORDER BY. Nếu dữ liệu đầu vào chưa có thứ tự phù hợp, kế hoạch có thể chứa Sort. Sắp xếp hàng triệu hàng tiêu tốn CPU và bộ nhớ; nếu không đủ memory grant, thao tác có thể spill ra vùng lưu trữ tạm.

Các dấu hiệu cần xem:

- Sort chiếm tỷ lệ thời gian lớn hoặc có actual rows cao.
- Sort spill, temp read/write hoặc cảnh báo bộ nhớ.
- Memory grant lớn so với dữ liệu thực tế.
- Nhiều phép sort riêng cho các định nghĩa cửa sổ có thứ tự khác nhau.
- Số hàng đầu vào của window operator lớn do lọc chưa đủ sớm.
- Một phân vùng rất lớn khiến xử lý tập trung vào một nhóm dữ liệu lệch.

Một truy vấn có nhiều hàm cửa sổ cùng PARTITION BY và ORDER BY có thể được thực hiện trên cùng thứ tự dữ liệu hoặc chia sẻ một số bước sắp xếp, tùy optimizer. Nếu mỗi hàm có thứ tự khác nhau, hệ quản trị có thể cần thêm Sort.

### Chọn PARTITION BY hợp lý

PARTITION BY quá rộng hoặc thiếu khóa nghiệp vụ có thể khiến một phân vùng rất lớn. Một phân vùng lớn có thể cần giữ nhiều trạng thái hoặc xử lý nhiều hàng trước khi trả kết quả, tùy hàm và frame.

Thêm cột vào PARTITION BY chỉ để giảm kích thước phân vùng có thể làm thay đổi kết quả. Ví dụ, thêm order_id vào PARTITION BY sẽ biến mỗi đơn thành phân vùng riêng và làm tổng lũy kế theo khách hàng không còn đúng. Chỉ dùng khóa phân vùng phản ánh đúng nhóm nghiệp vụ.

Dữ liệu lệch (skew) cũng quan trọng. Nếu một tenant có 50% tổng số hàng còn các tenant khác rất nhỏ, phân vùng của tenant lớn có thể chi phối thời gian và bộ nhớ. Hãy xem phân bố số hàng theo partition key, không chỉ số trung bình.

### Chỉ mục hỗ trợ thứ tự cửa sổ

Chỉ mục có thứ tự phù hợp với các cột phân vùng và sắp xếp có thể giúp giảm hoặc tránh một số thao tác sort. Ví dụ, truy vấn theo customer_id rồi order_date có thể hưởng lợi từ chỉ mục ghép bắt đầu bằng customer_id và tiếp theo là order_date, tùy hệ quản trị và các cột cần lấy.

~~~sql
CREATE INDEX ix_orders_customer_date
ON orders (customer_id, order_date, order_id);
~~~

Đây là chỉ mục ứng viên, không phải khuyến nghị áp dụng tự động. Cần cân nhắc:

- Có lọc theo customer_id hay toàn bộ khách hàng?
- Thứ tự ASC/DESC có phù hợp với truy vấn và hệ quản trị không?
- Có cần thêm cột bao phủ không?
- Chỉ mục có làm tăng chi phí ghi, dung lượng và áp lực cache không?
- Optimizer có thể dùng thứ tự chỉ mục sau các phép lọc/join trước đó không?

Nếu truy vấn sắp xếp theo nhiều thứ tự cửa sổ khác nhau, một chỉ mục không thể đáp ứng tất cả. Hãy ưu tiên workload có tần suất và tác động lớn.

### Giảm số hàng trước khi tính cửa sổ

Nếu nghiệp vụ cho phép, lọc dữ liệu ở truy vấn đầu vào trước khi tính hàm cửa sổ để giảm số hàng phải phân vùng và sắp xếp. Ví dụ, chỉ phân tích một khoảng ngày cụ thể thay vì toàn bộ lịch sử.

Tuy nhiên, vị trí lọc có thể thay đổi kết quả. Nếu cần tính tổng lũy kế từ đầu lịch sử nhưng chỉ hiển thị 30 ngày gần nhất, không thể đơn giản lọc 30 ngày trước khi tính SUM; việc đó sẽ làm mất phần lũy kế trước khoảng hiển thị. Có thể cần tính cửa sổ trên dữ liệu lịch sử cần thiết rồi lọc ở truy vấn ngoài.

~~~sql
WITH calculated AS (
    SELECT
        account_id,
        transaction_time,
        transaction_id,
        amount,
        SUM(amount) OVER (
            PARTITION BY account_id
            ORDER BY transaction_time, transaction_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_total
    FROM account_transactions
    WHERE transaction_time < TIMESTAMP '2026-12-01 00:00:00'
)
SELECT *
FROM calculated
WHERE transaction_time >= TIMESTAMP '2026-11-01 00:00:00';
~~~

Truy vấn vẫn đọc phần lịch sử trước tháng 11 để tính tổng lũy kế đúng, nhưng chỉ hiển thị kết quả từ tháng 11. Nếu cần giới hạn lịch sử, phải xác định số dư đầu kỳ hoặc snapshot để bảo toàn ngữ nghĩa.

### Frame nhỏ không luôn đồng nghĩa chi phí nhỏ

Frame ROWS BETWEEN 2 PRECEDING AND CURRENT ROW chỉ cần tối đa ba hàng về mặt logic cho mỗi hàng hiện tại. Nhưng hệ quản trị vẫn có thể phải đọc và sắp xếp toàn bộ tập đầu vào để thiết lập đúng thứ tự phân vùng. Frame nhỏ không tự loại bỏ chi phí sort.

Ngược lại, một frame toàn phân vùng cho SUM có thể được thực hiện hiệu quả bằng cách tích lũy trạng thái sau khi sắp xếp hoặc thậm chí không cần sort nếu không có ORDER BY. Chi phí thực tế phụ thuộc hàm, frame, thứ tự dữ liệu và implementation của hệ quản trị.

## Đọc execution plan và đo hiệu năng

Khi tối ưu truy vấn cửa sổ, hãy xem:

1. **Số hàng đầu vào:** bao nhiêu hàng đi vào toán tử cửa sổ sau WHERE, JOIN và GROUP BY?
2. **Sort:** có Sort hoặc Incremental Sort không; số hàng và độ rộng hàng là bao nhiêu?
3. **Window operator:** hệ quản trị dùng Window Aggregate, Window Spool, Window Function hoặc toán tử tương đương nào?
4. **Memory grant:** bộ nhớ ước lượng và thực tế có phù hợp không?
5. **Spill:** sort/hash/window có ghi dữ liệu tạm ra đĩa không?
6. **Partition skew:** phân vùng lớn nhất có vượt xa phân vùng thông thường không?
7. **Estimated Rows và Actual Rows:** cardinality estimate có sai lệch lớn không?
8. **I/O và CPU:** logical reads, temp I/O, CPU time và elapsed time thay đổi ra sao?
9. **Parallelism:** kế hoạch có song song hóa được không; có bước exchange hoặc gather làm nghẽn không?
10. **Kết quả:** việc thay đổi frame hoặc thứ tự có bảo toàn tập kết quả và thứ hạng nghiệp vụ không?

Tên toán tử và cách báo số liệu khác nhau giữa PostgreSQL, SQL Server, MySQL và các hệ quản trị khác. Dùng actual execution plan, thống kê truy vấn và công cụ của đúng sản phẩm. Không suy luận chỉ từ phần trăm cost hiển thị trong giao diện.

### Đo baseline trước khi thay đổi

Ghi lại truy vấn, tham số, số hàng đầu vào, kích thước phân vùng, thứ tự sắp xếp, p50/p95/p99, CPU, logical reads, temp I/O và memory grant. Đo dưới tải đại diện và lặp lại đủ lần để hiểu dao động do cache hoặc tác vụ nền.

Sau đó thay đổi một yếu tố chính, ví dụ thêm chỉ mục hỗ trợ thứ tự, giảm cột đầu vào, thay đổi cách tổng hợp hoặc viết lại frame. Chạy lại cùng workload và so sánh cả thời gian, tài nguyên lẫn kết quả dữ liệu.

## Các sai lầm thường gặp

- **Nhầm PARTITION BY với partition vật lý:** phân vùng cửa sổ là nhóm logic, không phải cách chia file hoặc partition table.
- **Cho rằng ORDER BY trong OVER sắp xếp kết quả cuối:** cần ORDER BY ở truy vấn ngoài nếu giao diện yêu cầu thứ tự.
- **Dùng ROWS khi nghiệp vụ muốn tính theo giá trị:** ROWS đếm bản ghi; RANGE/GROUPS xử lý peer và giá trị theo cách khác.
- **Không xác định thứ tự duy nhất:** ROW_NUMBER và frame ROWS có thể không ổn định khi các khóa sắp xếp trùng.
- **Quên frame mặc định:** SUM hoặc LAST_VALUE có thể xử lý peer khác điều người viết dự kiến.
- **Dùng LAST_VALUE để lấy giá trị cuối phân vùng mà không mở rộng frame:** kết quả thường chỉ là cuối frame hiện tại.
- **Nhầm 7 hàng với 7 ngày:** ROWS 6 PRECEDING là bảy bản ghi, không phải bảy ngày lịch.
- **Thêm khóa phụ vào RANK làm mất đồng hạng:** thứ tự phụ có thể thay đổi định nghĩa peer.
- **Lọc quá sớm:** loại dữ liệu lịch sử cần cho tổng lũy kế hoặc cửa sổ.
- **Tạo chỉ mục chỉ dựa trên một truy vấn:** bỏ qua chi phí ghi, dung lượng và workload khác.
- **Chỉ nhìn thời gian truy vấn:** bỏ qua spill, memory grant, temp I/O và ảnh hưởng đến hệ thống dưới tải đồng thời.

## Checklist thiết kế và tối ưu hàm cửa sổ

- [ ] Xác định grain của từng hàng đầu vào và kết quả mong muốn.
- [ ] Chọn đúng PARTITION BY theo khóa nghiệp vụ.
- [ ] Chọn ORDER BY phản ánh thứ tự tính toán; thêm khóa duy nhất khi cần thứ tự ổn định.
- [ ] Xác định peer và cách xử lý giá trị đồng hạng.
- [ ] Khai báo frame tường minh khi kết quả phụ thuộc kích thước khung.
- [ ] Phân biệt ROWS, RANGE và GROUPS.
- [ ] Kiểm tra frame mặc định và hành vi của LAST_VALUE/FIRST_VALUE.
- [ ] Phân biệt thứ tự trong OVER với thứ tự kết quả ngoài.
- [ ] Đọc số hàng đầu vào, sort, window operator, memory grant và spill.
- [ ] Đánh giá chỉ mục theo thứ tự partition/order và chi phí ghi.
- [ ] Chỉ lọc trước cửa sổ khi không làm mất dữ liệu cần cho phép tính.
- [ ] Đo lại p95/p99, CPU, I/O, temp usage và xác minh kết quả nghiệp vụ.

## Thực hành: tính tổng lũy kế và trung bình trượt

Cho bảng account_transactions gồm account_id, transaction_id, transaction_time và amount. Hãy tạo hai kết quả:

1. Tổng lũy kế của mỗi tài khoản theo từng giao dịch.
2. Trung bình của tối đa năm giao dịch gần nhất.

Có thể dùng hai cửa sổ với cùng phân vùng và thứ tự:

~~~sql
SELECT
    account_id,
    transaction_time,
    transaction_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY transaction_time, transaction_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total,
    AVG(amount) OVER (
        PARTITION BY account_id
        ORDER BY transaction_time, transaction_id
        ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
    ) AS moving_average_5
FROM account_transactions
ORDER BY account_id, transaction_time, transaction_id;
~~~

Để đánh giá hiệu năng, hãy đo kế hoạch và số liệu trên tập dữ liệu đại diện trước và sau khi tạo chỉ mục ứng viên (account_id, transaction_time, transaction_id). Kiểm tra liệu sort có giảm không, số hàng đầu vào có thay đổi không, memory grant và temp I/O có cải thiện không. Cân nhắc chi phí cập nhật chỉ mục khi giao dịch mới được ghi liên tục.

Nếu hai hàm dùng cùng PARTITION BY và ORDER BY, optimizer có thể tận dụng cùng thứ tự dữ liệu, nhưng điều này không được bảo đảm ở mọi hệ quản trị. Hãy kiểm tra kế hoạch thực tế thay vì giả định hai hàm luôn chỉ cần một lần sort.

Hàm cửa sổ giúp tính toán trên dữ liệu có thứ tự mà vẫn giữ chi tiết từng hàng. Để sử dụng đúng và hiệu quả, cần xác định rõ phân vùng, thứ tự, peer và frame; sau đó đánh giá chi phí sort, bộ nhớ, spill và I/O bằng kế hoạch thực thi. Một frame đúng về nghiệp vụ và một đường truy cập phù hợp giúp kết quả ổn định, dễ kiểm chứng và có hiệu năng dự đoán được hơn.
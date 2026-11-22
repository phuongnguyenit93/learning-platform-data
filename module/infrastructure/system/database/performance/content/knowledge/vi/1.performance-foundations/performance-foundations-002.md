# Hành trình một yêu cầu: kết nối, phân tích SQL, lập kế hoạch, thực thi và trả kết quả

Một câu SQL chỉ là phần nhìn thấy được của một yêu cầu cơ sở dữ liệu. Trước khi ứng dụng nhận được kết quả, hệ quản trị cơ sở dữ liệu (DBMS) phải tiếp nhận kết nối, hiểu câu lệnh, xác định dữ liệu cần đọc hoặc thay đổi, chọn cách thực hiện, xử lý tranh chấp với giao dịch khác và chuyển kết quả về cho ứng dụng. Mỗi chặng đều có thể tạo ra độ trễ.

Trong module **DATABASE_PERFORMANCE**, chúng ta rèn phương pháp tối ưu hiệu năng dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Vì vậy, hiểu hành trình của một yêu cầu là nền tảng để đặt đúng câu hỏi: thời gian đang bị tiêu tốn ở đâu, bằng chứng nào xác nhận nút thắt, và thay đổi nào có thể cải thiện kết quả mà không làm giảm tính đúng đắn?

Bài học đi theo một yêu cầu đọc dữ liệu điển hình, từ lúc ứng dụng lấy kết nối đến khi nhận xong các dòng kết quả. Một số chi tiết triển khai khác nhau giữa PostgreSQL, MySQL, SQL Server và các DBMS khác; các bước dưới đây mô tả những khái niệm chung, đồng thời ghi rõ khi ví dụ phụ thuộc vào một hệ quản trị cụ thể.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả được các giai đoạn chính của một yêu cầu SQL và phân biệt thời gian chờ lấy kết nối với thời gian xử lý trong DBMS.
- Giải thích vai trò của phân tích cú pháp, phân giải tên và kiểu dữ liệu, tối ưu hóa, thống kê và kế hoạch thực thi.
- Đọc các dấu hiệu cơ bản trong execution plan để nhận diện ước lượng sai, truy cập dữ liệu tốn kém, sort, spill bộ nhớ và chờ khóa.
- Phân biệt chi phí CPU, I/O, bộ nhớ, mạng và tranh chấp giao dịch khi phân tích độ trễ.
- Thiết lập cách đo trước và sau khi điều chỉnh để xác nhận hiệu quả trên tải đại diện.

## 1. Nhìn toàn bộ vòng đời của yêu cầu

Một yêu cầu SQL thường đi qua chuỗi bước sau:

1. Ứng dụng lấy một kết nối từ connection pool hoặc thiết lập kết nối mới.
2. Ứng dụng gửi câu lệnh và tham số qua giao thức của DBMS.
3. DBMS phân tích cú pháp, kiểm tra đối tượng, quyền truy cập và kiểu dữ liệu.
4. DBMS viết lại câu lệnh khi cần, sau đó tối ưu hóa và chọn kế hoạch thực thi.
5. Bộ thực thi chạy kế hoạch, đọc hoặc ghi dữ liệu, phối hợp với bộ nhớ đệm và hệ thống lưu trữ.
6. Giao dịch hoàn tất theo ngữ nghĩa commit hoặc rollback.
7. DBMS mã hóa và gửi các dòng kết quả về ứng dụng; driver giải mã để mã ứng dụng sử dụng.

Có thể hình dung luồng tổng quát như sau:

~~~mermaid
flowchart TD
    A["Ứng dụng tạo yêu cầu"] --> B["Lấy kết nối từ pool"]
    B --> C["Gửi SQL và tham số"]
    C --> D["Parse và kiểm tra ngữ nghĩa"]
    D --> E["Viết lại và tối ưu hóa"]
    E --> F["Chọn execution plan"]
    F --> G["Thực thi các toán tử"]
    G --> H["Đọc / ghi buffer và storage"]
    H --> I["Hoàn tất giao dịch"]
    I --> J["Mã hóa và truyền kết quả"]
    J --> K["Driver và ứng dụng nhận dữ liệu"]
~~~

Sơ đồ là mô hình khái niệm. Trong thực tế, một DBMS có thể gộp một số bước, tái sử dụng kế hoạch đã lưu, hoặc truyền từng phần kết quả trong khi các toán tử vẫn đang chạy. Vì thế, các giai đoạn không phải lúc nào cũng tách biệt thành những khoảng thời gian cộng nối hoàn toàn độc lập.

Một cách phân rã độ trễ ở phía ứng dụng là:

~~~text
Thời gian phản hồi
  ≈ thời gian chờ connection pool
  + thời gian gửi yêu cầu và xử lý giao thức
  + thời gian parse / bind / plan
  + thời gian thực thi và chờ tài nguyên
  + thời gian commit (nếu có)
  + thời gian truyền và tiêu thụ kết quả
~~~

Đây là khung phân tích, không phải công thức đo chính xác cho mọi DBMS. Một số hệ thống đo thời gian thực thi đến lúc trả dòng đầu tiên; hệ thống khác đo đến lúc client đọc hết kết quả. Truy vấn streaming cũng có thể vừa thực thi vừa gửi dữ liệu. Khi so sánh số liệu, cần biết rõ điểm bắt đầu và kết thúc của từng bộ đo.

## 2. Ứng dụng lấy kết nối và gửi câu lệnh

### 2.1. Connection pool

Ứng dụng thường không mở một kết nối TCP mới cho từng câu SQL. Thay vào đó, nó lấy một kết nối đã được tạo và xác thực từ connection pool. Pool giới hạn số kết nối đồng thời, tái sử dụng phiên làm việc và giảm chi phí thiết lập kết nối.

Khi pool không còn kết nối rảnh, yêu cầu phải xếp hàng. Người dùng có thể thấy API phản hồi chậm dù câu SQL khi chạy trong DBMS lại nhanh. Vì vậy, cần phân biệt:

- **Pool wait:** thời gian ứng dụng chờ một kết nối sẵn sàng.
- **Connect time:** thời gian mở kết nối mới, thương lượng giao thức, xác thực và thiết lập phiên.
- **Database execution time:** thời gian DBMS xử lý câu lệnh, bao gồm những thời gian chờ tài nguyên được bộ đo của DBMS ghi nhận.

Các chỉ số nên theo dõi gồm số kết nối đang hoạt động, số kết nối nhàn rỗi, giới hạn pool, số yêu cầu đang chờ lấy kết nối, thời gian chờ ở các phân vị p50/p95/p99 và số lần tạo kết nối mới. Nếu pool quá nhỏ, hàng đợi tăng; nếu quá lớn, DBMS có thể phải quản lý quá nhiều phiên và tranh chấp tài nguyên.

Tăng kích thước pool không phải lúc nào cũng làm hệ thống nhanh hơn. Khi DBMS đã bão hòa CPU, I/O hoặc khóa, nhiều kết nối hơn có thể làm số yêu cầu đồng thời tăng nhưng thông lượng không tăng, thậm chí độ trễ p95/p99 xấu đi. Cần đo tải và tìm điểm bão hòa trước khi điều chỉnh.

### 2.2. Giao thức và trạng thái phiên

Sau khi lấy được kết nối, driver gửi câu lệnh theo giao thức của DBMS. Phiên làm việc có thể mang theo trạng thái như schema hiện tại, timezone, isolation level, biến phiên, transaction đang mở và các thiết lập tối ưu hóa. Hai lần chạy cùng một SQL trên hai phiên có cấu hình khác nhau có thể có hành vi khác nhau.

Ứng dụng cũng có thể gửi SQL theo hai cách phổ biến:

- Gửi câu lệnh đã chứa giá trị literal.
- Gửi câu lệnh đã chuẩn bị (prepared statement) và truyền giá trị tham số riêng.

Prepared statement giúp tái sử dụng cấu trúc câu lệnh, giảm việc phân tích lặp lại và tránh ghép chuỗi dữ liệu không an toàn. Tuy nhiên, cách DBMS lưu và tái sử dụng kế hoạch phụ thuộc vào sản phẩm và cấu hình. Một kế hoạch tổng quát có thể phù hợp với nhiều giá trị tham số nhưng kém tối ưu với một số giá trị có độ chọn lọc rất khác nhau. Hiện tượng này thường được gọi là vấn đề kế hoạch nhạy cảm với tham số.

Ví dụ, truy vấn tìm đơn hàng của một khách hàng lớn có thể trả về hàng trăm nghìn dòng, trong khi khách hàng khác chỉ có vài dòng. Một kế hoạch dùng index lookup có thể tốt cho trường hợp thứ hai nhưng không hiệu quả cho trường hợp thứ nhất. Khi điều tra, hãy kiểm tra giá trị tham số đại diện, cơ chế plan cache và cách DBMS chọn kế hoạch cho prepared statement.

## 3. Parse, bind và kiểm tra ngữ nghĩa

### 3.1. Phân tích cú pháp

DBMS phân tích chuỗi SQL theo ngữ pháp của nó và xây dựng biểu diễn nội bộ, thường là cây cú pháp (syntax tree). Bước này phát hiện lỗi cú pháp như thiếu dấu ngoặc, sai từ khóa hoặc cấu trúc mệnh đề không hợp lệ.

Ví dụ, câu lệnh sau có cấu trúc cơ bản gồm SELECT, FROM, WHERE, ORDER BY và LIMIT:

~~~sql
SELECT id, created_at, total
FROM orders
WHERE customer_id = $1
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
~~~

Ký hiệu tham số $1 là cách viết thường gặp trong PostgreSQL; các DBMS khác dùng cú pháp tham số khác. Việc dùng tham số giúp driver truyền dữ liệu đúng kiểu và tách giá trị khỏi cấu trúc SQL.

### 3.2. Phân giải tên và kiểm tra kiểu

Sau khi hiểu cấu trúc, DBMS cần xác định orders là bảng hoặc view nào, customer_id thuộc đối tượng nào, các cột có tồn tại không, kiểu dữ liệu có tương thích không và người dùng có quyền thực hiện thao tác không. Bước này còn có thể áp dụng quy tắc chuyển kiểu ngầm định, kiểm tra hàm, toán tử, schema và quyền truy cập.

Một phép chuyển kiểu không phù hợp có thể ảnh hưởng đến khả năng sử dụng chỉ mục. Chẳng hạn, nếu cột được lưu dưới kiểu số nhưng ứng dụng truyền chuỗi và DBMS phải chuyển kiểu trên cột trong biểu thức lọc, kế hoạch có thể không tận dụng được index như mong đợi. Cách xử lý phụ thuộc kiểu dữ liệu và bộ tối ưu của từng DBMS; nên kiểm tra execution plan thay vì kết luận chỉ từ hình thức SQL.

### 3.3. Viết lại câu truy vấn

Một số DBMS có bước rewrite để chuyển view, áp dụng quy tắc, mở rộng biểu thức hoặc đưa các điều kiện bảo mật vào câu truy vấn. Bộ tối ưu cũng có thể biến đổi biểu diễn logic mà vẫn giữ nguyên ngữ nghĩa, ví dụ đẩy điều kiện lọc xuống gần nơi đọc dữ liệu hoặc loại bỏ cột không cần thiết.

Mục tiêu là giảm lượng dữ liệu phải xử lý càng sớm càng tốt, nhưng mọi phép biến đổi đều phải bảo toàn kết quả theo ngữ nghĩa SQL, bao gồm NULL, phép nối, thứ tự và giới hạn dòng.

## 4. Tối ưu hóa và chọn kế hoạch thực thi

### 4.1. Kế hoạch logic và kế hoạch vật lý

Câu SQL mô tả **kết quả cần có**; nó không chỉ định chính xác DBMS phải đọc bảng theo thứ tự nào, dùng chỉ mục nào hay nối bảng bằng thuật toán nào. Bộ tối ưu chuyển yêu cầu logic thành một kế hoạch vật lý gồm các toán tử có thể thực thi.

Với truy vấn đọc dữ liệu, kế hoạch có thể gồm:

- Scan: đọc dữ liệu từ bảng hoặc chỉ mục.
- Filter: loại bỏ các dòng không thỏa điều kiện.
- Projection: chỉ giữ các cột cần thiết.
- Join: kết hợp dòng từ nhiều nguồn.
- Sort: sắp xếp theo thứ tự yêu cầu.
- Aggregate: tính COUNT, SUM, GROUP BY hoặc các phép tổng hợp khác.
- Limit: dừng sau khi thu được số dòng cần thiết.

Các toán tử có thể chạy theo dạng pipeline, chuyển dòng cho nhau mà không cần lưu toàn bộ kết quả trung gian. Một số thao tác như sort hoặc hash join có thể cần bộ nhớ để xây dựng cấu trúc trung gian.

### 4.2. Thống kê và ước lượng cardinality

Bộ tối ưu thường dùng thống kê để ước lượng số dòng đầu ra của mỗi toán tử (cardinality), độ chọn lọc của điều kiện, kích thước dữ liệu và chi phí dự kiến. Các thống kê thường gặp gồm:

- Tổng số dòng và số trang dữ liệu của bảng.
- Số giá trị phân biệt của một cột.
- Histogram hoặc phân bố giá trị.
- Tỷ lệ NULL.
- Thống kê chỉ mục và kích thước các đối tượng.
- Thống kê tương quan giữa thứ tự logic của giá trị và vị trí vật lý, hoặc giữa nhiều cột nếu DBMS hỗ trợ.

Nếu thống kê cũ hoặc không phản ánh phân bố thực tế, bộ tối ưu có thể ước lượng sai. Sai lệch này ảnh hưởng đến lựa chọn access path, thứ tự join, thuật toán join và dung lượng bộ nhớ cần thiết.

Ví dụ, DBMS ước lượng một điều kiện chỉ trả về 10 dòng nhưng thực tế trả về 500.000 dòng. Nó có thể chọn nested loop với nhiều lần tra cứu chỉ mục; kế hoạch này có thể rất tốn kém khi số dòng thực tế lớn. Ngược lại, nếu ước lượng quá cao, DBMS có thể chọn scan hoặc hash join trong khi index lookup sẽ rẻ hơn.

Khi đọc execution plan, hãy so sánh số dòng ước lượng với số dòng thực tế ở các toán tử quan trọng. Chênh lệch lớn là manh mối để kiểm tra thống kê, tương quan giữa cột, tham số và biểu thức lọc.

### 4.3. Các đường truy cập dữ liệu

Bộ tối ưu có thể chọn một trong nhiều cách:

- **Table scan / sequential scan:** đọc lần lượt phần lớn hoặc toàn bộ bảng. Đây có thể là lựa chọn tốt khi cần nhiều dòng, bảng nhỏ hoặc dữ liệu nằm gần nhau trên thiết bị lưu trữ.
- **Index seek / index scan:** đi qua cấu trúc chỉ mục để tìm một vùng khóa hoặc tập dòng phù hợp. Có lợi khi điều kiện chọn lọc tốt và chỉ mục phù hợp.
- **Index-only access:** lấy các cột cần thiết trực tiếp từ chỉ mục khi DBMS có thể xác nhận dữ liệu trong chỉ mục đủ để trả lời truy vấn. Điều kiện để thực hiện được phụ thuộc DBMS và trạng thái dữ liệu.
- **Bitmap access:** kết hợp vị trí dòng từ một hoặc nhiều chỉ mục trước khi truy cập bảng; có thể hữu ích khi mỗi điều kiện chọn được một tập dòng vừa phải.

Không nên mặc định rằng dùng index luôn nhanh hơn scan. Nếu truy vấn cần phần lớn dòng của bảng, nhiều lần tra cứu ngẫu nhiên qua chỉ mục có thể tốn kém hơn đọc tuần tự. Hiệu quả còn phụ thuộc kích thước bảng, độ chọn lọc, cache, loại lưu trữ, thứ tự dữ liệu và chi phí truy cập các cột bổ sung.

### 4.4. Thuật toán join

Ba nhóm thuật toán join phổ biến là:

- **Nested loop join:** với mỗi dòng từ phía ngoài, tìm dòng phù hợp ở phía trong. Thường hiệu quả khi phía ngoài nhỏ và phía trong có chỉ mục phù hợp.
- **Hash join:** xây dựng bảng băm từ một đầu vào rồi dò tìm bằng đầu vào còn lại. Thường phù hợp với phép nối bằng trên tập dữ liệu lớn; có thể cần nhiều bộ nhớ và ghi dữ liệu tạm nếu không đủ bộ nhớ.
- **Merge join:** đọc hai đầu vào đã được sắp xếp theo khóa nối và ghép chúng theo thứ tự. Có thể hiệu quả khi dữ liệu đã có thứ tự phù hợp hoặc chi phí sắp xếp hợp lý.

Không có thuật toán join tốt nhất cho mọi trường hợp. Lựa chọn phụ thuộc số dòng thực tế, thống kê, chỉ mục, thứ tự đầu vào và tài nguyên. Nếu kế hoạch có một nested loop với số vòng lặp rất lớn, hãy kiểm tra số dòng đầu vào và số lần truy cập phía trong. Nếu hash join hoặc sort ghi dữ liệu tạm, hãy kiểm tra kích thước dữ liệu, cấu hình bộ nhớ và mức độ đồng thời.

### 4.5. Kế hoạch được lưu và tái sử dụng

DBMS có thể lưu kế hoạch để tránh tối ưu lại mỗi lần chạy. Việc tái sử dụng giúp giảm chi phí parse/plan, nhưng kế hoạch đã lưu có thể trở nên không phù hợp khi dữ liệu thay đổi, thống kê cập nhật hoặc các giá trị tham số có phân bố khác nhau.

Khi một câu SQL có độ trễ không ổn định theo tham số, hãy thu thập kế hoạch cho các nhóm tham số đại diện. Ghi nhận cả thời gian parse/plan nếu DBMS cung cấp, thời gian thực thi, số dòng ước lượng và số dòng thực tế. Không nên xóa plan cache như một phản xạ đầu tiên; trước hết cần xác định kế hoạch cũ có thực sự là nguyên nhân và việc xóa cache có thể làm tăng chi phí tối ưu đồng loạt hay không.

## 5. Thực thi kế hoạch: CPU, bộ nhớ và I/O

Khi kế hoạch được chọn, execution engine thực hiện các toán tử. Một toán tử scan có thể đọc trang từ buffer cache hoặc yêu cầu đọc từ storage. Các toán tử tiếp theo lọc, nối, sắp xếp và tổng hợp dữ liệu. Hiệu năng lúc này phụ thuộc mạnh vào lượng dữ liệu, cách truy cập, tài nguyên sẵn có và mức độ tranh chấp.

### 5.1. Buffer cache và lưu trữ

DBMS thường duy trì vùng nhớ đệm các trang dữ liệu và chỉ mục. Nếu trang cần thiết đã có trong cache, DBMS có thể đọc từ RAM; nếu chưa có, hệ thống phải yêu cầu I/O từ storage. Vì vậy, cùng một truy vấn có thể nhanh hơn sau lần chạy đầu khi dữ liệu đã được nạp vào cache.

Cần phân biệt:

- **Logical read / buffer hit:** DBMS tìm thấy trang trong bộ nhớ đệm và không cần đọc trang đó từ thiết bị lưu trữ ở lần truy cập này.
- **Physical read / buffer miss:** DBMS phải lấy trang từ storage hoặc tầng cache thấp hơn.
- **Sequential I/O:** truy cập các vùng dữ liệu liên tiếp, thường có lợi cho việc đọc nhiều dữ liệu.
- **Random I/O:** truy cập các vị trí rời rạc, có thể tốn kém khi số lần truy cập lớn.

Tên gọi và cách đếm các chỉ số khác nhau theo DBMS. Một cache hit vẫn tiêu tốn CPU và băng thông bộ nhớ; nó không đồng nghĩa với chi phí bằng không. Tương tự, một physical read không tự động chứng minh storage là nút thắt. Cần xem số lượng, độ trễ I/O, hàng đợi thiết bị và tỷ lệ cache hit trong bối cảnh tải thực tế.

### 5.2. Bộ nhớ cho sort, hash và dữ liệu trung gian

Sort, hash join, hash aggregate và một số toán tử khác cần bộ nhớ cho dữ liệu trung gian. Nếu dữ liệu vượt quá ngưỡng bộ nhớ cho phép, DBMS có thể chia dữ liệu thành nhiều phần và ghi tạm ra storage (spill). Spill làm tăng I/O và thường khiến truy vấn chậm đáng kể.

Khi thấy sort hoặc hash operation tốn nhiều thời gian, hãy kiểm tra số dòng và kích thước dữ liệu đầu vào, số dòng sau lọc, dung lượng bộ nhớ được cấp và chỉ số đọc/ghi dữ liệu tạm. Giảm số dòng trước khi sort hoặc join, chỉ lấy các cột cần thiết và cải thiện điều kiện lọc có thể hiệu quả hơn việc chỉ tăng bộ nhớ.

Một thiết lập bộ nhớ lớn có thể giúp một truy vấn riêng lẻ nhưng gây áp lực RAM khi nhiều truy vấn chạy đồng thời. Hãy đánh giá tổng mức tiêu thụ bộ nhớ ở tải đồng thời, vì cấu hình có lợi trong thử nghiệm đơn lẻ có thể gây swap hoặc thiếu bộ nhớ trong môi trường thật.

### 5.3. CPU và xử lý song song

CPU được dùng để đánh giá điều kiện, so sánh khóa, tính biểu thức, băm, sắp xếp, giải mã và thực hiện các toán tử khác. Một truy vấn đọc dữ liệu từ cache vẫn có thể chậm nếu phải xử lý quá nhiều dòng hoặc biểu thức phức tạp.

Một số DBMS có thể chia công việc cho nhiều worker hoặc nhiều luồng. Song song hóa có thể giảm thời gian của truy vấn lớn, nhưng cũng tiêu thụ thêm CPU, bộ nhớ và băng thông. Với truy vấn nhỏ, chi phí khởi tạo và phối hợp worker có thể lớn hơn lợi ích. Khi phân tích, cần xem số worker thực sự tham gia, mức độ mất cân bằng giữa các worker và tổng tài nguyên tiêu thụ, không chỉ nhìn thời gian của một truy vấn.

## 6. Giao dịch đồng thời, khóa và ghi dữ liệu

Một yêu cầu không chạy trong môi trường trống. Nhiều phiên có thể cùng đọc hoặc ghi các hàng và trang dữ liệu. Cơ chế đồng thời bảo đảm các giao dịch tuân thủ isolation level và quy tắc nhất quán của DBMS, nhưng có thể tạo thời gian chờ.

### 6.1. Lock, latch và wait

- **Lock** bảo vệ quyền truy cập logic vào đối tượng hoặc dữ liệu theo mô hình đồng thời của DBMS. Một giao dịch có thể phải chờ giao dịch khác nhả khóa.
- **Latch** thường bảo vệ cấu trúc dữ liệu nội bộ trong thời gian ngắn. Tranh chấp latch có thể xuất hiện khi nhiều phiên cùng thao tác trên một cấu trúc nóng.
- **Wait event** là cách DBMS phân loại trạng thái chờ, chẳng hạn chờ I/O, khóa, log flush, buffer hoặc giao tiếp.

Nếu thời gian phản hồi tăng nhưng CPU không bận tương ứng, hãy kiểm tra các phiên đang chờ và loại wait event. Một truy vấn có thời gian elapsed cao có thể dành phần lớn thời gian chờ khóa thay vì thực hiện phép tính.

Deadlock xảy ra khi các giao dịch tạo thành vòng chờ lẫn nhau. DBMS thường phát hiện và hủy một giao dịch để phá vòng chờ. Cần xem log hoặc báo cáo deadlock để xác định thứ tự truy cập tài nguyên, sau đó cân nhắc thống nhất thứ tự cập nhật, rút ngắn transaction và xử lý retry có kiểm soát.

### 6.2. MVCC và phiên bản dữ liệu

Nhiều DBMS dùng Multi-Version Concurrency Control (MVCC) hoặc cơ chế tương tự để cho phép giao dịch đọc một phiên bản dữ liệu phù hợp với snapshot của nó. Nhờ đó, một số thao tác đọc có thể không phải chờ thao tác ghi. Tuy nhiên, việc giữ nhiều phiên bản tạo thêm chi phí lưu trữ và dọn dẹp.

Giao dịch kéo dài có thể giữ snapshot cũ lâu, làm chậm việc thu hồi phiên bản không còn cần thiết hoặc gây tăng dung lượng dữ liệu phiên bản. Một truy vấn đọc lâu cũng có thể giữ tài nguyên và làm giảm khả năng dọn dẹp. Vì thế, khi điều tra hiệu năng, cần quan sát tuổi giao dịch, transaction đang mở lâu và cơ chế vacuum hoặc cleanup tương ứng với DBMS.

### 6.3. Commit, transaction log và độ bền

Với thao tác ghi, DBMS thường ghi thông tin cần thiết vào transaction log hoặc write-ahead log (WAL) trước khi xác nhận commit theo chính sách độ bền. Việc flush log xuống storage có thể tạo độ trễ. Một số DBMS hỗ trợ group commit, gộp nhiều commit vào một lần flush để giảm chi phí I/O.

Nếu câu lệnh UPDATE nhanh nhưng transaction commit chậm, cần xem thời gian chờ log flush, độ trễ storage của log, tần suất commit và mức độ đồng thời. Không nên rút ngắn transaction bằng cách bỏ qua yêu cầu nhất quán hoặc độ bền; hãy điều chỉnh ranh giới giao dịch và cách ghi theo đúng yêu cầu nghiệp vụ.

## 7. Trả kết quả về ứng dụng

Sau khi có các dòng kết quả, DBMS mã hóa chúng theo giao thức, gửi qua kết nối và driver giải mã kiểu dữ liệu để ứng dụng sử dụng. Quá trình này cũng tiêu tốn CPU, bộ nhớ và băng thông mạng.

Có ba mốc thời gian cần phân biệt:

- **Time to first row:** thời gian từ lúc gửi yêu cầu đến khi ứng dụng nhận được dòng đầu tiên.
- **Time to last row:** thời gian đến khi ứng dụng nhận đủ toàn bộ dòng kết quả.
- **Application processing time:** thời gian ứng dụng chuyển đổi, tuần tự hóa, tính toán hoặc ghi kết quả vào nơi khác.

Một truy vấn có thể tạo dòng đầu tiên nhanh nhưng mất lâu để truyền hết hàng triệu dòng. Nếu công cụ đo chỉ dừng ở dòng đầu tiên, nó không phản ánh tổng thời gian người dùng chờ. Ngược lại, nếu ứng dụng chỉ cần 20 dòng nhưng SQL trả về hàng trăm nghìn dòng, chi phí truyền và xử lý dữ liệu dư thừa có thể lớn hơn chi phí thực thi trong DBMS.

Để giảm chi phí ở chặng này:

- Chỉ chọn các cột ứng dụng thực sự sử dụng, tránh SELECT * trong luồng có dữ liệu lớn.
- Dùng điều kiện lọc và giới hạn dòng phù hợp với yêu cầu nghiệp vụ.
- Phân trang theo khóa ổn định khi cần duyệt tập dữ liệu lớn; tránh offset quá lớn nếu DBMS phải bỏ qua nhiều dòng.
- Dùng streaming hoặc fetch theo lô khi ứng dụng cần xử lý tập dữ liệu lớn, đồng thời quản lý tài nguyên và thời gian sống của cursor.
- Đo cả thời gian DBMS và thời gian client đọc hết dữ liệu.

## 8. Ví dụ xuyên suốt: truy vấn danh sách đơn hàng

Giả sử một API cần lấy 20 đơn hàng đã thanh toán gần nhất của một khách hàng:

~~~sql
SELECT id, created_at, total
FROM orders
WHERE customer_id = $1
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
~~~

Ta có thể lần theo yêu cầu như sau:

1. API lấy một kết nối từ pool. Nếu pool đang cạn, độ trễ có thể phát sinh trước khi SQL đến DBMS.
2. Driver gửi câu lệnh cùng giá trị tham số khách hàng.
3. DBMS parse câu lệnh, xác định bảng orders, kiểm tra cột, kiểu và quyền.
4. Bộ tối ưu ước lượng số đơn hàng phù hợp với customer_id và status, rồi chọn kế hoạch.
5. Execution engine tìm các dòng phù hợp, lấy dữ liệu cần thiết và dừng khi đủ 20 dòng nếu kế hoạch cho phép.
6. DBMS gửi các dòng về driver; API chuyển chúng thành response.

Một chỉ mục tổng hợp có thể phù hợp với mẫu truy vấn này:

~~~sql
-- Ví dụ cú pháp PostgreSQL; cần điều chỉnh theo DBMS đang dùng.
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at DESC)
INCLUDE (id, total);
~~~

Hai cột đầu được lọc bằng điều kiện bằng; cột tiếp theo hỗ trợ thứ tự giảm dần theo thời gian. Các cột INCLUDE có thể giúp lấy dữ liệu trả về từ chỉ mục mà không cần truy cập bảng trong những điều kiện DBMS cho phép. Cú pháp INCLUDE và khả năng index-only access không giống nhau ở mọi DBMS.

Chỉ mục này là một giả thuyết cần kiểm chứng, không phải kết luận mặc định. Trước khi tạo, cần kiểm tra:

- Truy vấn có thực sự chiếm tỷ trọng đáng kể trong tải hay không.
- Số dòng phù hợp với từng khách hàng và độ chọn lọc của status.
- Execution plan hiện tại đang scan bảng, dùng chỉ mục nào, có sort hay không.
- Chỉ mục tương tự đã tồn tại chưa.
- Chi phí lưu trữ và chi phí ghi tăng thêm khi INSERT, UPDATE hoặc DELETE.
- Kết quả có thay đổi theo tham số khách hàng hay không.

Nếu truy vấn đã dùng một chỉ mục phù hợp và chỉ đọc rất ít trang, nguyên nhân chậm có thể nằm ở pool wait, lock wait, truyền nhiều dữ liệu ở tầng ứng dụng hoặc tải hệ thống. Tạo thêm chỉ mục trong trường hợp đó có thể không giải quyết được nút thắt.

## 9. Đọc execution plan để tìm bằng chứng

Execution plan cho biết DBMS dự định hoặc đã thực hiện truy vấn bằng những toán tử nào. Tùy DBMS, có thể xem kế hoạch ước lượng (estimated plan) hoặc kế hoạch thực tế (actual plan).

Ví dụ với PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT id, created_at, total
FROM orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
~~~

EXPLAIN thông thường chỉ hiển thị kế hoạch ước lượng. EXPLAIN ANALYZE thực sự chạy câu truy vấn và bổ sung số liệu thực tế. Với câu lệnh ghi dữ liệu, việc chạy phân tích có thể tạo thay đổi thật; chỉ thực hiện trong môi trường và transaction an toàn đã được chuẩn bị. Rollback không nhất thiết đảo ngược mọi tác động bên ngoài hoặc mọi loại side effect.

Khi đọc kế hoạch, hãy tập trung vào:

- **Estimated rows và actual rows:** chênh lệch lớn cho thấy bộ tối ưu có thể ước lượng cardinality sai.
- **Actual time và loops:** thời gian và số lần một toán tử được thực hiện. Một toán tử nhanh mỗi lần nhưng lặp hàng trăm nghìn lần vẫn có thể là nút thắt.
- **Buffers hoặc logical/physical reads:** lượng trang được lấy từ cache hoặc phải đọc từ tầng lưu trữ.
- **Sort / hash / temporary I/O:** dấu hiệu dữ liệu trung gian lớn hoặc tràn bộ nhớ.
- **Join type và thứ tự join:** kiểm tra đầu vào có kích thước như bộ tối ưu dự đoán không.
- **Filter và Rows Removed:** nhiều dòng bị loại sau khi đã đọc có thể gợi ý điều kiện lọc chưa được áp dụng hiệu quả ở access path.
- **Planning time và execution time:** giúp phân biệt chi phí tạo kế hoạch với chi phí chạy kế hoạch, nếu DBMS cung cấp.

Không đọc một con số đơn lẻ ngoài ngữ cảnh. Một sequential scan trên bảng nhỏ có thể là lựa chọn tốt. Một index scan có thể chậm nếu phải truy cập bảng nhiều lần. Cost trong plan là ước lượng nội bộ để so sánh phương án, không phải số mili giây được bảo đảm. Luôn đối chiếu với số dòng thực tế, số trang đọc, tải đồng thời và thời gian đo từ ứng dụng.

## 10. Phân biệt các nhóm nút thắt

Bảng dưới đây giúp định hướng câu hỏi tiếp theo. Đây là dấu hiệu điều tra, không phải quy tắc kết luận tự động.

| Dấu hiệu quan sát | Khả năng cần kiểm tra | Bằng chứng tiếp theo |
|---|---|---|
| API chậm, DBMS ghi nhận truy vấn nhanh | Chờ connection pool, mạng hoặc xử lý ở ứng dụng | Pool wait, trace theo request, thời gian đọc hết result set |
| CPU cao, số dòng xử lý lớn | Scan quá nhiều, join hoặc biểu thức tốn CPU | Actual rows, số vòng lặp, CPU theo truy vấn |
| I/O cao hoặc đọc nhiều trang | Access path chưa phù hợp, cache miss, dữ liệu lớn | Buffer reads, physical reads, độ trễ và hàng đợi storage |
| Sort/hash ghi dữ liệu tạm | Thiếu bộ nhớ cho toán tử hoặc đầu vào quá lớn | Số dòng trước sort/join, temp read/write, cấu hình memory |
| Elapsed time cao nhưng CPU thấp | Chờ khóa, I/O, log hoặc tài nguyên khác | Wait events, blocking session, lock graph, log flush |
| Độ trễ biến động theo tham số | Phân bố dữ liệu lệch hoặc kế hoạch nhạy tham số | Kế hoạch và actual rows với nhiều giá trị đại diện |
| Dòng đầu tiên nhanh, hoàn tất chậm | Tập kết quả lớn hoặc client tiêu thụ chậm | Time to first/last row, số byte, tốc độ fetch |
| Pool wait tăng khi tải cao | Pool quá nhỏ hoặc DBMS đã bão hòa | Active/idle/waiting connections, throughput và độ trễ theo concurrency |

Một hệ thống có thể gặp nhiều nút thắt cùng lúc. Ví dụ, truy vấn đọc quá nhiều dòng làm tăng CPU và I/O, kéo dài thời gian giữ tài nguyên, từ đó khiến các phiên khác phải chờ. Cần xác định quan hệ nhân quả bằng trace và số liệu theo thời gian.

## 11. Quy trình đo và cải thiện có kiểm chứng

Một thay đổi chỉ được xem là cải thiện khi kết quả tốt hơn trên tải đại diện và vẫn giữ đúng chức năng. Hãy thực hiện theo trình tự:

### Bước 1: Xác định triệu chứng và phạm vi

Ghi rõ endpoint hoặc nghiệp vụ bị ảnh hưởng, câu SQL liên quan, khoảng thời gian xảy ra, tỷ lệ lỗi và mức tải. Xác định độ trễ người dùng đang quan tâm: p50, p95, p99 hay thời gian hoàn tất toàn bộ tác vụ.

### Bước 2: Thu thập baseline

Trước khi sửa, ghi nhận tối thiểu:

- Độ trễ p50/p95/p99 và thông lượng.
- Số lần chạy, số dòng trả về và kích thước dữ liệu.
- Pool wait và số kết nối đang hoạt động/chờ.
- Execution plan cùng các số liệu actual nếu có thể thu thập an toàn.
- CPU, bộ nhớ, buffer/cache, I/O, wait events và lock contention.
- Giá trị tham số đại diện, trạng thái cache và mức đồng thời của tải thử nghiệm.

Giữ điều kiện so sánh nhất quán. Cần phân biệt lần chạy cache nóng và cache lạnh; không so sánh một lần chạy lạnh với một lần chạy nóng rồi kết luận thay đổi đã cải thiện hiệu năng. Dùng nhiều lần chạy và xem phân vị thay vì chỉ lấy một mẫu.

### Bước 3: Lập giả thuyết từ bằng chứng

Ví dụ: “Truy vấn chậm do sort toàn bộ tập kết quả” là một giả thuyết có thể kiểm chứng. Bằng chứng cần tìm gồm số dòng đầu vào, toán tử sort, dữ liệu tạm và thời gian của toán tử. “Thiếu index” chỉ là phỏng đoán nếu chưa kiểm tra plan, độ chọn lọc và chi phí đọc.

### Bước 4: Thay đổi một yếu tố có kiểm soát

Có thể thử cập nhật thống kê, sửa điều kiện SQL, bổ sung chỉ mục, giảm cột trả về, thay đổi ranh giới transaction hoặc điều chỉnh cấu hình tài nguyên. Mỗi thay đổi cần có lý do gắn với nút thắt đã xác định. Tránh thay nhiều yếu tố cùng lúc vì sẽ khó biết yếu tố nào tạo ra khác biệt.

### Bước 5: Đo lại trong cùng điều kiện

Chạy lại bộ dữ liệu và tải tương đương, so sánh plan, actual rows, CPU, I/O, wait, độ trễ và thông lượng. Một truy vấn nhanh hơn khi chạy riêng lẻ nhưng làm giảm thông lượng toàn hệ thống hoặc tăng thời gian ghi có thể không phải là cải thiện tổng thể.

### Bước 6: Theo dõi sau khi áp dụng

Quan sát ở tải thực tế qua một khoảng thời gian đủ đại diện. Kiểm tra độ trễ theo phân vị, lỗi, tài nguyên, truy vấn liên quan và chi phí ghi. Chỉ mục mới có thể cải thiện SELECT nhưng làm INSERT/UPDATE/DELETE tốn kém hơn; thay đổi cấu hình bộ nhớ có thể giúp một truy vấn nhưng ảnh hưởng nhiều truy vấn khác.

## 12. Những ngộ nhận thường gặp

**“SQL ngắn thì phải nhanh.”** Độ dài câu SQL không cho biết số dòng phải đọc, số lần join, lượng dữ liệu trung gian hoặc thời gian chờ tài nguyên.

**“Có index là truy vấn sẽ nhanh.”** Index chỉ hữu ích khi cấu trúc và thứ tự cột phù hợp với điều kiện truy vấn, độ chọn lọc và dữ liệu cần trả về. Index cũng làm tăng chi phí ghi và bảo trì.

**“Sequential scan luôn là kế hoạch xấu.”** Scan tuần tự có thể rẻ hơn nhiều lần tra cứu ngẫu nhiên khi cần đọc phần lớn bảng hoặc bảng rất nhỏ.

**“CPU thấp nghĩa là DBMS không có vấn đề.”** DBMS có thể đang chờ khóa, storage, log flush hoặc tài nguyên khác. Cần đọc wait events và thời gian chờ.

**“EXPLAIN cost là thời gian chạy.”** Cost là ước lượng phục vụ việc so sánh kế hoạch. Cần actual execution và số liệu đo ở ứng dụng để biết độ trễ thật.

**“Chạy thử một lần là đủ.”** Cache, tải đồng thời, dữ liệu và tham số có thể làm kết quả thay đổi. Cần lặp lại trong điều kiện kiểm soát và xem phân vị.

**“Truy vấn đã xong khi DBMS trả dòng đầu tiên.”** Ứng dụng có thể vẫn phải nhận và xử lý một tập kết quả rất lớn. Hãy đo đến khi client đọc xong nếu đó là trải nghiệm thực tế cần tối ưu.

## 13. Checklist khi điều tra một yêu cầu SQL chậm

- [ ] Đã xác định thời gian đo bắt đầu và kết thúc ở tầng ứng dụng chưa?
- [ ] Đã tách pool wait, connect time, DB execution và thời gian client đọc kết quả chưa?
- [ ] Đã thu thập SQL cùng kiểu và giá trị tham số đại diện chưa?
- [ ] Đã xem execution plan và so sánh estimated rows với actual rows chưa?
- [ ] Đã kiểm tra access path, join, sort, aggregate và dữ liệu tạm chưa?
- [ ] Đã kiểm tra buffer/cache, CPU, I/O và wait events chưa?
- [ ] Đã xem lock, transaction kéo dài và mức đồng thời chưa?
- [ ] Đã đo cả time to first row và time to last row khi tập kết quả lớn chưa?
- [ ] Đã có baseline và so sánh sau thay đổi trong điều kiện tương đương chưa?
- [ ] Đã kiểm tra tác động phụ lên thao tác ghi và các truy vấn khác chưa?

## Kết luận

Hành trình của một yêu cầu SQL bắt đầu trước khi DBMS thực thi câu lệnh và chỉ kết thúc khi ứng dụng nhận, tiêu thụ kết quả theo nhu cầu. Độ trễ có thể đến từ connection pool, parse và plan, truy cập dữ liệu, CPU, bộ nhớ, I/O, tranh chấp giao dịch, commit hoặc truyền kết quả. Execution plan giúp hiểu DBMS dự định và thực tế xử lý dữ liệu như thế nào; thống kê và số liệu tải giúp giải thích vì sao kế hoạch đó được chọn và tài nguyên nào đang bị giới hạn.

Khi tối ưu hiệu năng cơ sở dữ liệu, hãy lần theo toàn bộ vòng đời, đo từng chặng bằng công cụ phù hợp, hình thành giả thuyết từ bằng chứng và kiểm chứng từng thay đổi trên tải đại diện. Cách làm này giúp cải thiện thời gian phản hồi mà vẫn bảo toàn tính đúng đắn và độ ổn định của hệ thống.


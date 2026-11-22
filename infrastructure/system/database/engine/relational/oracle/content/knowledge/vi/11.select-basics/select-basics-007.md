# ORDER BY, thứ tự NULL và yêu cầu sắp xếp xác định

Trong Oracle Database, một câu SELECT không tự cam kết trả các hàng theo thứ tự được lưu trên đĩa, thứ tự chèn, khóa chính hay thứ tự mà một lần chạy trước đó tình cờ hiển thị. Nếu ứng dụng cần kết quả theo ngày mới nhất, điểm cao nhất, tên tăng dần hoặc phân trang ổn định, phải mô tả thứ tự đó bằng **ORDER BY**.

Một yêu cầu sắp xếp đúng còn phải trả lời ba câu hỏi:

1. **Sắp xếp theo khóa nào và theo chiều nào?** Có thể là một cột, nhiều cột hoặc biểu thức tính toán.
2. **Giá trị NULL nằm ở đâu?** Oracle có thứ tự mặc định khác nhau giữa ASC và DESC; nên khai báo rõ khi NULL có ý nghĩa nghiệp vụ.
3. **Các hàng có cùng giá trị sắp xếp được xử lý thế nào?** Nếu nhiều hàng bằng nhau ở mọi khóa ORDER BY, thứ tự giữa chúng không được bảo đảm. Muốn kết quả xác định, cần thêm khóa phân biệt, thường là primary key.

Bài học này trình bày cú pháp ORDER BY, thứ tự NULL, sắp xếp nhiều khóa, biểu thức và collation, phân trang, top-N, analytic functions, tác động của index và cách xây dựng thứ tự xác định cho ứng dụng Java/JDBC.

## 1. Kết quả SELECT không có thứ tự mặc định

Một bảng heap trong Oracle được tổ chức theo block và segment, không phải như một danh sách luôn giữ thứ tự chèn. Câu truy vấn sau:

~~~sql
SELECT ma_don_hang, ma_khach_hang, ngay_dat
FROM don_hang;
~~~

không có cam kết rằng kết quả sẽ theo mã đơn, ngày đặt hoặc thứ tự INSERT. Kết quả có thể thay đổi sau khi:

- Optimizer chọn execution plan khác.
- Index được tạo, bỏ hoặc thay đổi.
- Thống kê optimizer được cập nhật.
- Dữ liệu được thêm, sửa, xóa hoặc tổ chức lại segment.
- Truy vấn chạy song song hoặc được thực hiện trong một môi trường tải khác.

Ngay cả khi một câu SELECT hôm nay tình cờ trả hàng theo khóa chính, đó cũng không phải hợp đồng thứ tự của SQL. **Chỉ ORDER BY ở query block cuối cùng mà ứng dụng nhận kết quả mới xác định thứ tự trả về.**

Ví dụ:

~~~sql
SELECT ma_don_hang, ngay_dat
FROM don_hang
ORDER BY ngay_dat DESC, ma_don_hang DESC;
~~~

Truy vấn yêu cầu ngày đặt mới hơn đứng trước; nếu nhiều đơn có cùng ngày, mã đơn lớn hơn đứng trước. Nếu tổ hợp hai khóa tạo thứ tự duy nhất, kết quả sẽ có một thứ tự xác định đối với cùng một tập dữ liệu.

## 2. Cú pháp cơ bản của ORDER BY

Cấu trúc tổng quát:

~~~sql
SELECT select_list
FROM table_or_view
WHERE condition
GROUP BY group_expression
HAVING group_condition
ORDER BY sort_expression [ASC | DESC] [NULLS FIRST | NULLS LAST];
~~~

Trong một câu truy vấn không có GROUP BY/HAVING, phần WHERE có thể được bỏ. ORDER BY thường nằm sau các mệnh đề lọc, nhóm và HAVING.

- **ASC**: thứ tự tăng dần; đây là mặc định nếu không chỉ rõ ASC/DESC.
- **DESC**: thứ tự giảm dần.
- **NULLS FIRST**: đưa giá trị NULL lên trước các giá trị không NULL.
- **NULLS LAST**: đưa NULL xuống sau các giá trị không NULL.

Ví dụ:

~~~sql
-- Giá tăng dần.
SELECT ma_san_pham, ten_san_pham, don_gia
FROM san_pham
ORDER BY don_gia ASC;

-- Giá giảm dần.
SELECT ma_san_pham, ten_san_pham, don_gia
FROM san_pham
ORDER BY don_gia DESC;
~~~

Với dữ liệu số, ASC thường cho số nhỏ trước; DESC cho số lớn trước. Với ngày giờ, ASC đưa thời điểm sớm lên trước; DESC đưa thời điểm mới lên trước. Với chuỗi, kết quả còn phụ thuộc quy tắc so sánh/collation.

### 2.1. ORDER BY theo alias trong SELECT

Có thể đặt bí danh cho biểu thức trong danh sách SELECT rồi dùng alias để sắp xếp:

~~~sql
SELECT ma_don_hang,
       so_luong * don_gia AS thanh_tien
FROM chi_tiet_don_hang
ORDER BY thanh_tien DESC, ma_don_hang ASC;
~~~

Alias giúp câu SQL dễ đọc hơn khi biểu thức dài. Trong cùng query block, ORDER BY có thể tham chiếu select-list alias theo quy tắc Oracle. Không nên dùng alias ở WHERE của cùng query block như thể nó đã được tính trước SELECT.

### 2.2. ORDER BY theo vị trí cột

Oracle cho phép dùng vị trí trong select list:

~~~sql
SELECT ma_don_hang, ngay_dat, trang_thai
FROM don_hang
ORDER BY 2 DESC, 1 ASC;
~~~

Số 2 chỉ cột thứ hai (NGAY_DAT), số 1 chỉ cột đầu (MA_DON_HANG). Cách viết này ngắn nhưng dễ gây lỗi khi người khác thay đổi thứ tự cột trong SELECT. Trong mã ứng dụng và tài liệu nghiệp vụ, nên ưu tiên **tên cột hoặc alias** để ý nghĩa rõ ràng.

### 2.3. Biểu thức trong ORDER BY

Có thể sắp xếp theo biểu thức tính toán:

~~~sql
SELECT ma_nhan_vien,
       ho_ten,
       luong
FROM nhan_vien
ORDER BY luong * 12 DESC, ma_nhan_vien ASC;
~~~

Ví dụ trên sắp theo lương năm giả định, rồi theo mã nhân viên. Có thể dùng CASE, hàm ngày giờ, phép toán số học hoặc hàm chuỗi làm sort key. Hãy bảo đảm kiểu dữ liệu và cách chuyển đổi rõ ràng; không dựa vào implicit conversion giữa số, ngày và chuỗi.

## 3. Sắp xếp nhiều khóa: thứ tự từ trái sang phải

Khi ORDER BY có nhiều biểu thức, Oracle so sánh theo thứ tự ưu tiên từ trái sang phải:

1. So sánh khóa thứ nhất.
2. Nếu bằng nhau, so sánh khóa thứ hai.
3. Nếu tiếp tục bằng nhau, so sánh khóa thứ ba.
4. Tiếp tục đến khi có khóa phân biệt hoặc hết danh sách.

Ví dụ sắp xếp nhân viên theo phòng ban, lương giảm dần và mã nhân viên tăng dần:

~~~sql
SELECT ma_nhan_vien,
       ma_phong,
       ho_ten,
       luong
FROM nhan_vien
ORDER BY ma_phong ASC,
         luong DESC,
         ma_nhan_vien ASC;
~~~

Kết quả được chia nhóm theo mã phòng tăng dần. Trong từng phòng, người lương cao hơn đứng trước. Nếu hai nhân viên cùng lương, mã nhân viên nhỏ hơn đứng trước.

### 3.1. Mỗi khóa có chiều riêng

Không có yêu cầu tất cả khóa phải dùng cùng một chiều:

~~~sql
SELECT ma_don_hang,
       trang_thai,
       ngay_dat,
       tong_tien
FROM don_hang
ORDER BY
    CASE trang_thai
        WHEN 'PENDING' THEN 1
        WHEN 'PAID' THEN 2
        WHEN 'SHIPPED' THEN 3
        WHEN 'CANCELLED' THEN 4
        ELSE 5
    END ASC,
    ngay_dat DESC,
    ma_don_hang ASC;
~~~

Thứ tự nghiệp vụ được tạo bằng CASE, sau đó ngày mới nhất đứng trước và mã đơn làm khóa phụ. Đây là cách thể hiện thứ tự trạng thái tùy chỉnh thay vì hy vọng thứ tự alphabet của chuỗi trùng với thứ tự nghiệp vụ.

### 3.2. Khóa cuối cùng nên phân biệt các hàng

Nếu mã đơn là primary key, ví dụ:

~~~sql
ORDER BY ngay_dat DESC, ma_don_hang DESC
~~~

thì hai hàng khác nhau không thể có cùng toàn bộ tổ hợp sort key, vì MA_DON_HANG là duy nhất. Đây là **total ordering** trên tập kết quả.

Ngược lại:

~~~sql
ORDER BY ngay_dat DESC
~~~

chỉ xác định thứ tự giữa các ngày khác nhau. Nếu nhiều đơn có cùng NGAY_DAT, thứ tự tương đối giữa các đơn đó không được đảm bảo.

Có thể dùng một tổ hợp khóa thay vì một cột duy nhất, miễn là tổ hợp đó phân biệt mọi hàng trong kết quả. Với truy vấn JOIN làm một đơn xuất hiện nhiều lần do có nhiều dòng chi tiết, chỉ thêm mã đơn chưa chắc đủ; có thể cần cả mã sản phẩm hoặc khóa chính của dòng chi tiết.

## 4. Thứ tự NULL trong Oracle

NULL biểu thị giá trị chưa biết, chưa cung cấp hoặc không áp dụng theo mô hình dữ liệu. Nó không phải số 0, chuỗi rỗng có ý nghĩa nghiệp vụ hay ngày mặc định.

Oracle có quy tắc mặc định:

| Cách sắp xếp | Vị trí mặc định của NULL |
| --- | --- |
| **ASC** | **NULLS LAST** |
| **DESC** | **NULLS FIRST** |

Nói cách khác, trong Oracle NULL được xem như giá trị lớn hơn các giá trị không NULL cho mục đích thứ tự mặc định. Đây là điểm dễ gây ngạc nhiên nếu ứng dụng mong NULL luôn ở cuối danh sách.

### 4.1. ASC và NULLS LAST

~~~sql
SELECT ma_nhan_vien, ho_ten, ngay_nghi_viec
FROM nhan_vien
ORDER BY ngay_nghi_viec ASC;
~~~

Với mặc định ASC, các ngày nhỏ hơn đứng trước, NULL đứng cuối. Đây thường là kết quả mong muốn khi cột ngày nghỉ việc NULL có nghĩa nhân viên vẫn đang làm việc hoặc chưa xác định ngày nghỉ.

Để ý nghĩa được thể hiện rõ trong code:

~~~sql
SELECT ma_nhan_vien, ho_ten, ngay_nghi_viec
FROM nhan_vien
ORDER BY ngay_nghi_viec ASC NULLS LAST,
         ma_nhan_vien ASC;
~~~

Khai báo NULLS LAST tường minh giúp người đọc không phải nhớ mặc định của Oracle.

### 4.2. DESC mặc định đưa NULL lên đầu

~~~sql
SELECT ma_nhan_vien, ho_ten, ngay_nghi_viec
FROM nhan_vien
ORDER BY ngay_nghi_viec DESC;
~~~

Trong Oracle, DESC mặc định là NULLS FIRST. Nếu NULL có nghĩa “chưa nghỉ việc” và muốn nhóm này nằm cuối danh sách, phải viết:

~~~sql
SELECT ma_nhan_vien, ho_ten, ngay_nghi_viec
FROM nhan_vien
ORDER BY ngay_nghi_viec DESC NULLS LAST,
         ma_nhan_vien ASC;
~~~

Không suy luận rằng DESC tự động đặt NULL cuối vì đó là cách nhiều giao diện hoặc hệ quản trị khác có thể được cấu hình.

### 4.3. NULLS FIRST và NULLS LAST trên từng khóa

Mỗi biểu thức sort có thể khai báo vị trí NULL riêng:

~~~sql
SELECT ma_cong_viec,
       ngay_hoan_tat,
       muc_uu_tien
FROM cong_viec
ORDER BY ngay_hoan_tat DESC NULLS LAST,
         muc_uu_tien ASC NULLS FIRST,
         ma_cong_viec ASC;
~~~

Ở đây:
- Công việc đã hoàn tất gần đây đứng trước; ngày hoàn tất NULL nằm cuối.
- Trong cùng thời điểm, ưu tiên thấp hơn theo thứ tự số đứng trước.
- Ưu tiên NULL được đưa lên đầu trong nhóm khóa thứ hai.
- Mã công việc là khóa phụ cuối cùng.

Vị trí NULL được đánh giá theo từng khóa khi khóa trước bằng nhau; NULLS LAST của khóa đầu không tự áp dụng cho khóa sau.

### 4.4. NULL không đồng nghĩa với giá trị thay thế

Có thể dùng NVL/COALESCE để thay NULL trong biểu thức:

~~~sql
SELECT ma_nhan_vien, ho_ten, diem
FROM nhan_vien
ORDER BY NVL(diem, -1) DESC,
         ma_nhan_vien;
~~~

Cách này đưa điểm NULL xuống sau nếu điểm hợp lệ không âm. Nhưng nó **thay đổi sort key**: nếu -1 là giá trị thực hợp lệ hoặc có thể xuất hiện trong dữ liệu, NULL và -1 có thể trở thành cùng khóa. Ngoài ra, hàm trên cột có thể làm thay đổi khả năng dùng index thông thường.

Nếu chỉ muốn quyết định vị trí NULL, ưu tiên:

~~~sql
ORDER BY diem DESC NULLS LAST, ma_nhan_vien
~~~

Dùng NVL/COALESCE khi thật sự muốn coi NULL như một giá trị thay thế theo quy tắc nghiệp vụ, không chỉ để điều khiển vị trí NULL.

## 5. Sắp xếp NULL bằng CASE khi cần quy tắc tùy chỉnh

CASE có thể tạo khóa ưu tiên riêng, hữu ích khi thứ tự nghiệp vụ phức tạp hơn NULLS FIRST/LAST:

~~~sql
SELECT ma_nhan_vien,
       ho_ten,
       ngay_nghi_viec
FROM nhan_vien
ORDER BY
    CASE
        WHEN ngay_nghi_viec IS NULL THEN 1
        ELSE 0
    END ASC,
    ngay_nghi_viec DESC,
    ma_nhan_vien ASC;
~~~

Khóa CASE đặt hàng có ngày nghỉ việc trước, hàng NULL sau. Trong nhóm đã có ngày, ngày gần nhất đứng trước; mã nhân viên phá hòa.

Có thể sắp xếp NULL lên đầu bằng cách đổi 1 và 0:

~~~sql
ORDER BY
    CASE WHEN ngay_nghi_viec IS NULL THEN 0 ELSE 1 END,
    ngay_nghi_viec DESC,
    ma_nhan_vien;
~~~

Đối với quy tắc chỉ cần đưa NULL lên đầu/cuối, cú pháp NULLS FIRST/LAST ngắn và trực tiếp hơn. CASE phù hợp khi có nhiều nhóm trạng thái hoặc cần ưu tiên một số giá trị cụ thể.

## 6. Sắp xếp chuỗi: collation và NLS

Thứ tự chuỗi không chỉ đơn giản là A trước B theo cách mắt người đọc. Nó phụ thuộc cách Oracle so sánh ký tự và cấu hình collation/NLS.

Những yếu tố có thể ảnh hưởng:
- Chữ hoa và chữ thường.
- Dấu tiếng Việt và các dấu phụ.
- Thứ tự theo ngôn ngữ.
- Thiết lập NLS của session.
- Biểu thức/collation được áp dụng trực tiếp trong truy vấn.

### 6.1. NLS_SORT và NLS_COMP

Có thể xem các thiết lập phiên:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_SORT', 'NLS_COMP')
ORDER BY parameter;
~~~

NLS_SORT quy định quy tắc sắp xếp ngôn ngữ; NLS_COMP ảnh hưởng cách Oracle áp dụng so sánh ngôn ngữ trong những ngữ cảnh tương ứng. Hành vi cụ thể phụ thuộc cấu hình phiên và phiên bản Oracle.

Không nên dựa vào mặc định môi trường phát triển để suy ra thứ tự chuỗi trên production, nhất là khi database được sử dụng bởi nhiều ứng dụng hoặc session pool.

### 6.2. NLSSORT để chỉ rõ quy tắc sắp xếp

Có thể tạo sort key ngôn ngữ tường minh bằng NLSSORT:

~~~sql
SELECT ho_ten
FROM nhan_vien
ORDER BY NLSSORT(ho_ten, 'NLS_SORT=BINARY_CI'),
         ma_nhan_vien;
~~~

BINARY_CI minh họa thứ tự không phân biệt chữ hoa/chữ thường ở mức binary case-insensitive. Với dữ liệu tiếng Việt, cần chọn quy tắc linguistic phù hợp và kiểm thử chính xác trên phiên bản Oracle/collation đang dùng; không giả định BINARY_CI tự xử lý mọi quy tắc dấu tiếng Việt theo mong muốn.

Có thể dùng những kiểu linguistic sort khác theo Oracle hỗ trợ, nhưng phải xem tên sort hợp lệ trong môi trường triển khai.

### 6.3. Khóa phụ vẫn cần thiết sau NLSSORT

Hai chuỗi khác nhau có thể tạo sort key tương đương theo quy tắc collation không phân biệt hoa/thường hoặc dấu. Vì vậy:

~~~sql
ORDER BY NLSSORT(ho_ten, 'NLS_SORT=BINARY_CI'),
         ma_nhan_vien;
~~~

vẫn cần mã nhân viên để có thứ tự xác định khi hai tên được xem là tương đương theo collation.

### 6.4. Tránh sắp xếp số được lưu dưới dạng chuỗi

Giả sử cột MA_THU_TU là VARCHAR2 chứa '2', '10', '100'. ORDER BY theo chuỗi có thể đưa '10' trước '2' vì đó là thứ tự ký tự, không phải thứ tự số.

~~~sql
SELECT ma_thu_tu
FROM du_lieu_import
ORDER BY ma_thu_tu;
~~~

Nếu dữ liệu thực sự mang ý nghĩa số, nên lưu kiểu NUMBER. Khi phải xử lý dữ liệu import có chuỗi số, chuyển kiểu tường minh và kiểm soát các giá trị không hợp lệ:

~~~sql
SELECT ma_thu_tu
FROM du_lieu_import
ORDER BY TO_NUMBER(ma_thu_tu);
~~~

Câu trên chỉ phù hợp nếu mọi giá trị đều chuyển được sang NUMBER. Với dữ liệu không sạch, cần kiểm tra/chuẩn hóa trước hoặc dùng CASE/VALIDATE_CONVERSION phù hợp với phiên bản để tránh lỗi chuyển kiểu.

## 7. ORDER BY với GROUP BY và hàm tổng hợp

Sau khi GROUP BY, ORDER BY thường sắp xếp các nhóm theo biểu thức tổng hợp hoặc khóa nhóm:

~~~sql
SELECT ma_phong,
       COUNT(*) AS so_nhan_vien,
       AVG(luong) AS luong_trung_binh
FROM nhan_vien
GROUP BY ma_phong
ORDER BY so_nhan_vien DESC NULLS LAST,
         ma_phong ASC;
~~~

Nhóm có số nhân viên lớn đứng trước; nếu bằng nhau thì mã phòng tăng dần. Trong ví dụ COUNT(*) không trả NULL, nhưng cú pháp NULLS LAST vẫn minh họa cách viết tường minh.

Có thể sắp theo biểu thức tổng hợp:

~~~sql
SELECT ma_phong,
       SUM(luong) AS tong_luong
FROM nhan_vien
GROUP BY ma_phong
ORDER BY SUM(luong) DESC, ma_phong;
~~~

Khi dùng alias tổng hợp, ưu tiên alias giúp biểu thức dễ đọc. Nếu ORDER BY có biểu thức không thuộc nhóm hợp lệ sau GROUP BY, Oracle có thể báo lỗi; phải bảo đảm khóa sắp xếp tương thích với các biểu thức nhóm.

### 7.1. ORDER BY sau DISTINCT

Với SELECT DISTINCT, Oracle có quy tắc giới hạn biểu thức ORDER BY: biểu thức dùng để sắp xếp cần nằm trong danh sách SELECT theo các quy tắc tương ứng. Ví dụ:

~~~sql
SELECT DISTINCT ma_phong
FROM nhan_vien
ORDER BY ma_phong;
~~~

là rõ ràng. Nếu muốn SELECT DISTINCT một tập cột nhưng sắp xếp theo một biểu thức không được chọn, cần thiết kế lại query block, ví dụ đưa DISTINCT vào inline view rồi sắp xếp ở query block ngoài khi ngữ nghĩa phù hợp. Không giả định mọi cột của bảng đều có thể dùng trong ORDER BY sau DISTINCT.

## 8. ORDER BY trong subquery, view và set operator

### 8.1. ORDER BY trong query block bên trong không thay thế thứ tự ngoài

Một inline view hoặc view có thể có logic sắp xếp phục vụ row limiting hoặc tính toán cụ thể, nhưng **không nên dựa vào thứ tự bên trong để bảo đảm thứ tự kết quả query block ngoài**.

~~~sql
SELECT ma_don_hang, ngay_dat
FROM (
    SELECT ma_don_hang, ngay_dat
    FROM don_hang
    ORDER BY ngay_dat DESC
)
WHERE ROWNUM <= 10;
~~~

Đây là mẫu top-N cũ: ORDER BY nằm trong inline view để xác định tập 10 hàng trước khi ROWNUM được áp dụng ở query block ngoài. Tuy nhiên, nếu có nhiều đơn cùng NGAY_DAT, 10 hàng ở biên vẫn không được xác định hoàn toàn nếu thiếu khóa phụ.

Khi muốn kết quả cuối có thứ tự xác định, thêm ORDER BY ở ngoài:

~~~sql
SELECT ma_don_hang, ngay_dat
FROM (
    SELECT ma_don_hang, ngay_dat
    FROM don_hang
    ORDER BY ngay_dat DESC, ma_don_hang DESC
)
WHERE ROWNUM <= 10
ORDER BY ngay_dat DESC, ma_don_hang DESC;
~~~

### 8.2. ORDER BY ở cuối compound query

Với UNION, UNION ALL, INTERSECT hoặc MINUS, ORDER BY thường đặt ở cuối toàn bộ compound query để sắp xếp kết quả hợp nhất:

~~~sql
SELECT ma_khach_hang AS ma
FROM khach_hang
WHERE trang_thai = 'ACTIVE'
UNION
SELECT ma_khach_hang AS ma
FROM khach_hang_lich_su
ORDER BY ma;
~~~

Tên alias của select list đầu tiên thường được dùng để tham chiếu cột kết quả. Không đặt một ORDER BY độc lập giữa các nhánh rồi kỳ vọng thứ tự cuối cùng được giữ nguyên. Nếu cần sắp xếp nội bộ để chọn top-N trong một nhánh, đặt query block con phù hợp và sắp xếp kết quả ngoài riêng.

### 8.3. ORDER BY trong view không tạo hợp đồng thứ tự cho caller

View biểu diễn một truy vấn được lưu. Ngay cả khi một định nghĩa view có cơ chế/giới hạn cho phép chứa ORDER BY trong một ngữ cảnh cụ thể, caller vẫn nên khai báo ORDER BY của chính câu SELECT cuối cùng:

~~~sql
SELECT ma_khach_hang, ho_ten
FROM v_khach_hang
ORDER BY ho_ten ASC NULLS LAST, ma_khach_hang;
~~~

Không xem thứ tự quan sát được khi chạy SELECT từ view là thứ tự cố định nếu câu truy vấn ngoài không có ORDER BY.

## 9. ORDER BY trong analytic function khác ORDER BY của kết quả

Các hàm phân tích như ROW_NUMBER, RANK, DENSE_RANK, LAG, LEAD có thể có ORDER BY trong mệnh đề OVER:

~~~sql
SELECT ma_nhan_vien,
       ma_phong,
       luong,
       ROW_NUMBER() OVER (
           PARTITION BY ma_phong
           ORDER BY luong DESC, ma_nhan_vien
       ) AS thu_hang_trong_phong
FROM nhan_vien;
~~~

ORDER BY trong OVER xác định thứ tự xử lý **bên trong cửa sổ phân tích** và cách đánh số hàng. Nó không tự bảo đảm thứ tự các hàng cuối cùng trả ra client.

Muốn cả thứ hạng lẫn thứ tự hiển thị ổn định:

~~~sql
SELECT ma_nhan_vien,
       ma_phong,
       luong,
       ROW_NUMBER() OVER (
           PARTITION BY ma_phong
           ORDER BY luong DESC, ma_nhan_vien
       ) AS thu_hang_trong_phong
FROM nhan_vien
ORDER BY ma_phong,
         thu_hang_trong_phong;
~~~

### 9.1. ROW_NUMBER và RANK khác nhau

- **ROW_NUMBER** gán số duy nhất cho mỗi hàng theo thứ tự window. Nếu khóa window bị trùng, hàng nào nhận số trước có thể không xác định nếu thiếu khóa phụ.
- **RANK** cho các hàng cùng giá trị sort key cùng hạng, và để khoảng trống ở hạng tiếp theo.
- **DENSE_RANK** cho các hàng cùng giá trị cùng hạng nhưng không bỏ số hạng tiếp theo.

Ví dụ:

~~~sql
SELECT ma_nhan_vien,
       diem,
       RANK() OVER (ORDER BY diem DESC NULLS LAST) AS hang,
       DENSE_RANK() OVER (ORDER BY diem DESC NULLS LAST) AS hang_day
FROM ket_qua_thi
ORDER BY diem DESC NULLS LAST, ma_nhan_vien;
~~~

Ở đây RANK/DENSE_RANK chỉ xét điểm, nên người bằng điểm có cùng hạng. ORDER BY ngoài thêm mã nhân viên để hiển thị ổn định. Nếu thêm mã nhân viên vào trong ORDER BY của RANK, hai người bằng điểm sẽ không còn đồng hạng; đó là thay đổi ngữ nghĩa nghiệp vụ, không chỉ là kỹ thuật phá hòa.

## 10. Top-N và phân trang ổn định

Ứng dụng thường cần lấy 10 sản phẩm giá cao nhất, 20 đơn mới nhất hoặc trang thứ ba của danh sách khách hàng. Những thao tác này cần thứ tự xác định.

### 10.1. FETCH FIRST và OFFSET/FETCH

Oracle hỗ trợ row limiting clause trong các phiên bản hiện đại (từ Oracle 12c):

~~~sql
SELECT ma_san_pham, ten_san_pham, don_gia
FROM san_pham
ORDER BY don_gia DESC NULLS LAST,
         ma_san_pham
FETCH FIRST 10 ROWS ONLY;
~~~

Câu truy vấn trả tối đa 10 hàng theo giá giảm dần, NULL cuối, rồi mã sản phẩm phá hòa. Nếu không thêm khóa duy nhất, khi có nhiều sản phẩm cùng giá ở ranh giới top 10, tập hàng được chọn có thể thay đổi.

Lấy trang với OFFSET/FETCH:

~~~sql
SELECT ma_khach_hang, ho_ten, ngay_dang_ky
FROM khach_hang
ORDER BY ngay_dang_ky DESC NULLS LAST,
         ma_khach_hang DESC
OFFSET 20 ROWS FETCH NEXT 10 ROWS ONLY;
~~~

Đây là trang bắt đầu sau 20 hàng, lấy tối đa 10 hàng. Nếu sắp xếp theo NGAY_DANG_KY nhưng không thêm mã khách hàng, nhiều khách đăng ký cùng ngày có thể đổi vị trí giữa các lần chạy.

### 10.2. WITH TIES

~~~sql
SELECT ma_san_pham, ten_san_pham, don_gia
FROM san_pham
ORDER BY don_gia DESC NULLS LAST
FETCH FIRST 10 ROWS WITH TIES;
~~~

WITH TIES lấy thêm các hàng có cùng giá trị khóa sắp xếp với hàng ở ranh giới top-N. Đây là lựa chọn khi nghiệp vụ muốn **giữ toàn bộ hàng đồng hạng** thay vì cắt đúng N hàng.

Nếu thêm mã sản phẩm duy nhất vào ORDER BY, các hàng khác nhau thường không còn cùng toàn bộ sort key, vì thế WITH TIES có thể không còn giữ nhóm đồng giá như mong muốn. Hãy chọn sort key theo đúng ý nghĩa: đồng hạng theo điểm/giá hay cần thứ tự duy nhất cho phân trang.

### 10.3. Top-N với ROW_NUMBER

Có thể dùng analytic function để kiểm soát số hàng:

~~~sql
SELECT ma_san_pham, ten_san_pham, don_gia
FROM (
    SELECT ma_san_pham,
           ten_san_pham,
           don_gia,
           ROW_NUMBER() OVER (
               ORDER BY don_gia DESC NULLS LAST,
                        ma_san_pham
           ) AS rn
    FROM san_pham
)
WHERE rn <= 10
ORDER BY rn;
~~~

ROW_NUMBER với khóa phụ duy nhất tạo ra top 10 xác định trên cùng một tập dữ liệu. Nếu muốn đồng hạng, dùng RANK/DENSE_RANK theo đúng khóa điểm/giá, thay vì ROW_NUMBER.

### 10.4. Phân trang bằng keyset pagination

OFFSET lớn có thể khiến Oracle phải tìm và bỏ qua nhiều hàng trước khi trả trang cần thiết. Với danh sách sắp xếp theo NGAY_DAT DESC và MA_DON_HANG DESC, trang kế tiếp có thể bắt đầu sau khóa cuối cùng của trang trước:

~~~sql
SELECT ma_don_hang, ngay_dat, trang_thai
FROM don_hang
WHERE ngay_dat < :last_ngay_dat
   OR (
        ngay_dat = :last_ngay_dat
        AND ma_don_hang < :last_ma_don_hang
      )
ORDER BY ngay_dat DESC,
         ma_don_hang DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Đây là mẫu keyset pagination cho sort key không NULL. Nó sử dụng giá trị khóa cuối trang trước để tiếp tục, tránh phải OFFSET qua tất cả hàng cũ.

Nếu NGAY_DAT có thể NULL, phải thiết kế nhánh predicate và quy tắc NULLS FIRST/LAST tương ứng. Không dùng phép so sánh = với NULL; cần xử lý IS NULL và xác định khóa tiếp trang phù hợp. Trong nhiều hệ thống, chọn cột sort key bắt buộc NOT NULL giúp pagination đơn giản hơn.

Keyset pagination vẫn cần thứ tự duy nhất, ổn định và khóa phân trang được bind chính xác. Nếu dữ liệu thay đổi giữa hai request, hàng mới có thể xuất hiện trước/sau con trỏ tùy sort key. Khi cần một snapshot nhất quán qua nhiều trang, phải xét transaction/read consistency hoặc một mốc dữ liệu/SCN theo thiết kế.

## 11. Tạo thứ tự xác định: total order và tie-breaker

Một truy vấn có thứ tự xác định khi sort key phân biệt mọi hàng trong tập kết quả. Đây là điều kiện quan trọng cho:

- Phân trang không lặp/mất hàng do tie không xác định trên cùng snapshot.
- Top-N lặp lại được.
- Báo cáo có thứ tự ổn định.
- Xuất CSV/Excel có thể so sánh giữa các lần chạy.
- Test tự động không phụ thuộc thứ tự tình cờ.
- API có contract rõ ràng cho client.

### 11.1. Ví dụ chưa xác định

~~~sql
SELECT ma_don_hang, ngay_dat
FROM don_hang
ORDER BY ngay_dat DESC;
~~~

Nếu 50 đơn có cùng NGAY_DAT, Oracle không cam kết thứ tự tương đối của 50 đơn ấy. Kế hoạch chạy hôm nay có thể hiển thị theo mã vật lý hoặc index; lần sau có thể khác.

### 11.2. Thêm khóa duy nhất

~~~sql
SELECT ma_don_hang, ngay_dat
FROM don_hang
ORDER BY ngay_dat DESC NULLS LAST,
         ma_don_hang DESC;
~~~

Nếu MA_DON_HANG là primary key, tổ hợp khóa đã phân biệt mọi hàng. NULLS LAST còn xác định vị trí của ngày chưa biết.

### 11.3. Khi kết quả JOIN tạo nhiều dòng cho một thực thể

~~~sql
SELECT d.ma_don_hang,
       ct.ma_san_pham,
       ct.so_luong
FROM don_hang d
JOIN chi_tiet_don_hang ct
  ON ct.ma_don_hang = d.ma_don_hang
ORDER BY d.ngay_dat DESC,
         d.ma_don_hang DESC,
         ct.ma_san_pham ASC;
~~~

Ở đây MA_DON_HANG một mình không duy nhất trong kết quả vì mỗi đơn có nhiều dòng chi tiết. Nếu cặp MA_DON_HANG và MA_SAN_PHAM là khóa chính của bảng chi tiết, ba sort key trên tạo thứ tự phân biệt các dòng kết quả.

### 11.4. Tổ hợp khóa phải phản ánh đúng dữ liệu đã lọc

Nếu query GROUP BY, DISTINCT hoặc UNION, khóa chính của bảng gốc có thể không còn xuất hiện trong tập kết quả. Cần chọn khóa phá hòa phù hợp với **mỗi hàng sau khi biến đổi**, chẳng hạn các cột nhóm hoặc alias biểu thức tổng hợp cùng một khóa phân biệt nhóm.

Không thể thêm tùy tiện cột ngoài tập SELECT vào ORDER BY sau DISTINCT. Có thể cần tạo inline view để đưa khóa cần thiết vào query block đúng nơi.

## 12. ORDER BY và index: sắp xếp có thể tốn tài nguyên

Oracle có thể chọn một index để trả hàng theo thứ tự phù hợp mà không cần thực hiện một thao tác sort riêng, nhưng điều đó **không được bảo đảm chỉ vì cột ORDER BY có index**.

Ví dụ:

~~~sql
CREATE INDEX ix_don_hang_ngay_ma
    ON don_hang (ngay_dat DESC, ma_don_hang DESC);
~~~

Truy vấn:

~~~sql
SELECT ma_don_hang, ngay_dat
FROM don_hang
ORDER BY ngay_dat DESC, ma_don_hang DESC;
~~~

có thể tận dụng index nếu access path, điều kiện lọc, cấu trúc index và yêu cầu NULL phù hợp. Optimizer vẫn có thể chọn một plan khác nếu ước lượng chi phí thấp hơn.

### 12.1. Điều gì ảnh hưởng khả năng dùng index để trả thứ tự?

- Các cột sort có nằm ở phần đầu của index theo thứ tự phù hợp không?
- Chiều ASC/DESC có thể được đáp ứng bằng scan thuận/ngược không?
- Query có biểu thức như NVL, CASE, NLSSORT hay hàm trên cột không?
- Điều kiện WHERE có làm thay đổi access path?
- Sort key có bao gồm cột không có trong index không?
- NULL và cấu trúc composite index có phù hợp với kết quả cần trả không?
- Optimizer đánh giá full scan + sort có rẻ hơn index access không?

Một B-tree index một cột thường không lưu entry cho hàng mà **tất cả các cột của index đều NULL**. Với composite index, hàng có ít nhất một cột key không NULL có thể vẫn có entry. Vì vậy không suy luận mọi hàng NULL đều biến mất khỏi mọi index; phải xét cấu trúc index.

### 12.2. Xem execution plan

Có thể dùng EXPLAIN PLAN trong môi trường thực hành:

~~~sql
EXPLAIN PLAN FOR
SELECT ma_don_hang, ngay_dat
FROM don_hang
ORDER BY ngay_dat DESC NULLS LAST,
         ma_don_hang DESC;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Trong plan có thể thấy thao tác như **SORT ORDER BY**, **SORT ORDER BY STOPKEY**, hoặc một access path có thể đáp ứng thứ tự. Chi tiết phụ thuộc phiên bản và plan thực tế. EXPLAIN PLAN cho biết plan được ước lượng; khi chẩn đoán production, cần xem cursor plan/runtime statistics thích hợp nếu có quyền.

### 12.3. Sort dùng bộ nhớ và TEMP

Nếu Oracle phải sort lượng dữ liệu lớn, thao tác có thể sử dụng workarea trong PGA. Khi không đủ bộ nhớ, sort có thể spill ra TEMP tablespace. ORDER BY trên hàng triệu bản ghi hoặc sort nhiều cột/biểu thức có thể tốn CPU, I/O và TEMP.

Một số nguyên tắc:
- Lọc dữ liệu hợp lý trước khi sort khi ngữ nghĩa cho phép.
- Chỉ SELECT các cột cần thiết thay vì kéo toàn bộ payload lớn.
- Dùng top-N/row limiting khi chỉ cần một số hàng.
- Chọn index dựa trên workload và đo execution plan.
- Không tạo index cho mọi ORDER BY vì index cũng tốn dung lượng và chi phí DML.

## 13. Bộ dữ liệu mẫu để thực hành thứ tự NULL và tie-breaker

Chạy trên schema sandbox có quyền tạo bảng. Các mã được đặt cố định để có thể đối chiếu kết quả.

### 13.1. Tạo bảng

~~~sql
CREATE TABLE nhan_vien_sort (
    ma_nhan_vien NUMBER(6)
        CONSTRAINT pk_nhan_vien_sort PRIMARY KEY,
    ho_ten       VARCHAR2(100 CHAR) NOT NULL,
    ma_phong     NUMBER(4),
    diem         NUMBER(5, 2),
    ngay_vao     DATE,
    ngay_nghi    DATE
);
~~~

### 13.2. Nạp dữ liệu

~~~sql
INSERT INTO nhan_vien_sort VALUES
    (101, 'An', 10, 9.50, DATE '2022-01-10', NULL);

INSERT INTO nhan_vien_sort VALUES
    (102, 'Binh', 10, 9.50, DATE '2022-01-10', NULL);

INSERT INTO nhan_vien_sort VALUES
    (103, 'Chi', 20, 8.00, DATE '2023-03-15', DATE '2024-02-01');

INSERT INTO nhan_vien_sort VALUES
    (104, 'Dung', 20, NULL, DATE '2023-03-15', NULL);

INSERT INTO nhan_vien_sort VALUES
    (105, 'Giang', 10, 7.25, NULL, DATE '2024-01-31');

INSERT INTO nhan_vien_sort VALUES
    (106, 'Hanh', 30, 9.50, DATE '2022-01-10', DATE '2024-02-01');

INSERT INTO nhan_vien_sort VALUES
    (107, 'Khanh', 30, NULL, NULL, NULL);

COMMIT;
~~~

Bộ dữ liệu cố ý có:
- Điểm bằng nhau giữa các nhân viên 101, 102 và 106.
- Ngày vào làm trùng nhau.
- Điểm NULL ở nhân viên 104 và 107.
- Ngày vào làm NULL ở nhân viên 105 và 107.
- Ngày nghỉ NULL và ngày nghỉ đã biết.

### 13.3. Điểm giảm dần với NULL cuối và mã phá hòa

~~~sql
SELECT ma_nhan_vien, ho_ten, diem
FROM nhan_vien_sort
ORDER BY diem DESC NULLS LAST,
         ma_nhan_vien ASC;
~~~

Thứ tự dự kiến:

| Thứ tự | Mã | Tên | Điểm |
| ---: | ---: | --- | ---: |
| 1 | 101 | An | 9.50 |
| 2 | 102 | Binh | 9.50 |
| 3 | 106 | Hanh | 9.50 |
| 4 | 103 | Chi | 8.00 |
| 5 | 105 | Giang | 7.25 |
| 6 | 104 | Dung | NULL |
| 7 | 107 | Khanh | NULL |

Ba hàng điểm 9.50 được xếp theo mã nhân viên tăng dần. Hai hàng NULL cũng được xếp theo mã, nên toàn bộ kết quả có thứ tự xác định.

### 13.4. So sánh mặc định DESC và DESC NULLS LAST

~~~sql
-- Oracle mặc định NULLS FIRST cho DESC.
SELECT ma_nhan_vien, ho_ten, diem
FROM nhan_vien_sort
ORDER BY diem DESC;

-- Đưa NULL xuống cuối.
SELECT ma_nhan_vien, ho_ten, diem
FROM nhan_vien_sort
ORDER BY diem DESC NULLS LAST,
         ma_nhan_vien;
~~~

Truy vấn đầu đưa các hàng điểm NULL lên đầu theo mặc định của Oracle. Truy vấn thứ hai đưa NULL xuống cuối và thêm khóa phụ. Hai câu có ý nghĩa hiển thị khác nhau dù cùng dùng DESC.

### 13.5. Nhân viên chưa nghỉ việc lên đầu

~~~sql
SELECT ma_nhan_vien, ho_ten, ngay_nghi
FROM nhan_vien_sort
ORDER BY
    CASE WHEN ngay_nghi IS NULL THEN 0 ELSE 1 END,
    ngay_nghi DESC,
    ma_nhan_vien;
~~~

Các nhân viên có NGAY_NGHI NULL đứng trước; trong nhóm đã nghỉ, ngày nghỉ gần nhất đứng trước. Mã nhân viên đảm bảo thứ tự ổn định trong trường hợp cùng ngày hoặc cùng trạng thái NULL.

### 13.6. Phân trang ổn định

~~~sql
SELECT ma_nhan_vien, ho_ten, diem
FROM nhan_vien_sort
ORDER BY diem DESC NULLS LAST,
         ma_nhan_vien
OFFSET 2 ROWS FETCH NEXT 3 ROWS ONLY;
~~~

Truy vấn lấy ba hàng sau hai hàng đầu tiên theo thứ tự điểm giảm dần, NULL cuối và mã nhân viên tăng dần. Nếu bỏ mã nhân viên, vị trí trang tại ranh giới những hàng đồng điểm có thể thay đổi giữa các lần chạy.

### 13.7. Dọn bảng thực hành

~~~sql
DROP TABLE nhan_vien_sort PURGE;
~~~

Chỉ thực hiện trên bảng sandbox do bài tập tạo và khi không còn cần dữ liệu. DROP TABLE là DDL, có quy tắc implicit commit; PURGE bỏ qua recycle bin theo hành vi thông thường.

## 14. Những lỗi và nhầm lẫn thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Kết quả thay đổi thứ tự dù dữ liệu không đổi | Không có ORDER BY hoặc sort key bị trùng | Thêm ORDER BY với khóa phá hòa duy nhất |
| NULL đứng đầu khi DESC | Đây là mặc định Oracle | Viết DESC NULLS LAST nếu muốn NULL cuối |
| NULL đứng cuối khi ASC | Đây là mặc định Oracle | Viết rõ NULLS LAST để thể hiện ý định |
| Top 10 thay đổi giữa các lần chạy | Hàng ở biên có cùng sort key | Thêm khóa duy nhất hoặc dùng WITH TIES nếu muốn lấy đồng hạng |
| Phân trang lặp hoặc mất hàng | Thứ tự không xác định hoặc dữ liệu thay đổi giữa các request | Dùng total order, keyset pagination và snapshot phù hợp |
| Số 100 đứng trước số 2 | Cột số được lưu dạng VARCHAR2 | Lưu NUMBER hoặc chuyển kiểu tường minh |
| Tên tiếng Việt sắp xếp khác giữa môi trường | NLS_SORT/NLS_COMP hoặc collation khác | Chốt quy tắc linguistic sort, dùng NLSSORT khi cần |
| ORDER BY trong view không đảm bảo thứ tự caller | Query block ngoài không có ORDER BY | Đặt ORDER BY ở SELECT cuối |
| ROW_NUMBER có số thứ tự khác giữa các hàng bằng nhau | Window ORDER BY thiếu tie-breaker | Thêm khóa phân biệt vào ORDER BY trong OVER |
| Chỉ có ORDER BY trong OVER nhưng output không theo thứ tự | Analytic order khác final result order | Thêm ORDER BY ngoài cùng |
| ORDER BY tốn TEMP | Sort lớn không vừa workarea | Giảm tập dữ liệu, dùng top-N/index phù hợp và xem plan |
| ORDER BY biểu thức không dùng index mong đợi | Sort key là hàm/biểu thức khác cột index | Xem plan, cân nhắc function-based index khi workload chứng minh cần |

## 15. Nguyên tắc thiết kế ORDER BY cho API và báo cáo

Một API trả danh sách nên công bố thứ tự rõ ràng trong hợp đồng, ví dụ:

- Mới nhất trước: NGAY_TAO DESC NULLS LAST, ID DESC.
- Điểm cao nhất trước: DIEM DESC NULLS LAST, ID ASC.
- Tên tăng dần: NLSSORT(TEN, quy_tac_collation), ID ASC.
- Chưa xử lý trước: CASE trạng thái, NGAY_TAO ASC, ID ASC.

Không chỉ ghi “sắp xếp theo ngày” nếu ngày có thể NULL hoặc nhiều hàng cùng ngày. Hãy định nghĩa cả hướng, vị trí NULL và khóa phụ.

Với ứng dụng Java/JDBC:
- Bind giá trị lọc và phân trang bằng PreparedStatement.
- Không ghép tên cột hoặc hướng ASC/DESC trực tiếp từ input không kiểm soát. Sort field nên ánh xạ qua whitelist.
- Nếu client yêu cầu sort động, xây danh sách sort expression đã được cho phép; bind variable không thể thay thế tên cột hay từ khóa SQL.
- Giữ một khóa duy nhất ở cuối ORDER BY để trang ổn định.
- Kiểm tra null semantics giữa Oracle và logic hiển thị của frontend.
- Khi cần nhiều trang nhất quán qua thời gian, xác định chiến lược snapshot hoặc mốc dữ liệu phù hợp.

Ví dụ whitelist ở tầng Java có thể ánh xạ tên trường API như CREATED_AT, SCORE hoặc NAME vào biểu thức SQL cố định; không nối trực tiếp chuỗi người dùng gửi vào ORDER BY. Phần ASC/DESC cũng phải được kiểm tra chỉ nhận hai lựa chọn hợp lệ.

## 16. Checklist tư duy khi viết ORDER BY

Trước khi hoàn tất câu SELECT, tự trả lời:

1. Tập kết quả có bắt buộc thứ tự không? Nếu có, ORDER BY nằm ở query block cuối chưa?
2. Khóa sắp xếp có đúng kiểu dữ liệu và ý nghĩa nghiệp vụ không?
3. ASC/DESC đã rõ cho từng khóa chưa?
4. Mỗi khóa có quy tắc NULLS FIRST/LAST phù hợp chưa?
5. Có nhiều hàng bằng nhau ở mọi khóa không? Nếu có, đã thêm tie-breaker duy nhất chưa?
6. Với top-N hoặc pagination, kết quả có ổn định trên cùng tập dữ liệu không?
7. Nếu dùng DISTINCT, GROUP BY hoặc set operator, biểu thức ORDER BY có hợp lệ trong ngữ cảnh đó không?
8. Nếu dùng analytic function, đã phân biệt window ORDER BY và final ORDER BY chưa?
9. Thứ tự chuỗi có cần collation/ngôn ngữ tường minh không?
10. Execution plan có SORT ORDER BY lớn, TEMP spill hoặc index access phù hợp không?
11. Ứng dụng có ghép động tên cột/hướng sort từ input không kiểm soát không?
12. Dữ liệu thay đổi giữa các trang có cần snapshot nhất quán không?

## 17. Bài tập tự luyện

1. Viết truy vấn lấy nhân viên theo lương giảm dần, NULL cuối, rồi mã nhân viên tăng dần.
2. Giải thích vì sao ORDER BY NGAY_NGHI_VIEC DESC trong Oracle có thể đưa nhân viên chưa có ngày nghỉ lên đầu.
3. Tạo truy vấn đưa những nhân viên chưa nghỉ việc lên trước, rồi người đã nghỉ theo ngày nghỉ mới nhất.
4. Một bảng có 100 hàng cùng NGAY_TAO. Vì sao ORDER BY NGAY_TAO DESC chưa tạo thứ tự xác định?
5. Với kết quả JOIN đơn hàng và chi tiết đơn hàng, chọn những khóa nào để phân biệt từng dòng?
6. So sánh ORDER BY NULLS LAST với ORDER BY NVL(cot, gia_tri_thay_the). Khi nào hai cách cho kết quả khác nhau?
7. Viết truy vấn lấy top 10 sản phẩm giá cao nhất, giữ toàn bộ sản phẩm đồng giá với vị trí thứ 10 bằng WITH TIES.
8. Viết truy vấn ROW_NUMBER để lấy ba nhân viên điểm cao nhất mỗi phòng, đảm bảo mã nhân viên phá hòa.
9. Vì sao ORDER BY trong OVER không tự sắp xếp kết quả cuối cùng?
10. Một view có ORDER BY nhưng câu SELECT ngoài không có ORDER BY. Có thể cam kết thứ tự trả về cho API không?
11. Sắp xếp chuỗi số '2', '10', '100' theo thứ tự số. Cần thay đổi kiểu dữ liệu hoặc biểu thức thế nào?
12. Giải thích vai trò của NLS_SORT và NLSSORT khi sắp xếp tên có dấu.
13. Viết truy vấn phân trang trang thứ ba, mỗi trang 20 hàng, theo NGAY_DANG_KY mới nhất và MA_KHACH_HANG giảm dần.
14. Vì sao thêm khóa phụ duy nhất giúp top-N và OFFSET/FETCH ổn định hơn?
15. Khi nào keyset pagination có lợi hơn OFFSET lớn? Điều kiện nào phải bổ sung nếu sort key cho phép NULL?
16. Một sort lớn tạo TEMP usage cao. Hãy nêu những thông tin trong execution plan và workload cần xem trước khi tạo index.
17. Tại sao không nên ghép trực tiếp ORDER BY column_name từ tham số request vào câu SQL?
18. Phân biệt thứ tự xác định trên cùng một snapshot với tính nhất quán giữa nhiều request khi dữ liệu đang được cập nhật.

**ORDER BY xác định cách sắp xếp, NULLS FIRST/LAST xác định vị trí giá trị chưa biết, còn khóa phụ duy nhất tạo thứ tự xác định giữa những hàng đồng khóa.** Ba yếu tố này đặc biệt quan trọng với top-N, phân trang, analytic functions và API. Kết hợp kiểu dữ liệu đúng, quy tắc NLS phù hợp và kiểm tra execution plan giúp kết quả vừa đúng nghiệp vụ vừa có thể dự đoán và vận hành ổn định.

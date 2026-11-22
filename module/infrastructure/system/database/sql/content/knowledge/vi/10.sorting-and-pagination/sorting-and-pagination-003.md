# Sắp xếp bằng CASE theo thứ tự nghiệp vụ trong SQL

Trong cơ sở dữ liệu, câu lệnh **ORDER BY** thường sắp kết quả theo tên, ngày tạo hoặc giá trị số. Nhưng thứ tự cần hiển thị trong nghiệp vụ thường không giống thứ tự chữ cái. Chẳng hạn, danh sách công việc của một nhóm hỗ trợ cần **BLOCKED** trước **IN_PROGRESS**, tiếp theo **NEW**, sau đó mới tới **DONE** và **CANCELLED**.

Nếu chỉ dùng ORDER BY trên cột trạng thái, hệ quản trị sắp xếp các chuỗi theo quy tắc so sánh ký tự (collation), không hiểu đâu là trạng thái cấp bách. Biểu thức **CASE trong ORDER BY** giúp biến từng trạng thái hoặc điều kiện thành **khóa thứ hạng** do nghiệp vụ quy định.

Bài học thuộc nhóm **Sắp xếp và phân trang** của Database SQL. Bạn sẽ dùng CASE để xây dựng thứ tự tùy chỉnh, ghép nhiều tiêu chí, xử lý giá trị NULL, tạo thứ tự ổn định và phân trang. Ví dụ chạy trên **PostgreSQL**, đồng thời chỉ rõ các điểm cần lưu ý khi sử dụng DBMS khác.

## 1. Vì sao cần thứ tự tùy chỉnh?

Giả sử một hệ thống quản lý công việc có các trạng thái:

| Trạng thái | Ý nghĩa | Thứ tự muốn hiển thị |
|---|---|---:|
| BLOCKED | Bị chặn, cần tháo gỡ | 1 |
| IN_PROGRESS | Đang xử lý | 2 |
| NEW | Chưa bắt đầu | 3 |
| DONE | Hoàn thành | 4 |
| CANCELLED | Đã hủy | 5 |
| Trạng thái chưa được ánh xạ | Xử lý theo mặc định | 99 |

Lệnh thông thường:

~~~sql
SELECT id, trang_thai
FROM cong_viec
ORDER BY trang_thai ASC;
~~~

chỉ sắp theo chữ. Ví dụ, CANCELLED có thể đứng trước DONE, IN_PROGRESS và NEW. Đó không phải thứ tự xử lý mà nhóm hỗ trợ cần.

Một biểu thức CASE có thể cho kết quả số như sau:

~~~sql
CASE trang_thai
    WHEN 'BLOCKED' THEN 1
    WHEN 'IN_PROGRESS' THEN 2
    WHEN 'NEW' THEN 3
    WHEN 'DONE' THEN 4
    WHEN 'CANCELLED' THEN 5
    ELSE 99
END
~~~

Khi đặt biểu thức này trong ORDER BY với hướng ASC, hạng **1** sẽ lên trước hạng **2**, rồi 3, 4, 5 và 99. Các con số là quy ước ưu tiên, không phải giá trị đang lưu trong cột trạng thái.

## 2. Hai dạng CASE cần biết

### 2.1. Simple CASE: ánh xạ một giá trị

~~~sql
CASE trang_thai
    WHEN 'BLOCKED' THEN 1
    WHEN 'IN_PROGRESS' THEN 2
    WHEN 'NEW' THEN 3
    WHEN 'DONE' THEN 4
    WHEN 'CANCELLED' THEN 5
    ELSE 99
END
~~~

Simple CASE dùng khi cần so sánh **một biểu thức** với các giá trị cụ thể. Đây là cách gọn gàng để ánh xạ mã trạng thái hoặc mức độ ưu tiên thành thứ hạng.

Cấu trúc:

~~~sql
CASE bieu_thuc
    WHEN gia_tri_1 THEN ket_qua_1
    WHEN gia_tri_2 THEN ket_qua_2
    ELSE ket_qua_mac_dinh
END
~~~

### 2.2. Searched CASE: dùng điều kiện

~~~sql
CASE
    WHEN trang_thai = 'BLOCKED' THEN 1
    WHEN trang_thai = 'IN_PROGRESS' THEN 2
    WHEN trang_thai = 'NEW' THEN 3
    WHEN trang_thai = 'DONE' THEN 4
    WHEN trang_thai = 'CANCELLED' THEN 5
    ELSE 99
END
~~~

Searched CASE cho phép các điều kiện phức tạp như AND, OR, so sánh ngày, số tiền hoặc kiểm tra NULL. Đây là lựa chọn phù hợp khi độ ưu tiên phụ thuộc **nhiều cột cùng lúc**.

### 2.3. Nhánh WHEN đầu tiên khớp sẽ quyết định kết quả

~~~sql
CASE
    WHEN muc_do IN ('CRITICAL', 'HIGH') THEN 2
    WHEN muc_do = 'CRITICAL' THEN 1
    ELSE 3
END
~~~

Với giá trị CRITICAL, nhánh đầu đã đúng và CASE trả **2**, không phải 1. Muốn CRITICAL đứng trước HIGH, hãy đặt nhánh đặc biệt lên trước:

~~~sql
CASE
    WHEN muc_do = 'CRITICAL' THEN 1
    WHEN muc_do = 'HIGH' THEN 2
    ELSE 3
END
~~~

**Thứ tự các nhánh có ý nghĩa khi điều kiện bị chồng lấn.** Với simple CASE ánh xạ các chuỗi khác nhau, các nhánh thường không chồng lấn; với searched CASE, cần đặc biệt chú ý.

### 2.4. CASE trả về giá trị có kiểu dữ liệu

Với mục đích xếp hạng, nên để các nhánh THEN và ELSE cùng trả về **số nguyên**. Trộn số với một chuỗi không thể chuyển thành số có thể gây lỗi kiểu dữ liệu trong PostgreSQL:

~~~sql
-- Không nên viết:
CASE
    WHEN trang_thai = 'BLOCKED' THEN 1
    ELSE 'cuoi_danh_sach'
END
~~~

Thay bằng:

~~~sql
CASE
    WHEN trang_thai = 'BLOCKED' THEN 1
    ELSE 99
END
~~~

CASE là một **biểu thức SQL**, không phải lệnh thay đổi dữ liệu. Việc xếp hạng bằng CASE không tự ghi số 1 hoặc 99 vào bảng.

## 3. Chuẩn bị dữ liệu để thực hành

Dùng PostgreSQL trong **cơ sở dữ liệu thử nghiệm**. Tạo một bảng tạm để không ảnh hưởng các bảng nghiệp vụ khác. Bảng tạm tồn tại trong phiên kết nối, vì vậy hãy thực hiện các ví dụ trong cùng một phiên.

~~~sql
CREATE TEMP TABLE case_cong_viec (
    id INTEGER PRIMARY KEY,
    tieu_de VARCHAR(100) NOT NULL,
    trang_thai VARCHAR(20) NOT NULL
        CHECK (trang_thai IN (
            'BLOCKED', 'IN_PROGRESS', 'NEW',
            'DONE', 'CANCELLED', 'ON_HOLD'
        )),
    muc_do VARCHAR(20)
        CHECK (muc_do IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    han_xu_ly DATE,
    ngay_tao TIMESTAMP NOT NULL
);

INSERT INTO case_cong_viec
    (id, tieu_de, trang_thai, muc_do, han_xu_ly, ngay_tao)
VALUES
    (101, 'Lỗi đăng nhập', 'BLOCKED', 'CRITICAL',
     DATE '2026-11-15', TIMESTAMP '2026-11-10 09:00:00'),
    (102, 'Gửi email nhắc', 'NEW', 'LOW',
     NULL, TIMESTAMP '2026-11-10 10:00:00'),
    (103, 'Đồng bộ kho', 'IN_PROGRESS', 'HIGH',
     DATE '2026-11-16', TIMESTAMP '2026-11-11 08:30:00'),
    (104, 'Sửa màn hình thanh toán', 'IN_PROGRESS', 'CRITICAL',
     DATE '2026-11-14', TIMESTAMP '2026-11-12 14:00:00'),
    (105, 'Viết tài liệu', 'DONE', 'MEDIUM',
     NULL, TIMESTAMP '2026-11-09 12:00:00'),
    (106, 'Kiểm thử API', 'NEW', 'HIGH',
     DATE '2026-11-18', TIMESTAMP '2026-11-12 09:00:00'),
    (107, 'Hủy tác vụ cũ', 'CANCELLED', 'LOW',
     NULL, TIMESTAMP '2026-11-07 07:00:00'),
    (108, 'Rà soát chính sách', 'BLOCKED', NULL,
     DATE '2026-11-17', TIMESTAMP '2026-11-13 15:00:00'),
    (109, 'Đánh giá hiệu suất', 'ON_HOLD', 'MEDIUM',
     DATE '2026-11-20', TIMESTAMP '2026-11-11 10:00:00'),
    (110, 'Phân tích log', 'NEW', 'HIGH',
     DATE '2026-11-13', TIMESTAMP '2026-11-13 16:00:00');
~~~

Bảng có **10 công việc**. Hai cột muc_do và han_xu_ly có thể NULL. Trạng thái ON_HOLD hợp lệ nhưng cố tình chưa có trong bảng ánh xạ thứ hạng nghiệp vụ để minh họa vai trò của ELSE.

Quan sát dữ liệu:

~~~sql
SELECT id, tieu_de, trang_thai, muc_do, han_xu_ly
FROM case_cong_viec
ORDER BY id;
~~~

## 4. Sắp xếp trạng thái bằng CASE trong ORDER BY

~~~sql
SELECT id, tieu_de, trang_thai
FROM case_cong_viec
ORDER BY
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        WHEN 'DONE' THEN 4
        WHEN 'CANCELLED' THEN 5
        ELSE 99
    END ASC,
    id ASC;
~~~

Kết quả:

| Vị trí | id | trang_thai | Hạng CASE |
|---:|---:|---|---:|
| 1 | 101 | BLOCKED | 1 |
| 2 | 108 | BLOCKED | 1 |
| 3 | 103 | IN_PROGRESS | 2 |
| 4 | 104 | IN_PROGRESS | 2 |
| 5 | 102 | NEW | 3 |
| 6 | 106 | NEW | 3 |
| 7 | 110 | NEW | 3 |
| 8 | 105 | DONE | 4 |
| 9 | 107 | CANCELLED | 5 |
| 10 | 109 | ON_HOLD | 99 |

Hai dòng BLOCKED cùng hạng 1 được sắp tiếp bằng id ASC; vì thế 101 xuất hiện trước 108. Trạng thái ON_HOLD rơi vào ELSE và xuống cuối.

### 4.1. Hiển thị hạng để dễ giải thích

~~~sql
SELECT
    id,
    trang_thai,
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        WHEN 'DONE' THEN 4
        WHEN 'CANCELLED' THEN 5
        ELSE 99
    END AS hang_trang_thai
FROM case_cong_viec
ORDER BY hang_trang_thai, id;
~~~

Trong PostgreSQL, bí danh hang_trang_thai ở SELECT có thể được dùng tại ORDER BY. Cột này giúp kiểm tra bằng mắt thứ tự đang được tính như thế nào.

### 4.2. ORDER BY không giống WHERE

~~~sql
-- A: tất cả công việc, nhưng BLOCKED ở đầu.
SELECT id, trang_thai
FROM case_cong_viec
ORDER BY
    CASE WHEN trang_thai = 'BLOCKED' THEN 0 ELSE 1 END,
    id;
~~~

~~~sql
-- B: chỉ những công việc BLOCKED.
SELECT id, trang_thai
FROM case_cong_viec
WHERE trang_thai = 'BLOCKED'
ORDER BY id;
~~~

A trả **10 dòng**, B trả **2 dòng**. ORDER BY chỉ thay đổi vị trí trong tập kết quả; WHERE mới loại bỏ những hàng không phù hợp.

## 5. Vai trò của ELSE và NULL

Nếu CASE không có ELSE, khi không nhánh nào khớp nó trả về **NULL**:

~~~sql
CASE trang_thai
    WHEN 'BLOCKED' THEN 1
    WHEN 'IN_PROGRESS' THEN 2
    WHEN 'NEW' THEN 3
    WHEN 'DONE' THEN 4
    WHEN 'CANCELLED' THEN 5
END
~~~

Với ON_HOLD, khóa sắp xếp trở thành NULL. Vị trí NULL khi sắp xếp phụ thuộc DBMS và hướng sort: trong PostgreSQL, ASC mặc định đặt NULL cuối, DESC mặc định đặt NULL đầu. Những hệ quản trị khác có thể có quy tắc khác.

**ELSE 99** đặt chính sách rõ ràng: các trạng thái chưa xếp hạng nhận giá trị lớn và đứng sau khi sắp ASC. Khi nghiệp vụ bổ sung trạng thái mới, nên xem xét cập nhật ánh xạ; không nên để ELSE vô tình che giấu một trường hợp quan trọng.

Với cột nullable, simple CASE có nhánh WHEN NULL không dùng để kiểm tra giá trị thiếu như một phép so sánh thông thường. Hãy dùng searched CASE với điều kiện IS NULL:

~~~sql
CASE
    WHEN muc_do IS NULL THEN 99
    WHEN muc_do = 'CRITICAL' THEN 1
    WHEN muc_do = 'HIGH' THEN 2
    WHEN muc_do = 'MEDIUM' THEN 3
    WHEN muc_do = 'LOW' THEN 4
    ELSE 99
END
~~~

Trong SQL, so sánh bằng với NULL không trả TRUE. Nếu dùng WHEN muc_do = NULL, điều kiện sẽ không chọn được hàng có muc_do NULL.

## 6. Sắp xếp theo nhiều tiêu chí nghiệp vụ

Một danh sách thực tế có thể muốn:

1. **Trạng thái**: BLOCKED, IN_PROGRESS, NEW, DONE, CANCELLED, còn lại.
2. **Mức độ**: CRITICAL, HIGH, MEDIUM, LOW, chưa phân loại.
3. **Hạn xử lý**: ngày sớm trước, thiếu hạn sau.
4. **ID**: tiêu chí phá hòa cuối.

Các biểu thức trong ORDER BY được so sánh **theo thứ tự từ trái sang phải**. Nếu hai dòng có cùng tiêu chí thứ nhất, SQL xét tiêu chí thứ hai rồi tiếp tục.

~~~sql
SELECT id, tieu_de, trang_thai, muc_do, han_xu_ly
FROM case_cong_viec
ORDER BY
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        WHEN 'DONE' THEN 4
        WHEN 'CANCELLED' THEN 5
        ELSE 99
    END ASC,
    CASE muc_do
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        WHEN 'LOW' THEN 4
        ELSE 99
    END ASC,
    CASE WHEN han_xu_ly IS NULL THEN 1 ELSE 0 END ASC,
    han_xu_ly ASC,
    id ASC;
~~~

Kết quả:

| Vị trí | id | trang_thai | muc_do | han_xu_ly |
|---:|---:|---|---|---|
| 1 | 101 | BLOCKED | CRITICAL | 2026-11-15 |
| 2 | 108 | BLOCKED | NULL | 2026-11-17 |
| 3 | 104 | IN_PROGRESS | CRITICAL | 2026-11-14 |
| 4 | 103 | IN_PROGRESS | HIGH | 2026-11-16 |
| 5 | 110 | NEW | HIGH | 2026-11-13 |
| 6 | 106 | NEW | HIGH | 2026-11-18 |
| 7 | 102 | NEW | LOW | NULL |
| 8 | 105 | DONE | MEDIUM | NULL |
| 9 | 107 | CANCELLED | LOW | NULL |
| 10 | 109 | ON_HOLD | MEDIUM | 2026-11-20 |

Công việc 104 và 103 cùng IN_PROGRESS nhưng CRITICAL đứng trước HIGH. Công việc 110 và 106 đều NEW/HIGH nên ngày đến hạn 13/11 đứng trước 18/11.

**Thứ tự biểu thức quyết định mức ưu tiên.** Nếu đưa hạn xử lý lên trước trạng thái, một công việc NEW có hạn sớm có thể đứng trước BLOCKED dù quy tắc ban đầu yêu cầu ngược lại.

### 6.1. Dùng ASC và DESC ở các khóa khác nhau

~~~sql
SELECT id, trang_thai, ngay_tao
FROM case_cong_viec
ORDER BY
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        ELSE 99
    END ASC,
    ngay_tao DESC,
    id DESC;
~~~

Trạng thái có hạng số nhỏ vẫn xuất hiện trước; trong cùng trạng thái, công việc **mới tạo hơn** đứng trước. Một biểu thức ORDER BY không bắt buộc dùng cùng chiều với những biểu thức còn lại.

## 7. Dùng CASE để xếp NULL ở vị trí mong muốn

Giả sử muốn công việc **có hạn** trước công việc **chưa có hạn**:

~~~sql
SELECT id, han_xu_ly
FROM case_cong_viec
ORDER BY
    CASE
        WHEN han_xu_ly IS NULL THEN 1
        ELSE 0
    END,
    han_xu_ly ASC,
    id ASC;
~~~

Biểu thức đầu phân thành nhóm có hạn (hạng 0) và chưa có hạn (hạng 1); biểu thức thứ hai xếp các ngày thực trong nhóm có hạn.

PostgreSQL hỗ trợ cú pháp tương đương cho mục đích này:

~~~sql
SELECT id, han_xu_ly
FROM case_cong_viec
ORDER BY han_xu_ly ASC NULLS LAST, id;
~~~

Nhưng NULLS FIRST/LAST không được mọi SQL dialect hỗ trợ giống nhau. CASE kiểm tra IS NULL giúp diễn đạt hành vi nhất quán hơn khi chuyển hệ quản trị.

Một số truy vấn dùng COALESCE với ngày cực lớn như DATE '9999-12-31' để thay NULL. Cách đó phụ thuộc miền ngày hợp lệ, có thể trùng ngày thật và che đi khác biệt giữa dữ liệu thiếu với giá trị thời gian. Khi chỉ cần phân nhóm NULL, CASE rõ nghĩa hơn.

Nếu muốn **chưa có hạn đứng đầu**, đảo kết quả CASE:

~~~sql
ORDER BY
    CASE WHEN han_xu_ly IS NULL THEN 0 ELSE 1 END,
    han_xu_ly ASC,
    id
~~~

## 8. Searched CASE: trạng thái và hạn xử lý

Yêu cầu: **công việc đang mở, quá hạn phải xuất hiện trước**. Bài dùng ngày tham chiếu cố định 14/11/2026 để kết quả thực hành không thay đổi theo ngày chạy. Ứng dụng thực tế có thể truyền một ngày tham số hoặc dùng CURRENT_DATE nếu phù hợp.

~~~sql
SELECT id, tieu_de, trang_thai, han_xu_ly
FROM case_cong_viec
ORDER BY
    CASE
        WHEN trang_thai NOT IN ('DONE', 'CANCELLED')
         AND han_xu_ly < DATE '2026-11-14'
        THEN 0
        ELSE 1
    END,
    han_xu_ly ASC NULLS LAST,
    id;
~~~

Công việc **110 — Phân tích log** có hạn 13/11 và còn NEW, nên thuộc nhóm hạng 0. Công việc đến hạn đúng 14/11 không bị xem là **quá hạn** do điều kiện dùng dấu nhỏ hơn.

Nếu bỏ kiểm tra trạng thái, những công việc đã kết thúc nhưng có hạn cũ cũng có thể bị đẩy lên đầu, sai với mục tiêu xử lý công việc đang mở.

### 8.1. Điều kiện cụ thể phải đứng trước điều kiện bao quát

Giả sử muốn thứ tự:

1. Quá hạn **và CRITICAL**.
2. Quá hạn ở mức độ khác.
3. Chưa quá hạn nhưng CRITICAL.
4. Các trường hợp còn lại.

~~~sql
SELECT id, trang_thai, muc_do, han_xu_ly
FROM case_cong_viec
ORDER BY
    CASE
        WHEN han_xu_ly < DATE '2026-11-14'
         AND muc_do = 'CRITICAL'
         AND trang_thai NOT IN ('DONE', 'CANCELLED')
        THEN 1

        WHEN han_xu_ly < DATE '2026-11-14'
         AND trang_thai NOT IN ('DONE', 'CANCELLED')
        THEN 2

        WHEN muc_do = 'CRITICAL'
         AND trang_thai NOT IN ('DONE', 'CANCELLED')
        THEN 3

        ELSE 4
    END,
    id;
~~~

Nhánh quá hạn và CRITICAL phải đứng trước nhánh quá hạn chung. Nếu đảo ngược, công việc đủ cả hai điều kiện sẽ khớp nhánh tổng quát trước và nhận hạng 2.

### 8.2. NULL khi đánh giá điều kiện ngày

Với hạn NULL, phép so sánh han_xu_ly nhỏ hơn ngày tham chiếu cho kết quả UNKNOWN. Nhánh WHEN đó không được chọn và CASE chuyển sang các nhánh tiếp theo hoặc ELSE.

Nếu muốn công việc **chưa có hạn** được ưu tiên rà soát, thêm điều kiện rõ ràng:

~~~sql
CASE
    WHEN han_xu_ly IS NULL
     AND trang_thai NOT IN ('DONE', 'CANCELLED')
    THEN 0
    WHEN han_xu_ly < DATE '2026-11-14'
     AND trang_thai NOT IN ('DONE', 'CANCELLED')
    THEN 1
    ELSE 2
END
~~~

Không nên dựa vào việc NULL vô tình rơi vào ELSE rồi mặc định hành vi đó đúng nghiệp vụ.

## 9. Một số kiểu ưu tiên đặc biệt

### 9.1. Đưa một công việc được ghim lên đầu

~~~sql
SELECT id, tieu_de, trang_thai
FROM case_cong_viec
ORDER BY
    CASE WHEN id = 104 THEN 0 ELSE 1 END,
    ngay_tao DESC,
    id;
~~~

ID 104 nhận hạng 0 và đứng đầu, còn các ID khác được xếp theo ngày tạo mới nhất. Đây là kiểu danh sách **pinned item**. Trong hệ thống thực tế, danh sách công việc ghim có thể được truyền từ ứng dụng hoặc lưu thành dữ liệu, thay vì hard-code mã trong mọi câu SQL.

### 9.2. Mỗi nhóm một chiều sắp xếp thời gian

Giả sử trong nhóm BLOCKED, công việc cũ phải lên trước để giải quyết tồn đọng; còn ngoài nhóm BLOCKED, công việc mới lên trước.

~~~sql
SELECT id, trang_thai, ngay_tao
FROM case_cong_viec
ORDER BY
    CASE WHEN trang_thai = 'BLOCKED' THEN 0 ELSE 1 END,
    CASE
        WHEN trang_thai = 'BLOCKED' THEN ngay_tao
        ELSE NULL
    END ASC,
    CASE
        WHEN trang_thai <> 'BLOCKED' THEN ngay_tao
        ELSE NULL
    END DESC,
    id;
~~~

Khóa thứ nhất chia nhóm. Khóa thời gian thứ hai chỉ có giá trị cho BLOCKED với chiều ASC; khóa thứ ba chỉ có giá trị cho nhóm còn lại với chiều DESC. Tách khóa như vậy diễn đạt hai quy tắc trái chiều trong cùng ORDER BY.

### 9.3. Nhãn hiển thị khác thứ hạng

~~~sql
SELECT
    id,
    CASE trang_thai
        WHEN 'BLOCKED' THEN 'Cần tháo gỡ'
        WHEN 'IN_PROGRESS' THEN 'Đang xử lý'
        WHEN 'NEW' THEN 'Chưa bắt đầu'
        WHEN 'DONE' THEN 'Hoàn thành'
        WHEN 'CANCELLED' THEN 'Đã hủy'
        ELSE 'Khác'
    END AS nhan_hien_thi
FROM case_cong_viec
ORDER BY
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        WHEN 'DONE' THEN 4
        WHEN 'CANCELLED' THEN 5
        ELSE 99
    END,
    id;
~~~

Nhãn tiếng Việt được dùng để trình bày, còn hạng số được dùng để sắp xếp. Nếu ORDER BY trên nhãn tiếng Việt, thứ tự phụ thuộc collation và không chắc trùng thứ tự ưu tiên.

## 10. Tạo thứ tự ổn định để phân trang

Nếu chỉ ORDER BY theo CASE trạng thái, nhiều hàng có cùng hạng. SQL **không bảo đảm thứ tự giữa các hàng có cùng toàn bộ khóa ORDER BY**. Một lần chạy có thể cho NEW theo thứ tự 102, 106, 110; lần khác có thể thay đổi khi kế hoạch thực thi hoặc dữ liệu thay đổi.

Với màn hình phân trang, nên thêm tiêu chí cuối **duy nhất**, chẳng hạn khóa chính id:

~~~sql
ORDER BY
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        ELSE 99
    END,
    id
~~~

Điều này xác định thứ tự cho **tập dữ liệu tại thời điểm truy vấn**. Nó không tự tạo ảnh chụp dữ liệu bất biến qua nhiều lần tải trang khi người khác sửa dữ liệu.

### 10.1. LIMIT và OFFSET trong PostgreSQL

Ví dụ trang đầu có kích thước 4, theo thứ tự trạng thái → mức độ → hạn → ID:

~~~sql
SELECT id, tieu_de, trang_thai, muc_do, han_xu_ly
FROM case_cong_viec
ORDER BY
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        WHEN 'DONE' THEN 4
        WHEN 'CANCELLED' THEN 5
        ELSE 99
    END,
    CASE muc_do
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        WHEN 'LOW' THEN 4
        ELSE 99
    END,
    CASE WHEN han_xu_ly IS NULL THEN 1 ELSE 0 END,
    han_xu_ly ASC,
    id ASC
LIMIT 4 OFFSET 0;
~~~

**Trang 1:** 101, 108, 104, 103.

Đổi dòng cuối thành:

~~~sql
LIMIT 4 OFFSET 4;
~~~

**Trang 2:** 110, 106, 102, 105.

Nếu đánh số trang từ 1, OFFSET thông thường là (số trang - 1) × kích thước trang. Giá trị LIMIT/OFFSET do ứng dụng truyền nên được kiểm tra để không quá lớn hoặc không hợp lệ.

### 10.2. Vì sao OFFSET có thể trùng hoặc bỏ sót dòng?

Giả sử người dùng xem trang 1, sau đó một công việc NEW được đổi trạng thái thành BLOCKED trước khi xem trang 2. Nó có thể di chuyển lên phía đầu danh sách. Khi chạy OFFSET 4 cho trang 2, máy chủ bỏ qua bốn dòng đầu **của tập dữ liệu mới**, không phải chính xác bốn dòng đã xem ở lần truy vấn trước.

ID duy nhất giải quyết đồng hạng, nhưng không giải quyết mọi thay đổi đồng thời. Nếu cần trải nghiệm ổn định hơn, cân nhắc **keyset pagination** hoặc snapshot tùy yêu cầu.

## 11. Keyset pagination với khóa CASE

Keyset pagination (cursor pagination) lấy những hàng nằm **sau khóa của hàng cuối trang trước**. Khi sắp theo trạng thái và ID, cursor phải chứa cả hai.

### 11.1. Tính khóa hạng bằng CTE

~~~sql
WITH ranked AS (
    SELECT
        id,
        tieu_de,
        trang_thai,
        CASE trang_thai
            WHEN 'BLOCKED' THEN 1
            WHEN 'IN_PROGRESS' THEN 2
            WHEN 'NEW' THEN 3
            WHEN 'DONE' THEN 4
            WHEN 'CANCELLED' THEN 5
            ELSE 99
        END AS hang_trang_thai
    FROM case_cong_viec
)
SELECT id, trang_thai, hang_trang_thai
FROM ranked
ORDER BY hang_trang_thai, id
LIMIT 3;
~~~

Trang đầu:

| id | hang_trang_thai |
|---:|---:|
| 101 | 1 |
| 108 | 1 |
| 103 | 2 |

Cursor cuối trang là **hạng 2, ID 103**, chứ không phải chỉ ID 103.

### 11.2. Lấy các hàng sau cursor

PostgreSQL cho phép so sánh bộ giá trị:

~~~sql
WITH ranked AS (
    SELECT
        id,
        trang_thai,
        CASE trang_thai
            WHEN 'BLOCKED' THEN 1
            WHEN 'IN_PROGRESS' THEN 2
            WHEN 'NEW' THEN 3
            WHEN 'DONE' THEN 4
            WHEN 'CANCELLED' THEN 5
            ELSE 99
        END AS hang_trang_thai
    FROM case_cong_viec
)
SELECT id, trang_thai, hang_trang_thai
FROM ranked
WHERE (hang_trang_thai, id) > (2, 103)
ORDER BY hang_trang_thai, id
LIMIT 3;
~~~

Kết quả: **104, 102, 106**. Với thứ tự hai khóa ASC và không NULL, có thể diễn đạt tương đương:

~~~sql
WHERE hang_trang_thai > 2
   OR (hang_trang_thai = 2 AND id > 103)
~~~

Nếu có thêm mức độ, hạn, hướng DESC hoặc NULL, điều kiện cursor phải phản ánh **đủ các khóa và chiều sắp xếp**. Không thể chỉ sao chép điều kiện so sánh cặp ở đây cho mọi thứ tự phức tạp.

Keyset giúp tránh một số vấn đề của OFFSET nhưng **không tạo snapshot bất biến**. Nếu hạng hoặc dữ liệu thay đổi giữa các lần xem, tập kết quả vẫn có thể thay đổi.

## 12. Tránh lặp biểu thức CASE bằng bảng dẫn xuất hoặc CTE

Nếu muốn vừa lọc theo hạng vừa sắp xếp theo hạng, đôi khi cần dùng nhiều lần CASE. Trong PostgreSQL, bí danh ở SELECT có thể dùng ở ORDER BY nhưng **không dùng được trực tiếp trong WHERE cùng cấp**:

~~~sql
-- Không hợp lệ trong PostgreSQL vì WHERE không biết alias hang:
SELECT
    id,
    CASE WHEN trang_thai = 'BLOCKED' THEN 1 ELSE 9 END AS hang
FROM case_cong_viec
WHERE hang = 1;
~~~

Dùng bảng dẫn xuất:

~~~sql
SELECT dt.id, dt.trang_thai, dt.hang
FROM (
    SELECT
        id,
        trang_thai,
        CASE
            WHEN trang_thai = 'BLOCKED' THEN 1
            ELSE 9
        END AS hang
    FROM case_cong_viec
) AS dt
WHERE dt.hang = 1
ORDER BY dt.id;
~~~

Hoặc dùng WITH/CTE để tạo hạng một lần rồi lọc/sắp xếp ở truy vấn ngoài. Điều này giúp truy vấn dài dễ đọc và thuận tiện khi xây dựng cursor.

### 12.1. Khi thứ tự là dữ liệu nghiệp vụ thay đổi thường xuyên

Nếu bảng ánh xạ trạng thái cần thay đổi thường xuyên hoặc nhiều truy vấn sử dụng cùng quy tắc, có thể lưu hạng trong bảng cấu hình:

~~~sql
CREATE TEMP TABLE case_thu_tu_trang_thai (
    trang_thai VARCHAR(20) PRIMARY KEY,
    thu_tu INTEGER NOT NULL UNIQUE
);

INSERT INTO case_thu_tu_trang_thai (trang_thai, thu_tu)
VALUES
    ('BLOCKED', 1),
    ('IN_PROGRESS', 2),
    ('NEW', 3),
    ('DONE', 4),
    ('CANCELLED', 5);
~~~

Sau đó JOIN:

~~~sql
SELECT
    cv.id,
    cv.trang_thai,
    COALESCE(tt.thu_tu, 99) AS hang_trang_thai
FROM case_cong_viec AS cv
LEFT JOIN case_thu_tu_trang_thai AS tt
    ON tt.trang_thai = cv.trang_thai
ORDER BY COALESCE(tt.thu_tu, 99), cv.id;
~~~

Trạng thái ON_HOLD chưa có ánh xạ nên nhận hạng 99. Cách này giúp điều chỉnh quy tắc qua dữ liệu nhưng cần quản lý quyền thay đổi cấu hình và bảo đảm không có trạng thái thiếu hạng gây hậu quả ngoài mong đợi.

**CASE phù hợp cho tập trạng thái nhỏ và ổn định; bảng cấu hình phù hợp khi hạng cần quản lý tập trung hoặc thay đổi thường xuyên.**

## 13. ORDER BY CASE trong GROUP BY, DISTINCT và UNION

### 13.1. Sắp xếp các nhóm trạng thái

~~~sql
SELECT
    trang_thai,
    COUNT(*) AS so_cong_viec
FROM case_cong_viec
GROUP BY trang_thai
ORDER BY
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        WHEN 'DONE' THEN 4
        WHEN 'CANCELLED' THEN 5
        ELSE 99
    END;
~~~

Kết quả:

| trang_thai | so_cong_viec |
|---|---:|
| BLOCKED | 2 |
| IN_PROGRESS | 2 |
| NEW | 3 |
| DONE | 1 |
| CANCELLED | 1 |
| ON_HOLD | 1 |

GROUP BY gom nhóm và đếm. CASE chỉ sắp các dòng nhóm theo đúng thứ tự nghiệp vụ.

### 13.2. SELECT DISTINCT có hạn chế ORDER BY

Trong PostgreSQL, SELECT DISTINCT có quy tắc rằng biểu thức ORDER BY phải có mặt thích hợp trong danh sách SELECT. Nếu chỉ cần danh sách trạng thái không trùng nhưng muốn sắp bằng CASE, dùng một bảng dẫn xuất:

~~~sql
SELECT dt.trang_thai
FROM (
    SELECT DISTINCT trang_thai
    FROM case_cong_viec
) AS dt
ORDER BY
    CASE dt.trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        WHEN 'DONE' THEN 4
        WHEN 'CANCELLED' THEN 5
        ELSE 99
    END;
~~~

### 13.3. UNION ALL và biểu thức sắp xếp

Một số hệ quản trị giới hạn ORDER BY sau UNION/UNION ALL chỉ được tham chiếu các cột của kết quả. Có thể bọc UNION trong bảng dẫn xuất để sắp bằng CASE:

~~~sql
SELECT dt.trang_thai
FROM (
    SELECT trang_thai
    FROM case_cong_viec
    WHERE trang_thai = 'BLOCKED'

    UNION ALL

    SELECT trang_thai
    FROM case_cong_viec
    WHERE trang_thai = 'NEW'
) AS dt
ORDER BY
    CASE dt.trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'NEW' THEN 2
        ELSE 99
    END,
    dt.trang_thai;
~~~

UNION ALL giữ các dòng trùng: dữ liệu mẫu có hai BLOCKED và ba NEW. Nếu muốn mỗi trạng thái xuất hiện một lần, cần UNION hoặc DISTINCT theo đúng yêu cầu.

## 14. CASE trong ORDER BY của hàm cửa sổ

Hàm ROW_NUMBER() có ORDER BY riêng trong OVER (...):

~~~sql
SELECT
    id,
    trang_thai,
    ROW_NUMBER() OVER (
        ORDER BY
            CASE trang_thai
                WHEN 'BLOCKED' THEN 1
                WHEN 'IN_PROGRESS' THEN 2
                WHEN 'NEW' THEN 3
                WHEN 'DONE' THEN 4
                WHEN 'CANCELLED' THEN 5
                ELSE 99
            END,
            id
    ) AS so_thu_tu
FROM case_cong_viec
ORDER BY so_thu_tu;
~~~

**ORDER BY trong OVER** quyết định thứ tự dùng để đánh số; **ORDER BY ngoài cùng** quyết định thứ tự hiển thị. Nếu không viết ORDER BY ngoài cùng, không được giả định các dòng sẽ xuất hiện đúng trình tự ROW_NUMBER đã tính.

Có thể đánh số trong từng trạng thái với PARTITION BY:

~~~sql
SELECT
    id,
    trang_thai,
    muc_do,
    ROW_NUMBER() OVER (
        PARTITION BY trang_thai
        ORDER BY
            CASE muc_do
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH' THEN 2
                WHEN 'MEDIUM' THEN 3
                WHEN 'LOW' THEN 4
                ELSE 99
            END,
            id
    ) AS so_trong_nhom
FROM case_cong_viec
ORDER BY trang_thai, so_trong_nhom;
~~~

Ở truy vấn thứ hai, mỗi nhóm trạng thái có dãy số riêng. Để xếp **các nhóm** theo nghiệp vụ thay vì chữ cái, cần dùng CASE thêm vào ORDER BY ngoài cùng.

## 15. Không dựa vào ORDER BY bên trong truy vấn con

Xét:

~~~sql
SELECT dt.id, dt.trang_thai
FROM (
    SELECT id, trang_thai
    FROM case_cong_viec
    ORDER BY
        CASE WHEN trang_thai = 'BLOCKED' THEN 0 ELSE 1 END,
        id
) AS dt;
~~~

Không nên suy ra rằng kết quả của SELECT ngoài **luôn** được hiển thị theo thứ tự trong truy vấn con. Nếu cần thứ tự của kết quả cuối, hãy viết ORDER BY ngoài cùng.

ORDER BY trong subquery có thể có ý nghĩa khi đi kèm LIMIT/FETCH để **chọn những hàng nào** vào bảng dẫn xuất. Nhưng việc trình bày kết quả ngoài cùng vẫn cần ORDER BY ngoài cùng. Một số DBMS, như SQL Server, còn có hạn chế riêng đối với ORDER BY trong derived table.

## 16. Hiệu năng của ORDER BY CASE

CASE tạo khóa sắp xếp dựa trên biểu thức. Index thông thường trên cột trang_thai không nhất thiết giúp máy chủ trả kết quả theo thứ tự hạng CASE, vì thứ tự từ điển của chuỗi khác thứ tự nghiệp vụ.

Trên PostgreSQL, có thể xem kế hoạch dự kiến:

~~~sql
EXPLAIN
SELECT id, trang_thai
FROM case_cong_viec
ORDER BY
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        ELSE 99
    END,
    id;
~~~

EXPLAIN cho biết kế hoạch của optimizer. Với bảng nhỏ, cách quét và sắp xếp có thể rất đơn giản; với bảng lớn, kế hoạch phụ thuộc thống kê, chỉ mục, điều kiện và phiên bản PostgreSQL.

Khi một quy tắc CASE được dùng nhiều lần trên tập dữ liệu lớn, có thể cân nhắc:

- **Expression index** nếu DBMS hỗ trợ và biểu thức phù hợp kế hoạch truy vấn.
- **Cột hạng tính sẵn hoặc generated column** khi thứ tự ổn định và thường xuyên được dùng.
- **Bảng cấu hình thứ hạng** nếu thứ tự thay đổi theo nghiệp vụ.
- **Lọc các hàng cần thiết trước khi sắp** nếu không làm đổi mục tiêu truy vấn.
- **Keyset pagination** khi cần duyệt nhiều trang với OFFSET lớn.

Các phương án tối ưu đều có chi phí lưu trữ, cập nhật hoặc quản lý. Không nên thêm chúng chỉ vì dữ liệu mẫu nhỏ có CASE.

## 17. Khác biệt theo hệ quản trị

CASE trong ORDER BY là kỹ thuật phổ biến, nhưng cú pháp giới hạn dòng và quy tắc NULL không hoàn toàn giống nhau.

| Hệ quản trị | CASE trong ORDER BY | Lưu ý |
|---|---|---|
| PostgreSQL | Có | LIMIT/OFFSET, NULLS FIRST/LAST, expression index |
| MySQL/MariaDB | Có | LIMIT/OFFSET, thứ tự NULL mặc định có thể khác |
| SQL Server | Có | OFFSET ... FETCH hoặc TOP; không dùng LIMIT |
| Oracle | Có | FETCH FIRST ... ROWS ONLY trên phiên bản phù hợp |
| SQLite | Có | LIMIT/OFFSET, đặc điểm kiểu dữ liệu và tối ưu riêng |

### 17.1. SQL Server

~~~sql
-- Ví dụ giả định đã có bảng dbo.CongViec.
SELECT Id, TrangThai
FROM dbo.CongViec
ORDER BY
    CASE TrangThai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        ELSE 99
    END,
    Id
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Đây là mẫu T-SQL; tên bảng và cột cần điều chỉnh theo cơ sở dữ liệu thực tế.

### 17.2. MySQL/MariaDB

~~~sql
SELECT id, trang_thai
FROM cong_viec
ORDER BY
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        ELSE 99
    END,
    id
LIMIT 20 OFFSET 0;
~~~

### 17.3. Oracle

~~~sql
SELECT id, trang_thai
FROM cong_viec
ORDER BY
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        ELSE 99
    END,
    id
FETCH FIRST 20 ROWS ONLY;
~~~

Ví dụ này dùng cú pháp giới hạn dòng của phiên bản Oracle có hỗ trợ tương ứng.

### 17.4. SQLite

~~~sql
SELECT id, trang_thai
FROM cong_viec
ORDER BY
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        ELSE 99
    END,
    id
LIMIT 20;
~~~

Các ví dụ ngoài PostgreSQL dùng bảng giả định tên cong_viec; bộ DDL PostgreSQL ở phần 3 không nhất thiết chạy nguyên dạng trên mỗi DBMS.

**Collation:** khi một tiêu chí ORDER BY là tên người hoặc tên công việc, thứ tự tiếng Việt, chữ hoa và chữ thường còn phụ thuộc quy tắc so sánh chuỗi. CASE trả **số hạng** giúp xếp nhóm theo nghiệp vụ, nhưng nếu thêm tên làm tiêu chí phụ, tên vẫn chịu ảnh hưởng collation.

## 18. Những lỗi thường gặp

| Cách viết hoặc giả định | Vấn đề | Cách xử lý |
|---|---|---|
| ORDER BY trang_thai tự xếp đúng nghiệp vụ | Chỉ sắp theo ký tự | Dùng CASE ánh xạ hạng |
| Bỏ ELSE | Giá trị chưa khớp cho NULL | Đặt ELSE theo chính sách |
| Dùng WHEN x = NULL | So sánh NULL không cho TRUE | Dùng IS NULL |
| Hạng 1 ưu tiên nhất nhưng dùng DESC | Hạng lớn lên trước | Dùng ASC hoặc đổi hạng có chủ đích |
| Đặt hạn trước trạng thái | Hạn thành tiêu chí chính | Đặt biểu thức theo mức độ ưu tiên |
| Không thêm ID cuối ORDER BY | Hàng cùng hạng không có thứ tự xác định | Thêm khóa duy nhất |
| Đặt WHEN rộng trước WHEN cụ thể | Điều kiện đặc biệt bị che | Kiểm tra thứ tự nhánh |
| Trộn số và chuỗi trong kết quả CASE | Có thể lỗi chuyển kiểu | Dùng kiểu kết quả phù hợp |
| Có CASE trong SELECT nhưng thiếu ORDER BY | Chỉ tính hạng, chưa sắp | Thêm ORDER BY |
| Đặt ORDER BY trong truy vấn con là đủ | Không bảo đảm thứ tự ngoài cùng | ORDER BY ở SELECT cuối |
| OFFSET luôn không trùng trang | Dữ liệu có thể thay đổi | Cân nhắc cursor/snapshot |
| CASE tự làm truy vấn nhanh | Không thay thế chỉ mục | Xem EXPLAIN |

## 19. Bài tập tự luyện và lời giải

Các bài sau dùng bảng case_cong_viec đã tạo ở phần 3.

### Bài 1. NEW đứng trước IN_PROGRESS và BLOCKED

**Yêu cầu:** màn hình phân công muốn NEW → IN_PROGRESS → BLOCKED → DONE → còn lại, cùng trạng thái thì ID tăng dần.

~~~sql
SELECT id, trang_thai
FROM case_cong_viec
ORDER BY
    CASE trang_thai
        WHEN 'NEW' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'BLOCKED' THEN 3
        WHEN 'DONE' THEN 4
        ELSE 99
    END,
    id;
~~~

**Kết quả theo nhóm:** NEW: 102, 106, 110; IN_PROGRESS: 103, 104; BLOCKED: 101, 108; DONE: 105; các trạng thái còn lại: 107, 109.

### Bài 2. Mức độ chưa được gán phải đứng đầu

**Yêu cầu:** chưa phân loại trước, sau đó CRITICAL, HIGH, MEDIUM, LOW.

~~~sql
SELECT id, muc_do
FROM case_cong_viec
ORDER BY
    CASE
        WHEN muc_do IS NULL THEN 0
        WHEN muc_do = 'CRITICAL' THEN 1
        WHEN muc_do = 'HIGH' THEN 2
        WHEN muc_do = 'MEDIUM' THEN 3
        WHEN muc_do = 'LOW' THEN 4
        ELSE 99
    END,
    id;
~~~

**Đáp án:** ID 108 đứng đầu vì muc_do NULL. Sau đó đến nhóm CRITICAL gồm 101, 104.

### Bài 3. Công việc chưa có hạn nằm cuối

~~~sql
SELECT id, han_xu_ly
FROM case_cong_viec
ORDER BY
    CASE WHEN han_xu_ly IS NULL THEN 1 ELSE 0 END,
    han_xu_ly,
    id;
~~~

**Kết quả:** nhóm có hạn theo thứ tự 110, 104, 101, 103, 108, 106, 109; nhóm thiếu hạn là 102, 105, 107.

### Bài 4. Lấy ba công việc đầu tiên theo trạng thái nghiệp vụ

~~~sql
SELECT id, trang_thai
FROM case_cong_viec
ORDER BY
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        WHEN 'DONE' THEN 4
        WHEN 'CANCELLED' THEN 5
        ELSE 99
    END,
    id
LIMIT 3;
~~~

**Đáp án:** 101, 108, 103. Với dữ liệu không đổi, trang tiếp theo dùng LIMIT 3 OFFSET 3 sẽ có 104, 102, 106.

### Bài 5. Giải thích vì sao một CASE trả hạng sai

~~~sql
CASE
    WHEN muc_do IN ('CRITICAL', 'HIGH') THEN 2
    WHEN muc_do = 'CRITICAL' THEN 1
    ELSE 3
END
~~~

**Đáp án:** CRITICAL nhận hạng 2 vì nhánh đầu đúng và CASE không xét tiếp. Cần đưa nhánh CRITICAL riêng lên trước.

### Bài 6. Đếm số việc theo trạng thái nhưng sắp theo thứ tự nghiệp vụ

~~~sql
SELECT trang_thai, COUNT(*) AS so_luong
FROM case_cong_viec
GROUP BY trang_thai
ORDER BY
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        WHEN 'DONE' THEN 4
        WHEN 'CANCELLED' THEN 5
        ELSE 99
    END;
~~~

**Đáp án:** BLOCKED 2, IN_PROGRESS 2, NEW 3, DONE 1, CANCELLED 1, ON_HOLD 1.

### Bài 7. ON_HOLD phải đứng giữa NEW và DONE

~~~sql
SELECT id, trang_thai
FROM case_cong_viec
ORDER BY
    CASE trang_thai
        WHEN 'BLOCKED' THEN 1
        WHEN 'IN_PROGRESS' THEN 2
        WHEN 'NEW' THEN 3
        WHEN 'ON_HOLD' THEN 4
        WHEN 'DONE' THEN 5
        WHEN 'CANCELLED' THEN 6
        ELSE 99
    END,
    id;
~~~

**Đáp án:** ID 109 (ON_HOLD) xuất hiện sau nhóm NEW và trước DONE. Dữ liệu trạng thái trong bảng không cần sửa.

### Bài 8. Lấy ba hàng sau cursor

**Yêu cầu:** thứ tự theo hạng trạng thái rồi ID tăng dần. Cursor của trang trước là hạng 2, ID 104.

~~~sql
WITH ranked AS (
    SELECT
        id,
        trang_thai,
        CASE trang_thai
            WHEN 'BLOCKED' THEN 1
            WHEN 'IN_PROGRESS' THEN 2
            WHEN 'NEW' THEN 3
            WHEN 'DONE' THEN 4
            WHEN 'CANCELLED' THEN 5
            ELSE 99
        END AS hang_trang_thai
    FROM case_cong_viec
)
SELECT id, trang_thai
FROM ranked
WHERE (hang_trang_thai, id) > (2, 104)
ORDER BY hang_trang_thai, id
LIMIT 3;
~~~

**Đáp án:** 102, 106, 110 — ba công việc NEW theo ID.

## 20. Ghi nhớ

**ORDER BY CASE** chuyển quy tắc ưu tiên nghiệp vụ thành khóa sắp xếp có thể giải thích được:

- Simple CASE phù hợp để ánh xạ các mã trạng thái; searched CASE phù hợp để xét nhiều cột và điều kiện phức hợp.
- Các nhánh WHEN được xét theo thứ tự, và ELSE cần có ý nghĩa rõ ràng đối với giá trị chưa được ánh xạ.
- Nhiều biểu thức trong ORDER BY tạo thứ tự **theo cấp**: trạng thái, mức độ, hạn xử lý rồi khóa duy nhất chẳng hạn.
- Cần xử lý NULL có chủ đích và chọn ASC/DESC phù hợp với ý nghĩa hạng số.
- Khi phân trang, hãy có khóa phá hòa duy nhất; OFFSET có thể dịch vị trí khi dữ liệu thay đổi, còn cursor cần mang đủ khóa sắp xếp.
- Với quy tắc thường xuyên thay đổi, cân nhắc bảng cấu hình hạng; với dữ liệu lớn, xem kế hoạch thực thi trước khi tối ưu.

Nhờ sử dụng CASE trong ORDER BY đúng cách, danh sách SQL phản ánh được trình tự xử lý thực tế, đồng thời giữ logic ưu tiên minh bạch và phù hợp với yêu cầu phân trang của ứng dụng.

# Chuyển quan hệ một với một hoặc một với nhiều thành khóa ngoại

## Mục tiêu học tập

Sơ đồ thực thể–liên kết (ER) mô tả **thực thể** và **bội số liên kết** giữa các thực thể, còn mô hình quan hệ cần các bảng, khóa và ràng buộc có thể thực thi. Khi ánh xạ một liên kết **một–một (1:1)** hoặc **một–nhiều (1:N)** sang bảng SQL, quyết định quan trọng nhất là **đặt khóa ngoại ở bảng nào**, sau đó xác định liên kết có bắt buộc hay không và có yêu cầu duy nhất hay không.

Bài thuộc chương **Mô hình quan hệ** của module **DATABASE_DATA_MODELING**. Mục tiêu của module là rèn kỹ năng chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, từ thực thể, quan hệ và ràng buộc đến chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; so sánh mô hình quan hệ với document, đồ thị và dữ liệu phân tích để chọn cấu trúc phù hợp, dễ tiến hóa và kiểm chứng.

Sau bài học, bạn có thể:

1. Đọc đúng bội số **0..1, 1..1, 0..N, 1..N** và xác định bên nào là “một”, bên nào là “nhiều”.
2. Ánh xạ liên kết **1:N** thành **khóa ngoại ở phía N**, phân biệt liên kết bắt buộc và tùy chọn.
3. Ánh xạ liên kết **1:1** bằng **FK kết hợp UNIQUE** hoặc **khóa chính dùng chung**, lựa chọn hướng đặt FK phù hợp vòng đời dữ liệu.
4. Giải thích chính xác những gì **FOREIGN KEY**, **NOT NULL**, **UNIQUE** có thể và không thể bảo đảm, đặc biệt là tham gia toàn phần ở **phía được tham chiếu**.
5. Nhận diện trường hợp cần **khóa ngoại ghép**, bảng lịch sử quan hệ hoặc mô hình khác do yêu cầu nghiệp vụ.
6. Kiểm chứng thiết kế bằng lệnh SQL, dữ liệu mẫu, các thao tác vi phạm ràng buộc và truy vấn JOIN.

## 1. Đọc đúng bội số và tính bắt buộc trước khi đặt khóa ngoại

Một **liên kết** trong ER cho biết các thể hiện của hai kiểu thực thể có thể liên hệ với nhau như thế nào. Hai thông tin cần tách riêng là:

- **Bội số tối đa:** tối đa một hay nhiều thể hiện được liên kết.
- **Bội số tối thiểu:** có bắt buộc ít nhất một thể hiện được liên kết không.

| Ký hiệu | Cách đọc | Ví dụ nghiệp vụ |
| --- | --- | --- |
| **0..1** | Không có hoặc tối đa một | Nhân viên có thể chưa được cấp tài khoản |
| **1..1** | Bắt buộc đúng một | Mỗi đơn hàng phải thuộc đúng một khách hàng |
| **0..N** | Không có hoặc nhiều | Một khách có thể chưa có đơn, hoặc có nhiều đơn |
| **1..N** | Ít nhất một, có thể nhiều | Một lớp đang hoạt động phải có ít nhất một học viên |

**Ví dụ 1 — 1:N:** Mỗi **ĐƠN_HÀNG** thuộc đúng một **KHÁCH_HÀNG**, còn một khách hàng có thể đặt **0..N** đơn. Ta nói **KHÁCH_HÀNG là phía 1**, **ĐƠN_HÀNG là phía N**.

**Ví dụ 2 — 1:1:** Mỗi **TÀI_KHOẢN_NỘI_BỘ** thuộc đúng một **NHÂN_VIÊN**, còn một nhân viên có thể chưa có tài khoản hoặc có tối đa một tài khoản. Đây là 1:1, nhưng tính bắt buộc **không đối xứng**: tài khoản phải có nhân viên, nhân viên có thể chưa có tài khoản.

### Đọc sơ đồ ER bằng Mermaid

~~~~mermaid
erDiagram
    KHACH_HANG ||--o{ DON_HANG : dat
    NHAN_VIEN ||--o| TAI_KHOAN : duoc_cap
~~~~

Theo ký hiệu chân quạ ở đây, **o{** là 0..N, **o|** là 0..1, còn **||** là đúng một. Vì vậy:

- Mỗi đơn thuộc **đúng một khách**, nhưng mỗi khách có **0..N đơn**.
- Mỗi tài khoản thuộc **đúng một nhân viên**, nhưng mỗi nhân viên có **0..1 tài khoản**.

Khi đọc sơ đồ từ tài liệu khác, cần xác định ký pháp mà công cụ sử dụng; không suy ra bội số chỉ từ việc đường nối được vẽ ở bên trái hay bên phải.

## 2. Khóa ngoại thực sự bảo đảm điều gì?

**Khóa ngoại (foreign key, FK)** là thuộc tính hoặc tập thuộc tính của **bảng tham chiếu** (*bảng con*) trỏ tới khóa phù hợp của **bảng được tham chiếu** (*bảng cha*). Ví dụ:

~~~~text
KHACH_HANG(ma_kh PK, ho_ten)
DON_HANG(ma_dh PK, ma_kh FK, ngay_dat)

DON_HANG.ma_kh → KHACH_HANG.ma_kh
~~~~

Trong thiết kế trên:

- FK bảo đảm một giá trị **DON_HANG.ma_kh** không NULL phải khớp với mã khách hàng tồn tại.
- **NOT NULL** đặt ở DON_HANG.ma_kh bảo đảm đơn hàng không bỏ trống mã khách.
- FK không cấm **nhiều đơn cùng ma_kh**; đây chính là tính chất cần có cho 1:N.
- FK **không bắt khách hàng phải có đơn**: khách hàng chưa từng mua vẫn hợp lệ.

Nếu một FK cho phép NULL, SQL thường không yêu cầu hàng chứa NULL phải tìm được bản ghi cha, theo quy tắc kiểm tra mặc định. Vì vậy, **FK không tự diễn đạt liên kết bắt buộc**; cần đặt thêm NOT NULL khi mọi bản ghi con phải tham gia liên kết.

Một FK cũng **không tự mô tả tất cả bội số ở phía cha**. Ví dụ, không thể chỉ thêm FK ở DON_HANG để bảo đảm mọi khách hàng đã đăng ký phải có ít nhất một đơn. Điều kiện “ít nhất một bản ghi con” là ràng buộc tồn tại ngược chiều, thường phải xử lý qua quy trình nghiệp vụ hoặc cơ chế liên bảng phù hợp.

## 3. Quy tắc ánh xạ quan hệ 1:N

### 3.1. Đặt FK ở bảng phía nhiều

Với liên kết 1:N giữa thực thể **A** (phía 1) và **B** (phía N), phép ánh xạ quan hệ thông dụng:

1. Tạo bảng A với khóa chính **PK(A)**.
2. Tạo bảng B với khóa chính riêng **PK(B)**.
3. **Đưa PK(A) vào B** làm một hoặc nhiều cột FK tham chiếu A.
4. Nếu **mọi B phải thuộc một A**, khai báo các thành phần FK cần thiết là **NOT NULL**.
5. Nếu **B có thể chưa thuộc A**, cho phép FK NULL khi phù hợp với nghiệp vụ.
6. **Không đặt UNIQUE trên FK ở B** nếu một A được phép có nhiều B.

Minh họa:

~~~~text
KHACH_HANG(ma_kh PK, ho_ten)
            1
            |
            | đặt khóa ma_kh xuống phía N
            v
DON_HANG(ma_dh PK, ma_kh FK, ngay_dat)
            N
~~~~

SQL mẫu:

~~~~sql
CREATE TABLE khach_hang (
    ma_kh VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL
);

CREATE TABLE don_hang (
    ma_dh VARCHAR(20) PRIMARY KEY,
    ma_kh VARCHAR(20) NOT NULL,
    ngay_dat DATE NOT NULL,
    CONSTRAINT fk_don_hang_khach
        FOREIGN KEY (ma_kh)
        REFERENCES khach_hang (ma_kh)
);
~~~~

Một khách **KH01** có thể xuất hiện trong hàng trăm dòng của DON_HANG; điều đó không vi phạm FK. Các đơn vẫn khác nhau nhờ khóa chính ma_dh.

### 3.2. Vì sao không đặt FK đơn hàng trong KHACH_HANG?

Nếu đặt cột **ma_dh** trong KHACH_HANG, mỗi hàng khách hàng chỉ có chỗ cho một mã đơn. Điều này tương đương mô hình “một khách có tối đa một đơn” nếu chỉ sử dụng một cột đơn trị, trái với yêu cầu khách được đặt nhiều đơn.

Các phương án như lưu chuỗi **DH01,DH02,DH03** trong một ô khách hàng còn gây khó khăn khi truy vấn, kiểm tra FK và chuẩn hóa. Cách đúng là để **nhiều hàng DON_HANG tham chiếu cùng KHACH_HANG**, như bảng con của 1:N.

### 3.3. Tùy chọn ở phía nhiều

Một **NHÂN_VIÊN** có thể tạm thời chưa thuộc **PHÒNG_BAN**, nhưng mỗi nhân viên được gán phòng thì chỉ thuộc tối đa một phòng hiện tại. Một phòng có thể có nhiều nhân viên.

~~~~sql
CREATE TABLE phong_ban (
    ma_phong VARCHAR(20) PRIMARY KEY,
    ten_phong VARCHAR(120) NOT NULL
);

CREATE TABLE nhan_vien (
    ma_nv VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL,
    ma_phong VARCHAR(20),
    FOREIGN KEY (ma_phong) REFERENCES phong_ban(ma_phong)
);
~~~~

Ở đây **ma_phong có thể NULL** để biểu diễn “chưa phân phòng”. Nếu yêu cầu thay thành “mọi nhân viên phải thuộc đúng một phòng”, chỉ cho NULL không còn phù hợp; cần khai báo **ma_phong NOT NULL** và có thể cần di chuyển hoặc sửa dữ liệu cũ trước khi áp ràng buộc.

Không nên dùng một giá trị giả như **'NONE'** hoặc **'0'** làm mã phòng không có thật chỉ để tránh NULL, trừ khi tổ chức thực sự có một phòng được quản trị riêng với mã đó.

## 4. Quy tắc ánh xạ quan hệ 1:1

Một liên kết 1:1 nghĩa là **mỗi thể hiện ở mỗi phía liên kết với tối đa một thể hiện phía kia**. Chỉ một FK thông thường **chưa đủ**: nếu không có ràng buộc duy nhất, nhiều hàng con có thể cùng tham chiếu một hàng cha, trở thành 1:N.

### 4.1. FK kèm UNIQUE

Ví dụ, mỗi **NHÂN_VIÊN** được cấp tối đa một **TÀI_KHOẢN**, và mọi tài khoản phải thuộc đúng một nhân viên.

~~~~text
NHAN_VIEN(ma_nv PK, ho_ten)
TAI_KHOAN(ma_tk PK, ma_nv FK UNIQUE NOT NULL, ten_dang_nhap)
~~~~

SQL:

~~~~sql
CREATE TABLE nhan_vien (
    ma_nv VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL
);

CREATE TABLE tai_khoan (
    ma_tk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_nv VARCHAR(20) NOT NULL UNIQUE,
    ten_dang_nhap VARCHAR(60) NOT NULL UNIQUE,
    CONSTRAINT fk_tai_khoan_nhan_vien
        FOREIGN KEY (ma_nv)
        REFERENCES nhan_vien (ma_nv)
        ON DELETE RESTRICT
);
~~~~

Mỗi ràng buộc có một nhiệm vụ khác nhau:

| Ràng buộc | Điều được bảo đảm |
| --- | --- |
| TAI_KHOAN.ma_nv là FK | Mọi tài khoản phải trỏ đến nhân viên có thật nếu có mã |
| TAI_KHOAN.ma_nv NOT NULL | Mọi tài khoản bắt buộc có mã nhân viên |
| TAI_KHOAN.ma_nv UNIQUE | Không có hai tài khoản trỏ đến cùng nhân viên |
| TAI_KHOAN.ma_tk PRIMARY KEY | Mỗi tài khoản có định danh riêng |
| NHAN_VIEN.ma_nv PRIMARY KEY | Mỗi nhân viên có định danh duy nhất |

Như vậy, **mỗi tài khoản thuộc đúng một nhân viên**, và **mỗi nhân viên có tối đa một tài khoản**. Một nhân viên chưa có tài khoản vẫn hợp lệ; UNIQUE ở TAI_KHOAN không buộc phải tạo tài khoản cho tất cả nhân viên.

### 4.2. Chọn chiều đặt FK dựa trên tính bắt buộc và vòng đời

Với liên kết 1:1, **FK có thể đặt ở một trong hai bảng**, nhưng chiều được chọn ảnh hưởng đến số lượng giá trị NULL, thời điểm tạo dữ liệu và khả năng diễn đạt sự tham gia bắt buộc.

| Tình huống | Cách thường chọn | Lý do |
| --- | --- | --- |
| Nhân viên có thể chưa có tài khoản; tài khoản phải có nhân viên | Đặt FK UNIQUE NOT NULL tại TAI_KHOAN | Không cần cột NULL ở NHAN_VIEN; bắt buộc ở phía tài khoản |
| Nhân viên có thể được cấp một chỗ đỗ xe; chỗ đỗ cũng có thể trống | Đặt FK nullable UNIQUE ở một phía tùy vòng đời, hoặc bảng phân công riêng nếu cần lịch sử | Cả hai phía đều tùy chọn |
| Hồ sơ chi tiết không có ý nghĩa tách khỏi nhân viên | Dùng **khóa chính dùng chung**, PK của hồ sơ đồng thời là FK | Thể hiện định danh gắn chặt với nhân viên |
| Hai phần dữ liệu luôn sinh ra cùng lúc, có cùng vòng đời và bảo mật | Cân nhắc lưu cùng bảng | Tránh tách không cần thiết |

Đừng chọn chiều FK chỉ vì một bảng được vẽ bên trái hay bên phải. Cần hỏi **bảng nào có thể tồn tại trước**, **đối tượng nào bắt buộc có đối tượng còn lại**, **thao tác xóa/sửa ảnh hưởng ra sao** và **bảng nào chứa thông tin riêng cần bảo vệ**.

### 4.3. Khóa chính dùng chung (shared primary key)

Nếu **HỒ_SƠ_NHÂN_VIÊN** có tối đa một bản ghi cho mỗi nhân viên và không cần định danh độc lập:

~~~~sql
CREATE TABLE ho_so_nhan_vien (
    ma_nv VARCHAR(20) PRIMARY KEY,
    ngay_sinh DATE,
    dia_chi VARCHAR(250),
    CONSTRAINT fk_ho_so_nhan_vien
        FOREIGN KEY (ma_nv)
        REFERENCES nhan_vien (ma_nv)
        ON DELETE CASCADE
);
~~~~

Cột **ho_so_nhan_vien.ma_nv** đóng **hai vai trò**: PK của hồ sơ và FK tới nhân viên. Vì là PK, ma_nv không NULL và không được lặp; vì là FK, ma_nv phải tham chiếu nhân viên có thật. Kết quả là một nhân viên có **0 hoặc 1 hồ sơ**, còn mỗi hồ sơ thuộc **đúng một nhân viên**.

Đây là cách ánh xạ gọn khi bản ghi bổ sung được định danh bằng chủ sở hữu. Tuy nhiên, **shared PK không tự bắt buộc mọi nhân viên phải có hồ sơ**. Việc bắt buộc cả hai phía tham gia cần cơ chế khác hoặc cân nhắc gộp dữ liệu khi thích hợp.

### 4.4. FK UNIQUE nullable và nhiều giá trị NULL

Giả sử **CHO_DO** có cột **ma_nv** cho biết nhân viên đang sử dụng chỗ đỗ, nhưng chỗ đỗ có thể đang trống:

~~~~sql
CREATE TABLE cho_do (
    ma_cho VARCHAR(20) PRIMARY KEY,
    ma_nv VARCHAR(20) UNIQUE
        REFERENCES nhan_vien(ma_nv)
);
~~~~

Trong PostgreSQL, một ràng buộc UNIQUE thông thường **cho phép nhiều dòng có ma_nv NULL**. Do vậy, nhiều chỗ đỗ trống là hợp lệ, nhưng một nhân viên không thể được gán hai chỗ đỗ có ma_nv xác định.

Nếu nghiệp vụ muốn biểu diễn rằng **mọi chỗ đỗ luôn được phân cho đúng một nhân viên**, thì ma_nv phải NOT NULL. Nhưng yêu cầu này có thể không thực tế vì chỗ đỗ trống trong quá trình vận hành. Việc cho phép NULL là quyết định từ **bội số tối thiểu**, không phải lỗi kỹ thuật.

## 5. Điều mà FK, UNIQUE và NOT NULL chưa bảo đảm

### 5.1. Không bảo đảm phía cha phải có con

Trong 1:N:

~~~~text
KHACH_HANG (1) ← (N) DON_HANG
~~~~

FK từ DON_HANG bảo đảm **mỗi đơn có khách hàng phù hợp**, chứ không bảo đảm **mọi khách hàng đều có ít nhất một đơn**.

Tương tự, trong 1:1, FK UNIQUE NOT NULL tại TAI_KHOAN bảo đảm **tài khoản luôn gắn với một nhân viên** và **một nhân viên có tối đa một tài khoản**, nhưng **không** bảo đảm **mỗi nhân viên đều có tài khoản**.

Đây là khác biệt giữa **tham gia toàn phần ở phía chứa FK** và **tham gia toàn phần ở phía được tham chiếu**.

### 5.2. Không tự diễn đạt 1..N ở phía cha

Giả sử bài toán yêu cầu “mỗi **LỚP_HỌC đã khai giảng** phải có ít nhất một **HỌC_VIÊN**”, còn mỗi học viên thuộc đúng một lớp:

- FK trong HOC_VIEN kiểm tra học viên phải tham chiếu lớp tồn tại.
- NOT NULL của HOC_VIEN.ma_lop bảo đảm học viên có lớp.
- Không có ràng buộc FK đơn giản nào ở bảng học viên tự bảo đảm **mỗi lớp đã khai giảng có ít nhất một học viên**.

Vì vậy, cần kiểm tra khi chuyển trạng thái lớp sang **da_khai_giang**, trong giao dịch hoặc cơ chế DB phù hợp; đồng thời cần kiểm soát thao tác chuyển/xóa học viên cuối cùng khi lớp đang hoạt động.

Một truy vấn tìm lớp đã khai giảng nhưng rỗng có thể là:

~~~~sql
-- Minh họa cú pháp, giả định có hai bảng lop_hoc và hoc_vien.
SELECT l.ma_lop
FROM lop_hoc AS l
WHERE l.trang_thai = 'da_khai_giang'
  AND NOT EXISTS (
      SELECT 1
      FROM hoc_vien AS hv
      WHERE hv.ma_lop = l.ma_lop
  );
~~~~

Truy vấn trên **phát hiện** vi phạm nếu dữ liệu đã tồn tại; tự nó không **ngăn** thao tác ghi. Cần xác định cơ chế thực thi ràng buộc để bảo vệ dữ liệu khi có giao dịch đồng thời.

### 5.3. Quan hệ 1:1 bắt buộc ở cả hai phía

Một yêu cầu 1:1 có thể nói “mỗi A phải có đúng một B và mỗi B phải có đúng một A”. FK UNIQUE NOT NULL đặt ở B mới bảo đảm **mỗi B có đúng một A** và **mỗi A có tối đa một B**; chưa bảo đảm **mỗi A có ít nhất một B**.

Có ba hướng xử lý tùy nhu cầu:

1. **Gộp thành một bảng** khi hai phần có cùng định danh, cùng vòng đời, mọi thuộc tính bắt buộc hoặc được phép nằm chung và không có lý do rõ ràng để tách.
2. **Tách hai bảng với shared PK** rồi dùng quy trình tạo dữ liệu trong giao dịch, kiểm tra điều kiện bắt buộc ở trạng thái nghiệp vụ thích hợp.
3. **Tách với ràng buộc liên bảng chuyên biệt**, chẳng hạn trigger hoặc constraint trì hoãn nếu DBMS hỗ trợ và triển khai đúng; phải quan tâm đến điều kiện đồng thời và thời điểm kiểm tra.

**Không nên mặc định thêm hai FK trỏ vòng qua lại** vì điều đó tạo khó khăn khi chèn, xóa và kiểm soát dữ liệu, mà vẫn cần hiểu rõ hành vi kiểm tra ràng buộc. Khi nghiệp vụ thật sự bắt buộc hai chiều mọi thời điểm, thiết kế cần được thẩm định riêng.

## 6. Thuộc tính của liên kết nên đặt ở đâu?

### 6.1. Thuộc tính của liên kết 1:N

Giả sử một nhân viên thuộc một phòng hiện tại và có **ngay_nhan_phong**. Nếu đây là ngày bắt đầu **phòng hiện tại**, thuộc tính liên kết có thể đặt cùng FK ở bảng phía N:

~~~~text
PHONG_BAN(ma_phong PK, ten_phong)
NHAN_VIEN(ma_nv PK, ma_phong FK, ngay_nhan_phong)
~~~~

Nhưng nếu cần **lịch sử nhân viên chuyển qua nhiều phòng**, một cột ma_phong hiện tại và ngay_nhan_phong chỉ mô tả hiện tại, **không đủ cho các lần phân công trước**. Khi đó có thể tạo bảng sự kiện liên kết:

~~~~text
LICH_SU_PHAN_CONG(
    ma_phan_cong PK,
    ma_nv FK,
    ma_phong FK,
    tu_ngay,
    den_ngay
)
~~~~

Bảng này lưu **nhiều lần liên kết theo thời gian**. Phải định nghĩa rõ liệu các khoảng thời gian có được chồng lấn, một nhân viên được đồng thời ở nhiều phòng hay không, và cách xác định phân công hiện tại.

### 6.2. Thuộc tính của liên kết 1:1

Ví dụ chỗ đỗ được gán cho nhân viên kèm **ngay_bat_dau**. Nếu chỉ cần thông tin hiện tại, có thể đặt ngay_bat_dau ở bảng chứa FK hoặc dùng bảng PHAN_CHO_DO một–một. Nếu cần lưu các lần thay đổi chỗ đỗ theo thời gian, cần mô hình lịch sử riêng với định danh sự kiện.

**Lựa chọn bảng chứa thuộc tính** cần dựa trên thông tin đó thuộc về thực thể hay về **một lần liên kết**. Không nên đưa thuộc tính lịch sử vào thực thể hiện tại rồi hy vọng FK sẽ lưu được các lần chuyển đổi.

## 7. Khi nào không dùng cách ánh xạ 1:1 hoặc 1:N đơn giản?

| Yêu cầu thực tế | Điểm cần xem lại |
| --- | --- |
| Một đơn chứa nhiều sản phẩm, một sản phẩm có trong nhiều đơn | Đây là **N:N**, thường cần bảng chi tiết/bảng nối |
| Một nhân viên chuyển phòng nhiều lần, cần lịch sử | Mối liên kết **thay đổi theo thời gian**, cần bảng lịch sử |
| Mã phòng chỉ duy nhất trong một tenant | FK có thể cần **nhiều cột**, gồm tenant_id |
| Hai phía 1:1 đều bắt buộc tồn tại | FK một chiều chưa đảm bảo cả hai chiều tối thiểu bằng 1 |
| Nhiều người cùng chia sẻ một tài khoản | Không còn 1:1; phải xem lại bội số nghiệp vụ |
| Một hóa đơn có nhiều dòng số thứ tự chỉ duy nhất trong hóa đơn | Đây có thể là **thực thể yếu** với PK ghép (ma_hd, so_dong), không chỉ FK đơn giản |

Số lượng bảng không phải thước đo đúng sai. Mục tiêu của ánh xạ là bảo toàn **ngữ nghĩa thực thể**, **bội số liên kết**, **ràng buộc tham gia** và nhu cầu truy vấn, đồng thời để mô hình dễ mở rộng khi yêu cầu thay đổi.

## 8. Ánh xạ khi khóa phía 1 gồm nhiều cột

Không phải mọi thực thể đều có khóa chính một cột. Giả sử hệ thống phục vụ nhiều công ty (*tenant*); mã phòng **KT** có thể xuất hiện ở nhiều công ty, nên định danh phòng là **(tenant_id, ma_phong)**.

Một phòng thuộc một tenant có thể có nhiều nhân viên; mỗi nhân viên thuộc một phòng của chính tenant:

~~~~text
PHONG_BAN(tenant_id, ma_phong, ten_phong)
PK = (tenant_id, ma_phong)

NHAN_VIEN(tenant_id, ma_nv, ma_phong, ho_ten)
PK = (tenant_id, ma_nv)
FK (tenant_id, ma_phong)
    → PHONG_BAN(tenant_id, ma_phong)
~~~~

Phép ánh xạ 1:N ở đây vẫn tuân theo quy tắc **đưa khóa phía 1 xuống phía N**, nhưng phải đưa **đầy đủ các thành phần** của khóa.

~~~~sql
CREATE TABLE phong_ban (
    tenant_id BIGINT NOT NULL,
    ma_phong VARCHAR(20) NOT NULL,
    ten_phong VARCHAR(120) NOT NULL,
    CONSTRAINT pk_phong_ban PRIMARY KEY (tenant_id, ma_phong)
);

CREATE TABLE nhan_vien (
    tenant_id BIGINT NOT NULL,
    ma_nv VARCHAR(20) NOT NULL,
    ma_phong VARCHAR(20) NOT NULL,
    ho_ten VARCHAR(120) NOT NULL,
    CONSTRAINT pk_nhan_vien PRIMARY KEY (tenant_id, ma_nv),
    CONSTRAINT fk_nv_phong
        FOREIGN KEY (tenant_id, ma_phong)
        REFERENCES phong_ban (tenant_id, ma_phong)
);
~~~~

**Không nên tách** FK ghép thành FK riêng trên tenant_id và FK riêng trên ma_phong: mỗi cột riêng lẻ không định danh được phòng; tệ hơn, nếu tham chiếu tới hai bảng cha khác nhau, chúng không bảo đảm cặp phòng–tenant thuộc cùng một hàng.

### Ánh xạ 1:1 khi khóa là khóa ghép

Nếu mỗi nhân viên trong mô hình trên có tối đa một hồ sơ bổ sung:

~~~~sql
CREATE TABLE ho_so_nhan_vien (
    tenant_id BIGINT NOT NULL,
    ma_nv VARCHAR(20) NOT NULL,
    ngay_sinh DATE,
    dia_chi VARCHAR(250),
    CONSTRAINT pk_ho_so_nv PRIMARY KEY (tenant_id, ma_nv),
    CONSTRAINT fk_ho_so_nv
        FOREIGN KEY (tenant_id, ma_nv)
        REFERENCES nhan_vien (tenant_id, ma_nv)
        ON DELETE CASCADE
);
~~~~

Đây là mô hình **shared primary key dạng ghép**: cùng cặp (tenant_id, ma_nv) là PK của hồ sơ và FK đến nhân viên. Nó bảo đảm mỗi hồ sơ có đúng một nhân viên hợp lệ và mỗi nhân viên có tối đa một hồ sơ. Một nhân viên chưa có hồ sơ vẫn được phép tồn tại.

### Tham chiếu khóa ứng viên không được chọn

Nếu **KHACH_HANG** có PK id và mã nghiệp vụ **ma_khach UNIQUE NOT NULL**, thì DON_HANG cũng có thể tham chiếu **ma_khach**:

~~~~sql
-- DDL độc lập, dùng để giải thích trường hợp FK trỏ alternate key.
CREATE TABLE khach_hang_theo_id (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_khach VARCHAR(20) NOT NULL UNIQUE,
    ho_ten VARCHAR(100) NOT NULL
);

CREATE TABLE don_hang_theo_ma (
    ma_dh VARCHAR(20) PRIMARY KEY,
    ma_khach VARCHAR(20) NOT NULL
        REFERENCES khach_hang_theo_id(ma_khach)
);
~~~~

FK không buộc phải trỏ vào PK nếu cột đích có ràng buộc duy nhất đủ điều kiện của DBMS. Tuy nhiên, nếu mã nghiệp vụ hay thay đổi, tham chiếu bằng id ổn định có thể đơn giản hơn. **Bội số 1:N** được giữ nguyên dù FK dùng khóa chính hay một khóa ứng viên khác.

## 9. Ví dụ thực hành hoàn chỉnh: 1:N và 1:1 trong PostgreSQL

Đoạn SQL ở phần này là **một kịch bản độc lập**; hãy chạy từ đầu trên cơ sở dữ liệu thử nghiệm trống. Nếu đã tạo các bảng cùng tên trong những đoạn minh họa trước, dùng một schema hoặc cơ sở dữ liệu thử khác. Các đoạn DDL ở các mục trước chủ yếu giải thích từng tình huống, không có mục tiêu chạy nối tiếp tất cả.

### 9.1. Xác định mô hình và bội số

| Liên kết | Phía A | Phía B | Quy tắc |
| --- | --- | --- | --- |
| Khách hàng đặt đơn | KHACH_HANG | DON_HANG | Mỗi đơn có **1** khách; mỗi khách có **0..N** đơn |
| Nhân viên được cấp tài khoản | NHAN_VIEN | TAI_KHOAN | Mỗi tài khoản có **1** nhân viên; mỗi nhân viên có **0..1** tài khoản |

Sơ đồ có đánh dấu PK, FK, và UK (ràng buộc UNIQUE):

~~~~mermaid
erDiagram
    KHACH_HANG ||--o{ DON_HANG : dat
    NHAN_VIEN ||--o| TAI_KHOAN : duoc_cap

    KHACH_HANG {
        varchar ma_kh PK
        varchar ho_ten
    }
    DON_HANG {
        varchar ma_dh PK
        varchar ma_kh FK
        date ngay_dat
        decimal tong_tien
    }
    NHAN_VIEN {
        varchar ma_nv PK
        varchar ho_ten
    }
    TAI_KHOAN {
        bigint ma_tk PK
        varchar ma_nv FK,UK
        varchar ten_dang_nhap UK
    }
~~~~

### 9.2. Tạo bảng và ràng buộc

~~~~sql
CREATE TABLE khach_hang (
    ma_kh VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL
);

CREATE TABLE don_hang (
    ma_dh VARCHAR(20) PRIMARY KEY,
    ma_kh VARCHAR(20) NOT NULL,
    ngay_dat DATE NOT NULL,
    tong_tien NUMERIC(12, 2) NOT NULL,
    CONSTRAINT ck_don_hang_tong_tien CHECK (tong_tien >= 0),
    CONSTRAINT fk_don_hang_khach
        FOREIGN KEY (ma_kh)
        REFERENCES khach_hang (ma_kh)
        ON DELETE RESTRICT
);

CREATE TABLE nhan_vien (
    ma_nv VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL
);

CREATE TABLE tai_khoan (
    ma_tk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_nv VARCHAR(20) NOT NULL,
    ten_dang_nhap VARCHAR(60) NOT NULL,
    CONSTRAINT ak_tai_khoan_nhan_vien UNIQUE (ma_nv),
    CONSTRAINT ak_tai_khoan_dang_nhap UNIQUE (ten_dang_nhap),
    CONSTRAINT fk_tai_khoan_nhan_vien
        FOREIGN KEY (ma_nv)
        REFERENCES nhan_vien (ma_nv)
        ON DELETE RESTRICT
);
~~~~

Trong DON_HANG, **ma_kh không UNIQUE** vì khách có thể đặt nhiều đơn. Trong TAI_KHOAN, **ma_nv UNIQUE** vì một nhân viên chỉ có tối đa một tài khoản.

### 9.3. Chèn dữ liệu hợp lệ

~~~~sql
INSERT INTO khach_hang (ma_kh, ho_ten) VALUES
    ('KH01', 'Nguyễn An'),
    ('KH02', 'Trần Bình'),
    ('KH03', 'Lê Chi');

INSERT INTO don_hang (ma_dh, ma_kh, ngay_dat, tong_tien) VALUES
    ('DH01', 'KH01', DATE '2026-10-01', 200000),
    ('DH02', 'KH01', DATE '2026-10-02', 350000),
    ('DH03', 'KH02', DATE '2026-10-03', 100000);

INSERT INTO nhan_vien (ma_nv, ho_ten) VALUES
    ('NV01', 'Mai Minh'),
    ('NV02', 'Vũ Lan'),
    ('NV03', 'Hoàng Khoa');

INSERT INTO tai_khoan (ma_nv, ten_dang_nhap) VALUES
    ('NV01', 'mai.minh'),
    ('NV03', 'hoang.khoa');
~~~~

Hệ thống cho phép:

- Hai đơn DH01 và DH02 cùng thuộc KH01 (**1:N**).
- Khách KH03 chưa có đơn (**0..N ở phía khách**).
- Nhân viên NV02 chưa có tài khoản (**0..1 ở phía nhân viên**).

### 9.4. Kiểm tra bằng truy vấn JOIN

**Đếm số đơn trên từng khách hàng**, kể cả khách chưa mua:

~~~~sql
SELECT
    kh.ma_kh,
    kh.ho_ten,
    COUNT(dh.ma_dh) AS so_don
FROM khach_hang AS kh
LEFT JOIN don_hang AS dh ON dh.ma_kh = kh.ma_kh
GROUP BY kh.ma_kh, kh.ho_ten
ORDER BY kh.ma_kh;
~~~~

| ma_kh | ho_ten | so_don |
| --- | --- | ---: |
| KH01 | Nguyễn An | 2 |
| KH02 | Trần Bình | 1 |
| KH03 | Lê Chi | 0 |

Chọn **COUNT(dh.ma_dh)** vì ma_dh là khóa chính không NULL ở bảng con. Nếu dùng COUNT(*) trên LEFT JOIN, khách KH03 vẫn sinh một dòng kết quả với các cột đơn hàng NULL và sẽ bị đếm nhầm là có một đơn.

**Liệt kê tài khoản của từng nhân viên**, kể cả người chưa có:

~~~~sql
SELECT
    nv.ma_nv,
    nv.ho_ten,
    tk.ten_dang_nhap
FROM nhan_vien AS nv
LEFT JOIN tai_khoan AS tk ON tk.ma_nv = nv.ma_nv
ORDER BY nv.ma_nv;
~~~~

| ma_nv | ho_ten | ten_dang_nhap |
| --- | --- | --- |
| NV01 | Mai Minh | mai.minh |
| NV02 | Vũ Lan | NULL |
| NV03 | Hoàng Khoa | hoang.khoa |

Giá trị NULL ở cột kết quả của NV02 do **LEFT JOIN không tìm được tài khoản**, không có nghĩa bảng TAI_KHOAN chứa một bản ghi với ma_nv NULL. Thực tế, cột TAI_KHOAN.ma_nv là NOT NULL.

### 9.5. Thử dữ liệu vi phạm

Các lệnh dưới đây **cố ý thất bại**, nên chạy từng câu riêng trên dữ liệu đã nạp để quan sát ràng buộc:

~~~~sql
-- Vi phạm FK: khách KH999 không tồn tại.
INSERT INTO don_hang (ma_dh, ma_kh, ngay_dat, tong_tien)
VALUES ('DH99', 'KH999', DATE '2026-10-04', 1000);

-- Vi phạm NOT NULL: mỗi đơn bắt buộc có khách.
INSERT INTO don_hang (ma_dh, ma_kh, ngay_dat, tong_tien)
VALUES ('DH98', NULL, DATE '2026-10-04', 1000);

-- Vi phạm UNIQUE của 1:1: NV01 đã có tài khoản.
INSERT INTO tai_khoan (ma_nv, ten_dang_nhap)
VALUES ('NV01', 'mai.minh.phu');

-- Vi phạm FK: NV999 không tồn tại.
INSERT INTO tai_khoan (ma_nv, ten_dang_nhap)
VALUES ('NV999', 'nv.khong.ton.tai');

-- Vi phạm NOT NULL: tài khoản phải có nhân viên.
INSERT INTO tai_khoan (ma_nv, ten_dang_nhap)
VALUES (NULL, 'khong.co.nhan.vien');
~~~~

Ngược lại, **đơn mới DH04 có ma_kh = KH01** sẽ hợp lệ vì quan hệ khách–đơn là 1:N; mã khách xuất hiện trong nhiều đơn là đúng với nghiệp vụ:

~~~~sql
INSERT INTO don_hang (ma_dh, ma_kh, ngay_dat, tong_tien)
VALUES ('DH04', 'KH01', DATE '2026-10-04', 50000);
~~~~

## 10. Chính sách xóa và cập nhật khóa được tham chiếu

Khi thêm FK, cần quyết định **điều gì xảy ra nếu bản ghi phía 1 bị xóa hoặc khóa của nó thay đổi**.

| Chính sách | Hành vi | Gợi ý sử dụng |
| --- | --- | --- |
| **ON DELETE RESTRICT** | Chặn xóa bản ghi phía 1 còn được tham chiếu | Khách có đơn đã chốt, nhân viên có hồ sơ cần giữ |
| **ON DELETE NO ACTION** | Không cho giao dịch kết thúc với FK vi phạm; chi tiết thời điểm kiểm tra có thể khác RESTRICT nếu có ràng buộc trì hoãn | Giao dịch cập nhật nhiều bảng |
| **ON DELETE CASCADE** | Xóa các hàng phía chứa FK khi xóa bản ghi phía 1 | Dữ liệu phụ thực sự không cần sống riêng |
| **ON DELETE SET NULL** | Đặt FK trong bản ghi con thành NULL | Liên kết **tùy chọn**, cột FK cho phép NULL |
| **ON UPDATE CASCADE** | Tự cập nhật FK con khi khóa cha đổi | Mã nghiệp vụ được phép thay đổi |

Trong ví dụ DON_HANG.ma_kh NOT NULL, dùng **SET NULL** khi xóa khách sẽ xung đột với quy tắc đơn phải có khách. **CASCADE** có thể làm mất đơn hàng lịch sử, nên không nên chọn chỉ vì thuận tiện.

Trong 1:1, nếu TAI_KHOAN bắt buộc thuộc nhân viên, xóa nhân viên đang có tài khoản cần một chính sách cụ thể: chặn xóa, xóa tài khoản cùng nhân viên, hoặc dùng trạng thái ngừng hoạt động. Không có chính sách chung đúng cho mọi hệ thống.

**ON UPDATE CASCADE** có thể phù hợp nếu FK tham chiếu mã nghiệp vụ được phép đổi. Tuy vậy, những định danh kỹ thuật được dùng làm PK thường nên ổn định; việc đổi khóa có thể ảnh hưởng nhiều bảng và quy trình tích hợp.

## 11. Khóa ngoại, ràng buộc duy nhất và chỉ mục

**Ràng buộc khóa** diễn đạt tính đúng của dữ liệu; **chỉ mục** phục vụ tìm kiếm và có thể giúp thực thi ràng buộc.

Trong PostgreSQL:

- PRIMARY KEY và UNIQUE thường tạo chỉ mục duy nhất tương ứng.
- Khai báo FOREIGN KEY ở bảng con **không tự động tạo chỉ mục ở cột FK**.
- Với 1:N, thường cần xem xét chỉ mục trên FK phía nhiều khi truy vấn thường lọc theo phía 1 hoặc khi có nhiều thao tác xóa/cập nhật phía cha.
- Với 1:1, chỉ mục được tạo bởi UNIQUE ở cột FK thường đã hỗ trợ các truy vấn tìm hàng con theo khóa cha.

Ví dụ với bảng DON_HANG:

~~~~sql
CREATE INDEX ix_don_hang_ma_kh
    ON don_hang (ma_kh);
~~~~

Đây là một **quyết định vật lý**, không làm thay đổi 1:N thành 1:1. Ngược lại, nếu thêm **UNIQUE(ma_kh)** vào DON_HANG, đó là thay đổi **ràng buộc logic** và sẽ vô tình giới hạn mỗi khách còn tối đa một đơn.

Không tạo chỉ mục cho tất cả FK theo thói quen. Hãy đánh giá kích thước bảng, các truy vấn thật, cấu trúc chỉ mục đã có, kế hoạch thực thi và chi phí ghi trước khi quyết định.

## 12. Bảng quyết định nhanh khi ánh xạ liên kết

Trước khi chuyển một đường nối ER thành cột FK, hãy xác định rõ **bội số tối đa**, **bội số tối thiểu** và **bảng nào mang FK**. Bảng dưới giả định A là phía cha/được tham chiếu, B là phía con/chứa FK.

| Quan hệ nghiệp vụ | Quy tắc trong bảng B | Điều SQL bảo đảm trực tiếp | Điều còn cần xem xét |
| --- | --- | --- | --- |
| A 1 — B N, mỗi B bắt buộc có A | FK đến A **NOT NULL**, **không UNIQUE** | Mỗi B có một A tồn tại; nhiều B được chia sẻ A | Có cần mỗi A có ít nhất một B không? |
| A 1 — B N, B có thể chưa có A | FK đến A **nullable**, **không UNIQUE** | Mỗi B có 0 hoặc 1 A; mỗi A có nhiều B | NULL mang ý nghĩa gì trong nghiệp vụ? |
| A 1 — B 1, B bắt buộc có A | FK đến A **UNIQUE NOT NULL** | Mỗi B đúng một A; mỗi A tối đa một B | Có bắt buộc mỗi A có một B không? |
| A 1 — B 1, B có thể không có A | FK đến A **UNIQUE nullable** | Mỗi B tối đa một A; mỗi A tối đa một B | NULL và thời điểm gán liên kết |
| B dùng định danh của A cho một phần mở rộng 1:1 | PK(B) đồng thời là FK đến A | B luôn có A và A có tối đa một B | Sự tồn tại bắt buộc của B đối với A |
| Mỗi A bắt buộc có ít nhất một B | FK trong B như 1:N, thêm điều kiện tồn tại phía A | Bảo đảm chiều B → A | Cần quy tắc liên bảng/giao dịch cho A → ít nhất một B |

**Cách đọc:** Một FK ở B trỏ đến một hàng A chỉ định danh được **một** A cho mỗi B. Để bảo đảm chiều ngược lại “một A không quá một B” trong 1:1, cần **UNIQUE trên FK của B**. Để bảo đảm “B bắt buộc có A”, cần **NOT NULL trên FK của B**. Còn “A bắt buộc có B” là một quy tắc khác, không tự xuất hiện từ hai ràng buộc trên.

### Ví dụ phản chứng cho 1:1

Giả sử có:

~~~~text
NHAN_VIEN:
NV01, NV02

TAI_KHOAN:
TK01 → NV01
~~~~

Hàng TK01 có FK NOT NULL hợp lệ, UNIQUE(ma_nv) cũng hợp lệ. Nhưng NV02 chưa có tài khoản. Nếu yêu cầu là **0..1 tài khoản trên mỗi nhân viên**, dữ liệu đúng. Nếu yêu cầu là **1..1 tài khoản trên mỗi nhân viên**, dữ liệu đã vi phạm một quy tắc nghiệp vụ **chưa được ràng buộc bằng FK và UNIQUE đơn thuần**.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đặt FK ở phía 1 khi quan hệ thực tế là 1:N | Mỗi hàng phía 1 chỉ thể hiện được một hàng phía N | Chuyển FK sang phía N |
| Đặt UNIQUE trên FK của phía N | Vô tình biến 1:N thành tối đa 1:1 | Bỏ UNIQUE nếu nghiệp vụ cho phép nhiều B chung A |
| Ánh xạ 1:1 bằng FK mà không UNIQUE | Nhiều hàng B có thể cùng trỏ vào A | Thêm UNIQUE hoặc dùng PK đồng thời FK |
| Ánh xạ liên kết bắt buộc mà cho FK NULL | B có thể không có A | Bổ sung NOT NULL theo bội số tối thiểu |
| Cho NOT NULL trên FK của một liên kết tùy chọn | Không thể tạo bản ghi trước khi được gán liên kết | Cho phép NULL nếu nghiệp vụ thực sự cho phép |
| Nghĩ FK UNIQUE NOT NULL bảo đảm 1:1 bắt buộc hai chiều | Phía A vẫn có thể tồn tại mà không có B | Gộp bảng hoặc bổ sung cơ chế kiểm tra phía A |
| Dùng một FK đơn cho khóa cha ghép theo tenant | Không định danh đúng cha, dễ sai phạm vi | Tham chiếu toàn bộ khóa ghép |
| Lưu các mã con ngăn cách dấu phẩy ở bảng cha | Không kiểm chứng được mỗi mã bằng FK thông thường | Dùng các hàng ở bảng phía N |
| Dùng ON DELETE CASCADE vì tiện thao tác | Dễ mất dữ liệu giao dịch cần lưu vết | Xác định vòng đời và chính sách xóa |
| Dùng SET NULL với FK bắt buộc NOT NULL | Hành động xóa xung đột ràng buộc | Dùng chính sách khác, hoặc xem lại tính bắt buộc |
| Lưu thuộc tính lịch sử ở FK hiện tại | Mất những lần liên kết trước | Tạo bảng lịch sử/sự kiện khi cần |
| Cứ có hai bảng và hai FK là quan hệ N:N | Nhầm giữa liên kết 1:1, 1:N với bảng nối N:N | Xác định bội số và định danh sự kiện liên kết |

### Trường hợp đặc biệt: bảng nối xuất hiện khi cần lịch sử

Quan hệ “nhân viên thuộc phòng ban” ở một **thời điểm** thường là 1:N, có thể dùng FK ở NHAN_VIEN. Nhưng quan hệ “nhân viên **đã từng** thuộc phòng ban nào” có thể là N:N theo lịch sử. Một nhân viên từng thuộc nhiều phòng, một phòng từng có nhiều nhân viên, và mỗi lần phân công có thể có ngày bắt đầu/kết thúc. Vì vậy, một bảng lịch sử liên kết là phù hợp.

Điều này **không bác bỏ** quy tắc ánh xạ 1:N. Nó cho thấy trước khi ánh xạ, phải xác định **thời điểm và phạm vi sự kiện** mà câu mô tả nghiệp vụ đề cập.

## 14. Quy trình làm việc từ ER đến lược đồ quan hệ

Có thể áp dụng quy trình sau cho một bài toán thực tế:

1. **Viết hai chiều của quy tắc nghiệp vụ.** Ví dụ “mỗi đơn có đúng một khách” **và** “mỗi khách có thể có nhiều đơn”. Không chỉ viết một câu.
2. **Xác định bội số tối thiểu và tối đa ở từng phía.** Ghi rõ 0..1, 1..1, 0..N hay 1..N.
3. **Tìm khóa của mỗi thực thể.** Đảm bảo phía được tham chiếu có PK hoặc khóa duy nhất thích hợp.
4. **Nếu là 1:N, đặt FK ở phía N.** Không đặt UNIQUE lên FK trừ khi nghiệp vụ thực tế đã đổi.
5. **Nếu là 1:1, chọn hướng FK.** Ưu tiên hướng cho phép diễn đạt phía bắt buộc bằng FK NOT NULL và tránh NULL không cần thiết; cân nhắc shared PK.
6. **Ánh xạ bội số tối thiểu thành NOT NULL khi phù hợp.** Với liên kết tùy chọn ở phía chứa FK, cho phép NULL theo quy tắc đã mô tả.
7. **Xem xét phần còn lại của tính tham gia toàn phần.** Nếu phía cha buộc có con, xác định cách kiểm tra khi tạo, chuyển trạng thái, xóa hoặc chuyển liên kết.
8. **Quy định thay đổi khóa và xóa dữ liệu.** Chọn RESTRICT, CASCADE, SET NULL hoặc giải pháp vòng đời phù hợp.
9. **Kiểm tra khóa ghép và phạm vi dữ liệu.** Với hệ thống nhiều tenant, không để tham chiếu vượt ranh giới do thiếu thành phần khóa.
10. **Tạo phản ví dụ và thử SQL.** Kiểm tra bản ghi con không có cha, FK trùng trong 1:1, FK trùng hợp lệ trong 1:N và trường hợp chưa có liên kết.
11. **Đánh giá truy vấn và chỉ mục.** Sau khi mô hình logic đúng, đo truy vấn phổ biến và bổ sung chỉ mục nếu cần.

## 15. Bài tập tự kiểm tra có đáp án

### Bài 1 — Nhà xuất bản và sách: 1:N

Mỗi sách phải có đúng một nhà xuất bản, mỗi nhà xuất bản có thể có 0 hoặc nhiều sách. Cho hai bảng NHA_XUAT_BAN(ma_nxb, ten_nxb) và SACH(ma_sach, tieu_de).

**Yêu cầu:** Nêu phía 1, phía N, vị trí FK và các ràng buộc bắt buộc.

**Đáp án:** NHA_XUAT_BAN là phía 1, SACH là phía N. Thêm SACH.ma_nxb **NOT NULL REFERENCES NHA_XUAT_BAN(ma_nxb)**. **Không đặt UNIQUE** trên SACH.ma_nxb vì nhiều sách có thể chung nhà xuất bản. Không yêu cầu mỗi nhà xuất bản phải có sách.

### Bài 2 — Đoán bội số từ DDL

~~~~sql
CREATE TABLE a (
    id BIGINT PRIMARY KEY
);

CREATE TABLE b (
    id BIGINT PRIMARY KEY,
    a_id BIGINT NOT NULL UNIQUE REFERENCES a(id)
);
~~~~

**Câu hỏi:** Quan hệ thực thi giữa A và B là 1:N hay 1:1? Một A có thể không có B không?

**Đáp án:** Đây là **1:1 có phía B bắt buộc và phía A tùy chọn**: mỗi B trỏ đúng một A; mỗi A có tối đa một B. A có thể không có B vì không có ràng buộc nào bắt A phải xuất hiện trong bảng B.

### Bài 3 — Bỏ UNIQUE trong 1:1

Giả sử bảng TAI_KHOAN(ma_tk PK, ma_nv NOT NULL FK) thiếu UNIQUE trên ma_nv, còn yêu cầu là mỗi nhân viên có tối đa một tài khoản.

**Câu hỏi:** Có thể xảy ra dữ liệu sai nào? Sửa bằng SQL ra sao?

**Đáp án:** Hai tài khoản khác ma_tk có thể cùng ma_nv. Khi dữ liệu hiện có không trùng, có thể thêm:

~~~~sql
ALTER TABLE tai_khoan
ADD CONSTRAINT ak_tai_khoan_nhan_vien UNIQUE (ma_nv);
~~~~

Nếu bảng đã có dữ liệu trùng, cần xử lý các bản ghi vi phạm trước khi thêm ràng buộc.

### Bài 4 — Liên kết tùy chọn ở phía N

Một nhân viên có thể chưa được phân phòng; một phòng có thể có nhiều nhân viên. Cho PHONG_BAN(ma_phong PK), NHAN_VIEN(ma_nv PK, ma_phong).

**Câu hỏi:** Có nên khai báo NHAN_VIEN.ma_phong NOT NULL không? Có cần UNIQUE không?

**Đáp án:** Không nên đặt NOT NULL nếu vẫn cho phép nhân viên chưa phân phòng; ma_phong cần là FK **nullable**. Không đặt UNIQUE vì nhiều nhân viên có thể cùng phòng. Khi quy tắc đổi sang “mọi nhân viên phải có phòng”, mới cân nhắc NOT NULL sau khi xử lý dữ liệu hiện có.

### Bài 5 — Chỗ đỗ xe 1:1 tùy chọn cả hai phía

Một nhân viên có tối đa một chỗ đỗ; một chỗ đỗ có tối đa một nhân viên; nhiều chỗ có thể trống. Bảng CHO_DO(ma_cho PK, ma_nv) lưu người được gán.

**Câu hỏi:** Cần ràng buộc gì trên ma_nv? Có thể có hai hàng ma_nv NULL không?

**Đáp án:** Cần **UNIQUE(ma_nv)** và FK đến NHAN_VIEN(ma_nv), nhưng cho phép ma_nv **NULL** để biểu diễn chỗ trống. Với PostgreSQL UNIQUE thông thường, **nhiều NULL được phép**. Hai chỗ trống không vi phạm tính 1:1; một nhân viên không được gán hai chỗ có mã nhân viên không NULL.

### Bài 6 — 1:1 bắt buộc cả hai phía

Một nhân viên phải có đúng một hồ sơ và mọi hồ sơ phải thuộc đúng một nhân viên. Bảng HO_SO_NHAN_VIEN(ma_nv PK FK) đã tồn tại.

**Câu hỏi:** Có thể tạo NHAN_VIEN mới mà chưa có HO_SO_NHAN_VIEN không? Vì sao?

**Đáp án:** **Có thể**, vì PK đồng thời FK tại bảng hồ sơ chỉ chặn **hồ sơ không có nhân viên** và **hai hồ sơ cùng nhân viên**; nó không bắt mỗi nhân viên phải có hồ sơ. Nếu nghiệp vụ yêu cầu bắt buộc cả hai phía, cân nhắc gộp bảng hoặc kiểm soát tạo và xóa qua giao dịch và ràng buộc liên bảng phù hợp.

### Bài 7 — FK ghép theo tenant

Mã phòng chỉ duy nhất trong từng công ty. PHONG_BAN có PK(tenant_id, ma_phong), NHAN_VIEN có tenant_id và ma_phong.

**Câu hỏi:** FK của NHAN_VIEN cần gồm những cột nào? Có thể chỉ dùng ma_phong không?

**Đáp án:** Cần **FOREIGN KEY (tenant_id, ma_phong) REFERENCES PHONG_BAN(tenant_id, ma_phong)**. Chỉ dùng ma_phong sẽ thiếu thành phần định danh và có nguy cơ tham chiếu nhầm phòng cùng mã của công ty khác.

### Bài 8 — Phân biệt COUNT trên LEFT JOIN

KHACH_HANG có KH01 và KH02; DON_HANG chỉ có hai đơn đều thuộc KH01. Truy vấn:

~~~~sql
SELECT kh.ma_kh, COUNT(*) AS so_don
FROM khach_hang AS kh
LEFT JOIN don_hang AS dh ON dh.ma_kh = kh.ma_kh
GROUP BY kh.ma_kh;
~~~~

**Câu hỏi:** Tại sao KH02 được đếm bằng 1? Cần sửa điều gì?

**Đáp án:** LEFT JOIN tạo một dòng kết quả cho KH02 dù không có đơn, với các cột DON_HANG bằng NULL. COUNT(*) đếm dòng này. Thay **COUNT(*)** thành **COUNT(dh.ma_dh)**, vì ma_dh là khóa chính không NULL và chỉ xuất hiện khi có đơn thực sự.

### Bài 9 — Quan hệ 1:N thay đổi theo thời gian

Mỗi nhân viên chỉ thuộc một phòng **tại một thời điểm**, nhưng hệ thống phải lưu lại mọi lần chuyển phòng trước đó.

**Câu hỏi:** Một cột NHAN_VIEN.ma_phong có đủ để đáp ứng lịch sử không? Nên bổ sung mô hình nào?

**Đáp án:** Cột ma_phong chỉ thể hiện phân công hiện tại, không lưu những phòng cũ. Nên bổ sung **LICH_SU_PHAN_CONG(ma_phan_cong PK, ma_nv FK, ma_phong FK, tu_ngay, den_ngay)** hoặc thiết kế bảng khoảng hiệu lực tương đương. Cần định nghĩa quy tắc chồng lấn thời gian và xác định phân công hiện tại để giữ đúng “một phòng tại một thời điểm”.

### Bài 10 — Không nên dùng CASCADE trong mọi trường hợp

Mỗi đơn thuộc một khách. Khi xóa khách hàng, lập trình viên đề xuất ON DELETE CASCADE để tự xóa mọi đơn.

**Câu hỏi:** Ràng buộc nào cần xem xét trước khi quyết định?

**Đáp án:** Cần xem yêu cầu lưu lịch sử mua hàng, kế toán, báo cáo, hoàn tiền và chính sách lưu trữ. Nếu đơn đã chốt phải còn, nên chặn xóa vật lý khách có đơn, hoặc dùng trạng thái ngừng hoạt động/giải pháp lưu giữ phù hợp. Chỉ dùng CASCADE khi hệ thống thực sự cho phép xóa cả dữ liệu con.

## 16. Tổng kết

| Trường hợp | Cách ánh xạ cốt lõi |
| --- | --- |
| **1:N** | Đưa khóa phía **1** sang bảng phía **N** làm FK |
| **1:N, phía N bắt buộc có cha** | FK **NOT NULL**, không UNIQUE |
| **1:N, phía N có thể chưa có cha** | FK **nullable**, không UNIQUE |
| **1:1** | FK ở một phía **kèm UNIQUE**, hoặc shared PK |
| **1:1, phía chứa FK bắt buộc có phía kia** | FK **UNIQUE NOT NULL** |
| **1:1, phía chứa FK tùy chọn** | FK **UNIQUE nullable** |
| **Khóa chính dùng chung** | PK của bảng phụ đồng thời là FK đến bảng chủ |
| **Bắt buộc có bản ghi con** | FK ở bảng con **không đủ**; cần quy tắc khác |
| **Khóa cha ghép** | FK ở bảng con tham chiếu **đủ mọi thành phần** |
| **Liên kết có lịch sử** | Có thể cần bảng liên kết/sự kiện thay cho một FK hiện tại |

Khi chuyển quan hệ **một–một** hoặc **một–nhiều** sang lược đồ quan hệ, hãy xác định bội số và tính bắt buộc theo **cả hai chiều** trước khi thêm cột. Với 1:N, FK thường nằm ở phía N; với 1:1, FK cần được kết hợp UNIQUE hoặc dùng khóa chính dùng chung. Sau đó, dùng NOT NULL, chính sách tham chiếu và cơ chế kiểm tra liên bảng khi cần để bảo toàn ý nghĩa nghiệp vụ. Chính việc diễn đạt đúng những ràng buộc này tạo nền tảng cho chuẩn hóa, lựa chọn chỉ mục và thiết kế lược đồ vật lý có thể kiểm chứng.

# DEFERRABLE và kiểm tra ràng buộc tại thời điểm commit

Trong Oracle Database, các ràng buộc (*constraints*) bảo vệ tính toàn vẹn của dữ liệu: khóa chính không được trùng, khóa ngoại phải tham chiếu bản ghi cha hợp lệ, giá trị phải thỏa miền cho phép và dữ liệu bắt buộc không được thiếu. Thông thường, Oracle kiểm tra ràng buộc ngay khi một câu lệnh DML hoàn thành. Nhưng có những giao dịch cần **tạm thời đi qua trạng thái chưa thỏa ràng buộc**, miễn là **toàn bộ dữ liệu hợp lệ trước khi giao dịch được commit**.

Ví dụ, khi di chuyển một loạt mã tham chiếu, ứng dụng có thể cần tạo bản ghi con trước bản ghi cha; hoặc khi hoán đổi hai vị trí có ràng buộc UNIQUE, bước trung gian có thể bị trùng dù kết quả cuối cùng không trùng. Oracle giải quyết những tình huống này bằng thuộc tính **DEFERRABLE** và chế độ kiểm tra **IMMEDIATE/DEFERRED**.

Bài này giải thích thời điểm kiểm tra, cách khai báo và thay đổi chế độ theo transaction, ví dụ lỗi tại COMMIT, cách dùng trong Java JDBC, metadata để quan sát và các giới hạn cần lưu ý.

## 1. Một ràng buộc có thể được kiểm tra ở những thời điểm nào?

Với một giao dịch nhiều câu SQL, ta có thể phân biệt:

- **Kiểm tra ở cuối từng câu lệnh (IMMEDIATE)**: mỗi câu INSERT, UPDATE hoặc DELETE phải để dữ liệu thỏa các ràng buộc đang ở chế độ kiểm tra ngay. Nếu vi phạm, câu lệnh đó thất bại.
- **Kiểm tra ở thời điểm kết thúc giao dịch (DEFERRED)**: đối với các ràng buộc được phép hoãn và đang ở chế độ DEFERRED, Oracle cho phép những trạng thái trung gian chưa hợp lệ trong cùng transaction, rồi kiểm tra khi COMMIT hoặc khi ứng dụng yêu cầu chuyển lại về IMMEDIATE.
- **Không có nghĩa là tắt ràng buộc**: dữ liệu cuối cùng vẫn phải hợp lệ mới được commit. Nếu không, COMMIT thất bại và giao dịch không thể được chấp nhận.

~~~text
Giao dịch T
  |
  +-- Câu lệnh 1: chèn bản ghi con tham chiếu cha chưa có
  |       |
  |       +-- IMMEDIATE: báo lỗi ở câu lệnh 1
  |       |
  |       +-- DEFERRED: tạm cho phép, đợi kiểm tra
  |
  +-- Câu lệnh 2: chèn bản ghi cha phù hợp
  |
  +-- COMMIT
          |
          +-- Dữ liệu cuối cùng thỏa constraint --> COMMIT thành công
          |
          +-- Vẫn còn vi phạm ---------------> COMMIT lỗi, transaction bị rollback
~~~

Điểm đáng chú ý là **IMMEDIATE không nhất thiết có nghĩa kiểm tra sau từng hàng được thay đổi**. Khi một statement cập nhật nhiều hàng, Oracle đánh giá các ràng buộc immediate theo ngữ nghĩa kiểm tra câu lệnh thích hợp. DEFERRED khác ở chỗ cho phép vi phạm tồn tại **qua ranh giới của nhiều statement** trong cùng giao dịch.

## 2. Phân biệt DEFERRABLE với DEFERRED

Hai từ gần giống nhau nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Phạm vi |
| --- | --- | --- |
| **DEFERRABLE** | Ràng buộc được khai báo **có khả năng** hoãn kiểm tra | Thuộc tính của định nghĩa constraint |
| **NOT DEFERRABLE** | Ràng buộc không được chuyển sang chế độ kiểm tra cuối giao dịch | Thuộc tính của định nghĩa constraint |
| **INITIALLY IMMEDIATE** | Mặc định mỗi transaction bắt đầu ở chế độ kiểm tra ngay | Cấu hình ban đầu của constraint |
| **INITIALLY DEFERRED** | Mặc định mỗi transaction bắt đầu ở chế độ hoãn kiểm tra | Cấu hình ban đầu của constraint |
| **SET CONSTRAINTS ... IMMEDIATE** | Đổi chế độ kiểm tra trong transaction hiện tại về ngay | Điều khiển trong giao dịch |
| **SET CONSTRAINTS ... DEFERRED** | Đổi chế độ của constraint có thể hoãn trong transaction hiện tại | Điều khiển trong giao dịch |

Một ràng buộc **DEFERRABLE INITIALLY IMMEDIATE** hoàn toàn có thể bị kiểm tra ngay trong phần lớn giao dịch, và chỉ được hoãn trong một giao dịch đặc biệt khi ứng dụng gọi SET CONSTRAINTS.

Ngược lại, một ràng buộc **DEFERRABLE INITIALLY DEFERRED** mặc định đợi tới cuối transaction, nhưng ứng dụng vẫn có thể yêu cầu kiểm tra sớm bằng SET CONSTRAINTS ... IMMEDIATE.

**NOT DEFERRABLE** không có nghĩa constraint không quan trọng; nó có nghĩa không được chuyển sang chế độ kiểm tra hoãn bằng SET CONSTRAINTS. Nếu không viết DEFERRABLE trong định nghĩa, trạng thái mặc định của ràng buộc thường là **NOT DEFERRABLE**.

### 2.1. Ma trận thiết kế

| Khai báo | Mặc định khi transaction bắt đầu | Có thể gọi SET CONSTRAINTS ... DEFERRED? |
| --- | --- | --- |
| Không chỉ định DEFERRABLE | IMMEDIATE (NOT DEFERRABLE) | Không |
| NOT DEFERRABLE INITIALLY IMMEDIATE | IMMEDIATE | Không |
| DEFERRABLE INITIALLY IMMEDIATE | IMMEDIATE | Có |
| DEFERRABLE INITIALLY DEFERRED | DEFERRED | Có |

Không được khai báo một constraint **NOT DEFERRABLE INITIALLY DEFERRED** để mong “mặc định deferred nhưng không cho đổi”; đó là hai ý trái nhau. Muốn mặc định kiểm tra ở cuối giao dịch, cần một constraint được khai báo DEFERRABLE.

## 3. Tại sao cần cơ chế hoãn kiểm tra?

### 3.1. Tạo cha và con không theo thứ tự

Thông thường, để chèn bản ghi **NHAN_VIEN** có khóa ngoại tới **PHONG_BAN**, ứng dụng cần chèn phòng ban trước:

~~~text
PHONG_BAN (ma_phong = 10)
    |
    +--- NHAN_VIEN (ma_nv = 101, ma_phong = 10)
~~~

Nhưng trong một đợt import, có thể thuận tiện chèn nhân viên trước rồi mới chèn phòng ban, miễn là toàn bộ hai phần được xử lý trong một transaction. Với khóa ngoại DEFERRABLE đang ở DEFERRED, trạng thái trung gian có thể được cho phép.

### 3.2. Hoán đổi giá trị UNIQUE

Giả sử hai hàng đang có vị trí xếp hạng 1 và 2, mỗi vị trí phải là duy nhất:

~~~text
Trước:
  Mục A -> vị trí 1
  Mục B -> vị trí 2

Mục tiêu:
  Mục A -> vị trí 2
  Mục B -> vị trí 1
~~~

Nếu đổi A sang 2 trước, câu UPDATE đầu tiên tạm tạo hai hàng có vị trí 2. Nếu đổi B trước, lại tạm tạo hai hàng có vị trí 1. Với UNIQUE DEFERRABLE, ứng dụng có thể hoãn kiểm tra cho đến sau cả hai UPDATE, khi kết quả cuối cùng không còn trùng.

### 3.3. Quan hệ khóa ngoại vòng

Ví dụ:

- Mỗi nhân viên thuộc một phòng ban.
- Mỗi phòng ban phải chỉ định một nhân viên làm trưởng phòng.

Trong một số thiết kế, hai bảng tham chiếu qua lại. Khi tạo cả phòng ban và trưởng phòng mới, không có thứ tự chèn nào làm thỏa tất cả khóa ngoại bắt buộc ngay từ statement đầu tiên. Hoãn khóa ngoại phù hợp trong **một giao dịch** có thể giải quyết vòng phụ thuộc. Tuy nhiên, đôi khi cần **thiết kế lại quan hệ và thời điểm gán trưởng phòng** thay vì sử dụng cơ chế hoãn cho mọi thao tác.

## 4. Cú pháp tạo ràng buộc DEFERRABLE

Trong Oracle, thuộc tính có thể khai báo tại thời điểm tạo constraint, ví dụ với FOREIGN KEY và UNIQUE:

~~~sql
CREATE TABLE phong_ban_dt (
    ma_phong  NUMBER(6) CONSTRAINT pk_pb_dt PRIMARY KEY,
    ten_phong VARCHAR2(100 CHAR) NOT NULL
);

CREATE TABLE nhan_vien_dt (
    ma_nv     NUMBER(6) CONSTRAINT pk_nv_dt PRIMARY KEY,
    ma_phong  NUMBER(6) NOT NULL,
    ho_ten    VARCHAR2(100 CHAR) NOT NULL,

    CONSTRAINT fk_nv_phong_dt
        FOREIGN KEY (ma_phong)
        REFERENCES phong_ban_dt (ma_phong)
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

Trong ví dụ:

- **PK_PB_DT** và **PK_NV_DT** là primary key được khai báo thông thường.
- **FK_NV_PHONG_DT** là foreign key **DEFERRABLE**, nhưng mặc định ở chế độ **IMMEDIATE**.
- **MA_PHONG NOT NULL** vẫn yêu cầu giá trị mã phòng được cung cấp; hoãn foreign key **không** biến một mã phòng NULL thành giá trị hợp lệ.
- Các tên constraint được đặt rõ ràng để có thể gọi SET CONSTRAINTS và đọc thông báo lỗi dễ hơn.

Với dữ liệu có nhiều thao tác cần hoãn mặc định, có thể khai báo khóa ngoại dạng:

~~~sql
CONSTRAINT fk_ten_rang_buoc
    FOREIGN KEY (ma_cha)
    REFERENCES bang_cha (ma_cha)
    DEFERRABLE INITIALLY DEFERRED
~~~

Đây là **một đoạn cú pháp minh họa bên trong CREATE TABLE hoặc ALTER TABLE ADD CONSTRAINT**, không phải câu SQL độc lập có thể thực thi riêng. Đặt trạng thái mặc định theo đặc tính nghiệp vụ: phần lớn hệ thống giao dịch trực tuyến nên cân nhắc IMMEDIATE để nhận lỗi sớm, và chỉ dùng DEFERRED ở những thao tác có yêu cầu thực sự.

### 4.1. Không thể đổi tùy tiện thuộc tính DEFERRABLE sau khi tạo

Trong Oracle, không thể chỉ dùng một lệnh ALTER CONSTRAINT để chuyển trực tiếp một constraint từ **NOT DEFERRABLE** thành **DEFERRABLE** hoặc ngược lại. Nếu cần thay thuộc tính khả năng hoãn, thường phải có kế hoạch **drop và tái tạo constraint** với định nghĩa tương ứng.

Việc thay constraint có thể ảnh hưởng khóa, index hỗ trợ, kiểm tra dữ liệu hiện hữu và DDL implicit commit. Không thực hiện tùy tiện trong một giao dịch nghiệp vụ hoặc trên production khi chưa có kế hoạch migration và kiểm tra đầy đủ.

## 5. Thực hành 1: khóa ngoại kiểm tra ngay

Với hai bảng **PHONG_BAN_DT** và **NHAN_VIEN_DT** vừa tạo, giả định ban đầu chưa có hàng nào. Thử chèn nhân viên trước khi có phòng ban:

~~~sql
-- Cố ý gây lỗi vì phòng ban 10 chưa tồn tại.
INSERT INTO nhan_vien_dt (ma_nv, ma_phong, ho_ten)
VALUES (101, 10, 'Nguyen An');
~~~

Vì **FK_NV_PHONG_DT** đang ở chế độ INITIALLY IMMEDIATE theo mặc định, câu lệnh thất bại, thường với lỗi **ORA-02291** (integrity constraint violated - parent key not found).

Điều quan trọng là lỗi xảy ra **ở statement INSERT**, không cần đợi COMMIT. Nếu ứng dụng thực hiện một transaction lớn, lỗi sớm giúp xác định bước có vấn đề ngay khi nó xuất hiện.

Nếu muốn chạy lại bài thử trong cùng schema:

~~~sql
ROLLBACK;
~~~

Đây chỉ là thao tác dọn phần DML chưa commit nếu có; câu INSERT bị từ chối không được chèn vào bảng. Không phải cứ ROLLBACK mới khiến ràng buộc immediate hoạt động.

## 6. Thực hành 2: hoãn kiểm tra khóa ngoại, rồi sửa trước COMMIT

Trong một transaction mới, đặt **FK_NV_PHONG_DT** sang DEFERRED trước khi chèn:

~~~sql
-- Áp dụng cho transaction hiện tại.
SET CONSTRAINTS fk_nv_phong_dt DEFERRED;

-- Tạm thời thiếu parent: được cho phép vì FK đang deferred.
INSERT INTO nhan_vien_dt (ma_nv, ma_phong, ho_ten)
VALUES (101, 10, 'Nguyen An');

-- Hoàn thiện parent trước khi commit.
INSERT INTO phong_ban_dt (ma_phong, ten_phong)
VALUES (10, 'Phong nghiep vu');

-- Chủ động yêu cầu kiểm tra FK ngay lúc này.
SET CONSTRAINTS fk_nv_phong_dt IMMEDIATE;

COMMIT;
~~~

Ở thời điểm giữa hai INSERT, trong transaction có nhân viên tham chiếu phòng ban chưa tồn tại. Nhưng sau INSERT thứ hai, dữ liệu đã thỏa khóa ngoại, nên lệnh **SET CONSTRAINTS ... IMMEDIATE** có thể kiểm tra thành công và COMMIT chấp nhận giao dịch.

Kết quả có thể kiểm tra:

~~~sql
SELECT nv.ma_nv, nv.ho_ten, pb.ten_phong
FROM nhan_vien_dt nv
JOIN phong_ban_dt pb
  ON pb.ma_phong = nv.ma_phong
ORDER BY nv.ma_nv;
~~~

Kết quả gồm nhân viên **101** thuộc **Phong nghiep vu**.

**SET CONSTRAINTS không thay đổi thuộc tính DEFERRABLE được lưu trong schema**; nó điều chỉnh thời điểm kiểm tra trong transaction hiện tại. Khi transaction kết thúc, transaction tiếp theo lại bắt đầu theo cấu hình INITIALLY của constraint.

### 6.1. Vì sao nên kiểm tra sớm bằng IMMEDIATE?

Nếu transaction còn nhiều việc sau khi hoàn thiện quan hệ, việc gọi:

~~~sql
SET CONSTRAINTS ALL IMMEDIATE;
~~~

có thể giúp phát hiện các ràng buộc đang hoãn mà vẫn bị vi phạm **trước khi thực hiện thêm công việc ứng dụng**. Khi chuyển sang IMMEDIATE, Oracle phải kiểm tra những ràng buộc tương ứng. Nếu còn vi phạm, câu SET CONSTRAINTS có thể thất bại.

Tuy nhiên, **SET CONSTRAINTS ALL IMMEDIATE không phải COMMIT**. DML vẫn chưa trở thành thay đổi đã commit. Nếu kiểm tra sớm thành công, ứng dụng vẫn cần COMMIT để kết thúc giao dịch. Những constraint không thể hoãn vốn luôn được kiểm tra theo cơ chế của chúng, không bị tác động bởi câu lệnh này.

## 7. Thực hành 3: phát hiện vi phạm khi cố chuyển về IMMEDIATE

Giả sử không chèn phòng ban tương ứng:

~~~sql
SET CONSTRAINTS fk_nv_phong_dt DEFERRED;

INSERT INTO nhan_vien_dt (ma_nv, ma_phong, ho_ten)
VALUES (102, 999, 'Tran Binh');

-- Cố ý gây lỗi vì chưa có PHONG_BAN_DT(999).
SET CONSTRAINTS fk_nv_phong_dt IMMEDIATE;
~~~

Lệnh SET CONSTRAINTS IMMEDIATE kiểm tra trạng thái hiện tại của khóa ngoại và thất bại vì **999** không có trong bảng cha. Đây là cách phát hiện sớm, trước COMMIT.

Trong ví dụ này, nếu không muốn tạo phòng ban 999, có thể hoàn tác giao dịch:

~~~sql
ROLLBACK;
~~~

Hoặc nếu nghiệp vụ thực sự muốn tạo phòng ban 999, có thể chèn parent tương ứng rồi yêu cầu kiểm tra lại, miễn là transaction vẫn đang hoạt động và có đủ quyền. Không phải mọi lỗi SET CONSTRAINTS đều đồng nghĩa dữ liệu bị commit một phần; cần phân biệt **kiểm tra constraint không thành công** với **COMMIT thất bại**.

### 7.1. Kiểm tra theo transaction nhưng không hiển thị cho session khác

Khi khóa ngoại đang deferred, session của transaction đó có thể thấy hàng con tạm thời thiếu parent do chính mình vừa chèn. Các session khác theo isolation thông thường không thấy DML chưa commit của transaction này.

Dù vậy, một trạng thái trung gian chưa hợp lệ vẫn có thể ảnh hưởng đến **trigger, SQL tiếp theo trong cùng transaction, xử lý Java và logic kiểm tra khác**. Do đó chỉ dùng deferral trong phạm vi logic đã được thiết kế để xử lý trạng thái trung gian.

## 8. Thực hành 4: vi phạm tồn tại tới COMMIT

Một tình huống khác là ứng dụng không hề đưa dữ liệu về trạng thái hợp lệ:

~~~sql
SET CONSTRAINTS fk_nv_phong_dt DEFERRED;

INSERT INTO nhan_vien_dt (ma_nv, ma_phong, ho_ten)
VALUES (103, 998, 'Le Chi');

-- Cố ý gây lỗi ở giai đoạn COMMIT.
COMMIT;
~~~

Vì **PHONG_BAN_DT(998)** không tồn tại, COMMIT phải kiểm tra khóa ngoại đang hoãn và không thể hoàn tất. Oracle thường báo chuỗi lỗi liên quan như:

~~~text
ORA-02091: transaction rolled back
ORA-02291: integrity constraint (...) violated - parent key not found
~~~

Khi một deferred constraint bị vi phạm tại COMMIT, **Oracle rollback giao dịch thất bại**, không chấp nhận một nửa transaction rồi chỉ loại bỏ hàng lỗi. Sau đó phải khởi tạo transaction mới với dữ liệu hợp lệ; không thể coi COMMIT lỗi là đã ghi thành công một phần.

Có thể đối chiếu:

~~~sql
SELECT ma_nv, ma_phong, ho_ten
FROM nhan_vien_dt
ORDER BY ma_nv;
~~~

Nếu trước đó chỉ có transaction thành công ở phần 6, bảng vẫn có nhân viên **101** và không có nhân viên **103**. Thông điệp lỗi chi tiết có thể khác theo phiên bản hoặc driver; phần quan trọng là **không có COMMIT thành công** cho dữ liệu vi phạm.

### 8.1. Một lỗi COMMIT khác lỗi câu INSERT

| Thời điểm | Dạng lỗi | Kết quả cần hiểu |
| --- | --- | --- |
| INSERT khi FK immediate | Statement bị từ chối | Không thêm hàng vi phạm; transaction có thể tiếp tục xử lý những việc khác tùy ứng dụng |
| SET CONSTRAINTS ... IMMEDIATE khi còn vi phạm | Không chuyển kiểm tra thành công | Cần sửa dữ liệu hoặc rollback, không tự xem là đã commit |
| COMMIT khi FK vẫn deferred và vi phạm | Giao dịch không thể commit | Transaction bị rollback |
| COMMIT sau khi mọi deferred constraint đã thỏa | Giao dịch commit thành công | Thay đổi được chấp nhận theo quy tắc transaction |

Với ứng dụng Java, nếu JDBC trả lỗi lúc COMMIT, không được báo cho người dùng rằng thao tác đã hoàn thành. Cần ghi nhận lỗi, xác định trạng thái transaction theo loại lỗi và áp dụng quy trình retry có kiểm soát.

## 9. Thực hành 5: UNIQUE DEFERRABLE và hoán đổi giá trị

Ví dụ khóa ngoại cho thấy sự phụ thuộc giữa hai bảng. Một trường hợp khác là cần tạm trùng giá trị khi cập nhật nhiều hàng, nhưng trạng thái cuối phải duy nhất.

### 9.1. Tạo bảng có UNIQUE DEFERRABLE

~~~sql
CREATE TABLE thu_tu_dt (
    ma_muc  NUMBER(6) CONSTRAINT pk_tt_dt PRIMARY KEY,
    vi_tri  NUMBER(5) NOT NULL,

    CONSTRAINT uq_tt_vitri_dt
        UNIQUE (vi_tri)
        DEFERRABLE INITIALLY IMMEDIATE
);

INSERT INTO thu_tu_dt (ma_muc, vi_tri) VALUES (1, 1);
INSERT INTO thu_tu_dt (ma_muc, vi_tri) VALUES (2, 2);
COMMIT;
~~~

Bảng có hai hàng, các giá trị **VI_TRI** là 1 và 2. Nếu chạy một UPDATE riêng:

~~~sql
-- Cố ý gây lỗi ở chế độ immediate vì vị trí 2 đã tồn tại.
UPDATE thu_tu_dt
SET vi_tri = 2
WHERE ma_muc = 1;
~~~

Câu lệnh này thường bị từ chối do **UQ_TT_VITRI_DT**, với lỗi như **ORA-00001**. Dù mục tiêu sau cùng là hoán đổi, riêng statement đầu tiên tạo trạng thái hai hàng có cùng vị trí 2.

### 9.2. Hoán đổi trong một transaction deferred

~~~sql
SET CONSTRAINTS uq_tt_vitri_dt DEFERRED;

UPDATE thu_tu_dt
SET vi_tri = 2
WHERE ma_muc = 1;

UPDATE thu_tu_dt
SET vi_tri = 1
WHERE ma_muc = 2;

SET CONSTRAINTS uq_tt_vitri_dt IMMEDIATE;

COMMIT;
~~~

Sau hai UPDATE:

~~~sql
SELECT ma_muc, vi_tri
FROM thu_tu_dt
ORDER BY ma_muc;
~~~

Kết quả:

| MA_MUC | VI_TRI |
| --- | --- |
| 1 | 2 |
| 2 | 1 |

Tình trạng trùng ở giữa giao dịch đã được giải quyết trước khi kiểm tra. Không cần xóa ràng buộc UNIQUE hoặc đặt một giá trị sentinel như -1 chỉ để vòng tránh một xung đột trung gian.

**Lưu ý:** Việc một **UPDATE duy nhất** hoán đổi hai hàng có cần deferral hay không phụ thuộc cơ chế kiểm tra ở cấp statement và cấu trúc DML. Bài tập này dùng **hai UPDATE riêng biệt** để minh họa rõ lợi ích của kiểm tra ở cuối transaction, thay vì kết luận mọi kiểu hoán đổi đều sẽ thất bại trong chế độ IMMEDIATE.

### 9.3. Cơ chế index của UNIQUE DEFERRABLE

Đối với UNIQUE hoặc PRIMARY KEY được khai báo DEFERRABLE, Oracle có thể sử dụng **index không unique** để hỗ trợ ràng buộc, bởi trong transaction đang hoãn có thể tạm xuất hiện các khóa trùng. Điều này khác việc đơn giản tạo một **UNIQUE index** cố định ngăn duplicate ngay ở mức index.

Khi thiết kế constraint, index và chuyển đổi thuộc tính DEFERRABLE, phải xem metadata cũng như kế hoạch triển khai. Không tự ý thay index hỗ trợ constraint hoặc giả định tất cả constraint UNIQUE đều có cùng dạng index.

## 10. INITIALLY DEFERRED: mặc định đợi tới cuối giao dịch

Trong các ví dụ trước, constraint **DEFERRABLE INITIALLY IMMEDIATE** cần SET CONSTRAINTS để được hoãn. Nếu mô hình nghiệp vụ thường xuyên xử lý dữ liệu chưa thỏa quan hệ ở giai đoạn đầu transaction, có thể chọn **INITIALLY DEFERRED** ngay khi tạo.

Ví dụ độc lập:

~~~sql
CREATE TABLE lo_hang_dd (
    ma_lo    NUMBER(6) CONSTRAINT pk_lo_dd PRIMARY KEY,
    ten_lo   VARCHAR2(100 CHAR) NOT NULL
);

CREATE TABLE mat_hang_dd (
    ma_mat_hang NUMBER(6) CONSTRAINT pk_mh_dd PRIMARY KEY,
    ma_lo       NUMBER(6) NOT NULL,
    ten_mat_hang VARCHAR2(100 CHAR) NOT NULL,

    CONSTRAINT fk_mh_lo_dd
        FOREIGN KEY (ma_lo)
        REFERENCES lo_hang_dd (ma_lo)
        DEFERRABLE INITIALLY DEFERRED
);
~~~

Vì khóa ngoại **FK_MH_LO_DD** mặc định hoãn kiểm tra, trong transaction này có thể chèn hàng con trước mà không cần gọi SET CONSTRAINTS:

~~~sql
INSERT INTO mat_hang_dd
    (ma_mat_hang, ma_lo, ten_mat_hang)
VALUES (501, 20, 'Mat hang A');

INSERT INTO lo_hang_dd
    (ma_lo, ten_lo)
VALUES (20, 'Lo 20');

COMMIT;
~~~

Dữ liệu cuối cùng hợp lệ nên commit được chấp nhận. Nhưng nếu quên tạo LO_HANG_DD(20), COMMIT sẽ thất bại.

### 10.1. Transaction tiếp theo bắt đầu theo trạng thái INITIALLY

Ví dụ một transaction muốn lỗi xuất hiện sớm:

~~~sql
SET CONSTRAINTS fk_mh_lo_dd IMMEDIATE;

-- Vi phạm sẽ bị chặn ở cuối câu INSERT, không đợi COMMIT.
INSERT INTO mat_hang_dd
    (ma_mat_hang, ma_lo, ten_mat_hang)
VALUES (502, 999, 'Mat hang khong co lo');
~~~

Lệnh INSERT này được dự kiến thất bại vì khóa ngoại đang ở IMMEDIATE trong transaction hiện tại. Có thể **ROLLBACK** để kết thúc bài thử.

Điều cần ghi nhớ: **INITIALLY** quy định chế độ **mặc định khi bắt đầu giao dịch**; không phải cam kết rằng constraint đó không bao giờ có thể chuyển chế độ.

## 11. SET CONSTRAINTS: phạm vi, cách đặt tên và giới hạn

Cú pháp ý tưởng:

~~~sql
SET CONSTRAINTS ALL DEFERRED;

SET CONSTRAINTS ALL IMMEDIATE;

SET CONSTRAINTS fk_nv_phong_dt DEFERRED;

SET CONSTRAINTS fk_nv_phong_dt IMMEDIATE;
~~~

Phạm vi của thay đổi là **transaction hiện tại**. Sau COMMIT hoặc ROLLBACK, transaction mới trở về trạng thái INITIALLY đã khai báo cho từng constraint.

### 11.1. ALL không biến NOT DEFERRABLE thành DEFERRABLE

**SET CONSTRAINTS ALL DEFERRED** chỉ có thể áp dụng chế độ hoãn cho những constraint có thể hoãn. Các ràng buộc **NOT DEFERRABLE** không được phép chuyển sang DEFERRED. Dùng ALL không có tác dụng “mở khóa mọi thứ” trong database.

Nếu chỉ muốn hoãn một khóa ngoại trong giao dịch, nên **nêu tên chính xác** thay vì ALL. Việc hoãn không cần thiết một UNIQUE hoặc FK khác có thể khiến lỗi phát hiện trễ hơn dự kiến và làm transaction khó chẩn đoán.

### 11.2. Không sử dụng SET CONSTRAINTS như một lệnh cấu hình vĩnh viễn

SET CONSTRAINTS không thay đổi cấu trúc trong data dictionary. Khác với:

~~~sql
CREATE TABLE ... (
    ...
    CONSTRAINT ten_fk FOREIGN KEY (...)
        REFERENCES ...
        DEFERRABLE INITIALLY DEFERRED
);
~~~

Lệnh DDL tạo constraint xác định thuộc tính schema, còn SET CONSTRAINTS chỉ ảnh hưởng cách kiểm tra trong transaction của một session. Trong môi trường connection pool, transaction kế tiếp không được phép dựa vào một giả định rằng lần request trước đã để chế độ DEFERRED mãi mãi.

### 11.3. DDL không nằm trong quy trình sửa vi phạm tạm thời

Các lệnh **CREATE TABLE**, **ALTER TABLE**, **DROP CONSTRAINT** là DDL và có quy tắc **implicit commit** trong Oracle. Nếu đang có transaction với dữ liệu tạm thời chưa thỏa deferred constraint, không dùng một lệnh ALTER TABLE giữa chừng để “thêm định nghĩa” rồi mới tiếp tục. DDL có thể kích hoạt ranh giới commit và làm transaction hiện tại thất bại hoặc gây những tác động ngoài kế hoạch.

Chuẩn bị schema/constraint **trước** khi bắt đầu transaction DML cần deferral.

## 12. Phân biệt DEFERRABLE với ENABLE, VALIDATE và DISABLE

Các thuộc tính này cùng xuất hiện trong metadata constraint nhưng trả lời các câu hỏi **khác nhau**:

| Thuộc tính/trạng thái | Trả lời câu hỏi | Điểm phân biệt |
| --- | --- | --- |
| **DEFERRABLE / NOT DEFERRABLE** | Có thể dời thời điểm kiểm tra trong transaction không? | Được khai báo khi tạo constraint |
| **INITIALLY DEFERRED / IMMEDIATE** | Transaction mới bắt đầu kiểm tra vào lúc nào? | Chỉ là chế độ mặc định |
| **SET CONSTRAINTS ... DEFERRED** | Transaction hiện tại đang yêu cầu hoãn gì? | Không sửa metadata định nghĩa |
| **ENABLE / DISABLE** | Constraint có đang được Oracle thực thi theo chế độ đã chọn không? | DISABLE không giống deferred |
| **VALIDATE / NOVALIDATE** | Dữ liệu hiện hữu đã được xác nhận theo trạng thái constraint chưa? | Không đồng nghĩa kiểm tra ở COMMIT |

**DEFERRED không phải DISABLED.** Deferred vẫn đòi dữ liệu hợp lệ trước COMMIT; disabled là trạng thái quản trị khác và có hệ quả về bảo vệ dữ liệu. Không tắt FK/UNIQUE trong ứng dụng chỉ để giải quyết một trạng thái trung gian có thể xử lý bằng deferral.

Tương tự, **NOVALIDATE** liên quan đến kiểm tra dữ liệu hiện có và chính sách thực thi tương ứng, không phải cách nói khác của INITIALLY DEFERRED.

Trong hoạt động migration/bulk load, cần phân biệt rõ các trạng thái để tránh vô tình để lại dữ liệu bất nhất.

## 13. Quan sát metadata qua USER_CONSTRAINTS

Sau khi tạo các bảng ví dụ, có thể kiểm tra constraint đã khai báo DEFERRABLE hay chưa:

~~~sql
SELECT table_name,
       constraint_name,
       constraint_type,
       deferrable,
       deferred,
       status,
       validated
FROM user_constraints
WHERE table_name IN (
    'PHONG_BAN_DT',
    'NHAN_VIEN_DT',
    'THU_TU_DT',
    'LO_HANG_DD',
    'MAT_HANG_DD'
)
ORDER BY table_name, constraint_name;
~~~

Những cột quan trọng:

- **CONSTRAINT_TYPE**: thường gặp **P** cho primary key, **U** cho unique, **R** cho foreign key, **C** cho check và các loại khác theo metadata của Oracle.
- **DEFERRABLE**: cho biết constraint có được khai báo khả năng hoãn hay không.
- **DEFERRED**: cho biết trạng thái **INITIALLY** của constraint, không phải một cách đáng tin cậy để hỏi “session này vừa gọi SET CONSTRAINTS DEFERRED hay chưa?”.
- **STATUS**: ENABLED hoặc DISABLED.
- **VALIDATED**: thông tin trạng thái xác thực dữ liệu của constraint.

Ví dụ FK_NV_PHONG_DT sẽ có thuộc tính **DEFERRABLE** và cấu hình ban đầu **IMMEDIATE**. FK_MH_LO_DD sẽ có cấu hình ban đầu **DEFERRED**. Lệnh SET CONSTRAINTS trong một transaction không đổi hai giá trị định nghĩa này.

### 13.1. Xem cột thuộc constraint

~~~sql
SELECT c.table_name,
       c.constraint_name,
       c.constraint_type,
       cc.column_name,
       cc.position
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
WHERE c.table_name IN ('NHAN_VIEN_DT', 'THU_TU_DT')
ORDER BY c.table_name, c.constraint_name, cc.position;
~~~

Câu truy vấn giúp xác định ràng buộc thuộc những cột nào, hữu ích khi một bảng có nhiều FK/UNIQUE hoặc tên constraint được sinh tự động.

### 13.2. Xem khóa ngoại trỏ tới khóa nào

~~~sql
SELECT fk.constraint_name AS fk_name,
       fk.table_name AS child_table,
       parent.constraint_name AS referenced_constraint,
       parent.table_name AS parent_table,
       fk.deferrable,
       fk.deferred
FROM user_constraints fk
JOIN user_constraints parent
  ON parent.constraint_name = fk.r_constraint_name
WHERE fk.constraint_type = 'R'
  AND fk.table_name IN ('NHAN_VIEN_DT', 'MAT_HANG_DD')
ORDER BY fk.table_name, fk.constraint_name;
~~~

**R_CONSTRAINT_NAME** là constraint khóa được tham chiếu ở phía cha. Trong cùng schema bài tập, nối như trên đủ để tìm parent. Khi phân tích nhiều schema thực tế, phải tính cả owner trong metadata **ALL_CONSTRAINTS** hoặc **DBA_CONSTRAINTS** để tránh ghép nhầm tên constraint giữa những schema khác nhau.

## 14. Java JDBC: quản lý một transaction có deferred constraint

Ứng dụng Java cần đặt **SET CONSTRAINTS và toàn bộ DML liên quan trên cùng một Connection và trong cùng transaction**. Đây là điểm thường bị bỏ sót khi dùng connection pool hoặc repository tự mở connection cho từng lời gọi.

Ví dụ dùng DataSource đã cấu hình Oracle JDBC, bảng ở phần 4 đã tồn tại và các giá trị ID chưa bị chiếm bởi dữ liệu trước đó:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import javax.sql.DataSource;

public final class ImportNhanVienService {
    private final DataSource dataSource;

    public ImportNhanVienService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void taoNhanVienVaPhongBan(long maNv, long maPhong)
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();
            connection.setAutoCommit(false);

            try {
                // Chỉ hoãn đúng FK cần thiết trong transaction này.
                try (Statement statement = connection.createStatement()) {
                    statement.execute(
                        "SET CONSTRAINTS fk_nv_phong_dt DEFERRED"
                    );
                }

                try (PreparedStatement insertNv =
                         connection.prepareStatement(
                           "INSERT INTO nhan_vien_dt " +
                           "(ma_nv, ma_phong, ho_ten) VALUES (?, ?, ?)")) {
                    insertNv.setLong(1, maNv);
                    insertNv.setLong(2, maPhong);
                    insertNv.setString(3, "Nhan vien tu Java");
                    insertNv.executeUpdate();
                }

                try (PreparedStatement insertPhong =
                         connection.prepareStatement(
                           "INSERT INTO phong_ban_dt " +
                           "(ma_phong, ten_phong) VALUES (?, ?)")) {
                    insertPhong.setLong(1, maPhong);
                    insertPhong.setString(2, "Phong tu Java");
                    insertPhong.executeUpdate();
                }

                // Phát hiện vấn đề trước khi gọi COMMIT nếu có.
                try (Statement statement = connection.createStatement()) {
                    statement.execute(
                        "SET CONSTRAINTS fk_nv_phong_dt IMMEDIATE"
                    );
                }

                connection.commit();
            } catch (SQLException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                connection.setAutoCommit(originalAutoCommit);
            }
        }
    }
}
~~~

Đây là ví dụ để thể hiện ranh giới transaction:

1. **getConnection()** lấy một kết nối từ DataSource.
2. **setAutoCommit(false)** bảo đảm hai câu INSERT không tự commit sau từng statement.
3. **SET CONSTRAINTS ... DEFERRED** áp dụng cho transaction trên kết nối đó.
4. Hai bảng được ghi trong cùng transaction, dù hàng con xuất hiện trước cha.
5. **SET CONSTRAINTS ... IMMEDIATE** xác minh trạng thái trước COMMIT.
6. **commit()** chỉ thực hiện khi các bước thành công.
7. Nếu thao tác gây SQLException, service thử **rollback**; exception từ rollback được giữ lại dưới dạng suppressed thay vì che lỗi gốc.

Trong hệ thống thật, nên quản lý thêm việc phục hồi khi lỗi khôi phục autocommit hoặc connection bị hỏng. Cần tránh retry một giao dịch ghi mà không có quy tắc chống trùng và kiểm soát trạng thái commit.

### 14.1. Vì sao autocommit đặc biệt quan trọng?

Nếu **autoCommit = true**, mỗi DML thành công được commit theo cơ chế JDBC. Một transaction không thể duy trì trạng thái con thiếu cha qua nhiều lệnh đã tự commit: khi INSERT con dẫn tới COMMIT, Oracle phải kiểm tra deferred FK và transaction sẽ thất bại.

Do đó, chỉ chạy **SET CONSTRAINTS DEFERRED** nhưng để từng repository tự mượn connection khác nhau hoặc dùng autocommit là không đủ. Cần một transaction thực sự bao trùm toàn bộ các bước.

### 14.2. Khi dùng Spring và @Transactional

Trong Spring, **@Transactional** có thể quản lý transaction cho một phương thức service gọi nhiều repository, miễn là các thao tác dữ liệu dùng đúng transaction manager/DataSource và tham gia cùng transaction.

Có thể đặt SET CONSTRAINTS bằng JDBC/JdbcTemplate trong phạm vi transaction được Spring sở hữu rồi thực hiện DML. Khi đó **không tự gọi Connection.commit() hoặc rollback()** trên connection mà Spring đang quản lý. Cần kiểm tra hành vi với nhiều DataSource, nested transaction, propagation hoặc lời gọi bất đồng bộ: những thao tác tách transaction có thể không chia sẻ chế độ deferred.

Ví dụ khái niệm:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ThemDonViService {
    private final JdbcTemplate jdbc;

    public ThemDonViService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void taoNhanVienVaPhongBan() {
        jdbc.execute("SET CONSTRAINTS fk_nv_phong_dt DEFERRED");

        jdbc.update(
            "INSERT INTO nhan_vien_dt " +
            "(ma_nv, ma_phong, ho_ten) VALUES (?, ?, ?)",
            301, 30, "Nhan vien Spring"
        );

        jdbc.update(
            "INSERT INTO phong_ban_dt (ma_phong, ten_phong) " +
            "VALUES (?, ?)",
            30, "Phong Spring"
        );

        jdbc.execute("SET CONSTRAINTS fk_nv_phong_dt IMMEDIATE");
        // Spring transaction manager commit khi phương thức thành công.
    }
}
~~~

Giả định dự án đã cấu hình Spring JDBC và transaction manager phù hợp, các ID chưa tồn tại và phương thức được gọi thông qua Spring proxy để @Transactional có hiệu lực. Nếu phương thức bị gọi theo cách bỏ qua proxy hoặc sử dụng nhiều DataSource không nằm chung transaction, hành vi có thể khác.

**Lỗi deferred constraint tại bước commit do Spring thực hiện** có thể xuất hiện ngoài thời điểm dòng Java cuối trong service kết thúc, ví dụ ở tầng proxy/transaction manager. Cần thiết kế xử lý lỗi ở ranh giới transaction, không chỉ bắt lỗi của từng lệnh jdbc.update.

## 15. Tính đúng đắn, hiệu năng và vận hành

### 15.1. Đừng trì hoãn kiểm tra khi không cần

Một ràng buộc immediate thông báo lỗi sớm ở statement vi phạm. Với deferred constraint, lỗi có thể chỉ xuất hiện sau nhiều câu SQL, khi transaction đã sử dụng thêm CPU, I/O, undo/redo, giữ khóa và tài nguyên lâu hơn.

Vì thế:

- Chỉ đánh dấu DEFERRABLE cho những constraint có tình huống nghiệp vụ cần thiết.
- Nếu chỉ một thao tác import/hoán đổi cần deferred, dùng **DEFERRABLE INITIALLY IMMEDIATE** và bật DEFERRED cục bộ.
- Khi việc tổ chức dữ liệu đã hoàn thành, cân nhắc gọi **SET CONSTRAINTS ... IMMEDIATE** để kiểm tra sớm.
- Hạn chế transaction quá dài, vì vừa tăng chi phí vừa làm trạng thái lỗi khó giải thích.
- Không dùng deferral thay cho xác thực dữ liệu từ nguồn nhập hoặc thiết kế transaction rõ ràng.

### 15.2. Hoãn ràng buộc không thay thế khóa và isolation

Deferred FK/UNIQUE **không phải công cụ điều khiển thứ tự chạy giữa nhiều session**. Hai transaction đồng thời vẫn chịu cơ chế khóa, isolation và kiểm tra toàn vẹn của Oracle. Một COMMIT có thể phải đợi hoặc thất bại do dữ liệu/khóa của transaction khác.

Không suy luận rằng “constraint được hoãn” đồng nghĩa không có lock hoặc không xảy ra contention. Với workload nhiều giao dịch cạnh tranh trên cùng khóa, cần thử nghiệm đồng thời thay vì chỉ chạy tuần tự một session.

### 15.3. Không phải mọi ràng buộc khác đều được hoãn

Một constraint DEFERRABLE riêng lẻ ở DEFERRED không tự động hoãn **primary key, NOT NULL, các FK khác hoặc những ràng buộc NOT DEFERRABLE**. Ví dụ FK_NV_PHONG_DT có thể hoãn, nhưng MA_PHONG trong NHAN_VIEN_DT vẫn được khai báo **NOT NULL** và mã nhân viên phải không vi phạm PK.

Trong transaction import, không nên cho rằng chỉ cần SET CONSTRAINTS cho một khóa ngoại thì mọi dữ liệu sai cấu trúc đều được chấp nhận tới commit.

### 15.4. Chiến lược thay thế

Đôi khi có cách phù hợp hơn:

- **Sắp xếp dữ liệu đúng thứ tự cha → con** nếu không có vòng phụ thuộc.
- **Staging table** nhận dữ liệu thô, kiểm tra tính toàn vẹn rồi chuyển vào bảng chính theo transaction được thiết kế.
- **Cập nhật một statement** nếu có thể, thay vì nhiều UPDATE tạo trạng thái trung gian.
- **Tái thiết kế quan hệ vòng** hoặc cho phép một liên kết tạm NULL rồi cập nhật khi đủ dữ liệu, nếu phù hợp quy tắc nghiệp vụ.
- **Deferrable constraint** khi toàn vẹn cuối transaction là yêu cầu tự nhiên, không phải cách né lỗi do logic ứng dụng thiếu kiểm soát.

Không có một giải pháp áp dụng cho mọi giao dịch. Lựa chọn phải xét tính nguyên tử, thao tác đồng thời, lượng dữ liệu và nhu cầu kiểm tra sớm.

## 16. Chẩn đoán lỗi với constraint DEFERRED

Khi gặp lỗi ở COMMIT, hãy bắt đầu từ mã constraint thay vì thử đổi toàn bộ constraint sang DISABLE.

**Bước 1 — Ghi nhận mã lỗi và constraint name.** ORA-02291 thường gợi ý thiếu bản ghi cha; ORA-02292 thường liên quan xóa cha khi còn con; ORA-00001 là vi phạm duy nhất. Ở commit có thể kèm ORA-02091.

**Bước 2 — Xem định nghĩa constraint.**

~~~sql
SELECT constraint_name,
       table_name,
       constraint_type,
       deferrable,
       deferred,
       status,
       validated
FROM user_constraints
WHERE constraint_name = 'FK_NV_PHONG_DT';
~~~

**Bước 3 — Kiểm tra dữ liệu transaction.** Nếu còn trước commit hoặc ở một bài thử tái hiện, so sánh mã tham chiếu ở child với khóa parent. Khi COMMIT đã rollback giao dịch vì lỗi deferred constraint, các hàng chưa commit có thể không còn để xem; cần dựa vào log ứng dụng, tập dữ liệu đầu vào hoặc tái hiện có kiểm soát.

**Bước 4 — Kiểm tra ranh giới transaction.** Có chắc SET CONSTRAINTS, child INSERT và parent INSERT cùng một connection và không có autocommit hoặc DDL giữa chừng?

**Bước 5 — Đối chiếu kiểu dữ liệu và khóa.** FK có thể tham chiếu khóa duy nhất/khóa chính; không phải lúc nào tên cột giống nhau. Đọc USER_CONS_COLUMNS và R_CONSTRAINT_NAME để xác định chính xác cột liên quan.

**Bước 6 — Kiểm tra sớm trước khi commit.** Trong bài thử, có thể gọi SET CONSTRAINTS ... IMMEDIATE để cô lập lỗi sau một nhóm statement. Không nên dùng kỹ thuật này tùy tiện giữa các bước khi transaction đang cố ý ở trạng thái chưa đầy đủ.

**Bước 7 — Sửa nguồn vấn đề.** Thiếu parent thì tạo parent đúng hoặc loại bỏ child không hợp lệ; trùng UNIQUE thì bảo đảm kết quả cuối cùng thực sự duy nhất; lỗi khóa/transaction thì xử lý theo quy trình tương ứng. Không xóa constraint vì một giao dịch sai thứ tự.

### 16.1. Những mã lỗi thường gặp

| Mã lỗi | Tình huống điển hình | Khi nào xuất hiện? |
| --- | --- | --- |
| **ORA-02291** | FK trỏ đến parent không tồn tại | Ở statement immediate hoặc khi kiểm tra FK deferred |
| **ORA-02292** | Xóa/sửa parent bị FK con tham chiếu | Ở statement immediate hoặc khi kiểm tra FK deferred |
| **ORA-00001** | Trùng khóa PRIMARY KEY/UNIQUE | Ở statement immediate hoặc khi kiểm tra constraint deferred |
| **ORA-02091** | Transaction bị rollback, ví dụ do vi phạm deferred constraint khi commit | Khi giao dịch không thể hoàn tất |
| **ORA-02447** hoặc lỗi tương đương theo ngữ cảnh | Yêu cầu thay đổi trạng thái constraint không phù hợp | Khi thao tác SET CONSTRAINTS/định nghĩa không hợp lệ, tùy phiên bản và câu lệnh |

Không cần ghi nhớ mọi mã lỗi để hiểu bài học. Quan trọng hơn là biết phân biệt **statement bị từ chối**, **kiểm tra IMMEDIATE thất bại** và **COMMIT không thành công**.

## 17. Quy trình thực hành tổng hợp

Để thấy rõ mối quan hệ giữa hai cách kiểm tra:

1. Tạo bảng PHONG_BAN_DT và NHAN_VIEN_DT với FK_NV_PHONG_DT **DEFERRABLE INITIALLY IMMEDIATE**.
2. Chèn child tham chiếu parent không tồn tại mà không gọi SET CONSTRAINTS. Quan sát lỗi ngay ở INSERT.
3. Bắt đầu giao dịch mới, gọi **SET CONSTRAINTS fk_nv_phong_dt DEFERRED**.
4. Chèn child trước, rồi chèn parent đúng; gọi **SET CONSTRAINTS fk_nv_phong_dt IMMEDIATE** và COMMIT. Quan sát giao dịch thành công.
5. Bắt đầu giao dịch khác, chèn child nhưng không tạo parent; thử chuyển constraint sang IMMEDIATE và quan sát lỗi.
6. ROLLBACK rồi làm lại tình huống thiếu parent, lần này đi thẳng tới COMMIT; quan sát lỗi và transaction rollback.
7. Tạo THU_TU_DT, thử hoán đổi hai giá trị duy nhất bằng hai UPDATE trong một transaction deferred.
8. Tạo LO_HANG_DD/MAT_HANG_DD để quan sát **INITIALLY DEFERRED** hoạt động mà không cần SET CONSTRAINTS trước.
9. Dùng USER_CONSTRAINTS và USER_CONS_COLUMNS để đối chiếu định nghĩa với hành vi.
10. Thử một ví dụ Java JDBC hoặc Spring để kiểm soát transaction và lỗi commit.

Nếu muốn dọn schema thực hành, chỉ xóa những bảng sandbox do bài học tạo, theo thứ tự con trước cha:

~~~sql
DROP TABLE nhan_vien_dt PURGE;
DROP TABLE phong_ban_dt PURGE;
DROP TABLE thu_tu_dt PURGE;
DROP TABLE mat_hang_dd PURGE;
DROP TABLE lo_hang_dd PURGE;
~~~

**DROP TABLE là DDL**, có hiệu lực và quy tắc implicit commit; không chạy trong môi trường đang chứa dữ liệu cần giữ. PURGE tránh cơ chế recycle bin thông thường, nên chỉ sử dụng khi chắc chắn các đối tượng là dữ liệu thực hành được phép xóa vĩnh viễn.

## 18. Những nhầm lẫn thường gặp

**“DEFERRABLE nghĩa là luôn được kiểm tra tại COMMIT.”** Không đúng. DEFERRABLE chỉ cho biết có thể hoãn. Nếu INITIALLY IMMEDIATE và transaction không đổi sang DEFERRED, constraint vẫn được kiểm tra ngay.

**“INITIALLY DEFERRED nghĩa là không bao giờ kiểm tra ở giữa transaction.”** Không đúng. Có thể dùng SET CONSTRAINTS ... IMMEDIATE để yêu cầu kiểm tra sớm.

**“SET CONSTRAINTS ALL DEFERRED vô hiệu hóa mọi constraint.”** Không đúng. Nó không biến NOT DEFERRABLE thành DEFERRED và không tắt ràng buộc.

**“DEFERRED giống DISABLE CONSTRAINT.”** Không đúng. Deferred phải thỏa tính toàn vẹn trước khi COMMIT; disabled là một trạng thái quản trị khác.

**“Một INSERT thành công thì giao dịch chắc chắn commit được.”** Không đúng. Nếu đang hoãn constraint, một hoặc nhiều statement có thể thành công nhưng COMMIT vẫn thất bại.

**“COMMIT lỗi vì deferred FK vẫn giữ lại các hàng INSERT trước đó.”** Không đúng trong tình huống deferred constraint vi phạm tại COMMIT: transaction bị rollback.

**“Có thể đổi NOT DEFERRABLE thành DEFERRABLE chỉ bằng SET CONSTRAINTS.”** Không đúng. SET CONSTRAINTS chỉ đổi chế độ kiểm tra của những constraint đã hỗ trợ deferral.

**“Một ứng dụng dùng connection pool có thể SET CONSTRAINTS trên connection A và INSERT trên connection B.”** Không đúng về ranh giới giao dịch. Các statement phải tham gia cùng transaction phù hợp.

**“INITIALLY DEFERRED giúp ứng dụng không cần transaction.”** Không đúng. Chính ranh giới transaction quyết định lúc constraint được kiểm tra; autocommit có thể khiến commit diễn ra ngay sau từng câu lệnh.

**“Mọi giá trị tạm không hợp lệ đều vô hại.”** Không đúng. Trigger, các câu SQL khác trong transaction và logic ứng dụng vẫn cần hiểu rằng trạng thái trung gian có thể khác trạng thái cuối.

**“Chỉ cần đọc USER_CONSTRAINTS.DEFERRED là biết transaction hiện tại đã gọi SET CONSTRAINTS thế nào.”** Không đúng. Cột metadata này mô tả chế độ INITIALLY của constraint, không theo dõi mỗi lệnh đổi trạng thái trong một transaction đang chạy.

## 19. Câu hỏi tự luyện

1. Phân biệt **DEFERRABLE**, **DEFERRED**, **INITIALLY IMMEDIATE** và **INITIALLY DEFERRED** theo thuộc tính schema và trạng thái transaction.
2. Trong ví dụ nhân viên/phòng ban, vì sao INSERT nhân viên trước phòng ban thất bại ở chế độ IMMEDIATE nhưng có thể thành công khi hoãn FK?
3. Nếu đã gọi SET CONSTRAINTS fk_nv_phong_dt DEFERRED, điều gì xảy ra khi COMMIT mà phòng ban tham chiếu vẫn chưa được tạo?
4. Trong trường hợp SET CONSTRAINTS ... IMMEDIATE phát hiện lỗi, tại sao không thể coi đây là một COMMIT thành công?
5. Vì sao thêm MA_PHONG NOT NULL vào bảng nhân viên vẫn là điều kiện cần dù foreign key được khai báo DEFERRABLE?
6. Một ứng dụng chỉ làm việc với một trường hợp cần tạm trùng UNIQUE mỗi ngày. Nên xem xét INITIALLY IMMEDIATE hay INITIALLY DEFERRED, và vì sao?
7. Tại sao đổi vị trí bằng hai UPDATE riêng biệt cần xem xét trạng thái kiểm tra UNIQUE tại các ranh giới statement?
8. Một client Java đang bật autocommit nhưng gọi SET CONSTRAINTS DEFERRED rồi thực hiện nhiều INSERT. Nguy cơ đối với transaction là gì?
9. Nếu Spring service có @Transactional nhưng repository lại tự tạo kết nối khác ngoài transaction manager, liệu SET CONSTRAINTS của service có chắc ảnh hưởng các câu INSERT hay không?
10. Trường DEFERRABLE và DEFERRED trong USER_CONSTRAINTS khác nhau thế nào? Vì sao metadata không đủ để suy ra chế độ đã SET trong một transaction hiện tại?
11. Vì sao không nên dùng ALTER TABLE DROP CONSTRAINT giữa một giao dịch cần tạm hoãn FK?
12. Với một batch import lớn, so sánh ba phương án: sắp dữ liệu cha trước con, import qua staging table, và dùng deferrable FK.
13. Nếu UNIQUE được hoãn nhưng vẫn còn hai hàng có cùng giá trị tại COMMIT, Oracle có cho phép giao dịch lưu một phần hàng hợp lệ không?
14. Một quan hệ FK vòng giữa PHONG_BAN và NHAN_VIEN có thể dùng DEFERRABLE như thế nào? Khi nào nên xem lại thiết kế quan hệ?
15. Khi lỗi xuất hiện tại commit từ JDBC, vì sao service nên báo thất bại và tránh tự động retry không có khóa chống trùng?

**DEFERRABLE là khả năng hoãn kiểm tra, DEFERRED là chế độ đang được sử dụng trong một transaction.** Oracle cho phép một số vi phạm ràng buộc tồn tại tạm thời để hoàn thành thao tác nhiều bước, nhưng **COMMIT chỉ có thể thành công nếu tất cả ràng buộc còn hiệu lực đã được thỏa**. Hiểu rõ INITIALLY IMMEDIATE/DEFERRED, SET CONSTRAINTS, điểm kiểm tra ở cuối statement so với cuối transaction và ranh giới JDBC/Spring giúp dùng cơ chế này đúng mục đích mà không đánh đổi tính toàn vẹn của cơ sở dữ liệu.

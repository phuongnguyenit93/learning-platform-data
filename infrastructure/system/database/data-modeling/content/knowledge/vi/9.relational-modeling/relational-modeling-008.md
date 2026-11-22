# Chuyển cấu trúc kiểu cha, kiểu con sang các phương án bảng

## Mục tiêu học tập

Trong mô hình thực thể–liên kết mở rộng (**EER**), một đối tượng có thể thuộc **kiểu cha** (*supertype*) đồng thời thuộc một hoặc nhiều **kiểu con** (*subtype*). Kiểu con kế thừa những đặc điểm chung và bổ sung thuộc tính, quan hệ hoặc quy tắc riêng. Khi chuyển EER sang cơ sở dữ liệu quan hệ, cần lựa chọn cách tổ chức bảng sao cho **không làm mất định danh, thuộc tính chung hay ràng buộc nghiệp vụ**.

Bài thuộc chương **Mô hình quan hệ** của module **DATABASE_DATA_MODELING**. Mục tiêu chung của module là rèn kỹ năng chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, từ thực thể, quan hệ, ràng buộc đến chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; đồng thời so sánh các cách mô hình hóa quan hệ, document, đồ thị và dữ liệu phân tích để lựa chọn cấu trúc phù hợp, dễ tiến hóa và kiểm chứng.

Sau bài học, bạn có thể:

1. Phân biệt **kiểu cha–kiểu con**, **chuyên biệt hóa**, **tổng quát hóa** và ý nghĩa của kế thừa trong EER.
2. Phân tích các ràng buộc **loại trừ/chồng lấn** (*disjoint/overlapping*) và **toàn phần/bộ phận** (*total/partial*).
3. Chuyển cùng một cấu trúc cha–con sang ba phương án chính: **một bảng cho cả cây**, **một bảng cha và các bảng con**, hoặc **một bảng cho mỗi kiểu con cụ thể**.
4. Thiết kế **khóa chính**, **khóa ngoại**, **UNIQUE**, **NOT NULL**, **CHECK** và cơ chế kiểm tra bổ sung tương ứng với từng phương án.
5. So sánh cách truy vấn, chi phí JOIN/UNION, tính thưa của cột, mở rộng kiểu con, vòng đời và mức độ toàn vẹn của ba phương án.
6. Đề xuất và kiểm chứng thiết kế bằng ví dụ SQL PostgreSQL cùng các phản ví dụ nghiệp vụ.

## 1. Kiểu cha, kiểu con và kế thừa định danh

Giả sử một hệ thống quản lý **PHƯƠNG_TIỆN** có hai loại:

- **Ô_TÔ:** có số chỗ ngồi.
- **XE_MÁY:** có dung tích xi lanh.

Mọi phương tiện đều có **mã định danh**, **biển số** và **hãng xe**. Các thuộc tính chung đặt ở kiểu cha PHUONG_TIEN; các thuộc tính riêng đặt ở kiểu con O_TO và XE_MAY.

~~~~text
                         PHUONG_TIEN
                id, bien_so, hang_xe
                        /      \
                       /        \
                    O_TO       XE_MAY
                  so_cho     dung_tich_cc
~~~~

### 1.1. Kế thừa trong EER không phải kế thừa lớp lập trình

Trong EER, **O_TO là một tập con của PHUONG_TIEN**: mỗi ô tô cũng chính là một phương tiện, có **cùng định danh** với thể hiện kiểu cha. Không được hiểu rằng ô tô là một bản sao độc lập của phương tiện.

\[
O\_TO \subseteq PHUONG\_TIEN,\qquad
XE\_MAY \subseteq PHUONG\_TIEN
\]

Nếu phương tiện có id **101** và thuộc kiểu con O_TO, các thuộc tính riêng **so_cho** là thông tin về **chính phương tiện 101**, không phải một phương tiện khác.

**Chuyên biệt hóa** (*specialization*) bắt đầu từ một kiểu cha và phân thành các kiểu con theo sự khác biệt. **Tổng quát hóa** (*generalization*) đi từ các kiểu cụ thể nhận ra những thuộc tính/quy tắc chung để tạo kiểu cha. Hai hướng suy nghĩ có thể dẫn đến cùng một cấu trúc EER.

Sơ đồ sau biểu diễn ý nghĩa kế thừa ở mức khái niệm. Không nên hiểu đây là cú pháp tạo bảng SQL.

~~~~mermaid
classDiagram
    class PHUONG_TIEN {
      +id: bigint
      +bien_so: string
      +hang_xe: string
    }
    class O_TO {
      +so_cho: integer
    }
    class XE_MAY {
      +dung_tich_cc: integer
    }
    PHUONG_TIEN <|-- O_TO
    PHUONG_TIEN <|-- XE_MAY
~~~~

### 1.2. Những quy tắc nghiệp vụ của ví dụ

Để có thể so sánh các phương án ánh xạ, ta **cố định cùng một bộ quy tắc**:

1. Mỗi phương tiện có một **id duy nhất**, biển số bắt buộc và không trùng **trên toàn bộ hệ thống**.
2. Phương tiện đang được quản lý phải là **ô tô hoặc xe máy**, không có loại thứ ba.
3. Một phương tiện **không thể đồng thời vừa là ô tô vừa là xe máy**.
4. Ô tô có **so_cho** là số nguyên từ 2 đến 60; không có thuộc tính dung_tich_cc trong đặc tả ô tô của ví dụ.
5. Xe máy có **dung_tich_cc** là số nguyên từ 50 đến 2000; không có thuộc tính so_cho theo đặc tả đang xét.
6. Những thuộc tính chung **id**, **bien_so**, **hang_xe** có cùng ý nghĩa ở cả hai kiểu con.

Giới hạn 2–60 và 50–2000 là **giả định thực hành**, không phải kết luận rằng mọi loại xe ngoài đời phải thỏa các khoảng này. Nếu doanh nghiệp quản lý xe điện, xe chuyên dụng hoặc ô tô ít/nhiều chỗ hơn, phải cập nhật yêu cầu và kiểm tra thay vì giữ các giới hạn giả định.

## 2. Ràng buộc EER cần giữ nguyên khi ánh xạ

### 2.1. Loại trừ (*disjoint*) và chồng lấn (*overlapping*)

- **Disjoint (loại trừ):** Một thể hiện kiểu cha được phép thuộc **tối đa một** kiểu con trong nhóm chuyên biệt hóa đang xét.
- **Overlapping (chồng lấn):** Một thể hiện kiểu cha **có thể thuộc nhiều** kiểu con cùng nhóm.

Ví dụ **PHUONG_TIEN → O_TO/XE_MAY** ở trên là **disjoint**: một id không được xuất hiện đồng thời ở hai kiểu con.

Ngược lại, mô hình **NGUOI → NHAN_VIEN/KHACH_HANG** có thể là **overlapping**: một người vừa là nhân viên vừa là khách hàng. Nếu dùng bảng riêng cho từng kiểu con, cùng id người có thể xuất hiện ở cả hai bảng; đây là **dữ liệu hợp lệ**, không phải trùng sai.

### 2.2. Toàn phần (*total*) và bộ phận (*partial*)

- **Total (toàn phần):** Mọi thể hiện kiểu cha phải thuộc **ít nhất một** kiểu con trong nhóm.
- **Partial (bộ phận):** Một số thể hiện kiểu cha có thể **chưa thuộc kiểu con nào**.

Ví dụ hệ thống chỉ quản lý ô tô và xe máy đặt ràng buộc **total**: không có phương tiện “chưa phân loại”. Nhưng một hệ thống đăng ký tài sản có thể lưu tài sản trước, rồi mới phân loại; lúc đó chuyên biệt hóa có thể là **partial**.

### 2.3. Bốn tổ hợp ràng buộc

| Nhóm chuyên biệt hóa | Số kiểu con mà một thể hiện cha được phép thuộc | Tình huống |
| --- | --- | --- |
| **Disjoint + total** | Đúng **1** | Phương tiện phải là đúng một loại trong tập O_TO/XE_MAY |
| **Disjoint + partial** | **0 hoặc 1** | Phương tiện có thể chờ phân loại |
| **Overlapping + total** | **Ít nhất 1**, có thể nhiều | Người tham gia tổ chức phải là nhân viên hoặc khách hoặc cả hai |
| **Overlapping + partial** | **0, 1 hoặc nhiều** | Người được lưu trước khi phát sinh vai trò |

Hai trục **disjoint/overlapping** và **total/partial** là **độc lập**. Có một cột discriminator chỉ nhận O_TO/XE_MAY thường dễ thể hiện disjoint, nhưng không tự động giải quyết mọi trường hợp overlapping hoặc các kiểu con có thể bổ sung trong tương lai.

### 2.4. Giữ nguyên đối tượng và khóa

Ba chiến lược ánh xạ dưới đây phải giữ được ba bất biến:

1. **Không tách một phương tiện thành nhiều định danh độc lập** chỉ vì nó có phần dữ liệu riêng.
2. **Không để mất kiểm tra tính duy nhất** của biển số trên toàn bộ hệ thống.
3. **Không để trái quy tắc subtype** (ô tô thiếu số chỗ, xe máy mang thuộc tính chỉ dành cho ô tô, hoặc phương tiện thuộc sai tập loại).

Việc có thể lưu dữ liệu bằng SQL không đồng nghĩa rằng mọi bất biến đã được DDL bảo vệ. Cần liệt kê rõ **ràng buộc nào do DBMS kiểm tra trực tiếp**, **ràng buộc nào đòi hỏi trigger/giao dịch/quy trình**, và **ràng buộc nào chưa được mô hình thực thi**.

## 3. Phương án A: một bảng cho cả kiểu cha lẫn mọi kiểu con

Phương án này thường được gọi là **single-table inheritance**, **table-per-hierarchy** hoặc **một bảng cho toàn bộ phân cấp**.

### 3.1. Cấu trúc

Tạo một bảng PHUONG_TIEN gồm:

- Các cột chung: id, bien_so, hang_xe.
- Một **cột phân loại** (*discriminator*) như loai.
- Các cột riêng của mọi kiểu con: so_cho, dung_tich_cc.

~~~~text
PHUONG_TIEN_ST(
  id PK,
  bien_so UNIQUE NOT NULL,
  hang_xe NOT NULL,
  loai NOT NULL,
  so_cho,
  dung_tich_cc
)
~~~~

Vì cùng một hàng chỉ thuộc một kiểu con trong ví dụ **disjoint**, một số cột riêng sẽ là NULL **theo thiết kế**. Không nên hiểu mọi giá trị NULL đó đều là dữ liệu nhập thiếu: với xe máy, so_cho thực sự **không áp dụng** trong mô hình này.

### 3.2. PostgreSQL: CHECK bảo vệ cặp loại–thuộc tính

~~~~sql
CREATE TABLE phuong_tien_st (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bien_so VARCHAR(20) NOT NULL UNIQUE,
    hang_xe VARCHAR(100) NOT NULL,
    loai VARCHAR(10) NOT NULL,
    so_cho SMALLINT,
    dung_tich_cc INTEGER,
    CONSTRAINT ck_pt_st_loai CHECK (loai IN ('OTO', 'XEMAY')),
    CONSTRAINT ck_pt_st_chi_tiet CHECK (
        (
            loai = 'OTO'
            AND so_cho IS NOT NULL
            AND so_cho BETWEEN 2 AND 60
            AND dung_tich_cc IS NULL
        )
        OR
        (
            loai = 'XEMAY'
            AND dung_tich_cc IS NOT NULL
            AND dung_tich_cc BETWEEN 50 AND 2000
            AND so_cho IS NULL
        )
    )
);

INSERT INTO phuong_tien_st
    (bien_so, hang_xe, loai, so_cho, dung_tich_cc)
VALUES
    ('OTO-MAU-01', 'Toyota', 'OTO', 5, NULL),
    ('XM-MAU-01', 'Honda', 'XEMAY', NULL, 125);

SELECT id, bien_so, hang_xe, so_cho
FROM phuong_tien_st
WHERE loai = 'OTO'
ORDER BY id;
~~~~

Biển số trong ví dụ là **chuỗi giả lập**, không phải dữ liệu biển số thật. Hai bản ghi hợp lệ vì mỗi loại có đúng thuộc tính riêng theo ràng buộc.

**Vì sao CHECK phải có IS NOT NULL?** Trong SQL, điều kiện có NULL có thể cho kết quả **UNKNOWN**; CHECK thông thường không từ chối UNKNOWN. Nếu chỉ viết điều kiện so_cho BETWEEN 2 AND 60, dòng ô tô có so_cho NULL có thể lọt qua kiểm tra. Bổ sung **so_cho IS NOT NULL** và **dung_tich_cc IS NOT NULL** ở nhánh tương ứng bảo vệ rõ tính bắt buộc.

### 3.3. Điều gì được thực thi?

| Ràng buộc nghiệp vụ | Cơ chế trong bảng đơn |
| --- | --- |
| Một hàng là một phương tiện | PK(id) |
| Biển số duy nhất trên cả hai loại | UNIQUE(bien_so) ở cùng bảng |
| Phải thuộc một trong hai loại | loai NOT NULL + CHECK tập giá trị |
| Không đồng thời thuộc hai loại | Một discriminator với các nhánh CHECK loại trừ |
| Ô tô có số chỗ hợp lệ | CHECK với so_cho IS NOT NULL và giới hạn |
| Xe máy có dung tích hợp lệ | CHECK với dung_tich_cc IS NOT NULL và giới hạn |
| Không mang cột riêng không áp dụng | CHECK bắt cột của loại còn lại IS NULL |

Đối với cấu trúc **disjoint + total**, phương án A có thể biểu diễn các điều kiện chính ngay bằng **ràng buộc trên một hàng**. Không cần JOIN để lấy dữ liệu chung cùng thuộc tính riêng của một xe.

### 3.4. Ưu điểm, nhược điểm

**Ưu điểm:**

- Truy vấn toàn bộ phương tiện hoặc một kiểu con đơn giản; dữ liệu chung và riêng cùng ở một bảng.
- Một khóa chính, một nơi kiểm tra tính duy nhất toàn hệ thống.
- Ràng buộc loại trừ và toàn phần thường dễ viết bằng discriminator và CHECK khi tập kiểu con hữu hạn, loại trừ nhau.
- FK từ các bảng khác đến tất cả phương tiện chỉ cần trỏ vào PHUONG_TIEN_ST.id.

**Nhược điểm:**

- Số cột có thể phình to khi có nhiều kiểu con khác nhau; xuất hiện nhiều NULL “không áp dụng”.
- Phải duy trì CHECK phức tạp và sửa bảng khi thêm kiểu con hoặc thuộc tính riêng.
- Khó diễn đạt trường hợp **overlapping** bằng **chỉ một discriminator một giá trị**; cần đổi cơ chế phân loại hoặc dùng phương án khác.
- Quyền truy cập, quy tắc và vòng đời của các kiểu con có thể khác nhau, khó tách rạch ròi khi dùng một bảng.

**Không nên kết luận:** “Có NULL là vi phạm chuẩn hóa”. NULL cho thuộc tính không áp dụng **không tự chứng minh** lỗi chuẩn hóa; cần phân tích phụ thuộc hàm, ngữ nghĩa và truy vấn. Nhưng số cột thưa lớn vẫn là một tín hiệu cần cân nhắc thiết kế.

## 4. Phương án B: một bảng kiểu cha và một bảng cho mỗi kiểu con

Phương án này thường được gọi là **class-table inheritance**, **joined-table inheritance** hoặc **table-per-type** theo nghĩa **bảng cha + bảng con**.

### 4.1. Cấu trúc và khóa

~~~~text
PHUONG_TIEN_JT(id PK, bien_so UNIQUE, hang_xe, loai)
O_TO_JT(id PK, FK → PHUONG_TIEN_JT.id, so_cho)
XE_MAY_JT(id PK, FK → PHUONG_TIEN_JT.id, dung_tich_cc)
~~~~

**Cột id ở bảng con vừa là PK vừa là FK** đến bảng cha. Đây là **shared primary key 1:1**: một id phương tiện có tối đa một hàng O_TO_JT và tối đa một hàng XE_MAY_JT. Không tạo id mới ở bảng con để thay thế id của cha.

Khi đọc ô tô, JOIN O_TO_JT với PHUONG_TIEN_JT qua id để lấy đủ thông tin. Khi truy vấn tất cả phương tiện, có thể đọc riêng bảng cha nếu chỉ cần thông tin chung.

### 4.2. PostgreSQL: thực thi tính đúng loại khi tách bảng

Một FK đơn từ bảng con tới id của bảng cha **chỉ** bảo đảm bản ghi cha tồn tại. Nó chưa ngăn **cùng một id** xuất hiện ở cả O_TO_JT và XE_MAY_JT, và chưa bảo đảm loai trong cha khớp với loại bảng con.

Với ví dụ **disjoint**, ta có thể tăng độ chặt bằng **khóa ngoại ghép (id, loai)**. Mỗi bảng con có cột loai hằng số đúng loại; FK ghép trỏ đến cặp tương ứng trong bảng cha:

~~~~sql
CREATE TABLE phuong_tien_jt (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bien_so VARCHAR(20) NOT NULL UNIQUE,
    hang_xe VARCHAR(100) NOT NULL,
    loai VARCHAR(10) NOT NULL,
    CONSTRAINT ck_pt_jt_loai CHECK (loai IN ('OTO', 'XEMAY')),
    CONSTRAINT uq_pt_jt_id_loai UNIQUE (id, loai)
);

CREATE TABLE o_to_jt (
    id BIGINT PRIMARY KEY,
    loai VARCHAR(10) NOT NULL DEFAULT 'OTO',
    so_cho SMALLINT NOT NULL,
    CONSTRAINT ck_ot_jt_loai CHECK (loai = 'OTO'),
    CONSTRAINT ck_ot_jt_so_cho CHECK (so_cho BETWEEN 2 AND 60),
    CONSTRAINT fk_ot_jt_cha
        FOREIGN KEY (id, loai)
        REFERENCES phuong_tien_jt (id, loai)
        ON DELETE CASCADE
);

CREATE TABLE xe_may_jt (
    id BIGINT PRIMARY KEY,
    loai VARCHAR(10) NOT NULL DEFAULT 'XEMAY',
    dung_tich_cc INTEGER NOT NULL,
    CONSTRAINT ck_xm_jt_loai CHECK (loai = 'XEMAY'),
    CONSTRAINT ck_xm_jt_dung_tich
        CHECK (dung_tich_cc BETWEEN 50 AND 2000),
    CONSTRAINT fk_xm_jt_cha
        FOREIGN KEY (id, loai)
        REFERENCES phuong_tien_jt (id, loai)
        ON DELETE CASCADE
);
~~~~

Trong PostgreSQL, ràng buộc **UNIQUE(id, loai)** ở bảng cha cần thiết để cặp cột này là đích FK ghép hợp lệ, dù **id** đã là PK và do đó việc duy nhất của cặp có tính dư thừa logic. Đây là một đánh đổi vật lý để có **ràng buộc tham chiếu đúng loại**.

Với thiết kế trên:

- O_TO_JT không thể trỏ đến bản ghi cha có loai = XEMAY.
- XE_MAY_JT không thể trỏ đến bản ghi cha có loai = OTO.
- Một id cha chỉ có đúng một giá trị loai, nên không thể được lưu hợp lệ vào **cả hai** bảng con cùng lúc.
- Bảng con không thể tồn tại khi không có cha, vì PK đồng thời nằm trong FK ghép.

Nhưng **một hàng PHUONG_TIEN_JT chưa có hàng ở bảng con vẫn được phép tồn tại**. Đây là điểm quan trọng: cách kiểm tra trên **chưa bảo đảm ràng buộc total**.

### 4.3. Chèn dữ liệu trong một luồng thống nhất

Có thể chèn cha rồi con trong cùng một câu lệnh PostgreSQL bằng CTE ghi dữ liệu và **RETURNING**:

~~~~sql
WITH moi_cha AS (
    INSERT INTO phuong_tien_jt (bien_so, hang_xe, loai)
    VALUES ('OTO-JT-01', 'Toyota', 'OTO')
    RETURNING id
)
INSERT INTO o_to_jt (id, so_cho)
SELECT id, 5
FROM moi_cha;

WITH moi_cha AS (
    INSERT INTO phuong_tien_jt (bien_so, hang_xe, loai)
    VALUES ('XM-JT-01', 'Honda', 'XEMAY')
    RETURNING id
)
INSERT INTO xe_may_jt (id, dung_tich_cc)
SELECT id, 125
FROM moi_cha;
~~~~

Phương tiện cha và dòng con được tạo trong một lệnh, tránh phải đoán giá trị id sinh ra. Truy vấn đủ thuộc tính của mỗi loại:

~~~~sql
SELECT
    pt.id,
    pt.bien_so,
    pt.hang_xe,
    pt.loai,
    ot.so_cho,
    xm.dung_tich_cc
FROM phuong_tien_jt AS pt
LEFT JOIN o_to_jt AS ot ON ot.id = pt.id
LEFT JOIN xe_may_jt AS xm ON xm.id = pt.id
ORDER BY pt.id;
~~~~

| bien_so | hang_xe | loai | so_cho | dung_tich_cc |
| --- | --- | --- | ---: | ---: |
| OTO-JT-01 | Toyota | OTO | 5 | NULL |
| XM-JT-01 | Honda | XEMAY | NULL | 125 |

Trong kết quả JOIN, NULL ở phía không khớp nghĩa là **không có dòng kiểu con đó**, không phải bằng chứng có hàng dữ liệu sai. Với thiết kế disjoint, mỗi id chỉ được có một loại; trong thiết kế overlapping, nhiều bảng con có thể đồng thời có dòng.

### 4.4. Khoảng trống của quy tắc toàn phần

Lệnh sau **vẫn hợp lệ** với DDL ở mục 4.2:

~~~~sql
INSERT INTO phuong_tien_jt (bien_so, hang_xe, loai)
VALUES ('OTO-JT-CHUA-CO-CON', 'Toyota', 'OTO');
~~~~

Bây giờ bản ghi cha khai báo là OTO nhưng không có hàng tương ứng ở O_TO_JT. Các FK chỉ bảo đảm chiều **con → cha**, không tự bảo đảm **cha → phải có con**.

Truy vấn phát hiện những dòng chưa có kiểu con:

~~~~sql
SELECT pt.id, pt.bien_so, pt.loai
FROM phuong_tien_jt AS pt
WHERE
    (
        pt.loai = 'OTO'
        AND NOT EXISTS (
            SELECT 1 FROM o_to_jt AS ot
            WHERE ot.id = pt.id
        )
    )
    OR
    (
        pt.loai = 'XEMAY'
        AND NOT EXISTS (
            SELECT 1 FROM xe_may_jt AS xm
            WHERE xm.id = pt.id
        )
    )
ORDER BY pt.id;
~~~~

Nếu **partial** là ý nghĩa nghiệp vụ, việc tồn tại cha chưa có dòng con có thể hợp lệ. Nhưng nếu mô hình là **total**, cần cơ chế bổ sung:

- **Tạo cha và con như một đơn vị giao dịch**; kiểm soát đường ghi dữ liệu để không thể chèn cha rồi bỏ con.
- Nếu phải bảo đảm ở **cấp cơ sở dữ liệu** trong mọi đường ghi, xem xét **constraint trigger trì hoãn đến cuối giao dịch** hoặc quy trình DB kiểm tra đúng thời điểm, có thiết kế đồng thời phù hợp.
- Định nghĩa rõ lúc nào một bản ghi chuyển từ “nháp” sang “được quản lý đầy đủ”; nếu cho phép trạng thái nháp, đặc tả EER ở giai đoạn đó có thể là **partial** thay vì total.

Chỉ có **CHECK** trong bảng cha không thể trực tiếp truy vấn bảng con trong PostgreSQL để xác nhận ít nhất một dòng con; không nên viết CHECK với truy vấn con rồi coi là ràng buộc hợp lệ. Một câu SELECT kiểm tra sau khi ghi là phép **phát hiện**, không tự nó ngăn dữ liệu sai giữa các giao dịch.

### 4.5. Hệ thống overlapping: một người có nhiều vai trò

Trường hợp cùng một người có thể là **nhân viên** và **khách hàng** phù hợp với phương án bảng cha + bảng con:

~~~~sql
CREATE TABLE nguoi_ov (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL
);

CREATE TABLE nhan_vien_ov (
    nguoi_id BIGINT PRIMARY KEY
        REFERENCES nguoi_ov(id) ON DELETE CASCADE,
    ma_nhan_vien VARCHAR(20) NOT NULL UNIQUE
);

CREATE TABLE khach_hang_ov (
    nguoi_id BIGINT PRIMARY KEY
        REFERENCES nguoi_ov(id) ON DELETE CASCADE,
    ma_khach VARCHAR(20) NOT NULL UNIQUE
);

WITH n AS (
    INSERT INTO nguoi_ov (ho_ten)
    VALUES ('Nguyễn An')
    RETURNING id
)
SELECT id FROM n;
~~~~

Sau khi có id của người, có thể dùng **cùng id đó** để tạo một dòng ở NHAN_VIEN_OV và một dòng ở KHACH_HANG_OV. Điều này biểu diễn **một người có hai vai trò**, không tạo hai người độc lập.

**Lưu ý về đoạn SQL:** Câu cuối chỉ tạo người và trả về id; nó không tự tạo bản ghi vai trò. Trạng thái người chưa có vai trò hợp lệ với **overlapping + partial**. Nếu nghiệp vụ yêu cầu mỗi người phải có ít nhất một vai trò (**overlapping + total**), vẫn phải có cơ chế kiểm tra thêm.

Không dùng một discriminator chỉ được chọn một giá trị để cấm người có nhiều vai trò. Trong mô hình overlapping, sự hiện diện đồng thời ở nhiều bảng con **là hợp lệ** và không cần ràng buộc loại trừ.

### 4.6. Ưu điểm, nhược điểm

**Ưu điểm:**

- Tách rõ thuộc tính chung và thuộc tính riêng; mỗi bảng con có **NOT NULL** và **CHECK** độc lập cho thuộc tính của nó.
- Có một bảng cha để định danh thống nhất, giữ **UNIQUE(bien_so)** toàn bộ tập phương tiện và làm đích FK từ các bảng liên quan.
- Phù hợp khi kiểu con có nhiều thuộc tính đặc thù, quan hệ đặc thù hoặc cần phân quyền khác nhau.
- Thường tự nhiên cho **overlapping**, vì cùng id cha có thể xuất hiện ở nhiều bảng con mà không phải nhân bản các thuộc tính chung.

**Nhược điểm:**

- Truy vấn đầy đủ thuộc tính thường phải JOIN; truy vấn đa hình nhiều kiểu có thể cần nhiều LEFT JOIN hoặc UNION.
- Thêm/sửa/xóa một đối tượng có thể đụng tới nhiều bảng; cần giao dịch.
- **Tính toàn phần ở phía cha không tự được FK bảo đảm**; tính loại trừ giữa các bảng con cũng không tự bảo đảm nếu chỉ dùng FK đơn tới id mà không có thiết kế bổ sung.
- PK và các FK liên quan cần được quản lý cẩn thận để không tạo dòng con mồ côi hoặc sai loại.

## 5. Phương án C: chỉ tạo bảng cho các kiểu con cụ thể

Phương án này thường được gọi là **table-per-concrete-class**, **concrete-table inheritance** hoặc **bảng riêng cho mỗi kiểu con cụ thể**. Không có một bảng PHUONG_TIEN chung; mỗi bảng O_TO và XE_MAY tự chứa **cả thuộc tính chung lẫn thuộc tính riêng**.

### 5.1. Cấu trúc

~~~~text
O_TO_CT(
  id PK, bien_so UNIQUE, hang_xe, so_cho
)

XE_MAY_CT(
  id PK, bien_so UNIQUE, hang_xe, dung_tich_cc
)
~~~~

Khi thêm ô tô, chỉ INSERT một bảng O_TO_CT. Khi thêm xe máy, chỉ INSERT XE_MAY_CT. Không có thao tác tạo hai hàng cha–con.

### 5.2. PostgreSQL

~~~~sql
CREATE TABLE o_to_ct (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bien_so VARCHAR(20) NOT NULL UNIQUE,
    hang_xe VARCHAR(100) NOT NULL,
    so_cho SMALLINT NOT NULL CHECK (so_cho BETWEEN 2 AND 60)
);

CREATE TABLE xe_may_ct (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bien_so VARCHAR(20) NOT NULL UNIQUE,
    hang_xe VARCHAR(100) NOT NULL,
    dung_tich_cc INTEGER NOT NULL
        CHECK (dung_tich_cc BETWEEN 50 AND 2000)
);

INSERT INTO o_to_ct (bien_so, hang_xe, so_cho)
VALUES ('OTO-CT-01', 'Toyota', 5);

INSERT INTO xe_may_ct (bien_so, hang_xe, dung_tich_cc)
VALUES ('XM-CT-01', 'Honda', 125);
~~~~

Các bảng đều có ràng buộc hợp lệ **cho chính loại của mình**. Nhưng có một khoảng trống lớn:

> **UNIQUE(bien_so) ở mỗi bảng chỉ bảo đảm duy nhất trong bảng đó.** SQL trên vẫn cho phép cùng biển số xuất hiện một lần ở O_TO_CT và một lần ở XE_MAY_CT, mặc dù yêu cầu nghiệp vụ nói biển số phải duy nhất toàn bộ hệ thống.

Tương tự, **id** do hai bộ sinh riêng tạo ra có thể trùng số giữa hai bảng. Hai giá trị id giống nhau thuộc hai bảng **không tự chứng minh là một phương tiện chung**, và không thể dùng id đơn lẻ làm đích FK chung tới mọi phương tiện.

### 5.3. Truy vấn đa hình bằng UNION ALL

Để liệt kê mọi phương tiện theo một tập cột chung:

~~~~sql
SELECT
    'OTO'::TEXT AS loai,
    id,
    bien_so,
    hang_xe,
    so_cho,
    NULL::INTEGER AS dung_tich_cc
FROM o_to_ct

UNION ALL

SELECT
    'XEMAY'::TEXT AS loai,
    id,
    bien_so,
    hang_xe,
    NULL::SMALLINT AS so_cho,
    dung_tich_cc
FROM xe_may_ct

ORDER BY loai, id;
~~~~

**UNION ALL** giữ tất cả bản ghi và chỉ ghép các dòng của những loại khác nhau. Không nên thay bằng UNION chỉ nhằm “chữa” trùng nghiệp vụ: nếu cùng biển số xuất hiện ở hai loại, cần **ràng buộc dữ liệu** chứ không phải phép loại trùng kết quả truy vấn.

Các phép tổng hợp toàn bộ phương tiện cũng phải kết hợp dữ liệu từ nhiều bảng:

~~~~sql
SELECT COUNT(*) AS tong_so_phuong_tien
FROM (
    SELECT id FROM o_to_ct
    UNION ALL
    SELECT id FROM xe_may_ct
) AS tat_ca;
~~~~

Đây là cách đếm số **hàng phương tiện đang lưu**, chứ không tự xác nhận tính duy nhất của các đối tượng ngoài đời. Nếu cùng một phương tiện bị nhập vào hai bảng, kết quả vẫn đếm hai hàng.

### 5.4. Khó khăn về toàn vẹn chung và tham chiếu

Với ba bảng chung + con, bảng PHUONG_TIEN_JT có thể là đích cho một FK như:

~~~~text
BAO_TRI(phuong_tien_id FK → PHUONG_TIEN_JT.id)
~~~~

Với phương án chỉ có bảng con, **không tồn tại một bảng cha chung** làm đích FK như vậy. Những cách xử lý tùy yêu cầu gồm:

- Tạo FK riêng cho từng loại trong bảng bảo trì với ràng buộc “chỉ một loại được chọn”; làm tăng số cột và quy tắc.
- Tạo bảng **đăng ký định danh chung** để bảo vệ id và biển số, rồi cho các bảng loại tham chiếu; giải pháp này gần với việc **khôi phục một bảng kiểu cha**.
- Sử dụng hệ thống định danh và quy trình kiểm tra riêng; cần minh bạch rằng tính toàn vẹn đa hình **không được bảo vệ bằng một FK thông thường**.

Không có FK SQL chuẩn có thể tự động “tham chiếu một trong hai bảng O_TO_CT hoặc XE_MAY_CT tùy giá trị discriminator” nếu chỉ khai báo một cột tham chiếu duy nhất mà không thêm cấu trúc hỗ trợ.

### 5.5. Ưu điểm, nhược điểm

**Ưu điểm:**

- Mỗi bảng loại tự đầy đủ; truy vấn thuộc tính riêng không cần JOIN.
- Các cột riêng có thể được đặt NOT NULL và CHECK trực tiếp, không tạo cột NULL chỉ vì loại không áp dụng.
- Cách lưu đơn giản nếu hệ thống luôn xử lý **từng loại cụ thể** và rất ít khi dùng truy vấn hoặc tham chiếu đến kiểu cha chung.

**Nhược điểm:**

- Lặp cột và ràng buộc chung ở mọi bảng: bien_so, hang_xe, các quy tắc kiểm tra.
- **Không bảo đảm UNIQUE toàn phân cấp bằng UNIQUE từng bảng**; dễ phát sinh dữ liệu trùng ở hai loại.
- Không có định danh và đích FK chung cho tất cả phương tiện nếu không thêm cấu trúc.
- Truy vấn chung phải UNION ALL; khi thêm kiểu con mới, các báo cáo và truy vấn đa hình có thể phải cập nhật.
- Khó hỗ trợ **overlapping**: một đối tượng có nhiều vai trò phải xuất hiện ở nhiều bảng cụ thể, có thể nhân bản hoặc bất nhất dữ liệu chung.

Phương án này hợp lý khi các loại thực sự có thể vận hành khá độc lập. Nhưng với ví dụ phương tiện có yêu cầu **biển số duy nhất toàn hệ thống** và nhiều bảng khác cùng tham chiếu PHUONG_TIEN, nó kém thuận lợi hơn hai phương án có bảng/định danh chung.

## 6. Bảng so sánh ba phương án ánh xạ

| Tiêu chí | A. Một bảng cho toàn phân cấp | B. Bảng cha + các bảng con | C. Bảng cho từng loại cụ thể |
| --- | --- | --- | --- |
| Nơi lưu thuộc tính chung | Cùng bảng với tất cả thuộc tính riêng | Chỉ trong bảng cha | Lặp ở từng bảng con |
| Khóa định danh chung | Một PK toàn phân cấp | PK cha, PK con dùng chung id cha | Không có PK chung mặc định |
| Tính duy nhất của biển số toàn hệ thống | Dễ bảo vệ bằng một UNIQUE | Dễ bảo vệ bằng UNIQUE ở cha | Cần cơ chế riêng ngoài UNIQUE từng bảng |
| Thuộc tính riêng bắt buộc | CHECK theo discriminator, thường có cột nullable | NOT NULL/CHECK trong từng bảng con | NOT NULL/CHECK trong từng bảng cụ thể |
| Disjoint | Dễ biểu diễn với một discriminator | Cần cơ chế ngăn id xuất hiện ở các con loại trừ; ví dụ FK ghép loại | Cần ngăn cùng đối tượng xuất hiện ở nhiều bảng |
| Overlapping | Không tự nhiên nếu chỉ dùng một discriminator | Tự nhiên, một id cha có nhiều dòng con theo vai trò | Dễ nhân bản dữ liệu chung |
| Total | Dễ kiểm tra theo hàng với discriminator và CHECK cho mô hình disjoint | FK con → cha chưa đủ; cần kiểm soát cha phải có con | Mọi bản ghi đã lưu đều nằm trong một bảng cụ thể, nhưng không có tập cha thống nhất để kiểm chứng |
| Partial | Cần giá trị trạng thái/loại phù hợp và quy tắc cột | Cho phép cha chưa có bảng con | Không biểu diễn được bản ghi chỉ có phần chung nếu không bổ sung bảng |
| Truy vấn đầy đủ một loại | Không JOIN, có điều kiện loai | JOIN cha và bảng loại | Không JOIN |
| Truy vấn tất cả loại | SELECT một bảng | SELECT cha hoặc JOIN nhiều bảng | UNION ALL các bảng |
| FK chung từ bảng nghiệp vụ khác | Một FK đến bảng chung | Một FK đến bảng cha | Khó nếu không tạo bảng định danh chung |
| Thêm kiểu con mới | Thường ALTER TABLE và CHECK | Tạo bảng con, cập nhật quy tắc phân loại nếu có | Tạo bảng mới, cập nhật truy vấn và ràng buộc chung |
| Nguy cơ khi thay đổi loại | Cập nhật discriminator và cột riêng | Cần chuyển dòng giữa bảng con trong giao dịch | Có thể phải chuyển bản ghi qua bảng khác, khó giữ FK chung |

Không có phương án nào luôn tối ưu. Chọn chiến lược không chỉ theo số lượng bảng mà phải dựa vào **ràng buộc định danh**, **tính chồng lấn**, **tính bắt buộc**, **kiểu truy vấn**, **vòng đời dữ liệu** và **khả năng thêm kiểu con**.

### 6.1. Trường hợp nên ưu tiên A

Cân nhắc **một bảng** khi:

- Tập kiểu con tương đối ít, phân biệt rõ, nhất là **disjoint + total**.
- Số cột riêng không quá lớn, quy tắc từng loại có thể diễn đạt rõ bằng CHECK.
- Phần lớn truy vấn cần đọc dữ liệu chung và riêng cùng lúc.
- Cần một định danh chung và ràng buộc duy nhất toàn hệ thống với chi phí JOIN thấp.

Với ví dụ hai kiểu O_TO và XE_MAY cùng vài thuộc tính riêng, phương án A khá dễ hiểu và có thể bảo vệ phần lớn quy tắc ngay ở DDL.

### 6.2. Trường hợp nên ưu tiên B

Cân nhắc **bảng cha + bảng con** khi:

- Có nhiều thuộc tính hoặc quan hệ đặc thù theo từng loại.
- Cần truy vấn thực thể chung và tham chiếu đến kiểu cha từ nhiều nghiệp vụ.
- Có vai trò **overlapping**, một đối tượng thuộc nhiều kiểu con.
- Muốn phân quyền hoặc vòng đời dữ liệu riêng cho từng nhóm thuộc tính.
- Chấp nhận JOIN và có kế hoạch kiểm soát các ràng buộc **total/disjoint** tương ứng.

Với **NGUOI → NHAN_VIEN/KHACH_HANG** mà một người có thể thuộc cả hai vai trò, phương án B thường trực quan hơn một cột loại đơn trị.

### 6.3. Trường hợp có thể dùng C

Cân nhắc **bảng theo loại cụ thể** khi:

- Các loại gần như hoạt động độc lập, ít truy vấn qua kiểu cha.
- Ít hoặc không có bảng khác cần FK chung tới mọi loại.
- Có thể quản lý các ràng buộc toàn hệ thống bằng một cơ chế được thiết kế rõ nếu cần.
- Chấp nhận trùng cấu trúc cột chung và cập nhật truy vấn UNION khi thêm loại.

Không nên chọn C cho một mô hình có nhiều liên kết tới “mọi phương tiện” chỉ vì muốn giảm JOIN. Có thể phí duy trì tính toàn vẹn và sự trùng lặp dữ liệu sẽ vượt lợi ích truy vấn từng loại.

## 7. Thêm kiểu con, chuyển loại và thay đổi nghiệp vụ

### 7.1. Khi xuất hiện kiểu mới

Giả sử từ năm sau hệ thống thêm **XE_TAI** với **tai_trong_kg**. Mô hình đang là disjoint + total với ba kiểu O_TO, XE_MAY, XE_TAI.

**Phương án A:** Thêm cột tai_trong_kg, mở rộng tập loai và CHECK liên kết loại với thuộc tính. Bản ghi các loại cũ có cột mới NULL; những truy vấn mặc định dựa trên tập loại cũng phải được xem lại.

**Phương án B:** Tạo bảng XE_TAI_JT có PK/FK cùng id với cha, CHECK tải trọng, sửa tập loại trong bảng cha và cơ chế kiểm tra total/disjoint. Truy vấn chung chỉ đọc bảng cha có thể không đổi; truy vấn đầy đủ mọi kiểu cần JOIN thêm bảng.

**Phương án C:** Tạo bảng XE_TAI_CT và lặp cấu trúc thuộc tính chung. Mọi báo cáo hợp nhất phải bổ sung nhánh XE_TAI_CT; quy tắc UNIQUE toàn phân cấp và FK đa hình cần được đánh giá lại.

Không được chỉ thêm kiểu mới ở mã nguồn ứng dụng mà bỏ qua **CHECK của cơ sở dữ liệu**, nếu không INSERT của kiểu mới sẽ bị từ chối hoặc dữ liệu không có cơ chế ràng buộc cần thiết.

### 7.2. Khi một thể hiện chuyển từ kiểu con này sang kiểu con khác

Giả sử một hệ thống khác cho phép một đối tượng nghiệp vụ **thay đổi nhóm phân loại**, ví dụ quyền thành viên từ “thường” sang “doanh nghiệp”. Khi chuyển loại:

- Với **A**, cập nhật discriminator và các cột riêng trong cùng hàng, nhưng phải giữ CHECK hợp lệ; có thể cần thay thế các thuộc tính không còn áp dụng.
- Với **B**, thêm/bớt hàng ở bảng con và cập nhật quy tắc phân loại của cha trong một giao dịch; cần tránh trạng thái trung gian sai với FK hoặc kiểm tra bổ sung.
- Với **C**, có thể phải chuyển hàng sang bảng khác và sửa mọi tham chiếu mang tính loại; việc giữ nguyên định danh qua các bảng khó hơn.

**Không phải loại nào cũng được phép chuyển**: đổi một chiếc xe máy thành ô tô có thể không có nghĩa trong nghiệp vụ; thay đổi loại thường chỉ hợp lý với **vai trò, trạng thái pháp lý hoặc phân hạng**. Nếu bản chất là một **trạng thái thay đổi theo thời gian**, cân nhắc mô hình trạng thái hoặc lịch sử phân loại thay vì một subtype bất biến.

### 7.3. Từ disjoint sang overlapping

Nếu một kiểu người đang được chia “KHÁCH” hoặc “NHÂN_VIÊN” nhưng nay một người có thể vừa là khách vừa là nhân viên, điều đó làm thay đổi **ràng buộc EER**, không chỉ một giá trị enum.

- Phương án A với một cột loai đơn trị không còn diễn đạt đủ; một số phương án mở rộng dùng tập cờ/vai trò hoặc tách bảng vai trò.
- Phương án B cho phép cùng một id có cả hàng KHACH_HANG và NHAN_VIEN; phải **bỏ ràng buộc loại trừ** nếu đã áp đặt nó.
- Phương án C dễ sinh hai bản ghi độc lập của cùng một người; cần giải quyết việc chia sẻ định danh và thuộc tính chung.

Lựa chọn mô hình ngay từ đầu nên xét xác suất nghiệp vụ chuyển từ disjoint sang overlapping, thay vì chỉ tối ưu cho dữ liệu hiện tại.

## 8. Chi tiết ràng buộc SQL thường bị hiểu nhầm

### 8.1. FK PK–PK ở bảng con không tự bảo đảm disjoint

Giả sử chỉ có:

~~~~sql
-- Ví dụ minh họa cấu trúc, không chạy trực tiếp cùng DDL mục 4.
-- O_TO(id PRIMARY KEY REFERENCES PHUONG_TIEN(id), so_cho ...)
-- XE_MAY(id PRIMARY KEY REFERENCES PHUONG_TIEN(id), dung_tich_cc ...)
~~~~

Hai bảng con được bảo đảm mỗi bảng có tối đa một dòng cho mỗi id, nhưng **cả hai bảng có thể cùng chứa id 101**. Nếu mô hình là disjoint thì đây là sai.

Vì vậy trong mục 4, ta dùng **loai hằng tại bảng con kết hợp FK ghép (id, loai)** đến bảng cha để chặn việc sai loại. Một lựa chọn khác là trigger kiểm tra ràng buộc loại trừ, nhưng phải thiết kế đúng với giao dịch đồng thời.

### 8.2. Disjoint không đồng nghĩa total

Nếu DB chặn một id xuất hiện ở **cả hai** bảng con, nó mới bảo vệ **tối đa một**; vẫn có thể có id **không xuất hiện ở bảng con nào**. Muốn **đúng một**, phải bảo vệ cả hai điều kiện:

\[
\text{số kiểu con của một id} \leq 1
\]

và

\[
\text{số kiểu con của một id} \geq 1
\]

Điều kiện đầu là **disjoint**, điều kiện sau là **total**. Bảo vệ đầu mà quên sau là lỗi thường gặp khi chuyển EER sang mô hình quan hệ.

### 8.3. UNIQUE ở từng bảng không phải UNIQUE toàn phân cấp

~~~~text
O_TO_CT:  bien_so = "X-001"  (hợp lệ trong bảng ô tô)
XE_MAY_CT: bien_so = "X-001"  (hợp lệ trong bảng xe máy)
~~~~

Nếu biển số là định danh duy nhất của **mọi phương tiện**, dữ liệu trên là sai nghiệp vụ nhưng vẫn hợp lệ với hai UNIQUE riêng. Đặt UNIQUE trên từng bảng chỉ kiểm soát phạm vi **từng bảng**.

Muốn duy nhất toàn bộ loại, cần **một nơi tập trung kiểm soát mã** hoặc giải pháp khác có khả năng thực thi liên bảng. Đưa mã vào bảng đăng ký chung là một thiết kế thường thấy, nhưng khi đó kiến trúc đã tiến gần phương án có kiểu cha.

### 8.4. CHECK và NULL

Trong PostgreSQL, biểu thức CHECK **FALSE** mới bị từ chối; TRUE và UNKNOWN thường được chấp nhận. Ví dụ CHECK(so_cho >= 2) **không** buộc so_cho khác NULL. Muốn thuộc tính riêng bắt buộc, dùng **NOT NULL** ở bảng loại hoặc **IS NOT NULL** trong nhánh CHECK thích hợp ở bảng chung.

### 8.5. Không nên nhầm PK riêng với định danh chung

Nếu kiểu con dùng **id riêng tự tăng** thay vì id cha, câu JOIN:

~~~~text
O_TO.id = PHUONG_TIEN.id
~~~~

không tự đúng. Hai giá trị id có thể trùng số ngẫu nhiên mà **không có quan hệ định danh**. Nếu vẫn muốn id kỹ thuật riêng ở bảng con, phải có **phuong_tien_id FK UNIQUE NOT NULL** để biểu đạt quan hệ 1:1; nhưng cách đó thường phức tạp hơn **shared PK** khi bảng con thuần túy là một phần chuyên biệt của cùng thể hiện cha.

### 8.6. PostgreSQL INHERITS không thay thế ba phương án ánh xạ logic

PostgreSQL có tính năng kế thừa bảng vật lý **INHERITS**, nhưng không nên mặc định nó tương đương với ánh xạ EER kiểu cha–con dùng **PK/FK** hay với ba chiến lược ORM. Những đặc tính như phạm vi ràng buộc UNIQUE/PK, FK và truy vấn qua bảng cha phải được kiểm tra theo loại kế thừa cụ thể của PostgreSQL. Khi yêu cầu là một định danh và một UNIQUE **toàn hệ thống**, bảng con PK/FK rõ ràng hoặc một bảng chung thường dễ kiểm chứng hơn việc dựa vào trực giác kế thừa lớp.

## 9. Liên hệ với code Java và ORM

Khi ứng dụng Java dùng ORM, các tên chiến lược thường gặp tương ứng ở mức ý tưởng:

| Chiến lược mô hình quan hệ | Tên quen thuộc trong ORM Java | Điều vẫn phải kiểm chứng trong DB |
| --- | --- | --- |
| Một bảng toàn phân cấp | SINGLE_TABLE | Discriminator, CHECK theo loại, NOT NULL có điều kiện |
| Bảng cha + bảng con | JOINED | PK/FK chia sẻ, đúng loại, disjoint/total |
| Bảng theo từng lớp cụ thể | TABLE_PER_CLASS | Truy vấn đa hình, định danh chung, UNIQUE toàn phân cấp |

Các annotation và hành vi SQL cụ thể tùy framework, phiên bản và cách cấu hình. **Mapping ORM không tự thay thế phân tích EER và ràng buộc cơ sở dữ liệu**. Dù đối tượng Java có quan hệ extends, cần kiểm tra SQL do ORM sinh ra, khóa được sử dụng, cách cập nhật phân loại và các trường hợp vi phạm ràng buộc nghiệp vụ.

Đặc biệt, **overlapping** là một mô hình về tập hợp vai trò và ràng buộc dữ liệu: một người đồng thời là nhân viên và khách hàng. Điều này không nhất thiết nên ép vào cây kế thừa lớp Java một chiều; một số hệ thống phù hợp hơn với **thực thể người chung + các vai trò liên kết** hoặc mô hình thành phần.

## 10. Quy trình thiết kế từ yêu cầu nghiệp vụ

Khi gặp một sơ đồ EER có kiểu cha–kiểu con, có thể thực hiện theo trình tự:

1. **Xác định định danh chung.** Một thể hiện kiểu con có chính là một thể hiện của kiểu cha hay là một đối tượng mới có liên kết 1:1? Không tự tạo id mới nếu đó là cùng một đối tượng.
2. **Tách thuộc tính chung và riêng.** Ví dụ bien_so và hang_xe chung; so_cho riêng ô tô; dung_tich_cc riêng xe máy.
3. **Viết rõ bội số thành viên của nhóm subtype.** Mỗi cha thuộc đúng một, tối đa một, ít nhất một hay bất kỳ số lượng con nào?
4. **Xác định loại trừ hay chồng lấn.** Tìm tình huống một đối tượng thuộc đồng thời hai kiểu con; nếu có, không dùng mô hình disjoint.
5. **Xác định toàn phần hay bộ phận.** Có cho phép bản ghi cha chưa có kiểu con? Nếu có, nó mang ý nghĩa nào và tồn tại tới khi nào?
6. **Liệt kê ràng buộc toàn phân cấp.** Tính duy nhất biển số, mã đối tượng, FK chung, trạng thái chung, chính sách xóa và lịch sử.
7. **Chọn chiến lược bảng.** Đặt phương án A, B, C cạnh các yêu cầu để nhận diện đánh đổi về JOIN, UNION, cột thưa, khóa và tính toàn vẹn.
8. **Viết DDL và đánh dấu khoảng trống.** Mỗi ràng buộc dùng PK, FK, UNIQUE, CHECK, NOT NULL hay cần cơ chế liên bảng? Phân biệt rõ phần đã và chưa được bảo đảm.
9. **Kiểm thử phản ví dụ.** Thử thiếu thuộc tính riêng, id con không có cha, sai discriminator, cha không có con, một id có hai loại, trùng mã giữa hai bảng cụ thể.
10. **Xem xét truy vấn và tiến hóa.** Có thường xuyên truy vấn tất cả loại không? Có thể xuất hiện kiểu mới hoặc chồng lấn vai trò không? Những bảng nào tham chiếu kiểu cha?
11. **Chỉ sau đó tối ưu vật lý.** Chọn chỉ mục theo khối lượng dữ liệu, kế hoạch truy vấn và chi phí ghi; không đổi ràng buộc logic chỉ để tránh JOIN.

### Bộ kiểm thử tối thiểu theo từng chiến lược

| Thử nghiệm | A. Bảng chung | B. Cha + con | C. Theo kiểu cụ thể |
| --- | --- | --- | --- |
| Chèn hai phương tiện trùng biển số ở hai loại | UNIQUE chung phải chặn | UNIQUE ở cha phải chặn | Hai UNIQUE riêng **không đủ** |
| Tạo ô tô không có so_cho | CHECK với IS NOT NULL phải chặn | NOT NULL ở O_TO_JT phải chặn nếu đã tạo con | NOT NULL ở O_TO_CT phải chặn |
| Tạo dòng con không có cha | Không có bảng con độc lập | FK phải chặn | Không có khái niệm cha riêng |
| Một id xuất hiện ở O_TO và XE_MAY | Discriminator một giá trị không cho phép | Phải có cơ chế disjoint, chẳng hạn FK ghép đúng loại | Cần cơ chế nhận diện chung để phát hiện nhân bản |
| Tạo cha nhưng không tạo con | Không biểu diễn kiểu cha ngoài tập đã khai nếu total | **Có thể lọt** nếu chưa kiểm tra total | Không có bảng cha chung |
| Một người vừa là nhân viên vừa là khách | Không phù hợp với discriminator đơn trị | Hai bảng vai trò cùng trỏ một id cha hợp lệ | Dễ nhân bản thông tin người |
| FK từ bảo trì đến mọi phương tiện | Tham chiếu PK của bảng chung | Tham chiếu PK bảng cha | Không có đích FK chung mặc định |

## 11. Bài tập thực hành có đáp án

### Bài 1 — Nhận diện disjoint và total

Hệ thống quản lý thẻ thành viên có hai loại **CA_NHAN** và **DOANH_NGHIEP**. Mỗi thẻ bắt buộc thuộc một loại, không thể đồng thời thuộc hai loại.

**Câu hỏi:** Phân cấp thuộc tổ hợp nào? Phương án bảng nào giúp diễn đạt rõ khi mỗi loại có rất ít thuộc tính riêng?

**Đáp án:** **Disjoint + total**: mỗi thẻ thuộc đúng một kiểu con. Có thể chọn **một bảng** với discriminator **loai** và CHECK theo loại nếu số thuộc tính riêng ít, ít cột thưa. Nếu các loại có nhiều thuộc tính/quy tắc riêng, bảng cha + bảng con cũng phù hợp nhưng phải kiểm soát điều kiện mỗi cha có đúng một con.

### Bài 2 — Kiểm tra ràng buộc loại trong một bảng

Một bảng đơn có cột loai nhận OTO/XEMAY, so_cho và dung_tich_cc, với CHECK:

~~~~sql
CHECK (
    (loai = 'OTO' AND so_cho BETWEEN 2 AND 60)
    OR
    (loai = 'XEMAY' AND dung_tich_cc BETWEEN 50 AND 2000)
)
~~~~

**Câu hỏi:** Điều kiện này đã đủ để bảo đảm ô tô luôn có số chỗ và xe máy không mang số chỗ chưa?

**Đáp án:** **Chưa.** Trong PostgreSQL, CHECK có thể cho **UNKNOWN** đi qua, nên so_cho NULL ở nhánh ô tô không bị chặn chắc chắn. Điều kiện cũng **không cấm** xe máy mang so_cho khác NULL hoặc ô tô mang dung_tich_cc khác NULL. Cần thêm **loai NOT NULL**, điều kiện **IS NOT NULL** cho thuộc tính bắt buộc và **IS NULL** cho thuộc tính không áp dụng như ở mục 3.2.

### Bài 3 — Vì sao bảng con có PK=FK chưa chắc là disjoint?

Cho PHUONG_TIEN(id PK), O_TO(id PK FK → PHUONG_TIEN), XE_MAY(id PK FK → PHUONG_TIEN).

**Câu hỏi:** Cùng một id 101 có thể xuất hiện ở cả hai bảng con không, nếu chỉ khai báo các ràng buộc kể trên?

**Đáp án:** **Có.** Mỗi PK chỉ bảo đảm duy nhất **trong bảng con riêng**, còn mỗi FK chỉ bảo đảm cha tồn tại. Để thực thi disjoint, phải có quy tắc chung, chẳng hạn discriminator ở cha và **FK ghép (id, loai)** từ mỗi bảng con với loai cố định đúng loại, hoặc một cơ chế liên bảng tương đương.

### Bài 4 — Một cha không có con có hợp lệ không?

Mô hình PHUONG_TIEN → O_TO/XE_MAY là disjoint + total. DDL bảng cha + bảng con có shared PK và FK, nhưng không có trigger hay quy trình bắt buộc tạo con.

**Câu hỏi:** Chèn một hàng cha loai = OTO mà không chèn O_TO có vi phạm FK không? Có đúng nghiệp vụ không?

**Đáp án:** **Không vi phạm FK con → cha**, vì chưa có dòng con nào cần kiểm tra. Nhưng **sai nghiệp vụ total**: mỗi cha phải có một kiểu con. Cần bổ sung kiểm tra tạo đủ cha–con và ngăn trạng thái thiếu con theo cơ chế áp dụng cho tất cả đường ghi dữ liệu.

### Bài 5 — Overlapping vai trò người

Một người có thể đồng thời là **NHAN_VIEN** và **KHACH_HANG**. Cần quản lý họ tên một lần và có FK chung đến người từ các bảng khác.

**Câu hỏi:** Phương án nào phù hợp? Khóa của các bảng vai trò nên thế nào?

**Đáp án:** Phương án **bảng NGUOI chung + bảng NHAN_VIEN và KHACH_HANG** phù hợp. Cùng một nguoi_id có thể xuất hiện trong hai bảng vai trò; tại mỗi bảng, **nguoi_id là PK đồng thời là FK** đến NGUOI(id). Điều này giữ một định danh và một bản ghi tên chung. Không áp dụng discriminator đơn trị cấm hai vai trò.

### Bài 6 — UNIQUE cục bộ khác UNIQUE toàn hệ thống

Hai bảng O_TO_CT và XE_MAY_CT đều có bien_so UNIQUE NOT NULL.

**Câu hỏi:** Có thể tồn tại hai hàng cùng bien_so = X001, một ở mỗi bảng không? Đề xuất giải pháp nếu biển số phải duy nhất trong mọi loại.

**Đáp án:** **Có**, vì mỗi UNIQUE chỉ bảo vệ bảng của mình. Có thể bổ sung **bảng định danh/đăng ký phương tiện chung với UNIQUE(bien_so)** rồi để mọi loại dùng chung mã đó, hoặc chọn phương án A/B. Dùng SELECT DISTINCT ở báo cáo không thay thế ràng buộc lúc ghi.

### Bài 7 — Truy vấn toàn bộ kiểu con

Cho hai bảng O_TO_CT(id, bien_so, hang_xe, so_cho) và XE_MAY_CT(id, bien_so, hang_xe, dung_tich_cc).

**Câu hỏi:** Viết truy vấn lấy một danh sách có cột loai, bien_so và hang_xe cho cả hai loại; có nên dùng UNION ALL không?

**Đáp án tham khảo:**

~~~~sql
SELECT 'OTO' AS loai, bien_so, hang_xe
FROM o_to_ct
UNION ALL
SELECT 'XEMAY' AS loai, bien_so, hang_xe
FROM xe_may_ct;
~~~~

**UNION ALL** phù hợp khi cần giữ mọi bản ghi từ hai loại và không dùng loại trùng để che lỗi dữ liệu. Muốn thứ tự ổn định, bao kết quả hoặc thêm ORDER BY phù hợp với cú pháp truy vấn chung.

### Bài 8 — Có nên chọn table-per-concrete khi có FK chung?

Hệ thống có bảng **SU_KIEN_BAO_TRI** tham chiếu phương tiện bất kể loại; các mã phương tiện cần duy nhất toàn hệ thống. Các kiểu O_TO và XE_MAY lại ít thuộc tính riêng.

**Câu hỏi:** Phương án nào có lợi thế về tính toàn vẹn?

**Đáp án:** **Một bảng toàn phân cấp (A)** hoặc **bảng cha + bảng con (B)** có đích FK chung và một nơi kiểm tra duy nhất mã phương tiện. Nếu đặc tả đơn giản, A có thể ít JOIN hơn; nếu loại có nhiều dữ liệu riêng, B có thể hợp lý hơn. C phải bổ sung cơ chế định danh chung mới bảo vệ được yêu cầu như hai phương án kia.

### Bài 9 — Thêm kiểu con mới

Hệ thống thêm XE_TAI có tai_trong_kg. Giả sử trước đó chỉ có O_TO và XE_MAY, disjoint + total.

**Câu hỏi:** Nêu công việc thay đổi schema hoặc truy vấn với mỗi phương án.

**Đáp án:**

- **A:** Thêm cột tai_trong_kg, mở rộng discriminator và CHECK theo loại.
- **B:** Tạo bảng XE_TAI với PK/FK cùng id cha, cập nhật ràng buộc phân loại, cơ chế disjoint/total và truy vấn chi tiết đa hình.
- **C:** Tạo XE_TAI_CT với các cột chung, cập nhật UNION/report, giải pháp bảo toàn mã và FK chung nếu có.

Ở cả ba cách, phải kiểm tra tác động lên mã nghiệp vụ, dữ liệu cũ và các ứng dụng đọc trường loai.

### Bài 10 — Trường hợp partial

Một hệ thống tiếp nhận hồ sơ người dùng trước, chỉ sau khi thẩm định mới gán vai trò NHAN_VIEN hoặc KHACH_HANG. Một số hồ sơ có thể không bao giờ nhận vai trò.

**Câu hỏi:** Nên coi chuyên biệt hóa là total hay partial? Có bắt buộc tạo ngay một dòng ở bảng con không?

**Đáp án:** Nếu hồ sơ người dùng được phép tồn tại hợp lệ mà chưa có vai trò thì chuyên biệt hóa là **partial**. Với bảng NGUOI + bảng vai trò, không cần tạo dòng con ngay; một dòng cha không có vai trò là hợp lệ. Không nên gắn nhãn total chỉ vì sau này phần lớn hồ sơ sẽ được phân vai trò.

### Bài 11 — Đếm số người và số vai trò

Một người id 7 có mặt trong cả NHAN_VIEN và KHACH_HANG; thêm một người id 8 chỉ có trong KHACH_HANG. Bảng NGUOI có đúng hai người.

**Câu hỏi:** Có bao nhiêu người và có bao nhiêu lần gán vai trò? Nếu ghép vai trò bằng UNION ALL, số dòng là bao nhiêu?

**Đáp án:** Có **2 người**, nhưng **3 lần gán vai trò**: nhân viên của người 7, khách hàng của người 7 và khách hàng của người 8. UNION ALL trên hai bảng vai trò trả **3 dòng**. Không được lấy số dòng vai trò làm số người phân biệt; muốn đếm người dùng COUNT trên bảng NGUOI hoặc đếm id phân biệt theo yêu cầu.

### Bài 12 — Thiết kế bảo vệ thuộc tính loại

Trong phương án joined, bảng O_TO_JT có so_cho NOT NULL và FK(id) đến cha, còn cha có loai.

**Câu hỏi:** Điều gì vẫn thiếu để bảo đảm một dòng O_TO_JT chỉ tham chiếu cha khai báo OTO?

**Đáp án:** FK(id) chỉ kiểm tra sự tồn tại, không kiểm tra **loai**. Có thể dùng **CHECK loai='OTO' trong bảng con** cùng **FK ghép (id, loai)** tham chiếu UNIQUE(id, loai) của cha như mục 4.2; hoặc dùng một cơ chế kiểm tra loại liên bảng phù hợp. Sau đó vẫn phải xem riêng ràng buộc **total**.

## 12. Ghi nhớ nhanh

| Khái niệm | Quy tắc trọng tâm |
| --- | --- |
| **Kiểu cha (supertype)** | Thực thể chung có định danh và các thuộc tính chung |
| **Kiểu con (subtype)** | Một tập con của kiểu cha; kế thừa định danh, có thuộc tính/quy tắc riêng |
| **Disjoint** | Một đối tượng cha ở tối đa một con trong nhóm |
| **Overlapping** | Một đối tượng cha có thể ở nhiều con cùng nhóm |
| **Total** | Mỗi đối tượng cha phải ở ít nhất một con |
| **Partial** | Đối tượng cha có thể chưa ở con nào |
| **Một bảng toàn phân cấp** | Discriminator + các cột chung/riêng; dễ CHECK disjoint + total khi nhóm đơn giản |
| **Bảng cha + bảng con** | Shared PK/FK, thuộc tính chung ở cha, riêng ở con; total cần kiểm tra bổ sung |
| **Bảng theo loại cụ thể** | Mỗi bảng chứa cả thuộc tính chung/riêng; cần quan tâm UNIQUE và FK toàn phân cấp |
| **Một PK chung** | Một đối tượng có một định danh xuyên qua các kiểu con |
| **CHECK với NULL** | Phải dùng NOT NULL/IS NOT NULL thích hợp, tránh UNKNOWN lọt qua |
| **FK con → cha** | Chỉ kiểm tra sự tồn tại của cha, không bắt cha phải có con |
| **Chuyển kiểu hoặc thêm kiểu** | Xem lại ràng buộc EER, migration, truy vấn và vòng đời |

**Kết luận:** Chuyển kiểu cha–kiểu con sang bảng không đơn thuần là chọn số bảng ít nhất. Việc quan trọng là giữ **định danh xuyên phân cấp**, **tính duy nhất**, **đúng thuộc tính từng kiểu**, **loại trừ/chồng lấn** và **toàn phần/bộ phận**. Một bảng có thể đơn giản khi các kiểu loại trừ và ít thuộc tính riêng; bảng cha + các bảng con linh hoạt khi có nhiều vai trò hoặc đặc tính riêng; bảng theo từng kiểu cụ thể thuận tiện cho xử lý độc lập nhưng phải cân nhắc ràng buộc toàn hệ thống. Hãy chọn phương án dựa trên yêu cầu có thể kiểm chứng, rồi mới tối ưu SQL, chỉ mục và thiết kế vật lý.

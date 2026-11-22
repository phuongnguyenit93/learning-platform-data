# Truy vấn khoảng thời gian giao nhau và khoảng hiệu lực trong SQL

> **Module:** Database SQL  
> **Chương:** Mẫu truy vấn  
> **Bài học:** Truy vấn khoảng thời gian giao nhau và khoảng hiệu lực

Trong nhiều hệ thống, dữ liệu không chỉ cho biết **một sự kiện xảy ra lúc nào** mà còn cho biết **một trạng thái, giá, quyền truy cập hoặc lịch đặt chỗ có hiệu lực trong khoảng thời gian nào**. Ví dụ: phòng họp đã được đặt từ 10:00 đến 12:00, hợp đồng có hiệu lực từ ngày 01/01 đến trước ngày 01/07, giá sản phẩm áp dụng từ một mốc tới khi có bản giá mới, hay nhân viên thuộc phòng ban nào tại ngày lập báo cáo.

Các câu hỏi tưởng đơn giản như “hai khoảng có giao nhau không?” thường gây lỗi ở **cận bằng nhau**, **đầu/cuối bao gồm hay loại trừ**, **NULL biểu thị vô hạn**, **kiểu DATE/TIMESTAMP**, **múi giờ** và **các bản ghi khoảng hiệu lực chồng lấn**. Bài học hướng dẫn các mẫu SQL có thể tái sử dụng, đồng thời làm rõ khác biệt giữa hệ quản trị.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Biểu diễn một khoảng thời gian bằng **thời điểm bắt đầu** và **thời điểm kết thúc**, phân biệt cận mở/cận đóng.
- Viết điều kiện SQL phát hiện **hai khoảng giao nhau** bằng bất đẳng thức chính xác.
- Phân biệt **giao nhau**, **chạm nhau**, **một khoảng chứa một thời điểm**, **một khoảng bao trọn khoảng khác**, **trước/sau** và **khoảng rỗng**.
- Dùng quy ước **nửa mở [start, end)** để tránh đếm trùng hoặc xung đột giả tại ranh giới.
- Xử lý **valid_from/valid_to**, khoảng hiện hành không có ngày hết hạn và dữ liệu NULL.
- Truy vấn lịch sử hiệu lực **as-of**: tìm phiên bản giá, trạng thái hoặc thuộc tính đúng tại thời điểm sự kiện.
- Phát hiện **khoảng hiệu lực trùng nhau** của cùng một đối tượng; hiểu vì sao SQL đúng cú pháp vẫn có thể tạo nhiều kết quả.
- Tính **giao của hai khoảng**, thời lượng giao, khoảng trống giữa các khoảng và gộp các khoảng liền/đè lên nhau.
- Đánh giá tình huống **đặt chỗ đồng thời** và biết rằng câu SELECT kiểm tra trước INSERT không tự ngăn race condition.
- Nhận biết khác biệt của PostgreSQL range types, SQL Server system-versioned temporal tables, Oracle, MySQL và SQLite.
- Thiết kế bộ kiểm thử gồm cận bằng nhau, khoảng rỗng, NULL, DST, dữ liệu sai và số lượng bản ghi lớn.

## 2. Hiểu đúng một khoảng thời gian

Một khoảng thời gian được mô tả bởi hai mốc:

~~~text
start_time ---------------------- end_time
~~~

Nhưng như vậy chưa đủ. Phải xác định **mỗi mốc có được tính là thuộc khoảng hay không**.

Trong toán học thường viết:

| Ký hiệu | Ý nghĩa | Ví dụ với khoảng 10:00 đến 12:00 |
|---|---|---|
| **[a, b]** | Bao gồm cả hai đầu | 10:00 và 12:00 đều thuộc khoảng |
| **[a, b)** | Bao gồm đầu, loại trừ cuối | 10:00 thuộc, 12:00 không thuộc |
| **(a, b]** | Loại trừ đầu, bao gồm cuối | 10:00 không thuộc, 12:00 thuộc |
| **(a, b)** | Loại trừ cả hai đầu | Không bao gồm 10:00 hoặc 12:00 |

Trong nhiều ứng dụng đặt lịch, hiệu lực và phiên bản dữ liệu, lựa chọn thuận tiện nhất là **khoảng nửa mở [start, end)**.

### 2.1. Vì sao [start, end) thường là mặc định tốt?

Giả sử phòng họp có hai lịch liên tiếp:

~~~text
Lịch A: [10:00, 12:00)
Lịch B: [12:00, 14:00)
~~~

Hai lịch **chạm nhau tại 12:00** nhưng **không giao nhau**, vì lịch A không còn hiệu lực tại 12:00. Do đó, phòng có thể được dùng liên tiếp, không có phút nào bị chiếm đồng thời.

Nếu biểu diễn bằng **[10:00, 12:00]** và **[12:00, 14:00]**, cả hai đều chứa đúng thời điểm 12:00; theo toán học, chúng giao nhau ở một điểm. Điều này có thể không phù hợp với hệ thống đặt chỗ.

Với khoảng nửa mở, độ dài cũng tự nhiên:

\[
\operatorname{duration}([s,e))=e-s
\]

và hai khoảng liên tiếp ghép thành một khoảng không tạo đếm đôi:

\[
[10,12)\cup[12,14)=[10,14)
\]

### 2.2. Quy ước phải nhất quán

Không có một quy tắc áp dụng cho mọi nghiệp vụ. Một hợp đồng có thể ghi “hết ngày 31/12”, trong khi cột dữ liệu lưu thời điểm chính xác. Đôi khi quy tắc pháp lý yêu cầu bao gồm đúng thời điểm cuối. Khi đó hãy mô hình hóa rõ ràng.

**Điểm cốt lõi:** một điều kiện SQL không thể đúng nếu người viết chưa xác định cận nào bao gồm, cận nào loại trừ.

## 3. Dữ liệu mẫu: lịch đặt phòng

Giả sử có bảng **lich_dat_phong**:

~~~sql
CREATE TABLE lich_dat_phong (
    ma_lich INTEGER PRIMARY KEY,
    ma_phong VARCHAR(20) NOT NULL,
    bat_dau TIMESTAMP NOT NULL,
    ket_thuc TIMESTAMP NOT NULL,
    trang_thai VARCHAR(20) NOT NULL,
    CONSTRAINT ck_khoang_duong
        CHECK (bat_dau < ket_thuc)
);
~~~

Mẫu dùng TIMESTAMP để dễ đọc. Trong hệ thống thực tế có nhiều múi giờ, phải cân nhắc kiểu chứa **thời điểm tuyệt đối** thích hợp DBMS, không giả định mọi TIMESTAMP đều mang thông tin timezone.

Dữ liệu giả định, mỗi khoảng theo quy ước **[bat_dau, ket_thuc)**:

| ma_lich | ma_phong | bat_dau | ket_thuc | trang_thai |
|---:|---|---|---|---|
| 101 | A | 2026-04-10 10:00 | 2026-04-10 12:00 | CONFIRMED |
| 102 | A | 2026-04-10 12:00 | 2026-04-10 14:00 | CONFIRMED |
| 103 | A | 2026-04-10 15:00 | 2026-04-10 17:00 | CONFIRMED |
| 104 | A | 2026-04-11 09:00 | 2026-04-11 11:00 | CANCELLED |
| 201 | B | 2026-04-10 11:00 | 2026-04-10 13:00 | CONFIRMED |
| 202 | B | 2026-04-10 14:00 | 2026-04-10 16:00 | CONFIRMED |

Trong tất cả ví dụ đặt phòng, chỉ các bản ghi **CONFIRMED** được coi là giữ chỗ. Bản ghi **CANCELLED** có thể vẫn được lưu để tra cứu lịch sử nhưng không gây xung đột.

Một câu hỏi thường gặp:

> Phòng A còn trống từ **11:30 đến 12:30** ngày 10/04/2026 không?

Khoảng cần kiểm tra **[11:30, 12:30)** giao với cả lịch 101 **[10:00,12:00)** lẫn lịch 102 **[12:00,14:00)**. Đó là **hai xung đột**, không phải một.

## 4. Công thức quan trọng nhất: hai khoảng nửa mở giao nhau

Giả sử hai khoảng hợp lệ:

~~~text
A = [a_start, a_end)
B = [b_start, b_end)
~~~

với:

~~~text
a_start < a_end
b_start < b_end
~~~

Điều kiện cần và đủ để chúng có **giao không rỗng**:

\[
a_{\text{start}} < b_{\text{end}}
\quad\land\quad
b_{\text{start}} < a_{\text{end}}
\]

Trong SQL:

~~~sql
a.bat_dau < b.ket_thuc
AND b.bat_dau < a.ket_thuc
~~~

Khi kiểm tra một khoảng mới **[new_start, new_end)** so với dòng đang lưu:

~~~sql
bat_dau < :new_end
AND :new_start < ket_thuc
~~~

Dấu **<** là điểm quyết định. Nếu hai khoảng chỉ **chạm** tại một điểm thì điều kiện giao nhau phải cho FALSE.

### 4.1. Tại sao công thức đúng?

Hai khoảng **không giao nhau** khi chúng nằm tách biệt:

~~~text
A kết thúc trước hoặc đúng lúc B bắt đầu:
a_end <= b_start

HOẶC

B kết thúc trước hoặc đúng lúc A bắt đầu:
b_end <= a_start
~~~

Tức là:

\[
\text{không giao}
=
(a_{\text{end}}\le b_{\text{start}})
\lor
(b_{\text{end}}\le a_{\text{start}})
\]

Phủ định theo De Morgan, trong điều kiện giá trị đầu/cuối xác định và hợp lệ:

\[
\text{giao}
=
(a_{\text{end}}>b_{\text{start}})
\land
(b_{\text{end}}>a_{\text{start}})
\]

Tương đương:

~~~sql
a.bat_dau < b.ket_thuc
AND b.bat_dau < a.ket_thuc
~~~

### 4.2. Sơ đồ các tình huống

~~~text
A = [10:00----------12:00)

B1 =      [11:00-----------13:00)   GIAO
B2 =                   [12:00---14:00)  CHẠM, KHÔNG GIAO
B3 = [08:00--10:00)                    CHẠM, KHÔNG GIAO
B4 = [08:00----------------15:00)       B CHỨA A, CÓ GIAO
B5 =         [10:30--11:00)            B NẰM TRONG A, CÓ GIAO
B6 =                           [13:00--14:00) KHÔNG GIAO
~~~

Chỉ cần hai phép bất đẳng thức là bao phủ mọi dạng giao nhau: chồng một phần, bao trọn, nằm trong, trùng hẳn. Không cần liệt kê từng trường hợp bằng nhiều nhánh OR.

## 5. Câu SQL tìm lịch đặt phòng bị giao nhau

Với phòng A và khoảng mới [11:30, 12:30):

~~~sql
SELECT
    ma_lich,
    ma_phong,
    bat_dau,
    ket_thuc
FROM lich_dat_phong
WHERE ma_phong = 'A'
  AND trang_thai = 'CONFIRMED'
  AND bat_dau < ?
  AND ? < ket_thuc
ORDER BY bat_dau, ma_lich;
~~~

Bind tham số theo thứ tự:

1. **new_end = 2026-04-10 12:30**.
2. **new_start = 2026-04-10 11:30**.

Kết quả:

| ma_lich | bat_dau | ket_thuc |
|---:|---|---|
| 101 | 10:00 | 12:00 |
| 102 | 12:00 | 14:00 |

Nếu DBMS có hỗ trợ tên tham số trong công cụ tương ứng, ý tưởng có thể diễn đạt rõ hơn:

~~~sql
WHERE ma_phong = :room_id
  AND trang_thai = 'CONFIRMED'
  AND bat_dau < :new_end
  AND :new_start < ket_thuc
~~~

**Dấu :... chỉ là ký hiệu tham số của công cụ/driver hoặc framework**, không phải cú pháp nhận diện thống nhất trong mọi DBMS. JDBC thuần thường dùng **?**.

### 5.1. Truy vấn kiểm tra còn trống

Nếu chỉ cần trả lời **có xung đột hay không**, dùng EXISTS:

~~~sql
SELECT CASE
    WHEN EXISTS (
        SELECT 1
        FROM lich_dat_phong l
        WHERE l.ma_phong = ?
          AND l.trang_thai = 'CONFIRMED'
          AND l.bat_dau < ?
          AND ? < l.ket_thuc
    )
    THEN 'CO_XUNG_DOT'
    ELSE 'TRONG'
END AS tinh_trang;
~~~

Tham số gồm phòng, new_end, new_start. EXISTS không cần đếm hết các lịch xung đột để biết có ít nhất một lịch.

**Nhưng kiểm tra trống bằng SELECT không tự ngăn hai giao dịch đồng thời đặt trùng.** Phần về concurrency sẽ phân tích rõ.

## 6. Bảng kiểm thử ranh giới giao nhau

Giữ lịch A là **[10:00,12:00)**. Các khoảng B đều là khoảng hợp lệ, trừ khi ghi rõ:

| Khoảng B | Kết quả giao | Lý do |
|---|---|---|
| [09:00,10:00) | Không | Kết thúc đúng lúc A bắt đầu |
| [09:00,10:01) | Có | Có một phút chung |
| [10:00,11:00) | Có | B bắt đầu đúng đầu A |
| [11:00,12:00) | Có | B nằm trong A |
| [11:30,12:30) | Có | Giao một phần |
| [12:00,13:00) | Không | Chạm đúng cuối A |
| [12:01,13:00) | Không | B bắt đầu sau A |
| [09:00,13:00) | Có | B chứa A |
| [10:00,12:00) | Có | Hai khoảng giống nhau |
| [11:00,11:00) | Không hợp lệ theo chính sách khoảng dương | Start = end |
| [13:00,12:00) | Không hợp lệ | Start > end |

Ở các bảng giao dịch thực tế, nên đưa **đúng cận**, **ngay trước cận**, **ngay sau cận**, **trùng toàn bộ** và **không có giao** vào bộ test. “Ngay trước” có thể là microsecond hoặc nanosecond tùy độ chính xác kiểu dữ liệu; không cố thêm/bớt “một mili giây” khi DBMS có độ phân giải khác.

## 7. Vì sao BETWEEN thường không phù hợp để kiểm tra giao nhau?

Một cách viết dễ gặp:

~~~sql
WHERE :new_start BETWEEN bat_dau AND ket_thuc
~~~

Điều này hỏi “**điểm bắt đầu** của khoảng mới có nằm trong khoảng cũ không?”, không hỏi hai khoảng giao nhau trong mọi trường hợp.

Ví dụ:

~~~text
Lịch cũ: [10:00,12:00)
Lịch mới: [09:00,13:00)
~~~

Lịch mới **bao trọn** lịch cũ nên chắc chắn giao. Nhưng new_start = 09:00 không nằm trong lịch cũ, vì thế truy vấn trên có thể bỏ sót xung đột.

Một cách khác:

~~~sql
WHERE bat_dau BETWEEN :new_start AND :new_end
~~~

cũng không hoàn chỉnh nếu lịch cũ bao trọn lịch mới.

### 7.1. BETWEEN thường bao gồm cả hai cận

Theo ngữ nghĩa thông thường:

~~~sql
x BETWEEN a AND b
~~~

tương đương:

~~~sql
x >= a AND x <= b
~~~

Điều này dễ gây lỗi chạm biên với quy ước **[start,end)**. Chẳng hạn, điểm 12:00 không còn nằm trong [10:00,12:00) nhưng BETWEEN 10:00 AND 12:00 lại cho TRUE.

Khi kiểm tra một thời điểm **t** nằm trong khoảng nửa mở, dùng:

~~~sql
bat_dau <= :t
AND :t < ket_thuc
~~~

Khi kiểm tra **hai khoảng giao nhau**, dùng:

~~~sql
a.bat_dau < b.ket_thuc
AND b.bat_dau < a.ket_thuc
~~~

**BETWEEN không sai tự thân**; nó phù hợp với miền dữ liệu và cận bao gồm cả hai đầu. Lỗi là áp dụng một phép kiểm tra điểm vào bài toán giao của hai khoảng, hoặc quên rằng cận trên được bao gồm.

## 8. Giao nhau, chạm nhau và đứng trước nhau

Với A = [a_start,a_end) và B = [b_start,b_end), giả định hai khoảng có độ dài dương:

| Quan hệ | Điều kiện |
|---|---|
| Có giao thực sự | a_start < b_end AND b_start < a_end |
| A đứng trước hoặc chạm B | a_end <= b_start |
| A đứng hoàn toàn trước B, có khoảng trống | a_end < b_start |
| A chạm B từ bên trái | a_end = b_start |
| B chạm A từ bên trái | b_end = a_start |
| A bằng B | a_start = b_start AND a_end = b_end |
| A chứa trọn B | a_start <= b_start AND b_end <= a_end |
| A nằm trọn trong B | b_start <= a_start AND a_end <= b_end |
| A chứa thời điểm t | a_start <= t AND t < a_end |

Một truy vấn tìm **lịch ngay sát** lịch đang xét có thể dùng:

~~~sql
WHERE a.ket_thuc = b.bat_dau
   OR b.ket_thuc = a.bat_dau
~~~

Điều kiện này nhận **chạm biên**, không phải giao nhau. Nếu muốn phát hiện xung đột đặt phòng, không dùng nó thay cho predicate giao nhau.

### 8.1. Giao nhưng không chứa hoàn toàn

Nếu cần “hai khoảng giao một phần, không có khoảng nào bao trọn khoảng còn lại”, cần kết hợp predicate giao với các điều kiện phủ định quan hệ chứa. Tuy nhiên, hãy xác nhận định nghĩa “giao một phần” trong báo cáo: có hệ thống coi **trùng hẳn** cũng là giao, có hệ thống muốn loại trùng hẳn.

### 8.2. Đầu bằng nhau

Hai khoảng [10:00,12:00) và [10:00,11:00) **giao nhau** vì cả hai chứa các thời điểm từ 10:00 đến trước 11:00. Dấu **<** trong công thức giao không có nghĩa phải loại tất cả các cận bằng nhau; chỉ loại trường hợp **một khoảng kết thúc đúng lúc khoảng kia bắt đầu**.

## 9. Kiểm tra hợp lệ trước khi so khoảng

Công thức giao nhau ở phần 4 giả định:

~~~text
start_time < end_time
~~~

Nếu cho phép khoảng rỗng **[t,t)**, công thức cần cẩn thận. Ví dụ khoảng A rỗng [11:00,11:00) và B [10:00,12:00):

~~~text
a_start < b_end  -> TRUE
b_start < a_end  -> TRUE
~~~

Hai bất đẳng thức có thể đều TRUE dù khoảng A **không chứa thời điểm nào**. Bởi vậy, công thức đơn giản chỉ tương đương với giao không rỗng khi **cả hai khoảng đều hợp lệ và không rỗng**.

### 9.1. Chính sách thường dùng: cấm khoảng rỗng

Với đặt phòng, giá trị và hợp đồng có thời lượng dương, khai báo:

~~~sql
CHECK (bat_dau < ket_thuc)
~~~

và bảo đảm hai cột **NOT NULL**. Khi nhận yêu cầu tạo lịch mới, cũng kiểm tra:

~~~text
new_start < new_end
~~~

trước khi tìm xung đột.

### 9.2. Nếu nghiệp vụ cho phép khoảng rỗng

Phải định nghĩa nghĩa của một khoảng rỗng: sự kiện tức thời có nên mô hình hóa bằng một **timestamp riêng** thay vì start=end hay không?

Nếu buộc phải giữ [t,t) như một khoảng không có thời lượng, trước khi kiểm tra giao thêm:

~~~sql
a.bat_dau < a.ket_thuc
AND b.bat_dau < b.ket_thuc
AND a.bat_dau < b.ket_thuc
AND b.bat_dau < a.ket_thuc
~~~

Không đánh đồng **event tại thời điểm t** với **interval không có phần tử**. Đó là hai loại dữ liệu có quy tắc khác nhau.

### 9.3. CHECK và NULL

Trong nhiều DBMS, CHECK không từ chối một biểu thức đánh giá thành UNKNOWN giống như từ chối FALSE. Nếu bat_dau hoặc ket_thuc NULL, điều kiện bat_dau < ket_thuc có thể UNKNOWN, không đủ để bảo đảm cả hai có giá trị.

Do đó, nếu khoảng phải hữu hạn và không rỗng, dùng đồng thời:

~~~sql
bat_dau TIMESTAMP NOT NULL,
ket_thuc TIMESTAMP NOT NULL,
CHECK (bat_dau < ket_thuc)
~~~

Nếu NULL ở ket_thuc đại diện vô hạn, cần một constraint khác, trình bày phần sau.

## 10. Khoảng hiệu lực: valid_from và valid_to

Trong hệ thống giá, quyền truy cập, thuế suất hoặc lịch sử thuộc tính, thường dùng:

~~~text
valid_from
valid_to
~~~

Quy ước khuyến nghị:

~~~text
[valid_from, valid_to)
~~~

Một bản ghi áp dụng tại thời điểm **:as_of** khi:

~~~sql
valid_from <= :as_of
AND :as_of < valid_to
~~~

Ví dụ lịch sử giá của sản phẩm P01:

| ma_phien_ban | ma_san_pham | gia | valid_from | valid_to |
|---:|---|---:|---|---|
| 1 | P01 | 100000 | 2026-01-01 | 2026-02-01 |
| 2 | P01 | 120000 | 2026-02-01 | 2026-03-15 |
| 3 | P01 | 110000 | 2026-03-15 | NULL |

Nếu NULL ở valid_to mang nghĩa **chưa có ngày kết thúc**, các bản giá có khoảng:

~~~text
[2026-01-01, 2026-02-01)
[2026-02-01, 2026-03-15)
[2026-03-15, +infinity)
~~~

Tại **2026-02-01 00:00**, bản giá thứ nhất hết hiệu lực, bản thứ hai bắt đầu. Quy ước này tránh việc hai giá cùng áp dụng tại đúng một thời điểm biên.

### 10.1. Query as-of

~~~sql
SELECT
    ma_san_pham,
    gia
FROM lich_su_gia
WHERE ma_san_pham = 'P01'
  AND valid_from <= :as_of
  AND (
      valid_to > :as_of
      OR valid_to IS NULL
  );
~~~

Nếu :as_of = 2026-02-01, kết quả dự kiến là **giá 120000**.

Nếu :as_of = 2026-04-01, kết quả là **giá 110000** ở bản hiện hành.

### 10.2. Nên dùng điều kiện cận theo cùng một quy ước

Nếu dùng:

~~~sql
valid_from <= :as_of
AND :as_of <= valid_to
~~~

cho dữ liệu lưu các khoảng nửa mở, tại biên 2026-02-01 hai bản giá có thể cùng thỏa. Một phép nối với đơn hàng vào đúng biên sẽ tạo **hai dòng giá**, có thể nhân tiền hoặc chọn giá sai.

**Dấu < ở cận trên là quy ước nghiệp vụ, không phải chi tiết tùy chọn.**

## 11. NULL ở ngày kết thúc: vô hạn hay dữ liệu bị thiếu?

Một cột **valid_to NULL** có ít nhất hai cách diễn giải:

1. **Vô hạn tương lai:** bản ghi chưa được ấn định ngày hết hạn.
2. **Chưa biết giá trị:** nguồn chưa nhập ngày kết thúc, không chắc khoảng còn hiệu lực.

Hai nghĩa này khác nhau. SQL không tự hiểu NULL là vô hạn.

### 11.1. Nếu NULL được quy ước là +infinity

Tìm hiệu lực tại một thời điểm:

~~~sql
valid_from <= :t
AND (valid_to IS NULL OR :t < valid_to)
~~~

Hai khoảng có thể cùng open-ended:

~~~sql
a.bat_dau < b.ket_thuc
AND b.bat_dau < a.ket_thuc
~~~

sẽ cho UNKNOWN nếu b.ket_thuc hoặc a.ket_thuc NULL. Cần mở rộng logic:

~~~sql
(a.ket_thuc IS NULL OR b.bat_dau < a.ket_thuc)
AND
(b.ket_thuc IS NULL OR a.bat_dau < b.ket_thuc)
~~~

Đây là predicate hai khoảng **[start,end)** với **end NULL nghĩa là +infinity**, với giả định **các giá trị start NOT NULL**, còn end nếu có thì **end > start**. Đặt tên bảng/cột tùy thực tế.

### 11.2. Công thức xung đột với một khoảng mới hữu hạn

Nếu các lịch hiện tại cho phép ket_thuc NULL = vô hạn, còn khoảng mới [new_start,new_end) hữu hạn và không rỗng:

~~~sql
existing.bat_dau < :new_end
AND
(
    existing.ket_thuc IS NULL
    OR :new_start < existing.ket_thuc
)
~~~

Nếu chính khoảng mới cũng có thể kết thúc mở, cần thêm điều kiện:

~~~sql
(:new_end IS NULL OR existing.bat_dau < :new_end)
AND
(existing.ket_thuc IS NULL OR :new_start < existing.ket_thuc)
~~~

Chú ý thứ tự logic: mỗi vế kiểm tra **đầu của một khoảng** có nằm trước **cuối của khoảng kia** hay không.

### 11.3. Nếu NULL là dữ liệu không rõ

Không được tự xử lý NULL như vô hạn. Một bản ghi thiếu valid_to có thể cần trạng thái **DANG_CHO_BO_SUNG**, được loại ra khỏi báo cáo hiệu lực hoặc được gắn cờ chất lượng.

Trong thiết kế, có thể thêm **is_open_ended**, **status** hoặc quy tắc rõ ràng để tránh dùng cùng một NULL cho hai ý nghĩa.

### 11.4. Giá trị sentinel ngày rất xa

Một số hệ lưu **9999-12-31** thay vì NULL. Cách này giúp so sánh bằng bất đẳng thức trực tiếp, nhưng có vấn đề:

- Khả năng biểu diễn ngày tối đa khác nhau theo kiểu/DBMS.
- Giá trị đó không thật sự là **+infinity**.
- Biểu thức cộng ngày có thể tràn.
- Bản báo cáo có thể hiển thị ngày giả như một ngày nghiệp vụ.

Nếu dùng sentinel, phải quy định nó là dữ liệu kỹ thuật và xử lý thống nhất ở toàn hệ thống. PostgreSQL có range types và biểu diễn infinity chuyên biệt; không nên tự tạo sentinel nếu có một mô hình chính xác và phù hợp hơn.

## 12. Cận mở ở đầu: hiệu lực từ quá khứ vô hạn

Có hệ thống cho phép:

~~~text
valid_from NULL => hiệu lực từ -infinity
valid_to NULL   => hiệu lực đến +infinity
~~~

Với quy ước hai NULL như vậy, một bản ghi áp dụng tại :t khi:

~~~sql
(valid_from IS NULL OR valid_from <= :t)
AND
(valid_to IS NULL OR :t < valid_to)
~~~

Hai khoảng như vậy giao nhau nếu:

~~~sql
(a.valid_to IS NULL
    OR b.valid_from IS NULL
    OR b.valid_from < a.valid_to)
AND
(b.valid_to IS NULL
    OR a.valid_from IS NULL
    OR a.valid_from < b.valid_to)
~~~

Giả định mỗi khoảng có định nghĩa hợp lệ và không rỗng theo quy ước cận vô hạn; phải kiểm tra riêng các trường hợp cả hai cận NULL hoặc cận hữu hạn đảo ngược.

**Không áp dụng mở đầu bằng NULL nếu thiết kế không cho phép.** Nhiều hệ SCD Type 2 bắt buộc valid_from có giá trị và chỉ valid_to mới NULL.

## 13. Kiểm tra một khoảng hoàn toàn nằm trong khoảng khác

Đôi khi không chỉ cần một phần giao mà muốn biết lịch nhỏ có **được bao trọn** trong lịch lớn không.

Cho A = [a_start,a_end), B = [b_start,b_end), hai khoảng hữu hạn:

~~~sql
a_start <= b_start
AND
b_end <= a_end
~~~

Kết quả TRUE nghĩa là **A chứa B**.

Ví dụ chính sách: thời gian một phiên họp phải nằm trong ca làm việc:

~~~sql
ca.bat_dau <= hop.bat_dau
AND
hop.ket_thuc <= ca.ket_thuc
~~~

Dấu **<=** ở so sánh các cận thể hiện hai khoảng được phép **bắt đầu cùng lúc** hoặc **kết thúc cùng lúc**. Điều đó không mâu thuẫn với quy ước cận cuối bị loại: [10:00,12:00) vẫn có thể chứa [10:00,12:00) hoàn toàn.

Nếu end NULL nghĩa vô hạn, điều kiện bao trọn phải xét vô hạn đúng, không dùng so sánh trực tiếp với NULL.

## 14. Khoảng giao và độ dài phần giao

Nếu hai khoảng hữu hạn giao nhau, khoảng giao của chúng là:

\[
[\max(a_{\text{start}},b_{\text{start}}),
  \min(a_{\text{end}},b_{\text{end}}))
\]

Ví dụ:

~~~text
A = [10:00, 13:00)
B = [11:30, 15:00)

Giao = [11:30, 13:00)
Độ dài giao = 1 giờ 30 phút
~~~

### 14.1. SQL xác định cận của phần giao

Trên những DBMS hỗ trợ **GREATEST/LEAST** cho kiểu thời gian:

~~~sql
SELECT
    GREATEST(a.bat_dau, b.bat_dau) AS giao_tu,
    LEAST(a.ket_thuc, b.ket_thuc) AS giao_den
FROM lich_a a
JOIN lich_b b
    ON a.bat_dau < b.ket_thuc
   AND b.bat_dau < a.ket_thuc;
~~~

Trong ví dụ này, mỗi dòng JOIN là **một cặp có giao**. Chỉ tính độ dài khi giao thực sự tồn tại và cận hợp lệ.

**Khả chuyển:** PostgreSQL, MySQL và nhiều phiên bản Oracle có GREATEST/LEAST; SQL Server có GREATEST/LEAST ở các phiên bản mới hơn, không nên giả định SQL Server cũ luôn hỗ trợ. Cần kiểm tra hành vi NULL và kiểu dữ liệu cụ thể.

### 14.2. Dùng CASE khi cần tương thích rộng

~~~sql
CASE
    WHEN a.bat_dau >= b.bat_dau THEN a.bat_dau
    ELSE b.bat_dau
END AS giao_tu,

CASE
    WHEN a.ket_thuc <= b.ket_thuc THEN a.ket_thuc
    ELSE b.ket_thuc
END AS giao_den
~~~

Điều kiện trên giả định **bốn mốc đều NOT NULL**. Với end NULL nghĩa +infinity, cần logic riêng: nếu một phía vô hạn thì cận cuối của giao lấy cận hữu hạn kia, hoặc giao cũng vô hạn nếu cả hai vô hạn.

### 14.3. Tính thời lượng giao

Công thức:

\[
\operatorname{duration} =
\max\left(0,\min(a_e,b_e)-\max(a_s,b_s)\right)
\]

Cách trừ timestamp rất khác nhau:

- **PostgreSQL:** trừ hai timestamp/timestamptz cho ra interval, có thể chuyển sang giây theo EXTRACT(EPOCH FROM ...).
- **SQL Server:** có thể dùng DATEDIFF hoặc DATEDIFF_BIG với đơn vị cụ thể; lưu ý DATEDIFF đếm ranh giới đơn vị và có thể khác độ dài thực nếu chọn đơn vị quá thô.
- **MySQL:** TIMESTAMPDIFF với đơn vị phù hợp; kiểm tra timezone/kiểu.
- **Oracle:** DATE trừ DATE cho số ngày; TIMESTAMP trừ TIMESTAMP cho interval, tùy kiểu.
- **SQLite:** có thể dùng hàm thời gian như julianday hoặc unixepoch theo cách lưu, chú ý độ chính xác.

Không dùng **DATEDIFF(day, ...)** để tính số ngày công chính xác của khoảng thời gian có giờ phút vì nó có thể đếm số lần vượt mốc ngày thay vì số giờ/24.

## 15. Lọc các khoảng cắt qua một kỳ báo cáo

Giả sử cần lấy đơn đặt phòng có bất kỳ phần nào rơi vào **ngày 10/04/2026**.

Quy ước ngày báo cáo là:

~~~text
[2026-04-10 00:00, 2026-04-11 00:00)
~~~

Truy vấn:

~~~sql
SELECT ma_lich, ma_phong, bat_dau, ket_thuc
FROM lich_dat_phong
WHERE trang_thai = 'CONFIRMED'
  AND bat_dau < :report_end
  AND :report_start < ket_thuc;
~~~

Với report_start = nửa đêm 10/04 và report_end = nửa đêm 11/04, truy vấn tìm mọi lịch có phần giao thực sự với ngày đó, kể cả lịch bắt đầu từ ngày 09/04 nhưng kéo sang ngày 10/04.

### 15.1. Lỗi khi chỉ lọc điểm bắt đầu

~~~sql
WHERE bat_dau >= :report_start
  AND bat_dau < :report_end
~~~

chỉ tìm các lịch **bắt đầu** trong ngày báo cáo. Nó có thể bỏ sót lịch bắt đầu tối hôm trước và kết thúc sáng hôm sau.

Hai yêu cầu khác nhau:

- **Các lịch bắt đầu trong ngày:** lọc bat_dau.
- **Các lịch có bất kỳ thời lượng nào trong ngày:** dùng predicate giao nhau.

### 15.2. Tính tiền theo phần thời gian giao

Nếu hợp đồng tính phí theo giờ và một lịch kéo qua nhiều ngày, việc gán toàn bộ tiền cho ngày bắt đầu có thể sai. Khi đó cần:

1. Tìm các lịch giao với kỳ báo cáo.
2. Tính **giao_tu, giao_den**.
3. Tính thời lượng thực trong kỳ.
4. Áp dụng quy tắc tính tiền theo thời lượng/đơn giá (và làm tròn phù hợp).

Không chỉ đếm dòng giao nhau rồi chia đều một cách tùy ý.

## 16. DATE khác TIMESTAMP: kết thúc ngày có bao gồm không?

Trong giao diện hợp đồng có thể ghi:

~~~text
Có hiệu lực từ 01/01/2026 đến hết ngày 31/03/2026.
~~~

Nếu lưu bằng cột DATE bao gồm cả hai ngày:

~~~text
start_date = 2026-01-01
end_date_inclusive = 2026-03-31
~~~

điều kiện ngày D nằm trong hợp đồng là:

~~~sql
start_date <= D
AND D <= end_date_inclusive
~~~

Nhưng với thời điểm TIMESTAMP, “hết ngày 31/03” không nên biểu diễn bằng 23:59:59.999 vì độ chính xác khác theo DBMS.

### 16.1. Chuyển ngày kết thúc bao gồm sang cận trên loại trừ

Nếu miền nghiệp vụ là **ngày lịch**, có thể lưu:

~~~text
valid_from = 2026-01-01
valid_to_exclusive = 2026-04-01
~~~

và kiểm tra:

~~~sql
valid_from <= :date
AND :date < valid_to_exclusive
~~~

Cách này tránh phải cộng “một phần thời gian nhỏ nhất” vào cuối ngày.

### 16.2. Không tự cộng một ngày cho mọi TIMESTAMP

Nếu một hợp đồng kết thúc lúc **2026-03-31 15:30** theo giờ cụ thể, cộng một ngày sẽ thành 2026-04-01 15:30, không phản ánh hợp đồng “đến 15:30”. Phép chuyển **inclusive date → exclusive next-day date** chỉ phù hợp khi nguồn thể hiện **ngày nguyên** theo đúng nghiệp vụ.

### 16.3. Ngày cực đại

Nếu end_date_inclusive = ngày lớn nhất mà DBMS có thể lưu, cộng một ngày có thể tràn. Với các miền có cận trên vô hạn, cân nhắc biểu diễn **NULL theo chính sách**, range type hoặc giá trị infinity được DBMS hỗ trợ.

## 17. Khoảng giờ địa phương, UTC và DST

Với dữ liệu thời gian có giờ, điểm khó không chỉ là SQL. Cần phân biệt:

- **Local date/time:** ngày giờ mà người dùng nhìn trên lịch ở một múi giờ.
- **Instant:** thời điểm tuyệt đối trên trục thời gian, có thể biểu diễn UTC.
- **Time zone:** quy tắc lịch sử/chuyển đổi giữa local date/time và instant.

### 17.1. Một giờ địa phương có thể không tồn tại hoặc lặp lại

Ở những múi giờ có **daylight saving time (DST)**:

- Một ngày có thể dài **23 hoặc 25 giờ**, không phải luôn 24.
- Một mốc local time có thể **không tồn tại** khi đồng hồ nhảy tới.
- Một mốc local time có thể **xảy ra hai lần** khi đồng hồ lùi.

Vì vậy, việc lấy ngày địa phương D rồi cộng **24 giờ tuyệt đối** có thể không tương đương “từ nửa đêm ngày D đến nửa đêm ngày D+1 tại múi giờ địa phương”.

### 17.2. Mẫu an toàn cho truy vấn kỳ ngày địa phương

1. Xác định **múi giờ nghiệp vụ** của báo cáo.
2. Tạo thời điểm bắt đầu của ngày D theo múi giờ đó.
3. Tạo thời điểm bắt đầu của ngày D+1 theo **cùng múi giờ đó**.
4. Chuyển hai mốc sang kiểu instant/UTC phù hợp với cột đang lưu.
5. Dùng half-open range **[start_instant, end_instant)**.

Không cố định một ngày lịch luôn có 86.400 giây.

### 17.3. TIMESTAMP không có cùng nghĩa ở mọi DBMS

- **PostgreSQL TIMESTAMP WITHOUT TIME ZONE** là ngày giờ không gắn timezone; **TIMESTAMPTZ** biểu diễn thời điểm với chuyển đổi phụ thuộc session timezone khi hiển thị.
- **SQL Server DATETIME2** không tự mang offset; **DATETIMEOFFSET** có offset.
- **MySQL TIMESTAMP** có xử lý timezone liên quan session, trong khi **DATETIME** là giá trị ngày giờ theo cách khác.
- **Oracle DATE**, **TIMESTAMP**, **TIMESTAMP WITH TIME ZONE** và **TIMESTAMP WITH LOCAL TIME ZONE** có ngữ nghĩa khác.
- **SQLite** có thể lưu ngày giờ dưới dạng TEXT/REAL/INTEGER; quy ước của ứng dụng quyết định phép so sánh thực sự.

Do đó, hai cột cùng tên **start_time/end_time** nhưng ở hai DBMS khác nhau không mặc nhiên có cùng tính chất. Khi đồng bộ, phải xác định chính xác loại giá trị được lưu và cách chuyển đổi.

## 18. As-of join: nối sự kiện với phiên bản có hiệu lực

Đây là mẫu truy vấn đặc biệt quan trọng trong kho dữ liệu, phân tích lịch sử và hệ thống điều chỉnh giá.

Giả sử:

~~~text
don_hang(
    ma_don,
    ma_san_pham,
    thoi_diem_dat,
    so_luong
)

lich_su_gia(
    ma_phien_ban,
    ma_san_pham,
    gia,
    valid_from,
    valid_to
)
~~~

Yêu cầu:

> Với mỗi đơn hàng, tìm **mức giá của sản phẩm có hiệu lực đúng tại thời điểm đặt đơn**, không phải giá hiện tại.

Truy vấn:

~~~sql
SELECT
    d.ma_don,
    d.ma_san_pham,
    d.thoi_diem_dat,
    d.so_luong,
    g.ma_phien_ban,
    g.gia
FROM don_hang d
LEFT JOIN lich_su_gia g
    ON g.ma_san_pham = d.ma_san_pham
   AND g.valid_from <= d.thoi_diem_dat
   AND (
       d.thoi_diem_dat < g.valid_to
       OR g.valid_to IS NULL
   );
~~~

Hai điều kiện ngày giờ **nằm trong ON** để LEFT JOIN vẫn giữ đơn hàng không có phiên bản giá phù hợp, cho phép phát hiện **lỗ hổng lịch sử giá**.

### 18.1. Vì sao dùng giá hiện tại là sai?

Một đơn đặt ngày 15/01 có thể cần giá **100000**, dù hôm nay giá sản phẩm đã là **110000**. JOIN theo mã sản phẩm với bảng giá hiện hành sẽ gán lại giá mới cho giao dịch cũ, làm sai báo cáo doanh thu lịch sử.

### 18.2. Vì sao LEFT JOIN có thể trả nhiều dòng cho một đơn?

Nếu cùng sản phẩm có hai phiên bản giá chồng nhau:

~~~text
Giá A: [2026-01-01, 2026-03-01)
Giá B: [2026-02-01, 2026-04-01)
~~~

thì đơn ngày 15/02 khớp **cả hai giá**, tạo **hai dòng cho một đơn**. SQL chạy đúng theo dữ liệu, nhưng dữ liệu vi phạm quy tắc “tại mỗi thời điểm chỉ có một giá hiệu lực”.

Không dùng DISTINCT hoặc MIN(gia) để che lỗi nếu nghiệp vụ yêu cầu đúng một mức giá. Cần phát hiện và sửa **khoảng hiệu lực chồng lấn**.

### 18.3. WHERE sau LEFT JOIN có thể làm mất đơn

Sai về ý định giữ mọi đơn:

~~~sql
FROM don_hang d
LEFT JOIN lich_su_gia g
    ON g.ma_san_pham = d.ma_san_pham
WHERE g.valid_from <= d.thoi_diem_dat
  AND d.thoi_diem_dat < g.valid_to
~~~

Những đơn không khớp có cột g.* NULL, nên WHERE loại chúng. Nếu cần giữ đơn chưa tìm được giá để kiểm tra, đặt điều kiện hiệu lực trong **ON** như mẫu ở trên.

## 19. SCD Type 2: khoảng hiệu lực cho phiên bản thuộc tính

Trong kho dữ liệu, **Slowly Changing Dimension Type 2 (SCD2)** thường giữ nhiều phiên bản của một đối tượng:

~~~text
ma_phien_ban (surrogate key)
ma_khach      (business key)
hang_khach
valid_from
valid_to
is_current    (tùy thiết kế)
~~~

Ví dụ:

| ma_phien_ban | ma_khach | hang_khach | valid_from | valid_to |
|---:|---|---|---|---|
| 501 | K1 | SILVER | 2026-01-01 | 2026-04-01 |
| 502 | K1 | GOLD | 2026-04-01 | NULL |
| 601 | K2 | BRONZE | 2026-02-01 | NULL |

### 19.1. Tìm trạng thái tại mốc

~~~sql
SELECT
    ma_khach,
    hang_khach
FROM dim_khach_hang
WHERE ma_khach = 'K1'
  AND valid_from <= :as_of
  AND (valid_to IS NULL OR :as_of < valid_to);
~~~

Tại 2026-03-01 trả SILVER; tại 2026-04-01 trả GOLD.

### 19.2. Phiên bản hiện hành

Nếu NULL ở valid_to = vô hạn, có thể viết:

~~~sql
SELECT *
FROM dim_khach_hang
WHERE valid_to IS NULL;
~~~

Nhưng nếu hệ thống lưu is_current, cần đảm bảo **is_current** và **valid_to** nhất quán. Không nên có hai dòng is_current=TRUE cùng business key nếu yêu cầu chỉ một phiên bản hiện hành.

### 19.3. Cập nhật SCD2

Khi khách K1 chuyển SILVER → GOLD tại thời điểm T:

1. Đóng bản ghi cũ: **valid_to = T**.
2. Thêm bản ghi mới: **valid_from = T, valid_to = NULL**.
3. Thực hiện trong một giao dịch phù hợp.
4. Bảo đảm không có gap/overlap ngoài chủ đích.

Khoảng cũ **[from,T)** và mới **[T,∞)** chạm nhau mà không giao. Các báo cáo **as-of T** chỉ chọn bản mới.

**Lưu ý về dữ liệu đến muộn:** nếu thay đổi thuộc tính có hiệu lực từ một ngày trong quá khứ, có thể cần chia lại một khoảng cũ thành các đoạn; không chỉ đóng bản hiện hành theo thời điểm hệ thống nhận dữ liệu.

## 20. Phát hiện hai khoảng hiệu lực chồng nhau

Giả sử bảng:

~~~text
lich_su_gia(
    ma_phien_ban PRIMARY KEY,
    ma_san_pham,
    valid_from NOT NULL,
    valid_to NULLABLE,
    gia
)
~~~

Cần tìm những cặp phiên bản **cùng sản phẩm** có giao thời gian, với valid_to NULL = +infinity.

~~~sql
SELECT
    a.ma_san_pham,
    a.ma_phien_ban AS ban_a,
    b.ma_phien_ban AS ban_b,
    a.valid_from AS tu_a,
    a.valid_to AS den_a,
    b.valid_from AS tu_b,
    b.valid_to AS den_b
FROM lich_su_gia a
JOIN lich_su_gia b
    ON a.ma_san_pham = b.ma_san_pham
   AND a.ma_phien_ban < b.ma_phien_ban
   AND (
       a.valid_to IS NULL
       OR b.valid_from < a.valid_to
   )
   AND (
       b.valid_to IS NULL
       OR a.valid_from < b.valid_to
   )
ORDER BY a.ma_san_pham, ban_a, ban_b;
~~~

Giải thích:

- **a.ma_san_pham = b.ma_san_pham**: chỉ so phiên bản của cùng sản phẩm.
- **a.ma_phien_ban < b.ma_phien_ban**: tránh ghép một dòng với chính nó và tránh trả cả (a,b) lẫn (b,a).
- Hai nhóm điều kiện còn lại: predicate giao của hai khoảng có end NULL nghĩa vô hạn.

Điều kiện ma_phien_ban < ... giả định ID so sánh được và là **khóa duy nhất**. Nếu khóa là UUID hoặc một kiểu có đặc tính khác, có thể chọn một cách đánh số cặp phù hợp DBMS.

### 20.1. Đếm số cặp xung đột

~~~sql
WITH cap_trung AS (
    SELECT a.ma_san_pham
    FROM lich_su_gia a
    JOIN lich_su_gia b
      ON a.ma_san_pham = b.ma_san_pham
     AND a.ma_phien_ban < b.ma_phien_ban
     AND (a.valid_to IS NULL OR b.valid_from < a.valid_to)
     AND (b.valid_to IS NULL OR a.valid_from < b.valid_to)
)
SELECT
    ma_san_pham,
    COUNT(*) AS so_cap_trung
FROM cap_trung
GROUP BY ma_san_pham;
~~~

**COUNT(*) là số cặp xung đột**, không nhất thiết là số phiên bản lỗi. Ba phiên bản cùng chồng nhau có thể tạo ba cặp; cần chọn chỉ số phù hợp báo cáo.

### 20.2. Tìm bản ghi xung đột bằng EXISTS

~~~sql
SELECT a.*
FROM lich_su_gia a
WHERE EXISTS (
    SELECT 1
    FROM lich_su_gia b
    WHERE b.ma_san_pham = a.ma_san_pham
      AND b.ma_phien_ban <> a.ma_phien_ban
      AND (a.valid_to IS NULL OR b.valid_from < a.valid_to)
      AND (b.valid_to IS NULL OR a.valid_from < b.valid_to)
);
~~~

Truy vấn trả **mỗi bản ghi A tối đa một lần** (theo nguồn), dù nó chồng lên nhiều phiên bản B. Đây là mẫu phù hợp để lấy danh sách các bản ghi cần điều tra.

## 21. Tìm khoảng hiệu lực bị thiếu (gaps)

Một lịch sử hợp lệ có thể có:

~~~text
P01: [01/01,01/02)
     [01/02,15/03)
     [15/03,+∞)
~~~

Các khoảng nối liên tục, không có gap.

Nhưng:

~~~text
P02: [01/01,01/02)
     [10/02,01/03)
~~~

có gap **[01/02,10/02)**.

### 21.1. Phát hiện gap bằng LEAD

Nếu đã biết các khoảng của **mỗi sản phẩm không chồng lên nhau**, sắp theo valid_from và nhìn điểm bắt đầu kế tiếp:

~~~sql
WITH co_ky_tiep_theo AS (
    SELECT
        ma_san_pham,
        valid_from,
        valid_to,
        LEAD(valid_from) OVER (
            PARTITION BY ma_san_pham
            ORDER BY valid_from, ma_phien_ban
        ) AS next_from
    FROM lich_su_gia
)
SELECT
    ma_san_pham,
    valid_to AS gap_from,
    next_from AS gap_to
FROM co_ky_tiep_theo
WHERE valid_to IS NOT NULL
  AND next_from IS NOT NULL
  AND valid_to < next_from;
~~~

Kết quả cho P02 sẽ báo **gap_from = 01/02** và **gap_to = 10/02**.

### 21.2. LEAD đơn giản có giới hạn

Nếu dữ liệu có khoảng **lồng nhau** hoặc **chồng chéo**, so valid_to của dòng hiện tại với next_from chưa phản ánh “điểm phủ xa nhất” của các khoảng đã gặp. Ví dụ:

~~~text
A = [01/01,01/12)
B = [01/02,01/03)
C = [01/04,01/05)
~~~

B kết thúc 01/03 trước khi C bắt đầu 01/04, nên LEAD có thể báo một gap giả [01/03,01/04), dù A vẫn phủ liên tục toàn bộ khoảng đó.

Khi dữ liệu có overlap/lồng nhau, cần dùng **running maximum của end** hoặc **gộp các khoảng** trước, rồi mới tìm gap. Đó là lý do không nên dùng LEAD đơn giản làm bộ kiểm tra hoàn chỉnh cho mọi dữ liệu bẩn.

## 22. Gộp các khoảng giao nhau: interval islands

Một bài toán nâng cao là hợp nhất những khoảng chồng hoặc chạm để tạo các đoạn liên tục.

Ví dụ:

~~~text
[10:00,12:00)
[11:00,13:00)
[13:00,14:00)
[16:00,17:00)
~~~

Nếu coi **chạm là nối liên tục**, các đoạn gộp là:

~~~text
[10:00,14:00)
[16:00,17:00)
~~~

### 22.1. Vì sao không chỉ nhìn end của dòng ngay trước?

Cho:

~~~text
A [10:00,20:00)
B [11:00,12:00)
C [13:00,14:00)
~~~

B và C không giao nhau, nhưng cả hai đều nằm trong A. Nếu chỉ dùng **LAG(end)**, dòng C có thể nhìn end 12:00 của B và bị tách sai thành nhóm mới, dù toàn bộ tập A,B,C liên tục.

Cần biết **end lớn nhất của mọi dòng trước đó**.

### 22.2. Mẫu gộp interval bằng window functions

Giả sử bảng **khoang_phu** có:

~~~text
ma_doi_tuong, ma_khoang, bat_dau, ket_thuc
~~~

và mỗi khoảng hữu hạn, có độ dài dương. Một truy vấn dùng window functions:

~~~sql
WITH sap_xep AS (
    SELECT
        k.*,
        MAX(ket_thuc) OVER (
            PARTITION BY ma_doi_tuong
            ORDER BY bat_dau, ket_thuc, ma_khoang
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND 1 PRECEDING
        ) AS end_lon_nhat_truoc
    FROM khoang_phu k
),
danh_dau AS (
    SELECT
        *,
        CASE
            WHEN end_lon_nhat_truoc IS NULL THEN 1
            WHEN bat_dau > end_lon_nhat_truoc THEN 1
            ELSE 0
        END AS bat_dau_dao_moi
    FROM sap_xep
),
gan_nhom AS (
    SELECT
        *,
        SUM(bat_dau_dao_moi) OVER (
            PARTITION BY ma_doi_tuong
            ORDER BY bat_dau, ket_thuc, ma_khoang
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ) AS ma_dao
    FROM danh_dau
)
SELECT
    ma_doi_tuong,
    ma_dao,
    MIN(bat_dau) AS tu,
    MAX(ket_thuc) AS den
FROM gan_nhom
GROUP BY ma_doi_tuong, ma_dao
ORDER BY ma_doi_tuong, tu;
~~~

Giải thích:

1. **sap_xep** lấy **cận cuối lớn nhất trước dòng hiện tại** theo thứ tự start.
2. **danh_dau** đánh dấu đảo mới nếu **bat_dau > end_lon_nhat_truoc**: dòng bắt đầu sau toàn bộ vùng phủ cũ, có gap.
3. **gan_nhom** cộng dồn số lần bắt đầu đảo để tạo mã nhóm.
4. SELECT cuối gộp mỗi nhóm bằng MIN(start) và MAX(end).

Với điều kiện **bat_dau > end_lon_nhat_truoc**, hai khoảng **chạm nhau** được gộp thành một đoạn liên tục. Nếu chỉ muốn gộp những khoảng **giao thực sự**, không gộp chạm, cân nhắc điều kiện **bat_dau >= end_lon_nhat_truoc**; điều này thay đổi ngữ nghĩa kết quả.

**Phạm vi áp dụng:** ví dụ dành cho các hệ hỗ trợ window frames ở dạng này và các khoảng **end NOT NULL**. Với end NULL = vô hạn, cần xử lý riêng để running max không bị biến mất do MAX bỏ qua NULL. Cách gộp cũng cần có khóa phá hòa và dữ liệu start/end hợp lệ.

## 23. Tìm thời gian rảnh trong một khung đặt chỗ

Giả sử phòng A mở cửa từ **09:00 đến 18:00**, có các đặt chỗ:

~~~text
[10:00,12:00)
[12:00,14:00)
[15:00,17:00)
~~~

Nếu gộp các khoảng chạm nhau, thời gian bận là:

~~~text
[10:00,14:00)
[15:00,17:00)
~~~

Trong khung mở cửa **[09:00,18:00)**, các khoảng rảnh:

~~~text
[09:00,10:00)
[14:00,15:00)
[17:00,18:00)
~~~

### 23.1. Quy trình tổng quát

1. Lọc lịch **CONFIRMED** giao với khung giờ mở cửa.
2. **Cắt** mỗi lịch theo [open_start,open_end) để không đưa ra thời gian ngoài khung.
3. Gộp các lịch giao/chạm thành những đảo bận không chồng nhau.
4. Sắp các đảo bận theo start.
5. Tạo khoảng rảnh giữa **open_start → đảo đầu**, **end đảo trước → start đảo sau**, **end đảo cuối → open_end**.
6. Chỉ giữ những khoảng có **start < end**.

### 23.2. Không suy ra thời gian rảnh từ lịch chưa gộp

Nếu hai lịch chồng nhau, lấy LAG(end) trực tiếp có thể tạo một khoảng rảnh giả bên trong lịch dài. Vì vậy, muốn tìm **khoảng rảnh chính xác**, phải xử lý vùng phủ (interval union) trước.

### 23.3. Truy vấn tìm mọi lịch giao với khung

Đây là bước đầu tiên có thể tái sử dụng:

~~~sql
SELECT ma_lich, bat_dau, ket_thuc
FROM lich_dat_phong
WHERE ma_phong = :room
  AND trang_thai = 'CONFIRMED'
  AND bat_dau < :open_end
  AND :open_start < ket_thuc;
~~~

Các bước cắt và gộp tùy khả năng DBMS. Một ứng dụng có thể làm các bước cuối tại SQL hoặc ở tầng dịch vụ sau khi nhận dữ liệu đã được sắp và bảo đảm nhất quán; phải tránh lệch ngữ nghĩa giữa các lớp.

## 24. Tính số lịch giao nhau và mức độ sử dụng

Muốn đếm có bao nhiêu lịch giao với một kỳ:

~~~sql
SELECT
    ma_phong,
    COUNT(*) AS so_lich_co_giao
FROM lich_dat_phong
WHERE trang_thai = 'CONFIRMED'
  AND bat_dau < :period_end
  AND :period_start < ket_thuc
GROUP BY ma_phong;
~~~

Đây là **số bản ghi lịch có giao**, không phải số giờ phòng bị bận.

### 24.1. SUM thời lượng giao có thể đếm đôi

Nếu các lịch trong cùng phòng **có overlap**, cộng thời lượng phần giao từng lịch với kỳ có thể **đếm đôi** vùng thời gian bị chiếm đồng thời.

Ví dụ:

~~~text
Lịch 1: [10:00,12:00) = 2 giờ
Lịch 2: [11:00,13:00) = 2 giờ
~~~

Tổng từng lịch = 4 giờ, nhưng hợp vùng bận [10:00,13:00) chỉ dài **3 giờ**.

Muốn tính tỷ lệ sử dụng phòng theo **thời gian thực tế bận**, cần **gộp các khoảng đã cắt theo kỳ** rồi cộng độ dài các đảo không chồng nhau.

Nếu nghiệp vụ lại muốn **tổng giờ đặt theo số lượt thuê** (mỗi lịch tính riêng), cộng 4 giờ có thể đúng. Phải xác định chỉ số trước khi viết SUM.

## 25. Điều kiện giao nhau trong JOIN giữa hai bảng

Giả sử có bảng **ca_lam** và **su_kien**; cần tìm các sự kiện chạm vào ca làm.

~~~sql
SELECT
    c.ma_ca,
    e.ma_su_kien,
    c.bat_dau AS ca_tu,
    c.ket_thuc AS ca_den,
    e.bat_dau AS su_kien_tu,
    e.ket_thuc AS su_kien_den
FROM ca_lam c
JOIN su_kien e
    ON c.ma_nhan_vien = e.ma_nhan_vien
   AND c.bat_dau < e.ket_thuc
   AND e.bat_dau < c.ket_thuc;
~~~

Điều kiện giao nằm trong **ON** vì nó định nghĩa cặp ca–sự kiện hợp lệ.

### 25.1. Một sự kiện có thể giao nhiều ca

Một sự kiện từ 11:00 đến 15:00 có thể giao ca sáng và ca chiều. JOIN sẽ trả **hai dòng cho một sự kiện** nếu hai ca đều giao, không phải lỗi SQL. Nếu muốn tổng giờ theo nhân viên phải chú ý ca có chồng nhau hay không.

### 25.2. LEFT JOIN giữ sự kiện không có ca

~~~sql
SELECT
    e.ma_su_kien,
    c.ma_ca
FROM su_kien e
LEFT JOIN ca_lam c
    ON c.ma_nhan_vien = e.ma_nhan_vien
   AND c.bat_dau < e.ket_thuc
   AND e.bat_dau < c.ket_thuc;
~~~

Nếu cần tìm sự kiện **không giao ca nào**, có thể thêm:

~~~sql
WHERE c.ma_ca IS NULL
~~~

với giả định **c.ma_ca là khóa NOT NULL của ca thật**. Không kiểm tra một cột ca có thể NULL tùy ý vì có thể phân loại sai dòng ca thật.

## 26. Anti-join: tìm các khoảng không giao với bất kỳ khoảng nào

Nếu yêu cầu là “những lịch đề xuất không giao với lịch CONFIRMED nào của cùng phòng”, dùng **NOT EXISTS**:

~~~sql
SELECT d.*
FROM de_xuat_lich d
WHERE NOT EXISTS (
    SELECT 1
    FROM lich_dat_phong l
    WHERE l.ma_phong = d.ma_phong
      AND l.trang_thai = 'CONFIRMED'
      AND l.bat_dau < d.ket_thuc
      AND d.bat_dau < l.ket_thuc
);
~~~

Mỗi dòng đề xuất chỉ được giữ nếu **không có bất kỳ lịch nào giao**. NOT EXISTS không nhân dòng đề xuất dù phòng có nhiều lịch đang bận.

### 26.1. Cần kiểm tra đề xuất hợp lệ

Nếu de_xuat_lich chứa start >= end, NOT EXISTS có thể cho kết quả đánh lừa. Nên validate các khoảng trước khi kiểm tra:

~~~sql
WHERE d.bat_dau IS NOT NULL
  AND d.ket_thuc IS NOT NULL
  AND d.bat_dau < d.ket_thuc
  AND NOT EXISTS (...)
~~~

Trong câu SQL thật, thay dấu **(...)** bằng subquery đầy đủ. Đây là ý tưởng bổ sung để nhấn mạnh kiểm tra dữ liệu đầu vào, không phải một câu hoàn chỉnh có thể chạy nguyên văn.

## 27. PostgreSQL: range types và toán tử thời gian

PostgreSQL có hệ kiểu **range** giúp lưu khoảng như một giá trị:

- **daterange**: khoảng DATE.
- **tsrange**: khoảng TIMESTAMP WITHOUT TIME ZONE.
- **tstzrange**: khoảng TIMESTAMP WITH TIME ZONE.
- Những range types khác cho số nguyên/số, cùng multirange types ở các phiên bản hỗ trợ.

Một khoảng:

~~~sql
tstzrange(
    '2026-04-10 10:00+07'::timestamptz,
    '2026-04-10 12:00+07'::timestamptz,
    '[)'
)
~~~

được tạo với cận trái **bao gồm** và cận phải **loại trừ**.

### 27.1. Kiểm tra overlap bằng &&

Giả sử bảng lưu:

~~~sql
CREATE TABLE lich_dat_phong_pg (
    ma_lich BIGINT PRIMARY KEY,
    ma_phong TEXT NOT NULL,
    khoang_gio TSTZRANGE NOT NULL
);
~~~

Truy vấn tìm khoảng giao:

~~~sql
SELECT ma_lich, ma_phong
FROM lich_dat_phong_pg
WHERE ma_phong = 'A'
  AND khoang_gio && tstzrange(
      '2026-04-10 11:30+07'::timestamptz,
      '2026-04-10 12:30+07'::timestamptz,
      '[)'
  );
~~~

Toán tử **&&** hỏi hai range có overlap không theo ngữ nghĩa biên của từng range.

### 27.2. Những toán tử range hữu ích

| Toán tử | Ý tưởng |
|---|---|
| **&&** | Hai range giao nhau |
| **@>** | Range bên trái chứa phần tử hoặc range bên phải |
| **<@** | Phần tử/range bên trái nằm trong range bên phải |
| **-|-** | Hai range liền kề (adjacent) |
| **<<** | Range trái nằm hoàn toàn trước range phải |
| **>>** | Range trái nằm hoàn toàn sau range phải |

Khả năng dùng toán tử cụ thể phụ thuộc kiểu range và thứ tự đối số. Với range rỗng, vô hạn hoặc cận khác loại, PostgreSQL áp dụng quy tắc kiểu range; không suy diễn một cách máy móc từ cột start/end.

### 27.3. Khoảng vô hạn và khoảng rỗng

PostgreSQL range có thể biểu diễn cận không giới hạn mà không cần dùng một timestamp sentinel. Ví dụ ý tưởng:

~~~sql
tstzrange(
    '2026-03-15 00:00+07'::timestamptz,
    NULL,
    '[)'
)
~~~

khoảng có **cận dưới hữu hạn** và **không có cận trên**.

Các hàm như **lower()**, **upper()**, **isempty()**, **lower_inf()**, **upper_inf()** giúp kiểm tra đặc tính của range. Hãy phân biệt **unbounded range** với một phần tử thời gian chứa literal infinity đặc thù PostgreSQL: chúng có ngữ nghĩa riêng về cận và bao gồm/loại trừ.

### 27.4. daterange và tính liên tục ngày

PostgreSQL **daterange** dùng miền ngày rời rạc, có quy tắc chuẩn hóa dạng khoảng canonical thích hợp. Với ứng dụng lưu ngày bắt đầu bao gồm và ngày kết thúc loại trừ, [) là lựa chọn tự nhiên.

Không sao chép kết quả canonicalization của daterange sang tsrange: timestamp là một miền khác về độ phân giải và tính rời rạc/ liên tục.

## 28. PostgreSQL: bảo đảm không đặt trùng bằng exclusion constraint

Một câu SELECT kiểm tra xung đột có thể chạy đúng nhưng **không chặn race condition** giữa hai giao dịch.

PostgreSQL hỗ trợ **exclusion constraint** kết hợp range overlap để ràng buộc:

> Không được có hai dòng cùng phòng mà khoảng thời gian giao nhau.

Ví dụ ý tưởng cho bảng có khoang_gio TSTZRANGE:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE dat_phong_khong_trung (
    ma_lich BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_phong TEXT NOT NULL,
    khoang_gio TSTZRANGE NOT NULL,
    CONSTRAINT ck_khong_rong CHECK (NOT isempty(khoang_gio)),
    CONSTRAINT khong_dat_trung
        EXCLUDE USING gist (
            ma_phong WITH =,
            khoang_gio WITH &&
        )
);
~~~

Giải thích:

- **ma_phong WITH =**: kiểm tra cùng phòng.
- **khoang_gio WITH &&**: kiểm tra khoảng giao.
- Exclusion constraint ngăn hai dòng đồng thời vi phạm cả hai điều kiện, do đó ngăn overlap theo điều kiện đã định nghĩa.
- **btree_gist** cung cấp hỗ trợ GiST cho toán tử bằng trên những kiểu thông dụng như TEXT trong cách viết này.

**Lưu ý:** ví dụ không có cột trạng thái. Nếu chỉ các lịch **CONFIRMED** được coi là giữ chỗ, cần thiết kế constraint **chỉ áp dụng các dòng confirmed** (ví dụ partial exclusion constraint theo khả năng PostgreSQL) hoặc tách bảng giữ chỗ thực tế khỏi lịch hủy. Cũng cần kiểm tra quyền tạo extension, kiểu dữ liệu, trạng thái giao dịch và hành vi xóa/sửa.

### 28.1. Chỉ mục GiST phục vụ truy vấn overlap

PostgreSQL có thể dùng chỉ mục GiST cho range, ví dụ:

~~~sql
CREATE INDEX idx_dat_phong_khoang_gio
ON lich_dat_phong_pg
USING gist (khoang_gio);
~~~

Với truy vấn thường lọc cả phòng và khoảng, có thể cân nhắc chỉ mục GiST nhiều cột hoặc thiết kế chỉ mục kết hợp phù hợp. Nên đo bằng EXPLAIN trên dữ liệu thật, không mặc định GiST luôn nhanh hơn B-tree cho mọi trường hợp.

### 28.2. Ràng buộc chống overlap thay đổi theo yêu cầu

Nếu nghiệp vụ muốn **hai khoảng chạm nhau được phép**, range [) với toán tử && phù hợp. Nếu muốn cả chạm biên cũng bị coi là vi phạm (ví dụ bắt buộc có thời gian dọn phòng), cần sửa mô hình: mở rộng khoảng giữ chỗ theo thời gian chuẩn bị/cleanup hoặc dùng quy tắc quan hệ khác; không chỉ đổi ngẫu nhiên ký hiệu cận mà không xem xét.

## 29. SQL Server: khoảng hiệu lực tự xây và system-versioned temporal tables

Trong SQL Server, mẫu hai cột **valid_from/valid_to** có thể viết bằng T-SQL thông thường:

~~~sql
SELECT *
FROM lich_su_gia
WHERE ma_san_pham = @ma
  AND valid_from <= @as_of
  AND (@as_of < valid_to OR valid_to IS NULL);
~~~

Đây là **business valid time** do ứng dụng định nghĩa.

SQL Server còn có **system-versioned temporal tables**, ghi lại lịch sử dòng theo **system time** do cơ sở dữ liệu quản lý. Cú pháp truy vấn phổ biến:

~~~sql
SELECT *
FROM dbo.BangLichSu
FOR SYSTEM_TIME AS OF @as_of;
~~~

Tuy nhiên, **system time khác business valid time**:

- **System time:** thời gian phiên bản được hệ thống cơ sở dữ liệu ghi nhận/duy trì.
- **Business valid time:** thời gian mà bản giá, hợp đồng hoặc trạng thái **có hiệu lực trong thế giới nghiệp vụ**.

Một giá sửa hôm nay nhưng có hiệu lực từ tháng trước là ví dụ hai trục thời gian khác nhau. Không dùng **FOR SYSTEM_TIME AS OF** thay cho truy vấn business valid_from/valid_to nếu hai ý nghĩa không trùng nhau.

### 29.1. Độ chính xác và kiểu dữ liệu

SQL Server có DATETIME, DATETIME2 và DATETIMEOFFSET với độ chính xác/ngữ nghĩa khác nhau. Để thực hiện khoảng half-open, nên thống nhất kiểu **tham số** và **cột** (thường DATETIME2 hoặc DATETIMEOFFSET theo mô hình) thay vì ép kiểu ngầm tùy tiện.

### 29.2. Ràng buộc không overlap

SQL Server thông thường không có một cú pháp exclusion constraint PostgreSQL tương đương trực tiếp cho hai cột thời gian. Thường phải thiết kế **giao dịch, khóa phạm vi, chỉ mục, isolation level và logic kiểm tra** phù hợp, hoặc một mô hình slot/unique constraint khác.

Không được xem **SELECT kiểm tra rồi INSERT** trong transaction mặc định là đủ ngăn hai phiên đồng thời đặt chỗ. Phần concurrency ở sau giải thích.

## 30. Oracle Database: business validity và lịch sử

Trên Oracle, một khoảng hiệu lực tự quản lý vẫn có thể dùng predicate chuẩn:

~~~sql
SELECT *
FROM lich_su_gia
WHERE ma_san_pham = :ma
  AND valid_from <= :as_of
  AND (:as_of < valid_to OR valid_to IS NULL);
~~~

Oracle cũng có tính năng liên quan tới **temporal validity** với khai báo period/valid-time ở các phiên bản hỗ trợ và **Flashback Query** cho một số nhu cầu xem lại dữ liệu theo thời gian hệ thống. Chúng không phải cùng một khái niệm:

- Temporal validity mô hình hóa **khoảng nghiệp vụ** được khai báo.
- Flashback Query/Flashback Version Query chủ yếu liên quan lịch sử dữ liệu theo thời gian hệ thống và khả năng lưu giữ cần thiết.
- Validity period của ứng dụng có thể khác thời điểm dòng được INSERT/UPDATE.

Cú pháp cụ thể như **PERIOD FOR**, **AS OF PERIOD FOR** hoặc **VERSIONS BETWEEN** cần đối chiếu với đúng bản Oracle và kiểu dữ liệu được hỗ trợ.

### 30.1. Lưu ý DATE trong Oracle

Oracle **DATE** bao gồm thành phần giờ/phút/giây, khác một số DBMS mà DATE chỉ biểu diễn ngày lịch. Khi dùng cột Oracle DATE làm start/end và viết:

~~~sql
valid_from <= :t
AND :t < valid_to
~~~

hãy xác định liệu cột thực sự lưu ngày ở 00:00 hay có thời gian trong ngày. Một nhãn “DATE” không bảo đảm dữ liệu chỉ có ngày nguyên.

## 31. MySQL và SQLite: dùng hai cột thời gian rõ ràng

MySQL và SQLite có thể biểu diễn khoảng bằng start/end và dùng predicate bất đẳng thức như ở phần 4.

### 31.1. MySQL

~~~sql
SELECT
    ma_lich,
    ma_phong
FROM lich_dat_phong
WHERE ma_phong = ?
  AND trang_thai = 'CONFIRMED'
  AND bat_dau < ?
  AND ? < ket_thuc;
~~~

Với SCD/as-of, thêm điều kiện valid_to IS NULL khi NULL biểu thị +infinity.

MySQL có khác biệt giữa **DATETIME** và **TIMESTAMP** khi làm việc với session timezone; cần kiểm tra kiểu và cách bind tham số qua driver. Không nên ép kiểu cột start/end thành DATE trong điều kiện overlap nếu nhu cầu là timestamp chính xác vì có thể thay đổi ngữ nghĩa và ảnh hưởng chỉ mục.

### 31.2. SQLite

SQLite không có một kiểu TIMESTAMP native cố định như một số RDBMS. Ngày giờ có thể được lưu bằng **TEXT ISO-8601**, **INTEGER epoch**, hoặc **REAL Julian day** theo quy ước.

Ví dụ nếu dùng TEXT chuẩn hóa dạng thời gian UTC với độ rộng và định dạng nhất quán:

~~~sql
SELECT *
FROM lich_dat_phong
WHERE ma_phong = ?
  AND bat_dau < ?
  AND ? < ket_thuc;
~~~

Phép so sánh chuỗi có thể phản ánh thứ tự thời gian nếu **tất cả** giá trị thực sự ở cùng dạng ISO chuẩn hóa và cùng múi giờ. Không dùng phép so sánh từ điển tùy ý giữa các chuỗi khác định dạng, khác offset hoặc thiếu số 0.

### 31.3. Cần tự thiết kế bảo vệ concurrency

Ở những DBMS không có range/exclusion constraint phù hợp, cần giao dịch và chiến lược kiểm soát ghi thích hợp, thay vì nghĩ rằng predicate đúng là đủ. Mức isolation và cách khóa phạm vi khác nhau; một công thức áp dụng cho PostgreSQL không thể chuyển nguyên văn sang SQLite hoặc MySQL.

## 32. Đặt chỗ đồng thời: vấn đề race condition

Giả sử hai người đặt **cùng phòng A** cho cùng khoảng **[11:00,12:00)**.

Một quy trình không an toàn:

~~~text
Giao dịch T1: SELECT xung đột -> không có
Giao dịch T2: SELECT xung đột -> không có
Giao dịch T1: INSERT lịch A
Giao dịch T2: INSERT lịch B
Cả hai COMMIT
~~~

Nếu không có constraint/khóa phù hợp, cả hai lịch có thể được ghi thành công dù giao nhau. Điều kiện SQL tìm overlap hoàn toàn đúng nhưng **không bảo vệ thao tác ghi đồng thời**.

### 32.1. Các hướng bảo vệ

Tùy hệ quản trị:

1. **Ràng buộc tại DBMS:** ví dụ PostgreSQL exclusion constraint trên room + range.
2. **Khóa một tài nguyên đại diện:** lock dòng phòng, hoặc một dòng quản lý duy nhất cho mỗi phòng trước khi kiểm tra và chèn, với transaction phù hợp.
3. **Serializable isolation** hoặc chiến lược khóa phạm vi hỗ trợ, cộng cơ chế retry khi phát sinh xung đột serialization/deadlock.
4. **Mô hình slot cố định có UNIQUE** nếu nghiệp vụ thực sự chia phòng thành các slot rời rạc cố định; không dùng slot tùy tiện khi cho phép khoảng bất kỳ.
5. **Một dịch vụ đặt chỗ tuần tự hóa theo phòng** khi kiến trúc cho phép và vẫn có biện pháp bảo đảm dữ liệu bền vững.

Mỗi lựa chọn có trade-off về throughput, deadlock, số lượng phòng, độ dài khoảng và khả năng mở rộng.

### 32.2. Tại sao chỉ thêm FOR UPDATE lên các lịch xung đột chưa đủ?

Nếu **chưa có lịch nào giao**, câu SELECT tìm lịch xung đột có thể trả **0 dòng**, tức **không có dòng nào để khóa**. Hai giao dịch có thể cùng thấy tập rỗng. Để ngăn xung đột phải khóa **phạm vi/đối tượng điều phối** hoặc dùng constraint/serialization có hiệu lực theo DBMS.

### 32.3. Cập nhật lịch cũng phải được bảo vệ

Không chỉ INSERT mới tạo overlap. Một lịch có thể được dời từ [14:00,15:00) sang [11:00,12:00), hoặc được chuyển từ CANCELLED sang CONFIRMED. Quy tắc bảo vệ cần áp dụng cho cả **UPDATE trạng thái**, **UPDATE start/end**, thay đổi phòng và các đường ghi dữ liệu khác.

## 33. Chỉ mục và hiệu năng truy vấn overlap

Predicate:

~~~sql
WHERE ma_phong = ?
  AND bat_dau < ?
  AND ? < ket_thuc
~~~

có thể xử lý lượng dữ liệu lớn. Hướng cơ bản là có chỉ mục trên phòng và các mốc thời gian:

~~~sql
CREATE INDEX idx_lich_phong_bat_dau
ON lich_dat_phong (ma_phong, bat_dau);
~~~

hoặc một chỉ mục phù hợp với cách truy vấn/DBMS:

~~~sql
CREATE INDEX idx_lich_phong_ket_thuc
ON lich_dat_phong (ma_phong, ket_thuc);
~~~

### 33.1. B-tree không tối ưu mọi điều kiện hai chiều

Một chỉ mục B-tree nhiều cột có thể giúp lọc theo phòng và một mốc trước/sau, nhưng **không bảo đảm loại bỏ hoàn toàn** các dòng khi cả start và end đều có điều kiện bất đẳng thức. Bộ tối ưu phải chọn chiến lược dựa trên phân phối dữ liệu.

### 33.2. Tránh hàm trên cột khi không cần thiết

Không nên viết:

~~~sql
WHERE DATE(bat_dau) = :ngay
~~~

để tìm những lịch giao một ngày: vừa có thể bỏ sót lịch bắt đầu hôm trước, vừa đặt hàm trên cột và có thể ảnh hưởng khả năng dùng chỉ mục.

Dùng mốc ngày:

~~~sql
WHERE bat_dau < :ngay_hom_sau
  AND :ngay_bat_dau < ket_thuc
~~~

vừa đúng ý định giao với ngày vừa tránh biến đổi bat_dau trong predicate cơ bản.

### 33.3. Phân vùng theo thời gian

Với bảng hàng trăm triệu bản ghi, có thể phân vùng theo thời gian, phòng hoặc tenant. Nhưng khoảng có thể **vắt qua ranh giới partition**; nếu phân vùng theo start_time rồi chỉ truy vấn partition chứa :query_start, bạn có thể bỏ sót lịch bắt đầu rất lâu trước đó nhưng còn hiệu lực.

Phân vùng là chiến lược tổ chức dữ liệu, không thay thế công thức overlap.

### 33.4. Cần đo kế hoạch thực thi

- PostgreSQL: EXPLAIN/EXPLAIN ANALYZE, xem GiST/B-tree.
- SQL Server: execution plan, đánh giá seek/scan, cardinality.
- MySQL: EXPLAIN và thống kê/index usage.
- Oracle: DBMS_XPLAN/execution plan.
- SQLite: EXPLAIN QUERY PLAN.

Đừng thay bất đẳng thức < bằng BETWEEN hay phép so sánh khác chỉ để kế hoạch “trông tốt hơn” nếu kết quả sai nghiệp vụ.

## 34. Khoảng hiệu lực và dữ liệu nhiều tenant

Giả sử hai doanh nghiệp khác nhau cùng có mã sản phẩm P01. Khóa lịch sử phải gồm **tenant_id + ma_san_pham**.

Sai:

~~~sql
SELECT d.ma_don, g.gia
FROM don_hang d
JOIN lich_su_gia g
    ON g.ma_san_pham = d.ma_san_pham
   AND g.valid_from <= d.thoi_diem_dat
   AND (g.valid_to IS NULL OR d.thoi_diem_dat < g.valid_to);
~~~

Nếu hai tenant cùng mã P01 có giá khác nhau, đơn của tenant A có thể khớp giá tenant B, gây sai dữ liệu và rủi ro phân tách tenant.

Đúng về khóa quan hệ:

~~~sql
ON g.tenant_id = d.tenant_id
AND g.ma_san_pham = d.ma_san_pham
AND g.valid_from <= d.thoi_diem_dat
AND (g.valid_to IS NULL OR d.thoi_diem_dat < g.valid_to)
~~~

Tương tự, khi phát hiện khoảng chồng lấn của cùng thực thể, phải so theo **toàn bộ khóa nghiệp vụ**: tenant, sản phẩm, đơn vị tiền, kênh bán hoặc những thuộc tính thực sự định danh miền hiệu lực. Không bỏ qua một chiều khóa chỉ vì dữ liệu thử chưa có mã trùng.

## 35. Hai trục thời gian: business time và system time

Trong những hệ thống cần kiểm toán, một bản ghi có thể có **hai khoảng khác nhau**:

1. **Business/valid time:** khi sự thật nghiệp vụ có hiệu lực.
2. **System/transaction time:** khi cơ sở dữ liệu đã biết hoặc ghi nhận sự thật đó.

Ví dụ:

~~~text
Ngày 10/03: hệ thống biết khách K1 là GOLD từ 01/03.
Ngày 20/03: phát hiện thực tế K1 là GOLD từ 15/02.
~~~

Tại thời điểm 12/03, “hệ thống lúc đó tin gì?” và “bây giờ biết sự thật hiệu lực ngày 12/03 là gì?” có thể cho kết quả khác.

### 35.1. Mô hình bitemporal minh họa

~~~text
ma_khach
trang_thai
valid_from
valid_to
system_from
system_to
~~~

Muốn xem trạng thái có hiệu lực tại thời điểm nghiệp vụ **:v** theo kiến thức hệ thống tại thời điểm **:s**, cần lọc trên **cả hai trục**:

~~~sql
WHERE valid_from <= :v
  AND (:v < valid_to OR valid_to IS NULL)
  AND system_from <= :s
  AND (:s < system_to OR system_to IS NULL)
~~~

Điều này giả định cả hai trục được lưu half-open, NULL cận trên nghĩa vô hạn và không có overlap sai. Trong thực tế, cách DBMS quản lý system time có thể khác; nếu là SQL Server system-versioned temporal table, dùng cú pháp hệ thống phù hợp.

### 35.2. Không trộn hai ý nghĩa

Một câu “lấy bản ghi tại ngày 01/03” có thể chưa đủ. Cần hỏi:

- “Có hiệu lực trong thế giới nghiệp vụ ngày 01/03?”
- Hay “được hệ thống lưu/biết ở thời điểm 01/03?”
- Hay “cả hai”?

Đây là lý do tên cột **created_at/updated_at** không thể thay thế trực tiếp **valid_from/valid_to**.

## 36. Thiết kế tính toàn vẹn cho khoảng hiệu lực

Một bảng lịch sử giá đúng không chỉ cần CHECK(start < end). Nếu mỗi sản phẩm chỉ được có **một giá tại một thời điểm**, còn cần đảm bảo:

- Khóa phiên bản là duy nhất.
- Business key có đầy đủ các thuộc tính miền.
- valid_from NOT NULL (nếu quy ước).
- valid_to NULL hoặc > valid_from.
- Không có overlap giữa hai phiên bản cùng business key.
- Số phiên bản hiện hành phù hợp chính sách.
- Nếu yêu cầu liên tục, không có gap.
- Nếu có lịch sử cập nhật ngược, xử lý cắt/đóng khoảng cũ nhất quán.

### 36.1. Constraint cơ bản

~~~sql
CREATE TABLE lich_su_gia (
    ma_phien_ban INTEGER PRIMARY KEY,
    ma_san_pham VARCHAR(30) NOT NULL,
    gia DECIMAL(12, 2) NOT NULL,
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP,
    CONSTRAINT ck_gia_valid_interval
        CHECK (valid_to IS NULL OR valid_from < valid_to)
);
~~~

Ràng buộc này chỉ ngăn khoảng đảo ngược hoặc rỗng trên **mỗi dòng riêng**, chưa tự ngăn hai dòng của cùng sản phẩm chồng nhau.

### 36.2. Unique không thay thế non-overlap

Một UNIQUE trên (ma_san_pham, valid_from) ngăn hai phiên bản cùng ngày bắt đầu nhưng **không ngăn** hai phiên bản:

~~~text
[01/01,01/03)
[01/02,01/04)
~~~

vì valid_from khác nhau. Muốn cấm overlap cần một constraint chuyên biệt, khóa/giao dịch bảo vệ logic hoặc thiết kế lại mô hình.

### 36.3. Bản ghi hiện hành

Nếu dùng cột is_current hoặc valid_to NULL, cần bảo đảm không có **hai bản ghi cùng sản phẩm đều “hiện hành”**. Một filtered/partial unique index có thể giúp ngăn trùng “current” trong DBMS hỗ trợ, nhưng chỉ có một current vẫn chưa đảm bảo lịch sử không có overlap ở quá khứ. Phải bảo vệ toàn bộ quy tắc không giao.

## 37. Truy vấn tìm bản ghi hiện hành và thời điểm vừa thay đổi

Giả sử valid_to NULL = vô hạn:

~~~sql
SELECT *
FROM lich_su_gia
WHERE valid_to IS NULL;
~~~

Muốn tìm các phiên bản **có hiệu lực ngay lúc này**, không thể mặc định valid_to NULL là đủ. Một bản ghi có valid_from trong tương lai nhưng valid_to NULL chưa có hiệu lực tại hiện tại.

Điều kiện chính xác:

~~~sql
valid_from <= :now
AND (valid_to IS NULL OR :now < valid_to)
~~~

Đặt **:now** là một tham số thời điểm nhất quán cho toàn câu truy vấn. Không đọc giờ hệ thống lặp nhiều lần từ tầng ứng dụng giữa các truy vấn nếu cần snapshot logic đồng nhất.

### 37.1. Tìm bản mới sẽ có hiệu lực trong tương lai

~~~sql
SELECT *
FROM lich_su_gia
WHERE valid_from > :now
ORDER BY valid_from;
~~~

### 37.2. Tìm bản hết hiệu lực trong kỳ

Nếu yêu cầu là “có thời điểm kết thúc trong [period_start,period_end)”:

~~~sql
WHERE valid_to IS NOT NULL
  AND valid_to >= :period_start
  AND valid_to < :period_end
~~~

Đây là lọc **thời điểm kết thúc nằm trong kỳ**, khác với lọc **khoảng hiệu lực giao với kỳ**. Phải phân biệt hai yêu cầu.

## 38. Bài toán hóa đơn: chọn đơn giá theo ngày sử dụng

Giả sử khách dùng dịch vụ trong khoảng **[usage_start, usage_end)**, nhưng đơn giá thay đổi giữa kỳ:

~~~text
Giá A: [01/01,01/15)  100/giờ
Giá B: [01/15,02/01)  120/giờ

Sử dụng: [01/14,01/16)
~~~

Không thể JOIN đúng một mức giá theo usage_start rồi tính toàn bộ kỳ sử dụng bằng giá A nếu nghiệp vụ yêu cầu áp giá theo từng thời điểm.

Cần:

1. JOIN kỳ sử dụng với **mọi khoảng giá có giao**.
2. Tính phần giao của từng cặp.
3. Tính thời lượng cho từng phần.
4. Nhân đơn giá tương ứng.
5. Cộng các phần, bảo đảm lịch sử giá không overlap hoặc gap gây trùng/thiếu phí.

Mẫu SQL khái niệm:

~~~sql
SELECT
    u.ma_luot,
    g.ma_phien_ban,
    CASE WHEN u.bat_dau >= g.valid_from
         THEN u.bat_dau ELSE g.valid_from END AS doan_tu,
    CASE
         WHEN g.valid_to IS NULL THEN u.ket_thuc
         WHEN u.ket_thuc <= g.valid_to THEN u.ket_thuc
         ELSE g.valid_to
    END AS doan_den,
    g.don_gia
FROM su_dung u
JOIN lich_su_gia g
    ON g.ma_dich_vu = u.ma_dich_vu
   AND (g.valid_to IS NULL OR u.bat_dau < g.valid_to)
   AND g.valid_from < u.ket_thuc;
~~~

Ở ví dụ, một lượt sử dụng có thể trả **hai dòng**, mỗi dòng là một phần có đơn giá khác nhau. Đây là kết quả đúng khi kỳ sử dụng cắt qua ngày đổi giá.

Không được nhân **toàn bộ thời lượng sử dụng** cho từng dòng giá; phải nhân **thời lượng của chính phần giao**.

## 39. SQL trong Java/JDBC: đặt chỗ bằng tham số

Ví dụ kiểm tra lịch xung đột:

~~~java
String sql = """
    SELECT ma_lich, bat_dau, ket_thuc
    FROM lich_dat_phong
    WHERE ma_phong = ?
      AND trang_thai = 'CONFIRMED'
      AND bat_dau < ?
      AND ? < ket_thuc
    ORDER BY bat_dau, ma_lich
    """;

java.time.LocalDateTime newStart =
    java.time.LocalDateTime.of(2026, 4, 10, 11, 30);
java.time.LocalDateTime newEnd =
    java.time.LocalDateTime.of(2026, 4, 10, 12, 30);

if (!newStart.isBefore(newEnd)) {
    throw new IllegalArgumentException(
        "Khoang dat phong phai co do dai duong"
    );
}

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "A");
    ps.setObject(2, newEnd);
    ps.setObject(3, newStart);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(
                "Xung dot voi lich " + rs.getInt("ma_lich")
            );
        }
    }
}
~~~

Đây là ví dụ **JDBC kiểm tra** khi cột TIMESTAMP không kèm timezone theo mô hình đã chọn. Hành vi **setObject(LocalDateTime)** phụ thuộc driver và kiểu SQL, nên cần dùng kiểu bind tương thích và xác nhận trên DBMS thực tế.

### 39.1. Khi cần thời điểm tuyệt đối

Trong ứng dụng đa múi giờ, mô hình có thể dùng **Instant**, **OffsetDateTime** và UTC. Việc bind những kiểu này phụ thuộc driver/JDBC và cột đích; không được giả định một **LocalDateTime** luôn đại diện cho một instant duy nhất.

### 39.2. Kiểm tra xung đột không đủ để ghi an toàn

Code ví dụ chỉ thực hiện SELECT. Nếu tiếp tục INSERT, ứng dụng cần một chiến lược **giao dịch và ràng buộc chống overlap** như phần 28/32. Không dùng kết quả “không có dòng” làm bằng chứng chỗ vẫn trống tại thời điểm COMMIT nếu có cập nhật đồng thời.

### 39.3. Không ghép giờ người dùng trực tiếp vào SQL

Dùng PreparedStatement để tránh SQL injection và để driver nhận đúng kiểu ngày giờ. Kiểm tra đầu vào:

- room ID hợp lệ.
- start/end đúng kiểu.
- start < end.
- múi giờ/offset xác định.
- độ dài tối đa theo chính sách.
- trạng thái lịch nào được coi là đang giữ chỗ.

## 40. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách xử lý |
|---|---|---|
| Dùng BETWEEN kiểm tra hai interval có giao không | Chỉ kiểm tra một điểm, có thể bỏ sót bao trọn | Dùng startA < endB AND startB < endA |
| Dùng <= cho giao nhau của [start,end) | Xem chạm là xung đột | Dùng < |
| Không xác định cận đóng/mở | Biên bằng nhau gây kết quả khác | Ghi quy ước [) hoặc quy tắc thật |
| Không kiểm tra start < end | Khoảng rỗng/đảo có thể tạo kết quả sai | NOT NULL + CHECK và validate input |
| Nghĩ NULL end tự là vô hạn | So sánh với NULL thành UNKNOWN | OR end IS NULL theo chính sách |
| Dùng NULL cho cả vô hạn và dữ liệu thiếu | Báo cáo nhập nhằng | Tách trạng thái/nghĩa |
| Kết thúc ngày bằng 23:59:59.999 | Độ chính xác DBMS khác | Dùng next-day exclusive khi là DATE nghiệp vụ |
| Cộng 24 giờ cho ngày địa phương | DST làm ngày 23/25 giờ | Tính mốc ngày kế tiếp theo múi giờ |
| Chỉ lọc start thuộc kỳ | Bỏ sót khoảng bắt đầu trước kỳ nhưng cắt qua kỳ | Predicate overlap |
| Dùng giá hiện hành để JOIN đơn quá khứ | Sai dữ liệu lịch sử | As-of join theo thời điểm đơn |
| Đặt điều kiện as-of ở WHERE sau LEFT JOIN | Mất đơn không có giá khớp | Đặt trong ON |
| Có hai bản giá overlap nhưng vẫn JOIN | Nhân đơn và doanh thu | Kiểm tra/đảm bảo non-overlap |
| Dùng UNIQUE(start) để ngăn overlap | Không ngăn khoảng khác start chồng nhau | Exclusion/transaction phù hợp |
| SELECT trống rồi INSERT | Race condition | Constraint/khóa/serialization |
| FOR UPDATE trên tập xung đột rỗng | Không có dòng để khóa | Khóa tài nguyên/phạm vi hoặc constraint |
| SUM thời lượng các interval overlap | Đếm đôi vùng phủ | Gộp interval trước khi SUM |
| Dùng LEAD(end) để tìm gap trong dữ liệu có nested interval | Có thể tạo gap giả | Running max / interval islands |
| GREATEST/LEAST với NULL end | Kết quả phụ thuộc hàm/DBMS và có thể NULL | Xử lý open-ended tường minh |
| JOIN thiếu tenant/product/currency | Khớp nhầm miền hiệu lực | Đủ business key |
| Không phân biệt system time và valid time | Trả lịch sử sai góc nhìn | Chọn trục thời gian rõ |
| So sánh TIMESTAMP khác timezone | Sai thời điểm và biên | Chuẩn hóa instant/múi giờ |
| Dùng hàm DATE() trên cột để tìm overlap | Sai ý nghĩa và có thể giảm hiệu năng | Dùng hai cận kiểu tương thích |
| Chỉ dùng B-tree và kỳ vọng tìm mọi overlap cực nhanh | Hai bất đẳng thức có giới hạn index | Đo plan, dùng GiST/range nếu phù hợp |
| Tưởng một khoảng giao nhiều dòng là lỗi SQL | Mỗi cặp giao được trả riêng | Kiểm tra grain và quy tắc nghiệp vụ |
| Đếm xung đột bằng COUNT(*) rồi coi là số đối tượng lỗi | Một đối tượng có nhiều cặp xung đột | Phân biệt cặp và đối tượng bằng EXISTS/ID |
| Chỉ kiểm tra INSERT, không kiểm tra UPDATE trạng thái/giờ | Có thể sinh overlap sau sửa lịch | Bảo vệ mọi đường ghi |
| So sánh timestamp bằng string định dạng lẫn lộn | Lexicographic order khác chronological | Dùng kiểu ngày giờ hoặc mã hóa chuẩn |

## 41. Bài tập thực hành có đáp án

### Bài 1 — Giao nhau cơ bản

Cho A = [10:00,12:00) và B = [11:00,13:00). Hai khoảng có giao nhau không? Phần giao là gì?

<details>
<summary>Đáp án gợi ý</summary>

**Có giao**, vì 10:00 < 13:00 và 11:00 < 12:00. Phần giao là **[11:00,12:00)**, dài 1 giờ.

</details>

### Bài 2 — Chạm biên

A = [10:00,12:00), B = [12:00,14:00). Có xung đột đặt phòng không?

<details>
<summary>Đáp án gợi ý</summary>

**Không** theo quy ước nửa mở. A kết thúc tại 12:00, B bắt đầu tại 12:00. Điều kiện **b_start < a_end** là **12:00 < 12:00**, FALSE.

</details>

### Bài 3 — Phát hiện giao nhau bằng SQL

Viết điều kiện WHERE để tìm những lịch có giao với khoảng mới [new_start,new_end), giả định các khoảng đều hợp lệ và hữu hạn.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
WHERE bat_dau < :new_end
  AND :new_start < ket_thuc
~~~

Bổ sung điều kiện mã phòng, trạng thái nếu nghiệp vụ cần.

</details>

### Bài 4 — Vì sao BETWEEN sai?

A = [10:00,12:00), B = [09:00,13:00). Nếu chỉ kiểm tra b_start BETWEEN a_start AND a_end, kết quả gì? Có đúng không?

<details>
<summary>Đáp án gợi ý</summary>

09:00 không nằm giữa 10:00 và 12:00, nên điều kiện FALSE, **dù B chứa hoàn toàn A**. Đây là ví dụ BETWEEN trên điểm bắt đầu không kiểm tra giao nhau tổng quát.

</details>

### Bài 5 — Khoảng rỗng

Nếu cho phép A=[11:00,11:00), công thức a_start < b_end AND b_start < a_end luôn phản ánh giao không rỗng với B không?

<details>
<summary>Đáp án gợi ý</summary>

**Không.** A là khoảng rỗng, nhưng hai bất đẳng thức có thể cùng TRUE nếu B bao trùm 11:00. Thông thường cấm khoảng rỗng bằng **start < end** hoặc xử lý riêng.

</details>

### Bài 6 — Một thời điểm nằm trong khoảng

Với [start,end), viết điều kiện tìm giá có hiệu lực tại t.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
valid_from <= :t
AND :t < valid_to
~~~

Khi valid_to NULL = vô hạn, thêm **OR valid_to IS NULL**.

</details>

### Bài 7 — Ngày kết thúc bao gồm

Hợp đồng có hiệu lực **từ 01/01 đến hết ngày 31/03/2026**. Nếu lưu half-open bằng cột DATE, valid_to nên là ngày nào?

<details>
<summary>Đáp án gợi ý</summary>

**2026-04-01**, vì khoảng **[2026-01-01,2026-04-01)** chứa toàn bộ các ngày 01/01 đến 31/03.

</details>

### Bài 8 — Cận kết thúc NULL

Cho valid_from = 2026-03-15 và valid_to = NULL, với NULL nghĩa +infinity. Bản ghi có hiệu lực tại 2026-04-01 không?

<details>
<summary>Đáp án gợi ý</summary>

**Có**, nếu start <= t. Điều kiện:

~~~sql
valid_from <= :t
AND (valid_to IS NULL OR :t < valid_to)
~~~

</details>

### Bài 9 — Chạm nhau trong lịch sử giá

Hai bản giá [01/01,01/02) và [01/02,01/03) có overlap không? Ngày 01/02 thuộc bản nào?

<details>
<summary>Đáp án gợi ý</summary>

**Không overlap**, chỉ chạm tại 01/02. Ngày 01/02 thuộc **bản thứ hai**, không thuộc bản thứ nhất.

</details>

### Bài 10 — As-of join

Đơn đặt lúc 2026-02-01 00:00. Bảng giá có [01/01,01/02) giá 100000 và [01/02,01/03) giá 120000. Giá nào khớp?

<details>
<summary>Đáp án gợi ý</summary>

**120000**, vì thời điểm đó là cận đầu bao gồm của phiên bản thứ hai và cận trên loại trừ của phiên bản thứ nhất.

</details>

### Bài 11 — LEFT JOIN và WHERE

Vì sao để điều kiện valid_from <= d.thoi_diem_dat và d.thoi_diem_dat < valid_to trong WHERE có thể khiến đơn không tìm được giá biến mất?

<details>
<summary>Đáp án gợi ý</summary>

Vì với dòng LEFT JOIN không khớp, cột g.* là NULL và điều kiện WHERE trở thành UNKNOWN. WHERE chỉ giữ TRUE. Đặt predicate hiệu lực trong **ON** nếu muốn giữ đơn để phát hiện lỗi lịch sử.

</details>

### Bài 12 — Phát hiện khoảng chồng nhau

Viết điều kiện JOIN để so hai phiên bản giá cùng mã sản phẩm và chỉ trả mỗi cặp một lần, với end hữu hạn.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
ON a.ma_san_pham = b.ma_san_pham
AND a.ma_phien_ban < b.ma_phien_ban
AND a.valid_from < b.valid_to
AND b.valid_from < a.valid_to
~~~

Nếu end có thể NULL = vô hạn, thay hai điều kiện giao bằng biểu thức có IS NULL tương ứng.

</details>

### Bài 13 — Hai phiên bản hiện hành

Hai dòng cùng sản phẩm đều có valid_to NULL. Điều này có nhất thiết vi phạm yêu cầu một giá hiệu lực tại một thời điểm không?

<details>
<summary>Đáp án gợi ý</summary>

Nếu cả hai valid_from đều đã xảy ra, **có**: hai khoảng cùng kéo tới +infinity nên overlap. Nếu một valid_from còn trong tương lai, hai khoảng vẫn overlap trong tương lai từ mốc bắt đầu muộn hơn. Dữ liệu cần được thiết kế/cắt lại để chỉ một mức giá mỗi thời điểm.

</details>

### Bài 14 — Giao của hai khoảng

A=[10:00,13:00), B=[11:30,15:00). Tìm hai cận của khoảng giao.

<details>
<summary>Đáp án gợi ý</summary>

**max(10:00,11:30)=11:30** và **min(13:00,15:00)=13:00**, nên giao là **[11:30,13:00)**.

</details>

### Bài 15 — Báo cáo ngày

Một lịch [2026-04-09 23:00, 2026-04-10 01:00) có giao với ngày 10/04 không? Vì sao lọc bat_dau nằm trong ngày là sai?

<details>
<summary>Đáp án gợi ý</summary>

**Có**, vì lịch còn hoạt động từ 00:00 đến trước 01:00 ngày 10/04. Bat_dau thuộc ngày 09/04, nên chỉ lọc start của ngày 10/04 sẽ bỏ sót.

</details>

### Bài 16 — Bẫy SUM thời lượng

Có hai lịch [10:00,12:00), [11:00,13:00). Tổng thời lượng từng lịch và tổng thời gian phòng thực sự bận là bao nhiêu?

<details>
<summary>Đáp án gợi ý</summary>

Tổng thời lượng các lịch **4 giờ**; hợp vùng thời gian bận [10:00,13:00) chỉ **3 giờ**. Nếu đo thời gian phòng được sử dụng thực tế, cần gộp khoảng trước khi cộng.

</details>

### Bài 17 — Gap

Hai khoảng [01/01,01/02), [10/02,01/03) có gap không? Khoảng gap là gì?

<details>
<summary>Đáp án gợi ý</summary>

**Có**, gap là **[01/02,10/02)**.

</details>

### Bài 18 — LEAD và khoảng lồng nhau

A=[10:00,20:00), B=[11:00,12:00), C=[13:00,14:00). Nếu sắp theo start, dùng LAG(end) của dòng liền trước để tìm gap trước C thì có thể sai ra sao?

<details>
<summary>Đáp án gợi ý</summary>

C có thể thấy end của B là 12:00 và báo gap [12:00,13:00), dù **A vẫn phủ đến 20:00**. Cần **running maximum end** của mọi khoảng trước hoặc gộp khoảng trước khi tìm gap.

</details>

### Bài 19 — Interval islands

Các khoảng [10:00,12:00), [11:00,13:00), [13:00,14:00), [16:00,17:00) gộp thành gì nếu khoảng chạm được xem là liền?

<details>
<summary>Đáp án gợi ý</summary>

Hai đảo: **[10:00,14:00)** và **[16:00,17:00)**.

</details>

### Bài 20 — Đặt chỗ đồng thời

Tại sao hai giao dịch cùng chạy SELECT NOT EXISTS rồi INSERT có thể tạo lịch trùng nhau?

<details>
<summary>Đáp án gợi ý</summary>

Cả hai có thể **đọc cùng trạng thái chưa có lịch xung đột** trước khi giao dịch kia INSERT/COMMIT. Nếu không có constraint/khóa/serializable isolation phù hợp, cả hai có thể ghi thành công. Predicate đúng không thay thế cơ chế đồng bộ ghi.

</details>

### Bài 21 — PostgreSQL range

Trên PostgreSQL, toán tử nào thường dùng để kiểm tra hai range có overlap? Ký hiệu '[)' có nghĩa gì?

<details>
<summary>Đáp án gợi ý</summary>

Toán tử **&&**; **'[)'** nghĩa cận đầu bao gồm, cận cuối loại trừ.

</details>

### Bài 22 — System time và business time

Một giá được nhập vào hệ thống ngày 10/03 nhưng có hiệu lực từ 01/03. Nếu hỏi “giá nào có hiệu lực ngày 05/03”, có thể chỉ dùng SQL Server FOR SYSTEM_TIME AS OF 05/03 không?

<details>
<summary>Đáp án gợi ý</summary>

**Không thể mặc định.** FOR SYSTEM_TIME AS OF truy vấn lịch sử theo **system time** của phiên bản lưu trữ, còn hiệu lực từ 01/03 là **business valid time**. Cần dùng valid_from/valid_to hoặc mô hình bitemporal đúng.

</details>

### Bài 23 — Đổi tenant

Nếu hai tenant cùng dùng mã sản phẩm P01, điều kiện as-of JOIN cần thêm gì ngoài mã sản phẩm và thời gian?

<details>
<summary>Đáp án gợi ý</summary>

Cần **tenant_id**, và mọi cột khác thuộc **khóa nghiệp vụ** của giá như đơn vị tiền/kênh bán nếu chúng quyết định miền hiệu lực.

</details>

### Bài 24 — Vô hạn ở hai phía

Hai khoảng A=[01/01,+∞), B=[01/02,+∞) có overlap không? Nếu end NULL nghĩa vô hạn, predicate cần xử lý gì?

<details>
<summary>Đáp án gợi ý</summary>

**Có**, từ 01/02 trở đi. Phải có điều kiện **end IS NULL OR ...**; so sánh trực tiếp với NULL sẽ cho UNKNOWN.

</details>

### Bài 25 — Ranh giới DST

Tại sao “từ 00:00 hôm nay đến 00:00 ngày mai” không nên luôn chuyển thành start UTC + 24 giờ nếu báo cáo theo ngày địa phương?

<details>
<summary>Đáp án gợi ý</summary>

Ở múi giờ có DST, ngày địa phương có thể dài 23 hoặc 25 giờ. Cần tính **hai nửa đêm liên tiếp tại múi giờ nghiệp vụ**, rồi chuyển từng mốc sang instant/UTC.

</details>

### Bài 26 — Lọc các lịch không xung đột

Viết truy vấn dùng NOT EXISTS để lấy đề xuất đặt phòng không giao lịch CONFIRMED nào của cùng phòng, với hai cột start/end hữu hạn.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
SELECT d.*
FROM de_xuat_lich d
WHERE d.bat_dau < d.ket_thuc
  AND NOT EXISTS (
      SELECT 1
      FROM lich_dat_phong l
      WHERE l.ma_phong = d.ma_phong
        AND l.trang_thai = 'CONFIRMED'
        AND l.bat_dau < d.ket_thuc
        AND d.bat_dau < l.ket_thuc
  );
~~~

Giả định lịch trong bảng và đề xuất đều dùng [start,end), cột không NULL và đề xuất có mã phòng phù hợp.

</details>

### Bài 27 — Tìm bản giá bị overlap

Nếu một sản phẩm có ba khoảng [01/01,01/04), [01/02,01/03), [01/03,01/05), có bao nhiêu **cặp** overlap thực sự theo [start,end)?

<details>
<summary>Đáp án gợi ý</summary>

**Hai cặp**:

- Khoảng 1 giao khoảng 2.
- Khoảng 1 giao khoảng 3.

Khoảng 2 **chạm** khoảng 3 tại 01/03 nhưng không giao (cận cuối loại trừ). Vì vậy có hai cặp lỗi overlap.

</details>

### Bài 28 — Kiểm tra cận DATE

Nếu bảng lưu end_date_inclusive và câu SQL dùng **date BETWEEN start_date AND end_date_inclusive**, điều đó có thể phù hợp không?

<details>
<summary>Đáp án gợi ý</summary>

**Có** nếu miền nghiệp vụ thật sự là **DATE nguyên** và cận cuối được bao gồm. Tuy nhiên, khi chuyển sang timestamp interval [start,end), phải đổi điều kiện tương ứng, không sao chép BETWEEN máy móc.

</details>

## 42. Tình huống tổng hợp: hệ thống đăng ký dịch vụ theo gói

Giả sử mỗi khách hàng có nhiều gói dịch vụ. Mỗi dòng:

~~~text
dang_ky_dich_vu(
    ma_dang_ky,
    tenant_id,
    ma_khach,
    ma_dich_vu,
    valid_from,
    valid_to,
    trang_thai
)
~~~

Quy tắc:

- Một khách có thể đăng ký nhiều dịch vụ khác nhau.
- Với **cùng khách + cùng dịch vụ + cùng tenant**, không có hai gói **ACTIVE** giao nhau.
- valid_to NULL = chưa có thời điểm hết hạn.
- Khoảng dùng **[valid_from,valid_to)**.
- Gói CANCELLED không còn áp dụng theo chính sách đăng ký, nhưng lịch sử có thể được lưu.

### 42.1. Truy vấn gói đang hiệu lực tại t

~~~sql
SELECT *
FROM dang_ky_dich_vu
WHERE tenant_id = :tenant
  AND ma_khach = :customer
  AND ma_dich_vu = :service
  AND trang_thai = 'ACTIVE'
  AND valid_from <= :t
  AND (valid_to IS NULL OR :t < valid_to);
~~~

Nếu dữ liệu đúng quy tắc, truy vấn này nên trả **tối đa một dòng** cho mỗi bộ khóa và thời điểm. Nếu trả hai dòng, có thể có lỗi khoảng overlap hoặc trạng thái.

### 42.2. Kiểm tra gói mới có chồng không

Với valid_from mới là **:new_start**, valid_to mới có thể NULL:

~~~sql
SELECT d.ma_dang_ky
FROM dang_ky_dich_vu d
WHERE d.tenant_id = :tenant
  AND d.ma_khach = :customer
  AND d.ma_dich_vu = :service
  AND d.trang_thai = 'ACTIVE'
  AND (:new_end IS NULL OR d.valid_from < :new_end)
  AND (d.valid_to IS NULL OR :new_start < d.valid_to);
~~~

Trước đó phải kiểm tra new_start khác NULL và new_end NULL hoặc **new_start < new_end**. Nếu không, logic open-ended/giao có thể không biểu diễn đúng yêu cầu.

### 42.3. Tạo gói nối tiếp không giao

Gói cũ [01/01,01/07), gói mới [01/07,+∞) **không overlap**. Tại đúng 01/07, chỉ gói mới có hiệu lực.

Nếu hệ thống yêu cầu có thời gian chờ giữa các gói, “không overlap” chưa đủ; cần thêm điều kiện gap tối thiểu theo chính sách.

### 42.4. Báo cáo chất lượng dữ liệu

Nên có các kiểm tra độc lập:

1. valid_from bị NULL trái quy tắc.
2. valid_to <= valid_from khi valid_to có giá trị.
3. Có hai khoảng ACTIVE giao nhau theo cùng business key.
4. Có hơn một gói hiệu lực tại một thời điểm được kiểm thử.
5. Có gap ngoài kỳ vọng.
6. Có bản ghi trạng thái sai hoặc thiếu tenant.
7. Có các thay đổi nhập muộn làm lịch sử không còn liên tục.
8. Có nhiều giao dịch đồng thời cập nhật khoảng gây race condition.

**Không gộp việc phát hiện lỗi dữ liệu với quyết định tự xóa hoặc tự thay đổi hợp đồng.** Một khoảng overlap có thể cần xác nhận thời điểm hiệu lực thực tế với hệ thống nguồn trước khi sửa.

## 43. Tóm tắt và nguyên tắc cần nhớ

1. **Xác định quy ước cận trước khi viết SQL.** Với rất nhiều lịch và hiệu lực, **[start,end)** là lựa chọn đơn giản, nhất quán.
2. Với **hai khoảng hữu hạn, hợp lệ và không rỗng**, giao nhau khi **a.start < b.end AND b.start < a.end**.
3. Hai khoảng [10:00,12:00) và [12:00,14:00) **chạm** nhưng **không giao**; dấu **<** phản ánh quy tắc đó.
4. **BETWEEN** mặc định bao gồm hai cận và không giải quyết đầy đủ bài toán hai khoảng có giao.
5. **start < end** là bất biến quan trọng nếu nghiệp vụ không cho phép khoảng rỗng. Hãy kết hợp CHECK với NOT NULL/chính sách NULL.
6. **NULL ở end không tự là vô hạn.** Chỉ dùng **end IS NULL OR ...** khi mô hình đã quy định NULL = +infinity.
7. Tìm giá/trạng thái tại thời điểm **t** bằng **valid_from <= t AND (t < valid_to OR valid_to IS NULL)**.
8. **As-of join** phải nối theo đúng khóa nghiệp vụ **và** khoảng hiệu lực; chồng lấn làm một sự kiện khớp nhiều bản lịch sử.
9. **LEFT JOIN** nên giữ điều kiện hiệu lực trong **ON** khi muốn giữ sự kiện không có phiên bản tương ứng.
10. **Bản giá SCD2** cần không overlap, và có thể cần không có gap, tùy nghiệp vụ.
11. **Phần giao** là **[max(start),min(end))**; muốn tính thời gian sử dụng thật sự, phải tránh đếm đôi các khoảng overlap.
12. **Khoảng trống** và **gộp khoảng** cần xét running maximum của end khi có interval lồng nhau; LEAD của dòng ngay trước không luôn đủ.
13. **Một ngày địa phương không luôn là 24 giờ** ở vùng có DST; tính cận ngày theo múi giờ nghiệp vụ.
14. **DATE, TIMESTAMP, TIMESTAMPTZ/DATETIMEOFFSET** có ngữ nghĩa khác nhau; phải thống nhất cách lưu và bind tham số.
15. PostgreSQL có **range types**, **&&** và **exclusion constraints** giúp truy vấn/ràng buộc không overlap. Các DBMS khác thường dùng cột start/end và chiến lược transaction/khóa phù hợp.
16. **SELECT kiểm tra không xung đột rồi INSERT chưa đủ an toàn khi có concurrency**. Phải bảo vệ tại mọi đường ghi.
17. **System time** và **business valid time** trả hai câu hỏi khác nhau; đừng dùng lịch sử hệ thống để thay hiệu lực nghiệp vụ khi chúng không trùng.
18. Kiểm thử giá trị biên, start=end, NULL, cận bằng nhau, dữ liệu trùng, timezone, lịch sử chồng/gap và tải đồng thời là phần thiết yếu của một hệ thống thời gian chính xác.

### Tài liệu tham khảo định hướng

Khi viết SQL cho hệ thống thật, cần xem tài liệu chính thức **đúng phiên bản DBMS và kiểu dữ liệu**:

- **PostgreSQL Documentation:** *Range Types*, *Range Functions and Operators*, *Exclusion Constraints*, *GiST Indexes*, *Date/Time Types*.
- **Microsoft Learn — SQL Server:** *Temporal Tables*, *FOR SYSTEM_TIME*, *DATETIME2*, *DATETIMEOFFSET*, *Transaction Isolation Levels*, *Locking Guide*.
- **Oracle Database SQL Language Reference:** *Datetime Data Types*, *Temporal Validity*, *Flashback Query*, *Intervals*, *Transaction Isolation*.
- **MySQL Reference Manual:** *Date and Time Data Types*, *Comparison Operators*, *InnoDB Locking and Transaction Model*.
- **SQLite Documentation:** *Date And Time Functions*, *Datatypes*, *Transactions*, *Query Planner*.

**Câu hỏi tự kiểm tra quan trọng nhất:** **“Hai cận được bao gồm hay loại trừ; khoảng rỗng và cận vô hạn có được phép không; tại thời điểm biên nào một bản ghi vừa hết hiệu lực và bản khác bắt đầu?”**. Khi trả lời rõ ba điều đó, phần lớn bài toán khoảng thời gian giao nhau và khoảng hiệu lực đều có thể giải bằng những predicate SQL ngắn gọn, chính xác và dễ kiểm thử.

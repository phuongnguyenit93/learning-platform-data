# Sequence: NEXTVAL, CURRVAL, CACHE, ORDER và khoảng trống khóa trong Oracle

Trong Oracle Database, **sequence** là đối tượng schema tạo ra một chuỗi số theo quy tắc đã khai báo. Sequence thường được dùng để cấp mã định danh cho dòng mới, chẳng hạn mã đơn hàng, mã khách hàng hoặc mã giao dịch. Hai pseudo-column quan trọng nhất là **NEXTVAL** và **CURRVAL**: NEXTVAL lấy số tiếp theo, còn CURRVAL trả lại số gần nhất mà session hiện tại đã lấy từ sequence đó.

Sequence được thiết kế cho việc cấp số đồng thời giữa nhiều session. Nó không phải bộ đếm giao dịch có khả năng rollback, cũng không phải công cụ tự bảo đảm số thứ tự liên tục. Vì vậy, các tùy chọn **CACHE**, **ORDER** và **NOORDER** ảnh hưởng đến hiệu năng, thứ tự cấp số và khả năng xuất hiện khoảng trống (gap).

Bài học này trình bày cách tạo và dùng sequence, phạm vi session của CURRVAL, cache và RAC, nguyên nhân sequence bị nhảy số, cách quan sát sequence trong Data Dictionary và cách chọn sequence hoặc identity column theo nhu cầu.

## 1. Sequence là gì?

Sequence là một đối tượng schema độc lập, tạo ra các giá trị số theo cấu hình. Sequence không tự gắn với một bảng hoặc một cột cụ thể. Một hoặc nhiều câu lệnh SQL có thể sử dụng cùng sequence; một bảng cũng có thể không dùng sequence nào.

Ví dụ, ta tạo sequence cấp mã đơn hàng:

~~~sql
CREATE SEQUENCE lab_order_seq
    START WITH 1001
    INCREMENT BY 1
    MINVALUE 1
    NOMAXVALUE
    NOCYCLE
    CACHE 50
    NOORDER;
~~~

Ý nghĩa:

| Thuộc tính | Giá trị | Ý nghĩa |
|---|---:|---|
| START WITH | 1001 | Giá trị đầu tiên được cấp khi sequence mới bắt đầu |
| INCREMENT BY | 1 | Mỗi lần lấy số, tăng thêm 1 |
| MINVALUE | 1 | Giá trị nhỏ nhất cho sequence tăng |
| NOMAXVALUE | — | Không đặt MAXVALUE tường minh; Oracle dùng giới hạn tối đa theo kiểu sequence |
| NOCYCLE | — | Không quay vòng về đầu khi chạm giới hạn |
| CACHE | 50 | Cache trước một nhóm giá trị để giảm chi phí lấy số |
| NOORDER | — | Không yêu cầu bảo đảm thứ tự toàn cục theo thời điểm yêu cầu |

Các tùy chọn được ghi tường minh để người đọc hiểu hành vi. Mặc định và giới hạn cụ thể có thể khác theo phiên bản Oracle và loại sequence; với đối tượng quan trọng, nên khai báo rõ cấu hình thay vì phụ thuộc mặc định.

### 1.1. Sequence không phải cột tự tăng

Sequence chỉ cấp giá trị. Nó không tự biết bảng nào cần nhận giá trị và không tự bảo đảm giá trị đó là duy nhất trong bảng. Muốn dùng làm khóa chính, ta phải đưa NEXTVAL vào INSERT và khai báo PRIMARY KEY hoặc UNIQUE constraint:

~~~sql
CREATE TABLE lab_order (
    order_id      NUMBER(12) PRIMARY KEY,
    customer_name VARCHAR2(80 CHAR) NOT NULL,
    created_at    DATE NOT NULL
);

INSERT INTO lab_order (
    order_id,
    customer_name,
    created_at
)
VALUES (
    lab_order_seq.NEXTVAL,
    'An',
    SYSDATE
);
~~~

Sequence tạo ra giá trị cho ORDER_ID; primary key mới là constraint bảo đảm không có hai dòng cùng ORDER_ID trong bảng.

## 2. NEXTVAL: lấy giá trị kế tiếp

NEXTVAL yêu cầu sequence cấp một giá trị mới và tiến sequence theo INCREMENT BY.

~~~sql
SELECT lab_order_seq.NEXTVAL
FROM dual;
~~~

Nếu sequence vừa được tạo với START WITH 1001, lần gọi đầu tiên trả về 1001. Những lần gọi sau lần lượt trả 1002, 1003, 1004... với cấu hình INCREMENT BY 1.

Ví dụ:

~~~sql
SELECT lab_order_seq.NEXTVAL AS generated_id FROM dual;
SELECT lab_order_seq.NEXTVAL AS generated_id FROM dual;
SELECT lab_order_seq.NEXTVAL AS generated_id FROM dual;
~~~

Kết quả minh họa:

| Lần gọi | GENERATED_ID |
|---:|---:|
| 1 | 1001 |
| 2 | 1002 |
| 3 | 1003 |

Các con số này giả định chưa có session nào khác gọi sequence và sequence chưa được dùng trước đó. Trong hệ thống đồng thời, session khác cũng có thể lấy giá trị giữa hai lần gọi của session hiện tại.

### 2.1. Dùng NEXTVAL trong INSERT

Đây là cách dùng phổ biến nhất:

~~~sql
INSERT INTO lab_order (
    order_id,
    customer_name,
    created_at
)
VALUES (
    lab_order_seq.NEXTVAL,
    'Binh',
    SYSDATE
);
~~~

Không cần truy vấn MAX(ORDER_ID) rồi cộng 1. Cách MAX + 1 có thể tạo trùng khóa khi nhiều session cùng đọc một MAX trước khi INSERT. Sequence được thiết kế để nhiều session lấy số mà không phải tự đồng bộ bằng cách đọc dữ liệu bảng.

### 2.2. Dùng NEXTVAL trong INSERT ... SELECT

Có thể cấp một giá trị cho từng dòng được chèn:

~~~sql
INSERT INTO lab_order (
    order_id,
    customer_name,
    created_at
)
SELECT
    lab_order_seq.NEXTVAL,
    customer_name,
    SYSDATE
FROM lab_order_stage
WHERE import_status = 'READY';
~~~

Mỗi dòng được xử lý trong query block ngoài nhận một giá trị sequence theo quy tắc sử dụng NEXTVAL của Oracle. Không dựa vào thứ tự dòng của SELECT nếu nghiệp vụ cần gán số theo một thứ tự cụ thể; hãy thiết kế nguồn và thứ tự cấp số phù hợp.

## 3. CURRVAL: giá trị gần nhất trong session hiện tại

CURRVAL trả về giá trị gần nhất mà **session hiện tại** đã lấy từ NEXTVAL của sequence đó.

~~~sql
SELECT lab_order_seq.CURRVAL
FROM dual;
~~~

Điều kiện quan trọng: session phải gọi NEXTVAL của sequence ít nhất một lần trước đó. Nếu chưa, Oracle báo lỗi:

~~~text
ORA-08002: sequence LAB_ORDER_SEQ.CURRVAL is not yet defined in this session
~~~

Ví dụ đúng:

~~~sql
SELECT lab_order_seq.NEXTVAL FROM dual;
SELECT lab_order_seq.CURRVAL FROM dual;
~~~

Hai câu lệnh trong cùng session sẽ trả cùng giá trị ở lần CURRVAL. CURRVAL không làm sequence tăng thêm.

### 3.1. CURRVAL được ghi nhớ theo session

Giả sử:

- Session A gọi NEXTVAL và nhận 1001.
- Session B gọi NEXTVAL và nhận 1002.
- Session A gọi CURRVAL và nhận lại 1001.
- Session B gọi CURRVAL và nhận lại 1002.

Mỗi session có trạng thái CURRVAL riêng:

| Session | NEXTVAL đã nhận | CURRVAL trả về |
|---|---:|---:|
| A | 1001 | 1001 |
| B | 1002 | 1002 |

Session A không bị thay đổi CURRVAL chỉ vì session B gọi NEXTVAL. Đây là lý do CURRVAL hữu ích khi một session vừa lấy mã mới và cần dùng lại mã đó trong cùng session.

### 3.2. COMMIT và ROLLBACK không đặt lại CURRVAL

Trạng thái sequence không thuộc transaction theo cách dữ liệu bảng thuộc transaction:

- COMMIT không làm CURRVAL mất giá trị vừa lấy.
- ROLLBACK không đưa sequence về số trước đó.
- CURRVAL vẫn là giá trị NEXTVAL gần nhất của session, cho đến khi session gọi NEXTVAL tiếp theo hoặc kết thúc.

Sequence cấp số độc lập với việc transaction chứa câu INSERT có commit hay rollback.

## 4. Dùng NEXTVAL và CURRVAL trong cùng câu lệnh

Trong một query block, khi NEXTVAL được tham chiếu nhiều lần cho cùng một dòng được xử lý, Oracle tăng sequence một lần cho dòng đó và các tham chiếu sequence tương ứng trong dòng nhận cùng giá trị mới. CURRVAL trong cùng ngữ cảnh đó trả giá trị hiện tại do NEXTVAL vừa tạo.

Ví dụ minh họa:

~~~sql
SELECT
    lab_order_seq.NEXTVAL AS new_value,
    lab_order_seq.CURRVAL AS current_value
FROM dual;
~~~

Trong một session hợp lệ, hai cột ở dòng kết quả phản ánh cùng giá trị vừa được cấp. Để người học dễ quan sát và tránh phụ thuộc vào chi tiết vị trí tham chiếu trong một câu SQL phức tạp, có thể tách thành hai câu:

~~~sql
SELECT lab_order_seq.NEXTVAL FROM dual;
SELECT lab_order_seq.CURRVAL FROM dual;
~~~

### 4.1. Lấy mã vừa INSERT

Trong cùng session, sau INSERT:

~~~sql
INSERT INTO lab_order (
    order_id,
    customer_name,
    created_at
)
VALUES (
    lab_order_seq.NEXTVAL,
    'Chi',
    SYSDATE
);

SELECT lab_order_seq.CURRVAL AS inserted_order_id
FROM dual;
~~~

CURRVAL cho biết giá trị sequence mà session gần nhất đã lấy. Trong ứng dụng, nếu cần lấy chính xác giá trị của dòng vừa chèn, mệnh đề RETURNING INTO thường rõ ràng hơn:

~~~sql
DECLARE
    v_order_id lab_order.order_id%TYPE;
BEGIN
    INSERT INTO lab_order (
        order_id,
        customer_name,
        created_at
    )
    VALUES (
        lab_order_seq.NEXTVAL,
        'Dung',
        SYSDATE
    )
    RETURNING order_id INTO v_order_id;

    DBMS_OUTPUT.PUT_LINE('Inserted order: ' || v_order_id);
END;
/
~~~

RETURNING lấy giá trị trực tiếp từ dòng bị tác động. Điều này hữu ích khi trigger hoặc logic khác cũng có thể sử dụng sequence, vì CURRVAL luôn chỉ phản ánh NEXTVAL gần nhất của sequence trong session.

## 5. NEXTVAL không bị hoàn tác cùng transaction

Đây là nguyên nhân quan trọng nhất của khoảng trống khóa.

~~~sql
SELECT lab_order_seq.NEXTVAL FROM dual;
-- Giả sử nhận 1004.

ROLLBACK;

SELECT lab_order_seq.NEXTVAL FROM dual;
-- Giá trị tiếp theo là 1005, không quay lại 1004.
~~~

ROLLBACK chỉ hoàn tác thay đổi dữ liệu thuộc transaction. Việc lấy số từ sequence không được hoàn tác. Giá trị 1004 đã được cấp và không được cấp lại chỉ vì transaction rollback.

Tương tự, nếu INSERT dùng NEXTVAL nhưng sau đó vi phạm constraint, câu INSERT bị rollback ở mức statement, song sequence đã tiến vẫn không lùi:

~~~sql
-- Giả sử order_id 1005 đã tồn tại.
INSERT INTO lab_order (order_id, customer_name, created_at)
VALUES (1005, 'E', SYSDATE);
-- Có thể lỗi unique/primary key.

SELECT lab_order_seq.NEXTVAL FROM dual;
~~~

Ví dụ này cố tình dùng một ID có thể trùng để minh họa lỗi INSERT. Giá trị sequence đã cấp trong một câu lệnh lỗi vẫn có thể bị tiêu thụ; không dựa vào rollback để lấy lại số.

### 5.1. Vì sao sequence không transactional?

Sequence được thiết kế để cấp giá trị nhanh cho nhiều session đồng thời mà không cần khóa một dòng bộ đếm trong bảng và chờ transaction commit. Nếu sequence phải quay ngược mỗi khi một transaction rollback, Oracle phải đồng bộ việc thu hồi số đã cấp với mọi session đang chạy. Điều đó sẽ làm phức tạp và giảm khả năng cấp số đồng thời.

Vì vậy, sequence ưu tiên cấp số an toàn cho concurrency và hiệu năng. **Tính liên tục không phải bảo đảm của sequence.**

## 6. CACHE và NOCACHE

CACHE quy định Oracle giữ trước một nhóm giá trị sequence để giảm chi phí cấp số. NOCACHE không giữ trước một nhóm giá trị như vậy.

Ví dụ:

~~~sql
CREATE SEQUENCE lab_cached_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 100
    NOORDER
    NOCYCLE;
~~~

Oracle có thể chuẩn bị một vùng giá trị cho sequence để các lần NEXTVAL không phải thực hiện cùng mức công việc quản lý mỗi lần. CACHE thường cải thiện hiệu năng khi sequence được sử dụng thường xuyên.

### 6.1. Cache không có nghĩa số đã được INSERT

Nếu sequence dùng CACHE 100, điều đó không có nghĩa Oracle đã tạo 100 dòng trong bảng hoặc đã commit 100 giá trị. Cache là vùng giá trị được quản lý cho việc cấp số; chỉ khi ứng dụng gọi NEXTVAL thì giá trị mới được trả về.

### 6.2. Số chưa dùng trong cache có thể bị mất

Giả sử sequence cache một nhóm số 1 đến 100. Session chỉ lấy đến 12 thì instance bị dừng hoặc gặp sự cố. Các số còn lại trong cache có thể bị bỏ. Sau khi instance khởi động lại, sequence tiếp tục từ vùng đã dự trữ tiếp theo; kết quả có thể nhảy đến một giá trị cao hơn 100.

Mô hình:

~~~text
Cache được cấp: 1 ... 100
Ứng dụng đã lấy: 1 ... 12
                       |
                       v
              Instance dừng/sự cố
                       |
                       v
           Các số cache chưa dùng bị bỏ
                       |
                       v
       Lần cấp sau có thể tiếp tục từ 101
~~~

Khoảng trống này là hành vi bình thường của CACHE. Nó không có nghĩa dữ liệu trong bảng đã bị xóa hoặc transaction đã commit các số còn lại.

### 6.3. NOCACHE có loại bỏ gap không?

Không. NOCACHE tránh mất một vùng giá trị chưa dùng do cache bị bỏ, nhưng không loại bỏ các gap do:

- Transaction lấy NEXTVAL rồi ROLLBACK.
- INSERT dùng NEXTVAL thất bại.
- Ứng dụng lấy số nhưng không sử dụng.
- Một câu lệnh cấp nhiều số nhưng chỉ lưu một phần dữ liệu theo logic ứng dụng.
- Sequence được ALTER, RESTART hoặc cấu hình lại.

NOCACHE cũng có thể làm tăng chi phí quản lý sequence và giảm throughput. Không nên chọn NOCACHE với giả định nó tạo ra số liên tục.

### 6.4. CACHE bao nhiêu là phù hợp?

Không có một kích thước cache tối ưu cho mọi hệ thống:

- Sequence ít được dùng: cache nhỏ có thể đủ.
- Sequence được gọi với tần suất cao: cache lớn hơn thường giảm chi phí lấy số.
- Ứng dụng chạy RAC: cần cân nhắc thêm cách phân phối cache trên nhiều instance và tùy chọn ORDER.
- Hệ thống có restart thường xuyên: vùng cache lớn có thể làm số nhảy xa hơn sau khi instance dừng.

Chọn cache dựa trên throughput, số instance, tần suất restart và mức chấp nhận gap. Không dùng cache size như một cơ chế đánh số nghiệp vụ liên tục.

## 7. ORDER và NOORDER

ORDER và NOORDER quy định yêu cầu về thứ tự cấp số.

- **ORDER** bảo đảm sequence numbers được tạo theo thứ tự yêu cầu.
- **NOORDER** không yêu cầu bảo đảm thứ tự toàn cục đó; Oracle có thể tối ưu việc cấp số, đặc biệt khi nhiều instance cùng sử dụng sequence.

Ví dụ:

~~~sql
CREATE SEQUENCE lab_ordered_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 50
    ORDER
    NOCYCLE;
~~~

Và:

~~~sql
CREATE SEQUENCE lab_unordered_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 50
    NOORDER
    NOCYCLE;
~~~

### 7.1. ORDER không có nghĩa commit theo thứ tự

Giả sử session A lấy số 10 trước session B lấy số 11. Session A có thể thực hiện nhiều công việc và COMMIT sau session B. Vì vậy:

| Sự kiện | Session A | Session B |
|---|---|---|
| Lấy NEXTVAL | 10 | 11 |
| Hoàn tất DML | Chậm hơn | Nhanh hơn |
| COMMIT | Sau B | Trước A |

Ngay cả khi sequence dùng ORDER, số 10 vẫn có thể được commit sau số 11. ORDER điều khiển thứ tự tạo số theo yêu cầu sequence, không bảo đảm:

- Thứ tự INSERT hoàn tất.
- Thứ tự COMMIT.
- Thứ tự client nhận kết quả.
- Thứ tự dòng được SELECT nếu không có ORDER BY.

Nếu báo cáo cần hiển thị theo mã tăng dần, hãy viết ORDER BY ở truy vấn đọc dữ liệu.

### 7.2. NOORDER trong RAC

Trong Oracle RAC, nhiều instance cùng truy cập database. Với NOORDER, mỗi instance có thể sử dụng vùng sequence cache riêng. Vì vậy các giá trị được trả về trên toàn cluster có thể không theo thứ tự tăng dần theo thời gian request toàn cục.

Ví dụ minh họa:

~~~text
Instance 1 cache: 1 ... 100
Instance 2 cache: 101 ... 200

Instance 2 cấp: 101, 102
Instance 1 cấp: 1, 2
~~~

Các giá trị vẫn có thể duy nhất trong cấu hình sequence phù hợp, nhưng thứ tự quan sát giữa các instance không nhất thiết tăng dần. Đây là trade-off thường chấp nhận được khi sequence chỉ dùng làm khóa định danh.

### 7.3. ORDER trong RAC có chi phí

Nếu ứng dụng thực sự cần thứ tự cấp số theo request trên các instance, ORDER có thể cần phối hợp giữa các instance và làm tăng chi phí đồng bộ. Với sequence được gọi rất thường xuyên, điều này có thể làm giảm khả năng mở rộng.

Chỉ chọn ORDER khi yêu cầu nghiệp vụ thực sự cần thứ tự cấp số. Đừng bật ORDER chỉ vì muốn ID trông có vẻ liên tục; ORDER không loại bỏ gap.

## 8. Bảng so sánh CACHE/NOCACHE và ORDER/NOORDER

| Tùy chọn | Tác động chính | Lợi ích | Giới hạn |
|---|---|---|---|
| CACHE n | Chuẩn bị trước n giá trị | Thường tăng throughput, giảm chi phí lấy số | Có thể bỏ các số chưa dùng khi instance dừng |
| NOCACHE | Không giữ vùng cache giá trị như CACHE | Tránh mất một vùng cache chưa dùng | Không loại bỏ gap do rollback/lỗi; có thể chậm hơn |
| ORDER | Bảo đảm thứ tự tạo số theo thứ tự yêu cầu | Hữu ích khi thứ tự cấp số toàn cục là yêu cầu | Có thể tăng chi phí đồng bộ, đặc biệt trong RAC |
| NOORDER | Không yêu cầu thứ tự toàn cục | Thường phù hợp cho hiệu năng và RAC | Không thể suy ra thứ tự request toàn cluster từ số |

CACHE/NOCACHE và ORDER/NOORDER là hai lựa chọn độc lập. Ví dụ CACHE 100 NOORDER là cấu hình thường phù hợp cho khóa định danh; NOCACHE ORDER có thể được chọn vì một yêu cầu cụ thể, nhưng vẫn không tạo ra dãy số không có gap.

## 9. Vì sao sequence có khoảng trống khóa?

Gap là hiện tượng có thể xảy ra ngay cả khi không có lỗi trong Oracle. Sequence được thiết kế để cấp số, không phải để bảo đảm số liên tục.

### 9.1. Lấy NEXTVAL rồi ROLLBACK

~~~sql
INSERT INTO lab_order (order_id, customer_name, created_at)
VALUES (lab_order_seq.NEXTVAL, 'An', SYSDATE);

ROLLBACK;
~~~

Dòng đơn hàng bị hủy nhưng giá trị NEXTVAL đã tiêu thụ. Lần INSERT sau nhận giá trị kế tiếp.

### 9.2. INSERT thất bại

Một INSERT có thể lấy NEXTVAL rồi thất bại do vi phạm unique constraint, check constraint, foreign key hoặc lỗi khác. Việc câu lệnh bị rollback không làm sequence lùi.

### 9.3. Ứng dụng lấy số nhưng không dùng

Ví dụ:

~~~sql
SELECT lab_order_seq.NEXTVAL
FROM dual;
~~~

Nếu ứng dụng lấy số để kiểm tra rồi bỏ đi, số đó vẫn đã được cấp. Không cần có INSERT thì sequence mới tăng.

### 9.4. Cache bị bỏ khi instance dừng

Các giá trị cache chưa được dùng có thể bị mất khi instance shutdown hoặc gặp sự cố. Sau khi khởi động lại, sequence có thể tiếp tục ở một vùng cao hơn.

### 9.5. Nhiều session và nhiều instance

Nhiều session cùng lấy số, nhưng một số transaction có thể rollback hoặc không dùng giá trị. Với RAC và NOORDER, việc dùng cache riêng trên từng instance còn khiến thứ tự nhìn thấy có thể khác thứ tự tăng toàn cục.

### 9.6. Cấu hình sequence thay đổi

ALTER SEQUENCE hoặc thao tác quản trị như restart/recreate có thể làm dãy số thay đổi theo cấu hình mới. Khi vận hành, phải kiểm soát việc thay đổi START/INCREMENT/MIN/MAX/CYCLE và không giả định dãy số cũ tiếp tục theo quy tắc trước đó.

## 10. Gap không đồng nghĩa dữ liệu bị mất

Giả sử bảng đơn hàng có các ID:

| ORDER_ID | CUSTOMER_NAME |
|---:|---|
| 1001 | An |
| 1002 | Binh |
| 1005 | Chi |

Việc không có 1003 và 1004 không chứng minh hai đơn hàng đã bị xóa. Các số này có thể đã được cấp cho transaction rollback, câu INSERT thất bại hoặc session không sử dụng.

Muốn biết đơn hàng nào đã được tạo/xóa, hãy truy vấn bảng nghiệp vụ và audit/history. Không dùng phép so sánh khoảng ID để suy ra số bản ghi hoặc số giao dịch thành công.

Ví dụ:

~~~sql
SELECT COUNT(*) AS order_count,
       MIN(order_id) AS min_order_id,
       MAX(order_id) AS max_order_id
FROM lab_order;
~~~

MAX(ORDER_ID) - MIN(ORDER_ID) + 1 không nhất thiết bằng COUNT(*), vì sequence có thể có gap và bảng có thể có xóa dữ liệu.

## 11. Sequence có bảo đảm duy nhất không?

Sequence cung cấp các giá trị khác nhau theo cấu hình và cơ chế cấp số đồng thời, nhưng không thay thế constraint duy nhất trong bảng.

Để dùng sequence làm khóa chính:

~~~sql
CREATE TABLE lab_customer (
    customer_id NUMBER(12) PRIMARY KEY,
    customer_name VARCHAR2(80 CHAR) NOT NULL
);

CREATE SEQUENCE lab_customer_seq
    START WITH 1
    INCREMENT BY 1
    NOCYCLE
    CACHE 100
    NOORDER;

INSERT INTO lab_customer (customer_id, customer_name)
VALUES (lab_customer_seq.NEXTVAL, 'An');
~~~

PRIMARY KEY bảo đảm dữ liệu bảng không chứa hai CUSTOMER_ID giống nhau. NOCYCLE tránh sequence tự quay lại vùng số cũ khi đạt giới hạn. Nếu dùng CYCLE, giá trị có thể được sử dụng lại sau khi chạm giới hạn; không dùng một sequence cycling làm khóa duy nhất lâu dài nếu không có thiết kế bổ sung để xử lý tái sử dụng.

Nếu sequence bị drop/recreate hoặc bị cấu hình lại về vùng số đã dùng, có thể phát sinh xung đột khóa. Quản trị sequence phải xem dữ liệu thực tế và constraint, không chỉ nhìn LAST_NUMBER.

## 12. Cấu hình CYCLE và NOCYCLE

- **NOCYCLE**: sequence dừng khi đạt giới hạn MAXVALUE hoặc MINVALUE; NEXTVAL tiếp theo báo lỗi khi không còn giá trị theo hướng tăng/giảm.
- **CYCLE**: sequence quay lại MINVALUE hoặc MAXVALUE theo hướng increment khi chạm giới hạn.

Ví dụ sequence nhỏ để quan sát:

~~~sql
CREATE SEQUENCE lab_cycle_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1
    MAXVALUE 3
    CYCLE
    NOCACHE
    NOORDER;
~~~

Các lần NEXTVAL sẽ quay vòng qua 1, 2, 3 rồi trở lại 1 theo cấu hình. Vì giá trị có thể lặp, không dùng sequence CYCLE làm primary key đơn giản nếu các giá trị cũ vẫn còn trong bảng.

Ví dụ NOCYCLE:

~~~sql
CREATE SEQUENCE lab_nocycle_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1
    MAXVALUE 3
    NOCYCLE
    NOCACHE
    NOORDER;
~~~

Sau khi cấp hết 1, 2, 3, lần NEXTVAL tiếp theo không thể tiếp tục và Oracle báo lỗi sequence đã đạt giới hạn. NOCYCLE bảo vệ khỏi việc tự động tái sử dụng số nhưng không tạo gap-free sequence.

## 13. INCREMENT BY âm và sequence giảm

Sequence có thể tăng hoặc giảm:

~~~sql
CREATE SEQUENCE lab_countdown_seq
    START WITH 10
    INCREMENT BY -1
    MINVALUE 1
    MAXVALUE 10
    NOCYCLE
    NOCACHE
    NOORDER;
~~~

Các giá trị được cấp lần lượt 10, 9, 8... đến 1. Khi sequence đạt giới hạn theo hướng giảm, NOCYCLE khiến nó dừng. Cần bảo đảm MINVALUE/MAXVALUE phù hợp với hướng increment.

Đa số khóa định danh dùng sequence tăng. Sequence giảm chỉ phù hợp khi có yêu cầu riêng và cần đánh giá kỹ khả năng trùng khóa với dữ liệu đã tồn tại.

## 14. Thay đổi cấu hình bằng ALTER SEQUENCE

Có thể thay đổi một số thuộc tính:

~~~sql
ALTER SEQUENCE lab_order_seq
    INCREMENT BY 1
    CACHE 200
    NOORDER
    NOCYCLE;
~~~

Các thuộc tính có thể điều chỉnh gồm INCREMENT BY, MINVALUE/MAXVALUE, CYCLE/NOCYCLE, CACHE/NOCACHE và ORDER/NOORDER, tùy quy tắc phiên bản và trạng thái sequence. Việc thay đổi cấu hình có thể làm hành vi cấp số thay đổi; cần xem xét ứng dụng đang sử dụng sequence.

Không giả định ALTER SEQUENCE có thể tùy ý đặt lại START WITH cho sequence đang tồn tại. Khả năng restart sequence và cú pháp liên quan phụ thuộc phiên bản Oracle; trước khi thay đổi giá trị hiện tại, hãy kiểm tra tài liệu phiên bản triển khai và bảo đảm không đụng vào khóa đã được lưu.

### 14.1. Xóa sequence

~~~sql
DROP SEQUENCE lab_order_seq;
~~~

DROP SEQUENCE xóa đối tượng sequence. Nó không xóa các dòng trong bảng đã lưu giá trị do sequence cấp. Nếu tạo lại sequence với START WITH thấp hơn các khóa đã có, INSERT sau đó có thể vi phạm primary key.

## 15. Xem cấu hình sequence trong Data Dictionary

Trong schema sở hữu sequence, dùng USER_SEQUENCES:

~~~sql
SELECT
    sequence_name,
    min_value,
    max_value,
    increment_by,
    cycle_flag,
    order_flag,
    cache_size,
    last_number
FROM user_sequences
WHERE sequence_name = 'LAB_ORDER_SEQ';
~~~

Các cột thường cần xem:

| Cột | Ý nghĩa |
|---|---|
| SEQUENCE_NAME | Tên sequence |
| MIN_VALUE / MAX_VALUE | Giới hạn cấu hình |
| INCREMENT_BY | Bước tăng/giảm |
| CYCLE_FLAG | Có quay vòng hay không |
| ORDER_FLAG | Có yêu cầu ORDER hay không |
| CACHE_SIZE | Kích thước cache |
| LAST_NUMBER | Thông tin số kế tiếp/ranh giới cache được ghi trong dictionary |

### 15.1. Cẩn thận khi đọc LAST_NUMBER

Với sequence dùng CACHE, LAST_NUMBER không nhất thiết là giá trị NEXTVAL tiếp theo mà session sẽ nhận. Oracle có thể ghi ranh giới cache cao hơn giá trị đã cấp gần nhất để dự trữ vùng tiếp theo. Do đó, không dùng LAST_NUMBER để khẳng định chính xác “số kế tiếp sẽ được INSERT”.

Đây cũng là lý do sau restart, sequence có thể nhảy tới vùng số cao hơn giá trị cuối cùng mà ứng dụng từng nhìn thấy.

Nếu cần xem giá trị hiện tại của session, sau khi session đã gọi NEXTVAL, dùng CURRVAL trong chính session đó. CURRVAL không phải một giá trị toàn cục cho mọi session.

## 16. Sequence trong RAC và khả năng mở rộng

Trong Oracle RAC, nhiều instance phục vụ cùng một database. Sequence cần hỗ trợ nhiều session trên nhiều instance cùng lấy số.

### 16.1. NOORDER và cache theo instance

Với NOORDER, các instance có thể dùng các vùng cache riêng. Điều này giảm nhu cầu phối hợp thứ tự toàn cục và thường cải thiện khả năng mở rộng. Giá trị có thể được cấp xen kẽ theo thời gian quan sát trên các instance.

### 16.2. ORDER yêu cầu thứ tự toàn cục

ORDER yêu cầu sequence cấp số theo thứ tự request. Trong RAC, điều này có thể cần điều phối giữa các instance và tạo chi phí đồng bộ. Dùng khi thứ tự cấp số thực sự là yêu cầu nghiệp vụ, không dùng chỉ để cố tránh gap.

### 16.3. Scalable sequence

Các phiên bản Oracle mới có thêm các tùy chọn sequence phục vụ workload có tính đồng thời rất cao, chẳng hạn scalable sequence với tùy chọn SCALE. Những sequence này có thể mã hóa thông tin instance/session vào phần giá trị để giảm tranh chấp khi cấp số. Giá trị có thể không còn là dãy tăng liên tục dễ đọc theo từng đơn vị.

Nếu dùng SCALE hoặc EXTEND, cần đọc tài liệu đúng phiên bản Oracle và kiểm tra giới hạn độ dài/kiểu số, tính duy nhất, khả năng tương thích với ứng dụng và cách hiển thị. Không áp dụng cú pháp nâng cao vào môi trường Oracle cũ khi chưa xác nhận phiên bản hỗ trợ.

## 17. Sequence và identity column

Oracle hỗ trợ identity column từ Oracle Database 12c. Identity column giúp khai báo cột tự sinh giá trị trong DDL:

~~~sql
CREATE TABLE lab_identity_order (
    order_id NUMBER GENERATED BY DEFAULT AS IDENTITY
        (START WITH 1 INCREMENT BY 1 CACHE 50),
    customer_name VARCHAR2(80 CHAR) NOT NULL,
    created_at DATE NOT NULL,
    CONSTRAINT pk_lab_identity_order PRIMARY KEY (order_id)
);
~~~

Có hai chế độ thường gặp:

- GENERATED ALWAYS AS IDENTITY: Oracle luôn tạo giá trị identity; người dùng không thể tùy ý cung cấp giá trị cho cột trong INSERT thông thường.
- GENERATED BY DEFAULT AS IDENTITY: Oracle tạo giá trị khi INSERT không cung cấp cột; ứng dụng có thể cung cấp giá trị tường minh theo quy tắc của chế độ.

Một biến thể là GENERATED BY DEFAULT ON NULL AS IDENTITY, cho phép Oracle tạo giá trị khi cột bị bỏ qua hoặc truyền NULL.

| Tiêu chí | Sequence tường minh | Identity column |
|---|---|---|
| Cách dùng | Gọi NEXTVAL trong SQL/PLSQL | Oracle tự cấp cho cột |
| Dùng chung cho nhiều bảng | Có | Identity gắn với cột của bảng |
| Điều khiển sequence trực tiếp | Có | Có các thuộc tính identity và sequence nội bộ được Oracle quản lý |
| Có gap khi rollback/cache? | Có | Có thể có |
| Phù hợp | Nhiều đối tượng cần chia sẻ bộ cấp số hoặc logic cấp số riêng | Cột khóa tự sinh thông thường |

Identity column thường được hỗ trợ bởi cơ chế sequence nội bộ; không nên giả định nó tạo số không gap. Nếu yêu cầu là khóa định danh kỹ thuật, cả sequence và identity đều là lựa chọn phù hợp tùy thiết kế.

## 18. Vì sao không dùng sequence cho số chứng từ bắt buộc liên tục?

Khóa định danh kỹ thuật và số chứng từ nghiệp vụ là hai mục đích khác nhau.

- Khóa định danh cần phân biệt dòng và hỗ trợ JOIN/constraint.
- Số chứng từ có thể phải tuân thủ quy tắc đánh số theo năm, chi nhánh, loại chứng từ hoặc quy định kiểm toán.

Sequence có thể có gap do rollback, lỗi, cache loss và concurrency. ORDER hoặc NOCACHE không giải quyết tất cả nguyên nhân đó. Vì vậy, nếu nghiệp vụ yêu cầu kiểm soát số chứng từ liên tục, không nên mặc định dùng sequence thông thường.

Một phương án có thể là bảng cấp số nghiệp vụ được khóa theo phạm vi (ví dụ loại chứng từ và năm), chỉ tăng số trong transaction phát hành chứng từ và kiểm soát việc hủy bằng trạng thái/biên bản. Cách này tạo điểm đồng bộ, có thể giảm throughput và vẫn cần quy tắc rõ cho chứng từ đã phát hành nhưng bị hủy. Yêu cầu pháp lý phụ thuộc ngành và khu vực; cần thiết kế theo quy định cụ thể.

Không nên tái sử dụng số đã phát hành chỉ để lấp gap nếu quy định kiểm toán yêu cầu giữ dấu vết. Nhiều hệ thống lưu chứng từ hủy với trạng thái CANCELLED thay vì xóa dòng để giải thích khoảng trống.

## 19. Các lỗi thường gặp khi dùng sequence

| Dấu hiệu | Nguyên nhân | Cách xử lý |
|---|---|---|
| ORA-08002 | Session gọi CURRVAL trước khi gọi NEXTVAL | Gọi NEXTVAL trong cùng session trước |
| ORA-08004 | Sequence đạt giới hạn MAXVALUE/MINVALUE với NOCYCLE | Xem lại giới hạn, increment và chiến lược sequence |
| ORA-00001 khi INSERT | Sequence bị cấu hình lại, cycle/restart hoặc dữ liệu khóa đã tồn tại | Kiểm tra PK, dữ liệu hiện có và cấu hình sequence |
| ID nhảy số sau ROLLBACK | NEXTVAL không transactional | Đây là hành vi bình thường; không cố rollback sequence |
| ID nhảy sau restart | Cache chưa dùng bị bỏ | Chấp nhận gap hoặc chọn cache theo yêu cầu vận hành |
| ID không tăng theo thời gian commit trong RAC | NOORDER hoặc transaction hoàn tất khác thứ tự | Không dùng sequence ID làm đồng hồ commit; dùng timestamp/audit phù hợp |
| LAST_NUMBER lớn hơn ID cuối đã dùng | Dictionary phản ánh ranh giới cache | Không coi LAST_NUMBER là giá trị kế tiếp chính xác |
| Nhiều bảng dùng chung sequence có khoảng số xen kẽ | Các session/bảng cùng tiêu thụ một sequence | Xác định rõ phạm vi cấp số; dùng sequence riêng nếu cần phân vùng |

## 20. Bài tập thực hành

### Bài 1 — Tạo sequence và lấy NEXTVAL

Tạo sequence bắt đầu từ 500, tăng 1, NOCYCLE, CACHE 20 và NOORDER. Gọi NEXTVAL năm lần.

**Câu hỏi:** Các giá trị trả về là gì nếu không có session nào khác sử dụng sequence?

### Bài 2 — CURRVAL theo session

Mở hai session A và B. A gọi NEXTVAL; B gọi NEXTVAL; sau đó cả hai gọi CURRVAL.

**Câu hỏi:** Vì sao CURRVAL ở A không đổi khi B lấy số mới?

### Bài 3 — ROLLBACK và gap

INSERT một dòng bằng NEXTVAL rồi ROLLBACK. INSERT dòng tiếp theo.

**Câu hỏi:** Vì sao ID của dòng thứ hai không quay về giá trị đã dùng trong transaction rollback?

### Bài 4 — CACHE và NOCACHE

Tạo hai sequence, một CACHE 50 và một NOCACHE. Quan sát metadata trong USER_SEQUENCES. Thảo luận điều gì có thể xảy ra với vùng cache khi instance restart.

### Bài 5 — ORDER và NOORDER

Tạo hai sequence với cùng START/INCREMENT, một ORDER và một NOORDER. So sánh cấu hình trong USER_SEQUENCES.

**Câu hỏi:** ORDER có bảo đảm transaction commit theo thứ tự số không?

**Đáp án:** Không. ORDER liên quan thứ tự tạo số, không phải thứ tự COMMIT.

### Bài 6 — NOCYCLE và CYCLE

Tạo sequence MINVALUE 1 MAXVALUE 3, lần lượt thử NOCYCLE và CYCLE.

**Câu hỏi:** Điều gì xảy ra sau khi cấp hết ba số? Cấu hình nào có thể tái sử dụng giá trị cũ?

### Bài 7 — Sequence làm khóa chính

Tạo bảng có PRIMARY KEY, tạo sequence và INSERT nhiều dòng. Sau đó thử INSERT một ID đã tồn tại.

**Câu hỏi:** Vai trò của sequence và primary key khác nhau thế nào?

**Đáp án định hướng:** sequence cấp giá trị; primary key bảo đảm duy nhất trong bảng.

### Bài 8 — LAST_NUMBER

Đọc LAST_NUMBER của sequence cache lớn sau khi đã gọi một vài NEXTVAL.

**Câu hỏi:** Vì sao không nên dùng LAST_NUMBER làm giá trị kế tiếp chính xác?

### Bài 9 — Sequence hay identity?

Thiết kế bảng đơn hàng và bảng chi tiết. Quyết định nên dùng sequence tường minh hay identity cho khóa đơn hàng và giải thích liệu cách chọn có loại bỏ gap không.

### Bài 10 — Số chứng từ liên tục

Một hệ thống yêu cầu số hóa đơn có thể giải trình mọi số bị bỏ. Đề xuất mô hình quản lý số và trạng thái chứng từ, giải thích vì sao CACHE/ORDER/NOCACHE của sequence không đủ để bảo đảm dãy không gap.

## 21. Quy trình chọn cấu hình sequence

Trước khi tạo sequence, trả lời các câu hỏi:

1. Sequence dùng cho khóa định danh hay số nghiệp vụ?
2. Một hay nhiều bảng sẽ dùng chung sequence?
3. Có cần thứ tự cấp số toàn cục không, hay chỉ cần giá trị duy nhất?
4. Hệ thống chạy single instance hay RAC?
5. Throughput cấp số dự kiến là bao nhiêu?
6. Mức gap có thể chấp nhận là gì?
7. Có cần CYCLE hay phải dừng khi chạm giới hạn?
8. Có cần NOCACHE vì yêu cầu vận hành đặc thù, và đã hiểu chi phí chưa?
9. Có thể dùng identity column để đơn giản hóa DDL không?
10. Có constraint PRIMARY KEY/UNIQUE bảo vệ cột nhận giá trị không?

Gợi ý lựa chọn:

| Nhu cầu | Cấu hình thường xem xét |
|---|---|
| Khóa định danh thông thường, workload vừa/lớn | CACHE, NOORDER, NOCYCLE |
| Khóa định danh trong RAC | CACHE, NOORDER thường là điểm bắt đầu hợp lý |
| Cần thứ tự cấp số theo request | ORDER sau khi đánh giá chi phí |
| Muốn giảm rủi ro mất vùng cache khi restart | NOCACHE, nhưng vẫn chấp nhận gap do rollback/lỗi |
| Muốn dãy số không bao giờ tự quay lại | NOCYCLE và giới hạn phù hợp |
| Cột tự sinh trong một bảng | Cân nhắc identity column |
| Số chứng từ cần giải trình gap | Thiết kế bộ cấp số nghiệp vụ và audit riêng |

Sơ đồ:

~~~text
Xác định mục đích cấp số
          |
          v
Khóa định danh hay số nghiệp vụ?
       /                 \
   Định danh            Nghiệp vụ
      |                    |
      v                    v
Sequence / Identity   Thiết kế quy tắc phát hành
      |               và audit theo nghiệp vụ
      v
Single instance hay RAC?
      |
      v
Có cần thứ tự cấp số toàn cục?
      |                 |
     Không              Có
      |                 |
      v                 v
   NOORDER             ORDER
      |                 |
      +--------+--------+
               |
               v
        Chọn CACHE/NOCACHE
               |
               v
        Chọn CYCLE/NOCYCLE
               |
               v
     Bảo vệ cột bằng PK/UNIQUE
               |
               v
       Kiểm tra gap và vận hành
~~~

Sequence là bộ cấp số độc lập với transaction. NEXTVAL lấy số mới; CURRVAL nhớ số gần nhất trong session; CACHE tối ưu việc cấp số; ORDER kiểm soát thứ tự yêu cầu cấp số. ROLLBACK không thu hồi số đã cấp, cache có thể mất các giá trị chưa dùng và NOORDER trong RAC không bảo đảm thứ tự toàn cục. Vì vậy, sequence phù hợp để tạo khóa định danh có khả năng mở rộng, còn số chứng từ cần liên tục phải được quản lý bằng quy tắc nghiệp vụ và cơ chế kiểm soát riêng.

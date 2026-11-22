# RESULT_CACHE, điều kiện phù hợp và phụ thuộc dữ liệu trong PL/SQL

Oracle PL/SQL có thể lưu kết quả của một function trong **server result cache** bằng mệnh đề `RESULT_CACHE`. Khi function được gọi lại với cùng tham số và các dữ liệu mà function phụ thuộc chưa thay đổi, Oracle có thể trả kết quả đã lưu mà không phải chạy lại phần thân function. Cơ chế này hữu ích cho các phép tra cứu tương đối tốn kém, được gọi lặp lại và dựa trên dữ liệu thay đổi không thường xuyên.

Result cache không phải cách biến mọi function thành hàm nhanh hơn. Function chỉ phù hợp khi kết quả có thể được tái sử dụng an toàn giữa các lần gọi và giữa các session. Nếu function phụ thuộc vào package variable, thời gian hiện tại, sequence, người dùng hiện tại hoặc NLS/session context mà không đưa các giá trị đó vào đầu vào một cách rõ ràng, cache có thể trả kết quả không đúng ngữ cảnh. Nếu bảng phụ thuộc thay đổi liên tục, cache thường xuyên bị invalidated và chi phí quản lý có thể lớn hơn lợi ích.

Bài học thuộc chủ đề **PL/SQL nâng cao** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Cách khai báo và hoạt động của PL/SQL function result cache.
- Điều kiện phù hợp, tính thuần (purity) và các phụ thuộc dữ liệu.
- Cache key, tham số function và session-specific context.
- Theo dõi phụ thuộc bảng và tự động invalidation sau commit.
- Hành vi trong transaction, nhiều session và Oracle RAC.
- Khác biệt giữa PL/SQL function result cache và SQL query result cache.
- Giám sát bằng DBMS_RESULT_CACHE và các V$ views.
- Bài thực hành tạo function, quan sát cache hit và invalidation.

## 1. Result cache là gì?

Result cache là vùng bộ nhớ dùng chung trong SGA để lưu kết quả có thể tái sử dụng. Với PL/SQL function result cache, function được đánh dấu `RESULT_CACHE` để Oracle quản lý kết quả theo giá trị tham số và các phụ thuộc dữ liệu mà function sử dụng.

Luồng xử lý khái quát:

~~~text
Caller invokes function(parameters)
              |
              v
       Build/find cache key
              |
       +------+------+
       |             |
    Cache hit     Cache miss
       |             |
       v             v
 Return cached    Execute function
 result           body and query data
       |             |
       |             v
       |          Store result
       |          if cacheable
       |             |
       +------+------+
              |
              v
         Return value
~~~

Khi cache hit, Oracle trả về kết quả đã lưu. Khi cache miss, function chạy bình thường; nếu kết quả và ngữ cảnh đủ điều kiện, Oracle lưu kết quả để những lần gọi sau có thể dùng lại.

### Phạm vi cache

- Cache nằm trong SGA của database instance, không nằm trong PGA riêng của session.
- Nhiều session trên cùng instance có thể dùng chung kết quả đã cache.
- Cache có thể bị thay thế/giải phóng do áp lực bộ nhớ, quản trị hoặc invalidation.
- Kết quả cache không phải dữ liệu bền vững; không được coi nó như bảng lưu trữ.
- Trong Oracle RAC, result cache là cache theo instance; các instance có vùng cache riêng và Oracle phối hợp invalidation giữa các instance khi dữ liệu phụ thuộc thay đổi.

Result cache là tối ưu hiệu năng. Function vẫn phải trả đúng kết quả theo semantics của chương trình khi cache không có entry, bị flush hoặc bị invalidated.

## 2. Khai báo function với RESULT_CACHE

Mệnh đề `RESULT_CACHE` được đặt trong phần khai báo function, sau kiểu trả về:

~~~sql
CREATE OR REPLACE FUNCTION get_tax_rate (
    p_region_code IN VARCHAR2
)
RETURN NUMBER
RESULT_CACHE
IS
    l_rate NUMBER;
BEGIN
    SELECT tax_rate
    INTO l_rate
    FROM tax_configuration
    WHERE region_code = p_region_code;

    RETURN l_rate;
END get_tax_rate;
/
~~~

Function này tra cứu mức thuế theo mã vùng. Khi nhiều session gọi `get_tax_rate('APAC')` và dữ liệu cấu hình liên quan chưa thay đổi, Oracle có thể dùng chung kết quả đã cache.

### Gọi function

~~~sql
SELECT get_tax_rate('APAC')
FROM dual;
~~~

Hoặc từ PL/SQL:

~~~sql
DECLARE
    l_rate NUMBER;
BEGIN
    l_rate := get_tax_rate('APAC');
    DBMS_OUTPUT.PUT_LINE(l_rate);
END;
/
~~~

Lần gọi đầu thường cần chạy function để tạo cache entry. Lần gọi sau với cùng tham số và dependency còn hợp lệ có thể là cache hit. Không nên dựa vào số lần chạy body trong code nghiệp vụ; result cache có thể bị bypass hoặc entry có thể bị loại bỏ bất kỳ lúc nào.

### Function trong package

Function public có thể khai báo `RESULT_CACHE` trong package specification:

~~~sql
CREATE OR REPLACE PACKAGE tax_api AS
    FUNCTION tax_rate(
        p_region_code IN VARCHAR2
    ) RETURN NUMBER RESULT_CACHE;
END tax_api;
/
~~~

Phần triển khai:

~~~sql
CREATE OR REPLACE PACKAGE BODY tax_api AS
    FUNCTION tax_rate(
        p_region_code IN VARCHAR2
    ) RETURN NUMBER RESULT_CACHE
    IS
        l_rate NUMBER;
    BEGIN
        SELECT tax_rate
        INTO l_rate
        FROM tax_configuration
        WHERE region_code = p_region_code;

        RETURN l_rate;
    END tax_rate;
END tax_api;
/
~~~

Nếu function được công bố trong specification, chữ ký và thuộc tính của phần triển khai phải nhất quán. Private function trong package body cũng có thể được khai báo result-cached nếu phù hợp.

### RESULT_CACHE không giống DETERMINISTIC

`DETERMINISTIC` là lời khẳng định của người viết rằng function trả cùng kết quả cho cùng input theo điều kiện của thuộc tính deterministic; Oracle không tự theo dõi đầy đủ bảng mà function truy vấn chỉ vì có từ khóa này. `RESULT_CACHE` là cơ chế lưu kết quả và quản lý phụ thuộc dữ liệu để tái sử dụng. Hai thuộc tính có mục đích khác nhau; không thêm cả hai theo thói quen hoặc xem chúng là từ đồng nghĩa.

## 3. Điều kiện phù hợp: function phải có kết quả có thể tái sử dụng

Một function phù hợp với result cache thường có những đặc điểm:

- Cùng tập tham số và cùng trạng thái dữ liệu phụ thuộc phải tạo ra cùng kết quả.
- Không tạo side effect như INSERT/UPDATE/DELETE, ghi file, gửi message hoặc thay đổi trạng thái bên ngoài.
- Không dựa vào trạng thái session ẩn nếu trạng thái đó chưa được biểu diễn trong tham số/cache key.
- Có chi phí tính toán hoặc truy vấn đủ lớn để việc tái sử dụng đáng giá.
- Kết quả được gọi lặp lại nhiều lần trong khi dữ liệu phụ thuộc thay đổi tương đối ít.
- Kích thước kết quả và số lượng key không làm cache bị chiếm dụng quá mức.

### Ví dụ phù hợp

Function tra cứu mã vùng, thuế suất, cấu hình sản phẩm, thông tin loại tiền hoặc bảng tham chiếu ít thay đổi thường có cơ hội hưởng lợi:

~~~sql
CREATE OR REPLACE FUNCTION get_country_name (
    p_country_code IN VARCHAR2
)
RETURN VARCHAR2
RESULT_CACHE
IS
    l_country_name countries.country_name%TYPE;
BEGIN
    SELECT country_name
    INTO l_country_name
    FROM countries
    WHERE country_code = p_country_code;

    RETURN l_country_name;
END get_country_name;
/
~~~

Function có đầu vào tường minh, đọc một bảng tham chiếu và trả về một giá trị. Nếu danh mục quốc gia ít thay đổi và được tra cứu thường xuyên, result cache có thể giảm số lần thực hiện SELECT.

### Ví dụ không phù hợp: kết quả phụ thuộc thời gian

~~~sql
CREATE OR REPLACE FUNCTION current_time_text
RETURN VARCHAR2
RESULT_CACHE
IS
BEGIN
    RETURN TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF');
END current_time_text;
/
~~~

Kết quả thay đổi theo thời điểm gọi dù không có tham số. Cache không thể coi kết quả của lần gọi trước là kết quả đúng cho lần gọi sau. Không đánh dấu function dạng này RESULT_CACHE; gọi SYSTIMESTAMP trực tiếp hoặc truyền mốc thời gian làm tham số nếu muốn cache một phép tính dựa trên mốc đó.

### Ví dụ không phù hợp: side effect

Function có nhiệm vụ tăng counter, ghi audit hoặc cập nhật trạng thái không nên dùng result cache:

~~~sql
CREATE OR REPLACE PROCEDURE increment_business_counter (
    p_new_value OUT NUMBER
)
IS
BEGIN
    UPDATE business_counter
    SET counter_value = counter_value + 1
    RETURNING counter_value INTO p_new_value;
END increment_business_counter;
/
~~~

Đây là procedure vì thao tác có side effect. Một function có side effect không phải phép tính có thể bỏ qua lần thực thi khi cache hit. Hãy dùng procedure/sequence hoặc cơ chế cấp số phù hợp, không dùng result cache.

## 4. Tham số và cache key

Oracle dùng các giá trị tham số đầu vào để xác định một lần gọi có thể dùng cache entry nào. Vì vậy, mọi thông tin làm thay đổi kết quả phải được thể hiện trong tham số hoặc được quản lý bằng cơ chế dependency mà Oracle theo dõi.

### Tham số phải biểu diễn đầy đủ đầu vào logic

Ví dụ function tính giá sau thuế theo vùng:

~~~sql
CREATE OR REPLACE FUNCTION price_with_tax (
    p_net_amount IN NUMBER,
    p_region_code IN VARCHAR2
)
RETURN NUMBER
RESULT_CACHE
IS
    l_tax_rate NUMBER;
BEGIN
    SELECT tax_rate
    INTO l_tax_rate
    FROM tax_configuration
    WHERE region_code = p_region_code;

    RETURN p_net_amount * (1 + l_tax_rate);
END price_with_tax;
/
~~~

Kết quả phụ thuộc vào cả net amount lẫn region code, nên cả hai đều phải là tham số. Nếu chỉ truyền amount rồi đọc region từ package variable hoặc session context, hai session có thể gọi cùng key nhưng cần kết quả khác nhau.

### Tham số IN và không có OUT/IN OUT

Function result-cached dùng tham số đầu vào để xác định kết quả. Không thiết kế function result-cached với OUT hoặc IN OUT parameter; function nên trả kết quả qua RETURN value. Nếu cần trả nhiều giá trị, dùng record/collection được hỗ trợ hoặc thiết kế API khác, đồng thời xác nhận datatype phù hợp với phiên bản Oracle.

### NULL cũng là một đầu vào

Nếu tham số nullable, phải định nghĩa rõ ý nghĩa NULL:

~~~sql
CREATE OR REPLACE FUNCTION get_discount_rate (
    p_customer_tier IN VARCHAR2
)
RETURN NUMBER
RESULT_CACHE
IS
    l_rate NUMBER;
BEGIN
    SELECT discount_rate
    INTO l_rate
    FROM discount_tiers
    WHERE tier_code = p_customer_tier;

    RETURN l_rate;
END get_discount_rate;
/
~~~

Nếu p_customer_tier là NULL, điều kiện `tier_code = NULL` không trả hàng vì so sánh với NULL cho UNKNOWN. Hãy quyết định NULL có nghĩa “không có tier”, “tier mặc định” hay dữ liệu lỗi và xử lý tường minh. Cache key phải phản ánh đầu vào thực tế; đừng dựa vào implicit conversion hoặc NLS để chuẩn hóa tham số.

### Chuẩn hóa đầu vào

Nếu nghiệp vụ coi mã vùng không phân biệt hoa/thường, hãy chuẩn hóa trước khi gọi hoặc ngay trong function bằng một quy tắc rõ ràng:

~~~sql
FUNCTION get_region_rate(p_region_code IN VARCHAR2)
RETURN NUMBER
RESULT_CACHE
IS
    l_rate NUMBER;
    l_code VARCHAR2(30) := UPPER(TRIM(p_region_code));
BEGIN
    SELECT tax_rate
    INTO l_rate
    FROM tax_configuration
    WHERE region_code = l_code;

    RETURN l_rate;
END;
~~~

Các cách viết APAC, apac và khoảng trắng đầu/cuối có thể tạo những cache key khác nhau dù function chuẩn hóa về cùng một mã. Nếu caller chuẩn hóa thống nhất trước khi gọi, tránh tạo nhiều key tương đương. Không để kết quả chuẩn hóa phụ thuộc NLS/session nếu các session phải dùng chung cache.

## 5. Phụ thuộc dữ liệu: Oracle theo dõi điều gì?

Function result cache đặc biệt hữu ích khi function truy vấn bảng. Oracle theo dõi các đối tượng dữ liệu mà function phụ thuộc và quản lý tính hợp lệ của kết quả cache theo thay đổi dữ liệu đã commit.

Ví dụ function tra cứu thuế:

~~~sql
CREATE OR REPLACE FUNCTION lookup_tax (
    p_region_code IN VARCHAR2
)
RETURN NUMBER
RESULT_CACHE
IS
    l_tax_rate NUMBER;
BEGIN
    SELECT tax_rate
    INTO l_tax_rate
    FROM tax_configuration
    WHERE region_code = p_region_code;

    RETURN l_tax_rate;
END lookup_tax;
/
~~~

Khi function chạy, Oracle nhận biết bảng TAX_CONFIGURATION được truy vấn. Nếu một transaction thay đổi dữ liệu bảng này rồi COMMIT, cache entries phụ thuộc dữ liệu thay đổi sẽ bị invalidated để lần gọi sau không dùng kết quả cũ.

### Dependency được theo dõi tự động

Với SQL tĩnh trong function, Oracle có thể xác định các table/view được truy cập và ghi nhận dependency. Việc theo dõi dependency cho phép result cache biết khi nào dữ liệu nguồn đã thay đổi.

Trong code mới, không nên dựa vào `RELIES_ON` để khai báo thủ công mọi bảng như một giải pháp mặc định. Cơ chế dependency của function result cache được Oracle tự theo dõi; `RELIES_ON` là cú pháp cũ/legacy trong các phiên bản Oracle trước và đã bị deprecated trong các phiên bản mới. Khi bảo trì hệ thống cũ, kiểm tra tài liệu đúng phiên bản trước khi thay đổi hoặc xóa clause này.

### Thay đổi chưa COMMIT

Transaction A cập nhật TAX_CONFIGURATION nhưng chưa COMMIT. Transaction B vẫn nhìn thấy dữ liệu đã commit theo isolation của Oracle và có thể tiếp tục dùng cache entry tương ứng với trạng thái đã commit. Khi A COMMIT, Oracle invalidates kết quả phụ thuộc; các lần gọi sau sẽ tính lại theo dữ liệu mới.

Trong chính session đang thay đổi bảng phụ thuộc, Oracle có thể bypass result cache cho function phụ thuộc bảng đó trong transaction để không trả dữ liệu cache cũ thay cho thay đổi chưa commit của session. Sau COMMIT/ROLLBACK, cơ chế cache tiếp tục theo trạng thái dữ liệu hợp lệ.

### Dependency có thể gián tiếp

Function có thể truy vấn view hoặc gọi function khác; dependency có thể phát sinh qua chuỗi object. Hãy hiểu dependency ở cấp dữ liệu được truy cập, không chỉ nhìn tên bảng xuất hiện trực tiếp trong source của function ngoài cùng.

Nếu function dùng dynamic SQL, synonym, view hoặc gọi package/function khác, hãy kiểm tra kỹ dependency thực tế và phiên bản Oracle. Không giả định mọi nguồn dữ liệu động hoặc bên ngoài đều được theo dõi như một câu SELECT tĩnh đơn giản.

### Những thứ không tự động được xem là table dependency

Result cache không thể suy ra mọi trạng thái ẩn trong PL/SQL. Ví dụ:

- Package variables hoặc biến global khác.
- Sequence NEXTVAL/CURRVAL.
- SYSDATE, SYSTIMESTAMP hoặc giá trị ngẫu nhiên.
- SYS_CONTEXT, application context hoặc identity người dùng.
- NLS settings, time zone, current schema và các session settings.
- File, HTTP service, message queue hoặc dữ liệu ngoài database.

Nếu kết quả phụ thuộc vào một giá trị như vậy, hãy đưa nó thành tham số tường minh khi phù hợp hoặc không dùng result cache. Không trông chờ invalidation của bảng để làm mới các trạng thái không phải dependency dữ liệu được theo dõi.

## 6. Session-specific context và kết quả dùng chung

PL/SQL function result cache có thể chia sẻ kết quả giữa các session trên cùng instance. Vì thế function phải không phụ thuộc ngầm vào danh tính hoặc thiết lập riêng của session.

### Ví dụ nguy hiểm: người dùng hiện tại

~~~sql
CREATE OR REPLACE FUNCTION current_user_discount
RETURN NUMBER
RESULT_CACHE
IS
    l_discount NUMBER;
BEGIN
    SELECT discount_rate
    INTO l_discount
    FROM user_discounts
    WHERE username = SYS_CONTEXT('USERENV', 'SESSION_USER');

    RETURN l_discount;
END current_user_discount;
/
~~~

Kết quả phụ thuộc SESSION_USER nhưng function không có tham số. Nếu dùng cache chung như thể kết quả chỉ phụ thuộc vào tham số rỗng, người dùng khác có thể cần kết quả khác. Không thiết kế function này như một function result-cached không tham số.

### Đưa ngữ cảnh thành tham số tường minh

~~~sql
CREATE OR REPLACE FUNCTION user_discount (
    p_username IN VARCHAR2
)
RETURN NUMBER
RESULT_CACHE
IS
    l_discount NUMBER;
BEGIN
    SELECT discount_rate
    INTO l_discount
    FROM user_discounts
    WHERE username = p_username;

    RETURN l_discount;
END user_discount;
/
~~~

Giờ username là một phần của đầu vào. Tuy nhiên, chỉ truyền username không tự giải quyết authorization: caller vẫn phải được xác thực và được phép yêu cầu dữ liệu đó. Không dùng result cache để thay thế kiểm tra quyền truy cập.

### NLS, timezone và định dạng

Một function trả chuỗi đã định dạng theo NLS_DATE_LANGUAGE hoặc NLS_NUMERIC_CHARACTERS có thể cho kết quả khác giữa các session dù tham số giống nhau. Cách an toàn là:

- Trả DATE/NUMBER nguyên bản và để caller định dạng ở tầng cần hiển thị.
- Hoặc truyền locale/time zone/format cần thiết thành tham số rõ ràng.
- Tránh đọc session setting ẩn trong function result-cached.

### Tenant và application context

Trong ứng dụng multi-tenant, function đọc tenant id từ SYS_CONTEXT có thể tạo rủi ro cache chéo tenant nếu context không được thể hiện đúng trong key hoặc cơ chế cache không bảo đảm tách biệt. Truyền tenant id thành tham số tường minh và kiểm tra quyền caller; không xem application context như dependency bảng tự động.

### Session context có thể thay đổi trong cùng session

Connection pool có thể tái sử dụng session cho nhiều request. Nếu package variable hoặc application context thay đổi theo request, function result-cached phụ thuộc vào các giá trị đó có nguy cơ trả kết quả không đúng nếu chúng không được phản ánh trong tham số/cache identity. Ưu tiên tham số tường minh và cleanup session state.

## 7. Transaction, commit và invalidation

Result cache phải phản ánh dữ liệu đã commit mà transaction hiện tại được phép nhìn thấy. Oracle phối hợp cache với transaction để không dùng kết quả cũ sau khi dữ liệu phụ thuộc thay đổi.

### Thay đổi dữ liệu phụ thuộc

Giả sử function LOOKUP_TAX đọc TAX_CONFIGURATION:

~~~sql
SELECT lookup_tax('APAC') FROM dual;
~~~

Sau lần gọi đầu, kết quả có thể được cache. Khi một transaction cập nhật:

~~~sql
UPDATE tax_configuration
SET tax_rate = 0.09
WHERE region_code = 'APAC';
~~~

Trước COMMIT, transaction đó nhìn thấy thay đổi của chính nó theo quy tắc read consistency; các session khác vẫn nhìn thấy dữ liệu đã commit trước đó. Khi transaction COMMIT, cache entries phụ thuộc vào thay đổi đã commit sẽ bị invalidated. Lần gọi tiếp theo phải tính lại từ dữ liệu mới.

### ROLLBACK

Nếu transaction rollback, thay đổi không trở thành dữ liệu đã commit. Oracle không cần làm cache phản ánh một giá trị chưa bao giờ được commit. Cache entry hợp lệ với trạng thái dữ liệu trước transaction có thể tiếp tục được sử dụng sau rollback.

### Session thực hiện DML trên dependency

Khi session sửa một bảng mà function result-cached phụ thuộc, result cache có thể bị bypass cho các lần gọi function trong transaction đó để tránh trả kết quả cache không phản ánh thay đổi của session. Sau COMMIT, cache entry cũ bị invalidated; sau ROLLBACK, dữ liệu cũ vẫn là trạng thái đã commit.

Không dùng cache như một cách đọc dữ liệu uncommitted của session khác. Result cache phục vụ dữ liệu theo transaction consistency của Oracle, không phải kênh chia sẻ thay đổi chưa commit.

### Invalidation có thể ảnh hưởng nhiều entry

Một bảng thay đổi có thể là dependency của nhiều kết quả khác nhau, ví dụ nhiều region code trong cùng bảng cấu hình. Oracle invalidates các cache result phụ thuộc vào đối tượng thay đổi theo cơ chế quản lý dependency; phạm vi cụ thể có thể rộng hơn một key duy nhất tùy object/dependency. Vì vậy, bảng cập nhật thường xuyên có thể làm tỷ lệ hit giảm mạnh.

### DDL và thay đổi cấu trúc

Các thay đổi metadata trên đối tượng phụ thuộc có thể làm invalidated object hoặc result cache entry liên quan. Sau deploy DDL, recompile hoặc thay đổi schema, hãy theo dõi object validity và result cache; đừng giả định cache entry cũ luôn còn hợp lệ.

## 8. Oracle RAC và nhiều instance

Trong RAC, mỗi instance có SGA và result cache riêng. Một cache entry được tạo trên instance 1 không phải một vùng bộ nhớ trực tiếp mà instance 2 đọc được. Mỗi instance có thể xây dựng cache riêng từ các lần gọi trên instance đó.

Khi transaction trên một instance commit thay đổi dữ liệu mà result cache ở các instance khác phụ thuộc, Oracle phối hợp invalidation để tránh sử dụng kết quả đã lỗi thời. Việc phối hợp này có chi phí giao tiếp và đồng bộ; workload cập nhật dependency liên tục có thể làm giảm lợi ích của cache trên RAC.

### Hệ quả vận hành

- Không giả định cache hit trên instance A đồng nghĩa cache hit trên instance B.
- Cùng một function có thể được tính lại trên từng instance.
- DML commit trên một instance có thể làm cache entry phụ thuộc bị invalidated ở các instance khác.
- Theo dõi thống kê và memory của từng instance khi phân tích RAC.
- Kiểm tra service routing/load balancing vì request có thể được phân phối sang instance khác.

### Không dùng result cache làm kho dữ liệu chia sẻ

Result cache là tối ưu hiệu năng và có thể bị flush, invalidated hoặc aged out. Dữ liệu cần bền vững hoặc đồng bộ giữa instance phải nằm trong bảng hoặc hệ thống lưu trữ thích hợp.

## 9. Khi nào result cache bị bypass hoặc không còn hiệu quả?

Khai báo RESULT_CACHE không bảo đảm mọi lần gọi đều là cache hit. Oracle có thể không dùng cache hoặc không lưu kết quả trong một số tình huống:

- Function phụ thuộc trạng thái session hoặc giá trị không được thể hiện đầy đủ trong tham số.
- Function có side effect hoặc dùng các thao tác không phù hợp với result caching.
- Session đang thay đổi dữ liệu mà function phụ thuộc.
- Result cache bị disable/bypass ở mức instance hoặc session.
- Cache entry bị invalidated do dependency thay đổi.
- Cache entry bị loại bỏ do áp lực bộ nhớ hoặc chính sách quản lý.
- Kiểu dữ liệu tham số/kết quả hoặc cách triển khai không được result cache hỗ trợ trong phiên bản đang dùng.
- Function phát sinh exception thay vì trả về một kết quả bình thường có thể tái sử dụng.

### Không dựa vào số lần function body được chạy

Không viết logic nghiệp vụ dựa trên giả định “function chỉ chạy một lần”. Cache có thể miss, bị xóa, bị bypass hoặc bị invalidated bất kỳ lúc nào. Function phải luôn đúng khi thực thi lại.

### Result cache không thay thế materialized view

Nếu cần lưu và quản lý một tập dữ liệu dẫn xuất lớn, refresh theo lịch hoặc theo commit, materialized view có thể phù hợp hơn. Function result cache phù hợp với kết quả function theo tham số và dependency; nó không phải bảng tổng hợp có schema và query plan riêng.

### Result cache không thay thế index

Nếu function chạy chậm vì truy vấn không có index phù hợp, cache có thể giúp các lần gọi lặp lại nhưng cache miss vẫn chậm. Tối ưu SQL, index, statistics và access path trước khi đánh giá cache.

## 10. Kích thước, tần suất thay đổi và hiệu quả cache

Result cache tiêu thụ bộ nhớ SGA. Kết quả lớn, nhiều key ít được dùng hoặc dependency thay đổi thường xuyên có thể khiến cache chiếm bộ nhớ nhưng ít hit.

Các yếu tố nên xem xét:

- **Reuse:** cùng key được gọi lại bao nhiêu lần?
- **Computation cost:** chạy function và SQL bên trong tốn bao nhiêu CPU/I/O?
- **Invalidation frequency:** bảng dependency thay đổi bao thường xuyên?
- **Result size:** mỗi kết quả chiếm bao nhiêu bộ nhớ?
- **Key cardinality:** số lượng tổ hợp tham số có thể phát sinh là bao nhiêu?
- **Concurrency:** nhiều session có gọi cùng key đồng thời không?
- **Cache pressure:** result cache có bị loại bỏ liên tục không?

Ví dụ:

| Loại function | Mức phù hợp thường gặp | Lý do |
| --- | --- | --- |
| Tra cứu tên quốc gia theo mã | Cao | Ít thay đổi, nhiều lần gọi lặp lại, kết quả nhỏ. |
| Tra cứu thuế suất theo vùng | Có thể cao | Phụ thuộc bảng cấu hình ít thay đổi. |
| Tính số dư tài khoản hiện tại | Thấp | Dữ liệu thay đổi thường xuyên, freshness quan trọng. |
| Lấy giờ hiện tại | Không phù hợp | Kết quả phụ thuộc thời gian gọi. |
| Sinh số tiếp theo | Không phù hợp | Có side effect/sequence semantics. |
| Tính biểu thức số học rất rẻ | Thường thấp | Cache lookup có thể đắt hơn phép tính. |
| Tính báo cáo lớn theo hàng triệu tham số duy nhất | Thường thấp | Key cardinality và result size lớn, reuse thấp. |

### Đo lường trước và sau

Không chỉ đo elapsed time của một lần gọi. Hãy so sánh:

- Tổng số lần gọi function.
- Số lần function body thực sự chạy.
- Số cache hit/miss hoặc thống kê result cache.
- Logical reads/physical reads và CPU.
- Tỷ lệ invalidation sau DML.
- Memory dùng bởi result cache.
- Latency ở cache warm và cache cold.

Chạy thử với dữ liệu, concurrency và tần suất cập nhật gần production. Một microbenchmark một session, một key và không có DML có thể phóng đại lợi ích.

## 11. PL/SQL function result cache và SQL query result cache

Oracle có hai cơ chế result cache dễ bị nhầm:

| Tiêu chí | PL/SQL function result cache | SQL query result cache |
| --- | --- | --- |
| Đánh dấu | Clause `RESULT_CACHE` trên function | Hint `/*+ RESULT_CACHE */` hoặc cấu hình query result cache |
| Đối tượng được cache | Giá trị RETURN của một function theo tham số | Kết quả của một câu truy vấn SQL |
| Cache key chính | Function identity và các giá trị tham số | Query/result semantics và các yếu tố liên quan |
| Dependency | Dữ liệu được function truy cập và các dependency liên quan | Đối tượng dữ liệu mà query đọc |
| Phạm vi | SGA result cache của instance | SGA result cache của instance |
| Dùng khi | Nhiều caller gọi cùng function với đầu vào lặp lại | Nhiều lần chạy cùng query có kết quả có thể tái sử dụng |

### SQL query result cache

Có thể yêu cầu Oracle cache kết quả query:

~~~sql
SELECT /*+ RESULT_CACHE */
       region_code,
       tax_rate
FROM tax_configuration
WHERE region_code = 'APAC';
~~~

Hoặc điều khiển hành vi query result cache qua tham số RESULT_CACHE_MODE (MANUAL/FORCE), tùy cấu hình hệ thống. Đây là cơ chế cache kết quả câu SQL; nó không tự đánh dấu một PL/SQL function là result-cached.

### Function result cache được khai báo ở function

~~~sql
CREATE OR REPLACE FUNCTION get_tax_rate(p_region_code VARCHAR2)
RETURN NUMBER
RESULT_CACHE
IS
    l_rate NUMBER;
BEGIN
    SELECT tax_rate
    INTO l_rate
    FROM tax_configuration
    WHERE region_code = p_region_code;
    RETURN l_rate;
END;
/
~~~

Caller có thể gọi function từ PL/SQL hoặc SQL. Cache quản lý giá trị RETURN của function theo tham số và dependency.

### Không dùng nhầm RESULT_CACHE_MODE

Đặt RESULT_CACHE_MODE=FORCE không phải cách thay thế clause RESULT_CACHE trên function. Nếu muốn function được quản lý như PL/SQL result-cached, hãy khai báo đúng thuộc tính trên function. Ngược lại, SQL query result cache có thể được điều khiển bằng hint và parameter tương ứng.

### Có thể kết hợp hai cơ chế?

Một query có thể gọi PL/SQL function result-cached, và bản thân query cũng có thể được xem xét cho SQL query result cache. Tuy nhiên, việc chồng nhiều lớp cache làm khó chẩn đoán invalidation, hit ratio và memory. Chọn cơ chế ở đúng tầng, đo lường và chỉ kết hợp khi có lợi ích rõ ràng.

## 12. Giám sát bằng DBMS_RESULT_CACHE

Package DBMS_RESULT_CACHE cung cấp API quản trị và quan sát result cache. Quyền thực thi và một số thao tác quản trị phụ thuộc quyền user và phiên bản Oracle.

### Xem trạng thái cache

~~~sql
SELECT DBMS_RESULT_CACHE.STATUS
FROM dual;
~~~

STATUS trả về trạng thái result cache theo phiên bản và cấu hình. Cách quan sát phổ biến khác là các dynamic performance views ở phần kế tiếp.

### Báo cáo bộ nhớ

~~~sql
BEGIN
    DBMS_RESULT_CACHE.MEMORY_REPORT;
END;
/
~~~

MEMORY_REPORT in thông tin sử dụng bộ nhớ result cache qua output của package. Bật DBMS_OUTPUT nếu muốn xem output trong SQL Developer/SQL*Plus.

### Bypass cache

Có thể yêu cầu bypass result cache ở phạm vi session hoặc hệ thống bằng API phù hợp:

~~~sql
BEGIN
    DBMS_RESULT_CACHE.BYPASS(
        bypass_mode => TRUE,
        session => TRUE
    );
END;
/
~~~

Để bật lại cho session:

~~~sql
BEGIN
    DBMS_RESULT_CACHE.BYPASS(
        bypass_mode => FALSE,
        session => TRUE
    );
END;
/
~~~

BYPASS là công cụ chẩn đoán hoặc quản trị, không phải cách sửa function sai dependency. Khi bypass, function vẫn chạy và có thể chậm hơn; hãy ghi nhận trạng thái trước/sau thử nghiệm.

### Flush cache

~~~sql
BEGIN
    DBMS_RESULT_CACHE.FLUSH;
END;
/
~~~

FLUSH giải phóng các entry result cache theo phạm vi API và quyền của user. Đây là thao tác ảnh hưởng toàn bộ workload dùng cache trên instance; không chạy tùy tiện trong production chỉ để “làm mới” một function. Khi cần invalidation một object cụ thể, xem API INVALIDATE và xác định dependency trước.

### Invalidate object

DBMS_RESULT_CACHE có API INVALIDATE để invalidated cache entries liên quan đến một object theo owner/name. Cú pháp và quyền có thể khác theo phiên bản; tra package specification của database đích trước khi chạy trong môi trường vận hành.

## 13. Giám sát qua V$ views

Dynamic performance views cho biết cache có entry gì, dependency ra sao và thống kê hoạt động. Thường cần quyền SELECT_CATALOG_ROLE hoặc quyền truy cập view phù hợp.

### V$RESULT_CACHE_OBJECTS

~~~sql
SELECT cache_id,
       type,
       status,
       name,
       creation_timestamp,
       block_count,
       scan_count,
       pin_count
FROM v$result_cache_objects
ORDER BY creation_timestamp DESC;
~~~

View này có thể hiển thị result objects và dependency objects. TYPE/STATUS giúp phân biệt kết quả đã publish, dependency hoặc entry đang ở trạng thái khác. Các cột chi tiết có thể khác theo phiên bản; kiểm tra DESC V$RESULT_CACHE_OBJECTS trên database thực tế.

### Tìm object liên quan đến function

~~~sql
SELECT cache_id,
       type,
       status,
       name,
       creation_timestamp
FROM v$result_cache_objects
WHERE UPPER(name) LIKE '%GET_TAX_RATE%'
ORDER BY creation_timestamp DESC;
~~~

Tên hiển thị có thể bao gồm schema, package hoặc thông tin định danh khác. Không dựa duy nhất vào LIKE để kết luận không có cache entry; kiểm tra toàn bộ objects và dependencies nếu cần.

### V$RESULT_CACHE_STATISTICS

~~~sql
SELECT name, value
FROM v$result_cache_statistics
ORDER BY name;
~~~

View thống kê cung cấp các chỉ số liên quan tới bộ nhớ, số lần tạo/invalidated entry và hoạt động cache tùy phiên bản. Đọc tên metric cùng ý nghĩa từ tài liệu đúng release; không gán một giá trị chung cho mọi hệ thống.

### V$RESULT_CACHE_MEMORY

~~~sql
SELECT *
FROM v$result_cache_memory;
~~~

View này cho biết các vùng/khối bộ nhớ được result cache sử dụng. Dùng DESC để xem cột sẵn có trên phiên bản đang chạy.

### V$RESULT_CACHE_DEPENDENCY

~~~sql
SELECT *
FROM v$result_cache_dependency;
~~~

View dependency giúp lần theo result object và đối tượng dữ liệu mà nó phụ thuộc. Cấu trúc cột có thể thay đổi theo phiên bản; xem DESC trước khi viết báo cáo quản trị cố định.

### So sánh trước và sau DML

Một phép đo hữu ích là:

1. Gọi function hai lần với cùng tham số.
2. Quan sát result/dependency objects và statistics.
3. UPDATE bảng phụ thuộc rồi COMMIT.
4. Gọi lại function.
5. Quan sát entry cũ invalidated và entry mới được tạo khi function chạy lại.

Không chỉ nhìn một cột hit/miss. Kết hợp thời gian thực thi, số lần body chạy, số lần invalidation, memory và lượng DML trên bảng phụ thuộc.

## 14. Quy tắc thiết kế và điều kiện không phù hợp

Trước khi thêm RESULT_CACHE, hãy xác nhận các điều kiện sau:

| Câu hỏi | Nếu câu trả lời là “không” |
| --- | --- |
| Cùng tham số và cùng dữ liệu dependency có luôn cho cùng kết quả? | Không dùng result cache cho function đó. |
| Mọi đầu vào ảnh hưởng kết quả đã nằm trong tham số hoặc dependency được theo dõi? | Bổ sung tham số hoặc loại bỏ trạng thái ẩn. |
| Function không có side effect? | Dùng procedure hoặc thiết kế API khác. |
| Function không dựa vào session state/NLS/user context ẩn? | Truyền context rõ ràng hoặc không cache. |
| Dữ liệu nguồn thay đổi đủ ít để entry có cơ hội được tái sử dụng? | Result cache có thể không hiệu quả. |
| Cùng key được gọi đủ thường xuyên? | Chi phí cache lookup/memory có thể không đáng. |
| Kích thước và số lượng kết quả có kiểm soát? | Giảm cardinality/result size hoặc chọn cache khác. |
| Function vẫn đúng khi cache miss hoặc cache bị flush? | Sửa function; cache không được là điều kiện đúng/sai của nghiệp vụ. |

### Quy tắc purity

Result-cached function phải được thiết kế như phép tính không có side effect. Tránh:

- DML hoặc transaction control.
- Thay đổi package variables hoặc global state.
- Ghi file, gửi message hoặc gọi API ngoài.
- Đọc sequence hoặc giá trị thay đổi theo thời gian.
- Dựa vào current user, application context, locale hoặc timezone ngầm.
- Dựa vào thứ tự gọi trước đó hoặc state từ một request khác.

Oracle có thể áp dụng các hạn chế biên dịch/runtime cho một số trường hợp, nhưng người thiết kế vẫn chịu trách nhiệm bảo đảm function có semantics an toàn. Đừng dựa vào việc compiler không báo lỗi để kết luận function phù hợp.

### Kiểu dữ liệu và chữ ký function

Function result cache có các giới hạn về kiểu dữ liệu tham số/kết quả và dạng function tùy phiên bản. Thực tế an toàn là ưu tiên scalar SQL types và kiểu PL/SQL được tài liệu phiên bản hỗ trợ; tránh dùng LOB, LONG, REF CURSOR hoặc kiểu phức tạp nếu chưa xác nhận hỗ trợ. Function không nên dùng OUT/IN OUT parameters. Nếu cần trả nhiều giá trị, có thể cân nhắc record/collection được hỗ trợ hoặc một API khác, rồi kiểm tra khả năng cache với release thực tế.

### Function có exception

Nếu function không trả kết quả bình thường mà phát sinh exception, caller nhận exception theo semantics PL/SQL. Không thiết kế logic dựa trên giả định exception được cache như một kết quả. Hãy xử lý NO_DATA_FOUND, TOO_MANY_ROWS và lỗi dữ liệu theo quy tắc nghiệp vụ; cache chỉ tối ưu kết quả hợp lệ có thể tái sử dụng.

### Dynamic SQL và nguồn dữ liệu gián tiếp

Khi function dùng EXECUTE IMMEDIATE, synonym thay đổi, database link hoặc nguồn dữ liệu ngoài, hãy kiểm tra dependency tracking của phiên bản Oracle và đường thực thi cụ thể. Không giả định dependency của dynamic SQL luôn hiển thị giống câu SELECT tĩnh. Nếu không thể bảo đảm Oracle invalidates entry khi nguồn dữ liệu thay đổi, không dùng result cache hoặc thiết kế lại để dependency rõ ràng.

### Function có phân quyền theo DEFINER/INVOKER

Một function có thể được biên dịch với AUTHID DEFINER hoặc AUTHID CURRENT_USER. Nếu kết quả phụ thuộc vào quyền, current schema hoặc danh tính caller, phải đánh giá kỹ khả năng chia sẻ cache giữa các session. Không cache dữ liệu nhạy cảm theo một key không bao gồm đúng ngữ cảnh bảo mật; ưu tiên truyền đầu vào tường minh và kiểm tra authorization độc lập.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Function không có cache hit | Tham số liên tục khác nhau, cache bypass, entry bị invalidated hoặc bị aged out | Kiểm tra key reuse, bypass status, dependency DML và thống kê. |
| Kết quả cũ sau khi bảng thay đổi | Dependency không được theo dõi như dự kiến hoặc dữ liệu nguồn ngoài bảng | Kiểm tra dependency view, dynamic SQL và trạng thái commit; không dựa vào hidden state. |
| Function trả kết quả khác giữa user/session | Function đọc session context, NLS hoặc package variable | Đưa context thành tham số hoặc bỏ RESULT_CACHE. |
| Cache bị invalidated thường xuyên | Bảng dependency có DML liên tục | Chọn dữ liệu tham chiếu ít thay đổi hoặc không dùng cache. |
| Bộ nhớ cache tăng và entry ít dùng | Nhiều key khác nhau hoặc result size lớn | Giảm cardinality, cache kết quả nhỏ, đo reuse và cấu hình SGA. |
| Function chạy lại sau FLUSH | Cache đã bị giải phóng | Đây là hành vi bình thường; function phải đúng khi cache miss. |
| Function chậm ở lần gọi đầu | Cache miss phải thực thi SQL và tạo entry | Đo cả cold/warm path; tối ưu query nguồn. |
| Function result cache không hoạt động với kiểu dữ liệu | Kiểu không được hỗ trợ hoặc chữ ký không hợp lệ | Kiểm tra lỗi biên dịch và tài liệu phiên bản; chọn kiểu được hỗ trợ. |
| Kết quả sai khi dùng package state | Package variable không phải tham số/dependency dữ liệu được theo dõi như bảng | Loại bỏ state ẩn hoặc truyền giá trị vào tham số. |
| Cache hit trên instance này nhưng miss trên instance khác | RAC có cache riêng theo instance | Đo từng instance và tính đến cache warm-up/invalidation. |
| DML session không thấy dữ liệu mới qua function | Function result cache bị dùng sai trong transaction hoặc dependency chưa được phản ánh | Kiểm tra session DML, commit/rollback và cache bypass/invalidation. |
| ORA-04068 hoặc package invalidation bị nhầm với cache miss | Package state và result cache là hai cơ chế khác nhau | Chẩn đoán package validity riêng với result cache objects. |

### Quy trình chẩn đoán đề xuất

1. Xác nhận function thực sự được khai báo RESULT_CACHE và compile VALID.
2. Gọi cùng function với cùng tham số trong cùng session.
3. Kiểm tra cache status, objects và statistics.
4. Kiểm tra các bảng dependency có bị DML/COMMIT thường xuyên không.
5. Kiểm tra function có đọc package state, SYS_CONTEXT, NLS, thời gian hoặc nguồn ngoài không.
6. Thử bypass trong session thử nghiệm để so sánh kết quả và latency.
7. So sánh cache cold/warm và nhiều session/instance.
8. Chỉ giữ RESULT_CACHE nếu kết quả đúng và workload thực sự cải thiện.

## 16. Bài thực hành tổng hợp

Thực hiện trong schema học tập có quyền CREATE TABLE và CREATE FUNCTION. Các lệnh DDL có implicit commit trong Oracle; không chạy trên bảng cấu hình nghiệp vụ thật.

### Bước 1: tạo bảng cấu hình thuế

~~~sql
CREATE TABLE lab_tax_configuration (
    region_code VARCHAR2(20)
        CONSTRAINT pk_lab_tax_configuration PRIMARY KEY,
    tax_rate NUMBER(8,5) NOT NULL
);

INSERT INTO lab_tax_configuration VALUES ('APAC', 0.08000);
INSERT INTO lab_tax_configuration VALUES ('EMEA', 0.20000);
COMMIT;
~~~

### Bước 2: tạo function result-cached

~~~sql
CREATE OR REPLACE FUNCTION lab_tax_rate (
    p_region_code IN VARCHAR2
)
RETURN NUMBER
RESULT_CACHE
IS
    l_rate lab_tax_configuration.tax_rate%TYPE;
BEGIN
    SELECT tax_rate
    INTO l_rate
    FROM lab_tax_configuration
    WHERE region_code = p_region_code;

    RETURN l_rate;
END lab_tax_rate;
/
~~~

Kiểm tra compile:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'LAB_TAX_RATE';

SELECT name, type, line, position, text
FROM user_errors
WHERE name = 'LAB_TAX_RATE'
ORDER BY sequence;
~~~

### Bước 3: gọi nhiều lần cùng tham số

~~~sql
SET SERVEROUTPUT ON;

BEGIN
    DBMS_OUTPUT.PUT_LINE(lab_tax_rate('APAC'));
    DBMS_OUTPUT.PUT_LINE(lab_tax_rate('APAC'));
    DBMS_OUTPUT.PUT_LINE(lab_tax_rate('EMEA'));
    DBMS_OUTPUT.PUT_LINE(lab_tax_rate('APAC'));
END;
/
~~~

Các lần gọi APAC dùng cùng tham số và cùng dữ liệu dependency, nên có cơ hội cache hit sau lần tính đầu. EMEA là một key khác. Kết quả trả về phải giống nhau dù cache hit hay miss.

### Bước 4: quan sát cache objects và statistics

~~~sql
SELECT cache_id, type, status, name, creation_timestamp
FROM v$result_cache_objects
ORDER BY creation_timestamp DESC;

SELECT name, value
FROM v$result_cache_statistics
ORDER BY name;
~~~

Nếu không có quyền đọc V$ views, nhờ DBA cấp quyền phù hợp hoặc dùng công cụ quản trị được phép. Tên/chi tiết entry phụ thuộc phiên bản và cách hiển thị object; không yêu cầu một tên cache cố định.

### Bước 5: thay đổi dependency rồi COMMIT

~~~sql
UPDATE lab_tax_configuration
SET tax_rate = 0.09000
WHERE region_code = 'APAC';

COMMIT;

SELECT lab_tax_rate('APAC')
FROM dual;
~~~

Sau COMMIT, kết quả cache phụ thuộc dữ liệu APAC cũ bị invalidated. Lần gọi sau tính lại và trả 0.09. Quan sát lại V$RESULT_CACHE_OBJECTS và thống kê.

### Bước 6: thử ROLLBACK

~~~sql
UPDATE lab_tax_configuration
SET tax_rate = 0.10000
WHERE region_code = 'APAC';

SELECT lab_tax_rate('APAC')
FROM dual;

ROLLBACK;

SELECT lab_tax_rate('APAC')
FROM dual;
~~~

Session đang thay đổi dependency có thể bypass cache trong transaction để nhìn thấy dữ liệu của chính nó. Sau ROLLBACK, dữ liệu đã commit vẫn là 0.09. Quan sát kết quả thay vì giả định cache luôn được sử dụng trong transaction có DML.

### Bước 7: thử hai session

**Session A:**

~~~sql
SELECT lab_tax_rate('APAC') FROM dual;
~~~

**Session B:**

~~~sql
SELECT lab_tax_rate('APAC') FROM dual;
~~~

Hai session trên cùng instance có thể dùng chung result cache entry hợp lệ. Tiếp theo, Session A UPDATE tax rate và COMMIT; Session B gọi lại function để quan sát invalidation và tính lại theo dữ liệu mới.

### Bước 8: so sánh với function phụ thuộc session

Không triển khai function phụ thuộc SESSION_USER như một result-cached function không tham số. Hãy thiết kế function có tham số username/tenant rõ ràng, sau đó kiểm tra authorization độc lập. Thảo luận vì sao cache key phải phân biệt những đầu vào làm thay đổi kết quả.

### Bước 9: bypass trong session thử nghiệm

~~~sql
BEGIN
    DBMS_RESULT_CACHE.BYPASS(
        bypass_mode => TRUE,
        session => TRUE
    );
END;
/

SELECT lab_tax_rate('APAC') FROM dual;

BEGIN
    DBMS_RESULT_CACHE.BYPASS(
        bypass_mode => FALSE,
        session => TRUE
    );
END;
/
~~~

Thử nghiệm bypass chỉ tác động session hiện tại theo tham số session. Ghi nhận thời gian và kết quả trước/sau; không dùng bypass để che lỗi dependency.

### Bước 10: dọn dữ liệu

~~~sql
DROP FUNCTION lab_tax_rate;
DROP TABLE lab_tax_configuration PURGE;
~~~

Chỉ chạy khi đã hoàn thành lab và không cần giữ object. DROP là DDL và có implicit commit.

## 17. Câu hỏi tự kiểm tra

1. **RESULT_CACHE trên PL/SQL function làm gì?** Cho phép Oracle lưu và tái sử dụng giá trị RETURN theo tham số và dependency dữ liệu.
2. **Cache nằm ở đâu?** Trong SGA result cache của database instance.
3. **Nhiều session cùng instance có dùng chung cache không?** Có thể, nếu entry còn hợp lệ và function đủ điều kiện.
4. **Cùng tham số có luôn đủ để trả cùng kết quả không?** Chỉ khi mọi dữ liệu/context ảnh hưởng kết quả cũng giống nhau và dependency được quản lý đúng.
5. **Vì sao function không nên đọc package variable ẩn?** Package state không phải đầu vào cache key được theo dõi như tham số; session khác có thể có giá trị khác.
6. **Function result-cached có nên có side effect không?** Không; cache hit có thể bỏ qua việc thực thi body.
7. **Function có OUT/IN OUT parameters phù hợp không?** Không; dùng tham số IN và RETURN value.
8. **Oracle theo dõi thay đổi bảng dependency khi nào?** DML đã commit trên object phụ thuộc có thể invalidated cache entries liên quan.
9. **ROLLBACK có làm dữ liệu mới trở thành dependency state không?** Không; thay đổi rollback không trở thành dữ liệu đã commit.
10. **RELIES_ON nên dùng thế nào trong code mới?** Không dùng làm mặc định; đây là clause legacy/deprecated trong các phiên bản mới, dependency được tự theo dõi cho SQL phù hợp.
11. **Có nên cache function đọc SYSDATE hoặc sequence?** Không, vì kết quả phụ thuộc trạng thái thay đổi ngoài tham số.
12. **Khi function đọc SESSION_USER hoặc tenant context cần chú ý gì?** Đưa context thành tham số rõ ràng hoặc bỏ result cache; authorization vẫn phải kiểm tra riêng.
13. **RAC có một cache chung cho mọi instance không?** Không; mỗi instance có cache riêng và Oracle phối hợp invalidation.
14. **PL/SQL function result cache khác SQL query result cache thế nào?** Một cơ chế cache giá trị RETURN của function; cơ chế kia cache kết quả câu SQL.
15. **RESULT_CACHE_MODE có thay thế clause RESULT_CACHE của function không?** Không; parameter này điều khiển SQL query result cache, còn function phải khai báo thuộc tính của chính nó.
16. **Cache hit có được bảo đảm không?** Không; entry có thể miss, bị bypass, invalidated hoặc aged out.
17. **Vì sao bảng dependency cập nhật thường xuyên làm cache kém hiệu quả?** Các entry liên quan liên tục bị invalidated trước khi được tái sử dụng.
18. **Dùng view nào để xem cache objects?** V$RESULT_CACHE_OBJECTS.
19. **Dùng view nào để xem thống kê cache?** V$RESULT_CACHE_STATISTICS.
20. **Vì sao cần đo cold và warm path?** Lần đầu phải tính kết quả; các lần sau có thể hit. Cả hai đều thuộc workload thực tế.

PL/SQL RESULT_CACHE phù hợp với function không có side effect, có đầu vào rõ ràng, phụ thuộc vào dữ liệu ổn định và được gọi lặp lại. Oracle tự theo dõi các dependency dữ liệu phù hợp và invalidates kết quả sau thay đổi đã commit. Function không nên phụ thuộc vào package state, thời gian, sequence, NLS, user hoặc application context ẩn. Hãy phân biệt function result cache với SQL query result cache, đo hit/miss và invalidation trên workload thật, đồng thời bảo đảm function luôn đúng khi cache miss hoặc bị flush.

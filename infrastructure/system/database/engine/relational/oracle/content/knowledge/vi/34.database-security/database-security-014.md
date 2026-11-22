# Data Redaction, che dữ liệu thử nghiệm và kiểm tra điều kiện sử dụng

Trong Oracle Database, dữ liệu nhạy cảm như số điện thoại, email, địa chỉ, số định danh cá nhân, thông tin lương và dữ liệu thanh toán cần được bảo vệ trong suốt vòng đời sử dụng. Không phải người dùng nào có quyền truy vấn một bảng cũng cần nhìn thấy giá trị thật của mọi cột. Nhân viên hỗ trợ có thể cần xác nhận một phần số điện thoại; nhóm báo cáo có thể cần phân tích doanh thu nhưng không cần biết danh tính khách hàng; nhóm phát triển cần dữ liệu đủ giống thực tế để kiểm thử nhưng không nên nhận bản sao chứa thông tin cá nhân thật.

Oracle có các cách tiếp cận khác nhau cho những mục tiêu này. **Data Redaction** che giá trị ở thời điểm truy vấn trả kết quả, trong khi **data masking tĩnh** thay đổi dữ liệu trong bản sao hoặc môi trường thử nghiệm. Hai kỹ thuật giải quyết các rủi ro khác nhau và không thể thay thế hoàn toàn cho nhau.

## 1. Phân biệt Data Redaction và data masking

### 1.1. Data Redaction là che dữ liệu động

Oracle Data Redaction đánh giá một chính sách khi người dùng truy vấn cột được bảo vệ. Nếu điều kiện của chính sách đúng, Oracle biến đổi giá trị trong kết quả trả về theo kiểu che đã cấu hình. Giá trị lưu trong bảng vẫn giữ nguyên.

Ví dụ, bảng `CUSTOMERS` lưu số điện thoại đầy đủ. Nhân viên hỗ trợ chỉ cần nhìn thấy một phần số điện thoại để xác nhận khách hàng. Một truy vấn có thể trả về chuỗi đã che cho nhân viên đó, trong khi người dùng được phép xem dữ liệu đầy đủ vẫn nhận giá trị gốc.

Đặc điểm chính:

- Che dữ liệu tại thời điểm truy vấn; không cập nhật hoặc thay thế giá trị lưu trong bảng.
- Có thể áp dụng khác nhau theo điều kiện chính sách và ngữ cảnh phiên đăng nhập.
- Phù hợp để giới hạn những gì người dùng nhìn thấy trong kết quả SQL mà không phải tạo một bản sao dữ liệu riêng.
- Cần kiểm soát chặt quyền quản trị chính sách và các quyền có thể bỏ qua redaction.

Data Redaction thường được gọi là **dynamic data masking**. Nó giúp giảm khả năng lộ dữ liệu qua kết quả truy vấn của các tài khoản thông thường, nhưng không xóa dữ liệu nhạy cảm khỏi database.

### 1.2. Data masking tĩnh là biến đổi dữ liệu trong bản sao

Data masking tĩnh tạo một tập dữ liệu đã được thay thế hoặc biến đổi trước khi cấp cho người dùng thử nghiệm. Ví dụ, một bản sao production được tạo trong môi trường kiểm thử, sau đó email, số điện thoại, địa chỉ và thông tin định danh được thay bằng dữ liệu giả trước khi nhóm phát triển được truy cập.

Đặc điểm chính:

- Giá trị trong bản sao đã được thay đổi; người dùng thử nghiệm không cần dựa vào một policy che kết quả mỗi lần truy vấn.
- Có thể dùng để chuẩn bị dữ liệu cho development, QA, staging, đào tạo hoặc chia sẻ với nhà cung cấp.
- Cần bảo toàn quan hệ giữa các bảng, kiểu dữ liệu, ràng buộc, định dạng và những đặc điểm cần thiết cho kiểm thử.
- Phải xử lý tất cả bản sao, file xuất, log, bản sao lưu và dữ liệu dẫn xuất có chứa thông tin nhạy cảm.

Oracle Data Safe có khả năng hỗ trợ phát hiện dữ liệu nhạy cảm, masking và subsetting trong các môi trường được hỗ trợ. Tổ chức cũng có thể dùng quy trình ETL hoặc công cụ masking đã được phê duyệt. Việc lựa chọn công cụ phụ thuộc kiến trúc, phiên bản, dịch vụ và quyền sử dụng tại nơi triển khai.

### 1.3. So sánh hai cách tiếp cận

| Tiêu chí | Data Redaction động | Data masking tĩnh |
|---|---|---|
| Thời điểm biến đổi | Khi truy vấn trả kết quả. | Trước khi cấp dữ liệu cho môi trường hoặc người dùng. |
| Dữ liệu gốc | Vẫn giữ nguyên trong database. | Bản sao đích chứa giá trị đã biến đổi. |
| Mục tiêu phù hợp | Giới hạn hiển thị dữ liệu trong môi trường đang vận hành. | Cung cấp dữ liệu an toàn hơn cho dev, QA, staging hoặc bên thứ ba. |
| Phụ thuộc policy lúc truy vấn | Có. | Không cần policy redaction để che các giá trị đã được thay đổi. |
| Quan hệ và tính nhất quán | Dữ liệu gốc vẫn giữ quan hệ ban đầu; chỉ kết quả hiển thị bị che. | Phải thiết kế phép biến đổi nhất quán giữa các bảng và khóa liên quan. |
| Rủi ro chính | Quyền bypass, đường truy cập đặc quyền, suy luận từ kết quả và cấu hình policy sai. | Bỏ sót cột hoặc bản sao, dữ liệu giả không nhất quán, bản sao chưa mask bị lộ. |

Nếu mục tiêu là cho phép nhân viên hỗ trợ xem dữ liệu đã che trong production, Data Redaction có thể phù hợp. Nếu mục tiêu là giao một bản sao database cho nhóm phát triển, hãy dùng data masking tĩnh trước khi bàn giao. Chỉ bật Data Redaction trên bản sao production không chứng minh rằng dữ liệu lưu trong bản sao đã an toàn.

## 2. Các kiểu Data Redaction trong Oracle

Oracle cung cấp nhiều kiểu biến đổi. Chọn kiểu dựa trên mục đích hiển thị, kiểu dữ liệu và định dạng mà ứng dụng cần.

| Kiểu | Tác dụng | Trường hợp sử dụng |
|---|---|---|
| `FULL` | Thay toàn bộ giá trị bằng giá trị che mặc định phù hợp với kiểu dữ liệu. | Ẩn hoàn toàn số định danh hoặc mức lương. |
| `PARTIAL` | Chỉ che một phần giá trị theo tham số định dạng. | Chỉ hiển thị vài chữ số cuối của số thẻ hoặc số điện thoại. |
| `REGEXP` | Dùng biểu thức chính quy để thay thế một phần hoặc toàn bộ chuỗi. | Giữ ký tự đầu và domain của email nhưng che phần tên. |
| `RANDOM` | Trả về giá trị ngẫu nhiên phù hợp với kiểu dữ liệu theo chức năng redaction. | Giảm khả năng nhận biết giá trị thật khi không cần giữ một mẫu hiển thị cố định. |

Các kiểu che không tự động bảo đảm dữ liệu đầu ra đáp ứng mọi quy tắc nghiệp vụ. Ví dụ, giá trị số được thay bằng 0 có thể gây hiểu nhầm trong báo cáo; chuỗi bị che có thể không còn hợp lệ theo định dạng ứng dụng. Luôn kiểm tra kiểu dữ liệu, ứng dụng tiêu thụ kết quả và phiên bản Oracle đang chạy.

## 3. Quản lý Data Redaction bằng DBMS_REDACT

Oracle cung cấp package `DBMS_REDACT` để tạo và quản lý redaction policy. Người quản trị cần có quyền phù hợp, trong đó quyền `ADMINISTER REDACTION POLICY` được dùng để quản lý chính sách. Không cấp quyền quản trị này cho tài khoản ứng dụng thông thường.

### 3.1. Ví dụ che toàn bộ số điện thoại

Giả sử bảng `APP.CUSTOMERS` có cột `PHONE_NUMBER`. Tất cả user trừ tài khoản được phép xem đầy đủ `APP_PRIVILEGED` sẽ nhận giá trị đã che:

```sql
BEGIN
    DBMS_REDACT.ADD_POLICY(
        object_schema => 'APP',
        object_name   => 'CUSTOMERS',
        column_name   => 'PHONE_NUMBER',
        policy_name   => 'REDACT_CUSTOMER_PHONE',
        function_type => DBMS_REDACT.FULL,
        expression    => 'SYS_CONTEXT(''USERENV'', ''SESSION_USER'') <> ''APP_PRIVILEGED'''
    );
END;
/
```

Trong ví dụ, điều kiện được đánh giá theo user đăng nhập vào database. Khi `SESSION_USER` khác `APP_PRIVILEGED`, policy áp dụng redaction cho cột được chỉ định. Khi user là `APP_PRIVILEGED`, biểu thức sai nên không áp dụng việc che theo policy này.

Nếu cần che cho tất cả phiên, có thể dùng biểu thức luôn đúng:

```sql
expression => '1=1'
```

Chính sách thực tế nên dựa trên vai trò và ngữ cảnh đã được kiểm soát. Việc loại trừ một username cụ thể chỉ phù hợp với ví dụ đơn giản; trong hệ thống lớn, cần xác định rõ danh tính nào được xem dữ liệu gốc, ai phê duyệt và cách kiểm toán quyền đó.

### 3.2. Che một phần email bằng REGEXP

Ví dụ sau giữ ký tự đầu tiên và phần domain của email, đồng thời thay phần còn lại bằng dấu sao:

```sql
BEGIN
    DBMS_REDACT.ADD_POLICY(
        object_schema          => 'APP',
        object_name            => 'CUSTOMERS',
        column_name            => 'EMAIL',
        policy_name            => 'REDACT_CUSTOMER_EMAIL',
        function_type          => DBMS_REDACT.REGEXP,
        expression             => 'SYS_CONTEXT(''USERENV'', ''SESSION_USER'') <> ''APP_PRIVILEGED''',
        regexp_pattern         => '(^.).*(@.*$)',
        regexp_replace_string  => '\1*****\2',
        regexp_position        => 1,
        regexp_occurrence      => 0,
        regexp_match_parameter => 'i'
    );
END;
/
```

Với giá trị như `alice@example.com`, kết quả minh họa có dạng `a*****@example.com`. `regexp_pattern` xác định các nhóm cần giữ; `regexp_replace_string` tham chiếu nhóm thứ nhất và thứ hai; `regexp_occurrence => 0` áp dụng cho tất cả lần khớp. Hãy thử với email ngắn, dài, chữ hoa, ký tự đặc biệt, giá trị `NULL` và dữ liệu không đúng định dạng để bảo đảm kết quả phù hợp.

Không nên coi ví dụ regex này là quy tắc xác thực email. Nó chỉ là ví dụ che chuỗi. Nếu ứng dụng có nhiều định dạng email hoặc yêu cầu che khác nhau, hãy thiết kế và kiểm thử mẫu biểu thức theo dữ liệu thực tế mà không đưa thông tin cá nhân thật vào mã nguồn hoặc tài liệu.

### 3.3. Partial redaction

`DBMS_REDACT.PARTIAL` dùng tham số định dạng để giữ một số phần của giá trị và che phần còn lại. Đây là lựa chọn thường gặp khi người dùng cần nhận biết một phần số thẻ hoặc số điện thoại mà không cần thấy toàn bộ giá trị.

Ví dụ về yêu cầu nghiệp vụ:

- Chỉ hiển thị bốn chữ số cuối của số thẻ thanh toán.
- Hiển thị mã vùng nhưng che phần còn lại của số điện thoại.
- Giữ một phần mã khách hàng để nhân viên có thể đối chiếu.

Cấu hình `function_parameters` phải phù hợp độ dài, vị trí và kiểu dữ liệu của cột. Định dạng cụ thể cần được đối chiếu với tài liệu Oracle đúng phiên bản và thử trên các trường hợp biên. Không nên tự suy ra chuỗi tham số partial từ ví dụ của một kiểu dữ liệu khác.

### 3.4. Kiểm tra policy và column đã cấu hình

DBA có thể kiểm tra các policy và cột được bảo vệ qua data dictionary:

```sql
SELECT
    object_owner,
    object_name,
    policy_name,
    expression,
    enable
FROM dba_redaction_policies
WHERE object_owner = 'APP'
ORDER BY object_name, policy_name;

SELECT
    object_owner,
    object_name,
    policy_name,
    column_name,
    function_type,
    function_parameters
FROM dba_redaction_columns
WHERE object_owner = 'APP'
ORDER BY object_name, column_name;
```

Các view `DBA_REDACTION_POLICIES` và `DBA_REDACTION_COLUMNS` cung cấp thông tin cấu hình policy và cột. Khả năng đọc các view `DBA_` phụ thuộc quyền của tài khoản. Có thể dùng view phạm vi user hoặc schema tương ứng khi không có quyền DBA.

### 3.5. Tạm tắt, bật lại hoặc xóa policy

Trong quá trình bảo trì, có thể cần tắt hoặc bật một policy. Ví dụ:

```sql
BEGIN
    DBMS_REDACT.DISABLE_POLICY(
        object_schema => 'APP',
        object_name   => 'CUSTOMERS',
        policy_name   => 'REDACT_CUSTOMER_PHONE'
    );
END;
/
```

Bật lại:

```sql
BEGIN
    DBMS_REDACT.ENABLE_POLICY(
        object_schema => 'APP',
        object_name   => 'CUSTOMERS',
        policy_name   => 'REDACT_CUSTOMER_PHONE'
    );
END;
/
```

Xóa policy khi không còn sử dụng:

```sql
BEGIN
    DBMS_REDACT.DROP_POLICY(
        object_schema => 'APP',
        object_name   => 'CUSTOMERS',
        policy_name   => 'REDACT_CUSTOMER_PHONE'
    );
END;
/
```

Tắt hoặc xóa policy có thể làm lộ dữ liệu thật cho các tài khoản vốn dựa vào redaction. Chỉ thực hiện trong cửa sổ thay đổi được phê duyệt, giới hạn người thực hiện và xác nhận policy được bật lại nếu việc tắt chỉ nhằm bảo trì tạm thời.

## 4. Thiết kế điều kiện sử dụng policy

Điều kiện policy quyết định khi nào redaction được áp dụng. Một policy có thể luôn áp dụng hoặc chỉ áp dụng cho một số phiên, user, ứng dụng hay ngữ cảnh nhất định.

### 4.1. Dùng SESSION_USER cho quy tắc theo database user

Ví dụ:

```sql
expression => 'SYS_CONTEXT(''USERENV'', ''SESSION_USER'') <> ''APP_PRIVILEGED'''
```

`SYS_CONTEXT('USERENV','SESSION_USER')` trả về user database đã xác thực cho session. Đây là lựa chọn dễ hiểu khi mỗi nhóm người dùng có tài khoản database riêng. Cần nhớ rằng nhiều người có thể dùng chung một tài khoản connection pool; khi đó `SESSION_USER` chỉ nhận diện tài khoản kết nối, không nhận diện người dùng cuối của ứng dụng.

### 4.2. Dùng application context khi ứng dụng chia sẻ database user

Trong hệ thống nhiều người dùng kết nối qua cùng một tài khoản runtime, có thể cần phân biệt người dùng cuối hoặc vai trò nghiệp vụ. Oracle application context cho phép ứng dụng lưu thông tin ngữ cảnh trong session; policy có thể tham chiếu bằng `SYS_CONTEXT`.

Ví dụ về biểu thức đọc một thuộc tính ngữ cảnh:

```sql
SYS_CONTEXT('APP_SECURITY_CTX', 'ACCESS_LEVEL') <> 'FULL'
```

Đây chỉ là biểu thức minh họa. `APP_SECURITY_CTX` phải được tạo và bảo vệ bằng cơ chế secure application context; chỉ package được tin cậy mới có thể thiết lập thuộc tính. Không nên để client tự do đặt một giá trị như `ACCESS_LEVEL = 'FULL'`, vì người gọi có thể tự khai báo mình là người có quyền xem dữ liệu.

Với connection pool, phải thiết lập context khi mượn connection cho request và xóa hoặc đặt lại context khi trả connection về pool. Nếu không, thông tin của request trước có thể còn trong session và ảnh hưởng request tiếp theo. Cần kiểm thử cả luồng thành công, lỗi và timeout.

### 4.3. Dùng CLIENT_IDENTIFIER có kiểm soát

`CLIENT_IDENTIFIER` có thể giúp ghi nhận danh tính người dùng cuối hoặc mã request:

```sql
BEGIN
    DBMS_SESSION.SET_IDENTIFIER('support_agent_102');
END;
/
```

Policy có thể đọc giá trị bằng:

```sql
SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER')
```

`CLIENT_IDENTIFIER` hữu ích cho audit và phân loại phiên, nhưng không tự trở thành bằng chứng xác thực. Nếu người gọi có thể tự đặt identifier tùy ý, họ có thể giả mạo giá trị được policy tin cậy. Chỉ dùng nó cho quyết định bảo mật khi đường thiết lập giá trị được kiểm soát và gắn với danh tính đã xác thực.

### 4.4. Nguyên tắc viết điều kiện

- Viết điều kiện rõ ràng, có thể kiểm thử và gắn với danh tính hoặc ngữ cảnh được tin cậy.
- Dùng biểu thức luôn đúng như `1=1` khi mục tiêu là che cho mọi user thông thường.
- Tránh điều kiện dựa trên giá trị do client tự gửi mà không xác thực.
- Xác định rõ hành vi khi context bị thiếu, sai hoặc chưa được khởi tạo; chính sách nên mặc định an toàn.
- Kiểm tra user đặc quyền, tài khoản quản trị và quyền bypass để tránh vô tình tạo đường xem dữ liệu gốc.
- Lưu lại người phê duyệt, mục đích, phạm vi cột, ngày hiệu lực và ngày rà soát policy.

## 5. Quyền bypass và giới hạn bảo vệ

Data Redaction không thay thế mô hình phân quyền. Một số danh tính đặc quyền, trong đó có `SYS`/kết nối `SYSDBA`, có thể truy cập dữ liệu mà không bị redaction. Người dùng được cấp system privilege `EXEMPT REDACTION POLICY` cũng có thể bỏ qua chính sách.

Vì vậy:

- Không cấp `EXEMPT REDACTION POLICY` cho tài khoản ứng dụng hoặc người dùng thông thường.
- Hạn chế và giám sát quyền quản trị database, quyền `SYSDBA`, quyền quản lý redaction policy và quyền đọc từ điển dữ liệu.
- Không để tài khoản runtime sở hữu bảng nhạy cảm nếu không cần thiết; tách schema owner khỏi runtime user.
- Không coi việc hiển thị giá trị đã che là bằng chứng rằng người dùng không thể suy luận thông tin gốc.
- Dùng quyền đối tượng, role, VPD hoặc cơ chế kiểm soát phù hợp để giới hạn bảng và dòng được truy cập.

Redaction thay đổi giá trị trả về cho cột được bảo vệ; dữ liệu lưu trong bảng và các phép xử lý truy vấn vẫn dựa trên dữ liệu gốc. Người dùng có thể suy luận thông tin từ việc lọc, đếm, nhóm, sắp xếp hoặc so sánh kết quả nếu quyền truy vấn quá rộng. Do đó, không nên cho phép người dùng đọc mọi dòng rồi chỉ dựa vào việc che cột để bảo vệ toàn bộ thông tin.

Data Redaction cũng không tự che những bản sao đã xuất ra file, báo cáo, cache ứng dụng, log, data warehouse hoặc bản backup. Những luồng dữ liệu đó cần được bảo vệ riêng.

## 6. Che dữ liệu cho môi trường thử nghiệm

### 6.1. Xác định phạm vi dữ liệu nhạy cảm

Trước khi tạo bản sao cho dev hoặc QA, hãy xác định dữ liệu nào có thể nhận diện cá nhân, dữ liệu tài chính, dữ liệu xác thực hoặc thông tin nội bộ cần bảo vệ. Không chỉ xem tên cột; dữ liệu nhạy cảm có thể nằm trong ghi chú tự do, JSON, XML, CLOB, BLOB, file đính kèm, bảng audit và log.

Một danh mục dữ liệu có thể gồm:

| Nhóm dữ liệu | Ví dụ | Phương án biến đổi thường dùng |
|---|---|---|
| Định danh cá nhân | Họ tên, số giấy tờ, mã khách hàng | Thay bằng danh tính tổng hợp hoặc token giả. |
| Liên hệ | Email, số điện thoại, địa chỉ | Sinh dữ liệu giả theo định dạng hợp lệ. |
| Tài chính | Số thẻ, tài khoản, số dư, lương | Token hóa hoặc thay bằng giá trị thử nghiệm theo quy tắc nghiệp vụ. |
| Xác thực | Password, token, API key, câu hỏi bảo mật | Loại bỏ hoặc thay bằng credential thử nghiệm không dùng được ở môi trường thật. |
| Nội dung tự do | Ghi chú, nội dung hỗ trợ, địa chỉ trong văn bản | Xóa, thay thế hoặc xử lý bằng quy trình đã kiểm tra; không chỉ mask các cột có tên rõ ràng. |
| Dữ liệu kỹ thuật | Log, audit, file xuất, bản sao lưu | Xác định và xử lý mọi bản sao có thể chứa giá trị thật. |

### 6.2. Các kỹ thuật masking tĩnh

- **Substitution:** thay bằng giá trị giả được sinh từ tập dữ liệu an toàn, ví dụ tên và địa chỉ giả.
- **Shuffling:** hoán đổi giá trị giữa các dòng. Cần đánh giá nguy cơ liên kết ngược và không dùng nếu hoán đổi có thể làm lộ quan hệ thật.
- **Nulling hoặc xóa:** đặt `NULL` hoặc loại bỏ dữ liệu khi trường đó không cần cho kiểm thử.
- **Format-preserving masking:** giữ định dạng, độ dài hoặc mẫu ký tự để ứng dụng và bộ kiểm thử tiếp tục hoạt động.
- **Tokenization:** thay giá trị nhạy cảm bằng token; bảng ánh xạ phải được bảo vệ và không được đưa vào môi trường thử nghiệm.
- **Synthetic data:** tạo dữ liệu hoàn toàn giả thay vì sao chép bản ghi production.

Hash đơn giản không phải lúc nào cũng là cách ẩn danh an toàn. Với email, số điện thoại hoặc mã có không gian giá trị nhỏ, kẻ tấn công có thể thử các giá trị phổ biến rồi so sánh hash. Nếu cần giữ khả năng liên kết nhất quán, hãy dùng tokenization hoặc phép biến đổi có khóa theo quy trình bảo mật đã phê duyệt, đồng thời kiểm soát nơi lưu khóa và bảng ánh xạ.

### 6.3. Bảo toàn quan hệ và tính hợp lệ của dữ liệu

Một bản sao thử nghiệm thường cần giữ quan hệ giữa bảng khách hàng, đơn hàng, thanh toán và địa chỉ. Nếu thay mã khách hàng ở bảng `CUSTOMERS` nhưng không thay các khóa ngoại tương ứng trong `ORDERS`, dữ liệu thử nghiệm sẽ mất tính nhất quán.

Khi thiết kế phép masking, cần xác định:

1. Khóa chính và khóa ngoại nào phải tiếp tục khớp giữa các bảng.
2. Những cột nào cần cùng một phép biến đổi để cùng một thực thể vẫn có cùng danh tính giả.
3. Ràng buộc `UNIQUE`, `CHECK`, `NOT NULL`, định dạng và độ dài cột nào phải được giữ.
4. Các quan hệ thời gian, trạng thái và phân bố dữ liệu nào cần thiết để kịch bản kiểm thử có ý nghĩa.
5. Cột dẫn xuất, chỉ mục tìm kiếm, bảng lịch sử và dữ liệu phi cấu trúc nào cũng cần được xử lý.

Ví dụ, nếu một khách hàng xuất hiện trong `CUSTOMERS`, `ORDERS`, `SUPPORT_CASES` và `PAYMENTS`, hãy dùng cùng một ánh xạ giả cho mã khách hàng ở tất cả các bảng. Không tạo bốn mã độc lập nếu bài kiểm thử cần truy vết một khách hàng xuyên suốt quy trình.

### 6.4. Quy trình chuẩn bị bản sao đã mask

Một quy trình có kiểm soát có thể gồm:

1. **Phê duyệt mục đích:** xác định môi trường nhận dữ liệu, người dùng, thời hạn lưu và phạm vi được phép sử dụng.
2. **Phân loại và khám phá:** lập danh sách bảng, cột, file và log có dữ liệu nhạy cảm; xác định quan hệ và dependency.
3. **Tạo bản sao cô lập:** phục hồi vào vùng không cho nhóm phát triển truy cập trước khi hoàn tất masking.
4. **Thực hiện masking:** áp dụng phép biến đổi nhất quán trên mọi bảng và đối tượng có liên quan.
5. **Kiểm tra:** tìm giá trị thật còn sót, kiểm tra quan hệ, ràng buộc, định dạng và các kịch bản ứng dụng.
6. **Phê duyệt bàn giao:** chỉ cấp quyền sau khi chủ dữ liệu hoặc bộ phận an toàn thông tin xác nhận kết quả theo quy trình.
7. **Quản lý vòng đời:** giới hạn thời gian giữ bản sao, xóa bản sao cũ và xử lý backup hoặc file trung gian theo chính sách lưu trữ.

Không nên mở quyền truy cập dev vào bản clone ngay sau khi restore rồi mới bắt đầu mask. Khoảng thời gian dữ liệu thật tồn tại trong môi trường có người dùng không được phép cũng là một rủi ro cần kiểm soát.

## 7. Kiểm tra điều kiện sử dụng và xác nhận policy

Một policy được tạo thành công chưa đủ để chứng minh dữ liệu được che đúng. Cần kiểm tra điều kiện áp dụng, danh tính phiên, quyền bypass, các kiểu dữ liệu và kết quả mà ứng dụng thực sự nhận.

### 7.1. Xây dựng ma trận kiểm thử

Trước khi triển khai, lập ma trận gồm ít nhất các trường hợp sau:

| Trường hợp | Điều cần xác nhận |
|---|---|
| User thông thường có quyền đọc cột | Nhận giá trị đã redaction khi điều kiện policy đúng. |
| User được phép xem dữ liệu gốc | Nhận giá trị gốc đúng theo điều kiện đã phê duyệt. |
| User khác nhưng dùng cùng role | Policy có hành xử đúng theo danh tính hoặc context, không nhầm role với user. |
| Session thiếu application context | Hành vi mặc định an toàn, không tự mở quyền xem dữ liệu gốc. |
| Connection được tái sử dụng từ pool | Context của request trước không còn ảnh hưởng request sau. |
| Policy bị disable hoặc enable | Trạng thái policy được kiểm soát và kết quả thay đổi đúng dự kiến. |
| Tài khoản đặc quyền hoặc có quyền bypass | Xác định rõ ai có thể nhìn thấy dữ liệu gốc và audit việc sử dụng. |
| Dữ liệu `NULL`, chuỗi rỗng, sai định dạng hoặc độ dài biên | Kết quả không gây lỗi hoặc làm sai chức năng ứng dụng. |
| Truy vấn qua view, report hoặc API | Dữ liệu trả về ở mọi lớp vẫn phù hợp chính sách. |

### 7.2. Kiểm thử bằng hai session riêng

Không chỉ dùng một session DBA để kiểm tra policy. Hãy đăng nhập bằng tài khoản thông thường và tài khoản được phép xem dữ liệu gốc, rồi chạy cùng một truy vấn:

```sql
SELECT customer_id, email, phone_number
FROM app.customers
WHERE customer_id = :customer_id;
```

So sánh kết quả với dữ liệu gốc trong một quy trình kiểm thử được kiểm soát. Xác nhận user thông thường thấy giá trị đã che và user được phê duyệt thấy đúng giá trị gốc. Không đưa dữ liệu nhạy cảm thật vào ảnh chụp màn hình, log kiểm thử hoặc tài liệu bàn giao.

### 7.3. Kiểm tra điều kiện policy trong session

Đối với policy dựa trên `SESSION_USER`, có thể kiểm tra ngữ cảnh:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER') AS client_identifier
FROM dual;
```

`SESSION_USER` là danh tính đăng nhập; `CURRENT_SCHEMA` có thể được thay đổi để phân giải tên đối tượng và không nên dùng thay cho danh tính xác thực. `CLIENT_IDENTIFIER` chỉ đáng tin khi ứng dụng thiết lập nó qua đường được bảo vệ.

### 7.4. Kiểm tra cả policy và dữ liệu đã mask

Với Data Redaction, xác nhận policy tồn tại, đang bật, gắn đúng bảng/cột, dùng đúng hàm và có biểu thức đúng. Với static masking, chạy các truy vấn kiểm tra trên bản sao để tìm mẫu dữ liệu thật còn sót và xác nhận tính nhất quán giữa bảng.

Không chỉ kiểm tra một vài bản ghi đầu tiên. Nên dùng tiêu chí tìm kiếm dựa trên mẫu dữ liệu, tập giá trị đã biết trong môi trường kiểm thử, kiểm tra thống kê và rà soát các bảng hoặc cột có liên quan. Các truy vấn xác nhận cũng phải tránh ghi dữ liệu nhạy cảm ra log.

## 8. Tình huống nên dùng và không nên dùng

| Tình huống | Cách tiếp cận phù hợp | Lý do |
|---|---|---|
| Nhân viên hỗ trợ cần xem một phần số điện thoại trong production | Data Redaction | Giá trị gốc được giữ trong database; kết quả truy vấn được che theo policy. |
| Nhóm báo cáo cần phân tích nhưng không cần danh tính khách hàng | Data Redaction kết hợp quyền truy cập phù hợp, hoặc view tổng hợp | Giảm dữ liệu cá nhân xuất hiện trong kết quả; vẫn cần giới hạn dòng và cột được truy cập. |
| Cấp bản sao production cho developer | Static masking trước khi bàn giao | Dữ liệu lưu trong môi trường dev phải được biến đổi, không chỉ che lúc truy vấn. |
| Gửi dữ liệu cho nhà cung cấp hoặc đối tác | Static masking hoặc synthetic data theo phê duyệt | Bên nhận không nên được cấp bản sao có thông tin thật nếu không có căn cứ và kiểm soát phù hợp. |
| Cần kiểm thử luồng thanh toán với số thẻ thử nghiệm | Synthetic/test data do cổng thanh toán thử nghiệm cung cấp | Không dùng số thẻ thật; cần dữ liệu đáp ứng quy tắc sandbox. |
| Cần phân tích xu hướng mà không cần từng cá nhân | Tổng hợp, ẩn danh hoặc giảm độ chi tiết kết hợp masking | Giảm khả năng nhận diện từ tổ hợp thuộc tính và các tập dữ liệu khác. |

Không nên dùng Data Redaction làm biện pháp duy nhất khi người dùng có quyền quản trị, quyền bypass hoặc có thể truy cập bản sao chưa được bảo vệ. Cũng không nên dùng static masking mà không kiểm tra các bản sao, log, file xuất và dữ liệu phi cấu trúc.

## 9. Lỗi thiết kế và rủi ro thường gặp

| Lỗi | Hậu quả | Cách giảm rủi ro |
|---|---|---|
| Nghĩ rằng Data Redaction thay đổi dữ liệu lưu | Bản sao dev vẫn chứa dữ liệu thật. | Dùng static masking trước khi bàn giao bản sao. |
| Cấp `EXEMPT REDACTION POLICY` quá rộng | User có thể đọc dữ liệu gốc. | Giới hạn quyền bypass cho tài khoản quản trị được phê duyệt và audit. |
| Dựa vào `CLIENT_IDENTIFIER` do client tự đặt | Người gọi có thể giả danh user được xem dữ liệu gốc. | Thiết lập context qua package tin cậy và xác minh danh tính trước. |
| Chỉ mask cột có tên rõ ràng | Dữ liệu nhạy cảm còn trong ghi chú, JSON, log hoặc file đính kèm. | Khám phá dữ liệu trên toàn bộ schema và luồng xuất dữ liệu. |
| Mask khóa ở từng bảng bằng giá trị ngẫu nhiên độc lập | Mất quan hệ khóa ngoại và tính nhất quán. | Dùng cùng phép ánh xạ cho cùng thực thể trên mọi bảng. |
| Dùng hash không khóa cho email hoặc số điện thoại | Có thể dò ngược bằng danh sách giá trị phổ biến. | Dùng tokenization hoặc phép biến đổi có khóa được bảo vệ. |
| Chỉ thử bằng tài khoản DBA | Không phát hiện policy sai với user ứng dụng; DBA có thể bypass. | Kiểm tra bằng các danh tính thực tế và ma trận điều kiện. |
| Tắt policy để sửa lỗi rồi quên bật lại | Dữ liệu thật xuất hiện trong kết quả. | Quản lý thay đổi, giới hạn thời gian và kiểm tra trạng thái sau bảo trì. |
| Không kiểm tra connection pool | Context của request cũ có thể ảnh hưởng request mới. | Thiết lập và xóa context ở mọi đường thành công và lỗi. |
| Chỉ kiểm tra bảng nguồn | API, view, report hoặc export vẫn có thể làm lộ dữ liệu. | Kiểm thử toàn bộ đường dữ liệu tới người tiêu thụ. |

## 10. Quy trình triển khai Data Redaction

Khi triển khai một policy trên môi trường đang vận hành, có thể áp dụng trình tự sau:

1. **Xác định mục tiêu:** ghi rõ cột nhạy cảm, nhóm user cần che, nhóm được phép xem đầy đủ và lý do nghiệp vụ.
2. **Rà soát quyền:** kiểm tra grants, role, `EXEMPT REDACTION POLICY`, `SYSDBA` và tài khoản sở hữu schema.
3. **Chọn kiểu redaction:** full, partial, regexp hoặc random theo yêu cầu hiển thị và kiểu dữ liệu.
4. **Thiết kế expression:** dùng danh tính hoặc context tin cậy; xác định hành vi khi context thiếu hoặc sai.
5. **Tạo policy ở môi trường kiểm thử:** dùng `DBMS_REDACT.ADD_POLICY` và xác nhận policy cùng column trong data dictionary.
6. **Kiểm thử nhiều session:** xác nhận user thông thường, user được phép, tài khoản ứng dụng và các đường truy vấn thực tế.
7. **Đánh giá tác động:** kiểm tra ứng dụng, báo cáo, truy vấn lọc, xử lý lỗi, connection pool và hiệu năng.
8. **Triển khai có phê duyệt:** lưu script, người thực hiện, người phê duyệt, thời điểm và kế hoạch rollback.
9. **Giám sát và rà soát:** kiểm tra policy còn bật, quyền bypass không bị mở rộng và danh sách cột nhạy cảm được cập nhật khi schema thay đổi.

Đối với static masking, cần thêm bước cô lập bản sao, biến đổi toàn bộ dữ liệu liên quan, kiểm tra giá trị thật còn sót và chỉ bàn giao sau khi được phê duyệt.

## Kết luận

Data Redaction của Oracle che giá trị trong kết quả truy vấn theo policy và điều kiện sử dụng; dữ liệu gốc vẫn được giữ trong database. Static data masking biến đổi bản sao để môi trường dev, QA hoặc bên thứ ba không nhận dữ liệu thật. Muốn bảo vệ hiệu quả, cần chọn đúng kỹ thuật theo mục tiêu, kiểm soát quyền bypass, thiết kế điều kiện dựa trên ngữ cảnh tin cậy, bảo toàn quan hệ dữ liệu thử nghiệm và kiểm tra bằng nhiều danh tính cùng các đường truy cập thực tế. Policy chỉ được coi là triển khai đúng khi kết quả hiển thị, quyền truy cập và các bản sao dữ liệu đều đáp ứng yêu cầu bảo vệ đã xác định.

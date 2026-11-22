# Conditional compilation, cảnh báo và tham số biên dịch trong PL/SQL

PL/SQL có một số cơ chế giúp kiểm soát mã nguồn ngay tại thời điểm biên dịch. Ba nhóm thường được dùng cùng nhau nhưng có mục đích khác nhau:

- **Conditional compilation** chọn phần mã sẽ được đưa vào unit đã biên dịch, dựa trên điều kiện tĩnh và compile-time flags.
- **Compiler warnings** cảnh báo các mẫu code đáng ngờ hoặc có thể gây lỗi, ví dụ mã không thể chạy hay exception handler nuốt lỗi.
- **Compiler parameters** quyết định cách compiler tối ưu, tạo code interpreted/native, thu thập thông tin phân tích và xử lý cảnh báo.

Ví dụ, một package có thể chứa nhánh debug chỉ được đưa vào bản development, đồng thời production bật cảnh báo ở mức nghiêm ngặt và dùng cùng một bộ compiler settings cho mọi lần build:

```sql
ALTER SESSION SET PLSQL_CCFLAGS =
    'debug:FALSE, feature_orders:TRUE';

ALTER SESSION SET PLSQL_WARNINGS = 'ENABLE:ALL';

ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL = 2;
ALTER SESSION SET PLSQL_CODE_TYPE = INTERPRETED;
```

Các setting này ảnh hưởng đến lần biên dịch PL/SQL trong phạm vi áp dụng. Chúng không tự thay đổi logic của một object đã biên dịch; muốn áp dụng cấu hình mới, cần biên dịch lại object tương ứng.

## 1. Conditional compilation là gì?

### 1.1. Chọn mã tại thời điểm biên dịch

Conditional compilation cho phép compiler chọn một nhánh mã dựa trên biểu thức tĩnh. Nhánh không được chọn sẽ không trở thành mã thực thi trong unit đã biên dịch.

Cú pháp cơ bản:

```sql
$IF static_boolean_expression $THEN
    -- Phần mã được chọn khi điều kiện TRUE
$ELSIF another_static_expression $THEN
    -- Nhánh thay thế
$ELSE
    -- Nhánh mặc định
$END
```

Ví dụ:

```sql
CREATE OR REPLACE PROCEDURE show_build_mode AS
BEGIN
    $IF $$DEBUG_BUILD $THEN
        DBMS_OUTPUT.PUT_LINE('Debug build');
    $ELSE
        DBMS_OUTPUT.PUT_LINE('Production build');
    $END
END;
/
```

Nếu compile flag DEBUG_BUILD là TRUE, compiler giữ nhánh debug. Nếu FALSE, compiler giữ nhánh production. Nhánh còn lại bị loại khỏi mã được biên dịch.

### 1.2. Khác với IF runtime

`IF` và `CASE` thông thường quyết định luồng chạy khi chương trình đang thực thi. Conditional compilation quyết định nhánh nào tồn tại trong unit đã biên dịch.

| Tiêu chí | IF runtime | Conditional compilation |
|---|---|---|
| Thời điểm quyết định | Khi chạy | Khi biên dịch |
| Điều kiện | Có thể dựa trên biến, parameter, dữ liệu runtime | Biểu thức tĩnh/compile-time flag |
| Nhánh không được chọn | Vẫn được biên dịch | Bị loại khỏi unit đã biên dịch |
| Mục đích | Điều khiển nghiệp vụ | Khác biệt theo version/build/configuration |
| Thay đổi điều kiện | Thay input/runtime state | Phải compile lại để đổi nhánh |

Ví dụ runtime:

```sql
IF p_debug_mode THEN
    DBMS_OUTPUT.PUT_LINE('Debug');
ELSE
    NULL;
END IF;
```

Ví dụ compile time:

```sql
$IF $$DEBUG_BUILD $THEN
    DBMS_OUTPUT.PUT_LINE('Debug');
$ELSE
    NULL;
$END
```

Không dùng conditional compilation cho điều kiện nghiệp vụ cần thay đổi theo từng request. Đó là công việc của IF runtime hoặc cấu hình dữ liệu.

### 1.3. Khi nào nên dùng?

Các trường hợp phù hợp:

- Hỗ trợ nhiều phiên bản Oracle có API hoặc syntax khác nhau.
- Bật/tắt instrumentation hoặc diagnostic code giữa development và production.
- Chọn implementation theo platform hoặc build profile.
- Bật feature thử nghiệm khi compile một bản riêng.
- Loại bỏ code tương thích ngược khi build cho phiên bản database mới.
- Gắn thông tin build/unit vào log hoặc diagnostic output.

Conditional compilation không phải cơ chế phân quyền. Không được dựa vào flag để quyết định một user có được phép xem hoặc sửa dữ liệu hay không.

## 2. Compile-time flags và PLSQL_CCFLAGS

### 2.1. Khai báo flag

Tham số `PLSQL_CCFLAGS` nhận danh sách cặp tên/giá trị, phân cách bằng dấu phẩy:

```sql
ALTER SESSION SET PLSQL_CCFLAGS =
    'debug:TRUE, trace:FALSE, feature_orders:TRUE';
```

Flag có thể mang giá trị Boolean hoặc số nguyên tĩnh. Tên flag được tham chiếu trong source bằng hai dấu dollar:

```sql
$IF $$DEBUG $THEN
    -- Compile nhánh debug
$END
```

Tên flag trong ví dụ là DEBUG. Flag được cung cấp lúc biên dịch, không phải biến PL/SQL được gán trong runtime.

### 2.2. Dùng nhiều flag

```sql
$IF $$FEATURE_ORDERS AND NOT $$TRACE $THEN
    DBMS_OUTPUT.PUT_LINE('Orders feature without trace');
$ELSIF $$TRACE $THEN
    DBMS_OUTPUT.PUT_LINE('Trace build');
$ELSE
    NULL;
$END
```

Biểu thức điều kiện có thể kết hợp toán tử Boolean và các giá trị tĩnh. Hãy đặt giá trị mặc định rõ trong build script để tránh phụ thuộc vào flag không được khai báo.

### 2.3. Giá trị số

Flag số có thể dùng cho mức tương thích hoặc lựa chọn implementation:

```sql
ALTER SESSION SET PLSQL_CCFLAGS =
    'api_level:2, debug:FALSE';
```

Trong source:

```sql
$IF $$API_LEVEL >= 2 $THEN
    l_result := new_api_call();
$ELSE
    l_result := legacy_api_call();
$END
```

Giá trị số cần là giá trị tĩnh phù hợp với quy tắc PLSQL_CCFLAGS. Không truyền chuỗi runtime hoặc nội dung người dùng vào compile flags.

### 2.4. Kết hợp flag với package

```sql
CREATE OR REPLACE PACKAGE build_features AS
    FUNCTION feature_name RETURN VARCHAR2;
END build_features;
/

CREATE OR REPLACE PACKAGE BODY build_features AS
    FUNCTION feature_name RETURN VARCHAR2 IS
    BEGIN
        $IF $$FEATURE_ORDERS $THEN
            RETURN 'ORDERS_ENABLED';
        $ELSE
            RETURN 'ORDERS_DISABLED';
        $END
    END;
END build_features;
/
```

Khi đổi flag và compile lại package body, implementation được chọn thay đổi. Nếu package specification không đổi, caller thường không cần đổi signature, nhưng vẫn cần triển khai và kiểm tra dependency theo quy trình.

### 2.5. Flag không được khai báo

Không nên dựa vào giá trị ngầm của một flag chưa được cấu hình. Hãy luôn đặt PLSQL_CCFLAGS đầy đủ trong build pipeline và kiểm tra giá trị đã lưu của object sau compile. Với môi trường có nhiều profile, lưu compile flags vào artifact/build metadata để có thể tái tạo chính xác.

## 3. Inquiry directives

Inquiry directives là giá trị do compiler cung cấp trong lúc biên dịch. Chúng được viết với tiền tố $$ và có thể dùng trong biểu thức static hoặc trong mã PL/SQL phù hợp.

### 3.1. $$PLSQL_UNIT

``PLSQL_UNIT` trả về tên PL/SQL unit đang được biên dịch. Có thể dùng để tạo diagnostic:

```sql
CREATE OR REPLACE PROCEDURE process_orders AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Unit=' || $$PLSQL_UNIT
    );
END;
/
```

Tên unit hữu ích khi cùng một đoạn code hoặc helper được biên dịch trong nhiều object.

### 3.2. $$PLSQL_LINE

``PLSQL_LINE` cung cấp số dòng source tại vị trí directive. Nó hữu ích cho trace hoặc error context:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'At line ' || $$PLSQL_LINE ||
        ' in ' || $$PLSQL_UNIT
    );
END;
```

Khi source thay đổi, số dòng thay đổi theo. Không dùng số dòng làm định danh bền vững cho một nghiệp vụ.

### 3.3. Các inquiry directives khác

Oracle cung cấp thêm các directive về unit và compile environment, tùy phiên bản:

| Directive | Ý nghĩa |
|---|---|
| $$PLSQL_UNIT | Tên unit đang biên dịch |
| $$PLSQL_LINE | Số dòng source tại vị trí directive |
| $$PLSQL_UNIT_OWNER | Owner của unit trong các phiên bản hỗ trợ |
| $$PLSQL_UNIT_TYPE | Loại unit trong các phiên bản hỗ trợ |
| $$PLSQL_COMPILATION_PARAMETER('name') | Giá trị compiler parameter được dùng cho lần compile |
| $$flag_name | Giá trị compile-time flag do PLSQL_CCFLAGS cung cấp |

Kiểm tra danh sách directive được hỗ trợ trong đúng Oracle release. Không giả định một directive mới có mặt trên mọi phiên bản database.

### 3.4. Đọc compiler parameter

``PLSQL_COMPILATION_PARAMETER` cho phép source biết giá trị một compiler parameter tại thời điểm biên dịch:

```sql
CREATE OR REPLACE PROCEDURE show_compile_settings AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Optimize level=' ||
        $$PLSQL_COMPILATION_PARAMETER('PLSQL_OPTIMIZE_LEVEL')
    );
    DBMS_OUTPUT.PUT_LINE(
        'Code type=' ||
        $$PLSQL_COMPILATION_PARAMETER('PLSQL_CODE_TYPE')
    );
END;
/
```

Đây là giá trị gắn với bản compile hiện tại, không phải truy vấn động tham số instance ở mỗi lần gọi. Nếu compile lại với setting khác, giá trị được nhúng trong unit sẽ thay đổi.

### 3.5. Dùng directive trong diagnostic

```sql
CREATE OR REPLACE PROCEDURE log_compile_context AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Unit=' || $$PLSQL_UNIT ||
        ', line=' || $$PLSQL_LINE ||
        ', optimize=' ||
        $$PLSQL_COMPILATION_PARAMETER('PLSQL_OPTIMIZE_LEVEL')
    );
END;
/
```

Không nên in các thông tin này ở mọi request production nếu tạo log quá nhiều. Chúng hữu ích trong diagnostic, support bundle hoặc log có mức độ.

## 4. Cấu trúc conditional compilation

### 4.1. $IF, $ELSIF, $ELSE và $END

Một directive selection bắt đầu bằng $IF và kết thúc bằng $END. Có thể có nhiều $ELSIF và một $ELSE:

```sql
$IF $$API_LEVEL >= 3 $THEN
    l_result := implementation_v3();
$ELSIF $$API_LEVEL = 2 $THEN
    l_result := implementation_v2();
$ELSE
    l_result := implementation_v1();
$END
```

Mỗi nhánh cần là PL/SQL hợp lệ khi được chọn. Đảm bảo các nhánh có cùng kiểu dữ liệu/contract cần thiết để phần code còn lại compile.

### 4.2. Conditional compilation lồng nhau

```sql
$IF $$FEATURE_ORDERS $THEN
    $IF $$DEBUG $THEN
        log_debug('Orders enabled');
    $END
    process_orders;
$ELSE
    raise_application_error(-20091, 'Orders feature unavailable');
$END
```

Nesting hữu ích khi một nhánh phụ thuộc nhiều điều kiện. Giữ nesting nông và đặt flag có tên mô tả để người đọc hiểu build profile.

### 4.3. Trong phần khai báo

Có thể điều kiện hóa khai báo constant, variable hoặc subprogram:

```sql
CREATE OR REPLACE PACKAGE BODY build_config AS
    $IF $$DEBUG $THEN
        c_log_level CONSTANT PLS_INTEGER := 5;
    $ELSE
        c_log_level CONSTANT PLS_INTEGER := 1;
    $END

    PROCEDURE show_level IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(c_log_level);
    END;
END build_config;
/
```

Tên và kiểu được tham chiếu phía sau phải tồn tại trong mọi profile được hỗ trợ.

### 4.4. Loại bỏ implementation theo version

Ví dụ minh họa chọn code dựa trên version database:

```sql
$IF DBMS_DB_VERSION.VERSION >= 12 $THEN
    -- Implementation dành cho phiên bản mới.
$ELSE
    -- Implementation tương thích cũ.
$END
```

DBMS_DB_VERSION cung cấp các constant về phiên bản Oracle. Hãy kiểm tra chính xác version/feature boundary của API cần dùng; không suy luận rằng một feature xuất hiện chỉ vì version major đã đạt ngưỡng.

### 4.5. $ERROR để dừng compile có chủ đích

Directive $ERROR cho phép compiler phát sinh lỗi do lập trình viên định nghĩa khi điều kiện build không được đáp ứng:

```sql
$IF $$API_LEVEL < 2 $THEN
    $ERROR 'This package requires API_LEVEL 2 or later' $END
$END
```

Đây là cách làm build fail sớm nếu cấu hình không tương thích. Nội dung lỗi nên nói rõ điều kiện cần thiết và flag phải được đặt thế nào.

## 5. Conditional compilation theo version và feature

### 5.1. Version check

Khi một package hỗ trợ nhiều Oracle release, conditional compilation có thể chọn implementation phù hợp:

```sql
$IF DBMS_DB_VERSION.VERSION >= 19 $THEN
    -- Nhánh cho release mới.
$ELSE
    -- Nhánh tương thích cũ.
$END
```

Version check nên dựa trên feature thực tế và release/RU được hỗ trợ. Một tính năng có thể phụ thuộc patch level, option hoặc cấu hình, không chỉ major version.

### 5.2. Feature flag của build

```sql
ALTER SESSION SET PLSQL_CCFLAGS =
    'feature_bulk_api:TRUE, feature_json:FALSE';
```

```sql
$IF $$FEATURE_BULK_API $THEN
    call_bulk_implementation;
$ELSE
    call_legacy_implementation;
$END
```

Flag compile-time phù hợp để tạo artifact khác nhau. Nó không phải feature toggle runtime mà quản trị viên có thể bật/tắt ngay mà không compile lại.

### 5.3. Tránh nhiều bản build khó kiểm soát

Nếu mỗi khách hàng hoặc môi trường có một tổ hợp flags riêng, số lượng artifact có thể tăng nhanh. Quản lý ma trận:

| Profile | DEBUG | FEATURE_ORDERS | API_LEVEL | Mục đích |
|---|---:|---:|---:|---|
| Development | TRUE | TRUE | 3 | Debug và thử feature |
| Test | FALSE | TRUE | 3 | Kiểm thử gần production |
| Production | FALSE | TRUE | 3 | Artifact triển khai |
| Legacy | FALSE | FALSE | 2 | Tương thích hệ thống cũ |

Không tạo profile không được kiểm thử. Build flags, compiler settings và database release phải được ghi lại cùng artifact.

### 5.4. Không dùng flag cho dữ liệu nhạy cảm

Flag được lưu trong compile settings và có thể xem qua data dictionary theo quyền. Không đưa password, secret, token hoặc dữ liệu người dùng vào PLSQL_CCFLAGS. Compile-time flags là cấu hình build, không phải kho bí mật.

## 6. Compiler warnings

### 6.1. Warning khác compile error

Compiler warning là thông báo về cấu trúc code có thể đáng ngờ hoặc không tối ưu. Warning thường không ngăn object được tạo, trừ khi cấu hình nâng warning thành error.

Oracle dùng mã cảnh báo dạng PLW-nnnnn. Warning không phải exception runtime và không có nghĩa chương trình chắc chắn sai; nhưng nên xem xét trước khi phát hành.

### 6.2. Bật tất cả warning

```sql
ALTER SESSION SET PLSQL_WARNINGS = 'ENABLE:ALL';
```

Setting này áp dụng cho các lần compile trong session sau đó, theo phạm vi hỗ trợ của compiler. Nếu chỉ bật warning trong session nhưng build được thực hiện ở session khác, cấu hình có thể không giống nhau.

### 6.3. Bật theo category

Oracle hỗ trợ các category cảnh báo chính:

- SEVERE: vấn đề nghiêm trọng.
- PERFORMANCE: cơ hội cải thiện hiệu năng.
- INFORMATIONAL: thông tin bổ sung.

Ví dụ:

```sql
ALTER SESSION SET PLSQL_WARNINGS =
    'ENABLE:SEVERE, ENABLE:PERFORMANCE';
```

Có thể bật/tắt theo category và theo mã cảnh báo cụ thể. Xác định policy cho project thay vì chỉ dùng setting tùy ý trên máy cá nhân.

### 6.4. Tắt warning

```sql
ALTER SESSION SET PLSQL_WARNINGS = 'DISABLE:ALL';
```

Tắt warning có thể che các vấn đề đáng chú ý. Trong pipeline CI/build, nên bật tối thiểu severe và thường bật all để có thông tin đầy đủ; nếu phải tắt một warning, ghi lý do và phạm vi rõ ràng.

### 6.5. Nâng warning thành error

```sql
ALTER SESSION SET PLSQL_WARNINGS = 'ERROR:06002';
```

Có thể nâng một warning hoặc category thành lỗi compile. Ví dụ policy:

```sql
ALTER SESSION SET PLSQL_WARNINGS =
    'ENABLE:ALL, ERROR:06002';
```

Khi compiler phát hiện warning đã được nâng thành error, compilation thất bại. Cách này hữu ích để ngăn một số anti-pattern đi vào build.

## 7. Ví dụ warning và cách đọc

### 7.1. Unreachable code

Một nhánh code không thể chạy có thể tạo warning:

```sql
CREATE OR REPLACE PROCEDURE unreachable_demo AS
BEGIN
    RETURN;
    DBMS_OUTPUT.PUT_LINE('This statement cannot run');
END;
/
```

Compiler có thể báo PLW-06002 cho unreachable code. Xem lại control flow để xóa code thừa hoặc sửa điều kiện/return.

### 7.2. OTHERS handler không ném lại lỗi

Ví dụ:

```sql
CREATE OR REPLACE PROCEDURE swallow_error_demo AS
BEGIN
    risky_operation;
EXCEPTION
    WHEN OTHERS THEN
        log_error(SQLERRM);
        -- Không RAISE: caller có thể tưởng operation thành công.
END;
/
```

Compiler có thể cảnh báo PLW-06009 khi OTHERS handler không kết thúc bằng RAISE hoặc RAISE_APPLICATION_ERROR. Cách xử lý thường tốt hơn:

```sql
EXCEPTION
    WHEN OTHERS THEN
        log_error(SQLERRM);
        RAISE;
```

Nếu chủ đích chuyển lỗi thành kết quả nghiệp vụ, hãy làm rõ contract và bảo đảm lỗi được biểu diễn đầy đủ cho caller.

### 7.3. Warning hiệu năng

Một số warning chỉ ra cơ hội tối ưu như parameter có thể hưởng lợi từ NOCOPY hoặc biểu thức/biến có thể được viết hiệu quả hơn. Không thêm NOCOPY chỉ để hết warning: NOCOPY có thể thay đổi semantics khi exception xảy ra vì parameter có thể đã bị thay đổi một phần.

Đọc mã cảnh báo cụ thể và tài liệu Oracle trước khi sửa. Warning hiệu năng là gợi ý cần đánh giá bằng benchmark, không phải chỉ thị bắt buộc.

### 7.4. Warning không thay thế test

Compiler không thể chứng minh logic nghiệp vụ đúng, transaction đúng hay mọi dữ liệu runtime hợp lệ. Bật warning là một lớp kiểm soát tĩnh, cần kết hợp unit/integration tests, static analysis và runtime monitoring.

## 8. Đọc compiler warnings và errors

### 8.1. USER_ERRORS

Sau khi compile, xem lỗi và warning:

```sql
SELECT name,
       type,
       sequence,
       line,
       position,
       attribute,
       message_number,
       text
FROM user_errors
ORDER BY name, type, sequence;
```

Các cột ATTRIBUTE và MESSAGE_NUMBER giúp phân biệt ERROR/WARNING và mã thông báo. ALL_ERRORS/DBA_ERRORS dùng khi cần phạm vi rộng hơn và có quyền.

### 8.2. Lọc theo object

```sql
SELECT name,
       type,
       line,
       position,
       attribute,
       text
FROM user_errors
WHERE name = 'UNREACHABLE_DEMO'
ORDER BY sequence;
```

Tên object trong data dictionary thường được lưu uppercase nếu không tạo quoted identifier.

### 8.3. SHOW ERRORS

Trong SQL*Plus hoặc SQLcl:

```sql
SHOW ERRORS PROCEDURE unreachable_demo;
```

SHOW ERRORS hữu ích khi thao tác thủ công. Trong build automation, truy vấn data dictionary thường dễ thu thập và lưu kết quả hơn.

### 8.4. Xác định trạng thái object

```sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE object_name = 'UNREACHABLE_DEMO';
```

Object INVALID thường có lỗi compilation hoặc dependency cần xử lý. Object VALID vẫn có thể có warning; warning không đồng nghĩa object invalid.

## 9. DBMS_WARNING

### 9.1. Điều khiển warning bằng package

DBMS_WARNING cung cấp API để đọc/đặt warning settings từ PL/SQL:

```sql
DECLARE
    l_old_setting VARCHAR2(4000);
BEGIN
    l_old_setting :=
        DBMS_WARNING.GET_WARNING_SETTING_STRING('SESSION');

    DBMS_WARNING.SET_WARNING_SETTING_STRING(
        'ENABLE:ALL',
        'SESSION'
    );

    -- Thực hiện thao tác compile cần thiết trong session.

    DBMS_WARNING.SET_WARNING_SETTING_STRING(
        l_old_setting,
        'SESSION'
    );
END;
/
```

Ví dụ cho thấy cần lưu setting cũ và khôi phục sau khi thao tác. Nếu chỉ đổi setting rồi để lại, các lần compile tiếp theo trong cùng session có thể chịu ảnh hưởng ngoài dự kiến.

### 9.2. Scope SESSION và SYSTEM

DBMS_WARNING hỗ trợ phạm vi SESSION và SYSTEM theo API. Thay đổi SYSTEM ảnh hưởng default rộng hơn và cần quyền thích hợp; không thay đổi system-wide warning policy chỉ để compile một object riêng.

### 9.3. Thiết lập theo mã warning

DBMS_WARNING có API làm việc với mã cảnh báo cụ thể, ví dụ GET_WARNING_SETTING_NUM và ADD_WARNING_SETTING_NUM. Dùng khi cần quản lý một mã riêng bằng code. Tên warning và category cần được kiểm tra theo Oracle release.

### 9.4. Khi nào dùng DBMS_WARNING?

Phù hợp cho build/deployment script chạy trong PL/SQL hoặc công cụ quản trị muốn lưu và khôi phục warning policy. Với pipeline SQL đơn giản, ALTER SESSION SET PLSQL_WARNINGS thường dễ đọc hơn.

## 10. Compiler parameters quan trọng

Compiler parameters ảnh hưởng cách unit PL/SQL được tạo. Chúng cần được quản lý như một phần của build configuration.

### 10.1. PLSQL_OPTIMIZE_LEVEL

PLSQL_OPTIMIZE_LEVEL điều khiển mức tối ưu hóa PL/SQL. Các mức thường gặp:

| Mức | Ý nghĩa khái quát |
|---:|---|
| 0 | Tối ưu hóa tối thiểu, hữu ích cho một số tình huống debug/compatibility |
| 1 | Một số tối ưu cơ bản |
| 2 | Mức mặc định thường dùng trong các release hiện đại |
| 3 | Tối ưu hóa mạnh hơn, có thể bao gồm thêm cơ hội inlining |

Ví dụ:

```sql
ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL = 2;
```

Mức cao hơn không bảo đảm mọi chương trình nhanh hơn. Đo workload thực tế, kiểm tra behavior và xem xét các routine có side effect hoặc phụ thuộc thứ tự thực thi.

### 10.2. PLSQL_CODE_TYPE

PLSQL_CODE_TYPE chọn dạng code:

- INTERPRETED: PL/SQL được thực thi theo cơ chế interpreted.
- NATIVE: PL/SQL được biên dịch thành native code theo khả năng và cấu hình database/platform.

Ví dụ:

```sql
ALTER SESSION SET PLSQL_CODE_TYPE = INTERPRETED;
```

NATIVE có thể cải thiện hiệu năng cho workload PL/SQL CPU-bound, nhưng cần xem yêu cầu platform, cấu hình native compilation, thời gian compile, vận hành và khả năng triển khai. Không mặc định native luôn nhanh hơn cho mọi ứng dụng.

### 10.3. PLSQL_WARNINGS

PLSQL_WARNINGS đặt warning policy: ENABLE, DISABLE hoặc ERROR theo ALL, category hoặc warning number. Setting này quyết định thông báo nào được phát ra và warning nào làm compile thất bại.

### 10.4. PLSQL_CCFLAGS

PLSQL_CCFLAGS truyền compile-time flags cho conditional compilation. Giá trị phải được quản lý nhất quán trong build script; thay flag cần compile lại unit để đổi nhánh được chọn.

### 10.5. PLSQL_DEBUG

PLSQL_DEBUG là setting liên quan đến thông tin phục vụ debug trong các release/công cụ tương ứng. Cách sử dụng và mức độ cần thiết phụ thuộc phiên bản Oracle và debugger. Không nhầm PLSQL_DEBUG với flag ứng dụng tên DEBUG hoặc với việc in DBMS_OUTPUT. Kiểm tra tài liệu release đang chạy trước khi chuẩn hóa setting này.

### 10.6. PLSCOPE_SETTINGS

PLSCOPE_SETTINGS điều khiển metadata compiler thu thập cho PL/SQL identifiers và statements, phục vụ phân tích source/dependency:

```sql
ALTER SESSION SET PLSCOPE_SETTINGS =
    'IDENTIFIERS:ALL, STATEMENTS:ALL';
```

Metadata có thể được truy vấn qua USER_IDENTIFIERS và USER_STATEMENTS trong các release hỗ trợ. Thu thập thêm metadata có chi phí storage/compile nhất định; bật theo nhu cầu code analysis và công cụ.

### 10.7. NLS_LENGTH_SEMANTICS

NLS_LENGTH_SEMANTICS có thể ảnh hưởng cách khai báo độ dài CHAR/VARCHAR2 khi compile source không chỉ rõ BYTE hoặc CHAR. Vì vậy, cùng một source được compile trong session có NLS_LENGTH_SEMANTICS khác nhau có thể có metadata khác. Ưu tiên khai báo rõ CHAR/BYTE trong schema/source quan trọng và ghi lại setting build.

## 11. Scope và cách áp dụng compiler settings

### 11.1. ALTER SESSION

ALTER SESSION thay đổi setting cho session hiện tại và ảnh hưởng những lần compile phù hợp sau đó:

```sql
ALTER SESSION SET PLSQL_WARNINGS = 'ENABLE:ALL';
ALTER SESSION SET PLSQL_CCFLAGS = 'debug:FALSE, feature_orders:TRUE';
ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL = 2;
ALTER SESSION SET PLSQL_CODE_TYPE = INTERPRETED;
```

Đây thường là cách thuận tiện cho build script kết nối bằng một session chuyên dụng.

### 11.2. ALTER SYSTEM

ALTER SYSTEM đặt giá trị ở cấp instance/system theo khả năng modifiable của parameter và scope được chọn:

```sql
ALTER SYSTEM SET PLSQL_WARNINGS = 'ENABLE:ALL' SCOPE=BOTH;
```

Lệnh cần quyền DBA phù hợp và có thể ảnh hưởng nhiều session/build process. Không dùng ALTER SYSTEM trong script compile một module nếu ALTER SESSION là đủ.

### 11.3. Object-level compile options

Có thể truyền compiler options khi compile một object:

```sql
ALTER PROCEDURE unreachable_demo COMPILE
    PLSQL_WARNINGS = 'ENABLE:ALL';
```

Với package, specification và body có thể được compile riêng:

```sql
ALTER PACKAGE build_features COMPILE SPECIFICATION;
ALTER PACKAGE build_features COMPILE BODY;
```

Kiểm tra syntax chính xác của ALTER ... COMPILE theo object type và Oracle release đang dùng.

### 11.4. REUSE SETTINGS

`REUSE SETTINGS` yêu cầu Oracle dùng lại compiler settings đã lưu cho object khi biên dịch lại, thay vì lấy các setting mặc định hiện hành của session theo cách thông thường.

Ví dụ:

```sql
ALTER PROCEDURE unreachable_demo COMPILE REUSE SETTINGS;
```

Điều này hữu ích khi compile lại object để giữ nguyên cấu hình build đã dùng trước đó. Khi muốn đổi flags hoặc warnings, hãy truyền setting mới theo cú pháp được hỗ trợ hoặc tạo lại object trong session build có cấu hình rõ ràng.

### 11.5. CREATE OR REPLACE

CREATE OR REPLACE tạo/biên dịch unit bằng compiler settings áp dụng trong môi trường compile. Do đó build script cần thiết lập các tham số trước khi chạy DDL tạo package/procedure/function.

Không giả định một object được tạo trên developer laptop sẽ có cùng settings với object được tạo trên CI hoặc production.

## 12. Xem settings đã dùng cho object

### 12.1. USER_PLSQL_OBJECT_SETTINGS

View USER_PLSQL_OBJECT_SETTINGS lưu thông tin compiler settings của PL/SQL object trong schema:

```sql
SELECT name,
       type,
       plsql_optimize_level,
       plsql_code_type,
       plsql_debug,
       plsql_warnings,
       plsql_ccflags,
       plscope_settings,
       nls_length_semantics
FROM user_plsql_object_settings
ORDER BY type, name;
```

ALL_PLSQL_OBJECT_SETTINGS hoặc DBA_PLSQL_OBJECT_SETTINGS có thể dùng cho phạm vi rộng hơn nếu có quyền. Tên/cột view có thể khác theo release; kiểm tra data dictionary của hệ thống.

### 12.2. So sánh giữa các object

```sql
SELECT name,
       type,
       plsql_optimize_level,
       plsql_code_type,
       plsql_warnings,
       plsql_ccflags
FROM user_plsql_object_settings
WHERE name IN ('BUILD_FEATURES', 'SHOW_COMPILE_SETTINGS')
ORDER BY name, type;
```

Nếu cùng một package spec/body hoặc các unit trong cùng module có settings không đồng nhất, cần xác định đó là chủ đích hay sai lệch build.

### 12.3. Lưu lại build manifest

Một build manifest có thể ghi:

- Oracle database version/RU.
- Schema owner và object list.
- PLSQL_OPTIMIZE_LEVEL.
- PLSQL_CODE_TYPE.
- PLSQL_WARNINGS.
- PLSQL_CCFLAGS.
- PLSCOPE_SETTINGS.
- NLS_LENGTH_SEMANTICS.
- Source revision/build ID.

Manifest giúp tái tạo artifact và điều tra khác biệt giữa môi trường.

## 13. Ví dụ quy trình compile có kiểm soát

### 13.1. Đặt compiler settings

```sql
ALTER SESSION SET PLSQL_WARNINGS = 'ENABLE:ALL';
ALTER SESSION SET PLSQL_CCFLAGS =
    'debug:FALSE, feature_orders:TRUE, api_level:3';
ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL = 2;
ALTER SESSION SET PLSQL_CODE_TYPE = INTERPRETED;
ALTER SESSION SET PLSCOPE_SETTINGS =
    'IDENTIFIERS:ALL, STATEMENTS:ALL';
```

### 13.2. Tạo object

```sql
CREATE OR REPLACE PROCEDURE compile_profile_demo AS
BEGIN
    $IF $$DEBUG $THEN
        DBMS_OUTPUT.PUT_LINE('Diagnostic enabled');
    $END

    $IF $$FEATURE_ORDERS $THEN
        DBMS_OUTPUT.PUT_LINE('Orders feature enabled');
    $ELSE
        DBMS_OUTPUT.PUT_LINE('Orders feature disabled');
    $END
END;
/
```

### 13.3. Xem warning/error

```sql
SELECT name, type, line, position, attribute, text
FROM user_errors
WHERE name = 'COMPILE_PROFILE_DEMO'
ORDER BY sequence;
```

### 13.4. Xem object status và settings

```sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'COMPILE_PROFILE_DEMO';

SELECT name,
       type,
       plsql_optimize_level,
       plsql_code_type,
       plsql_warnings,
       plsql_ccflags,
       plscope_settings
FROM user_plsql_object_settings
WHERE name = 'COMPILE_PROFILE_DEMO';
```

### 13.5. Build profile khác

```sql
ALTER SESSION SET PLSQL_CCFLAGS =
    'debug:TRUE, feature_orders:FALSE, api_level:2';

CREATE OR REPLACE PROCEDURE compile_profile_demo AS
BEGIN
    $IF $$DEBUG $THEN
        DBMS_OUTPUT.PUT_LINE('Diagnostic enabled');
    $END

    $IF $$FEATURE_ORDERS $THEN
        DBMS_OUTPUT.PUT_LINE('Orders feature enabled');
    $ELSE
        DBMS_OUTPUT.PUT_LINE('Orders feature disabled');
    $END
END;
/
```

Lần compile này tạo artifact khác. Nếu môi trường có nhiều profile, lưu riêng source revision và settings của từng artifact.

## 14. Tác động tới dependency và deployment

### 14.1. Conditional compilation thay đổi nội dung object

Hai lần compile cùng source nhưng khác PLSQL_CCFLAGS có thể tạo implementation khác nhau. Điều này có thể ảnh hưởng:

- Hành vi procedure/function.
- Dependency vào object chỉ xuất hiện trong một nhánh.
- SQL statements được compile.
- Runtime performance và diagnostics.
- Package body size và metadata.

### 14.2. Compile flags không đồng bộ giữa các object

Nếu package A được compile với FEATURE_X=TRUE còn package B compile với FALSE, hai object có thể kỳ vọng contract khác nhau. Build pipeline cần áp dụng cùng profile cho toàn bộ nhóm object phụ thuộc.

### 14.3. Recompile dependent objects

Khi thay đổi package specification hoặc object dependency, Oracle có thể invalidated dependent objects. Conditional compilation không loại bỏ quy tắc dependency. Sau deploy, kiểm tra USER_OBJECTS, USER_ERRORS và compile lại theo thứ tự.

### 14.4. Tái tạo artifact

Không chỉ lưu source. Cần lưu database version, compiler parameters, flags và build script. Nếu thiếu flags, một lần compile lại trên môi trường khác có thể chọn nhánh khác dù source không đổi.

### 14.5. Rollback deployment

Nếu build mới có lỗi, rollback phải khôi phục source và compiler settings tương ứng. Chỉ chạy CREATE OR REPLACE với source cũ nhưng flags mới có thể tạo artifact khác với bản trước. Giữ manifest của artifact trước để có thể tái tạo.

## 15. Những lỗi và hiểu nhầm thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nhánh debug vẫn xuất hiện sau khi đổi flag | Object chưa được compile lại | Compile lại object sau khi đổi PLSQL_CCFLAGS |
| Flag có giá trị không như mong đợi | Build session không đặt flag hoặc đặt sai tên/giá trị | Kiểm tra compile script và USER_PLSQL_OBJECT_SETTINGS |
| Code dùng API mới vẫn không compile | Nhánh điều kiện chọn implementation không tương thích | Kiểm tra version/flag và compile environment |
| Warning không xuất hiện | PLSQL_WARNINGS đang disable hoặc compile bằng session khác | Bật warning trong đúng session build |
| Warning làm build thất bại | Category/mã warning được đặt ERROR | Xem policy và mã PLW cụ thể |
| Object VALID nhưng có warning | Warning không đồng nghĩa compile error | Xem USER_ERRORS và quyết định xử lý |
| Recompile dùng settings khác | Không dùng REUSE SETTINGS hoặc session defaults khác | Đặt settings tường minh và kiểm tra metadata |
| Build dev khác production | Flags/parameters/version khác nhau | Dùng build manifest và profile có kiểm soát |
| NLS length khác giữa môi trường | NLS_LENGTH_SEMANTICS khác | Khai báo CHAR/BYTE rõ và chuẩn hóa setting |
| Warning bị nuốt trong pipeline | Script chỉ kiểm tra exit status hoặc INVALID object | Đọc USER_ERRORS, fail theo warning policy |

## 16. Quy tắc thiết kế và vận hành

### 16.1. Giữ số lượng compile profile nhỏ

Mỗi profile làm tăng số artifact cần build, test và deploy. Chỉ tạo profile có mục đích rõ, ví dụ DEV, TEST, PROD hoặc một profile legacy được hỗ trợ.

### 16.2. Dùng flags có tên mô tả

Tên như DEBUG, FEATURE_ORDERS, API_LEVEL dễ hiểu hơn các cờ ngắn không có ngữ nghĩa. Ghi tài liệu giá trị hợp lệ và default.

### 16.3. Luôn đặt flag tường minh

Build script phải đặt toàn bộ flags cần thiết trước compile. Không dựa vào trạng thái session còn sót từ một bước build khác.

### 16.4. Bật warnings trong CI

CI nên compile với warning policy cố định, thu thập USER_ERRORS và fail khi gặp lỗi hoặc warning đã được policy nâng thành error. Đừng chỉ dựa vào trạng thái object VALID.

### 16.5. Chỉ nâng warning có chủ đích

ERROR:ALL có thể làm build thất bại vì các warning chưa được xử lý hoặc không phù hợp với code legacy. Có thể bắt đầu bằng ENABLE:ALL, phân loại warning, sửa hoặc ghi exception có thời hạn, rồi nâng các mã quan trọng thành ERROR.

### 16.6. Không tắt warning toàn hệ thống để xử lý một object

Dùng ALTER SESSION hoặc object-level compile option nếu chỉ cần thay đổi trong một build. ALTER SYSTEM chỉ dùng khi có quyết định quản trị chung.

### 16.7. Đo trước khi thay optimize/code type

Thay PLSQL_OPTIMIZE_LEVEL hoặc PLSQL_CODE_TYPE có thể ảnh hưởng compile time, runtime performance, debug và vận hành. Benchmark bằng workload đại diện và ghi settings theo artifact.

### 16.8. Conditional compilation không thay thế versioned API

Nếu các implementation khác nhau có contract rất khác nhau, cân nhắc package adapter hoặc module riêng. Đừng nhồi quá nhiều nhánh compile-time vào một package khó hiểu.

## 17. Bài thực hành

Thực hiện trong schema lab riêng, không thay compiler settings toàn hệ thống.

### Bước 1 — Compile profile cơ bản

Đặt PLSQL_CCFLAGS với DEBUG TRUE và FEATURE_ORDERS FALSE. Tạo procedure có hai nhánh conditional compilation. Compile và xem kết quả.

### Bước 2 — Đổi flag

Đổi DEBUG FALSE và FEATURE_ORDERS TRUE, compile lại procedure. So sánh output và USER_PLSQL_OBJECT_SETTINGS.

### Bước 3 — Inquiry directives

Tạo procedure in $$PLSQL_UNIT, $$PLSQL_LINE và PLSQL_OPTIMIZE_LEVEL qua $$PLSQL_COMPILATION_PARAMETER. Thay source để quan sát line number thay đổi.

### Bước 4 — Version branch

Tạo hai nhánh dựa trên DBMS_DB_VERSION hoặc một compile flag API_LEVEL. Compile trên database release hỗ trợ và ghi lại nhánh được chọn.

### Bước 5 — Thử $ERROR

Đặt API_LEVEL thấp hơn yêu cầu và dùng $ERROR để làm compile fail. Sau đó sửa flag và compile lại.

### Bước 6 — Bật compiler warnings

Đặt PLSQL_WARNINGS ENABLE:ALL. Tạo procedure có unreachable code và OTHERS handler không RAISE. Xem mã warning trong USER_ERRORS.

### Bước 7 — Nâng warning thành error

Chọn một warning cụ thể và đặt ERROR cho mã đó. Compile lại, quan sát trạng thái object và thông báo.

### Bước 8 — DBMS_WARNING

Đọc warning setting cũ, thay đổi trong scope SESSION, rồi khôi phục. Xác nhận setting cuối cùng giống ban đầu.

### Bước 9 — Compiler parameters

Compile một procedure với optimize level 2, sau đó thử level 3. Đo thời gian compile và runtime bằng workload ổn định. Không kết luận từ một lần chạy.

### Bước 10 — PLSCOPE

Bật IDENTIFIERS và STATEMENTS, compile một package. Xem USER_IDENTIFIERS/USER_STATEMENTS nếu release hỗ trợ.

### Bước 11 — REUSE SETTINGS

Compile object với flags/warnings đã chọn. Recompile bằng REUSE SETTINGS và xem lại USER_PLSQL_OBJECT_SETTINGS. So sánh với compile trong session có settings mới.

### Bước 12 — Build manifest

Tạo file manifest ghi database version, source revision, flags, warnings, optimize level, code type, PLSCOPE và NLS_LENGTH_SEMANTICS. Thực hiện lại build trên môi trường khác và so sánh.

## 18. Câu hỏi tự kiểm tra

1. Conditional compilation quyết định nhánh code ở thời điểm nào?
2. Conditional compilation khác IF runtime như thế nào?
3. Cú pháp $IF, $ELSIF, $ELSE và $END hoạt động ra sao?
4. PLSQL_CCFLAGS được dùng để làm gì?
5. Flag compile-time được tham chiếu trong source bằng cú pháp nào?
6. Vì sao phải đặt flags tường minh trong build pipeline?
7. $$PLSQL_UNIT và $$PLSQL_LINE cung cấp thông tin gì?
8. $$PLSQL_COMPILATION_PARAMETER dùng để làm gì?
9. Khi nào nên dùng DBMS_DB_VERSION trong conditional compilation?
10. $ERROR giúp kiểm soát build như thế nào?
11. Compiler warning khác compile error ở điểm nào?
12. Các category SEVERE, PERFORMANCE và INFORMATIONAL có ý nghĩa gì?
13. PLSQL_WARNINGS có thể nâng warning thành error ra sao?
14. USER_ERRORS lưu warning/error ở những cột nào?
15. Vì sao object VALID vẫn có thể có warning?
16. DBMS_WARNING hỗ trợ những scope nào?
17. PLSQL_OPTIMIZE_LEVEL ảnh hưởng quá trình compile ra sao?
18. PLSQL_CODE_TYPE INTERPRETED khác NATIVE như thế nào?
19. PLSCOPE_SETTINGS thu thập metadata phục vụ công việc gì?
20. NLS_LENGTH_SEMANTICS có thể ảnh hưởng source được compile thế nào?
21. ALTER SESSION khác ALTER SYSTEM ở phạm vi tác động nào?
22. REUSE SETTINGS có ích gì khi recompile?
23. USER_PLSQL_OBJECT_SETTINGS giúp xác minh điều gì?
24. Vì sao cần compile/test mọi profile có conditional branch?
25. Vì sao conditional compilation không được dùng làm cơ chế authorization?

**Nguyên tắc cần nhớ:** conditional compilation chọn mã khi compile; PLSQL_WARNINGS kiểm soát cảnh báo và có thể nâng warning thành compile error; compiler parameters quyết định cách PL/SQL được tối ưu, tạo code và thu thập metadata. Hãy đặt PLSQL_CCFLAGS cùng các compiler settings tường minh trong build pipeline, compile lại khi đổi flags, đọc USER_ERRORS và USER_PLSQL_OBJECT_SETTINGS để xác nhận kết quả. Giữ số profile nhỏ, kiểm thử từng profile và lưu build manifest để có thể tái tạo chính xác artifact đã triển khai.

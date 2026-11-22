# Kiểm thử package, function và procedure bằng utPLSQL hoặc JDBC

Oracle PL/SQL thường chứa phần lớn logic chạy gần dữ liệu: package, function, procedure, trigger và các routine phục vụ nghiệp vụ. Khi Java/Spring Boot gọi các routine này qua JDBC hoặc JPA, chất lượng hệ thống phụ thuộc cả vào logic PL/SQL lẫn hợp đồng giữa database và ứng dụng. Một routine có thể chạy đúng khi DBA gọi trong SQL Developer nhưng vẫn lỗi khi được gọi từ Java do kiểu tham số, quyền thực thi, transaction boundary, session state hoặc cách driver ánh xạ kết quả.

Có hai hướng kiểm thử bổ sung cho nhau:

- **utPLSQL** chạy test ngay trong Oracle Database. Nó phù hợp để kiểm tra logic PL/SQL, dữ liệu, exception, package API và các quy tắc cần database thực thi.
- **JDBC/JUnit** chạy ở phía Java, gọi package/function/procedure bằng JDBC driver thật. Nó phù hợp để xác nhận contract giữa ứng dụng và database: bind parameter, IN/OUT, REF CURSOR, kiểu dữ liệu, transaction, quyền và cách xử lý lỗi.

Không nên chỉ chọn một hướng rồi bỏ hướng còn lại nếu PL/SQL là một phần quan trọng của ứng dụng. utPLSQL kiểm tra logic gần database; JDBC integration test xác nhận đường đi thật từ Java tới Oracle. Test cần có dữ liệu độc lập, kết quả có thể lặp lại và quy tắc cleanup rõ ràng.

## 1. Mục tiêu và phạm vi kiểm thử PL/SQL

Một package thường gom các procedure và function có liên quan vào một API. Public specification định nghĩa tên routine, kiểu tham số, kiểu trả về và exception có thể phát sinh; package body triển khai logic. Khi kiểm thử, nên tập trung vào hành vi công khai mà ứng dụng hoặc package khác sử dụng.

Ví dụ package quản lý đơn hàng:

    CREATE OR REPLACE PACKAGE order_api AS
      PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_amount      IN NUMBER,
        p_order_id    OUT NUMBER
      );

      FUNCTION calculate_total(
        p_order_id IN NUMBER
      ) RETURN NUMBER;

      PROCEDURE approve_order(
        p_order_id IN NUMBER,
        p_actor    IN VARCHAR2
      );
    END order_api;
    /

Các test cần xác minh:

- Routine nhận input hợp lệ và trả kết quả đúng.
- Input không hợp lệ bị từ chối theo contract đã định nghĩa.
- Function trả đúng giá trị, bao gồm NULL và biên số học nếu được phép.
- Procedure thay đổi đúng các hàng và chỉ các hàng dự kiến.
- OUT parameter, return value và REF CURSOR có kiểu, thứ tự và nội dung đúng.
- Transaction không commit hoặc rollback ngoài ý muốn.
- Exception nghiệp vụ được phát ra với mã và thông điệp ổn định.
- Quyền EXECUTE, quyền trên object phụ thuộc và schema resolution đúng.
- Kết quả không phụ thuộc dữ liệu test trước, NLS, timezone hoặc session state còn sót.
- Java client có thể gọi routine với đúng cách bind và đọc kết quả.

### 1.1. Phân biệt unit test và integration test

Unit test kiểm tra một đơn vị logic trong phạm vi có kiểm soát. Với PL/SQL, đơn vị có thể là function, procedure hoặc public API của package. Tuy nhiên, PL/SQL thường truy cập table, sequence, view và package khác; test chạy trong Oracle thật có thể được xem là database unit test nhưng vẫn sử dụng database engine.

Integration test kiểm tra nhiều thành phần cùng hoạt động, ví dụ:

- Package gọi các package khác và truy vấn nhiều bảng.
- Trigger, constraint và foreign key cùng tham gia transaction.
- Java gọi procedure qua Oracle JDBC.
- Spring transaction manager phối hợp với JDBC connection.
- OUT parameter hoặc cursor được chuyển thành DTO.
- Quyền của application user khác quyền owner package.

Một bộ test tốt tách test nhanh và tập trung khỏi test tích hợp rộng. Khi test thất bại, nhóm phát triển phải biết lỗi nằm trong logic PL/SQL, schema fixture, quyền, driver hay cách gọi từ Java.

### 1.2. Kiểm thử theo hợp đồng công khai

Không nên phụ thuộc vào package private helper hoặc chi tiết triển khai nội bộ nếu chúng không phải API. Hãy gọi public procedure/function và quan sát:

- Giá trị trả về.
- OUT/IN OUT parameter.
- Hàng dữ liệu được tạo, cập nhật hoặc xóa.
- Exception và error code.
- Side effect được tài liệu hóa.
- Tính nhất quán sau commit/rollback.

Private procedure trong package body thường được kiểm tra gián tiếp qua public API. Điều này cho phép refactor implementation mà không phải viết lại toàn bộ test chỉ vì tên helper thay đổi.

## 2. utPLSQL là gì?

utPLSQL là framework kiểm thử mã PL/SQL chạy trong Oracle Database. Test được viết bằng package PL/SQL riêng, có thể khai báo suite, test case, hook setup/teardown và assertion. Runner thực thi suite rồi trả kết quả chi tiết về test thành công, thất bại hoặc lỗi.

Một cấu trúc phổ biến:

    Application schema
      +-- ORDER_API package
      +-- ORDER_TABLE
      +-- CUSTOMER_TABLE

    Test schema
      +-- TEST_ORDER_API package
      +-- utPLSQL framework objects

    utPLSQL runner
      +-- discovers suite annotations
      +-- runs setup and test procedures
      +-- evaluates expectations
      +-- reports results

Framework nên được cài theo hướng dẫn của phiên bản utPLSQL tương thích với Oracle Database. Tùy chính sách tổ chức, framework có thể nằm trong schema riêng hoặc được cài theo mô hình được DBA phê duyệt. Không tự cài framework vào production schema chỉ để chạy test.

### 2.1. Vì sao kiểm thử ngay trong database?

utPLSQL có thể kiểm tra dữ liệu và hành vi trực tiếp trong cùng database engine mà package chạy. Nó giảm phần code harness cần viết và hỗ trợ test PL/SQL mà không phải dựng một Java application cho từng assertion.

Các lợi ích thường gặp:

- Test có thể gọi package, function và procedure trực tiếp.
- Assertion có thể so sánh scalar, collection và kết quả truy vấn.
- Setup/teardown được tổ chức thành hook.
- Suite có thể được chọn chạy riêng hoặc theo package/path.
- Test có thể chạy từ SQL*Plus, SQLcl, SQL Developer hoặc CI runner phù hợp.
- Kết quả có cấu trúc để tích hợp vào pipeline kiểm thử.

utPLSQL không thay thế kiểm thử từ Java. Nó không chứng minh rằng Oracle JDBC driver bind đúng kiểu, Spring transaction hoạt động như mong muốn hoặc application user có đủ quyền.

### 2.2. Cài đặt và phân quyền

Cài đặt utPLSQL là công việc quản trị database. Cần xác định:

- Phiên bản Oracle Database và các tính năng được hỗ trợ.
- Phiên bản utPLSQL framework.
- Schema owner của framework.
- Schema chứa test package.
- Quyền execute runner và quyền truy cập package được test.
- Cách chạy suite trong local, CI và môi trường tích hợp.
- Cách nâng cấp hoặc gỡ framework theo quy trình quản trị.

Test user chỉ nên có quyền cần thiết để chạy suite và truy cập fixture. Tránh cấp DBA cho tài khoản test. Nếu test cần truy cập object ở schema khác, cấp quyền trực tiếp hoặc qua cơ chế được framework/database hỗ trợ và kiểm tra quyền thực tế trong execution context.

## 3. Viết suite utPLSQL đầu tiên

utPLSQL nhận diện suite thông qua annotation đặt trong comment của package specification. Các annotation thông dụng gồm:

- --%suite: đánh dấu package là test suite.
- --%suitepath: nhóm suite trong cây tổ chức.
- --%test: đánh dấu procedure là một test case.
- --%beforeall / --%afterall: hook chạy trước/sau toàn bộ suite.
- --%beforeeach / --%aftereach: hook chạy trước/sau từng test.
- --%context: nhóm test theo ngữ cảnh.
- --%rollback(auto) hoặc --%rollback(manual): khai báo cách xử lý rollback theo khả năng của phiên bản/framework.

Ví dụ suite kiểm tra function cộng số:

    CREATE OR REPLACE PACKAGE test_math_api AS
      --%suite(Math API)
      --%suitepath(Database.Unit)

      --%test(Adds two positive numbers)
      PROCEDURE adds_positive_numbers;

      --%test(Handles zero)
      PROCEDURE handles_zero;
    END test_math_api;
    /

Package body:

    CREATE OR REPLACE PACKAGE BODY test_math_api AS

      PROCEDURE adds_positive_numbers IS
        l_actual NUMBER;
      BEGIN
        l_actual := math_api.add_numbers(2, 3);

        ut.expect(l_actual).to_equal(5);
      END adds_positive_numbers;

      PROCEDURE handles_zero IS
        l_actual NUMBER;
      BEGIN
        l_actual := math_api.add_numbers(0, 8);

        ut.expect(l_actual).to_equal(8);
      END handles_zero;

    END test_math_api;
    /

Chạy suite bằng runner:

    BEGIN
      ut.run('TEST_SCHEMA.TEST_MATH_API');
    END;
    /

Tên schema và package phải thay bằng môi trường thực tế. Cú pháp chọn suite, output reporter và cách truyền tham số runner có thể khác theo phiên bản utPLSQL.

### 3.1. Tổ chức suite theo package nghiệp vụ

Một package test thường tương ứng với một package ứng dụng hoặc một nhóm hành vi liên quan. Ví dụ:

    TEST_ORDER_API
      +-- create_order
      +-- calculate_total
      +-- approve_order
      +-- rejects_unknown_customer
      +-- rejects_negative_amount

Tên test nên mô tả hành vi, không chỉ lặp tên routine. Khi test fail, log cần giúp người đọc hiểu điều kiện nào đã không được đáp ứng.

### 3.2. Một test case nên kiểm tra một hành vi chính

Ví dụ test create_order không nên đồng thời kiểm tra tính thuế, gửi email, cập nhật tồn kho và tạo báo cáo nếu đó là các hành vi có thể kiểm tra độc lập. Test nhỏ làm nguyên nhân thất bại dễ nhận diện và giảm chi phí sửa.

Có thể dùng một test để kiểm tra nhiều assertion khi chúng cùng mô tả một contract, chẳng hạn procedure tạo order phải trả OUT ID và tạo đúng một hàng với customer/amount tương ứng. Tránh nhồi nhiều tình huống không liên quan vào cùng test.

## 4. Assertion và expectation trong utPLSQL

utPLSQL sử dụng API ut.expect để biểu đạt kỳ vọng. Một số matcher phổ biến:

    ut.expect(l_actual).to_equal(l_expected);
    ut.expect(l_actual).to_be_null();
    ut.expect(l_actual).not_to_be_null();
    ut.expect(l_actual).to_be_true();
    ut.expect(l_actual).to_be_false();
    ut.expect(l_actual).to_be_greater_than(0);

Tên matcher và overload cụ thể cần đối chiếu tài liệu của phiên bản utPLSQL đang cài. Ví dụ trên thể hiện cách dùng phổ biến; không giả định mọi kiểu PL/SQL hoặc custom type đều có matcher mặc định.

### 4.1. Kiểm tra function trả scalar

Giả sử function:

    FUNCTION calculate_discount(
      p_amount IN NUMBER,
      p_rate   IN NUMBER
    ) RETURN NUMBER;

Test:

    PROCEDURE calculates_discount IS
      l_actual NUMBER;
    BEGIN
      l_actual := pricing_api.calculate_discount(100, 0.10);

      ut.expect(l_actual).to_equal(10);
    END;

Nên kiểm tra cả input biên:

- Amount bằng 0.
- Rate bằng 0.
- Rate ở mức tối đa cho phép.
- Giá trị NULL nếu contract cho phép.
- Giá trị âm nếu routine phải từ chối.
- Precision/rounding theo quy tắc tiền tệ.

Với số thập phân tài chính, không kiểm thử bằng so sánh floating point tùy tiện. Oracle NUMBER và Java BigDecimal phù hợp hơn cho giá trị decimal cần chính xác. Xác định rõ scale, rounding mode và currency rule.

### 4.2. Kiểm tra procedure thay đổi dữ liệu

Giả sử procedure:

    PROCEDURE set_order_status(
      p_order_id IN NUMBER,
      p_status   IN VARCHAR2
    );

Test có thể chuẩn bị một order, gọi procedure và truy vấn lại:

    PROCEDURE changes_order_status IS
      l_status order_header.status%TYPE;
    BEGIN
      INSERT INTO order_header(order_id, status)
      VALUES (900001, 'NEW');

      order_api.set_order_status(900001, 'APPROVED');

      SELECT status
      INTO l_status
      FROM order_header
      WHERE order_id = 900001;

      ut.expect(l_status).to_equal('APPROVED');
    END;

Fixture phải dùng khóa riêng, không đụng dữ liệu dùng chung. Nếu framework rollback tự động, không commit trong test. Nếu package tự commit, phải dùng database/schema test riêng hoặc chiến lược cleanup có kiểm soát.

### 4.3. Kiểm tra nhiều điều kiện

Có thể kiểm tra OUT parameter, row count và các giá trị của hàng:

    PROCEDURE creates_order_with_expected_values IS
      l_order_id NUMBER;
      l_customer_id NUMBER;
      l_amount NUMBER;
      l_status VARCHAR2(30);
    BEGIN
      order_api.create_order(
        p_customer_id => 7001,
        p_amount      => 125.50,
        p_order_id    => l_order_id
      );

      SELECT customer_id, amount, status
      INTO l_customer_id, l_amount, l_status
      FROM order_header
      WHERE order_id = l_order_id;

      ut.expect(l_order_id).not_to_be_null();
      ut.expect(l_customer_id).to_equal(7001);
      ut.expect(l_amount).to_equal(125.50);
      ut.expect(l_status).to_equal('NEW');
    END;

Nếu thứ tự assertion có ý nghĩa chẩn đoán, chia test theo hành vi hoặc dùng các expectation có thông điệp mô tả. Đừng kiểm tra duy nhất OUT ID rồi suy luận rằng toàn bộ dữ liệu đã được tạo đúng.

### 4.4. Kiểm tra collection và query result

Khi routine trả collection hoặc ref cursor, test cần xác nhận cả số phần tử và nội dung. Có thể đưa kết quả về một tập giá trị có thứ tự xác định rồi so sánh. Nếu không có ORDER BY, thứ tự hàng trong SQL không được bảo đảm; test không nên phụ thuộc thứ tự ngẫu nhiên.

Với query result, cân nhắc matcher/table comparison hoặc helper của utPLSQL được phiên bản hỗ trợ. Khi chỉ cần kiểm tra một điều kiện, truy vấn COUNT, EXISTS hoặc aggregate có thể làm test rõ ràng hơn.

## 5. Fixture: chuẩn bị và dọn dữ liệu test

Fixture là dữ liệu và trạng thái cần thiết để một test chạy độc lập. Fixture tốt phải xác định được, nhỏ, có thể tạo lại và không phụ thuộc thứ tự test.

Ví dụ một order test cần:

- Customer có trạng thái hoạt động.
- Order chưa tồn tại.
- Product có giá đã biết.
- Inventory đủ số lượng.
- Currency/rate phù hợp nếu package tính tiền.
- Các sequence, trigger và constraint liên quan ở trạng thái bình thường.

Không nên dùng một customer production hoặc ID ngẫu nhiên lấy từ database dùng chung. Mỗi test phải biết chính xác dữ liệu nào thuộc về nó.

### 5.1. Hook beforeeach và aftereach

Có thể dùng hook để tạo và dọn fixture cho từng test:

    CREATE OR REPLACE PACKAGE test_order_api AS
      --%suite(Order API)

      --%beforeeach
      PROCEDURE setup;

      --%aftereach
      PROCEDURE cleanup;

      --%test(Creates a new order)
      PROCEDURE creates_order;
    END test_order_api;
    /

Package body:

    CREATE OR REPLACE PACKAGE BODY test_order_api AS

      PROCEDURE setup IS
      BEGIN
        INSERT INTO customer(customer_id, customer_name, active_flag)
        VALUES (7001, 'UTPLSQL CUSTOMER', 'Y');
      END;

      PROCEDURE cleanup IS
      BEGIN
        DELETE FROM order_line WHERE order_id IN (
          SELECT order_id
          FROM order_header
          WHERE customer_id = 7001
        );

        DELETE FROM order_header
        WHERE customer_id = 7001;

        DELETE FROM customer
        WHERE customer_id = 7001;
      END;

      PROCEDURE creates_order IS
        l_order_id NUMBER;
      BEGIN
        order_api.create_order(7001, 125.50, l_order_id);
        ut.expect(l_order_id).not_to_be_null();
      END;

    END test_order_api;
    /

Đây là cấu trúc minh họa. Nếu test runner rollback tự động, cleanup có thể không cần xóa những thay đổi transactional; nếu dùng manual rollback hoặc test routine commit, cleanup phải được thiết kế riêng. Dữ liệu fixture cần tránh va chạm với các lần chạy song song.

### 5.2. beforeall và afterall

beforeall chạy một lần trước suite; afterall chạy một lần sau suite. Dùng cho trạng thái dùng chung có vòng đời rõ ràng, chẳng hạn tạo dữ liệu tham chiếu cố định trong transaction test hoặc khởi tạo package context.

Không dùng beforeall để tạo một fixture mutable mà nhiều test cùng sửa, trừ khi mỗi test reset trạng thái. Test phụ thuộc vào thứ tự chạy rất dễ fail khi runner thực thi suite khác thứ tự hoặc chạy song song.

### 5.3. Rollback tự động và manual

Trong utPLSQL, annotation rollback cho phép chọn cách runner xử lý transaction của test theo khả năng framework. Chế độ auto thường giúp rollback các thay đổi transactional sau test để dữ liệu không rò sang test kế tiếp. Chế độ manual dành cho test cần tự điều khiển transaction/cleanup.

Cần hiểu rõ:

- DML transactional có thể được rollback nếu không commit.
- COMMIT bên trong package làm thay đổi transaction boundary và có thể khiến dữ liệu tồn tại sau test.
- DDL thường có implicit commit; không tạo/drop table trong test thông thường.
- Autonomous transaction không bị rollback cùng transaction caller.
- Sequence NEXTVAL không được hoàn lại khi rollback.
- Gửi email, gọi HTTP, enqueue hoặc ghi file là side effect ngoài transaction và không tự biến mất khi rollback.
- Global temporary table có semantics theo transaction hoặc session tùy cấu hình; session pooling có thể giữ trạng thái nếu không dọn đúng.

Không viết test giả định rollback sẽ đảo ngược mọi side effect. Với routine tự commit hoặc gọi hệ thống ngoài, cần schema/database dùng riêng, mock/stub dependency phù hợp hoặc cleanup có chủ đích.

### 5.4. Không phụ thuộc sequence value chính xác

Sequence Oracle có thể tạo gap do cache, rollback, concurrency hoặc instance restart. Test không nên kỳ vọng ID kế tiếp luôn bằng một số cố định. Hãy kiểm tra ID khác NULL, tồn tại trong bảng và liên kết đúng với các hàng con.

## 6. Kiểm tra exception và lỗi nghiệp vụ bằng utPLSQL

Một routine thường phải từ chối input sai bằng exception có contract rõ ràng. Ví dụ:

- Customer không tồn tại.
- Order đã bị hủy.
- Amount âm.
- Trạng thái không cho phép chuyển.
- Người gọi không có quyền thực hiện.
- Resource bị khóa hoặc dữ liệu cạnh tranh thay đổi.

Test phải xác minh routine từ chối đúng trường hợp và không để lại dữ liệu nửa chừng.

Ví dụ package phát sinh lỗi nghiệp vụ:

    PROCEDURE approve_order(p_order_id IN NUMBER) IS
      l_status order_header.status%TYPE;
    BEGIN
      SELECT status
      INTO l_status
      FROM order_header
      WHERE order_id = p_order_id
      FOR UPDATE;

      IF l_status <> 'NEW' THEN
        RAISE_APPLICATION_ERROR(
          -20041,
          'Only NEW orders can be approved'
        );
      END IF;

      UPDATE order_header
      SET status = 'APPROVED'
      WHERE order_id = p_order_id;
    END;

Test lỗi trạng thái cần xác nhận procedure thực sự phát sinh lỗi nghiệp vụ và mã lỗi đúng. Có thể dùng exception expectation/helper mà phiên bản utPLSQL đang cài cung cấp. Một cách PL/SQL thuần, dễ đọc và không phụ thuộc matcher exception, là bắt exception rồi assert SQLCODE:

    PROCEDURE rejects_approved_order IS
      l_error_code NUMBER;
    BEGIN
      INSERT INTO order_header(order_id, status)
      VALUES (900002, 'APPROVED');

      BEGIN
        order_api.approve_order(900002);
      EXCEPTION
        WHEN OTHERS THEN
          l_error_code := SQLCODE;
      END;

      ut.expect(l_error_code).to_equal(-20041);
    END;

Nếu routine không phát sinh lỗi, l_error_code vẫn NULL và test fail. Nếu muốn kiểm tra message, đọc SQLERRM trong exception handler và so sánh nội dung ổn định. Tránh phụ thuộc toàn bộ error text nếu nó chứa thông tin thay đổi theo ngôn ngữ hoặc phiên bản.

### 6.1. Không nuốt exception ngoài ý muốn

Mẫu sau không tốt:

    BEGIN
      order_api.approve_order(p_order_id);
    EXCEPTION
      WHEN OTHERS THEN
        NULL;
    END;

Nếu exception bị nuốt, caller không thể biết thao tác thất bại và test có thể báo thành công giả. Chỉ bắt exception khi có hành động cụ thể: chuyển thành lỗi nghiệp vụ, bổ sung context rồi raise lại, rollback phần phù hợp hoặc ghi nhận lỗi theo chính sách.

Trong test, luôn phân biệt “đã nhận đúng exception” với “routine không ném exception”. Đừng chỉ kiểm tra rằng test procedure chạy tới cuối.

## 7. Kiểm tra function có side effect và tính xác định

Function thường được dùng trong biểu thức SQL, vì vậy thiết kế function nên ưu tiên tính toán và trả giá trị. Function có DML hoặc side effect phức tạp có thể bị hạn chế khi gọi từ SQL và gây khó dự đoán.

Khi test function:

- Kiểm tra input bình thường, biên và NULL.
- Xác minh precision/rounding.
- Kiểm tra function deterministic chỉ khi contract thực sự bảo đảm cùng input cho cùng output.
- Không giả định function được gọi đúng một lần trong SQL expression; optimizer có thể thay đổi cách thực thi.
- Kiểm tra exception khi dữ liệu đầu vào không hợp lệ.
- Nếu function đọc bảng, chuẩn bị dữ liệu fixture độc lập.

Ví dụ:

    FUNCTION calculate_tax(
      p_net_amount IN NUMBER,
      p_rate       IN NUMBER
    ) RETURN NUMBER;

Test có thể kiểm tra amount 100, rate 0.08 cho kết quả 8; amount 0 cho 0; rate NULL theo contract; và số âm bị từ chối nếu nghiệp vụ cấm.

Không dùng hàm random hoặc SYSDATE trực tiếp trong test mà không kiểm soát. Với logic phụ thuộc thời gian, truyền mốc thời gian vào routine hoặc dùng một abstraction/test seam để test được boundary như ngày cuối tháng, timezone và thời hạn hết hiệu lực.

## 8. Kiểm tra package state và session state

Package PL/SQL có thể chứa biến global, constant, cursor hoặc trạng thái khởi tạo trong package initialization section. Trạng thái package thường tồn tại trong session sau lần gọi đầu tiên.

Nếu connection pool tái sử dụng session, request sau có thể thấy package state do request trước thay đổi. Test chạy trên một session đơn có thể không phát hiện vấn đề này.

Các trường hợp cần kiểm tra:

- Procedure thay đổi package global variable.
- Package cache dữ liệu theo session.
- Package initialization đọc NLS hoặc timezone.
- DBMS_SESSION.SET_CONTEXT tạo application context.
- DBMS_APPLICATION_INFO đặt MODULE/ACTION.
- Temporary table dùng ON COMMIT PRESERVE ROWS.
- Package bị invalidated hoặc recompiled trong lúc session còn giữ state.

utPLSQL test có thể chạy nhiều test trong cùng session hoặc runner quản lý session theo cách riêng. Hãy kiểm tra hành vi package state và reset state rõ ràng nếu package được thiết kế stateful. Đừng dựa vào việc mở connection mới ở mỗi test trừ khi runner thực sự làm vậy.

Nếu package cần stateless behavior cho application pool, thiết kế API để truyền state qua tham số và dọn context trong finally/transaction boundary. Test integration qua pool để kiểm tra session reuse.

## 9. Test procedure/function từ Java bằng JDBC

JDBC integration test xác nhận cách ứng dụng Java thực sự gọi PL/SQL. Dùng Oracle JDBC driver tương thích với JDK/database và kết nối tới database test riêng.

Một test Java nên xác nhận:

- CallableStatement gọi đúng package/routine.
- IN parameter bind đúng kiểu và thứ tự.
- OUT parameter được register với JDBC type phù hợp.
- Function return value được đăng ký đúng vị trí.
- REF CURSOR được đọc và đóng đúng cách.
- SQLException được ánh xạ đúng.
- Transaction commit/rollback đúng ý đồ.
- Kết quả database sau khi gọi đúng như contract.

### 9.1. JUnit 5 và DataSource

Ví dụ cấu trúc test:

    @SpringBootTest
    class OrderApiJdbcTest {

        @Autowired
        DataSource dataSource;

        @Test
        void createsOrderAndReturnsId() throws Exception {
            try (Connection connection = dataSource.getConnection()) {
                // call the package procedure
            }
        }
    }

Có thể dùng Spring Boot context để lấy DataSource và cấu hình giống ứng dụng. Với test đơn giản hơn, có thể tạo DataSource test trực tiếp. Dù chọn cách nào, test phải chạy với Oracle thật hoặc môi trường Oracle tương thích, không chỉ H2 giả lập nếu đang xác nhận Oracle PL/SQL, package, type hoặc driver behavior.

### 9.2. Gọi procedure có IN và OUT parameter

Giả sử:

    PROCEDURE create_order(
      p_customer_id IN NUMBER,
      p_amount      IN NUMBER,
      p_order_id    OUT NUMBER
    );

Java JDBC:

    String call = "{ call order_api.create_order(?, ?, ?) }";

    try (Connection connection = dataSource.getConnection();
         CallableStatement statement =
             connection.prepareCall(call)) {

        statement.setLong(1, 7001L);
        statement.setBigDecimal(2, new BigDecimal("125.50"));
        statement.registerOutParameter(3, Types.NUMERIC);

        statement.execute();

        BigDecimal orderId = statement.getBigDecimal(3);
        assertNotNull(orderId);
    }

Dùng BigDecimal cho Oracle NUMBER khi cần độ chính xác decimal, đặc biệt tiền tệ. setLong phù hợp với số nguyên nằm trong miền long; nếu NUMBER có precision lớn hơn, dùng BigDecimal.

Thứ tự tham số trong CallableStatement phải khớp với signature routine. Nếu package API thay đổi thứ tự hoặc kiểu tham số, test sẽ phát hiện sớm.

### 9.3. Gọi function trả scalar

Function có return value cần đăng ký tham số return ở vị trí đầu tiên trong escape call:

    FUNCTION calculate_total(p_order_id IN NUMBER)
      RETURN NUMBER;

Java:

    String call = "{ ? = call order_api.calculate_total(?) }";

    try (Connection connection = dataSource.getConnection();
         CallableStatement statement =
             connection.prepareCall(call)) {

        statement.registerOutParameter(1, Types.NUMERIC);
        statement.setLong(2, 900001L);

        statement.execute();

        BigDecimal total = statement.getBigDecimal(1);
        assertEquals(new BigDecimal("125.50"), total);
    }

Có thể dùng PL/SQL block thay cho escape syntax khi cần kiểm soát rõ:

    BEGIN
      ? := order_api.calculate_total(?);
    END;

Cú pháp escape function call thường dễ đọc cho scalar return. Kiểm tra Oracle JDBC driver version và cách driver xử lý kiểu trả về thực tế.

### 9.4. Procedure với IN OUT parameter

IN OUT parameter vừa nhận giá trị đầu vào vừa trả giá trị sau khi thực thi. JDBC cần register output và bind input ở cùng vị trí:

    String call = "{ call account_api.normalize_code(?) }";

    try (CallableStatement statement =
             connection.prepareCall(call)) {

        statement.setString(1, " ab-100 ");
        statement.registerOutParameter(1, Types.VARCHAR);
        statement.execute();

        String normalized = statement.getString(1);
        assertEquals("AB-100", normalized);
    }

Thứ tự set và register có thể được driver hỗ trợ; dùng cách nhất quán đã được kiểm thử. Đọc OUT sau execute, không đọc trước khi statement thực thi.

### 9.5. Gọi PL/SQL block trực tiếp

Với signature phức tạp hoặc routine cần block PL/SQL, dùng:

    String plsql = """
        BEGIN
          order_api.approve_order(?);
        END;
        """;

    try (CallableStatement statement =
             connection.prepareCall(plsql)) {

        statement.setLong(1, 900001L);
        statement.execute();
    }

Text block yêu cầu Java 15 trở lên. Với Java thấp hơn, dùng chuỗi nối hoặc một string literal nhiều dòng theo khả năng ngôn ngữ. Không ghép giá trị input trực tiếp vào PL/SQL text; bind bằng dấu hỏi.

## 10. Đọc REF CURSOR từ JDBC

Procedure có thể trả SYS_REFCURSOR để cung cấp tập kết quả. Oracle JDBC hỗ trợ REF CURSOR thông qua kiểu OracleTypes.CURSOR hoặc JDBC REF_CURSOR tùy phiên bản driver/JDBC API.

Ví dụ package:

    PROCEDURE list_orders(
      p_customer_id IN NUMBER,
      p_result      OUT SYS_REFCURSOR
    );

Ví dụ Java với Oracle JDBC type:

    try (Connection connection = dataSource.getConnection();
         CallableStatement statement =
             connection.prepareCall(
                 "{ call order_api.list_orders(?, ?) }")) {

        statement.setLong(1, 7001L);
        statement.registerOutParameter(2, OracleTypes.CURSOR);
        statement.execute();

        try (ResultSet rs = (ResultSet) statement.getObject(2)) {
            while (rs.next()) {
                long orderId = rs.getLong("ORDER_ID");
                String status = rs.getString("STATUS");
            }
        }
    }

OracleTypes.CURSOR nằm trong Oracle JDBC API; cần import đúng package theo driver version. Nếu dùng Types.REF_CURSOR, xác nhận driver hỗ trợ. Luôn đóng ResultSet, CallableStatement và Connection bằng try-with-resources.

Không đọc cursor sau khi connection đã được trả về pool. ResultSet phụ thuộc statement/connection còn mở. Nếu cần trả dữ liệu ra tầng service, map thành DTO hoặc collection trước khi đóng resource.

## 11. Test transaction và rollback từ JDBC

JDBC test phải xác định rõ ai sở hữu transaction. Nếu test tự quản lý connection, có thể tắt auto-commit, gọi procedure, kiểm tra dữ liệu trong cùng connection rồi rollback.

Ví dụ:

    @Test
    void rollsBackOrderCreation() throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                callCreateOrder(connection, 7001L,
                    new BigDecimal("125.50"));

                int count = countOrdersForCustomer(connection, 7001L);
                assertEquals(1, count);
            } finally {
                connection.rollback();
            }
        }
    }

Đây là ví dụ cho procedure không tự COMMIT và thao tác được thực hiện trong transaction caller. Nếu procedure tự commit, rollback của Java không thể đảo ngược phần đã commit.

Trong Spring Boot, test có thể dùng @Transactional để rollback sau mỗi test khi transaction manager và test execution cùng quản lý transaction. Nhưng cần hiểu rõ:

- Một procedure chạy COMMIT có thể kết thúc transaction của session.
- Autonomous transaction không nằm trong transaction caller.
- Dữ liệu do một connection khác tạo ra có transaction riêng.
- HTTP call tới service khác không nằm trong local transaction.
- DDL có implicit commit trong Oracle.
- Test có thể nhìn thấy dữ liệu khác nhau tùy connection/session.

Không giả định @Transactional của test luôn dọn sạch mọi dữ liệu do PL/SQL tạo. Kiểm tra package body và transaction contract trước khi dựa vào rollback tự động.

### 11.1. Không để test phụ thuộc commit ngoài ý muốn

Nếu procedure nghiệp vụ bắt buộc commit nội bộ, hãy cân nhắc thiết kế lại transaction ownership hoặc chạy integration test trên schema/database có thể reset. Một routine dùng cho transaction của application thường nên để caller quản lý commit/rollback, trừ khi contract yêu cầu rõ ràng khác.

Nếu không thể thay package, cleanup phải xử lý dữ liệu đã commit theo khóa riêng. Không dùng bảng production hoặc dữ liệu chia sẻ để thử routine có commit.

### 11.2. Spring @Transactional test

Ví dụ:

    @SpringBootTest
    @Transactional
    class OrderServiceIntegrationTest {

        @Autowired
        OrderService service;

        @Test
        void createsOrder() {
            Long id = service.createOrder(
                new OrderRequest(7001L, new BigDecimal("125.50"))
            );

            assertNotNull(id);
        }
    }

Spring test transaction thường rollback sau test nếu không được commit thủ công. Tuy nhiên, nếu package commit hoặc chạy autonomous transaction, dữ liệu đó có thể tồn tại. Với test cần kiểm tra commit visibility từ connection khác, cần thiết kế test transaction riêng và cleanup rõ ràng.

## 12. Kiểm thử exception từ JDBC

Oracle JDBC thường ném SQLException khi PL/SQL raise exception. Với RAISE_APPLICATION_ERROR, mã lỗi ứng dụng thường nằm trong SQLException.getErrorCode() dưới dạng mã Oracle tương ứng, thường là số dương của mã âm -20xxx; cần xác nhận trên driver đang dùng.

Ví dụ:

    @Test
    void rejectsApprovalForClosedOrder() throws Exception {
        try (Connection connection = dataSource.getConnection();
             CallableStatement statement =
                 connection.prepareCall(
                     "{ call order_api.approve_order(?) }")) {

            statement.setLong(1, 900003L);

            SQLException error =
                assertThrows(SQLException.class, statement::execute);

            assertEquals(20041, error.getErrorCode());
        }
    }

Không so sánh message đầy đủ nếu message phụ thuộc NLS hoặc Oracle version. Ưu tiên error code và một phần contract message ổn định nếu cần.

Nếu application layer chuyển SQLException thành domain exception, viết thêm test service để xác nhận mapping đó. Ví dụ ORA-20041 có thể trở thành OrderStateConflictException; client REST nhận HTTP 409 theo API contract. Tách test database error và test mapping HTTP giúp tìm lỗi nhanh hơn.

## 13. Kiểm tra kiểu dữ liệu và null parameter

Một lỗi phổ biến trong JDBC call là bind sai kiểu hoặc không xử lý NULL. Oracle NUMBER, VARCHAR2, DATE, TIMESTAMP, CLOB, BLOB, collection và object type có cách binding khác nhau.

Ví dụ bind NULL:

    statement.setNull(1, Types.NUMERIC);

Với tham số DATE/TIMESTAMP, dùng java.time/JDBC 4.2 khi driver hỗ trợ và chọn đúng semantics. Với Oracle DATE có giờ, không dùng java.sql.Date nếu cần giữ giờ. Với TSTZ/TSLTZ, kiểm tra timezone/session semantics.

Với BigDecimal, tránh tạo từ double:

    new BigDecimal(0.1)

Vì biểu diễn nhị phân double có thể tạo giá trị thập phân không chính xác. Dùng:

    new BigDecimal("0.10")

Test nên bao phủ:

- NULL input được phép và không được phép.
- Số lớn, scale lớn và rounding.
- Chuỗi rỗng và NULL theo semantics Oracle VARCHAR2.
- Unicode và độ dài tối đa.
- Ngày giờ, timezone và fractional seconds.
- OUT parameter trả NULL.
- REF CURSOR rỗng.
- Collection rỗng và phần tử NULL.

Oracle xử lý chuỗi rỗng VARCHAR2 như NULL trong nhiều ngữ cảnh. Nếu Java gửi chuỗi rỗng, đừng giả định database phân biệt nó như một giá trị rỗng khác NULL.

## 14. Kiểm thử quyền và execution context

Một package có thể được gọi thành công khi test bằng owner schema nhưng thất bại khi application user gọi. Nguyên nhân thường là quyền, synonym, current_schema hoặc quyền trên object phụ thuộc.

Cần kiểm tra:

- Application user có EXECUTE trên package không.
- Package chạy AUTHID DEFINER hay AUTHID CURRENT_USER.
- Owner package có quyền trên table/view/package phụ thuộc không.
- Quyền được cấp trực tiếp hay qua role, và execution context có sử dụng role đó không.
- Synonym trỏ tới đúng owner/object.
- Database service/PDB là đúng môi trường.
- VPD, application context và policy có ảnh hưởng kết quả không.

Ví dụ cấp quyền:

    GRANT EXECUTE ON order_api TO app_user;

Không cấp quyền DBA hoặc quyền DML rộng nếu application chỉ cần gọi package. Nếu package dùng quyền definer, owner cần các quyền object phù hợp được cấp trực tiếp theo quy tắc Oracle cho stored PL/SQL.

JDBC integration test nên kết nối bằng application user thực tế hoặc user có quyền tương đương. Chạy toàn bộ test bằng SYSTEM/SYS có thể che giấu lỗi phân quyền.

## 15. Test package dependency và mock/stub

PL/SQL package có thể phụ thuộc package khác, sequence, table, database link hoặc external service. Test có thể cần kiểm soát dependency để kết quả ổn định.

Các cách thường dùng:

- Tách logic tính toán thuần thành function nhỏ để test độc lập.
- Truyền dependency hoặc tham số thời gian vào thay vì đọc SYSDATE trực tiếp.
- Tạo test schema với fixture riêng.
- Dùng interface package/wrapper để thay thế dependency trong test khi kiến trúc cho phép.
- Dùng package test double có cùng contract trong schema test nếu có cơ chế deployment an toàn.
- Dùng database link/service giả lập trong môi trường integration test.
- Với side effect ngoài database, ghi ra outbox/event table để kiểm tra thay vì gọi hệ thống ngoài trong unit test.

Không tạo mock quá sâu khiến test chỉ xác minh mock. Test cuối cùng vẫn cần một số integration test với package và dependency thật.

## 16. Test concurrency và locking

Procedure có thể chạy đúng khi test đơn lẻ nhưng lỗi khi nhiều session đồng thời cập nhật cùng dữ liệu. Các vấn đề thường gặp:

- Lost update.
- Deadlock.
- Unique constraint race.
- SELECT FOR UPDATE timeout.
- Lock contention.
- Sequence/number allocation assumption.
- Isolation và read consistency.

Test concurrency cần nhiều connection/session độc lập và điều phối đồng thời. utPLSQL có thể kiểm tra logic tuần tự trong session; JDBC/JUnit hoặc harness chuyên dụng thường phù hợp hơn để tạo concurrent session và đo kết quả.

Ví dụ hai transaction cùng approve một order:

    Session A                         Session B
    ---------                         ---------
    SELECT order FOR UPDATE
    UPDATE status = APPROVED
                                      SELECT order FOR UPDATE (wait)
    COMMIT
                                      resumes and reads current state
                                      detects status is no longer NEW
                                      raises business error

Test cần xác nhận chỉ một request thành công, request còn lại nhận lỗi xung đột đúng contract và dữ liệu cuối cùng ở trạng thái hợp lệ. Dùng latch/barrier hoặc cơ chế đồng bộ test để tái hiện race condition; không dựa vào sleep ngẫu nhiên.

## 17. Tổ chức bộ test trong CI/CD

Một pipeline có thể chia thành các tầng:

    Commit / Pull Request
          |
          v
    Compile PL/SQL and schema migration
          |
          v
    utPLSQL unit suites
          |
          v
    Java JDBC integration tests
          |
          v
    Service / API integration tests
          |
          v
    Deployment candidate

Từng tầng cần database/schema riêng hoặc fixture isolation phù hợp. Không chạy test đồng thời trên cùng dữ liệu mutable nếu chúng có thể xung đột.

### 17.1. Chạy utPLSQL trong pipeline

Pipeline cần:

1. Khởi tạo Oracle test database hoặc cấp một schema test dùng riêng.
2. Deploy migration và package cần test.
3. Cài/đảm bảo utPLSQL framework ở phiên bản tương thích.
4. Cấp quyền test runner.
5. Chạy suite được chọn.
6. Thu thập report và log.
7. Đánh dấu build fail nếu có test failure/error.
8. Dọn môi trường test theo chính sách.

Runner có thể được gọi qua SQLcl/SQL*Plus hoặc công cụ tương thích. Cú pháp reporter, exit code và cách chọn suite cần theo phiên bản framework. Đừng chỉ grep từ khóa PASS trong stdout; dùng reporter/exit status có cấu trúc nếu pipeline hỗ trợ.

### 17.2. Chạy JDBC integration test

Pipeline Java cần:

- Oracle database có package và schema migration đúng phiên bản.
- Oracle JDBC driver đúng với JDK/runtime.
- Secret kết nối test được cấp an toàn.
- Test user có quyền giống application user.
- JUnit/Spring test profile riêng.
- Timeout và cleanup để tránh test treo hoặc để lại session.
- Log lỗi SQL đã masking dữ liệu nhạy cảm.

Nếu dùng Oracle Free/XE hoặc database container cho CI, xác nhận image/version có hỗ trợ feature mà package cần. Không giả định H2 hoặc database khác mô phỏng chính xác PL/SQL, NUMBER, REF CURSOR, package, trigger hay transaction behavior của Oracle.

### 17.3. Không chạy test phá hủy trên production

Test có thể INSERT/UPDATE/DELETE, gọi sequence, commit hoặc kích hoạt trigger. Chỉ chạy trên database test hoặc schema được cô lập và có chính sách cleanup. Không dùng production làm môi trường thử nghiệm routine chỉ vì có dữ liệu thật.

### 17.4. Phân loại test theo tốc độ

- Fast database unit test: function tính toán và package API với fixture nhỏ.
- Database integration test: nhiều bảng, constraint, trigger và package dependency.
- JDBC contract test: callable statement, OUT parameter, cursor và exception.
- Service integration test: Spring transaction, repository và mapping exception.
- Concurrency test: nhiều session và lock behavior.
- Performance test: volume dữ liệu, execution plan, throughput và latency.

Chạy test nhanh ở mỗi pull request; test nặng hoặc concurrency có thể chạy theo lịch hoặc trước release, nhưng các luồng quan trọng vẫn phải có coverage đủ sớm để phát hiện regression.

## 18. So sánh utPLSQL và JDBC/JUnit

| Tiêu chí | utPLSQL | JDBC/JUnit |
|---|---|---|
| Ngôn ngữ test | PL/SQL | Java |
| Nơi chạy | Trong Oracle Database | Ứng dụng/test JVM kết nối Oracle |
| Kiểm tra logic PL/SQL | Rất phù hợp | Có thể, nhưng test harness phức tạp hơn |
| Kiểm tra JDBC bind/OUT | Không kiểm tra Java driver | Phù hợp |
| REF CURSOR mapping | Kiểm tra cursor logic trong PL/SQL | Kiểm tra cách Java đọc cursor |
| Spring transaction | Không kiểm tra Spring | Có thể kiểm tra qua Spring context |
| Quyền application user | Có thể chạy dưới test user | Có thể dùng chính application user |
| Session pool behavior | Giới hạn theo runner/session | Có thể kiểm tra connection reuse |
| Test concurrency từ nhiều session | Có thể nhưng cần orchestration | Phù hợp với nhiều JDBC connection |
| Tích hợp CI | Cần Oracle runner/report | Tích hợp JUnit/Surefire/Gradle/Maven |
| Phụ thuộc Oracle JDBC driver | Không | Có |
| Kiểm tra API HTTP | Không phải mục tiêu | Có thể mở rộng qua service/API test |

Hai hướng không loại trừ nhau. Một package có nhiều logic database nên có utPLSQL suite để kiểm tra quy tắc nội bộ, đồng thời có JDBC contract test cho các routine Java thực sự gọi.

## 19. Ví dụ một chiến lược test hoàn chỉnh cho order_api

Giả sử package order_api có:

- create_order: tạo order và trả OUT ID.
- calculate_total: tính tổng tiền.
- approve_order: chuyển trạng thái NEW sang APPROVED.
- list_orders: trả SYS_REFCURSOR.
- cancel_order: từ chối nếu order đã giao.

Có thể chia test:

### 19.1. utPLSQL

    TEST_ORDER_API
      +-- creates_order_for_active_customer
      +-- rejects_unknown_customer
      +-- rejects_negative_amount
      +-- calculates_total_with_discount
      +-- calculates_zero_total
      +-- approves_new_order
      +-- rejects_approval_for_closed_order
      +-- cancels_eligible_order
      +-- rejects_cancel_for_delivered_order

Test dùng fixture customer/product/order riêng và rollback transactional changes. Kiểm tra cả row state và exception code.

### 19.2. JDBC contract test

    OrderApiJdbcTest
      +-- binds_create_order_in_parameters
      +-- reads_create_order_out_parameter
      +-- calls_calculate_total_function
      +-- reads_list_orders_ref_cursor
      +-- maps_application_error_to_sql_exception
      +-- rolls_back_when_caller_rolls_back
      +-- executes_as_application_user

Test này xác nhận signature PL/SQL, JDBC types, driver và quyền.

### 19.3. Spring service test

    OrderServiceIntegrationTest
      +-- creates_order_with_transaction
      +-- maps_business_error_to_domain_exception
      +-- returns_expected_order_dto
      +-- does_not_hold_transaction_during_external_call

Service test xác nhận Spring transaction boundary, exception translation và mapping DTO. Nếu service gọi package qua repository/adapter, dùng Oracle database thật trong integration profile.

## 20. Checklist thiết kế test

### Trước khi viết test

- Xác định public package API và contract từng routine.
- Ghi rõ IN, OUT, IN OUT, return type và exception code.
- Xác định bảng, sequence, trigger, package dependency và quyền cần thiết.
- Xác định routine có COMMIT, autonomous transaction hoặc external side effect không.
- Chọn fixture có khóa riêng và không dùng dữ liệu production.
- Chọn test layer: utPLSQL, JDBC/JUnit hay cả hai.
- Xác định Oracle version, utPLSQL version, JDK và ojdbc version.

### Khi viết utPLSQL

- Suite có annotation đúng.
- Mỗi test mô tả một hành vi chính.
- Fixture được tạo theo từng test hoặc reset rõ ràng.
- Assertion kiểm tra kết quả, row state và exception.
- Rollback mode phù hợp transaction behavior.
- Không phụ thuộc thứ tự test, sequence value hoặc NLS mặc định.
- Không giả định DDL, COMMIT hay autonomous transaction sẽ rollback.

### Khi viết JDBC/JUnit

- Kết nối bằng Oracle JDBC driver thật.
- CallableStatement bind đúng kiểu và thứ tự.
- OUT parameter/function return được register trước execute.
- REF CURSOR được đọc trước khi đóng connection.
- BigDecimal được dùng cho decimal chính xác.
- SQLException được kiểm tra theo error code/contract.
- Transaction cleanup được xác nhận, nhất là khi procedure commit.
- Test dùng application user hoặc quyền tương đương.
- Connection, statement và result set được đóng bằng try-with-resources.

### Sau khi test chạy

- Xem đầy đủ test failure/error và SQL error.
- Xác minh không để lại dữ liệu test đã commit.
- Kiểm tra session/connection được giải phóng.
- Chạy lại suite để xác nhận tính lặp lại.
- Lưu report và phiên bản schema/driver/framework.
- Không coi test pass ở owner schema là bằng chứng application user có quyền đúng.

## 21. Các lỗi kiểm thử thường gặp

### 21.1. Test pass dưới owner nhưng application user thất bại

Nguyên nhân là owner có quyền trực tiếp trên object, còn application user thiếu EXECUTE hoặc package dependency thiếu quyền. Chạy JDBC test bằng application user và kiểm tra AUTHID/privilege.

### 21.2. Test để lại dữ liệu sau khi chạy

Nguyên nhân có thể là package COMMIT, autonomous transaction, DDL hoặc side effect ngoài database. Xác định transaction contract và dùng schema test riêng hoặc cleanup theo khóa fixture.

### 21.3. Test fail khi chạy song song

Fixture dùng ID cố định hoặc shared mutable data gây unique constraint conflict và race. Dùng ID namespace riêng, dữ liệu độc lập và isolation giữa worker/session.

### 21.4. JDBC đọc sai OUT parameter

Có thể register sai JDBC type, sai index hoặc đọc trước execute. Kiểm tra signature package, thứ tự tham số và driver mapping. Dùng BigDecimal cho NUMBER cần precision cao.

### 21.5. REF CURSOR bị đóng sớm

ResultSet được trả từ cursor phụ thuộc statement và connection. Map dữ liệu trước khi đóng resource; không trả ResultSet ra khỏi repository sau khi connection đã được release.

### 21.6. Assertion dựa vào thứ tự SQL không bảo đảm

Nếu query không có ORDER BY, database không bảo đảm thứ tự kết quả. Thêm ORDER BY theo khóa xác định hoặc so sánh theo tập hợp thay vì vị trí.

### 21.7. Test phụ thuộc ngày giờ hiện tại

Dùng SYSDATE/SYSTIMESTAMP trực tiếp làm test không ổn định theo thời gian và timezone. Truyền mốc thời gian vào routine, cố định session timezone hoặc tạo dữ liệu tương đối có biên rõ ràng.

## 22. Nguyên tắc cần nhớ

- utPLSQL kiểm thử package, procedure và function ngay trong Oracle; JDBC/JUnit kiểm tra contract từ Java tới database.
- Test public behavior thay vì phụ thuộc private implementation.
- Fixture phải độc lập, xác định được và có cleanup rõ ràng.
- Không giả định rollback tự động đảo ngược COMMIT, autonomous transaction, DDL, sequence hoặc side effect ngoài database.
- CallableStatement cần bind đúng IN/OUT/IN OUT và register function return đúng vị trí.
- REF CURSOR phải được đọc khi statement và connection còn mở.
- Dùng BigDecimal cho NUMBER cần chính xác; kiểm tra NULL, precision và chuỗi rỗng theo semantics Oracle.
- Test bằng application user để phát hiện lỗi EXECUTE, AUTHID và quyền object.
- Connection pool/session state và transaction boundary cần được kiểm thử trong integration layer.
- Chạy test trên Oracle tương thích và driver thật; database giả lập không chứng minh được toàn bộ hành vi Oracle.
- CI cần report/exit status đáng tin cậy và môi trường test cô lập.
- Không chạy test có DML/COMMIT trên production.

Một chiến lược kiểm thử PL/SQL vững chắc dùng utPLSQL để kiểm tra quy tắc trong database và JDBC/JUnit để xác nhận cách ứng dụng gọi các routine đó. Khi contract, fixture, transaction và quyền được kiểm soát, lỗi được phát hiện ở đúng tầng và các thay đổi package ít có nguy cơ phá vỡ ứng dụng Spring Boot đang sử dụng chúng.

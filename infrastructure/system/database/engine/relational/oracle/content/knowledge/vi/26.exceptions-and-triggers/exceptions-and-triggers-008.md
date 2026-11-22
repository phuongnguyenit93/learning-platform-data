# Mutating table và lựa chọn compound trigger

Trong Oracle Database, lỗi **ORA-04091: table is mutating, trigger/function may not see it** thường xuất hiện khi một row-level trigger đọc hoặc sửa chính bảng đang được câu lệnh DML thay đổi. Đây là cơ chế bảo vệ tính nhất quán của Oracle: trong lúc một câu lệnh cập nhật nhiều hàng đang chạy, trạng thái trung gian của bảng chưa phải trạng thái cuối cùng của câu lệnh.

Khi nghiệp vụ cần lấy dữ liệu từng hàng qua :OLD/:NEW, đồng thời cần truy vấn lại toàn bộ bảng sau khi tất cả hàng đã được xử lý, **compound trigger** là một lựa chọn phù hợp. Nó cho phép gom dữ liệu ở thời điểm xử lý từng hàng rồi dùng dữ liệu đã gom trong phần AFTER STATEMENT, nơi câu lệnh DML đã hoàn tất việc thay đổi các hàng.

## 1. Mutating table là gì?

Một bảng được gọi là *mutating* trong ngữ cảnh trigger khi câu lệnh DML đang thay đổi bảng đó và Oracle chưa hoàn tất việc xử lý tất cả các hàng. Với row-level trigger, Oracle không cho phép trigger truy vấn hoặc thay đổi lại chính bảng đang mutating theo cách có thể khiến kết quả phụ thuộc vào thứ tự xử lý từng hàng.

Ví dụ, giả sử bảng EMPLOYEES lưu nhân viên, phòng ban và lương. Ta muốn kiểm tra lương mới của nhân viên có vượt quá hai lần mức lương trung bình trong phòng ban hay không. Cách viết trực tiếp sau đây có vấn đề:

~~~sql
CREATE OR REPLACE TRIGGER trg_check_emp_salary
BEFORE INSERT OR UPDATE OF salary ON employees
FOR EACH ROW
DECLARE
  l_avg_salary NUMBER;
BEGIN
  SELECT AVG(salary)
    INTO l_avg_salary
    FROM employees
   WHERE department_id = :NEW.department_id;

  IF :NEW.salary > 2 * l_avg_salary THEN
    RAISE_APPLICATION_ERROR(
      -20001,
      'Salary exceeds twice the department average'
    );
  END IF;
END;
/
~~~

Trigger này chạy một lần cho mỗi hàng. Trong lúc trigger đang chạy, câu lệnh INSERT hoặc UPDATE bên ngoài vẫn đang thay đổi EMPLOYEES. Vì vậy, câu SELECT trong trigger đọc lại EMPLOYEES có thể gặp ORA-04091. Việc chuyển câu SELECT vào một procedure hoặc function được gọi từ trigger cũng không giải quyết được vấn đề: Oracle vẫn xem đó là thao tác đọc bảng mutating trong cùng ngữ cảnh row-level trigger.

Vấn đề không chỉ nằm ở câu SELECT. Một row-level trigger cũng không nên tự UPDATE hoặc DELETE lại chính bảng đang kích hoạt nó. Nếu cần xử lý dữ liệu của chính bảng đó, hãy xem xét chuyển phần xử lý sang thời điểm statement-level hoặc thiết kế lại nghiệp vụ.

### Vì sao Oracle hạn chế truy vấn bảng đang mutating?

Một câu lệnh như UPDATE có thể tác động đến hàng trăm hoặc hàng nghìn bản ghi. Oracle không cam kết thứ tự xử lý các hàng theo cách mà nghiệp vụ có thể dựa vào. Nếu trigger của hàng thứ nhất đọc bảng khi chỉ một phần các hàng đã được cập nhật, kết quả có thể khác với kết quả sau khi toàn bộ câu lệnh hoàn thành.

Ví dụ, khi cập nhật đồng thời lương của nhiều nhân viên, một trigger đọc mức trung bình ở giữa quá trình có thể nhìn thấy một tập hợp giá trị chưa hoàn chỉnh. Nếu quyết định nghiệp vụ phụ thuộc vào tập hợp trung gian đó, kết quả có thể thay đổi theo cách Oracle thực thi câu lệnh. Hạn chế mutating table giúp tránh kiểu phụ thuộc này.

## 2. Chọn cách xử lý phù hợp

Không phải mọi ORA-04091 đều cần compound trigger. Trước hết, hãy xác định trigger cần dữ liệu nào và cần dữ liệu ở thời điểm nào.

| Nhu cầu | Hướng xử lý thường phù hợp |
|---|---|
| Quy tắc có thể biểu diễn bằng ràng buộc dữ liệu | Ưu tiên PRIMARY KEY, UNIQUE, FOREIGN KEY hoặc CHECK khi phù hợp |
| Chỉ cần đọc trạng thái bảng trước khi câu lệnh bắt đầu | Có thể dùng BEFORE STATEMENT trigger |
| Chỉ cần đọc trạng thái sau khi toàn bộ câu lệnh hoàn tất, không cần :OLD/:NEW của từng hàng | Có thể dùng AFTER STATEMENT trigger |
| Cần thu thập :OLD/:NEW của từng hàng rồi truy vấn bảng sau khi DML hoàn tất | Dùng compound trigger |
| Hệ thống cũ chưa thể dùng compound trigger | Có thể dùng package state kết hợp row-level và statement-level trigger, nhưng phải quản lý trạng thái cẩn thận |

Một statement-level trigger thông thường không có :OLD và :NEW vì nó không chạy riêng cho từng hàng. Nếu nghiệp vụ cần biết phòng ban cũ và mới của từng nhân viên được cập nhật, compound trigger có thể lưu các giá trị đó trong phần AFTER EACH ROW rồi xử lý ở AFTER STATEMENT.

## 3. Cấu trúc của compound trigger

Compound trigger là một trigger DML có thể chứa nhiều timing section trong cùng một khai báo. Các section có thể dùng là:

| Timing section | Thời điểm chạy | Công việc thường thực hiện |
|---|---|---|
| BEFORE STATEMENT | Một lần trước khi xử lý các hàng | Khởi tạo trạng thái hoặc kiểm tra điều kiện đầu câu lệnh |
| BEFORE EACH ROW | Trước mỗi hàng | Kiểm tra hoặc điều chỉnh giá trị :NEW |
| AFTER EACH ROW | Sau mỗi hàng | Thu thập :OLD/:NEW hoặc ghi nhận dữ liệu cần xử lý sau |
| AFTER STATEMENT | Một lần sau khi xử lý xong các hàng | Truy vấn trạng thái cuối cùng, tổng hợp hoặc thực hiện xử lý theo lô |

Không bắt buộc phải khai báo đủ cả bốn section. Chỉ khai báo những section cần dùng. Các biến và subprogram đặt ở phần khai báo chung sau COMPOUND TRIGGER được chia sẻ giữa các section trong cùng một lần thực thi câu lệnh. Trạng thái này được tạo khi câu lệnh bắt đầu và được giải phóng khi lần thực thi trigger kết thúc.

Khung cú pháp tổng quát:

~~~sql
CREATE OR REPLACE TRIGGER trigger_name
FOR INSERT OR UPDATE OR DELETE ON table_name
COMPOUND TRIGGER

  -- Khai báo biến, kiểu dữ liệu và subprogram dùng chung.

  BEFORE STATEMENT IS
  BEGIN
    -- Chạy một lần trước câu lệnh DML.
  END BEFORE STATEMENT;

  AFTER EACH ROW IS
  BEGIN
    -- Chạy sau mỗi hàng; có thể dùng :OLD và :NEW.
  END AFTER EACH ROW;

  AFTER STATEMENT IS
  BEGIN
    -- Chạy một lần sau khi câu lệnh DML xử lý xong các hàng.
  END AFTER STATEMENT;

END trigger_name;
/
~~~

Trong các section theo từng hàng, có thể dùng :OLD và :NEW theo loại DML. Với INSERT, :NEW chứa giá trị hàng được thêm; với DELETE, :OLD chứa giá trị hàng bị xóa; với UPDATE, cả hai đều có thể được sử dụng. Các section statement-level không có dữ liệu :OLD/:NEW của một hàng cụ thể.

## 4. Ví dụ: kiểm tra tổng lương của phòng ban sau khi DML hoàn tất

Giả sử có hai bảng:

- DEPARTMENTS(department_id, salary_budget): lưu ngân sách lương của mỗi phòng ban.
- EMPLOYEES(employee_id, department_id, salary): lưu nhân viên, phòng ban và lương.

Quy tắc nghiệp vụ: sau mỗi câu lệnh INSERT, UPDATE hoặc DELETE trên EMPLOYEES, tổng lương của mỗi phòng ban bị ảnh hưởng không được vượt quá salary_budget của phòng ban đó.

Nếu kiểm tra tổng lương trong row-level trigger bằng cách SELECT SUM(salary) FROM EMPLOYEES, trigger có thể gặp ORA-04091. Ta sẽ dùng compound trigger theo hai giai đoạn:

1. Trong AFTER EACH ROW, chỉ ghi nhận department_id cũ và mới của các hàng bị ảnh hưởng. Không truy vấn EMPLOYEES tại đây.
2. Trong AFTER STATEMENT, duyệt các phòng ban đã ghi nhận, truy vấn tổng lương hiện tại của từng phòng ban và so sánh với ngân sách.

~~~sql
CREATE OR REPLACE TRIGGER trg_check_dept_salary_budget
FOR INSERT OR UPDATE OR DELETE ON employees
COMPOUND TRIGGER

  TYPE t_department_ids IS TABLE OF departments.department_id%TYPE
    INDEX BY PLS_INTEGER;

  g_department_ids   t_department_ids;
  g_department_count PLS_INTEGER := 0;

  PROCEDURE remember_department(
    p_department_id IN departments.department_id%TYPE
  ) IS
  BEGIN
    IF p_department_id IS NULL THEN
      RETURN;
    END IF;

    -- Chỉ lưu mỗi department_id một lần để tránh truy vấn lặp.
    IF g_department_count > 0 THEN
      FOR i IN 1 .. g_department_count LOOP
        IF g_department_ids(i) = p_department_id THEN
          RETURN;
        END IF;
      END LOOP;
    END IF;

    g_department_count := g_department_count + 1;
    g_department_ids(g_department_count) := p_department_id;
  END remember_department;

  AFTER EACH ROW IS
  BEGIN
    IF INSERTING THEN
      remember_department(:NEW.department_id);

    ELSIF DELETING THEN
      remember_department(:OLD.department_id);

    ELSIF UPDATING('SALARY') OR UPDATING('DEPARTMENT_ID') THEN
      -- Khi nhân viên chuyển phòng ban, phải kiểm tra cả nơi đi và nơi đến.
      remember_department(:OLD.department_id);
      remember_department(:NEW.department_id);
    END IF;
  END AFTER EACH ROW;

  AFTER STATEMENT IS
    l_total_salary NUMBER;
    l_budget       departments.salary_budget%TYPE;
  BEGIN
    IF g_department_count > 0 THEN
      FOR i IN 1 .. g_department_count LOOP
        SELECT d.salary_budget
          INTO l_budget
          FROM departments d
         WHERE d.department_id = g_department_ids(i);

        SELECT NVL(SUM(e.salary), 0)
          INTO l_total_salary
          FROM employees e
         WHERE e.department_id = g_department_ids(i);

        IF l_total_salary > l_budget THEN
          RAISE_APPLICATION_ERROR(
            -20041,
            'Total salary exceeds budget for department '
              || TO_CHAR(g_department_ids(i))
          );
        END IF;
      END LOOP;
    END IF;
  END AFTER STATEMENT;

END trg_check_dept_salary_budget;
/
~~~

Ví dụ giả định DEPARTMENTS.department_id là khóa chính, EMPLOYEES.department_id tham chiếu đến khóa đó, salary_budget có giá trị NOT NULL và salary được lưu theo đơn vị tiền tệ thống nhất. Nếu hệ thống cho phép nhân viên không thuộc phòng ban nào, đoạn mã bỏ qua department_id NULL.

### Phân tích luồng chạy

**Khi INSERT:** AFTER EACH ROW lấy :NEW.department_id. Nếu một câu INSERT thêm nhiều nhân viên cùng phòng ban, thủ tục remember_department chỉ giữ department_id đó một lần.

**Khi DELETE:** AFTER EACH ROW lấy :OLD.department_id. Phòng ban cũ cần được kiểm tra vì tổng lương của phòng ban đã giảm.

**Khi UPDATE lương:** trigger ghi nhận phòng ban của hàng trước và sau cập nhật. Nếu nhân viên vẫn ở cùng phòng ban, hàm remember_department loại bỏ giá trị trùng.

**Khi UPDATE phòng ban:** trigger ghi nhận cả :OLD.department_id và :NEW.department_id. Phòng ban cũ có thể giảm tổng lương, còn phòng ban mới có thể tăng tổng lương; cả hai đều cần được kiểm tra.

**Trong AFTER STATEMENT:** toàn bộ hàng của câu lệnh DML đã được xử lý. Vì vậy, SELECT SUM(salary) FROM EMPLOYEES có thể đọc trạng thái sau câu lệnh mà không gặp hạn chế mutating table của row-level trigger. Nếu tổng lương vượt ngân sách, RAISE_APPLICATION_ERROR làm câu lệnh DML thất bại; các thay đổi của câu lệnh đó sẽ được rollback theo cơ chế giao dịch của Oracle.

Ví dụ này tập trung minh họa cách chia công việc giữa AFTER EACH ROW và AFTER STATEMENT. Với quy tắc ngân sách phải được bảo đảm tuyệt đối khi nhiều session cùng sửa dữ liệu, cần thiết kế thêm cơ chế đồng bộ. Hai session có thể cùng đọc một tổng lương chưa bao gồm thay đổi chưa commit của session kia và đều vượt qua phép kiểm tra. Một giải pháp thường cần khóa hàng DEPARTMENTS tương ứng trước khi tính tổng, đồng thời khóa nhiều phòng ban theo cùng một thứ tự để giảm nguy cơ deadlock. Cần kiểm thử thiết kế khóa trong bối cảnh giao dịch thực tế của ứng dụng.

## 5. Compound trigger giải quyết mutating table như thế nào?

Điểm quyết định là **thời điểm truy vấn bảng**:

- AFTER EACH ROW chỉ thu thập các giá trị cần thiết từ :OLD và :NEW. Nó không đọc lại bảng EMPLOYEES.
- AFTER STATEMENT mới truy vấn EMPLOYEES. Lúc này câu lệnh DML đã xử lý xong tất cả hàng, nên bảng không còn ở trạng thái mutating đối với câu lệnh đó.

Compound trigger cũng giúp giữ dữ liệu trung gian trong phạm vi một lần thực thi câu lệnh. Ta không cần một package global để chuyển dữ liệu từ row-level trigger sang statement-level trigger riêng biệt.

## 6. Khi nào nên chọn compound trigger?

Compound trigger đặc biệt hữu ích khi có đủ hai yêu cầu:

1. Cần lấy thông tin của từng hàng qua :OLD hoặc :NEW.
2. Cần thực hiện một thao tác tổng hợp hoặc truy vấn lại bảng sau khi toàn bộ câu lệnh hoàn tất.

Các tình huống thường gặp gồm:

- Thu thập khóa của các hàng bị thay đổi, sau đó kiểm tra quy tắc liên quan đến nhiều hàng.
- Gom dữ liệu thay đổi để ghi audit hoặc cập nhật bảng tổng hợp theo lô.
- Kiểm tra trạng thái cuối cùng của các nhóm hàng sau một câu lệnh DML nhiều hàng.
- Tránh truy vấn bảng đang mutating trong row-level trigger.

Nếu chỉ cần chạy một lần sau câu lệnh và không cần dữ liệu riêng của từng hàng, AFTER STATEMENT trigger đơn giản có thể đã đủ. Nếu chỉ cần kiểm tra giá trị của chính hàng đang thay đổi, row-level trigger có thể phù hợp miễn là không truy vấn hoặc sửa lại bảng đang mutating. Nếu quy tắc có thể được thể hiện bằng constraint, nên ưu tiên constraint vì Oracle quản lý tính toàn vẹn trực tiếp ở tầng dữ liệu.

## 7. Package state: phương án cũ và những điểm cần cẩn thận

Trước khi compound trigger được hỗ trợ, một cách xử lý phổ biến là dùng package chứa collection dùng chung:

1. Row-level trigger ghi các khóa hoặc giá trị :OLD/:NEW vào collection của package.
2. Statement-level trigger đọc collection, truy vấn bảng sau khi DML hoàn tất rồi xử lý.
3. Package phải xóa collection sau mỗi câu lệnh và xử lý đúng cả đường đi thành công lẫn ngoại lệ.

Cách này có thể dùng trong hệ thống cũ, nhưng trạng thái package tồn tại trong session. Nếu quên reset khi có lỗi, trạng thái của câu lệnh trước có thể ảnh hưởng câu lệnh sau. Recursive DML, nhiều trigger cùng dùng package hoặc các đường xử lý ngoại lệ cũng làm việc quản lý trạng thái phức tạp hơn. Compound trigger gom phần khai báo, thu thập và xử lý vào một trigger, đồng thời giới hạn tuổi thọ của trạng thái theo câu lệnh DML.

Compound trigger được Oracle hỗ trợ từ Oracle Database 11g Release 1. Với phiên bản cũ hơn, cần cân nhắc phương án package state hoặc thay đổi thiết kế.

## 8. Những cách xử lý dễ gây lỗi

**Gọi function để che câu SELECT:** nếu function được gọi từ row-level trigger và function truy vấn lại bảng đang mutating, ORA-04091 vẫn có thể xảy ra. Chuyển câu SELECT sang một tầng gọi khác không thay đổi thời điểm thực thi của nó.

**Dùng autonomous transaction để né lỗi:** autonomous transaction không làm cho trạng thái của bảng chính trở nên an toàn để kiểm tra. Nó chạy trong giao dịch độc lập, có thể nhìn thấy dữ liệu khác với giao dịch gọi nó và có thể commit những tác động tách rời khỏi câu lệnh chính. Đây không phải cách sửa đúng cho mutating table.

**Bắt rồi bỏ qua mọi ngoại lệ:** WHEN OTHERS THEN NULL chỉ che giấu lỗi và có thể khiến quy tắc nghiệp vụ không được thực thi. Hãy xử lý đúng nguyên nhân hoặc phát sinh lỗi rõ ràng để câu lệnh thất bại khi dữ liệu không hợp lệ.

**Lặp truy vấn cho mọi hàng:** nếu AFTER EACH ROW chỉ cần ghi nhận một khóa, hãy lưu khóa đó rồi xử lý một lần ở AFTER STATEMENT. Khử trùng lặp các khóa giúp tránh truy vấn cùng một nhóm nhiều lần trong một câu lệnh lớn.

**Quên hàng ở phòng ban cũ:** khi UPDATE chuyển một hàng từ nhóm A sang nhóm B, chỉ kiểm tra nhóm B là chưa đủ. Các quy tắc tổng hợp có thể bị ảnh hưởng ở cả nhóm cũ và nhóm mới.

## 9. Cách kiểm tra một compound trigger

Khi triển khai, nên kiểm tra các trường hợp theo đúng cách ứng dụng sẽ sử dụng bảng:

1. INSERT một hàng và INSERT nhiều hàng vào cùng một phòng ban.
2. UPDATE lương của một hàng và UPDATE nhiều hàng trong cùng một câu lệnh.
3. Chuyển nhân viên từ phòng ban này sang phòng ban khác; xác nhận cả hai phòng ban đều được kiểm tra.
4. DELETE một hàng và DELETE nhiều hàng.
5. DML không làm thay đổi cột liên quan; xác nhận trigger không thực hiện xử lý thừa ngoài dự kiến.
6. Câu lệnh làm vi phạm quy tắc; xác nhận lỗi được trả về và toàn bộ câu lệnh bị rollback.
7. Các trường hợp NULL, phòng ban không có nhân viên và dữ liệu biên theo constraint thực tế.
8. Hai session cùng thay đổi dữ liệu của một phòng ban; xác nhận cơ chế khóa hoặc đồng bộ bảo vệ được quy tắc nghiệp vụ.

Khi gặp ORA-04091, hãy đọc thông báo lỗi để xác định bảng mutating và trigger liên quan. Sau đó kiểm tra cả các procedure, function và dynamic SQL được gọi gián tiếp từ row-level trigger. Nếu cần dữ liệu cuối cùng của nhiều hàng, hãy chuyển phần truy vấn sang AFTER STATEMENT và chỉ giữ lại trong AFTER EACH ROW những thông tin thực sự cần thu thập.

## 10. Kết luận lựa chọn

Hãy dùng compound trigger khi nghiệp vụ cần kết hợp xử lý từng hàng với xử lý toàn bộ câu lệnh. Mẫu triển khai thường là: khai báo collection ở phần chung, thu thập khóa hoặc giá trị trong AFTER EACH ROW, loại bỏ phần tử trùng, rồi truy vấn hoặc xử lý dữ liệu trong AFTER STATEMENT. Cách này giải quyết đúng nguyên nhân thường gặp của ORA-04091 và giữ trạng thái trung gian trong phạm vi một câu lệnh DML.

Compound trigger không tự động giải quyết mọi vấn đề toàn vẹn dữ liệu. Với quy tắc phụ thuộc nhiều hàng và nhiều session, vẫn phải xem xét khóa, mức cô lập giao dịch, deadlock và cách ứng dụng thực hiện DML. Chọn giải pháp theo thời điểm cần dữ liệu và phạm vi của quy tắc sẽ giúp trigger dễ hiểu, dễ bảo trì và an toàn hơn.

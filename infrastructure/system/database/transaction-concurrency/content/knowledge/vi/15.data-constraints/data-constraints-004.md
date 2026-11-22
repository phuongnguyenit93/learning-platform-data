# Khóa ngoại khi hàng cha bị cập nhật hoặc xóa đồng thời

Khóa ngoại (foreign key — FK) bảo đảm mỗi giá trị khóa ngoại ở bảng con tham chiếu đến một hàng hợp lệ ở bảng cha, theo quy tắc ràng buộc đã khai báo. Khi nhiều transaction cùng thao tác trên hai phía của quan hệ, hệ quản trị phải phối hợp việc kiểm tra FK với cập nhật hoặc xóa hàng cha.

Ví dụ, một nhân viên thuộc về một phòng ban. Transaction A có thể thêm nhân viên mới với `department_id = 10`, trong khi transaction B đang xóa phòng ban 10 hoặc đổi khóa của phòng ban đó. Nếu chỉ kiểm tra phòng ban tồn tại bằng một câu `SELECT` thông thường rồi mới `INSERT`, hai thao tác có thể xen kẽ khiến kết quả kiểm tra trở nên cũ.

Ràng buộc FK trong cơ sở dữ liệu xử lý cuộc đua này bằng cơ chế đồng bộ nội bộ như khóa trên khóa tham chiếu, kiểm tra lại ràng buộc hoặc theo dõi xung đột, tùy hệ quản trị. Kết quả cuối cùng phải tuân thủ hành động tham chiếu đã khai báo. Ứng dụng cần hiểu các trường hợp có thể chờ, bị từ chối, bị cascade và deadlock để xử lý transaction đúng cách.

## 1. Mô hình hàng cha và hàng con

Giả sử có hai bảng:

```sql
CREATE TABLE department (
    department_id BIGINT PRIMARY KEY,
    department_name VARCHAR(200) NOT NULL
);

CREATE TABLE employee (
    employee_id BIGINT PRIMARY KEY,
    employee_name VARCHAR(200) NOT NULL,
    department_id BIGINT NOT NULL,
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id)
        REFERENCES department (department_id)
        ON UPDATE NO ACTION
        ON DELETE RESTRICT
);
```

`department` là bảng cha (referenced table), còn `employee` là bảng con (referencing table). Mỗi giá trị `employee.department_id` phải khớp với một `department.department_id` hợp lệ.

Ràng buộc tham chiếu có hai hướng kiểm tra:

- Khi thêm hoặc đổi `employee.department_id`, hệ quản trị phải xác nhận hàng cha tương ứng tồn tại.
- Khi xóa hàng `department` hoặc thay đổi `department.department_id`, hệ quản trị phải xử lý các hàng con đang tham chiếu theo `ON DELETE` hoặc `ON UPDATE`.

Khóa chính hoặc khóa duy nhất ở phía cha bảo đảm giá trị được tham chiếu là duy nhất. Ở phía con, index trên cột FK thường rất hữu ích để tìm nhanh các hàng tham chiếu khi xóa hoặc đổi khóa cha. Một số hệ quản trị tự tạo index con khi cần, nhưng nhiều hệ quản trị không tự tạo; cần kiểm tra sản phẩm đang dùng.

## 2. Vì sao kiểm tra tồn tại ở ứng dụng có race condition?

Một cách triển khai dễ mắc lỗi là kiểm tra cha trước rồi mới thêm con:

```sql
-- Transaction A
SELECT department_id
FROM department
WHERE department_id = 10;

-- Ứng dụng thấy phòng ban tồn tại và tiếp tục.
INSERT INTO employee (employee_id, employee_name, department_id)
VALUES (501, 'An', 10);
```

Trong lúc đó, transaction B có thể xóa phòng ban 10. Nếu lần đọc của A không giữ một cơ chế bảo vệ phù hợp, kết quả `SELECT` chỉ phản ánh trạng thái tại thời điểm đọc. B có thể xóa cha trước khi A ghi con.

Một lịch xen kẽ minh họa:

| Thời điểm | Transaction A: thêm nhân viên | Transaction B: xóa phòng ban |
|---|---|---|
| 1 | Kiểm tra thấy phòng ban 10 tồn tại | |
| 2 | | Xóa phòng ban 10 và commit |
| 3 | Thêm nhân viên với `department_id = 10` | |
| 4 | Nếu không có FK, hàng con có thể mồ côi | |

Đây là lý do kiểm tra bằng code ứng dụng không thay thế được FK. Nếu constraint được khai báo và bật, hệ quản trị sẽ phối hợp kiểm tra tham chiếu với thao tác xóa/cập nhật cha để không cho phép một hàng con mồ côi được commit.

Ngay cả khi ứng dụng dùng một câu `SELECT ... FOR UPDATE`, cú pháp và loại khóa cần thiết phụ thuộc hệ quản trị. Khóa sai chế độ, khóa sai thời điểm hoặc chỉ khóa hàng con đang tồn tại vẫn có thể không bảo vệ đúng quan hệ. Hãy dùng FK thật và chỉ bổ sung khóa ứng dụng khi có yêu cầu phối hợp nghiệp vụ rõ ràng.

## 3. Hai transaction thêm con và xóa cha đồng thời

Giả sử ban đầu phòng ban 10 tồn tại và chưa có nhân viên tham chiếu. Transaction A thêm nhân viên mới; transaction B xóa phòng ban.

```sql
-- Transaction A
BEGIN;
INSERT INTO employee (employee_id, employee_name, department_id)
VALUES (501, 'An', 10);
COMMIT;
```

```sql
-- Transaction B
BEGIN;
DELETE FROM department
WHERE department_id = 10;
COMMIT;
```

Để bảo vệ FK, hệ quản trị phải điều phối hai thao tác trên khóa cha 10 và quan hệ con. Một cách hình dung tổng quát là thao tác thêm con cần bảo vệ hàng cha trong lúc xác nhận tham chiếu; thao tác xóa hoặc đổi khóa cha cần có quyền thực hiện hành động có thể làm mất hiệu lực tham chiếu.

Kết quả phụ thuộc transaction nào giành được quyền tương thích trước và hành động tham chiếu được khai báo:

### Trường hợp A kiểm tra và thêm con trước

1. A bắt đầu thêm nhân viên tham chiếu phòng ban 10.
2. Cơ chế FK bảo vệ khóa cha trong lúc A xác nhận tham chiếu.
3. B yêu cầu xóa phòng ban 10 và phải chờ nếu thao tác của B xung đột với bảo vệ mà A đang giữ.
4. A commit hàng nhân viên.
5. B tiếp tục kiểm tra và thực hiện hành động tham chiếu.

Với `RESTRICT` hoặc `NO ACTION`, B thường bị từ chối vì hiện đã có nhân viên tham chiếu phòng ban. Với `CASCADE`, B có thể xóa cả nhân viên theo quy tắc đã khai báo. Với `SET NULL`, B có thể đặt `department_id` của nhân viên thành `NULL` nếu cột cho phép.

### Trường hợp B xóa cha trước

1. B khóa hoặc giành quyền xóa phòng ban 10.
2. A yêu cầu thêm nhân viên tham chiếu phòng ban 10 và phải chờ nếu kiểm tra FK xung đột với thao tác của B.
3. B commit việc xóa cha.
4. A tiếp tục kiểm tra FK; phòng ban 10 không còn tồn tại nên thao tác thêm nhân viên bị từ chối.

Nếu B rollback thay vì commit, A có thể tiếp tục sau khi trạng thái cha được khôi phục và kiểm tra lại thành công.

Đây là mô tả logic của việc điều phối. Thứ tự khóa vật lý, loại khóa và thời điểm kiểm tra cụ thể khác nhau theo hệ quản trị; không nên coi sơ đồ này là cam kết rằng mọi engine dùng cùng một loại khóa hoặc cùng thứ tự lấy khóa.

## 4. Hành động tham chiếu khi xóa hoặc đổi khóa cha

Khi khai báo FK, `ON DELETE` và `ON UPDATE` xác định hệ quản trị phải xử lý hàng con như thế nào khi khóa được tham chiếu thay đổi.

| Hành động | Khi xóa hoặc đổi khóa cha | Hệ quả với hàng con |
|---|---|---|
| `RESTRICT` | Từ chối thao tác nếu còn hàng con tham chiếu. | Các hàng con được giữ nguyên. Thời điểm kiểm tra có thể khác theo sản phẩm; `RESTRICT` thường không trì hoãn được. |
| `NO ACTION` | Kiểm tra FK và từ chối nếu kết quả cuối cùng vi phạm. | Có thể kiểm tra ngay hoặc trì hoãn đến cuối transaction nếu constraint được khai báo deferrable và hệ quản trị hỗ trợ. |
| `CASCADE` | Thực hiện cùng hành động trên các hàng con liên quan. | Xóa con khi xóa cha; cập nhật FK con khi khóa cha đổi. |
| `SET NULL` | Giữ hàng con nhưng xóa liên kết. | Đặt cột FK thành `NULL`; cột phải cho phép `NULL`. |
| `SET DEFAULT` | Đặt FK con về giá trị mặc định. | Giá trị mặc định vẫn phải thỏa FK, tức là tham chiếu đến một hàng cha hợp lệ hoặc được phép `NULL`. |

Ví dụ dùng cascade khi xóa phòng ban:

```sql
FOREIGN KEY (department_id)
REFERENCES department (department_id)
ON DELETE CASCADE
```

Nếu phòng ban bị xóa, các nhân viên tham chiếu cũng bị xóa. Đây là quyết định nghiệp vụ lớn: cần chắc chắn vòng đời nhân viên thực sự phụ thuộc hoàn toàn vào phòng ban. Nếu nhân viên cần được giữ lại để chuyển sang phòng ban khác hoặc lưu lịch sử, `CASCADE` có thể không phù hợp.

Ví dụ dùng `SET NULL`:

```sql
department_id BIGINT NULL,
FOREIGN KEY (department_id)
REFERENCES department (department_id)
ON DELETE SET NULL
```

Khi cha bị xóa, nhân viên vẫn tồn tại nhưng không còn thuộc phòng ban. Ứng dụng cần có quy tắc xử lý các nhân viên chưa được phân công.

`ON UPDATE` áp dụng khi giá trị khóa được tham chiếu ở hàng cha thay đổi. Ví dụ `ON UPDATE CASCADE` sẽ cập nhật FK ở các hàng con sang khóa mới. Với khóa định danh thay đổi hiếm khi cần thiết, nhiều hệ thống chọn khóa thay thế (surrogate key) bất biến để tránh chi phí và rủi ro của việc đổi khóa cha.

## 5. `RESTRICT` và `NO ACTION` không phải lúc nào cũng giống nhau

Hai hành động này đều có thể khiến thao tác xóa hoặc đổi khóa cha thất bại khi vẫn còn hàng con tham chiếu. Điểm khác biệt quan trọng là thời điểm kiểm tra.

- `RESTRICT` thường yêu cầu từ chối ngay khi thao tác cha được thực hiện mà còn tham chiếu. Trên một số hệ quản trị, hành động này không thể trì hoãn.
- `NO ACTION` kiểm tra rằng ràng buộc phải đúng tại thời điểm kiểm tra constraint. Nếu FK là deferrable và được đặt ở chế độ deferred, việc kiểm tra có thể được dời đến cuối transaction.

Khả năng trì hoãn và khác biệt chính xác phụ thuộc hệ quản trị. Không phải sản phẩm nào cũng hỗ trợ deferrable foreign key. Hãy kiểm tra tài liệu và thử nghiệm trước khi dựa vào hành vi đó.

Ví dụ về constraint trì hoãn trong một hệ quản trị hỗ trợ cú pháp này:

```sql
FOREIGN KEY (department_id)
REFERENCES department (department_id)
DEFERRABLE INITIALLY DEFERRED
```

Trong một transaction, ứng dụng có thể tạm thời tạo trạng thái vi phạm FK rồi sửa lại trước commit. Nếu đến lúc kiểm tra cuối transaction vẫn còn tham chiếu không hợp lệ, commit thất bại. Việc trì hoãn kiểm tra không cho phép trạng thái vi phạm được commit và cũng không loại bỏ nhu cầu điều phối với transaction đồng thời khác.

## 6. Khi cập nhật khóa chính hoặc khóa duy nhất của hàng cha

Khóa ngoại có thể tham chiếu đến khóa chính hoặc một khóa duy nhất. Nếu giá trị được tham chiếu thay đổi, hệ quản trị phải xử lý các hàng con.

Giả sử đổi mã phòng ban từ 10 sang 20:

```sql
UPDATE department
SET department_id = 20
WHERE department_id = 10;
```

Nếu FK dùng `ON UPDATE CASCADE`, các hàng nhân viên đang có `department_id = 10` sẽ được cập nhật sang 20 theo hành động cascade. Nếu dùng `NO ACTION` hoặc `RESTRICT`, thao tác đổi khóa thường bị từ chối khi vẫn còn hàng con tham chiếu. `SET NULL` hoặc `SET DEFAULT` có thể áp dụng nếu được khai báo và thỏa các ràng buộc khác.

Khi có transaction thêm nhân viên mới trong lúc khóa cha đang đổi:

- Nếu thao tác thêm con đã bảo vệ khóa 10 trước, việc đổi khóa cha phải chờ hoặc phối hợp; sau khi thêm con hoàn tất, cascade phải tính cả hàng mới theo ngữ nghĩa của engine.
- Nếu thao tác đổi khóa cha hoàn tất trước, một transaction thêm con dùng khóa cũ 10 sẽ không thể commit tham chiếu đến khóa không còn tồn tại.
- Nếu `ON UPDATE CASCADE` được dùng, các hàng con được chuyển sang khóa mới trong cùng thao tác tham chiếu; transaction khác phải quan sát kết quả theo isolation level của nó.

Đổi khóa được tham chiếu có thể tác động đến nhiều hàng con và nhiều index. Với bảng con lớn, việc cascade có thể tốn thời gian, giữ khóa lâu và làm tăng nguy cơ deadlock. Nếu khóa cha là định danh kỹ thuật, nên ưu tiên tính bất biến của nó; thay đổi tên hoặc mã hiển thị có thể được thực hiện trên một cột nghiệp vụ riêng.

## 7. Cập nhật cột không tham gia khóa ngoại

Không phải mọi thay đổi ở hàng cha đều làm thay đổi quan hệ FK. Ví dụ, đổi `department_name` không làm thay đổi `department_id`:

```sql
UPDATE department
SET department_name = 'Engineering'
WHERE department_id = 10;
```

Thao tác này không làm mất hiệu lực giá trị `employee.department_id = 10`. Ràng buộc FK chỉ quan tâm đến khóa được tham chiếu và sự tồn tại của hàng cha theo khóa đó.

Tuy vậy, update cột không phải khóa vẫn có thể xung đột với delete hoặc update khác trên cùng hàng vì cơ chế khóa hàng của hệ quản trị. Một số engine phân biệt mức khóa cập nhật cột khóa và cột không khóa; một số cơ chế MVCC có cách xử lý khác. Vì vậy:

- Không giả định mọi update trên hàng cha đều cần khóa giống như đổi khóa chính.
- Không giả định update cột tên có thể chạy song song với delete mà không chờ.
- Nếu nghiệp vụ yêu cầu hàng cha phải ở trạng thái `ACTIVE` khi thêm con, FK thông thường chưa đủ; cần bảo vệ thêm quy tắc trạng thái.

## 8. FK không tự bảo vệ mọi quy tắc nghiệp vụ của hàng cha

Giả sử chỉ được phép thêm nhân viên vào phòng ban đang hoạt động. FK chỉ bảo đảm phòng ban tồn tại; nó không tự kiểm tra `department.status = 'ACTIVE'`.

Một cách triển khai có thể đọc trạng thái cha rồi thêm con:

```sql
SELECT status
FROM department
WHERE department_id = :department_id;

-- Nếu ACTIVE thì INSERT employee.
```

Đây vẫn có race condition nếu transaction khác đổi phòng ban sang `INACTIVE` sau lần đọc. Nếu yêu cầu là trạng thái phải còn ACTIVE tại thời điểm tạo liên kết, cần một cơ chế đồng bộ chung:

- Khóa hàng cha theo chế độ phù hợp trước khi kiểm tra trạng thái và thêm con.
- Yêu cầu transaction chuyển cha sang `INACTIVE` cũng lấy khóa theo giao thức tương ứng.
- Hoặc biểu diễn điều kiện bằng một mô hình dữ liệu/constraint phù hợp nếu hệ quản trị hỗ trợ.

Điều quan trọng là mọi đường thay đổi trạng thái cha và mọi đường thêm con phải tuân thủ cùng giao thức. Nếu chỉ bên thêm con khóa cha còn bên vô hiệu hóa cha bỏ qua quy tắc, invariant vẫn có thể bị phá vỡ.

## 9. Index ở phía con và chi phí xóa cha

Khi xóa hoặc đổi khóa cha, hệ quản trị cần tìm các hàng con đang tham chiếu. Nếu bảng con có nhiều dữ liệu và cột FK không có index phù hợp, việc tìm kiếm có thể phải quét nhiều hàng.

Ví dụ, truy vấn logic cần tìm:

```sql
SELECT employee_id
FROM employee
WHERE department_id = 10;
```

Index trên `employee(department_id)` có thể giúp tìm các hàng con nhanh hơn. Điều này thường rút ngắn thời gian kiểm tra FK hoặc thực hiện cascade, qua đó giảm thời gian transaction giữ khóa và giảm thời gian các transaction khác phải chờ.

Index con không làm thay đổi quy tắc đúng/sai của FK, nhưng có thể ảnh hưởng hiệu năng và lock footprint. Khi thiết kế index, cân nhắc:

- Các truy vấn và thao tác xóa/cập nhật cha thường dùng cột FK nào.
- FK gồm một cột hay nhiều cột; thứ tự cột index có phù hợp với predicate hay không.
- Chi phí ghi thêm index khi insert/update/delete hàng con.
- Hệ quản trị có tự tạo index con hay không.

Không nên giả định một index đơn cột luôn phù hợp cho FK ghép nhiều cột. Hãy xem kế hoạch truy vấn và thống kê trên dữ liệu thực tế.

## 10. Deadlock liên quan đến FK và hành động cascade

FK có thể tạo ra khóa ngầm mà ứng dụng không nhìn thấy trong câu SQL. Khi một transaction thay đổi hàng con, hệ quản trị có thể cần xác nhận hàng cha. Khi transaction khác xóa hàng cha, hệ quản trị có thể phải tìm và khóa hàng con để kiểm tra hoặc cascade.

Một lịch có thể tạo vòng chờ nếu hai transaction đã giữ tài nguyên ở hai phía theo thứ tự khác nhau. Ví dụ khái quát:

```text
T1: khóa hàng con C
    cần xác nhận/khóa hàng cha P

T2: khóa hàng cha P
    cần khóa hàng con C để xóa hoặc cascade
```

Nếu T1 chờ P trong khi T2 chờ C, có thể hình thành deadlock. Đây là mô hình minh họa; loại khóa và thứ tự cụ thể phụ thuộc engine, hành động FK, index và câu lệnh.

Các tình huống dễ làm tăng rủi ro:

- Xóa nhiều hàng cha theo các thứ tự khác nhau trong hai transaction.
- Một transaction cập nhật hàng con trước rồi thay đổi cha; transaction khác thay đổi cha trước rồi cascade xuống con.
- Cascade qua nhiều cấp quan hệ cha–con.
- Trigger hoặc stored procedure truy cập thêm bảng theo thứ tự khác nhau.
- Bảng con thiếu index phù hợp khiến việc tìm hàng tham chiếu kéo dài.

Để giảm deadlock:

1. Xác định thứ tự tài nguyên nhất quán cho các thao tác nghiệp vụ có thể giao nhau.
2. Giữ transaction ngắn và tránh chờ bên ngoài trong lúc đang giữ khóa.
3. Tạo index phù hợp trên cột FK để việc tìm hàng con hiệu quả.
4. Chia thao tác xóa/cập nhật lớn thành batch nếu có thể mà vẫn giữ đúng quy tắc nghiệp vụ.
5. Đọc deadlock graph hoặc lock wait metadata để biết chính xác tài nguyên nào tạo vòng chờ.
6. Xử lý deadlock bằng cách rollback và retry toàn bộ transaction khi thao tác có thể lặp an toàn.

Không có một thứ tự “cha trước, con sau” hoặc “con trước, cha sau” đúng cho mọi hệ quản trị và mọi hành động FK. Cần tính cả khóa ngầm do engine lấy và kiểm tra bằng deadlock graph trên đúng sản phẩm.

## 11. Isolation level và thời điểm kiểm tra FK

FK là ràng buộc toàn vẹn dữ liệu do hệ quản trị thực thi. Ứng dụng không nên cho rằng chỉ cần dùng `SERIALIZABLE` mới có thể giữ FK đúng, hoặc `READ COMMITTED` thì kiểm tra FK không an toàn. Hệ quản trị phải phối hợp thao tác ghi với constraint theo cách phù hợp với isolation level và cơ chế nội bộ.

Tuy nhiên, isolation level ảnh hưởng đến cách transaction đọc dữ liệu khác và cách engine phát hiện xung đột. Một transaction có thể bị hủy do deadlock hoặc serialization failure ngay cả khi câu lệnh FK về mặt nghiệp vụ hợp lệ. Ứng dụng cần phân biệt:

- **FK violation:** giá trị tham chiếu không hợp lệ hoặc hành động `RESTRICT/NO ACTION` không được phép.
- **Deadlock victim:** transaction bị chọn rollback để phá vòng chờ.
- **Serialization failure:** hệ quản trị từ chối transaction để bảo đảm lịch tuần tự hóa.
- **Timeout/lock wait timeout:** transaction chờ khóa quá thời hạn cấu hình.

Các lỗi này cần phản hồi khác nhau. FK violation thường là kết quả nghiệp vụ hoặc lỗi dữ liệu; deadlock và serialization failure có thể phù hợp để retry toàn bộ transaction; timeout có thể cần retry có giới hạn hoặc trả lỗi tạm thời.

## 12. Cách kiểm thử cập nhật/xóa cha đồng thời với thao tác con

Kiểm thử phải dùng ít nhất hai connection độc lập và điều khiển thứ tự xen kẽ. Chỉ chạy các câu lệnh tuần tự sẽ không kiểm tra được race condition.

### Kịch bản 1: thêm con đồng thời xóa cha với `RESTRICT`

1. Tạo phòng ban 10, chưa có nhân viên.
2. Connection A bắt đầu transaction và insert nhân viên tham chiếu 10, nhưng tạm dừng trước commit.
3. Connection B bắt đầu transaction và thử delete phòng ban 10.
4. Quan sát B chờ, bị từ chối hoặc xử lý theo ngữ nghĩa của engine.
5. Cho A commit, sau đó kiểm tra kết quả của B.
6. Xác nhận không thể có nhân viên tham chiếu đến phòng ban đã bị xóa.

Lặp lại với thứ tự ngược: B xóa cha trước nhưng chưa commit, sau đó A thử insert con. Nếu B commit, A phải bị từ chối; nếu B rollback, A có thể tiếp tục khi FK được kiểm tra lại.

### Kịch bản 2: xóa cha với `CASCADE`

1. Tạo cha và một số hàng con.
2. A thêm một hàng con trong lúc B xóa cha.
3. Kiểm tra kết quả theo transaction nào hoàn tất trước.
4. Sau khi cả hai kết thúc, xác nhận không còn hàng con mồ côi; nếu xóa cha commit thành công, các hàng con thuộc phạm vi cascade cũng phải được xử lý.

### Kịch bản 3: đổi khóa cha với `ON UPDATE CASCADE`

1. Tạo cha có khóa 10 và một số hàng con tham chiếu 10.
2. A thêm con tham chiếu 10 trong lúc B đổi khóa cha từ 10 sang 20.
3. Kiểm tra A chờ hay B chờ và trạng thái cuối cùng.
4. Xác nhận các hàng con hợp lệ tham chiếu khóa mới theo quy tắc cascade; không có hàng con trỏ đến khóa cũ đã biến mất.

### Kịch bản 4: cascade nhiều cấp và deadlock

1. Tạo quan hệ cha–con–cháu với nhiều hàng.
2. Chạy hai transaction xóa/cập nhật các hàng cha theo thứ tự ngược nhau.
3. Thu thập deadlock graph và lock wait.
4. Thử lại transaction bị rollback và xác nhận không có dữ liệu mồ côi hoặc cascade một phần được commit.

Sau mỗi kịch bản, kiểm tra trực tiếp tính toàn vẹn bằng truy vấn tìm hàng con không có cha:

```sql
SELECT e.employee_id, e.department_id
FROM employee e
LEFT JOIN department d
  ON d.department_id = e.department_id
WHERE e.department_id IS NOT NULL
  AND d.department_id IS NULL;
```

Kết quả phải rỗng nếu FK đang bật và không có ngoại lệ dữ liệu ngoài phạm vi kiểm soát. Bài kiểm thử cũng cần xác nhận hành động cascade, set null hoặc lỗi constraint đúng như cấu hình.

## 13. Quan sát trong vận hành

Khi một thao tác xóa hoặc cập nhật cha bị chậm, hãy thu thập:

- Transaction nào đang giữ khóa và transaction nào đang chờ.
- Tài nguyên bị chờ thuộc hàng cha, hàng con, index, khoảng khóa hay bảng.
- Câu lệnh và kế hoạch truy cập đang tìm hàng con như thế nào.
- Có cascade hoặc trigger nào mở rộng phạm vi cập nhật không.
- Thời gian transaction và số lượng hàng con bị ảnh hưởng.
- Deadlock graph, lock wait event và lỗi constraint thực tế.

Không nên chỉ nhìn log ứng dụng rồi kết luận “FK chậm”. Có thể nguyên nhân là thiếu index phía con, cascade quá lớn, transaction giữ khóa quá lâu, một trigger cập nhật bảng khác hoặc hai luồng lấy khóa theo thứ tự trái ngược.

## 14. Nguyên tắc thiết kế an toàn

- Khai báo FK thực sự trong cơ sở dữ liệu; không chỉ kiểm tra tồn tại bằng code ứng dụng.
- Chọn `RESTRICT`, `NO ACTION`, `CASCADE`, `SET NULL` hoặc `SET DEFAULT` theo vòng đời nghiệp vụ.
- Dùng khóa cha ổn định, bất biến nếu không có nhu cầu nghiệp vụ rõ ràng để thay đổi khóa được tham chiếu.
- Tạo index phù hợp ở phía con khi thao tác cha cần tìm nhiều hàng tham chiếu.
- Giữ transaction ngắn và xác định thứ tự truy cập nhất quán, có tính đến khóa ngầm từ FK.
- Với quy tắc ngoài phạm vi FK như “cha phải ACTIVE”, thiết kế cơ chế phối hợp riêng.
- Phân biệt FK violation với deadlock, serialization failure và timeout để xử lý đúng.
- Khi retry deadlock hoặc serialization failure, chạy lại toàn bộ transaction và bảo vệ tác dụng phụ bên ngoài khỏi bị lặp.
- Kiểm thử cả hai thứ tự xen kẽ: con trước cha và cha trước con.

## 15. Checklist khi hàng cha bị cập nhật hoặc xóa đồng thời

- [ ] FK được khai báo và bật trên đúng cột, đúng khóa cha.
- [ ] Đã xác định cột nào thực sự là khóa được tham chiếu; update cột không khóa được phân biệt với đổi khóa.
- [ ] Đã chọn hành động `ON DELETE` và `ON UPDATE` phù hợp với vòng đời dữ liệu.
- [ ] Đã hiểu `RESTRICT` và `NO ACTION` cùng khả năng trì hoãn constraint trên hệ quản trị.
- [ ] Đã có index phù hợp để tìm hàng con khi xóa hoặc đổi khóa cha.
- [ ] Đã tính đến cascade, trigger, foreign key lồng nhau và khóa ngầm.
- [ ] Đã kiểm tra các quy tắc nghiệp vụ bổ sung như trạng thái ACTIVE của hàng cha.
- [ ] Đã kiểm thử insert/update con đồng thời với delete/update khóa cha bằng nhiều connection.
- [ ] Đã thu thập lock wait/deadlock graph cho các trường hợp cạnh tranh.
- [ ] Đã có cách xử lý FK violation, deadlock, serialization failure và timeout phù hợp.

Khóa ngoại giúp cơ sở dữ liệu bảo vệ quan hệ cha–con ngay cả khi nhiều transaction thao tác đồng thời. Khi thiết kế, cần hiểu hành động tham chiếu, thời điểm kiểm tra constraint, index phía con và những khóa ngầm phát sinh từ cascade. Ứng dụng nên dựa vào FK để bảo đảm tính toàn vẹn, phối hợp thêm các quy tắc nghiệp vụ ngoài FK bằng một giao thức khóa rõ ràng, và kiểm thử cả hai thứ tự xen kẽ của thao tác cha và con trên hệ quản trị thực tế.

# Bất biến trên quan hệ cha–con khi thêm hoặc xóa đồng thời

Trong mô hình dữ liệu quan hệ cha–con, một hàng cha có thể liên kết với nhiều hàng con. Ví dụ, một dự án có nhiều thành viên, một đơn hàng có nhiều dòng hàng, hoặc một phòng ban có nhiều nhân viên. Khi nhiều giao dịch cùng thêm, xóa hoặc chuyển hàng con giữa các hàng cha, dữ liệu có thể vẫn thỏa khóa ngoại nhưng lại vi phạm một quy tắc nghiệp vụ liên quan đến cả nhóm.

Điểm quan trọng là cần phân biệt hai loại bất biến:

- **Toàn vẹn tham chiếu:** mỗi hàng con phải trỏ đến một hàng cha đang tồn tại. Khóa ngoại (`FOREIGN KEY`) bảo vệ quy tắc này.
- **Bất biến nghiệp vụ trên tập con:** ví dụ một dự án đang hoạt động phải có ít nhất một thành viên đang hoạt động, hoặc một phòng ban không được xóa nhân viên cuối cùng. Khóa ngoại đơn thuần không bảo vệ được điều kiện đếm hoặc điều kiện tổng hợp này.

Khi thao tác thêm và xóa diễn ra đồng thời, các giao dịch có thể đọc cùng một trạng thái cũ rồi cập nhật những hàng con khác nhau. Để bảo vệ bất biến trên cả nhóm, cần một điểm điều phối chung, một mức cô lập đủ mạnh hoặc một cách thiết kế dữ liệu để DBMS kiểm tra điều kiện đó.

## 1. Mô hình cha–con và các quy tắc cần bảo vệ

Giả sử ứng dụng quản lý dự án. Mỗi dự án có nhiều thành viên và dự án đang hoạt động phải luôn có ít nhất một thành viên đang hoạt động.

```sql
CREATE TABLE projects (
    project_id BIGINT PRIMARY KEY,
    project_name VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE project_members (
    member_id BIGINT PRIMARY KEY,
    project_id BIGINT NOT NULL,
    employee_id BIGINT NOT NULL,
    active BOOLEAN NOT NULL,
    CONSTRAINT fk_member_project
        FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
        ON DELETE RESTRICT
);
```

Khóa ngoại bảo đảm `project_members.project_id` tham chiếu đến một dự án tồn tại. `ON DELETE RESTRICT` biểu đạt rằng không được xóa dự án khi vẫn còn hàng thành viên tham chiếu đến nó. Nếu hệ thống muốn xóa dự án và toàn bộ thành viên cùng lúc, có thể chọn `ON DELETE CASCADE`; đây là một quy tắc nghiệp vụ khác.

Quy tắc “dự án đang hoạt động phải có ít nhất một thành viên đang hoạt động” là một điều kiện khác. Nó không thể được diễn đạt bằng khóa ngoại trên vì khóa ngoại chỉ kiểm tra rằng hàng cha tồn tại, không kiểm tra số lượng hàng con thỏa một điều kiện.

Ví dụ trạng thái hợp lệ:

| project_id | member_id | active |
|---:|---:|---:|
| 7 | 101 | TRUE |
| 7 | 102 | TRUE |

Nếu cả hai thành viên chuyển sang `active = FALSE` trong khi dự án vẫn `ACTIVE`, quy tắc nghiệp vụ bị vi phạm dù mọi `project_id` vẫn tham chiếu đến hàng cha hợp lệ.

## 2. Vì sao kiểm tra COUNT trước khi xóa có thể sai?

Một cách triển khai đơn giản là:

1. Đếm số thành viên đang hoạt động của dự án.
2. Nếu còn nhiều hơn một người, cho phép xóa hoặc vô hiệu hóa một thành viên.
3. Nếu chỉ còn một người, từ chối thao tác.

Giả sử dự án 7 có hai thành viên đang hoạt động: An và Bình. Hai yêu cầu đồng thời muốn vô hiệu hóa mỗi người một giao dịch.

```text
T1: xử lý yêu cầu vô hiệu hóa An       T2: xử lý yêu cầu vô hiệu hóa Bình
---------------------------------     -------------------------------------
BEGIN                                 BEGIN
COUNT(active members) = 2             COUNT(active members) = 2
Kiểm tra: 2 > 1                       Kiểm tra: 2 > 1
UPDATE An.active = FALSE              UPDATE Bình.active = FALSE
COMMIT                                COMMIT

Kết quả: dự án còn 0 thành viên active.
```

Hai giao dịch đọc cùng trạng thái ban đầu nhưng ghi vào hai hàng con khác nhau. Cơ chế phát hiện xung đột ghi cùng hàng có thể không thấy xung đột vì `T1` cập nhật hàng An còn `T2` cập nhật hàng Bình. Cả hai có thể commit, làm cho bất biến “ít nhất một thành viên đang hoạt động” bị phá vỡ.

Đây là một dạng **write skew** trên quan hệ cha–con. Vấn đề không nằm ở việc một lần ghi ghi đè lần ghi kia. Hai lần ghi đều được giữ; chính kết quả kết hợp của chúng làm sai điều kiện nghiệp vụ trên tập con.

## 3. Khóa ngoại bảo vệ quan hệ cha–con khi thêm và xóa đồng thời

Xét một tình huống khác: `T1` muốn xóa dự án 7, trong khi `T2` muốn thêm một thành viên mới cho dự án 7.

Nếu chỉ kiểm tra bằng ứng dụng:

```sql
SELECT project_id
FROM projects
WHERE project_id = 7;

-- Nếu tìm thấy thì INSERT thành viên.
```

vẫn có khoảng trống giữa bước đọc và bước chèn. Một giao dịch khác có thể xóa dự án trong khoảng thời gian đó.

Khóa ngoại là hàng rào toàn vẹn ở database. Khi chèn hàng con, DBMS kiểm tra hàng cha tham chiếu có tồn tại. Khi xóa hàng cha, DBMS kiểm tra các hàng con theo hành vi `ON DELETE` đã khai báo. Các thao tác cạnh tranh phải được điều phối theo cơ chế khóa và kiểm tra ràng buộc của DBMS; không thể commit một hàng con mồ côi nếu khóa ngoại được bật và được thực thi.

Kết quả cụ thể phụ thuộc hành vi khóa và constraint của DBMS:

- Với `ON DELETE RESTRICT` hoặc `NO ACTION`, thao tác xóa cha có thể phải chờ giao dịch chèn con; sau đó việc xóa có thể thất bại vì hàng con đã tồn tại.
- Nếu thao tác xóa cha hoàn tất trước, thao tác chèn con có thể thất bại vì không còn hàng cha để tham chiếu.
- Với `ON DELETE CASCADE`, xóa cha có thể kéo theo xóa các hàng con theo quy tắc cascade; giao dịch chèn con cạnh tranh vẫn phải tuân theo kiểm tra khóa ngoại.

Điều cần nhớ: **FOREIGN KEY ngăn orphan (hàng con mồ côi), nhưng không tự bảo đảm dự án đang hoạt động phải có ít nhất một thành viên đang hoạt động.**

## 4. Khóa hàng cha làm điểm điều phối chung

Để bảo vệ bất biến “mỗi dự án đang hoạt động có ít nhất một thành viên hoạt động”, các giao dịch có thể khóa hàng cha trước khi đọc hoặc thay đổi tập hàng con.

Hàng cha đóng vai trò **guard row (hàng điều phối)**. Mọi thao tác có thể làm thay đổi điều kiện của nhóm thành viên phải lấy cùng một khóa trên hàng dự án trước khi đếm, thêm, xóa hoặc chuyển trạng thái thành viên.

Ví dụ với PostgreSQL:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

-- Khóa dự án trước khi kiểm tra các thành viên.
SELECT project_id, status
FROM projects
WHERE project_id = 7
FOR UPDATE;

-- Đếm thành viên đang hoạt động sau khi đã lấy khóa guard.
SELECT COUNT(*)
FROM project_members
WHERE project_id = 7
  AND active = TRUE;

-- Nếu số lượng lớn hơn 1, mới vô hiệu hóa thành viên cần xóa.
UPDATE project_members
SET active = FALSE
WHERE project_id = 7
  AND member_id = 101;

COMMIT;
```

Ứng dụng phải kiểm tra kết quả `COUNT(*)` và chỉ chạy `UPDATE` khi điều kiện cho phép. Nếu không đủ thành viên, transaction kết thúc mà không thay đổi dữ liệu.

### Vì sao khóa hàng cha giải quyết được write skew?

Giả sử `T1` và `T2` đều khóa hàng `projects.project_id = 7` bằng `FOR UPDATE`:

1. `T1` lấy được khóa hàng cha.
2. `T2` yêu cầu cùng khóa và phải chờ.
3. `T1` đếm thành viên, kiểm tra điều kiện, cập nhật An rồi commit.
4. `T1` giải phóng khóa hàng cha.
5. `T2` lấy được khóa và thực hiện kiểm tra trên trạng thái mới nhất theo semantics của DBMS.
6. `T2` thấy chỉ còn một thành viên đang hoạt động nên từ chối vô hiệu hóa Bình.

```text
T1: khóa project 7 ── đếm = 2 ── vô hiệu hóa An ── COMMIT
       │
       └── T2 chờ khóa project 7 ──────────────────────┐
                                                       ▼
T2:                           lấy khóa ── đếm = 1 ── từ chối xóa Bình
```

Điểm quyết định là cả hai giao dịch phải tranh chấp trên **cùng một hàng cha**, dù chúng cập nhật các hàng con khác nhau.

Ví dụ này dùng PostgreSQL `READ COMMITTED`: mỗi câu lệnh đọc có snapshot mới. Vì vậy, sau khi `T2` chờ lấy khóa cha và được tiếp tục, câu `COUNT(*)` kế tiếp nhìn thấy các thay đổi đã commit của `T1`. Ở isolation level dùng snapshot cố định như PostgreSQL `REPEATABLE READ`, chỉ khóa hàng cha rồi chạy một câu đọc thường có thể vẫn đếm trên snapshot cũ đã được tạo trước khi chờ. Với mức cô lập đó, cần dùng chiến lược có xung đột ghi trên hàng guard để transaction cũ bị phát hiện và retry, dùng locking/current read phù hợp với DBMS, hoặc chọn `SERIALIZABLE`. Không được giả định một câu `SELECT ... FOR UPDATE` tự làm mới snapshot của toàn transaction.

### Điều kiện để guard row có hiệu lực

Khóa hàng cha chỉ bảo vệ bất biến nếu mọi đường ghi có thể làm thay đổi điều kiện đều tuân theo cùng giao thức:

- Thêm thành viên phải khóa hàng cha trước khi chèn.
- Xóa hoặc vô hiệu hóa thành viên phải khóa hàng cha trước khi đếm và cập nhật.
- Chuyển thành viên từ dự án này sang dự án khác phải điều phối cả hai dự án.
- Tác vụ nền, import, admin tool và batch job cũng phải tuân theo giao thức.

Ví dụ một giao dịch thêm thành viên cũng lấy cùng khóa guard trước khi chèn:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT project_id, status
FROM projects
WHERE project_id = 7
FOR UPDATE;

-- Ứng dụng xác nhận dự án còn cho phép nhận thành viên.
INSERT INTO project_members (
    member_id, project_id, employee_id, active
)
VALUES (103, 7, 203, TRUE);

COMMIT;
```

Nếu dự án không tồn tại hoặc không còn ở trạng thái cho phép thêm thành viên, ứng dụng phải dừng transaction. Khóa guard cần được lấy trước khi đọc trạng thái và thêm con, trong cùng transaction.

Nếu một đường ghi bỏ qua khóa guard, giao dịch đó có thể thay đổi tập con trong khi giao dịch khác đang dựa vào kết quả kiểm tra. Khi đó, bất biến lại có thể bị phá vỡ.

## 5. Thêm thành viên đồng thời với xóa thành viên cuối cùng

Giả sử dự án chỉ còn một thành viên hoạt động là An. `T1` muốn vô hiệu hóa An; `T2` muốn thêm Bình.

Nếu hai thao tác cùng khóa hàng cha trước khi kiểm tra, kết quả được tuần tự hóa:

**Trường hợp T1 lấy khóa trước:**

1. T1 khóa dự án 7 và đếm được một thành viên.
2. T1 từ chối vô hiệu hóa An vì đây là thành viên cuối cùng.
3. T1 commit/rollback và nhả khóa.
4. T2 lấy khóa, thêm Bình và commit.

**Trường hợp T2 lấy khóa trước:**

1. T2 khóa dự án 7, thêm Bình và commit.
2. T1 lấy khóa sau đó và đếm được hai thành viên.
3. T1 có thể vô hiệu hóa An vì Bình vẫn hoạt động.
4. T1 commit; dự án vẫn còn một thành viên.

Ở cả hai thứ tự, quy tắc “ít nhất một thành viên hoạt động” được giữ. Nếu T2 chỉ chèn con mà không lấy khóa guard, T1 có thể đếm trên trạng thái không bao gồm hàng mới tùy snapshot/isolation level và quyết định sai. Do đó, thao tác thêm cũng phải tham gia giao thức điều phối nếu nó có thể ảnh hưởng đến kết luận.

## 6. Thêm hoặc chuyển hàng con giữa hai hàng cha

Một hàng con có thể được chuyển từ dự án 7 sang dự án 8. Đây không chỉ là một lần cập nhật `project_id`; nó có thể làm giảm số thành viên của cha nguồn và tăng số thành viên của cha đích.

Nếu cả hai dự án đều có quy tắc ít nhất một thành viên hoạt động, transaction chuyển thành viên phải bảo vệ cả hai bất biến.

Một cách làm là khóa hai hàng cha theo thứ tự `project_id` tăng dần:

```sql
BEGIN;

-- Luôn khóa theo cùng thứ tự để giảm deadlock.
SELECT project_id
FROM projects
WHERE project_id IN (7, 8)
ORDER BY project_id
FOR UPDATE;

-- Đếm thành viên active của dự án nguồn sau khi đã khóa.
SELECT COUNT(*)
FROM project_members
WHERE project_id = 7
  AND active = TRUE;

-- Chỉ chuyển nếu dự án nguồn vẫn còn ít nhất một thành viên.
UPDATE project_members
SET project_id = 8
WHERE member_id = 101
  AND project_id = 7;

COMMIT;
```

Ứng dụng cần kiểm tra số lượng và trạng thái trả về trước khi cập nhật. Nếu dự án nguồn chỉ còn một thành viên, transaction không được chuyển người đó đi. Dự án đích cũng cần được kiểm tra còn hoạt động và cho phép nhận thành viên.

Khóa hai cha theo thứ tự cố định giúp giảm tình huống `T1` khóa cha 7 rồi chờ cha 8 trong khi `T2` khóa cha 8 rồi chờ cha 7. Quy tắc thứ tự phải thống nhất ở tất cả luồng xử lý.

Nếu một thành viên có thể thuộc nhiều nhóm, hoặc việc chuyển thành viên tác động đến nhiều bất biến khác, cần mở rộng phạm vi khóa tương ứng.

## 7. Dùng Serializable Isolation thay cho khóa guard

Một lựa chọn khác là chạy thao tác ở mức `SERIALIZABLE`. DBMS phải bảo đảm lịch thực thi tương đương với một thứ tự tuần tự hợp lệ. Nếu hai giao dịch đọc tập con giống nhau rồi xóa hai hàng khác nhau tạo ra write skew, một giao dịch có thể bị hủy với serialization failure.

Ví dụ:

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM project_members
WHERE project_id = 7
  AND active = TRUE;

-- Chỉ vô hiệu hóa nếu còn nhiều hơn một thành viên.
UPDATE project_members
SET active = FALSE
WHERE project_id = 7
  AND member_id = 101;

COMMIT;
```

Nếu DBMS phát hiện phụ thuộc không thể tuần tự hóa, transaction có thể thất bại khi chạy hoặc commit. Ứng dụng phải rollback và retry **toàn bộ transaction**, bắt đầu từ bước đọc và kiểm tra. Không được chỉ chạy lại câu `UPDATE` cuối vì kết luận dựa trên `COUNT(*)` cũ có thể không còn đúng.

Serializable là cách diễn đạt trực tiếp yêu cầu kết quả tuần tự, nhưng có thể tạo thêm serialization failure và retry dưới tải cao. Khóa guard có thể dễ dự đoán hơn khi mỗi bất biến có một hàng cha rõ ràng, nhưng yêu cầu mọi đường ghi tuân thủ giao thức.

## 8. Duy trì bộ đếm ở hàng cha

Nếu ứng dụng thường xuyên cần biết số lượng thành viên đang hoạt động, có thể lưu một bộ đếm như `active_member_count` trên hàng cha.

```sql
ALTER TABLE projects
ADD COLUMN active_member_count INTEGER NOT NULL DEFAULT 0;
```

Khi thêm thành viên, tăng bộ đếm; khi vô hiệu hóa hoặc xóa thành viên, giảm bộ đếm. Các thay đổi ở hàng con và bộ đếm cha phải nằm trong cùng transaction.

Ví dụ, thao tác vô hiệu hóa có thể cập nhật bộ đếm có điều kiện:

```sql
BEGIN;

UPDATE projects
SET active_member_count = active_member_count - 1
WHERE project_id = 7
  AND active_member_count > 1;

-- Chỉ tiếp tục nếu đúng một hàng dự án được cập nhật.
UPDATE project_members
SET active = FALSE
WHERE project_id = 7
  AND member_id = 101
  AND active = TRUE;

COMMIT;
```

Đây chỉ là khung minh họa. Ứng dụng phải xác nhận câu cập nhật bộ đếm thành công và câu cập nhật thành viên thực sự thay đổi đúng một hàng; nếu bất kỳ điều kiện nào không đạt, rollback toàn transaction. Cần tránh giảm bộ đếm khi thành viên vốn đã inactive hoặc không thuộc dự án đó.

Ưu điểm là hàng cha trở thành điểm ghi chung, và điều kiện `active_member_count > 1` được kiểm tra trong câu cập nhật nguyên tử. Nhưng bộ đếm là dữ liệu dẫn xuất; nếu có một đường ghi cập nhật bảng con mà quên cập nhật bộ đếm, hai nguồn dữ liệu sẽ lệch nhau. Có thể dùng trigger hoặc một service/repository duy nhất để quản lý mọi thay đổi, kèm quy trình đối soát bộ đếm.

Một phương án khác là dùng `UPDATE ... RETURNING` hoặc cơ chế trả về số hàng cập nhật của DBMS để xác nhận điều kiện đã được thỏa mãn. Chi tiết cú pháp khác nhau giữa các hệ quản trị.

## 9. Ràng buộc khóa ngoại và ON DELETE

Khi xóa hàng cha, lựa chọn hành vi khóa ngoại quyết định cách xử lý hàng con:

| Hành vi | Kết quả khi xóa hàng cha đang có con | Khi phù hợp |
|---|---|---|
| `RESTRICT` | Từ chối xóa khi còn hàng con | Không cho phép xóa cha trước khi xử lý hết con |
| `NO ACTION` | Kiểm tra ràng buộc theo thời điểm kiểm tra của DBMS/constraint | Muốn giữ toàn vẹn tham chiếu và có thể cần constraint trì hoãn nếu DBMS hỗ trợ |
| `CASCADE` | Tự động xóa các hàng con tham chiếu | Xóa cha đồng nghĩa xóa toàn bộ dữ liệu con |
| `SET NULL` | Đặt khóa ngoại ở hàng con thành NULL nếu cột cho phép | Hàng con có thể tồn tại độc lập sau khi cha bị xóa |
| `SET DEFAULT` | Đặt khóa ngoại về giá trị mặc định nếu hợp lệ | Có một cha mặc định phù hợp với nghiệp vụ |

Chọn `ON DELETE CASCADE` không phải cách tổng quát để bảo vệ bất biến “cha luôn có ít nhất một con”. Cascade thực hiện quy tắc xóa cả nhóm. Nếu nghiệp vụ cần giữ cha khi còn con, dùng `RESTRICT`/`NO ACTION` phù hợp.

Khóa ngoại cũng không tự bảo đảm mỗi dự án có ít nhất một thành viên đang hoạt động. Để biểu diễn quy tắc đó, cần cơ chế kiểm soát trên tập con như guard lock, Serializable Isolation, bộ đếm có kiểm soát hoặc thiết kế dữ liệu phù hợp.

## 10. Thứ tự khóa và deadlock khi thao tác nhiều cha–con

Các thao tác thêm, xóa hoặc chuyển hàng con có thể khóa nhiều hàng cha và nhiều hàng con. Nếu các transaction lấy khóa theo thứ tự khác nhau, deadlock có thể xảy ra.

Ví dụ:

```text
T1: khóa project 7 → yêu cầu khóa project 8
T2: khóa project 8 → yêu cầu khóa project 7

T1 chờ T2; T2 chờ T1.
```

Hãy thống nhất thứ tự lấy khóa, chẳng hạn:

1. Khóa tất cả hàng cha theo `project_id` tăng dần.
2. Sau đó khóa hoặc cập nhật các hàng con theo `member_id` tăng dần.
3. Giữ thứ tự đó ở mọi luồng thêm, xóa, chuyển và batch job.

Thứ tự ổn định giảm nguy cơ deadlock nhưng không loại bỏ mọi deadlock do các tài nguyên khác hoặc trigger có thể lấy khóa bổ sung. Ứng dụng vẫn phải xử lý deadlock victim và retry toàn bộ transaction khi phù hợp.

## 11. Chọn cơ chế bảo vệ phù hợp

| Cơ chế | Bảo vệ điều gì? | Ưu điểm | Điều kiện/cái giá |
|---|---|---|---|
| `FOREIGN KEY` | Hàng con không tham chiếu cha không tồn tại | Ràng buộc rõ ràng, DBMS tự thực thi | Không bảo vệ số lượng hoặc trạng thái tổng hợp của con |
| `ON DELETE RESTRICT` | Không xóa cha khi còn con | Ngăn xóa cha vô tình | Không bảo vệ “ít nhất một con active” khi cha vẫn tồn tại |
| Khóa hàng cha (guard row) | Tuần tự hóa mọi thay đổi tập con của cùng cha | Dễ mô hình hóa theo phạm vi nghiệp vụ | Mọi đường ghi phải lấy cùng khóa; tăng tranh chấp trên cha |
| `SERIALIZABLE` | Các phụ thuộc đọc/ghi gây lịch không tuần tự hóa | Bảo vệ nhiều quy tắc phức tạp | Có thể serialization failure; ứng dụng cần retry |
| Bộ đếm trên cha | Điều kiện đếm được kiểm tra qua một hàng chung | Có thể kiểm tra và cập nhật nguyên tử | Phải duy trì bộ đếm chính xác trong mọi đường ghi |
| Thiết kế lại dữ liệu | Chuyển bất biến thành ràng buộc trực tiếp hơn | Có thể giảm logic kiểm tra nhiều hàng | Cần mô hình hóa cẩn thận và có thể thay đổi cấu trúc dữ liệu |

Với dự án phải có ít nhất một thành viên hoạt động, khóa hàng cha là một lựa chọn dễ hiểu: mọi thay đổi thành viên của dự án đều khóa cùng hàng dự án trước khi kiểm tra. Nếu hệ thống có nhiều quy tắc phức tạp trên nhiều tập dữ liệu, Serializable Isolation có thể phù hợp hơn.

## 12. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra `COUNT(*)` rồi xóa | Hai transaction có thể cùng thấy số lượng cũ và xóa các hàng khác nhau | Khóa guard hoặc dùng Serializable |
| Cho rằng FOREIGN KEY bảo đảm cha luôn có con | FK chỉ ngăn con mồ côi, không bảo đảm số con tối thiểu | Bổ sung cơ chế bảo vệ bất biến nghiệp vụ |
| Chỉ khóa hàng con định xóa | Hai giao dịch xóa hai con khác nhau không tranh chấp khóa | Khóa hàng cha chung trước khi kiểm tra |
| Giao dịch thêm con không khóa guard nhưng giao dịch xóa có khóa | Tập con vẫn có thể thay đổi ngoài giao thức kiểm soát | Mọi đường ghi ảnh hưởng đến bất biến phải tham gia giao thức |
| Chuyển con giữa hai cha theo thứ tự khóa khác nhau | Có thể tạo deadlock | Khóa các cha theo thứ tự ID thống nhất |
| Dùng `ON DELETE CASCADE` dù muốn giữ con hoặc giữ cha | Xóa cha kéo theo xóa toàn bộ con | Chọn hành vi FK đúng với quy tắc nghiệp vụ |
| Duy trì bộ đếm nhưng có đường ghi bỏ qua bộ đếm | Bộ đếm lệch với dữ liệu con | Quản lý tập trung, trigger phù hợp và đối soát |
| Retry chỉ câu UPDATE sau serialization failure | Quyết định vẫn dựa trên kết quả đếm cũ | Rollback và chạy lại toàn bộ transaction |

## 13. Tự kiểm tra

**Tình huống 1:** Dự án 7 có An và Bình đều active. `T1` đếm được 2 rồi vô hiệu hóa An. `T2` cũng đếm được 2 rồi vô hiệu hóa Bình. Cả hai cập nhật hàng con khác nhau. Vì sao FOREIGN KEY không ngăn được kết quả cuối có 0 thành viên active?

**Đáp án:** Cả hai hàng con vẫn tham chiếu đến dự án 7 đang tồn tại. FOREIGN KEY chỉ bảo vệ quan hệ tham chiếu, không kiểm tra số lượng thành viên active. Đây là write skew trên tập con.

**Tình huống 2:** `T1` khóa hàng dự án 7 trước khi đếm và xóa An. `T2` cũng khóa hàng dự án 7 trước khi xóa Bình. Điều gì xảy ra?

**Đáp án:** Một giao dịch lấy khóa trước; giao dịch còn lại phải chờ. Sau khi giao dịch đầu commit, giao dịch sau kiểm tra trạng thái mới. Nếu chỉ còn một thành viên active, thao tác xóa cuối cùng bị từ chối.

**Tình huống 3:** Một giao dịch thêm thành viên mới vào dự án cùng lúc giao dịch khác muốn vô hiệu hóa thành viên cuối cùng. Vì sao giao dịch thêm cũng cần khóa guard?

**Đáp án:** Vì thao tác thêm làm thay đổi tập dữ liệu mà giao dịch xóa dùng để kiểm tra bất biến. Nếu thêm không tham gia cùng giao thức, kết quả đọc và quyết định có thể không phản ánh trạng thái sau cùng.

**Tình huống 4:** `T1` chuyển thành viên từ dự án 7 sang 8, còn `T2` chuyển một thành viên từ 8 sang 7. Vì sao nên khóa hai hàng cha theo cùng thứ tự?

**Đáp án:** Nếu T1 khóa 7 rồi chờ 8 trong khi T2 khóa 8 rồi chờ 7, hai giao dịch tạo deadlock. Cùng khóa theo thứ tự ID tăng dần giúp loại bỏ kiểu vòng chờ do thứ tự hai cha bị đảo.

**Tình huống 5:** Dự án có `ON DELETE CASCADE`. Xóa dự án sẽ ảnh hưởng đến hàng thành viên như thế nào?

**Đáp án:** DBMS tự xóa các hàng con tham chiếu theo quy tắc cascade. Đây là lựa chọn phù hợp nếu nghiệp vụ yêu cầu xóa cả nhóm; nó không có nghĩa là giữ dự án và bảo đảm luôn còn một thành viên active.

**Tình huống 6:** Dùng Serializable Isolation và nhận serialization failure ở bước commit. Ứng dụng nên retry phần nào?

**Đáp án:** Rollback và chạy lại toàn bộ transaction, gồm đọc tập con, kiểm tra điều kiện và cập nhật. Không chỉ chạy lại câu lệnh ghi cuối.

Khi bảo vệ một bất biến cha–con, hãy xác định điều kiện nào thuộc về khóa ngoại và điều kiện nào thuộc về toàn bộ tập con. Dùng `FOREIGN KEY` để ngăn hàng con mồ côi; dùng guard row, Serializable Isolation hoặc bộ đếm được duy trì nguyên tử để bảo vệ quy tắc như “ít nhất một con còn hoạt động”. Mọi thao tác thêm, xóa và chuyển con có thể ảnh hưởng đến cùng bất biến phải được điều phối theo một giao thức thống nhất.

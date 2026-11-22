# Lưu lịch sử thuộc tính và lịch sử quan hệ

## 1. Một thực thể có thể thay đổi thuộc tính và quan hệ theo những nhịp khác nhau

Trong **DATABASE_DATA_MODELING**, yêu cầu “cần xem dữ liệu tại một thời điểm trong quá khứ” chỉ được giải quyết đúng khi xác định **thứ gì đã thay đổi**: giá trị thuộc tính của một thực thể, quan hệ giữa các thực thể, hay cả hai. Đây là phần của chương **Thời gian và lịch sử**, gắn trực tiếp với nhiệm vụ chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, khóa, ràng buộc, chỉ mục và lược đồ vật lý có thể kiểm chứng.

Xét nhân viên số **42**. Đội nhân sự cần trả lời ba câu hỏi:

- Ngày **15/02/2026**, nhân viên có ngạch **JUNIOR** hay **SENIOR**?
- Cũng ngày đó, nhân viên thuộc **phòng ban nào**?
- Ngày **20/08/2026**, nhân viên ở ngạch nào, thuộc phòng nào, và hai giá trị có cùng hiệu lực tại thời điểm được hỏi không?

Giả sử dữ liệu nghiệp vụ được xác nhận như sau:

| Thuộc tính hoặc quan hệ | Giai đoạn hiệu lực | Giá trị |
|---|---|---|
| Ngạch nhân viên | [01/01/2026, 01/07/2026) | JUNIOR |
| Ngạch nhân viên | [01/07/2026, không giới hạn) | SENIOR |
| Phân công phòng chính | [01/01/2026, 01/04/2026) | Phòng A |
| Phân công phòng chính | [01/04/2026, 01/10/2026) | Phòng B |
| Phân công phòng chính | [01/10/2026, không giới hạn) | Phòng C |

Nhân viên không đổi danh tính qua các giai đoạn. **Ngạch** là một thuộc tính thay đổi theo thời gian. **Thuộc phòng ban** là một quan hệ thay đổi theo thời gian giữa hai thực thể. Nếu chỉ lưu một hàng nhân viên với ngạch và phòng ban mới nhất, dữ liệu hiện tại sẽ là **SENIOR, phòng C**, khiến câu hỏi về tháng 2 hoặc tháng 8 không còn căn cứ.

Bài học này hướng dẫn thiết kế hai dạng lịch sử, cách kết hợp chúng bằng **temporal join**, cách tránh mất dữ liệu khi cập nhật và cách chọn cơ chế phù hợp giữa cơ sở dữ liệu quan hệ, document, graph và kho phân tích.

**Mục tiêu học tập:** sau bài này, người học có thể phân biệt lịch sử thuộc tính với lịch sử quan hệ; tách các phiên bản theo nhịp thay đổi; chọn khóa và khoảng hiệu lực; viết truy vấn “as of”; giữ toàn vẹn lịch sử khi có cập nhật đồng thời; và nhận diện khi cần mở rộng sang lịch sử hai trục thời gian.

## 2. Lịch sử thuộc tính là gì?

**Lịch sử thuộc tính** (*attribute history*) ghi những giá trị mà một hoặc một nhóm thuộc tính của thực thể có hiệu lực tại từng giai đoạn. Ví dụ:

- Một nhân viên thay đổi ngạch chuyên môn từ JUNIOR sang SENIOR.
- Một sản phẩm thay đổi giá niêm yết hoặc thời hạn bảo hành.
- Một khách hàng thay đổi hạng thành viên.
- Một hợp đồng thay đổi hạn mức tín dụng hoặc chu kỳ thanh toán.
- Một tài khoản được chuyển trạng thái ACTIVE → SUSPENDED → ACTIVE.

Với thực thể nhân viên, **employee_id = 42** vẫn là một định danh ổn định. Lịch sử ngạch có thể gồm những phiên bản riêng:

~~~text
employee_id = 42

[2026-01-01, 2026-07-01)  grade = JUNIOR
[2026-07-01, +∞)          grade = SENIOR
~~~

Một bản ghi phiên bản thường gồm:

| Thành phần | Trách nhiệm |
|---|---|
| **entity_id** | Chỉ ra thực thể logic được phiên bản hóa |
| **version_id** | Định danh riêng của một phiên bản |
| **attribute value(s)** | Giá trị có hiệu lực trong phiên bản |
| **valid_from / valid_to** hoặc **valid_period** | Khoảng hiệu lực nghiệp vụ |
| **source_ref** | Nguồn quyết định hoặc tài liệu căn cứ |
| **recorded_at** | Thời điểm phiên bản được ghi vào hệ thống, phục vụ quan sát |

**version_id** không thay thế **entity_id**. Cũng không nên dùng số phiên bản tăng dần để suy đoán ngày hiệu lực: một quyết định có thể được ghi sớm cho tương lai hoặc đến muộn với hiệu lực hồi tố.

### 2.1. Chọn mức hạt của thuộc tính được phiên bản hóa

Không phải mọi thuộc tính của thực thể đều có cùng chu kỳ thay đổi. Giả sử nhân viên có **ngạch**, **địa chỉ liên hệ**, **phương thức thanh toán lương** và **ảnh hồ sơ**. Nếu mỗi lần sửa ảnh lại sinh một phiên bản đầy đủ chứa tất cả dữ liệu, lịch sử sẽ tăng nhanh và phát sinh nhiều bản sao không mang ý nghĩa mới cho ngạch.

Có ba cách thường gặp:

| Cách tổ chức | Ưu điểm | Đánh đổi |
|---|---|---|
| **Phiên bản toàn bộ thực thể** | Dễ lấy snapshot đầy đủ tại ngày D nếu mọi thay đổi đều được chụp | Dữ liệu lặp lớn; các thuộc tính độc lập bị gắn chung lịch sử |
| **Phiên bản một nhóm thuộc tính có cùng quy tắc** | Giữ ngữ nghĩa rõ, phù hợp khóa và ràng buộc từng miền | Temporal join khi dựng ảnh toàn bộ thực thể |
| **EAV/attribute-value theo từng thuộc tính** | Linh hoạt khi nhiều thuộc tính động | Khó kiểm tra kiểu, ràng buộc, đồng bộ thay đổi nhiều thuộc tính; truy vấn phức tạp |

Quy tắc thực dụng: **nhóm những thuộc tính cần thay đổi và xác nhận cùng nhau** vào một phiên bản, tách các thuộc tính có vòng đời hoặc điều kiện toàn vẹn khác nhau. Ví dụ **grade_code** và **grade_allowance** có thể nằm cùng phiên bản nếu một quyết định ngạch bắt buộc thay đổi hai giá trị đồng thời. Ngược lại, phòng ban của nhân viên thường là **quan hệ với thực thể Department**, nên nên có mô hình riêng.

### 2.2. Snapshot lịch sử khác nhật ký thay đổi

Một hàng phiên bản lưu **giá trị đã có hiệu lực trong một khoảng**. Nhật ký ghi **“ngày nào, ai đổi giá trị gì”** có thể giúp audit, nhưng không tự thay thế mô hình hiệu lực nếu quyết định được nhập muộn hoặc có thể đặt cho tương lai.

Ví dụ ngạch SENIOR được phê duyệt ngày 20/06 nhưng **có hiệu lực từ 01/07**. Nếu chỉ lấy ngày phê duyệt làm mốc chuyển phiên bản, báo cáo nhân sự cuối tháng 6 sẽ sai. Bản ghi phải tách **ngày hiệu lực** khỏi **ngày hệ thống ghi nhận** khi nghiệp vụ cần.

## 3. Lịch sử quan hệ là gì?

**Lịch sử quan hệ** (*relationship history*) ghi thời gian một mối liên kết giữa các thực thể có hiệu lực. Nếu thuộc tính trả lời **“nhân viên có giá trị gì?”**, quan hệ trả lời **“nhân viên gắn với đối tượng nào, trong vai trò nào, và vào giai đoạn nào?”**

Ví dụ:

- Nhân viên thuộc phòng ban nào trong tháng 3?
- Khách hàng có người quản lý tài khoản nào khi ký hợp đồng?
- Sản phẩm nằm trong danh mục nào tại thời điểm chốt đơn?
- Một người dùng thuộc nhóm quyền nào vào ngày hệ thống phê duyệt truy cập?
- Một thành viên tham gia dự án nào, với vai trò và thời lượng phân bổ ra sao?
- Một công ty con do pháp nhân nào sở hữu trong từng giai đoạn?

Giả sử nhân viên 42 chuyển phòng:

~~~text
Employee(42)
  ├── MEMBER_OF Department(A): [01/01, 01/04)
  ├── MEMBER_OF Department(B): [01/04, 01/10)
  └── MEMBER_OF Department(C): [01/10, +∞)
~~~

Nếu bảng **employee** chỉ có **department_id = C**, các lần gắn với A và B đã bị ghi đè. Nếu xóa hàng liên kết Employee–Department mỗi khi chuyển phòng, cũng không thể trả lời các câu hỏi về quá khứ.

### 3.1. Quan hệ cũng có thuộc tính

Mối quan hệ “nhân viên tham gia dự án” có thể mang **vai trò trong dự án**, **tỷ lệ phân bổ thời gian** và **thời điểm tham gia**. Những thuộc tính này thuộc về **liên kết Employee–Project**, không phải mặc nhiên là thuộc tính của nhân viên hoặc của dự án.

~~~text
Employee(42) --[PROJECT_MEMBER, role=Reviewer,
                 allocation=40%, valid=[01/04, 01/07))--> Project(900)
~~~

Nếu vai trò đổi từ Reviewer sang Lead vào 01/07, có thể phải chia phiên bản quan hệ thành hai khoảng. Nếu nhân viên cùng lúc tham gia Project 900 và Project 901, các khoảng ấy có thể chồng nhau vì **khóa quan hệ gồm cả project_id**; không nên áp ràng buộc “mỗi nhân viên chỉ có một dự án”.

### 3.2. Quan hệ có thể là một-nhiều hoặc nhiều-nhiều theo thời gian

Với **phòng ban chính**, quy tắc có thể là **mỗi nhân viên có tối đa một phòng chính tại một ngày**. Đây là ràng buộc theo **employee_id + assignment_kind=PRIMARY**.

Với **dự án**, một nhân viên có thể tham gia nhiều dự án cùng lúc, nhưng không được có hai phiên bản trùng nhau cho **cùng nhân viên, cùng dự án, cùng loại vai trò** nếu nghiệp vụ xem đó là cùng một quan hệ.

Khóa dùng để chống chồng lấn phải xuất phát từ câu hỏi **“hai liên kết nào thực sự cạnh tranh nhau?”**, chứ không lấy một quy tắc chung cho mọi loại quan hệ.

## 4. Thực thể, quan hệ và phiên bản trong mô hình logic

Để tránh gắn tất cả thông tin thay đổi vào một bảng, có thể mô hình như sau:

~~~mermaid
erDiagram
    EMPLOYEE ||--o{ EMPLOYEE_GRADE_HISTORY : "có lịch sử ngạch"
    EMPLOYEE ||--o{ EMPLOYEE_DEPARTMENT_HISTORY : "có lịch sử phân công"
    DEPARTMENT ||--o{ EMPLOYEE_DEPARTMENT_HISTORY : "được phân công đến"
    EMPLOYEE ||--o{ PROJECT_MEMBERSHIP_HISTORY : "tham gia"
    PROJECT ||--o{ PROJECT_MEMBERSHIP_HISTORY : "có thành viên"
    EMPLOYEE {
        bigint employee_id PK
        text employee_code UK
    }
    EMPLOYEE_GRADE_HISTORY {
        bigint grade_version_id PK
        bigint employee_id FK
        text grade_code
        daterange valid_period
    }
    DEPARTMENT {
        bigint department_id PK
        text department_name
    }
    EMPLOYEE_DEPARTMENT_HISTORY {
        bigint assignment_id PK
        bigint employee_id FK
        bigint department_id FK
        text assignment_kind
        daterange valid_period
    }
    PROJECT {
        bigint project_id PK
    }
    PROJECT_MEMBERSHIP_HISTORY {
        bigint membership_id PK
        bigint employee_id FK
        bigint project_id FK
        text project_role
        daterange valid_period
    }
~~~

Mô hình này tách được:

- **Employee**: thực thể logic, không đổi ID khi ngạch và phòng thay đổi.
- **EmployeeGradeHistory**: phiên bản giá trị ngạch, không cần tham chiếu một phòng ban cụ thể.
- **EmployeeDepartmentHistory**: phiên bản của một **quan hệ** giữa Employee và Department, có **assignment_kind** phân biệt phòng chính và kiêm nhiệm.
- **ProjectMembershipHistory**: một quan hệ nhiều-nhiều với chu kỳ và thuộc tính riêng.

Ở cấp lược đồ vật lý, ta phải chọn khóa chính cho bản ghi phiên bản, khóa ngoại đến các thực thể gốc, quy tắc chồng lấn và chỉ mục theo truy vấn lịch sử.

Không nên làm cho bản ghi của Department trở thành một phần danh tính của Employee. Việc nhân viên chuyển phòng **không tạo ra nhân viên mới**.

## 5. Chọn đơn vị thời gian và quy ước khoảng

Các bảng lịch sử trong ví dụ dùng khoảng ngày nửa mở:

~~~text
[valid_from, valid_to)

valid_from được bao gồm.
valid_to bị loại trừ.
~~~

Một phân công **[01/01, 01/04)** còn đúng đến hết ngày 31/03, và phân công mới **[01/04, 01/10)** bắt đầu đúng ngày 01/04. Hai khoảng chỉ tiếp giáp sẽ không chồng lấn.

Nếu nghiệp vụ dùng **giờ/phút** (ví dụ phân công ca trực), thay **date/daterange** bằng **timestamptz/tstzrange** và thống nhất múi giờ của nghiệp vụ. Không trừ đi “một giây cuối cùng” để cố biểu diễn biên kết thúc vì độ chính xác của timestamp có thể lớn hơn giây.

**Biên trên không giới hạn** có nghĩa chưa xác định ngày kết thúc. Ví dụ **[01/10, +∞)** phản ánh phân công hiện tại theo thông tin đã biết, không phải cam kết vĩnh viễn.

Các quy tắc toàn vẹn thường là:

1. Khoảng không được rỗng.
2. Mốc bắt đầu phải rõ ràng và được bao gồm.
3. Mốc kết thúc, nếu có, phải loại trừ; không tạo hai phiên bản cùng đúng ở biên chuyển đổi.
4. Với cùng phạm vi nghiệp vụ, hai khoảng hiệu lực không được giao nhau nếu quy tắc chỉ cho phép tối đa một giá trị.
5. Có hay không cho phép **khoảng trống** phải được quy định riêng. **Không chồng lấn** không đồng nghĩa **luôn có một giá trị**.

Trường **recorded_at** dùng để biết khi nào thông tin được nhập, còn **valid_period** xác định thông tin có hiệu lực khi nào. Một hệ thống cần tra cứu cả **“ngày D giá trị nào đúng?”** và **“ngày K hệ thống từng tin gì về ngày D?”** cần mô hình hai trục thời gian hoặc chuỗi sự kiện đủ để tái dựng; một timestamp recorded_at trên hàng đã bị UPDATE là chưa đủ.

## 6. Lược đồ PostgreSQL: lịch sử thuộc tính

Đây là ví dụ PostgreSQL có thể chạy trên một cơ sở dữ liệu thử nghiệm. Chúng ta dùng **daterange** vì nghiệp vụ phân ngạch nhân viên có hiệu lực theo **ngày**.

~~~sql
-- btree_gist cung cấp phép bằng cho bigint/text trong GiST.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE employee (
    employee_id   bigint PRIMARY KEY,
    employee_code text NOT NULL UNIQUE
);

CREATE TABLE department (
    department_id   bigint PRIMARY KEY,
    department_name text NOT NULL
);

CREATE TABLE employee_grade_history (
    grade_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id      bigint NOT NULL
                     REFERENCES employee(employee_id),
    grade_code       text NOT NULL
                     CHECK (grade_code IN ('JUNIOR', 'MIDDLE', 'SENIOR')),
    valid_period     daterange NOT NULL,
    source_ref       text NOT NULL,
    recorded_at      timestamptz NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT ck_grade_valid_period
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    CONSTRAINT ex_grade_one_at_a_time
        EXCLUDE USING gist (
            employee_id WITH =,
            valid_period WITH &&
        )
);
~~~

**Giải thích thiết kế:**

- **employee_id** trong Employee là khóa của thực thể logic.
- **grade_version_id** nhận diện riêng từng phiên bản ngạch.
- **grade_code** có thể thay bằng khóa ngoại tới danh mục ngạch nếu ngạch có metadata cần quản lý.
- **valid_period** cho biết khoảng ngày hiệu lực.
- **source_ref** tham chiếu quyết định nhân sự làm căn cứ.
- **recorded_at** ghi thời điểm lưu và **không** làm lịch sử tự động trở thành bitemporal.
- **ex_grade_one_at_a_time** yêu cầu một nhân viên tại một ngày chỉ có **tối đa một ngạch**. Hai khoảng với cùng employee_id và giao nhau sẽ bị từ chối, kể cả khi giá trị grade_code giống nhau.

Ràng buộc **EXCLUDE USING gist** ngăn chồng lấn mà một ràng buộc **UNIQUE(employee_id, lower(valid_period))** không thể bảo đảm. Hai khoảng có ngày bắt đầu khác nhau vẫn có thể giao nhau.

Việc định nghĩa grade_code bằng CHECK là lựa chọn cho ví dụ nhỏ. Khi danh mục ngạch biến đổi hoặc dùng chung nhiều module, bảng tham chiếu với khóa ngoại và quy tắc hiệu lực riêng thường dễ quản trị hơn.

## 7. Lược đồ PostgreSQL: lịch sử quan hệ nhân viên – phòng ban

Với phân công phòng ban, quan hệ có thuộc tính **assignment_kind**:

- **PRIMARY**: phòng ban chính, tối đa một phòng cho mỗi nhân viên tại một ngày.
- **SECONDARY**: phòng kiêm nhiệm, có thể cùng tồn tại với phòng chính và có thể nhiều phòng khác nhau.

~~~sql
CREATE TABLE employee_department_history (
    assignment_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id     bigint NOT NULL REFERENCES employee(employee_id),
    department_id   bigint NOT NULL REFERENCES department(department_id),
    assignment_kind text NOT NULL
                    CHECK (assignment_kind IN ('PRIMARY', 'SECONDARY')),
    valid_period    daterange NOT NULL,
    decision_ref    text NOT NULL,
    recorded_at     timestamptz NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT ck_department_valid_period
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    -- Không có hai phòng PRIMARY đồng thời cho cùng nhân viên.
    CONSTRAINT ex_one_primary_department
        EXCLUDE USING gist (
            employee_id WITH =,
            valid_period WITH &&
        )
        WHERE (assignment_kind = 'PRIMARY'),

    -- Không trùng hai bản ghi của cùng một loại quan hệ.
    CONSTRAINT ex_duplicate_department_membership
        EXCLUDE USING gist (
            employee_id WITH =,
            department_id WITH =,
            assignment_kind WITH =,
            valid_period WITH &&
        )
);
~~~

**Hai ràng buộc loại trừ bảo vệ hai quy tắc khác nhau.** Ràng buộc thứ nhất kiểm soát *các phòng chính cạnh tranh*, bất kể department_id nào. Ràng buộc thứ hai không cho ghi hai phiên bản chồng lấn của **cùng nhân viên + cùng phòng + cùng loại phân công**.

Nếu không có ràng buộc thứ nhất, một nhân viên có thể có hai hàng PRIMARY thuộc hai department_id khác nhau cùng hiệu lực. Nếu chỉ có ràng buộc thứ nhất, các hàng SECONDARY trùng hệt quan hệ có thể vô tình được chèn nhiều lần.

Ví dụ cho phép một nhân viên vừa PRIMARY ở phòng B vừa SECONDARY ở phòng C trong cùng giai đoạn. Nếu công ty quy định **không thể là PRIMARY và SECONDARY trong cùng phòng tại cùng ngày**, phải bổ sung bất biến tương ứng; mô hình trên chưa cấm tình huống đó vì coi hai loại phân công là hai vai trò khác nhau.

Lưu ý **cấm chồng lấn** chưa bảo đảm một nhân viên luôn có đúng một phòng ban chính. Nếu nghiệp vụ yêu cầu điều đó trong toàn bộ thời gian còn làm việc, cần kiểm tra thêm **không có khoảng trống** so với khoảng thời gian làm việc.

## 8. Tạo dữ liệu mẫu cho thuộc tính và quan hệ

~~~sql
INSERT INTO employee (employee_id, employee_code)
VALUES (42, 'E-0042');

INSERT INTO department (department_id, department_name)
VALUES
    (10, 'Phòng A'),
    (20, 'Phòng B'),
    (30, 'Phòng C');

INSERT INTO employee_grade_history (
    employee_id, grade_code, valid_period, source_ref
)
VALUES
(
    42, 'JUNIOR',
    daterange(DATE '2026-01-01', DATE '2026-07-01', '[)'),
    'HR-GRADE-001'
),
(
    42, 'SENIOR',
    daterange(DATE '2026-07-01', NULL, '[)'),
    'HR-GRADE-002'
);

INSERT INTO employee_department_history (
    employee_id, department_id, assignment_kind,
    valid_period, decision_ref
)
VALUES
(
    42, 10, 'PRIMARY',
    daterange(DATE '2026-01-01', DATE '2026-04-01', '[)'),
    'HR-DEPT-001'
),
(
    42, 20, 'PRIMARY',
    daterange(DATE '2026-04-01', DATE '2026-10-01', '[)'),
    'HR-DEPT-002'
),
(
    42, 30, 'PRIMARY',
    daterange(DATE '2026-10-01', NULL, '[)'),
    'HR-DEPT-003'
);
~~~

Các bản ghi phân công ở đây là **phiên bản của quan hệ**, không phải bản sao của nhân viên. Khi đổi phòng B thành C, **employee_id = 42** vẫn là 42. Dữ liệu phòng ban vẫn được quản lý độc lập trong bảng Department.

Theo các khoảng đã chèn:

| Ngày hỏi | Ngạch | Phòng chính |
|---|---|---|
| 15/02/2026 | JUNIOR | Phòng A |
| 15/05/2026 | JUNIOR | Phòng B |
| 20/08/2026 | SENIOR | Phòng B |
| 20/10/2026 | SENIOR | Phòng C |

Điều cần chú ý là **ngạch đổi vào 01/07 nhưng phòng không đổi vào ngày đó**; phòng đổi vào 01/04 và 01/10 nhưng ngạch không đổi. Hai lịch sử độc lập theo thời gian, vì vậy một hàng lịch sử tổng hợp cả ngạch và phòng có thể tạo các phiên bản dư thừa hoặc làm khó xác định điều gì thực sự thay đổi.

## 9. Truy vấn lịch sử thuộc tính

### 9.1. Ngạch có hiệu lực tại một ngày

~~~sql
SELECT
    grade_version_id,
    grade_code,
    valid_period,
    source_ref
FROM employee_grade_history
WHERE employee_id = 42
  AND valid_period @> DATE '2026-08-20';
~~~

Kết quả: **SENIOR**. Toán tử **@>** trong PostgreSQL trả về đúng khi khoảng bên trái chứa điểm ngày bên phải.

Nếu quy tắc một ngạch mỗi nhân viên/ngày đã được bảo vệ bằng exclusion constraint, truy vấn hợp lệ trả tối đa một hàng. Trường hợp không có hàng có thể nghĩa là nhân viên chưa có ngạch vào ngày được hỏi, đã nghỉ việc, hoặc dữ liệu lịch sử chưa được lưu đủ phạm vi. Không tự thay thế bằng ngạch mới nhất.

### 9.2. Liệt kê dòng thời gian của một thuộc tính

~~~sql
SELECT
    grade_version_id,
    grade_code,
    lower(valid_period) AS valid_from,
    upper(valid_period) AS valid_to,
    source_ref
FROM employee_grade_history
WHERE employee_id = 42
ORDER BY lower(valid_period), grade_version_id;
~~~

Trong PostgreSQL, biên trên không giới hạn khiến **upper(valid_period)** trả NULL, dù **valid_period** không phải SQL NULL. UI có thể diễn đạt là “chưa có ngày kết thúc”.

Không dùng **ORDER BY grade_version_id DESC LIMIT 1** để trả lời “ngạch đang có hiệu lực hôm nay” nếu hệ thống cho phép đăng ký một quyết định thăng ngạch có hiệu lực trong tương lai.

## 10. Truy vấn lịch sử quan hệ

### 10.1. Phòng ban chính tại ngày D

~~~sql
SELECT
    d.department_id,
    d.department_name,
    a.valid_period,
    a.decision_ref
FROM employee_department_history a
JOIN department d
  ON d.department_id = a.department_id
WHERE a.employee_id = 42
  AND a.assignment_kind = 'PRIMARY'
  AND a.valid_period @> DATE '2026-05-15';
~~~

Kết quả: **Phòng B**. Đây là truy vấn trên quan hệ có hiệu lực, không phải JOIN từ cột **employee.department_id** hiện tại.

### 10.2. Toàn bộ phòng ban từng tham gia

~~~sql
SELECT
    a.assignment_kind,
    d.department_name,
    lower(a.valid_period) AS valid_from,
    upper(a.valid_period) AS valid_to
FROM employee_department_history a
JOIN department d
  ON d.department_id = a.department_id
WHERE a.employee_id = 42
ORDER BY lower(a.valid_period), a.assignment_kind, d.department_name;
~~~

Một nhân viên có thể có các bản ghi SECONDARY chồng thời gian với PRIMARY. Vì vậy khi dựng **dòng thời gian phòng ban chính**, điều kiện **assignment_kind = 'PRIMARY'** là một phần bắt buộc của ngữ nghĩa truy vấn.

### 10.3. Xem người thuộc một phòng tại ngày D

Đây là truy vấn theo chiều ngược lại của quan hệ:

~~~sql
SELECT e.employee_id, e.employee_code
FROM employee_department_history a
JOIN employee e
  ON e.employee_id = a.employee_id
WHERE a.department_id = 20
  AND a.assignment_kind = 'PRIMARY'
  AND a.valid_period @> DATE '2026-08-20'
ORDER BY e.employee_id;
~~~

Kết quả gồm nhân viên 42. Với workload thường xuyên hỏi “phòng B có những nhân viên nào tại ngày D”, chỉ mục tối ưu theo **department_id + valid_period** có thể cần thiết; chỉ mục phục vụ kiểm soát một phòng chính theo **employee_id** chưa chắc hiệu quả cho chiều truy vấn này.

## 11. Temporal join: kết hợp lịch sử thuộc tính và quan hệ

Để biết **ngạch và phòng ban cùng có hiệu lực tại ngày D**, không thể JOIN mọi phiên bản của ngạch với mọi phiên bản phòng rồi chọn tùy ý. Phải lọc **cùng một ngày nghiệp vụ** ở cả hai bảng.

~~~sql
SELECT
    e.employee_id,
    e.employee_code,
    g.grade_code,
    d.department_name
FROM employee e
JOIN employee_grade_history g
  ON g.employee_id = e.employee_id
JOIN employee_department_history a
  ON a.employee_id = e.employee_id
JOIN department d
  ON d.department_id = a.department_id
WHERE e.employee_id = 42
  AND a.assignment_kind = 'PRIMARY'
  AND g.valid_period @> DATE '2026-08-20'
  AND a.valid_period @> DATE '2026-08-20';
~~~

Kết quả kỳ vọng:

~~~text
employee_id | employee_code | grade_code | department_name
42          | E-0042        | SENIOR     | Phòng B
~~~

Nếu bỏ điều kiện lọc thời gian cho một trong hai bảng, ta có thể tạo ra tổ hợp **“SENIOR, phòng A”** dù hai giá trị chưa từng cùng có hiệu lực.

### 11.1. Kết hợp hai dòng thời gian thành các lát cắt cùng hiệu lực

Khi cần dựng toàn bộ lịch sử ngạch + phòng ban, không thể đơn giản nối hai danh sách ngày bắt đầu rồi nhân hàng; ta cần tính **giao của hai khoảng**.

PostgreSQL hỗ trợ toán tử **\*** để lấy giao của hai range, sau khi biết chúng giao nhau bằng **&&**:

~~~sql
SELECT
    g.grade_code,
    d.department_name,
    g.valid_period * a.valid_period AS jointly_valid_period
FROM employee_grade_history g
JOIN employee_department_history a
  ON a.employee_id = g.employee_id
 AND a.assignment_kind = 'PRIMARY'
 AND g.valid_period && a.valid_period
JOIN department d
  ON d.department_id = a.department_id
WHERE g.employee_id = 42
ORDER BY lower(g.valid_period * a.valid_period);
~~~

Kết quả theo dữ liệu mẫu:

| Ngạch | Phòng chính | Khoảng đồng thời có hiệu lực |
|---|---|---|
| JUNIOR | Phòng A | [01/01, 01/04) |
| JUNIOR | Phòng B | [01/04, 01/07) |
| SENIOR | Phòng B | [01/07, 01/10) |
| SENIOR | Phòng C | [01/10, không giới hạn) |

Truy vấn này là cách tạo các **lát cắt theo thời gian** từ hai lịch sử độc lập. Có thể mở rộng cho nhiều thuộc tính và quan hệ, nhưng số phép giao và khối lượng kết quả có thể tăng nhanh. Mỗi lần thêm bảng lịch sử, phải xác định thuộc tính/quan hệ nào bắt buộc có giá trị tại thời điểm cần truy vấn.

**Lưu ý về thiếu dữ liệu:** INNER JOIN chỉ trả những khoảng mà cả ngạch và phòng đều có bản ghi. Nếu tháng 6 có ngạch nhưng thiếu phân công phòng, phần thời gian ấy có thể biến mất khỏi báo cáo. Khi mục tiêu là phát hiện thiếu dữ liệu, cần dùng truy vấn kiểm tra gap hoặc LEFT JOIN theo thời điểm thích hợp, thay vì coi không có hàng là không có nhân viên.

### 11.2. Temporal join với giao dịch đã chốt

Khi một hóa đơn, đơn hàng hoặc chứng từ được chốt vào thời điểm D, các thuộc tính và quan hệ dùng để tính toán có thể được tìm bằng temporal join. Nhưng nếu dữ liệu hiệu lực sau này bị điều chỉnh hồi tố, chạy lại temporal join với dữ liệu mới nhất có thể cho kết quả khác lúc giao dịch được chốt.

Vì vậy dữ liệu giao dịch có yêu cầu kiểm toán nên lưu **giá trị hoặc snapshot đã dùng khi chốt**, cùng tham chiếu tới nguồn quyết định hoặc version ID đã áp dụng. Không dùng một JOIN động tới lịch sử hiện tại để âm thầm sửa số tiền hay quyền lợi của chứng từ đã phát hành.

## 12. Quan hệ nhiều-nhiều có lịch sử và thuộc tính của liên kết

Phân công phòng chính là một quan hệ gần với **một-nhiều theo thời điểm**. Trong khi đó Employee–Project là **nhiều-nhiều**: một nhân viên có thể tham gia nhiều dự án và một dự án có nhiều nhân viên.

~~~sql
CREATE TABLE project (
    project_id bigint PRIMARY KEY,
    project_name text NOT NULL
);

CREATE TABLE project_membership_history (
    membership_version_id bigint
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id     bigint NOT NULL REFERENCES employee(employee_id),
    project_id      bigint NOT NULL REFERENCES project(project_id),
    project_role    text NOT NULL,
    allocation_pct  numeric(5, 2) NOT NULL
                    CHECK (allocation_pct > 0 AND allocation_pct <= 100),
    valid_period    daterange NOT NULL,
    decision_ref    text NOT NULL,

    CONSTRAINT ck_membership_period
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    CONSTRAINT ex_membership_version_nonoverlap
        EXCLUDE USING gist (
            employee_id WITH =,
            project_id WITH =,
            valid_period WITH &&
        )
);
~~~

Bất biến ở đây là **một cặp Employee–Project chỉ có một phiên bản phân công tại mỗi ngày**; phiên bản gồm cả **project_role** và **allocation_pct**. Cùng một nhân viên vẫn có thể tham gia Project 900 và Project 901 cùng lúc, vì các hàng có **project_id khác nhau**.

Nếu nghiệp vụ cho phép người đó có **hai vai trò song song trong cùng dự án**, khóa nghiệp vụ cần thêm một định danh **vai trò hoặc loại phân công**, thay vì dùng nguyên ràng buộc trên Employee–Project.

Một yêu cầu như “tổng tỷ lệ phân bổ của nhân viên vào các dự án không vượt 100% tại bất kỳ ngày nào” khó hơn chống overlap: các khoảng khác dự án được phép giao nhau, nhưng **tổng allocation_pct theo từng lát thời gian** phải ≤ 100. Một CHECK ở một hàng riêng lẻ không thể kiểm soát tổng trên nhiều hàng; cần transaction/locking và thuật toán kiểm tra các điểm chuyển giao, hoặc một cơ chế tính toán đã được thiết kế riêng.

### 12.1. Quan hệ đối xứng và quan hệ có hướng

Các quan hệ như **“sở hữu”, “quản lý”, “phụ thuộc vào”** có hướng và có vai trò rõ. Trong bảng liên kết cần phân biệt **from_entity_id** và **to_entity_id** hoặc đặt tên FK có nghĩa.

Với quan hệ đối xứng, ví dụ “hai tài khoản được liên kết hai chiều”, phải chuẩn hóa cặp khóa để không lưu đồng thời A–B và B–A như hai quan hệ độc lập ngoài chủ đích. Quy tắc **trùng quan hệ theo thời gian** phụ thuộc vào tính đối xứng/hướng của quan hệ, không chỉ vào các mốc thời gian.

## 13. Ghi thay đổi: đóng khoảng cũ và mở khoảng mới

Các câu lệnh INSERT minh họa giúp hiểu lịch sử đã có; trong thực tế, thay đổi thường đến liên tục và có thể xảy ra đồng thời. Khi chuyển phòng từ A sang B tại ngày **01/04**, mô hình hiện hành ban đầu có thể là:

~~~text
Employee 42 — PRIMARY — Department A
[2026-01-01, +∞)
~~~

Sau chuyển phòng phải trở thành:

~~~text
Employee 42 — PRIMARY — Department A
[2026-01-01, 2026-04-01)

Employee 42 — PRIMARY — Department B
[2026-04-01, +∞)
~~~

Một transaction minh họa dùng **dữ liệu ban đầu chỉ có phòng A mở vô hạn**, độc lập với dữ liệu mẫu ba phòng ở phần 8:

~~~sql
BEGIN;

-- Khóa thực thể gốc để tuần tự hóa thay đổi cho Employee 42.
SELECT employee_id
FROM employee
WHERE employee_id = 42
FOR UPDATE;

UPDATE employee_department_history
SET valid_period = daterange(
    lower(valid_period),
    DATE '2026-04-01',
    '[)'
)
WHERE employee_id = 42
  AND assignment_kind = 'PRIMARY'
  AND lower(valid_period) < DATE '2026-04-01'
  AND upper_inf(valid_period)
RETURNING assignment_id;

-- Ứng dụng phải xác nhận UPDATE tác động đúng một hàng.
-- Nếu không, ROLLBACK, đọc lại timeline và xử lý xung đột.

INSERT INTO employee_department_history (
    employee_id, department_id, assignment_kind,
    valid_period, decision_ref
)
VALUES (
    42, 20, 'PRIMARY',
    daterange(DATE '2026-04-01', NULL, '[)'),
    'HR-TRANSFER-APR'
);

COMMIT;
~~~

Mẫu này **chỉ phù hợp với trường hợp đã xác minh có đúng một khoảng PRIMARY mở vô hạn trước ngày chuyển**. Nếu đã có lịch chuyển phòng khác trong tương lai, hoặc ngày chuyển nằm giữa một khoảng hữu hạn, cần **chia các khoảng bị ảnh hưởng** theo quy tắc riêng; không tự ý cắt mất các quyết định đã lên lịch.

Lệnh UPDATE và INSERT phải nằm trong **cùng transaction** để tránh trạng thái đóng phòng cũ mà chưa ghi phòng mới. Nếu INSERT bị từ chối do exclusion constraint, transaction phải rollback. Nếu UPDATE trả 0 hoặc nhiều hàng, logic ứng dụng không được commit như thể thành công.

### 13.1. Đồng thời và tính idempotent

Hai yêu cầu chuyển phòng đồng thời có thể đọc cùng lịch sử cũ và đề xuất hai đích khác nhau. Nên kết hợp:

- **Khóa theo thực thể**, ví dụ SELECT Employee FOR UPDATE trước khi tính lại timeline.
- **Ràng buộc database** để chống trạng thái cuối chồng lấn trái quy tắc, kể cả khi một đường ghi có lỗi.
- **Revision hoặc expected version** để phát hiện yêu cầu xây trên lịch sử đã cũ.
- **Idempotency key** hoặc mã quyết định nhân sự duy nhất để retry không tạo bản ghi lịch sử trùng.
- **Quy tắc xử lý xung đột** và kiểm tra số hàng bị tác động; không tự chọn “request đến sau” là đúng nghiệp vụ.

Khóa dòng Employee có thể gây tranh chấp nếu mọi loại thuộc tính và quan hệ đều dùng cùng khóa. Khi hệ thống lớn, có thể dùng khóa hoặc thực thể điều phối theo **miền nghiệp vụ** để tăng song song, nhưng phải chứng minh các thao tác cạnh tranh được bảo vệ đầy đủ.

### 13.2. Append-only và sửa sai

Bảng phiên bản theo valid time có thể cần UPDATE **valid_period** để đóng khoảng đang mở. Nếu yêu cầu là mọi thay đổi đã ghi phải **bất biến tuyệt đối**, mô hình cần bổ sung **event log append-only**, table history do hệ thống quản lý, hoặc bitemporal history thay vì cho phép UPDATE xóa dấu vết của trạng thái kiến thức trước đó.

Sự kiện “quyết định chuyển phòng đã được duyệt” khác với “bảng phân công có hiệu lực từ ngày X”. Có thể lưu sự kiện làm bằng chứng quyết định và duy trì bảng khoảng hiệu lực làm mô hình đọc. Các bản ghi lịch sử và sự kiện phải được cập nhật qua giao thức nhất quán.

## 14. Dữ liệu đến muộn, hồi tố và hai trục thời gian

Một thay đổi có thể có hiệu lực **trước ngày hệ thống ghi nhận**. Ví dụ:

- 01/07: nhân viên thực tế chuyển sang phòng B.
- 05/07: hệ thống nhân sự mới nhận được quyết định có hiệu lực từ 01/07.
- 10/07: bộ phận kiểm toán hỏi “ngày 03/07, hệ thống đã ghi nhận nhân viên thuộc phòng nào?”

Nếu chỉ lưu quan hệ valid-time mới nhất, hệ thống có thể trả lời “phòng B có hiệu lực ngày 03/07 theo hiểu biết hiện nay”, nhưng **không chắc** trả lời được “ngày 03/07 hệ thống từng nghĩ nhân viên thuộc phòng nào”. Đây là hai câu hỏi khác nhau.

Để phân biệt, mô hình **bitemporal** bổ sung:

| Trục thời gian | Nghĩa |
|---|---|
| **valid_period** | Khoảng quan hệ hoặc thuộc tính có hiệu lực theo nghiệp vụ |
| **known_period / recorded_period** | Khoảng hệ thống chấp nhận phiên bản ấy là thông tin đang biết |

Ở trường hợp có sửa hồi tố, một phiên bản cũ có thể giao với phiên bản mới theo **valid_period**, nhưng chúng không giao nhau trong cùng **known_period**. Vì thế ràng buộc bitemporal thường xem cả hai trục:

~~~sql
-- Phác thảo constraint cho bảng bitemporal tương ứng:
EXCLUDE USING gist (
    employee_id WITH =,
    valid_period WITH &&,
    known_period WITH &&
)
~~~

Với lịch sử **quan hệ**, khóa còn phải phản ánh tính chất của liên kết. Ví dụ nếu chỉ một phòng PRIMARY được phép tại mỗi cặp (ngày nghiệp vụ, thời điểm hệ thống biết), ràng buộc phải xét employee_id, assignment_kind=PRIMARY, valid và known range; không thêm department_id vào điều kiện cấm chồng lấn PRIMARY, vì như vậy hai phòng khác nhau vẫn có thể cùng hiệu lực.

Một **recorded_at** lưu trên hàng không có **recorded_to** hoặc cơ chế giữ phiên bản cũ chưa đủ để truy vấn mọi trạng thái kiến thức trong quá khứ. Cũng cần phân biệt thời điểm ứng dụng gọi **now()** với thời điểm transaction thực sự commit nếu yêu cầu kiểm toán đòi thời gian khả kiến chính xác.

## 15. Những sai lầm thiết kế phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ giữ **employee.department_id** mới nhất | Không biết phòng ban lịch sử | Bảng quan hệ có khoảng hiệu lực |
| Mỗi lần nhân viên chuyển phòng lại tạo Employee mới | Mất danh tính ổn định; liên kết giao dịch sai | Một Employee ID, nhiều phiên bản quan hệ |
| Cập nhật phòng ban nhưng không ghi ngày chuyển | Không trả lời được “thuộc phòng vào D” | Thêm valid_period với ngữ nghĩa ngày rõ ràng |
| Dùng một bảng snapshot mọi thuộc tính và quan hệ | Phiên bản bị nhân nhiều lần khi dữ liệu đổi độc lập | Tách nhóm thuộc tính/quan hệ theo vòng đời |
| Chỉ đặt UNIQUE trên ngày bắt đầu | Hai khoảng khác ngày bắt đầu vẫn chồng | Exclusion constraint hoặc cơ chế overlap an toàn |
| Chống overlap Employee–Project chỉ theo employee_id | Cấm nhân viên tham gia nhiều dự án cùng lúc | Ràng buộc theo đúng cặp quan hệ |
| Chỉ ràng buộc Employee–Department theo cả employee_id và department_id cho phòng chính | Hai phòng PRIMARY khác nhau vẫn có thể chồng | Ràng buộc PRIMARY riêng theo employee_id |
| Dùng INNER JOIN lịch sử không kiểm tra gap | Các khoảng thiếu dữ liệu biến mất khỏi báo cáo | Kiểm tra gap và nhu cầu hiển thị dữ liệu thiếu |
| Lấy phiên bản có ID lớn nhất làm giá trị ở D | Sai với phiên bản tương lai và hồi tố | Lọc đúng valid_period chứa D |
| Ghi đè lịch sử và dùng recorded_at để giả làm bitemporal | Không tái dựng được hệ thống đã biết gì vào K | Lưu known-period hoặc event history đầy đủ |
| Xóa cascade lịch sử khi xóa thực thể | Mất chứng cứ có thể phải giữ | Chính sách retention, khóa ngoại và xóa rõ ràng |
| Chỉ sửa timeline rồi tính lại hóa đơn đã phát hành | Làm thay đổi dữ liệu giao dịch quá khứ | Snapshot kết quả đã chốt; điều chỉnh bằng nghiệp vụ mới |

## 16. Chỉ mục và hiệu năng truy vấn lịch sử

Lịch sử thuộc tính và lịch sử quan hệ có mẫu truy vấn khác nhau:

| Truy vấn phổ biến | Chiều tra cứu chính | Hướng tối ưu |
|---|---|---|
| Ngạch của một nhân viên tại D | employee_id + grade.valid_period | GiST exclusion hoặc chỉ mục phù hợp |
| Phòng chính của một nhân viên tại D | employee_id + kind + assignment.valid_period | GiST theo employee và range, tận dụng partial constraint |
| Danh sách nhân viên của phòng B tại D | department_id + assignment.valid_period | Chỉ mục bổ sung theo department/range nếu workload lớn |
| Mọi dự án của nhân viên tại D | employee_id + membership.valid_period | Chỉ mục theo nhân viên và khoảng |
| Báo cáo toàn công ty theo kỳ | Phạm vi ngày + joins nhiều bảng | Kho phân tích, partitioning, kế hoạch truy vấn và thống kê |
| Giá trị hiện tại phục vụ API khối lượng lớn | Nhiều thực thể, ngày hiện tại | Projection hiện tại được đồng bộ nếu cần |

Ví dụ chỉ mục bổ sung cho truy vấn ngược từ phòng tới nhân viên:

~~~sql
CREATE INDEX ix_department_history_lookup
ON employee_department_history
USING gist (department_id, valid_period);
~~~

Do bảng dùng **btree_gist**, PostgreSQL có thể xây GiST kết hợp **department_id** và **daterange**. Không nhất thiết phải tạo mọi chỉ mục ngay từ đầu: hãy đo truy vấn thực tế bằng **EXPLAIN (ANALYZE, BUFFERS)** và cân nhắc chi phí ghi dữ liệu phiên bản.

### 16.1. Bảng hiện tại và bảng lịch sử

Đối với API hiển thị phòng ban hiện tại cho hàng triệu nhân viên, đôi khi cần một projection **employee_current_department** hoặc cache để giảm số lần lọc range. Nếu làm vậy, phải xác định bảng lịch sử hay sự kiện nào là **nguồn sự thật**, đồng thời duy trì cập nhật hoặc đối soát với projection.

Một quy trình kiểm tra là lấy giá trị bằng câu hỏi **valid_period chứa ngày nghiệp vụ hiện tại** rồi so với projection. Đừng tự nhận **hàng có valid_from lớn nhất** là hiện tại, vì một phiên bản tương lai có thể đã được nhập.

### 16.2. Phân vùng và thời hạn lưu

Nếu bảng lịch sử rất lớn, partitioning hoặc archive có thể hữu ích. Tuy nhiên, phân vùng theo thời gian ghi nhận có thể khiến hai phiên bản cùng thực thể và khoảng hiệu lực giao nhau ở **hai phân vùng khác nhau**. Không giả định exclusion constraint trên từng phân vùng tự động bảo vệ mọi cặp toàn cục; phải kiểm chứng theo phiên bản PostgreSQL và cấu trúc phân vùng đang dùng.

Lịch sử nhân sự và liên kết quyền truy cập có thể chứa thông tin cá nhân, nên cần quy tắc quyền đọc, retention, ẩn danh và xóa dữ liệu theo chính sách áp dụng. **Append-only** về nghiệp vụ không đồng nghĩa mọi thông tin cá nhân phải được giữ vĩnh viễn.

## 17. Lịch sử thuộc tính và quan hệ trong các mô hình dữ liệu khác

Cùng một yêu cầu “các giá trị/quan hệ nào có hiệu lực vào ngày D?” có thể triển khai theo nhiều mô hình; lựa chọn phụ thuộc khả năng duy trì bất biến và mẫu truy vấn.

### 17.1. Document database

Có thể lưu các phiên bản thuộc tính và liên kết thành những document riêng:

~~~json
{
  "employeeId": 42,
  "versionId": "grade-42-2026-07",
  "gradeCode": "SENIOR",
  "validFrom": "2026-07-01",
  "validTo": null,
  "sourceRef": "HR-GRADE-002"
}
~~~

~~~json
{
  "employeeId": 42,
  "departmentId": 20,
  "assignmentKind": "PRIMARY",
  "validFrom": "2026-04-01",
  "validTo": "2026-10-01",
  "decisionRef": "HR-DEPT-002"
}
~~~

Nếu nhúng mọi lịch sử vào một document Employee, số phiên bản có thể tăng không giới hạn và gây chi phí ghi lớn. Một collection riêng cho lịch sử thường dễ phân trang, lập chỉ mục và quản lý lưu trữ hơn. Nhưng document database có thể thiếu ràng buộc chống overlap ở cấp schema; phải dùng giao dịch, khóa logic theo thực thể hoặc cơ chế cập nhật có điều kiện tương ứng.

Không chọn document chỉ vì bản ghi lịch sử “trông như JSON”. Quan trọng là bảo đảm lịch sử quan hệ không bị ghi lệch khi cập nhật đồng thời và ứng dụng có thể trả lời truy vấn theo ngày.

### 17.2. Graph database

Graph thường biểu diễn Employee và Department bằng node, còn **MEMBER_OF** là edge. Vì **quan hệ** có thời gian hiệu lực, các edge cũng cần mang valid_from/valid_to hoặc có phiên bản riêng.

~~~text
(Employee:42)
  -[MEMBER_OF, PRIMARY, 01/01..trước 01/04]-> (Department:A)
  -[MEMBER_OF, PRIMARY, 01/04..trước 01/10]-> (Department:B)
  -[MEMBER_OF, PRIMARY, 01/10..về sau]-> (Department:C)
~~~

Để tìm cấu trúc tổ chức ngày D, mọi node/edge liên quan trong đường đi phải được lọc theo D. Chỉ phiên bản hóa node Employee mà không phiên bản hóa MEMBER_OF sẽ cho kết quả sai khi nhân viên chuyển phòng.

Với graph nhiều bước, ví dụ **nhân viên → nhóm → phòng → pháp nhân**, còn phải quyết định ngữ nghĩa thời gian của cả đường đi: các cạnh phải đồng thời có hiệu lực vào D, hoặc trong một số truy vấn cần tồn tại một khoảng giao chung không rỗng.

### 17.3. Kho phân tích và SCD Type 2

Trong kho phân tích, **SCD Type 2** là cách phổ biến để lưu các phiên bản thuộc tính của dimension. Có thể lưu **employee_sk**, **employee_id**, **grade_code**, **effective_from**, **effective_to**. Các fact gắn với thời điểm nghiệp vụ có thể JOIN tới phiên bản dimension có hiệu lực vào thời điểm ấy.

Quan hệ Employee–Department cũng có thể được mô hình hóa bằng **bridge table có thời gian hiệu lực** khi là nhiều-nhiều hoặc có vai trò riêng. Nếu fact JOIN vào hai bảng lịch sử mà không lọc cùng ngày D, báo cáo có thể nhân hàng và đếm sai.

Một kho phân tích chỉ tải dữ liệu mỗi đêm có thể **bỏ lỡ các trạng thái trung gian** nếu nguồn giao dịch chỉ giữ giá trị cuối. Vì vậy việc giữ lịch sử ngay từ hệ thống nguồn hoặc lấy đầy đủ các thay đổi CDC/event là điều kiện quan trọng nếu báo cáo yêu cầu truy vết từng lần chuyển.

### 17.4. Event store và audit log

Event store lưu sự kiện miền, chẳng hạn **GradePromoted** hoặc **EmployeeTransferredToDepartment**, và projection dựng ra những khoảng hiệu lực để truy vấn nhanh. Nó phù hợp khi nghiệp vụ muốn chứng minh diễn biến và có khả năng replay, nhưng đòi xử lý thứ tự, idempotency, schema evolution và điều chỉnh hồi tố.

**Audit log** ghi ai thực hiện thao tác nào lúc nào, thường phục vụ điều tra truy cập hoặc thao tác quản trị. Audit log không tự bảo đảm có đủ **khoảng hiệu lực nghiệp vụ**; một bản log “đổi phòng vào 05/07” chưa cho biết việc đổi có hiệu lực từ 01/07 nếu payload không lưu ngày hiệu lực.

## 18. Di chuyển dữ liệu từ mô hình chỉ có trạng thái hiện tại

Một tổ chức trước đây chỉ có:

~~~text
employee(employee_id, grade_code, department_id, updated_at)
~~~

Nay cần lịch sử. Không thể suy diễn chính xác mọi giá trị đã tồn tại trong quá khứ chỉ từ hàng hiện tại. Khi migration, cần đánh dấu nguồn, độ tin cậy và giới hạn lịch sử.

Một hướng triển khai:

1. **Xác nhận câu hỏi nghiệp vụ**: từ thời điểm nào trở đi bắt buộc trả lời lịch sử ngạch và phòng?
2. **Phân loại nguồn cũ**: quyết định nhân sự, hợp đồng, log nhập liệu, dữ liệu báo cáo; xác định nguồn đáng tin cho ngày hiệu lực.
3. **Thiết kế bảng lịch sử và khóa**: tách entity ID, attribute version ID và relationship assignment ID.
4. **Backfill có chứng cứ**: nếu chỉ biết giá trị hiện tại, không tự gán nó cho toàn bộ quá khứ; có thể lưu ngày bắt đầu được xác minh và nguồn quyết định.
5. **Kiểm tra chồng lấn/gap** trước khi bật constraint; xử lý từng mâu thuẫn theo nghiệp vụ.
6. **Chuyển đường ghi** qua service/transaction chuẩn, chặn các UPDATE trực tiếp vào cột hiện tại gây lệch bảng lịch sử.
7. **Đối soát** giữa giá trị hiện tại và truy vấn as-of; triển khai cảnh báo khi có chênh lệch.
8. **Công bố giới hạn truy vấn**: ngày trước thời kỳ dữ liệu được lưu đầy đủ phải trả “không đủ lịch sử”, không mặc định kết luận thực thể chưa tồn tại.

Nếu cần dữ liệu lịch sử trong thời gian migration, có thể song song ghi bảng mới và projection cũ theo một giao thức nhất quán. Nhưng **dual write** qua hai dịch vụ không có transaction chung cần cơ chế outbox, idempotency, retry và đối soát.

## 19. Ma trận kiểm thử cho thuộc tính, quan hệ và temporal join

Dùng dữ liệu nhân viên 42 ở phần 8. Các mốc là ngày nghiệp vụ, không phải giờ UTC.

| Kịch bản | Ngày hỏi | Kỳ vọng |
|---|---|---|
| Trước ngày bắt đầu mọi lịch sử | 31/12/2025 | Không tìm thấy ngạch/phân công |
| Ngày đầu phiên bản ngạch | 01/01/2026 | JUNIOR |
| Ngày cuối trước khi đổi ngạch | 30/06/2026 | JUNIOR |
| Đúng biên thăng ngạch | 01/07/2026 | SENIOR |
| Ngày cuối của phòng A | 31/03/2026 | PRIMARY tại phòng A |
| Đúng biên chuyển sang B | 01/04/2026 | PRIMARY tại phòng B |
| Sau đổi ngạch nhưng trước đổi phòng | 20/08/2026 | SENIOR, phòng B |
| Đúng biên chuyển sang C | 01/10/2026 | SENIOR, phòng C |
| Hai dự án khác nhau cùng ngày | Bất kỳ ngày được cho phép | Hai quan hệ Project được cùng tồn tại |
| Hai phòng PRIMARY giao khoảng | Một khoảng giao nhau | Database từ chối |
| Phòng PRIMARY và SECONDARY giao khoảng | Một ngày thuộc cả hai | Hợp lệ nếu khác phạm vi/đúng quy tắc |
| Một khoảng rỗng | [01/07, 01/07) | Database từ chối |

Các ca kiểm thử vận hành bổ sung:

- **Atomicity**: đóng phân công cũ rồi chèn phân công mới thất bại; transaction rollback toàn bộ.
- **Concurrency**: hai request chuyển phòng cùng một nhân viên không thể tạo hai phòng chính có hiệu lực trùng nhau.
- **Retry/idempotency**: lặp lại cùng quyết định không sinh bản lịch sử trùng.
- **Ghi tương lai**: quyết định tăng ngạch tháng sau không làm thay đổi ngạch của hôm nay.
- **Đính chính hồi tố**: mô hình ghi rõ khả năng tái dựng lịch sử ghi nhận, hoặc công bố giới hạn chỉ lưu lịch sử hiệu lực.
- **Temporal join**: mỗi kết quả ngạch + phòng phải tồn tại một ngày D thuộc cả hai khoảng.
- **Gap detection**: khi ngạch có nhưng phòng chính thiếu, hệ thống không được âm thầm trả ngạch + một phòng cũ không còn hiệu lực.
- **Nguồn quyết định**: mọi phiên bản có thể truy tới tài liệu/quyết định làm căn cứ.
- **Đối soát bản hiện tại**: projection hiện tại phải bằng lát cắt as-of trong giới hạn trễ đã định nghĩa.
- **Múi giờ/độ phân giải**: nếu chuyển từ date sang timestamptz, quy tắc ngày nghiệp vụ vẫn phải nhất quán.

## 20. Bài thực hành: lịch sử thuộc tính sản phẩm và lịch sử danh mục

Một nền tảng thương mại điện tử cần:

> “Biết thời hạn bảo hành đã áp dụng cho sản phẩm tại ngày chốt đơn; biết sản phẩm nằm trong danh mục nào khi được bán; một sản phẩm có thể thuộc nhiều danh mục đồng thời nhưng không được có hai phiên bản bảo hành khác nhau cùng hiệu lực.”

Hãy thiết kế mô hình:

1. **Product** là thực thể ổn định với khóa **product_id**.
2. **ProductWarrantyHistory** lưu **warranty_months** và **valid_period**, mỗi sản phẩm tối đa một chính sách bảo hành có hiệu lực tại một ngày nếu đó là quy tắc nghiệp vụ.
3. **ProductCategoryHistory** là bảng liên kết Product–Category có **valid_period**. Một sản phẩm được thuộc nhiều danh mục khác nhau cùng lúc; chống trùng cùng cặp Product–Category trong cùng giai đoạn.
4. **OrderLine** lưu sản phẩm, thời điểm chốt, thông tin bảo hành đã áp dụng và các thuộc tính chứng từ cần đóng băng.
5. Viết một truy vấn as-of lấy thời hạn bảo hành tại ngày D và các danh mục có hiệu lực tại D. Với nhiều danh mục, kết quả có thể nhiều hàng: cần tập hợp danh mục trước khi ghép với OrderLine để tránh nhân số lượng hoặc tiền.
6. Thử một trường hợp sản phẩm đổi bảo hành ngày 01/07 nhưng đổi danh mục ngày 15/06. Hãy xác định các lát cắt thời gian mà cả chính sách bảo hành và tập danh mục cùng không đổi.
7. Giả sử ngày 10/08 có quyết định bảo hành hồi tố hiệu lực từ 01/07. Phân biệt câu hỏi “chính sách hiện biết áp dụng ngày 15/07 là gì?” với “ngày chốt đơn 16/07 hệ thống đã ghi nhận chính sách nào?”. Hãy nêu yêu cầu bổ sung về recorded time hoặc snapshot chứng từ.

**Tiêu chí đánh giá:** có khóa nghiệp vụ đúng cho từng bảng; khoảng nửa mở nhất quán; ngăn chồng lấn ở thuộc tính bảo hành; cho phép nhiều danh mục khác nhau đồng thời; JOIN theo ngày D cho cả hai loại lịch sử; giữ số tiền, quyền lợi và chứng cứ của đơn đã chốt.

## 21. Checklist trước khi phê duyệt mô hình

- **Thực thể:** ID của thực thể ổn định qua các thay đổi thuộc tính và quan hệ chưa?
- **Lịch sử thuộc tính:** những trường có cùng quy tắc thay đổi đã được nhóm hợp lý, tránh snapshot toàn bộ thực thể không cần thiết chưa?
- **Lịch sử quan hệ:** các FK và thuộc tính của liên kết có nằm trên bảng quan hệ thay vì bị ghi đè vào thực thể chưa?
- **Khóa nghiệp vụ:** phạm vi nào phải độc nhất theo thời gian; quan hệ nào cho phép nhiều bản ghi đồng thời?
- **Khoảng hiệu lực:** dùng date hay timestamp, biên [from, to), ngày bắt đầu, kết thúc và khoảng trống đã được định nghĩa rõ chưa?
- **Ràng buộc:** database có ngăn overlap, khoảng rỗng và sai phạm vi quan hệ trong điều kiện ghi đồng thời chưa?
- **Ghi dữ liệu:** chuyển trạng thái, chuyển quan hệ, lập lịch tương lai, chia khoảng, rollback, retry và sửa hồi tố có một giao thức rõ ràng chưa?
- **Temporal join:** mọi bảng lịch sử trong một kết quả có được lọc theo **cùng ngày D** hoặc lấy giao khoảng đúng không?
- **Audit và bitemporal:** có cần biết hệ thống **đã ghi nhận điều gì vào K** hay chỉ cần giá trị đang được xác nhận có hiệu lực vào D?
- **Chứng từ đã chốt:** dữ liệu của đơn hàng/hóa đơn có lưu những giá trị thực sự áp dụng để tránh thay đổi ngầm khi lịch sử được đính chính không?
- **Hiệu năng và bảo mật:** chỉ mục theo cả chiều truy vấn thực thể và chiều truy vấn quan hệ, retention, quyền truy cập và chính sách dữ liệu cá nhân đã được tính đến chưa?

**Nguyên tắc chốt:** thuộc tính thay đổi theo thời gian tạo ra **lịch sử giá trị của thực thể**; liên kết giữa các thực thể thay đổi theo thời gian tạo ra **lịch sử quan hệ**. Hai loại lịch sử phải chia sẻ quy ước thời gian rõ ràng nhưng có khóa và bất biến riêng. Khi ghép chúng để giải thích quá khứ, luôn yêu cầu các phiên bản **cùng có hiệu lực tại thời điểm được hỏi**. Nhờ đó mô hình dữ liệu giữ đúng ý nghĩa nghiệp vụ, truy vấn được kiểm chứng và có thể tiến hóa mà không làm mất bản chất của các quan hệ trong hệ thống.

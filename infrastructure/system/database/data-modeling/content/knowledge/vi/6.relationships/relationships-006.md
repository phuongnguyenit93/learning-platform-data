# Quan hệ tự tham chiếu và nhiều vai trò giữa cùng một loại thực thể

Trong module **DATABASE_DATA_MODELING**, mô hình dữ liệu cần mô tả được cách các thực thể tham gia vào quan hệ nghiệp vụ. Một trường hợp dễ gây nhầm lẫn là khi một thực thể liên kết với một thực thể khác cùng loại: nhân viên quản lý nhân viên, khóa học yêu cầu khóa học tiên quyết, tài khoản chuyển tiền cho tài khoản, hoặc người dùng theo dõi người dùng.

Đây là **quan hệ tự tham chiếu (recursive relationship)**. Khi hai đầu quan hệ cùng tham chiếu một loại thực thể, mỗi đầu vẫn có thể mang một vai trò khác nhau. Ví dụ, trong giao dịch chuyển tiền, một tài khoản là bên gửi và tài khoản còn lại là bên nhận. Nếu mô hình chỉ ghi “tài khoản liên quan đến tài khoản”, ý nghĩa của dữ liệu sẽ không rõ.

Bài học này trình bày cách nhận diện quan hệ tự tham chiếu, đặt tên vai trò, xác định bội số, lựa chọn cách biểu diễn trong mô hình quan hệ và các họ mô hình khác, đồng thời kiểm soát vòng lặp, chu trình và lịch sử quan hệ.

## 1. Quan hệ tự tham chiếu là gì?

**Quan hệ tự tham chiếu** là quan hệ nối các thể hiện của cùng một loại thực thể. Trong sơ đồ, hai đầu quan hệ cùng trỏ về một thực thể, nhưng mỗi đầu có thể đại diện cho vai trò khác nhau.

Ví dụ:

- Một nhân viên báo cáo cho một nhân viên khác.
- Một danh mục cha chứa các danh mục con.
- Một khóa học có các khóa học tiên quyết.
- Một tài khoản gửi tiền đến một tài khoản khác.
- Một người dùng theo dõi một người dùng khác.
- Một sản phẩm thay thế hoặc tương thích với một sản phẩm khác.

~~~mermaid
erDiagram
    EMPLOYEE ||--o{ EMPLOYEE : manages
    COURSE ||--o{ COURSE : prerequisite_for
    ACCOUNT ||--o{ ACCOUNT : transfers_to
~~~

Sơ đồ khái quát cho thấy một loại thực thể có thể xuất hiện ở cả hai đầu. Khi triển khai và tài liệu hóa, cần ghi rõ tên vai trò để không hiểu nhầm đầu nào là nguồn, đầu nào là đích.

### Quan hệ đệ quy và quan hệ giữa hai loại thực thể

So sánh:

- **Quan hệ thông thường:** Khách hàng đặt Đơn hàng. Hai đầu là hai loại thực thể khác nhau.
- **Quan hệ tự tham chiếu:** Nhân viên quản lý Nhân viên. Hai đầu đều là loại thực thể Nhân viên, nhưng vai trò là người quản lý và người được quản lý.

Việc hai đầu cùng loại không làm mất đi sự khác biệt về vai trò. Vai trò là một phần của ngữ nghĩa quan hệ và cần được ghi rõ trong mô hình.

## 2. Đặt tên vai trò cho từng đầu quan hệ

Khi cùng một loại thực thể xuất hiện nhiều lần trong một quan hệ, hãy đặt tên cho từng vai trò. Tên vai trò nên mô tả chức năng nghiệp vụ của thực thể trong quan hệ đó.

| Loại thực thể | Vai trò thứ nhất | Vai trò thứ hai | Ý nghĩa quan hệ |
|---|---|---|---|
| Nhân viên | Manager | Subordinate/Report | Một nhân viên quản lý nhân viên khác |
| Khóa học | Course | Prerequisite | Một khóa học yêu cầu hoàn thành khóa khác |
| Tài khoản | Source account | Destination account | Một tài khoản chuyển tiền cho tài khoản khác |
| Người dùng | Follower | Followed user | Một người dùng theo dõi người dùng khác |
| Sản phẩm | Original product | Replacement product | Một sản phẩm được thay thế bởi sản phẩm khác |

Tránh các tên chung chung như `entity_a`, `entity_b`, `related_id` hoặc `other_id` nếu có thể đặt tên theo vai trò. Tên rõ ràng giúp đọc sơ đồ, viết truy vấn, thiết kế API và kiểm tra quy tắc dễ hơn.

### Vai trò có hướng

Trong quan hệ “A quản lý B”, vai trò Manager và Subordinate không thể hoán đổi tùy ý. Tương tự, Source account và Destination account có ý nghĩa khác nhau trong giao dịch chuyển tiền.

Hãy viết câu theo cả hai chiều:

- “Nhân viên A quản lý nhân viên B.”
- “Nhân viên B báo cáo cho nhân viên A.”

Hai câu diễn đạt cùng một liên kết nhưng từ hai vai trò khác nhau. Điều này giúp kiểm tra hướng và tránh đặt tên cột sai.

### Vai trò không nhất thiết là thuộc tính của thực thể

Một người có thể là người gửi trong giao dịch này và là người nhận trong giao dịch khác. Không nên thêm cột `is_sender` hoặc `is_receiver` cố định vào bảng Person để biểu diễn vai trò trong mọi quan hệ. Vai trò thường thuộc về **lần tham gia vào quan hệ cụ thể**, không phải bản chất cố định của người đó.

## 3. Xác định bội số và tính bắt buộc

Quan hệ tự tham chiếu vẫn cần xác định bội số ở từng đầu. Không được suy ra bội số chỉ vì hai đầu cùng loại thực thể.

### Ví dụ: cấu trúc quản lý nhân viên

Một nhân viên có thể không có người quản lý nếu là lãnh đạo cao nhất; mỗi nhân viên có tối đa một người quản lý trực tiếp. Một người quản lý có thể quản lý nhiều nhân viên.

| Vai trò | Số lượng tham gia | Diễn giải |
|---|---:|---|
| Manager của một Subordinate | 0..1 | Nhân viên có thể chưa có quản lý trực tiếp hoặc có đúng một người |
| Subordinate của một Manager | 0..N | Một quản lý có thể chưa có hoặc có nhiều nhân viên báo cáo |

Mô hình này là quan hệ một-nhiều tự tham chiếu. Nếu mỗi nhân viên có thể có nhiều quản lý trực tiếp, cấu trúc sẽ chuyển thành nhiều-nhiều và cần bảng liên kết.

### Ví dụ: khóa học tiên quyết

Một khóa học có thể yêu cầu hoàn thành nhiều khóa học tiên quyết, và một khóa học có thể là điều kiện tiên quyết cho nhiều khóa khác.

| Vai trò | Số lượng tham gia |
|---|---:|
| Course cần điều kiện | 0..N Prerequisite |
| Prerequisite được yêu cầu bởi | 0..N Course |

Đây là quan hệ nhiều-nhiều tự tham chiếu. Mỗi cặp có hướng cần được xác định rõ: khóa học nào yêu cầu, khóa học nào phải hoàn thành trước.

### Ví dụ: chuyển tiền giữa tài khoản

Mỗi giao dịch chuyển tiền có đúng một tài khoản nguồn và một tài khoản đích. Một tài khoản có thể là nguồn trong nhiều giao dịch và là đích trong nhiều giao dịch.

- Vai trò Source: đúng một tài khoản cho mỗi giao dịch.
- Vai trò Destination: đúng một tài khoản cho mỗi giao dịch.
- Một tài khoản có thể tham gia 0..N giao dịch ở mỗi vai trò.

Đây là quan hệ có hai vai trò cố định cùng tham chiếu bảng Account. Nó không phải một quan hệ một-nhiều đơn giản như cây quản lý nhân viên.

## 4. Quan hệ một-nhiều tự tham chiếu trong mô hình quan hệ

Với quan hệ một-nhiều, cách biểu diễn phổ biến là đặt khóa ngoại tự tham chiếu ở phía nhiều. Ví dụ, mỗi nhân viên có một `manager_id` trỏ đến `employee.employee_id`.

~~~mermaid
erDiagram
    EMPLOYEE ||--o{ EMPLOYEE : manages
    EMPLOYEE {
        bigint employee_id PK
        string employee_name
        bigint manager_id FK
    }
~~~

DDL minh họa:

~~~sql
CREATE TABLE employee (
    employee_id BIGINT PRIMARY KEY,
    employee_name VARCHAR(160) NOT NULL,
    manager_id BIGINT,
    CONSTRAINT fk_employee_manager
        FOREIGN KEY (manager_id) REFERENCES employee(employee_id),
    CONSTRAINT ck_employee_not_own_manager
        CHECK (manager_id IS NULL OR manager_id <> employee_id)
);
~~~

Trong ví dụ này:

- `employee_id` định danh một nhân viên.
- `manager_id` là khóa ngoại trỏ đến một nhân viên khác đóng vai trò quản lý.
- NULL biểu thị nhân viên không có quản lý trực tiếp trong phạm vi mô hình.
- CHECK cấm nhân viên tự quản lý chính mình.
- Khóa ngoại bảo đảm người quản lý được tham chiếu tồn tại.

Khóa ngoại và CHECK chưa đủ để bảo đảm cấu trúc quản lý không có chu trình dài. Ví dụ A quản lý B, B quản lý C, C lại quản lý A vẫn không vi phạm hai ràng buộc trên. Nếu nghiệp vụ yêu cầu cấu trúc cây hoặc rừng không chu trình, cần kiểm tra chu trình khi thay đổi quan hệ.

### Truy vấn tự nối (self join)

Để hiển thị nhân viên cùng tên người quản lý, cùng một bảng được dùng hai lần với bí danh khác nhau:

~~~sql
SELECT
    subordinate.employee_id,
    subordinate.employee_name,
    manager.employee_id AS manager_id,
    manager.employee_name AS manager_name
FROM employee AS subordinate
LEFT JOIN employee AS manager
    ON manager.employee_id = subordinate.manager_id
ORDER BY subordinate.employee_id;
~~~

Bí danh `subordinate` và `manager` thể hiện hai vai trò. LEFT JOIN giữ lại cả nhân viên chưa có người quản lý. Nếu dùng INNER JOIN, những nhân viên không có manager_id sẽ không xuất hiện.

### Truy vấn cây nhiều cấp

Có thể dùng truy vấn đệ quy để đi từ một nhân viên đến các cấp báo cáo bên dưới. Cú pháp dưới đây minh họa PostgreSQL:

~~~sql
WITH RECURSIVE reporting_tree AS (
    SELECT
        employee_id,
        employee_name,
        manager_id,
        0 AS depth
    FROM employee
    WHERE employee_id = :root_employee_id

    UNION ALL

    SELECT
        child.employee_id,
        child.employee_name,
        child.manager_id,
        parent.depth + 1
    FROM employee AS child
    JOIN reporting_tree AS parent
      ON child.manager_id = parent.employee_id
)
SELECT employee_id, employee_name, manager_id, depth
FROM reporting_tree
ORDER BY depth, employee_id;
~~~

Truy vấn giả định dữ liệu không có chu trình. Nếu có chu trình, truy vấn đệ quy có thể lặp vô hạn hoặc tiếp tục cho đến khi đạt giới hạn của hệ quản trị. Khi truy vấn dữ liệu chưa được tin cậy, cần dùng cơ chế phát hiện đường đi đã thăm hoặc giới hạn độ sâu phù hợp, đồng thời sửa dữ liệu nguồn.

## 5. Quan hệ nhiều-nhiều tự tham chiếu

Một quan hệ nhiều-nhiều giữa các thể hiện cùng loại thường được lưu bằng bảng liên kết. Ví dụ, một khóa học có nhiều khóa học tiên quyết và đồng thời có thể là điều kiện tiên quyết của nhiều khóa học khác.

~~~mermaid
erDiagram
    COURSE ||--o{ COURSE_PREREQUISITE : requires
    COURSE ||--o{ COURSE_PREREQUISITE : prerequisite
    COURSE {
        bigint course_id PK
        string course_name
    }
    COURSE_PREREQUISITE {
        bigint course_id PK, FK
        bigint prerequisite_course_id PK, FK
    }
~~~

~~~sql
CREATE TABLE course (
    course_id BIGINT PRIMARY KEY,
    course_name VARCHAR(200) NOT NULL
);

CREATE TABLE course_prerequisite (
    course_id BIGINT NOT NULL,
    prerequisite_course_id BIGINT NOT NULL,
    CONSTRAINT pk_course_prerequisite
        PRIMARY KEY (course_id, prerequisite_course_id),
    CONSTRAINT fk_prerequisite_course
        FOREIGN KEY (course_id) REFERENCES course(course_id),
    CONSTRAINT fk_required_course
        FOREIGN KEY (prerequisite_course_id) REFERENCES course(course_id),
    CONSTRAINT ck_no_self_prerequisite
        CHECK (course_id <> prerequisite_course_id)
);
~~~

Quy ước trong ví dụ:

- `course_id` là khóa học đang yêu cầu điều kiện tiên quyết.
- `prerequisite_course_id` là khóa học cần hoàn thành trước.
- Khóa chính ghép ngăn lưu trùng cùng một cặp có hướng.
- CHECK ngăn khóa học tự làm điều kiện tiên quyết cho chính nó.
- Khóa ngoại bảo đảm cả hai khóa học đều tồn tại.

Nếu nghiệp vụ cho phép quan hệ ngược độc lập, cặp A → B và B → A là hai quan hệ khác nhau theo khóa chính. Nếu nghiệp vụ yêu cầu đồ thị không chu trình, cần phát hiện chu trình nhiều bước, không chỉ cặp ngược trực tiếp.

### Kiểm tra chu trình

Với quan hệ tiên quyết, chu trình như A yêu cầu B, B yêu cầu C và C yêu cầu A khiến không khóa nào có thể được hoàn thành trước khóa còn lại. Một cách kiểm tra là trước khi thêm cạnh A → B, tìm xem đã tồn tại đường đi từ B đến A hay chưa. Nếu có, thêm cạnh mới sẽ tạo chu trình.

Ví dụ truy vấn PostgreSQL minh họa kiểm tra đường đi từ khóa tiên quyết đến khóa đang yêu cầu:

~~~sql
WITH RECURSIVE reachable(course_id) AS (
    SELECT prerequisite_course_id
    FROM course_prerequisite
    WHERE course_id = :new_prerequisite_course_id

    UNION

    SELECT cp.prerequisite_course_id
    FROM course_prerequisite AS cp
    JOIN reachable AS r
      ON cp.course_id = r.course_id
)
SELECT EXISTS (
    SELECT 1
    FROM reachable
    WHERE course_id = :new_course_id
) AS would_create_cycle;
~~~

Nếu kết quả là TRUE, đã có đường đi khiến cạnh mới tạo chu trình theo quy ước hướng của ví dụ. Việc kiểm tra và chèn phải được bảo vệ trong một giao dịch có kiểm soát đồng thời. Nếu hai giao dịch cùng kiểm tra trước khi chèn, cả hai có thể thấy trạng thái chưa có chu trình rồi cùng thêm các cạnh tạo thành chu trình. Có thể dùng mức cô lập phù hợp, khóa theo phạm vi đồ thị hoặc cơ chế tuần tự hóa thay đổi quan hệ.

## 6. Nhiều vai trò cố định giữa cùng một loại thực thể

Một quan hệ có thể có nhiều vai trò cố định cùng tham chiếu một bảng. Ví dụ giao dịch chuyển tiền có một tài khoản nguồn và một tài khoản đích.

~~~mermaid
erDiagram
    ACCOUNT ||--o{ TRANSFER : source_account
    ACCOUNT ||--o{ TRANSFER : destination_account
    ACCOUNT {
        bigint account_id PK
        string account_number
    }
    TRANSFER {
        bigint transfer_id PK
        bigint source_account_id FK
        bigint destination_account_id FK
        decimal amount
        datetime created_at
    }
~~~

~~~sql
CREATE TABLE account (
    account_id BIGINT PRIMARY KEY,
    account_number VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE account_transfer (
    transfer_id BIGINT PRIMARY KEY,
    source_account_id BIGINT NOT NULL,
    destination_account_id BIGINT NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_transfer_source
        FOREIGN KEY (source_account_id) REFERENCES account(account_id),
    CONSTRAINT fk_transfer_destination
        FOREIGN KEY (destination_account_id) REFERENCES account(account_id),
    CONSTRAINT ck_transfer_different_accounts
        CHECK (source_account_id <> destination_account_id),
    CONSTRAINT ck_transfer_amount_positive
        CHECK (amount > 0)
);
~~~

Hai cột khóa ngoại tham chiếu cùng bảng Account nhưng có tên và vai trò khác nhau. Hai ràng buộc FK độc lập giúp hệ quản trị kiểm tra cả nguồn lẫn đích. CHECK thể hiện giả định giao dịch không được chuyển tiền cho chính tài khoản nguồn. Nếu nghiệp vụ có loại giao dịch nội bộ cho phép cùng tài khoản, điều kiện phải được điều chỉnh theo loại giao dịch.

Truy vấn lấy tên tài khoản nguồn và đích cũng cần hai bí danh:

~~~sql
SELECT
    tr.transfer_id,
    source.account_number AS source_account,
    destination.account_number AS destination_account,
    tr.amount,
    tr.created_at
FROM account_transfer AS tr
JOIN account AS source
  ON source.account_id = tr.source_account_id
JOIN account AS destination
  ON destination.account_id = tr.destination_account_id;
~~~

Không nên dùng một cột `account_id` duy nhất rồi thêm cột `role` nếu quan hệ luôn có đúng hai vai trò cố định và mỗi vai trò có quy tắc riêng. Hai FK có tên vai trò giúp ràng buộc bắt buộc và truy vấn rõ hơn.

## 7. Nhiều vai trò biến đổi: dùng bảng tham gia

Có trường hợp cùng một loại thực thể tham gia một sự kiện với số lượng và vai trò không cố định. Ví dụ, một cuộc họp có người tổ chức, người trình bày, người ghi biên bản và người tham dự; một người có thể đảm nhận nhiều vai trò nếu quy tắc cho phép.

Khi số vai trò có thể mở rộng, dùng bảng tham gia với một hàng cho mỗi người và vai trò:

~~~sql
CREATE TABLE meeting (
    meeting_id BIGINT PRIMARY KEY,
    meeting_title VARCHAR(200) NOT NULL
);

CREATE TABLE person (
    person_id BIGINT PRIMARY KEY,
    display_name VARCHAR(160) NOT NULL
);

CREATE TABLE meeting_participant (
    meeting_id BIGINT NOT NULL,
    person_id BIGINT NOT NULL,
    role_code VARCHAR(30) NOT NULL,
    joined_at TIMESTAMP,
    CONSTRAINT pk_meeting_participant
        PRIMARY KEY (meeting_id, person_id, role_code),
    CONSTRAINT fk_participant_meeting
        FOREIGN KEY (meeting_id) REFERENCES meeting(meeting_id),
    CONSTRAINT fk_participant_person
        FOREIGN KEY (person_id) REFERENCES person(person_id)
);
~~~

Khóa chính ghép cho phép cùng một người có nhiều vai trò trong một cuộc họp, nhưng không cho phép lặp cùng một vai trò hai lần. Nếu nghiệp vụ quy định mỗi cuộc họp chỉ có một người tổ chức, cần thêm ràng buộc duy nhất có điều kiện theo role_code, hoặc biểu diễn vai trò tổ chức bằng một cột FK riêng. Nếu mỗi người chỉ được có một vai trò, khóa chính có thể là (meeting_id, person_id).

### Chọn giữa FK vai trò cố định và bảng vai trò

| Tình huống | Cách biểu diễn phù hợp |
|---|---|
| Luôn có một người gửi và một người nhận | Hai FK có tên vai trò trên bảng quan hệ |
| Luôn có người quản lý và nhân viên báo cáo | FK tự tham chiếu manager_id trên Employee |
| Có nhiều người tham gia với vai trò thay đổi | Bảng tham gia gồm entity_id và role_code |
| Một người có thể đảm nhận nhiều vai trò trong cùng sự kiện | Khóa gồm event_id, person_id, role_code hoặc cấu trúc tương đương |
| Mỗi vai trò chỉ có tối đa một người | Ràng buộc UNIQUE theo event_id và role_code |
| Vai trò có dữ liệu riêng | Bảng vai trò/tham gia có các thuộc tính tương ứng |

Không nên tạo một cột cho mọi vai trò có thể tưởng tượng nếu vai trò thường xuyên thay đổi. Ngược lại, không nên dùng bảng role quá tổng quát nếu nghiệp vụ chỉ có hai vai trò cố định với các ràng buộc khác nhau.

## 8. Phân biệt cây, rừng và đồ thị có hướng không chu trình

Không phải mọi quan hệ tự tham chiếu đều là cây. Cần xác định cấu trúc được phép:

- **Cây (tree):** một gốc, mỗi node không phải gốc có đúng một cha; không có chu trình và mọi node thuộc cùng cây.
- **Rừng (forest):** nhiều cây độc lập; mỗi node có tối đa một cha.
- **DAG:** đồ thị có hướng không chu trình; một node có thể có nhiều node cha và nhiều node con.
- **Đồ thị tổng quát:** có thể có chu trình, nhiều đường đi và nhiều liên kết khác nhau.

| Nghiệp vụ | Cấu trúc thường gặp | Lưu ý |
|---|---|---|
| Cơ cấu quản lý nhân viên | Cây hoặc rừng | Mỗi nhân viên thường có tối đa một quản lý trực tiếp |
| Danh mục phân cấp một cha | Cây hoặc rừng | Node con có một danh mục cha |
| Khóa học tiên quyết | DAG | Một khóa có thể có nhiều điều kiện tiên quyết |
| Người dùng theo dõi nhau | Đồ thị có hướng tổng quát | Có thể tồn tại vòng theo dõi |
| Quan hệ bạn bè đối xứng | Đồ thị vô hướng về ngữ nghĩa | Cần quy tắc lưu một lần hay hai chiều |

Không được dùng mô hình cây nếu nghiệp vụ cho phép nhiều cha. Cũng không nên áp đặt quy tắc không chu trình cho quan hệ có chu trình hợp lệ, như người dùng theo dõi lẫn nhau.

### Các cách lưu cấu trúc phân cấp

Với quan hệ cây, có một số cách biểu diễn phổ biến:

| Mô hình | Cách lưu | Ưu điểm | Hạn chế |
|---|---|---|---|
| Adjacency list | Mỗi node lưu parent_id | Đơn giản, dễ di chuyển node | Truy vấn toàn cây cần đệ quy |
| Closure table | Lưu mọi cặp ancestor-descendant và depth | Truy vấn tổ tiên/hậu duệ nhanh, rõ | Tốn thêm hàng và chi phí cập nhật |
| Materialized path | Lưu đường dẫn từ gốc đến node | Truy vấn nhánh theo tiền tố thuận tiện | Di chuyển node phải cập nhật đường dẫn con |
| Nested sets | Lưu khoảng trái/phải | Đọc cây con hiệu quả với một số workload | Chèn/di chuyển node có thể cập nhật nhiều hàng |

Adjacency list thường là điểm khởi đầu dễ hiểu. Khi truy vấn tổ tiên/hậu duệ trở thành nút thắt, có thể cân nhắc closure table hoặc materialized path dựa trên workload.

Ví dụ closure table:

Giả sử bảng `employee` đã được tạo như ví dụ adjacency list ở trên. Bảng dưới đây là cấu trúc bổ sung cho cách lưu closure table; có thể dùng nó thay cho việc truy vấn đệ quy nhiều lần trên `manager_id`.

~~~sql
CREATE TABLE employee_hierarchy (
    ancestor_id BIGINT NOT NULL,
    descendant_id BIGINT NOT NULL,
    depth INTEGER NOT NULL,
    CONSTRAINT pk_employee_hierarchy
        PRIMARY KEY (ancestor_id, descendant_id),
    CONSTRAINT fk_hierarchy_ancestor
        FOREIGN KEY (ancestor_id) REFERENCES employee(employee_id),
    CONSTRAINT fk_hierarchy_descendant
        FOREIGN KEY (descendant_id) REFERENCES employee(employee_id),
    CONSTRAINT ck_hierarchy_depth CHECK (depth >= 0)
);
~~~

Bảng closure thường có hàng tự thân với depth = 0 cho mỗi nhân viên, ngoài các quan hệ tổ tiên-hậu duệ. Khi chuyển nhân viên sang nhánh khác, phải cập nhật tập đường đi cũ và mới trong cùng giao dịch. Đây là mô hình dẫn xuất từ quan hệ cha-con; cần có nguồn chuẩn và quy tắc đồng bộ để tránh dữ liệu closure lệch.

## 9. Biểu diễn quan hệ tự tham chiếu trong các họ mô hình

Ý nghĩa vai trò cần giữ nhất quán dù cấu trúc lưu trữ thay đổi.

| Họ mô hình | Cách biểu diễn | Khi phù hợp |
|---|---|---|
| Quan hệ | FK tự tham chiếu, nhiều FK vai trò hoặc bảng liên kết | Cần toàn vẹn tham chiếu, giao dịch và ràng buộc rõ |
| Document | Trường parentId, các trường tham chiếu vai trò hoặc mảng cạnh/participant | Dữ liệu được đọc theo aggregate; cần kiểm soát cập nhật và chu trình ở ứng dụng |
| Đồ thị | Node cùng loại nối bằng edge có hướng và nhãn vai trò | Truy vấn nhiều bước, đường đi và quan hệ lân cận là trọng tâm |
| Phân tích | Dimension tự tham chiếu, bridge hoặc fact quan hệ | Cần phân tích phân cấp, vai trò nguồn/đích hoặc lịch sử quan hệ |

### Document: parent reference và embedded children

Một document danh mục có thể lưu `parentId` để tham chiếu document cha. Cách này gần với adjacency list. Có thể nhúng children nếu cây nhỏ, cấu trúc ít thay đổi và thường được đọc cùng cha; nhưng nhúng toàn bộ hậu duệ có thể làm document lớn và khó di chuyển node.

Với hai vai trò cố định, có thể lưu `sourceAccountId` và `destinationAccountId`. Với nhiều vai trò biến đổi, mảng participant chứa personId và roleCode phù hợp hơn. Cần xác thực rằng các ID tham chiếu tồn tại và các quy tắc cardinality được bảo vệ trong luồng ghi.

### Đồ thị: cùng loại node, nhiều nhãn quan hệ

Trong graph database, hai đầu edge có thể là node cùng nhãn nhưng edge thể hiện hướng và vai trò:

~~~mermaid
flowchart LR
    A["(:Employee {id: A})"] -->|"MANAGES"| B["(:Employee {id: B})"]
    C["(:Employee {id: C})"] -->|"MENTORS"| B
~~~

Nhân viên B có thể được A quản lý và được C hướng dẫn. Hai quan hệ khác loại có cùng đích nhưng mang ý nghĩa khác nhau. Nếu chỉ lưu một trường `relatedEmployeeId`, thông tin vai trò sẽ bị mất.

### Phân tích: vai trò dimension

Trong kho dữ liệu, một fact có thể tham chiếu cùng dimension nhân viên ở nhiều vai trò, ví dụ người tạo giao dịch, người phê duyệt và người nhận xử lý. Cần tạo các role-playing dimensions hoặc nhiều khóa ngoại có tên vai trò. Báo cáo phải dùng đúng bí danh dimension cho từng vai trò để không nhầm người tạo với người phê duyệt.

## 10. Vòng đời, thời gian và xóa quan hệ

Quan hệ tự tham chiếu có thể thay đổi theo thời gian. Một nhân viên chuyển sang quản lý mới; một khóa học thay đổi điều kiện tiên quyết; một người dùng bỏ theo dõi người khác; một tài khoản bị đóng.

Cần phân biệt:

- **Quan hệ hiện tại:** chỉ giữ liên kết đang có hiệu lực.
- **Lịch sử quan hệ:** giữ các lần liên kết và thời gian bắt đầu/kết thúc.
- **Snapshot:** lưu vai trò hoặc thông tin tại thời điểm một sự kiện xảy ra.
- **Quan hệ dẫn xuất:** được tính từ các quan hệ gốc, ví dụ đường đi trong cây hoặc closure table.

Nếu cần lịch sử, có thể thêm `valid_from`, `valid_to`, `created_at`, `ended_at` hoặc trạng thái. Khi đó, quy tắc duy nhất phải xét đến khoảng hiệu lực. Ví dụ một nhân viên có thể có nhiều quản lý qua thời gian nhưng chỉ có tối đa một quản lý trực tiếp đang hoạt động tại một thời điểm.

Chính sách xóa cũng cần rõ:

- `ON DELETE RESTRICT`: không cho xóa thực thể đang được tham chiếu.
- `ON DELETE SET NULL`: giữ thực thể con nhưng bỏ quan hệ cha; phù hợp nếu quan hệ không bắt buộc và không cần lưu lịch sử riêng.
- `ON DELETE CASCADE`: xóa các hàng quan hệ phụ thuộc; chỉ dùng khi đúng vòng đời nghiệp vụ.
- Ngừng hoạt động/soft delete: giữ dữ liệu và lịch sử, thường phù hợp với nhân sự, tài khoản và dữ liệu kiểm toán.

Không nên chọn CASCADE chỉ để tránh lỗi khóa ngoại. Xóa một nhân viên có thể làm mất cây báo cáo hoặc lịch sử quản lý nếu không có quy tắc chuyển giao trước.

## 11. Kiểm chứng quan hệ tự tham chiếu và nhiều vai trò

Sau khi thiết kế, hãy tạo các ca kiểm thử cụ thể:

1. Tạo quan hệ hợp lệ giữa hai thực thể khác nhau cùng loại.
2. Thử tự tham chiếu A → A nếu nghiệp vụ cấm.
3. Thử tạo cặp ngược A → B và B → A để kiểm tra quy tắc đối xứng hoặc chu trình.
4. Với cây, thử gán một node có hai cha.
5. Với DAG, thử tạo chu trình ba node.
6. Với nhiều vai trò cố định, thử bỏ trống vai trò bắt buộc hoặc dùng cùng thực thể ở hai vai trò nếu bị cấm.
7. Với bảng vai trò, thử lặp cùng vai trò và thử một người có nhiều vai trò.
8. Thử xóa node cha hoặc node đang được tham chiếu.
9. Thử thay đổi quan hệ đồng thời từ hai giao dịch.
10. Đối chiếu lịch sử và dữ liệu dẫn xuất sau khi chuyển node hoặc đổi vai trò.

### Truy vấn tìm nhân viên tự quản lý

~~~sql
SELECT employee_id, manager_id
FROM employee
WHERE employee_id = manager_id;
~~~

### Truy vấn tìm nhân viên có nhiều hơn một quản lý đang hoạt động

Giả sử lịch sử quản lý được lưu trong `employee_manager_history`:

~~~sql
SELECT
    employee_id,
    COUNT(*) AS active_manager_count
FROM employee_manager_history
WHERE valid_to IS NULL
GROUP BY employee_id
HAVING COUNT(*) > 1;
~~~

Kết quả phải rỗng nếu quy tắc nghiệp vụ yêu cầu tối đa một quản lý trực tiếp đang hoạt động. Truy vấn kiểm tra dữ liệu hiện có không thay thế ràng buộc bảo vệ thao tác ghi.

### Truy vấn kiểm tra vai trò nguồn và đích

Với giao dịch tài khoản, cần xác minh cả hai FK đều tồn tại và không vi phạm quy tắc khác tài khoản. Ràng buộc CHECK và FK đã bảo vệ các điều kiện đơn giản; các quy tắc như tài khoản đang hoạt động, cùng loại tiền hoặc đủ số dư cần được kiểm tra trong giao dịch nghiệp vụ có kiểm soát đồng thời.

## 12. Quy trình thiết kế và tài liệu hóa

Với mỗi quan hệ tự tham chiếu hoặc nhiều vai trò cùng loại thực thể:

1. Xác định loại thực thể tham gia và lý do hai đầu cùng loại.
2. Đặt tên vai trò riêng cho từng đầu; viết câu nghiệp vụ theo từng vai trò.
3. Xác định hướng, tính đối xứng, khả năng tự tham chiếu và tính bắc cầu.
4. Ghi min/max ở từng vai trò, không suy diễn từ đầu còn lại.
5. Xác định cấu trúc là một-nhiều, nhiều-nhiều, cây, rừng, DAG hay đồ thị tổng quát.
6. Xác định thuộc tính của quan hệ và nhu cầu lưu lịch sử.
7. Chọn FK tự tham chiếu, nhiều FK cố định, bảng liên kết hoặc cấu trúc node/edge.
8. Định nghĩa ràng buộc khóa, duy nhất, không tự tham chiếu, không chu trình và quy tắc vai trò.
9. Xác định chính sách xóa, lưu trữ và chuyển đổi quan hệ.
10. Kiểm chứng bằng self join, truy vấn đệ quy, ca chu trình và thao tác đồng thời.

### Mẫu đặc tả

| Trường | Nội dung |
|---|---|
| Loại thực thể | Ví dụ Employee |
| Tên quan hệ | MANAGES, PREREQUISITE_OF, TRANSFERS_TO |
| Vai trò đầu A | Manager, Course, Source account |
| Vai trò đầu B | Subordinate, Prerequisite, Destination account |
| Hướng | Có hướng, đối xứng hoặc hai chiều độc lập |
| Bội số | Min..max cho từng vai trò |
| Tự tham chiếu | Có/không; điều kiện cho phép |
| Chu trình | Cho phép, cấm hoặc chỉ cấm một số loại chu trình |
| Thuộc tính quan hệ | Thời gian, trạng thái, số tiền, hiệu lực |
| Lịch sử | Chỉ trạng thái hiện tại hay lưu các phiên bản |
| Biểu diễn | FK tự tham chiếu, nhiều FK, bảng liên kết, node/edge |
| Toàn vẹn | PK, FK, UNIQUE, CHECK, transaction hoặc thuật toán |
| Kiểm chứng | Ca hợp lệ, tự tham chiếu, chu trình, đồng thời và xóa |

## 13. Bài tập thực hành và tiêu chí đánh giá

### Bài 1 — Cơ cấu nhân viên

Một nhân viên có tối đa một quản lý trực tiếp, nhưng có thể hướng dẫn nhiều nhân viên khác. Hệ thống cần lưu lịch sử điều chuyển quản lý theo thời gian.

Hãy xác định vai trò Manager và Subordinate, bội số, cấu trúc cây/rừng, thiết kế bảng hiện tại và bảng lịch sử. Nêu cách bảo đảm một nhân viên không có hai quản lý trực tiếp cùng hiệu lực.

### Bài 2 — Khóa học tiên quyết

Một khóa học có thể yêu cầu nhiều khóa học khác và một khóa có thể là điều kiện cho nhiều khóa khác. Không được có chu trình.

Hãy thiết kế bảng liên kết, khóa, CHECK tự tham chiếu và thuật toán phát hiện chu trình. Giải thích cách bảo vệ kiểm tra khi có hai người cùng cập nhật danh mục khóa học.

### Bài 3 — Chuyển tiền

Một giao dịch có tài khoản nguồn và tài khoản đích. Hai vai trò bắt buộc, phải khác nhau; mỗi tài khoản có thể tham gia nhiều giao dịch.

Hãy thiết kế hai FK có tên vai trò, viết truy vấn self join hai bí danh và liệt kê các quy tắc cần kiểm tra trong giao dịch chuyển tiền.

### Bài 4 — Cuộc họp nhiều vai trò

Một cuộc họp có người tổ chức, người trình bày, người ghi biên bản và người tham dự. Một người có thể đảm nhiệm nhiều vai trò, nhưng mỗi cuộc họp chỉ có một người tổ chức.

Hãy chọn giữa các FK cố định và bảng participant, định nghĩa khóa và ràng buộc duy nhất cho vai trò tổ chức.

### Rubric tự đánh giá

| Tiêu chí | Đạt yêu cầu khi |
|---|---|
| Nhận diện | Xác định đúng quan hệ giữa các thể hiện cùng loại thực thể |
| Vai trò | Đặt tên rõ cho từng đầu, không nhầm nguồn và đích |
| Bội số | Xác định min/max riêng cho từng vai trò |
| Cấu trúc đồ thị | Phân biệt cây, rừng, DAG và đồ thị tổng quát |
| Biểu diễn | Chọn đúng self-FK, nhiều FK hoặc bảng liên kết |
| Toàn vẹn | Kiểm soát tự tham chiếu, trùng lặp, chu trình và vai trò bắt buộc |
| Vòng đời | Xử lý xóa, thay đổi và lịch sử quan hệ |
| Kiểm chứng | Có truy vấn và ca kiểm thử cho các trường hợp biên |

Quan hệ tự tham chiếu không chỉ là một khóa ngoại trỏ về chính bảng của nó. Điều quan trọng là xác định đúng vai trò của từng đầu, bội số, hướng và cấu trúc đồ thị mà nghiệp vụ cho phép. Khi những quyết định này được thể hiện rõ, mô hình dữ liệu có thể biểu diễn cây quản lý, điều kiện tiên quyết, chuyển giao giữa tài khoản và các sự kiện nhiều vai trò một cách nhất quán, dễ truy vấn và dễ tiến hóa.


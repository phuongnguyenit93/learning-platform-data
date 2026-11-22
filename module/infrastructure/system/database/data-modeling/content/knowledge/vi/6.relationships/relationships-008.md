# Quan hệ có hướng, có thứ tự hoặc có giới hạn số lượng

Trong module **DATABASE_DATA_MODELING**, mô hình dữ liệu cần mô tả chính xác không chỉ những thực thể nào tồn tại mà còn cách chúng liên hệ với nhau. Một quan hệ có thể mang ý nghĩa **có hướng**, có **thứ tự** hoặc bị **giới hạn số lượng** ở một hay cả hai đầu. Những đặc điểm này ảnh hưởng trực tiếp đến ngữ nghĩa nghiệp vụ, cấu trúc khóa, ràng buộc toàn vẹn và cách truy vấn dữ liệu.

Nếu bỏ qua hướng, hệ thống có thể hiểu nhầm ai phụ thuộc vào ai hoặc đối tượng nào là nguồn và đối tượng nào là đích. Nếu bỏ qua thứ tự, một danh sách quy trình, tuyến đường hoặc nội dung phát lại có thể bị sắp xếp sai. Nếu không mô tả giới hạn số lượng, dữ liệu có thể vi phạm quy tắc như “mỗi đơn chỉ có một hóa đơn chính”, “một nhân viên có tối đa hai người liên hệ khẩn cấp” hoặc “một khóa học cần ít nhất một học phần tiên quyết khi được mở”.

Bài học này giúp nhận diện ba đặc điểm đó, biểu diễn chúng trong mô hình khái niệm và chuyển thành ràng buộc có thể kiểm chứng.

## 1. Quan hệ có nhiều chiều ngữ nghĩa

Một quan hệ mô tả cách hai hoặc nhiều thực thể tham gia cùng một sự kiện hoặc liên kết nghiệp vụ. Khi mô hình hóa, cần trả lời:

- Những thực thể hoặc vai trò nào tham gia?
- Một phía đóng vai trò gì và phía còn lại đóng vai trò gì?
- Quan hệ có phân biệt nguồn và đích không?
- Các liên kết có thứ tự hay chỉ là một tập không thứ tự?
- Mỗi thực thể được tham gia tối thiểu và tối đa bao nhiêu lần?
- Quan hệ có thuộc tính riêng như thời điểm, trạng thái, thứ tự, người tạo hoặc hiệu lực không?
- Quy tắc có thay đổi theo trạng thái hoặc thời gian không?

Ba đặc điểm có thể cùng xuất hiện. Ví dụ, một quy trình phê duyệt có các bước nối theo hướng từ bước trước đến bước sau, mỗi bước có vị trí và một yêu cầu có thể giới hạn tối đa năm người phê duyệt. Không nên xem “có hướng”, “có thứ tự” và “có giới hạn” là ba lựa chọn loại trừ nhau.

### Bội số và số lượng tham gia

Bội số (multiplicity/cardinality) mô tả số lượng liên kết có thể có ở mỗi đầu quan hệ. Một số cách ghi thường dùng:

| Ký hiệu | Ý nghĩa |
|---|---|
| 0..1 | Không có hoặc có tối đa một |
| 1..1 hoặc 1 | Bắt buộc đúng một |
| 0..N hoặc 0..* | Có thể không có hoặc có nhiều |
| 1..N hoặc 1..* | Phải có ít nhất một, có thể nhiều |
| 2..5 | Từ hai đến năm phần tử |

Cần xác định rõ đang nói về số lượng ở phía nào. Với quan hệ Khách hàng đặt Đơn hàng, một khách hàng có thể đặt 0..N đơn; mỗi đơn thuộc về đúng một khách hàng. Đây là hai ràng buộc khác nhau.

Ngoài bội số, cần phân biệt **tính bắt buộc tham gia** với **giới hạn tối đa**. “Một đơn phải có ít nhất một dòng hàng khi được xác nhận” là ràng buộc tối thiểu có điều kiện theo trạng thái. “Một nhân viên có tối đa hai người liên hệ khẩn cấp đang hoạt động” là giới hạn tối đa trên tập liên kết.

## 2. Quan hệ có hướng

**Quan hệ có hướng (directed relationship)** phân biệt vai trò của hai đầu liên kết. Một phía là nguồn, bên kia là đích, hoặc mỗi đầu có vai trò nghiệp vụ riêng. Đảo ngược hướng sẽ tạo ra một ý nghĩa khác.

Ví dụ:

- Khóa học A là điều kiện tiên quyết của khóa học B.
- Nhân viên M quản lý nhân viên N.
- Tài khoản A chuyển tiền cho tài khoản B.
- Người dùng A theo dõi người dùng B.
- Công việc X phụ thuộc vào công việc Y.

Trong quan hệ “A là điều kiện tiên quyết của B”, hướng có thể được diễn giải là A phải hoàn thành trước khi B được học. Nếu đảo hai đầu, ý nghĩa sẽ thành B là điều kiện tiên quyết của A.

~~~mermaid
flowchart LR
    A["Khóa học A"] -->|"phải hoàn thành trước"| B["Khóa học B"]
    B -->|"phải hoàn thành trước"| C["Khóa học C"]
~~~

### Xác định vai trò nguồn và đích

Không nên chỉ đặt tên chung như `related_course` hoặc `linked_employee`. Hãy đặt tên theo vai trò:

- `course_id`: khóa học đang yêu cầu điều kiện tiên quyết.
- `prerequisite_course_id`: khóa học phải hoàn thành trước.
- `manager_id`: người quản lý.
- `subordinate_id`: nhân viên được quản lý.
- `source_account_id`: tài khoản chuyển tiền.
- `destination_account_id`: tài khoản nhận tiền.

Tên vai trò giúp người đọc hiểu được hướng ngay cả khi không nhìn sơ đồ. Với quan hệ tự tham chiếu, chẳng hạn nhân viên quản lý nhân viên, hai đầu đều trỏ đến cùng một bảng nhưng có vai trò khác nhau.

### Quan hệ có hướng không tự động có quan hệ ngược

Nếu A theo dõi B, không có nghĩa B theo dõi A. Nếu A là quản lý của B, không có nghĩa B quản lý A. Một số quan hệ có thể có cặp liên kết ngược, nhưng phải được nghiệp vụ xác nhận.

Cần phân biệt:

- **Bất đối xứng:** A liên kết với B không kéo theo B liên kết với A, ví dụ theo dõi hoặc phụ thuộc.
- **Đối xứng:** nếu A là bạn của B thì B cũng là bạn của A, theo định nghĩa nghiệp vụ.
- **Phản xạ:** một đối tượng có được phép liên kết với chính nó không?
- **Phi phản xạ:** một đối tượng không được phép liên kết với chính nó, ví dụ khóa học không thể là điều kiện tiên quyết của chính nó.
- **Bắc cầu:** nếu A liên quan B và B liên quan C, có suy ra A liên quan C không? Không nên tự suy diễn tính bắc cầu nếu nghiệp vụ chưa định nghĩa.

Một quan hệ đối xứng có thể được lưu bằng một cặp chuẩn hóa để tránh lưu cả A-B và B-A, hoặc lưu hai chiều nếu hệ thống cần truy vấn theo từng hướng. Cách lưu phải có quy tắc duy nhất rõ ràng.

### Biểu diễn quan hệ có hướng trong mô hình quan hệ

Ví dụ khóa học có thể có nhiều khóa học tiên quyết:

~~~mermaid
erDiagram
    COURSE ||--o{ COURSE_PREREQUISITE : requires
    COURSE ||--o{ COURSE_PREREQUISITE : prerequisite_for
    COURSE {
        bigint course_id PK
        string course_name
    }
    COURSE_PREREQUISITE {
        bigint course_id PK, FK
        bigint prerequisite_course_id PK, FK
    }
~~~

DDL minh họa:

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
    CONSTRAINT fk_cp_course
        FOREIGN KEY (course_id) REFERENCES course(course_id),
    CONSTRAINT fk_cp_prerequisite
        FOREIGN KEY (prerequisite_course_id) REFERENCES course(course_id),
    CONSTRAINT ck_course_not_own_prerequisite
        CHECK (course_id <> prerequisite_course_id)
);
~~~

Trong bảng này, `course_id` là khóa học cần điều kiện; `prerequisite_course_id` là khóa học phải hoàn thành trước. Khóa chính ghép ngăn cùng một cặp có hướng bị ghi lặp. Nó không tự cấm cặp ngược; nếu nghiệp vụ cấm hai khóa học làm điều kiện tiên quyết lẫn nhau, cần kiểm tra riêng.

Ràng buộc CHECK chỉ cấm một khóa học tự làm điều kiện cho chính nó. Nó không phát hiện chu trình dài như A phụ thuộc B, B phụ thuộc C và C phụ thuộc A. Nếu quan hệ phải tạo thành đồ thị có hướng không chu trình (DAG), cần kiểm tra khả năng tạo chu trình bằng truy vấn đệ quy hoặc thuật toán đồ thị trong một giao dịch có kiểm soát đồng thời. Không thể thay thế kiểm tra chu trình bằng khóa ngoại thông thường.

## 3. Quan hệ có thứ tự

**Quan hệ có thứ tự (ordered relationship)** là quan hệ mà vị trí hoặc trình tự của các phần tử mang ý nghĩa nghiệp vụ. Ví dụ:

- Các bước trong quy trình phê duyệt.
- Các chặng của một hành trình.
- Các bài học trong một khóa học.
- Các bài hát trong danh sách phát.
- Các mục ưu tiên trong hàng đợi xử lý.
- Các phiên bản hoặc giai đoạn theo thời gian.

Một quan hệ nhiều-nhiều thông thường không mặc định có thứ tự. Nếu thứ tự có ý nghĩa, cần mô hình hóa nó rõ ràng bằng vị trí, số thứ tự, thời điểm hoặc quy tắc sắp xếp.

### Thứ tự nghiệp vụ và thứ tự hiển thị

Cần phân biệt hai trường hợp:

- **Thứ tự nghiệp vụ:** thay đổi vị trí làm thay đổi ý nghĩa hoặc quy trình. Ví dụ bước phê duyệt thứ hai chỉ được chạy sau bước thứ nhất.
- **Thứ tự hiển thị:** chỉ quy định cách trình bày danh sách, có thể thay đổi mà không làm thay đổi nghiệp vụ. Ví dụ sắp xếp danh sách sản phẩm theo tên.

Không nên lưu thứ tự hiển thị vào mô hình nghiệp vụ nếu nó chỉ là lựa chọn giao diện tạm thời. Ngược lại, nếu vị trí quyết định quy trình, phải bảo vệ nó như dữ liệu nghiệp vụ.

### Các cách biểu diễn thứ tự

| Cách biểu diễn | Phù hợp khi | Điểm cần lưu ý |
|---|---|---|
| Số vị trí (position/sequence_no) | Danh sách có thứ tự tường minh | Cần xác định duy nhất trong phạm vi cha và cách đổi vị trí |
| Thời điểm (occurred_at/effective_at) | Thứ tự được xác định theo thời gian thực tế | Cần xử lý hai sự kiện cùng thời điểm và độ chính xác timestamp |
| Quan hệ trước/sau | Chỉ cần biết thứ tự phụ thuộc, không cần vị trí tuyệt đối | Có thể tạo chu trình; truy vấn thứ tự đầy đủ phức tạp hơn |
| Khóa sắp xếp (sort_key) | Thường xuyên chèn giữa các phần tử | Cần quy tắc tái cân bằng và tránh trùng khóa |

Không được dựa vào thứ tự vật lý của hàng trong cơ sở dữ liệu. Nếu cần thứ tự, truy vấn phải sắp xếp tường minh theo cột được định nghĩa, ví dụ `ORDER BY position`.

### Ví dụ: danh sách phát có thứ tự

Một danh sách phát chứa nhiều bài hát; mỗi bài có vị trí riêng trong danh sách. Giả sử mỗi bài chỉ xuất hiện tối đa một lần trong cùng danh sách:

~~~mermaid
erDiagram
    PLAYLIST ||--o{ PLAYLIST_ITEM : contains
    TRACK ||--o{ PLAYLIST_ITEM : selected_as
    PLAYLIST {
        bigint playlist_id PK
        string playlist_name
    }
    PLAYLIST_ITEM {
        bigint playlist_id PK, FK
        int position PK
        bigint track_id FK
        datetime added_at
    }
~~~

~~~sql
CREATE TABLE playlist (
    playlist_id BIGINT PRIMARY KEY,
    playlist_name VARCHAR(200) NOT NULL
);

CREATE TABLE track (
    track_id BIGINT PRIMARY KEY,
    track_title VARCHAR(200) NOT NULL
);

CREATE TABLE playlist_item (
    playlist_id BIGINT NOT NULL,
    position INTEGER NOT NULL,
    track_id BIGINT NOT NULL,
    added_at TIMESTAMP NOT NULL,
    CONSTRAINT pk_playlist_item
        PRIMARY KEY (playlist_id, position),
    CONSTRAINT uq_playlist_track
        UNIQUE (playlist_id, track_id),
    CONSTRAINT fk_item_playlist
        FOREIGN KEY (playlist_id) REFERENCES playlist(playlist_id),
    CONSTRAINT fk_item_track
        FOREIGN KEY (track_id) REFERENCES track(track_id),
    CONSTRAINT ck_playlist_position_positive
        CHECK (position > 0)
);
~~~

Khóa chính ghép bảo đảm mỗi vị trí trong một danh sách chỉ có một bài hát. UNIQUE bảo đảm một bài hát không xuất hiện hai lần trong cùng danh sách theo giả định nghiệp vụ. Nếu cho phép phát lại cùng bài nhiều lần, cần bỏ ràng buộc UNIQUE này; mỗi lần xuất hiện vẫn có vị trí riêng.

DDL trên chưa tự giới hạn danh sách tối đa 100 bài. Đây là quy tắc đếm nhiều hàng, nên cần kiểm tra trong cùng giao dịch với cơ chế chống tranh chấp. Một cách triển khai là mọi thao tác thêm bài đều khóa hàng playlist tương ứng trước khi đếm và chèn:

~~~text
BEGIN TRANSACTION
  Lock the playlist row for this playlist_id
  Count playlist_item rows for this playlist_id
  If count >= 100, reject the insert
  Otherwise, insert the new playlist_item
COMMIT
~~~

Đây là giả mã mô tả thứ tự thao tác. Trên PostgreSQL có thể dùng `SELECT ... FOR UPDATE` để khóa hàng playlist; các luồng ghi phải tuân thủ cùng giao thức. Có thể dùng trigger hoặc bộ đếm được cập nhật nguyên tử nếu phù hợp hơn, nhưng phải bảo đảm hai giao dịch đồng thời không cùng nhìn thấy một slot còn trống rồi cùng chèn.

Truy vấn lấy danh sách theo đúng thứ tự:

~~~sql
SELECT
    pi.position,
    t.track_id,
    t.track_title
FROM playlist_item pi
JOIN track t ON t.track_id = pi.track_id
WHERE pi.playlist_id = :playlist_id
ORDER BY pi.position;
~~~

### Đổi vị trí và tính duy nhất

Nếu hai phần tử đổi chỗ, việc cập nhật từng hàng có thể tạm thời vi phạm UNIQUE(playlist_id, position). Có thể dùng vị trí tạm, cập nhật theo thứ tự an toàn hoặc cơ chế constraint trì hoãn nếu hệ quản trị hỗ trợ. Khi nhiều người chỉnh sửa cùng danh sách, cần kiểm soát xung đột để hai giao dịch không gán cùng vị trí.

Nếu danh sách rất dài và thường xuyên chèn giữa, có thể dùng sort key có khoảng trống hoặc thứ tự phân số. Tuy nhiên, cách này cần chiến lược xử lý khóa gần nhau, độ chính xác và tái cân bằng. Số vị trí tuần tự thường dễ hiểu hơn nếu tần suất thay đổi thứ tự thấp.

## 4. Quan hệ có giới hạn số lượng

**Quan hệ có giới hạn số lượng (bounded relationship)** đặt ra số lần tham gia tối thiểu hoặc tối đa của một thực thể ở một đầu quan hệ.

Ví dụ:

- Mỗi đơn đã xác nhận phải có ít nhất một dòng hàng.
- Mỗi nhân viên có tối đa hai người liên hệ khẩn cấp đang hoạt động.
- Mỗi tài khoản chỉ có một người đại diện chính tại một thời điểm.
- Một nhóm có từ ba đến tám thành viên.
- Một quy trình có tối đa năm cấp phê duyệt.

Hãy viết giới hạn bằng ngôn ngữ rõ ràng và xác định phạm vi:

- Tối thiểu hay tối đa?
- Áp dụng cho mọi bản ghi hay chỉ một trạng thái?
- Đếm phần tử hiện tại hay cả lịch sử?
- Tính theo từng chủ thể, từng loại hay toàn hệ thống?
- Có hiệu lực tại thời điểm nào?

### Phân biệt giới hạn theo mỗi phía

Ví dụ quan hệ Nhóm – Thành viên:

- Một nhóm có từ 3 đến 8 thành viên đang hoạt động.
- Một thành viên có thể thuộc 0 đến 5 nhóm.

Hai giới hạn này áp dụng ở hai phía khác nhau. Nếu chỉ ghi “nhóm có tối đa 8 thành viên”, không thể suy ra mỗi thành viên chỉ được tham gia tối đa 8 nhóm.

~~~mermaid
flowchart LR
    G["Nhóm"] -->|"3..8 thành viên"| M1["Thành viên"]
    M2["Thành viên"] -->|"0..5 nhóm"| G2["Nhóm"]
~~~

Sơ đồ quan hệ nên ghi bội số cạnh đúng đầu thực thể. Khi dùng ký pháp ERD hoặc UML, phải kiểm tra quy ước của công cụ để tránh đọc nhầm phía được giới hạn.

### Ràng buộc tối đa một

Một trường hợp thường gặp là “mỗi khách hàng có tối đa một địa chỉ chính đang hoạt động”. Có thể dùng cờ `is_primary` trên bảng địa chỉ và ràng buộc duy nhất có điều kiện nếu hệ quản trị hỗ trợ partial/filtered unique index.

Ví dụ theo cú pháp PostgreSQL:

~~~sql
CREATE UNIQUE INDEX uq_customer_one_active_primary_address
    ON customer_address (customer_id)
    WHERE is_active = TRUE AND is_primary = TRUE;
~~~

Ràng buộc này ngăn một khách hàng có hai địa chỉ vừa hoạt động vừa được đánh dấu chính. Nó không bắt buộc khách hàng phải có ít nhất một địa chỉ chính; đó là quy tắc tối thiểu khác và cần được bảo vệ ở thời điểm nghiệp vụ thích hợp.

### Ràng buộc số lượng tối đa lớn hơn một

Giả sử mỗi nhân viên được có tối đa hai người liên hệ khẩn cấp đang hoạt động. Nếu giới hạn nhỏ và cố định, có thể mô hình hóa một vị trí trong tập cho phép:

~~~sql
CREATE TABLE employee_emergency_contact (
    employee_id BIGINT NOT NULL,
    slot_no SMALLINT NOT NULL,
    contact_name VARCHAR(160) NOT NULL,
    phone_number VARCHAR(32) NOT NULL,
    is_active BOOLEAN NOT NULL,
    CONSTRAINT pk_employee_emergency_contact
        PRIMARY KEY (employee_id, slot_no),
    CONSTRAINT fk_emergency_contact_employee
        FOREIGN KEY (employee_id) REFERENCES employee(employee_id),
    CONSTRAINT ck_emergency_contact_slot
        CHECK (slot_no IN (1, 2))
);
~~~

Khóa chính ghép cùng CHECK giới hạn mỗi nhân viên có tối đa hai slot. Thiết kế này thích hợp nếu hai vị trí là một giới hạn nhỏ, cố định và không mang thứ tự nghiệp vụ phức tạp. Nếu số lượng tối đa thay đổi theo chính sách hoặc phụ thuộc loại liên hệ, slot cố định có thể gây khó tiến hóa.

Với giới hạn tổng quát như tối đa N bản ghi đang hoạt động, CHECK trên từng hàng không đủ vì điều kiện phụ thuộc nhiều hàng. Cần cơ chế kiểm soát đồng thời: transaction có khóa trên bản ghi cha, trigger phù hợp hoặc bộ đếm được cập nhật nguyên tử cùng thao tác thêm/xóa. Cần tránh tình huống hai giao dịch cùng đếm thấy còn chỗ rồi đồng thời thêm, khiến giới hạn bị vượt.

### Ràng buộc tối thiểu

Ví dụ “đơn hàng đã xác nhận phải có ít nhất một dòng hàng” là điều kiện trên cả tập dòng hàng và trạng thái của đơn. Một CHECK ở bảng order chỉ kiểm tra cột của chính hàng đó, không thể trực tiếp đếm các dòng trong bảng order_line.

Có thể kiểm tra khi chuyển đơn từ DRAFT sang CONFIRMED trong cùng giao dịch: khóa hoặc bảo vệ đơn hàng, kiểm tra có ít nhất một dòng, rồi mới cập nhật trạng thái. Nếu hệ quản trị hỗ trợ constraint trigger trì hoãn, có thể dùng cơ chế đó để kiểm tra ở thời điểm commit. Phải xác định rõ cách ngăn giao dịch đồng thời xóa dòng cuối cùng trong khi giao dịch khác xác nhận đơn.

## 5. Khi quan hệ có hướng, thứ tự và giới hạn cùng xuất hiện

Trong thực tế, các đặc điểm này thường kết hợp.

Ví dụ một quy trình phê duyệt có tối đa năm bước. Mỗi bước trỏ đến bước tiếp theo; thứ tự quyết định ai phê duyệt trước; một bước có thể có người phê duyệt chính và người thay thế. Mô hình cần biểu diễn:

- Hướng từ bước trước sang bước sau.
- Vị trí của từng bước trong quy trình.
- Giới hạn tối đa năm bước.
- Mỗi vị trí chỉ có một bước trong cùng quy trình.
- Không có bước tự trỏ đến chính nó.
- Quy tắc không tạo chu trình.
- Lịch sử thay đổi khi quy trình đã được kích hoạt.

Một lựa chọn khác là lưu `sequence_no` trên bảng bước, rồi suy ra bước trước/sau bằng vị trí. Nếu chỉ có một tuyến tính duy nhất, không nhất thiết phải lưu cả `next_step_id` và `sequence_no`, vì hai nguồn thứ tự có thể mâu thuẫn. Nếu quy trình có nhiều nhánh, cần mô hình hóa các cạnh chuyển tiếp riêng và xác định rõ thứ tự hiển thị khác với luồng thực thi.

### Tránh lưu cùng một sự thật ở nhiều nơi

Nếu `position = 3` xác định bước thứ ba, đồng thời `previous_step_id` và `next_step_id` cũng được lưu, mỗi lần di chuyển bước phải cập nhật nhiều quan hệ. Nếu một trường không thể suy ra an toàn từ trường còn lại, cần có lý do cụ thể. Mỗi dữ kiện nên có một nguồn chuẩn hoặc có quy tắc đồng bộ được kiểm chứng.

## 6. Chuyển các đặc điểm quan hệ sang mô hình dữ liệu

| Đặc điểm | Mô hình khái niệm | Mô hình quan hệ | Document | Đồ thị |
|---|---|---|---|---|
| Có hướng | Vai trò nguồn và đích rõ ràng | Hai FK có tên vai trò | Hai trường tham chiếu có ý nghĩa | Edge có hướng từ source đến target |
| Có thứ tự | Vị trí hoặc quy tắc trình tự | Cột position/sequence hoặc thời điểm | Mảng có thứ tự hoặc trường sort key | Thuộc tính thứ tự trên edge/node hoặc quan hệ trước-sau |
| Giới hạn số lượng | Min/max ở từng đầu quan hệ | UNIQUE, CHECK, trigger hoặc transaction | Validation và cập nhật nguyên tử trên aggregate | Ràng buộc/kiểm tra theo ứng dụng hoặc khả năng của graph engine |
| Có thuộc tính riêng | Quan hệ được mô hình hóa như association có thuộc tính | Bảng liên kết | Object lồng hoặc document liên kết | Thuộc tính trên edge hoặc node quan hệ |

Trong mô hình phân tích, quan hệ nhiều-nhiều thường cần bridge table. Nếu quan hệ có hướng, bridge phải giữ đúng vai trò nguồn/đích. Nếu có thứ tự, lưu sequence hoặc effective time. Nếu có giới hạn, cần kiểm tra ở nguồn giao dịch hoặc trong quy trình nạp dữ liệu; kho phân tích thường không phải nơi duy nhất bảo vệ quy tắc nghiệp vụ.

## 7. Kiểm chứng các ràng buộc quan hệ

Một sơ đồ đúng chưa đủ. Hãy kiểm chứng từng đặc điểm bằng các ca hợp lệ và không hợp lệ.

### Kiểm tra hướng

- Tạo quan hệ A → B và xác minh truy vấn không diễn giải thành B → A.
- Thử tạo liên kết ngược B → A để xem nghiệp vụ có cho phép không.
- Kiểm tra quan hệ tự tham chiếu A → A.
- Nếu có yêu cầu DAG, thử tạo chu trình ngắn và chu trình nhiều bước.

### Kiểm tra thứ tự

- Tạo ba phần tử có vị trí 1, 2, 3 và xác minh truy vấn trả về đúng thứ tự.
- Thử gán trùng vị trí trong cùng phạm vi cha.
- Đổi vị trí hai phần tử và kiểm tra cập nhật không để lại thứ tự trùng hoặc thiếu ngoài quy ước.
- Thử hai người dùng sắp xếp cùng lúc.
- Nếu dùng thời gian, thử các sự kiện có timestamp giống nhau.

### Kiểm tra giới hạn

- Thử tạo ít hơn số lượng tối thiểu.
- Thử đúng giới hạn tối đa.
- Thử vượt giới hạn tối đa.
- Thử xóa phần tử khiến tập vi phạm số lượng tối thiểu.
- Thử hai giao dịch đồng thời cùng thêm phần tử cuối cùng.
- Thử chuyển trạng thái làm quy tắc cardinality bắt đầu có hiệu lực.

### Kiểm tra ví dụ bằng truy vấn

Tìm các khóa học có quan hệ tiên quyết tự tham chiếu hoặc dữ liệu lặp:

~~~sql
SELECT
    course_id,
    prerequisite_course_id
FROM course_prerequisite
WHERE course_id = prerequisite_course_id;
~~~

Nếu hệ thống đã có dữ liệu trước khi áp dụng ràng buộc, truy vấn này giúp phát hiện trường hợp tự tham chiếu. Có thể tìm cặp cạnh bị lặp bằng:

~~~sql
SELECT
    course_id,
    prerequisite_course_id,
    COUNT(*) AS duplicate_count
FROM course_prerequisite
GROUP BY course_id, prerequisite_course_id
HAVING COUNT(*) > 1;
~~~

Nếu bảng đã có khóa chính ghép, dữ liệu trùng không thể được chèn mới; truy vấn vẫn hữu ích khi kiểm tra dữ liệu nhập từ nguồn cũ hoặc staging trước khi áp dụng ràng buộc.

## 8. Tiến hóa quan hệ theo thời gian

Giới hạn và ý nghĩa quan hệ có thể thay đổi theo nghiệp vụ. Ví dụ, một nhóm trước đây tối đa tám thành viên nay cho phép mười hai; một quy trình phê duyệt được bổ sung nhánh; danh sách phát cho phép một bài xuất hiện nhiều lần; hoặc một quan hệ từng là một chiều nay trở thành hai chiều theo yêu cầu mới.

Khi thay đổi, hãy xem xét:

1. Dữ liệu hiện có có vi phạm giới hạn mới hoặc cũ không?
2. Các ứng dụng và tích hợp có hiểu đúng hướng, vai trò và thứ tự không?
3. Có cần backfill position, source/target hoặc trạng thái hiệu lực không?
4. Ràng buộc mới có thể triển khai trước khi chuyển ứng dụng không?
5. Cần xử lý dữ liệu vi phạm như thế nào và ai xác nhận?
6. Có cần giữ lịch sử quan hệ cũ để kiểm toán không?

Với thay đổi giới hạn tối đa, kiểm tra dữ liệu hiện tại trước khi tạo ràng buộc mới. Với thay đổi thứ tự, xác định thứ tự chuẩn từ nguồn nào và cách xử lý phần tử có vị trí trùng. Với thay đổi hướng, không tự động đảo mọi cạnh cũ; cần quy tắc nghiệp vụ cho từng loại quan hệ.

Một quy trình migration an toàn thường gồm mở rộng cấu trúc, backfill và đối soát, chuyển ứng dụng, bật ràng buộc mới, sau đó mới loại bỏ trường cũ. Nếu quy tắc mới có thể làm gián đoạn ghi dữ liệu, cần kế hoạch chuyển tiếp và cách xử lý lỗi.

## 9. Những lỗi mô hình hóa thường gặp

- Dùng một quan hệ chung chung như `related_to` dù hai đầu có vai trò khác nhau.
- Cho rằng quan hệ A → B luôn kéo theo B → A.
- Không xác định quan hệ có cho phép tự tham chiếu không.
- Dùng thứ tự vật lý của hàng hoặc thứ tự phần tử không được bảo đảm.
- Lưu cả position và next/previous ID mà không có nguồn chuẩn.
- Chỉ ghi giới hạn tối đa mà quên tối thiểu hoặc điều kiện theo trạng thái.
- Dùng CHECK trên một hàng để giả định đã bảo vệ được số lượng nhiều hàng.
- Kiểm tra số lượng trước khi insert nhưng không kiểm soát đồng thời.
- Dùng khóa ngoại để giả định đồ thị không có chu trình.
- Không xác định giới hạn áp dụng theo thời gian, trạng thái hay loại quan hệ.
- Thay đổi giới hạn hoặc thứ tự mà không đối soát dữ liệu hiện tại.
- Bỏ qua thuộc tính riêng của quan hệ như thời điểm, trạng thái, người tạo và hiệu lực.

## 10. Quy trình thiết kế và ghi tài liệu

Với mỗi quan hệ cần mô hình hóa:

1. Đặt tên bằng động từ thể hiện ý nghĩa nghiệp vụ.
2. Xác định từng đầu quan hệ và vai trò nguồn/đích.
3. Xác định quan hệ có hướng, đối xứng, tự tham chiếu hoặc bắc cầu không.
4. Ghi bội số tối thiểu/tối đa ở từng đầu và điều kiện áp dụng.
5. Xác định thứ tự có ý nghĩa không; nếu có, chọn vị trí, thời gian hay quan hệ trước/sau.
6. Liệt kê thuộc tính của chính quan hệ, nếu có.
7. Chọn cách biểu diễn logic và khóa cho quan hệ.
8. Xác định ràng buộc có thể dùng PK, FK, UNIQUE, CHECK và ràng buộc nào cần transaction hoặc kiểm tra liên hàng.
9. Xác định cách xử lý xóa, lưu trữ, thay đổi và lịch sử.
10. Viết truy vấn kiểm chứng và ca kiểm thử vượt giới hạn, đảo hướng, trùng thứ tự hoặc tạo chu trình.

### Mẫu đặc tả quan hệ

| Trường | Nội dung cần ghi |
|---|---|
| Tên quan hệ | Động từ hoặc cụm từ nghiệp vụ |
| Thực thể/vai trò A | Đầu thứ nhất và vai trò |
| Thực thể/vai trò B | Đầu thứ hai và vai trò |
| Hướng | Có hướng, đối xứng hoặc không áp dụng |
| Bội số A | Min..max ở phía A |
| Bội số B | Min..max ở phía B |
| Thứ tự | Không có, theo vị trí, thời gian hoặc quan hệ trước/sau |
| Giới hạn | Max/min, phạm vi đếm và điều kiện hiệu lực |
| Thuộc tính quan hệ | Trạng thái, thời gian, người tạo, thứ tự, hiệu lực |
| Quy tắc vòng đời | Xóa, lưu trữ, thay đổi, lịch sử |
| Cách bảo vệ | PK/FK/UNIQUE/CHECK/trigger/transaction |
| Kiểm chứng | Truy vấn và ca kiểm thử hợp lệ/không hợp lệ |

## 11. Bài tập thực hành và tiêu chí đánh giá

### Bài 1 — Điều kiện tiên quyết của khóa học

Một khóa học có thể yêu cầu nhiều khóa học tiên quyết. Quan hệ có hướng và không được tạo chu trình. Một khóa học có tối đa năm điều kiện tiên quyết.

Hãy xác định vai trò hai đầu, thiết kế bảng liên kết, khóa và ràng buộc. Mô tả cách phát hiện chu trình và cách kiểm soát hai giao dịch cùng thêm quan hệ.

### Bài 2 — Danh sách phát

Một danh sách phát có thứ tự bài hát, không chứa cùng bài hai lần và tối đa 100 bài. Người dùng có thể đổi vị trí và thêm/xóa bài.

Hãy thiết kế mô hình, khóa, UNIQUE và giới hạn số lượng. Giải thích cách đổi vị trí mà không tạo trùng position trong lúc cập nhật.

### Bài 3 — Thành viên nhóm

Một nhóm phải có từ ba đến tám thành viên đang hoạt động; mỗi thành viên có thể tham gia tối đa năm nhóm.

Hãy chỉ ra giới hạn ở từng đầu quan hệ và cách bảo vệ các giới hạn liên hàng khi có thao tác đồng thời.

### Bài 4 — Quy trình phê duyệt

Một quy trình có tối đa năm bước theo thứ tự. Mỗi bước có người phê duyệt chính và có thể có người thay thế. Một số bước có thể bị bỏ qua theo điều kiện nghiệp vụ.

Hãy xác định khi nào dùng sequence, khi nào cần quan hệ chuyển tiếp, cách lưu lịch sử và cách tránh hai nguồn thứ tự mâu thuẫn.

### Rubric tự đánh giá

| Tiêu chí | Đạt yêu cầu khi |
|---|---|
| Ngữ nghĩa hướng | Xác định đúng nguồn, đích và vai trò từng đầu |
| Tính đối xứng | Biết quan hệ ngược có được suy ra hay phải lưu riêng |
| Thứ tự | Chọn cách biểu diễn thứ tự có nguồn chuẩn và truy vấn tường minh |
| Cardinality | Ghi rõ min/max ở từng đầu và điều kiện hiệu lực |
| Toàn vẹn | Phân biệt ràng buộc một hàng với ràng buộc nhiều hàng |
| Đồng thời | Có cách ngăn vượt giới hạn do giao dịch cạnh tranh |
| Tiến hóa | Có kế hoạch thay đổi hướng, thứ tự, giới hạn và lịch sử |

Một quan hệ được mô hình hóa tốt phải trả lời rõ ai liên kết với ai, theo hướng nào, ở thứ tự nào và được phép có bao nhiêu liên kết. Khi các quy tắc này được ghi thành ngữ nghĩa và ràng buộc có thể kiểm tra, mô hình dữ liệu sẽ giảm nhập nhằng, bảo vệ toàn vẹn và hỗ trợ thay đổi nghiệp vụ có kiểm soát.


# Bội số, tính bắt buộc và ký pháp chân quạ (crow's foot)

## Mục tiêu bài học

Sau bài này, bạn có thể đọc và vẽ quan hệ giữa các thực thể trong mô hình dữ liệu bằng cách xác định **bội số (cardinality)** và **tính bắt buộc (optionality/participation)** ở cả hai đầu quan hệ. Bạn sẽ hiểu các ký hiệu vòng tròn, vạch đơn và chân quạ; chuyển quy tắc nghiệp vụ thành ký pháp crow's foot; nhận diện quan hệ một-một, một-nhiều và nhiều-nhiều; đồng thời kiểm tra mô hình bằng ví dụ và tình huống biên.

## 1. Vì sao cần mô tả bội số và tính bắt buộc?

Một câu như “khách hàng có đơn hàng” chỉ cho biết hai khái niệm có liên hệ. Nó chưa trả lời:

- Một khách hàng có thể chưa có đơn hàng hay bắt buộc phải có ít nhất một đơn?
- Một khách hàng có thể có nhiều đơn hàng không?
- Một đơn hàng có thể thuộc về nhiều khách hàng hay đúng một khách hàng?
- Một đơn hàng có thể tồn tại khi chưa gắn với khách hàng không?

Nếu không ghi rõ các giới hạn này, mỗi người đọc sơ đồ có thể tự hiểu theo một cách. Hệ quả có thể xuất hiện trong thiết kế khóa ngoại, validation, API, dữ liệu kiểm thử và quy trình nghiệp vụ.

**Bội số** mô tả số lượng đối tượng ở một đầu quan hệ có thể hoặc phải liên kết với một đối tượng ở đầu kia. **Tính bắt buộc** mô tả việc mối quan hệ có thể vắng mặt hay phải tồn tại. Hai khía cạnh thường được biểu diễn cùng nhau bằng khoảng min–max, ví dụ:

- 0..1: không có hoặc có tối đa một.
- 1..1: bắt buộc đúng một.
- 0..*: không có hoặc có nhiều.
- 1..*: ít nhất một, có thể nhiều.

Ký pháp chân quạ giúp biểu diễn trực quan các giới hạn đó trên sơ đồ thực thể–quan hệ (ERD).

## 2. Phân biệt bội số, tính bắt buộc và lực lượng quan hệ

Trong thực hành, các tài liệu có thể dùng thuật ngữ cardinality, multiplicity, optionality và participation với cách diễn đạt hơi khác nhau. Để tránh nhầm lẫn, bài này dùng các ý nghĩa sau:

- **Bội số (cardinality/multiplicity):** số lượng đối tượng tối thiểu và tối đa có thể tham gia quan hệ.
- **Tính bắt buộc (optionality):** một đối tượng có được phép không tham gia quan hệ hay không; đây là phần giới hạn tối thiểu bằng 0 hoặc 1 trong các ví dụ cơ bản.
- **Lực lượng quan hệ:** cách gọi tổng quát cho số lượng liên kết, thường được mô tả bằng một-một, một-nhiều hoặc nhiều-nhiều.

Một quan hệ không chỉ có “một” hay “nhiều”. Nó có thể là “không hoặc một”, “đúng một”, “không hoặc nhiều”, hay “ít nhất một”. Vì thế, ghi rõ min–max chính xác hơn việc chỉ ghi 1:1 hoặc 1:N.

### 2.1. Bốn khoảng min–max thường gặp

| Khoảng | Ý nghĩa | Ví dụ |
|---|---|---|
| 0..1 | Không có hoặc có tối đa một | Một hồ sơ nhân viên có thể chưa được cấp thẻ ra vào; mỗi hồ sơ có tối đa một thẻ hiện hành |
| 1..1 | Bắt buộc đúng một | Mỗi dòng hàng thuộc về đúng một đơn hàng |
| 0..* | Không có hoặc có nhiều | Một khách hàng có thể chưa đặt đơn nào hoặc có nhiều đơn |
| 1..* | Bắt buộc ít nhất một | Một đơn đã xác nhận phải có ít nhất một dòng hàng |

Dấu * nghĩa là không giới hạn số lượng tối đa trong mô hình khái niệm. Trong hệ thống vật lý, vẫn có thể tồn tại giới hạn vận hành như dung lượng, quota hoặc quy tắc nghiệp vụ khác.

### 2.2. Đọc quan hệ từ cả hai phía

Giả sử một khách hàng có thể đặt nhiều đơn, và mỗi đơn phải thuộc về đúng một khách hàng.

Ta cần đọc được hai câu:

- Với một Customer bất kỳ, có thể có 0 đến nhiều Order.
- Với một Order bất kỳ, phải có đúng một Customer.

Không được chỉ nói “Customer–Order là 1:N” rồi bỏ qua đầu còn lại. Bội số và tính bắt buộc được xác định riêng ở mỗi đầu quan hệ.

## 3. Ký pháp chân quạ (crow's foot)

Ký pháp crow's foot đặt các dấu ở hai đầu đường nối giữa các thực thể. Mỗi đầu mô tả số lượng bản ghi ở thực thể tại đầu đó có thể liên kết với một bản ghi ở phía đối diện.

Ba dấu cơ bản:

| Ký hiệu | Ý nghĩa | Giới hạn |
|---|---|---|
| Vòng tròn (o) | Quan hệ có thể không tồn tại | Min = 0 |
| Vạch đơn (vạch đứng) | Giới hạn một ở đầu quan hệ | Max = 1; khi kết hợp hai vạch là đúng một |
| Chân quạ (ba nhánh) | Có thể có nhiều đối tượng | Max = nhiều (*) |

Khi kết hợp hai ký hiệu ở cùng một đầu, ta nhận được khoảng min–max:

| Ký hiệu crow's foot | Min–max | Cách đọc |
|---|---:|---|
| Vòng tròn + vạch | 0..1 | Không hoặc một |
| Hai vạch | 1..1 | Đúng một |
| Vòng tròn + chân quạ | 0..* | Không hoặc nhiều |
| Vạch + chân quạ | 1..* | Một hoặc nhiều |

Trong nhiều công cụ ERD, chân quạ được vẽ giống ba nhánh hoặc hình chạc. Cách vẽ có thể khác đôi chút, nhưng ý nghĩa của vòng tròn, vạch và nhánh nhiều vẫn như nhau.

### 3.1. Lưu ý quan trọng về vị trí ký hiệu

Ký hiệu ở gần thực thể nào thì mô tả số lượng thực thể đó có thể liên kết với **một** thực thể ở đầu đối diện.

Ví dụ:

~~~text
CUSTOMER || —— o{ ORDER
~~~

- || ở phía Customer: mỗi Order gắn với đúng một Customer.
- o{ ở phía Order: mỗi Customer có thể có 0 hoặc nhiều Order.

Đây là điểm dễ đọc ngược. Hãy thử chọn một bản ghi ở đầu trái, rồi hỏi có bao nhiêu bản ghi ở đầu phải có thể liên kết với nó; sau đó đổi chiều và đọc lại.

## 4. Đọc ba kiểu quan hệ cơ bản

### 4.1. Một-một (one-to-one)

Quan hệ một-một nghĩa là mỗi đối tượng ở một phía liên kết với tối đa một đối tượng ở phía còn lại. Tính bắt buộc ở hai đầu có thể khác nhau.

Ví dụ: một hồ sơ nhân viên có thể có một thẻ ra vào hiện hành; mỗi thẻ hiện hành thuộc về đúng một hồ sơ nhân viên.

~~~text
EMPLOYEE || —— o| ACCESS_CARD
~~~

Cách đọc:

- Mỗi Employee có thể có 0 hoặc 1 AccessCard.
- Mỗi AccessCard phải thuộc về đúng 1 Employee.

Nếu cả hai phía đều bắt buộc đúng một, ký hiệu là:

~~~text
EMPLOYEE || —— || EMPLOYEE_PROFILE
~~~

Không phải quan hệ một-một nào cũng cần tách thành hai bảng. Nếu hai khái niệm luôn có cùng vòng đời và luôn được truy cập cùng nhau, có thể chúng chỉ là một thực thể với các thuộc tính khác nhau. Tách riêng có ý nghĩa khi chúng có vòng đời, quyền truy cập, tính tùy chọn hoặc nguồn dữ liệu độc lập.

### 4.2. Một-nhiều (one-to-many)

Ví dụ phổ biến: một khách hàng có thể có nhiều đơn hàng; mỗi đơn hàng thuộc về đúng một khách hàng.

~~~text
CUSTOMER || —— o{ ORDER
~~~

Cách đọc:

- Một Customer có thể có 0 hoặc nhiều Order.
- Mỗi Order phải thuộc về đúng 1 Customer.

Một biến thể khác là một đơn hàng đã được xác nhận phải có ít nhất một dòng hàng:

~~~text
ORDER || —— |{ ORDER_ITEM
~~~

Cách đọc:

- Mỗi Order có từ 1 đến nhiều OrderItem theo quy tắc đã xác nhận.
- Mỗi OrderItem thuộc về đúng 1 Order.

Cần chú ý phạm vi trạng thái. Một đơn hàng ở trạng thái bản nháp có thể tạm thời chưa có dòng hàng, nhưng đơn đã xác nhận thì bắt buộc có ít nhất một dòng. Nếu quy tắc thay đổi theo trạng thái, hãy ghi điều kiện đó vào mô tả nghiệp vụ hoặc ràng buộc tương ứng; một ký hiệu ERD tĩnh có thể không thể hiện đầy đủ mọi điều kiện thời gian.

### 4.3. Nhiều-nhiều (many-to-many)

Ví dụ: một sinh viên có thể đăng ký nhiều môn học, và một môn học có nhiều sinh viên.

~~~text
STUDENT }o —— o{ COURSE
~~~

Trong mô hình khái niệm, đây là quan hệ nhiều-nhiều. Khi triển khai bằng mô hình quan hệ, thường cần một thực thể kết hợp như Enrollment để lưu mỗi lần đăng ký.

~~~text
STUDENT || —— o{ ENROLLMENT
COURSE  || —— o{ ENROLLMENT
~~~

Mỗi Enrollment phải tham chiếu đúng một Student và một Course; mỗi Student hoặc Course có thể có 0 hoặc nhiều Enrollment.

Nếu quan hệ có thuộc tính riêng như ngày đăng ký, điểm, trạng thái hoặc kỳ học, thực thể kết hợp đặc biệt hữu ích. Những thuộc tính này mô tả lần đăng ký, không phải bản thân sinh viên hay môn học.

## 5. Ví dụ ERD cho hệ thống bán hàng

Xét các quy tắc nghiệp vụ sau:

1. Một khách hàng có thể chưa có đơn hàng hoặc có nhiều đơn hàng.
2. Mỗi đơn hàng được tạo cho đúng một khách hàng.
3. Một đơn hàng đã xác nhận phải có ít nhất một dòng hàng.
4. Mỗi dòng hàng tham chiếu đúng một sản phẩm.
5. Một sản phẩm có thể chưa từng được đặt hoặc xuất hiện trong nhiều dòng hàng.
6. Một đơn hàng có thể chưa có lần thanh toán hoặc có nhiều lần thử thanh toán.

ERD minh họa:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : appears_in
    ORDER ||--o{ PAYMENT_ATTEMPT : has
~~~

Đọc từng quan hệ:

| Quan hệ | Đọc từ thực thể thứ nhất | Đọc từ thực thể thứ hai |
|---|---|---|
| Customer–Order | Một Customer có 0..* Order | Mỗi Order có đúng 1 Customer |
| Order–OrderItem | Một Order có 1..* OrderItem theo quy tắc đã xác nhận | Mỗi OrderItem thuộc đúng 1 Order |
| Product–OrderItem | Một Product có 0..* OrderItem | Mỗi OrderItem tham chiếu đúng 1 Product |
| Order–PaymentAttempt | Một Order có 0..* PaymentAttempt | Mỗi PaymentAttempt thuộc đúng 1 Order |

ERD khái niệm không nhất thiết hiển thị mọi thuộc tính. Khi đi đến mô hình logic, ta sẽ bổ sung khóa, thuộc tính và ràng buộc cụ thể.

### 5.1. Vì sao OrderItem là thực thể kết hợp?

Quan hệ giữa Order và Product về bản chất là nhiều-nhiều: một đơn hàng có nhiều sản phẩm và một sản phẩm có thể xuất hiện trong nhiều đơn hàng. Nhưng bản thân quan hệ còn có dữ liệu:

- số lượng đặt;
- đơn giá tại thời điểm mua;
- mức giảm giá;
- ghi chú hoặc lựa chọn biến thể.

Do đó, OrderItem là thực thể kết hợp. Nó biểu diễn một lần sản phẩm được đưa vào một đơn hàng cụ thể.

### 5.2. Không suy ra quy tắc nghiệp vụ từ ký hiệu một cách máy móc

Ví dụ, sơ đồ thể hiện một Order có 1..* OrderItem. Điều này phải dựa trên quy tắc “đơn đã xác nhận phải có ít nhất một dòng hàng”. Nếu hệ thống cho phép lưu đơn nháp chưa có dòng hàng, mô hình cần thể hiện rõ phạm vi áp dụng:

- có thể mô tả Order nháp với 0..* OrderItem;
- hoặc tách trạng thái/aggregate theo từng giai đoạn;
- hoặc ghi chú ràng buộc có điều kiện: chỉ Order đã xác nhận mới phải có ít nhất một OrderItem.

Không nên ép một ký hiệu duy nhất đại diện cho nhiều quy tắc theo trạng thái nếu nó làm người đọc hiểu sai.

## 6. Chuyển ký pháp crow's foot sang mô hình quan hệ

Ký pháp crow's foot là cách mô tả quan hệ ở mức khái niệm hoặc logic. Khi triển khai bằng cơ sở dữ liệu quan hệ, quan hệ thường được hiện thực hóa bằng khóa ngoại và ràng buộc.

### 6.1. Một-nhiều: đặt khóa ngoại ở phía nhiều

Với Customer–Order, mỗi Order thuộc về một Customer. Bảng phía nhiều (orders) chứa khóa ngoại tham chiếu phía một (customers).

~~~sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
~~~

- NOT NULL biểu diễn yêu cầu mỗi Order phải có Customer.
- Khóa ngoại bảo đảm Customer được tham chiếu tồn tại.
- Một Customer có thể có nhiều Order vì nhiều hàng trong orders có thể cùng tham chiếu một customer_id.

Nếu Order được phép chưa gắn Customer, cột khóa ngoại có thể cho phép NULL. Tuy nhiên, cần định nghĩa ý nghĩa của trường hợp thiếu liên kết; NULL không nên đại diện tùy tiện cho nhiều trạng thái nghiệp vụ khác nhau.

### 6.2. Một-một: kết hợp khóa ngoại và UNIQUE

Nếu mỗi nhân viên có tối đa một thẻ và mỗi thẻ thuộc đúng một nhân viên, có thể đặt khóa ngoại duy nhất ở bảng thẻ:

~~~sql
CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY
);

CREATE TABLE access_cards (
    card_id BIGINT PRIMARY KEY,
    employee_id BIGINT NOT NULL UNIQUE,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);
~~~

- NOT NULL yêu cầu mỗi thẻ có nhân viên.
- UNIQUE ngăn một nhân viên được tham chiếu bởi nhiều thẻ trong bảng này.
- Việc một nhân viên có thể chưa có thẻ được cho phép vì không có ràng buộc buộc mọi Employee phải có AccessCard.

### 6.3. Nhiều-nhiều: dùng bảng kết hợp

Với Student–Course, bảng enrollments chứa khóa ngoại đến cả hai phía:

~~~sql
CREATE TABLE students (
    student_id BIGINT PRIMARY KEY
);

CREATE TABLE courses (
    course_id BIGINT PRIMARY KEY
);

CREATE TABLE enrollments (
    student_id BIGINT NOT NULL REFERENCES students(student_id),
    course_id BIGINT NOT NULL REFERENCES courses(course_id),
    enrolled_at TIMESTAMP NOT NULL,
    PRIMARY KEY (student_id, course_id)
);
~~~

Khóa chính ghép ngăn một sinh viên có nhiều bản ghi đăng ký trùng cho cùng một môn trong cùng phạm vi khóa. Nếu nghiệp vụ cho phép học lại theo kỳ, khóa có thể cần thêm term_id hoặc một định danh lần đăng ký riêng.

### 6.4. Giới hạn của khóa ngoại

Khóa ngoại và NOT NULL có thể bảo vệ nhiều quy tắc, nhưng không phải mọi min–max đều được thực thi trực tiếp bằng một ràng buộc đơn giản.

Ví dụ, khóa ngoại trong order_items bảo đảm mỗi dòng hàng thuộc về một đơn hàng hợp lệ. Nó không tự bảo đảm mọi Order đều có ít nhất một OrderItem. Để bảo vệ quy tắc “đơn đã xác nhận phải có ít nhất một dòng”, hệ thống có thể cần transaction nghiệp vụ, kiểm tra trước khi chuyển trạng thái, trigger hoặc cơ chế ràng buộc phù hợp với hệ quản trị.

Vì vậy, hãy phân biệt:

- điều mô hình yêu cầu;
- ràng buộc có thể khai báo trực tiếp trong schema;
- quy tắc phải được kiểm tra trong transaction hoặc logic ứng dụng.

## 7. Cách xác định bội số từ yêu cầu nghiệp vụ

Đừng bắt đầu bằng việc chọn ký hiệu. Hãy bắt đầu bằng câu hỏi về từng phía của quan hệ.

### Bước 1: Xác định hai khái niệm

Ví dụ: Department và Employee.

Định nghĩa rõ mỗi khái niệm. Department là đơn vị tổ chức; Employee là hồ sơ nhân sự. Tránh dùng tên mơ hồ như “người dùng” khi có nhiều vai trò khác nhau.

### Bước 2: Viết câu theo hai chiều

- Một Department có thể có bao nhiêu Employee?
- Một Employee có thể thuộc bao nhiêu Department tại cùng một thời điểm?

Câu trả lời có thể là: một phòng ban có thể có 0..* nhân viên; mỗi nhân viên thuộc đúng một phòng ban hiện tại.

### Bước 3: Hỏi trường hợp tối thiểu

- Phòng ban mới tạo có thể chưa có nhân viên không?
- Nhân viên mới có thể chưa được phân công phòng ban không?

Câu hỏi này quyết định đầu quan hệ là tùy chọn hay bắt buộc. Đừng suy ra từ quy trình hiện tại nếu nghiệp vụ có thể cho phép giai đoạn trung gian.

### Bước 4: Hỏi giới hạn tối đa

- Một nhân viên có thể làm việc đồng thời ở nhiều phòng ban không?
- Một phòng ban có thể có số lượng nhân viên không giới hạn về mặt nghiệp vụ không?

Nếu một nhân viên có thể thuộc nhiều phòng ban, quan hệ có thể là nhiều-nhiều và cần khái niệm phân công (Assignment), có thời gian hiệu lực và vai trò.

### Bước 5: Kiểm tra vòng đời và thời gian

Quan hệ có thay đổi theo thời gian không? Nếu nhân viên chuyển phòng ban, hệ thống cần lưu phòng ban hiện tại hay lịch sử phân công?

Nếu cần lịch sử, một quan hệ trực tiếp Employee–Department có thể chưa đủ. Thực thể Assignment có thể lưu valid_from, valid_to, chức vụ hoặc tỷ lệ phân bổ.

### Bước 6: Viết quy tắc bằng ngôn ngữ rõ ràng

Ví dụ:

- Một Department có thể chưa có nhân viên hoặc có nhiều nhân viên.
- Mỗi Employee đang hoạt động phải có đúng một Department chính.
- Một Employee có thể có nhiều Assignment lịch sử, nhưng các khoảng thời gian phân công chính không được chồng lấn.

Các câu này có thể được kiểm tra và chuyển thành ERD, schema cùng acceptance criteria.

## 8. Các trường hợp nâng cao cần chú ý

### 8.1. Quan hệ đệ quy (recursive relationship)

Một thực thể có thể liên hệ với chính nó. Ví dụ, một nhân viên có thể báo cáo cho một quản lý cũng là nhân viên.

~~~text
EMPLOYEE (manager) o| —— o{ EMPLOYEE (subordinate)
~~~

Cần đọc rõ vai trò ở hai đầu:

- Một Employee ở vai trò quản lý có thể quản lý 0..* nhân viên.
- Một Employee ở vai trò cấp dưới có thể có 0..1 quản lý trực tiếp, tùy chính sách tổ chức.

Nếu mỗi nhân viên (trừ người đứng đầu) bắt buộc có một quản lý, đầu cấp dưới sẽ là || thay vì o|. Nên đặt tên vai trò để tránh nhầm hai đầu cùng tham chiếu một bảng.

### 8.2. Quan hệ có thời gian hiệu lực

Một người có thể thuộc nhiều nhóm ở các thời điểm khác nhau. Nếu chỉ lưu một khóa ngoại group_id hiện tại, lịch sử bị mất.

Có thể dùng thực thể liên kết Membership với:

- member_id;
- group_id;
- valid_from;
- valid_to;
- role.

Khi đó quan hệ thành viên có vòng đời riêng và các quy tắc không chồng lấn theo thời gian cần được xác định. Bội số ở thời điểm hiện tại có thể khác bội số trong toàn bộ lịch sử.

### 8.3. Quan hệ bậc ba hoặc nhiều phía

Một số quy tắc không thể diễn đạt chính xác bằng cách tách thành nhiều quan hệ hai phía. Ví dụ, một nhà cung cấp cung cấp một sản phẩm cho một chi nhánh theo một hợp đồng cụ thể. Ý nghĩa phụ thuộc đồng thời vào Supplier, Product và Branch.

Nếu tách thành ba quan hệ hai phía, có thể mất ràng buộc rằng chính tổ hợp ba đối tượng đó được phép. Khi đó cần xem xét thực thể kết hợp như SupplyAgreement hoặc một quan hệ bậc ba trong mô hình khái niệm.

### 8.4. Bội số có điều kiện

Một quan hệ có thể phụ thuộc trạng thái, loại đối tượng hoặc thời gian:

- Đơn nháp có thể chưa có dòng hàng.
- Đơn đã xác nhận phải có ít nhất một dòng hàng.
- Nhân viên chính thức phải có phòng ban; cộng tác viên có thể không.
- Một tài khoản chỉ có một hồ sơ xác minh đang hiệu lực, nhưng có thể có nhiều hồ sơ lịch sử.

Hãy ghi điều kiện rõ ràng. Nếu công cụ ERD không biểu diễn được, thêm ghi chú ràng buộc hoặc mô hình hóa trạng thái/quan hệ bằng thực thể riêng.

## 9. Kiểm chứng ERD và những lỗi thường gặp

Một ERD không chỉ cần vẽ đúng ký hiệu. Nó cần phản ánh chính xác các quy tắc nghiệp vụ và đủ rõ để nhóm triển khai cùng hiểu.

### 9.1. Checklist kiểm tra

Với mỗi quan hệ, hãy kiểm tra:

1. Tên quan hệ có thể đọc thành câu nghiệp vụ rõ ràng không?
2. Đã đọc từ cả hai phía chưa?
3. Min và max ở mỗi đầu đã được xác nhận chưa?
4. Tính bắt buộc có đúng cho trạng thái và vòng đời liên quan không?
5. Quan hệ nhiều-nhiều có cần thực thể kết hợp không?
6. Quan hệ có thuộc tính riêng hoặc thời gian hiệu lực không?
7. Có quy tắc nào không thể biểu diễn bằng ký hiệu crow's foot đơn giản không?
8. Có thể chuyển quan hệ thành khóa và ràng buộc phù hợp không?
9. Có tình huống dữ liệu nào làm sơ đồ trở nên mâu thuẫn không?

### 9.2. Lỗi thường gặp

- **Chỉ ghi 1:N mà không ghi optionality:** người đọc không biết phía nhiều có thể bằng 0 hay phải có ít nhất một.
- **Đọc ngược ký hiệu:** dấu ở đầu Entity mô tả số lượng Entity đó đối với một bản ghi ở phía kia.
- **Nhầm max one với exactly one:** 0..1 là tùy chọn; 1..1 là bắt buộc.
- **Giả định mọi quan hệ một-một đều cần bảng riêng:** có thể làm mô hình phức tạp nếu hai phần có cùng vòng đời và quyền truy cập.
- **Để quan hệ nhiều-nhiều trong schema quan hệ mà không có bảng kết hợp:** thường không thể lưu thuộc tính của từng liên kết và khó bảo vệ tính duy nhất.
- **Quên quy tắc theo trạng thái:** một đơn nháp và một đơn đã xác nhận có thể có điều kiện dòng hàng khác nhau.
- **Dùng khóa ngoại để giả định đã bảo vệ mọi cardinality:** FK bảo vệ tham chiếu, nhưng không tự bảo đảm phía cha có ít nhất một bản ghi con.
- **Không đặt tên vai trò cho quan hệ đệ quy:** người đọc không phân biệt được quản lý và cấp dưới.
- **Bỏ qua lịch sử:** bội số hiện tại không nhất thiết mô tả được quan hệ trong toàn bộ thời gian.

## 10. Từ ERD đến tiêu chí chấp nhận

Sau khi thống nhất bội số, hãy viết các tiêu chí có thể kiểm thử. Ví dụ với Customer–Order:

- Khi tạo Order, hệ thống yêu cầu một Customer hợp lệ.
- Một Customer chưa từng đặt hàng vẫn có thể tồn tại.
- Một Customer có thể có nhiều Order.
- Không thể tạo Order tham chiếu đến Customer không tồn tại.

Với Order–OrderItem, nếu quy tắc chỉ áp dụng cho đơn đã xác nhận:

- Order ở trạng thái Draft có thể chưa có OrderItem.
- Khi chuyển Order sang Confirmed, phải có ít nhất một OrderItem hợp lệ.
- Mỗi OrderItem phải tham chiếu đúng một Order.
- Khi xóa hoặc hủy một Order, xử lý các OrderItem theo chính sách lưu lịch sử đã xác nhận.

Tiêu chí chấp nhận làm rõ điều gì phải đúng và cung cấp tình huống để kiểm thử. Nó cũng giúp nhận ra ràng buộc nào cần database bảo vệ và ràng buộc nào cần quy trình nghiệp vụ.

## 11. Kết luận

Bội số xác định số lượng liên kết tối thiểu và tối đa giữa các thực thể; tính bắt buộc cho biết một quan hệ có thể vắng mặt hay phải tồn tại. Ký pháp crow's foot kết hợp vòng tròn, vạch và chân quạ để thể hiện các giới hạn đó ở hai đầu quan hệ.

Khi thiết kế ERD, hãy xác định khái niệm, viết quy tắc nghiệp vụ theo hai chiều, xác nhận min–max, rồi mới chọn ký hiệu. Sau đó kiểm chứng bằng tình huống biên và chuyển các quy tắc thành khóa, ràng buộc hoặc logic nghiệp vụ thích hợp. Một sơ đồ tốt giúp mọi người hiểu cùng một điều và có thể triển khai, kiểm tra nhất quán.

## Tự kiểm tra

1. Ký hiệu o{ có ý nghĩa gì? Khác |{ ở điểm nào?
2. Với CUSTOMER ||--o{ ORDER, hãy diễn giải quan hệ từ cả hai phía.
3. Vì sao quan hệ một-nhiều thường đặt khóa ngoại ở phía nhiều?
4. Khóa ngoại có tự bảo đảm mỗi Order phải có ít nhất một OrderItem không? Giải thích.
5. Khi nào quan hệ nhiều-nhiều cần thực thể kết hợp?
6. Làm thế nào biểu diễn việc một nhân viên có thể chuyển phòng ban và cần lưu lịch sử?
7. Hãy chọn một quan hệ trong hệ thống bạn biết, viết hai câu min–max theo hai chiều, vẽ crow's foot và đề xuất tiêu chí chấp nhận để kiểm tra.


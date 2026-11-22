# Chuyển miền dữ liệu và quan hệ nghiệp vụ thành bảng Oracle

Thiết kế bảng Oracle không bắt đầu từ câu hỏi “cần bao nhiêu cột?”, mà bắt đầu từ việc **hiểu dữ liệu thuộc miền nghiệp vụ nào, một bản ghi đại diện cho điều gì, các đối tượng liên hệ với nhau ra sao và những quy tắc nào phải được giữ đúng khi dữ liệu thay đổi**. Nếu chuyển yêu cầu nghiệp vụ thành bảng một cách máy móc, ta dễ tạo ra một bảng chứa mọi thứ, lặp lại thông tin khách hàng trên từng đơn hàng, lưu danh sách sản phẩm trong một cột văn bản hoặc chỉ kiểm tra khóa ngoại ở mã Java. Những quyết định đó khiến dữ liệu khó sửa, dễ bất nhất và khó mở rộng.

Trong Oracle Database, mô hình quan hệ được hiện thực qua **table, column, data type, primary key, foreign key, unique constraint, check constraint, not null** và các cấu trúc hỗ trợ. Bài học này đi xuyên suốt một ví dụ bán hàng nhỏ: từ câu mô tả nghiệp vụ, thiết kế thực thể và quan hệ, viết DDL Oracle, thêm dữ liệu mẫu, truy vấn liên bảng cho đến nhận diện những quy tắc cần xử lý bằng transaction hoặc logic nghiệp vụ.

## 1. Từ ngôn ngữ nghiệp vụ đến mô hình quan hệ

Giả sử người phụ trách sản phẩm đưa ra yêu cầu:

> “Hệ thống lưu khách hàng và sản phẩm. Một khách hàng có thể tạo nhiều đơn hàng; mỗi đơn hàng thuộc đúng một khách hàng. Một đơn hàng có nhiều dòng sản phẩm, mỗi dòng chỉ tới một sản phẩm, ghi số lượng và đơn giá tại thời điểm đặt hàng. Một đơn hàng có thể có một địa chỉ giao hàng đã chốt. Sản phẩm còn được bán ở nhiều đơn hàng. Đơn hàng có trạng thái nháp, xác nhận hoặc hủy.”

Ta chưa nên viết ngay `CREATE TABLE`. Trước tiên cần tách:

| Thành phần trong câu mô tả | Câu hỏi cần xác định | Kết quả thiết kế khả dĩ |
|---|---|---|
| Khách hàng | Một khách hàng có những thuộc tính nhận diện nào? | Thực thể `CUSTOMER` |
| Sản phẩm | SKU, tên, giá hiện hành và trạng thái bán là gì? | Thực thể `PRODUCT` |
| Đơn hàng | Một dòng đơn hàng biểu thị giao dịch nào? | Thực thể `SALES_ORDER` |
| Dòng đơn hàng | Số lượng và giá của **từng sản phẩm trong từng đơn** thuộc về đâu? | Thực thể liên kết `ORDER_ITEM` |
| Địa chỉ giao hàng đã chốt | Có phải dữ liệu riêng theo từng đơn, không thay đổi khi hồ sơ khách hàng đổi? | `ORDER_SHIPPING` hoặc nhóm cột snapshot trong đơn |
| Trạng thái đơn | Có những giá trị hợp lệ nào? Trạng thái nào được phép chuyển sang trạng thái nào? | Cột `ORDER_STATUS`, `CHECK` và quy tắc chuyển trạng thái |

Không phải **mọi danh từ** đều là một bảng. Ví dụ “địa chỉ” có thể là một **value object** gồm nhiều thuộc tính; nếu nghiệp vụ chỉ dùng một địa chỉ giao hàng tại thời điểm chốt đơn, ta có thể lưu các cột snapshot trong `SALES_ORDER` hoặc tách ra `ORDER_SHIPPING` khi có lý do về vòng đời/quyền truy cập. Còn “đơn giá ở thời điểm đặt” là thuộc tính của **dòng đơn hàng**, không phải chỉ thuộc tính hiện tại của sản phẩm.

Một bảng nên có **mục đích và grain rõ ràng**: *một dòng trong bảng đại diện cho một điều gì?*

- `CUSTOMER`: một dòng = một khách hàng.
- `PRODUCT`: một dòng = một sản phẩm có SKU riêng.
- `SALES_ORDER`: một dòng = một đơn hàng.
- `ORDER_ITEM`: một dòng = một dòng sản phẩm trong một đơn hàng.
- `ORDER_SHIPPING`: một dòng = thông tin giao hàng đã chốt của tối đa một đơn hàng.

Nếu không nói rõ grain, rất dễ cộng tiền hai lần sau khi `JOIN` hoặc lưu lẫn thông tin của các mức chi tiết khác nhau.

## 2. Xác định thực thể, thuộc tính và giá trị nghiệp vụ

### 2.1. Entity và value object khác nhau thế nào?

**Entity** có danh tính tồn tại qua thời gian: khách hàng vẫn là cùng khách hàng dù đổi tên; đơn hàng vẫn là đơn hàng đó dù trạng thái thay đổi. Trong database, entity thường cần một khóa ổn định.

**Value object** được nhận biết chủ yếu bởi **giá trị**: tiền với số tiền và đơn vị, địa chỉ với các thành phần, khoảng thời gian với hai đầu mút. Một value object không nhất thiết cần bảng riêng. Quyết định tách bảng dựa trên tính độc lập, nhu cầu truy vấn, số lần xuất hiện, quan hệ, quyền truy cập, yêu cầu lịch sử và chi phí thay đổi.

Ví dụ, nếu hệ thống cho phép mỗi khách hàng đăng ký nhiều địa chỉ và đánh dấu địa chỉ mặc định, đó có thể là thực thể `CUSTOMER_ADDRESS` liên kết `CUSTOMER` theo quan hệ 1:N. Nhưng **địa chỉ giao của đơn đã phát sinh** thường cần giữ nguyên dù khách hàng cập nhật địa chỉ cá nhân. Vì vậy đơn hàng có thể lưu một **snapshot** địa chỉ, thay vì chỉ tham chiếu đến địa chỉ hồ sơ đang có.

### 2.2. Phân biệt khóa kỹ thuật và khóa nghiệp vụ

Trong ví dụ:

- `CUSTOMER_ID`: khóa kỹ thuật, do database cấp, dùng cho foreign key.
- `CUSTOMER_CODE`: mã nghiệp vụ, phải duy nhất theo phạm vi quy định.
- `PRODUCT_ID`: khóa kỹ thuật của sản phẩm.
- `SKU`: mã sản phẩm do nghiệp vụ định nghĩa, cần unique theo quy tắc catalog.
- `ORDER_ID`: khóa kỹ thuật của đơn hàng.
- `ORDER_NUMBER`: mã đơn dùng ở giao diện/tra cứu và tích hợp.

**Natural key** là thuộc tính hoặc nhóm thuộc tính có ý nghĩa nghiệp vụ, chẳng hạn SKU. **Surrogate key** là khóa kỹ thuật không mang ý nghĩa nghiệp vụ, chẳng hạn identity `PRODUCT_ID`.

Khóa kỹ thuật phù hợp khi business key có thể đổi hoặc dài/phức tạp. Nhưng dùng surrogate key **không miễn** việc áp dụng `UNIQUE` cho business key nếu nghiệp vụ yêu cầu duy nhất. Nếu chỉ có `CUSTOMER_ID` là primary key, Oracle vẫn có thể cho phép hai dòng mang cùng `CUSTOMER_CODE` trừ khi có unique constraint hay một quy tắc thực thi khác.

## 3. Đọc cardinality và optionality trước khi viết foreign key

**Cardinality** mô tả số lượng bản ghi có thể liên hệ; **optionality** cho biết một quan hệ có bắt buộc hay không. Các ký hiệu `1`, `0..1`, `0..N`, `1..N` cần được diễn đạt từ **cả hai phía**, vì “khách hàng có đơn hàng” chưa đủ để xác định khách hàng có bắt buộc phải có ít nhất một đơn hay không.

| Quan hệ | Diễn giải nghiệp vụ | Cách mô hình thường dùng |
|---|---|---|
| **1:N** | Mỗi đơn thuộc đúng một khách hàng; một khách có thể có 0..N đơn | `SALES_ORDER.CUSTOMER_ID NOT NULL` tham chiếu `CUSTOMER` |
| **0..1:1** | Một đơn có tối đa một thông tin giao hàng; có thể chưa có khi còn nháp | `ORDER_SHIPPING.ORDER_ID` vừa `PRIMARY KEY` vừa `FOREIGN KEY` |
| **N:M** | Một đơn có nhiều sản phẩm; một sản phẩm có thể thuộc nhiều đơn | Bảng liên kết `ORDER_ITEM` có hai foreign key và các thuộc tính của liên kết |
| **1:N với FK nullable** | Một nhân viên có thể chưa có người quản lý | `EMPLOYEE.MANAGER_ID NULL` tham chiếu `EMPLOYEE` |
| **N:M đơn thuần** | Một học viên học nhiều khóa; một khóa có nhiều học viên | `ENROLLMENT(STUDENT_ID, COURSE_ID)` với khóa ghép |

Sơ đồ miền bán hàng:

~~~text
      CUSTOMER                           PRODUCT
   [CUSTOMER_ID]                       [PRODUCT_ID]
        │                                    │
        │ 1                                  │ 1
        │                                    │
        │ 0..N                               │ 0..N
        ▼                                    ▼
    SALES_ORDER 1 ─────── 0..N ORDER_ITEM N..0 ──── PRODUCT
     [ORDER_ID]              [ORDER_ID, LINE_NO]
        │                     [PRODUCT_ID]
        │ 1                   [QUANTITY]
        │                     [UNIT_PRICE_AT_ORDER]
        │ 0..1
        ▼
   ORDER_SHIPPING
   [ORDER_ID = PK + FK]
~~~

Đọc sơ đồ theo nghiệp vụ: một đơn phải có khách hàng; một khách có thể chưa từng mua. Một đơn mới tạo có thể chưa có dòng hàng hoặc địa chỉ giao hàng, nhưng khi chuyển sang trạng thái xác nhận, nghiệp vụ có thể yêu cầu đã có ít nhất một dòng và một địa chỉ. **Một số điều kiện tối thiểu phụ thuộc trạng thái như vậy không được giải quyết chỉ bằng FK và NOT NULL.**

## 4. Ánh xạ các kiểu quan hệ thành bảng Oracle

### 4.1. Quan hệ một-nhiều (1:N)

Đặt **foreign key ở phía nhiều**. Với khách hàng và đơn hàng:

~~~text
CUSTOMER.CUSTOMER_ID          PK
           ▲
           │ FK
SALES_ORDER.CUSTOMER_ID       NOT NULL
~~~

`NOT NULL` buộc mỗi đơn phải chỉ tới một khách. Foreign key buộc giá trị đó phải tồn tại trong bảng khách hàng ở trạng thái constraint áp dụng. Ngược lại, **không cần lưu danh sách `ORDER_ID` bên trong một cột của `CUSTOMER`**.

Để quan hệ là 0..N đơn hàng trên một khách hàng, không thêm unique constraint cho `SALES_ORDER.CUSTOMER_ID`. Nếu đặt `UNIQUE(CUSTOMER_ID)` ở bảng đơn hàng, mỗi khách hàng chỉ có tối đa một đơn và mô hình trở thành khác yêu cầu.

### 4.2. Quan hệ nhiều-nhiều (N:M)

Một cột `PRODUCT_IDS = '11,17,25'` trong `SALES_ORDER` sẽ khó ràng buộc từng sản phẩm tồn tại, khó cập nhật số lượng, khó tạo index chuẩn và khó viết join. Ta dùng **bảng liên kết**:

~~~text
SALES_ORDER ───< ORDER_ITEM >─── PRODUCT
                ORDER_ID       (FK)
                LINE_NO        (vị trí dòng trong đơn)
                PRODUCT_ID     (FK)
                QUANTITY
                UNIT_PRICE_AT_ORDER_VND
~~~

`ORDER_ITEM` không chỉ nối hai bảng: nó biểu diễn **sự kiện/quan hệ có thuộc tính riêng**, gồm số lượng và giá tại thời điểm đặt. Dữ liệu này không thể đặt trọn vẹn trên `PRODUCT` vì cùng một sản phẩm có thể được đặt với số lượng, đơn giá và chiết khấu khác nhau trong các đơn.

Có hai cách phổ biến chọn khóa cho bảng liên kết:

- **Khóa ghép**: `PRIMARY KEY(ORDER_ID, LINE_NO)` nếu mỗi đơn có các dòng 1, 2, 3...
- **Khóa surrogate**: `ORDER_ITEM_ID` làm primary key, cộng unique constraint cho tổ hợp nghiệp vụ nếu cần.

Trong ví dụ ta dùng khóa ghép `(ORDER_ID, LINE_NO)`. Nếu nghiệp vụ quy định *mỗi sản phẩm chỉ xuất hiện một lần trong mỗi đơn*, có thể thêm `UNIQUE(ORDER_ID, PRODUCT_ID)`. Nếu cùng SKU được phép xuất hiện ở hai dòng với khuyến mãi hoặc phân bổ kho khác nhau, **không** thêm ràng buộc unique đó. Đây là một quyết định nghiệp vụ, không có đáp án chung cho mọi hệ thống.

### 4.3. Quan hệ một-một (1:1)

Nếu `ORDER_SHIPPING` chứa thông tin giao hàng ở cấp một đơn, có thể dùng:

~~~text
SALES_ORDER.ORDER_ID                 PRIMARY KEY
               ▲
               │
ORDER_SHIPPING.ORDER_ID              PRIMARY KEY + FOREIGN KEY
~~~

Khóa chính của `ORDER_SHIPPING` bảo đảm **mỗi order_id xuất hiện tối đa một lần**. FK bảo đảm đơn tương ứng tồn tại. Nhưng không có dòng `ORDER_SHIPPING` vẫn hợp lệ: đây là quan hệ **0..1 thông tin giao hàng cho một đơn**.

Nếu nghiệp vụ yêu cầu **mọi đơn** luôn có địa chỉ, có thể cân nhắc đưa các cột địa chỉ bắt buộc trực tiếp vào `SALES_ORDER`, hoặc dùng logic transaction để bảo đảm khi xác nhận đơn phải có dòng shipping. Việc tách bảng 1:1 chỉ đáng làm nếu có lý do về vòng đời, quyền truy cập, thuộc tính tùy chọn hoặc cách vận hành.

### 4.4. Quan hệ tự tham chiếu

Một nhân viên có thể báo cáo cho một nhân viên khác. Mô hình:

~~~sql
CREATE TABLE lab_employee (
  employee_id NUMBER GENERATED ALWAYS AS IDENTITY,
  display_name VARCHAR2(100 CHAR) NOT NULL,
  manager_id NUMBER,
  CONSTRAINT pk_lab_employee PRIMARY KEY (employee_id),
  CONSTRAINT fk_lab_employee_manager
    FOREIGN KEY (manager_id) REFERENCES lab_employee (employee_id),
  CONSTRAINT ck_lab_employee_not_self
    CHECK (manager_id IS NULL OR manager_id <> employee_id)
);
~~~

`MANAGER_ID` nullable diễn đạt nhân viên có thể không có quản lý. `CHECK` ngăn một nhân viên trực tiếp quản lý chính mình, nhưng **không ngăn mọi chu trình dài hơn**, ví dụ A quản lý B và B quản lý A. Nếu nghiệp vụ bắt buộc cây quản lý không chu trình, cần cơ chế kiểm soát bổ sung, thường được đặt trong logic cập nhật có quản lý transaction.

## 5. Từ quy tắc nghiệp vụ đến constraint Oracle

Mỗi ràng buộc nên gắn với một câu quy tắc cụ thể. Đừng chỉ tạo cột rồi dựa vào developer nhớ kiểm tra.

| Quy tắc nghiệp vụ | Cơ chế Oracle phù hợp | Điều cần phân biệt |
|---|---|---|
| Một đơn hàng có khóa định danh duy nhất | `PRIMARY KEY` | PK luôn unique và not null |
| Mã khách hàng không trùng | `UNIQUE(CUSTOMER_CODE)` cộng `NOT NULL` nếu bắt buộc | Unique cho cột nullable có hành vi NULL cần hiểu rõ |
| Mỗi đơn thuộc khách hàng có thật | `FOREIGN KEY(CUSTOMER_ID) REFERENCES CUSTOMER` | Cần xác định được khóa đích PK/unique |
| Đơn bắt buộc có khách hàng | `CUSTOMER_ID NOT NULL` | FK một mình không làm cột bắt buộc |
| Số lượng phải lớn hơn 0 | `CHECK(QUANTITY > 0)` cộng `NOT NULL` | CHECK một mình không bác bỏ NULL |
| Đơn giá không âm | `CHECK(UNIT_PRICE_AT_ORDER_VND >= 0)` | Còn phải chọn numeric precision hợp lý |
| Trạng thái chỉ trong tập xác định | `CHECK(ORDER_STATUS IN (...))` | Không kiểm soát thứ tự chuyển trạng thái |
| Tên/địa chỉ phải có dữ liệu hữu ích | `NOT NULL` và kiểm tra nội dung phù hợp | Chuỗi rỗng được Oracle xử lý như NULL; khoảng trắng vẫn có thể là giá trị |
| Đơn xác nhận phải có ít nhất một dòng hàng | Thường cần transaction/logic nghiệp vụ hoặc cơ chế nâng cao | Một FK thông thường không thể đếm bản ghi con |
| Tổng đơn bằng tổng các dòng hàng | Tính toán/query hoặc cơ chế đồng bộ có kiểm soát | CHECK không được truy vấn nhiều dòng/bảng khác |

### 5.1. Những đặc điểm Oracle cần nhớ

**NOT NULL và CHECK khác nhau.** Trong SQL, điều kiện CHECK thường từ chối khi biểu thức **FALSE**, còn kết quả **UNKNOWN do NULL** có thể được chấp nhận. Vì vậy `CHECK(quantity > 0)` không tự cấm giá trị `NULL`; hãy thêm `NOT NULL` khi dữ liệu bắt buộc.

**UNIQUE và NULL.** Với unique constraint trên **một cột nullable**, Oracle có thể cho nhiều hàng chứa `NULL`. Nếu business key bắt buộc, dùng cả `NOT NULL`. Với unique constraint nhiều cột, cách Oracle xử lý tổ hợp chứa NULL có các quy tắc riêng; không nên dựa vào giả định “NULL nào cũng hoàn toàn không bị ràng buộc”.

**CHECK không phải procedural program.** Không viết truy vấn con hoặc logic tham chiếu bản ghi khác vào CHECK như cách thay cho constraint liên bảng. Những quy tắc phụ thuộc trạng thái nhiều dòng cần thiết kế bổ sung.

**DEFAULT không phải dữ liệu đã có sẵn.** Default áp dụng trong các ngữ cảnh insert tương ứng; nó không tự sửa mọi dữ liệu cũ và không thay thế `NOT NULL`. Một default status `DRAFT` có thể giúp tạo đơn mới, nhưng trạng thái đó vẫn phải nằm trong miền giá trị được CHECK cho phép.

**Ràng buộc là một phần bảo vệ dữ liệu.** Kể cả ứng dụng Java có kiểm tra trước, vẫn cần constraint trong database để ngăn hai transaction đồng thời ghi dữ liệu vi phạm. Kiểm tra “mã chưa tồn tại” rồi mới insert trong Java không tránh hoàn toàn race condition nếu thiếu unique constraint.

## 6. Chọn kiểu dữ liệu trước khi tạo bảng

Trong ví dụ bán hàng, ta áp dụng các quyết định rõ ràng:

| Thuộc tính | Kiểu Oracle minh họa | Lý do |
|---|---|---|
| ID kỹ thuật | `NUMBER GENERATED ALWAYS AS IDENTITY` | Oracle cấp khóa, không phụ thuộc mã nghiệp vụ |
| Mã khách/SKU/mã đơn | `VARCHAR2(n CHAR)` | Có thể chứa chữ, dấu gạch; giữ nguyên số 0 ở đầu |
| Tên hiển thị | `VARCHAR2(n CHAR)` | Độ dài theo ký tự, phù hợp tên nhiều ngôn ngữ |
| Số lượng | `NUMBER(9,0)` | Miền nghiệp vụ số lượng nguyên với phạm vi có giới hạn |
| Giá tiền VND | `NUMBER(15,0)` | Ví dụ quy ước số nguyên đồng Việt Nam; cần kiểm tra đầu vào trước ghi |
| Trạng thái | `VARCHAR2(20 CHAR)` cùng CHECK | Tập mã ổn định, dễ đọc |
| Cờ bán được | `CHAR(1 CHAR)`, `Y/N` cùng CHECK | Dùng được ở nhiều bản Oracle, có giá trị được kiểm soát |
| Thời điểm tạo | `TIMESTAMP(6) WITH TIME ZONE` | Ghi thời điểm có thông tin múi giờ/offset |

Ở đây **mọi giá đều tính bằng VND và lưu số nguyên** theo một giả định có chủ ý. Nếu một hệ thống phải hỗ trợ nhiều tiền tệ hoặc chữ số thập phân, mô hình cần bổ sung `CURRENCY_CODE`, chọn precision/scale phù hợp và định nghĩa rõ quy tắc chuyển đổi/làm tròn. Không nên đặt một `NUMBER` mơ hồ rồi để từng ứng dụng tự hiểu đơn vị.

**Chú ý:** `NUMBER(9,0)` hoặc `NUMBER(15,0)` có thể **làm tròn** giá trị nguồn khi dữ liệu có phần thập phân. Dù cột chỉ lưu số nguyên, việc ngăn đầu vào như `1.5` biến thành `2` cần được xử lý ở bước parse/validation nếu nghiệp vụ không cho phép làm tròn.

## 7. DDL Oracle hoàn chỉnh: từ mô hình đến bảng

Các lệnh dưới đây dùng cú pháp Oracle Database có hỗ trợ **identity column** (Oracle 12c trở lên) và thực hiện trong **schema của một PDB thực hành**. Cần quyền tạo bảng và dung lượng/quota thích hợp. Chạy trên schema trống vì các tên `LAB_*` chưa được tạo.

### 7.1. Bảng khách hàng

~~~sql
CREATE TABLE lab_customer (
  customer_id   NUMBER GENERATED ALWAYS AS IDENTITY,
  customer_code VARCHAR2(30 CHAR) NOT NULL,
  display_name  VARCHAR2(150 CHAR) NOT NULL,
  email         VARCHAR2(200 CHAR),
  created_at    TIMESTAMP(6) WITH TIME ZONE
                  DEFAULT SYSTIMESTAMP NOT NULL,

  CONSTRAINT pk_lab_customer PRIMARY KEY (customer_id),
  CONSTRAINT uq_lab_customer_code UNIQUE (customer_code)
);
~~~

`CUSTOMER_ID` là surrogate key; `CUSTOMER_CODE` là business key bắt buộc và unique. `EMAIL` được phép null vì ví dụ không yêu cầu mọi khách hàng phải cung cấp email. **Không tự đặt unique(email)** trước khi xác nhận nghiệp vụ: một email có thể là địa chỉ dùng chung, và việc so sánh không phân biệt chữ hoa/chữ thường cần quy tắc rõ ràng.

### 7.2. Bảng sản phẩm

~~~sql
CREATE TABLE lab_product (
  product_id     NUMBER GENERATED ALWAYS AS IDENTITY,
  sku            VARCHAR2(40 CHAR) NOT NULL,
  product_name   VARCHAR2(200 CHAR) NOT NULL,
  unit_price_vnd NUMBER(15,0) NOT NULL,
  active_flag    CHAR(1 CHAR) DEFAULT 'Y' NOT NULL,

  CONSTRAINT pk_lab_product PRIMARY KEY (product_id),
  CONSTRAINT uq_lab_product_sku UNIQUE (sku),
  CONSTRAINT ck_lab_product_price CHECK (unit_price_vnd >= 0),
  CONSTRAINT ck_lab_product_active CHECK (active_flag IN ('Y', 'N'))
);
~~~

Giá `UNIT_PRICE_VND` ở đây là **giá sản phẩm hiện hành**. Đơn hàng cũ phải giữ giá đã chốt ở `ORDER_ITEM.UNIT_PRICE_AT_ORDER_VND`; nếu chỉ tham chiếu tới giá hiện tại, việc cập nhật bảng sản phẩm sẽ làm sai số tiền lịch sử. `ACTIVE_FLAG = 'N'` có thể dùng ngừng bán sản phẩm mà vẫn giữ khóa ngoại từ các đơn cũ.

### 7.3. Bảng đơn hàng: quan hệ nhiều đơn trên một khách

~~~sql
CREATE TABLE lab_sales_order (
  order_id      NUMBER GENERATED ALWAYS AS IDENTITY,
  order_number  VARCHAR2(40 CHAR) NOT NULL,
  customer_id   NUMBER NOT NULL,
  order_status  VARCHAR2(20 CHAR) DEFAULT 'DRAFT' NOT NULL,
  created_at    TIMESTAMP(6) WITH TIME ZONE
                  DEFAULT SYSTIMESTAMP NOT NULL,

  CONSTRAINT pk_lab_sales_order PRIMARY KEY (order_id),
  CONSTRAINT uq_lab_sales_order_number UNIQUE (order_number),
  CONSTRAINT fk_lab_sales_order_customer
    FOREIGN KEY (customer_id)
    REFERENCES lab_customer (customer_id),
  CONSTRAINT ck_lab_sales_order_status
    CHECK (order_status IN ('DRAFT', 'CONFIRMED', 'CANCELLED'))
);
~~~

`SALES_ORDER.CUSTOMER_ID NOT NULL` kết hợp foreign key bảo đảm mỗi đơn chỉ tới khách hàng hợp lệ. `ORDER_NUMBER` được unique để tránh hai đơn có cùng mã nghiệp vụ. Oracle không kiểm soát được chuỗi chuyển trạng thái, ví dụ từ `CANCELLED` về `CONFIRMED` có được phép hay không, chỉ bằng `CHECK IN`; đó là quy tắc cho transaction/service xử lý.

### 7.4. Bảng dòng đơn: chuyển quan hệ N:M thành entity liên kết

~~~sql
CREATE TABLE lab_order_item (
  order_id                NUMBER NOT NULL,
  line_no                 NUMBER(5,0) NOT NULL,
  product_id              NUMBER NOT NULL,
  quantity                NUMBER(9,0) NOT NULL,
  unit_price_at_order_vnd NUMBER(15,0) NOT NULL,

  CONSTRAINT pk_lab_order_item
    PRIMARY KEY (order_id, line_no),

  CONSTRAINT fk_lab_order_item_order
    FOREIGN KEY (order_id)
    REFERENCES lab_sales_order (order_id),

  CONSTRAINT fk_lab_order_item_product
    FOREIGN KEY (product_id)
    REFERENCES lab_product (product_id),

  CONSTRAINT ck_lab_order_item_line_no
    CHECK (line_no >= 1),

  CONSTRAINT ck_lab_order_item_quantity
    CHECK (quantity > 0),

  CONSTRAINT ck_lab_order_item_price
    CHECK (unit_price_at_order_vnd >= 0)
);
~~~

Khóa ghép `(ORDER_ID, LINE_NO)` buộc các dòng trong cùng đơn có số thứ tự khác nhau. `PRODUCT_ID` không là một phần của PK, vì cùng một sản phẩm **có thể được đặt ở nhiều đơn**. Nếu mỗi sản phẩm chỉ được ghi một dòng trong mỗi đơn, bổ sung:

~~~sql
-- Chỉ thêm nếu nghiệp vụ cấm một SKU xuất hiện nhiều dòng trong cùng đơn.
ALTER TABLE lab_order_item
  ADD CONSTRAINT uq_lab_order_item_product
  UNIQUE (order_id, product_id);
~~~

Ràng buộc trên là **tùy chọn**. Ví dụ chính chưa áp dụng nó, vì có hệ thống tách cùng sản phẩm thành nhiều dòng do chiết khấu, đợt giao hoặc kho xuất khác nhau.

### 7.5. Bảng thông tin giao hàng: 0..1:1

~~~sql
CREATE TABLE lab_order_shipping (
  order_id       NUMBER NOT NULL,
  recipient_name VARCHAR2(150 CHAR) NOT NULL,
  address_text   VARCHAR2(500 CHAR) NOT NULL,

  CONSTRAINT pk_lab_order_shipping PRIMARY KEY (order_id),
  CONSTRAINT fk_lab_order_shipping_order
    FOREIGN KEY (order_id)
    REFERENCES lab_sales_order (order_id)
);
~~~

Một dòng shipping chỉ tồn tại nếu có đơn hàng tương ứng. Do `ORDER_ID` là PK của `LAB_ORDER_SHIPPING`, không thể tạo hai địa chỉ shipping riêng cho cùng một đơn ở bảng này. Nhưng một đơn **có thể chưa có dòng shipping**; khi xác nhận đơn, ứng dụng cần kiểm tra điều kiện nghiệp vụ tương ứng.

### 7.6. Index hỗ trợ các foreign key quan trọng

PK/unique constraint thường được Oracle hỗ trợ bằng index phù hợp. **Foreign key không tự động được tạo một index riêng chỉ vì có FK**. Với những truy vấn join và thao tác xóa/cập nhật khóa cha thường gặp, có thể xem xét:

~~~sql
CREATE INDEX ix_lab_sales_order_customer
  ON lab_sales_order (customer_id);

CREATE INDEX ix_lab_order_item_product
  ON lab_order_item (product_id);
~~~

Khóa chính ghép `(ORDER_ID, LINE_NO)` đã có cấu trúc index bắt đầu bằng `ORDER_ID`, nên không nhất thiết tạo thêm index `ORDER_ID` riêng trên `LAB_ORDER_ITEM`. Có nên thêm index hay không còn tùy dữ liệu, execution plan và loại workload; mỗi index cũng làm tăng chi phí ghi và lưu trữ.

## 8. Chèn dữ liệu mẫu theo thứ tự quan hệ

Do FK yêu cầu bản ghi cha tồn tại, luồng tạo dữ liệu trong ví dụ là **khách hàng/sản phẩm → đơn hàng → dòng đơn/địa chỉ giao**. Identity của Oracle cấp các ID kỹ thuật; khi cần liên kết, có thể tìm lại bản ghi bằng business key đã unique hoặc dùng cơ chế lấy ID sau insert của JDBC/PLSQL.

~~~sql
-- 1. Dữ liệu danh mục.
INSERT INTO lab_customer (customer_code, display_name, email)
VALUES ('CUS-001', 'Khach hang mau', 'customer@example.invalid');

INSERT INTO lab_product (sku, product_name, unit_price_vnd)
VALUES ('SKU-KEYBOARD', 'Ban phim mau', 450000);

INSERT INTO lab_product (sku, product_name, unit_price_vnd)
VALUES ('SKU-MOUSE', 'Chuot mau', 200000);

-- 2. Đơn hàng chỉ tới CUSTOMER_ID hợp lệ.
INSERT INTO lab_sales_order (order_number, customer_id)
SELECT 'SO-0001', customer_id
FROM lab_customer
WHERE customer_code = 'CUS-001';

-- 3. Đưa sản phẩm vào đơn, lấy giá hiện tại làm snapshot.
INSERT INTO lab_order_item (
  order_id, line_no, product_id, quantity, unit_price_at_order_vnd
)
SELECT o.order_id, 1, p.product_id, 2, p.unit_price_vnd
FROM lab_sales_order o
CROSS JOIN lab_product p
WHERE o.order_number = 'SO-0001'
  AND p.sku = 'SKU-KEYBOARD';

INSERT INTO lab_order_item (
  order_id, line_no, product_id, quantity, unit_price_at_order_vnd
)
SELECT o.order_id, 2, p.product_id, 1, p.unit_price_vnd
FROM lab_sales_order o
CROSS JOIN lab_product p
WHERE o.order_number = 'SO-0001'
  AND p.sku = 'SKU-MOUSE';

-- 4. Chốt snapshot thông tin giao hàng của đơn.
INSERT INTO lab_order_shipping (
  order_id, recipient_name, address_text
)
SELECT order_id, 'Nguoi nhan mau', 'Dia chi giao hang vi du'
FROM lab_sales_order
WHERE order_number = 'SO-0001';

COMMIT;
~~~

Email `example.invalid`, tên và địa chỉ ở trên chỉ là **dữ liệu giả lập**. Không đưa dữ liệu khách hàng thật vào bài lab. Các `INSERT ... SELECT` dựa vào những business key có unique constraint. Khi chạy lại toàn bộ script, có thể gặp lỗi unique do dữ liệu đã tồn tại; trong hệ thống thật nên dùng migration/seed có quản lý phiên bản, mã chạy lại an toàn hoặc reset riêng schema lab.

### 8.1. Xem đơn và giá trị các dòng hàng

~~~sql
SELECT
  o.order_number,
  c.customer_code,
  o.order_status,
  i.line_no,
  p.sku,
  i.quantity,
  i.unit_price_at_order_vnd,
  i.quantity * i.unit_price_at_order_vnd AS line_amount_vnd
FROM lab_sales_order o
JOIN lab_customer c
  ON c.customer_id = o.customer_id
JOIN lab_order_item i
  ON i.order_id = o.order_id
JOIN lab_product p
  ON p.product_id = i.product_id
WHERE o.order_number = 'SO-0001'
ORDER BY i.line_no;
~~~

Kết quả logic:

| ORDER_NUMBER | SKU | QUANTITY | UNIT_PRICE_AT_ORDER_VND | LINE_AMOUNT_VND |
|---|---|---:|---:|---:|
| `SO-0001` | `SKU-KEYBOARD` | 2 | 450000 | 900000 |
| `SO-0001` | `SKU-MOUSE` | 1 | 200000 | 200000 |

Tổng đơn từ hai dòng là **1.100.000 VND** trong giả định chưa có thuế, chiết khấu hay phí vận chuyển. Nếu nghiệp vụ yêu cầu các khoản này, cần bổ sung các thành phần dữ liệu/quy tắc tính và snapshot thích hợp; không mặc định mọi tổng là phép nhân giá × lượng đơn giản.

### 8.2. Tính tổng một đơn từ các dòng

~~~sql
SELECT
  o.order_number,
  NVL(SUM(i.quantity * i.unit_price_at_order_vnd), 0)
    AS item_total_vnd
FROM lab_sales_order o
LEFT JOIN lab_order_item i
  ON i.order_id = o.order_id
WHERE o.order_number = 'SO-0001'
GROUP BY o.order_number;
~~~

`LEFT JOIN` vẫn cho thấy đơn chưa có dòng hàng; `SUM` trên tập giá trị rỗng trả `NULL`, nên `NVL(..., 0)` chuyển thành 0 cho hiển thị/tính toán theo quy tắc của bài ví dụ. Nếu ứng dụng yêu cầu đơn xác nhận phải có dòng hàng, cần kiểm tra riêng điều kiện đó.

### 8.3. Vì sao phải lưu giá tại thời điểm đặt?

Giả sử sau khi tạo đơn, giá `SKU-KEYBOARD` đổi từ 450000 thành 500000:

~~~sql
UPDATE lab_product
SET unit_price_vnd = 500000
WHERE sku = 'SKU-KEYBOARD';

COMMIT;
~~~

Giá **hiện tại** ở `LAB_PRODUCT` đã thay đổi. Tuy nhiên `LAB_ORDER_ITEM.UNIT_PRICE_AT_ORDER_VND` của đơn cũ vẫn là **450000**, nên báo cáo lịch sử còn đúng. Đây là một trường hợp **lưu snapshot có chủ đích**: dù về hình thức có hai cột giá, chúng mang hai ngữ nghĩa thời gian khác nhau, không phải sự trùng lặp vô ích.

## 9. Trực tiếp quan sát constraint bảo vệ dữ liệu

Trong một schema lab độc lập, ta có thể thử những câu lệnh **cố ý vi phạm** để thấy khác biệt giữa các ràng buộc. Chạy riêng từng ví dụ; mỗi câu lỗi sẽ không tạo dòng thành công.

### 9.1. Khóa ngoại: không có khách hàng tương ứng

~~~sql
-- CUSTOMER_ID = -99999 được giả định không tồn tại trong lab.
INSERT INTO lab_sales_order (order_number, customer_id)
VALUES ('SO-ORPHAN', -99999);
~~~

Oracle sẽ từ chối khi FK đang được bật/kiểm tra; lỗi thường gặp là `ORA-02291: integrity constraint violated - parent key not found`. Nếu chỉ kiểm tra “khách có tồn tại không” ở Java nhưng bỏ FK, một client khác vẫn có thể chèn đơn mồ côi.

### 9.2. Business key trùng

~~~sql
INSERT INTO lab_customer (customer_code, display_name)
VALUES ('CUS-001', 'Khach hang trung ma');
~~~

Unique constraint `UQ_LAB_CUSTOMER_CODE` phải ngăn mã đã tồn tại, thường báo `ORA-00001`. Oracle thực thi tính duy nhất trong điều kiện đồng thời; một lời gọi `SELECT` “kiểm tra chưa có” trước `INSERT` ở ứng dụng không thay thế được unique constraint.

### 9.3. Giá trị ngoài miền

~~~sql
INSERT INTO lab_product (
  sku, product_name, unit_price_vnd, active_flag
)
VALUES ('SKU-NEGATIVE', 'San pham loi', -100, 'Y');
~~~

`CHECK(unit_price_vnd >= 0)` từ chối giá âm, thường báo `ORA-02290`. Tương tự, `ACTIVE_FLAG = 'Z'` sẽ bị `CHECK(active_flag IN ('Y','N'))` từ chối.

### 9.4. Thiếu dữ liệu bắt buộc

~~~sql
INSERT INTO lab_product (sku, product_name, unit_price_vnd)
VALUES ('SKU-NONAME', NULL, 100000);
~~~

`PRODUCT_NAME NOT NULL` từ chối giá trị null, thường báo `ORA-01400`. Oracle còn coi chuỗi ký tự rỗng `''` là NULL trong các ngữ cảnh chuỗi hiện hành; nhưng một chuỗi toàn khoảng trắng thường vẫn là giá trị và cần kiểm tra nghiệp vụ nếu không được phép.

### 9.5. Vi phạm khóa ghép của dòng đơn

Chèn lại một dòng đã tồn tại với cùng `(ORDER_ID, LINE_NO)` sẽ vi phạm `PK_LAB_ORDER_ITEM`, dù `PRODUCT_ID` có khác. Điều này xác nhận **số dòng là duy nhất trong phạm vi từng đơn**, chứ không nhất thiết duy nhất trên toàn database.

## 10. Chuẩn hóa mô hình và các trường hợp được phép lưu bản sao

### 10.1. Một bảng “tất cả trong một” có vấn đề gì?

Thiết kế ban đầu thường gặp:

~~~text
ORDER_FLAT(
  ORDER_NUMBER,
  CUSTOMER_CODE,
  CUSTOMER_NAME,
  PRODUCT_1,
  QTY_1,
  PRODUCT_2,
  QTY_2,
  PRODUCT_3,
  QTY_3,
  ...
)
~~~

Các vấn đề:

- Chỉ hỗ trợ cố định số lượng sản phẩm, hoặc phải thêm cột liên tục.
- Dữ liệu khách hàng bị lặp trên mọi đơn; đổi tên khách hàng phải sửa nhiều dòng.
- Không dễ thêm khóa ngoại cho từng `PRODUCT_n` và không dễ thống kê doanh số theo sản phẩm.
- Các thao tác insert/update/delete có thể gây **anomalies**: cập nhật một bản sao nhưng quên những bản khác.

Mô hình quan hệ tách `CUSTOMER`, `PRODUCT`, `SALES_ORDER` và `ORDER_ITEM`, với khóa ngoại bảo đảm tham chiếu, giải quyết một phần lớn các vấn đề đó.

### 10.2. Hiểu đúng chuẩn hóa

- **1NF:** tổ chức giá trị và các dòng theo quan hệ; tránh nhóm cột lặp kiểu `PRODUCT_1, PRODUCT_2` hoặc danh sách ID phân tách dấu phẩy trong một cột để thay quan hệ.
- **2NF:** khi bảng có khóa ghép, thuộc tính không khóa không nên phụ thuộc **chỉ vào một phần** của khóa nếu nó thực sự thuộc entity khác. Ví dụ tên sản phẩm thuộc `PRODUCT_ID`, không phải phụ thuộc vào toàn bộ `(ORDER_ID, LINE_NO)` trong bảng dòng đơn.
- **3NF:** thuộc tính không khóa không nên phụ thuộc bắc cầu vào khóa thông qua một thuộc tính không khóa khác khi đó là dữ liệu của entity khác. Ví dụ `CUSTOMER_NAME` có nguồn gốc ở `CUSTOMER`, không nên lặp như thông tin hiện hành trong mọi `SALES_ORDER`.

Đây là cách hiểu thực hành; khi cần chứng minh chuẩn hóa hình thức phải xác định đầy đủ **functional dependencies** và các candidate keys của bảng.

### 10.3. Denormalization có chủ đích: snapshot lịch sử

`ORDER_ITEM.UNIT_PRICE_AT_ORDER_VND` và `PRODUCT.UNIT_PRICE_VND` đều là giá, nhưng một cột biểu diễn **giá đã chốt của giao dịch** còn cột kia biểu diễn **giá catalog hiện tại**. Chúng không thể thay thế nhau.

Tương tự, thông tin shipping của đơn phải thể hiện **địa chỉ được chốt cho đơn đó**, tránh thay đổi khi khách sửa địa chỉ hồ sơ. Đây không phải lập luận để tùy ý sao chép mọi thông tin khách hàng vào mọi bảng. Chỉ lưu bản snapshot khi nghiệp vụ thật sự yêu cầu **lịch sử không được thay đổi theo dữ liệu nguồn hiện tại** và xác định rõ ai cập nhật snapshot, vào thời điểm nào.

## 11. Quan hệ và quy tắc nghiệp vụ vượt khả năng constraint đơn giản

### 11.1. Các trạng thái hợp lệ khác với chuyển trạng thái hợp lệ

`CHECK(ORDER_STATUS IN ('DRAFT','CONFIRMED','CANCELLED'))` chỉ kiểm tra **một giá trị nằm trong tập hợp**. Nó không thể bảo đảm quy tắc:

~~~text
DRAFT ─────────▶ CONFIRMED
  │                   │
  └────────▶ CANCELLED ◀────────┘

CANCELLED không quay lại CONFIRMED.
CONFIRMED phải có ít nhất một ORDER_ITEM.
~~~

Quy trình xác nhận thường cần transaction:

1. Khóa hoặc kiểm soát đồng thời trên đơn hàng cần cập nhật.
2. Xác nhận trạng thái hiện tại cho phép chuyển đổi.
3. Kiểm tra ít nhất một dòng sản phẩm và địa chỉ giao nếu nghiệp vụ yêu cầu.
4. Kiểm tra giá, số lượng, tồn kho/thanh toán khi chúng nằm trong quy tắc.
5. Cập nhật trạng thái và commit toàn bộ phần thay đổi liên quan; rollback nếu không đạt.

Những kiểm tra đa bảng phải xét **concurrency**: hai request cùng sửa một đơn có thể quan sát dữ liệu khác nhau nếu chỉ chạy các câu SELECT rời rạc. Logic nghiệp vụ và transaction isolation/locking cần được thiết kế cho tình huống này. Không nên coi một trigger đơn giản với SELECT COUNT ở bất kỳ thời điểm nào là lời giải tự động cho mọi invariant liên bảng.

### 11.2. Bắt buộc phải có ít nhất một dòng con

FK `ORDER_ITEM.ORDER_ID → SALES_ORDER.ORDER_ID` bảo đảm *dòng item không mồ côi*. Nó **không** bảo đảm mọi đơn có item. Một constraint cấp dòng trên `SALES_ORDER` cũng không thể đơn giản kiểm tra “đếm item phải lớn hơn 0” bằng subquery.

Nếu quy tắc chỉ áp dụng với đơn `CONFIRMED`, nên giữ cho đơn `DRAFT` hợp lệ khi chưa có item, rồi thực hiện kiểm tra tại transaction chuyển trạng thái. Nếu hệ thống có nhiều con đường cập nhật (API, import, batch, SQL trực tiếp), phải thống nhất ranh giới thực thi quy tắc thay vì chỉ đặt trong một màn hình Java.

### 11.3. Unique một cách có điều kiện

Ví dụ “email chỉ cần duy nhất với các tài khoản đang hoạt động” không tương đương một unique constraint đơn giản trên cột `EMAIL`. Có thể cân nhắc **function-based unique index** hoặc cách tổ chức dữ liệu khác nếu Oracle version và domain cho phép. Đây là thiết kế nâng cao, cần mô tả rõ xử lý NULL, chữ hoa/thường, chuẩn hóa khoảng trắng và các tình huống concurrent insert/update.

Không thêm unique constraint chỉ dựa vào quan sát rằng dữ liệu mẫu hiện tại chưa trùng. Phải hỏi **nghiệp vụ có cho phép trùng trong tương lai không**, và phạm vi duy nhất là trong một PDB, một tenant, một tổ chức hay toàn hệ thống.

### 11.4. Quy tắc phụ thuộc thời gian

Một khách hàng có thể có nhiều địa chỉ theo các khoảng hiệu lực. Không chỉ cần FK; còn cần quyết định hai khoảng thời gian có được chồng nhau không, cách biểu diễn đầu mút và xử lý transaction đồng thời. Oracle có kiểu dữ liệu thời gian và các cơ chế hỗ trợ, nhưng mô hình hóa ranh giới hiệu lực không tự hình thành chỉ bằng hai cột `VALID_FROM` và `VALID_TO`.

## 12. Chiến lược xóa và cập nhật quan hệ

Khi khách hàng đã có đơn, xóa khách hàng có thể làm mất ngữ cảnh lịch sử. Oracle FK mặc định ngăn thao tác xóa khóa cha nếu vẫn còn bản ghi con tham chiếu, trừ khi hành vi khác đã được cấu hình hoặc ràng buộc không còn áp dụng.

| Cách xử lý | Ảnh hưởng | Khi cân nhắc |
|---|---|---|
| **Giữ mặc định của FK** | Không xóa parent đang được child tham chiếu; thường gặp `ORA-02292` | Dữ liệu lịch sử quan trọng, không muốn xóa dây chuyền |
| **`ON DELETE CASCADE`** | Xóa parent sẽ xóa các dòng child liên quan | Child phụ thuộc hoàn toàn và không cần tồn tại độc lập, ví dụ một số bảng phụ tạm |
| **`ON DELETE SET NULL`** | Khi xóa parent, FK child thành NULL | Quan hệ phải **nullable** và nghiệp vụ cho phép child không có parent |
| **Soft delete / inactive flag** | Giữ bản ghi và khóa, đổi trạng thái hoạt động | Catalog/khách hàng có lịch sử giao dịch cần giữ |

Ví dụ cú pháp Oracle của một quan hệ tùy chọn:

~~~sql
-- Ví dụ khái niệm cho bảng hỗ trợ; manager_id phải nullable.
FOREIGN KEY (manager_id)
REFERENCES lab_employee (employee_id)
ON DELETE SET NULL
~~~

Oracle hỗ trợ hành vi `ON DELETE CASCADE` và `ON DELETE SET NULL` cho FK theo cú pháp thích hợp, nhưng **không có cú pháp FK `ON UPDATE CASCADE` phổ biến như ở một số RDBMS khác**. Dùng khóa kỹ thuật ổn định và tránh cập nhật PK là chiến lược thông dụng. Nếu một business key thay đổi, xử lý nó như thuộc tính nghiệp vụ mà không phải đổi hàng loạt foreign key.

**Không bật cascade theo thói quen.** Xóa `PRODUCT` không nên làm biến mất những dòng đơn lịch sử; xóa `CUSTOMER` không nên tự động xóa toàn bộ đơn nếu có yêu cầu lưu chứng từ. Chính sách xóa là quyết định nghiệp vụ và pháp lý/vận hành, không phải chỉ là lựa chọn cú pháp.

## 13. Kiểm tra mô hình thực tế qua Oracle data dictionary

Sau khi tạo bảng trong đúng schema/PDB, có thể đọc metadata để thấy **mô hình database đang bảo vệ điều gì**. Trước hết xác nhận session:

~~~sql
SELECT
  SYS_CONTEXT('USERENV', 'DB_NAME') AS database_name,
  SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
  SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
  SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Trong kiến trúc CDB/PDB, quan hệ và dữ liệu ứng dụng thuộc phạm vi PDB/schema đã chọn. Trùng tên bảng ở hai PDB không tự có nghĩa có FK hoặc dữ liệu dùng chung giữa chúng.

### 13.1. Xem bảng và cột

~~~sql
SELECT table_name
FROM user_tables
WHERE table_name LIKE 'LAB_%'
ORDER BY table_name;

SELECT
  table_name, column_id, column_name,
  data_type, nullable
FROM user_tab_columns
WHERE table_name IN (
  'LAB_CUSTOMER', 'LAB_PRODUCT',
  'LAB_SALES_ORDER', 'LAB_ORDER_ITEM', 'LAB_ORDER_SHIPPING'
)
ORDER BY table_name, column_id;
~~~

`USER_*` phản ánh đối tượng của user hiện tại. Nếu cần kiểm tra bảng thuộc schema khác mà bạn được phép xem, dùng các view `ALL_*` với điều kiện `OWNER`; góc nhìn `DBA_*` cần quyền catalog thích hợp.

### 13.2. Xem PK, FK, UNIQUE và CHECK

~~~sql
SELECT
  c.table_name,
  c.constraint_name,
  c.constraint_type,
  c.status,
  c.validated,
  cc.column_name,
  cc.position
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.table_name IN (
  'LAB_CUSTOMER', 'LAB_PRODUCT',
  'LAB_SALES_ORDER', 'LAB_ORDER_ITEM', 'LAB_ORDER_SHIPPING'
)
ORDER BY c.table_name, c.constraint_name, cc.position;
~~~

`CONSTRAINT_TYPE` thường dùng `P` cho primary key, `R` cho referential/foreign key, `U` cho unique, `C` cho check (bao gồm các biểu diễn liên quan NOT NULL trong catalog). `STATUS` và `VALIDATED` cho biết constraint có đang bật và đã kiểm tra tính phù hợp của dữ liệu theo trạng thái quản trị hay chưa. Một constraint `DISABLED` hay `NOVALIDATED` không mang cùng bảo đảm như constraint đang `ENABLED VALIDATED`.

### 13.3. Lấy quan hệ FK và bảng đích

~~~sql
SELECT
  child.table_name AS child_table,
  child.constraint_name AS fk_name,
  parent.table_name AS parent_table,
  parent.constraint_name AS parent_key_name
FROM user_constraints child
JOIN user_constraints parent
  ON parent.constraint_name = child.r_constraint_name
 AND parent.owner = child.r_owner
WHERE child.constraint_type = 'R'
  AND child.table_name LIKE 'LAB_%'
ORDER BY child.table_name, child.constraint_name;
~~~

Query mô tả quan hệ từ constraint của bảng con tới constraint PK/unique phía bảng cha. Khi cần bản ERD chính xác tới **cột**, phải kết hợp `USER_CONS_COLUMNS` cho cả FK và khóa tham chiếu theo thứ tự `POSITION`, đặc biệt với khóa ghép. **Tên cột giống nhau không chứng minh có FK**, chỉ metadata constraint hoặc DDL mới cho biết database đang thực thi quan hệ đó.

## 14. Từ mô hình tới ứng dụng Java/JPA và migration

Một hệ thống Java có thể dùng JPA/Hibernate để ánh xạ entity, nhưng nên phân biệt **quan hệ trong Java object graph** với **ràng buộc trong Oracle**.

Ví dụ:

~~~java
@Entity
@Table(name = "LAB_SALES_ORDER")
public class SalesOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "ORDER_ID")
    private Long id;

    @ManyToOne(optional = false, fetch = FetchType.LAZY)
    @JoinColumn(name = "CUSTOMER_ID", nullable = false)
    private Customer customer;
}
~~~

Đoạn code minh họa mapping; để chạy thực tế cần class `Customer` và cấu hình Jakarta Persistence/driver tương ứng. `@ManyToOne` mô tả quan hệ object và cách ORM truy cập; **FK được tạo và kiểm tra ở Oracle** mới bảo vệ cả những thay đổi đến từ SQL script, batch, công cụ ETL hoặc ứng dụng khác. Các tùy chọn cascade trong JPA cũng không đồng nhất hoàn toàn với `ON DELETE CASCADE` của database.

### 14.1. Quản lý schema bằng migration

Một repository có thể tổ chức:

~~~text
database/
├── migrations/
│   ├── V001__create_customer_and_product.sql
│   ├── V002__create_sales_order.sql
│   ├── V003__create_order_item_and_shipping.sql
│   ├── V004__add_indexes.sql
│   └── V005__add_business_rule_changes.sql
└── docs/
    ├── domain-rules.md
    └── erd.md
~~~

Tên migration ở đây minh họa convention của một công cụ như Flyway. Thứ tự tạo bảng phải tôn trọng phụ thuộc FK: tạo bảng cha trước, rồi bảng con hoặc dùng `ALTER TABLE` bổ sung FK sau. Khi thay đổi quan hệ, cần quan tâm **dữ liệu đã có**, không chỉ DDL mới: một FK mới có thể không validate được vì tồn tại bản ghi mồ côi; một unique constraint mới có thể thất bại vì trùng business key.

**Oracle DDL thường có implicit commit.** Không nên nghĩ một chuỗi `CREATE TABLE`/`ALTER TABLE` sẽ được hoàn tác đơn giản bằng `ROLLBACK` như một transaction DML. Migration cần có chiến lược triển khai, chạy thử, backup và phương án sửa tiếp nếu lỗi.

### 14.2. Thay đổi nghiệp vụ phải có kế hoạch dữ liệu

Giả sử ban đầu một đơn chỉ có một địa chỉ giao, sau này cần nhiều lần giao hàng từng phần. Việc đổi mô hình từ `ORDER_SHIPPING` 1:1 sang `SHIPMENT` 1:N không chỉ là thay `PRIMARY KEY`:

1. Xác định **một dòng shipment** đại diện cho một chuyến giao hay một kiện hàng.
2. Thêm `SHIPMENT_ID` nếu mỗi shipment cần danh tính độc lập.
3. Thêm FK `SHIPMENT.ORDER_ID`; bỏ ràng buộc unique một đơn–một shipment khi phù hợp.
4. Chuyển dữ liệu địa chỉ/shipping cũ thành bản ghi shipment theo logic thống nhất.
5. Cập nhật API, JPA, báo cáo, quy tắc trạng thái và dữ liệu lịch sử.
6. Kiểm chứng không mất quan hệ và chuẩn bị phương án chuyển đổi ứng dụng.

Đây là lý do mô hình quan hệ cần xuất phát từ **quy tắc nghiệp vụ**, không chỉ từ những form hiện đang có trên màn hình.

## 15. Bài tập thực hành theo cấp độ

### Bài 1 — Xác định entity và grain

Yêu cầu: “Một thư viện có độc giả, đầu sách, nhiều bản sao vật lý của một đầu sách và phiếu mượn. Một độc giả có thể mượn nhiều bản sao ở các thời điểm khác nhau.”

Hãy xác định entity và grain cho `READER`, `BOOK_TITLE`, `BOOK_COPY` và `LOAN`. Vì sao không nên chỉ có bảng `BOOK` với một cờ `IS_BORROWED` nếu cùng đầu sách có năm bản sao?

**Định hướng:** `BOOK_TITLE` diễn đạt tác phẩm/ấn phẩm ở mức đầu sách, còn `BOOK_COPY` diễn đạt từng bản sao vật lý. `LOAN` là sự kiện mượn một bản sao tại một khoảng thời gian. Một đầu sách có thể có nhiều copy, một copy có thể xuất hiện trong nhiều loan qua lịch sử.

### Bài 2 — Từ câu mô tả đến PK/FK

Yêu cầu: “Một lớp học có nhiều học viên; một học viên có thể tham gia nhiều lớp. Mỗi lần đăng ký cần ghi ngày và trạng thái.”

Hãy vẽ quan hệ và đề xuất các bảng `STUDENT`, `CLASS`, `ENROLLMENT`. Nếu một học viên chỉ được có **một đăng ký** vào cùng lớp, hãy chọn primary key hoặc unique constraint phù hợp.

**Định hướng:**

~~~text
STUDENT 1 ───< ENROLLMENT >─── 1 CLASS
                STUDENT_ID (FK)
                CLASS_ID   (FK)
                ENROLLED_AT
                STATUS
~~~

`PRIMARY KEY(STUDENT_ID, CLASS_ID)` phù hợp nếu không cho phép đăng ký lặp trong lịch sử. Nếu cần đăng ký nhiều lần sau khi rút/đăng ký lại, phải xác định grain mới: mỗi **lần đăng ký** là một entity riêng, có thể cần `ENROLLMENT_ID` và quy tắc unique có điều kiện cho đăng ký đang hoạt động.

### Bài 3 — Optionality của 1:N

Với quan hệ `CUSTOMER 1 — 0..N SALES_ORDER`, trả lời:

1. Cột nào chứa FK?
2. Vì sao FK đó là `NOT NULL`?
3. Khách hàng chưa có đơn hàng có vi phạm constraint không?
4. Nếu muốn bắt buộc mỗi khách có ít nhất một đơn thì các constraint hiện tại có đủ không?

**Đáp án:** FK là `SALES_ORDER.CUSTOMER_ID`; nó NOT NULL vì mỗi đơn phải thuộc đúng một khách. Khách chưa có đơn vẫn hợp lệ. FK này không thể bảo đảm mỗi khách đều có ít nhất một đơn.

### Bài 4 — Dòng đơn và giá lịch sử

Sau khi chèn mẫu, cập nhật `LAB_PRODUCT.UNIT_PRICE_VND` của `SKU-KEYBOARD` thành 500000. Dùng query phần 8.1 để kiểm tra giá đã chốt trong `LAB_ORDER_ITEM`.

**Câu hỏi:** Tại sao không nên tính lại giá của đơn cũ bằng giá hiện hành từ bảng `LAB_PRODUCT`?

**Định hướng:** Giá giao dịch là thuộc tính của **dòng đơn tại thời điểm đặt**, khác với giá catalog hiện tại. Không lưu snapshot sẽ làm thay đổi báo cáo lịch sử khi bảng sản phẩm được cập nhật.

### Bài 5 — Phân biệt quy tắc enforce được và chưa enforce được

Hãy phân loại:

| Quy tắc | Một constraint trên bảng đã đủ? |
|---|---|
| SKU không trùng | Có: `UNIQUE` và `NOT NULL` nếu bắt buộc |
| Mỗi dòng đơn chỉ tới sản phẩm tồn tại | Có: `FOREIGN KEY` |
| Số lượng lớn hơn 0 | Có: `CHECK` + `NOT NULL` |
| Đơn `CONFIRMED` có ít nhất một dòng | Không bằng một row-level CHECK/FK đơn giản |
| Không chuyển từ `CANCELLED` sang `CONFIRMED` | Không bằng CHECK chỉ kiểm tra danh sách trạng thái |
| Một đơn có tối đa một shipping snapshot | Có: `ORDER_SHIPPING.ORDER_ID` làm PK |

Hãy viết thêm cách quản lý **transaction và đồng thời** cho hai quy tắc chưa được constraint đơn giản bảo vệ.

### Bài 6 — Xác nhận thực tế qua data dictionary

Chạy các truy vấn `USER_CONSTRAINTS` và `USER_CONS_COLUMNS` ở phần 13. Tìm:

- PK của `LAB_ORDER_ITEM` gồm những cột nào?
- `LAB_ORDER_ITEM.PRODUCT_ID` tham chiếu khóa nào?
- `LAB_ORDER_SHIPPING` có thể có hai hàng cùng `ORDER_ID` không?
- Có phải mọi FK đều đã có index riêng không?

**Định hướng:** PK dòng đơn là `(ORDER_ID, LINE_NO)`; product FK tham chiếu `LAB_PRODUCT.PRODUCT_ID`; shipping không thể có hai hàng cùng PK; index FK cần đánh giá riêng, Oracle không tự tạo một index riêng cho mọi FK.

## 16. Quy trình ra quyết định khi thêm một quan hệ mới

Khi một yêu cầu mới xuất hiện, có thể đi theo chuỗi câu hỏi:

~~~text
MÔ TẢ NGHIỆP VỤ
      |
      v
Một dòng dữ liệu đại diện cho gì?
      |
      v
Entity, value object hay trạng thái/thuộc tính?
      |
      v
Khóa nhận diện là gì? Có business key duy nhất không?
      |
      v
Quan hệ 1:1, 1:N, N:M? Bắt buộc hay tùy chọn?
      |
      v
Chọn PK, FK, UNIQUE, NOT NULL, CHECK và kiểu dữ liệu
      |
      v
Cần snapshot lịch sử, soft delete hoặc quy tắc thời gian?
      |
      v
Quy tắc nào vượt khả năng constraint đơn giản?
      |
      v
Thiết kế transaction / service / cơ chế thực thi bổ sung
      |
      v
Tạo migration và dữ liệu mẫu, chạy truy vấn JOIN
      |
      v
Đối chiếu data dictionary và yêu cầu nghiệp vụ
~~~

**Điểm cốt lõi:** Quan hệ trong Oracle không chỉ là nét nối giữa hai ô trên sơ đồ ERD. **Primary key** làm rõ danh tính; **foreign key** bảo vệ tham chiếu; **NOT NULL, UNIQUE và CHECK** đưa những quy tắc cục bộ xuống database; **bảng liên kết** biến N:M thành dữ liệu có thể truy vấn và kiểm soát; còn **transaction cùng logic nghiệp vụ** bảo vệ các invariant vượt phạm vi một dòng. Khi mỗi bảng có grain rõ ràng và mỗi constraint gắn với một quy tắc cụ thể, schema Oracle sẽ dễ hiểu, dễ mở rộng và đáng tin cậy hơn trong cả SQL lẫn ứng dụng Java.

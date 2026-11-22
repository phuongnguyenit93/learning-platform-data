# Bất biến (invariant) mô tả điều luôn phải đúng trong một mô hình

## Mục tiêu bài học

Sau bài này, bạn có thể giải thích bất biến dữ liệu là gì, phân biệt bất biến với validation và điều kiện của một thao tác, nhận diện phạm vi mà quy tắc phải được giữ đúng, và chuyển quy tắc nghiệp vụ thành ràng buộc có thể kiểm chứng. Bạn cũng sẽ biết cách chọn nơi thực thi bất biến trong database, transaction hoặc tầng nghiệp vụ; xử lý cập nhật đồng thời; và kiểm tra dữ liệu hiện có trước khi áp dụng ràng buộc.

## 1. Bất biến là gì?

**Bất biến (invariant)** là một mệnh đề hoặc điều kiện phải luôn đúng đối với mô hình trong phạm vi và trạng thái đã xác định. Bất biến mô tả điều mà hệ thống không được phép vi phạm khi dữ liệu được tạo, cập nhật, xóa hoặc chuyển trạng thái.

Ví dụ trong hệ thống bán hàng:

- Số lượng trên một dòng hàng phải lớn hơn 0.
- Mỗi dòng hàng phải thuộc về một đơn hàng tồn tại.
- Mã đơn hàng phải duy nhất trong phạm vi cửa hàng.
- Tổng tiền thanh toán được ghi nhận không được vượt quá số tiền phải thu nếu nghiệp vụ không cho phép thu thừa.
- Một đơn hàng đã giao không thể quay lại trạng thái nháp.
- Hai lịch đặt phòng đã xác nhận không được chiếm cùng phòng trong những khoảng thời gian chồng lấn.

Những điều kiện này không chỉ mô tả dữ liệu mẫu. Chúng phải đúng với mọi trạng thái dữ liệu hợp lệ mà hệ thống chấp nhận.

Có thể diễn đạt một bất biến bằng vị từ logic trên trạng thái dữ liệu D:

~~~text
Invariant P: P(D) = true
~~~

Mỗi thao tác hợp lệ biến trạng thái D thành D'. Điều cần bảo đảm là:

~~~text
P(D) = true  =>  P(D') = true
~~~

Nói cách khác, nếu trạng thái trước thao tác hợp lệ thì sau khi thao tác hoàn tất, trạng thái mới vẫn phải thỏa mãn bất biến. Nếu một thao tác khiến bất biến sai, hệ thống phải từ chối thao tác, điều chỉnh cách thực hiện hoặc đưa dữ liệu về trạng thái hợp lệ trước khi commit.

### 1.1. Bất biến có phạm vi

Một câu như “mỗi đơn hàng phải có ít nhất một dòng hàng” chưa đủ chính xác nếu đơn hàng nháp được phép chưa có dòng hàng.

Cần làm rõ:

- Áp dụng cho đơn hàng ở mọi trạng thái hay chỉ đơn đã xác nhận?
- Có áp dụng cho đơn nhập từ hệ thống cũ không?
- Điều kiện phải đúng sau mỗi câu lệnh SQL hay sau khi transaction hoàn tất?
- Có áp dụng xuyên nhiều tenant hoặc chỉ trong một tenant?
- Quy tắc có hiệu lực từ thời điểm nào?

Một bất biến tốt luôn có phạm vi, điều kiện áp dụng và cách xác định trạng thái hợp lệ.

Ví dụ rõ hơn:

> Mỗi đơn hàng ở trạng thái CONFIRMED phải có ít nhất một dòng hàng hợp lệ tại thời điểm transaction chuyển đơn sang trạng thái đó.

Câu này xác định đối tượng, điều kiện trạng thái và thời điểm phải kiểm tra.

## 2. Phân biệt bất biến với validation và điều kiện thao tác

Các khái niệm này liên quan nhưng giải quyết những câu hỏi khác nhau.

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Invariant | Điều gì phải luôn đúng trong trạng thái hợp lệ? | Số dư tài khoản không âm |
| Validation | Dữ liệu đầu vào có hợp lệ theo định dạng hoặc quy tắc không? | Email có định dạng được chấp nhận |
| Precondition | Điều gì phải đúng trước khi thao tác được phép chạy? | Tài khoản phải đang hoạt động trước khi chuyển tiền |
| Postcondition | Điều gì phải đúng sau khi thao tác hoàn tất? | Tài khoản gửi giảm và tài khoản nhận tăng cùng số tiền |
| Authorization | Chủ thể gọi có quyền thực hiện không? | Người dùng chỉ được sửa đơn thuộc tenant của mình |

Một validation có thể kiểm tra dữ liệu trước khi ghi, nhưng dữ liệu vẫn có thể trở nên sai do một request khác chạy đồng thời. Bất biến phải được bảo vệ xuyên suốt các thao tác ghi và các đường truy cập dữ liệu.

Precondition và postcondition thường mô tả một thao tác cụ thể. Một thao tác đúng cần giữ các invariant của mô hình sau khi hoàn tất.

Ví dụ chuyển tiền:

- Precondition: tài khoản gửi đang hoạt động và có đủ số dư.
- Thao tác: trừ tiền tài khoản gửi, cộng tiền tài khoản nhận.
- Postcondition: số dư hai tài khoản thay đổi đúng số tiền chuyển.
- Invariant: tổng giá trị tiền trong phạm vi được quản lý được bảo toàn, số dư không âm nếu chính sách cấm thấu chi.

Không phải mọi validation đều là invariant. Kiểm tra trường nhập có tối đa 100 ký tự có thể là quy tắc giao diện hoặc hợp đồng API. Nếu mọi dữ liệu được lưu trong database cũng phải tuân thủ giới hạn đó, nó có thể trở thành constraint của schema.

## 3. Các nhóm bất biến thường gặp

Phân loại giúp chọn cách biểu diễn và nơi thực thi.

### 3.1. Bất biến miền giá trị (domain invariant)

Giá trị của thuộc tính phải nằm trong miền được phép.

Ví dụ:

- số lượng lớn hơn 0;
- phần trăm nằm trong khoảng 0 đến 100;
- trạng thái thuộc tập giá trị đã định nghĩa;
- ngày kết thúc không sớm hơn ngày bắt đầu;
- mã tiền tệ thuộc danh sách được hỗ trợ.

Có thể bảo vệ bằng kiểu dữ liệu, NOT NULL, CHECK, enum hoặc validation ở biên ứng dụng.

~~~sql
CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    discount_percent NUMERIC(5, 2) NOT NULL
        CHECK (discount_percent >= 0 AND discount_percent <= 100)
);
~~~

Kiểu dữ liệu giúp loại bỏ một số giá trị không hợp lệ, còn CHECK biểu diễn điều kiện miền cụ thể. Cần kiểm tra cú pháp và hành vi của hệ quản trị đang sử dụng.

### 3.2. Bất biến định danh và duy nhất (identity and uniqueness invariant)

Một định danh phải duy nhất trong phạm vi đã xác định.

Ví dụ:

- mỗi khách hàng có một customer_id;
- mã đơn hàng duy nhất trong một cửa hàng;
- số dòng hàng duy nhất trong một đơn hàng;
- mã ngoài duy nhất trong cùng issuer và namespace.

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    store_id BIGINT NOT NULL,
    order_number VARCHAR(50) NOT NULL,
    UNIQUE (store_id, order_number)
);
~~~

Ràng buộc trên cho phép hai cửa hàng dùng cùng order_number nhưng không cho phép trùng trong cùng cửa hàng. Phạm vi duy nhất cần khớp với quy tắc nghiệp vụ.

### 3.3. Bất biến tham chiếu (referential invariant)

Mọi tham chiếu phải trỏ đến đối tượng hợp lệ trong phạm vi dữ liệu.

Ví dụ:

- mỗi dòng hàng tham chiếu một đơn hàng tồn tại;
- mỗi khoản thanh toán tham chiếu một đơn hàng hợp lệ;
- mỗi nhân viên tham chiếu một phòng ban tồn tại nếu quy tắc yêu cầu bắt buộc.

~~~sql
CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

Khóa ngoại bảo vệ tham chiếu. NOT NULL yêu cầu phải có giá trị tham chiếu. Nếu FK được phép NULL, mô hình phải định nghĩa rõ trường hợp không liên kết có ý nghĩa gì.

### 3.4. Bất biến liên thuộc tính (cross-attribute invariant)

Hai hoặc nhiều thuộc tính trong cùng bản ghi phải thỏa mãn một quan hệ.

Ví dụ:

- ngày kết thúc phải lớn hơn hoặc bằng ngày bắt đầu;
- giá sau giảm không lớn hơn giá trước giảm;
- trạng thái hủy phải có thời điểm hủy;
- khoảng ngày có ngày bắt đầu trước ngày kết thúc.

~~~sql
CREATE TABLE contracts (
    contract_id BIGINT PRIMARY KEY,
    starts_on DATE NOT NULL,
    ends_on DATE,
    CHECK (ends_on IS NULL OR ends_on >= starts_on)
);
~~~

Quy tắc được đặt gần dữ liệu giúp mọi ứng dụng ghi vào bảng đều chịu cùng một điều kiện.

### 3.5. Bất biến liên bản ghi (cross-row invariant)

Điều kiện phụ thuộc vào nhiều hàng hoặc nhiều thực thể.

Ví dụ:

- tổng số tiền đã phân bổ không vượt quá ngân sách;
- một phòng không có hai lịch đặt xác nhận chồng lấn;
- tổng các dòng phân bổ phải bằng tổng giao dịch;
- mỗi đơn đã xác nhận có ít nhất một dòng hàng.

Nhóm này khó biểu diễn bằng CHECK đơn giản vì CHECK thông thường chỉ kiểm tra giá trị của hàng đang được ghi. Không nên dùng một CHECK có truy vấn đến bảng khác như thể nó tự bảo vệ được quy tắc liên hàng. Cần chọn UNIQUE, khóa ngoại, exclusion constraint, trigger hoặc transaction/logic nghiệp vụ phù hợp.

### 3.6. Bất biến trạng thái và chuyển trạng thái

Một đối tượng có tập trạng thái hợp lệ và chỉ được chuyển theo một số đường cho phép.

Ví dụ:

~~~text
DRAFT -> CONFIRMED -> FULFILLING -> SHIPPED -> COMPLETED
   |          |
   v          v
CANCELLED   CANCELLED
~~~

Không phải mọi cặp trạng thái đều được phép chuyển trực tiếp. Một đơn đã SHIPPED có thể không được chuyển về DRAFT. Quy tắc này không chỉ là kiểm tra trạng thái thuộc danh sách; nó kiểm tra quan hệ giữa trạng thái trước và trạng thái sau.

Có thể bảo vệ bằng logic chuyển trạng thái trong domain service, transaction và kiểm soát cập nhật đồng thời. Nếu có nhiều dịch vụ cùng cập nhật trạng thái, cần một cơ chế thống nhất để không có đường ghi nào bỏ qua quy tắc.

### 3.7. Bất biến thời gian (temporal invariant)

Quy tắc phụ thuộc thời gian, khoảng hiệu lực hoặc thứ tự sự kiện.

Ví dụ:

- thời điểm kết thúc không trước thời điểm bắt đầu;
- mã định danh không được gán cho hai đối tượng trong các khoảng hiệu lực chồng lấn;
- một nhân viên không có hai phân công chính cùng hiệu lực;
- lịch đặt phòng không chồng lấn với lịch đã xác nhận khác.

Một số quy tắc có thể dùng range type hoặc exclusion constraint trong hệ quản trị hỗ trợ. Với hệ khác, có thể cần transaction và khóa phù hợp để kiểm tra khoảng thời gian an toàn.

### 3.8. Bất biến tổng hợp và cân bằng (aggregate/balance invariant)

Một tập dữ liệu phải giữ quan hệ tổng thể.

Ví dụ trong kế toán:

- tổng debit bằng tổng credit trong mỗi bút toán;
- số dư được tính từ các giao dịch theo quy tắc xác định;
- tổng phân bổ ngân sách không vượt mức được duyệt.

Với quy tắc cân bằng, cần xác định grain, phạm vi tổng hợp, tiền tệ, độ chính xác và thời điểm ghi nhận. Nếu có nhiều loại tiền, không được cộng trực tiếp số tiền khác đơn vị mà không có quy tắc quy đổi.

## 4. Bất biến ở cấp thuộc tính, thực thể và mô hình

Bất biến có thể áp dụng ở nhiều cấp.

### 4.1. Cấp thuộc tính

Một thuộc tính có miền giá trị rõ:

- quantity là số nguyên dương;
- currency_code có định dạng và thuộc danh sách hỗ trợ;
- status không nhận giá trị tùy ý;
- email không được NULL nếu nghiệp vụ yêu cầu.

Các quy tắc đơn giản thường phù hợp với NOT NULL, CHECK, kiểu dữ liệu và enum.

### 4.2. Cấp thực thể

Một bản ghi phải thỏa mãn nhiều điều kiện kết hợp:

- hợp đồng có ngày bắt đầu và ngày kết thúc hợp lệ;
- một lần thanh toán phải có số tiền dương, tiền tệ và mã giao dịch;
- trạng thái COMPLETED yêu cầu completed_at;
- hồ sơ đã đóng không nhận cập nhật thuộc tính thông thường.

Có thể kết hợp constraint ở database với logic nghiệp vụ để bảo vệ điều kiện phụ thuộc trạng thái hoặc quy trình.

### 4.3. Cấp quan hệ

Quan hệ phải bảo đảm bội số, tính bắt buộc hoặc điều kiện liên kết:

- mỗi OrderItem thuộc đúng một Order;
- mỗi tài khoản có tối đa một hồ sơ xác minh đang hoạt động;
- một nhân viên chỉ có một phòng ban chính tại một thời điểm;
- một đơn đã xác nhận phải có ít nhất một dòng hàng.

Khóa ngoại và UNIQUE xử lý được nhiều trường hợp, nhưng một số điều kiện tối thiểu ở phía cha cần transaction, trigger hoặc cơ chế khác.

### 4.4. Cấp aggregate hoặc toàn mô hình

Một aggregate là ranh giới nhất quán được thiết kế để bảo vệ các quy tắc liên quan trong một đơn vị nghiệp vụ. Ví dụ, đơn hàng và các dòng hàng có thể được thay đổi trong cùng một transaction trước khi đơn xác nhận.

Một bất biến toàn mô hình có thể liên quan đến nhiều aggregate hoặc nhiều dịch vụ. Khi đó, cần xác định liệu quy tắc phải được bảo đảm tức thời hay có thể hội tụ sau một quy trình đồng bộ. Không nên tuyên bố một invariant được bảo đảm toàn cục nếu kiến trúc chỉ kiểm tra riêng lẻ ở từng dịch vụ.

## 5. Chọn nơi thực thi bất biến

Một quy tắc có thể được kiểm tra ở nhiều lớp. Chọn nơi thực thi dựa trên phạm vi, khả năng của công nghệ và cách dữ liệu được ghi.

### 5.1. Ràng buộc ở database

Database phù hợp với những quy tắc có thể khai báo trực tiếp và cần bảo vệ bất kể dữ liệu đến từ ứng dụng nào.

Các công cụ phổ biến:

| Cơ chế | Bảo vệ điều gì | Ví dụ |
|---|---|---|
| NOT NULL | Giá trị bắt buộc | order_id phải có |
| CHECK | Điều kiện trên hàng | quantity > 0 |
| PRIMARY KEY | Định danh duy nhất và không NULL | order_id |
| UNIQUE | Không trùng trong phạm vi khóa | (store_id, order_number) |
| FOREIGN KEY | Tham chiếu hợp lệ | order_items.order_id |
| EXCLUSION | Không cho các giá trị/range xung đột theo toán tử | Khoảng đặt phòng không chồng lấn |
| Trigger | Quy tắc cần logic theo thao tác hoặc nhiều hàng | Kiểm tra thay đổi theo trạng thái |

Ưu điểm của database constraint là mọi đường ghi vào database đều chịu kiểm tra, kể cả batch job hoặc ứng dụng khác. Tuy nhiên, constraint cần được thiết kế đúng và không thay thế toàn bộ logic nghiệp vụ.

### 5.2. Logic ở tầng nghiệp vụ

Một số quy tắc cần ngữ cảnh nghiệp vụ hoặc nhiều bước:

- trạng thái hiện tại có cho phép hành động này không;
- người dùng có quyền thay đổi không;
- có cần phê duyệt trước khi vượt hạn mức không;
- một đơn đã xác nhận có được sửa dòng hàng không;
- một quy trình có thể hoàn tất khi dịch vụ ngoài xác nhận hay chưa.

Các quy tắc này thường thuộc domain service hoặc application service. Tuy nhiên, nếu nhiều tiến trình có thể cập nhật cùng dữ liệu, logic ứng dụng phải kết hợp transaction, locking hoặc concurrency control. Chỉ đọc dữ liệu rồi kiểm tra ở ứng dụng có thể tạo race condition.

### 5.3. Validation ở API hoặc giao diện

API và giao diện nên kiểm tra sớm để phản hồi thân thiện:

- trường bắt buộc;
- định dạng;
- độ dài;
- miền giá trị;
- dữ liệu có thể hiển thị ngay lỗi.

Đây là lớp trải nghiệm và bảo vệ biên. Nó không phải lớp bảo đảm cuối cùng cho dữ liệu nếu còn batch import, worker, script quản trị hoặc dịch vụ khác có thể ghi trực tiếp.

### 5.4. Chọn lớp theo loại quy tắc

| Loại quy tắc | Nơi thực thi thường phù hợp |
|---|---|
| NOT NULL, miền giá trị đơn giản | Database và API |
| Duy nhất theo một hoặc nhiều cột | UNIQUE/index và xử lý lỗi ở ứng dụng |
| Tham chiếu tồn tại | FOREIGN KEY |
| Chuyển trạng thái theo nghiệp vụ | Domain service + transaction |
| Không chồng lấn khoảng thời gian | Exclusion constraint hoặc transaction/locking |
| Tổng hợp nhiều hàng | Transaction, trigger hoặc quy trình domain phù hợp |
| Quyền truy cập theo người dùng/tenant | Authorization và cơ chế bảo vệ dữ liệu ở database nếu có |
| Quy tắc hội tụ giữa dịch vụ | Event/process orchestration và kiểm tra nhất quán |

Có thể thực thi cùng một quy tắc ở nhiều lớp để cải thiện trải nghiệm và bảo vệ dữ liệu. Cần tránh để các lớp dùng định nghĩa khác nhau, chẳng hạn API cho phép số lượng bằng 0 trong khi database từ chối.

## 6. Bảo vệ bất biến khi có cập nhật đồng thời

Một bất biến có thể đúng khi kiểm tra từng request riêng lẻ nhưng bị vi phạm khi hai request chạy cùng lúc.

### 6.1. Race condition khi kiểm tra số lượng

Giả sử một phòng chỉ còn một chỗ. Hai request cùng đọc available_count = 1. Cả hai đều kiểm tra thấy còn chỗ rồi cùng tạo đặt chỗ. Kết quả có hai booking dù sức chứa chỉ còn một.

Kiểm tra ở ứng dụng theo trình tự “đọc rồi ghi” không đủ an toàn nếu không có kiểm soát đồng thời.

### 6.2. Cập nhật có điều kiện

Với số lượng tồn kho, có thể dùng một câu UPDATE nguyên tử:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = :product_id
  AND available_quantity >= 1;
~~~

Sau khi chạy, ứng dụng kiểm tra số hàng bị ảnh hưởng:

- 1 hàng: giữ chỗ thành công;
- 0 hàng: không đủ tồn kho hoặc sản phẩm không tồn tại.

Database đánh giá điều kiện và cập nhật trong một thao tác nguyên tử theo cơ chế của hệ quản trị. Nếu cần ghi booking cùng thao tác trừ tồn kho, đặt cả hai trong một transaction để chúng commit hoặc rollback cùng nhau.

### 6.3. Khóa bi quan (pessimistic locking)

Có thể khóa bản ghi cần kiểm tra trong transaction, ví dụ SELECT ... FOR UPDATE trong các hệ quản trị hỗ trợ.

Quy trình:

1. Bắt đầu transaction.
2. Khóa bản ghi tồn kho.
3. Đọc số lượng mới nhất.
4. Kiểm tra đủ hàng.
5. Trừ số lượng và tạo booking.
6. Commit.

Request khác phải chờ hoặc nhận kết quả theo chính sách timeout. Khóa cần được lấy theo thứ tự nhất quán để giảm nguy cơ deadlock.

### 6.4. Khóa lạc quan (optimistic locking)

Có thể dùng cột version để phát hiện dữ liệu đã bị thay đổi:

~~~sql
UPDATE inventory
SET available_quantity = :new_quantity,
    version = version + 1
WHERE product_id = :product_id
  AND version = :expected_version;
~~~

Nếu không cập nhật được hàng nào, version đã thay đổi; ứng dụng cần đọc lại và thử lại hoặc trả lỗi xung đột.

Optimistic locking phù hợp khi xung đột không quá thường xuyên. Retry phải có giới hạn và không được lặp lại side effect ngoài database một cách mù quáng.

### 6.5. Isolation level và serializable transaction

Transaction isolation quyết định mức độ các transaction nhìn thấy thay đổi của nhau. Với một số bất biến liên hàng, có thể cần SERIALIZABLE hoặc khóa phù hợp để tránh write skew.

SERIALIZABLE có thể khiến transaction bị abort khi phát hiện xung đột tuần tự hóa. Ứng dụng cần xử lý retry an toàn. Chỉ chọn isolation level cao hơn không thay thế việc hiểu quy tắc và kiểm thử dưới concurrency thực tế.

## 7. Ví dụ: bảo vệ các bất biến của đơn hàng

Xét mô hình đơn giản gồm Order và OrderItem.

Các quy tắc:

1. Mỗi dòng hàng thuộc đúng một đơn hàng.
2. Số lượng phải là số nguyên dương.
3. Đơn giá không âm.
4. Đơn nháp có thể chưa có dòng hàng.
5. Đơn chỉ được chuyển sang CONFIRMED khi có ít nhất một dòng hàng hợp lệ.
6. Đơn đã SHIPPED không được quay lại DRAFT.

### 7.1. Constraint ở database

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'SHIPPED', 'CANCELLED'))
);

CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
);
~~~

Các constraint trên bảo vệ trạng thái thuộc tập giá trị, tham chiếu đơn hàng, số lượng và đơn giá. Chúng chưa bảo đảm đơn CONFIRMED có ít nhất một dòng hàng, và cũng chưa bảo vệ đường chuyển trạng thái hợp lệ.

### 7.2. Transaction chuyển trạng thái

Một quy trình có thể:

1. Bắt đầu transaction.
2. Khóa hàng Order cần xác nhận.
3. Kiểm tra trạng thái hiện tại là DRAFT.
4. Kiểm tra có ít nhất một OrderItem hợp lệ.
5. Cập nhật status thành CONFIRMED.
6. Commit.

Nếu thêm dòng hàng và xác nhận đơn có thể diễn ra đồng thời, cần bảo vệ cả hai đường ghi. Chẳng hạn, các thao tác thêm/xóa dòng hàng phải khóa hoặc kiểm tra cùng Order theo một quy tắc nhất quán. Nếu chỉ khóa Order trong thao tác xác nhận nhưng thao tác xóa dòng hàng không phối hợp cùng cơ chế, bất biến vẫn có thể bị vi phạm.

### 7.3. Chuyển trạng thái có điều kiện

Có thể giới hạn cập nhật theo trạng thái trước:

~~~sql
UPDATE orders
SET status = 'SHIPPED'
WHERE order_id = :order_id
  AND status = 'CONFIRMED';
~~~

Nếu không có hàng nào được cập nhật, đơn không ở trạng thái cho phép hoặc không tồn tại. Cách này giúp ngăn một số cập nhật sai trạng thái, nhưng các quy tắc bổ sung như đã có hàng giao, tồn kho đã trừ hoặc thanh toán đã xác nhận vẫn cần được bảo vệ.

## 8. Ví dụ: bất biến tổng tiền và cân bằng

Giả sử một đơn hàng có các dòng hàng với quantity và unit_price. Tổng tiền dòng hàng được tính:

~~~text
line_total = quantity * unit_price
order_total = SUM(line_total) - discounts + fees
~~~

Cần xác định:

- đơn giá có bao gồm thuế không;
- chiết khấu áp dụng ở dòng hay toàn đơn;
- quy tắc làm tròn ở mỗi dòng hay cuối tổng;
- tiền tệ nào được dùng;
- tổng tiền được tính lại hay lưu snapshot;
- điều gì xảy ra khi dòng hàng thay đổi sau xác nhận.

Nếu lưu order_total như một giá trị cache hoặc snapshot, phải có quy tắc đồng bộ. Nếu tính động từ các dòng, cần kiểm soát transaction để báo cáo không đọc trạng thái nửa chừng.

Với kế toán kép, một bút toán thường cần tổng debit bằng tổng credit trong cùng loại tiền tệ và phạm vi bút toán. Không thể chỉ dùng CHECK trên từng dòng để đảm bảo tổng nhiều dòng cân bằng. Có thể cần stored procedure, trigger deferred, hoặc một transaction service chỉ cho phép post bút toán khi đã cân bằng.

Không nên dùng kiểu số thực nhị phân cho phép tính tiền cần chính xác thập phân. Chọn NUMERIC/DECIMAL với precision và scale phù hợp, đồng thời định nghĩa rõ cách làm tròn.

## 9. Ví dụ: khoảng thời gian không được chồng lấn

Giả sử một phòng họp không được có hai lịch đặt đã xác nhận chồng lấn.

Bất biến có thể viết:

> Với cùng room_id, hai booking ở trạng thái CONFIRMED không được có khoảng thời gian giao nhau.

Nếu hệ quản trị hỗ trợ range và exclusion constraint, có thể biểu diễn trực tiếp. Ví dụ PostgreSQL:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_bookings (
    booking_id BIGINT PRIMARY KEY,
    room_id BIGINT NOT NULL,
    during TSTZRANGE NOT NULL,
    status VARCHAR(20) NOT NULL,
    CHECK (NOT isempty(during)),
    EXCLUDE USING gist (
        room_id WITH =,
        during WITH &&
    ) WHERE (status = 'CONFIRMED')
);
~~~

Trong ví dụ PostgreSQL này, toán tử && kiểm tra hai khoảng có giao nhau. Exclusion constraint ngăn hai booking đã xác nhận cho cùng phòng có khoảng chồng lấn. Cần chọn kiểu range, biên đóng/mở và quy tắc thời gian phù hợp với nghiệp vụ.

Nếu database không hỗ trợ exclusion constraint, có thể kiểm tra trong transaction bằng khóa trên tài nguyên phòng hoặc một cơ chế tuần tự hóa tương đương. Chỉ truy vấn xem có booking trùng rồi insert mà không khóa hoặc bảo vệ concurrency có thể tạo race condition.

## 10. Bất biến trong hệ thống nhiều dịch vụ

Trong kiến trúc phân tán, dữ liệu có thể nằm ở nhiều database và được đồng bộ qua message. Không phải bất biến nào cũng có thể được bảo vệ bằng một transaction ACID duy nhất.

Cần phân biệt:

- **Bất biến cục bộ:** phải luôn đúng trong một database hoặc aggregate.
- **Bất biến liên dịch vụ:** phụ thuộc dữ liệu do nhiều dịch vụ sở hữu.
- **Điều kiện hội tụ:** trạng thái có thể tạm thời chưa đồng bộ nhưng phải đạt kết quả đúng sau quy trình.
- **Bất biến an toàn:** điều không được xảy ra, ví dụ không thu tiền hai lần.
- **Bất biến tiến triển:** điều cuối cùng phải xảy ra, ví dụ một giao dịch hợp lệ cuối cùng được hoàn tất hoặc thất bại rõ ràng.

Ví dụ, dịch vụ đơn hàng và dịch vụ thanh toán có database riêng. Không thể giả định một transaction SQL bao trùm cả hai. Có thể dùng saga hoặc quy trình orchestration:

1. Đơn hàng chuyển sang PENDING_PAYMENT.
2. Dịch vụ thanh toán tạo yêu cầu với idempotency key.
3. Nhà cung cấp trả kết quả.
4. Dịch vụ thanh toán phát event.
5. Dịch vụ đơn hàng cập nhật trạng thái theo event.
6. Nếu thanh toán thất bại hoặc hết hạn, quy trình xử lý hủy hoặc thử lại theo chính sách.

Trong khoảng thời gian đồng bộ, đơn hàng có thể đang PENDING_PAYMENT. Mô hình cần định nghĩa rõ trạng thái trung gian nào hợp lệ và điều gì tuyệt đối không được xảy ra, chẳng hạn không phát hành giao hàng khi chưa có điều kiện thanh toán cần thiết.

Idempotency, outbox/inbox, retry có giới hạn và xử lý event trùng giúp bảo vệ các bất biến trong môi trường message có thể gửi lại.

## 11. Phát hiện và sửa dữ liệu vi phạm bất biến

Trước khi thêm constraint vào một hệ thống đang chạy, cần kiểm tra dữ liệu hiện có. Nếu dữ liệu đã vi phạm, migration có thể thất bại hoặc constraint mới không thể được bật an toàn.

### 11.1. Kiểm tra dữ liệu trước khi áp dụng

Ví dụ tìm số lượng không hợp lệ:

~~~sql
SELECT order_item_id, quantity
FROM order_items
WHERE quantity <= 0;
~~~

Tìm khóa ngoại mồ côi:

~~~sql
SELECT oi.order_item_id, oi.order_id
FROM order_items oi
LEFT JOIN orders o ON o.order_id = oi.order_id
WHERE o.order_id IS NULL;
~~~

Tìm mã đơn trùng trong cửa hàng:

~~~sql
SELECT store_id, order_number, COUNT(*)
FROM orders
GROUP BY store_id, order_number
HAVING COUNT(*) > 1;
~~~

Các truy vấn này giúp xác định bản ghi cần xử lý trước khi bật ràng buộc.

### 11.2. Lập kế hoạch sửa dữ liệu

Với mỗi vi phạm, cần xác định:

- dữ liệu nào là nguồn chuẩn;
- có thể sửa tự động hay cần người có thẩm quyền;
- có cần giữ giá trị cũ để audit không;
- các quan hệ phụ thuộc có bị ảnh hưởng không;
- cách tránh tạo vi phạm mới trong lúc migration chạy;
- cách rollback nếu migration thất bại.

Không nên xóa dữ liệu vi phạm chỉ để migration chạy qua nếu dữ liệu đó có giá trị nghiệp vụ hoặc pháp lý.

### 11.3. Thêm constraint an toàn

Với hệ thống đang có tải, có thể cần quy trình nhiều bước:

1. Phân tích và thống kê vi phạm.
2. Sửa hoặc cách ly dữ liệu không hợp lệ.
3. Triển khai code mới để không tạo thêm vi phạm.
4. Thêm constraint hoặc index theo cách ít khóa nhất mà hệ quản trị hỗ trợ.
5. Xác minh constraint đã được kiểm tra đầy đủ.
6. Theo dõi lỗi ghi và truy vấn sau triển khai.

Tên lệnh, khả năng thêm constraint chưa validate và chiến lược index online khác nhau theo hệ quản trị. Hãy kiểm tra tài liệu phiên bản database trước khi chọn cách migration.

## 12. Ghi chép và kiểm chứng bất biến

Một bất biến quan trọng nên được ghi lại như một phần của mô hình dữ liệu hoặc tài liệu nghiệp vụ.

Thông tin nên có:

| Trường | Ý nghĩa |
|---|---|
| Invariant ID | Mã ổn định, ví dụ INV-ORDER-001 |
| Phát biểu | Điều kiện phải luôn đúng |
| Phạm vi | Thực thể, aggregate, tenant hoặc hệ thống |
| Điều kiện áp dụng | Trạng thái, thời điểm hoặc loại bản ghi |
| Chủ sở hữu | Người/nhóm chịu trách nhiệm nghiệp vụ |
| Cơ chế bảo vệ | CHECK, FK, UNIQUE, transaction, domain logic... |
| Hành vi khi vi phạm | Từ chối, retry, cách ly hoặc xử lý thủ công |
| Cách kiểm chứng | Query, test, metric hoặc audit |
| Liên kết | Requirement, decision, schema và API liên quan |

### 12.1. Ví dụ invariant record

**INV-ORDER-001 — Đơn xác nhận có ít nhất một dòng hàng**

- Phát biểu: Order ở trạng thái CONFIRMED phải có ít nhất một OrderItem hợp lệ.
- Phạm vi: một Order và các OrderItem thuộc nó.
- Điều kiện: tại thời điểm transaction xác nhận đơn.
- Cơ chế bảo vệ: transaction kiểm tra số dòng và khóa Order; thao tác thêm/xóa dòng hàng phối hợp cùng cơ chế.
- Hành vi vi phạm: không cho chuyển trạng thái, trả lỗi nghiệp vụ.
- Kiểm chứng: test đơn rỗng, đơn có một dòng, hai request xác nhận đồng thời và request xóa dòng hàng đồng thời.
- Chủ sở hữu: nghiệp vụ đơn hàng.

Bản ghi này giúp kỹ sư hiểu điều kiện, người kiểm thử biết tình huống cần xác minh và người vận hành biết cách tìm vi phạm.

### 12.2. Kiểm thử bất biến

Có thể kiểm thử theo các lớp:

- **Unit test:** kiểm tra hàm miền hoặc logic chuyển trạng thái.
- **Integration test:** xác nhận database thực sự từ chối dữ liệu vi phạm.
- **Concurrency test:** chạy nhiều request đồng thời để tìm race condition.
- **Migration test:** kiểm tra dữ liệu cũ và việc bật constraint.
- **Monitoring:** chạy truy vấn phát hiện vi phạm hoặc theo dõi lỗi constraint trong vận hành.

Không chỉ kiểm thử đường đi hợp lệ. Hãy chủ động tạo dữ liệu sai, request lặp, cập nhật đồng thời, timeout và retry.

## 13. Những sai lầm thường gặp

- **Chỉ kiểm tra ở giao diện:** batch job hoặc dịch vụ khác có thể ghi dữ liệu sai. Đặt ràng buộc ở lớp có thể bảo vệ mọi đường ghi.
- **Định nghĩa invariant quá mơ hồ:** “đơn hàng hợp lệ” không cho biết trạng thái, phạm vi hay điều kiện nào cần đúng.
- **Dùng CHECK cho quy tắc liên hàng:** CHECK thông thường không phải cơ chế an toàn để kiểm tra tổng hoặc truy vấn bản ghi khác.
- **Đọc rồi ghi mà không bảo vệ concurrency:** hai request có thể cùng vượt qua kiểm tra và tạo trạng thái sai.
- **Cho rằng transaction tự động giải quyết mọi race condition:** isolation level và cách khóa cần phù hợp với invariant.
- **Trộn validation với authorization:** dữ liệu đúng định dạng không có nghĩa người gọi có quyền thay đổi nó.
- **Dùng trigger mà không ghi tài liệu:** logic ẩn có thể khiến ứng dụng khó hiểu lỗi hoặc phát sinh side effect.
- **Bật constraint trước khi kiểm tra dữ liệu cũ:** migration có thể thất bại hoặc làm gián đoạn ghi.
- **Không xác định phản hồi khi vi phạm:** người dùng và dịch vụ gọi cần biết lỗi có thể sửa, retry hay phải dừng.
- **Không kiểm tra mọi đường ghi:** một dịch vụ có thể giữ invariant trong khi một batch import phá vỡ nó.
- **Tuyên bố invariant toàn cục trong hệ thống phân tán:** nếu chỉ có kiểm tra cục bộ và đồng bộ bất đồng bộ, cần mô tả trạng thái trung gian và điều kiện hội tụ.

## 14. Kết luận

Bất biến mô tả điều luôn phải đúng trong trạng thái dữ liệu hợp lệ và trong phạm vi đã xác định. Nó có thể liên quan đến miền giá trị, định danh, tham chiếu, nhiều thuộc tính, nhiều hàng, trạng thái, thời gian hoặc tổng hợp.

Để bảo vệ bất biến, hãy viết quy tắc rõ ràng, xác định phạm vi và thời điểm áp dụng, chọn cơ chế thực thi phù hợp, xử lý cập nhật đồng thời và kiểm tra dữ liệu hiện có. Database constraint bảo vệ tính đúng đắn ở tầng lưu trữ; transaction và logic nghiệp vụ bảo vệ các quy trình phức tạp; validation giúp phát hiện lỗi sớm. Các lớp cần dùng cùng một định nghĩa để mô hình luôn nhất quán.

## Tự kiểm tra

1. Bất biến khác validation và precondition như thế nào?
2. Vì sao câu “mỗi đơn hàng phải có ít nhất một dòng hàng” cần xác định trạng thái áp dụng?
3. Phân biệt domain invariant, referential invariant và cross-row invariant bằng ví dụ.
4. Vì sao CHECK không phù hợp để bảo đảm tổng tiền của nhiều hàng?
5. Hai request cùng đặt chỗ cuối cùng có thể vi phạm invariant như thế nào? Nêu hai cách bảo vệ.
6. Khi nào nên dùng UNIQUE, FOREIGN KEY, transaction hoặc exclusion constraint?
7. Trong hệ thống nhiều dịch vụ, cần phân biệt bất biến cục bộ và điều kiện hội tụ ra sao?
8. Trước khi thêm constraint vào database đang chạy, cần kiểm tra và chuẩn bị những gì?
9. Hãy viết một invariant record cho một quy tắc trong hệ thống bạn biết, gồm phát biểu, phạm vi, cơ chế bảo vệ và cách kiểm chứng.


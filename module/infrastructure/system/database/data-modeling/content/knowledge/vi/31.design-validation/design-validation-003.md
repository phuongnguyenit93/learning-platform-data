# Kiểm tra bất biến với dữ liệu biên, dữ liệu thiếu và trạng thái không hợp lệ

## Mục tiêu học tập và phạm vi

Một lược đồ dữ liệu có thể trông rất hợp lý trên sơ đồ ERD nhưng vẫn cho phép những trạng thái mà nghiệp vụ **không bao giờ chấp nhận**: dòng đơn có số lượng bằng 0, giảm giá lớn hơn tiền hàng, đơn được xác nhận dù chưa có dòng sản phẩm, khách hàng thiếu mọi phương thức liên hệ, hoặc hai phiên bản dữ liệu lịch sử cùng có hiệu lực tại một thời điểm. Những sai sót này thường không xuất hiện trong bộ dữ liệu mẫu “đẹp” vì mọi hàng đều đầy đủ và hợp lệ.

**Kiểm chứng thiết kế** là quá trình chuyển các phát biểu nghiệp vụ thành **bất biến (invariant) có thể quan sát và thử phản chứng**. Ta cố ý đưa dữ liệu biên, dữ liệu thiếu, liên kết không tồn tại và trạng thái chuyển đổi sai vào hệ thống thử để xem mô hình có **chấp nhận dữ liệu đúng và từ chối dữ liệu sai** theo đúng hợp đồng hay không.

Bài thuộc chương **Kiểm chứng thiết kế** của module **DATABASE_DATA_MODELING**. Mục tiêu chung của module là chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, từ thực thể, quan hệ và ràng buộc đến chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; đồng thời so sánh mô hình quan hệ, document, đồ thị và phân tích để có cấu trúc phù hợp, dễ tiến hóa và kiểm chứng. Trọng tâm của bài là **kiểm tra bất biến với dữ liệu biên, dữ liệu thiếu và trạng thái không hợp lệ**, không chỉ kiểm tra câu SQL có chạy hay không.

Sau bài học, bạn có thể:

1. Phân biệt **bất biến của thực thể, quan hệ, tập dữ liệu, trạng thái và thời gian**, đồng thời xác định nơi thích hợp để bảo vệ chúng.
2. Lập bộ giá trị kiểm thử **ngay dưới, đúng tại và ngay trên ngưỡng**; phân biệt trường hợp hợp lệ và không hợp lệ theo miền nghiệp vụ.
3. Nhận diện tác động của **NULL, chuỗi rỗng, giá trị không biết và logic ba giá trị của SQL**, đặc biệt với CHECK và UNIQUE.
4. Thiết kế kiểm thử âm cho **PK, FK, UNIQUE, NOT NULL, CHECK**, tính duy nhất theo phạm vi và các ràng buộc nhiều hàng.
5. Kiểm tra **chuyển trạng thái hợp lệ**, dữ liệu đến muộn, khoảng thời gian không chồng lấn và các bất biến chịu tác động của giao dịch đồng thời.
6. Viết ví dụ PostgreSQL có fixture, truy vấn phát hiện vi phạm và các bài thử **mong đợi thất bại**.
7. Kết hợp kiểm thử ở **domain Java, lớp ứng dụng, database và luồng tích hợp**; biết giới hạn của mỗi lớp.
8. Xây dựng ma trận kiểm chứng và tiêu chí nghiệm thu để mô hình không chỉ đúng với dữ liệu mẫu nhỏ mà còn chịu được trường hợp biên và thay đổi.

> **Giới hạn:** Ví dụ SQL dùng PostgreSQL trong môi trường thử nghiệm. Chúng không phải hướng dẫn chạy các lệnh cố tình gây lỗi trên production. Một lệnh bị constraint từ chối là **kết quả kiểm thử mong đợi**, không phải một bước migration thành công. Các bất biến xuyên nhiều hàng, nhiều giao dịch hoặc nhiều hệ thống cần được thử bằng cơ chế phù hợp, không thể chứng minh chỉ bằng một CHECK ở một hàng.

## 1. Bất biến là gì và vì sao cần kiểm chứng?

### 1.1. Định nghĩa theo ngữ nghĩa dữ liệu

**Bất biến dữ liệu** là một điều kiện **phải luôn đúng tại những thời điểm hệ thống cam kết trạng thái hợp lệ**. Ví dụ:

- Mỗi dòng đơn bán có **số lượng dương**.
- Số tiền giảm giá dòng nằm trong khoảng **từ 0 đến tổng tiền trước giảm**.
- Một khóa dòng đơn trỏ tới **đơn tồn tại**.
- Một tài khoản thuộc tenant A không được liên kết với đối tượng thuộc tenant B khi nghiệp vụ cấm.
- Một mã khách có **tối đa một phiên bản SCD2 đang hiệu lực tại một thời điểm**.
- Một đơn có trạng thái CONFIRMED phải có **ít nhất một dòng hàng hợp lệ**.

Không phải mọi quy tắc đều phải được bảo vệ bằng một câu lệnh SQL duy nhất. **Bất biến định nghĩa điều đúng**, còn CHECK, FK, transaction, trigger, API validation và kiểm thử tích hợp là **những cơ chế có thể bảo vệ/kiểm tra điều đó ở những ranh giới khác nhau**.

### 1.2. Phân biệt invariant, expectation và quality threshold

| Loại phát biểu | Ví dụ | Cách hiểu |
| --- | --- | --- |
| **Invariant cứng** | Dòng đơn có quantity > 0 | Một hàng quantity = 0 là không hợp lệ |
| **Quan hệ bắt buộc** | order_line.order_id trỏ tới order hiện hữu | Không chấp nhận dòng mồ côi ở trạng thái đã commit |
| **Quy tắc trạng thái** | Chỉ có thể CONFIRM một đơn DRAFT đủ điều kiện | Phải kiểm tra chuyển trạng thái, không chỉ tên trạng thái |
| **Quy tắc lịch sử** | Hai khoảng hiệu lực SCD2 của cùng khách không chồng lấn | Phải kiểm tra nhiều hàng và thời điểm |
| **Kỳ vọng nghiệp vụ** | 95% đơn giao trong 2 ngày | Đây là KPI, không nên mã hóa thành CHECK “mọi đơn giao trong 2 ngày” |
| **Ngưỡng chất lượng dữ liệu** | Tỷ lệ thiếu địa chỉ trong tập cũ dưới 1% | Là tiêu chí đo/chấp nhận theo chính sách, không nhất thiết cấm từng hàng |

Không biến mọi chỉ số thống kê thành ràng buộc cứng. Ngược lại, không ghi invariant quan trọng như một mục tiêu mơ hồ (“dữ liệu nên tốt”) khi cần **ngăn trạng thái sai ngay tại thời điểm ghi**.

### 1.3. Những thời điểm cần giữ bất biến

Một invariant có thể được định nghĩa tại:

- **Khi tạo object/domain command**: không thể tạo Money có currency rỗng.
- **Khi kết thúc một giao dịch DB**: order_line phải có order tương ứng.
- **Khi một bước nghiệp vụ chuyển trạng thái**: đơn từ DRAFT sang CONFIRMED phải có hàng hợp lệ.
- **Khi công bố dữ liệu phân tích**: fact/dimension phải đủ để báo cáo không đếm trùng.
- **Sau khi xử lý sự kiện liên hệ thống**: projection có thể trễ nhưng không được hiển thị trạng thái “đã quyết toán” khi chưa có bằng chứng được chấp nhận.

Một số mô hình cho phép **trạng thái trung gian trong một transaction** trước khi COMMIT, hoặc trong một saga trước khi hoàn tất. Điều đó không đồng nghĩa được phép phát hành dữ liệu sai: phải **ghi rõ trạng thái trung gian nào hợp lệ, ai được nhìn thấy và lúc nào invariant bắt buộc đúng**.

## 2. Viết bất biến dưới dạng điều kiện kiểm thử được

### 2.1. Từ câu nói mơ hồ thành phát biểu chính xác

Ví dụ yêu cầu: “Không cho đơn hàng có giảm giá bất thường”.

Phát biểu này chưa đủ để kiểm chứng. Có thể tách thành:

1. Mỗi dòng có **quantity là số nguyên dương**, tối đa 1.000 đơn vị theo chính sách ví dụ.
2. Đơn giá được chốt ở dòng **không âm**, đơn vị VND.
3. **discount_amount** thuộc khoảng [0, quantity × unit_price].
4. **net_amount** bằng quantity × unit_price − discount_amount.
5. Nếu tồn tại chương trình miễn phí hợp lệ, **net_amount = 0 được phép**.
6. Nếu một khách không được giảm 100%, đó là **quy tắc khác** và cần nêu rõ theo loại chương trình; không tự suy từ câu “bất thường”.

Phép kiểm thử **ngay tại biên** phải xuất phát từ quy tắc, không từ trực giác “0 luôn là xấu”.

### 2.2. Mẫu đặc tả bất biến

Với mỗi invariant, nên ghi:

~~~~text
INVARIANT ID: LINE-DISCOUNT-001

Đối tượng: dòng đơn hợp lệ.
Phạm vi: từng order_line đã lưu.
Thời điểm kiểm tra: trước/ở COMMIT khi insert hoặc update.

Tiền đề:
  quantity thuộc [1,1000], integer.
  unit_price là VND, không âm.

Mệnh đề:
  0 <= discount_amount <= quantity * unit_price
  net_amount = quantity * unit_price - discount_amount

Được phép:
  discount_amount = 0
  discount_amount = quantity * unit_price

Không được phép:
  discount_amount < 0
  discount_amount > quantity * unit_price
  quantity = 0 hoặc quantity > 1000

Bảo vệ:
  Domain/API validation + DB CHECK/NOT NULL
  net_amount là generated column theo công thức.

Kiểm chứng:
  Test dữ liệu tại ngưỡng và lân cận ngưỡng.
  Kiểm tra các lỗi SQL bị từ chối.
  Đối soát công thức từ dữ liệu đã commit.
~~~~

Mẫu này giúp QA, lập trình viên, kiến trúc sư dữ liệu và người sở hữu nghiệp vụ dùng **cùng một nghĩa**. Một test chỉ chứng minh quy tắc khi **đầu vào, thời điểm và kết quả mong đợi** đã được định nghĩa.

### 2.3. Sơ đồ kiểm chứng từ yêu cầu đến bằng chứng

~~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ"] --> B["Bất biến + phạm vi + thời điểm"]
    B --> C["Phân lớp dữ liệu: hợp lệ / biên / thiếu / sai"]
    C --> D["Mô hình: kiểu, khóa, trạng thái, quan hệ"]
    D --> E["Cơ chế bảo vệ: Java + SQL + transaction"]
    E --> F["Test dương: dữ liệu hợp lệ phải nhận"]
    E --> G["Test âm: dữ liệu sai phải bị từ chối"]
    F --> H["Đối soát và bằng chứng"]
    G --> H
    H --> I{"Đạt hợp đồng?"}
    I -- "Không" --> B
    I -- "Có" --> J["Nghiệm thu thiết kế ở phạm vi đã kiểm"]
~~~~

Không có bước nào là “vẽ ERD đẹp → coi như dữ liệu đúng”. **Bằng chứng chấp nhận dữ liệu hợp lệ và từ chối dữ liệu không hợp lệ** mới giúp xác nhận cơ chế bảo vệ đúng với mô hình.

## 3. Thiết kế dữ liệu biên: đừng chỉ thử giá trị trung bình

### 3.1. Phân vùng tương đương và phân tích giá trị biên

**Phân vùng tương đương** (*equivalence partitioning*) chia miền đầu vào thành những lớp dự kiến có hành vi giống nhau. **Phân tích biên** (*boundary value analysis*) tập trung vào điểm **vừa dưới, đúng tại và vừa trên** ranh giới của từng lớp.

Với quantity nguyên trong [1,1000]:

| Giá trị | Lớp | Kết quả dự kiến |
| ---: | --- | --- |
| -1 | Nhỏ hơn miền cho phép | Từ chối |
| 0 | Ngay dưới biên thấp | Từ chối |
| **1** | **Biên thấp hợp lệ** | Chấp nhận |
| 2 | Ngay trên biên thấp | Chấp nhận |
| 500 | Giá trị bình thường | Chấp nhận |
| 999 | Ngay dưới biên cao | Chấp nhận |
| **1000** | **Biên cao hợp lệ** | Chấp nhận |
| 1001 | Ngay trên biên cao | Từ chối |
| NULL | Thiếu dữ liệu | Từ chối nếu quantity bắt buộc |

Nếu code kiểm tra quantity > 1 thay vì ≥ 1, bộ test ở **biên thấp** sẽ phát hiện. Nếu code chỉ thử quantity = 2 và 500, lỗi bị che.

### 3.2. Biên số tiền và đơn vị

Với unit_price NUMERIC(14,2), discount_amount NUMERIC(14,2):

- **0.00** có thể là giá hợp lệ nếu nghiệp vụ cho phép hàng tặng.
- **-0.01** phải bị từ chối nếu giá không âm.
- Chiết khấu **bằng** tổng tiền có thể hợp lệ theo hợp đồng.
- Chiết khấu **hơn tổng tiền 0.01** phải bị từ chối.
- Cần thử **giá trị rất lớn, nhiều chữ số thập phân và phép nhân quantity × unit_price** để phát hiện overflow, cắt cụt hoặc làm tròn không đúng.
- Phải phân biệt **VND, USD** hoặc đơn vị tiền nhỏ nhất; số 100 có đúng kiểu kỹ thuật vẫn có thể sai nghĩa.

Ví dụ quantity = 2, unit_price = 100000.00 VND:

| discount_amount | net_amount dự kiến | Hợp lệ? |
| ---: | ---: | --- |
| -0.01 | Không tính | Không |
| 0.00 | 200000.00 | Có |
| 199999.99 | 0.01 | Có |
| 200000.00 | 0.00 | Có theo quy tắc ví dụ |
| 200000.01 | Không tính | Không |

**Không đưa số tiền vào kiểu floating-point nhị phân nếu cần bảo đảm thập phân tài chính chính xác.** Dùng kiểu decimal và quy tắc làm tròn rõ; test giới hạn precision/scale ở cả Java và database.

### 3.3. Biên thời gian

Với khoảng hiệu lực dạng **[valid_from, valid_to)** (bao gồm đầu, không bao gồm cuối):

- **valid_to = valid_from**: khoảng rỗng, từ chối nếu mỗi phiên bản phải tồn tại trong một khoảng dương.
- **valid_to ngay sau valid_from**: hợp lệ.
- **Thời điểm bằng valid_from**: được tính là có hiệu lực.
- **Thời điểm bằng valid_to**: **không** còn hiệu lực.
- **valid_to NULL**: có thể nghĩa là phiên bản hiện hành/chưa biết lúc kết thúc, tùy hợp đồng.
- Hai khoảng cùng nguồn và cùng đối tượng **chồng lấn** phải bị phát hiện nếu mô hình yêu cầu không chồng lấn.

**Không đánh đồng ngày địa phương và thời điểm UTC.** Test quanh nửa đêm, múi giờ, ranh giới năm và quy tắc lịch kinh doanh nếu chúng ảnh hưởng báo cáo.

### 3.4. Biên cardinality và kích thước tập

Với yêu cầu “một đơn CONFIRMED phải có ít nhất một dòng”, cần thử:

- **0 dòng:** không được CONFIRM.
- **1 dòng:** số lượng dòng tối thiểu hợp lệ.
- **Nhiều dòng:** hợp lệ nếu không vi phạm các quy tắc khác.
- **Thêm hai dòng cùng line_no:** vi phạm UNIQUE(order_id, line_no).
- **Xóa dòng cuối của đơn CONFIRMED:** phải bị chặn hoặc dẫn tới một quy trình đổi trạng thái hợp lệ.

Bẫy lớn: một FK trên order_line.order_id bảo đảm **dòng có cha**, nhưng **không bảo đảm cha có ít nhất một dòng**. Đây là hai phía khác nhau của quan hệ.

## 4. Dữ liệu thiếu: NULL, chuỗi rỗng và “không biết”

### 4.1. Không có dữ liệu không phải lúc nào cũng là NULL

| Biểu diễn | Có thể mang nghĩa | Lưu ý |
| --- | --- | --- |
| **SQL NULL** | Không biết, không được cung cấp hoặc không áp dụng, nếu chưa phân tách | Một giá trị SQL duy nhất không tự nói rõ **lý do** |
| **Chuỗi rỗng ''** | Người gửi có đưa trường nhưng không có ký tự | Khác NULL trong PostgreSQL; có thể là dữ liệu sai |
| **Chuỗi chỉ khoảng trắng** | Dữ liệu có ký tự khoảng trắng | Trim rồi xác định hợp lệ theo nghiệp vụ |
| **Số 0** | Một giá trị số cụ thể | Không tự nghĩa là thiếu; tồn kho 0 có thể đúng |
| **UNKNOWN enum/member** | Trạng thái chưa xác định được đặt tên | Cần phân biệt với NULL và “không áp dụng” |
| **N/A / không áp dụng** | Thuộc tính không có nghĩa với đối tượng này | Không nên gộp với trường hợp chưa thu thập |
| **Sentinel (-1, 9999-12-31)** | Giá trị quy ước thay cho trạng thái khác | Dễ gây sai khi SUM, JOIN hoặc so sánh nếu không được quản trị |

Ví dụ khách chỉ đăng ký bằng điện thoại thì email NULL có thể **hợp lệ**. Nhưng email = '   ' không phải một địa chỉ email có nghĩa. Vì thế không thể dùng CHECK(email IS NOT NULL) cho mọi khách, cũng không thể chấp nhận mọi chuỗi chỉ vì cột không NULL.

### 4.2. Logic ba giá trị trong SQL

SQL dùng ba kết quả logic: **TRUE**, **FALSE**, **UNKNOWN**. Các biểu thức so sánh với NULL thường trả về **UNKNOWN**, không phải FALSE.

~~~~sql
SELECT
    (NULL::INTEGER > 0) AS compare_null,
    (NULL::INTEGER = NULL::INTEGER) AS null_equals_null,
    (NULL::INTEGER IS NULL) AS null_check,
    (NULL::INTEGER IS NOT DISTINCT FROM NULL::INTEGER)
        AS null_safe_equal;
-- compare_null = NULL (UNKNOWN)
-- null_equals_null = NULL (UNKNOWN)
-- null_check = TRUE
-- null_safe_equal = TRUE
~~~~

Điều này ảnh hưởng trực tiếp đến ràng buộc **CHECK**. Trong PostgreSQL, một CHECK **chỉ từ chối khi kết quả là FALSE**. Nếu biểu thức trả UNKNOWN do NULL, ràng buộc CHECK **không từ chối** hàng đó.

~~~~sql
CREATE TABLE check_null_demo (
    quantity INTEGER CHECK (quantity > 0)
);

INSERT INTO check_null_demo(quantity)
VALUES (NULL); -- ĐƯỢC CHẤP NHẬN: CHECK không thay NOT NULL.
~~~~

Nếu quantity bắt buộc, cần:

~~~~sql
CREATE TABLE check_null_strict_demo (
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~~

**Nguyên tắc:** Mỗi khi đọc CHECK có phép so sánh, hãy hỏi **cột nào có thể NULL và UNKNOWN được phép đi qua không?** Cú pháp CHECK trông nghiêm ngặt chưa chứng minh ràng buộc đủ chặt.

### 4.3. NULL trong UNIQUE và khóa ngoại

Trong PostgreSQL, một UNIQUE thông thường **cho phép nhiều hàng chứa NULL** ở cột được so sánh vì NULL không được xem bằng nhau theo ngữ nghĩa mặc định của UNIQUE. Với email tùy chọn, điều này có thể hợp lý: nhiều khách đăng ký chỉ bằng điện thoại đều có email NULL.

~~~~sql
CREATE TABLE email_unique_demo (
    person_id BIGINT PRIMARY KEY,
    email TEXT UNIQUE
);

INSERT INTO email_unique_demo(person_id, email)
VALUES (1, NULL), (2, NULL);
-- Hai hàng cùng email NULL được chấp nhận theo UNIQUE mặc định.
~~~~

Nếu nghiệp vụ thật sự yêu cầu **coi NULL là trùng**, PostgreSQL hiện đại có tùy chọn UNIQUE NULLS NOT DISTINCT, nhưng cần kiểm tra phiên bản và áp dụng đúng phạm vi. **Không nên cấm nhiều email NULL chỉ để “làm UNIQUE mạnh hơn”** khi nghiệp vụ cho phép người dùng không có email.

Với FK nullable, một hàng có child_fk = NULL thường không bị coi là mồ côi: **không có tham chiếu để kiểm tra**. Nếu quan hệ là bắt buộc, cần kết hợp **NOT NULL + FK**. Với FK ghép, hành vi các thành phần NULL cần được quyết định rõ (mặc định MATCH SIMPLE cho phép một số tổ hợp thiếu); nếu toàn bộ khóa ghép phải có đủ thành phần, cần NOT NULL cho các cột hoặc một quy tắc phù hợp.

### 4.4. Test missing là nhiều trường hợp riêng

Cho một API nhận email và phone:

~~~~text
{ "email": "a@example.org", "phone": null }
{ "email": null, "phone": "0900000000" }
{ "email": null, "phone": null }
{ "email": "", "phone": "" }
{ "email": "   ", "phone": null }
{ "email": "a@example.org" }  (phone vắng mặt)
{ }  (cả hai trường vắng mặt)
~~~~

**Vắng mặt trong JSON**, **JSON null** và **SQL NULL** có thể được framework ánh xạ khác nhau, nhất là khi xử lý PATCH: trường vắng mặt có thể nghĩa là **không thay đổi**, còn trường null có thể nghĩa là **xóa giá trị**. Cần kiểm thử hợp đồng API và mapping, không suy diễn từ DDL.

Trong ví dụ tiếp theo, quy tắc nghiệp vụ là **khách phải có ít nhất một phương thức liên hệ không rỗng sau khi trim**, còn việc địa chỉ email/điện thoại có định dạng thật sự hợp lệ được xử lý thêm ở boundary và các phép kiểm tra riêng.

## 5. Xây dựng lược đồ PostgreSQL để kiểm chứng bất biến

### 5.1. Bối cảnh của bộ dữ liệu thử

Một hệ thống bán hàng nhỏ có:

- **Customer:** có ít nhất một phương thức liên hệ không rỗng; email là tùy chọn, nhưng nếu có thì không được để trống.
- **Product:** có SKU duy nhất và giá niêm yết không âm.
- **SalesOrder:** thuộc đúng một khách có thật, trạng thái trong {DRAFT, CONFIRMED, CANCELLED}, mốc confirmed_at hợp lệ.
- **OrderLine:** thuộc đúng một đơn, tham chiếu sản phẩm có thật; line_no duy nhất trong đơn; quantity từ 1 đến 1.000; giá và giảm giá hợp lệ.
- **Mục tiêu nghiệp vụ bổ sung:** Một đơn CONFIRMED phải có ít nhất một dòng hợp lệ. Đây là **bất biến nhiều hàng**, cần cơ chế vượt quá CHECK trên một hàng.

Các quy tắc chỉ mang tính **giả định của bài học**. Một hệ thống thực tế có thể cần quantity theo đơn vị đo, giá âm cho một loại bút toán điều chỉnh, nhiều tiền tệ hoặc khách ẩn danh. Trước khi thay đổi ràng buộc, phải xác định **ý nghĩa nghiệp vụ** thay vì cứng nhắc áp ví dụ.

### 5.2. Các bảng và ràng buộc

Chạy trên database thử nghiệm riêng, với quyền tạo schema/bảng:

~~~~sql
CREATE SCHEMA validation_lab;

CREATE TABLE validation_lab.customer (
    customer_id BIGINT PRIMARY KEY,
    email TEXT,
    phone TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_email_not_blank
        CHECK (email IS NULL OR BTRIM(email) <> ''),
    CONSTRAINT ck_phone_not_blank
        CHECK (phone IS NULL OR BTRIM(phone) <> ''),
    CONSTRAINT ck_contact_required
        CHECK (
            NULLIF(BTRIM(email), '') IS NOT NULL
            OR NULLIF(BTRIM(phone), '') IS NOT NULL
        )
);

-- Email được xem là không phân biệt chữ hoa/thường
-- theo quy tắc minh họa; cần xác minh chính sách thực tế.
CREATE UNIQUE INDEX uq_customer_email_normalized
    ON validation_lab.customer (LOWER(BTRIM(email)))
    WHERE email IS NOT NULL;

CREATE TABLE validation_lab.product (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL
        CHECK (BTRIM(product_name) <> ''),
    list_price NUMERIC(14, 2) NOT NULL
        CHECK (list_price >= 0)
);

CREATE TABLE validation_lab.sales_order (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES validation_lab.customer(customer_id),
    status TEXT NOT NULL DEFAULT 'DRAFT',
    created_at TIMESTAMPTZ NOT NULL,
    confirmed_at TIMESTAMPTZ,
    CONSTRAINT ck_order_status
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    CONSTRAINT ck_confirm_time
        CHECK (confirmed_at IS NULL OR confirmed_at >= created_at),
    CONSTRAINT ck_confirm_requires_time
        CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL)
);

CREATE TABLE validation_lab.order_line (
    line_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES validation_lab.sales_order(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL
        REFERENCES validation_lab.product(product_id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    discount_amount NUMERIC(18, 2) NOT NULL,
    currency_code CHAR(3) NOT NULL DEFAULT 'VND',
    net_amount NUMERIC(18, 2) GENERATED ALWAYS AS
        (quantity * unit_price - discount_amount) STORED,
    CONSTRAINT uq_order_line_no UNIQUE (order_id, line_no),
    CONSTRAINT ck_line_quantity CHECK (quantity BETWEEN 1 AND 1000),
    CONSTRAINT ck_line_unit_price CHECK (unit_price >= 0),
    CONSTRAINT ck_line_discount
        CHECK (
            discount_amount >= 0
            AND discount_amount <= quantity * unit_price
        ),
    CONSTRAINT ck_line_currency CHECK (currency_code = 'VND')
);
~~~~

**Các bảo đảm có thể suy từ DDL:**

- customer_id, product_id, order_id và line_id là khóa duy nhất không NULL.
- (order_id, line_no) duy nhất theo từng đơn, nhưng **line_no có thể lặp giữa các đơn khác nhau**.
- Mỗi dòng đơn trỏ đến đúng một order và một product **đã tồn tại trong cùng database**.
- Quantity, unit_price và discount_amount tuân thủ phạm vi được nêu, do các cột đầu vào đều NOT NULL nên không để UNKNOWN lọt qua CHECK qua NULL.
- net_amount được tính bằng cột GENERATED, tránh lưu hai giá trị tiền không khớp trong một dòng.
- Email **có thể NULL** nếu phone được cung cấp, nhưng một chuỗi chỉ khoảng trắng không được chấp nhận.
- Tên trạng thái là một trong ba giá trị đã công bố; nếu status = CONFIRMED thì confirmed_at không NULL và không trước created_at.

**Điều DDL chưa bảo đảm:**

- Đơn CONFIRMED **có ít nhất một dòng**.
- Một đơn chỉ được chuyển theo các bước **DRAFT → CONFIRMED → CANCELLED** cho phép, vì CHECK chỉ thấy **trạng thái mới**, không thấy lịch sử chuyển đổi.
- Không ai sửa dòng của một đơn đã CONFIRMED nếu chính sách yêu cầu bất biến giá chốt.
- Một customer bị vô hiệu hóa có còn được phép mua hay không.
- Email thực sự thuộc quyền sử dụng của người đăng ký; một cú pháp đơn giản không xác thực quyền sở hữu.
- Tổng quantity đặt có nằm trong khả năng cấp phát của kho khác hay không.

Những điều này đòi hỏi **các quy tắc và phép kiểm chứng bổ sung**, chứ không nên tuyên bố đã “bảo vệ mọi bất biến” sau khi tạo bảng.

### 5.3. Dữ liệu thử hợp lệ

~~~~sql
INSERT INTO validation_lab.customer
    (customer_id, email, phone)
VALUES
    (1, 'an@example.org', NULL),
    (2, NULL, '0900000002'),
    (3, 'binh@example.org', '0900000003');

INSERT INTO validation_lab.product
    (product_id, sku, product_name, list_price)
VALUES
    (101, 'NOTE-A5', 'Sổ tay A5', 100000.00),
    (102, 'PEN-BLUE', 'Bút mực xanh', 20000.00);

INSERT INTO validation_lab.sales_order
    (order_id, customer_id, status, created_at, confirmed_at)
VALUES
    (1001, 1, 'DRAFT',
     TIMESTAMPTZ '2026-10-01 08:00:00+07', NULL),
    (1002, 2, 'DRAFT',
     TIMESTAMPTZ '2026-10-01 09:00:00+07', NULL);

INSERT INTO validation_lab.order_line
    (line_id, order_id, line_no, product_id, quantity,
     unit_price, discount_amount)
VALUES
    (201, 1001, 1, 101, 2, 100000.00, 10000.00),
    (202, 1001, 2, 102, 1, 20000.00, 0.00),
    (203, 1002, 1, 101, 1, 100000.00, 100000.00);

UPDATE validation_lab.sales_order
SET status = 'CONFIRMED',
    confirmed_at = TIMESTAMPTZ '2026-10-01 08:05:00+07'
WHERE order_id = 1001;
~~~~

Kết quả dòng tiền:

| line_id | order_id | quantity | unit_price | discount_amount | net_amount |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 201 | 1001 | 2 | 100000.00 | 10000.00 | 190000.00 |
| 202 | 1001 | 1 | 20000.00 | 0.00 | 20000.00 |
| 203 | 1002 | 1 | 100000.00 | 100000.00 | 0.00 |

**Đơn 1001 có tổng 210000.00 VND**, còn đơn 1002 là DRAFT có dòng được giảm 100%. Số tiền dòng 203 bằng 0 là **hợp lệ theo chính sách giảm giá giả định**. Nếu nghiệp vụ cấm giảm toàn bộ giá cho một số sản phẩm, đó là một invariant khác chưa được đưa vào ví dụ.

### 5.4. Kiểm tra dữ liệu hợp lệ sau khi lưu

~~~~sql
SELECT
    o.order_id,
    o.status,
    COUNT(l.line_id) AS line_count,
    COALESCE(SUM(l.net_amount), 0) AS total_vnd
FROM validation_lab.sales_order AS o
LEFT JOIN validation_lab.order_line AS l
    ON l.order_id = o.order_id
GROUP BY o.order_id, o.status
ORDER BY o.order_id;
-- 1001: CONFIRMED, 2 dòng, 210000.00
-- 1002: DRAFT,     1 dòng,      0.00
~~~~

Đây là **test dương**: bộ dữ liệu tuân thủ các bất biến phải được nhận và phép tính tiền ra đúng. Nếu chỉ thực hiện test âm mà không có test dương ở **biên hợp lệ**, một CHECK viết quá chặt cũng có thể được báo là “hoạt động” vì từ chối tất cả.

## 6. Kiểm thử âm: mong đợi database từ chối dữ liệu sai

### 6.1. Vì sao nên xác minh mã lỗi?

Một test âm chỉ kiểm tra “câu INSERT có lỗi” có thể đánh lừa người kiểm thử: câu lệnh có thể lỗi **vì sai tên cột hoặc mất kết nối**, chứ không phải do invariant mong muốn được bảo vệ.

PostgreSQL có **SQLSTATE** thường gặp:

| SQLSTATE | Ý nghĩa thường gặp |
| --- | --- |
| **23502** | NOT NULL violation |
| **23503** | FOREIGN KEY violation |
| **23505** | UNIQUE violation |
| **23514** | CHECK violation |

Nếu muốn kiểm tra đúng ràng buộc cụ thể, có thể bổ sung **constraint name** khi bắt lỗi. Test âm nên yêu cầu **một lỗi có nghĩa xác định**, không chấp nhận mọi exception.

### 6.2. Helper thử lỗi trong môi trường học tập

Hàm dưới đây nhận một **câu SQL tin cậy do người viết test cung cấp**, thực hiện nó trong một PL/pgSQL exception block (subtransaction), rồi xác nhận SQLSTATE đúng kỳ vọng. Nếu câu SQL **thành công không đúng kỳ vọng**, hàm cố ý báo lỗi. Nếu câu SQL thất bại vì nguyên nhân khác, hàm cũng báo lỗi.

~~~~sql
CREATE OR REPLACE FUNCTION validation_lab.expect_failure(
    p_statement TEXT,
    p_expected_sqlstate TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_actual_sqlstate TEXT;
BEGIN
    BEGIN
        EXECUTE p_statement;
        RAISE EXCEPTION 'Expected statement to fail but it succeeded';
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            v_actual_sqlstate = RETURNED_SQLSTATE;

        IF v_actual_sqlstate IS DISTINCT FROM p_expected_sqlstate THEN
            RAISE EXCEPTION
                'Expected SQLSTATE %, observed %',
                p_expected_sqlstate, v_actual_sqlstate;
        END IF;
    END;

    RETURN 'PASS';
END;
$$;
~~~~

**Lưu ý an toàn và phạm vi:** Helper dùng **EXECUTE động** nên chỉ dùng trong database thử nghiệm với SQL cố định do người kiểm thử kiểm soát. **Không** nhận câu SQL từ HTTP/API hoặc người dùng không tin cậy. Nó kiểm tra **SQLSTATE**, chưa xác minh tên constraint; hệ thống test nghiêm ngặt nên khẳng định thêm tên constraint hoặc truy vấn dữ liệu sau khi xử lý.

Khi một INSERT thất bại trong exception block, thay đổi của câu SQL ấy được hoàn tác trong subtransaction, không làm bẩn fixture. Nếu nó **thành công bất ngờ**, ngoại lệ do helper phát ra cũng khiến thay đổi trong block bị hoàn tác và test thất bại theo mã lỗi khác kỳ vọng.

### 6.3. Các trường hợp không hợp lệ theo từng loại ràng buộc

**Quantity = 0 — CHECK phải từ chối (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.order_line
        (line_id, order_id, line_no, product_id, quantity,
         unit_price, discount_amount)
     VALUES (901, 1001, 9, 101, 0, 100000, 0)',
    '23514'
);
~~~~

**Quantity = 1001 — vượt biên trên (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.order_line
        (line_id, order_id, line_no, product_id, quantity,
         unit_price, discount_amount)
     VALUES (902, 1001, 9, 101, 1001, 100000, 0)',
    '23514'
);
~~~~

**Quantity NULL — NOT NULL phải từ chối (23502):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.order_line
        (line_id, order_id, line_no, product_id, quantity,
         unit_price, discount_amount)
     VALUES (903, 1001, 9, 101, NULL, 100000, 0)',
    '23502'
);
~~~~

**Chiết khấu âm — CHECK (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.order_line
        (line_id, order_id, line_no, product_id, quantity,
         unit_price, discount_amount)
     VALUES (904, 1001, 9, 101, 2, 100000, -0.01)',
    '23514'
);
~~~~

**Chiết khấu vượt tổng tiền 0.01 — CHECK (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.order_line
        (line_id, order_id, line_no, product_id, quantity,
         unit_price, discount_amount)
     VALUES (905, 1001, 9, 101, 2, 100000, 200000.01)',
    '23514'
);
~~~~

**order_id không tồn tại — FOREIGN KEY (23503):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.order_line
        (line_id, order_id, line_no, product_id, quantity,
         unit_price, discount_amount)
     VALUES (906, 9999, 1, 101, 1, 100000, 0)',
    '23503'
);
~~~~

**Lặp line_no trong cùng đơn — UNIQUE (23505):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.order_line
        (line_id, order_id, line_no, product_id, quantity,
         unit_price, discount_amount)
     VALUES (907, 1001, 1, 101, 1, 100000, 0)',
    '23505'
);
~~~~

**Khách không có liên hệ — CHECK (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.customer
        (customer_id, email, phone)
     VALUES (901, NULL, NULL)',
    '23514'
);
~~~~

**Email chỉ có khoảng trắng — CHECK (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.customer
        (customer_id, email, phone)
     VALUES (902, ''   '', ''0900000000'')',
    '23514'
);
~~~~

**Email trùng khi không phân biệt chữ hoa/thường — UNIQUE index (23505):**

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.customer
        (customer_id, email, phone)
     VALUES (903, ''AN@example.org'', NULL)',
    '23505'
);
~~~~

**Trạng thái không thuộc miền — CHECK (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'UPDATE validation_lab.sales_order
     SET status = ''PAID''
     WHERE order_id = 1002',
    '23514'
);
~~~~

**Trạng thái CONFIRMED thiếu thời điểm — CHECK (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'UPDATE validation_lab.sales_order
     SET status = ''CONFIRMED'', confirmed_at = NULL
     WHERE order_id = 1002',
    '23514'
);
~~~~

**Thời điểm CONFIRMED trước ngày tạo đơn — CHECK (23514):**

~~~~sql
SELECT validation_lab.expect_failure(
    'UPDATE validation_lab.sales_order
     SET status = ''CONFIRMED'',
         confirmed_at = TIMESTAMPTZ ''2026-09-30 10:00:00+07''
     WHERE order_id = 1002',
    '23514'
);
~~~~

Những câu test âm này phải trả **PASS**. Nếu một phép thử trả lỗi về tên bảng/cột sai hoặc một ràng buộc khác, không được đánh dấu là kiểm chứng đã đạt chỉ vì hệ thống phát sinh exception.

### 6.4. Test dương ở biên hợp lệ

Thử lượng bán ở biên trên và mức giảm tối đa, rồi ROLLBACK để giữ fixture:

~~~~sql
BEGIN;

INSERT INTO validation_lab.order_line
    (line_id, order_id, line_no, product_id, quantity,
     unit_price, discount_amount)
VALUES
    (950, 1002, 2, 101, 1000, 100000.00, 100000000.00);

SELECT line_id, quantity, discount_amount, net_amount
FROM validation_lab.order_line
WHERE line_id = 950;
-- quantity=1000, discount_amount=100000000.00, net_amount=0.00

ROLLBACK;
~~~~

Một cơ chế kiểm tra quá chặt, chẳng hạn quantity < 1000 hoặc discount_amount < quantity × unit_price, sẽ **bị test dương ở biên phát hiện**. Đừng chỉ đo khả năng từ chối; phải chứng minh các giá trị hợp lệ sát biên cũng được chấp nhận.

### 6.5. Bộ dữ liệu kiểm thử không được tự mâu thuẫn

Nếu một test muốn kiểm tra FK mồ côi nhưng đồng thời tạo quantity = 0, câu INSERT có thể thất bại vì CHECK trước hoặc theo thứ tự đánh giá thực tế không được bảo đảm. Khi đó test **không chứng minh FK**.

Nguyên tắc xây dữ liệu âm:

1. Giữ **mọi điều kiện khác hợp lệ**.
2. Chỉ làm sai **một quy tắc mục tiêu**.
3. Xác nhận **SQLSTATE/constraint** phù hợp.
4. Nếu cần kiểm tra nhiều invariant cùng lúc, viết **test riêng cho từng mục tiêu** và thêm các bài thử tích hợp.
5. Kiểm tra dữ liệu sau test để chắc không có tác dụng phụ ngoài mong đợi.

## 7. Ma trận kiểm chứng bất biến: từ bảng sang hành vi

| Bất biến | Trường hợp hợp lệ | Trường hợp biên/sai | Cơ chế bảo vệ |
| --- | --- | --- | --- |
| quantity [1,1000] | 1, 1000 | 0, 1001, NULL | NOT NULL + CHECK |
| unit_price ≥ 0 | 0.00 | -0.01, NULL | NOT NULL + CHECK |
| discount trong tổng tiền | 0, bằng tổng | âm, vượt tổng 0.01 | CHECK trên các cột NOT NULL |
| Một phương thức liên hệ | email hoặc phone | cả hai NULL, rỗng hoặc chỉ khoảng trắng | CHECK + validation |
| Email không trùng theo chuẩn hóa | email khác nhau | khác chữ hoa/thường nhưng cùng email | UNIQUE index theo chuẩn hóa |
| Dòng có đơn và sản phẩm | khóa tồn tại | khóa không tồn tại, NULL | NOT NULL + FK |
| line_no duy nhất trong đơn | line 1 của hai đơn | hai line 1 trong cùng đơn | UNIQUE(order_id,line_no) |
| status thuộc tập cho phép | DRAFT, CONFIRMED, CANCELLED | PAID, chuỗi rỗng, NULL | NOT NULL + CHECK |
| confirmed_at ≥ created_at | bằng hoặc sau | trước created_at | CHECK |
| CONFIRMED phải có ít nhất một dòng | đơn có 1 hoặc nhiều dòng | đơn 0 dòng | Quy tắc giao dịch + bảo vệ quan hệ nhiều hàng |
| Cấm cập nhật dòng đã chốt | sửa đơn DRAFT | sửa dòng của CONFIRMED | Domain transition + DB write control/trigger khi cần |
| Không giữ quá số tồn | available ≥ request | available < request, hai request đồng thời | Transaction atomic/conditional update |
| Không chồng lấn lịch sử | khoảng kề nhau | khoảng overlap cùng business key | Exclusion/constraint phù hợp + test thời gian |

**Ma trận không thay thế test thực tế.** Nó là bản đồ từ **định nghĩa nghiệp vụ → trường hợp phản chứng → cơ chế và bằng chứng**. Mỗi hàng cần được hiện thực thành test hoặc phép kiểm tra với tên rõ, dữ liệu chuẩn bị và kỳ vọng có thể quan sát.

## 8. Trạng thái không hợp lệ: kiểm tra đường đi chứ không chỉ giá trị hiện tại

### 8.1. Tập trạng thái hợp lệ khác tập chuyển trạng thái hợp lệ

Trong ví dụ, order.status thuộc ba giá trị:

~~~~text
DRAFT
CONFIRMED
CANCELLED
~~~~

Nhưng điều đó **không chứng minh** mọi phép chuyển giữa ba giá trị đều hợp lệ. Một chính sách nghiệp vụ minh họa:

~~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> CONFIRMED: Có ít nhất một dòng hợp lệ
    DRAFT --> CANCELLED: Hủy đơn nháp
    CONFIRMED --> CANCELLED: Quy trình hủy đã duyệt
    CONFIRMED --> CONFIRMED: Retry idempotent, không đổi dữ liệu
    CANCELLED --> [*]
~~~~

Theo chính sách này:

- **DRAFT → CONFIRMED:** hợp lệ khi các điều kiện xác nhận đạt.
- **DRAFT → CANCELLED:** hợp lệ.
- **CONFIRMED → CANCELLED:** chỉ theo quy trình hủy được phê duyệt.
- **CONFIRMED → DRAFT:** không hợp lệ.
- **CANCELLED → CONFIRMED:** không hợp lệ nếu đã hủy cuối cùng.
- **CANCELLED → DRAFT:** không hợp lệ.

CHECK(status IN (...)) chỉ thấy **giá trị cuối** nên không biết đường chuyển trước đó. Một lần UPDATE từ CONFIRMED về DRAFT vẫn có thể thỏa CHECK nếu mốc confirmed_at và các cột khác cũng được chỉnh cho phù hợp.

### 8.2. Phản ví dụ: CHECK vẫn cho một lần chuyển sai

Thử trong transaction rồi ROLLBACK:

~~~~sql
BEGIN;

-- Đơn 1001 đang CONFIRMED từ fixture.
UPDATE validation_lab.sales_order
SET status = 'DRAFT',
    confirmed_at = NULL
WHERE order_id = 1001;

SELECT order_id, status, confirmed_at
FROM validation_lab.sales_order
WHERE order_id = 1001;
-- DRAFT, NULL: được DDL chấp nhận nhưng sai state transition policy.

ROLLBACK;
~~~~

Kết quả này không nói PostgreSQL sai. Nó chứng minh **mô hình ràng buộc hiện tại chưa mã hóa đầy đủ invariant chuyển trạng thái**. Thiết kế cần thêm đường ghi được kiểm soát (domain service/transaction), kiểm tra phiên bản, hoặc trigger/constraint tương ứng nếu phải chặn mọi writer tại DB.

### 8.3. Phản ví dụ: đơn CONFIRMED không có dòng

Ta có thể tạo một đơn không có dòng rồi chuyển CONFIRMED:

~~~~sql
BEGIN;

INSERT INTO validation_lab.sales_order
    (order_id, customer_id, status, created_at, confirmed_at)
VALUES
    (1099, 1, 'DRAFT',
     TIMESTAMPTZ '2026-10-02 10:00:00+07', NULL);

UPDATE validation_lab.sales_order
SET status = 'CONFIRMED',
    confirmed_at = TIMESTAMPTZ '2026-10-02 10:01:00+07'
WHERE order_id = 1099;

SELECT
    o.order_id,
    o.status,
    COUNT(l.line_id) AS line_count
FROM validation_lab.sales_order AS o
LEFT JOIN validation_lab.order_line AS l
    ON l.order_id = o.order_id
WHERE o.order_id = 1099
GROUP BY o.order_id, o.status;
-- CONFIRMED, line_count = 0: sai invariant nghiệp vụ.

ROLLBACK;
~~~~

**Vì sao FK không chặn?** FK của order_line.order_id trả lời “nếu có dòng thì đơn cha có tồn tại không?”. Nó **không** trả lời “đơn cha có ít nhất một dòng không?”. Để bảo vệ quan hệ ngược, cần ranh giới giao dịch/quy tắc nhiều hàng phù hợp.

### 8.4. Kiểm tra xác nhận qua API/transaction

Một đường chuyển trạng thái có thể thực hiện:

~~~~text
ConfirmOrder(orderId):
  1. Xác thực quyền và orderId.
  2. Khóa/điều phối truy cập cùng đơn.
  3. Yêu cầu trạng thái hiện tại là DRAFT.
  4. Kiểm tra có ít nhất một dòng hợp lệ.
  5. Kiểm tra các điều kiện khác (giá chốt, tiền tệ, nghiệp vụ).
  6. Ghi CONFIRMED và confirmed_at trong giao dịch.
  7. Commit hoặc rollback toàn bộ.
~~~~

SQL minh họa **một phần** điều kiện:

~~~~sql
-- Chạy trong transaction được điều phối cùng các writer của order_line.
UPDATE validation_lab.sales_order AS o
SET status = 'CONFIRMED',
    confirmed_at = CURRENT_TIMESTAMP
WHERE o.order_id = 1002
  AND o.status = 'DRAFT'
  AND EXISTS (
      SELECT 1
      FROM validation_lab.order_line AS l
      WHERE l.order_id = o.order_id
  )
RETURNING o.order_id, o.status;
~~~~

**Đây chưa phải giải pháp chống mọi race condition.** Trong hệ thống có nhiều transaction, một luồng khác có thể xóa dòng cuối hoặc sửa giá sau kiểm tra. Muốn bảo vệ lâu dài, tất cả đường **thêm/sửa/xóa dòng và chuyển trạng thái** phải được điều phối qua cùng quy tắc khóa và trạng thái, hoặc dùng cơ chế DB phù hợp như trigger kiểm tra parent, khóa hàng, constraint trigger có chiến lược đồng thời. Chỉ có EXISTS trong một lệnh **không tự ràng buộc sự tồn tại của dòng mãi mãi**.

Trước khi thực sự dùng truy vấn UPDATE ở trên, fixture test nên đặt trong transaction rồi ROLLBACK hoặc trên database thử được reset, để tránh thay đổi trạng thái của order 1002 cho các test sau.

### 8.5. Các trường hợp trạng thái cần thử

| Trạng thái trước | Hành động | Điều kiện | Kết quả dự kiến |
| --- | --- | --- | --- |
| DRAFT | Confirm | Không có dòng | Từ chối |
| DRAFT | Confirm | Có dòng hợp lệ | Cho phép |
| DRAFT | Cancel | Quyền hợp lệ | Cho phép |
| CONFIRMED | Confirm lặp | Cùng idempotency key | Không tạo xác nhận trùng |
| CONFIRMED | Chuyển về DRAFT | Bất kỳ | Từ chối |
| CONFIRMED | Sửa giá đã chốt | Không có nghiệp vụ điều chỉnh | Từ chối |
| CONFIRMED | Cancel | Theo chính sách hủy | Chấp nhận có điều kiện |
| CANCELLED | Confirm | Không được phục hồi đơn | Từ chối |
| Không có order | Confirm | ID không tồn tại | Không được tạo order mới âm thầm |
| DRAFT | Confirm đồng thời từ hai request | Cùng một đơn | Chỉ có một hiệu ứng chuyển hợp lệ |

## 9. Bất biến thời gian và tính duy nhất qua nhiều phiên bản

### 9.1. Ví dụ SCD2: một khách có nhiều phân khúc theo thời gian

Giả sử báo cáo cần phân khúc khách **tại thời điểm bán**. Một khách có thể thay phân khúc từ Retail sang Business; mô hình giữ phiên bản theo khoảng **[valid_from, valid_to)**.

~~~~sql
CREATE TABLE validation_lab.customer_segment_history (
    segment_key BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES validation_lab.customer(customer_id),
    segment_code TEXT NOT NULL
        CHECK (segment_code IN ('RETAIL', 'BUSINESS')),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    CONSTRAINT ck_segment_valid_interval
        CHECK (valid_to IS NULL OR valid_to > valid_from),
    CONSTRAINT uq_segment_start UNIQUE (customer_id, valid_from)
);

INSERT INTO validation_lab.customer_segment_history
    (segment_key, customer_id, segment_code, valid_from, valid_to)
VALUES
    (501, 1, 'RETAIL',
     TIMESTAMPTZ '2026-01-01 00:00:00+07',
     TIMESTAMPTZ '2026-10-02 00:00:00+07'),
    (502, 1, 'BUSINESS',
     TIMESTAMPTZ '2026-10-02 00:00:00+07',
     NULL);
~~~~

Hai khoảng **kề nhau** mà không chồng lấn. Bản ghi 501 có hiệu lực đến **trước 00:00 ngày 02/10**, còn bản ghi 502 có hiệu lực bắt đầu **đúng 00:00 ngày 02/10**.

### 9.2. Kiểm tra ngay biên thời gian

~~~~sql
-- Tại thời điểm ngay trước chuyển phân khúc:
SELECT segment_key, segment_code
FROM validation_lab.customer_segment_history
WHERE customer_id = 1
  AND valid_from <= TIMESTAMPTZ '2026-10-01 23:59:59+07'
  AND (
      valid_to > TIMESTAMPTZ '2026-10-01 23:59:59+07'
      OR valid_to IS NULL
  );
-- Kỳ vọng 501, RETAIL.

-- Tại đúng mốc chuyển phân khúc:
SELECT segment_key, segment_code
FROM validation_lab.customer_segment_history
WHERE customer_id = 1
  AND valid_from <= TIMESTAMPTZ '2026-10-02 00:00:00+07'
  AND (
      valid_to > TIMESTAMPTZ '2026-10-02 00:00:00+07'
      OR valid_to IS NULL
  );
-- Kỳ vọng 502, BUSINESS, đúng một hàng.
~~~~

Nếu dùng điều kiện **valid_to >= event_time** thay vì **>**, tại mốc chuyển có thể **khớp hai phiên bản** và nhân bản một fact khi JOIN. Đây là lỗi ở **biên thời gian**, khó phát hiện nếu chỉ thử giữa ngày.

### 9.3. UNIQUE(customer_id, valid_from) chưa ngăn chồng lấn

Hai phiên bản có thể có **valid_from khác nhau** nhưng khoảng thời gian chồng lấn:

~~~~text
R1 = [2026-01-01, 2026-10-05)
R2 = [2026-10-02, 2026-11-01)
~~~~

UNIQUE(customer_id,valid_from) chấp nhận hai hàng vì thời điểm bắt đầu khác nhau. Cần kiểm tra:

~~~~sql
SELECT
    a.customer_id,
    a.segment_key AS version_a,
    b.segment_key AS version_b
FROM validation_lab.customer_segment_history AS a
JOIN validation_lab.customer_segment_history AS b
    ON a.customer_id = b.customer_id
   AND a.segment_key < b.segment_key
   AND a.valid_from <
       COALESCE(b.valid_to, 'infinity'::TIMESTAMPTZ)
   AND b.valid_from <
       COALESCE(a.valid_to, 'infinity'::TIMESTAMPTZ);
-- Kỳ vọng 0 cặp chồng lấn.
~~~~

**Bộ dữ liệu hiện tại không có overlap.** Nhưng nếu hai transaction cùng chèn những khoảng khác nhau khi chỉ có kiểm tra SELECT trước INSERT, chúng có thể **cùng đọc “chưa có overlap” rồi cùng commit** ở một số mức cô lập giao dịch nếu không có cơ chế chống ghi đua.

### 9.4. Ràng buộc khoảng thời gian tại database

PostgreSQL có **exclusion constraint** hỗ trợ kiểm tra chồng lấn theo các toán tử phù hợp. Ví dụ minh họa **bổ sung** cho bảng lịch sử trên:

~~~~sql
-- Cần quyền/khả năng bật extension trong database thử nghiệm.
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE validation_lab.customer_segment_history
ADD CONSTRAINT ex_customer_segment_no_overlap
EXCLUDE USING gist (
    customer_id WITH =,
    tstzrange(valid_from, valid_to, '[)') WITH &&
);
~~~~

Ý nghĩa:

- Hai hàng có **cùng customer_id** không được có khoảng thời gian **giao nhau**.
- Khoảng có **đầu bao gồm, cuối không bao gồm**.
- valid_to NULL trong range constructor thể hiện **đầu trên không giới hạn**.
- Nếu chèn chồng lấn, PostgreSQL từ chối bằng **exclusion violation** (SQLSTATE 23P01).

Đây là một lựa chọn cụ thể của PostgreSQL, phụ thuộc hỗ trợ kiểu dữ liệu/toán tử và quyền extension. Trong hệ thống khác, có thể cần trigger, serialization hoặc cơ chế đặc thù để kiểm tra no-overlap. **Một truy vấn SELECT kiểm tra dữ liệu sau khi nạp chỉ phát hiện lỗi; exclusion constraint có thể chặn lỗi ở lúc ghi.**

### 9.5. Không chồng lấn chưa đồng nghĩa không có khoảng trống

Hai khoảng:

~~~~text
[2026-01-01, 2026-10-01)
[2026-10-03, không giới hạn)
~~~~

không chồng lấn nhưng để **trống hai ngày**. Nếu nghiệp vụ yêu cầu tại mỗi thời điểm có đúng một phân khúc, cần kiểm tra **coverage/gap** ngoài no-overlap. Nếu phân khúc có thể không xác định trong một thời kỳ, gap có thể là **hợp lệ**; phải quyết định trước.

Một số quy tắc thời gian khác cần thử:

- valid_to = valid_from (khoảng rỗng) — CHECK từ chối.
- valid_to nhỏ hơn valid_from — CHECK từ chối.
- Hai phiên bản có mốc ranh giới trùng nhau — được phép với khoảng **[from,to)**.
- Hai phiên bản bắt đầu cùng thời điểm — UNIQUE từ chối.
- Hai bản hiện hành với valid_to NULL — exclusion từ chối nếu dùng ràng buộc trên.
- Sự kiện đến muộn phải được gán **phiên bản hiệu lực tại event_time**, không tự động dùng phiên bản hiện hành.

### 9.6. Kiểm chứng đúng thời điểm trong phân tích

Giả sử một đơn bán lúc 23:00 ngày 01/10, nhưng warehouse nhận sự kiện vào 03:00 ngày 02/10. Theo yêu cầu phân khúc tại thời điểm bán:

- **event_time:** ngày 01/10 ⇒ RETAIL.
- **ingestion_time:** ngày 02/10 ⇒ không được dùng làm ngày phân khúc nếu hợp đồng nói theo lúc bán.

Điểm kiểm tra không chỉ là range không chồng lấn, mà còn là **bên nạp dữ liệu chọn đúng thời gian tra cứu**. Một database có FK đến một segment_key hợp lệ vẫn có thể gắn **sai phiên bản** nếu ETL dùng giờ nạp thay vì giờ sự kiện.

## 10. Dữ liệu đồng thời: bất biến đúng trong một luồng chưa chắc đúng khi có hai luồng

### 10.1. Ví dụ giữ tồn kho

Kho có 5 đơn vị, chưa giữ chỗ đơn vị nào. Hai request cùng muốn giữ 4 đơn vị:

~~~~text
T1 đọc available = 5 → nghĩ đủ giữ 4.
T2 đọc available = 5 → cũng nghĩ đủ giữ 4.
T1 cộng reserved_qty += 4.
T2 cộng reserved_qty += 4.
Kết quả sai có thể thành reserved_qty = 8 nếu quy trình không đồng bộ.
~~~~

Nếu chỉ kiểm tra **available ở application trước khi ghi** mà không kiểm tra lại bằng thao tác nguyên tử/transaction, kết quả có thể vượt tồn.

### 10.2. Ràng buộc và cập nhật có điều kiện tại nơi sở hữu

~~~~sql
CREATE TABLE validation_lab.stock (
    product_id BIGINT PRIMARY KEY
        REFERENCES validation_lab.product(product_id),
    on_hand_qty INTEGER NOT NULL CHECK (on_hand_qty >= 0),
    reserved_qty INTEGER NOT NULL CHECK (reserved_qty >= 0),
    CONSTRAINT ck_stock_not_oversold
        CHECK (reserved_qty <= on_hand_qty)
);

INSERT INTO validation_lab.stock
    (product_id, on_hand_qty, reserved_qty)
VALUES (101, 5, 0);
~~~~

Thao tác dành cho **một** yêu cầu giữ 4 đơn vị:

~~~~sql
BEGIN;

UPDATE validation_lab.stock
SET reserved_qty = reserved_qty + 4
WHERE product_id = 101
  AND on_hand_qty - reserved_qty >= 4
RETURNING product_id, on_hand_qty, reserved_qty;

-- Thành công nếu có 1 hàng trả về, nghĩa là đã giữ thêm 4.
-- Không có hàng: không đủ hàng hoặc product_id không tồn tại.

ROLLBACK; -- Giữ nguyên fixture để thử nhiều lần.
~~~~

Khi cập nhật cùng một hàng PostgreSQL, các transaction tương tác qua cơ chế khóa hàng và kiểm tra điều kiện tương ứng theo isolation level. Thao tác **UPDATE có điều kiện trên giá trị hiện tại** và CHECK của DB là các lớp bảo vệ tốt hơn cách “SELECT rồi UPDATE mù” tách rời.

**Cảnh báo:** Một UPDATE đã thành công chưa phải quy trình giữ hàng đầy đủ; cần thêm reservation ID, idempotency key, xử lý retry, release/expiry và phân biệt hàng đã giữ với hàng đã xuất. Nếu tồn kho nằm ở context/database khác, một CHECK trong Sales không bảo vệ tồn Inventory.

### 10.3. Test hai phiên đồng thời

Mục tiêu test là từ stock (on_hand=5, reserved=0) có **hai yêu cầu giữ 4** cùng đến:

| Yêu cầu | Hành động | Kết quả kỳ vọng |
| --- | --- | --- |
| T1 | Conditional UPDATE +4 | Một yêu cầu thành công |
| T2 | Conditional UPDATE +4 | Yêu cầu còn lại không thành công khi điều kiện được đánh giá với trạng thái cập nhật |
| Kiểm tra sau COMMIT | Đọc stock | reserved_qty ≤ 5, không có hai reservation thành công cùng giữ 4 |

**Kết quả chính xác request nào thắng phụ thuộc lịch chạy.** Bất biến cần giữ là **không được commit tổng reserved=8**. Một test chỉ chạy T1 rồi T2 tuần tự không chứng minh hành vi khi có race.

Nên thử thêm:

- Hai request **cùng idempotency key** được retry.
- Hai request khác key, nhưng cùng đơn được gửi lặp.
- Một thao tác release đồng thời với reserve.
- Một thao tác giảm on_hand_qty đồng thời với reserve.
- Transaction timeout hoặc rollback sau khi đã lấy khóa.

Những trường hợp này có thể cần test tích hợp với hai kết nối database và cơ chế orchestrate concurrency, không thể mô phỏng đầy đủ bằng một SELECT đơn.

### 10.4. Write skew và bất biến nhiều hàng

Một quy tắc “luôn có ít nhất một bác sĩ trực” hoặc “mỗi order CONFIRMED có ít nhất một line” dựa trên **tập nhiều hàng** có thể bị phá nếu hai transaction cùng quyết định dựa vào một snapshot cũ.

Ví dụ order CONFIRMED có hai dòng. T1 thấy còn dòng B nên xóa A; T2 thấy còn dòng A nên xóa B. Nếu cả hai không điều phối quyền ghi ở cấp order, kết quả có thể là đơn không còn dòng.

Để bảo vệ:

- Đưa việc sửa tập dòng và chuyển trạng thái về **một aggregate/transaction protocol** có khóa phù hợp.
- Hoặc sử dụng **constraint trigger và cơ chế serialization/locking** được thiết kế để có kết quả đúng dưới concurrency.
- Kiểm thử **hai kết nối thực**, không chỉ kiểm tra từng request đơn lẻ.
- Theo dõi các trường hợp conflict/retry, không bỏ qua lỗi serializable rồi âm thầm báo thành công.

**Không khẳng định chỉ bật SERIALIZABLE là đủ cho mọi triển khai**: ứng dụng phải xử lý **serialization failure và retry giao dịch đúng cách**; ngoại lệ bên ngoài database và tác dụng phụ đã phát ra cũng phải được điều phối.

## 11. Ràng buộc thuộc phạm vi tenant và quan hệ ghép

### 11.1. FK đúng loại chưa chắc FK đúng phạm vi

Một nhân viên thuộc tenant A phải tham chiếu phòng ban cũng thuộc tenant A. Thiết kế sau **có nguy cơ** sai phạm vi nếu chỉ dùng department_id toàn cục:

~~~~text
EMPLOYEE(tenant_id, employee_id, department_id)
DEPARTMENT(tenant_id, department_id)
~~~~

FK chỉ trên department_id (nếu có index/UNIQUE thích hợp) có thể bảo đảm **phòng tồn tại ở đâu đó**, nhưng không bắt buộc phòng thuộc cùng tenant.

### 11.2. Dùng FK ghép để kiểm tra sự phù hợp ngữ cảnh

~~~~sql
CREATE TABLE validation_lab.department (
    tenant_id BIGINT NOT NULL,
    department_id BIGINT NOT NULL,
    department_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, department_id)
);

CREATE TABLE validation_lab.employee (
    tenant_id BIGINT NOT NULL,
    employee_id BIGINT NOT NULL,
    department_id BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, employee_id),
    FOREIGN KEY (tenant_id, department_id)
        REFERENCES validation_lab.department(tenant_id, department_id)
);

INSERT INTO validation_lab.department
    (tenant_id, department_id, department_name)
VALUES
    (10, 7, 'Kế toán A'),
    (20, 8, 'Kế toán B');

INSERT INTO validation_lab.employee
    (tenant_id, employee_id, department_id)
VALUES (10, 100, 7);
~~~~

Kiểm thử âm:

~~~~sql
SELECT validation_lab.expect_failure(
    'INSERT INTO validation_lab.employee
        (tenant_id, employee_id, department_id)
     VALUES (10, 101, 8)',
    '23503'
);
~~~~

Phòng ban (tenant 20, department 8) **có tồn tại**, nhưng không thuộc tenant 10; FK ghép phải từ chối. Đây là ví dụ kiểm tra **bất biến quan hệ theo phạm vi**, không chỉ sự tồn tại của một giá trị khóa.

### 11.3. Kiểm tra cả phần thiếu của khóa ghép

Nếu cho department_id hoặc tenant_id nullable, FK ghép mặc định có thể bỏ qua kiểm tra trong một số trường hợp một thành phần NULL. Trong ví dụ, cả hai đều NOT NULL để bảo đảm tham chiếu đầy đủ.

Nếu phòng ban là **tùy chọn**:

- Cần quyết định khi nào employee có thể chưa thuộc phòng.
- Khi có phòng, phải có **đầy đủ tenant và department_id**.
- Phân biệt “chưa phân phòng” với “được phân phòng thuộc tenant khác”.

Một FK đúng cú pháp không thay thế định nghĩa business key và phạm vi liên kết. **Mã cùng tên hoặc cùng số trong tenant khác không phải cùng đối tượng nghiệp vụ**.

## 12. Kiểm tra ở Java và ở database: hai lớp bảo vệ bổ sung

### 12.1. Bất biến trong value object/domain model

Một object Java có thể từ chối giá trị sai **ngay khi được tạo**, trước khi gọi DB. Ví dụ Java 17+:

~~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record OrderLineInput(
    int quantity,
    BigDecimal unitPrice,
    BigDecimal discountAmount
) {
    public OrderLineInput {
        Objects.requireNonNull(unitPrice, "unitPrice");
        Objects.requireNonNull(discountAmount, "discountAmount");

        if (quantity < 1 || quantity > 1000) {
            throw new IllegalArgumentException(
                "quantity must be between 1 and 1000"
            );
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("negative unitPrice");
        }

        BigDecimal gross = unitPrice.multiply(
            BigDecimal.valueOf(quantity)
        );
        if (discountAmount.signum() < 0
                || discountAmount.compareTo(gross) > 0) {
            throw new IllegalArgumentException("invalid discountAmount");
        }
    }

    public BigDecimal netAmount() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity))
            .subtract(discountAmount);
    }
}
~~~~

Đối tượng này bảo vệ những điều **có thể biết từ các trường trong chính object**, ví dụ quantity, unitPrice và discountAmount. Java có thể kiểm tra khi khởi tạo và giúp lỗi rõ nghĩa hơn một exception từ database.

Tuy nhiên:

- Giá trị từ **script SQL, ETL, tool quản trị hoặc một ứng dụng khác** có thể bỏ qua constructor Java.
- Java object có thể đúng nhưng **FK tham chiếu hàng không tồn tại**.
- Object không biết một order khác đang giữ hàng đồng thời trong database.
- Kiểu BigDecimal không tự giới hạn precision/scale theo NUMERIC(14,2); nếu hợp đồng yêu cầu hai chữ số thập phân, phải có quy tắc kiểm tra/làm tròn nhất quán ở boundary và DB.
- Một đối tượng đúng tại lúc tạo vẫn có thể không đủ điều kiện theo **trạng thái hiện tại** của hệ thống khi COMMIT.

Vì vậy, **domain validation và SQL constraints không thay thế lẫn nhau**. Domain giúp ngăn lỗi sớm, DB bảo vệ trạng thái dữ liệu khỏi mọi đường ghi được phép truy cập, còn ranh giới giao dịch bảo vệ các invariant chịu concurrency.

### 12.2. Test Java tại ngưỡng

Ví dụ với JUnit 5:

~~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;

class OrderLineInputTest {

    @Test
    void acceptsLowerAndUpperQuantityBoundaries() {
        assertDoesNotThrow(() -> new OrderLineInput(
            1, new BigDecimal("0.00"), new BigDecimal("0.00")
        ));
        assertDoesNotThrow(() -> new OrderLineInput(
            1000, new BigDecimal("100.00"),
            new BigDecimal("100000.00")
        ));
    }

    @Test
    void rejectsQuantityImmediatelyOutsideBoundaries() {
        assertThrows(IllegalArgumentException.class, () ->
            new OrderLineInput(0, BigDecimal.ONE, BigDecimal.ZERO));
        assertThrows(IllegalArgumentException.class, () ->
            new OrderLineInput(1001, BigDecimal.ONE, BigDecimal.ZERO));
    }

    @Test
    void rejectsNegativeAndExcessiveDiscount() {
        assertThrows(IllegalArgumentException.class, () ->
            new OrderLineInput(2, new BigDecimal("100.00"),
                new BigDecimal("-0.01")));
        assertThrows(IllegalArgumentException.class, () ->
            new OrderLineInput(2, new BigDecimal("100.00"),
                new BigDecimal("200.01")));
    }

    @Test
    void calculatesExpectedNetAmount() {
        var line = new OrderLineInput(
            2, new BigDecimal("100000.00"),
            new BigDecimal("10000.00")
        );
        assertEquals(0, new BigDecimal("190000.00")
            .compareTo(line.netAmount()));
    }
}
~~~~

**Tại sao compareTo thay vì equals với BigDecimal?** BigDecimal.equals còn xét scale: 1.0 và 1.00 có thể không equals dù bằng nhau về giá trị. Với yêu cầu so **giá trị tiền**, compareTo thường phù hợp; nếu scale là một phần invariant, cần kiểm thử **scale riêng**.

### 12.3. Kiểm thử domain và DB phải cùng phản ánh hợp đồng

Một bẫy:

~~~~text
Java: quantity từ 1 đến 999
Database: quantity từ 1 đến 1000
Nghiệp vụ: quantity từ 1 đến 1000
~~~~

DB chấp nhận quantity = 1000 nhưng API Java từ chối: người dùng gặp lỗi dù dữ liệu về mặt nghiệp vụ hợp lệ. Đó là **drift giữa các lớp kiểm tra**, không phải ưu điểm của việc “validate hai lần”.

Ngược lại, Java cho 1001 nhưng DB từ chối khiến lỗi chỉ phát hiện muộn, có thể phải rollback toàn bộ transaction.

Cần một **bộ trường hợp chuẩn (contract examples)** chạy trên cả domain và DB:

| Dữ liệu | Java | DB |
| --- | --- | --- |
| quantity = 1 | Chấp nhận | Chấp nhận |
| quantity = 1000 | Chấp nhận | Chấp nhận |
| quantity = 0 | Từ chối | Từ chối |
| quantity = 1001 | Từ chối | Từ chối |
| discount bằng gross | Chấp nhận | Chấp nhận |
| discount vượt gross | Từ chối | Từ chối |

Không nhất thiết trùng từng dòng code giữa Java và SQL; phải trùng **ý nghĩa invariant** theo hợp đồng. Những kiểm tra thuộc database như FK và concurrency cần có test riêng tại DB/tích hợp thay vì ép vào record constructor.

### 12.4. PATCH: trường vắng mặt khác trường yêu cầu xóa

Với endpoint cập nhật thông tin liên hệ, các payload có thể có ý nghĩa khác:

~~~~json
{}
~~~~

Thông thường nghĩa là **không thay đổi**. Còn:

~~~~json
{"email": null}
~~~~

có thể nghĩa là **xóa email** theo hợp đồng PATCH. Nếu phone cũng đang NULL, xóa email phải bị **ck_contact_required** từ chối hoặc ứng dụng từ chối sớm. Còn:

~~~~json
{"email": ""}
~~~~

không nên tự được hiểu giống JSON null nếu không có quy tắc; ứng dụng có thể từ chối chuỗi rỗng ngay ở boundary. **Deserializer tự chuyển trường vắng mặt thành null** mà không phân biệt ý định người dùng có thể làm hỏng invariant hoặc xóa dữ liệu ngoài ý muốn.

## 13. Kiểm thử sinh dữ liệu, thuộc tính và biến đổi

### 13.1. Vì sao ví dụ cố định chưa đủ?

Một bảng có nhiều miền dữ liệu: quantity, giá, chiết khấu, trạng thái, customer, sản phẩm, thời gian, tenant. Kiểm thử thủ công vài trường hợp giúp chứng minh quy tắc quan trọng, nhưng khó bao quát các **tổ hợp biên**.

**Property-based testing** sinh nhiều giá trị có kiểm soát, rồi kiểm tra **tính chất luôn phải đúng**. Nó bổ sung cho ví dụ viết tay; không thay thế việc nêu đúng bất biến.

### 13.2. Thuộc tính toán học của dòng bán

Với mọi dòng hợp lệ có quantity q, đơn giá p và chiết khấu d:

\[
1 \le q \le 1000,\qquad p\ge0,\qquad 0\le d\le q\times p
\]

ta phải có:

\[
\text{net}=q\times p-d
\]

và:

\[
0\le\text{net}\le q\times p.
\]

Một bộ sinh dữ liệu có thể:

1. Sinh q từ 1 đến 1000.
2. Sinh p là số thập phân không âm, giới hạn precision/scale theo schema.
3. Tính gross = q × p.
4. Sinh d từ 0 đến gross, cùng đơn vị/scale.
5. Kiểm tra Java object được chấp nhận, net bằng gross − d.
6. Chèn vào DB thử và kiểm tra net_amount, FK và đối soát.

**Chú ý:** Generator phải dùng kiểu thập phân chính xác, tạo tiền tệ nhất quán và hạn chế số trong phạm vi NUMERIC. Nếu sinh d bằng double rồi làm tròn ngẫu nhiên, một số trường hợp lỗi có thể do generator chứ không phải thiết kế.

### 13.3. Sinh trường hợp âm bằng cách phá một invariant

Thay vì chỉ random số vô tội vạ, ta có thể bắt đầu bằng một dòng hợp lệ và **đột biến đúng một điều kiện**:

~~~~text
VALID:
  q = 2, p = 100.00, d = 50.00

MUTATION A:
  q = 0
  → kỳ vọng từ chối vì quantity.

MUTATION B:
  d = -0.01
  → kỳ vọng từ chối vì chiết khấu âm.

MUTATION C:
  d = 200.01
  → kỳ vọng từ chối vì chiết khấu vượt gross.

MUTATION D:
  order_id = mã không tồn tại
  → kỳ vọng FK từ chối.

MUTATION E:
  line_no trùng trong cùng order
  → kỳ vọng UNIQUE từ chối.
~~~~

Mỗi mutation tạo **một nguyên nhân sai cụ thể**, giúp giải thích khi test fail và tránh tình trạng một constraint khác che lỗi mục tiêu.

### 13.4. Metamorphic testing: kiểm tra quan hệ giữa nhiều kết quả

Đôi khi khó biết trước **đáp án chính xác** cho mọi input phức tạp, nhưng có thể kiểm tra một **quan hệ bất biến khi biến đổi dữ liệu**:

- **Tăng chiết khấu thêm Δ**, khi vẫn trong miền hợp lệ, phải làm net giảm đúng Δ.
- **Thêm một dòng bán hợp lệ**, tổng net của đơn tăng đúng net của dòng ấy, nếu các dòng khác không đổi.
- **Đảo thứ tự các dòng**, SUM tiền đơn không được thay đổi.
- **Đổi tên hiển thị sản phẩm**, tổng doanh thu lịch sử giữ nguyên nếu giá chốt là snapshot.
- **Thêm một chiều mô tả 1:1 hợp lệ**, tổng measure sau JOIN không bị nhân đôi.
- **Phát lại cùng eventId** trong consumer có hợp đồng idempotent không làm số reservation tăng thêm.

Ví dụ với net_amount:

\[
\operatorname{net}(q,p,d+\Delta)
=\operatorname{net}(q,p,d)-\Delta
\]

với điều kiện \(0\le d+\Delta\le q\times p\) và không có quy tắc làm tròn bổ sung. Đây là một thuộc tính kiểm tra mạnh hơn việc thử riêng một giá trị cố định.

### 13.5. Model-based testing cho máy trạng thái

Một mô hình trạng thái có thể sinh chuỗi hành động:

~~~~text
CreateDraft
AddLine
Confirm
Cancel
ConfirmAgain
EditConfirmedLine
~~~~

Với mỗi hành động, test engine dựa trên **state machine tham chiếu** để biết:

- Trạng thái dự kiến tiếp theo là gì?
- Hành động có bị từ chối không?
- Có phát sinh tác dụng phụ không?
- Nếu retry cùng request, kết quả có idempotent không?

Điểm mấu chốt là **không chỉ sinh những giá trị status độc lập**. Bất biến chuyển trạng thái cần kiểm tra **chuỗi lịch sử hành động**, chẳng hạn không cho CONFIRMED → DRAFT, hoặc không cho CONFIRM sau CANCELLED.

### 13.6. Shrinking và tái lập lỗi

Khi property test tìm ra một chuỗi dài gây lỗi, một framework có thể **thu nhỏ (shrink)** input thành phản ví dụ dễ hiểu. Ví dụ từ 100 bước thêm/xóa/sửa dòng, lỗi được rút còn:

~~~~text
1. CreateOrder(DRAFT)
2. AddLine(A)
3. AddLine(B)
4. Confirm
5. Transaction T1 deletes A
6. Transaction T2 deletes B
7. Order is still CONFIRMED, no lines remain
~~~~

Hãy lưu **random seed**, phiên bản schema, isolation level và dữ liệu fixture để lỗi có thể tái hiện. Nếu test đồng thời phụ thuộc lịch scheduler, chỉ ghi “test thỉnh thoảng fail” sẽ khó sửa; cần log interleaving hoặc cơ chế kiểm thử điều phối concurrency.

## 14. Kiểm chứng dữ liệu thiếu và trạng thái sai qua ranh giới hệ thống

### 14.1. Một sự kiện hợp lệ về JSON vẫn có thể sai nghiệp vụ

Giả sử Sales nhận sự kiện:

~~~~json
{
  "eventId": "e-1001",
  "eventType": "StockReserved",
  "orderId": "1001",
  "productId": "101",
  "quantity": 2
}
~~~~

JSON có đủ trường và giá trị quantity > 0, nhưng còn nhiều câu hỏi:

- Sự kiện có đến từ **Inventory có thẩm quyền** hay từ một nguồn không được phép?
- Mã productId có đúng **tenant và dòng đơn** không?
- Sự kiện là lần giữ chỗ mới hay **replay** cùng eventId?
- Có phải một event **cũ** đến sau khi đơn đã bị hủy?
- Quantity = 2 có khớp với **số lượng đã yêu cầu giữ** không?
- Có một reservationId và trạng thái hết hạn phù hợp không?

**Schema validation** chỉ kiểm tra hình dạng/type. **Business validation** kiểm tra ngữ nghĩa, quyền sở hữu, trạng thái và thời gian. Hai lớp phải đi cùng nhau, không được coi “JSON hợp schema” là “sự kiện đúng”.

### 14.2. Missing field và evolution contract

Một consumer cũ chỉ biết field customerId. Producer mới thêm tenantId để định danh khách theo tenant. Nếu consumer bỏ tenantId và tiếp tục tra chỉ bằng customerId, nó có thể **gán nhầm dữ liệu giữa các tenant** mà không có lỗi parse.

Bộ test phải bao gồm:

- Payload v1 **thiếu tenantId**: có được phép tiếp tục sử dụng với phạm vi cũ đã định nghĩa không?
- Payload v2 **có tenantId hợp lệ**: mapping phải giữ đúng tenant.
- Payload v2 **tenantId NULL/rỗng**: từ chối theo contract nếu tenant bắt buộc.
- Event đến trễ từ v1 sau cutover: cần adapter hoặc xử lý có kiểm soát.
- Consumer nhận enum mới: không được coi trạng thái không biết là thành công.

Nếu thay đổi ngữ nghĩa quan trọng, cần **versioning và compatibility tests**, không chỉ tăng số version của bảng SQL.

### 14.3. Dữ liệu phân tích: đầy đủ và không đếm trùng

Một fact bán có grain **một hàng mỗi dòng bán**, liên kết DIM_PRODUCT để tổng hợp theo ngành hàng. Bất biến dữ liệu phân tích:

- Mỗi dòng bán hợp lệ xuất hiện **đúng một lần** theo business key đã chốt.
- Không có dòng fact bị mất do tham chiếu dimension thiếu hoặc không đúng phiên bản.
- Một dòng fact không bị JOIN thành hai hàng do dimension SCD2 có khoảng chồng lấn.
- Mọi measure có **đơn vị, thời điểm và tính cộng được** phù hợp.

Test cần so:

~~~~text
Tổng fact sau khi lọc nguồn hợp lệ
   = Tổng theo từng nhóm dimension (nếu phân cấp strict và complete)
   = Tổng doanh thu báo cáo ở cùng tập dữ liệu/thời gian
~~~~

Nếu dimension thuộc nhiều nhóm hoặc có khoản tiền đa tiền tệ, đẳng thức này cần **quy tắc phân bổ/quy đổi**; không được khẳng định SUM luôn bảo toàn khi ngữ nghĩa chưa chốt.

**Kiểm chứng thiết kế phân tích khác với triển khai pipeline:** Ta định nghĩa grain, khóa, invariant và phép đối soát. Scheduler, CDC, backfill, retry và alert là phần hiện thực vận hành, nhưng phải tuân thủ các quy tắc ấy.

### 14.4. Dữ liệu được chuyển qua migration

Khi đổi cột customer_email sang buyer_email:

- **Test dương:** những email cũ đúng ngữ nghĩa vẫn đọc được ở trường mới.
- **Test âm:** dữ liệu sai hoặc không thể suy ra không được tự điền giá trị bịa.
- **Test thiếu:** bản ghi chưa backfill được nhận diện rõ và chưa đưa vào trạng thái “đã chuyển” nếu hợp đồng yêu cầu đầy đủ.
- **Test song song:** writer phiên bản cũ/mới không làm hai trường lệch.
- **Test trạng thái cuối:** cột cũ chỉ bị bỏ khi không còn consumer cần nó và giá trị mới đã được đối soát.

Một migration báo thành công không chứng minh mô hình dữ liệu đích đúng nếu vẫn còn dữ liệu không hợp lệ hoặc writer cũ tiếp tục ghi sai. Vì vậy, **kiểm tra dữ liệu biên và trạng thái trung gian phải thuộc kế hoạch tiến hóa**, không chỉ kế hoạch dựng bảng mới.

## 15. Quy trình xây bộ kiểm chứng thiết kế có khả năng tái lập

### 15.1. Bước 1 — Thu thập yêu cầu và viết điều kiện có thể bác bỏ

Không bắt đầu bằng danh sách “test SQL cho đủ nhiều”. Hãy bắt đầu bằng:

1. Xác định **đối tượng và ý nghĩa của một hàng**.
2. Ghi loại dữ liệu, phạm vi, đơn vị đo, nullability và thời gian.
3. Ghi các quan hệ/khóa, trạng thái chuyển và điều kiện lịch sử.
4. Nêu **một phản ví dụ nhỏ nhất** khiến yêu cầu sai.
5. Nêu **thời điểm** yêu cầu phải đúng: khi object được tạo, lúc COMMIT hay lúc dữ liệu phân tích được công bố.
6. Xác định ai sở hữu quy tắc khi dữ liệu đi qua nhiều bounded context.

Ví dụ: “Khách phải có thông tin liên hệ” cần làm rõ **email hay phone có được không**, chuỗi toàn khoảng trắng có được không, thông tin liên hệ có phải được xác minh chưa, và trường hợp khách không có liên hệ ở dữ liệu lịch sử được xử lý thế nào.

### 15.2. Bước 2 — Phân lớp giá trị và tổ hợp

Đối với mỗi trường:

- Giá trị thông thường hợp lệ.
- Biên hợp lệ thấp/cao.
- Giá trị ngay ngoài biên.
- NULL, trống, chỉ khoảng trắng.
- Sai kiểu hoặc sai format ở API/JSON.
- Giá trị đúng kiểu nhưng **sai ngữ nghĩa** (ví dụ ID của tenant khác).
- Giá trị lặp lại, cũ hoặc không còn hiệu lực.

Đối với mỗi quan hệ:

- Có cha, không có cha, cha thuộc tenant khác.
- Một cha có 0, 1, nhiều con.
- Trùng khóa trong cùng phạm vi hoặc chỉ trùng ở phạm vi khác.
- Một thành viên dimension nằm nhiều nhóm hoặc không có nhóm.

Đối với trạng thái:

- Mỗi bước hợp lệ, mỗi bước bị cấm.
- Retry và cùng lệnh lặp lại.
- Hai thao tác cùng lúc.
- Sự kiện đến trễ hoặc đảo thứ tự.

### 15.3. Bước 3 — Chọn nơi kiểm tra và cơ chế bảo vệ

| Nơi kiểm tra | Thích hợp với | Giới hạn |
| --- | --- | --- |
| **DTO/API boundary** | Kiểu đầu vào, required fields, format, quyền truy cập | Có đường ghi DB khác có thể bỏ qua |
| **Value object/domain** | Bất biến trong một giá trị hoặc aggregate | Không biết dữ liệu hiện tại của context khác |
| **DB CHECK/NOT NULL** | Miền giá trị và biểu thức cùng hàng | Không trực tiếp giữ quy tắc nhiều hàng |
| **DB UNIQUE/PK** | Tính duy nhất theo khóa/phạm vi | Không tự chứng minh danh tính nghiệp vụ đã đúng |
| **DB FK** | Tham chiếu tồn tại trong cùng DB | Không tự kiểm tra đúng tenant nếu khóa thiếu scope; không xác minh dữ liệu ngoài DB |
| **Exclusion/constraint thời gian** | Không chồng lấn các khoảng hiệu lực | Cần DBMS hỗ trợ, vẫn phải kiểm tra gap và quy tắc lịch sử |
| **Transaction/locking** | Bất biến thay đổi theo nhiều row hoặc concurrency | Cần mọi writer theo giao thức, test cạnh tranh và retry |
| **Contract/consumer test** | Ý nghĩa API/event qua các hệ thống | JSON schema hợp lệ không chứng minh nghiệp vụ hợp lệ |
| **Data quality/reconciliation** | Đầy đủ, không trùng, đúng tổng sau transform | Phát hiện sau nạp, không nhất thiết chặn tại thời điểm ghi |

Một bất biến quan trọng có thể được bảo vệ **ở nhiều lớp** vì các lớp xử lý các lỗi khác nhau. Nhưng không nên sao chép quy tắc **không cùng nghĩa**: nếu Java cho 1000 mà DB chỉ cho 999, hệ thống có hai hợp đồng xung đột.

### 15.4. Bước 4 — Chuẩn bị fixture sạch và độc lập

Bộ dữ liệu kiểm thử nên có:

- **Định danh xác định**, dễ đọc và không trùng với fixture khác.
- **Quan hệ cha–con hợp lệ** trước khi thử FK âm.
- **Giá trị trạng thái/thời gian rõ ràng**, không phụ thuộc đồng hồ hệ thống khi không cần.
- Bộ dữ liệu **nhỏ nhưng đại diện cho các lớp quan trọng**.
- Mỗi test có cách **khôi phục trạng thái ban đầu** hoặc chạy trên schema riêng được reset.
- Sự kiện/ID với **phạm vi tenant** tường minh nếu có nhiều tenant.
- Dữ liệu nhạy cảm là **dữ liệu giả**, không sao chép email/địa chỉ/số điện thoại khách thật.

Không cho một test âm sửa fixture khiến test sau thất bại ngẫu nhiên. Trong PostgreSQL, có thể dùng transaction + ROLLBACK hoặc một fixture runner bảo đảm cleanup; những test lỗi dự kiến nên dùng cơ chế **bắt lỗi xác định** thay vì để một transaction bị aborted rồi tiếp tục chạy các câu lệnh khác trong cùng transaction.

### 15.5. Bước 5 — Xác nhận hai chiều: đúng phải qua, sai phải bị chặn

Ta cần tìm cả:

- **False acceptance:** dữ liệu sai được chấp nhận, ví dụ quantity = 0.
- **False rejection:** dữ liệu hợp lệ bị từ chối, ví dụ discount bằng gross khi chương trình miễn phí là hợp lệ.

Chỉ tối ưu “mọi dữ liệu sai đều bị chặn” sẽ dẫn tới ràng buộc quá mạnh, chặn luôn nghiệp vụ đúng. Chỉ tối ưu “tất cả ví dụ đều lưu được” sẽ dẫn tới ràng buộc quá yếu.

### 15.6. Bước 6 — Kiểm thử dưới concurrency và thay đổi

Sau khi test một hàng:

- Thử hai transaction tạo khóa trùng.
- Thử hai request giữ cùng tồn kho.
- Thử hai thao tác chỉnh sửa tập line của cùng đơn.
- Thử writer cũ/mới cùng ghi trong migration.
- Thử event trùng, đến muộn và từ tenant khác.
- Thử SCD2 thay đổi ở đúng thời điểm biên.
- Thử dữ liệu lịch sử không đủ thông tin để backfill.

Một invariant có thể pass **100% test tuần tự** mà vẫn bị phá khi có hai transaction.

### 15.7. Bước 7 — Kiểm tra sau thay đổi và chứng cứ nghiệm thu

Sau khi sửa mô hình:

1. Chạy lại bộ test ở các ngưỡng đã định.
2. Kiểm tra **migration đã áp dụng đúng phạm vi và dữ liệu đích**.
3. Kiểm tra các query/report không bị nhân hàng do thay khóa hoặc phân cấp.
4. Đánh giá hiệu năng khóa, số lần conflict và chi phí ràng buộc mới.
5. Lưu kết quả theo **schema version, build version, fixture version và DB isolation level**.
6. Đánh dấu những invariant **đã bảo vệ tại DB**, **chỉ kiểm tra tại application**, hoặc **mới phát hiện sau nạp**; không gom tất cả thành “PASS database”.

Nếu có lỗ hổng đã biết nhưng được chấp nhận tạm thời, phải ghi **rủi ro, phạm vi, thời hạn và người sở hữu hành động khắc phục**. Không ghi bài kiểm chứng “hoàn toàn thành công” khi còn một invariant cốt lõi không được bảo vệ.

## 16. Checklist nghiệm thu kiểm chứng thiết kế

### 16.1. Kiểm tra yêu cầu và mô hình

- [ ] Mỗi thực thể/quan hệ có định nghĩa **một hàng là gì** và danh tính theo business key.
- [ ] Bất biến được viết thành câu có thể **chấp nhận hoặc bác bỏ** bằng dữ liệu.
- [ ] Các miền số có **biên thấp/cao**, chính sách bao gồm/loại trừ ranh giới và đơn vị.
- [ ] NULL, rỗng, Unknown và Not applicable có ý nghĩa rõ, không trộn lẫn.
- [ ] Các cột bắt buộc dùng **NOT NULL** khi CHECK đơn thuần có thể để UNKNOWN đi qua.
- [ ] Các khóa UNIQUE/FK bao gồm đúng **tenant, source, thời gian hoặc phạm vi** nếu cần.
- [ ] Có ràng buộc hoặc phép kiểm tra **cardinality ngược** khi một cha bắt buộc có con.
- [ ] State machine có đường chuyển hợp lệ và bị cấm, không chỉ danh sách enum.
- [ ] Các mốc lịch sử dùng interval convention rõ (ví dụ [from,to)) và có quy tắc gap/overlap.
- [ ] Các trường tiền và số lượng có **đơn vị, precision/scale, quy tắc làm tròn** được phê duyệt.

### 16.2. Kiểm tra dữ liệu và transaction

- [ ] Có test dương **ngay tại biên** và test âm **ngay ngoài biên**.
- [ ] Có test dữ liệu thiếu qua **SQL NULL, JSON null, missing field, chuỗi rỗng và khoảng trắng**.
- [ ] Có test PK/FK/UNIQUE/CHECK với lỗi mong đợi **đúng loại**, không chấp nhận exception bất kỳ.
- [ ] Có test FK theo phạm vi tenant và khả năng sai danh tính.
- [ ] Có test **0, 1, nhiều bản ghi con** và điều kiện xác nhận một aggregate.
- [ ] Có test chuyển trạng thái, hủy, retry và lỗi xử lý trễ.
- [ ] Có test đồng thời đối với invariant phụ thuộc trạng thái nhiều hàng/tài nguyên.
- [ ] Có test interval bằng mốc bằng đầu/cuối và overlap/gap.
- [ ] Có phép đối soát **công thức và measure** với nguồn/ngữ nghĩa.
- [ ] Có phân biệt invariant **được chặn tại ghi** với vi phạm **chỉ được phát hiện sau ghi**.

### 16.3. Kiểm tra vận hành và thay đổi

- [ ] Fixture có thể reset, chạy lại, không dùng dữ liệu khách thật.
- [ ] Bộ test ghi schema/app/contract version và cấu hình isolation cần thiết.
- [ ] Có test cho phiên bản writer/reader cũ/mới nếu đang chuyển schema.
- [ ] Có test replay/duplicate và dữ liệu đến muộn ở ranh giới tích hợp.
- [ ] Có log/chỉ số cho constraint violation, conflict, deadlock, dữ liệu thiếu và đối soát sai.
- [ ] Có người sở hữu từng invariant và quyết định giải quyết dữ liệu ngoại lệ.
- [ ] Không chạy các lệnh INSERT/UPDATE cố tình sai trong database production.
- [ ] Không tuyên bố kết quả “đã kiểm thử concurrency” nếu chỉ chạy một kết nối tuần tự.
- [ ] Không suy từ “migration chạy xong” thành “mọi dữ liệu mới đúng nghiệp vụ”.

### 16.4. Ma trận nghiệm thu tối thiểu

| Phạm vi | Bằng chứng tối thiểu | Nếu thiếu |
| --- | --- | --- |
| **Single-row invariants** | Test biên dương/âm, SQLSTATE, dữ liệu được commit | Chưa bảo đảm miền giá trị |
| **Reference integrity** | FK có phạm vi đúng, test mồ côi/cross-tenant | Có nguy cơ liên kết sai |
| **State machine** | Test chuỗi hành động hợp lệ/bị cấm | Enum đúng nhưng chuyển trạng thái có thể sai |
| **Temporal integrity** | Test khoảng kề, overlap, gap và event time | Dễ JOIN nhầm phiên bản lịch sử |
| **Concurrent invariants** | Hai transaction thật, hậu điều kiện sau commit | Có thể race/write skew |
| **Integration validity** | Contract tests, replay/late/missing fields | JSON hợp lệ nhưng dữ liệu sai nghĩa |
| **Analytics consistency** | Đối soát fact/grain/dimension/measure | Có thể nhân hoặc mất doanh thu |
| **Schema evolution** | Mixed-version tests, backfill/reconciliation | Trạng thái trung gian chưa an toàn |

**Kết quả kiểm chứng phải có phạm vi:** Ví dụ “CHECK quantity và discount đã đạt 12 bài thử” là một tuyên bố hẹp có bằng chứng. Nó **không** đồng nghĩa “đã xác minh không có race khi ConfirmOrder” nếu chưa có test và cơ chế bảo vệ cho quy tắc ấy.

## 17. Bài tập thực hành có đáp án

### Bài 1 — Giá trị biên của số lượng

Một dòng đơn có quantity nguyên trong đoạn **[1,1000]**.

**Câu hỏi:** Hãy phân loại -1, 0, 1, 2, 999, 1000, 1001 và NULL thành hợp lệ/không hợp lệ.

**Đáp án:** **1, 2, 999, 1000 hợp lệ**; -1, 0 và 1001 nằm ngoài miền; NULL không hợp lệ nếu quantity bắt buộc. Cần test ở **1 và 1000**, không chỉ test các giá trị trung bình. Biên được bao gồm ở cả hai đầu theo ký hiệu [1,1000].

### Bài 2 — CHECK có đủ bảo vệ NULL không?

Bảng có cột quantity INTEGER CHECK (quantity > 0), không có NOT NULL.

**Câu hỏi:** INSERT quantity = NULL có bị CHECK từ chối không? Vì sao?

**Đáp án:** **Không**, vì NULL > 0 cho kết quả **UNKNOWN**, còn CHECK trong PostgreSQL chỉ từ chối khi biểu thức là FALSE. Để bắt buộc quantity có mặt và dương, cần **quantity INTEGER NOT NULL CHECK(quantity > 0)**.

### Bài 3 — Chiết khấu đúng tại biên

Một dòng có quantity = 2, unit_price = 100.00 VND, yêu cầu discount thuộc [0,200.00].

**Câu hỏi:** Các giá trị -0.01, 0, 199.99, 200.00, 200.01 hợp lệ không? Net bằng bao nhiêu khi discount = 200?

**Đáp án:** **0, 199.99 và 200.00 hợp lệ**; -0.01 và 200.01 không hợp lệ. Khi discount = 200.00, net_amount = **0.00 VND**. Không tự cấm giảm 100% khi hợp đồng cho phép hàng miễn phí.

### Bài 4 — Thiếu thông tin liên hệ

Khách hàng phải có ít nhất một email hoặc phone không rỗng sau trim.

**Câu hỏi:** Phân loại bốn trường hợp:

~~~~text
A: email=NULL, phone='0900000000'
B: email='a@example.org', phone=NULL
C: email=NULL, phone=NULL
D: email='   ', phone='0900000000'
~~~~

**Đáp án:** **A và B hợp lệ**. **C** không có phương thức liên hệ. **D** bị từ chối trong mô hình ví dụ vì email có mặt nhưng chỉ là khoảng trắng, vi phạm **ck_email_not_blank**; việc có phone hợp lệ không biến một email rỗng có mặt thành hợp lệ. Nếu nghiệp vụ quyết định trim rồi chuyển email rỗng thành NULL tại API, đó phải là quy tắc công khai và được kiểm thử riêng.

### Bài 5 — UNIQUE và nhiều NULL

Một bảng có email TEXT UNIQUE nhưng cho NULL. Hai người không dùng email đều lưu NULL.

**Câu hỏi:** Hai hàng có được chấp nhận trong PostgreSQL mặc định không? Có phải lỗi dữ liệu?

**Đáp án:** **Được chấp nhận** theo UNIQUE mặc định. Chưa thể gọi là lỗi nếu nghiệp vụ cho phép nhiều người không có email. Nếu muốn không cho NULL, dùng NOT NULL; nếu cần quy tắc coi NULL là trùng, phải chọn cơ chế phù hợp **và xác nhận ngữ nghĩa**, không tùy ý siết ràng buộc.

### Bài 6 — Kiểm tra email không phân biệt chữ hoa/thường

Bảng có unique index trên LOWER(BTRIM(email)). Đã có an@example.org.

**Câu hỏi:** INSERT AN@example.org có được chấp nhận không? Vì sao UNIQUE(email) thông thường chưa chắc đủ?

**Đáp án:** Index chuẩn hóa phải từ chối vì **LOWER('AN@example.org')** trùng với email đã lưu. UNIQUE trên chuỗi gốc thường phân biệt các giá trị khác chữ hoa/thường. Tuy nhiên, cách chuẩn hóa địa chỉ email là **quy tắc nghiệp vụ/kỹ thuật cần chốt**, không mặc định áp mọi chính sách normalization phức tạp.

### Bài 7 — Quan hệ một chiều của FK

ORDER_LINE.order_id có FK đến SALES_ORDER.order_id. Một order DRAFT chưa có dòng nào.

**Câu hỏi:** Có vi phạm FK không? Nếu chuyển đơn ấy thành CONFIRMED, FK có tự ngăn không?

**Đáp án:** **Không vi phạm FK** khi đơn chưa có dòng. FK từ child tới parent chỉ bảo đảm **nếu child tồn tại thì parent phải tồn tại**. Nó không bảo đảm parent có ít nhất một child. Muốn chặn CONFIRMED không có dòng, phải kiểm tra **bất biến nhiều hàng** trong đường chuyển trạng thái hoặc cơ chế DB bổ sung.

### Bài 8 — Mã lỗi test âm

Một test mong đợi FK từ chối order_id = 9999, nhưng SQL chạy lỗi vì tên cột order_ids không tồn tại.

**Câu hỏi:** Có nên đánh dấu PASS vì câu INSERT lỗi?

**Đáp án:** **Không.** Lỗi không chứng minh FK được bảo vệ. Phải xác nhận SQLSTATE **23503** (và khi cần tên constraint) thay vì chấp nhận mọi exception. Bộ test phải giữ các điều kiện khác hợp lệ để chỉ vi phạm quy tắc mục tiêu.

### Bài 9 — Trạng thái hợp lệ nhưng chuyển trạng thái sai

Một đơn đang CONFIRMED. SQL đổi status thành DRAFT và confirmed_at thành NULL. Cả hai giá trị đáp ứng CHECK trên hàng.

**Câu hỏi:** Vì sao vẫn có thể là lỗi nghiệp vụ?

**Đáp án:** Vì quy tắc state machine ví dụ **không cho CONFIRMED → DRAFT**. CHECK trạng thái chỉ kiểm tra **giá trị đích** chứ không biết đường chuyển. Cần dịch vụ chuyển trạng thái, trigger hoặc cơ chế ghi có kiểm soát để bảo vệ lịch sử chuyển.

### Bài 10 — Hai request cùng xác nhận một đơn

Hai request ConfirmOrder cùng chạy cho order DRAFT có một dòng.

**Câu hỏi:** Ngoài việc status cuối cùng là CONFIRMED, còn phải kiểm chứng gì?

**Đáp án:** Phải bảo đảm **không có hai tác dụng phụ** như thu tiền hai lần hoặc phát hai command giữ hàng không có idempotency. Kiểm tra điều kiện chuyển/phiên bản, giao dịch cạnh tranh, idempotency key, kết quả request thứ hai và sự kiện đã phát. Một trường status cuối đúng **không chứng minh quy trình không lặp tác dụng phụ**.

### Bài 11 — Ranh giới khoảng thời gian SCD2

Phiên bản khách:

~~~~text
R1: [2026-01-01 00:00, 2026-10-02 00:00)
R2: [2026-10-02 00:00, không giới hạn)
~~~~

**Câu hỏi:** Một sự kiện xảy ra đúng 00:00 ngày 02/10 thuộc phiên bản nào? Nếu dùng valid_to >= event_time, nguy cơ gì?

**Đáp án:** Thuộc **R2**, vì đầu được bao gồm và cuối bị loại. Dùng valid_to >= event_time có thể khiến R1 cũng khớp đúng thời điểm kết thúc, gây **hai bản ghi được JOIN** cho một sự kiện.

### Bài 12 — UNIQUE không chặn overlap

Hai phiên bản của cùng khách bắt đầu ngày 01/10 và 03/10, nhưng phiên bản đầu hết hiệu lực ngày 05/10.

**Câu hỏi:** UNIQUE(customer_id, valid_from) có phát hiện chồng lấn không? Cần gì thêm?

**Đáp án:** **Không**, vì valid_from khác nhau. Cần invariant **không chồng lấn khoảng hiệu lực**, có thể dùng PostgreSQL exclusion constraint với range hoặc cơ chế khóa/trigger phù hợp, cùng test concurrent insert. Cũng cần quyết định có chấp nhận **gap** hay không, vì no-overlap không bảo đảm bao phủ thời gian.

### Bài 13 — Ngày sự kiện và ngày nạp

Khách đổi phân khúc lúc 00:00 ngày 02/10. Đơn được bán lúc 23:00 ngày 01/10, nhưng sự kiện vào warehouse lúc 03:00 ngày 02/10.

**Câu hỏi:** Nếu KPI cần phân khúc tại thời điểm bán, dùng phiên bản nào?

**Đáp án:** Phiên bản có hiệu lực **lúc 23:00 ngày 01/10**, không phải lúc sự kiện được xử lý. Phải tra khoảng theo **event_time**. FK đến một version tồn tại chưa bảo đảm version đó là phiên bản đúng theo thời điểm giao dịch.

### Bài 14 — Hai giao dịch cùng giữ hàng

Stock có on_hand_qty = 5 và reserved_qty = 0. Hai request cùng đặt giữ 4.

**Câu hỏi:** Có được commit cả hai lần giữ không? Cách kiểm tra an toàn hơn SELECT rồi UPDATE mù?

**Đáp án:** **Không** nếu cả hai đều yêu cầu 4 đơn vị cùng lúc và chưa có hàng giải phóng/nhập thêm. Cần thao tác **UPDATE có điều kiện trên lượng khả dụng hiện tại** trong transaction và ràng buộc reserved_qty ≤ on_hand_qty; test bằng **hai kết nối cạnh tranh**. Kết quả hợp lệ là tối đa một lần giữ 4 thành công, nếu không có thay đổi stock khác.

### Bài 15 — Write skew trên tập dòng đơn

Order CONFIRMED có hai dòng A và B. Transaction T1 thấy B nên xóa A; transaction T2 thấy A nên xóa B.

**Câu hỏi:** Nếu cả hai commit, bất biến nào bị phá? Chỉ có FK còn đủ không?

**Đáp án:** Order CONFIRMED có thể còn **0 dòng**, phá quy tắc ít nhất một dòng. FK child → parent không chặn xóa dòng cuối. Cần điều phối các thao tác sửa/xóa và chuyển trạng thái qua **cùng giao thức khóa/transaction** hoặc cơ chế DB phù hợp, kiểm thử concurrency và xử lý serialization conflict nếu dùng isolation mạnh.

### Bài 16 — FK đúng đối tượng nhưng sai tenant

Department(tenant=20,id=8) tồn tại, Employee(tenant=10,id=101) tham chiếu department_id=8.

**Câu hỏi:** Vì sao FK chỉ theo department_id không đủ? Thiết kế nào chặn được?

**Đáp án:** Nó có thể chỉ chứng minh department_id=8 **tồn tại ở một tenant nào đó**. Nếu nghiệp vụ cấm liên kết xuyên tenant, FK phải mang phạm vi: **FOREIGN KEY(tenant_id, department_id) REFERENCES department(tenant_id,department_id)**, kết hợp NOT NULL cho các thành phần bắt buộc.

### Bài 17 — API PATCH và ý định xóa dữ liệu

Khách chỉ có email, phone NULL. API PATCH nhận {"email": null} để xóa email.

**Câu hỏi:** Cần kiểm tra gì? Payload {} có cùng nghĩa không?

**Đáp án:** Sau khi xóa email, khách sẽ **không còn phương thức liên hệ**, vi phạm quy tắc trong bài. API nên từ chối sớm hoặc database CHECK từ chối khi ghi. Payload **{}** thường được định nghĩa là **không thay đổi**, khác với yêu cầu xóa email; nếu framework biến cả hai thành null như nhau, phải thiết kế cách phân biệt ý định của người dùng.

### Bài 18 — Metamorphic test cho doanh thu

Một dòng hợp lệ có q=2, p=100.00, d=30.00, net=170.00. Tăng discount thêm 20.00 trong phạm vi hợp lệ.

**Câu hỏi:** Net phải thay đổi thế nào? Đây là loại test gì?

**Đáp án:** Net mới = **150.00**, giảm đúng **20.00**. Đây là **metamorphic/property test**, kiểm tra một quan hệ giữa hai kết quả thay vì chỉ so một đầu ra với hằng số; nó đòi hỏi không có quy tắc làm tròn bổ sung làm thay đổi phép tính.

### Bài 19 — Dữ liệu phân tích bị nhân sau JOIN

Fact sales có một dòng doanh thu 100.000 VND của P01. DIM_PRODUCT SCD2 có hai phiên bản cùng product_id=P01. Báo cáo JOIN bằng product_id mà không xét thời gian.

**Câu hỏi:** Tổng doanh thu có nguy cơ gì? Kiểm tra nào phát hiện?

**Đáp án:** Một dòng fact có thể JOIN thành **hai dòng**, khiến tổng thành **200.000 VND**. Phải dùng **product_key của phiên bản đã chọn** hoặc tra đúng khoảng hiệu lực; kiểm tra đếm số dòng sau JOIN và **đối soát tổng fact với tổng báo cáo** dưới cùng các giả định grain và measure additive.

### Bài 20 — Đã thêm NOT NULL nghĩa là dữ liệu lịch sử đúng?

Một migration đổi cột địa chỉ không có cấu trúc thành province_code NOT NULL bằng cách đặt mọi hàng không xác định thành mã “01”. Migration chạy thành công, không còn NULL.

**Câu hỏi:** Có thể coi mô hình mới đã được kiểm chứng không?

**Đáp án:** **Không**. NOT NULL chỉ bảo đảm cột có giá trị, không chứng minh **mã 01 là tỉnh đúng**. Cần đối soát với nguồn đáng tin, phân biệt trạng thái unknown/unresolved và chỉ áp giá trị mặc định nếu có ý nghĩa nghiệp vụ. Test phải kiểm tra **ngữ nghĩa và nguồn**, không chỉ hình dạng.

### Bài 21 — Test âm vô tình sai hai quy tắc

Một INSERT thử FK mồ côi dùng order_id=9999, nhưng quantity=0. Hệ thống báo CHECK violation.

**Câu hỏi:** Test FK có đạt không?

**Đáp án:** **Chưa.** Câu SQL thất bại do quantity sai trước khi chứng minh FK được bảo vệ. Cần dùng quantity hợp lệ và mọi trường khác hợp lệ, chỉ đặt **order_id không tồn tại**, rồi kiểm tra SQLSTATE 23503 hoặc tên FK mong đợi.

### Bài 22 — Bản ghi xuất hiện hai lần trong luồng event

Consumer nhận lại cùng StockReserved(eventId=e1) sau retry và cộng reserved_qty thêm lần nữa.

**Câu hỏi:** Đây là lỗi về kiểu dữ liệu hay bất biến nào?

**Đáp án:** Đây là lỗi **idempotency/định danh sự kiện**, không phải lỗi SQL type. Consumer phải lưu dấu event đã xử lý và gắn cập nhật tài nguyên với transaction phù hợp; ngoài eventId còn có thể cần **business request ID** để chống hai thông điệp khác ID nhưng cùng yêu cầu nghiệp vụ.

### Bài 23 — Trường hợp biên có phải luôn bị từ chối?

Một product có giá 0.00 VND do chương trình tặng kèm; lượng bán 1. Bộ test mặc định từ chối mọi unit_price=0 vì cho rằng bán hàng luôn phải có tiền.

**Câu hỏi:** Test này đúng hay sai?

**Đáp án:** **Sai trong hợp đồng của bài**, vì unit_price ≥ 0 nên **0 là biên hợp lệ**. Một test âm chỉ có ích khi quy tắc nghiệp vụ thực sự cấm giá 0. Nếu một loại đơn riêng phải có giá dương, hãy thêm invariant có điều kiện đúng theo loại đơn, không áp sai cho mọi dòng.

### Bài 24 — Kiểm thử ở DB và domain có thể mâu thuẫn

Java yêu cầu quantity < 1000, còn SQL cho quantity BETWEEN 1 AND 1000. Yêu cầu nghiệp vụ là [1,1000].

**Câu hỏi:** Dữ liệu quantity=1000 sẽ có kết quả nào và làm sao sửa?

**Đáp án:** Java từ chối dù DB chấp nhận; đây là **false rejection** ở application. Hãy đồng bộ quy tắc Java thành quantity ≤ 1000 và chạy chung bộ **boundary contract tests** ở hai lớp.

### Bài 25 — Chỉ một CHECK có chặn được mọi sai lệch không?

Nhóm thiết kế có các CHECK quantity, discount và status đúng; từ đó kết luận không cần kiểm thử transaction, FK, event hay dữ liệu lịch sử.

**Câu hỏi:** Kết luận đó sai ở đâu?

**Đáp án:** CHECK trong một hàng bảo vệ **một nhóm điều kiện nhất định**, không tự bảo vệ FK, quan hệ nhiều hàng, chuyển trạng thái, concurrency, phiên bản SCD2 hoặc tính đúng của sự kiện liên hệ thống. Phải chọn **cơ chế tương ứng với phạm vi invariant** và kiểm tra bằng test phản chứng, không đánh giá toàn bộ mô hình qua một loại constraint.

### Bài 26 — Viết kế hoạch kiểm chứng tổng hợp

Một dự án bổ sung trạng thái CONFIRMED, phân khúc khách SCD2 và kho giữ hàng. Trưởng nhóm yêu cầu “một danh sách test chứng minh thiết kế tốt”.

**Câu hỏi:** Nêu ít nhất sáu nhóm test cần có, cùng kết quả kỳ vọng chính.

**Đáp án tham khảo:**

1. **Giá trị biên:** quantity=1/1000 được nhận, 0/1001 bị từ chối; chiết khấu âm/vượt tiền bị từ chối.
2. **NULL/missing:** khách thiếu email và phone bị từ chối; email NULL với phone hợp lệ được nhận.
3. **Khóa/quan hệ:** line trỏ order/product không tồn tại bị FK từ chối; line_no trùng cùng order bị UNIQUE từ chối.
4. **Trạng thái:** ConfirmOrder không có line bị từ chối; Confirm từ DRAFT đủ điều kiện được nhận; CONFIRMED → DRAFT bị từ chối.
5. **SCD2:** hai khoảng kề nhau được nhận; overlap cùng customer bị từ chối; event đúng tại valid_to chỉ khớp phiên bản mới.
6. **Đồng thời:** hai request giữ vượt tồn không thể cùng commit thành công; không để confirmed order mất dòng cuối.
7. **Tích hợp:** event trùng được xử lý idempotent; sự kiện đến trễ không cập nhật lùi trạng thái và không gắn sai phân khúc.
8. **Đối soát phân tích:** tổng fact theo grain đúng bằng báo cáo sau JOIN với dimension conformed trong phạm vi được phép cộng.
9. **Tiến hóa:** writer cũ/mới và dữ liệu chưa backfill được xử lý theo hợp đồng; constraint mới không được siết trước thời điểm đủ điều kiện.

Một kết quả kiểm chứng đáng tin cậy cần ghi **test nào đã chạy, dữ liệu nào, kỳ vọng nào, mã phiên bản nào và rủi ro còn tồn tại**.

## 18. Tổng kết

| Khái niệm | Điều cần ghi nhớ |
| --- | --- |
| **Invariant** | Điều kiện dữ liệu phải đúng tại ranh giới nghiệp vụ/giao dịch đã xác định |
| **Boundary value analysis** | Thử ngay dưới, đúng tại và ngay trên ngưỡng; không chỉ giá trị bình thường |
| **Positive test** | Dữ liệu hợp lệ, đặc biệt tại biên, phải được chấp nhận |
| **Negative test** | Dữ liệu sai phải bị từ chối với **đúng nguyên nhân**, không chỉ có exception |
| **NULL/UNKNOWN** | CHECK có thể cho UNKNOWN đi qua; NOT NULL là ràng buộc khác |
| **Empty/whitespace** | Chuỗi rỗng và chỉ khoảng trắng không giống SQL NULL |
| **UNIQUE** | Bảo vệ tính duy nhất theo khóa/phạm vi; NULL có hành vi riêng |
| **FK** | Bảo vệ tham chiếu child → parent; không chứng minh cha có con hay cùng tenant nếu thiếu scope |
| **State machine** | Phải kiểm tra **đường chuyển**, không chỉ miền status |
| **Temporal invariant** | Interval boundaries, overlap/gap, event time và phiên bản hiệu lực |
| **Concurrency** | Invariant nhiều hàng cần transaction/locking hoặc cơ chế DB thích hợp |
| **Business key** | Cần đúng định danh và phạm vi tenant/source/time, không chỉ cùng kiểu ID |
| **Domain validation** | Từ chối giá trị sai sớm, nhưng không thay thế DB constraints |
| **Property-based testing** | Sinh nhiều input để kiểm tra tính chất tổng quát |
| **Metamorphic testing** | Kiểm tra quan hệ giữa các kết quả khi thay đổi đầu vào có kiểm soát |
| **Model-based testing** | Kiểm tra chuỗi hành động và quy tắc chuyển trạng thái |
| **Data quality/reconciliation** | Phát hiện thiếu, trùng, sai ngữ nghĩa sau tích hợp/nạp |
| **Design acceptance** | Ghi rõ phạm vi, bằng chứng và những invariant chưa được bảo vệ |

**Kết luận:** Một mô hình dữ liệu được kiểm chứng không chỉ là mô hình tạo bảng và lưu được các ví dụ đẹp. Cần **chủ động thử phá bất biến** bằng giá trị ngay ngoài biên, NULL và trường thiếu, mã tham chiếu không tồn tại, trạng thái chuyển sai, khoảng thời gian chồng lấn và các giao dịch đồng thời. Mỗi phản ví dụ phải gắn với **kết quả mong đợi và cơ chế bảo vệ cụ thể**; đồng thời phải chứng minh dữ liệu hợp lệ tại biên vẫn được chấp nhận. Kết hợp **validation tại Java, ràng buộc SQL, giao dịch, kiểm thử hợp đồng và đối soát dữ liệu** giúp thiết kế có thể giải thích, tiến hóa và bảo vệ được trước những điều kiện thực tế khó hơn bộ dữ liệu mẫu.

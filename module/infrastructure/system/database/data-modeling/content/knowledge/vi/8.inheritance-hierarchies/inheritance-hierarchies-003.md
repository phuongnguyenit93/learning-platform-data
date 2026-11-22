# Chuyên biệt hóa toàn phần hoặc một phần

Trong mô hình hóa dữ liệu, **chuyên biệt hóa (specialization)** là việc biểu diễn một nhóm thực thể chung (*supertype*, kiểu cha) qua các nhóm chi tiết hơn (*subtype*, kiểu con). Một câu hỏi nghiệp vụ rất quan trọng là:

> Có bắt buộc **mọi** thực thể của kiểu cha phải thuộc **ít nhất một** kiểu con được liệt kê hay không?

- **Chuyên biệt hóa toàn phần (total specialization):** mọi thực thể của kiểu cha phải thuộc **ít nhất một** kiểu con.
- **Chuyên biệt hóa một phần (partial specialization):** thực thể của kiểu cha **được phép không thuộc** kiểu con nào trong nhóm.

Quyết định này chi phối khả năng lưu trạng thái chưa phân loại, thiết kế khóa và ràng buộc, quá trình nhập dữ liệu, thao tác cập nhật và cách tiến hóa lược đồ. Trong phạm vi module **DATABASE_DATA_MODELING**, mục tiêu không dừng ở vẽ mô hình ER: cần chuyển yêu cầu thành ràng buộc có thể kiểm chứng trong hệ quan hệ, document, đồ thị hoặc phân tích mà vẫn dễ mở rộng.

## 1. Trực giác nghiệp vụ: “phải có một loại” hay “có thể chưa có loại”?

### Ví dụ 1: Thanh toán đã hoàn tất — toàn phần

Giả sử hệ thống chỉ chấp nhận hai hình thức **thanh toán đã hoàn tất**:

- **CardPayment:** thanh toán bằng thẻ.
- **BankTransferPayment:** thanh toán chuyển khoản.

Theo chính sách này, **mỗi thanh toán đã hoàn tất** phải thuộc CardPayment hoặc BankTransferPayment. Không thể có thanh toán đã hoàn tất mà không biết nó được thực hiện theo một trong hai hình thức đã định nghĩa. Đây là **chuyên biệt hóa toàn phần**.

Điều kiện “đã hoàn tất” rất quan trọng: một yêu cầu thanh toán vừa tạo có thể chưa chọn phương thức. Nếu kiểu cha đại diện cho **mọi yêu cầu thanh toán, bao gồm bản nháp**, quy tắc toàn phần có thể không còn đúng.

### Ví dụ 2: Nhân viên và chức danh đặc thù — một phần

Một hệ thống nhân sự quản lý tất cả nhân viên (**Employee**), trong đó chỉ một số người là:

- **Manager:** có quyền phê duyệt ngân sách nhóm.
- **SalesRepresentative:** có chỉ tiêu doanh số.

Nhân viên kỹ thuật hoặc nhân viên vận hành có thể **không** thuộc hai nhóm này. Điều đó hợp lệ và không có nghĩa bản ghi bị thiếu dữ liệu. Nhóm phân loại Manager/SalesRepresentative là **chuyên biệt hóa một phần**.

Một người có thể đồng thời là Manager và SalesRepresentative hay không là câu hỏi **khác**, liên quan đến tính loại trừ/chồng lấp; nó không tự quyết định tính toàn phần/một phần.

| Câu hỏi | Thanh toán đã hoàn tất | Nhân viên |
| --- | --- | --- |
| Kiểu cha | Payment | Employee |
| Kiểu con đang xét | CardPayment, BankTransferPayment | Manager, SalesRepresentative |
| Có thực thể cha không thuộc kiểu con nào không? | Không | Có, ví dụ nhân viên kỹ thuật |
| Quy tắc bao phủ | **Toàn phần** | **Một phần** |
| Điều cần hệ thống kiểm soát | Mỗi Payment phải có ít nhất một loại hợp lệ | Employee không có hai vai trò vẫn hợp lệ |

Điểm cốt lõi: **toàn phần** là yêu cầu *bắt buộc phân loại*, còn **một phần** là *cho phép tồn tại thực thể cha độc lập với các kiểu con đang xét*.

## 2. Phát biểu bằng tập hợp và quy tắc tham gia

Gọi **S** là tập thực thể của kiểu cha; **T₁, T₂, …, Tₙ** là các tập thực thể của kiểu con. Mọi kiểu con đều là tập con của S.

- **Toàn phần:** **S = T₁ ∪ T₂ ∪ … ∪ Tₙ**. Mọi phần tử thuộc S đều nằm trong ít nhất một tập kiểu con.
- **Một phần:** **T₁ ∪ T₂ ∪ … ∪ Tₙ ⊆ S** và mô hình **cho phép** có phần tử thuộc S nằm ngoài hợp của các kiểu con. Tại một thời điểm cụ thể, dữ liệu vẫn có thể tình cờ không có phần tử nằm ngoài đó.

Diễn đạt dưới dạng lực lượng thành viên, đặt **k(x)** là số kiểu con trong nhóm mà một thực thể x thuộc vào:

- **Toàn phần:** k(x) ≥ 1 với mọi x thuộc S.
- **Một phần:** k(x) ≥ 0; giá trị 0 được phép.

Lưu ý: ở đây chỉ xét **một nhóm chuyên biệt hóa xác định**. Một thực thể có thể tham gia nhóm chuyên biệt hóa A theo quy tắc toàn phần và đồng thời tham gia nhóm chuyên biệt hóa B theo quy tắc một phần. Không có nghĩa mọi kiểu con trong toàn hệ thống đều phải áp dụng cùng một quy tắc.

### Tính bao phủ khác với tính loại trừ/chồng lấp

**Toàn phần/một phần** quy định **số lượng tối thiểu** kiểu con. **Loại trừ nhau/chồng lấp** (*disjoint/overlapping*) quy định khả năng **đồng thời thuộc nhiều kiểu con**.

| Bao phủ | Tính kết hợp | Số kiểu con hợp lệ cho mỗi thực thể cha | Trạng thái không có kiểu con |
| --- | --- | --- | --- |
| Toàn phần | Loại trừ nhau | **Đúng 1** | Cấm |
| Một phần | Loại trừ nhau | **0 hoặc 1** | Cho phép |
| Toàn phần | Chồng lấp | **Ít nhất 1** | Cấm |
| Một phần | Chồng lấp | **0, 1 hoặc nhiều** | Cho phép |

Ví dụ một tài khoản **bắt buộc** là Buyer hoặc Seller nhưng **được phép đồng thời có cả hai** thì thuộc trường hợp **toàn phần + chồng lấp**. Một nhân viên chỉ được giữ tối đa một trong hai chức danh đặc thù nhưng cũng có thể không giữ chức danh nào là **một phần + loại trừ nhau**.

Trong sơ đồ **EER (Enhanced Entity–Relationship)**, tính toàn phần thường biểu diễn bằng **đường nối đôi** từ kiểu cha đến nút chuyên biệt hóa; tính một phần bằng **đường nối đơn**. Nút chuyên biệt hóa có thể ghi **d** (disjoint) hoặc **o** (overlapping). Ký pháp khác nhau giữa các công cụ, nên tài liệu mô hình luôn cần ghi rõ quy tắc bằng lời.

## 3. Xác định đúng tính toàn phần từ yêu cầu

Trước khi tạo bảng, hãy hỏi:

1. **Kiểu cha đại diện cho thực thể nào?** Là giao dịch đã xác nhận, yêu cầu giao dịch, tài khoản đang hoạt động hay tất cả tài khoản? Thay đổi phạm vi có thể thay đổi ràng buộc.
2. **Có trường hợp hợp lệ nào chưa thuộc kiểu con nào không?** Nếu có, chuyên biệt hóa phải cho phép trạng thái đó, hoặc phải tách rõ trạng thái dự thảo khỏi trạng thái chính thức.
3. **Danh sách kiểu con đã đầy đủ theo chính sách nghiệp vụ chưa?** Nếu còn loại không được mô hình hóa, khẳng định toàn phần có thể làm mất dữ liệu hoặc buộc nhãn sai.
4. **Một thực thể chỉ tạm thời chưa được phân loại hay vĩnh viễn không cần phân loại?** Hai tình huống có thể cần cùng biểu diễn ban đầu nhưng cơ chế kiểm tra thời hạn khác nhau.
5. **Ràng buộc bắt đầu có hiệu lực khi nào?** Từ lúc tạo bản ghi, khi kích hoạt, khi phê duyệt, khi thanh toán thành công hay từ một ngày hiệu lực cụ thể?
6. **Làm sao kiểm chứng trạng thái 0 kiểu con?** Phải có phép truy vấn hoặc ràng buộc cho ra kết quả đúng với chính sách.

Một phát biểu nghiệp vụ tốt có điều kiện, phạm vi và thời điểm:

> “Mọi payment có trạng thái COMPLETED phải có ít nhất một phương thức CardPayment hoặc BankTransferPayment hợp lệ. Payment còn ở trạng thái DRAFT được phép chưa có phương thức.”

Phát biểu này diễn đạt **tính toàn phần có điều kiện**, thường sát nghiệp vụ hơn một mệnh đề “mọi payment đều phải có kiểu con” không phân biệt vòng đời.

**Cẩn thận với loại OTHER:** tạo thêm một kiểu con Other chỉ để tránh bản ghi chưa phân loại có thể che khuất sai sót nghiệp vụ. Other chỉ là kiểu con hợp lệ nếu nghiệp vụ thực sự định nghĩa và chấp nhận loại đó, với ý nghĩa, dữ liệu và quy tắc xử lý rõ ràng.

## 4. Ánh xạ vào một bảng quan hệ

Một bảng cho cả kiểu cha và các kiểu con (*single-table inheritance*) thường là cách trực tiếp nhất để biểu diễn **toàn phần + loại trừ nhau**.

### 4.1. Toàn phần + loại trừ nhau: cột phân loại bắt buộc

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE completed_payments (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    amount     NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    method     TEXT NOT NULL
               CHECK (method IN ('CARD', 'BANK_TRANSFER')),
    card_token TEXT,
    transfer_reference TEXT,
    CONSTRAINT payment_details_match_method CHECK (
        (method = 'CARD'
            AND card_token IS NOT NULL
            AND transfer_reference IS NULL)
        OR
        (method = 'BANK_TRANSFER'
            AND transfer_reference IS NOT NULL
            AND card_token IS NULL)
    )
);
~~~

Ràng buộc **NOT NULL** trên method cùng với **CHECK** danh sách giá trị khiến mỗi payment có **ít nhất một** loại. Một cột method chỉ nhận một giá trị cũng đồng thời làm các loại **loại trừ nhau**. Ràng buộc thứ hai ngăn dữ liệu riêng của kiểu con bị ghi nhầm sang loại khác.

~~~sql
-- Hợp lệ: thuộc đúng một loại với dữ liệu riêng phù hợp.
INSERT INTO completed_payments
    (amount, method, transfer_reference)
VALUES
    (125000, 'BANK_TRANSFER', 'BANK-2026-001');

-- Không hợp lệ: payment hoàn tất chưa có phương thức.
INSERT INTO completed_payments (amount)
VALUES (125000);

-- Không hợp lệ: kiểu CARD nhưng có dữ liệu chuyển khoản.
INSERT INTO completed_payments
    (amount, method, transfer_reference)
VALUES
    (125000, 'CARD', 'BANK-2026-002');
~~~

Lưu ý trong PostgreSQL, một biểu thức **CHECK** bị vi phạm khi trả về **FALSE**, nhưng **UNKNOWN/NULL** được chấp nhận. Vì vậy **NOT NULL** và kiểm tra **IS NULL / IS NOT NULL** phải được định nghĩa rõ ràng; không nên dựa vào một phép so sánh với NULL để kiểm soát tính toàn phần.

### 4.2. Một phần + loại trừ nhau: cột phân loại có thể rỗng

Giả sử ta mô hình hóa nhóm vai trò đặc thù Manager/SalesRepresentative, trong đó nhân viên được phép không thuộc vai trò nào và, theo **giả định riêng của ví dụ này**, không thể đồng thời có cả hai:

~~~sql
CREATE TABLE employees (
    employee_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name TEXT NOT NULL,
    special_role TEXT
                 CHECK (special_role IN ('MANAGER', 'SALES_REP')),
    approval_limit NUMERIC(14, 2),
    sales_region   TEXT,
    CONSTRAINT employee_role_details CHECK (
        (special_role IS NULL
            AND approval_limit IS NULL
            AND sales_region IS NULL)
        OR
        (special_role = 'MANAGER'
            AND approval_limit IS NOT NULL
            AND approval_limit >= 0
            AND sales_region IS NULL)
        OR
        (special_role = 'SALES_REP'
            AND approval_limit IS NULL
            AND sales_region IS NOT NULL)
    )
);
~~~

~~~sql
-- Nhân viên không thuộc hai kiểu con vẫn hợp lệ.
INSERT INTO employees (display_name)
VALUES ('Lan - Ky su van hanh');

-- Nhân viên có vai trò Manager.
INSERT INTO employees
    (display_name, special_role, approval_limit)
VALUES
    ('Minh - Quan ly', 'MANAGER', 50000000);
~~~

Ở đây, **special_role IS NULL** thể hiện “không thuộc một trong các kiểu con đang xét”. Nó **không nhất thiết có nghĩa dữ liệu chưa biết hoặc nhập thiếu**. Cần phân biệt ba ý nghĩa có thể tồn tại trong nghiệp vụ: **không áp dụng**, **chưa biết**, và **chưa xác định**. Nếu hệ thống cần phân biệt, không nên gộp cả ba vào một NULL duy nhất; có thể thêm trạng thái phân loại rõ ràng.

Một cột phân loại đơn chỉ phù hợp với nhóm **loại trừ nhau**. Nếu nhân viên được phép vừa là Manager vừa là SalesRepresentative, phải đổi cách biểu diễn để lưu được hai vai trò cùng lúc.

### 4.3. Toàn phần chỉ ở trạng thái nghiệp vụ nhất định

Đối với thực thể có vòng đời, có thể cho phép chưa phân loại khi còn bản nháp nhưng bắt buộc phân loại khi kích hoạt:

~~~sql
CREATE TABLE payment_requests (
    request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    state      TEXT NOT NULL
               CHECK (state IN ('DRAFT', 'COMPLETED')),
    method     TEXT
               CHECK (method IN ('CARD', 'BANK_TRANSFER')),
    CONSTRAINT completed_needs_method CHECK (
        state <> 'COMPLETED' OR method IS NOT NULL
    )
);
~~~

Lúc tạo DRAFT, method có thể NULL. Trước khi chuyển sang COMPLETED, cơ sở dữ liệu yêu cầu method khác NULL. Để kiểm soát *toàn bộ* quy tắc thanh toán, còn phải thêm các ràng buộc về số tiền, dữ liệu riêng phương thức và chuyển trạng thái; ví dụ trên cố ý chỉ minh họa **điểm bắt đầu của tính toàn phần**.

## 5. Ánh xạ bảng cha – bảng con: dễ biểu diễn một phần, khó cưỡng chế toàn phần

Mỗi kiểu con được lưu trong bảng riêng, dùng khóa chính đồng thời là khóa ngoại tới bảng cha (*class-table inheritance*). Ví dụ nhóm nhân viên đặc thù **một phần + có thể chồng lấp**:

~~~sql
CREATE TABLE staff (
    staff_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name     TEXT NOT NULL
);

CREATE TABLE staff_managers (
    staff_id       BIGINT PRIMARY KEY
                   REFERENCES staff(staff_id) ON DELETE CASCADE,
    approval_limit NUMERIC(14, 2) NOT NULL
                   CHECK (approval_limit >= 0)
);

CREATE TABLE staff_sales_reps (
    staff_id     BIGINT PRIMARY KEY
                 REFERENCES staff(staff_id) ON DELETE CASCADE,
    sales_region TEXT NOT NULL
);
~~~

Cấu trúc trên cho phép:

- Một staff tồn tại **không có** dòng ở hai bảng con → hợp lệ với **một phần**.
- Một staff có dòng ở **một** bảng con → hợp lệ.
- Một staff có dòng ở **cả hai** bảng con → hợp lệ với giả định **chồng lấp**.
- Không có dòng bảng con nào tham chiếu tới staff không tồn tại → khóa ngoại kiểm soát.

Khóa chính staff_id trong từng bảng con bảo đảm một nhân viên có tối đa một hồ sơ thuộc cùng một kiểu con.

### 5.1. Vì sao khóa ngoại thông thường không đủ cho toàn phần?

Giả sử hai bảng con là card_payments và bank_transfer_payments cùng tham chiếu tới bảng payments.

~~~sql
-- Chẩn đoán dữ liệu vi phạm tính toàn phần.
SELECT p.payment_id
FROM payments AS p
WHERE NOT EXISTS (
    SELECT 1 FROM card_payments AS c
    WHERE c.payment_id = p.payment_id
)
AND NOT EXISTS (
    SELECT 1 FROM bank_transfer_payments AS b
    WHERE b.payment_id = p.payment_id
);
~~~

Truy vấn tìm **các payment cha không có bất cứ bản ghi kiểu con nào**. Khóa ngoại từ bảng con sang bảng cha chỉ kiểm tra **con phải có cha**; nó **không** kiểm tra chiều ngược lại **cha phải có con**.

Đây cũng là lý do không thể biến truy vấn NOT EXISTS xuyên bảng thành một **CHECK đơn giản trên một hàng** trong PostgreSQL. Khi tính toàn phần là yêu cầu cứng, cần chủ động chọn cơ chế:

1. **Đổi cấu trúc để ràng buộc nằm trên một hàng**, như bảng completed_payments với method NOT NULL và các trường riêng có CHECK. Đây thường là phương án dễ duy trì cho phân cấp nhỏ, loại trừ nhau.
2. **Ghi cha và con trong một giao dịch**, đồng thời có cơ chế ràng buộc kiểm tra trạng thái khi giao dịch hoàn tất. Trong PostgreSQL có thể dùng **constraint trigger có thể trì hoãn (DEFERRABLE)** khi nghiệp vụ cần kiểm tra xuyên bảng; thiết kế trigger phải xét cả thêm, sửa, xóa, và các thao tác đồng thời.
3. **Dùng cấu trúc khóa ngoại hỗ trợ từ cả hai phía** hoặc cơ chế khác bảo đảm tổng số bản ghi con tối thiểu một, với cách xử lý khóa vòng và ghi dữ liệu được xác định rõ. Đây là thiết kế phức tạp, cần đánh giá cho từng hệ quản trị.
4. **Định nghĩa bảng cha như một tập hợp dẫn xuất (VIEW)** từ các bảng loại cụ thể khi phù hợp, thay vì cho phép tạo một bản ghi cha độc lập. Cần xử lý định danh chung, khóa ngoại tới thực thể tổng quát và cập nhật qua view; phép UNION đơn thuần không tự bảo đảm mọi ràng buộc.

Việc ứng dụng “luôn cố gắng ghi cả cha và con” có thể đáp ứng đường đi thông thường nhưng **chưa phải ràng buộc dữ liệu hoàn chỉnh**, vì script nhập dữ liệu, job nền hoặc hệ thống khác vẫn có thể ghi cha mà thiếu con.

### 5.2. Kiểm soát sửa/xóa và giao dịch đồng thời

Ngay cả khi sau một lần INSERT dữ liệu hợp lệ, việc **xóa bản ghi con cuối cùng** có thể phá vỡ tính toàn phần. Cần kiểm tra không chỉ khi tạo cha mà còn khi cập nhật kiểu, chuyển loại, xóa kiểu con và đổi trạng thái.

Nếu kiểm tra xuyên bảng chỉ bằng thao tác “đọc rồi ghi” không có cơ chế đồng bộ, hai giao dịch đồng thời có thể quan sát trạng thái khác thực tế sau commit. Cần xem xét khóa thích hợp ở bản ghi cha, ràng buộc được quản lý ở tầng dữ liệu và thời điểm kiểm tra cuối giao dịch. Không nên mặc định rằng một trigger kiểm tra tồn tại thông thường đã giải quyết mọi trường hợp đua tranh.

## 6. Toàn phần + chồng lấp: bắt buộc ít nhất một, được phép nhiều

Trường hợp này dễ bị nhầm thành “phải đúng một loại”. Ví dụ, mọi thành viên của một nền tảng phải có ít nhất một tư cách **BUYER** hoặc **SELLER**, nhưng một người có thể giữ cả hai.

Nếu chỉ có vài vai trò ổn định, có thể biểu diễn trong một bảng để kiểm soát ràng buộc **ít nhất một**:

~~~sql
CREATE TABLE platform_members (
    member_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email     TEXT NOT NULL UNIQUE,
    is_buyer  BOOLEAN NOT NULL DEFAULT FALSE,
    is_seller BOOLEAN NOT NULL DEFAULT FALSE,
    buyer_tier TEXT,
    shop_name  TEXT,
    CONSTRAINT at_least_one_membership CHECK (
        is_buyer OR is_seller
    ),
    CONSTRAINT buyer_data_consistent CHECK (
        (is_buyer AND buyer_tier IS NOT NULL)
        OR
        (NOT is_buyer AND buyer_tier IS NULL)
    ),
    CONSTRAINT seller_data_consistent CHECK (
        (is_seller AND shop_name IS NOT NULL)
        OR
        (NOT is_seller AND shop_name IS NULL)
    )
);
~~~

~~~sql
-- Hợp lệ: người này tham gia cả hai tư cách.
INSERT INTO platform_members
    (email, is_buyer, is_seller, buyer_tier, shop_name)
VALUES
    ('member@example.test', TRUE, TRUE, 'SILVER', 'Member Shop');

-- Bị từ chối vì không có tư cách nào.
INSERT INTO platform_members (email)
VALUES ('unclassified@example.test');
~~~

Ưu điểm: kiểm tra tối thiểu một vai trò nằm trong một hàng nên biểu thức CHECK hoạt động trực tiếp. Nhược điểm: thêm một kiểu con mới có thể buộc thêm cột, mở rộng CHECK và thay đổi các truy vấn liên quan; bảng cũng có thể trở nên cồng kềnh khi vai trò có nhiều dữ liệu riêng.

Nếu vai trò có thể tăng hoặc có tập thuộc tính riêng lớn, **bảng member_roles** hay các **bảng hồ sơ con** phù hợp hơn để lưu dữ liệu chồng lấp. Tuy nhiên, với mô hình nhiều bảng, vẫn cần một giải pháp độc lập để cưỡng chế **ít nhất một** vai trò. Ràng buộc UNIQUE hoặc khóa chính ghép (member_id, role_code) chỉ ngăn **trùng một vai trò**, không tự bảo đảm **tồn tại một vai trò**.

### Một phần + chồng lấp

Đây là biến thể ngược lại: có thể có 0, 1 hoặc nhiều tư cách. Trong mô hình vai trò, chỉ cần một bảng cha và bảng liên kết member_roles với khóa chính ghép; người dùng mới chưa có vai trò vẫn được giữ hợp lệ. Khi nghiệp vụ có yêu cầu chuyển từ **PENDING** sang **ACTIVE**, có thể áp dụng quy tắc toàn phần riêng cho trạng thái ACTIVE, thay vì áp cho toàn bộ vòng đời.

## 7. Quy tắc toàn phần trong hệ phân cấp nhiều tầng

Một hệ thống có thể phân cấp theo nhiều lớp:

~~~text
Asset (Tài sản)
├── TangibleAsset (Tài sản hữu hình)
│   ├── Vehicle (Phương tiện)
│   └── Building (Tòa nhà)
└── IntangibleAsset (Tài sản vô hình)
~~~

Có thể phát biểu:

- Mọi **Asset** phải là **TangibleAsset** hoặc **IntangibleAsset** → chuyên biệt hóa từ Asset là **toàn phần**.
- Một **TangibleAsset** có thể không phải **Vehicle** hay **Building** (ví dụ máy móc) → chuyên biệt hóa từ TangibleAsset là **một phần**.

Hai mệnh đề không mâu thuẫn. Tính toàn phần **phải được xét tại từng điểm chuyên biệt hóa** và dựa trên tập kiểu con **trực tiếp** của điểm đó.

Nếu muốn “mọi tài sản hữu hình phải là Vehicle hoặc Building”, phải xác nhận rằng máy móc, thiết bị và các tài sản hữu hình khác đã được mô hình hóa theo chính sách. Không thể suy luận từ việc nhánh cha Asset là toàn phần rằng mọi nhánh cấp dưới cũng toàn phần.

Một thực thể cũng có thể tham gia nhiều cách phân loại song song, chẳng hạn Asset theo **bản chất tài sản** và Asset theo **mục đích sử dụng**. Phải xác định toàn phần/một phần **cho từng nhóm** thay vì áp một thuộc tính toàn phần chung lên cả thực thể.

## 8. Quan hệ với chuẩn hóa, khóa và chỉ mục

Ràng buộc bao phủ và chuẩn hóa giải quyết hai vấn đề khác nhau:

- **Chuẩn hóa:** đặt thuộc tính đúng theo phụ thuộc hàm, hạn chế dư thừa và bất thường cập nhật.
- **Tính toàn phần/một phần:** quy định tập trạng thái hợp lệ, đặc biệt có cho phép hàng kiểu cha không mang thông tin kiểu con hay không.

Một lược đồ có thể được chuẩn hóa tốt với các bảng cha–con riêng mà vẫn **vi phạm yêu cầu toàn phần** vì thiếu kiểm tra tồn tại ở bảng con. Ngược lại, một bảng duy nhất có discriminator NOT NULL có thể kiểm soát toàn phần nhưng trở nên nhiều cột nullable khi mỗi subtype có tập thuộc tính lớn.

Về khóa và chỉ mục:

- Kiểu cha cần khóa định danh bền vững. Khóa chính kiểu con thường chính là khóa ngoại tới kiểu cha để giữ quan hệ một-một trên mỗi loại.
- Chỉ mục trên khóa chính kiểu con hỗ trợ truy vấn **EXISTS/NOT EXISTS** để chẩn đoán tính bao phủ.
- Nếu ứng dụng lọc nhiều theo trạng thái phân loại hoặc phương thức thanh toán, cân nhắc chỉ mục theo **truy vấn thực tế**; ràng buộc NOT NULL không tự làm cho mọi truy vấn lọc theo loại trở nên nhanh.
- Với bảng liên kết kiểu con, khóa ghép thường dùng (parent_id, subtype_code). Nếu truy vấn theo subtype_code để lấy nhiều parent_id thường xuyên, có thể cần chỉ mục đảo (subtype_code, parent_id).

Không nên nhân bản một cờ “đã chuyên biệt hóa” trong bảng cha và đồng thời dùng sự tồn tại bản ghi con làm nguồn sự thật, trừ khi có cơ chế giữ hai biểu diễn luôn nhất quán.

## 9. Diễn đạt cùng một quy tắc trong document, đồ thị và phân tích

Quy tắc bao phủ là **ngữ nghĩa dữ liệu**, không phải tính năng chỉ tồn tại trong cơ sở dữ liệu quan hệ.

| Mô hình | Toàn phần | Một phần | Điều cần chú ý |
| --- | --- | --- | --- |
| **Quan hệ** | Discriminator NOT NULL hoặc ràng buộc tồn tại kiểu con | Kiểu cha có thể tồn tại khi không có hàng con | CHECK chỉ kiểm tra dữ liệu cùng hàng; toàn phần xuyên bảng đòi cơ chế bổ sung |
| **Document** | Yêu cầu trường phân loại hoặc ít nhất một cấu trúc subtype hợp lệ qua JSON Schema/validation | Cho phép document không có phần mở rộng subtype | Phân biệt trường thiếu, trường NULL và danh sách rỗng; kiểm tra logic theo trạng thái |
| **Đồ thị** | Node kiểu cha phải có ít nhất một nhãn/quan hệ thể hiện kiểu con tương ứng | Node kiểu cha có thể không có nhãn/cạnh subtype | Không mặc định DB tự cưỡng chế “ít nhất một cạnh”; cần chính sách ghi hoặc constraint phù hợp |
| **Kho dữ liệu phân tích** | Mọi sự kiện/đối tượng thuộc ít nhất một nhóm hợp lệ trong dimension/bridge | Có thể không thuộc các nhóm chuyên biệt hiện hành | Phân biệt “chưa được gán”, “không áp dụng”, “không rõ”; tránh nhân bản số liệu ở mô hình chồng lấp |

Ví dụ document biểu diễn thanh toán có phân loại đầy đủ:

~~~json
{
  "paymentId": 2201,
  "state": "COMPLETED",
  "method": "CARD",
  "card": {
    "token": "tok_example_001"
  }
}
~~~

Để cưỡng chế toàn phần, validator có thể yêu cầu **method** cho document ở trạng thái COMPLETED và kiểm tra khối dữ liệu riêng theo method. Nếu hai cấu trúc là loại trừ nhau, JSON Schema có thể dùng **oneOf** với các điều kiện nhánh không trùng nhau; nếu nhóm kiểu con được phép chồng lấp nhưng phải có ít nhất một, có thể dùng **anyOf**. Cả hai đòi định nghĩa rõ những thuộc tính nào làm một document thỏa mãn từng nhánh.

Với dữ liệu phân tích, đừng tự động diễn giải “không thuộc subtype nào” thành **UNKNOWN**. Một bản ghi một phần có thể **hợp lệ về nghiệp vụ** và chỉ không thuộc nhóm đặc thù đang nghiên cứu. Trộn trạng thái đó với dữ liệu bị thiếu sẽ làm sai tỷ lệ chất lượng dữ liệu hoặc báo cáo phân khúc.

## 10. Quy tắc thay đổi theo vòng đời và thời gian

Nhiều hệ thống có quy tắc: khi mới tạo, thực thể được phép chưa được phân loại; từ một mốc nghiệp vụ trở đi, việc phân loại trở thành bắt buộc.

Ví dụ:

~~~text
PaymentRequest[DRAFT]
    └── được phép chưa có phương thức
              |
              v
PaymentRequest[COMPLETED]
    └── bắt buộc có ít nhất một phương thức hợp lệ
~~~

Có hai cách tiếp cận quan trọng:

1. **Đặt điều kiện toàn phần theo trạng thái** bằng ràng buộc như ví dụ payment_requests. Hệ thống giữ cùng định danh qua các trạng thái.
2. **Tách loại thực thể** nếu bản nháp và đối tượng đã hoàn tất có vòng đời, khóa, trách nhiệm hoặc ràng buộc khác nhau đáng kể; ví dụ PaymentRequest chuyển thành CompletedPayment khi hoàn tất.

Trong cả hai cách, cần thống nhất điều gì xảy ra khi chuyển trạng thái hoặc xóa loại. Thao tác chuyển Payment từ CARD sang BANK_TRANSFER không nên để lại dữ liệu subtype cũ; nếu cập nhật thành nhiều bước, phải quản lý tính nguyên tử và thời điểm kiểm tra ràng buộc.

Nếu có yêu cầu truy vấn phân loại **tại thời điểm quá khứ**, việc lưu duy nhất subtype hiện tại là chưa đủ. Có thể cần bảng lịch sử với effective_from/effective_to và quy định rõ tính toàn phần tại mỗi khoảng thời gian đã đóng hoặc tại các mốc phê duyệt. Không nên suy ra vi phạm toàn phần tại thời điểm cũ chỉ từ trạng thái hiện tại.

## 11. Kiểm tra chất lượng mô hình và dữ liệu

Từ quy tắc nghiệp vụ, hãy viết ma trận kiểm thử trước khi chọn cấu trúc:

| Trường hợp | Toàn phần + loại trừ | Một phần + loại trừ | Toàn phần + chồng lấp | Một phần + chồng lấp |
| --- | --- | --- | --- | --- |
| 0 kiểu con | **Từ chối** | Cho phép | **Từ chối** | Cho phép |
| 1 kiểu con | Cho phép | Cho phép | Cho phép | Cho phép |
| 2 kiểu con đồng thời | **Từ chối** | **Từ chối** | Cho phép | Cho phép |
| Xóa kiểu con cuối cùng | **Từ chối** | Cho phép | **Từ chối** | Cho phép |
| Nhập thiếu thuộc tính bắt buộc của subtype | Từ chối | Từ chối nếu subtype đó được áp dụng | Từ chối | Từ chối nếu subtype đó được áp dụng |

Mỗi thiết kế thực tế nên kiểm thử thêm:

- **Tạo thực thể cha:** được phép tạo trước kiểu con hay phải tạo cùng giao dịch?
- **Chuyển trạng thái:** cập nhật từ DRAFT sang ACTIVE/COMPLETED khi chưa có kiểu con có bị chặn không?
- **Xóa/cập nhật subtype:** loại bỏ bản ghi con cuối cùng có phá ràng buộc không?
- **Chồng lấp:** nếu quy tắc cho phép 2 kiểu con, cơ sở dữ liệu có lưu và đọc được cả hai không?
- **Ghi đồng thời:** hai giao dịch thay đổi tư cách thành viên có thể để lại trạng thái ngoài chính sách không?
- **Định danh:** xóa hoặc thêm subtype có làm đổi khóa định danh của kiểu cha không?
- **Dữ liệu lịch sử:** phân loại có cần theo thời điểm hay chỉ trạng thái hiện tại?

Một chỉ báo chất lượng hữu ích khi kiểm kê dữ liệu là **số thực thể cha thiếu subtype**. Trong mô hình một phần, đó có thể là số liệu hoạt động bình thường. Trong mô hình toàn phần, đó là chỉ báo cần điều tra hoặc một điều kiện phải bằng 0:

~~~sql
-- Ví dụ trên các bảng staff ở phần 5:
SELECT COUNT(*) AS staff_without_special_role
FROM staff AS s
WHERE NOT EXISTS (
    SELECT 1 FROM staff_managers AS m
    WHERE m.staff_id = s.staff_id
)
AND NOT EXISTS (
    SELECT 1 FROM staff_sales_reps AS r
    WHERE r.staff_id = s.staff_id
);
~~~

Cùng một truy vấn không thể tự kết luận dữ liệu “tốt” hay “lỗi”; kết luận phụ thuộc **quy tắc bao phủ đã xác nhận**.

## 12. Các sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Tưởng toàn phần đồng nghĩa đúng một subtype | Toàn phần chỉ yêu cầu **ít nhất một**; vẫn có thể chồng lấp | Xác định độc lập tính loại trừ/chồng lấp |
| Tưởng một phần đồng nghĩa không có subtype | Một phần chỉ **cho phép** số lượng bằng 0 | Vẫn biểu diễn và kiểm soát subtype khi được áp dụng |
| Cho rằng khóa ngoại từ bảng con lên bảng cha đã cưỡng chế toàn phần | FK một chiều không yêu cầu cha có con | Thêm chiến lược bảo đảm bao phủ |
| Dùng discriminator NOT NULL cho bản nháp hợp lệ chưa phân loại | Ép nhập loại sai hoặc phải tạo loại giả | Đặt ràng buộc có điều kiện theo vòng đời |
| Dùng NULL mà không định nghĩa ý nghĩa | Trộn “không áp dụng”, “chưa phân loại”, “dữ liệu thiếu” | Tách trạng thái theo ngữ nghĩa nghiệp vụ |
| Biến danh sách subtype chưa đầy đủ thành mô hình toàn phần | Những loại thực sự hợp lệ khác không có chỗ biểu diễn | Bổ sung subtype hoặc xác định phạm vi một phần |
| Kiểm tra toàn phần chỉ khi INSERT | Xóa hàng con cuối cùng vẫn phá tính toàn phần | Kiểm tra cả UPDATE, DELETE và chuyển trạng thái |
| Gộp ràng buộc phân loại với thuộc tính NOT NULL chung | Bắt nhân viên không làm Manager cũng phải có hạn mức phê duyệt | Đặt thuộc tính bắt buộc **theo subtype** |

## 13. Bài tập tình huống có đáp án

**Tình huống A — Danh mục sản phẩm:** Bảng Product lưu điện thoại, laptop, bàn ghế và thực phẩm. Hai kiểu con được thiết kế là ElectronicProduct và FurnitureProduct. Mỗi sản phẩm điện tử có mã bảo hành; mỗi sản phẩm nội thất có vật liệu. Có nên đặt chuyên biệt hóa toàn phần?

**Phân tích:** Với **chỉ hai kiểu con đã liệt kê**, tính toàn phần là sai vì Product thực phẩm hợp lệ không thuộc cả hai. Chọn **một phần**, hoặc thiết kế một nhóm subtype đầy đủ nếu yêu cầu nghiệp vụ thật sự muốn phân loại mọi Product theo một hệ danh mục bao phủ. Không gán thực phẩm vào Electronics hoặc Furniture để thỏa ràng buộc.

**Tình huống B — Đơn yêu cầu hỗ trợ:** Ticket mới có thể chưa được chuyển cho nhóm nào; Ticket trạng thái ASSIGNED bắt buộc thuộc nhóm TechnicalTicket hoặc BillingTicket. Ticket chỉ được thuộc một nhóm tại một thời điểm.

**Phân tích:** Nhóm chuyên biệt hóa là **loại trừ**. Về tính bao phủ, Ticket mới **được phép không có subtype**; Ticket ASSIGNED phải có **đúng một** subtype. Có thể dùng cột ticket_type nullable kết hợp điều kiện:

~~~sql
-- Minh họa ràng buộc khi đã có status và ticket_type:
ALTER TABLE support_tickets
ADD CONSTRAINT assigned_ticket_needs_type CHECK (
    status <> 'ASSIGNED' OR ticket_type IS NOT NULL
);
~~~

Ràng buộc này giả định các cột đã tồn tại và status là NOT NULL; ngoài ra cần kiểm tra ticket_type chỉ nhận giá trị hợp lệ và chi tiết riêng của từng loại. Nếu Ticket có thể trở lại trạng thái chưa được gán, phải xác nhận liệu nghiệp vụ cho phép xóa thông tin phân loại trước đó hay cần giữ lịch sử.

**Tình huống C — Nền tảng thành viên:** Mọi thành viên đã kích hoạt phải là Consumer hoặc Partner, hoặc cả hai; tài khoản đang chờ xác minh có thể chưa thuộc loại nào.

**Phân tích:** Đây là **chồng lấp** với **tính toàn phần có điều kiện khi kích hoạt**. Lược đồ cần cho phép hai vai trò cùng tồn tại và chặn chuyển tài khoản sang ACTIVE khi chưa có vai trò. Một cột loại đơn với hai giá trị Consumer/Partner là không đủ vì nó cấm trường hợp cùng lúc có cả hai.

### Ghi nhớ khi chuyển yêu cầu thành lược đồ

**Toàn phần = mọi thực thể cha có ít nhất một subtype. Một phần = subtype là tùy chọn đối với thực thể cha.** Hai quy tắc này nói về **tính bao phủ**; muốn biết số subtype tối đa còn phải xét tính loại trừ hay chồng lấp. Chỉ khi mô hình xác định rõ **thực thể, phạm vi, thời điểm và vòng đời**, ta mới có thể tạo ràng buộc đáng tin cậy trên bảng, khóa, chỉ mục và các cơ chế lưu trữ khác.

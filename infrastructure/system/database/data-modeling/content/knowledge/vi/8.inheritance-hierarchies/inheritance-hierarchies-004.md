# Phân biệt quan hệ là một, có một và đóng vai trò

Trong thiết kế dữ liệu, ba cách nói **“A là một B” (IS-A)**, **“A có một B” (HAS-A)** và **“A đóng vai trò B” (PLAYS-A-ROLE)** mô tả ba loại sự thật nghiệp vụ khác nhau. Chúng có thể xuất hiện gần nhau trong cùng một hệ thống, nhưng dẫn đến những quyết định khác nhau về định danh, khóa, quan hệ, tính bắt buộc, vòng đời và khả năng mở rộng.

Hãy xét sàn thương mại điện tử:

- **DigitalProduct là một Product**: sản phẩm số là trường hợp chuyên biệt của sản phẩm.
- **SalesOrder có các OrderLine**: đơn hàng được cấu thành từ các dòng hàng.
- **AppUser đóng vai trò người mua trong SalesOrder**, và có thể **đóng vai trò người bán trên OrderLine**: một người dùng tham gia các giao dịch với những vai trò khác nhau.

Đây là chủ đề nền tảng của chương **Kế thừa và phân cấp** trong module **DATABASE_DATA_MODELING**: biến phát biểu nghiệp vụ thành mô hình có thể kiểm chứng, từ sơ đồ khái niệm đến lược đồ vật lý; phân biệt khi nào cần bảng kiểu con, khóa ngoại, bảng quan hệ và ràng buộc theo ngữ cảnh.

## 1. Nhìn nhanh ba loại quan hệ

| Tiêu chí | IS-A: “là một” | HAS-A: “có một/có các” | PLAYS-A-ROLE: “đóng vai trò” |
| --- | --- | --- | --- |
| Câu hỏi | A có phải là một trường hợp của B? | A liên kết với hoặc chứa những B nào? | A tham gia bối cảnh C với tư cách gì? |
| Ý nghĩa | Phân loại, chuyên biệt hóa, kế thừa thuộc tính | Liên kết, tập hợp, thành phần, sở hữu tùy nghiệp vụ | Tư cách tham gia, trách nhiệm hoặc quyền trong ngữ cảnh |
| Ví dụ | DigitalProduct là Product | Order có OrderLine | User là người mua của Order |
| Định danh | Kiểu con kế thừa **cùng định danh thực thể** của kiểu cha | Hai bên thường là **hai thực thể** hoặc một thực thể và giá trị thành phần | **Một chủ thể** có thể giữ nhiều vai trò theo giao dịch, nhóm và thời điểm |
| Ánh xạ quan hệ thường gặp | Discriminator hoặc bảng cha–con cùng khóa | Khóa ngoại, bảng nối, đôi khi lưu thành phần cùng bảng | Khóa ngoại mang tên vai trò, bảng gán vai trò có phạm vi và thời hạn |
| Sai lầm thường gặp | Dùng IS-A vì chỉ “có liên quan” | Nhầm mọi HAS-A đều phải xóa dây chuyền | Biến vai trò tạm thời thành kiểu thực thể cố định |

Một cách thử nhanh: **nếu mọi đối tượng A đều có thể được gọi là B, giữ nguyên đối tượng và định danh khi gọi như vậy**, có thể là IS-A. **Nếu A và B là những đối tượng khác nhau gắn với nhau**, thường là HAS-A hoặc quan hệ nói chung. **Nếu A giữ tư cách B chỉ khi tham gia một hoạt động hoặc bối cảnh**, cần xem xét PLAYS-A-ROLE.

Các phép thử này giúp phát hiện mô hình hợp lý nhưng **không thay thế xác nhận quy tắc nghiệp vụ**. Một tên gọi như “Customer” có thể là loại khách hàng cố định trong một hệ thống, là vai trò giao dịch trong hệ thống khác, hoặc là một hồ sơ người dùng có trạng thái riêng.

## 2. IS-A: quan hệ khái quát hóa và chuyên biệt hóa

**IS-A** mô tả quan hệ giữa **kiểu cha (supertype)** và **kiểu con (subtype)**. Mọi thực thể thuộc kiểu con đều thuộc kiểu cha. Kiểu con dùng chung định danh và các thuộc tính chung của cha, có thể có thuộc tính, quy tắc và hành vi riêng.

Ví dụ nghiệp vụ:

> “Mọi DigitalProduct đều là Product, có mã sản phẩm chung, tên và giá bán; DigitalProduct còn có địa chỉ tài nguyên tải xuống.”

Ở đây:

- Product là kiểu cha, DigitalProduct là kiểu con.
- Bản ghi DigitalProduct và bản ghi Product của nó đại diện cho **cùng một sản phẩm**, không phải hai sản phẩm được liên kết.
- Các quan hệ áp dụng cho Product, chẳng hạn OrderLine tham chiếu Product, cũng phải dùng được với DigitalProduct.
- Một trường hợp chuyên biệt có thể có ràng buộc riêng, ví dụ tài nguyên tải xuống không được trống.

Đó là ý nghĩa **thay thế theo kiểu dữ liệu (substitutability)**: nơi hệ thống cần tham chiếu Product thì đối tượng DigitalProduct cũng là một Product hợp lệ. Trong mô hình dữ liệu, không nên hiểu điều này thành lời hứa về kế thừa mã nguồn; **kế thừa trong lập trình và chuyên biệt hóa thực thể trong CSDL không nhất thiết có cùng cấu trúc**.

### 2.1. IS-A không chỉ là hai bảng có khóa ngoại

Xét:

~~~text
Product (product_id)
    ^
    | IS-A: cùng product_id
    |
DigitalProduct (product_id, download_url)
~~~

Khóa của DigitalProduct có thể đồng thời là khóa ngoại tới Product. Nó nói “bản ghi con này chi tiết hóa **chính sản phẩm ấy**”. Ngược lại, OrderLine có khóa riêng và tham chiếu product_id vì nó là **một dòng giao dịch khác với sản phẩm**; OrderLine không phải kiểu con của Product.

Nếu dùng hai bảng để biểu diễn IS-A, quan hệ một-một giữa kiểu con và kiểu cha vẫn chưa đủ để bảo đảm đầy đủ quy tắc phân cấp. Cần xác định thêm:

- **Toàn phần hay một phần:** mọi Product phải thuộc ít nhất một kiểu con hay được phép là Product chưa chuyên biệt hóa?
- **Loại trừ hay chồng lấp:** một Product được phép đồng thời thuộc nhiều kiểu con không?
- **Thuộc tính riêng:** các trường chỉ hợp lệ với subtype tương ứng.
- **Định danh chung:** có cho phép thay đổi subtype mà vẫn giữ product_id không?

Một ví dụ có **DigitalProduct** và **PhysicalProduct** chỉ loại trừ nhau khi nghiệp vụ thật sự quy định mỗi sản phẩm thuộc tối đa một trong hai nhóm. Nếu doanh nghiệp bán sản phẩm lai có cả nội dung tải xuống và hàng giao vật lý, thiết kế có thể phải cho phép chồng lấp hoặc mô hình hóa gói sản phẩm bằng các thành phần riêng.

### 2.2. Khi nào không nên chọn IS-A?

Các mệnh đề sau **không tạo ra quan hệ kiểu con chỉ vì chúng mô tả một thuộc tính hoặc sự tham gia**:

- “User có địa chỉ giao hàng” → quan hệ giữa người dùng và địa chỉ, hoặc thuộc tính giá trị; Address không phải subtype của User.
- “Order có Product” → OrderLine tham chiếu Product; Product không phải subtype của Order.
- “User là người mua của một Order” → User tham gia Order với vai trò buyer; chính Order là ngữ cảnh khiến tên gọi “người mua” có ý nghĩa.
- “Một nhân viên đang là trưởng nhóm của dự án X” → thường là vai trò theo dự án và thời gian, có thể mất hoặc đổi mà không biến nhân viên thành đối tượng mới.

Ngược lại, nếu nghiệp vụ xác định một **Manager** là kiểu Employee chuyên biệt có bộ thuộc tính và quy tắc riêng, IS-A có thể hợp lệ. Tên gọi không tự quyết định cách mô hình hóa; phải dựa vào **quy tắc định danh, tính ổn định, phạm vi và ràng buộc**.

## 3. HAS-A: quan hệ sở hữu, chứa hoặc liên kết

**HAS-A** mô tả rằng một thực thể **có, gồm, chứa, tham chiếu hoặc liên kết với** một thực thể khác. Các từ này dễ bị dùng lẫn, nhưng ràng buộc vòng đời có thể rất khác nhau.

Ví dụ:

> “Mỗi SalesOrder có nhiều OrderLine; mỗi OrderLine thuộc đúng một SalesOrder.”

Nếu đơn hàng chứa ba dòng sản phẩm, đó là **một SalesOrder và ba OrderLine**. Các dòng có định danh hoặc vị trí riêng trong đơn, số lượng và đơn giá tại thời điểm mua. OrderLine **không phải** một loại SalesOrder; nó là thành phần của đơn hàng.

Trong mô hình khái niệm, cần ghi cụ thể **bội số (cardinality)** và **tính bắt buộc (optionality)**:

| Quan hệ | Bội số phía thứ nhất | Bội số phía thứ hai | Diễn giải |
| --- | --- | --- | --- |
| SalesOrder – OrderLine | Một dòng thuộc đúng **1** đơn | Một đơn có **0..N** dòng khi còn nháp | Có thể thêm dòng sau khi tạo bản nháp |
| OrderLine – Product | Một dòng tham chiếu **1** sản phẩm | Một sản phẩm xuất hiện trong **0..N** dòng | Sản phẩm tồn tại độc lập với đơn |
| AppUser – SalesOrder | Một đơn có đúng **1** người mua | Một người dùng mua **0..N** đơn | Bản chất của người dùng không phụ thuộc việc đã mua |
| Department – Employee | Tùy chính sách, nhân viên có thể thuộc **0..1** phòng chính | Một phòng có **0..N** nhân viên | Liên kết tổ chức, không phải kế thừa |

Không nên suy luận “HAS-A” luôn có bội số 1–1 từ cụm “có một”. Ví dụ “User có một địa chỉ chính” có thể đồng thời “User có nhiều địa chỉ nhận hàng”. Hãy xác minh cụ thể số lượng tối thiểu, tối đa và phạm vi hiệu lực.

### 3.1. Liên kết, tập hợp và thành phần

Trong UML người ta phân biệt:

- **Association (liên kết):** hai đối tượng có liên quan, chẳng hạn OrderLine tham chiếu Product. Không nhất thiết có sở hữu hay phụ thuộc vòng đời.
- **Aggregation (tập hợp):** quan hệ toàn thể–bộ phận lỏng; thành phần có thể tồn tại độc lập và có thể được chia sẻ. Phạm vi ý nghĩa cần được phát biểu rõ.
- **Composition (thành phần chặt):** bộ phận thường phụ thuộc vào toàn thể và không là thành phần của hai toàn thể cùng lúc; ví dụ OrderLine chỉ thuộc một SalesOrder.

**Không được mặc định composition đồng nghĩa ON DELETE CASCADE.** Nếu đơn hàng là chứng từ tài chính phải được lưu nhiều năm, khi có dòng hàng thì việc xóa đơn có thể phải **bị từ chối** hoặc được thay bằng lưu trữ/đánh dấu hủy. Phụ thuộc vòng đời là **quy tắc nghiệp vụ**; hành vi xóa vật lý là một quyết định riêng.

Trong ER/quan hệ, nhiều trường hợp HAS-A được hiện thực bằng **khóa ngoại**. Quan hệ nhiều–nhiều dùng **bảng nối**. Một thành phần kiểu giá trị nhỏ, không có định danh độc lập, đôi khi thích hợp lưu cùng hàng hoặc nhúng vào document.

### 3.2. Ví dụ phân biệt sản phẩm và dòng đơn hàng

Một Product có thể được mua trong nhiều đơn hàng; một Order có nhiều dòng; mỗi dòng ghi số lượng và **đơn giá đã chốt tại thời điểm giao dịch**. Đơn giá trong OrderLine là dữ liệu của **lần mua** đó, nên không thể thay thế bằng giá hiện tại trong Product. Lưu cả đơn giá sản phẩm hiện tại và đơn giá giao dịch không nhất thiết là lỗi chuẩn hóa: chúng mô tả **hai sự thật khác thời điểm và ngữ cảnh**.

Đây là lý do OrderLine nên là một thực thể hoặc thành phần quan hệ có thuộc tính riêng, chứ không chỉ là một mảng product_id không rõ số lượng hay đơn giá.

## 4. PLAYS-A-ROLE: vai trò phụ thuộc ngữ cảnh

**PLAYS-A-ROLE** mô tả tư cách mà **một thực thể đang tham gia một quan hệ, hoạt động, tổ chức hoặc thời kỳ**. Vai trò không nhất thiết là subtype bền vững của thực thể.

Ví dụ:

> “Trong đơn hàng số 1001, User A đóng vai trò người mua. Trong một dòng giao dịch khác, chính User A có thể đóng vai trò người bán.”

Cùng User A vẫn dùng **một user_id**. Việc có vai trò người mua không có nghĩa cần một thực thể Buyer độc lập với User; càng không có nghĩa User chỉ được là Buyer hoặc Seller.

### 4.1. Vai trò gắn với một quan hệ

Trong mô hình quan hệ, tên khóa ngoại thường chính là cách ghi vai trò:

- **SalesOrder.buyer_user_id** → User tham gia SalesOrder với vai trò người mua.
- **OrderLine.seller_user_id** → User tham gia một dòng giao dịch với vai trò người bán.
- **Task.assignee_user_id** và **Task.reporter_user_id** → cùng bảng User tham gia Task dưới hai vai trò; một người có thể giữ cả hai, nếu nghiệp vụ cho phép.

Một sự kiện có thể có **nhiều vai trò tham gia** và **một thực thể có thể đảm nhiệm nhiều vai trò**, tùy ràng buộc. Không tự thêm CHECK ngăn buyer và seller trùng user_id chỉ vì tên vai trò khác nhau; phải có chính sách chống tự giao dịch rõ ràng mới thêm điều kiện đó.

### 4.2. Vai trò gắn với tổ chức, thời gian hoặc quyền

Không phải vai trò nào cũng chỉ cần một cột khóa ngoại. Ví dụ User giữ vai trò **EDITOR** trong Workspace A nhưng là **VIEWER** trong Workspace B; vai trò thay đổi theo thời gian và có thể đồng thời tồn tại.

Khi đó nên dùng một quan hệ gán vai trò có **ít nhất ba thành phần**:

~~~text
RoleAssignment(
    user_id,
    workspace_id,
    role_code,
    valid_from,
    valid_to,
    ...thuộc tính của lần gán vai trò
)
~~~

Định danh của sự gán vai trò có thể là khóa ghép thích hợp hoặc khóa riêng. Cần quyết định liệu một người có được giữ nhiều vai trò trong cùng workspace, có được có hai khoảng hiệu lực chồng nhau cho cùng vai trò và có cần giữ lịch sử khi thu hồi vai trò hay không.

**Vai trò tham gia giao dịch** và **quyền được phép thực hiện giao dịch** cũng khác nhau. User xuất hiện trong OrderLine với vai trò seller là một sự kiện lịch sử; quyền bán hàng hiện tại có thể do hồ sơ xác minh và trạng thái tài khoản quyết định. Không nên dùng “đã từng bán” làm bằng chứng rằng User hiện vẫn được phép bán.

### 4.3. Khi nào vai trò có thể trở thành subtype?

Vai trò *có thể* được biểu diễn bằng subtype nếu nghiệp vụ thực sự xây dựng một chuyên biệt hóa có dữ liệu và bất biến riêng, chẳng hạn **SellerAccount** có hồ sơ định danh, mã số thuế và cơ chế xét duyệt. Tuy nhiên phải trả lời:

1. SellerAccount có cùng định danh với AppUser hay là thực thể hồ sơ riêng?
2. Một AppUser có thể đồng thời có BuyerProfile và SellerProfile không?
3. Một User có thể thôi là Seller mà vẫn giữ lịch sử đơn hàng đã bán không?
4. Vai trò đó áp dụng toàn hệ thống hay riêng cho từng cửa hàng, nhóm hoặc giao dịch?

Nếu quy tắc phụ thuộc vào **quan hệ hoặc bối cảnh**, một bảng gán vai trò thường diễn đạt chính xác hơn việc cố tạo hệ phân cấp User → Buyer → Seller.

## 5. Một tình huống kết hợp cả ba loại quan hệ

Thiết kế hệ thống bán sản phẩm số và sản phẩm vật lý theo các giả định:

- Mọi Product được phân loại **đúng một** trong hai nhóm DIGITAL hoặc PHYSICAL.
- Một SalesOrder có một người mua, có thể ở trạng thái DRAFT trước khi có dòng hàng.
- Một OrderLine thuộc đúng một SalesOrder, tham chiếu đúng một Product và một người bán.
- Một AppUser có thể tham gia nhiều đơn hàng, vừa mua vừa bán ở những giao dịch khác nhau.

Sơ đồ khái niệm rút gọn:

~~~mermaid
flowchart LR
    DP["DigitalProduct"] -->|"IS-A"| P["Product"]
    PP["PhysicalProduct"] -->|"IS-A"| P
    O["SalesOrder"] -->|"HAS-A: nhiều dòng"| L["OrderLine"]
    L -->|"tham chiếu"| P
    U["AppUser"] -->|"đóng vai trò buyer"| O
    U -->|"đóng vai trò seller"| L
~~~

Mũi tên IS-A biểu thị sự chuyên biệt hóa; mũi tên HAS-A biểu thị quan hệ toàn thể–bộ phận; hai mũi tên từ AppUser cho thấy các **vai trò tham gia quan hệ**. Sơ đồ chỉ truyền đạt ngữ nghĩa chính; bội số và bắt buộc được định nghĩa rõ trong DDL bên dưới.

### 5.1. Lược đồ SQL minh họa (PostgreSQL)

Ví dụ dùng **một bảng Product với discriminator** để lưu phân cấp nhỏ, loại trừ nhau. Hai vai trò BUYER/SELLER được thể hiện trực tiếp trên quan hệ nghiệp vụ; OrderLine là bảng thành phần riêng.

~~~sql
-- Định danh người dùng là duy nhất bất kể vai trò tham gia.
CREATE TABLE app_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email   TEXT NOT NULL UNIQUE
);

-- IS-A: cùng một product_id; chỉ một loại sản phẩm trong ví dụ.
CREATE TABLE products (
    product_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title       TEXT NOT NULL,
    kind        TEXT NOT NULL
                CHECK (kind IN ('DIGITAL', 'PHYSICAL')),
    download_url TEXT,
    weight_grams INTEGER,
    CONSTRAINT product_details_match_kind CHECK (
        (kind = 'DIGITAL'
            AND download_url IS NOT NULL
            AND weight_grams IS NULL)
        OR
        (kind = 'PHYSICAL'
            AND download_url IS NULL
            AND weight_grams IS NOT NULL
            AND weight_grams > 0)
    )
);

-- PLAYS-A-ROLE: buyer_user_id trỏ tới User trong vai người mua.
CREATE TABLE sales_orders (
    order_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    buyer_user_id  BIGINT NOT NULL
                   REFERENCES app_users(user_id),
    status         TEXT NOT NULL DEFAULT 'DRAFT'
                   CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- HAS-A: OrderLine thuộc SalesOrder.
-- PLAYS-A-ROLE: seller_user_id là người bán của dòng hàng.
CREATE TABLE order_lines (
    order_id       BIGINT NOT NULL REFERENCES sales_orders(order_id),
    line_no        INTEGER NOT NULL CHECK (line_no > 0),
    product_id     BIGINT NOT NULL REFERENCES products(product_id),
    seller_user_id BIGINT NOT NULL REFERENCES app_users(user_id),
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit_price     NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Giải thích những quyết định đáng chú ý:

| Thiết kế | Quy tắc nghiệp vụ thể hiện | Cơ chế chính |
| --- | --- | --- |
| products.kind | Mọi Product thuộc đúng một nhóm đang xét | NOT NULL, CHECK, kiểm tra trường riêng theo loại |
| order_lines.order_id | Mỗi dòng phải thuộc một đơn hàng tồn tại | FK + NOT NULL; khóa ghép ngăn trùng line_no trong một đơn |
| order_lines.product_id | Dòng tham chiếu sản phẩm độc lập | FK; Product có thể xuất hiện trong nhiều dòng |
| sales_orders.buyer_user_id | User đóng vai người mua của Order | FK tới app_users; không cần bảng Buyer riêng |
| order_lines.seller_user_id | User đóng vai người bán trên OrderLine | FK tới app_users; cùng User có thể mua và bán |
| order_lines.unit_price | Giá tại thời điểm giao dịch | Thuộc tính dòng hàng, không dùng giá Product hiện tại |

**Giới hạn cần nêu rõ:** Lược đồ cho phép một Order ở trạng thái CONFIRMED có **0 dòng hàng**, vì FK từ OrderLine tới Order không kiểm tra chiều ngược lại. Nếu nghiệp vụ quy định đơn đã xác nhận phải có ít nhất một dòng, cần bổ sung kiểm soát tại điểm xác nhận bằng quy trình giao dịch và cơ chế kiểm tra dữ liệu phù hợp (ví dụ constraint trigger trì hoãn trong PostgreSQL). Đồng thời phải kiểm soát việc xóa dòng cuối của đơn đã xác nhận; chỉ kiểm tra thao tác tạo đơn là chưa đủ.

Ví dụ cũng chưa kiểm soát **tư cách bán hàng hợp lệ** của seller_user_id; nếu chỉ người bán đã xác minh được bán, cần một quan hệ/hồ sơ và ràng buộc kiểm tra riêng. Khóa ngoại app_users chỉ xác nhận người bán **tồn tại**, không xác nhận **đủ điều kiện**.

### 5.2. Truy vấn để thấy ý nghĩa khác nhau

Lấy các dòng hàng của đơn cùng sản phẩm và người bán:

~~~sql
SELECT o.order_id,
       o.buyer_user_id,
       l.line_no,
       l.quantity,
       l.unit_price,
       p.product_id,
       p.kind,
       p.title,
       l.seller_user_id
FROM sales_orders AS o
JOIN order_lines AS l ON l.order_id = o.order_id
JOIN products AS p ON p.product_id = l.product_id
WHERE o.order_id = 1001
ORDER BY l.line_no;
~~~

Phép JOIN giữa Order và OrderLine mô tả **HAS-A**; phép JOIN đến Product mô tả **dòng hàng tham chiếu sản phẩm**; tên buyer_user_id và seller_user_id ghi **vai trò**. Giá trị products.kind giúp phân biệt **IS-A** DigitalProduct/PhysicalProduct trong thiết kế một bảng.

Tìm User đã từng tham gia với **cả hai vai trò**, nhưng vẫn chỉ trả về mỗi User một lần:

~~~sql
SELECT u.user_id, u.email
FROM app_users AS u
WHERE EXISTS (
    SELECT 1
    FROM sales_orders AS o
    WHERE o.buyer_user_id = u.user_id
)
AND EXISTS (
    SELECT 1
    FROM order_lines AS l
    WHERE l.seller_user_id = u.user_id
);
~~~

Dùng EXISTS thay cho JOIN hai danh sách giao dịch để tránh nhân bản kết quả khi User có nhiều đơn đã mua và nhiều dòng đã bán. **User có cả hai vai trò không có nghĩa một đơn tự mua tự bán**; hai quan hệ có thể thuộc những giao dịch khác nhau.

### 5.3. Chỉ mục phục vụ các quan hệ

Khóa chính tự tạo chỉ mục trên product_id, user_id, order_id và cặp (order_id, line_no). Tuy nhiên, trong PostgreSQL, tạo **khóa ngoại ở bảng tham chiếu không tự tạo chỉ mục trên cột FK của bảng đó**. Nếu cần truy vấn theo người mua, người bán hoặc sản phẩm, có thể cân nhắc:

~~~sql
CREATE INDEX idx_sales_orders_buyer
    ON sales_orders (buyer_user_id, order_id);

CREATE INDEX idx_order_lines_seller
    ON order_lines (seller_user_id, order_id);

CREATE INDEX idx_order_lines_product
    ON order_lines (product_id);
~~~

Chỉ mục trên (order_id, line_no) đã hỗ trợ truy vấn dòng theo đơn hàng. Các chỉ mục bổ sung nên dựa trên truy vấn và khối lượng dữ liệu thực tế; không nên coi tất cả khóa ngoại đều cần cùng một loại chỉ mục.

## 6. Khi vai trò cần một bảng quan hệ có ngữ cảnh

Một ví dụ khác là người dùng tham gia **Workspace** với vai trò EDITOR hoặc VIEWER. Không nên tạo các thực thể UserEditor và UserViewer độc lập nếu cùng một người có thể giữ vai trò khác nhau trong nhiều workspace.

~~~sql
CREATE TABLE workspaces (
    workspace_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_name TEXT NOT NULL
);

CREATE TABLE workspace_role_assignments (
    user_id       BIGINT NOT NULL REFERENCES app_users(user_id),
    workspace_id  BIGINT NOT NULL REFERENCES workspaces(workspace_id),
    role_code     TEXT NOT NULL CHECK (role_code IN ('EDITOR', 'VIEWER')),
    valid_from    TIMESTAMPTZ NOT NULL,
    valid_to      TIMESTAMPTZ,
    CONSTRAINT valid_role_period CHECK (
        valid_to IS NULL OR valid_to > valid_from
    ),
    PRIMARY KEY (user_id, workspace_id, role_code, valid_from)
);
~~~

Bảng workspace_role_assignments mô hình hóa **quan hệ giữa User, Workspace và vai trò trong một khoảng hiệu lực**. Một User có thể làm EDITOR ở workspace A, VIEWER ở workspace B và đổi vai trò mà vẫn giữ user_id.

Lược đồ trên **cho phép hai vai trò đồng thời trong cùng workspace** và có thể có nhiều khoảng hiệu lực của **cùng vai trò** chồng lấp. Nếu nghiệp vụ cấm, phải bổ sung ràng buộc theo (user_id, workspace_id, role_code) và khoảng thời gian, chẳng hạn exclusion constraint phù hợp hoặc cơ chế ghi giao dịch nhất quán. Một UNIQUE đơn giản trên ba cột sẽ chặn lịch sử tái cấp vai trò, nên không phù hợp nếu vai trò có thể được thu hồi rồi cấp lại.

Quyết định “một User trong một Workspace chỉ có đúng một vai trò đang hiệu lực” khác với quyết định “một User có thể có nhiều vai trò trên toàn hệ thống”. Luôn gắn giới hạn số lượng với **phạm vi cụ thể**.

## 7. Chọn cách biểu diễn khi có ranh giới không rõ

Các phát biểu tự nhiên có thể gây nhầm lẫn:

| Phát biểu | Cách hiểu khả dĩ | Cần xác nhận |
| --- | --- | --- |
| “Customer là User” | Customer là subtype hoặc là vai trò mua hàng | User có phải tạo hồ sơ Customer riêng? Có thể không mua nữa nhưng vẫn còn lịch sử? |
| “Manager là Employee” | Manager là subtype hoặc là vai trò theo dự án/phòng ban | Có thuộc tính chuyên biệt lâu dài hay chỉ là việc phân công có thời hạn? |
| “Order có Product” | Quan hệ trực tiếp hay thông qua OrderLine | Cần lưu số lượng, đơn giá, giảm giá và số dòng trùng Product không? |
| “Account có Address” | Thành phần giá trị nhúng, hoặc entity Address có định danh | Một địa chỉ có thể dùng chung? Có cần lịch sử và loại địa chỉ? |
| “Seller bán Product” | Quan hệ giữa Seller và Product/Listing, hoặc vai trò trên dòng mua bán | Một Product có nhiều người bán không? Seller có thay đổi theo từng Listing? |
| “Vehicle là Asset” | Phân cấp IS-A | Có đối tượng Asset nào vừa là Vehicle vừa thuộc kiểu con khác không? |

Một số tình huống cần **kết hợp hai mô hình**, chứ không chọn một trong ba nhãn:
 
- SellerProfile có thể là **hồ sơ chuyên biệt** gắn với User (IS-A hoặc quan hệ 1–1 tùy định danh).
- User có thể **giữ vai trò seller** trong một dòng đơn hàng (PLAYS-A-ROLE).
- SellerProfile có thể **có** thông tin ngân hàng, địa chỉ và giấy tờ (HAS-A).

Như vậy, gọi một người là “seller” không tự chứng minh cần một bảng subtype Seller. Hãy tách **bản sắc đối tượng**, **cấu trúc thành phần** và **tư cách tham gia** trước khi thiết kế bảng.

## 8. Tác động đến chuẩn hóa, khóa, ràng buộc và vòng đời

### 8.1. Định danh và khóa

- **IS-A:** có một định danh thực thể chung. Nếu dùng bảng cha–con, khóa chính subtype thường là khóa ngoại tới supertype; không phát sinh một bản sao thực thể độc lập.
- **HAS-A:** mỗi thành phần/liên kết có cấu trúc khóa theo quy tắc của nó. OrderLine dùng (order_id, line_no) vì line_no chỉ duy nhất **trong một Order**.
- **PLAYS-A-ROLE:** xác định khóa dựa trên **chủ thể + ngữ cảnh + loại vai trò + thời điểm** nếu cần lịch sử. Chỉ dùng user_id làm khóa chính cho gán vai trò sẽ cấm một User có nhiều vai trò/ngữ cảnh.

### 8.2. Chuẩn hóa và dữ liệu trùng lặp

Không nên tạo bảng Buyer và Seller chứa lặp toàn bộ tên, email, điện thoại của cùng một User chỉ vì họ có hai vai trò. Thông tin nhận dạng dùng chung thuộc AppUser; thông tin chuyên biệt của vai trò có thể đặt ở profile hoặc quan hệ gán vai trò.

Mặt khác, thuộc tính gắn với **lần tham gia quan hệ** phải nằm đúng nơi phát sinh: OrderLine có quantity và unit_price; RoleAssignment có valid_from và valid_to. Dồn chúng vào Product hoặc User sẽ tạo phụ thuộc sai và dẫn tới bất thường cập nhật.

### 8.3. Xóa và chuyển trạng thái

- Xóa DigitalProduct phải tuân theo yêu cầu về Product cha và các giao dịch đã tham chiếu; có thể cần chuyển trạng thái ngừng kinh doanh thay vì xóa bản ghi lịch sử.
- Xóa Order có thể bị cấm khi cần bảo toàn chứng từ, dù OrderLine là thành phần của Order.
- Thu hồi quyền EDITOR không có nghĩa xóa User, không nên xóa lịch sử RoleAssignment.
- Nếu thay đổi loại Product từ DIGITAL sang PHYSICAL, phải xét cách chuyển thuộc tính riêng, dữ liệu lịch sử giao dịch và giới hạn của nghiệp vụ. Có thể việc đổi loại sau khi đã bán là bất hợp lệ.

Một nguyên tắc thiết kế hữu ích: **đời sống của thực thể, đời sống của thành phần và hiệu lực của vai trò là ba trục thời gian khác nhau**.

### 8.4. Các quy tắc vượt khả năng của CHECK một hàng

Một CHECK trên Product có thể kiểm tra kind và thuộc tính riêng vì chúng nằm **cùng một hàng**. Nhưng “mỗi Order trạng thái CONFIRMED có ít nhất một OrderLine”, hoặc “người được gán làm seller phải có giấy phép bán đang hiệu lực”, có thể cần truy vấn và kiểm soát **xuyên bảng**.

Đối với các quy tắc đó, có thể cần thay đổi thiết kế, giao dịch nguyên tử, constraint trigger trì hoãn hoặc cơ chế xác thực nhất quán. Một FK chỉ kiểm tra sự tồn tại của hàng được tham chiếu; không tự biểu diễn đầy đủ tư cách, trạng thái hay quyền trong thời gian.

## 9. Cùng một ngữ nghĩa trong document, đồ thị và dữ liệu phân tích

Ba loại quan hệ vẫn tồn tại khi không dùng CSDL quan hệ; khác nhau chủ yếu ở cơ chế biểu diễn và cách cưỡng chế ràng buộc.

| Cách lưu trữ | IS-A | HAS-A | PLAYS-A-ROLE |
| --- | --- | --- | --- |
| **Quan hệ** | Discriminator hoặc bảng subtype chung khóa với cha | FK, bảng nối, bảng thành phần | FK đặt tên theo vai trò hoặc bảng gán vai trò có ngữ cảnh |
| **Document** | Trường loại và schema cho biến thể cụ thể | Nhúng thành phần hoặc dùng tham chiếu tới document độc lập | Lưu id chủ thể trong vai trò cụ thể, hoặc mảng bản ghi gán vai trò |
| **Đồ thị** | Nhãn loại hoặc quan hệ phân loại được kiểm soát | Cạnh HAS_PART/CONTAINS/REFERENCES | Cạnh tham gia có tên vai trò và thuộc tính thời gian |
| **Phân tích** | Dimension với loại/chuyên biệt hóa rõ | Fact chi tiết và dimension/bridge phù hợp | Vai trò của dimension trong từng fact hoặc bridge phân quyền/tham gia |

### Document: nhúng đúng thứ phụ thuộc

Một đơn hàng có thể lưu các dòng hàng ngay trong document nếu chúng thường được đọc/cập nhật cùng đơn và không cần chia sẻ độc lập:

~~~json
{
  "orderId": 1001,
  "buyerUserId": 7,
  "status": "CONFIRMED",
  "lines": [
    {
      "lineNo": 1,
      "productId": 501,
      "sellerUserId": 18,
      "quantity": 2,
      "unitPrice": 49000
    }
  ]
}
~~~

Trong document này:

- **lines** là HAS-A được nhúng.
- **buyerUserId** và **sellerUserId** chỉ vai trò của cùng kiểu đối tượng User trong các ngữ cảnh khác nhau.
- **productId** là tham chiếu đến Product độc lập, không biến Product thành thành phần sống chết cùng Order.
- Loại DIGITAL/PHYSICAL của Product có thể được lưu trong document Product riêng với schema xác thực trường subtype.

Nhúng mọi dữ liệu User và Product vào từng đơn hàng thường gây trùng lặp và khó đồng bộ. Một số thuộc tính giao dịch như giá chốt hoặc tên hiển thị lịch sử có thể được chụp tại thời điểm bán theo yêu cầu kiểm toán; cần phân biệt bản chụp cố ý với sao chép không kiểm soát.

### Đồ thị: phân loại, cấu trúc và tư cách là các cạnh khác nhau

Trong mô hình đồ thị:

- Node Product có nhãn DigitalProduct khi biểu diễn IS-A bằng nhiều nhãn (nếu mô hình yêu cầu).
- Cạnh từ Order đến OrderLine có thể mang ý nghĩa CONTAINS.
- Quan hệ từ User đến Order có thể biểu diễn BOUGHT; từ User đến OrderLine có thể biểu diễn SOLD.
- Quan hệ từ User đến Workspace có thể chứa thuộc tính role và thời hạn hiệu lực.

Một nhãn hoặc cạnh **chưa tự động cưỡng chế** toàn bộ các quy tắc kiểu con, số lượng, thời điểm và vòng đời. Cần sử dụng constraint mà công nghệ hỗ trợ hoặc kiểm soát trong quy trình ghi.

### Phân tích: tránh nhân bản số liệu vì nhiều vai trò

Giả sử một User vừa mua vừa bán nhiều giao dịch. Nếu nối bảng fact doanh thu với mọi RoleAssignment của User mà không giới hạn vai trò/hiệu lực, mỗi dòng fact có thể bị lặp và tổng doanh thu tăng sai.

Trong mô hình phân tích, nên ghi rõ **grain (mức hạt)**: một dòng fact là **một OrderLine**, một Order, hay một khoản thanh toán? Buyer và Seller có thể là **hai khóa ngoại cùng tham chiếu một dimension User** (*role-playing dimension*) nhưng biểu thị hai vai trò **khác nhau trong cùng sự kiện**. Khi phân tích quyền theo thời gian, cần JOIN đúng phạm vi workspace và khoảng hiệu lực.

## 10. Quy trình thực hành khi đọc yêu cầu nghiệp vụ

Có thể ra quyết định theo trình tự:

1. **Nhận diện đối tượng và định danh:** A và B là cùng một thực thể nhìn dưới hai mức trừu tượng, hay hai thực thể khác nhau?
2. **Kiểm tra mệnh đề “mọi A đều là B”:** nếu đúng và subtype có tính chất riêng, đánh giá IS-A. Xác định tính loại trừ/chồng lấp và toàn phần/một phần trước khi chọn bảng.
3. **Kiểm tra quan hệ chứa/liên kết:** nếu A có B, xác định bội số hai phía, phụ thuộc vòng đời, tính chia sẻ và có cần lưu thuộc tính của quan hệ không.
4. **Kiểm tra vai trò theo bối cảnh:** nếu A chỉ “là B” khi tham gia C, hỏi về ngữ cảnh, quyền, thời điểm, một hay nhiều vai trò và lịch sử.
5. **Chọn ánh xạ lược đồ:** discriminator/bảng cha–con cho IS-A; FK/bảng nối cho HAS-A; FK mang tên vai trò hoặc bảng gán vai trò cho PLAYS-A-ROLE.
6. **Viết ràng buộc có thể kiểm chứng:** PK/FK, UNIQUE, NOT NULL, CHECK và cơ chế xuyên bảng nếu cần; định nghĩa cách xử lý xóa, sửa, chuyển trạng thái.
7. **Thử phản ví dụ:** một User vừa mua vừa bán; một Product xuất hiện trong nhiều OrderLine; Order chưa có dòng; RoleAssignment hết hạn; subtype có thuộc tính không hợp lệ.
8. **Đánh giá tiến hóa:** thêm subtype, thêm vai trò, đổi quy tắc bội số, lưu lịch sử và thay đổi hệ quản trị có cần đổi định danh hoặc nhân bản thông tin không?

### Bài tập tự kiểm tra

**Câu 1.** Một trường học quản lý Person, Student, Teacher. Một Person có thể vừa học vừa dạy. Nên mô hình Student và Teacher như thế nào?

**Gợi ý:** Nếu Student/Teacher là **vai trò trong một học kỳ/chương trình**, dùng các quan hệ Enrollment và TeachingAssignment có ngữ cảnh và thời hạn. Nếu nghiệp vụ định nghĩa hồ sơ Student và Teacher với thuộc tính, quy tắc riêng, có thể dùng các subtype/hồ sơ chuyên biệt **cho phép chồng lấp**. Dù chọn cách nào, không tạo hai Person khác nhau cho cùng một người.

**Câu 2.** “Vehicle có Engine” có phải Vehicle IS-A Engine không? Nếu Engine có mã riêng và có thể được chuyển giữa nhiều Vehicle qua thời gian, cần lưu gì?

**Gợi ý:** Đây là **HAS-A**. Engine và Vehicle có hai định danh. Nên lưu quan hệ lắp đặt với khoảng thời gian hiệu lực; có thể có thuộc tính ngày lắp, ngày tháo và quy tắc “một engine chỉ nằm trong tối đa một vehicle tại một thời điểm”. Chỉ thêm một cột engine_id trên Vehicle sẽ khó giữ được toàn bộ lịch sử.

**Câu 3.** Hệ thống có User A vừa là người tạo vừa là người được giao Task X. Có cần hai bảng CreatorUser và AssigneeUser không?

**Gợi ý:** Không nhất thiết. Hai khóa ngoại creator_user_id và assignee_user_id cùng trỏ đến User có thể mô tả hai **vai trò**. Một CHECK cấm chúng bằng nhau chỉ hợp lý nếu nghiệp vụ yêu cầu không tự giao việc.

**Câu 4.** Một DigitalProduct được mua 100 lần. Có nên tạo 100 bản ghi DigitalProduct để biểu diễn 100 lần mua?

**Gợi ý:** Không. **DigitalProduct IS-A Product** mang một định danh sản phẩm; các lần mua được biểu diễn bằng **OrderLine** hoặc sự kiện giao dịch liên kết đến product_id. Tách định danh sản phẩm khỏi các thực thể giao dịch giúp tránh sao chép thuộc tính và giữ khóa tham chiếu ổn định.

## 11. Ghi nhớ

- **IS-A:** một thực thể là trường hợp chuyên biệt của một loại tổng quát, **giữ cùng định danh**.
- **HAS-A:** những thực thể hoặc thành phần **có quan hệ cấu trúc/liên kết**, với bội số và vòng đời phải được định nghĩa.
- **PLAYS-A-ROLE:** một thực thể **tham gia một ngữ cảnh dưới tư cách xác định**, có thể đồng thời có nhiều vai trò và thay đổi theo thời gian.

Việc phân biệt ba khái niệm giúp mô hình dữ liệu phản ánh đúng nghiệp vụ, chọn khóa và ràng buộc chính xác, tránh sao chép danh tính, đồng thời dễ chuyển đổi giữa lược đồ quan hệ, document, đồ thị và mô hình phân tích khi hệ thống phát triển.

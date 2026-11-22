# Chọn mức chi tiết sơ đồ theo đối tượng đọc và mục đích trao đổi

## 1. Một mô hình dữ liệu, nhiều cách trình bày

Trong module **DATABASE_DATA_MODELING**, người học rèn khả năng chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng: nhận diện thực thể, quan hệ, ràng buộc, chuẩn hóa, khóa, chỉ mục và cấu trúc lưu trữ; đồng thời so sánh mô hình quan hệ, document, graph và mô hình phân tích để lựa chọn giải pháp phù hợp. Ở chương **Tài liệu mô hình**, một kỹ năng quan trọng là **chọn mức chi tiết của sơ đồ dựa trên người đọc và điều cần thảo luận**.

Giả sử một sàn thương mại điện tử muốn hỗ trợ **đặt hàng, thanh toán từng phần và hoàn hàng**. Cùng một hệ thống, ba cuộc họp đặt ra ba câu hỏi rất khác:

- **Chủ sản phẩm và nhân viên nghiệp vụ:** “Một đơn hàng liên quan đến khách, các dòng sản phẩm và thanh toán như thế nào? Có thể thanh toán nhiều lần không?”
- **Nhà phân tích và kiến trúc sư:** “Các thực thể có khóa định danh nào? Quan hệ có lực lượng 1–N hay N–N? Trạng thái và lịch sử được biểu diễn ra sao?”
- **Lập trình viên và DBA:** “Tạo bảng nào, PRIMARY KEY/FOREIGN KEY nào, kiểu dữ liệu, index, CHECK, ràng buộc uniqueness và migration cụ thể ra sao?”

Nếu đưa toàn bộ tên cột, kiểu VARCHAR, index và khóa ngoại vào cuộc họp đầu tiên, người nghiệp vụ phải tìm logic đơn hàng trong hàng trăm chi tiết kỹ thuật. Nhưng nếu chỉ dùng hình chữ nhật “Đơn hàng → Thanh toán” khi review migration, đội kỹ thuật không thể biết thiết kế bảo đảm điều gì.

**Mức chi tiết tốt không phải mức nhiều thông tin nhất; đó là mức ít thông tin nhất nhưng đủ để người đọc trả lời chính xác câu hỏi cần quyết định.**

Bài này tập trung vào cách tạo **nhiều góc nhìn có kiểm soát từ cùng một mô hình**, thay vì dùng một ERD cực lớn cho mọi người và mọi mục đích.

### Mục tiêu học tập

Sau bài, người học có thể:

1. Phân biệt **mô hình dữ liệu** với **một sơ đồ trình bày mô hình**.
2. Chọn sơ đồ **khái niệm (conceptual)**, **logic (logical)** hoặc **vật lý (physical)** theo người đọc và quyết định cần đưa ra.
3. Chọn phạm vi (scope), độ hạt và chi tiết được phép ẩn mà không làm sai nghĩa.
4. Thể hiện thực thể, quan hệ, lực lượng, tính bắt buộc và các ràng buộc trọng yếu đúng mức.
5. Tạo bộ sơ đồ nhiều tầng từ cùng một tình huống thương mại điện tử, đồng bộ với data dictionary và DDL.
6. Viết chú giải, giả định, quy tắc nghiệp vụ, ghi chú chưa quyết định và phiên bản tài liệu.
7. Review thay đổi mô hình và tránh các sơ đồ gây ngộ nhận, lỗi kỹ thuật hoặc rò dữ liệu nhạy cảm.

## 2. Phân biệt mô hình, sơ đồ, góc nhìn và tài liệu

**Mô hình dữ liệu** là tập những quyết định về thực thể, thuộc tính, quan hệ, khóa, quy tắc toàn vẹn, thời gian và ý nghĩa nghiệp vụ. Mô hình không chỉ tồn tại dưới dạng hình vẽ.

**Sơ đồ (diagram)** là một **góc nhìn** hữu hạn của mô hình, được chọn và trình bày cho mục đích cụ thể.

**Tài liệu mô hình** thường bao gồm nhiều thành phần:

| Thành phần | Điều nó giải thích | Có thể thay bằng sơ đồ không? |
|---|---|---|
| Sơ đồ khái niệm | Những khái niệm nghiệp vụ chính và quan hệ | Không thay được đầy đủ mô tả quy tắc |
| Sơ đồ logic | Thực thể, thuộc tính quan trọng, PK/FK logic, cardinality | Không thay được ví dụ trường hợp biên |
| Sơ đồ vật lý | Bảng/collection/node/edge, kiểu cột, ràng buộc, chỉ mục | Không thay được migration/runbook |
| Data dictionary | Định nghĩa từng thực thể và trường | Không, hình vẽ thường không đủ chỗ |
| Business-rule catalog | Quy tắc, ngoại lệ, bất biến | Một số quy tắc khó thể hiện bằng đường nối |
| ADR/decision log | Lý do lựa chọn và phương án đã loại | Sơ đồ chỉ mô tả trạng thái, không đủ lý do |
| DDL/migration | Cấu trúc DB thực thi | Không tự chứng minh đúng yêu cầu nghiệp vụ |
| Test cases | Bằng chứng thiết kế đáp ứng các bất biến | Sơ đồ chưa phải kiểm thử |
| Ownership/lineage | Ai sở hữu dữ liệu và nó đi đâu | Cần góc nhìn riêng nếu nhiều hệ |

Một hình có thể **đúng về cú pháp** nhưng sai về nghiệp vụ. Ngược lại, một schema SQL có thể triển khai được nhưng vẫn không giúp chủ sản phẩm xác nhận ý nghĩa của “đơn hàng”, “hoàn tiền” và “trả hàng”.

### 2.1. Một sơ đồ không cần hiển thị mọi thứ

Không có yêu cầu hợp lý nào buộc **mỗi diagram phải chứa mọi bảng**. Phải có một bộ sơ đồ liên kết cùng nguồn mô tả được kiểm soát, trong đó mỗi sơ đồ trả lời một nhóm câu hỏi.

Chìa khóa là **không bỏ qua thông tin quyết định kết luận của người đọc**. Được ẩn index trong sơ đồ nghiệp vụ; không được ẩn việc một đơn có **nhiều lần thanh toán** nếu người nghiệp vụ đang xác nhận chính quy tắc ấy.

## 3. Ba mức chi tiết chính: conceptual, logical, physical

| Tiêu chí | **Khái niệm** | **Logic** | **Vật lý** |
|---|---|---|---|
| Câu hỏi | Nghiệp vụ có các khái niệm và quan hệ nào? | Dữ liệu được tổ chức và ràng buộc như thế nào? | Database cụ thể lưu và thực thi ra sao? |
| Người đọc chính | Product owner, domain expert, PM | BA, architect, developer, data engineer | DBA, backend engineer, data engineer, reviewer triển khai |
| Đơn vị hiển thị | Khái niệm/thực thể nghiệp vụ | Entity, thuộc tính, khóa, quan hệ | Table, column, type, index, constraint, partition |
| Định danh | Có thể ghi định danh nghiệp vụ nếu quan trọng | PK/BK/surrogate key theo mô hình | PRIMARY KEY, UNIQUE, FK, sequence/UUID cụ thể |
| Cardinality | Chỉ quan hệ cốt lõi, có thể ghi 1–N | Phải rõ 0..1, 1, 0..N, 1..N | FK/NOT NULL/UNIQUE và quy tắc bổ sung |
| Quy tắc | Ghi dạng câu nghiệp vụ | Gắn vào thực thể/quan hệ và invariants | CHECK/EXCLUDE/trigger/transaction/validator |
| Phụ thuộc DBMS | Không | Cố gắng trung lập DBMS | Có, ví dụ PostgreSQL, MongoDB |
| Có cần mọi cột? | Không | Chỉ thuộc tính cần chốt | Các cột liên quan phạm vi triển khai; danh mục đầy đủ ở data dictionary |
| Kết quả review | Thống nhất ngôn ngữ nghiệp vụ | Thống nhất cấu trúc dữ liệu | Đủ cơ sở triển khai và kiểm thử |

Ba mức là **một khung tư duy**, không phải ba file bắt buộc của mọi dự án. Một sơ đồ **logic thiên về nghiệp vụ** có thể dùng để thảo luận với người không viết SQL, miễn những chi tiết kỹ thuật không thiết yếu được ẩn và ký hiệu được giải thích.

### 3.1. Mức chi tiết không chỉ là số lượng bảng

Một sơ đồ có **năm thực thể nhưng 70 trường** có thể khó đọc hơn một sơ đồ có **12 thực thể với chỉ tên và quan hệ**.

Mức chi tiết còn gồm:

- Số thực thể hiển thị.
- Số thuộc tính mỗi thực thể.
- Số mối quan hệ và lực lượng/cực trị.
- Có hiện PK, FK, alternate key không.
- Có biểu diễn thời gian, trạng thái và lịch sử không.
- Có hiển thị điều kiện nghiệp vụ đặc biệt không.
- Có DDL, physical type, index, constraint không.
- Có hiện hệ thống nguồn/đích và quyền sở hữu dữ liệu không.

Vì vậy, hãy chọn **mức chi tiết theo câu hỏi**, không cố định số bảng hoặc số cột làm chuẩn chung.

## 4. Bắt đầu bằng câu hỏi và quyết định cần đạt được

Trước khi mở công cụ vẽ, ghi một câu:

> “Sau khi đọc sơ đồ này, nhóm **X** cần có khả năng quyết định/kiểm chứng **Y**.”

Ví dụ:

| Quyết định cần đạt | Người đọc | Góc nhìn nên ưu tiên |
|---|---|---|
| Một đơn có thể thanh toán nhiều lần? | Product owner, kế toán | Conceptual với cardinality và quy tắc minh họa |
| Đơn và thanh toán định danh độc lập? | BA, architect | Logical với business key và quan hệ |
| Refund có thể gắn một payment hay nhiều payment? | Nghiệp vụ hoàn tiền, backend | Logical theo workflow refund, có giới hạn ngữ nghĩa |
| Bảo đảm amount không âm bằng gì? | Backend, DBA | Physical DDL + test |
| Query báo cáo 3 năm phải partition thế nào? | DBA, data engineer | Physical + workload query và retention |
| Dữ liệu khách đi qua dịch vụ nào? | Security, DPO, architect | Context/data-flow + nhãn nhạy cảm, không phải ERD toàn bảng |
| Một KPI “số đơn” lấy từ đâu? | BI, analytics | Fact grain + conformed dimensions + lineage |
| Sửa category hồi tố ảnh hưởng báo cáo cũ? | Data architect, nghiệp vụ | Temporal logical view + timeline |
| Hai hệ thống có cùng source ID không? | Integration, architect | Boundary/identity mapping view |
| Schema migration có phá consumer cũ? | Developer, reviewer | Before/after physical + dependency/contract |

**Nếu chưa biết câu hỏi phải trả lời, thường chưa nên bắt đầu bằng sơ đồ vật lý đầy đủ.**

### 4.1. Đề bài sơ đồ phải có phạm vi thời gian và đối tượng

Ví dụ hai đề bài khác nhau:

- “Mô tả đơn hàng và thanh toán hiện tại cho đối tượng bán hàng.”
- “Kiểm chứng khóa và lịch sử thanh toán khi hoàn tiền nhiều lần, tính tại ngày T và theo thông tin hệ thống biết ở K.”

Đề bài thứ hai cần logic thời gian và audit mà đề bài thứ nhất không cần. Dùng chung một hình đơn giản cho hai trường hợp dễ che mất sự khác biệt cốt lõi.

## 5. Phân loại người đọc: trình bày đúng ngôn ngữ của họ

### 5.1. Người nghiệp vụ

Họ thường cần biết:

- Những đối tượng có ý nghĩa gì.
- Điều gì có thể hoặc không thể xảy ra.
- Cần thông tin nào để vận hành.
- Trường hợp biên nào quan trọng.
- Thay đổi sẽ tác động quy trình ra sao.

Nên dùng **tên nghiệp vụ**, câu chú thích ngắn, cardinality đơn giản và ví dụ cụ thể. Tránh nhồi GUID, byte length, index hoặc tên constraint không cần thiết.

Không bỏ qua quy tắc chỉ vì khó vẽ. Ví dụ:

> Một đơn có thể nhận nhiều lần thanh toán, nhưng tổng số tiền được ghi nhận hợp lệ không được tùy ý vượt số tiền phải thu.

Quan hệ 1–N mô tả được phần đầu; phần giới hạn tiền nên ghi chú thành rule để nghiệp vụ xác nhận.

### 5.2. Nhà phân tích và kiến trúc sư

Họ cần:

- Định nghĩa entity và grain.
- Khóa tự nhiên, alternate key, surrogate key.
- Cardinality và optionality.
- Phân tách nhiều-nhiều.
- Hệ quả chuẩn hóa/denormalization.
- Thời gian hiệu lực và những quan hệ thay đổi theo thời gian.
- Phạm vi bounded context và ownership.

Sơ đồ logic thường là góc nhìn trung tâm. Nên kèm **data dictionary** và danh sách giả định/chưa chốt.

### 5.3. Developer, DBA và data engineer

Họ cần:

- Table/column names và types.
- PK, FK, UNIQUE, NOT NULL, CHECK/EXCLUDE.
- Cột kiểm soát trạng thái và thời gian.
- Index, partition, cache/materialization khi có.
- Chiến lược migration, backfill và rollback.
- Query quan trọng, concurrency và performance evidence.

Sơ đồ vật lý là cần thiết, nhưng vẫn không thay DDL, test và runbook. Với schema lớn, nên tách sơ đồ theo subsystem và liên kết đến migration cụ thể.

### 5.4. Security/privacy và kiểm toán

Họ thường cần **data flow**, phân loại dữ liệu, nơi lưu bản sao, mục đích, quyền sở hữu, retention, điểm phát sinh xóa và kiểm soát truy cập.

Một ERD cho thấy Customer tham chiếu Order nhưng **không cho biết** email khách được truyền sang bên thứ ba nào. Cần một góc nhìn khác, có thể bổ sung nhãn **PII**, owner, retention; không công khai giá trị nhạy cảm trong sơ đồ.

### 5.5. Người mới tham gia dự án

Họ cần bản đồ tổng quan trước rồi mới đi sâu. Một tuyến đọc phù hợp:

~~~text
Context / domain map
        ↓
Conceptual model
        ↓
Logical model theo phân hệ
        ↓
Physical tables và data dictionary
        ↓
Migration, test, ADR
~~~

Dẫn người mới thẳng tới ERD 200 bảng thường làm tăng chi phí onboarding mà không cải thiện hiểu biết.

## 6. Bước 1: xác định biên hệ thống và phạm vi sơ đồ

Một sơ đồ dữ liệu chỉ có ích nếu người đọc biết **phần nào nằm trong và ngoài phạm vi**.

Ví dụ một hệ thương mại điện tử có:

- **Sales**: đặt và quản lý đơn.
- **Payments**: nhận và đối soát thanh toán.
- **Fulfillment**: giao hàng.
- **Catalog**: thông tin sản phẩm.
- **Identity**: tài khoản và chủ thể.
- **Analytics**: báo cáo và mô hình phân tích.

Một cuộc họp về đơn và thanh toán không nhất thiết phải đưa **tất cả** bảng của Catalog, Identity, Analytics vào hình. Nhưng không được diễn giải sai boundary khi một đối tượng thuộc dịch vụ khác.

~~~mermaid
flowchart LR
    U["Khách hàng"] --> S["Sales / Order"]
    S --> P["Payments"]
    S --> F["Fulfillment"]
    S --> C["Catalog"]
    S --> A["Analytics events"]
~~~

Sơ đồ trên là **góc nhìn ngữ cảnh/luồng phụ thuộc**, chưa phải ERD. Nó hữu ích để xác định ai sở hữu dữ liệu và điểm tích hợp.

### 6.1. Đừng nhầm quan hệ nghiệp vụ với FOREIGN KEY xuyên dịch vụ

Sales có thể lưu **customer_id** hoặc **payment_id** từ dịch vụ khác. Điều đó **không có nghĩa** có FK vật lý giữa hai database độc lập.

Trong sơ đồ conceptual, có thể vẽ “Đơn thuộc Khách” để thể hiện quan hệ nghiệp vụ. Ở physical view cần ghi:

~~~text
orders.customer_id: tham chiếu logic tới Identity
Không có FOREIGN KEY xuyên database.
Tính nhất quán được kiểm soát qua API/event/reconciliation.
~~~

Sự khác biệt này phải được thể hiện bằng chú giải/note rõ ràng, không vẽ một đường nối trông như FK thật rồi để reviewer suy ra sai.

### 6.2. Chọn phạm vi theo use case

Một use case nên có một **central entity/aggregate**. Ví dụ “Hoàn tiền từ payment” đặt PAYMENT/REFUND ở trung tâm, chỉ đưa ORDER và CUSTOMER vào nếu tác động đến quy tắc.

Nếu diagram không thể đọc ở kích thước thông thường và phải thu nhỏ đến mức tên không nhìn thấy, hãy cân nhắc tách thành **nhiều view cùng namespace**, không thu nhỏ chữ để cố giữ một trang.

## 7. Sơ đồ khái niệm: dùng để xác nhận ngôn ngữ nghiệp vụ

Đặt mục tiêu: **“Đúng thực thể và đúng quan hệ theo cách người nghiệp vụ hiểu.”**

Ví dụ:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : "đặt"
    ORDER ||--|{ ORDER_LINE : "gồm"
    PRODUCT ||--o{ ORDER_LINE : "được mua trong"
    ORDER ||--o{ PAYMENT : "được thanh toán bằng"
    PAYMENT ||--o{ REFUND : "có thể phát sinh"
~~~

Ở mức này không cần liệt kê 40 cột của ORDER. Nhưng sơ đồ đã cho thấy:

- Một khách có thể đặt nhiều đơn.
- Một đơn gồm ít nhất một dòng hàng **trong trạng thái nghiệp vụ đang xét**.
- Một sản phẩm có thể xuất hiện ở nhiều dòng đơn.
- Một đơn có thể có nhiều payment.
- Một payment có thể có nhiều refund.

**Lưu ý về vòng đời:** đơn vừa được tạo ở trạng thái draft có thể chưa có dòng hàng, tùy yêu cầu. Khi đó dùng **ORDER ||--o{ ORDER_LINE** và ghi rule “đơn chỉ được xác nhận khi có ít nhất một dòng”. Đừng giữ ký hiệu “ít nhất một” cho mọi trạng thái nếu nghiệp vụ cho phép đơn draft rỗng.

### 7.1. Câu hỏi quan trọng hơn cột dữ liệu

Ngay trên sơ đồ nên có một vùng **Quy tắc cần xác nhận**:

1. Có cho phép một đơn được thanh toán bởi nhiều giao dịch không?
2. Một payment có thể tài trợ nhiều đơn khác nhau không?
3. Refund có thể được hoàn một phần nhiều lần không?
4. Một dòng đơn giữ giá tại lúc mua hay luôn đọc giá hiện hành?
5. Khách có thể đặt đơn như guest hay mọi đơn bắt buộc có tài khoản?

Nếu câu trả lời mục 2 là “có”, quan hệ ORDER–PAYMENT dạng 1–N có thể không đủ: cần PaymentAllocation hoặc quan hệ N–N có số tiền phân bổ.

### 7.2. Không nhầm minh họa tình huống với mô hình đầy đủ

Sơ đồ conceptual **cố tình lược bớt** thuế, giảm giá, phí vận chuyển, tồn kho, sổ cái hoặc hệ thống anti-fraud. Thêm chú giải:

> Phạm vi: đặt hàng, thanh toán và hoàn tiền cơ bản. Chưa mô hình hóa thuế, kế toán và khuyến mại; các quan hệ được trình bày theo trạng thái đơn đã xác nhận.

Không có chú giải, người đọc có thể nghĩ các yếu tố bỏ qua đã bị loại khỏi thiết kế tổng thể.

## 8. Sơ đồ logic: từ khái niệm sang thực thể và quan hệ có thể kiểm chứng

Đặt mục tiêu: **“Mỗi hàng đại diện cho gì; nó được nhận diện và liên kết thế nào?”**

Đối với cùng ví dụ:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--o{ ORDER_LINE : contains
    PRODUCT ||--o{ ORDER_LINE : sold_as
    SALES_ORDER ||--o{ PAYMENT : receives
    PAYMENT ||--o{ REFUND : refunds

    CUSTOMER {
        uuid customer_id PK
        string customer_type
    }
    SALES_ORDER {
        uuid order_id PK
        uuid customer_id FK
        string order_number UK
        string order_status
        datetime placed_at
    }
    ORDER_LINE {
        uuid line_id PK
        uuid order_id FK
        uuid product_id FK
        int line_no
        decimal quantity
        decimal captured_unit_price
    }
    PRODUCT {
        uuid product_id PK
        string sku UK
        string product_name
    }
    PAYMENT {
        uuid payment_id PK
        uuid order_id FK
        string provider_transaction_ref UK
        decimal captured_amount
        string payment_status
    }
    REFUND {
        uuid refund_id PK
        uuid payment_id FK
        decimal refund_amount
        string refund_status
    }
~~~

Đây là **biểu diễn logic minh họa**, không phải DDL. Ví dụ nó chưa chỉ ra điều kiện đồng tiền, trạng thái hoàn tiền, nghiệp vụ multiple payment allocations và tài khoản guest.

### 8.1. Gắn grain vào từng thực thể

| Thực thể | Grain | Khóa chính logic | Bất biến chính |
|---|---|---|---|
| CUSTOMER | Một hồ sơ khách đã được nhận diện | customer_id | Cơ chế guest/merge cần chính sách |
| SALES_ORDER | Một đơn hàng | order_id | order_number duy nhất trong namespace quy định |
| ORDER_LINE | Một dòng hàng của một đơn | line_id | line_no duy nhất trong order |
| PRODUCT | Một SKU/sản phẩm thương mại theo định nghĩa | product_id | sku duy nhất trong catalog scope |
| PAYMENT | Một lần thanh toán đã được ghi nhận | payment_id | provider ref không bị ghi trùng theo provider |
| REFUND | Một lần/đề nghị hoàn gắn payment | refund_id | Không vượt số tiền được phép hoàn theo policy |

Quy tắc “refund không vượt payment đã thành công” thường **không thể biểu diễn chỉ bằng PK/FK đơn giản**, vì đó là tổng của nhiều hàng theo trạng thái. Cần business rule và giao dịch/kiểm thử riêng.

### 8.2. Xác định optionality trước khi đặt NOT NULL

Một guest order không có customer account hợp lệ có thể được mô hình hóa theo một trong các cách:

- customer_id nullable và thông tin liên hệ đơn được lưu theo chính sách.
- Một GuestCustomer entity có định danh riêng.
- Một identity reference thuộc loại account/guest.

Đây là **lựa chọn nghiệp vụ và dữ liệu**, không được tự quyết chỉ vì hệ ORM đòi FK NOT NULL.

### 8.3. Lực lượng tối thiểu và tối đa phải có căn cứ

Một đường nối 1–N chưa nói đủ nếu không biết **N có thể bằng 0 hay không**. Có hai loại quy tắc:

- **Ràng buộc cấu trúc**: một ORDER_LINE bắt buộc thuộc đúng một ORDER.
- **Ràng buộc theo trạng thái**: ORDER draft có thể có 0 dòng, ORDER confirmed phải có ít nhất 1 dòng.

Phần thứ hai nên ghi rõ thành rule, thường được bảo đảm trong workflow xác nhận đơn, không chỉ trên sơ đồ.

## 9. Sơ đồ vật lý: dữ liệu được lưu và bảo vệ bằng DBMS cụ thể

Đặt mục tiêu: **“Có thể triển khai, migration và review constraint nào?”**

Ở mức vật lý, tên cột phải khớp schema thực, kiểu dữ liệu và ràng buộc phải có ngữ nghĩa. Ví dụ PostgreSQL tối giản:

~~~sql
CREATE TABLE sales_order (
    order_id uuid PRIMARY KEY,
    tenant_id bigint NOT NULL,
    order_number text NOT NULL,
    order_status text NOT NULL
        CHECK (order_status IN (
            'DRAFT', 'CONFIRMED', 'CANCELLED', 'COMPLETED'
        )),
    placed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT statement_timestamp(),

    UNIQUE (tenant_id, order_number),
    UNIQUE (tenant_id, order_id)
);

CREATE TABLE order_line (
    line_id uuid PRIMARY KEY,
    tenant_id bigint NOT NULL,
    order_id uuid NOT NULL,
    line_no integer NOT NULL CHECK (line_no > 0),
    product_id uuid NOT NULL,
    quantity numeric(18, 3) NOT NULL CHECK (quantity > 0),
    captured_unit_price numeric(18, 2) NOT NULL
        CHECK (captured_unit_price >= 0),
    currency_code char(3) NOT NULL,

    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales_order(tenant_id, order_id),

    UNIQUE (tenant_id, order_id, line_no)
);

CREATE INDEX ix_sales_order_tenant_created
    ON sales_order (tenant_id, created_at DESC);

CREATE INDEX ix_order_line_by_order
    ON order_line (tenant_id, order_id);
~~~

Đây là **một đoạn DDL minh họa** tập trung vào ORDER và ORDER_LINE, chưa phải lược đồ đủ cho thanh toán/hoàn tiền. Chiều dữ liệu customer_id, chính sách sản phẩm, thuế, phí, trạng thái và lịch sử cần thiết kế tiếp theo quyết định nghiệp vụ.

### 9.1. Điều physical view bổ sung

- **uuid** cho PK kỹ thuật, không suy ý nghĩa từ thứ tự số.
- **tenant_id** và **UNIQUE(tenant_id, order_number)** cho mã hiển thị theo namespace.
- **CHECK** cho trạng thái, quantity và giá.
- **FK (tenant_id, order_id)** ngăn dòng của tenant khác trỏ vào order không đúng tenant qua khóa ghép.
- **INDEX** hỗ trợ đọc đơn gần đây và các dòng trong một đơn.
- **timestamptz** lưu thời điểm tuyệt đối, tách created_at với placed_at.

### 9.2. DDL còn chưa thay thế metric và transaction rule

Dù có CHECK(quantity > 0), hệ thống vẫn cần quy tắc:

- Có thể sửa quantity sau khi xác nhận đơn không?
- Giá đã chốt có được thay đổi khi catalog đổi giá không?
- Có được xác nhận đơn có 0 dòng không?
- Payment nào được tính là hoàn thành?
- Nhiều refund có được cộng vượt payment đã thành công không?
- Những thay đổi phải ghi audit/event nào?

Một sơ đồ vật lý với mọi cột và constraint **vẫn không thay thế workflow hoặc điều kiện liên bảng**. Hãy gắn link đến business-rule catalog và test cases.

## 10. Cùng một thực tế, ba mức sơ đồ phải nhất quán

Một nguyên tắc quan trọng: **ba mức không được mâu thuẫn nhau**.

Ví dụ quy tắc:

> “Một đơn có nhiều dòng, mỗi dòng thuộc đúng một đơn.”

Ba tầng biểu đạt khác nhau:

| Tầng | Biểu diễn |
|---|---|
| Conceptual | “Đơn gồm các dòng đơn”; cardinality 1–N |
| Logical | ORDER_LINE có order_id bắt buộc; FK logic tới SALES_ORDER |
| Physical | order_line.order_id NOT NULL + FOREIGN KEY |
| Kiểm thử | INSERT line có order_id không tồn tại phải bị từ chối |

Nếu conceptual thể hiện “một đơn có một thanh toán” nhưng logical lại cho ORDER 1–N PAYMENT, cần giải thích đây là thay đổi quy tắc đã chấp thuận hay là **lỗi tài liệu**. Không được âm thầm cho hai sơ đồ sống riêng và để người đọc tự đoán.

### 10.1. Mapping giữa các mức

Một mapping tối giản:

~~~text
Business concept: Đơn hàng
  Logical entity: SALES_ORDER
    Physical table: sales_order
      PK: order_id
      Business key: (tenant_id, order_number)

Business concept: Dòng hàng
  Logical entity: ORDER_LINE
    Physical table: order_line
      PK: line_id
      FK: (tenant_id, order_id)
      Alternate key: (tenant_id, order_id, line_no)
~~~

Khi tên vật lý khác tên nghiệp vụ, **mapping** là phần bắt buộc để tránh hiểu sai. Chỉ vì schema đặt tên sales_order mà nghiệp vụ gọi “đơn đặt hàng” không có nghĩa có hai thực thể khác nhau.

### 10.2. Conceptual không cần đồng nhất một-một với bảng

Một khái niệm “Thanh toán” có thể cần nhiều bảng **payment_attempt**, **payment_transaction**, **payment_allocation** và **payment_method_snapshot**. Sự khác biệt phản ánh việc phân rã mô hình, không nhất thiết là conceptual sai.

Ngược lại, một bảng dimension được denormalize có thể chứa thuộc tính của nhiều thực thể logic để tăng tốc phân tích. Phải ghi rõ **grain và mapping**, không coi một hình chữ nhật trên sơ đồ là một bảng vật lý trong mọi trường hợp.

## 11. Cardinality và optionality: thông tin nào không nên ẩn?

Đối với ERD, cardinality thường có tác động nghiệp vụ lớn hơn hàng chục thuộc tính ít được sử dụng.

Các ký hiệu thông dụng trong Crow's Foot có thể biểu thị:

| Ký hiệu ý tưởng | Ý nghĩa ở một đầu quan hệ |
|---|---|
| **0..1** | Không có hoặc có đúng một |
| **1** | Bắt buộc có đúng một |
| **0..N** | Không có hoặc có nhiều |
| **1..N** | Bắt buộc có ít nhất một |
| **N..M** | Quan hệ nhiều-nhiều, cần phân tích thực thể liên kết |

Ví dụ:

- Một **ORDER_LINE** bắt buộc thuộc một **ORDER**.
- Một **ORDER** ở trạng thái draft có thể chưa có **PAYMENT**.
- Một **PAYMENT** có thể có nhiều **REFUND**.
- Một **PRODUCT** có thể được gắn nhiều **CATEGORY** nếu doanh nghiệp cho phép.

Không tự vẽ “1..N” chỉ vì hiện dữ liệu có ít nhất một con; phải là **ràng buộc nghiệp vụ**, không phải quan sát tạm của dữ liệu mẫu.

### 11.1. Nhiều-nhiều phải được giải nghĩa

Giả sử một sản phẩm có thể thuộc nhiều danh mục:

~~~mermaid
erDiagram
    PRODUCT ||--o{ PRODUCT_CATEGORY : assigned_to
    CATEGORY ||--o{ PRODUCT_CATEGORY : contains
    PRODUCT {
        uuid product_id PK
        string sku
    }
    CATEGORY {
        uuid category_id PK
        string category_name
    }
    PRODUCT_CATEGORY {
        uuid product_id FK
        uuid category_id FK
        date valid_from
        date valid_to
        boolean is_primary
    }
~~~

Conceptual view có thể chỉ vẽ PRODUCT N–N CATEGORY. Logical view nên lộ **PRODUCT_CATEGORY** khi thảo luận:

- Quan hệ có thời gian hiệu lực không?
- Một sản phẩm có tối đa một danh mục chính tại một ngày không?
- Một danh mục có được xóa khi đang được tham chiếu không?

Physical view cần nêu PK/FK, UNIQUE/EXCLUDE hoặc transaction rule tương ứng.

### 11.2. Ẩn thực thể trung gian có thể làm sai nghĩa

Nếu **PAYMENT_ALLOCATION** chứa số tiền phân bổ từ payment sang order, bỏ nó khỏi sơ đồ đang xét quy tắc thanh toán có thể khiến người đọc tưởng một payment chỉ trả cho một order.

Chỉ được ẩn thực thể liên kết khi **nó không ảnh hưởng tới câu hỏi của audience**. Khi audience đang review phân bổ tiền, đó là thực thể trung tâm.

## 12. Chọn thuộc tính nào đưa lên hình

Một thực thể Customer có thể có hàng trăm thuộc tính, nhưng không phải cuộc họp nào cũng cần xem chúng.

### 12.1. Thuộc tính tối thiểu cho conceptual

Thường chỉ cần:

- Tên khái niệm.
- Một mô tả 1–2 dòng.
- Mã nghiệp vụ nếu nhận diện là tranh luận chính.
- Quy tắc/cardinality trọng yếu.

Ví dụ:

~~~text
Khách hàng
- Có thể có nhiều đơn.
- Khách guest cần chính sách riêng.
~~~

### 12.2. Thuộc tính nên xuất hiện ở logical

Ưu tiên:

- Primary key và business key.
- FK logic hoặc định danh quan hệ.
- Các thuộc tính quyết định grain.
- Thuộc tính trạng thái/loại nếu thay đổi quan hệ.
- Các mốc thời gian có hiệu lực.
- Những trường cần chốt định nghĩa.
- Alternate key và unique business rules.

Không nhất thiết hiển thị mọi metadata ETL (loaded_at, batch_id) khi nó không tác động tới quyết định mô hình logic.

### 12.3. Thuộc tính nên xuất hiện ở physical

Trong phạm vi review triển khai:

- Column name, database type, nullability.
- PK, FK, UNIQUE và tham chiếu.
- CHECK/EXCLUDE hoặc tên constraint liên quan.
- Index, partition key, generated column nếu tác động workload.
- Default value, collation, precision, timezone.
- Migration/backfill note khi có breaking change.

**Một hình vật lý không cần chứa từng index phụ và mọi column comment nếu người đọc có thể tra vào data dictionary hoặc DDL đáng tin cậy.** Mục tiêu vẫn là đọc được và review đúng.

### 12.4. Quy tắc lọc thuộc tính

Một thuộc tính nên có mặt khi nó phục vụ ít nhất một điều:

1. Phân biệt hai cách hiểu nghiệp vụ.
2. Thể hiện định danh hoặc ràng buộc.
3. Thể hiện chiều/thời gian quan trọng của use case.
4. Ảnh hưởng migration, chất lượng hoặc hiệu năng.
5. Được người đọc cần xác nhận.

Nếu không đạt, đặt ở data dictionary thay vì bắt mọi sơ đồ hiển thị.

## 13. Không chỉ chọn mức: còn phải chọn loại sơ đồ

Một ERD không giải quyết được tất cả các câu hỏi về dữ liệu.

| Câu hỏi | Góc nhìn phù hợp |
|---|---|
| Hệ thống có những đối tượng nào? | Conceptual data model |
| Những bảng/tài liệu/node nào liên kết? | Logical ERD/document/graph model |
| DB lưu khóa, chỉ mục, cột gì? | Physical schema/DDL view |
| Dữ liệu được chuyển giữa các dịch vụ thế nào? | Context/data-flow diagram |
| Trường nào đi từ nguồn đến KPI? | Lineage diagram/metric lineage |
| Một bản ghi đổi trạng thái qua các bước nào? | State machine/sequence diagram |
| Một thuộc tính có hiệu lực vào lúc nào? | Timeline/temporal model |
| Ai được truy cập loại dữ liệu nào? | Data classification/authorization matrix |
| Quy trình migration đổi schema ra sao? | Before/after physical + dependency map |
| Các thực thể trong graph có quan hệ nhiều bước? | Graph domain view |
| Một event được nhận rồi projection cập nhật ra sao? | Event flow/projection diagram |

### 13.1. Khi nào thêm sequence diagram?

Nếu câu hỏi là “khi hai worker cùng xác nhận đơn, ai giành quyền ghi?” thì ERD chỉ thể hiện cấu trúc tĩnh. Cần **sequence diagram** hoặc mô tả transaction để diễn giải:

- Lock hoặc version check.
- Transaction boundary.
- Retry.
- Outbox publish.
- Consumer idempotency.

Không cố ghi tất cả xử lý đồng thời bằng đường mũi tên ERD; chúng biểu diễn loại thông tin khác.

### 13.2. Khi nào thêm timeline?

Nếu bài toán có **valid_from/valid_to**, hai phiên bản SCD2 hoặc một correction hồi tố, một timeline thường dễ giải thích hơn một danh sách cột datetime:

~~~text
Sản phẩm P01:
[01/01, 01/08)   FOOD
[01/08, +∞)      GIFT

Bán ngày 15/07 → FOOD
Bán ngày 15/08 → GIFT
~~~

ERD cho biết có bảng PRODUCT_VERSION, nhưng timeline cho thấy chính xác **biên nào được bao gồm**, tránh hiểu nhầm ở ngày giao nhau.

## 14. Data dictionary bổ sung những gì mà hình không đủ chỗ?

Một tài liệu model tốt có **data dictionary** gắn với từng thực thể/thuộc tính.

Ví dụ rút gọn:

| Entity/field | Định nghĩa | Kiểu logic | Nullable | Quy tắc | Nguồn |
|---|---|---|---|---|---|
| sales_order.order_id | Định danh toàn cục của đơn | UUID | Không | Unique trong DB có thẩm quyền | Sales |
| sales_order.order_number | Mã hiển thị cho khách | String | Không | Unique theo tenant | Sales |
| sales_order.placed_at | Lúc đơn được xác nhận đặt | Instant | Có khi draft | Không mặc định bằng created_at | Sales |
| order_line.line_no | Vị trí dòng trong một đơn | Positive integer | Không | Unique theo order | Sales |
| order_line.captured_unit_price | Giá đơn vị đã chốt ở thời điểm bán | Money | Không | Không tự đọc giá catalog hiện tại | Sales/Catalog |
| order_line.quantity | Số lượng dòng | Decimal | Không | > 0; đơn vị theo SKU | Sales |
| order_line.currency_code | Đồng tiền của giá chốt | ISO code/string | Không | Cần nhất quán với amount | Sales |

Ngoài định nghĩa, data dictionary có thể ghi:

- Chủ sở hữu và người duyệt.
- Tên API/source.
- Unit/precision/format.
- Giá trị hợp lệ và default.
- Cardinality và thời gian hiệu lực.
- PII/sensitivity classification.
- Retention và masking.
- Lineage/quality checks.
- Deprecated/replaced-by và mốc migration.

**Không nên đặt toàn bộ các thông tin này vào box ERD.** Chúng cần xuất hiện ở nơi có thể tìm kiếm, version và review độc lập.

### 14.1. Gắn ID ổn định cho thực thể và rule

Ví dụ:

~~~text
ENT-SALES-ORDER      Đơn hàng
ENT-ORDER-LINE       Dòng đơn
REL-ORDER-HAS-LINE   Một đơn có nhiều dòng
BR-ORDER-001         Một dòng chỉ thuộc một đơn
BR-ORDER-002         Đơn CONFIRMED phải có ít nhất một dòng
BR-ORDER-003         line_no duy nhất trong đơn
~~~

Sơ đồ gắn link tới **BR-ORDER-003**, còn DDL có UNIQUE(tenant_id, order_id, line_no). Khi rule đổi, reviewer truy được ảnh hưởng tới cả sơ đồ, migration và test.

## 15. Quy tắc nghiệp vụ nào cần chữ thay vì ký hiệu?

Không phải mọi ràng buộc đều mô tả được bằng cardinality.

Ví dụ:

> “Tổng refund thành công của một payment không được lớn hơn phần tiền thực tế có thể hoàn.”

ERD PAYMENT 1–N REFUND không nói được giới hạn tổng. CHECK(refund_amount >= 0) trên một dòng cũng chưa bảo đảm tổng các dòng.

Một rule nên ghi:

~~~text
BR-REFUND-004

Áp dụng:
- Payment có trạng thái CAPTURED/SETTLED theo định nghĩa.
- Chỉ tính refund SUCCESS theo chính sách tương ứng.

Bất biến:
SUM(successful_refund_amount) <= refundable_payment_amount

Thi hành:
- Giao dịch có khóa/version hoặc reservation.
- Không cho hai refund đồng thời vượt hạn mức.

Kiểm chứng:
- Hai refund chạy đồng thời không vượt phần còn lại.
- Retry cùng refund request không tạo refund mới.
~~~

Sơ đồ logic có thể đánh dấu **rule BR-REFUND-004** cạnh PAYMENT–REFUND. Chi tiết thuật toán nằm ở tài liệu quy tắc và test.

### 15.1. Công thức không đồng nghĩa constraint được database thực thi

Một tài liệu ghi **amount = quantity × unit_price** không chứng minh DDL có generated column hoặc CHECK. Reviewer cần biết:

- **Business invariant** được xác nhận.
- **Enforcement location** là DB, service, ETL hay kết hợp.
- **Test evidence** cụ thể ở đâu.
- Có đường ghi nào bypass enforcement không.

Mỗi mức sơ đồ chỉ cần hiển thị phần phù hợp, nhưng tổng bộ tài liệu phải liên kết được những phần này.

## 16. Những chủ đề nhạy với thời gian cần góc nhìn riêng

Khi hệ thống có lịch sử, một đường nối có thể **đúng ở hiện tại nhưng sai ở quá khứ**.

Ví dụ nhân viên chuyển từ phòng ban A sang B ngày 01/08. Mô hình chỉ có:

~~~text
EMPLOYEE.department_id
~~~

sẽ trả phòng ban hiện tại B cho mọi sự kiện lịch sử. Nếu yêu cầu báo cáo “nhân viên thuộc phòng nào khi giao dịch xảy ra”, cần:

~~~text
EMPLOYEE_DEPARTMENT_HISTORY
(employee_id, department_id, valid_from, valid_to)
~~~

Ở sơ đồ conceptual, người nghiệp vụ chỉ cần thấy:

> Một nhân viên có thể thay đổi phòng ban theo thời gian; báo cáo lịch sử xét quan hệ tại ngày giao dịch.

Ở sơ đồ logical, cần entity lịch sử và cardinality. Ở physical, cần kiểu thời gian, [from,to), khóa và ràng buộc chống chồng lấn.

### 16.1. Timeline với khoảng nửa mở

~~~text
employee E1 → department A: [2026-01-01, 2026-08-01)
employee E1 → department B: [2026-08-01, +∞)
~~~

Ngày 01/08 chỉ thuộc B. Không vẽ hai mũi tên E1 → A và E1 → B mà bỏ thời gian rồi khiến người xem tưởng nhân viên có hai phòng ban cùng lúc.

### 16.2. Khi nào cần bitemporal view?

Nếu một thay đổi có thể được sửa **hồi tố**, yêu cầu có thể gồm hai câu hỏi:

- Trạng thái nào **có hiệu lực nghiệp vụ** tại ngày B?
- Hệ thống **đã từng biết gì** vào thời điểm K?

Sơ đồ logical cần hai trục **valid time** và **known/system time** nếu cả hai câu hỏi là bắt buộc. Người nghiệp vụ có thể hiểu qua một bảng 2 chiều/timeline; DBA cần mô hình range constraint và chiến lược ghi revision.

Không đưa bitemporal vào mọi sơ đồ chỉ vì schema có updated_at. **updated_at không tự là known-period history.**

## 17. Tài liệu cho mô hình quan hệ, document, graph và phân tích

Module DATABASE_DATA_MODELING không chỉ nói về bảng quan hệ. Khung **chọn mức chi tiết theo người đọc** vẫn áp dụng cho các cách tổ chức dữ liệu khác nhau.

### 17.1. Relational model

- Conceptual: Customer – Order – Product.
- Logical: ORDER_LINE giải quan hệ Order–Product, định nghĩa PK/FK, tính bắt buộc.
- Physical: bảng, cột, kiểu, UNIQUE, CHECK, FOREIGN KEY, index và partition.

### 17.2. Document model

Một document order có thể chứa các item lồng bên trong:

~~~json
{
  "orderId": "O-100",
  "status": "CONFIRMED",
  "items": [
    {
      "lineNo": 1,
      "sku": "P01",
      "quantity": 2,
      "capturedUnitPrice": 100000
    }
  ]
}
~~~

Đây chỉ là **shape minh họa**, không phải hợp đồng production về tiền tệ/kiểu số và quyền ghi.

- Conceptual: Order có OrderLines.
- Logical: items có thể embedded vì chúng cùng aggregate/order lifecycle; cần giải thích vì sao.
- Physical: JSON schema/validator, giới hạn document, index trên orderId/status, chiến lược update và version.

Nếu payment được xử lý độc lập và có nhiều event/partial captures, không mặc định nhúng toàn bộ lịch sử payment vào order chỉ vì công cụ document cho phép. Hãy quyết định theo **boundary, workload và nhất quán**.

### 17.3. Graph model

Một graph có Customer, Product, Category, quan hệ PURCHASED/INTERESTED_IN/BELONGS_TO:

- Conceptual: loại node và loại quan hệ.
- Logical: identity key, hướng cạnh, cardinality khi có, thuộc tính và thời gian hiệu lực trên cạnh.
- Physical: labels/types, constraints/indexes, query pattern, dữ liệu nào được cập nhật đồng thời.

Nếu một sản phẩm thuộc nhiều danh mục, không thể đơn giản hóa thành “product.category” đơn trị trong biểu đồ dùng để thảo luận multi-category.

### 17.4. Analytical/star schema

- Conceptual: doanh thu theo ngày, sản phẩm, cửa hàng.
- Logical: **grain fact**, measures, dimensions, conformed dimensions và tính cộng được.
- Physical: fact_sales_line, dim_date, dim_product, surrogate keys, SCD, partition, clustering và materialized aggregates.

Một dashboard nói “doanh thu” mà sơ đồ không cho biết **grain** và công thức **net vs gross vs after returns** có thể dẫn tới sai số dù hình rất đẹp.

### 17.5. Sự khác biệt quan trọng

Một sơ đồ mô hình dữ liệu không bắt buộc dùng **Crow's Foot** nếu công nghệ cần notation khác. Nhưng chú giải phải đủ để người đọc biết:

- Nút/hộp biểu diễn gì.
- Đường nối/cạnh có nghĩa gì.
- Quan hệ có hạn chế cardinality hay không.
- Dữ liệu nào được nhúng và dữ liệu nào chỉ tham chiếu.
- Phần nào là logic mô hình, phần nào là chi tiết triển khai.

## 18. Data flow và privacy view: hiển thị rủi ro mà không lộ bí mật

Sơ đồ có thể dùng để review **bảo vệ dữ liệu**, nhưng phải chọn loại thông tin đúng.

Một privacy-aware view hữu ích:

~~~mermaid
flowchart LR
    C["Customer UI"] --> S["Order Service"]
    S --> DB["Order DB / tenant-scoped"]
    S --> P["Payment Provider"]
    S --> E["Event Stream"]
    E --> A["Analytics Warehouse"]
~~~

Nên chú thích ở ngoài:

- Trường nào chứa thông tin định danh hoặc dữ liệu nhạy cảm.
- Ai là controller/processor hoặc owner nghiệp vụ.
- Mục đích truyền dữ liệu.
- Có chuyển dữ liệu sang đối tác ngoài không.
- Mức tối thiểu hóa, masking, encryption và retention.
- Quyền truy cập theo tenant và vai trò.
- Có snapshot/backup/cache nào khác chứa bản sao không.

### 18.1. Không đưa dữ liệu thật vào ví dụ sơ đồ

Không cần đưa tên, số điện thoại, số tài khoản, token hoặc email thật để giải thích quan hệ Customer–Order. Dùng giá trị giả định và tránh secret trong artifact.

### 18.2. Không dùng chỉ nhãn PII như một biện pháp bảo mật

Nhãn **PII** trên sơ đồ giúp reviewer thấy vị trí có rủi ro, nhưng nó không triển khai access control hay retention. Cần liên kết tới policy, DDL/API control, hệ thống audit và kiểm thử.

Sơ đồ đúng cho nhóm privacy phải giúp **chỉ ra nơi cần kiểm soát**, không phải tuyên bố hệ thống đã an toàn chỉ vì có nhãn.

## 19. Cách chú giải, màu sắc và nhóm hình

Một sơ đồ khó đọc đôi khi do không có **legend**, không phải do sai dữ liệu.

Ví dụ convention:

| Cách biểu diễn | Nghĩa đã thống nhất |
|---|---|
| Hình/hộp | Entity hoặc bảng tùy level |
| Đường nối liền | Quan hệ dữ liệu được định nghĩa |
| Đường nét đứt | Tham chiếu logic xuyên boundary, không FK vật lý |
| Ký hiệu Crow's Foot | Cardinality/optionality |
| Nhãn [External] | Dữ liệu thuộc hệ thống khác |
| Nhãn [SCD2] | Entity có phiên bản hiệu lực |
| Nhãn [PII] | Chứa thông tin cần phân loại/bảo vệ |
| Nhãn [Derived] | Projection/materialized/aggregate, không là nguồn sự thật |
| Note BR-xxx | Business rule nằm ngoài khả năng diễn đạt của line |

Màu sắc nên là **phụ trợ**, không phải kênh truyền thông tin duy nhất. Người đọc in đen trắng hoặc dùng công cụ hỗ trợ tiếp cận vẫn cần phân biệt nhờ chữ, ký hiệu và legend.

### 19.1. Bố cục nên phản ánh dòng đọc

- Đặt thực thể trung tâm gần giữa sơ đồ.
- Nhóm theo bounded context hoặc subject area.
- Hạn chế đường giao chéo không cần thiết.
- Dùng tên nhất quán và đủ lớn để đọc.
- Có tiêu đề, mục đích, scope, ngày/version và link tới dictionary.
- Nếu hình vượt khổ, tách theo use case thay vì giảm toàn bộ font.

### 19.2. Không dùng ký hiệu mơ hồ

Đường nối “CUSTOMER — ORDER” mà không có nhãn/cardinality dễ bị hiểu thành:

- Một khách có bao nhiêu đơn?
- Một đơn có thể không có khách?
- Khách là account hay chủ thể thật?
- Quan hệ là FK trong cùng DB hay chỉ là liên kết nghiệp vụ?

Ở conceptual, có thể đơn giản hóa nhưng vẫn cần tối thiểu nhãn “đặt” và một ghi chú về tính bắt buộc. Ở logical, cần cardinality hoặc một rule tương đương.

## 20. Tạo bộ sơ đồ “từ tổng quan đến chi tiết” như thế nào?

Một cấu trúc tài liệu dễ dùng:

~~~text
/Architecture/Orders
  00-context
    - boundary Sales / Payments / Catalog

  01-conceptual
    - order-payment-refund overview
    - các quy tắc nghiệp vụ chủ chốt

  02-logical
    - order-and-lines
    - payment-and-refunds
    - temporal-relationships

  03-physical
    - PostgreSQL order storage
    - payment constraints and indexes
    - migration before/after

  04-supporting
    - data dictionary
    - business rules
    - decision log
    - query examples
    - tests / lineage / privacy
~~~

Đây là **cấu trúc minh họa của bộ tài liệu**, không yêu cầu tạo những file này trong nhiệm vụ hiện tại.

### 20.1. Mỗi sơ đồ cần metadata tối thiểu

Một header tốt:

~~~yaml
diagram_id: DM-ORD-LOGICAL-01
title: "Đơn hàng và dòng đơn"
level: logical
audience: ["BA", "Backend", "Data Architect"]
purpose: "Xác nhận grain, khóa và cardinality của đơn hàng"
scope: "Sales bounded context, không gồm payment settlement"
model_version: "2.3"
status: "Reviewed"
source_of_truth: "Model repository / revision tag"
reviewed_at: "2026-11-20"
owner: "Sales Domain Team"
~~~

Trường metadata này là **ví dụ nội dung tài liệu**, không phải metadata phải thêm vào YAML của bài học. Một hệ thống quản lý tài liệu có thể lưu metadata ở nhiều dạng khác.

### 20.2. Link chứ không chép lại mọi chi tiết

Trên conceptual view, entity Order dẫn tới logical entity SALES_ORDER; logical dẫn tới physical table và dictionary; physical liên kết tới migration và test. Nếu cùng một rule được viết lại ở 7 nơi, rất dễ drift khi thay đổi.

Có thể dùng **ID rule duy nhất** và tạo các trình bày khác nhau theo audience để giữ cùng nguồn ý nghĩa.

## 21. Quy trình cộng tác và review sơ đồ

### 21.1. Trước workshop

1. Ghi câu hỏi cần quyết định và người duyệt.
2. Chọn một business scenario và vài ví dụ dữ liệu.
3. Phác scope/boundary.
4. Chọn level thích hợp, loại bỏ chi tiết không phục vụ câu hỏi.
5. Đánh dấu giả định và điều chưa chắc chắn.
6. Kiểm tra sơ đồ so với dictionary/version hiện có.

### 21.2. Trong workshop

Hỏi người nghiệp vụ:

- Có thực thể nào không đúng nghĩa?
- Trường hợp một-to-many này có ngoại lệ không?
- Có trạng thái nào khiến tính bắt buộc thay đổi không?
- Khi một đối tượng bị hủy/xóa, bản ghi liên quan phải ra sao?
- Có giai đoạn lịch sử nào mà quan hệ thay đổi không?
- Có hai cách hiểu khác nhau của cùng một thuật ngữ không?

Hỏi kỹ thuật:

- Khóa nào thực sự duy nhất và trong phạm vi nào?
- Quy tắc nào enforce ở database và quy tắc nào ở service?
- Nếu hai transaction chạy đồng thời, có lỗi nào vẫn lọt không?
- Migration/backfill có tác động tới dữ liệu cũ không?
- Query nào sẽ dùng cấu trúc này thường xuyên nhất?

### 21.3. Sau workshop

- Ghi quyết định và những phương án bị loại.
- Cập nhật sơ đồ đúng level.
- Ghi mapping tới rule, schema, migration.
- Đặt owner và trạng thái review.
- Xác nhận những quyết định còn mở (open questions).
- Lưu phiên bản/commit để so sánh thay đổi.

**“Đã vẽ xong” không đồng nghĩa “đã được thống nhất hoặc đã triển khai”.** Trạng thái tài liệu nên phân biệt Draft, Reviewed, Approved và Implemented/Deployed khi quy trình yêu cầu.

## 22. Phiên bản tài liệu và độ lệch với schema thực tế

Một sơ đồ chụp từ tháng trước có thể không phản ánh schema vừa deploy. Cần quy trình phát hiện và xử lý **documentation drift**.

### 22.1. Hai nguồn thay đổi

- **Design-first:** nhóm thống nhất mô hình rồi tạo migration.
- **Schema-first:** schema thay đổi trước, sau đó công cụ trích metadata để dựng physical view.

Cả hai đều có chỗ dùng. Nhưng **chỉ reverse-engineer schema không đủ** để hiểu lý do nghiệp vụ, bounded context hay ràng buộc ở service. Ngược lại, một sơ đồ thiết kế mà không được so với database production có thể trở thành tài liệu mong muốn chứ không phản ánh hệ thống thật.

### 22.2. Liên kết sơ đồ với migration

Ví dụ thay đổi:

> Từ phiên bản 2.3, cho phép nhiều payment cho một order.

Cần xác minh:

1. Conceptual view đổi từ giả định 1–1 sang 1–N.
2. Logical view xác nhận PAYMENT có định danh riêng và FK/order relationship.
3. Physical view loại UNIQUE(payment.order_id) nếu nó từng cấm nhiều payment, đồng thời giữ FK và index cần thiết.
4. Migration có backfill/chuyển đường ghi và kiểm tra rollback.
5. Business rules về tổng payment hợp lệ được cập nhật.
6. Test tạo hai payment cho cùng order thành công; retry không tạo payment trùng.
7. Consumer/report không còn giả định một order chỉ có một payment.

Một thay đổi được coi là hoàn tất về tài liệu khi **các view và rule đều khớp trạng thái được duyệt**, không phải chỉ sửa đường nối trên hình.

### 22.3. Diff theo ngữ nghĩa

Công cụ diff ảnh PNG thường không phân biệt thay đổi vị trí box với thay đổi cardinality. Review tốt nên ghi:

~~~text
Model change:
- SALES_ORDER -> PAYMENT: 0..1 chuyển thành 0..N.
- PAYMENT có payment_id làm identity riêng.
- Bổ sung business rule về tổng captured_amount.
- Tác động: API, schema, reporting, reconciliation.
~~~

Có thể dùng mô hình dạng text/Mermaid hoặc công cụ data modeling có semantic diff, nhưng vẫn cần reviewer hiểu nghiệp vụ.

## 23. Các lỗi thường gặp khi chọn mức chi tiết

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Một ERD 200 bảng cho tất cả người đọc | Người đọc mất câu hỏi trọng tâm | Tách view theo audience/use case |
| Sơ đồ nghiệp vụ hiện tất cả index/type | Che mất thực thể và quy tắc | Chuyển chi tiết sang physical view |
| Physical view chỉ có tên bảng | Không thể review constraint/migration | Thêm PK/FK/types và link DDL |
| Không ghi grain của entity/fact | Đếm trùng, chọn sai khóa | Thêm một câu grain trong dictionary |
| Vẽ FK xuyên database như FK thật | Người đọc tin có referential integrity mạnh | Phân biệt logical reference và physical FK |
| Ẩn bảng bridge khi bàn nhiều-nhiều | Gây sai giả định về số tiền/đếm | Hiện entity quan hệ, rule phân bổ |
| Ghi 1–N nhưng không rõ 0 hay 1 | Sai NOT NULL/workflow | Nêu optionality và state-specific rule |
| Không có timestamp semantics | Báo cáo lịch sử sai | Thêm temporal view + interval definition |
| Lặp nhiều định nghĩa rule ở nhiều hình | Tài liệu drift | Rule ID chung, link dictionary |
| Chỉ dùng màu phân biệt ý nghĩa | Khó đọc, khó truy cập | Chữ/legend/ký hiệu ngoài màu |
| Gộp mô hình dữ liệu và sequence xử lý | Không thấy ranh giới tĩnh/động | Dùng thêm sequence/state diagram |
| Dùng ảnh schema cũ làm source of truth | Reviewer duyệt sai trạng thái | Gắn version/migration và so schema |
| Không ghi quyết định chưa chốt | Giả định trở thành “đã duyệt” | Mark open question và owner |
| Copy dữ liệu thật lên sơ đồ | Rò thông tin nhạy cảm | Dùng ví dụ giả và phân loại dữ liệu |
| Chỉ reverse engineer DDL | Không thể biết ý nghĩa nghiệp vụ | Thêm conceptual/logical + ADR |
| Thêm bảng aggregate mà không ghi grain | KPI cộng sai qua các chiều | Thể hiện fact grain/measure contract |

## 24. Mẫu chọn level nhanh theo mức rủi ro quyết định

Một cách tự kiểm tra:

### Bước A — Ai sẽ hành động từ sơ đồ?

- Người nghiệp vụ **xác nhận khái niệm** → conceptual.
- Nhóm thiết kế **chốt danh tính, cấu trúc, ràng buộc** → logical.
- Nhóm kỹ thuật **triển khai, đo hiệu năng, migrate** → physical.
- Nhóm security **kiểm tra dữ liệu đi đâu và ai dùng** → data-flow/privacy view.
- Nhóm BI **kiểm tra metric và lineage** → fact/dimension + lineage view.

### Bước B — Người đọc có thể quyết định sai điều gì nếu thông tin bị ẩn?

Ví dụ nếu không hiện PAYMENT_ALLOCATION, họ có thể cho phép tổng thanh toán sai. Vậy phải hiện nó dù sơ đồ trông dày hơn.

Nếu không hiện tên index, chủ sản phẩm vẫn xác nhận được “một đơn nhiều payment”, có thể ẩn.

### Bước C — Có cần sơ đồ bổ sung?

- Có lịch sử → timeline/temporal view.
- Có workflow đồng thời → sequence/state view.
- Có nhiều service → context/data-flow view.
- Có migration → before/after physical view.
- Có nhiều loại mô hình dữ liệu → notation riêng cho relational/document/graph.
- Có KPI → metric/grain/lineage view.

### Bước D — Có đủ bằng chứng đi cùng?

Một sơ đồ tốt cần link tới định nghĩa, rule, test và version để người đọc kiểm chứng. Nếu diagram chỉ đẹp nhưng không truy được quyết định thiết kế, nó chưa phải tài liệu model hoàn chỉnh.

## 25. Bài thực hành: thiết kế ba sơ đồ cho nghiệp vụ giao và hoàn hàng

Một chuỗi bán lẻ muốn xây dữ liệu cho:

> “Khách tạo đơn nhiều dòng. Một đơn có thể được giao thành nhiều kiện, mỗi kiện có thể giao lại nhiều lần. Khách có thể trả một phần số lượng ở từng dòng; hoàn tiền có thể chia nhiều lần qua các payment. Nhóm nghiệp vụ cần xác nhận quy trình; nhóm kiến trúc cần xác nhận quan hệ; đội database cần migration PostgreSQL.”

Yêu cầu bổ sung:

- Đơn ở trạng thái DRAFT có thể chưa có dòng.
- Khi CONFIRMED, đơn phải có ít nhất một dòng.
- Cùng một dòng đơn có thể được chia vào nhiều shipment.
- Một shipment có thể chứa nhiều dòng đơn, với số lượng riêng.
- Một payment có thể chỉ thanh toán một phần tổng đơn.
- Refund chỉ được thực hiện trong phần tiền được phép hoàn.
- Khi trả hàng, phải giữ được dòng đơn và số lượng thực tế đã trả.
- Người dùng báo cáo muốn biết ai/điều gì có hiệu lực vào ngày giao hàng.
- Dữ liệu khách hàng phải được phân loại bảo vệ; không để thông tin thật trên hình.

### 25.1. Phần A — Conceptual cho product owner

Vẽ tối đa một góc nhìn tập trung vào:

~~~text
Customer
Order
Order Line
Shipment
Payment
Return
Refund
~~~

Đặt tên quan hệ bằng ngôn ngữ nghiệp vụ, chỉ ra những quan hệ có thể nhiều-nhiều hoặc đa lần. Ghi ít nhất năm câu hỏi xác nhận, chẳng hạn “Shipment có thể chứa dòng từ nhiều đơn không?” và “Một refund có thể thuộc nhiều payment không?”.

**Không cần** vẽ UUID, kiểu decimal hay tên index tại đây.

### 25.2. Phần B — Logical cho kiến trúc sư

Xác định:

- Grain và business key cho Order, Line, Shipment, ShipmentLine, Payment, Refund, ReturnLine.
- Quan hệ **ORDER_LINE ↔ SHIPMENT** có cần **SHIPMENT_LINE** chứa quantity không.
- Quan hệ **PAYMENT ↔ ORDER** có cần PAYMENT_ALLOCATION nếu payment dùng cho nhiều đơn không.
- Một shipment có những trạng thái nào và giao lại được biểu diễn bằng DeliveryAttempt hay version.
- Một return cần gắn với line gốc và có thể gắn shipment không.
- Cardinality/optionality cho DRAFT và CONFIRMED.
- Các rule liên bảng về tổng lượng giao, lượng trả, tiền hoàn.
- Mốc thời gian và liên kết lịch sử nào cần theo hiệu lực.

Kèm bảng rule ID và ít nhất hai timeline minh họa.

### 25.3. Phần C — Physical cho backend/DBA

Đưa ra thiết kế PostgreSQL có:

- PK và FK, bao gồm composite tenant key nếu dữ liệu nhiều tenant.
- UNIQUE cho source request và line number.
- CHECK cho quantity/amount.
- Index phục vụ query shipment theo order và payment/refund theo trạng thái.
- Transaction rule ngăn hai refund đồng thời vượt phần tiền còn lại.
- Migration strategy từ schema cũ chỉ có một shipment/order.
- Test dữ liệu đến muộn và trạng thái bị sửa hồi tố.
- Quyền và retention cho customer data.

Không cần giả định mọi rule đều thể hiện được bằng CHECK một hàng. Với rule tổng hợp nhiều hàng, nêu cách khóa, idempotency và kiểm thử.

### 25.4. Phần D — Phân phối bộ tài liệu

Tạo một bảng:

| Người nhận | Sơ đồ chính | Tài liệu kèm |
|---|---|---|
| Product owner | Conceptual | Business-rule questions |
| BA/architect | Logical | Data dictionary, temporal rules |
| Backend/DBA | Physical | DDL, migration, index/query tests |
| Analytics | Fact/lineage view | Metric contract và grain |
| Security/privacy | Data-flow view | PII classification, retention |
| QA | Logical + physical | Business invariants, test matrix |

**Tiêu chí đạt:** một kết luận nghiệp vụ được diễn đạt nhất quán ở các góc nhìn; sơ đồ nào cũng đủ để nhóm mục tiêu ra quyết định; chi tiết ẩn không làm sai giả định; dữ liệu có owner, version và evidence kiểm tra.

## 26. Checklist phê duyệt và kết luận

Trước khi phát hành một sơ đồ mô hình dữ liệu, hãy kiểm tra:

- **Audience:** người đọc thực sự là ai? Họ có hiểu notation đang dùng không?
- **Purpose:** câu hỏi/điều cần quyết định được viết rõ chưa?
- **Level:** conceptual, logical hay physical có phù hợp, hay cần data-flow/timeline khác?
- **Scope:** những bounded context và trường hợp bị loại có ghi rõ không?
- **Grain:** mỗi entity/fact đại diện cho một bản ghi loại nào?
- **Semantics:** thuật ngữ nghiệp vụ có định nghĩa nhất quán và dễ hiểu không?
- **Identity:** PK, business key, surrogate key và namespace có được đưa vào đúng tầng không?
- **Cardinality:** 0..1, 1, 0..N, 1..N và N–N có được diễn giải chính xác không?
- **Optionality:** ràng buộc theo trạng thái được ghi riêng nếu không thể biểu diễn bằng FK chứ?
- **Relationships:** không vẽ tham chiếu logic xuyên DB như FK vật lý thực thi chứ?
- **Business rules:** những giới hạn tổng số, thời gian và concurrency có rule ID/link đi kèm không?
- **Temporal:** valid time, known time, timezone và [from,to) có được thể hiện khi liên quan không?
- **Physical:** DB types, constraints, index, partition và migration có thể truy ngược tới schema/test không?
- **Privacy:** không dùng dữ liệu thật, có phân loại/retention và boundary đúng mức không?
- **Consistency:** conceptual/logical/physical có mâu thuẫn về cardinality hoặc ngữ nghĩa không?
- **Readability:** hình có tên rõ, legend và font đọc được, không phụ thuộc vào màu không?
- **Traceability:** từ rule sang entity, DDL, migration và test có thể lần theo không?
- **Version:** owner, model version, trạng thái duyệt và mốc cập nhật được ghi không?
- **Change impact:** thay đổi mô hình có làm hỏng API, consumer, báo cáo hoặc dữ liệu lịch sử không?
- **Verification:** đã kiểm chứng với ví dụ thực tế, dữ liệu biên và reviewer phù hợp chưa?

**Nguyên tắc cốt lõi:** sơ đồ không phải bản sao trang trí của database, mà là **công cụ trao đổi một quyết định mô hình hóa**. Người nghiệp vụ cần nhìn ra thực thể và quy tắc; nhà phân tích cần thấy grain, khóa và quan hệ; đội triển khai cần thấy bảng, constraint và cách vận hành. Chọn mức chi tiết đúng giúp bộ tài liệu vừa **dễ đọc**, vừa **đủ căn cứ kiểm chứng**, vừa **tiến hóa nhất quán** khi yêu cầu và lược đồ thay đổi.

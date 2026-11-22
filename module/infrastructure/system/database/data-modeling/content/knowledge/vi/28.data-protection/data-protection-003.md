# Tách thông tin định danh khỏi dữ liệu nghiệp vụ khi phù hợp

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Nhận diện **thông tin định danh trực tiếp**, **thông tin có thể liên kết để tái định danh** và dữ liệu nghiệp vụ vẫn có thể trở thành dữ liệu cá nhân trong một bối cảnh cụ thể.
- Quyết định **khi nào nên tách** dữ liệu định danh khỏi đơn hàng, giao dịch, sự kiện và kho phân tích; khi nào việc tách có thể làm hỏng ngữ nghĩa hoặc phát sinh phức tạp không cần thiết.
- Thiết kế **vùng lưu thông tin định danh** và **vùng dữ liệu nghiệp vụ** bằng khóa tham chiếu, quyền truy cập tối thiểu, hợp đồng dịch vụ và quy trình tái định danh được kiểm soát.
- Phân biệt **tách vật lý**, **tách logic**, **giả danh hóa (*pseudonymization*)**, **ẩn danh hóa (*anonymization*)**, **tokenization**, **mã hóa** và **băm**; không hứa mức bảo vệ mà giải pháp chưa đạt.
- Viết lược đồ PostgreSQL có ranh giới tenant, khóa ngoại, bản ghi địa chỉ giao hàng đã chốt và quyền đọc theo vai trò; thiết kế API tránh lộ PII khi không cần.
- Xử lý các luồng **xác nhận đơn, giao hàng, hỗ trợ, phân tích, đối soát, xóa/hạn chế dữ liệu, khôi phục và thay đổi lược đồ**.
- Đánh giá những rủi ro còn lại như liên kết qua mã ổn định, tổ hợp thuộc tính hiếm, bản sao trong log/CDC, backup và môi trường kiểm thử.

Bài thuộc chương **Bảo vệ dữ liệu** của **DATABASE_DATA_MODELING**. Mục tiêu của module là chuyển yêu cầu nghiệp vụ thành mô hình có thực thể, quan hệ, ràng buộc, khóa, chỉ mục và lược đồ vật lý rõ ràng, đồng thời lựa chọn cấu trúc quan hệ, document, đồ thị hay phân tích phù hợp. Bảo vệ dữ liệu là một phần của việc mô hình hóa: **đặt đúng dữ liệu vào đúng ranh giới truy cập** thường quan trọng không kém việc viết một truy vấn nhanh.

> Phạm vi bài là **thiết kế kỹ thuật và quy trình quản trị dữ liệu**, không phải kết luận về nghĩa vụ pháp luật trong một khu vực cụ thể. Yêu cầu bảo vệ, căn cứ xử lý, thời hạn giữ và quyền của chủ thể dữ liệu phải được xác định theo chính sách và quy định áp dụng cho hệ thống thực tế.

## 1. Vấn đề: một bảng đơn hàng chứa quá nhiều thứ

Một ứng dụng thương mại điện tử đang lưu:

~~~text
orders
  order_id
  customer_id
  customer_name
  customer_email
  customer_phone
  shipping_address
  product_id
  product_name_at_confirmation
  unit_price_at_confirmation
  quantity
  total_amount
  currency
  confirmed_at
  status
~~~

Bộ phận vận hành cần **order_id, status, thời điểm và số tiền** để tính khối lượng công việc. Bộ phận phân tích cần **dòng hàng, số lượng, tiền và thời gian** để đo doanh số. Dịch vụ giao vận cần **địa chỉ và số điện thoại của đúng kiện hàng đang được giao**. Chỉ một số tác vụ hỗ trợ khách hàng cần tra **email** hoặc liên hệ người nhận.

Nếu mọi bộ phận cùng được quyền SELECT bảng trên, mỗi truy vấn nghiệp vụ cũng có khả năng truy cập thông tin liên hệ và địa chỉ cá nhân. Khi sao chép bảng sang search index, kho phân tích hoặc log, phạm vi hiện diện của thông tin định danh lại tăng.

Mục tiêu tách dữ liệu không phải “ẩn cột để bảng đẹp hơn”, mà là:

1. **Giảm số hệ thống/người cần nắm dữ liệu định danh.**
2. **Cho phép nghiệp vụ vận hành với định danh kỹ thuật không trực tiếp nói người ấy là ai.**
3. **Tạo điểm kiểm soát** khi một tác vụ có lý do chính đáng phải liên kết ID với con người.
4. **Giảm hậu quả** nếu một read model, báo cáo hoặc tài khoản ứng dụng bị lộ.
5. **Giúp quản lý vòng đời** thông tin định danh khác với dữ liệu giao dịch phải lưu theo hợp đồng.

Một đích thiết kế thường có dạng:

~~~text
              Đăng ký / xác minh khách
                        |
                        v
             [Vùng thông tin định danh]
               subject_ref -> tên/email/phone
                        |
                   subject_ref
                        |
                        v
              [Vùng nghiệp vụ Order]
            order_ref, subject_ref, trạng thái,
            giá đã chốt, dòng hàng, thời điểm
                        |
             +----------+------------+
             |                       |
             v                       v
     [Tổng hợp doanh số]      [Dịch vụ giao vận]
     không cần email/phone    lấy địa chỉ đã chốt
     thường không cần         qua quyền/hợp đồng
     subject_ref              chuyên biệt
~~~

**subject_ref** là mã liên kết giả danh do hệ thống cấp. Việc nó không chứa tên/email **không làm dữ liệu trở thành ẩn danh**: tổ chức vẫn có thể liên kết về người thật qua bảng ánh xạ hoặc qua dữ liệu phụ trợ.

## 2. Phân loại định danh: không chỉ email và số điện thoại

### 2.1. Định danh trực tiếp và gián tiếp

| Nhóm | Ví dụ | Rủi ro / cách hiểu |
| --- | --- | --- |
| **Định danh trực tiếp** | Họ tên đi kèm địa chỉ, email cá nhân, số điện thoại, số giấy tờ | Có thể nhận ra hoặc liên hệ một người trực tiếp |
| **Định danh kỹ thuật ổn định** | customerId, subject_ref, deviceId, account ID | Có thể liên kết nhiều hành vi của cùng người, dù không chứa tên |
| **Thuộc tính liên kết/quasi-identifier** | Ngày sinh, khu vực rất nhỏ, thời gian giao dịch chính xác, vị trí, nghề nghiệp | Kết hợp với nguồn khác có thể nhận ra người cụ thể |
| **Dữ liệu giao dịch** | Đơn hàng, hành trình giao, lịch sử mua, mức chi tiêu | Có thể là dữ liệu cá nhân nếu gắn được với một chủ thể |
| **Dữ liệu nhạy cảm theo ngữ cảnh** | Ghi chú hỗ trợ, lịch sử địa điểm, kết quả đánh giá rủi ro | Có thể gây hại nếu lộ, kể cả khi không có tên |
| **Bí mật xác thực** | Password hash, token phiên, khóa API | Cần kiểm soát riêng; không lưu chung “cho tiện JOIN” |

Ví dụ một bảng phân tích đã bỏ tên và email nhưng còn **subject_ref** cố định, thời gian mua chính xác và mã cửa hàng. Nếu người có quyền xem có thể nối tới hệ thống khách hàng hoặc biết giao dịch hiếm, dữ liệu vẫn có thể nhận diện lại người.

Vì vậy, ta cần phân loại dựa trên **khả năng liên kết trong môi trường thực**, không chỉ nhìn xem có cột tên **full_name** hay không.

### 2.2. Khả năng nhận diện thay đổi theo bên nhận

- Đội Order có thể cần **subject_ref** để xác định khách sở hữu đơn.
- Đội Fraud có thể cần hành vi giữa nhiều đơn, nhưng không nhất thiết cần tên hiển thị.
- Dịch vụ Dashboard đôi khi chỉ cần **ngày × trạng thái × currency** và tổng số đơn.
- Bên thứ ba nhận một tập dữ liệu nhỏ có thể kết hợp với thông tin công khai khác; việc thiếu tên chưa bảo đảm an toàn.
- Người quản trị database với quyền cao có thể đọc cả bảng kinh doanh và bảng ánh xạ nếu chúng cùng một hệ và không có phân tách quyền hiệu quả.

**Quy tắc:** xác định ai có khả năng tiếp cận thông tin bổ trợ và có mục đích gì trước khi kết luận một tập dữ liệu “không định danh”.

## 3. Khi nào nên tách và khi nào không nên tách máy móc?

Tách phù hợp khi **một tập dữ liệu được đọc rộng rãi** nhưng chỉ một số rất nhỏ use case cần thông tin định danh.

| Tình huống | Hướng thiết kế thường phù hợp | Vì sao |
| --- | --- | --- |
| Dashboard tổng số đơn theo ngày | Chỉ dùng fact/aggregate không có email, địa chỉ | Không cần nhận diện từng người |
| Chấm điểm rủi ro dựa trên hành vi | Dùng subject_ref và đặc trưng được duyệt; tra định danh qua quy trình riêng khi cần | Giảm lượng PII trong pipeline phân tích |
| Liệt kê 20 đơn gần nhất cho khách đã đăng nhập | Order API trả đơn của đúng chủ thể, có thể không cần email | Quyền đọc và định danh người gọi được xử lý tại boundary |
| Nhắn thông báo giao hàng | Dịch vụ thông báo có thể cần phone/email qua token hoặc service liên hệ | Chỉ một consumer cần kênh liên hệ |
| In nhãn giao hàng | Bản chụp người nhận/địa chỉ theo kiện với quyền giao vận | Cần dữ liệu thật để hoàn thành nhiệm vụ |
| Lưu đơn giá đã chốt trên hóa đơn/đơn | Giữ **snapshot nghiệp vụ** tại giao dịch | Không được làm mất chứng cứ chỉ vì dữ liệu có thể gắn với cá nhân |
| Truy vấn hỗ trợ khách trên một cửa hàng rất nhỏ | Có thể tách logic bằng view/role trước, đánh giá chi phí hệ riêng | Tránh phức tạp hóa vượt lợi ích |
| Dữ liệu đã tổng hợp thực sự không thể liên kết cá nhân trong bối cảnh xét | Không cần giữ liên kết cá nhân nếu không có nhu cầu | Giảm tối đa khả năng tái định danh |

**Không nên** tách theo khẩu hiệu “mọi tên và địa chỉ phải biến mất khỏi mọi giao dịch” khi nghiệp vụ cần biết **địa chỉ giao được chấp nhận tại thời điểm chốt đơn**, hay khi có nghĩa vụ lưu chứng từ. Thay vào đó, đặt **snapshot giao hàng** trong vùng truy cập hạn chế, áp dụng thời hạn lưu và quy tắc hiệu chỉnh phù hợp.

**Không nên** tạo một dịch vụ định danh từ xa chỉ vì muốn “microservices”: nếu mọi request checkout phải gọi xuyên mạng nhiều lần và không có chiến lược lỗi, tính sẵn sàng có thể giảm. Mức tách phải tương xứng với rủi ro, kích thước hệ thống, khả năng vận hành và yêu cầu giao dịch.

### 3.1. Câu hỏi quyết định theo từng trường

Trước khi đặt một trường trong bảng nghiệp vụ, hãy hỏi:

1. Nó là **thông tin cần để ra quyết định nghiệp vụ**, **thông tin liên hệ**, **chứng cứ giao dịch** hay **giá trị tổng hợp**?
2. Người đọc bảng này có **cần biết chủ thể là ai** để thực hiện tác vụ không?
3. Trường cần **giữ nguyên tại thời điểm giao dịch** hay **theo hồ sơ hiện hành**?
4. Nếu xóa hoặc tách liên kết tới danh tính, các **bất biến nghiệp vụ** còn được kiểm chứng không?
5. Nếu lộ riêng bảng này, bên ngoài có thể liên kết với nguồn khác đến mức nào?
6. Việc tách có làm phát sinh **giao dịch xuyên database, độ trễ, chi phí đối soát hoặc sự cố khi dịch vụ định danh không hoạt động** không?
7. Trường có thuộc phạm vi **giữ dữ liệu, xóa/ẩn, kiểm toán và xuất dữ liệu** đặc biệt không?

Trả lời ở mức **field và use case** thường chính xác hơn mệnh lệnh “đưa tất cả PII ra một database”.

## 4. Mô hình tham chiếu: identity, business, delivery và analytics

Một phương án cân bằng cho thương mại điện tử:

~~~text
commerce.customer_subjects
  (tenant_id, subject_ref)          -- định danh kỹ thuật ổn định

pii.customer_contacts
  (tenant_id, subject_ref)          -- tên, email, phone hiện hành

commerce.orders
  (tenant_id, order_ref)
  subject_ref                       -- có thể NULL theo chính sách unlink
  order_state, confirmed_at, amount, currency

commerce.order_lines
  (tenant_id, order_ref, line_no)
  product_ref, quantity,
  unit_price_at_confirmation

pii.order_delivery_snapshots
  (tenant_id, order_ref)
  recipient_name, phone, address_at_confirmation

analytics.daily_order_metrics
  (business_date, currency, status)
  order_count, confirmed_amount
~~~

### 4.1. Vì sao cần tách danh tính, khách hàng nghiệp vụ và người nhận?

- **Customer/subject** là thực thể nghiệp vụ thực hiện giao dịch. Nó có thể tồn tại dưới một mã ổn định mà không chứa email.
- **Contact** là một cách liên hệ **hiện hành** có thể được sửa, xác minh, thu hồi hoặc xóa theo chính sách.
- **Recipient** là người nhận một kiện/đơn; có thể **khác người đặt**. Tự JOIN tới contact hiện hành của customer để in nhãn có thể gửi sai địa chỉ hoặc tiết lộ dữ liệu.
- **Order snapshot** giữ địa chỉ giao đã xác nhận hoặc phiên bản địa chỉ theo lần giao, nhưng cần quyền vận hành và vòng đời lưu giữ riêng.
- **Analytics** thường không cần tên người nhận. Nếu cần phân tích nhóm khách, xác định rõ liệu một mã giả danh ổn định có thực sự cần thiết hay có thể xuất tổng hợp an toàn hơn.

Tách danh tính khỏi nghiệp vụ **không có nghĩa xóa hết khóa liên kết**, mà là giữ **đúng khóa tham chiếu tối thiểu** và kiểm soát việc khôi phục danh tính.

### 4.2. Hai loại quan hệ phải được mô tả tường minh

| Quan hệ | Tính chất | Cách cập nhật |
| --- | --- | --- |
| **subject_ref → contact hiện hành** | Hồ sơ liên hệ có thể đổi theo thời gian | Cập nhật theo nguồn Customer/Identity |
| **order_ref → delivery snapshot đã chốt** | Sự thật giao vận tại mốc xác nhận | Giữ bản chụp, có revision/điều chỉnh có dấu vết khi được phép |
| **order_ref → subject_ref** | Liên hệ người đặt và nghiệp vụ | Chỉ hủy liên kết theo chính sách được duyệt, không tự làm mất dấu audit |
| **fact → analytics aggregate** | Dữ liệu dẫn xuất phục vụ chỉ số | Làm mới/đối soát theo grain và thời điểm |
| **subject_ref → danh tính thật** | Khả năng tái định danh | Chỉ truy cập qua quyền và mục đích được kiểm soát |

Nếu dùng một cột **address** ở mọi nơi mà không ghi **current vs at_confirmation**, một job “đồng bộ để dữ liệu giống nhau” có thể viết lại lịch sử giao hàng. Điều đó là lỗi mô hình hóa, không phải chỉ là lỗi bảo mật.

## 5. PostgreSQL: lược đồ tách logic với khóa và quan hệ rõ ràng

Ví dụ sử dụng **hai schema trong cùng một PostgreSQL**: **commerce** cho nghiệp vụ và **pii** cho dữ liệu định danh. Cách này giúp tách quyền và thiết kế, **nhưng không tạo ranh giới an toàn vật lý hoàn toàn**; chủ sở hữu database, người có quyền cao, backup chung và lỗi cấu hình vẫn có thể tiếp cận cả hai vùng.

SQL sau là một **mô hình minh họa**, không phải cấu hình an ninh hoàn chỉnh cho sản xuất. Các UUID được tạo bởi tầng ứng dụng từ nguồn ngẫu nhiên phù hợp hoặc bởi một cơ chế cấp ID được kiểm soát.

### 5.1. Định danh kỹ thuật không lộ tên/địa chỉ

~~~sql
CREATE SCHEMA commerce;
CREATE SCHEMA pii;

CREATE TABLE commerce.customer_subjects (
    tenant_id BIGINT NOT NULL,
    subject_ref UUID NOT NULL,
    subject_state TEXT NOT NULL
        CHECK (subject_state IN ('ACTIVE', 'RESTRICTED', 'CLOSED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, subject_ref)
);
~~~

**subject_ref** là mã ngẫu nhiên ổn định, được tạo và quản lý theo hợp đồng. Không nhúng email/số điện thoại vào ID, không dùng mã có ý nghĩa như ngày sinh + mã vùng. Tùy rủi ro, có thể cấp **mã khác nhau theo audience hoặc mục đích** để giảm khả năng nối dữ liệu chéo.

Dù không đọc được danh tính trực tiếp từ UUID, người có khả năng xem nhiều đơn cùng subject_ref vẫn có thể suy hành vi của một người. **Pseudonymized data vẫn phải được kiểm soát theo rủi ro cá nhân**.

### 5.2. Bảng định danh hiện hành chỉ dành cho bên có quyền

~~~sql
CREATE TABLE pii.customer_contacts (
    tenant_id BIGINT NOT NULL,
    subject_ref UUID NOT NULL,
    legal_name TEXT,
    email TEXT,
    phone_e164 TEXT,
    contact_updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, subject_ref),
    FOREIGN KEY (tenant_id, subject_ref)
        REFERENCES commerce.customer_subjects(tenant_id, subject_ref)
        ON DELETE RESTRICT
);
~~~

Bảng này giữ **contact hiện hành**, không phải lịch sử chứng từ giao dịch. Nếu quy định cần lưu lịch sử thay đổi liên hệ, phải thiết kế version/retention và quyền riêng; không tự ghi vô hạn log PII.

Trong ví dụ, email và phone là TEXT để làm rõ cấu trúc. Hệ thống thực cần validation/normalization, cơ chế xác minh, chính sách tìm kiếm và có thể **mã hóa ở tầng ứng dụng**. Không khẳng định việc đặt hai trường ở schema **pii** tự mã hóa chúng.

**PRIMARY KEY (tenant_id, subject_ref)** ngăn hai contact hiện hành cho cùng subject trong mô hình một contact. Nếu người dùng có nhiều email, nhiều điện thoại hoặc người nhận khác, grain phải đổi thành một contact method/record với khóa riêng. Không ép nghiệp vụ nhiều giá trị vào một trường TEXT phân cách bằng dấu phẩy.

### 5.3. Bảng nghiệp vụ không chứa tên/email mặc định

~~~sql
CREATE TABLE commerce.orders (
    tenant_id BIGINT NOT NULL,
    order_ref UUID NOT NULL,
    subject_ref UUID,
    order_state TEXT NOT NULL
        CHECK (order_state IN (
            'CONFIRMED', 'PROCESSING', 'SHIPPED',
            'DELIVERED', 'CANCELLED'
        )),
    confirmed_at TIMESTAMPTZ NOT NULL,
    confirmed_amount NUMERIC(18, 2) NOT NULL
        CHECK (confirmed_amount >= 0),
    currency CHAR(3) NOT NULL,
    PRIMARY KEY (tenant_id, order_ref),
    FOREIGN KEY (tenant_id, subject_ref)
        REFERENCES commerce.customer_subjects(tenant_id, subject_ref)
        ON DELETE RESTRICT
);

CREATE TABLE commerce.order_lines (
    tenant_id BIGINT NOT NULL,
    order_ref UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_ref UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_confirmation NUMERIC(18, 2) NOT NULL
        CHECK (unit_price_at_confirmation >= 0),
    PRIMARY KEY (tenant_id, order_ref, line_no),
    FOREIGN KEY (tenant_id, order_ref)
        REFERENCES commerce.orders(tenant_id, order_ref)
        ON DELETE CASCADE
);

CREATE INDEX ix_orders_by_subject_recent
    ON commerce.orders (
        tenant_id, subject_ref, confirmed_at DESC, order_ref DESC
    );
~~~

**Grain và bất biến:**

- Mỗi **orders** là một đơn trong một tenant.
- Mỗi **order_lines** là một dòng đơn xác nhận, định danh bằng **(tenant_id, order_ref, line_no)**.
- **confirmed_amount** là số tiền ở grain đơn; không SUM trường này sau JOIN nhiều order_lines nếu không tổng hợp đúng cấp.
- **unit_price_at_confirmation** là giá đã chốt, không đồng bộ về giá danh mục hiện hành.
- **subject_ref** trong orders cho phép truy vấn đơn theo chủ thể nhưng có thể được làm **NULL** qua một quy trình hủy liên kết có phê duyệt, nếu nghiệp vụ và nghĩa vụ lưu giữ cho phép. Không xóa/NULL tùy tiện để vượt qua nghĩa vụ kiểm toán.
- Khóa ngoại composite giữ đúng **tenant_id** khi liên kết, giảm nguy cơ tham chiếu nhầm tenant do thiết kế.
- **ON DELETE CASCADE** ở order_lines chỉ diễn đạt quan hệ phụ thuộc khi chủ nguồn quyết định xóa một order. **Không phải** chính sách tự động xóa chứng từ giao dịch; việc xóa order phải được kiểm soát theo quy trình và retention.

### 5.4. Địa chỉ giao đã chốt ở vùng hạn chế

~~~sql
CREATE TABLE pii.order_delivery_snapshots (
    tenant_id BIGINT NOT NULL,
    order_ref UUID NOT NULL,
    recipient_name TEXT NOT NULL,
    recipient_phone TEXT,
    address_line1 TEXT NOT NULL,
    city TEXT NOT NULL,
    country_code CHAR(2) NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, order_ref),
    FOREIGN KEY (tenant_id, order_ref)
        REFERENCES commerce.orders(tenant_id, order_ref)
        ON DELETE CASCADE
);
~~~

Bảng này là **snapshot tại sự kiện giao dịch**, khác **pii.customer_contacts** hiện hành. Thay đổi địa chỉ mặc định không được tự viết lại **order_delivery_snapshots**. Nếu đơn có nhiều lần giao, nhiều kiện hoặc đổi địa chỉ sau xác nhận được phép, grain có thể là **(tenant_id, order_ref, delivery_revision)** hoặc **shipment_ref**, không còn một hàng mỗi order.

Đây là ví dụ cho **đơn hàng vật lý cần giao**. Với đơn kỹ thuật số, bản ghi giao nhận có thể không cần tồn tại. Khi địa chỉ đầy đủ không còn cần cho vận hành hay chứng từ, phải xem xét vòng đời xóa/ẩn theo chính sách thay vì giữ mãi vì “snapshot là bất biến”.

### 5.5. Đâu là phân tách logic, đâu là bảo đảm kiểm soát thực tế?

Việc đặt bảng trong schema khác nhau chỉ là **tổ chức tên và quyền**. Nếu cùng một tài khoản ứng dụng được quyền SELECT cả **commerce.orders** và **pii.customer_contacts**, nó vẫn JOIN được hai vùng. Nếu DBA có quyền sao lưu toàn database, backup có thể chứa cả thông tin nghiệp vụ và định danh.

Mô hình có ý nghĩa bảo vệ khi đi kèm:

- **Vai trò database và quyền trên bảng/cột** được cấp tối thiểu.
- **Service API** giới hạn chức năng tái định danh, yêu cầu quyền theo đối tượng và mục đích.
- **Không xuất dữ liệu định danh** sang projection hoặc kho phân tích khi không cần.
- **Quản lý key, backup, log, môi trường kiểm thử** theo ranh giới thực tế.
- **Kiểm thử và kiểm toán** các đường truy cập trực tiếp/gián tiếp tới dữ liệu.

## 6. Truy vấn nghiệp vụ không cần JOIN tên/email

Ví dụ dashboard cần tổng giá trị đơn xác nhận theo ngày nghiệp vụ Việt Nam và tiền tệ, không cần biết khách là ai:

~~~sql
SELECT
    (confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS business_date,
    currency,
    COUNT(*) AS order_count,
    SUM(confirmed_amount) AS confirmed_order_value
FROM commerce.orders
WHERE order_state IN (
    'CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED'
)
  AND confirmed_at >= $1::TIMESTAMPTZ
  AND confirmed_at <  $2::TIMESTAMPTZ
GROUP BY
    (confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE,
    currency
ORDER BY business_date, currency;
~~~

Truy vấn không cần bảng **pii** và cũng không cần trả **subject_ref**. Dữ liệu đầu ra là giá trị đơn **đã xác nhận**, **không tự đồng nghĩa doanh thu đã thu**; hoàn tiền, trạng thái, thuế, giảm giá và thời điểm ghi nhận phải có định nghĩa riêng.

Không cộng thẳng VND và USD. Với cùng currency, SUM vẫn phải được tính trên **grain đơn**. Nếu JOIN với nhiều dòng rồi SUM **confirmed_amount**, số tiền ở grain đơn có thể bị nhân theo số dòng.

### 6.1. Trang danh sách đơn cá nhân chỉ cần một phần dữ liệu

Một API “đơn gần đây của tôi” có thể lấy:

~~~sql
SELECT
    order_ref,
    order_state,
    confirmed_at,
    confirmed_amount,
    currency
FROM commerce.orders
WHERE tenant_id = $1
  AND subject_ref = $2::UUID
ORDER BY confirmed_at DESC, order_ref DESC
LIMIT 20;
~~~

Ở đây:

- **$1** phải đến từ tenant đã được xác thực.
- **$2** là subject_ref được dịch vụ Identity/Authorization ánh xạ từ **principal hiện tại**, **không** lấy nguyên từ query string do client tự chọn.
- Service chỉ trả **order_ref, trạng thái, thời điểm và tiền**, không trả subject_ref nếu màn hình không cần.
- Nếu một khách có nhiều tài khoản hợp lệ hoặc chia sẻ quyền xem đơn, quan hệ sở hữu phải được định nghĩa bởi nghiệp vụ và authorization, không chỉ so một UUID.

**Không được dùng** việc UUID khó đoán thay cho kiểm tra quyền. Thay đổi ID trong URL vẫn có thể tạo lỗi truy cập trái phép nếu backend không kiểm tra tenant và chủ sở hữu.

### 6.2. Khi cần tái định danh, gọi đúng năng lực được ủy quyền

Ví dụ nhân viên hỗ trợ cần gửi email liên quan một đơn cụ thể. Một luồng có thể là:

~~~text
Support user -> Support Service
    |
    | Xác thực role, tenant, mục đích và quyền xem đơn
    v
Order Service -> xác minh order_ref, trạng thái, subject_ref
    |
    | Request tới Contact Service: purpose=ORDER_SUPPORT
    | truyền subject_ref qua kênh nội bộ xác thực
    v
Contact Service
    | Kiểm tra chính sách, ghi audit
    | Chỉ trả email/phone cần cho tác vụ
    v
Support Service -> thực hiện liên hệ, giới hạn log/caching
~~~

**Không tự động trả mọi dữ liệu Contact**. Nếu workflow chỉ cần gửi thông báo, Contact Service có thể thực hiện gửi thay vì trả email trực tiếp cho Support Service; đây là phương án giảm số nơi nhìn thấy định danh.

Nếu Contact Service không sẵn sàng, ứng dụng phải có hành vi rõ: retry có kiểm soát, xếp hàng tác vụ, hoặc báo chưa thể liên hệ. **Không chuyển sang đọc bảng pii bằng một tài khoản toàn quyền** như cách xử lý sự cố mặc định.

## 7. Quyền database: tách vai trò nhưng không ảo tưởng về schema

Giả sử đã tạo các role **commerce_reader**, **contact_reader** trong quy trình cấp quyền chuẩn của tổ chức. Quy tắc minh họa:

~~~sql
-- Hạn chế đường vào mặc định của schema định danh.
REVOKE ALL ON SCHEMA pii FROM PUBLIC;

-- Chỉ tài khoản được cấp quyền mới có USAGE và SELECT.
GRANT USAGE ON SCHEMA commerce TO commerce_reader;
GRANT SELECT (
    tenant_id, order_ref, order_state,
    confirmed_at, confirmed_amount, currency
) ON commerce.orders TO commerce_reader;

GRANT USAGE ON SCHEMA pii TO contact_reader;
GRANT SELECT (
    tenant_id, subject_ref,
    legal_name, email, phone_e164
) ON pii.customer_contacts TO contact_reader;
~~~

Trong hệ thật cần xét quyền đã có trước đó, quyền schema/table/column, role inheritance, default privileges cho bảng mới, quyền owner, chức năng có **SECURITY DEFINER**, row-level security và tài khoản migration. **REVOKE trên schema không tự thu hồi mọi quyền bảng đã tồn tại**; muốn kiểm soát đầy đủ phải kiểm tra tất cả đường cấp quyền và khả năng gọi hàm/view.

Chỉ grant SELECT cột cũng **không tự bảo vệ tenant**. Nếu commerce_reader có thể chạy SQL tự do và nhìn tất cả tenant qua bảng orders, đây vẫn là quyền quá rộng cho một ứng dụng đa tenant.

### 7.1. Row-level security và giới hạn của nó

PostgreSQL cho phép chính sách RLS theo tenant, ví dụ đối với một role truy vấn chuyên biệt:

~~~sql
ALTER TABLE commerce.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE commerce.orders FORCE ROW LEVEL SECURITY;

CREATE POLICY commerce_orders_tenant_read
ON commerce.orders
FOR SELECT TO commerce_reader
USING (
    tenant_id =
      NULLIF(current_setting('app.tenant_id', true), '')::BIGINT
);
~~~

Một backend đáng tin có thể đặt **app.tenant_id** trong transaction sau khi xác thực principal và tenant, rồi truy vấn bằng role bị RLS ràng buộc. **Nhưng đây không phải hàng rào độc lập nếu client có thể tự chạy SQL hoặc tự đặt GUC**: một role có quyền SET giá trị tùy ý có thể giả mạo tenant. Phải bảo vệ đường vào, không cho user tùy ý chạy SQL với role ấy, và có thể dùng mô hình phân quyền mạnh hơn khi rủi ro yêu cầu.

RLS cũng có các ngoại lệ/đường quyền như superuser, quyền **BYPASSRLS**, owner trong một số cấu hình và quyền thông qua view/function; **FORCE ROW LEVEL SECURITY** không biến nó thành bảo vệ chống mọi tài khoản đặc quyền. Cần kiểm chứng trên đúng kiến trúc và phiên bản PostgreSQL triển khai.

Dù RLS chính xác, response/API vẫn cần **kiểm tra quyền theo đối tượng và mục đích**. Được quyền đọc một đơn không mặc nhiên được quyền xem số điện thoại của người nhận.

### 7.2. Tách trong cùng database hay tách sang dịch vụ riêng?

| Mức tách | Ví dụ | Lợi ích | Chi phí/giới hạn |
| --- | --- | --- | --- |
| **Cột và DTO có allowlist** | Không trả email trong API Order | Ít thay đổi, giảm lộ qua response | Role có SELECT bảng vẫn thấy PII |
| **Bảng/schema riêng cùng DB** | pii.customer_contacts và commerce.orders | Quyền và retention rõ hơn, vẫn có FK/transaction | DBA/backup và cấu hình quyền vẫn là điểm chung |
| **Database riêng** | Contact DB và Order DB | Giảm phạm vi tài khoản/backup, điều khiển truy cập độc lập | Không có FK xuyên DB mặc định; đồng bộ và đối soát phức tạp |
| **Dịch vụ định danh/vault** | API tra contact có kiểm soát và audit | Chặn tái định danh tại một điểm, có thể thực hiện hành động thay vì trả PII | Độ trễ, sẵn sàng, chi phí vận hành và tích hợp |
| **Tách khóa mã hóa/miền an ninh** | Dữ liệu liên hệ được mã hóa ở tầng ứng dụng, key quản lý riêng | Giảm tác động khi chỉ lộ bản sao database | Key management phức tạp; không giải quyết lộ tại điểm giải mã |

Không có mức nào là “chuẩn chung” cho mọi sản phẩm. **Tách vật lý và tách logic đều cần quản trị quyền**, và tách nhiều nơi có thể tăng các bản sao ngoài kiểm soát nếu luồng tích hợp không được thiết kế.

## 8. Giả danh hóa, tokenization, băm, mã hóa và ẩn danh hóa

Các thuật ngữ dễ bị dùng lẫn, dẫn đến đánh giá sai mức độ bảo vệ.

### 8.1. Pseudonymization: thay mã định danh, còn khả năng liên kết

**Giả danh hóa** thay thông tin định danh trực tiếp bằng mã khác, ví dụ:

~~~text
Khách: subject_ref = "6d03...e2c" (UUID ngẫu nhiên)
Identity mapping: subject_ref -> email, tên, phone
Order data:       subject_ref -> các đơn đã mua
~~~

Nếu mapping còn tồn tại, đơn hàng có thể liên kết về người. Ngay cả khi mapping bị xóa, dữ liệu chi tiết và các nguồn khác vẫn có thể cho phép suy danh tính. **Đừng gọi pseudonymized data là anonymous**.

Lợi ích chủ yếu là **giới hạn ai có khả năng nhận diện**, không phải cam kết “không ai có thể tái định danh”.

### 8.2. Tokenization: mã thay thế và nơi giữ ánh xạ

Một **token ngẫu nhiên** không mang nghĩa có thể được ánh xạ tới giá trị gốc tại một vault:

~~~text
payment_contact_token: "tok_..." (không phải email)
          |
          v
Token vault -> email hoặc kênh gửi được bảo vệ
~~~

Token có thể **khác nhau theo consumer/mục đích** để hạn chế nối dữ liệu. Thiết kế phải xác định:

- Ai cấp token và đảm bảo không trùng?
- Token ổn định trong bao lâu?
- Một token có thể dùng để tìm lại gì?
- Ai có quyền giải token, đọc dữ liệu hay chỉ ra lệnh gửi?
- Token bị lộ có thể bị lạm dụng như bearer credential không?
- Khi thu hồi, rotate hoặc xóa mapping, các consumer xử lý thế nào?

Tokenization và pseudonymization có thể giao thoa về kỹ thuật. Điểm chính không phải tên gọi, mà là **khả năng đảo ngược/liên kết, nơi giữ mapping và cơ chế kiểm soát quyền**.

### 8.3. Băm định danh: cẩn thận với email và số điện thoại

Một lựa chọn thường sai:

~~~text
customer_hash = SHA256(lowercase(email))
~~~

Email/số điện thoại thường có **không gian giá trị đoán được**. Nếu một bên có thể thử danh sách email rồi so hash, giá trị không tự trở thành ẩn danh. Dùng cùng một hash không khóa ở mọi dataset còn tạo **khóa nối dữ liệu xuyên hệ**.

Khi thật sự cần một **chỉ mục tra cứu xác định** mà không lưu plaintext trong index, có thể cân nhắc **HMAC với khóa bí mật và quy tắc chuẩn hóa rõ**, nhưng:

- Vẫn là dữ liệu có thể liên kết; **không phải ẩn danh hóa**.
- Key phải được quản lý và phân quyền độc lập, có chiến lược rotation.
- Cùng input/cùng key cho cùng output, có thể tạo khả năng nối không mong muốn.
- Thay đổi quy tắc chuẩn hóa email/phone có thể tạo mismatch.
- Nếu người có quyền sử dụng HMAC làm oracle cho mọi input tùy ý, họ có thể thử danh sách và lạm dụng quyền.
- Nếu cần tìm kiếm gần đúng, HMAC không giải quyết bài toán tự nhiên; tìm kiếm phải được thiết kế riêng.

Băm mật khẩu là bài toán khác (thường đòi hàm băm mật khẩu chuyên dụng với salt và chi phí tính toán), không được lấy mẫu “hash email” rồi áp nguyên cho password.

### 8.4. Mã hóa bảo vệ nội dung khi chưa được giải mã

**Encryption at rest** hoặc **application-level encryption** có thể bảo vệ email/địa chỉ khỏi một số hình thức truy cập trái phép. Cần lựa chọn thuật toán xác thực thích hợp, quản lý nonce/IV, key, định danh tenant và rotation qua thư viện/giải pháp được duyệt; không tự sáng tạo thuật toán mã hóa.

Các câu hỏi phải trả lời:

- Dữ liệu được giải mã **ở đâu và bởi role nào**?
- Key có ở cùng nơi với ciphertext hoặc backup không?
- Log, trace, cache hoặc kết quả query có giữ bản plaintext sau giải mã không?
- Có phân quyền theo đối tượng trước khi giải mã không?
- Khi đổi key, dữ liệu cũ được đọc/đổi thế nào?
- Khi cần tìm email, hệ thống dùng cơ chế tra cứu nào và rủi ro lộ pattern ra sao?

**Mã hóa không thay authorization.** Một dịch vụ có quyền giải mã mọi bản ghi vẫn có thể làm lộ toàn bộ dữ liệu nếu bị chiếm quyền.

### 8.5. Anonymization đòi đánh giá khả năng tái định danh

Một dataset chỉ có **số đơn theo ngày và currency** có thể ít rủi ro hơn dataset theo từng khách, nhưng **tổng hợp không tự bảo đảm ẩn danh**. Nhóm cực nhỏ, thời gian quá chi tiết hoặc lọc chồng nhau có thể làm lộ hành vi của một người.

Nếu cần **ẩn danh hóa thực sự**, phải đánh giá phương thức xử lý, dữ liệu phụ trợ có sẵn, đối tượng có thể tấn công, rủi ro tái định danh và mức mất thông tin chấp nhận. Có thể cần kỹ thuật như ngưỡng tối thiểu theo nhóm, làm thô thời gian/địa lý, hạn chế truy vấn hoặc phương pháp riêng tư thống kê phù hợp. **Xóa cột full_name không đủ** để kết luận dataset vô danh.

## 9. Đường ghi: tách dữ liệu nhưng vẫn phải đúng giao dịch

### 9.1. Đăng ký khách trong cùng database

Khi tạo khách mới, hai vùng có thể được ghi trong **một transaction PostgreSQL**:

~~~sql
BEGIN;

INSERT INTO commerce.customer_subjects (
    tenant_id, subject_ref, subject_state
)
VALUES ($1, $2::UUID, 'ACTIVE');

INSERT INTO pii.customer_contacts (
    tenant_id, subject_ref, legal_name, email, phone_e164
)
VALUES ($1, $2::UUID, $3, $4, $5);

COMMIT;
~~~

Giả định backend đã xác thực input, kiểm tra chính sách thu thập dữ liệu, cấp **subject_ref** một lần theo nguồn ngẫu nhiên được kiểm soát và xác định tenant từ context đáng tin. Nếu bước 2 thất bại, transaction rollback cả identity subject và contact.

Đây là lợi thế của **tách schema cùng database**: vẫn có thể sử dụng giao dịch và FK. Nếu chuyển **pii.customer_contacts** sang database riêng, không còn mặc định một transaction và FK như trên; cần giao thức tạo subject, idempotency, retry, đối soát và xử lý trạng thái tạo dở.

### 9.2. Xác nhận đơn: dữ liệu lịch sử cần ranh giới riêng

Giả sử khách chọn địa chỉ giao ở checkout. Khi xác nhận, hệ thống phải chốt:

- **subject_ref** của người đặt, đã xác thực quyền sở hữu.
- **order_ref** duy nhất cho đơn.
- Giá/số lượng/điều khoản được tính từ nguồn có thẩm quyền.
- **Địa chỉ giao đã được xác nhận**, có thể khác contact mặc định hiện hành.
- Trạng thái đơn, thời điểm và phiên bản giao dịch.

Trong một PostgreSQL, có thể INSERT **commerce.orders**, **commerce.order_lines** và **pii.order_delivery_snapshots** trong cùng transaction theo ứng dụng, sau khi thực hiện kiểm tra giá/tồn kho/định danh phù hợp. Không nên ghi đơn thành công rồi gửi thông báo “hãy tạo snapshot giao hàng” mà không có cơ chế chống mất sự kiện; nếu giao hàng cần dữ liệu ấy, thiếu snapshot là lỗi nghiệp vụ.

**Không lấy địa chỉ từ hồ sơ hiện hành mỗi lần in nhãn cho đơn cũ**. Nếu người dùng đổi contact hôm sau, địa chỉ đã chấp nhận của đơn vẫn có thể phải giữ, hoặc được thay theo quy trình sửa địa chỉ giao có dấu vết.

**Không ghi trực tiếp mọi field PII vào order_lines**. Grain dòng hàng không cần phone/email người nhận; làm vậy có thể nhân số lần xuất hiện của PII theo số dòng.

### 9.3. Nhiều database: ngoài tính nhất quán còn phải tính an toàn

Khi Identity và Order nằm ở hai database, ví dụ một request gồm:

~~~text
1. Order DB commit đơn và tham chiếu subject_ref.
2. Identity Service xác nhận subject đang hoạt động.
3. Delivery Service tạo snapshot/định tuyến giao.
~~~

Thứ tự này có thể tạo **TOCTOU** hoặc trạng thái một phần: subject bị hạn chế quyền giữa bước 1 và 2, dịch vụ 3 tạm lỗi, hoặc người đặt đổi địa chỉ. Cần định nghĩa **sự thật nào được chốt tại bước nào** và cơ chế phục hồi.

Một hướng thường dùng là **giao dịch cục bộ + outbox + trạng thái workflow**:

- Order chỉ xác nhận khi đủ điều kiện nghiệp vụ cốt lõi.
- Ghi event có định danh trong cùng transaction Order.
- Consumer được ủy quyền nhận event, thực hiện bước tiếp theo bằng idempotency key.
- Khi bước ngoài thất bại, order đi vào trạng thái có thể quan sát, retry hoặc xử lý bù; không báo “đã giao” quá sớm.
- Mọi message chứa PII phải theo hợp đồng kênh riêng hoặc chỉ mang token tham chiếu và được giải theo quyền.

Outbox giải quyết **khả năng phát lại ý định** nhưng không biến nhiều database và dịch vụ ngoài thành một giao dịch nguyên tử. **Sự kiện phát lại, đến sai thứ tự và thiếu consumer** vẫn cần được thiết kế.

## 10. API và event: chỉ công bố dữ liệu cần cho đúng mục đích

Một Order API cho dashboard vận hành không cần thông tin liên hệ:

~~~json
{
  "orderId": "7d3f8a52-0ff2-4bb6-8c89-79d2acf6d313",
  "status": "PROCESSING",
  "confirmedAt": "2026-11-22T01:00:00Z",
  "confirmedTotal": {
    "amount": "310000.00",
    "currency": "VND"
  }
}
~~~

Dữ liệu này vẫn có thể liên hệ đến một người thông qua mã đơn và quyền truy vấn hệ Order; do đó phải giới hạn object access. Nhưng nó **không chủ động phát email/phone/địa chỉ** cho consumer không cần.

Một integration event về trạng thái:

~~~json
{
  "eventId": "bfaef6c2-26e8-4874-a28e-2c1fc01080e6",
  "eventType": "OrderProcessingStarted",
  "schemaVersion": 1,
  "orderId": "7d3f8a52-0ff2-4bb6-8c89-79d2acf6d313",
  "orderVersion": 4,
  "occurredAt": "2026-11-22T01:03:00Z"
}
~~~

**Không gửi customer_contacts như phần mặc định của mọi OrderUpdated event.** Event bus có nhiều subscriber; một consumer muốn liên hệ khách không làm phát sinh quyền cho tất cả subscriber được biết email.

### 10.1. Hợp đồng giao vận riêng

Dịch vụ giao nhận cần đúng thông tin người nhận. Có thể thiết kế:

~~~text
POST /delivery-requests/{deliveryRef}/resolve-contact
Caller: authorized Logistics Service
Purpose: FULFILLMENT
Resource: đúng đơn/kiện được giao
Response: tên, số liên lạc, địa chỉ được phép giao

Yêu cầu:
- xác thực danh tính dịch vụ
- xác minh được giao xử lý đúng shipment/order
- giới hạn thời hạn sử dụng và lưu trữ
- ghi audit không chứa toàn bộ PII plaintext
~~~

Đây là **một hợp đồng quyền và nghiệp vụ**, không chỉ đường dẫn REST. Nếu giao nhận qua đối tác ngoài, còn cần giới hạn dữ liệu và thời hạn tiếp cận theo hợp đồng tích hợp. Khi không còn nhu cầu, token/quyền phải được thu hồi.

### 10.2. Analytics thường cần ít hơn tưởng tượng

Ví dụ xuất một fact ở grain **dòng đơn đã xác nhận**:

~~~text
fact_order_line_confirmed
  event_date
  product_ref
  currency
  quantity
  unit_price_at_confirmation
  discount_allocated
  net_line_amount
  channel_code
  source_order_ref       -- chỉ nếu cần kiểm chứng, có quyền giới hạn
~~~

Không tự đưa **email, phone, shipping_address, risk_score** vào fact. Nếu phân tích cần cohort, có thể dùng **phân khúc tại thời điểm sự kiện**, được cấp theo công thức và chính sách, thay vì đưa cả hồ sơ cá nhân.

Nếu giữ **subject_ref** trong warehouse để tính khách hàng duy nhất hoặc hành vi lặp lại, cần ghi rõ **mục đích, quyền, retention, hạn chế join** và rủi ro liên kết theo chuỗi. Một mã không có tên vẫn có thể là chìa khóa nối hành vi đa năm, nên không “miễn kiểm soát” chỉ vì đã giả danh.

## 11. Tránh bản sao PII ngoài kiểm soát: CDC, cache, log, backup

Tách schema nhưng phát **CDC của pii.customer_contacts** ra topic mà toàn công ty đọc được sẽ làm mất lợi ích phân quyền. Tương tự, nếu Order Service truy vấn contact rồi ghi toàn bộ JSON response vào log để debug, dữ liệu lại xuất hiện ở nơi khác.

### 11.1. Bản đồ nơi dữ liệu có thể xuất hiện

| Nơi | Rủi ro | Kiểm soát cần cân nhắc |
| --- | --- | --- |
| **Database nguồn** | Role đọc rộng, sai tenant, quyền DBA | Role/least privilege, audit, backup/key |
| **CDC/outbox/event bus** | Payload toàn row chứa PII, consumer mới tự subscribe | Allowlist event, topic ACL, retention, mã hóa đường truyền |
| **Cache** | Key/value chứa contact, lưu quá lâu hoặc dùng chung tenant | Key tách scope, TTL, invalidation, kiểm soát đọc |
| **Application log/APM/trace** | Log request/response, email, địa chỉ, auth token | Redaction và kiểm thử log, tránh ghi payload gốc |
| **Search index** | Index trực tiếp tên/phone/location, quyền tìm kiếm rộng | Mục đích rõ, field-level access, xóa theo nguồn |
| **Kho phân tích** | Mã subject ổn định, nhóm hiếm, JOIN nhiều tập | Pseudonym theo use case, aggregate, truy cập có điều kiện |
| **Export/report** | CSV được tải và chia sẻ ngoài chính sách | Quyền xuất, tracking/audit, hạn thời gian |
| **Test/staging** | Copy dữ liệu sản xuất, ít kiểm soát hơn | Synthetic/de-identified test data, quyền hạn hẹp |
| **Backup/archive** | Bản cũ còn PII sau khi hệ chính đã xóa | Chính sách retention, khóa, quy trình hết hạn và khôi phục |
| **DLQ/retry queues** | Payload lỗi giữ lâu hơn event chính | Redaction, ACL, time-to-live, cơ chế xóa |

**Tách dữ liệu là thiết kế đường đi dữ liệu, không chỉ sơ đồ bảng.** Khi một field đi qua 6 hệ thống, cả 6 nơi phải được kiểm kê theo chính sách áp dụng.

### 11.2. Không xuất bản toàn bộ row dưới danh nghĩa tích hợp

CDC là một công cụ hữu ích cho đồng bộ kỹ thuật, nhưng **raw row của bảng định danh** không phải integration contract chung. Nếu consumer cần chuyển trạng thái liên hệ, có thể phát event không chứa PII, rồi gọi Contact Service có quyền để lấy trường tối thiểu tại đúng thời điểm.

Ví dụ:

~~~text
CustomerContactChanged
  eventId
  subjectRef
  revision
  changedFieldCategories: ["PHONE"]
  occurredAt

KHÔNG mặc định chứa toàn bộ tên, địa chỉ, email, phone cũ/mới.
~~~

Ngay cả event này chứa subjectRef ổn định và thông tin thay đổi một phần, nên vẫn cần hạn chế subscriber/retention. Nếu một consumer không cần biết chủ thể nào đổi liên hệ, nó không nên nhận event ở mức đó.

## 12. Đối soát: tách vật lý không được làm mất tính đúng

Khi dữ liệu nằm ở nhiều bảng hoặc kho, cần đối soát **định danh tham chiếu**, **địa chỉ giao có đủ khi cần**, **sự kiện đến muộn** và **bản sao PII không bị lưu sai nơi**.

### 12.1. Kiểm tra tham chiếu và tình trạng liên hệ

Với DDL trong cùng database, FK bảo vệ quan hệ từ **commerce.orders.subject_ref** đến **commerce.customer_subjects** nếu subject_ref khác NULL. Muốn tìm đơn có chủ thể nhưng thiếu contact hiện hành, có thể chạy truy vấn chẩn đoán với role được phép:

~~~sql
SELECT
    o.tenant_id,
    o.order_ref,
    o.subject_ref
FROM commerce.orders AS o
LEFT JOIN pii.customer_contacts AS c
    ON c.tenant_id = o.tenant_id
   AND c.subject_ref = o.subject_ref
WHERE o.subject_ref IS NOT NULL
  AND c.subject_ref IS NULL;
~~~

**Không mặc định kết quả là lỗi.** Subject có thể đang đóng, chỉ có danh tính được xác minh ở hệ khác, contact đã xóa theo yêu cầu hoặc user dùng tài khoản không thu thập thông tin liên hệ. Cần **hợp đồng coverage** nói đơn/trạng thái nào bắt buộc có contact, và ngưỡng nào là bình thường.

Truy vấn này là **quyền đặc biệt của job đối soát**, không nên cấp cho dashboard hay mọi dịch vụ. Có thể chỉ xuất **số đếm và mã lỗi** thay vì danh sách order_ref/subject_ref cho người không có quyền.

### 12.2. Kiểm tra snapshot giao hàng bắt buộc

Giả sử **mỗi đơn vật lý ở trạng thái SHIPPED** phải có đúng một bản snapshot người nhận trong mô hình một kiện:

~~~sql
SELECT
    o.tenant_id,
    o.order_ref
FROM commerce.orders AS o
LEFT JOIN pii.order_delivery_snapshots AS d
    ON d.tenant_id = o.tenant_id
   AND d.order_ref = o.order_ref
WHERE o.order_state = 'SHIPPED'
  AND d.order_ref IS NULL;
~~~

Đây là **bất biến tùy use case đã giả định**, không áp cho đơn kỹ thuật số hoặc các đơn được phép xóa địa chỉ sau khi hoàn thành. Khi áp dụng retention, phải phân biệt **đơn đang giao cần dữ liệu** và **đơn lịch sử không còn quyền giữ địa chỉ**.

Nếu nhiều shipment, grain và khóa của snapshot phải đổi; câu SELECT trên chỉ dành cho mô hình một snapshot mỗi order.

### 12.3. Đối soát riêng quyền và xuất dữ liệu

Ngoài tính đúng bảng, phải kiểm tra:

- Role **commerce_reader** không SELECT được bảng **pii** qua đường cấp quyền nào.
- Endpoint danh sách đơn không trả **subject_ref** nếu contract không có field đó.
- Log/API error không chứa **legal_name**, **email**, **phone**, **address_line1**.
- Analytics export không vô tình thêm PII khi schema nguồn có cột mới.
- Mọi luồng tái định danh có **lý do, identity của actor, subject, thời điểm và kết quả**.
- Dữ liệu đã được hạn chế/xóa không sống lại qua job rebuild, retry event hoặc restore backup.
- Đối soát dữ liệu giữa các kho có cùng **watermark/version**, không gọi mọi lag hợp lệ là sai lệch vĩnh viễn.

Những bài kiểm tra này có thể tự động hóa bằng contract test, integration test, audit và các chỉ số vận hành. **Số dòng khớp không chứng minh dữ liệu được bảo vệ tốt**, và **không lộ tên không chứng minh dữ liệu vẫn đúng nghiệp vụ**.

## 13. Vòng đời dữ liệu: xóa, hạn chế, lưu giữ và khôi phục

Khi một người yêu cầu đóng tài khoản hoặc hạn chế sử dụng thông tin, tổ chức cần xác định **các quyền và nghĩa vụ cụ thể** trước khi xử lý. Không thể giả định mọi yêu cầu đều có cùng kết quả “DELETE hết”, vì có thể có chứng từ giao dịch, tranh chấp, kiểm toán hoặc thời hạn giữ phải đáp ứng.

Một mô hình vòng đời minh họa:

~~~text
ACTIVE
   |
   | yêu cầu thay đổi/hạn chế hoặc hết mục đích
   v
RESTRICTED
   |
   | xác minh phạm vi dữ liệu còn phải giữ / được phép xóa
   v
CONTACT_REMOVED_OR_REDACTED
   |
   | xử lý unlink, bản sao, cache, export, event
   v
RECONCILED / CLOSED
~~~

Đây **không phải sơ đồ pháp lý chung**. Mỗi bước cần căn cứ, người phê duyệt và audit theo bối cảnh.

### 13.1. Có thể xóa contact nhưng giữ chứng từ kinh doanh?

**Có thể trong một số tình huống nếu chính sách/quy định cho phép**, nhưng phải làm rõ:

- Bản ghi đơn còn cần cho kế toán, tranh chấp hoặc nghĩa vụ khác?
- Việc giữ **subject_ref** còn cần để chứng minh trách nhiệm hay có thể hủy liên kết?
- Địa chỉ đã chốt còn cần cho khiếu nại vận chuyển hoặc cần được xóa sau kỳ?
- Có dữ liệu nhận diện gián tiếp trong ghi chú, SKU hiếm, địa điểm, timestamp?
- Có bản sao trong search index, analytics, cache, log, backup?
- Có cần ngăn **tái tạo contact từ dữ liệu cũ** sau migration/replay?

Trong DDL ví dụ, **orders.subject_ref** cho phép NULL. Sau khi được duyệt, một quy trình có thể **gỡ liên kết đối với các đơn được phép** và sau đó xóa contact theo phạm vi:

~~~sql
BEGIN;

-- Chỉ minh họa thao tác sau khi đã được xét quyền,
-- nghĩa vụ giữ thông tin và phạm vi order của subject.
UPDATE commerce.orders
SET subject_ref = NULL
WHERE tenant_id = $1
  AND subject_ref = $2::UUID;

DELETE FROM pii.customer_contacts
WHERE tenant_id = $1
  AND subject_ref = $2::UUID;

-- KHÔNG tự động xóa customer_subjects hay lịch sử chứng từ.
-- Ứng dụng phải kiểm tra số hàng và các ràng buộc liên quan.
COMMIT;
~~~

**Không chạy đoạn này như một giải pháp xóa dữ liệu tổng quát.** Nó có thể làm mất khả năng tra cứu/đối soát giao dịch hợp pháp; còn **pii.order_delivery_snapshots**, log, backup và các nguồn khác chưa được xử lý. Quy trình thực phải có quyết định theo loại dữ liệu, trách nhiệm và hậu quả nghiệp vụ. Đối với dữ liệu đã lưu trong các hệ khác, cần cơ chế đồng bộ lệnh xóa/ẩn có xác nhận và kiểm soát sự kiện đến muộn.

### 13.2. Không tái tạo danh tính sau khi đã xóa

Một rủi ro thường gặp: hệ chính đã xóa contact, nhưng job backfill đọc từ event cũ hoặc bản backup và **tạo lại pii.customer_contacts**. Cần chính sách **tombstone/restriction marker**, kiểm soát replay và độ tươi của các bản sao, sao cho pipeline biết subject hoặc record nào không được tái tạo.

Những marker này cũng là metadata liên quan chủ thể và phải được quản lý với quyền, mục đích và retention phù hợp. Không phát tán toàn bộ danh sách người đã yêu cầu xóa cho mọi consumer.

### 13.3. Backup và thời hạn giữ thực tế

Việc xóa một hàng trong database hoạt động không có nghĩa mọi snapshot/backup lập tức được sửa. Thiết kế cần xem **chu kỳ backup, quyền restore, thời điểm hết hạn**, khả năng tạo lại dữ liệu từ bản cũ và cách áp dụng lại lệnh xóa/hạn chế sau khi phục hồi.

Một cơ chế phù hợp có thể là giữ **sổ yêu cầu xóa/hạn chế đã được bảo vệ**, thực hiện lại kiểm soát sau restore trước khi công bố dữ liệu, hoặc các giải pháp quản trị khóa/retention được chấp thuận. Không khẳng định mã hóa hoặc khóa riêng là “đã xóa hoàn toàn” nếu còn nhiều bản rõ hoặc đường giải mã.

## 14. Threat model: tách dữ liệu giảm rủi ro nào, còn rủi ro nào?

| Tình huống | Tách có thể giúp gì? | Điều phải bảo vệ thêm |
| --- | --- | --- |
| Tài khoản dashboard chỉ đọc số đơn bị lộ | Không có email/phone/address trong bảng đọc | Tránh khóa subject ổn định và các nhóm quá nhỏ |
| Service Order bị đọc ngoài quyền | Dữ liệu định danh trực tiếp nằm ở vùng khác | Role, tenant authorization, ID access, logs |
| Tài khoản DB admin bị chiếm | Tách schema cùng DB **không đủ** | Phân tách vận hành/key, MFA, audit, quyền tối thiểu |
| Backup OLTP bị lộ | Tách vật lý/key có thể giảm lượng PII trong một backup | Kiểm tra kho backup và quyền restore thực tế |
| Event broker có subscriber không mong muốn | Event tối thiểu không chứa contact | ACL, retention, token/subjectRef linkability |
| Search index bị công khai | Projection có thể loại PII | Phân quyền search, dữ liệu cũ, cập nhật xóa |
| Nhân viên lạm dụng chức năng tra contact | Endpoint tập trung giúp ghi audit | Authorization theo mục đích, hạn mức, phát hiện bất thường |
| Kho phân tích bị ghép với dữ liệu bên ngoài | Có thể giảm bằng aggregate, token theo ngữ cảnh | Quasi-identifier, nhóm hiếm, kiểm soát truy vấn |
| Tác vụ restore/replay dữ liệu cũ | Có thể duy trì cơ chế chặn tái sinh qua metadata | Quy trình restore, tombstone, đối soát sau khôi phục |

Điểm quan trọng: **tách làm giảm blast radius**, không tự chứng minh toàn hệ thống an toàn. Đe dọa cần xét dựa trên **ai có quyền, dữ liệu ở đâu, có thể nối được gì và các đường phục hồi**.

## 15. Di trú từ bảng chứa PII sang mô hình tách biệt

Giả sử bảng **legacy_orders** chứa cả địa chỉ, email, tên và dữ liệu đơn. Một kế hoạch giảm rủi ro:

1. **Kiểm kê field và consumer**: API, batch, dashboard, export, CDC, search, log. Phân loại PII/định danh kỹ thuật/snapshot/bản sao.
2. **Xác định nguồn chuẩn và grain**: customer hiện hành, order đã xác nhận, delivery snapshot; kiểm tra người đặt và người nhận có khác nhau không.
3. **Chốt chính sách dữ liệu**: quyền truy cập theo mục đích, retention, phân loại, yêu cầu xóa/ẩn và audit.
4. **Thiết kế khóa liên kết**: subject_ref ổn định hoặc token theo ngữ cảnh, mapping không trùng trong tenant; bảo vệ khả năng tái định danh.
5. **Tạo vùng mới**: tables/schemas, roles, kiểm thử tenant, quyền và encryption nếu được yêu cầu.
6. **Backfill theo mốc xác thực**: tạo subject/contact từ nguồn đáng tin; chuyển địa chỉ lịch sử sang delivery snapshots mà **không lấy địa chỉ hiện tại để ghi đè quá khứ**.
7. **Bắt kịp thay đổi trong lúc di trú**: dùng checkpoint/outbox/CDC được kiểm soát; không để job cũ ghi lùi hoặc tái sinh dữ liệu đã được hạn chế.
8. **Shadow read và đối soát**: số đơn, dòng hàng, tổng tiền, contact coverage, snapshot, quyền và kết quả API ở phạm vi được phép.
9. **Chuyển consumer từng nhóm**: dashboard chỉ đọc bảng nghiệp vụ/tổng hợp; logistics gọi hợp đồng riêng; support dùng dịch vụ tra contact.
10. **Thu hồi quyền cũ**: bỏ các đường SELECT bảng legacy rộng; chỉ xóa cột/bảng cũ sau khi không còn phụ thuộc và retention cho phép.
11. **Kiểm tra sự cố và phục hồi**: event đến muộn, Contact Service offline, request xóa trong khi backfill, restore backup, tenant mismatch.
12. **Quan sát lâu dài**: audit tái định danh, PII leak test, lag/coverage, quyền truy cập, số hệ còn giữ contact.

### 15.1. Không dùng dual-write để tạo hai nguồn chuẩn

Nếu một thời gian cả legacy_orders.email và pii.customer_contacts.email được ghi, phải xác định **một nơi quyết định giá trị**, nơi còn lại chỉ là projection trong thời gian chuyển tiếp. Nếu hai nơi cùng được sửa độc lập mà không có quy tắc xử lý xung đột, một hệ có thể cập nhật email mới còn hệ kia dùng email cũ.

Sau khi chuyển đổi, không nên giữ sync hai chiều vô thời hạn chỉ để “tương thích”. Cần lịch ngừng người ghi/đọc legacy dựa trên bằng chứng đã chuyển hết consumer.

### 15.2. Tính khả thi phải đo bằng workload và hậu quả

Một hệ nhỏ có thể không cần database riêng. Một hệ rất lớn có nhiều team độc lập có thể cần Contact Service và kho khóa riêng. Quyết định nên dựa trên:

- **Số consumer** thực sự cần tái định danh.
- **Tỷ lệ request** cần contact so với request chỉ cần nghiệp vụ.
- **Độ trễ/sẵn sàng** khi tra contact qua API.
- **Quyền truy cập hiện có** và khả năng giảm số tài khoản được thấy PII.
- **Rủi ro lộ** từ database, backup, log và hệ đối tác.
- **Chi phí đồng bộ, đối soát, phục hồi và xóa** khi dữ liệu nằm ở nhiều kho.
- **Nhu cầu kiểm toán, lịch sử chứng từ và chính sách lưu giữ**.

Một phương án tách rời chỉ có giá trị khi những điều được bảo vệ và cách vận hành **được diễn đạt thành tiêu chí kiểm chứng**, không phải vì sơ đồ kiến trúc trông hiện đại.

## 16. Đối chiếu relational, document, graph và analytics

### 16.1. Relational database

Mô hình quan hệ thuận lợi để diễn đạt **khóa tham chiếu, UNIQUE, quyền schema/bảng/cột, transaction và truy vấn đối soát**. Tách contact sang bảng riêng cùng DB thường là bước đầu ít tốn công, nhưng vẫn phải quản lý quyền đặc biệt và đường JOIN.

Khi chuyển sang nhiều database, không còn tự có FK/giao dịch xuyên ranh giới. Phải xác định authority cho mỗi field và thêm cơ chế nhất quán phù hợp.

### 16.2. Document database

Một document Customer chứa **cả hồ sơ, tài khoản, địa chỉ, lịch sử giao dịch** có thể tiện khi đọc, nhưng việc trả nguyên document dễ lộ PII. Có thể giữ **customerIdentity** riêng với **order document** chỉ chứa subjectRef và snapshot cần thiết; thiết kế quyền trên collection và projection DTO.

Nếu nhúng contact hiện hành vào nhiều order document, đổi email sẽ có fan-out lớn, trong khi đơn lịch sử không cần email mới. Hãy phân biệt **contact current** và **recipient at confirmation** trước khi quyết định embed.

### 16.3. Graph database

Graph cho phép biểu diễn quan hệ **Customer–PLACED–Order–SHIPPED_TO–Address**. Dù không trả tên, việc đi qua những cạnh độc nhất có thể suy ra cá nhân, địa điểm và hành vi.

Cần kiểm soát **các loại node/edge, mục đích traversal, độ sâu truy vấn, quyền theo chủ thể và lượng thông tin trả về**. Không coi xóa thuộc tính name khỏi node là đủ để làm toàn graph vô danh.

### 16.4. Analytical/columnar model

Một fact doanh số có grain **một dòng đơn**, dimension sản phẩm/ngày/kênh và số đo tiền. Nếu báo cáo không cần khách, bỏ **customer dimension key** hoặc chỉ dùng phân nhóm phù hợp. Nếu cần hành vi lặp lại, cân nhắc token phục vụ riêng một use case và quyền truy cập hạn chế.

Dữ liệu tổng hợp có thể giảm tính nhận diện, nhưng nhóm nhỏ hoặc kết hợp nhiều chiều có thể làm rủi ro tăng. Cần kiểm soát **grain, khả năng lọc, cardinality và thời hạn giữ**, không mặc định warehouse “chỉ có số liệu” nên an toàn.

## 17. Checklist review trước khi tách hoặc công bố dữ liệu

| Câu hỏi | Bằng chứng mong muốn |
| --- | --- |
| Một field có cần cho nghiệp vụ không? | Use case và chủ sở hữu cụ thể |
| Đây là định danh trực tiếp hay gián tiếp? | Phân loại trong bối cảnh liên kết dữ liệu |
| Thời điểm dữ liệu mang ý nghĩa gì? | Current, at-confirmation, event time, effective time |
| Người đặt và người nhận có giống nhau không? | Grain/quan hệ nghiệp vụ thực tế |
| Cần liên kết cross-domain không? | Mục đích và thời hạn của subjectRef/token |
| Ai có quyền tái định danh? | Vai trò, object authorization, purpose/audit |
| Tách logic hay tách vật lý? | Threat model, quyền, backup, chi phí giao dịch |
| Cách tạo và xoay ID/key? | Định danh ổn định, không trùng, không suy được PII |
| Bản sao ở đâu? | DB, CDC, logs, cache, index, DLQ, export, backup |
| Snapshot có được sửa theo hồ sơ mới không? | Quy tắc phiên bản/hiệu chỉnh giao dịch |
| Dữ liệu có được xóa/ẩn không? | Chính sách riêng cho contact, order, delivery |
| Rebuild có tái sinh dữ liệu đã xóa không? | Tombstone/restriction và replay rules |
| Có đối soát được không? | FK, coverage, count, quyền và freshness |
| API có để lộ subjectRef không cần thiết không? | DTO allowlist và contract test |
| Phương án có làm gián đoạn checkout không? | SLO, retry, idempotency, chế độ lỗi |
| Có người chịu trách nhiệm không? | Owner nguồn, identity vault, business, analytics |

## 18. Bài tập tình huống

### Bài 1 — Dashboard doanh số vẫn mang email

Bảng **fact_sales** chứa một hàng cho mỗi dòng đơn, nhưng pipeline chép thêm **customer_email** vào mọi dòng “để tiện truy vấn”. Dashboard chỉ hiển thị tổng doanh số theo ngày và currency.

**Câu hỏi:** Rủi ro gì? Cần công bố trường nào và có cần subject_ref không?

### Bài 2 — UUID có phải dữ liệu ẩn danh?

Một hệ thay email bằng **subject_ref UUID** trong toàn bộ lịch sử mua. Bảng ánh xạ subject_ref → email vẫn ở Identity Service; nhóm tuyên bố có thể chia sẻ dataset tự do vì không còn email.

**Câu hỏi:** Tuyên bố có đúng không? Những đường nào còn có thể tái định danh?

### Bài 3 — Người đặt khác người nhận

Khách A mua quà cho B và nhập địa chỉ B. Một job in nhãn đọc **pii.customer_contacts** của A thay vì snapshot trên đơn.

**Câu hỏi:** Đây là lỗi privacy hay mô hình nghiệp vụ, và sửa thế nào?

### Bài 4 — Hash email không khóa

Nhóm Analytics xuất **SHA256(lowercase(email))** và cho rằng không ai biết người trong tập dữ liệu. Một người có danh sách email phổ biến có thể tính lại hash.

**Câu hỏi:** Vì sao dễ bị dò? HMAC có giải quyết mọi vấn đề không?

### Bài 5 — Quyền tenant chỉ được kiểm tra ở UI

Service Order lấy đơn theo **order_ref** mà không lọc tenant/chủ sở hữu; client thay ID trong request có thể đọc đơn của người khác. Nhóm nói “UUID không đoán được nên đủ an toàn”.

**Câu hỏi:** Thiếu bảo vệ gì? Viết các điều kiện cần có trong query hoặc lớp quyền.

### Bài 6 — Tách database gây lỗi tạo tài khoản

Order DB và Identity DB được tách riêng. Tạo subject trong Order thành công nhưng ghi Contact thất bại; client retry nhiều lần. Có những subject chưa có contact, một số bị tạo trùng.

**Câu hỏi:** Cần quyết định tính nhất quán/idempotency và quy trình khôi phục nào?

### Bài 7 — Xóa contact nhưng giữ chứng từ

Một người yêu cầu đóng tài khoản. Hệ thống cần xem xét việc lưu đơn để phục vụ chứng từ trong thời hạn áp dụng; email hiện hành có thể không còn cần. Nhóm muốn **DELETE CASCADE** toàn bộ customer, orders và order_lines ngay lập tức.

**Câu hỏi:** Vì sao nguy hiểm? Phải phân loại và xử lý theo bước nào?

### Bài 8 — Dữ liệu sống lại sau khôi phục

Contact Service đã hạn chế/xóa một record theo quy trình. Một tuần sau, hệ thống restore backup cũ và chạy CDC replay, làm record đó xuất hiện lại trong index tìm kiếm.

**Câu hỏi:** Thiết kế vòng đời thiếu gì? Làm sao kiểm tra không còn dữ liệu bị thu hồi ở các bản sao?

### Bài 9 — Dịch vụ giao vận đọc mọi contact

Một service vận chuyển có quyền SELECT toàn bộ **pii.customer_contacts** trong tất cả tenant. Nó chỉ cần số điện thoại của người nhận cho những kiện được giao trong tuần.

**Câu hỏi:** Nên giới hạn theo chiều nào? API trả số điện thoại trực tiếp có phải lựa chọn duy nhất không?

### Bài 10 — Báo cáo hiếm có thể nhận diện lại

Một báo cáo không còn tên/email nhưng cho phép lọc theo **một phường nhỏ, chính xác từng phút, loại sản phẩm hiếm và tổng tiền**. Một người biết thời điểm giao dịch có thể suy ra khách.

**Câu hỏi:** Tại sao tổng hợp chưa đủ? Nêu ít nhất ba biện pháp điều chỉnh.

### Gợi ý lời giải

1. Email bị nhân bản vào từng dòng fact, tăng điểm lộ và chi phí xóa. Dashboard theo ngày/currency chỉ cần **business_date, currency, order_count, amount** với định nghĩa rõ; thường **không cần subject_ref**.
2. **Không đúng.** UUID là giả danh hóa, mapping vẫn cho phép tái định danh; hành vi mua, thời điểm, địa điểm và dữ liệu ngoài cũng có thể liên kết. Cần đánh giá quyền/mục đích/retention và rủi ro nối dữ liệu.
3. Cả hai: sai nguồn dữ liệu nghiệp vụ **người đặt ≠ người nhận**, đồng thời có thể tiết lộ địa chỉ hoặc giao sai. Cần dùng **delivery snapshot đúng order/shipment**, truy cập theo quyền của Logistics.
4. Không gian email dễ đoán, có thể tính hash từ danh sách để đối chiếu; cùng hash cho phép nối dữ liệu. HMAC có khóa bí mật giảm một số kiểu dò khi chưa có key, nhưng vẫn tạo ID có thể liên kết, cần key management, quyền oracle và rotation; **không là ẩn danh hóa**.
5. Thiếu authorization **theo đối tượng**, tenant và người sở hữu. Query phải giới hạn theo tenant đã xác thực và **subject_ref có quyền**, hoặc dùng một bảng access grant đã kiểm tra; không tin ID do client tự nhập là chứng cứ quyền.
6. Cần xác định **nguồn chuẩn subject**, idempotency key cho đăng ký, unique theo tenant và quy trình tạo contact có retry/compensation. Theo dõi trạng thái chưa hoàn tất và đối soát; không tạo subject mới mỗi lần retry. Không giả định hai database có transaction chung.
7. DELETE CASCADE có thể phá chứng từ và dấu vết cần giữ; phải phân loại **contact hiện hành, liên kết người–đơn, snapshot giao hàng, order và line**, xét nghĩa vụ/retention, giới hạn/xóa từng loại có duyệt, xử lý bản sao và audit.
8. Thiếu quy tắc **restriction/tombstone tồn tại qua restore/replay**, kiểm tra nguồn trước khi áp CDC, và đối soát nơi lưu. Cần áp dụng lại yêu cầu hạn chế/xóa sau khôi phục trước khi cho consumer dùng dữ liệu, theo dõi index/cache/backup.
9. Giới hạn **tenant, shipment được giao, purpose, thời gian**, role và lượng field trả. Dịch vụ Contact có thể **thực hiện gửi tin** thay vì trả phone; nếu cần phone để giao, chỉ trả trong phạm vi được ủy quyền và ghi audit.
10. Tổ hợp quasi-identifier có thể nhận diện người ngay cả khi không có tên. Có thể **làm thô thời gian/vùng**, **hạn chế nhóm quá nhỏ**, **giới hạn các chiều lọc và quyền xem**, hoặc áp dụng kỹ thuật bảo vệ thống kê phù hợp với mục tiêu, đánh giá rủi ro tái định danh thực tế.

## 19. Ghi nhớ

**Tách thông tin định danh khỏi dữ liệu nghiệp vụ khi phù hợp** là tạo ranh giới giữa **ai là người thật**, **họ đã thực hiện giao dịch gì** và **consumer nào thật sự có lý do được liên kết hai loại thông tin**. Ranh giới ấy cần hiện diện trong **lược đồ, quyền, API, event, log, backup, retention và quy trình phục hồi**, không chỉ qua việc đổi tên bảng.

**Giả danh hóa giảm khả năng nhận diện trực tiếp nhưng không đồng nghĩa ẩn danh hóa.** Một mã ổn định, lịch sử mua, vị trí và timestamp vẫn có thể nhận diện gián tiếp. Muốn bảo vệ hiệu quả, phải giảm số người và hệ thống có thể tái định danh, đồng thời đánh giá những nguồn kết hợp còn lại.

**Không hy sinh sự thật giao dịch để đạt cảm giác “không còn PII”.** Địa chỉ giao đã chốt, khoản tiền và chứng từ có vòng đời và mục đích khác hồ sơ liên hệ hiện hành. Hãy quản lý chúng trong vùng quyền phù hợp, có chính sách hiệu chỉnh và lưu giữ rõ ràng.

Trước khi tách một field, hãy hỏi: **“Ai cần biết danh tính để thực hiện hành động nào, bao lâu, dữ liệu này đúng tại thời điểm nào, có thể liên kết với gì, và nếu thu hồi quyền hoặc phục hồi hệ thống thì việc tách còn bảo vệ được người dùng không?”**. Trả lời bằng mô hình, ràng buộc, kiểm thử và quy trình vận hành sẽ giúp dữ liệu vừa hữu dụng vừa được bảo vệ có kiểm soát.

# Phiên bản lược đồ và quản lý các trạng thái trung gian khi triển khai

## Mục tiêu học tập

Một thay đổi lược đồ cơ sở dữ liệu hiếm khi chỉ là một câu **ALTER TABLE**. Trong một hệ thống đang phục vụ người dùng, có thể đồng thời tồn tại **nhiều phiên bản ứng dụng**, dữ liệu cũ chưa được chuyển đổi, tiến trình đồng bộ còn đọc cấu trúc cũ và những thông điệp được phát trước khi triển khai. Vì vậy, mô hình dữ liệu phải được thiết kế để **tiến hóa qua các trạng thái trung gian hợp lệ**, không chỉ mô tả trạng thái trước và sau.

Bài thuộc chương **Tiến hóa mô hình**, module **DATABASE_DATA_MODELING**. Mục tiêu của module là chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, từ thực thể, quan hệ, ràng buộc đến chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; đồng thời so sánh cấu trúc quan hệ, document, đồ thị và phân tích để có thiết kế dễ tiến hóa và kiểm chứng. Chủ đề trực tiếp ở đây là **phiên bản lược đồ và quản lý các trạng thái trung gian khi triển khai**.

Sau bài học, bạn có thể:

1. Phân biệt **phiên bản lược đồ**, **phiên bản ứng dụng**, **phiên bản hợp đồng API/event** và **trạng thái chuyển đổi dữ liệu**.
2. Giải thích vì sao **migration chạy thành công** chưa đủ chứng minh một bản phát hành tương thích.
3. Thiết kế chuỗi **expand → migrate/backfill → switch → contract** với các trạng thái trung gian, tiêu chí chuyển pha và khả năng phục hồi.
4. Xây dựng **ma trận tương thích** giữa phiên bản ứng dụng cũ/mới và lược đồ trước/sau mở rộng.
5. Dùng PostgreSQL để minh họa việc đổi tên cột một cách an toàn trong quá trình **rolling deployment**, bao gồm **đồng bộ hai cột**, backfill, kiểm chứng và loại bỏ cột cũ đúng thời điểm.
6. Phân tích rủi ro **dual-write, tính đồng thời, dữ liệu đến trễ, chỉ mục, ràng buộc mới, khóa DDL và migration chạy dài**.
7. Phân biệt **rollback ứng dụng**, **rollback schema**, **forward fix** và **phục hồi dữ liệu**; biết vì sao không phải thay đổi nào cũng đảo ngược được.
8. Đề xuất kiểm thử, telemetry, checklist và tiêu chí **go/no-go** cho từng pha triển khai mô hình dữ liệu.

> **Phạm vi:** Ví dụ sử dụng PostgreSQL và Java/JDBC ở mức minh họa. Đây là tài liệu thiết kế và quy trình migration, **không phải công cụ tự động triển khai**. Các lệnh SQL cần được xem xét với phiên bản PostgreSQL, quyền, kích thước dữ liệu, tải và cơ chế vận hành thực tế trước khi áp dụng ở production.

## 1. Vì sao mô hình dữ liệu phải tiến hóa theo giai đoạn?

### 1.1. Hình dung một thay đổi nhỏ

Giả sử bảng đơn hàng trước đây lưu email liên hệ ở cột **customer_email**. Sau khi làm rõ nghiệp vụ, nhóm muốn đổi thành **buyer_email** vì email này là **ảnh chụp email người đặt tại thời điểm tạo đơn**, không phải email hiện tại của hồ sơ khách hàng.

Giả định được hai nhóm phê duyệt trong ví dụ là:

> customer_email cũ và buyer_email mới có **cùng ngữ nghĩa giá trị cho các bản ghi hiện có**; thay đổi này chỉ làm tên trường chính xác hơn, **không** thay đổi người liên hệ, quyền truy cập hay thời điểm chụp dữ liệu.

Nếu thay đổi thực sự là từ “email của khách” sang “email của người nhận hàng” thì đây **không còn là đổi tên đơn thuần**. Không thể backfill máy móc từ cột cũ mà không xác minh dữ liệu nguồn.

Một câu lệnh trực tiếp:

~~~~sql
-- KHÔNG chạy câu này ngay nếu còn ứng dụng đang đọc customer_email.
ALTER TABLE sales_order RENAME COLUMN customer_email TO buyer_email;
~~~~

có thể thực hiện rất nhanh trên database nhưng khiến ứng dụng cũ gửi:

~~~~sql
SELECT customer_email FROM sales_order;
~~~~

và nhận lỗi **column does not exist**. Vấn đề không phải migration SQL viết sai, mà là **mối quan hệ giữa thay đổi schema và thời điểm thay đổi ứng dụng** chưa được quản lý.

### 1.2. Những phiên bản có thể tồn tại đồng thời

Trong quá trình triển khai, có thể có:

- **A0 — Ứng dụng cũ:** đọc/ghi customer_email.
- **A1 — Ứng dụng tương thích chuyển tiếp:** nhận biết cả hai trường và dùng quy tắc đọc/ghi đã chốt.
- **A2 — Ứng dụng mới:** chỉ cần buyer_email.
- **S0 — Lược đồ cũ:** chỉ có customer_email.
- **S1 — Lược đồ mở rộng:** có cả customer_email và buyer_email.
- **S2 — Lược đồ đã đối soát:** cả hai trường có dữ liệu phù hợp, mọi luồng ghi đang đồng bộ.
- **S3 — Lược đồ rút gọn:** chỉ còn buyer_email.

**A0, A1, A2** là phiên bản mã chạy, còn **S0–S3** là trạng thái lược đồ và dữ liệu. Chúng không phải một bộ số phiên bản dùng thay thế cho nhau. Một lần deploy ứng dụng có thể không đổi schema; một đợt backfill có thể làm trạng thái dữ liệu thay đổi mà không đổi bất kỳ định nghĩa bảng nào.

### 1.3. “Triển khai không gián đoạn” không đồng nghĩa không có khóa hay rủi ro

Khái niệm **zero-downtime migration** thường hướng tới việc **không cần dừng toàn bộ dịch vụ để đổi schema**. Tuy nhiên:

- Một số lệnh DDL vẫn cần khóa trên bảng, dù thời gian thực hiện có thể ngắn.
- Chờ khóa có thể khiến request khác bị chặn.
- Backfill có thể làm tăng tải I/O, WAL, replication lag và bloat.
- Nhiều phiên bản ứng dụng có thể ghi dữ liệu không nhất quán nếu thiếu cơ chế đồng bộ.
- Consumer hoặc job ít khi chạy vẫn có thể phụ thuộc cột cũ.

Vì vậy, “an toàn khi triển khai” là một **tập tiêu chí có thể kiểm chứng** chứ không phải một nhãn của một câu SQL.

## 2. Những loại phiên bản khác nhau

### 2.1. Phiên bản schema vật lý

Phiên bản schema cho biết tập thay đổi DDL đã được áp dụng, chẳng hạn:

~~~~text
V001__create_sales_order.sql
V002__add_buyer_email.sql
V003__add_email_constraint.sql
V004__drop_customer_email.sql
~~~~

Đây là **ví dụ tên file migration**, không phải yêu cầu phải dùng một công cụ cụ thể. Một số công cụ như Flyway hoặc Liquibase có cơ chế theo dõi lịch sử; nếu dùng, cần tuân theo quy ước chính xác của công cụ và phiên bản đang triển khai.

Một bản ghi lịch sử migration thường có:

| Thành phần | Ý nghĩa |
| --- | --- |
| **Migration identifier** | Xác định duy nhất bước thay đổi |
| **Thứ tự/phụ thuộc** | Bước nào phải có trước bước khác |
| **Checksum/nội dung** | Phát hiện nội dung đã áp dụng bị chỉnh lại |
| **Thời điểm áp dụng** | Truy vết mỗi môi trường đã chạy bước nào |
| **Kết quả** | Thành công, lỗi hoặc cần phục hồi thủ công |
| **Người/đường triển khai** | Trách nhiệm thay đổi và khả năng kiểm toán |

**Không sửa tùy ý một migration đã phát hành** rồi mong database tự hiểu phiên bản mới. Đối với thay đổi tiếp theo, nên tạo một migration mới có thứ tự và lý do rõ, trừ khi nhóm có quy trình sửa lịch sử chưa được áp dụng.

### 2.2. Phiên bản hợp đồng logic và ngữ nghĩa

Một lược đồ có thể giữ nguyên cột **amount NUMERIC(18,2)** nhưng nhóm đổi cách hiểu từ **VND** sang **đơn vị tiền nhỏ nhất**. DDL không đổi, nhưng **hợp đồng dữ liệu đã thay đổi nghiêm trọng**.

Các thành phần cần được version hóa hoặc quản trị tương thích:

- Ý nghĩa cột, đơn vị đo, nullability và miền giá trị.
- Grain của fact hoặc khóa nghiệp vụ.
- Quy tắc trạng thái và vòng đời.
- API request/response.
- Event payload, event type, schemaVersion và ngữ nghĩa của sự kiện.
- Projection/read model, báo cáo và các job ngoài luồng đọc database.

**Phiên bản schema vật lý không thay thế phiên bản hợp đồng.** Một hệ thống có thể đang ở migration V004 nhưng vẫn cần hỗ trợ event schema v1 do message cũ được phát lại.

### 2.3. Phiên bản dữ liệu

Dữ liệu có thể ở những mức chuyển đổi:

~~~~text
Chưa chuyển:
  customer_email có giá trị, buyer_email = NULL

Đang chuyển:
  một số hàng đã có buyer_email, một số hàng chưa có

Đã chuyển:
  buyer_email có giá trị và khớp quy tắc mapping

Đang cắt chuyển:
  ứng dụng đọc trường mới, song vẫn bảo vệ cập nhật từ phiên bản cũ
~~~~

Một lệnh ALTER TABLE ADD COLUMN thành công **không** có nghĩa mọi hàng đã được backfill. Một script backfill chạy hết cũng **không** chứng minh dữ liệu mới và cũ còn khớp sau khi các ứng dụng tiếp tục ghi.

### 2.4. Phiên bản ứng dụng và luồng ghi

Một hệ thống rolling update có thể đồng thời chạy:

~~~~text
3 instance A0 (đọc/ghi customer_email)
2 instance A1 (đọc/ghi buyer_email, tương thích cột cũ)
1 worker báo cáo cũ (SELECT customer_email theo lịch)
1 consumer event v1 (đọc payload trường customerEmail)
~~~~

Một container mới khỏe mạnh hoặc một request API thành công chưa đủ kết luận **mọi đường đọc/ghi cũ đã biến mất**. Trước bước contract, cần kiểm kê các **job theo lịch, CLI nội bộ, export, BI, stream consumer, replica reader và phần mềm đối tác**.

## 3. Ma trận tương thích trước khi đổi schema

Với mô hình chuyển đổi tên cột trong ví dụ, ta lập ma trận:

| Ứng dụng / Schema | S0: chỉ customer_email | S1: cả hai cột, đồng bộ | S3: chỉ buyer_email |
| --- | --- | --- | --- |
| **A0: chỉ dùng customer_email** | **Tương thích** | **Tương thích** nếu sync và các ràng buộc vẫn phục vụ A0 | **Không tương thích** |
| **A1: đọc mới có fallback, ghi theo giao thức chuyển đổi** | **Chỉ khi đã thiết kế fallback và write path phù hợp** | **Tương thích mục tiêu** | **Chỉ khi mã A1 không còn tham chiếu cột cũ** |
| **A2: chỉ dùng buyer_email** | **Không tương thích** | **Tương thích** sau khi cột mới và dữ liệu đã sẵn sàng | **Tương thích** |

Một ứng dụng “đọc fallback” mà lại **luôn INSERT buyer_email** không chạy được trên S0, vì S0 không có cột đó. Một ứng dụng “đọc mới có fallback” nhưng UPDATE hai cột trong mọi giao dịch **không tương thích với S3** nếu customer_email đã bị xóa. **Ma trận phải phản ánh SQL thực sự của từng bản build**, không chỉ tên phiên bản do nhóm đặt.

### 3.1. Quy tắc không phá phiên bản còn chạy

Một chuyển đổi schema an toàn thường bảo đảm:

1. **Mở rộng schema trước** khi phát hành mã buộc phải dùng cấu trúc mới.
2. Chạy giai đoạn tương thích khi còn **A0 và A1/A2 đồng thời**.
3. Chỉ bỏ trường cũ khi **không còn consumer còn cần trường ấy**.
4. Nếu cần khả năng rollback code về A0, **chưa được loại bỏ cột cũ**.

Đây là thứ tự triển khai **có phụ thuộc logic**. Không giải quyết được nó chỉ bằng cách gộp mọi SQL trong một transaction.

### 3.2. Tương thích ngược và tương thích tiến

Trong ngữ cảnh dữ liệu:

- **Tương thích ngược:** phiên bản mới chấp nhận dữ liệu/lược đồ hoặc contract do phiên bản cũ cung cấp, trong phạm vi cam kết.
- **Tương thích tiến:** phiên bản cũ vẫn chấp nhận được các thay đổi mà phía mới tạo ra, trong phạm vi đã thiết kế.

Ví dụ thêm **cột nullable** thường ít phá ứng dụng cũ dùng danh sách cột tường minh. Nhưng ứng dụng dùng **SELECT *** và đọc cột theo **vị trí**, hoặc dùng cơ chế serialize theo số cột, vẫn có thể hỏng. Thêm một giá trị enum vào bảng cũng có thể phá một consumer dùng switch không có nhánh mặc định. **Không được kết luận tương thích chỉ vì DDL “chỉ thêm cột”.**

## 4. Expand – Migrate – Switch – Contract

Mẫu **expand–contract** chia một thay đổi không tương thích thành nhiều bước. Đối với dữ liệu có sẵn, thường cần tách rõ thêm pha **migrate/backfill** và **switch/cutover**.

### 4.1. Bốn pha và trạng thái trung gian

| Pha | Lược đồ/dữ liệu | Ứng dụng | Điều kiện hoàn tất |
| --- | --- | --- | --- |
| **1. Expand** | Thêm cấu trúc mới; cấu trúc cũ còn nguyên | A0 vẫn hoạt động | Thay đổi không phá A0, có đường sync nếu ghi hai cột |
| **2. Migrate** | Backfill, kiểm tra dữ liệu lịch sử và dữ liệu mới | A0/A1 có thể cùng chạy | Không còn hàng chưa chuyển hoặc lệch theo hợp đồng |
| **3. Switch** | Cấu trúc cũ và mới còn được bảo vệ | Chuyển đọc/ghi chính sang A2 | Metric, lỗi, tính đúng và đường ghi cũ đã được kiểm soát |
| **4. Contract** | Bỏ cột/ràng buộc/đường sync cũ | Chỉ còn mã/consumer tương thích mới | Đã hết rollback window, không còn phụ thuộc cũ |

**Expand không phải là chạy xong trước khi có dữ liệu:** nếu có lưu lượng ghi trong lúc backfill, cần thiết kế cách **giữ hai biểu diễn đồng bộ** hoặc đặt ranh giới write cutover có thể kiểm chứng.

### 4.2. Sơ đồ trạng thái triển khai

~~~~mermaid
stateDiagram-v2
    [*] --> S0: Lược đồ và mã cũ
    S0 --> S1: Expand + compatibility guard
    S1 --> S2: Backfill + reconcile
    S2 --> S2: Retry batch / kiểm tra lại
    S2 --> S3: Switch readers/writers
    S3 --> S3: Theo dõi + đợi kết thúc rollback window
    S3 --> S4: Contract drop old column
    S4 --> [*]

    S1 --> S0: Chỉ nếu không có dữ liệu phụ thuộc mới
    S3 --> S2: Rollback ứng dụng trong khi còn old column
~~~~

Mũi tên quay lại là **khả năng có điều kiện**, không phải cam kết DOWN migration luôn an toàn. Nếu trong pha mới phát sinh dữ liệu mà phiên bản cũ không hiểu, việc quay lại có thể cần **forward fix, compatibility adapter hoặc xử lý dữ liệu bổ sung**, ngay cả khi cột cũ vẫn tồn tại.

### 4.3. Invariant của từng pha

| Pha | Invariant cần giữ |
| --- | --- |
| S0 | Mọi ghi/đọc của A0 hợp lệ trên schema cũ |
| S1 | A0 vẫn hoạt động; nếu cả hai cột đã được phép ghi, chúng không được diverge âm thầm |
| S2 | Mỗi bản ghi thuộc phạm vi migration có thể xác minh mapping cũ–mới |
| S3 | A2 đọc/ghi dữ liệu mới đầy đủ; dữ liệu cũ vẫn sẵn sàng trong thời gian cho phép rollback |
| S4 | Không còn consumer A0; mọi ràng buộc và dữ liệu của trạng thái mới được bảo vệ |

**Không cho phép “trạng thái giữa chừng” vô định:** mỗi pha phải có **điều kiện vào, điều kiện ra, người chịu trách nhiệm và dữ liệu quan sát được**. Nếu một bước bị lỗi, nhóm cần biết hệ thống đang ở pha nào và thao tác nào an toàn để chạy lại.

### 4.4. Các đường chuyển đổi không giống nhau

Cùng tên “expand–contract”, chiến lược cụ thể thay đổi theo loại biến đổi:

- **Thêm cột mới:** thêm nullable/default phù hợp, backfill, đổi code, siết NOT NULL.
- **Đổi tên cột:** giữ hai cột, đồng bộ, cắt chuyển đọc/ghi, bỏ cột cũ.
- **Tách một cột thành nhiều cột:** có thể không suy ra được mọi giá trị mới; cần chính sách xử lý trường hợp mơ hồ.
- **Gộp bảng:** phải đối chiếu khóa, cardinality, bản ghi trùng và quyền sở hữu.
- **Tách bảng:** cần dual-read/dual-write hoặc projection có nguồn sự thật rõ, tránh hai bên cùng sửa thiếu đồng bộ.
- **Đổi kiểu/đơn vị tiền:** phải quy định conversion chính xác và ngăn mất precision/range.
- **Thêm UNIQUE/FK/NOT NULL:** phải làm sạch dữ liệu cũ và giữ dữ liệu mới không vi phạm trong lúc validate.

Một câu ALTER TABLE không quyết định **cách dữ liệu và các bản ứng dụng sống chung** trong thời gian chuyển đổi.

## 5. Ví dụ PostgreSQL xuyên suốt: đổi tên cột trong hệ thống đang ghi

Ta thực hiện một **kịch bản độc lập trên database thử nghiệm**. Các tên bảng/hàm có hậu tố **_demo** để nhấn mạnh đây là mẫu học tập. Kịch bản giả định:

- Trường **customer_email** cũ và **buyer_email** mới có cùng nghĩa **email người đặt tại thời điểm lập đơn**.
- Một hàng đơn có đúng một email cần lưu theo chính sách ví dụ; dữ liệu nhập đã được xác thực cấu trúc ở tầng ứng dụng.
- Có thể tồn tại **ứng dụng A0 chỉ ghi customer_email** và **A2 chỉ ghi buyer_email** trong giai đoạn chuyển.
- Các ứng dụng có thể tiếp tục chạy; ta muốn chuyển dần mà không yêu cầu mọi instance nâng cấp đồng thời.

### 5.1. S0 — Lược đồ và dữ liệu cũ

~~~~sql
CREATE TABLE sales_order_demo (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO sales_order_demo (customer_email)
VALUES
    ('an@example.org'),
    ('binh@example.org'),
    ('chi@example.org');

SELECT order_id, customer_email
FROM sales_order_demo
ORDER BY order_id;
~~~~

Ở S0, ứng dụng cũ đọc/ghi customer_email; không có buyer_email. Mục tiêu là đổi **tên và hợp đồng trường**, không thay đổi lịch sử email đã chốt. Nếu giá trị nguồn có lỗi dữ liệu, đó là một nhiệm vụ làm sạch có tiêu chí riêng, không nên vô tình che giấu bằng cách đổi tên.

### 5.2. S1 — Expand: thêm cột mới, chưa xóa cột cũ

~~~~sql
ALTER TABLE sales_order_demo
ADD COLUMN buyer_email TEXT;
~~~~

**Tại sao ban đầu cho phép NULL?** Vì mọi hàng hiện có chưa có giá trị cột mới; nếu yêu cầu NOT NULL ngay mà không có giá trị hợp lệ cho tất cả hàng và đường ghi, ta có thể chặn dữ liệu cũ hoặc ứng dụng A0.

Sau bước này, trạng thái bình thường là:

| order_id | customer_email | buyer_email |
| ---: | --- | --- |
| 1 | an@example.org | NULL |
| 2 | binh@example.org | NULL |
| 3 | chi@example.org | NULL |

**NULL ở trạng thái chuyển tiếp không đồng nghĩa NULL được phép trong mô hình đích.** Ta đang mở rộng lược đồ tạm thời để di chuyển dữ liệu, sau đó mới siết invariant.

### 5.3. Vấn đề khi chỉ bảo ứng dụng mới dual-write

Giả sử A2 ghi **cả customer_email và buyer_email**, nhưng A0 vẫn chỉ ghi customer_email. Sau backfill, A0 có thể sửa customer_email còn buyer_email giữ giá trị cũ. Nếu A2 luôn đọc buyer_email, hai phiên bản sẽ thấy **hai dữ liệu khác nhau**.

Đây là lý do kế hoạch **“backfill một lần + ứng dụng mới dual-write”** không tự đủ khi **vẫn có writer cũ**. Cần một trong các phương án:

- **Đồng bộ tại database** trong giai đoạn chuyển, ví dụ trigger được thiết kế và kiểm thử cẩn thận.
- **Nâng toàn bộ writer lên phiên bản tương thích** trước khi cho phép viết theo trường mới, kèm cơ chế kiểm tra không còn A0.
- **Chặn/điều phối chuyển quyền ghi** trong một khoảng xác định, nếu mức gián đoạn đó được chấp thuận.

Ví dụ này chọn **trigger chuyển tiếp** để A0 và A2 có thể cùng tồn tại. Trigger không phải giải pháp bắt buộc cho mọi hệ thống; nó làm tăng độ phức tạp, tải ghi và trách nhiệm giám sát nên phải được gỡ khi đã contract.

### 5.4. Thiết lập cầu đồng bộ hai cột

Đầu tiên, tạo hàm PostgreSQL. Nó kiểm tra các trường hợp:

- **INSERT:** nếu chỉ có một email, sao chép sang trường còn lại; nếu hai email khác nhau, từ chối.
- **UPDATE cột cũ:** cột mới đi theo giá trị vừa sửa.
- **UPDATE cột mới:** cột cũ đi theo giá trị vừa sửa.
- **UPDATE cả hai với giá trị mâu thuẫn:** từ chối.
- **UPDATE hàng chưa backfill ở cột không liên quan:** hoàn thiện cột mới từ giá trị cũ nếu chưa có.

~~~~sql
CREATE OR REPLACE FUNCTION sync_sales_order_email_demo()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.customer_email IS NOT NULL
           AND NEW.buyer_email IS NOT NULL
           AND NEW.customer_email IS DISTINCT FROM NEW.buyer_email THEN
            RAISE EXCEPTION
                'Conflicting old/new email on INSERT';
        END IF;

        NEW.customer_email :=
            COALESCE(NEW.customer_email, NEW.buyer_email);
        NEW.buyer_email := NEW.customer_email;

    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.customer_email IS DISTINCT FROM OLD.customer_email
           AND NEW.buyer_email IS DISTINCT FROM OLD.buyer_email
           AND NEW.customer_email IS DISTINCT FROM NEW.buyer_email THEN
            RAISE EXCEPTION
                'Conflicting old/new email on UPDATE';

        ELSIF NEW.customer_email IS DISTINCT FROM OLD.customer_email THEN
            -- Writer cũ đã sửa trường cũ.
            NEW.buyer_email := NEW.customer_email;

        ELSIF NEW.buyer_email IS DISTINCT FROM OLD.buyer_email THEN
            -- Writer mới đã sửa trường mới.
            NEW.customer_email := NEW.buyer_email;

        ELSIF NEW.buyer_email IS NULL THEN
            -- Một hàng cũ chưa backfill đang được cập nhật.
            NEW.buyer_email := NEW.customer_email;

        ELSIF NEW.customer_email IS DISTINCT FROM NEW.buyer_email THEN
            RAISE EXCEPTION
                'Inconsistent old/new email in an existing row';
        END IF;
    END IF;

    IF NEW.customer_email IS NULL OR NEW.buyer_email IS NULL THEN
        RAISE EXCEPTION
            'Both old and new email must be present after synchronization';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_sync_sales_order_email_demo
BEFORE INSERT OR UPDATE
ON sales_order_demo
FOR EACH ROW
EXECUTE FUNCTION sync_sales_order_email_demo();
~~~~

**Tại sao BEFORE trigger quan trọng?** Với INSERT của A2 chỉ cung cấp buyer_email, trigger chạy trước khi PostgreSQL kiểm tra NOT NULL của customer_email và có thể gán lại customer_email hợp lệ. Nếu là AFTER trigger, bản ghi mới có thể bị ràng buộc NOT NULL từ chối trước khi đồng bộ.

**Cảnh báo kỹ thuật:** Trigger này chỉ minh họa **hai cột có cùng ngữ nghĩa**. Nó không giải quyết mọi xung đột nghiệp vụ. Hai transaction sửa email khác nhau dựa trên dữ liệu cũ có thể gây **lost update** theo chính sách ghi cuối thắng; muốn ngăn cần **optimistic locking với version**, điều kiện cập nhật hoặc giao thức giải quyết xung đột. Các writer có đặc quyền vượt trigger, replication đặc biệt hoặc thao tác quản trị cũng cần được kiểm soát. Không dùng trigger “đồng bộ hai nghĩa khác nhau” như giá niêm yết và giá chốt đơn.

### 5.5. S2 — Backfill dữ liệu cũ, không khóa toàn bộ quá trình ghi

Với tập thử nghiệm nhỏ:

~~~~sql
UPDATE sales_order_demo
SET buyer_email = customer_email
WHERE buyer_email IS NULL;
~~~~

Trong production, nếu bảng có nhiều triệu hàng, **một UPDATE duy nhất** có thể giữ transaction dài, sinh nhiều WAL, tạo bloat, làm replica trễ hoặc gây tranh chấp khóa. Nên cân nhắc **backfill theo lô nhỏ**, giới hạn tốc độ, checkpoint tiến độ và quan sát tải.

Một câu SQL chọn một lô có thể dùng:

~~~~sql
WITH batch AS (
    SELECT order_id
    FROM sales_order_demo
    WHERE buyer_email IS NULL
    ORDER BY order_id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE sales_order_demo AS o
SET buyer_email = o.customer_email
FROM batch
WHERE o.order_id = batch.order_id
RETURNING o.order_id;
~~~~

Một worker triển khai thực tế sẽ chạy các lô **theo transaction có kiểm soát**, nghỉ/giảm tốc khi tải cao, ghi nhận tiến độ và dừng khi không còn hàng cần chuyển. Câu SQL này chỉ là **một lô**, không tự tạo scheduler, retry, checkpoint hay dashboard vận hành.

**Tính idempotent:** Điều kiện buyer_email IS NULL giúp chạy lại lô không ghi đè hàng đã hoàn thiện. Nhưng nếu có dữ liệu **mâu thuẫn không NULL**, cần **kiểm tra và xử lý xung đột**, không được mặc định coi là hoàn tất chỉ vì hai cột đều có giá trị.

### 5.6. Kiểm thử writer cũ và mới khi cầu đồng bộ còn hoạt động

Sau khi trigger được cài và dữ liệu đã backfill, chạy:

~~~~sql
-- A0: ghi theo giao diện cũ.
UPDATE sales_order_demo
SET customer_email = 'an.new@example.org'
WHERE order_id = 1;

-- A2: ghi theo giao diện mới.
UPDATE sales_order_demo
SET buyer_email = 'binh.new@example.org'
WHERE order_id = 2;

-- A2: INSERT chỉ dùng trường mới.
INSERT INTO sales_order_demo (buyer_email)
VALUES ('dung@example.org');

SELECT order_id, customer_email, buyer_email
FROM sales_order_demo
ORDER BY order_id;
~~~~

Kết quả mong đợi (cột order_id do identity cấp):

| order_id | customer_email | buyer_email |
| ---: | --- | --- |
| 1 | an.new@example.org | an.new@example.org |
| 2 | binh.new@example.org | binh.new@example.org |
| 3 | chi@example.org | chi@example.org |
| 4 | dung@example.org | dung@example.org |

**Thử lỗi có chủ đích** để xác nhận hai giá trị mâu thuẫn bị từ chối:

~~~~sql
-- Dự kiến RAISE EXCEPTION từ trigger; chạy riêng ở môi trường thử.
UPDATE sales_order_demo
SET customer_email = 'one@example.org',
    buyer_email = 'two@example.org'
WHERE order_id = 1;
~~~~

Kết quả chính xác phụ thuộc việc các cột thực sự đổi so với OLD, nhưng với dữ liệu mẫu chúng đều đổi và khác nhau nên trigger từ chối. Không đưa câu lỗi cố ý vào chung một migration cần commit thành công.

### 5.7. Kiểm tra dữ liệu đích trước khi chuyển reader

~~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE buyer_email IS NULL) AS missing_new,
    COUNT(*) FILTER (
        WHERE buyer_email IS DISTINCT FROM customer_email
    ) AS mismatched
FROM sales_order_demo;
~~~~

**Điều kiện tối thiểu trước cutover** trong ví dụ: missing_new = 0 và mismatched = 0 trên toàn bộ phạm vi dữ liệu, đồng thời luồng ghi mới đang giữ dữ liệu đồng bộ. Nên kiểm tra lại sau các đợt tải ghi thực tế, không chỉ ngay sau khi backfill.

Một kiểm tra chất lượng không nên **đánh đồng tổng số dòng với độ đúng**. Hai cột có cùng số lượng giá trị non-null nhưng chứa email khác nhau vẫn sai contract.

### 5.8. Siết ràng buộc mới theo từng bước

Sau khi dữ liệu đã nhất quán, có thể bổ sung kiểm tra buyer_email không NULL:

~~~~sql
ALTER TABLE sales_order_demo
ADD CONSTRAINT ck_buyer_email_present_demo
CHECK (buyer_email IS NOT NULL) NOT VALID;

ALTER TABLE sales_order_demo
VALIDATE CONSTRAINT ck_buyer_email_present_demo;

ALTER TABLE sales_order_demo
ALTER COLUMN buyer_email SET NOT NULL;
~~~~

**Giải thích các bước:**

- Thêm CHECK **NOT VALID** không quét xác nhận toàn bộ hàng cũ ngay ở bước thêm, nhưng constraint vẫn được kiểm tra đối với những hàng được INSERT/UPDATE sau đó theo hành vi PostgreSQL.
- **VALIDATE CONSTRAINT** kiểm tra dữ liệu hiện có; nếu còn NULL, bước này không thành công và phải xử lý trước.
- **SET NOT NULL** biến yêu cầu thành thuộc tính schema rõ ràng. Với PostgreSQL đủ mới, một CHECK đã validate có thể giúp tránh quét lại toàn bảng trong một số trường hợp, nhưng **vẫn phải đánh giá khóa DDL và phiên bản DBMS**, không tự coi là không chặn ghi.

Sau khi đã đặt NOT NULL, CHECK trùng nghĩa có thể được loại bỏ **ở một migration riêng có kiểm soát**, không cần giữ hai ràng buộc mãi mãi:

~~~~sql
ALTER TABLE sales_order_demo
DROP CONSTRAINT ck_buyer_email_present_demo;
~~~~

**Chú ý về thứ tự:** Chỉ thực hiện các bước trên khi các ứng dụng đang chạy **không thể làm buyer_email thành NULL**. Cầu đồng bộ ở ví dụ sẽ từ chối INSERT/UPDATE thiếu cả hai email, nhưng production còn cần xem xét các đường ghi đặc biệt, load job và quyền bypass.

### 5.9. S3 — Switch ứng dụng, chưa vội xóa trường cũ

Ứng dụng mới có thể đọc:

~~~~sql
SELECT buyer_email
FROM sales_order_demo
WHERE order_id = 1;
~~~~

và ghi buyer_email. Trong thời gian **rollback window**, vẫn duy trì **customer_email và trigger** để A0 có thể quay lại nếu cần, với điều kiện chính sách dữ liệu mới vẫn được A0 hiểu.

Tiêu chí chuyển pha:

1. Tất cả record cần thiết đã chuyển và đối soát đạt.
2. Mã ứng dụng mới không cần reader cũ để phục vụ thao tác bình thường.
3. Tỉ lệ lỗi/độ trễ request, lock waits, DB CPU/WAL/replication lag trong giới hạn.
4. Không còn đường ghi cũ ngoài phạm vi được chấp thuận, hoặc chúng vẫn được cầu đồng bộ bảo vệ.
5. Cơ chế rollback ứng dụng đã được thử, kèm điều kiện dữ liệu phù hợp.

**Không dùng feature flag để che việc schema chưa sẵn sàng.** Flag đổi đường đọc/ghi chỉ an toàn nếu **mọi tổ hợp flag + code + schema có thể chạy** đã được xem xét.

### 5.10. S4 — Contract: bỏ cấu trúc cũ khi không còn phụ thuộc

Chỉ sau khi đã xác nhận **không còn instance A0, worker, job hoặc consumer đọc/ghi customer_email** và rollback window kết thúc, thực hiện:

~~~~sql
BEGIN;

DROP TRIGGER trg_sync_sales_order_email_demo
ON sales_order_demo;

DROP FUNCTION sync_sales_order_email_demo();

ALTER TABLE sales_order_demo
DROP COLUMN customer_email;

COMMIT;
~~~~

Lúc này **ứng dụng A0 không còn tương thích**. Nếu triển khai lại A0, nó sẽ lỗi vì customer_email không tồn tại. Đây là lý do bước contract phải là **một mốc phát hành riêng**, không trộn với expand khi đội ngũ chưa có bằng chứng consumer cũ đã nghỉ.

**Đánh đổi khi DROP COLUMN:** PostgreSQL có thể không thu hồi ngay mọi dung lượng vật lý của dữ liệu cột đã bỏ, và DDL vẫn cần khóa. Với bảng lớn, vấn đề kích thước file, vacuum/rewrite và các phụ thuộc view/function/BI phải được đánh giá riêng. Không mặc định DROP COLUMN là thao tác không có chi phí.

### 5.11. Tóm lược đường chuyển đổi

~~~~mermaid
flowchart LR
    A["S0: customer_email"] --> B["S1: thêm buyer_email"]
    B --> C["Cầu đồng bộ 2 cột"]
    C --> D["Backfill + đối soát"]
    D --> E["Bật đọc/ghi buyer_email"]
    E --> F{"Còn A0/consumer cũ?"}
    F -- "Có" --> G["Giữ 2 cột + quan sát"]
    G --> F
    F -- "Không" --> H["Gỡ sync + drop cột cũ"]
    H --> I["S4: buyer_email"]
~~~~

**Bài học:** Mô hình đích chỉ có buyer_email, nhưng để đi đến đó an toàn, hệ thống phải có **những trạng thái trung gian được bảo vệ và đo lường**. Các trạng thái ấy là một phần của thiết kế tiến hóa mô hình, không phải “cột tạm không cần nghĩ đến”.

## 6. Các kiểu migration không thể áp dụng một quy tắc máy móc

### 6.1. Thêm cột mới có giá trị bắt buộc

Giả sử bắt đầu lưu **sales_channel** cho mỗi đơn. Mô hình đích yêu cầu:

~~~~text
sales_channel ∈ {WEB, MOBILE, STORE}
sales_channel không NULL
~~~~

Nếu dữ liệu lịch sử không có thông tin kênh, đặt mọi hàng cũ thành WEB là **bịa thông tin**. Có thể cần giá trị **UNKNOWN** có nghĩa rõ hoặc đối soát từ log đáng tin.

Một tiến trình hợp lý:

~~~~sql
ALTER TABLE sales_order_demo
ADD COLUMN sales_channel VARCHAR(20);

-- Sau khi đã có chính sách phân loại nguồn và các giá trị được xác minh:
UPDATE sales_order_demo
SET sales_channel = 'UNKNOWN'
WHERE sales_channel IS NULL;
~~~~

Đoạn SQL này chỉ hợp lệ nếu nghiệp vụ đã phê duyệt **UNKNOWN** là trạng thái hợp lệ của lịch sử, và các bản ghi cần biết chính xác WEB/MOBILE/STORE không bị gán UNKNOWN bừa bãi.

Trước khi thêm NOT NULL và CHECK:

- Cập nhật mọi đường INSERT để không sinh NULL mới.
- Chạy backfill theo quy tắc nguồn thực tế.
- Kiểm tra các hàng thiếu và giá trị ngoài miền.
- Đặt ràng buộc mới theo pha để không chặn writer cũ.

**DEFAULT chỉ dành cho trường hợp có nghĩa nghiệp vụ:** Một default có thể hợp lý khi giá trị cũ thật sự cùng một ý nghĩa, ví dụ cột loại tiền ở hệ thống **chỉ giao dịch VND**. Một default không thể thay thế dữ liệu mà hệ thống nguồn chưa từng thu thập.

### 6.2. Tách cột địa chỉ dạng chuỗi thành trường có cấu trúc

Giả sử nguồn cũ:

~~~~text
shipping_address = "12 Nguyễn Trãi, P. Bến Thành, TP.HCM"
~~~~

Mô hình mới yêu cầu:

~~~~text
street_address
ward_code
district_code
province_code
country_code
~~~~

Không phải mọi chuỗi cũ đều có đủ thông tin để tách chính xác. Tên phường/quận có thể thay đổi, hai địa danh trùng tên, một số địa chỉ ghi thiếu hoặc là địa chỉ nước ngoài.

Một kế hoạch tốt:

1. **Expand:** thêm các cột mới nullable và quy định kiểu mã địa lý.
2. **Xác minh nguồn:** phân loại những hàng có đủ thông tin, không đủ thông tin và dữ liệu cần xác nhận.
3. **Backfill theo mức độ tin cậy:** chỉ gán province_code khi tìm được ánh xạ đáng tin; lưu thông tin nguồn và kết quả đối soát.
4. **Đổi luồng nhập mới:** thu thập mã có cấu trúc từ người dùng hoặc dịch vụ xác thực địa chỉ phù hợp.
5. **Chuyển đọc:** trong thời gian chuyển đổi, có thể hiển thị chuỗi gốc cho hàng chưa đủ dữ liệu.
6. **Contract có điều kiện:** không xóa chuỗi gốc nếu dữ liệu lịch sử cần tái dựng hoặc quy định lưu giữ yêu cầu giữ lại.

Đây là **thay đổi ngữ nghĩa và chất lượng dữ liệu**, không chỉ rename năm cột. Nếu không chứng minh được phép chuyển đổi, phải ghi **trạng thái chưa xác định** thay vì thông báo migration đã hoàn tất.

### 6.3. Đổi kiểu dữ liệu và đơn vị đo

Giả sử giá sản phẩm cũ lưu **NUMERIC(18,2)** theo VND, muốn chuyển sang **BIGINT biểu diễn đơn vị tiền nhỏ nhất**:

~~~~text
old_amount = 125000.00 VND
new_amount_minor = 125000 (đơn vị nhỏ nhất theo chính sách VND)
~~~~

Trước khi chuyển:

- Xác định đồng tiền và số chữ số thập phân có hiệu lực của mỗi dòng.
- Định nghĩa **làm tròn** hay từ chối số lẻ ngoài chuẩn.
- Kiểm tra khoảng giá trị có nằm trong BIGINT và phép tính có tràn số không.
- Xác định cột mới có giữ đúng ý nghĩa của giá **tại thời điểm giao dịch** không.
- Thử các trường hợp số âm, chiết khấu, hoàn tiền và nhiều tiền tệ nếu có.

Một thay đổi từ NUMERIC sang BIGINT **không chứng minh được** chỉ bằng CAST; nếu không xử lý precision và currency, số có thể thay đổi ý nghĩa. Khi phát sự kiện ra ngoài, phải version hóa hoặc bổ sung trường rõ như **amountMinor + currency** chứ không lặng lẽ đổi đơn vị trong trường amount đang dùng.

### 6.4. Đổi khóa chính từ số tự tăng sang UUID

Khi chuyển từ **customer_id BIGINT** sang **customer_uuid UUID**:

- Một khách cũ cần có **một UUID ổn định**, không tạo UUID khác nhau ở mỗi đợt backfill.
- Những FK nội bộ và tham chiếu ngoài phải có ánh xạ từ khóa cũ sang khóa mới.
- Không được chuyển parent trước rồi bỏ khóa cũ khi child còn tham chiếu.
- CDC, event, cache và API có thể vẫn chứa ID dạng số.
- Các thao tác có thể cần duy trì **cặp khóa cũ–mới** trong một khoảng dài.

Ví dụ bảng ánh xạ:

~~~~text
CUSTOMER_ID_MAPPING(
    old_customer_id BIGINT UNIQUE,
    new_customer_uuid UUID UNIQUE,
    mapping_version,
    created_at
)
~~~~

Nếu mapping là một–một theo nghiệp vụ, cần kiểm tra không có hai khóa cũ trỏ cùng khóa mới hoặc ngược lại. **Một key mới hợp lệ về kiểu không chứng minh đó là cùng khách hàng**; việc bảo toàn danh tính và quan hệ tham chiếu là bất biến cốt lõi.

### 6.5. Tách một bảng thành nhiều bảng

Một bảng **orders** cũ chứa thông tin đơn và một tập trường thanh toán. Sau khi tách bounded context, phần Billing được chuyển sang bảng/bộ lưu trữ riêng. Điều cần xác định:

- Sales vẫn sở hữu **Order**, Billing sở hữu **Payment/Invoice** hay không?
- Giá chốt trong Sales có phải nguồn để tính nghĩa vụ tiền ban đầu, còn số tiền đã quyết toán thuộc Billing?
- Một đơn có thể có nhiều lần thu/hoàn, nên không giữ giả định 1:1 sai.
- Tham chiếu **external_order_ref** và tính idempotent có được quản trị không?
- Có cần projection để hỗ trợ trang hiển thị tổng quan không?

Nếu hai database riêng, không thể lấy một giao dịch DDL/SQL cục bộ làm bảo đảm rằng mọi thay đổi đã commit đồng thời. Phải tách **quyền sở hữu dữ liệu và hợp đồng tích hợp** trước khi chuyển bảng.

## 7. Thêm ràng buộc trong lúc hệ thống vẫn ghi

Những thay đổi **PRIMARY KEY**, **UNIQUE**, **FOREIGN KEY**, **CHECK** và **NOT NULL** không chỉ đổi metadata: chúng có thể phát hiện **dữ liệu lịch sử không hợp lệ** hoặc chặn writer chưa được nâng cấp.

### 7.1. Thêm FK theo pha trên PostgreSQL

Giả sử hai bảng cục bộ:

~~~~sql
CREATE TABLE customer_demo (
    customer_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE order_customer_demo (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT
);
~~~~

Trước khi thêm FK:

~~~~sql
SELECT o.order_id, o.customer_id
FROM order_customer_demo AS o
LEFT JOIN customer_demo AS c
    ON c.customer_id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL;
-- Kỳ vọng 0 dòng mồ côi.
~~~~

Trong PostgreSQL có thể tách:

~~~~sql
ALTER TABLE order_customer_demo
ADD CONSTRAINT fk_order_customer_demo
FOREIGN KEY (customer_id)
REFERENCES customer_demo(customer_id)
NOT VALID;

-- Sau khi làm sạch dữ liệu lịch sử và theo dõi luồng ghi:
ALTER TABLE order_customer_demo
VALIDATE CONSTRAINT fk_order_customer_demo;
~~~~

Ý nghĩa:

- **NOT VALID** cho phép tạo ràng buộc mới mà chưa xác nhận tất cả hàng cũ ngay lúc tạo; các thay đổi mới chịu kiểm tra FK.
- **VALIDATE** kiểm tra dữ liệu đang tồn tại và chỉ thành công khi chúng tuân thủ FK.
- Một FK nullable vẫn cho phép customer_id NULL theo ngữ nghĩa SQL. Nếu nghiệp vụ yêu cầu không NULL, phải đặt thêm **NOT NULL** qua một pha riêng.

**Không nhầm:** NOT VALID **không** có nghĩa FK bị tắt hoàn toàn đối với INSERT/UPDATE mới. Và NOT VALID không phải tùy chọn dùng tương tự cho mọi loại UNIQUE.

### 7.2. Thêm UNIQUE khi dữ liệu lịch sử bị trùng

Nếu muốn UNIQUE(email), trước tiên phải biết **email có thật sự là định danh duy nhất toàn cục không**. Nhiều người có thể dùng cùng email hoặc địa chỉ bị tái sử dụng; nghiệp vụ có thể chỉ yêu cầu duy nhất theo tenant hoặc trong tập tài khoản đang hoạt động.

Giả sử quy tắc đã chốt là **external_code duy nhất theo tenant**. Kiểm tra trùng:

~~~~sql
-- Bảng ví dụ giả định đã tồn tại với hai cột tenant_id/external_code.
SELECT tenant_id, external_code, COUNT(*) AS duplicates
FROM customer_external_demo
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
~~~~

Truy vấn này là **mẫu kiểm tra trên bảng giả định**, không phải câu lệnh chạy độc lập trong bộ ví dụ sales_order_demo. Nếu có dữ liệu trùng, phải xác định **bản ghi nào là cùng một thực thể**, không tự chọn MIN(id) rồi xóa những hàng còn lại.

Khi dữ liệu đã sạch, PostgreSQL có thể hỗ trợ tạo unique index đồng thời:

~~~~sql
-- Chạy riêng, ngoài khối BEGIN...COMMIT.
CREATE UNIQUE INDEX CONCURRENTLY ux_customer_external_demo
ON customer_external_demo(tenant_id, external_code);
~~~~

**Điểm cần biết:**

- **CREATE INDEX CONCURRENTLY** không được thực hiện bên trong transaction block tường minh.
- Nó vẫn tiêu thụ tài nguyên và có thể thất bại nếu còn giá trị trùng hoặc có transaction/hoạt động ghi cạnh tranh.
- Một lần tạo thất bại có thể để lại index trạng thái **INVALID**, cần được kiểm tra và xử lý theo quy trình an toàn trước khi thử lại.
- Sau đó, nếu cần một **UNIQUE constraint** ở mức schema thay vì chỉ unique index, việc gắn index vào constraint phải xét điều kiện hỗ trợ của DBMS.
- Các cột NULL có ngữ nghĩa duy nhất riêng; nếu nghiệp vụ không chấp nhận NULL, cần NOT NULL và kiểm tra phù hợp.

Đừng đặt tên tập migration là “atomic rollback” nếu trong đó có CREATE INDEX CONCURRENTLY; công cụ migration có thể cần cấu hình **không bao transaction cho riêng bước ấy**.

### 7.3. Bắt buộc NOT NULL không chỉ là chạy một ALTER

Muốn đổi cột tùy chọn thành bắt buộc:

1. Định nghĩa **giá trị hợp lệ thực sự** ở mức nghiệp vụ.
2. Chặn luồng ghi mới tạo NULL, kể cả batch/consumer cũ.
3. Backfill những hàng lịch sử có nguồn dữ liệu đáng tin.
4. Kiểm tra số hàng còn NULL và các trường hợp không xác định.
5. Thêm/validate constraint, kiểm tra lock, sau đó đặt NOT NULL.
6. Giám sát lỗi ghi và chuẩn bị forward fix nếu còn đường ghi không tương thích.

Một giá trị DEFAULT chỉ làm migration dễ hơn nếu nó **thật sự có nghĩa**. Không lấy tiện lợi của SQL làm lý do khẳng định mọi đơn cũ thuộc kênh WEB hoặc mọi khách cũ có country_code = VN.

### 7.4. Constraint nào thuộc trạng thái trung gian?

Một số ràng buộc có thể **tạm lỏng hơn** mô hình đích:

- buyer_email nullable trong S1 nhưng bắt buộc ở S4.
- Hai tên cột cùng tồn tại nhưng phải giữ **giá trị bằng nhau** trong giai đoạn chuyển.
- Khóa cũ và khóa mới cùng được lưu trong bảng mapping.
- Bảng mới có cột source_version hoặc migration_status để phục vụ đối soát.

Nếu có ràng buộc tạm thời, phải ghi **khi nào được loại bỏ, bằng chứng đã an toàn và ai phê duyệt**. Không để cột/chỉ mục/trigger tạm trở thành di sản không ai dám sửa.

## 8. Khóa DDL, thời gian chạy và chiến lược migration lớn

### 8.1. DDL không phải lúc nào cũng “metadata only”

Trong PostgreSQL, nhiều thao tác **ALTER TABLE** cần khóa, đôi khi ở mức ngăn các thao tác đọc/ghi khác trong lúc thực thi hoặc chờ khóa. Thời gian chạy của lệnh SQL chỉ là một phần của rủi ro: nếu lệnh bị **chờ khóa phía sau một transaction dài**, những request đến sau có thể cũng bị ảnh hưởng.

Trước khi áp dụng trên bảng lớn:

- Tìm transaction kéo dài và các thao tác ghi/đọc lâu.
- Đánh giá **lock level**, thời gian chờ và khả năng quét hoặc rewrite bảng theo loại DDL cụ thể.
- Đặt **lock_timeout**, **statement_timeout** và kế hoạch retry theo chính sách đội vận hành.
- Ước tính WAL, replica lag, I/O, dung lượng trống và tác động vacuum.
- Thử trên dữ liệu có kích thước/phân bố gần production nếu có điều kiện.
- Có cửa sổ triển khai và tiêu chí dừng nếu lock waits vượt ngưỡng.

**Không** đặt lock_timeout lớn vô hạn chỉ để một migration cuối cùng chạy được; người dùng có thể phải trả giá bằng độ trễ dịch vụ.

### 8.2. Backfill theo lô và khả năng chạy lại

Một backfill tốt thường có:

- **Khóa phạm vi ổn định:** phân đoạn theo PK hoặc partition.
- **Batch size** phù hợp với khả năng ghi, lưu lượng và replication.
- **Idempotency:** chạy lại không tạo dòng trùng hoặc ghi đè dữ liệu mới hơn.
- **Checkpoint hoặc tiến độ:** biết hàng nào đã xử lý, còn hàng nào lỗi.
- **Retry có giới hạn:** phân biệt lỗi tạm thời với lỗi dữ liệu.
- **Throttling:** giảm tải nếu DB/replica vượt ngưỡng.
- **Đối soát cuối:** kiểm tra nội dung, không chỉ COUNT.

Trong ví dụ email, WHERE buyer_email IS NULL là cách nhận diện hàng chưa chuyển. Với bài toán giá chuyển đổi phức tạp, chỉ có cờ is_migrated có thể chưa đủ: cần **version của phép chuyển đổi, thông tin nguồn và checksum/đối soát** nếu kết quả có thể sai âm thầm.

### 8.3. Không đọc một snapshot rồi cho rằng dữ liệu sẽ đứng yên

Nếu chạy:

~~~~text
10:00:00  Count mismatch = 0
10:00:01  Writer A0 sửa customer_email
10:00:02  Bật reader A2
~~~~

thì kiểm tra lúc 10:00 không đủ chứng minh trạng thái 10:02. Vì vậy:

1. Cần **cầu đồng bộ** hoặc chặn writer cũ có kiểm chứng trong giai đoạn chuyển.
2. Kiểm tra lại sau khi chịu tải ghi bình thường.
3. Theo dõi mismatch liên tục hoặc theo chu kỳ có kiểm soát trước contract.
4. Xác định một mốc **cutover** gắn với bằng chứng mọi writer/consumer đã đổi.

Tính đúng của migration là **tính chất của hệ thống đang chuyển đổi**, không chỉ một phép quét dữ liệu tĩnh.

### 8.4. Sharding, partition và nhiều tenant

Nếu cùng ứng dụng vận hành nhiều database tenant hoặc shard, có thể xảy ra:

~~~~text
Shard 1: S2 - đã backfill
Shard 2: S1 - đang ghi hai cột
Shard 3: S0 - chưa expand
~~~~

Một ứng dụng mới dùng buyer_email trên **mọi shard** sẽ lỗi khi truy cập Shard 3.

Phải xác định:

- Migration được chạy **theo shard**, từng tenant hay đồng thời?
- Mỗi shard có version/state riêng được kiểm chứng không?
- Routing hoặc feature flag có biết shard nào đã sẵn sàng?
- Có cơ chế ngăn tenant mới được tạo với schema cũ sau khi migrator đi qua không?
- Có thể đánh dấu phát hành hoàn tất khi vẫn còn một shard/tenant lag không?

Không dùng một trường “schema_version toàn cụm = 4” để che thực tế các shard đang ở phiên bản khác nhau. Chính sách triển khai từng phần phải được thể hiện bằng **readiness theo phạm vi**.

## 9. Rollback, forward fix và khả năng phục hồi

### 9.1. Bốn khái niệm không đồng nghĩa

| Khái niệm | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| **Rollback ứng dụng** | Chạy lại build A0 sau khi A2 lỗi | Chỉ an toàn nếu schema và dữ liệu vẫn tương thích A0 |
| **Rollback schema** | Chạy migration ngược hoặc khôi phục DDL | Có thể làm mất cột/dữ liệu mới hoặc không thực hiện được an toàn |
| **Forward fix** | Tạo một phiên bản mới sửa lỗi mà giữ dữ liệu đã ghi | Cần kế hoạch, kiểm thử và quyền triển khai nhanh |
| **Restore dữ liệu** | Khôi phục từ backup hoặc PITR theo thời điểm | Có thể mất thay đổi sau mốc khôi phục, cần xác định phạm vi/đối soát |

Một câu **DROP COLUMN** có thể được đảo ngược về **hình dạng schema** bằng ADD COLUMN, nhưng không có nghĩa dữ liệu cũ đã xóa được phục hồi. Tương tự, đổi kiểu từ chuỗi sang số có thể làm mất định dạng/giá trị không chuyển được; migration DOWN đơn giản không thể tái tạo những gì đã mất.

### 9.2. Rollback window là cam kết phải có bằng chứng

Trong giai đoạn S3 của ví dụ:

~~~~text
Schema: customer_email + buyer_email + trigger
Ứng dụng mới: đọc/ghi buyer_email
Ứng dụng cũ: có thể quay lại đọc/ghi customer_email
~~~~

Nếu không có thay đổi ngữ nghĩa mà A0 không hiểu, rollback A2 → A0 **có khả năng** hoạt động vì trigger vẫn duy trì customer_email. Khi loại bỏ cột cũ ở S4, khả năng rollback này không còn.

Vì vậy:

- **Rollback window** phải được đặt cụ thể theo nhu cầu vận hành và tốc độ phát hiện lỗi.
- Không thực hiện contract ngay khi ứng dụng A2 “green” trong vài phút nếu còn chưa quan sát tải điển hình hoặc job theo lịch.
- Có thể lưu lại cấu trúc cũ lâu hơn một phiên bản ứng dụng, với chi phí ghi và quản trị có giới hạn rõ.
- Khi contract xong, rollback code cần một **kế hoạch phục hồi khác**, không chỉ bấm deploy lại build cũ.

### 9.3. Không tự động DOWN trên database có dữ liệu thật

Nhiều hệ thống lưu migration theo thứ tự và có thể định nghĩa bước DOWN. Tuy nhiên, lệnh DOWN chỉ an toàn khi:

1. Dữ liệu mới có thể biểu diễn trọn vẹn ở schema cũ.
2. Không có writer còn ghi vào trường/mô hình mới.
3. Các constraint, index, view và tham chiếu ngoài không bị phá.
4. Có backup/khả năng phục hồi và kế hoạch đối soát.
5. Hệ thống biết **mốc dữ liệu nào** được chấp nhận khi quay về.

Ví dụ chuyển một cột **full_name** thành first_name và last_name có thể không đảo ngược chính xác nếu người dùng đã sửa hai phần riêng và mất khoảng trắng/cách hiển thị gốc. Đảo về full_name bằng phép nối tên mới là **một quy tắc kinh doanh**, không phải phục hồi chính xác trạng thái trước.

### 9.4. Restore backup không giống rollback có chọn lọc

Khôi phục cả database về thời điểm trước migration có thể làm mất **đơn hàng hoặc thanh toán hợp lệ phát sinh sau thời điểm đó**. Đây là tác động nghiệp vụ nghiêm trọng.

Trước thay đổi lớn:

- Biết **RPO/RTO** theo chính sách vận hành: mức mất dữ liệu và thời gian phục hồi được phép.
- Kiểm tra khả năng backup/PITR hoặc snapshot thực sự có thể phục hồi.
- Tập dượt phục hồi ở môi trường phù hợp, không chỉ thấy “backup successful”.
- Xác định cách đối soát hoặc tái xử lý dữ liệu đã phát sinh sau mốc backup.
- Phân biệt sự cố **metadata** và sự cố **dữ liệu bị chuyển sai** để chọn phục hồi chính xác.

**Forward fix** có thể là cách ít rủi ro hơn nếu dữ liệu mới đã được ghi và có thể sửa bằng một migration tiếp theo. Nhưng không được dùng “roll forward” như lý do bỏ qua kiểm thử, audit hoặc bảo vệ dữ liệu.

## 10. Ứng dụng Java và ORM phải tương thích với nhiều trạng thái

Lược đồ có thể đã expand, nhưng Java/JDBC/JPA vẫn có thể bị phá nếu SQL của ứng dụng kỳ vọng một cấu trúc duy nhất.

### 10.1. Chữ ký Java không là bằng chứng SQL tương thích

Xét hai DTO:

~~~~java
record OldOrderView(long id, String customerEmail) {}
record NewOrderView(long id, String buyerEmail) {}
~~~~

Trình biên dịch Java biết các trường khác nhau, nhưng nếu repository cũ còn chạy:

~~~~java
String oldSql = """
    SELECT order_id, customer_email
    FROM sales_order_demo
    WHERE order_id = ?
    """;
~~~~

thì nó **sẽ lỗi khi cột customer_email bị xóa**. Ngược lại, ứng dụng mới:

~~~~java
String newSql = """
    SELECT order_id, buyer_email
    FROM sales_order_demo
    WHERE order_id = ?
    """;
~~~~

không chạy trên S0. Vì vậy kiểm thử compile Java và unit test bằng mock repository **không thay thế integration test với trạng thái schema thật**.

### 10.2. Read fallback có vai trò nhưng không đủ cho write

Ở trạng thái S1 khi buyer_email có thể NULL:

~~~~sql
SELECT
    order_id,
    COALESCE(buyer_email, customer_email) AS buyer_email
FROM sales_order_demo;
~~~~

Đây là cách đọc trong giai đoạn chuyển đổi. Nhưng:

- Nếu dữ liệu buyer_email cũ **không NULL nhưng đã lệch**, COALESCE vẫn ưu tiên giá trị sai.
- Nếu writer cũ sửa customer_email mà không có đồng bộ, fallback **không** sửa buyer_email.
- Trên S3 chỉ còn buyer_email, truy vấn này **không còn chạy được** vì nó vẫn tham chiếu customer_email.

Vì vậy cần phân biệt:

1. **A1 — mã chuyển tiếp** dùng hai cột, chỉ chạy trong một số trạng thái.
2. **A2 — mã cuối** chỉ dùng cột mới, chạy được sau contract.

Không nên giữ SQL fallback mãi rồi xóa cột mà không tìm các đoạn mã còn tham chiếu tên cũ.

### 10.3. ORM entity và schema migration

Với JPA/Hibernate hoặc một ORM khác, cần chú ý:

- Annotation mapping cột cũ/mới có thể thay đổi SQL tự sinh.
- Một phiên bản entity mới có thể fail **khi khởi động**, kể cả chưa xử lý request.
- Tự động cập nhật schema khi runtime startup có thể đua với nhiều instance, khó kiểm soát thứ tự deploy và bỏ qua kế hoạch backfill.
- Converter hoặc listener có thể ghi dữ liệu với ngữ nghĩa mới trước khi các consumer cũ thích nghi.
- Bản scan entity của một job offline có thể vẫn trỏ cột đã bỏ.

Trong môi trường cần kiểm soát tiến hóa nghiêm ngặt, nên có **migration review và deployment orchestration tường minh**, không mặc định mọi instance được phép tự ALTER TABLE khi khởi động. Quyết định cụ thể phụ thuộc công cụ, kiến trúc và yêu cầu vận hành.

### 10.4. Feature flag và schema readiness

Một chiến lược có thể dùng:

~~~~text
Feature flag: READ_BUYER_EMAIL

OFF: A1 đọc theo đường tương thích
ON : A1/A2 đọc buyer_email là nguồn chính
~~~~

Điều kiện bật flag:

- Schema S1/S2 đã có buyer_email ở mọi database/shard cần dùng.
- Backfill và dữ liệu ghi mới đã được kiểm chứng.
- Các instance mang mã đọc trường mới thực sự đã được triển khai.
- Có phương án quay lại khi số liệu sai, không chỉ khi HTTP 500 tăng.

**Feature flag không phải công cụ thay thế migration:** bật flag sai ở một shard S0 có thể gây lỗi SQL; tắt flag không chữa được các hàng bị backfill sai nghĩa.

### 10.5. Producer/consumer và contract dữ liệu ngoài database

Nếu ứng dụng phát:

~~~~json
{
  "eventType": "order-created",
  "schemaVersion": 1,
  "payload": {
    "customerEmail": "an@example.org"
  }
}
~~~~

rồi đổi ngay sang:

~~~~json
{
  "eventType": "order-created",
  "schemaVersion": 2,
  "payload": {
    "buyerEmail": "an@example.org"
  }
}
~~~~

thì consumer cũ vẫn đọc **customerEmail** có thể lỗi hoặc bỏ sót dữ liệu. Việc rename cột PostgreSQL **không tự đổi** hợp đồng event một cách an toàn.

Một kế hoạch có thể:

- Giữ **event v1** trong thời gian consumer cũ còn phụ thuộc.
- Công bố **event v2** với ngữ nghĩa đã xác nhận.
- Cho consumer hỗ trợ cả v1 và v2 trong cửa sổ chuyển tiếp, hoặc có adapter chuyển đổi.
- Kiểm thử **replay** event cũ sau khi database đã ở S3.
- Định nghĩa thời điểm ngừng phát/nhận v1 dựa trên bằng chứng consumer đã chuyển.

Nếu hai trường có cùng ý nghĩa, bản v2 có thể chỉ là đổi tên. Nếu ý nghĩa khác, phải thiết kế chuyển đổi hoặc giới hạn tính tương thích, không sửa payload cũ âm thầm.

## 11. Đồng bộ nhiều luồng ghi và dữ liệu bất đồng bộ

### 11.1. Application dual-write khác transactional outbox

**Dual-write hai cột trong cùng một database transaction** là một cách duy trì biểu diễn cũ/mới. Nó có thể an toàn nếu tất cả writer hợp lệ đều dùng chung giao thức và lỗi được rollback cùng transaction.

**Dual-write hai hệ thống độc lập**, ví dụ ghi PostgreSQL và gửi message hoặc ghi hai database trong hai transaction khác nhau, **không có atomicity mặc định**. Nếu một bên thành công và bên còn lại thất bại, hệ thống có thể lệch.

Đối với tích hợp với broker, **transactional outbox** thường được dùng để lưu thay đổi dữ liệu và ý định phát event trong một transaction của nguồn, sau đó relay gửi đi. Outbox giúp giảm rủi ro **commit thành công nhưng không có bản ghi sự kiện cần phát**, nhưng vẫn cần consumer idempotent vì event có thể được giao lại.

**Đừng nhầm hai khái niệm cùng tên dual-write:**

- Ghi **hai cột của cùng một row** trong một giao dịch.
- Ghi **hai hệ thống** độc lập, cần giao thức độ tin cậy và bù/đối soát.

### 11.2. Dữ liệu đến muộn

Khi chuyển từ event v1 sang v2, một event v1 có thể đến **sau** ngày ứng dụng bắt đầu dùng v2. Consumer mới cần xác định:

- Có tiếp tục nhận v1 trong bao lâu không?
- Có mapping sang mô hình mới có ý nghĩa không?
- Event xảy ra từ thời điểm nào và dữ liệu có cần gắn phiên bản lịch sử không?
- Có phân biệt **occurredAt** với **processedAt** không?
- Một event được phát lại có tạo bản ghi trùng hoặc cập nhật lùi trạng thái mới hơn không?

Schema version của message không tự cho biết **trình tự nghiệp vụ**; cần eventId, aggregate version hoặc quy tắc ordering tùy luồng dữ liệu.

### 11.3. CDC và downstream đọc lược đồ vật lý

Một công cụ CDC có thể đọc thay đổi từ cột customer_email của bảng nguồn. Khi thêm buyer_email rồi xóa customer_email, **dạng sự kiện CDC**, snapshot và cấu hình connector có thể đổi.

Trước contract:

- Kiểm kê connector/subscription đang đọc bảng/cột cũ.
- Xác minh downstream đã hiểu cột mới hoặc có phép chuyển tương thích.
- Kiểm tra snapshot/backfill không gây dữ liệu trùng.
- Quan sát offset/lag và tiến độ xử lý trước khi xóa cột.
- Xác định chiến lược khi phải phát lại dữ liệu lịch sử có schema cũ.

Không kết luận “không còn app nào đọc customer_email” chỉ vì tìm kiếm mã Java của một service không thấy tên cột; **BI, CDC, ETL, warehouse, export và ứng dụng bên ngoài** có thể còn phụ thuộc.

### 11.4. Mô hình document và phân tích cũng cần trạng thái trung gian

Các nguyên tắc tương tự áp dụng ngoài SQL:

- **Document database:** trong một thời gian có document chứa schema v1, v2 hoặc pha trộn; reader phải nhận biết version và kiểm tra trường thiếu trước khi cleanup.
- **Event stream:** sự kiện cũ vẫn nằm trong retention hoặc replay log; consumer cần hỗ trợ các phiên bản hợp đồng trong khoảng đã cam kết.
- **Warehouse:** fact/dimension mới có thể được backfill theo partition, cần đối soát KPI trước khi đổi dashboard hoặc semantic layer.
- **Graph database:** đổi loại cạnh/nhãn có thể cần giữ quan hệ cũ và mới trong cửa sổ tương thích, với kiểm chứng không nhân bản đường đi.

**Điểm chung là hợp đồng ngữ nghĩa và khả năng đọc dữ liệu trộn phiên bản**, không phải cú pháp DDL của một hệ quản trị duy nhất.

## 12. Kiểm thử các trạng thái trung gian

### 12.1. Unit test không kiểm tra đủ compatibility

Một bộ unit test chỉ mock repository có thể pass dù mã mới truy vấn buyer_email trên một database S0. Kiểm thử migration cần xét **tổ hợp ứng dụng và lược đồ đang xảy ra thực tế**, bao gồm khả năng chuyển trạng thái.

Ma trận kiểm thử ví dụ:

| Trạng thái | Ứng dụng cần thử | Tình huống tối thiểu |
| --- | --- | --- |
| **S0** | A0 | Đọc/ghi đơn cũ, không có cột mới |
| **S1 chưa backfill hết** | A0, A1 chuyển tiếp | Đọc hàng cũ chưa có buyer_email, tạo đơn mới, sửa email cũ |
| **S1 với trigger** | A0, A2 | Writer hai phiên bản cập nhật hai cột, dữ liệu vẫn khớp |
| **S2 đã backfill** | A0, A2 | Đọc đủ lịch sử, đối soát COUNT/mismatch, ghi đồng thời |
| **S3 cutover** | A2, A0 nếu còn trong rollback window | Reader mới không phụ thuộc dữ liệu cũ; rollback có điều kiện |
| **S4 đã contract** | Chỉ A2 và consumer tương thích | Không còn câu SQL tham chiếu customer_email |

**Không chạy A0 trên S4 rồi kỳ vọng nó pass**: đó là tổ hợp không tương thích được kế hoạch chủ ý loại bỏ. Điều cần thử là **không còn instance hoặc job A0 nào được phép truy cập S4**.

### 12.2. Kiểm thử dữ liệu cũ và dữ liệu mới

Một tập fixture hữu ích:

~~~~text
R1: hàng cũ, customer_email có, buyer_email NULL.
R2: hàng cũ đã backfill, hai trường bằng nhau.
R3: hàng mới được A0 tạo trong giai đoạn chuyển.
R4: hàng mới được A2 tạo trong giai đoạn chuyển.
R5: cùng một hàng bị A0 cập nhật rồi A2 cập nhật.
R6: yêu cầu cố ghi hai email khác nhau.
R7: dữ liệu có email rỗng/sai định dạng theo quy tắc miền.
R8: job báo cáo cũ chạy ngay trước thời điểm contract.
~~~~

Các phép kiểm tra:

- **R1:** reader chuyển tiếp có fallback và backfill có thể hoàn thiện.
- **R2:** dữ liệu khớp và có thể đọc cột mới.
- **R3/R4:** trigger hoặc giao thức sync bảo toàn cả hai trường.
- **R5:** xác định xung đột cập nhật và versioning nếu hai writer cùng thay đổi giá trị.
- **R6:** từ chối giá trị mâu thuẫn.
- **R7:** kiểm tra giá trị theo ngữ nghĩa, không chỉ NOT NULL.
- **R8:** phát hiện consumer chưa chuyển trước khi drop.

### 12.3. Kiểm thử đồng thời

Với hai phiên bản ứng dụng cùng ghi một row:

1. Transaction T1 đọc email và version của đơn.
2. Transaction T2 cập nhật email, commit.
3. T1 cố ghi dựa trên version đã cũ.

Nếu quy tắc nghiệp vụ không cho phép ghi đè cập nhật mới hơn, có thể dùng **optimistic locking** bằng cột version hoặc một điều kiện WHERE dựa trên version:

~~~~sql
-- Ví dụ độc lập: giả định đã thêm cột row_version BIGINT NOT NULL
-- vào sales_order_demo với giá trị ban đầu được backfill là 0.
UPDATE sales_order_demo
SET buyer_email = 'new@example.org',
    row_version = row_version + 1
WHERE order_id = 1
  AND row_version = 7
RETURNING order_id, row_version;
~~~~

Nếu T2 đã cập nhật version từ 7 lên 8, câu UPDATE của T1 sẽ không trả về hàng nào. Ứng dụng phải xử lý **conflict**, ví dụ đọc lại và yêu cầu người dùng xác nhận. Trên đường ghi thực tế, mọi writer được kỳ vọng tham gia version check phải thực hiện cùng giao thức; nếu A0 bỏ qua row_version, optimistic locking **không còn bảo vệ đầy đủ**.

**Cảnh báo:** Trigger đồng bộ hai cột trong mục 5 không giải quyết lost update tổng quát. Nó chỉ giữ hai biểu diễn của **cùng một trường** bằng nhau theo mỗi lần ghi thành công.

### 12.4. Kiểm thử kết quả sau restart và replay

Không chỉ thử migration trong một lần chạy liên tục. Cần mô phỏng:

- Backfill chạy được 40% rồi tiến trình dừng.
- Lần chạy sau tiếp tục ở đúng chỗ, không ghi đè dữ liệu mới.
- Một lô gặp hàng lỗi do dữ liệu không hợp lệ.
- Relay outbox phát trùng; consumer vẫn không áp dụng tác dụng phụ hai lần.
- Cắt chuyển ứng dụng thất bại giữa các instance; A0 và A2 cùng hoạt động.
- Schema đã expand, nhưng một tenant/shard chưa cập nhật.
- Báo cáo cũ chạy theo lịch ít gặp và chỉ phát hiện sau nhiều giờ.

**Kiểm thử chịu lỗi là một phần của khả năng tiến hóa mô hình**. Nếu chỉ có “happy path: schema ở S4 và app ở A2”, ta chưa biết liệu hệ thống có đi qua S1/S2/S3 một cách an toàn hay không.

### 12.5. Kiểm thử hợp đồng bên ngoài

Đối với API/event có phiên bản riêng:

| Producer | Consumer | Cần xác nhận |
| --- | --- | --- |
| Event v1 | Consumer v1 | Hợp đồng cũ vẫn chạy trong cửa sổ hỗ trợ |
| Event v1 | Consumer chuyển tiếp | Có thể đọc và ánh xạ trường cũ |
| Event v2 | Consumer chuyển tiếp | Trường mới có nghĩa đúng; không tạo bản ghi trùng |
| Event v2 | Consumer v2 | Đạt hợp đồng mới |
| Replay v1 sau cutover | Consumer v2 hoặc adapter | Có kế hoạch đọc/migrate hoặc từ chối có kiểm soát |

Không buộc mọi consumer hỗ trợ mọi version **vĩnh viễn**. Nhưng khoảng hỗ trợ, thời điểm contract và cách xử lý lịch sử phải được công bố và kiểm chứng.

## 13. Quan sát tiến độ và tiêu chí chuyển pha

### 13.1. Metric không chỉ là “migration succeeded”

Một lệnh migration áp dụng xong có thể có **exit code 0** nhưng dữ liệu còn sai, API còn lỗi và replica đang trễ. Theo dõi ít nhất:

| Nhóm | Metric hoặc bằng chứng |
| --- | --- |
| **Schema readiness** | Phiên bản migration thực tế ở từng database/shard/tenant |
| **Data completeness** | Số hàng cần backfill, số hàng còn NULL hoặc chưa chuyển |
| **Data equivalence** | Số mismatch giữa hai biểu diễn; kết quả đối soát theo khoảng thời gian |
| **Write compatibility** | Tỷ lệ INSERT/UPDATE lỗi theo phiên bản app và loại lỗi SQL |
| **Reader compatibility** | Số truy vấn còn dùng cột cũ, lỗi column-not-found, lỗi mapping |
| **DB health** | Lock waits, transaction duration, CPU, I/O, WAL, deadlocks |
| **Replication** | Replica replay lag và khả năng truy vấn đọc ở bản sao |
| **Backfill execution** | Rows/batch, batches failed, retry, thời gian chờ, checkpoint |
| **Event/CDC** | Consumer lag, schema errors, dead-letter, duplicate handling |
| **Business correctness** | Tổng đơn, doanh thu, tỉ lệ mồ côi và các invariant đặc thù |

Những chỉ số cần có **baseline và ngưỡng phù hợp tải thật**. “COUNT mismatch = 0” rất hữu ích, nhưng có thể không đủ khi dữ liệu sai **cùng nhau ở cả cột cũ và mới**. Khi thay nghĩa hoặc tách bảng, phải đối soát với nguồn/hợp đồng nghiệp vụ đáng tin cậy, không chỉ so hai bản sao của một lỗi.

### 13.2. Bộ kiểm tra SQL cho ví dụ email

~~~~sql
-- Số hàng chưa hoàn thiện và số hàng lệch.
SELECT
    COUNT(*) AS all_rows,
    COUNT(*) FILTER (WHERE buyer_email IS NULL) AS pending_rows,
    COUNT(*) FILTER (
        WHERE buyer_email IS DISTINCT FROM customer_email
    ) AS inconsistent_rows
FROM sales_order_demo;
~~~~

Nếu muốn tìm hàng bị lệch để xử lý:

~~~~sql
SELECT order_id, customer_email, buyer_email
FROM sales_order_demo
WHERE buyer_email IS DISTINCT FROM customer_email
ORDER BY order_id
LIMIT 100;
~~~~

Những truy vấn trên chỉ chạy **trước S4**, khi cả hai cột còn tồn tại. Sau contract, cần bỏ hoặc thay các job/monitor còn tham chiếu customer_email; chính script đối soát cũ cũng là một **consumer của schema cũ**.

### 13.3. Go/no-go ở từng pha

**Trước Expand:**

- Migration được review, có mô tả rủi ro khóa và tác động lên application/consumer.
- Biết phạm vi database và các shard/tenant.
- Có phương án quan sát lỗi/rollback phù hợp.
- Thử migration trên môi trường gần thực tế nếu có thể.

**Trước Backfill:**

- Cấu trúc mới đã có.
- Cầu đồng bộ/đường writer tương thích đã hoạt động.
- Có quy tắc mapping dữ liệu và xử lý trường hợp không thể chuyển.
- Có giới hạn tốc độ và cách chạy lại.

**Trước Switch:**

- Đối soát đúng theo hợp đồng; dữ liệu mới được ghi chính xác.
- Số lỗi writer/reader trong ngưỡng.
- Đã thử các trạng thái hỗn hợp A0/A2.
- Có phương án dừng hoặc quay lại đường đọc cũ.

**Trước Contract:**

- Không còn đường đọc/ghi của A0 hoặc consumer cần schema cũ.
- Rollback window đã kết thúc có phê duyệt.
- Backup/restore hoặc forward-fix plan đã được xem xét.
- Các view, trigger, CDC, báo cáo, job và quyền đã được kiểm kê.
- Đã kiểm tra ràng buộc đích và hành vi của A2 trên trạng thái S4.

Không biến kiểm tra thành thủ tục hình thức: nếu vẫn còn một batch cuối tháng cần customer_email, **không nên xóa cột chỉ vì các instance web đã nâng cấp**.

### 13.4. Những gì một dashboard không tự chứng minh

Nếu dashboard cho biết:

~~~~text
Backfill: 100%
Schema version: V004
App instances upgraded: 100%
Error rate: low
~~~~

vẫn cần hỏi:

- “100%” có bao phủ **mọi tenant và dữ liệu lịch sử** không?
- Event replay có thể tạo dữ liệu **v1** sau ngày cutover không?
- Công cụ BI có query ngoài đường triển khai web không?
- Giá trị mới có đúng **nghĩa nghiệp vụ** chứ không chỉ không NULL không?
- Ai xác nhận migration không làm sai báo cáo hoặc khoản tiền?

Quan sát tốt là **bằng chứng cho quyết định**, không thay thế việc xác nhận hợp đồng ngữ nghĩa.

## 14. Những kiểu lỗi thường gặp

### 14.1. Rename trực tiếp khi còn mã cũ

**Hiện tượng:** ALTER TABLE RENAME COLUMN thành công, nhưng ứng dụng A0 lỗi SELECT/INSERT.

**Nguyên nhân:** Thay đổi vật lý không tương thích được triển khai trước khi kiểm soát vòng đời ứng dụng.

**Khắc phục:** Expand hai cột, đồng bộ/đối soát, chuyển writer/reader, rồi contract.

### 14.2. Chỉ dual-write ở mã mới, bỏ quên writer cũ

**Hiện tượng:** buyer_email đúng ngay sau backfill, vài phút sau lệch customer_email.

**Nguyên nhân:** A0 vẫn UPDATE cột cũ và không cập nhật cột mới.

**Khắc phục:** Quản trị đường ghi hỗn hợp bằng DB synchronization hoặc yêu cầu tất cả writer chuyển lên giao thức mới trước khi cho phép sử dụng trường mới; có giám sát mismatch.

### 14.3. Backfill rồi bỏ qua dữ liệu đến muộn

**Hiện tượng:** Một batch import cũ nạp lại dữ liệu không có trường mới sau khi backfill kết thúc.

**Nguyên nhân:** Phạm vi migration chưa bao gồm dữ liệu đến trễ/replay.

**Khắc phục:** Adapter tương thích, cầu đồng bộ trong cửa sổ cần thiết, kiểm tra tiếp tục khi có replay, contract theo bằng chứng consumer.

### 14.4. Dùng default sai nghĩa

**Hiện tượng:** Tất cả đơn trước 2026 bị gán sales_channel=WEB mặc dù nhiều đơn được tạo tại cửa hàng.

**Nguyên nhân:** Coi default thuận tiện là dữ liệu lịch sử chính xác.

**Khắc phục:** Backfill từ nguồn đáng tin, hoặc dùng trạng thái UNKNOWN được phê duyệt, có công bố hạn chế lịch sử.

### 14.5. Siết constraint trước khi writer sẵn sàng

**Hiện tượng:** Đã thêm NOT NULL, ứng dụng cũ còn INSERT thiếu trường mới và liên tục lỗi.

**Nguyên nhân:** Siết invariant đích trước khi đường ghi mới có thể đáp ứng.

**Khắc phục:** Đặt constraint theo pha, triển khai writer tương thích, kiểm tra dữ liệu rồi mới validate/enforce.

### 14.6. Xóa cột khi job định kỳ chưa nâng cấp

**Hiện tượng:** Web chạy tốt, báo cáo cuối tuần thất bại vì còn SELECT customer_email.

**Nguyên nhân:** Danh sách consumer chỉ bao gồm các service chạy liên tục.

**Khắc phục:** Kiểm kê batch, BI, export, CDC, stored procedures, view và phần mềm đối tác, rồi chạy contract tests trước DROP.

### 14.7. Rollback code sau khi dữ liệu đã đổi nghĩa

**Hiện tượng:** A0 đọc cột cũ nhưng không hiểu đơn vị tiền mới hoặc trạng thái enum mới.

**Nguyên nhân:** Tồn tại cột cũ không đảm bảo **tương thích ngữ nghĩa**.

**Khắc phục:** Thử rollback trên dữ liệu mới thực sự, giữ adapter hoặc forward-fix; không tự coi có DOWN migration là an toàn.

### 14.8. Backfill quá lớn trong một transaction

**Hiện tượng:** DB tăng WAL, replica lag, lock waits, transaction kéo dài.

**Nguyên nhân:** Chạy UPDATE hàng triệu dòng trong một giao dịch không giới hạn.

**Khắc phục:** Batch nhỏ có checkpoint/idempotency, đo hiệu năng, throttling và giới hạn thời gian triển khai.

### 14.9. Lịch sử migration giữa môi trường khác nhau

**Hiện tượng:** Staging chạy V005, production chạy V003, nhưng cùng build ứng dụng được triển khai.

**Nguyên nhân:** Pipeline phát hành không gắn schema readiness với version code.

**Khắc phục:** Theo dõi migration state từng môi trường, có prerequisite/gate trước triển khai và kiểm tra ma trận tương thích.

### 14.10. Xem bảng lịch sử migration là dữ liệu nghiệp vụ duy nhất

**Hiện tượng:** Version table ghi V004 đã chạy nhưng 15% dữ liệu vẫn chưa backfill.

**Nguyên nhân:** Một bước DDL được xem là hoàn tất mọi chuyển đổi dữ liệu.

**Khắc phục:** Quản lý **schema state và data migration progress độc lập**, kèm kiểm tra chất lượng trước switch/contract.

## 15. Runbook mẫu cho một thay đổi lược đồ

Một **runbook migration** nên ngắn gọn đủ để người triển khai có thể hành động nhưng phải nêu **điều kiện vào, hành động, bằng chứng, tiêu chí dừng và phương án phục hồi**. Không nên chỉ là danh sách lệnh SQL thiếu bối cảnh.

### 15.1. Hồ sơ quyết định thay đổi

~~~~text
CHANGE: Rename sales_order.customer_email → buyer_email
BUSINESS MEANING:
  Giữ cùng nghĩa: email người đặt tại thời điểm đơn được tạo.
  Không đổi thành email người nhận hoặc email profile hiện tại.

OLD WRITERS:
  Web API A0, admin batch A0.

OLD READERS:
  Web API A0, customer support export, BI job hàng tuần.

NEW WRITERS:
  Web API A2 chỉ dùng buyer_email.

TARGET:
  sales_order.buyer_email NOT NULL.
  Không còn customer_email.

DATA RULE:
  Trong pha hai cột, buyer_email = customer_email.

ROLLBACK WINDOW:
  Có giới hạn theo chính sách release; chưa drop trường cũ trong cửa sổ.

CONTRACT GATE:
  Mọi writer/reader cũ đã ngừng hoặc có adapter tương thích.
  Pending/mismatch = 0, migration history đã đúng phạm vi.
  Đã xác nhận monitoring, backup/forward-fix và quyền phê duyệt.
~~~~

Các tên service và mốc thời gian trong tài liệu thật phải được thay bằng **đối tượng triển khai cụ thể đã kiểm kê**. Không tự điền “đã chuyển tất cả” khi chỉ có số liệu từ một cụm web.

### 15.2. Bảng runbook theo pha

| Pha | Hành động | Bằng chứng đạt | Stop / phản ứng |
| --- | --- | --- | --- |
| **Preflight** | Kiểm kê writer/reader, dữ liệu, khóa, timeout | Có owner, mapping, ma trận compatibility | Thiếu consumer hoặc không rõ nghĩa mới thì chưa deploy |
| **Expand** | Thêm buyer_email nullable, cài cầu sync | A0 còn chạy, INSERT/UPDATE không lỗi | Lỗi write/lock tăng: dừng rollout, điều tra |
| **Backfill** | Chạy theo lô, checkpoint và throttling | Pending giảm, mismatch = 0 | Gặp dữ liệu sai: cách ly hàng, không đoán giá trị |
| **Switch** | Triển khai A2, bật đường đọc/ghi mới | Request và report đúng, có thể rollback trong cửa sổ | Lỗi tăng: hạ cờ/quay code nếu dữ liệu tương thích |
| **Observe** | Theo dõi tải và các consumer còn sót | Không có truy vấn cũ, dữ liệu giữ đúng dưới tải | Có consumer cũ: kéo dài pha tương thích |
| **Contract** | Gỡ trigger, bỏ cột, dọn tài liệu | A2/consumer mới chạy trên schema đích | Không còn rollback A0 đơn giản; dùng plan phục hồi mới |

### 15.3. Ai chịu trách nhiệm?

| Vai trò | Quyết định hoặc bằng chứng |
| --- | --- |
| **Chủ sở hữu nghiệp vụ/dữ liệu** | Xác nhận hai trường có cùng nghĩa, cách xử lý hàng lịch sử |
| **Data Modeler/DBA** | DDL, khóa, constraint, mapping, phương án index và backfill |
| **Nhóm ứng dụng** | SQL/JPA mapping của từng phiên bản, feature flag, đường ghi tương thích |
| **Nhóm tích hợp** | API/event version, CDC, export, batch, contract với consumer |
| **SRE/Platform** | Tải, lock, replica lag, giám sát, backup/restore và triển khai |
| **QA/Data Quality** | Kết quả ma trận test, đối soát, kiểm thử lỗi/cạnh tranh |
| **Release Owner** | Go/no-go cho switch, kết thúc rollback window và contract |

Các vai trò này có thể do ít người cùng đảm nhận ở nhóm nhỏ. **Trách nhiệm vẫn phải rõ** dù tên chức danh khác nhau.

### 15.4. Quy tắc đặt version và tính tái lập

Nên lưu:

- **Schema migration sequence**: bước nào đã được áp dụng và checksum.
- **App build/version**: build nào có thể chạy trên từng schema state.
- **Data migration state**: tiến độ, checkpoint, lỗi, thời điểm đối soát.
- **Contract version**: API/event version nào được producer/consumer hỗ trợ.
- **Rollout state**: feature flag, canary cohort, shards/tenants đã chuyển.

Các trạng thái này phục vụ **những câu hỏi khác nhau**, không nên nén vào một cờ migrated=true. Ví dụ:

~~~~text
schema_migration = V004
data_backfill = 99.95%
app_rollout = 100% A2
event_consumer = v1 still active for partner X
contract_ready = false
~~~~

Ở ví dụ này, schema đã tới V004 nhưng **chưa đủ điều kiện xóa trường cũ**, vì còn dữ liệu chưa chuyển và consumer v1.

### 15.5. Quyết định sau khi migration thành công

Một thay đổi chỉ nên được coi là hoàn tất khi:

1. **Schema đích** đang tồn tại trên toàn phạm vi công bố.
2. **Dữ liệu đích** thỏa ràng buộc và đối soát đã phê duyệt.
3. **Ứng dụng và consumer** không còn phụ thuộc đường cũ.
4. **Các đường ghi mới** đã chứng minh bảo vệ invariant lâu dài.
5. **Telemetry** cho thấy không còn lỗi migration tồn đọng hoặc rollback window chưa đóng.
6. **Tài liệu và chủ sở hữu** được cập nhật; trigger/cột/chỉ mục tạm đã được xử lý có kiểm soát.

Đóng một ticket chỉ vì lệnh ALTER chạy xong có thể để lại **nợ kỹ thuật và dữ liệu mâu thuẫn** cho những đợt phát hành sau.

## 16. Checklist thiết kế và kiểm chứng

Trước khi gửi migration lên môi trường thật:

- [ ] Đã xác nhận **nghĩa của trường trước và sau**, không nhầm đổi tên với đổi nghĩa.
- [ ] Có danh sách **writer, reader, API, event, CDC, BI, batch và job định kỳ** liên quan.
- [ ] Có ma trận **app × schema × data state** với tổ hợp được phép và không được phép.
- [ ] Có kế hoạch **expand trước khi mã mới phụ thuộc schema mới**.
- [ ] Có quy tắc duy trì dữ liệu **hai biểu diễn** trong lúc writer cũ/mới cùng chạy.
- [ ] Backfill **idempotent**, theo lô phù hợp, có checkpoint, retry và giới hạn tải.
- [ ] Các hàng không chuyển được có **quy tắc nghiệp vụ**; không tự gán giá trị bịa.
- [ ] Có chỉ số **pending, mismatch, error, lock waits, replica lag** và ngưỡng stop.
- [ ] Các constraint mới chỉ được enforce khi writer và dữ liệu đã sẵn sàng.
- [ ] Đã đánh giá **transaction/DDL lock**, phiên bản PostgreSQL và tạo index concurrent nếu phù hợp.
- [ ] Đã kiểm tra **event version/replay**, consumer đến muộn và dịch vụ bên ngoài.
- [ ] Đã kiểm thử **mã cũ/mới cùng chạy** trong trạng thái chuyển tiếp.
- [ ] Đã kiểm thử **rollback ứng dụng** trên dữ liệu mới và giới hạn của rollback.
- [ ] Có **forward-fix/restore plan** cho sự cố làm hỏng dữ liệu.
- [ ] Rollout theo shard/tenant có **readiness riêng**, không đoán từ một version toàn cụm.
- [ ] Có người sở hữu **go/no-go**, điều kiện dừng và xử lý tình huống lỗi.
- [ ] Bước **contract tách khỏi expand** và chỉ thực hiện sau khi hết consumer cũ.
- [ ] Đã xem xét view, trigger, stored procedure, quyền, index tạm và quy trình cleanup.
- [ ] Sau migration, **tài liệu schema, hợp đồng API/event và báo cáo** được cập nhật.
- [ ] Không coi kết quả triển khai kỹ thuật là **đã QA học thuật/nghiệp vụ** nếu chưa xác minh các công thức, trạng thái và dữ liệu thực.

## 17. Bài tập thực hành có đáp án

Các bài tập dùng các ký hiệu **S0** (schema cũ), **S1** (schema mở rộng), **S2** (đã chuyển dữ liệu), **S3** (đã cắt sang ứng dụng mới) và **S4** (đã rút gọn). Nếu không có yêu cầu khác, giả định cột cũ và mới trong ví dụ email **cùng nghĩa nghiệp vụ**, hệ thống có thể có nhiều writer và PostgreSQL được dùng làm database.

### Bài 1 — Vì sao RENAME COLUMN trực tiếp có thể làm hỏng ứng dụng?

Ứng dụng A0 đang chạy SQL SELECT customer_email. Nhóm chạy ALTER TABLE RENAME COLUMN customer_email TO buyer_email rồi mới triển khai A2.

**Câu hỏi:** Bước nào rủi ro, và ma trận tương thích nói gì?

**Đáp án:** Ngay khi rename, A0 không còn cột customer_email để SELECT/INSERT/UPDATE; lỗi có thể xuất hiện trước khi A2 được triển khai. Ma trận xác định **A0 không tương thích với schema chỉ có buyer_email**. Nên expand giữ cả hai cột, chuyển code theo pha và contract sau khi A0 không còn hoạt động.

### Bài 2 — S0 có thể chạy ứng dụng chỉ ghi trường mới không?

A2 luôn thực hiện INSERT INTO sales_order_demo(buyer_email) VALUES (...). S0 chỉ có customer_email.

**Câu hỏi:** A2 có thể chạy trên S0 không?

**Đáp án:** **Không.** Database báo cột buyer_email không tồn tại. Dù A2 có logic fallback khi **đọc**, nó vẫn không tương thích với S0 trên **đường ghi**. Expand schema phải chạy trước khi bật hoặc triển khai write path mới trên phạm vi đó.

### Bài 3 — Backfill một lần có đủ khi A0 còn ghi?

Nhóm thêm buyer_email, backfill toàn bộ, rồi triển khai A2 ghi cả hai cột. A0 còn chạy trên vài instance và chỉ sửa customer_email.

**Câu hỏi:** Có thể xảy ra gì?

**Đáp án:** A0 sửa cột cũ sau backfill nhưng cột mới không thay đổi; A2 có thể đọc giá trị cũ ở buyer_email. Cần **đồng bộ tại DB** hoặc giao thức nâng cấp toàn bộ writer/điều phối chuyển quyền ghi. Chỉ dual-write ở A2 **không đủ** khi vẫn còn A0.

### Bài 4 — Trạng thái mở rộng có được phép NULL?

Mô hình cuối yêu cầu buyer_email NOT NULL, nhưng khi thêm buyer_email vào bảng có ba triệu dòng cũ, mọi giá trị buyer_email ban đầu NULL.

**Câu hỏi:** Vì sao có thể chủ ý để nullable ở S1?

**Đáp án:** Đó là **trạng thái trung gian hợp lệ** để các hàng cũ và A0 tiếp tục chạy. Sau khi có nguồn mapping, bảo vệ luồng ghi, backfill và xác nhận không còn NULL, mới siết CHECK/NOT NULL. Không phải vì mô hình đích cho phép email thiếu.

### Bài 5 — Trigger đồng bộ hai cột có giải quyết lost update không?

T1 và T2 cùng đọc email cũ. T2 lưu email mới, sau đó T1 ghi email khác dựa trên dữ liệu đã đọc trước đó. Trigger vẫn giữ hai cột bằng nhau sau mỗi UPDATE.

**Câu hỏi:** Dữ liệu có chắc giữ đúng quyết định của cả T1 và T2 không?

**Đáp án:** **Không.** Trigger bảo đảm hai biểu diễn cùng một giá trị sau mỗi ghi, nhưng không tự ngăn T1 **ghi đè quyết định mới hơn**. Nếu nghiệp vụ yêu cầu chống cập nhật mất, dùng optimistic locking/version hoặc quy tắc giao dịch cạnh tranh phù hợp, và tất cả writer phải tuân thủ giao thức ấy.

### Bài 6 — Vì sao COUNT(*) chưa đủ?

Sau backfill, buyer_email có giá trị trên tất cả hàng và COUNT(*) trước/sau bằng nhau.

**Câu hỏi:** Có thể kết luận migration đúng chưa?

**Đáp án:** Chưa. buyer_email có thể chứa **email sai**. Cần kiểm tra mismatch với trường cũ khi có cùng nghĩa, và nếu thay đổi ngữ nghĩa thì đối soát với nguồn/contract nghiệp vụ có thẩm quyền. Đếm đủ hàng chỉ đo **completeness**, không chứng minh **correctness**.

### Bài 7 — Backfill bị dừng giữa chừng

Một job chuyển dữ liệu chạy được 60% rồi server chết. Job được khởi động lại và dùng điều kiện WHERE buyer_email IS NULL.

**Câu hỏi:** Điều kiện này giúp gì? Đã đủ chưa?

**Đáp án:** Nó giúp **idempotency cơ bản**: những hàng đã có buyer_email không bị ghi đè khi chạy lại. Nhưng vẫn phải kiểm tra **hàng không NULL nhưng mâu thuẫn**, lưu tiến độ, theo dõi lỗi lô, xử lý dữ liệu đến trễ và tránh UPDATE quá lớn. Nếu phép mapping phức tạp, có thể cần version/chữ ký dữ liệu nguồn để biết kết quả còn đúng.

### Bài 8 — Thêm DEFAULT cho dữ liệu không biết

Hệ thống thêm sales_channel NOT NULL DEFAULT 'WEB' cho tất cả đơn cũ. Nhưng dữ liệu lịch sử có thể đến từ MOBILE hoặc STORE.

**Câu hỏi:** Mô hình có đúng không?

**Đáp án:** Không nếu WEB không phải giá trị đã biết. DEFAULT tạo dữ liệu **có vẻ hợp lệ nhưng sai nghĩa**. Cần tìm nguồn để backfill, hoặc dùng UNKNOWN theo chính sách được chấp thuận và công bố mức độ thiếu thông tin.

### Bài 9 — NOT VALID trên FOREIGN KEY

Nhóm thêm FK mới với NOT VALID rồi tuyên bố mọi INSERT mới sẽ được phép vi phạm FK cho đến khi VALIDATE.

**Câu hỏi:** Đúng không?

**Đáp án:** **Không.** Với PostgreSQL, FK được thêm NOT VALID **chưa quét xác minh dữ liệu cũ ngay**, nhưng các thay đổi mới phải tuân thủ constraint. VALIDATE kiểm tra toàn bộ dữ liệu lịch sử còn tồn tại. NOT VALID không phải nút tắt kiểm tra FK mới.

### Bài 10 — Tạo UNIQUE index concurrently ở đâu?

Nhóm viết migration gồm BEGIN; CREATE UNIQUE INDEX CONCURRENTLY ...; COMMIT.

**Câu hỏi:** Có vấn đề gì?

**Đáp án:** PostgreSQL không cho **CREATE INDEX CONCURRENTLY trong transaction block** tường minh. Cần cấu hình bước index riêng theo yêu cầu của công cụ migration, kiểm tra dữ liệu trùng và trạng thái index nếu thất bại. “Concurrently” không nghĩa không có tải hay không cần theo dõi.

### Bài 11 — Rollback ứng dụng và rollback dữ liệu

Schema ở S3 vẫn giữ cả customer_email, buyer_email và trigger. Nhóm muốn quay A2 về A0 vì ứng dụng mới lỗi. Trong hai ngày chạy A2 không có dữ liệu nào thay đổi ngữ nghĩa; trigger đã giữ cột cũ đồng bộ.

**Câu hỏi:** Rollback A2 → A0 có khả năng an toàn không? Có chắc chắn an toàn mọi trường hợp không?

**Đáp án:** **Có khả năng an toàn** trong giả định này vì A0 vẫn nhận được customer_email đồng bộ. Nhưng phải kiểm thử các đường đọc/ghi, enum/trạng thái, tiền tệ, event và dữ liệu mới thực sự. Tồn tại cột cũ **không tự chứng minh tương thích ngữ nghĩa**. Sau S4 đã DROP customer_email, quay lại A0 theo cách đơn giản sẽ không hoạt động.

### Bài 12 — Vì sao DOWN không phục hồi dữ liệu đã mất?

Migration đã gộp một số trường địa chỉ cũ rồi xóa địa chỉ gốc. Một file DOWN chỉ thực hiện ADD COLUMN original_address TEXT.

**Câu hỏi:** Đã khôi phục trạng thái trước migration chưa?

**Đáp án:** **Chưa.** ADD COLUMN chỉ khôi phục **hình dạng**, không tự dựng lại giá trị gốc đã xóa. Có thể cần backup hoặc bản ghi lịch sử, và ngay cả khi có dữ liệu mới thì phép chuyển ngược vẫn có thể không xác định. Hãy phân biệt rollback DDL với **restore dữ liệu**.

### Bài 13 — Đổi đơn vị nhưng giữ type

Một cột amount vẫn là BIGINT, trước đây đo **đồng**, sau migration đo **nghìn đồng**. Nhóm nói migration tương thích vì không đổi kiểu cột.

**Câu hỏi:** Đúng hay sai?

**Đáp án:** **Sai.** Đây là **breaking semantic change**: cùng giá trị số được hiểu khác đi 1.000 lần. Cần hợp đồng/version rõ, đặt tên cột hoặc đơn vị tường minh, chuyển đổi/đối soát và cập nhật consumer. Kiểm tra schema/type chỉ xác nhận hình dạng, không kiểm tra nghĩa.

### Bài 14 — Một shard còn schema cũ

Ứng dụng A2 được deploy cho toàn cụm, Shard 1 và 2 ở S2, Shard 3 còn S0.

**Câu hỏi:** Yêu cầu nào bị vi phạm? Cần bổ sung gì?

**Đáp án:** A2 buộc phải dùng buyer_email nhưng Shard 3 chưa có cột, gây lỗi khi đọc/ghi dữ liệu ở shard ấy. Phải có **schema readiness theo shard**, kiểm soát thứ tự triển khai hoặc routing/feature flag theo phiên bản được xác minh. Một biến schema_version toàn cụm không đủ nếu trạng thái thực tế không đồng nhất.

### Bài 15 — Event v1 đến sau khi database contract

Database Sales đã S4 chỉ còn buyer_email. Một consumer được yêu cầu phát lại sự kiện v1 chứa customerEmail.

**Câu hỏi:** Có nhất thiết phải phục hồi customer_email trong database không?

**Đáp án:** Không nhất thiết. Có thể dùng **consumer/adapter hỗ trợ v1 và ánh xạ theo hợp đồng đã biết** sang mô hình hiện tại. Nếu hai trường có cùng nghĩa, mapping có thể rõ ràng; nếu khác nghĩa, phải xác minh hoặc từ chối có kiểm soát. **Phiên bản sự kiện và phiên bản bảng là hai loại phiên bản khác nhau.**

### Bài 16 — Consumer không nằm trong kho mã ứng dụng chính

Web đã dùng buyer_email, nhưng một job BI chạy ngày đầu mỗi tháng vẫn SELECT customer_email. Nhóm muốn DROP cột cũ ngay ngày 2 sau triển khai.

**Câu hỏi:** Có đủ điều kiện contract không?

**Đáp án:** Chưa. Job BI là **reader cũ** và sẽ hỏng sau DROP. Phải kiểm kê, chuyển đổi và kiểm thử job, hoặc giữ compatibility view/adapter được thiết kế rõ trước khi loại cấu trúc cũ. Đánh giá chỉ trên version của web service là thiếu phạm vi.

### Bài 17 — Tách địa chỉ bằng cách đoán mã phường

Nhiều địa chỉ dạng văn bản thiếu quận/phường, nhưng nhóm backfill tự động đặt mọi ward_code chưa tìm thấy thành một mã mặc định.

**Câu hỏi:** Vì sao nguy hiểm? Mô hình cần có trạng thái gì?

**Đáp án:** Dữ liệu trở nên **đủ cột nhưng sai ngữ nghĩa**, có thể khiến giao hàng hoặc báo cáo địa lý sai. Cần phân biệt **không xác định, chưa chuyển, không áp dụng và đã xác minh**, giữ nguồn ban đầu khi cần, đưa trường hợp mơ hồ vào kiểm tra thủ công hoặc làm giàu từ nguồn tin cậy.

### Bài 18 — Bảng migration history báo V004

Migration V004 đã được ghi “success”, nhưng bảng có 1% buyer_email NULL. Một người kết luận deployment hoàn tất vì tất cả migration file đã chạy.

**Câu hỏi:** Có thể chuyển sang A2 chỉ dùng buyer_email và đặt NOT NULL chưa?

**Đáp án:** Chưa. **Schema history chỉ cho biết bước cấu trúc đã áp dụng**; không chứng minh data backfill hoàn tất. Phải phân tích 1% chưa chuyển, bảo vệ đường ghi, đối soát dữ liệu, xác định sự kiện đến trễ và chỉ siết constraint khi đủ điều kiện.

### Bài 19 — Đổi customer_id từ BIGINT sang UUID

Hai bảng có FK theo customer_id cũ. Nhóm muốn sinh UUID mới cho khách rồi bỏ cột số ngay, còn các dòng order sẽ được chuyển sau.

**Câu hỏi:** Điều gì thiếu trong thiết kế?

**Đáp án:** Phải có **mapping ổn định một–một**, chuyển quan hệ FK, kiểm tra toàn vẹn tham chiếu, hỗ trợ consumer/API/event đang mang ID cũ và giữ các trạng thái trung gian có thể JOIN/đối soát. Sinh UUID và DROP số cũ trước khi chuyển tất cả tham chiếu có thể tạo mồ côi và mất khả năng tra cứu.

### Bài 20 — Một bản phát hành có thể hoàn tất khi còn nhiều phiên bản cùng chạy?

Sau khi expand, một phần app chạy A0 và phần còn lại chạy A2. Trigger đồng bộ hoạt động, mismatch = 0, lỗi thấp; nhưng rollback window còn ba ngày và consumer BI cũ chưa chuyển.

**Câu hỏi:** Có thể coi giai đoạn mở rộng/cắt chuyển thành công không? Có được đánh dấu cả migration hoàn tất và DROP cột cũ không?

**Đáp án:** Có thể kết luận **pha tương thích hiện tại đang đạt tiêu chí kỹ thuật** nếu bằng chứng đủ. Nhưng **không được coi contract hoàn tất** và không DROP customer_email khi còn consumer cũ và rollback window chưa kết thúc. Quản lý trạng thái theo pha là điều kiện để đưa ra kết luận chính xác.

### Bài 21 — Trigger đồng bộ nhận hai giá trị mâu thuẫn

Một request mới cập nhật customer_email = a@example.org và buyer_email = b@example.org trong cùng một UPDATE.

**Câu hỏi:** Trigger ví dụ sẽ xử lý ra sao? Tại sao không chọn đại một bên?

**Đáp án:** Khi hai cột đều thay đổi so với giá trị cũ và khác nhau, trigger **RAISE EXCEPTION** để transaction không commit dữ liệu mâu thuẫn. Nếu chọn đại một bên sẽ che **bug ánh xạ hoặc xung đột nghiệp vụ**; trong pha chuyển tiếp khi hai cột được khẳng định cùng nghĩa, bất đồng phải được báo lỗi hoặc giải quyết theo quy tắc chủ sở hữu đã chốt.

### Bài 22 — Khi nào forward fix tốt hơn đảo schema?

Ứng dụng A2 phát hiện lỗi format buyer_email sau 8 giờ vận hành. Trong thời gian đó có nhiều đơn hợp lệ mới phát sinh. Schema đã dùng buyer_email nhưng vẫn còn dữ liệu nguồn đủ để sửa.

**Câu hỏi:** Có nên restore toàn bộ database về 8 giờ trước như hành động đầu tiên?

**Đáp án:** Không nên mặc định như vậy, vì có thể mất **các đơn hợp lệ của 8 giờ**. Cần phân loại lỗi, phạm vi dữ liệu ảnh hưởng, khả năng **forward fix** bằng script có đối soát, rollback code nếu còn tương thích, hoặc restore có kế hoạch bảo vệ dữ liệu phát sinh. Backup/PITR là công cụ phục hồi mạnh nhưng cần kiểm soát RPO/RTO và ảnh hưởng nghiệp vụ.

### Bài 23 — Tranh chấp khóa của DDL

ALTER TABLE chạy nhanh ở staging, nhưng trên production chờ một transaction kéo dài và nhiều request khác tăng độ trễ.

**Câu hỏi:** Có thể coi vì ALTER nhanh nên nó vô hại không?

**Đáp án:** Không. **Thời gian chờ khóa** và chuỗi request bị chặn có thể quan trọng hơn thời gian thực thi câu DDL khi đã giữ được khóa. Cần kiểm tra lock level, long-running transactions, lock_timeout, kế hoạch retry và thời điểm triển khai; không áp mặc định từ staging sang production.

### Bài 24 — Kết quả migration và tiêu chí nghiệm thu

Một nhóm tuyên bố “hoàn thành đổi cột” vì:

~~~~text
DDL success = true
Deployment A2 = 100%
Backfill pending = 0
~~~~

**Câu hỏi:** Nêu ít nhất bốn bằng chứng cần thêm trước khi contract.

**Đáp án tham khảo:**

1. **Mismatch = 0** và đối soát ngữ nghĩa theo dữ liệu thực.
2. Không còn **reader/writer cũ** như batch, BI, CDC, event consumer hoặc đối tác.
3. Đã thử **app/schema mixed-version**, replay và lỗi concurrent write.
4. Rollback window đã kết thúc và có **forward-fix/restore plan**.
5. Đã đo **lock waits, replication lag, lỗi ghi và lỗi đọc** dưới tải phù hợp.
6. Đã rà soát **view, trigger, index, constraint và quyền** phụ thuộc cột cũ.
7. Có owner phê duyệt ranh giới **go/no-go** và kế hoạch cleanup.

Ba con số ban đầu mới cho biết **một phần trạng thái**, chưa chứng minh việc bỏ cột cũ là an toàn.

## 18. Bảng ghi nhớ nhanh

| Khái niệm | Ý nghĩa và lời nhắc |
| --- | --- |
| **Schema version** | Bản thay đổi cấu trúc đã áp dụng; không đồng nghĩa tiến độ chuyển dữ liệu |
| **App version** | Mã đang chạy và những cột/API nó thật sự đọc/ghi |
| **Contract version** | Ý nghĩa và cấu trúc API/event; có thể đổi không cùng nhịp database |
| **Data migration state** | Hàng nào chưa chuyển, đã chuyển, mâu thuẫn hoặc không chuyển được |
| **Expand** | Thêm cấu trúc mới mà chưa phá phiên bản cũ |
| **Migrate/backfill** | Chuyển dữ liệu có thể kiểm chứng, idempotent và chịu được việc chạy lại |
| **Switch/cutover** | Chuyển đường đọc/ghi chính sang biểu diễn mới |
| **Contract** | Bỏ cấu trúc cũ sau khi hết phụ thuộc và rollback window |
| **Rolling deployment** | Có thể cùng lúc tồn tại A0 và A2; phải thiết kế tương thích |
| **Read fallback** | Hỗ trợ hàng chưa chuyển; không tự đồng bộ write và không chạy sau khi bỏ cột cũ nếu còn tham chiếu |
| **Dual-write** | Cần một giao thức bảo đảm nhất quán; phân biệt ghi hai cột cùng DB với ghi hai hệ thống |
| **Trigger bridge** | Một cách đồng bộ trong pha chuyển; tăng trách nhiệm vận hành và cần được gỡ |
| **Constraint validation** | Backfill và kiểm tra trước khi siết ràng buộc; hiểu NOT VALID theo DBMS |
| **CREATE INDEX CONCURRENTLY** | Không nằm trong transaction block; vẫn có chi phí và trạng thái lỗi cần xử lý |
| **Rollback window** | Thời gian còn duy trì hợp đồng cũ để quay ứng dụng, có giới hạn rõ |
| **Forward fix** | Sửa tiến lên khi dữ liệu mới đã tồn tại và đảo ngược không an toàn |
| **Reconcile** | Kiểm chứng dữ liệu có đúng nghĩa và tham chiếu không, không chỉ đủ hàng |
| **Go/no-go gates** | Tiêu chí chứng minh an toàn trước khi chuyển pha |
| **Version matrix** | Những tổ hợp app × schema × data × contract được hỗ trợ |
| **Ownership** | Ai chịu trách nhiệm dữ liệu, migration, rollback và quyết định contract |

**Kết luận:** Một lược đồ dữ liệu tiến hóa thành công không phải vì viết được lệnh DDL cuối cùng, mà vì **mọi trạng thái trên đường chuyển đổi đều có nghĩa rõ ràng, tương thích với mã còn chạy và có thể kiểm chứng**. Hãy quản trị độc lập phiên bản schema, ứng dụng, hợp đồng và trạng thái dữ liệu; dùng **expand–migrate–switch–contract**, kiểm tra các writer/reader hỗn hợp, đối soát dữ liệu và bảo vệ bất biến trong từng pha. Chỉ xóa cấu trúc cũ khi đã chứng minh không còn phụ thuộc và đã chấp nhận giới hạn rollback. Cách làm này giúp mô hình dữ liệu thay đổi theo nghiệp vụ mà vẫn giữ **tính đúng, khả năng phục hồi và độ tin cậy của hệ thống đang vận hành**.

# Chính sách xóa, lưu trữ dài hạn và dung lượng tăng theo thời gian

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, thiết kế dữ liệu không kết thúc sau khi xác định thực thể, quan hệ, khóa và chỉ mục. Một lược đồ vật lý tốt còn phải trả lời: **dữ liệu được giữ đến khi nào, chuyển sang đâu, xóa theo cách nào, và hệ thống sẽ cần bao nhiêu dung lượng sau một năm hoặc nhiều năm?**

Bài học thuộc chương **Mô hình vật lý** này giúp bạn:

1. Thiết kế **vòng đời dữ liệu** từ tạo lập, sử dụng, lưu trữ dài hạn đến xóa an toàn.
2. Phân biệt **ẩn/xóa logic**, **xóa vật lý**, **lưu trữ lưu trữ lạnh**, **ẩn danh hóa**, và **hết hạn theo chính sách**.
3. Xây dựng **retention policy** gắn với loại dữ liệu, mục đích nghiệp vụ, thời điểm bắt đầu tính hạn và ngoại lệ pháp lý.
4. Đánh giá tác động của khóa ngoại, giao dịch, backup, CDC, cache và dữ liệu dẫn xuất đối với yêu cầu xóa.
5. Lựa chọn **phân vùng, chỉ mục, TTL, batch purge, archive** theo khối lượng và mô hình truy cập, tránh nhầm thao tác xóa logic với giải phóng dung lượng.
6. Ước lượng tăng trưởng dung lượng theo số bản ghi, kích thước thực tế, chỉ mục, bản sao, backup và dự phòng.
7. Thiết lập phép đo, kiểm thử khôi phục và bằng chứng vận hành để chính sách có thể thực thi, kiểm chứng và tiến hóa.

## 1. Vì sao xóa và lưu trữ phải được thiết kế ngay từ đầu?

Hãy xét hệ thống bán hàng có các nhóm dữ liệu:

~~~text
CUSTOMERS       -- Hồ sơ khách hàng
ORDERS          -- Đơn hàng
ORDER_ITEMS     -- Dòng hàng, giá tại thời điểm mua
PAYMENT_EVENTS  -- Sự kiện thanh toán
AUDIT_EVENTS    -- Nhật ký thao tác
SESSION_EVENTS  -- Sự kiện phiên đăng nhập
PRODUCT_IMAGES  -- File ảnh nằm ở object storage
~~~

Giả sử chỉ thiết kế khóa và CRUD mà **không** định nghĩa vòng đời:

- `AUDIT_EVENTS` tăng liên tục, làm chỉ mục lớn, backup lâu và chiếm dung lượng nóng dù phần lớn sự kiện chỉ cần tra cứu trong thời gian ngắn.
- Nhân viên hỗ trợ bấm “xóa khách hàng”, nhưng bản ghi vẫn còn trong lịch sử đơn hàng, log, chỉ mục tìm kiếm hoặc bản sao dùng cho báo cáo.
- Xóa vật lý `CUSTOMERS` thất bại vì `ORDERS.customer_id` còn khóa ngoại; đổi sang `ON DELETE CASCADE` bừa bãi lại có thể xóa cả bằng chứng giao dịch.
- Dữ liệu đã chuyển sang kho lạnh nhưng quy trình khôi phục chưa được thử; tới khi cần đối soát thì **không đọc lại được**.
- Dung lượng tăng đều nhưng nhóm vận hành chỉ nhìn kích thước bảng chính, quên các chỉ mục, bản sao, WAL, phiên bản cũ, backup và file ngoài cơ sở dữ liệu.

Vì vậy, **chính sách xóa và lưu trữ dài hạn là một phần của mô hình dữ liệu**, không chỉ là tác vụ dọn dẹp định kỳ.

## 2. Các khái niệm không được đánh đồng

| Khái niệm | Thao tác thực tế | Dữ liệu còn tồn tại? | Mục đích thường gặp |
|---|---|---|---|
| **Xóa logic** (*soft delete*) | Đánh dấu `deleted_at`, `status` hoặc tombstone | **Có**, trong nguồn lưu trữ | Ẩn khỏi nghiệp vụ hiện hành, có thể khôi phục |
| **Xóa vật lý** (*hard delete*) | Xóa bản ghi/đối tượng khỏi kho dữ liệu cụ thể | Có thể còn bản sao, trang chưa tái sử dụng, backup | Kết thúc vòng đời ở nguồn chính |
| **Lưu trữ dài hạn** (*archive*) | Chuyển dữ liệu ít truy cập tới tầng lưu trữ có chi phí và thời gian truy xuất phù hợp | **Có**, nhưng ở vị trí/vòng đời khác | Đối soát, lịch sử, tra cứu hiếm |
| **Hết hạn** (*expiration*) | Đánh dấu dữ liệu đã quá thời hạn theo quy tắc | Chưa chắc đã xóa ngay | Xác định dữ liệu đủ điều kiện xử lý |
| **Ẩn danh hóa** (*anonymization*) | Biến đổi sao cho không còn định danh được cá nhân theo ngữ cảnh và dữ liệu phụ trợ | Vẫn có thể giữ số liệu không định danh | Phân tích sau khi hết mục đích định danh |
| **Giả danh hóa** (*pseudonymization*) | Thay định danh bằng mã/token có thể nối lại theo cơ chế kiểm soát | **Vẫn có thể là dữ liệu cá nhân** | Giảm mức lộ thông tin, hỗ trợ phân quyền |
| **Xóa theo khóa mã hóa** (*cryptographic erasure*) | Hủy khả năng truy cập dữ liệu mã hóa bằng khóa thích hợp | Bản mã có thể vẫn tồn tại | Một cơ chế xóa có điều kiện, cần đánh giá riêng |

**Ẩn bản ghi khỏi giao diện không đồng nghĩa dữ liệu đã bị xóa khỏi hệ thống.** Tương tự, chuyển bảng sang archive không có nghĩa chính sách lưu giữ đã kết thúc.

### Xóa vật lý và giải phóng dung lượng là hai việc khác nhau

Trong hệ cơ sở dữ liệu sử dụng MVCC, chẳng hạn PostgreSQL, lệnh `DELETE` có thể khiến bản ghi không còn hiển thị với giao dịch mới nhưng **không lập tức làm file dữ liệu trên đĩa nhỏ lại**. Cơ chế dọn phiên bản cũ (như `VACUUM`) có thể làm không gian được **tái sử dụng nội bộ**, trong khi việc giảm kích thước file vật lý là một câu chuyện khác và phụ thuộc thao tác/công cụ cụ thể.

Đối với object storage, xóa một tên đối tượng cũng chưa chắc xóa toàn bộ **phiên bản**, bản sao hoặc những bản trong cơ chế lưu giữ bất biến. Vì thế, báo cáo xóa nên phân biệt rõ **không còn truy cập được trong ứng dụng**, **không còn ở nguồn chính**, **đã xử lý dữ liệu dẫn xuất** và **đã hết vòng đời của bản sao/backup**.

## 3. Mô hình hóa vòng đời dữ liệu

Một mô hình vòng đời điển hình:

~~~mermaid
flowchart LR
    A["Tạo dữ liệu"] --> B["Đang hoạt động / hot"]
    B --> C["Ít truy cập / warm"]
    C --> D["Lưu trữ dài hạn / cold"]
    D --> E["Đủ điều kiện hủy"]
    E --> F{"Có ngoại lệ giữ lại?"}
    F -->|Có| G["Giữ có kiểm soát"]
    G --> F
    F -->|Không| H["Purge và đối soát"]
~~~

Đây là **mô hình tham khảo**, không phải mọi bản ghi đều đi qua đủ các tầng. Ví dụ:

- Phiên đăng nhập ngắn hạn có thể đi thẳng từ **hot** đến **purge**.
- Hóa đơn đã chốt có thể chuyển từ **hot** sang **archive** rồi mới được xét kết thúc thời hạn lưu trữ.
- Hồ sơ khách hàng có thể bị ẩn khỏi ứng dụng trước, nhưng một phần dữ liệu vẫn phải được giữ để thực hiện nghĩa vụ hợp lệ.
- Bản ghi đang có **legal hold** hoặc yêu cầu bảo toàn bằng chứng có thể bị tạm dừng quy trình purge dù đã qua thời hạn thông thường.

Trong thiết kế vật lý, cần xác định **sự kiện kích hoạt** mỗi chuyển trạng thái, ai sở hữu quyết định, bộ dữ liệu nào bị tác động và cách chứng minh thao tác hoàn tất.

### Vòng đời không nhất thiết giống trạng thái nghiệp vụ

Một đơn `CANCELLED` không tự động có nghĩa được xóa. Một đơn `COMPLETED` có thể vẫn phải giữ lâu để đối soát. `status` mô tả **trạng thái nghiệp vụ**, còn `retention_until`, `archived_at`, `purge_eligible_at` mô tả **vòng đời lưu trữ**. Hai loại trạng thái có quan hệ nhưng không nên thay thế nhau.

## 4. Viết chính sách retention từ mục đích và loại dữ liệu

**Retention policy** phải trả lời được:

1. **Đối tượng**: loại dữ liệu, mức hạt, chủ sở hữu và nơi có bản sao.
2. **Mục đích**: vì sao cần giữ; sử dụng hằng ngày, đối soát, an ninh, phân tích hay nghĩa vụ khác.
3. **Điểm bắt đầu** (*retention trigger*): thời điểm tạo, giao dịch hoàn tất, hợp đồng kết thúc, tài khoản đóng hay một sự kiện khác.
4. **Thời hạn**: độ dài và cách tính theo múi giờ/ngày/tháng, có quy tắc thay đổi theo phiên bản chính sách.
5. **Hành động cuối kỳ**: xóa, ẩn danh hóa, chuyển tầng, hoặc yêu cầu rà soát thủ công.
6. **Ngoại lệ**: tranh chấp, điều tra, legal hold, backup bất biến, lỗi đồng bộ, hồ sơ có nhiều mục đích lưu giữ.
7. **Bằng chứng**: log quyết định, số lượng xử lý, kết quả đối soát, quyền phê duyệt, lịch sử chính sách.

### Ví dụ ma trận chính sách

Các khoảng thời gian dưới đây **chỉ là giả định minh họa cho bài tập**, không phải yêu cầu pháp luật hay thời hạn mặc định nên áp dụng:

| Loại dữ liệu | Trigger minh họa | Hot | Archive | Kết thúc vòng đời | Lưu ý |
|---|---|---|---|---|---|
| Session events | Khi sự kiện xảy ra | 30 ngày | Không cần | Xóa sau 90 ngày | Kiểm tra nhu cầu điều tra sự cố |
| Application logs | Khi log được tạo | 14 ngày | 60 ngày tiếp theo | Xóa khi hết hạn | Tránh ghi dữ liệu nhạy cảm vào log |
| Orders | Khi đơn chốt | 12 tháng | Đến mốc lưu giữ đã phê duyệt | Xóa/ẩn danh hóa theo căn cứ hợp lệ | Nghĩa vụ giao dịch có thể khác theo phạm vi |
| Payment audit | Khi sự kiện thanh toán được xác nhận | 90 ngày | Lưu ở kho kiểm soát truy cập | Theo chính sách riêng | Không tự suy hạn từ bảng đơn hàng |
| Product media | Khi phiên bản file không còn dùng | Theo nhu cầu phục vụ | Có thể giữ bản cũ | Xóa phiên bản và bản sao phù hợp | Kiểm tra object versioning, CDN |
| Derived analytics | Khi tạo batch/model | Theo nhu cầu phân tích | Có thể lưu tổng hợp | Xóa hoặc ẩn danh hóa theo nguồn | Dữ liệu dẫn xuất cũng có vòng đời |

Thời hạn thực tế phải được chủ sở hữu dữ liệu, bộ phận pháp lý/tuân thủ và an ninh xác nhận theo **địa bàn áp dụng và mục đích sử dụng**. Không có một con số toàn cầu như “mọi đơn hàng giữ 7 năm” hoặc “mọi log xóa sau 30 ngày” áp dụng cho tất cả hệ thống.

### Cần tránh lỗ hổng “đồng hồ retention”

Ví dụ, chính sách “giữ đơn 24 tháng” chưa đủ rõ nếu không biết **24 tháng từ lúc nào**. Đơn có thể được tạo ngày 1, thanh toán ngày 3, giao ngày 10 và hoàn tất ngày 15. Khi tính hạn từ ngày hoàn tất, cần chọn một trigger bất biến, quy định trường hợp đơn mở mãi hoặc bị mở lại và cách xử lý khi thời điểm nguồn sai.

Một bản ghi có thể thuộc **nhiều nghĩa vụ lưu giữ**. Không được chọn hạn sớm nhất chỉ để tiết kiệm chỗ: cần xác định điều kiện đủ cho phép purge sau khi **tất cả lý do phải giữ** đã kết thúc và không có ngoại lệ tạm giữ.

## 5. Đưa chính sách vào mô hình logic và lược đồ vật lý

Những trường thường hữu ích:

| Trường / thuộc tính | Ý nghĩa | Lưu ý |
|---|---|---|
| `created_at` | Thời điểm sinh bản ghi | Không nhất thiết là trigger retention |
| `business_finalized_at` | Khi nghiệp vụ chốt | Có thể là trigger cho đơn/hóa đơn |
| `deleted_at` | Đánh dấu không còn được xem là bản ghi hoạt động | **Không** đồng nghĩa đã purge |
| `archived_at` | Đã chuyển xong sang kho archive | Chỉ đặt khi đã xác minh thành công |
| `purge_eligible_at` | Mốc sớm nhất được xét purge | Có thể thay đổi do chính sách/ngoại lệ |
| `retention_policy_version` | Phiên bản chính sách đã dùng khi quyết định | Phục vụ đối soát thay đổi |
| `legal_hold` hoặc tham chiếu hold | Có lý do bảo toàn đặc biệt | Thường cần bảng/luồng phê duyệt riêng |
| `tenant_id` | Phạm vi sở hữu và kiểm soát dữ liệu | Phải có ở các truy vấn và khóa liên quan khi cần |

Không nhất thiết đưa **tất cả trường vào mọi bảng**. Với dữ liệu sự kiện bất biến có thể tính mốc purge từ `occurred_at` cùng phiên bản chính sách. Với dữ liệu có nhiều ngoại lệ, bảng `retention_holds` và metadata xử lý riêng sẽ dễ quản trị hơn một cột `hold_reason` tự do.

### Trường thời gian và tính nhất quán

Sử dụng kiểu thời gian có nhận thức múi giờ nếu DBMS hỗ trợ, lưu mốc tuyệt đối nhất quán và chỉ chuyển sang múi giờ địa phương khi áp dụng quy tắc nghiệp vụ. Chú ý sự khác nhau giữa “90 ngày”, “3 tháng theo lịch”, “kết thúc ngày địa phương” và “đến thời điểm X”; các cách nói này **không luôn tương đương**.

Khi chính sách thay đổi, phải biết xử lý những bản ghi đã tồn tại như thế nào: tính lại `purge_eligible_at`, giữ phiên bản cũ theo quyết định đã phê duyệt, hoặc rà soát riêng. Tránh đổi một tham số rồi vô tình xóa cả dữ liệu lịch sử ngay trong lần chạy kế tiếp.

## 6. Xóa logic: hữu ích nhưng không phải giải pháp hoàn chỉnh

Xóa logic phù hợp khi người dùng cần **khôi phục** trong một khoảng thời gian, nghiệp vụ cần kiểm soát quy trình trước khi xóa thật, hoặc cần ngăn hiển thị ngay trong khi các hệ thống khác xử lý bất đồng bộ.

Ví dụ **cú pháp PostgreSQL**:

~~~sql
CREATE TABLE customer_profiles (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    purge_eligible_at TIMESTAMPTZ
);

-- Minh họa tính duy nhất CHỈ cho hồ sơ đang hoạt động.
-- Chỉ chọn chính sách này nếu email được phép tái sử dụng
-- sau khi hồ sơ cũ bị xóa logic.
CREATE UNIQUE INDEX uq_customer_profiles_active_email
    ON customer_profiles (email)
    WHERE deleted_at IS NULL;

-- Xóa logic một hồ sơ theo quyết định nghiệp vụ đã phê duyệt.
UPDATE customer_profiles
SET deleted_at = now(),
    purge_eligible_at = now() + INTERVAL '30 days'
WHERE customer_id = 123
  AND deleted_at IS NULL;

-- Truy vấn nghiệp vụ phải chủ động loại bản ghi đã xóa logic.
SELECT customer_id, email, display_name
FROM customer_profiles
WHERE deleted_at IS NULL;
~~~

**Các lưu ý quan trọng:**

- `deleted_at` không ngăn truy cập bằng truy vấn khác nếu lập trình viên quên lọc. Có thể dùng **view, quyền, row-level security** hoặc tầng truy cập dữ liệu để bảo vệ nhất quán; cần kiểm thử tất cả đường đọc.
- Ràng buộc `UNIQUE` từng phần ở trên cho phép một email có mặt ở **hồ sơ đã xóa logic** và **hồ sơ đang hoạt động**. Nếu nghiệp vụ cấm tái sử dụng hoặc cần phát hiện trùng trên lịch sử, thiết kế phải khác.
- Nếu khôi phục hồ sơ cũ, có thể phát sinh **xung đột email** với hồ sơ mới. Cần quy trình xử lý thay vì đơn giản đặt `deleted_at = NULL`.
- `purge_eligible_at` chỉ là **mốc xét đủ điều kiện**, không tự động cho phép xóa khi còn nghĩa vụ giữ khác.
- Bản ghi vẫn chiếm không gian và thường vẫn có tác động đến backup, chỉ mục, kiểm soát truy cập và truy vấn.

### Khi nào không nên dùng soft delete?

Với một bảng cache hoàn toàn tái tạo được, việc giữ tombstone nhiều năm có thể không đem lại lợi ích. Với dữ liệu nhạy cảm cần xóa sau một mốc hợp lệ, chỉ đánh dấu `deleted_at` mà **không có quy trình purge thực** cũng không đáp ứng mục tiêu kết thúc lưu trữ.

Với hệ thống phân tán, tombstone đôi khi cần tồn tại đủ lâu để **ngăn bản ghi đã xóa bị đồng bộ ngược trở lại**; thời gian tombstone phải phù hợp cơ chế replication/CDC, không thể xóa tùy tiện trước khi mọi bên đã nhận sự kiện.

## 7. Xóa vật lý và khóa ngoại: chọn hành vi theo nghiệp vụ

Một mô hình điển hình:

~~~text
CUSTOMERS(customer_id, ...)
ORDERS(order_id, customer_id, ...)
ORDER_ITEMS(order_id, line_no, ...)
PAYMENT_EVENTS(payment_event_id, order_id, ...)
~~~

Không phải mọi dữ liệu con đều có cùng chính sách xóa với cha:

- Xóa một bản nháp giỏ hàng có thể cho phép xóa các mục nháp đi kèm.
- Xóa hồ sơ khách hàng **không mặc nhiên** cho phép xóa đơn đã hoàn tất hoặc chứng từ thanh toán.
- Dữ liệu thanh toán có thể có vòng đời khác dữ liệu hồ sơ, trong khi báo cáo cần tổng doanh thu đã ẩn danh.

Các lựa chọn khóa ngoại:

| Hành vi | Khi thích hợp | Rủi ro nếu dùng sai |
|---|---|---|
| `ON DELETE RESTRICT` / `NO ACTION` | Không cho xóa cha khi còn dữ liệu con cần xử lý | Công việc purge phải giải quyết phụ thuộc trước |
| `ON DELETE CASCADE` | Dữ liệu con thật sự sống/chết cùng cha và được phép xóa cùng | Có thể xóa lan qua nhiều bảng, mất dữ liệu cần giữ |
| `ON DELETE SET NULL` | Quan hệ có thể vắng mặt và cột cho phép NULL | Mất tham chiếu, thay đổi ngữ nghĩa nếu đối tượng con cần chủ sở hữu |
| Tách liên kết / token hóa | Cần giữ sự kiện nhưng giảm khả năng liên hệ đến danh tính | Vẫn phải đánh giá khả năng tái định danh và dữ liệu liên kết khác |

**Không chọn `CASCADE` chỉ để lệnh `DELETE` chạy thành công.** Trước khi xóa phải lập bản đồ phụ thuộc, định nghĩa mức hạt và giữ đúng nghĩa vụ của từng tập dữ liệu.

### Xóa dữ liệu có quan hệ phức tạp

Một kế hoạch purge có thể theo bước:

1. Chặn phát sinh dữ liệu mới cho đối tượng đang được xóa nếu quy trình yêu cầu.
2. Xác nhận quyền yêu cầu, chính sách retention, legal hold và các trạng thái giao dịch liên quan.
3. Xác định **đồ thị tham chiếu**: khóa ngoại, bản sao, object, index tìm kiếm, kho phân tích, hàng đợi.
4. Xóa, ẩn danh hóa hoặc giữ từng nhóm theo chính sách tương ứng, trong giao dịch hoặc workflow có thể tiếp tục khi lỗi.
5. Ghi **kết quả xử lý và bằng chứng tối thiểu cần thiết**, tránh lưu lại chính dữ liệu nhạy cảm trong log xóa.
6. Xác minh đối tượng không còn truy cập được qua các đường đọc cần áp dụng; theo dõi những bản sao xử lý trễ.

Một yêu cầu xóa có thể đạt trạng thái “đã xóa khỏi ứng dụng, đang chờ hết vòng đời backup”, chứ không nên ghi ngay “đã xóa khỏi mọi nơi” khi chưa có căn cứ.

## 8. Phân vùng theo thời gian và dọn dữ liệu khối lượng lớn

Với dữ liệu sự kiện có lượng ghi lớn và chính sách retention dựa trên thời gian, **phân vùng theo khoảng thời gian** thường hữu ích hơn xóa từng dòng trên toàn bảng.

### Ví dụ PostgreSQL: bảng sự kiện theo tháng

~~~sql
CREATE TABLE audit_events (
    tenant_id BIGINT NOT NULL,
    event_id BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (tenant_id, occurred_at, event_id)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE audit_events_2027_01
    PARTITION OF audit_events
    FOR VALUES FROM ('2027-01-01 00:00:00+00')
               TO ('2027-02-01 00:00:00+00');

CREATE TABLE audit_events_2027_02
    PARTITION OF audit_events
    FOR VALUES FROM ('2027-02-01 00:00:00+00')
               TO ('2027-03-01 00:00:00+00');

CREATE INDEX idx_audit_tenant_time
    ON audit_events (tenant_id, occurred_at DESC);
~~~

**Lưu ý thiết kế:**

- Khóa chính của bảng phân vùng PostgreSQL phải bao gồm **cột khóa phân vùng** trong trường hợp này; vì thế `occurred_at` xuất hiện trong `PRIMARY KEY`. Nó **không** tự bảo đảm `event_id` duy nhất toàn cục nếu `occurred_at` khác nhau; nếu đó là yêu cầu, phải có chiến lược định danh/ràng buộc bổ sung.
- Cần tạo phân vùng cho những khoảng thời gian dự kiến nhận dữ liệu, xử lý sự kiện đến muộn và xác định chuẩn UTC/múi giờ.
- Truy vấn có điều kiện `occurred_at` phù hợp có thể được **partition pruning**, giảm số phân vùng cần đọc; lợi ích phụ thuộc kế hoạch thực thi và workload.
- Quá nhiều phân vùng nhỏ có thể tăng metadata, chi phí lập kế hoạch và bảo trì chỉ mục. Không phải bảng nào cũng nên phân vùng.

Ví dụ truy vấn hỗ trợ pruning:

~~~sql
SELECT tenant_id, event_id, occurred_at, event_type
FROM audit_events
WHERE tenant_id = 42
  AND occurred_at >= TIMESTAMPTZ '2027-01-15 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2027-02-01 00:00:00+00';
~~~

### Quy trình archive rồi mới loại phân vùng

Một quy trình an toàn có thể gồm:

1. Xác định phân vùng **hoàn toàn nằm trước mốc đủ điều kiện** và không chứa bản ghi bị legal hold hoặc các nghĩa vụ khác.
2. Xuất phân vùng sang định dạng/tầng lưu trữ dài hạn đã chọn.
3. Kiểm tra số bản ghi, checksum/manifest, metadata, khả năng đọc lại và quyền truy cập.
4. Phê duyệt loại khỏi nguồn nóng; thực hiện detach hoặc thao tác tương ứng theo DBMS.
5. Chỉ **sau** khi xác minh archive và điều kiện lưu giữ, mới tiến hành xóa vật lý đối tượng lưu trữ nguồn theo runbook.
6. Kiểm tra dung lượng, bản sao, backup và khả năng truy vết kết quả.

Trong PostgreSQL, `ALTER TABLE ... DETACH PARTITION ...` **chỉ tách phân vùng khỏi cây phân vùng**, không tự xóa file dữ liệu của bảng được tách. Việc xóa bảng/phân vùng sau đó là hành động **phá hủy dữ liệu**; không đưa vào cron mà thiếu điều kiện bảo vệ, khả năng phục hồi và phê duyệt phù hợp.

### Partition không thay thế policy

Không thể bỏ cả phân vùng nếu trong đó có một bản ghi cần giữ lâu hơn. Khi hạn lưu giữ tính từ **ngày giao dịch hoàn tất** chứ không phải ngày tạo sự kiện, phân vùng theo `occurred_at` có thể không khớp hoàn toàn với nhóm đủ điều kiện purge. Khi ấy cần thay đổi cách phân vùng, tách dữ liệu đặc biệt, hoặc xóa có chọn lọc.

## 9. Batch purge khi không thể xóa nguyên phân vùng

Với bảng không phân vùng hoặc có ngoại lệ giữ từng bản ghi, xóa theo **lô nhỏ** thường giảm thời gian giữ khóa và kích thước transaction so với một lệnh xóa hàng triệu dòng.

Ví dụ PostgreSQL với bảng session đơn giản:

~~~sql
CREATE TABLE sessions (
    session_id BIGINT PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL,
    legal_hold BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_sessions_expiration
    ON sessions (expires_at, session_id);

-- Một lô, chạy trong workflow có giới hạn tốc độ và điều kiện phê duyệt.
-- :cutoff được cấp từ một quyết định retention hợp lệ.
WITH batch AS (
    SELECT session_id
    FROM sessions
    WHERE expires_at < :cutoff
      AND legal_hold = FALSE
    ORDER BY expires_at, session_id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
DELETE FROM sessions AS s
USING batch AS b
WHERE s.session_id = b.session_id
RETURNING s.session_id;
~~~

Đây là **mẫu truy vấn kỹ thuật**, không phải một chính sách xóa hoàn chỉnh:

- `:cutoff` là **tham số ứng dụng**, không phải cú pháp SQL literal có thể chạy độc lập trong mọi công cụ.
- Cột `legal_hold` đơn giản hóa để minh họa. Hệ thống thật có thể có nhiều loại hold, nhiều lý do lưu giữ và quy tắc kiểm soát qua các bảng.
- Trước khi chạy cần bảo đảm bản ghi không bị giao dịch khác thay đổi theo cách làm mất điều kiện, ràng buộc khóa ngoại được xử lý và có quyền phê duyệt.
- `SKIP LOCKED` hỗ trợ các worker xử lý song song nhưng không thay thế cơ chế idempotency, đối soát và quản lý lỗi.
- `DELETE` nhiều dòng trên hệ dùng MVCC có thể tạo lượng lớn phiên bản chết/WAL; cần theo dõi khả năng dọn dẹp và ảnh hưởng replication.

Tốc độ purge nên được điều chỉnh theo **tải ghi, độ trễ truy vấn, lag bản sao, WAL, I/O** và khả năng dọn dữ liệu sau xóa. Mục tiêu là giảm backlog ổn định mà không gây gián đoạn vận hành.

## 10. Archive dài hạn: phải còn khả năng phục hồi đúng

Archive không chỉ là “chuyển file sang chỗ rẻ”. Một gói lưu trữ dài hạn cần trả lời được:

- **Nội dung:** dữ liệu, phiên bản schema, mã hóa, đơn vị thời gian, định danh tenant và mốc phạm vi.
- **Tính toàn vẹn:** manifest, số bộ/đối tượng, checksum và quy trình phát hiện thiếu/corrupt.
- **Đọc lại:** công cụ giải mã/giải nén, ánh xạ schema cũ sang schema hiện hành và kiểm thử phục hồi.
- **Phân quyền:** ai được xem, cơ chế phê duyệt, kiểm toán truy cập, khóa mã hóa.
- **Retention:** ngày hết hạn, legal hold, khóa chống xóa nếu cần, hành động sau hạn.
- **Chi phí:** lưu trữ, số yêu cầu truy xuất, phí phục hồi, thời gian chờ, chuyển dữ liệu.

### Chọn định dạng lưu trữ phù hợp

| Dạng lưu | Điểm mạnh | Điều cần kiểm tra |
|---|---|---|
| Bảng DB nóng/ấm | Truy vấn trực tiếp, giao dịch và join thuận tiện | Chi phí storage/index, tải vacuum, backup |
| Object storage dạng tệp nén | Chi phí phù hợp lưu trữ ít truy cập | Manifest, checksum, phiên bản object, quyền đọc |
| Dạng cột (ví dụ Parquet) | Hiệu quả với phân tích theo cột và batch | Schema evolution, partition metadata, đọc theo khóa lẻ |
| Archive bất biến / WORM | Hỗ trợ chính sách giữ không sửa/xóa trong thời hạn | Không được thiết kế để xóa sớm tùy ý, cơ chế legal hold |
| Kho chuyên dụng lịch sử | Tối ưu truy vấn thời gian/đối soát | Chi phí và mức nhất quán với nguồn |

Một tập dữ liệu có thể cần cả **bản giao dịch để đối soát** lẫn **bảng phân tích đã được tổng hợp**. Những bản này có thể có mục đích và thời hạn khác nhau; không đánh đồng bản dẫn xuất với nguồn chân lý.

### Kiểm thử phục hồi không thể bỏ qua

Ví dụ một gói archive của tháng 01/2027 phải được kiểm thử: đọc file, kiểm tra checksum, tái tạo schema, truy vấn lại một đơn hàng cụ thể, so tổng số bộ và xác minh khả năng giải mã bằng khóa hiện còn được quản lý. **Backup chưa từng restore** hoặc archive chưa từng được đọc lại không phải bằng chứng đầy đủ cho khả năng phục hồi.

Khi schema tiến hóa, có thể cần giữ **data dictionary, migration mapping, encoding, timezone** và mã phiên bản ứng dụng đủ lâu để hiểu dữ liệu cũ.

## 11. Xóa xuyên các bản sao và hệ thống dẫn xuất

Một bản ghi có thể tồn tại ở nhiều nơi:

~~~text
Ứng dụng
   |
   +-- Primary database
   +-- Read replica
   +-- Backup / snapshot
   +-- CDC stream / message queue
   +-- Search index
   +-- Cache / CDN
   +-- Warehouse / data lake
   +-- Object storage / file version
   +-- Logs, monitoring, exports
~~~

Nếu chính sách yêu cầu xóa dữ liệu về một đối tượng, cần có **data inventory và lineage** để biết các bản sao liên quan. Việc xóa khỏi cơ sở dữ liệu chính không tự động chứng minh đã xử lý tất cả nguồn dẫn xuất.

### Sự khác nhau giữa nguồn chính, replica và backup

- **Replica** nhận thay đổi từ nguồn chính theo một cơ chế đồng bộ nào đó; cần quan sát **replication lag** và lỗi áp dụng sự kiện xóa.
- **Backup/snapshot** thường phản ánh một thời điểm trước khi xóa. Một số bản sao bất biến không thể chỉnh sửa từng bộ; cần có **thời hạn backup**, cơ chế hạn chế truy cập và phương án **áp dụng lại các sự kiện xóa khi khôi phục** nếu thích hợp.
- **CDC/queue** có thể chứa sự kiện và payload cũ. Cần định nghĩa thời hạn stream, chính sách replay và cách ngăn dữ liệu bị khôi phục ngoài ý muốn.
- **Cache/search** thường cần invalidation hoặc reindex. Độ trễ cập nhật có thể khiến bản ghi còn thấy được sau khi nguồn chính đã xóa.
- **Object versioning** có thể giữ nhiều phiên bản cùng một tên đối tượng; lifecycle phải xét các phiên bản nếu mục tiêu là xóa thực sự.

Trong những hệ có yêu cầu bảo vệ dữ liệu cá nhân, thời hạn giữ backup, điều kiện ngoại lệ và cách đáp ứng yêu cầu xóa phải được rà soát theo nghĩa vụ áp dụng. **Không tự hứa “xóa khỏi mọi backup ngay lập tức”** nếu kiến trúc không thực hiện được; cũng không mặc định backup được miễn mọi yêu cầu mà không có căn cứ.

### Bằng chứng xử lý xóa

Một bản ghi công việc xóa có thể lưu:

~~~text
deletion_job_id
subject_ref_or_token
policy_version
requested_at
validated_at
source_purged_at
derived_systems_status
backup_expiry_or_restore_controls
completed_at
error_code
~~~

Nên lưu **mã tham chiếu/tokens tối thiểu** thay vì sao chép lại tên, email, địa chỉ hoặc nội dung nhạy cảm vào nhật ký công việc xóa. Quy trình xóa phải có chính sách lưu giữ **riêng cho bằng chứng xóa**.

## 12. Mô hình tăng trưởng dung lượng theo thời gian

Dung lượng của hệ thống không chỉ là:

~~~text
số dòng × kích thước cột khai báo
~~~

Một ước lượng vật lý phải xét:

- **Số sự kiện/bản ghi mới theo thời gian** và tăng trưởng traffic.
- **Kích thước trung bình thực tế** mỗi bản ghi sau encoding, row overhead, alignment, nén hoặc lưu ngoài hàng.
- **Chỉ mục**: số index, kích thước khóa, độ chọn lọc, bloat và fill factor.
- **Phiên bản cũ / free space** do MVCC, update/delete, autovacuum hoặc cơ chế tương đương.
- **Bản sao**: replication factor, nhiều vùng, độ trễ, bản sao dành cho đọc.
- **Backup/snapshot**, WAL/binlog, CDC, checkpoint, object versioning.
- **Archive** và data warehouse riêng, cùng chính sách retention khác nhau.
- **Dự phòng vận hành** để reindex, restore, compaction, migration và tăng trưởng đột biến.

### Công thức đơn giản cho dữ liệu có vòng đời hữu hạn

Với một loại sự kiện có tốc độ ghi ổn định \(\lambda\) (bản ghi/ngày), thời gian giữ trên tầng nóng \(T\) (ngày), và chi phí vật lý trung bình \(s\) (byte/bản ghi, gồm cả phần chỉ mục được phân bổ), ta có:

\[
N_{\text{hot}}\approx\lambda T
\]

\[
S_{\text{hot}}\approx\lambda T s.
\]

Nếu \(\lambda\) tăng theo thời gian, mô hình chính xác hơn dùng tổng theo ngày:

\[
N_{\text{hot}}(d)
\approx\sum_{k=d-T+1}^{d}\lambda(k).
\]

Đối với dữ liệu **không xóa**, nếu mỗi ngày ghi cùng số bản ghi, dung lượng gần như tăng tuyến tính theo thời gian. Với chính sách retention được thực thi ổn định, dung lượng có thể tiến tới một vùng ổn định **nếu tốc độ ghi và kích thước bản ghi không tăng**. Nếu traffic tiếp tục tăng, dung lượng tầng nóng vẫn tăng dù \(T\) không đổi.

### Ví dụ tính dung lượng

Giả định một hệ thống có:

- \(3.000.000\) sự kiện/ngày.
- Mỗi sự kiện tiêu thụ trung bình **800 byte trong nguồn nóng**, đã bao gồm phần chi phí chỉ mục và dữ liệu vật lý được phân bổ theo đo lường.
- Chính sách giữ trên nguồn nóng **90 ngày**.
- **3 bản sao đầy đủ** của dữ liệu nóng (tính cả primary).
- Dự phòng dung lượng ở mức **30% trên nhu cầu các bản sao**.

Khi đó:

~~~text
Dữ liệu mới/ngày:
3.000.000 × 800 byte = 2.400.000.000 byte ≈ 2,4 GB/ngày

Dữ liệu nóng trong 90 ngày:
2,4 × 90 = 216 GB

Tổng ba bản sao:
216 × 3 = 648 GB

Gồm thêm 30% dự phòng:
648 × 1,30 = 842,4 GB
~~~

Đây là **GB theo hệ thập phân** (\(1\text{ GB}=10^9\) byte) và chỉ là **ước lượng**. Con số **842,4 GB** chưa tính backup độc lập, WAL/CDC, archive, cache, object storage, overhead của hệ thống lưu trữ hoặc khả năng tăng lưu lượng trong 90 ngày. Không lấy con số này làm cấu hình chính xác khi chưa có benchmark.

### Thử độ nhạy của thiết kế

| Kịch bản minh họa | Giả định thay đổi | Dung lượng dữ liệu nóng một bản sao |
|---|---|---:|
| Cơ sở | 3 triệu dòng/ngày, 800 B, giữ 90 ngày | 216 GB |
| Giữ lâu hơn | 3 triệu dòng/ngày, 800 B, giữ 180 ngày | 432 GB |
| Traffic gấp đôi | 6 triệu dòng/ngày, 800 B, giữ 90 ngày | 432 GB |
| Bản ghi lớn hơn | 3 triệu dòng/ngày, 1.200 B, giữ 90 ngày | 324 GB |
| Kết hợp xấu hơn | 6 triệu dòng/ngày, 1.200 B, giữ 180 ngày | 1.296 GB |

Bảng chỉ xét **một bản sao dữ liệu nóng**, chưa nhân số replica và chưa thêm backup. Nó cho thấy **retention, traffic và kích thước bản ghi** cùng ảnh hưởng mạnh tới dung lượng. Trong thực tế cần đo theo giờ/ngày để thấy **mùa vụ, burst, dữ liệu đến muộn và tỷ lệ cập nhật**.

## 13. Các giới hạn của dự báo dung lượng

### Kích thước hàng trung bình có thể thay đổi

Một bản ghi `JSONB` hoặc `TEXT` có thể lớn hơn đáng kể khi thêm field, Unicode, metadata hoặc ảnh nhúng. `VARCHAR(255)` chỉ mô tả giới hạn logic, **không có nghĩa mỗi dòng chiếm đúng 255 byte**. Chi phí vật lý còn phụ thuộc DBMS, encoding, nén, page overhead và TOAST/LOB.

Để dự báo tốt hơn, lấy kích thước từ **đo lường trên dữ liệu đại diện** và theo dõi phân vị kích thước, không chỉ lấy giá trị trung bình trên một mẫu rất nhỏ.

### Dữ liệu cũ không lập tức biến mất

- `DELETE` làm thay đổi trạng thái logic nhưng có thể để lại vùng chờ dọn.
- Hệ LSM có thể cần **compaction** để thu hồi các phiên bản/tombstone.
- Phân vùng đã hết hạn có thể còn tồn tại do **legal hold**, việc archive chưa xác minh hoặc thao tác tách/xóa chưa hoàn tất.
- Replication lag và backlog CDC có thể khiến tăng trưởng tạm thời.
- Object versioning hoặc backup có thể giữ nội dung cũ thêm một giai đoạn.

Một mô hình dung lượng tốt nên có **dự phòng cho trễ xử lý**, chứ không giả định purge luôn chạy đúng thời điểm.

### Lưu trữ nóng và archive cần dự báo riêng

Nếu giữ 90 ngày ở nguồn nóng và thêm 2 năm trong archive, phải tính hai kho:

~~~text
Hot:    traffic × 90 ngày × kích thước nóng
Archive: traffic × thời gian archive × kích thước sau nén
~~~

Sau đó tính replica/backup riêng cho **từng tầng**, vì số bản sao, nén, cấu trúc chỉ mục và chi phí truy xuất có thể khác nhau. Không cộng mù quáng cùng một hệ số replica cho mọi tầng.

## 14. Đo thực tế thay vì chỉ suy từ DDL

Trong PostgreSQL, ví dụ kiểm tra kích thước **một bảng thường** cùng các chỉ mục và dữ liệu phụ trợ:

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('customer_profiles')) AS main_heap,
    pg_size_pretty(pg_table_size('customer_profiles')) AS table_storage,
    pg_size_pretty(pg_indexes_size('customer_profiles')) AS indexes,
    pg_size_pretty(pg_total_relation_size('customer_profiles')) AS total;
~~~

Các hàm trên giúp phân tích kích thước **quan hệ được chỉ định**, nhưng không nên coi kích thước của bảng cha phân vùng là tổng mọi bảng con trong mọi trường hợp. Muốn tính kích thước **toàn cây phân vùng**, cần liệt kê/đo các phân vùng lá hoặc dùng truy vấn/công cụ theo phiên bản PostgreSQL đang vận hành.

Theo dõi thêm:

~~~text
daily_inserted_rows
daily_updated_rows
daily_deleted_rows
live_rows_estimate
dead_tuples_estimate
retention_backlog_rows
oldest_unpurged_at
partition_count
hot_storage_bytes
archive_storage_bytes
index_bytes
replica_lag
backup_bytes_and_age
restore_test_passed_at
~~~

Không phải mọi bộ đếm là **số chính xác theo thời gian thực**: thống kê hệ quản trị có thể là ước lượng, trễ hoặc chỉ phản ánh một phần. Dung lượng trên hóa đơn hạ tầng còn có thể bao gồm bản sao, snapshot, WAL, dự phòng và dịch vụ khác.

### Cảnh báo vận hành nên gắn với hành động

Ví dụ:

- `oldest_unpurged_at` vượt SLA: kiểm tra job purge, legal hold, archive và lỗi dữ liệu.
- `retention_backlog_rows` tăng nhiều ngày: điều chỉnh công suất purge hoặc xem lại partition strategy.
- Dung lượng index tăng nhanh hơn dữ liệu: kiểm tra mẫu truy vấn, bloat và số index không cần thiết.
- Replication lag vượt ngưỡng khi purge: giảm batch size/tốc độ và kiểm tra I/O.
- Gói archive không restore được: **chặn xóa nguồn** cho đến khi quy trình lưu trữ được sửa.

Đặt ngưỡng cụ thể theo hệ thống, không dùng một con số chung cho mọi workload.

## 15. Quy trình triển khai chính sách an toàn

Một runbook nên đi theo các bước:

### Bước 1 — Phân loại và lập bản đồ dữ liệu

Xác định bảng, object, log, search index, cache, warehouse, CDC và backup liên quan. Ghi rõ dữ liệu nào có thể được dẫn xuất từ bảng nào; nếu chưa biết nguồn gốc, không giả định đã xóa đầy đủ.

### Bước 2 — Chốt quy tắc và ngoại lệ

Thống nhất retention trigger, thời hạn, hoạt động kết thúc, pháp lý/tuân thủ, legal hold, người phê duyệt và phiên bản chính sách. Không để scheduler tự suy ra quyết định pháp lý từ tên bảng.

### Bước 3 — Chọn phương thức thực thi theo loại dữ liệu

- Dữ liệu sự kiện lớn, hết hạn theo thời gian: cân nhắc **partition + archive + drop** sau xác minh.
- Dữ liệu có ngoại lệ từng dòng: **batch purge** có lọc chính xác.
- Dữ liệu phải được ẩn nhanh nhưng giữ tạm thời: **soft delete + workflow purge**.
- Dữ liệu rất ít truy cập nhưng còn nghĩa vụ lưu: **archive** với quyền và restore được kiểm thử.
- Dữ liệu dẫn xuất: **rebuild, invalidate, remove hoặc transform** theo quy tắc tương ứng.

### Bước 4 — Chạy thử an toàn

Trên dữ liệu thử nghiệm đại diện, kiểm tra cả **trường hợp không được xóa**: hold, đơn chưa chốt, giao dịch tranh chấp, bản ghi liên kết, tenant khác, sự kiện đến muộn, người dùng đang yêu cầu khôi phục.

Trước khi chạy trong sản xuất, tạo báo cáo **dry run**: bao nhiêu bản ghi đủ điều kiện, kích thước ước tính, các bảng phụ thuộc và ảnh hưởng dự kiến. So sánh với mốc bình thường để phát hiện sai tham số.

### Bước 5 — Thực hiện có kiểm soát

Áp dụng giới hạn quyền, transaction, batch size, tốc độ, idempotency, cơ chế tạm dừng/tiếp tục và giám sát. Với archive, **không hủy nguồn trước khi khôi phục mẫu và kiểm tra toàn vẹn thành công**.

### Bước 6 — Đối soát và ghi nhận kết quả

Xác minh số bản ghi xử lý, checksum khi phù hợp, sai khác nguồn–archive, các hệ dẫn xuất còn tồn đọng và trạng thái bản sao/backup. Lưu log xử lý đủ kiểm toán mà **không lộ lại nội dung nhạy cảm**.

### Bước 7 — Diễn tập phục hồi và kiểm soát thay đổi

Kiểm thử restore định kỳ, bao gồm **áp dụng lại các sự kiện xóa** hoặc các kiểm soát tương đương sau khi phục hồi backup cũ. Khi thay đổi retention policy, hãy chạy lại dự báo dung lượng, kiểm tra data lifecycle và rà soát runbook trước khi áp dụng.

## 16. Những sai lầm thường gặp

| Sai lầm | Vì sao rủi ro | Cách sửa |
|---|---|---|
| “Có `deleted_at` là đã xóa” | Dữ liệu còn ở bảng, index và backup | Thiết kế **purge thực** và đối soát |
| Dùng `ON DELETE CASCADE` cho toàn bộ quan hệ | Có thể xóa lan chứng từ và lịch sử cần giữ | Chọn hành vi FK theo **vòng đời mỗi thực thể** |
| Giữ mọi thứ vĩnh viễn “để sau này cần” | Tăng chi phí, rủi ro lộ dữ liệu và khó tuân thủ | Xác định mục đích, thời hạn, ngoại lệ |
| Xóa cả partition chỉ vì đã qua 90 ngày từ `occurred_at` | Có thể có bản ghi legal hold hoặc trigger khác | Kiểm tra chính sách **trên toàn phân vùng** |
| Chuyển file sang object storage rồi xóa nguồn ngay | Có thể không đọc lại được archive | Manifest, checksum, **restore test** trước khi hủy |
| Coi lệnh `DELETE` là giải phóng dung lượng ngay | MVCC/compaction có độ trễ thu hồi | Theo dõi bloat, vacuum/compaction và kích thước vật lý |
| Chỉ xóa primary, quên search, cache, CDC và bản sao | Bản ghi vẫn có thể được tìm thấy hoặc hồi sinh | Data lineage và workflow xóa xuyên hệ |
| Khẳng định backup đã xóa trong khi còn snapshot bất biến | Báo cáo sai trạng thái xử lý | Tách trạng thái nguồn chính, backup và thời hạn backup |
| Dự báo chỉ bằng số dòng × `VARCHAR(n)` | Bỏ sót dữ liệu biến độ dài, index, replication, backup | Đo kích thước thực tế và mô hình từng tầng |
| Đặt TTL như một SLA xóa tức thời | Một số hệ TTL chạy bất đồng bộ hoặc ở bước compaction | Định nghĩa **độ trễ xóa chấp nhận** và quan sát |
| Chỉ quản lý retention ở bảng chính, không ở tài liệu/ảnh | File và phiên bản object có thể tồn tại lâu | Gắn policy cho từng lớp lưu trữ |
| Giữ log công việc xóa chứa nguyên email/địa chỉ | Chính log xóa tạo bản sao dữ liệu cần xóa | Lưu bằng chứng tối thiểu, token hoặc mã công việc |

## 17. So sánh theo mô hình lưu trữ

| Mô hình | Cách tiếp cận vòng đời dữ liệu | Rủi ro đặc trưng |
|---|---|---|
| **Quan hệ** | Retention theo bảng/dòng/partition; FK, archive và batch purge | Xóa lan, khóa lâu, MVCC bloat, mất tham chiếu |
| **Document** | TTL cho document khi phù hợp, chính sách theo collection, object lifecycle | TTL có thể không tức thời; document nhúng chứa dữ liệu cần xóa ở nhiều nơi |
| **Đồ thị** | Xóa/ẩn danh hóa node/edge theo nghiệp vụ, kiểm soát quan hệ còn mồ côi | Xóa node ảnh hưởng nhiều cạnh; giữ liên kết có thể tạo khả năng tái định danh |
| **Phân tích / data lake** | Partition theo ngày, lifecycle theo file/object, tái xử lý bảng dẫn xuất | Snapshot/phiên bản file, truy vấn lịch sử và dữ liệu nguồn đã xóa |

**Đừng giả định một cơ chế áp dụng giống nhau cho mọi hệ.** Một số kho document có TTL index nhưng xóa không tức thì; một số object store có versioning hoặc retention lock; hệ đồ thị có hành vi xóa cạnh khác nhau; data lake có snapshot cần cleanup riêng. Luôn kiểm tra tính năng, giới hạn và cơ chế xóa của **phiên bản công nghệ thực tế** đang dùng.

## 18. Bài luyện tập có lời giải

### Bài 1 — Soft delete có đáp ứng purge không?

Hệ thống thêm `deleted_at` cho `CUSTOMERS`, sau đó luôn dùng `WHERE deleted_at IS NULL`. Người dùng được báo “đã xóa vĩnh viễn”.

**Lời giải:** Báo cáo không chính xác. Dữ liệu vẫn còn trong bảng và có thể tồn tại ở bản sao, backup hoặc search. Cần phân biệt **đã ẩn khỏi ứng dụng** với **đã xử lý xóa vật lý và các bản sao**; triển khai workflow purge theo chính sách đã xác nhận.

### Bài 2 — Xóa khách có đơn hàng lịch sử

`ORDERS.customer_id` là khóa ngoại tới `CUSTOMERS`. Một khách yêu cầu xóa hồ sơ nhưng các đơn hàng phải được giữ theo nghĩa vụ đã xác nhận. Có nên bật `ON DELETE CASCADE`?

**Lời giải:** Không. Xóa lan có thể làm mất đơn hàng cần giữ. Phải định nghĩa cách giữ chứng từ, hạn chế hoặc loại bỏ liên kết định danh khi hợp lệ, xử lý dữ liệu cá nhân còn trong đơn và kiểm soát khóa ngoại tương ứng. Một yêu cầu xóa không tự động cho phép phá hủy mọi giao dịch.

### Bài 3 — Ước lượng dữ liệu nóng

Hệ thống ghi 1 triệu sự kiện/ngày, mỗi sự kiện tiêu thụ trung bình 1.000 byte (gồm phần chỉ mục phân bổ), giữ nóng 60 ngày. Ước lượng dung lượng **một bản sao nóng**, chưa tính dự phòng?

**Lời giải:** \(1.000.000\times1.000\times60=60.000.000.000\) byte, tức **60 GB thập phân**. Đây là ước lượng trước backup, log, replica và overhead khác.

### Bài 4 — Tác động khi traffic gấp đôi

Tiếp tục bài 3, nếu traffic tăng lên 2 triệu sự kiện/ngày trong khi retention và kích thước bản ghi không đổi, dung lượng một bản sao ổn định sẽ như thế nào?

**Lời giải:** Tăng xấp xỉ **gấp đôi**, thành **120 GB**. Nếu traffic tăng dần theo ngày hoặc có burst, phải dùng dữ liệu từng ngày để ước lượng dung lượng tại thời điểm thực tế.

### Bài 5 — Có thể bỏ phân vùng cũ không?

Một phân vùng tháng 1 chứa hàng triệu log quá hạn nhưng có 20 sự kiện đang bị legal hold. Có nên drop cả phân vùng để tiết kiệm tài nguyên?

**Lời giải:** Không nếu chưa có cơ chế hợp lệ bảo toàn đủ 20 sự kiện theo hold và chứng minh việc xóa phần còn lại được phép. Có thể chuyển/bảo toàn sự kiện cần giữ sang một kho phù hợp, hoặc dùng purge chọn lọc. Phải kiểm tra tính đầy đủ của archive trước khi hủy nguồn.

### Bài 6 — `DELETE` nhưng file DB chưa nhỏ lại

Đã xóa 10 triệu dòng khỏi bảng PostgreSQL; kích thước file hầu như không giảm. Đây có phải bằng chứng rằng lệnh xóa không chạy?

**Lời giải:** Không. MVCC có thể để lại không gian chờ thu hồi/tái sử dụng; việc `VACUUM` thông thường không đồng nghĩa co file về hệ điều hành. Cần kiểm tra số dòng nhìn thấy, thống kê dead tuples, hoạt động vacuum và kích thước phân vùng/chỉ mục trước khi kết luận.

### Bài 7 — Archive có checksum nhưng chưa restore

Hệ thống ghi file nén thành công, lưu checksum, rồi dự định xóa bảng nguồn. Đã đủ an toàn chưa?

**Lời giải:** Chưa đủ. Phải kiểm tra **đọc và khôi phục thực tế**, schema/encoding, quyền giải mã, khả năng truy vấn và tính đầy đủ theo phạm vi dữ liệu. Checksum chỉ là một phần của kiểm chứng toàn vẹn.

### Bài 8 — Xóa trong hệ có bản sao

Hồ sơ đã bị xóa khỏi primary nhưng vẫn xuất hiện trong search trong vài phút và có thể nằm trong backup 30 ngày. Có thể công bố “đã xóa khỏi tất cả hệ thống ngay lập tức” không?

**Lời giải:** Không. Cần phản ánh chính xác trạng thái xử lý search/replica, backup và thời hạn giải quyết, có kiểm soát phục hồi/replay để dữ liệu không xuất hiện lại ngoài ý muốn. Chính sách phải tương thích nghĩa vụ áp dụng và kiến trúc thực tế.

### Bài 9 — Retention trigger không rõ

Chính sách nói “xóa đơn sau 24 tháng”, nhưng đơn được tạo trước khi thanh toán và có thể hoàn trả nhiều tháng sau. Nhóm thiết kế nên làm gì?

**Lời giải:** Phải chốt thời điểm bắt đầu tính hạn (tạo, chốt, giao, hết hiệu lực hay xử lý hoàn trả), ngoại lệ và trạng thái tranh chấp. Quy tắc cần có chủ sở hữu xác nhận; không chọn `created_at` chỉ vì cột này đã tồn tại.

## 19. Checklist trước khi đưa hệ thống vào vận hành

- [ ] Đã phân loại dữ liệu theo **mục đích, độ nhạy, mức hạt và vòng đời**.
- [ ] Mỗi tập dữ liệu có **retention trigger**, thời hạn, hành động cuối kỳ và người sở hữu rõ ràng.
- [ ] Đã xác nhận chính sách với bộ phận nghiệp vụ/pháp lý/tuân thủ khi cần, không bịa thời hạn chung.
- [ ] Đã xử lý ngoại lệ **legal hold**, dữ liệu tranh chấp và bản ghi có nhiều lý do phải giữ.
- [ ] Đã phân biệt **soft delete**, purge vật lý, archive và ẩn danh hóa.
- [ ] Đã rà soát khóa ngoại, `CASCADE`, ràng buộc duy nhất và đường đọc dữ liệu đã xóa.
- [ ] Đã chọn cách purge phù hợp: theo dòng, batch, partition hoặc TTL có giám sát.
- [ ] Archive có manifest, checksum, schema, quyền giải mã và **restore test**.
- [ ] Đã lập bản đồ primary, replica, backup, CDC, cache, search, file và warehouse.
- [ ] Có quy trình ngăn dữ liệu đã xóa **xuất hiện lại sau restore hoặc replay**.
- [ ] Đã dự báo dung lượng theo số bản ghi, kích thước thực tế, retention, replica, backup và dự phòng.
- [ ] Có theo dõi **retention backlog, oldest unpurged, kích thước index, replication lag, restore status**.
- [ ] Có dry run, phê duyệt, điều chỉnh tốc độ, kiểm tra kết quả và cách xử lý lỗi khi purge.
- [ ] Đã thử các trường hợp khó: tenant khác, dữ liệu đến muộn, một bảng con cần giữ, legal hold và object versioning.

**Ghi nhớ:** Mô hình vật lý đúng không chỉ lưu dữ liệu hiệu quả hôm nay mà còn xác định **khi nào ngừng giữ dữ liệu và cách chứng minh đã xử lý an toàn**. Hãy thiết kế retention dựa trên quy tắc nghiệp vụ và nghĩa vụ áp dụng; chọn partition, batch purge, archive và backup theo workload; dự báo dung lượng từ số liệu thực tế. **Xóa logic không phải xóa vật lý, xóa nguồn chính không phải xóa mọi bản sao, và archive không có khả năng khôi phục thì chưa phải chiến lược lưu trữ đáng tin cậy.**

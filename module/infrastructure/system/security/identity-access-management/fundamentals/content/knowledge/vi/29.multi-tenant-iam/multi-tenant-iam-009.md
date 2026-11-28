# Tenant data boundary

## 1. Ranh giới dữ liệu tenant là gì?

Trong hệ thống đa tenant, nhiều tổ chức cùng sử dụng một dịch vụ nhưng không vì thế mà có quyền truy cập dữ liệu của nhau. **Tenant data boundary** là ranh giới xác định dữ liệu thuộc tenant nào và những chủ thể nào được thực hiện những hành động nào đối với dữ liệu đó.

Ranh giới này bao gồm cả quyền đọc, tạo, sửa, xóa, tìm kiếm, xuất dữ liệu và xử lý dữ liệu bằng tác vụ nền. Nó phải được duy trì qua các thành phần mà dữ liệu đi qua, không chỉ ở màn hình người dùng hay một bảng cơ sở dữ liệu.

Ví dụ, ứng dụng quản lý hợp đồng phục vụ hai tổ chức:

- Tenant An Phú có hợp đồng nội bộ `contract-101`.
- Tenant Bình Minh cũng có thể có hợp đồng mang mã nội bộ `contract-101`.

Một thành viên của An Phú không được đọc hợp đồng Bình Minh bằng cách đổi tham số trên URL. Ngay cả khi ID hợp đồng được tạo duy nhất trên toàn hệ thống, việc biết ID vẫn không tạo ra quyền truy cập.

Với dữ liệu riêng của một tenant và không có cơ chế chia sẻ đặc biệt, một điều kiện truy cập có thể mô tả như sau:

```text
Cho phép truy cập khi đồng thời thỏa mãn:
  - Chủ thể và tenant context đã được xác minh.
  - Chủ thể có quan hệ truy cập hợp lệ với tenant.
  - Tài nguyên thuộc tenant đó.
  - Hành động được chính sách trong tenant cho phép.
  - Các điều kiện bổ sung của tài nguyên và phiên đều được đáp ứng.
```

Sau bài học, người học cần nhận diện được các điểm dễ làm mất tenant context, phân biệt quyền nghiệp vụ với cách ly dữ liệu và thiết kế được các kiểm tra cho luồng truy cập từ đầu đến cuối.

## 2. Tenant boundary bổ sung điều gì cho xác thực và phân quyền?

Xác thực trả lời chủ thể là ai. Phân quyền trả lời chủ thể được làm gì với tài nguyên. Ranh giới tenant là một phần quan trọng của quyết định phân quyền trong hệ thống đa tenant: quyền phải được áp dụng trong đúng phạm vi tổ chức.

| Kiểm tra | Câu hỏi cần trả lời | Ví dụ chưa đủ nếu chỉ kiểm tra riêng lẻ |
|---|---|---|
| Authentication | Ai đang gửi yêu cầu? | Lan đăng nhập hợp lệ nhưng yêu cầu hợp đồng của tổ chức khác |
| Membership | Lan có quan hệ hợp lệ với tenant nào? | Lan thuộc An Phú nhưng quyền đã bị đình chỉ tại An Phú |
| Tenant ownership của tài nguyên | Dữ liệu thuộc tenant nào? | Hợp đồng thuộc Bình Minh dù URL ghi An Phú |
| Permission | Lan được làm hành động nào trong tenant? | Lan có quyền xem nhưng không có quyền xuất dữ liệu |
| Điều kiện bổ sung | Thao tác có thỏa chính sách hiện tại không? | Export nhạy cảm yêu cầu xác thực bổ sung hoặc phê duyệt |

Quyền `contract.read` không nên được hiểu là quyền đọc mọi hợp đồng trên nền tảng. Một quyết định có ý nghĩa phải gắn quyền đó với tenant và tài nguyên cụ thể.

Một người có thể đồng thời là quản trị viên của An Phú và là viewer của Bình Minh. Khi chuyển sang Bình Minh, hệ thống phải sử dụng quyền trong Bình Minh. Không được gom mọi vai trò từ các tenant thành một tập quyền toàn cục.

Tương tự, tenant administrator chỉ có quyền quản trị được cấp trong phạm vi của mình. Quyền quản lý thành viên không mặc nhiên cho phép đọc mọi dữ liệu nghiệp vụ, và càng không cho phép truy cập tenant khác.

## 3. Thiết lập tenant context đáng tin cậy

Tenant context là ngữ cảnh tenant mà hệ thống dùng để ra quyết định và thực hiện thao tác. Nó thường gồm định danh tenant chuẩn hóa, chủ thể thực hiện, quan hệ thành viên và giới hạn quyền hoặc credential liên quan.

Client có thể đề xuất tenant thông qua đường dẫn, tên miền con hoặc header. Tuy nhiên, dữ liệu đó chỉ là đầu vào. Máy chủ phải phân giải và đối chiếu nó với bằng chứng xác thực và chính sách truy cập.

Một chuỗi xử lý điển hình:

1. Xác minh credential hoặc phiên của chủ thể.
2. Phân giải tenant được yêu cầu thành tenant chuẩn của hệ thống.
3. Nếu credential bị giới hạn vào một tenant, đối chiếu tenant được yêu cầu với giới hạn đó.
4. Xác minh membership hoặc grant hợp lệ cho chủ thể trong tenant đích.
5. Xác định quyền của chủ thể trong tenant đích và kiểm tra trạng thái liên quan.
6. Tạo tenant context phía máy chủ để truyền qua những lời gọi xử lý tiếp theo.

Trong hệ thống dùng token, một claim `tenant_id` chỉ có thể tham gia quyết định sau khi token đã được kiểm tra theo cơ chế xác thực của hệ thống và nguồn phát hành được tin cậy cho ý nghĩa đó. Đọc payload của token chưa được xác minh rồi lấy `tenant_id` làm phạm vi truy vấn là không đủ.

Nếu nhiều nguồn xác thực có thể phát hành cùng một giá trị `subject`, việc ánh xạ identity còn cần ngữ cảnh nguồn phát hành phù hợp. Không nên ghép người dùng từ hai nguồn hoặc hai tenant chỉ vì họ có cùng email hiển thị.

### Không có tenant context thì xử lý thế nào?

Đối với một thao tác bắt buộc có phạm vi tenant, thiếu tenant context phải dẫn tới từ chối hoặc lỗi có kiểm soát. Không chuyển ngầm sang chế độ đọc toàn bộ dữ liệu.

```text
Nguy hiểm:
  tenantId rỗng → bỏ điều kiện tenant_id khỏi truy vấn

Phù hợp với thao tác tenant-scoped:
  tenantId rỗng → dừng xử lý trước khi truy vấn dữ liệu
```

Các tác vụ quản trị nền tảng thực sự cần truy cập nhiều tenant phải dùng một luồng có thẩm quyền riêng. Không dùng tenant rỗng hoặc một chuỗi đặc biệt do client gửi để biểu diễn quyền toàn nền tảng.

## 4. Ràng buộc tenant trong mô hình dữ liệu

### 4.1. Tài nguyên phải có chủ sở hữu tenant rõ ràng

Với dữ liệu riêng của tenant, mỗi tài nguyên cần có cách xác định tenant sở hữu. Trong cơ sở dữ liệu dùng chung, cách phổ biến là lưu `tenant_id` cùng dữ liệu. Với cơ sở dữ liệu riêng, tenant có thể được gắn với một kết nối hoặc vị trí lưu trữ đã được định tuyến có kiểm soát.

Ví dụ SQL minh họa cho mô hình bảng dùng chung:

```sql
CREATE TABLE tenant_document (
    tenant_id   VARCHAR(64)  NOT NULL,
    document_id VARCHAR(64)  NOT NULL,
    title       VARCHAR(255) NOT NULL,
    PRIMARY KEY (tenant_id, document_id)
);

CREATE TABLE document_version (
    tenant_id   VARCHAR(64) NOT NULL,
    document_id VARCHAR(64) NOT NULL,
    version_no  INTEGER    NOT NULL,
    PRIMARY KEY (tenant_id, document_id, version_no),
    FOREIGN KEY (tenant_id, document_id)
        REFERENCES tenant_document (tenant_id, document_id)
);
```

Khóa ngoại ghép buộc phiên bản tài liệu tham chiếu tài liệu trong cùng tenant. Nó giúp tránh việc một bản ghi của An Phú vô tình liên kết với tài liệu Bình Minh khi ID chỉ duy nhất trong từng tenant.

Ràng buộc dữ liệu hỗ trợ tính toàn vẹn nhưng không thay thế việc phân quyền. Một truy vấn đọc thiếu điều kiện tenant vẫn có thể trả về dữ liệu tenant khác, dù mọi khóa ngoại đều hợp lệ.

### 4.2. Đọc và ghi phải cùng được giới hạn

Một truy vấn theo ID đơn lẻ có thể không thể hiện được ranh giới cần bảo vệ:

```sql
-- Chưa đủ cho tài nguyên tenant-scoped nếu thiếu kiểm tra khác.
SELECT title
FROM tenant_document
WHERE document_id = :documentId;
```

Truy vấn có phạm vi rõ hơn:

```sql
SELECT title
FROM tenant_document
WHERE tenant_id = :verifiedTenantId
  AND document_id = :documentId;
```

Giá trị `verifiedTenantId` phải đến từ tenant context đã được xác minh. Việc dùng câu lệnh có tham số giúp xử lý giá trị đầu vào an toàn về mặt truy vấn, nhưng tự nó không chứng minh người gọi có quyền với tenant được truyền vào.

Nguyên tắc tương tự áp dụng cho cập nhật và xóa:

```sql
UPDATE tenant_document
SET title = :newTitle
WHERE tenant_id = :verifiedTenantId
  AND document_id = :documentId;
```

Nếu không có tài nguyên phù hợp, ứng dụng không được bỏ điều kiện tenant để tìm tiếp trên toàn nền tảng. Cần xử lý kết quả theo hợp đồng API, đồng thời tránh tiết lộ thông tin không cần thiết về tài nguyên ngoài phạm vi.

Khi tạo mới, `tenant_id` của tài nguyên nên được gán từ ngữ cảnh máy chủ thay vì nhận nguyên trạng từ object client gửi lên. Các trường như `tenant_id`, chủ sở hữu hoặc phạm vi ACL không nên được cập nhật tùy ý thông qua một API sửa tiêu đề.

### 4.3. Join, thống kê và tìm kiếm vẫn là truy cập dữ liệu

Một endpoint có thể lọc tenant ở bảng chính nhưng làm sai ở phần join hoặc truy vấn phụ. Khi các ID có phạm vi tenant, quan hệ join cũng cần thể hiện tenant tương ứng:

```sql
SELECT d.document_id, v.version_no
FROM tenant_document d
JOIN document_version v
  ON v.tenant_id = d.tenant_id
 AND v.document_id = d.document_id
WHERE d.tenant_id = :verifiedTenantId;
```

Không chỉ nội dung tài liệu cần được cách ly. Tổng số bản ghi, gợi ý tìm kiếm, kết quả phân trang, thông báo “đã tồn tại” và dữ liệu tổng hợp cũng có thể làm lộ thông tin tenant khác nếu không được giới hạn đúng phạm vi.

## 5. Các mô hình cách ly lưu trữ

Tenant data boundary là yêu cầu về quyền và luồng dữ liệu. Nó có thể được hỗ trợ bằng nhiều cách bố trí lưu trữ khác nhau.

| Mô hình | Cách tổ chức | Điểm cần kiểm soát |
|---|---|---|
| Bảng dùng chung | Nhiều tenant cùng bảng, mỗi bản ghi có tenant key | Lọc truy vấn, ràng buộc quan hệ, policy truy cập và quyền của tài khoản ứng dụng |
| Schema riêng | Mỗi tenant có một schema riêng trong hệ quản trị dữ liệu | Định tuyến schema, quyền kết nối và trạng thái kết nối được tái sử dụng |
| Cơ sở dữ liệu riêng | Mỗi tenant có cơ sở dữ liệu riêng | Mapping tenant với kết nối, credential, backup và công cụ quản trị |
| Kết hợp | Một số tenant dùng tài nguyên chung, một số dùng riêng | Giữ cùng hợp đồng phân quyền và tránh fallback sang vị trí lưu trữ sai |

Tách cơ sở dữ liệu không tự động hoàn tất cách ly. Nếu dịch vụ chọn nhầm kết nối Bình Minh để xử lý một yêu cầu An Phú, dữ liệu vẫn có thể đi sai ranh giới. Nếu mọi kết nối dùng một credential có quyền rộng, lỗi ở lớp định tuyến vẫn có phạm vi ảnh hưởng lớn.

Ở mô hình dùng chung, cơ chế policy theo hàng của cơ sở dữ liệu, nếu được sử dụng và cấu hình phù hợp, có thể bổ sung một lớp kiểm soát. Cần hiểu rõ tài khoản nào chịu policy, tài khoản nào có thể vượt policy và tenant context được thiết lập, xóa như thế nào khi dùng connection pool. Không mặc định rằng chỉ bật một cơ chế là mọi đường đọc và ghi đã được bảo vệ.

Mã hóa dữ liệu cũng không thay thế phân quyền. Nếu ứng dụng có thể giải mã và trả dữ liệu cho sai người, dữ liệu vẫn bị lộ. Khóa riêng cho tenant chỉ có ý nghĩa bảo vệ như thiết kế dự kiến khi quyền sử dụng khóa và định tuyến khóa cũng được ràng buộc với tenant.

## 6. Duy trì ranh giới qua toàn bộ luồng xử lý

Dữ liệu thường đi qua nhiều thành phần:

```text
Yêu cầu của người dùng
        ↓
Tenant context đã xác minh + quyết định quyền
        ↓
Dịch vụ nghiệp vụ
        ├── Cơ sở dữ liệu
        ├── Cache
        ├── Chỉ mục tìm kiếm
        ├── Object storage
        └── Hàng đợi → Worker → File export
```

Mỗi nhánh phải giữ đúng tenant và giới hạn hành động. Một điểm kiểm tra ở API không đủ nếu một thành phần phía sau dùng ID mà bỏ mất tenant context.

### 6.1. Cache

Khóa cache chỉ có `document-101` có thể va chạm nếu nhiều tenant cùng dùng mã tài liệu đó. Một khóa như `tenant-an-phu:document:101` thể hiện phạm vi rõ hơn.

Tuy nhiên, chỉ thêm tenant vào khóa chưa đủ nếu nội dung cache phụ thuộc quyền người dùng. Kết quả dành cho quản trị viên có thể chứa trường mà viewer không được xem. Khi đó, thiết kế cache cần tính đến hình thức biểu diễn, đối tượng sử dụng và phiên bản quyền hoặc policy liên quan.

Trước khi trả một cache hit, hệ thống vẫn phải có quyết định truy cập phù hợp. Cache không phải một nguồn cấp quyền độc lập. Cache quyết định phân quyền cũng cần cơ chế hết hạn hoặc vô hiệu hóa tương ứng với yêu cầu thu hồi quyền.

### 6.2. Chỉ mục tìm kiếm

Tìm kiếm phải giới hạn theo tenant trước khi trả kết quả. Không chỉ các bản ghi chính mà cả tổng số kết quả, facets, autocomplete và gợi ý cũng phải tuân theo phạm vi dữ liệu được phép.

Nếu bộ lọc tenant bị thiếu, ứng dụng không nên coi đó là truy vấn toàn hệ thống cho một người dùng tenant thông thường. Nếu bộ lọc dựa trên một trường trong chỉ mục, quá trình đưa dữ liệu vào chỉ mục phải gắn đúng tenant ngay từ đầu.

### 6.3. Object storage và đường dẫn tải file

Một object key có tiền tố tenant giúp tổ chức dữ liệu, nhưng việc biết đường dẫn không tạo ra quyền đọc. Dịch vụ tải file cần xác minh người gọi được phép truy cập object đó hoặc cấp một cơ chế truy cập có giới hạn phù hợp.

Nếu sử dụng liên kết tải có chữ ký, cần kiểm tra tenant và quyền trước khi cấp liên kết, gắn liên kết với đúng object và chọn thời hạn phù hợp. Một liên kết có thể tiếp tục sử dụng được đến khi hết hạn tùy thiết kế; thu hồi role trong ứng dụng không đồng nghĩa mọi liên kết đã cấp lập tức mất hiệu lực.

File upload cũng cần được gắn tenant từ phía máy chủ. Không cho client chọn một đường dẫn của tenant khác rồi ghi đè file ở đó. Metadata sở hữu và vị trí object phải nhất quán.

### 6.4. Hàng đợi và worker

Job nền cần mang định danh tenant chuẩn cùng ngữ cảnh thực thi cần thiết. Nhưng một trường `tenantId` trong message không tự tạo ra thẩm quyền: hệ thống phải kiểm soát ai được phát message, message thuộc loại tác vụ nào và worker được phép xử lý phạm vi nào.

Với job chạy thay người dùng, cần xác định khi nào kiểm tra lại quyền của người yêu cầu. Một job được chấp thuận hôm qua có thể chạy sau khi người đó đã bị thu hồi quyền. Với job định kỳ của hệ thống, quyền có thể thuộc một workload identity được giao tác vụ cụ thể thay vì người dùng ban đầu.

Hai mô hình đều cần được định nghĩa rõ. Không mặc nhiên cho một worker có credential rộng xử lý mọi tenant do message tùy ý chỉ định. Nếu worker tái sử dụng thread, kết nối hoặc bộ nhớ ngữ cảnh, phải tránh để tenant của job trước lan sang job sau.

### 6.5. Log, audit và dữ liệu quan sát

Audit nên lưu tenant của hành động để có thể truy trách nhiệm, nhưng quyền đọc audit cũng phải được giới hạn. Tenant administrator của An Phú không được tìm thấy audit Bình Minh qua chức năng lọc log.

Không đưa token, credential hoặc toàn bộ dữ liệu nghiệp vụ vào log chỉ để thuận tiện gỡ lỗi. Log tập trung có thể trở thành một kho dữ liệu xuyên tenant nếu thu thập quá nhiều nội dung và được cấp quyền đọc rộng.

Với hành động nền tảng thực sự tác động nhiều tenant, audit cần thể hiện chủ thể thực hiện, phạm vi tác động và lý do, thay vì ngụy trang thành một yêu cầu của thành viên tenant.

## 7. Chia sẻ xuyên tenant và dữ liệu dùng chung

Cách ly dữ liệu không có nghĩa là mọi sản phẩm đều cấm hợp tác giữa tổ chức. Nó có nghĩa là truy cập xuyên tenant phải có một mô hình cấp quyền rõ ràng.

Ví dụ, An Phú chia sẻ một hợp đồng cụ thể với một cộng tác viên của Bình Minh. Hệ thống cần xác định:

1. Chủ thể nào của An Phú có quyền chia sẻ tài nguyên đó.
2. Chủ thể hoặc tổ chức nhận chia sẻ là ai.
3. Hành động nào được cấp, chẳng hạn chỉ đọc một hợp đồng.
4. Grant có thời hạn không và được thu hồi thế nào.
5. Dữ liệu liên quan nào không được mở rộng theo grant đó.

Grant đọc một hợp đồng không nên trở thành quyền liệt kê toàn bộ tài liệu An Phú. Một liên kết chia sẻ cũng không được tự động cho phép sửa tenant sở hữu của tài nguyên.

Đối với dữ liệu danh mục chung do nền tảng cung cấp, cần phân loại rõ đó là dữ liệu toàn nền tảng có chính sách riêng. Không dùng `tenant_id = null` như một lối tắt mơ hồ vừa có nghĩa “dữ liệu chung”, vừa có nghĩa “không biết tenant” và đôi khi lại có nghĩa “bỏ qua kiểm tra”.

Chuyển tài nguyên từ tenant này sang tenant khác cũng là một nghiệp vụ riêng. Nó có thể ảnh hưởng quyền truy cập, liên kết con, file, audit và credential liên quan. Không cho phép việc chuyển này xảy ra bằng một thao tác cập nhật tùy ý trường `tenant_id`.

## 8. Tình huống: xuất hợp đồng bằng tác vụ nền

Lan thuộc An Phú và được cấp quyền `contract.export`. Lan yêu cầu xuất các hợp đồng mà mình được phép đọc. Tác vụ được đưa vào hàng đợi và thực thi sau vài phút.

Một luồng thiết kế có kiểm soát có thể như sau:

1. API xác thực Lan, xác minh membership tại An Phú và kiểm tra quyền export cùng phạm vi hợp đồng được yêu cầu.
2. Máy chủ tạo bản ghi export thuộc An Phú, lưu người yêu cầu và phạm vi dữ liệu đã được chấp thuận.
3. Thành phần được phép phát job gửi định danh job; worker lấy tenant và tham số từ bản ghi tin cậy, không nhận một câu truy vấn hoặc tenant tùy ý do client cung cấp.
4. Khi thực thi, worker áp dụng quy tắc kiểm tra quyền tại thời điểm chạy theo chính sách của sản phẩm. Trong ví dụ này, worker kiểm tra lại membership và quyền của Lan.
5. Worker truy vấn dữ liệu trong An Phú và trong phạm vi Lan được phép xuất, rồi tạo file có metadata sở hữu đúng tenant.
6. API xem trạng thái và tải kết quả tiếp tục kiểm tra quyền của người gọi tại thời điểm truy cập.
7. Audit liên kết yêu cầu ban đầu, job và file kết quả để có thể điều tra.

Các tình huống cần được xử lý rõ:

| Tình huống | Kết quả cần bảo đảm |
|---|---|
| Lan chèn ID hợp đồng Bình Minh vào danh sách | Không đưa dữ liệu Bình Minh vào file |
| Lan bị thu hồi quyền trước khi worker chạy | Worker xử lý theo chính sách kiểm tra lại đã định nghĩa; trong ví dụ này từ chối export |
| Một người An Phú khác biết ID job của Lan | Chỉ xem hoặc tải nếu có quyền với job và dữ liệu tương ứng |
| Lan chuyển tab giao diện sang Bình Minh | Job An Phú vẫn giữ đúng tenant đã được xác minh; không lấy tenant từ lựa chọn giao diện hiện tại |
| Worker xử lý job Bình Minh ngay sau job An Phú | Kết nối, cache và trạng thái ngữ cảnh không mang tenant An Phú sang job mới |
| File đã được tạo nhưng người yêu cầu bị gỡ membership | Quyền tải file và hiệu lực cơ chế truy cập đã cấp được xử lý theo thiết kế thu hồi thực tế |

Ví dụ cho thấy một file export cũng là tài nguyên cần ranh giới tenant. Việc kiểm tra đúng ở bước gửi yêu cầu không đảm bảo các bước tạo file và tải file tự động đúng.

## 9. Vận hành và vòng đời dữ liệu

Khi tenant bị tạm ngừng, hệ thống cần xác định trạng thái đó tác động thế nào tới API, job chờ, job định kỳ, phiên và quyền truy cập file. Chỉ chặn trang đăng nhập mà vẫn để worker tiếp tục xuất dữ liệu có thể không đáp ứng ý nghĩa tạm ngừng đã cam kết trong sản phẩm.

Backup và phục hồi cũng cần giữ ranh giới. Một bản backup dùng chung có thể chứa nhiều tenant; quyền tải hoặc phục hồi backup vì vậy có phạm vi ảnh hưởng khác với quyền quản trị một tenant. Khôi phục dữ liệu của An Phú không nên vô tình ghi đè dữ liệu Bình Minh hoặc đưa dữ liệu Bình Minh vào một môi trường An Phú được truy cập.

Khi di chuyển tenant giữa các vị trí lưu trữ, cần kiểm soát mapping tenant, quyền truy cập bản sao, định tuyến đọc/ghi và thời điểm chuyển đổi. Một bản sao tạm thời chứa dữ liệu khách hàng vẫn thuộc phạm vi cần bảo vệ.

Khi xóa tenant, cần xem xét những nơi dữ liệu còn tồn tại như object storage, chỉ mục tìm kiếm, cache, file export và bản sao phục vụ vận hành. Cách giữ hoặc xóa backup cần được xác định trong chính sách dữ liệu của sản phẩm; không thể kết luận đã xóa mọi bản sao chỉ từ việc xóa các hàng trong cơ sở dữ liệu chính.

## 10. Kiểm tra ranh giới dữ liệu bằng các tình huống đối nghịch

Kiểm tra hữu ích cần chứng minh cả truy cập hợp lệ và truy cập bị từ chối. Nên tạo ít nhất hai tenant độc lập và các chủ thể có quyền khác nhau, kể cả một chủ thể tham gia cả hai tenant.

| Trường hợp kiểm tra | Điều cần quan sát |
|---|---|
| Thành viên An Phú đọc tài nguyên An Phú được cấp quyền | Trả đúng dữ liệu theo phạm vi được phép |
| Thành viên An Phú thay ID sang tài nguyên Bình Minh | Không trả nội dung hoặc thực hiện thay đổi trái phép |
| Hai tenant dùng cùng ID nội bộ | Dữ liệu được phân giải theo tenant; cache và join không va chạm |
| Một người là admin An Phú, viewer Bình Minh | Không sử dụng quyền admin An Phú khi thao tác trong Bình Minh |
| Danh sách batch gồm tài nguyên của cả hai tenant | Không xử lý trái phép; hành vi toàn bộ hoặc từng phần tuân theo hợp đồng API |
| Tenant context thiếu hoặc sai định dạng | Không rơi về truy vấn không giới hạn tenant |
| API phân trang, đếm hoặc gợi ý tìm kiếm | Không lộ metadata của tenant khác |
| Cache đã có dữ liệu từ tenant hoặc vai trò khác | Không trả nhầm nội dung do khóa hoặc biến thể biểu diễn không đủ phạm vi |
| Job chạy sau khi membership bị thu hồi | Áp dụng đúng chính sách thẩm quyền tại thời điểm chạy |
| Luồng tải file dùng ID hoặc liên kết đã biết | Quyền truy cập và thời hạn thực tế được áp dụng đúng thiết kế |

Với một batch có phần tử trái phép, sản phẩm có thể chọn từ chối toàn bộ hoặc chỉ xử lý các phần tử hợp lệ. Cả hai cách đều cần được định nghĩa rõ, tránh thay đổi một phần dữ liệu mà người gọi không biết hoặc tiết lộ sự tồn tại của dữ liệu ngoài phạm vi qua thông báo chi tiết.

Thông báo lỗi và log cũng là một phần của quan sát. Ứng dụng cần có đủ bằng chứng để điều tra nhưng phản hồi cho client không nên vô tình trở thành công cụ liệt kê tài nguyên tenant khác. Một lựa chọn mã lỗi không thể thay thế kiểm tra quyền thực tế.

## 11. Những hiểu lầm cần tránh

**“Có `tenant_id` trong bảng là đã cách ly.”** Trường này chỉ biểu diễn quan hệ sở hữu; ứng dụng và các lớp lưu trữ vẫn phải thực thi đúng quan hệ đó.

**“ID ngẫu nhiên nên người khác không đoán được.”** Khó đoán ID không phải là thẩm quyền. ID có thể xuất hiện trong liên kết, log hoặc dữ liệu được chia sẻ.

**“Prepared statement đã bảo vệ dữ liệu.”** Nó không quyết định người gọi có được dùng tenant hoặc tài nguyên đang truyền vào hay không.

**“Cơ sở dữ liệu riêng thì không cần kiểm tra tenant nữa.”** Vẫn phải xác minh định tuyến, credential và quyền truy cập trước khi sử dụng kết nối.

**“Chỉ API công khai mới cần cách ly.”** Cache, worker, công cụ hỗ trợ, tìm kiếm và export đều có thể tạo đường truy cập dữ liệu ngoài phạm vi.

**“Đã kiểm tra quyền lúc tạo job thì không cần chính sách ở các bước sau.”** Quyền có thể thay đổi; job và file kết quả cần một mô hình thẩm quyền xuyên suốt.

**“Mã hóa riêng cho tenant giải quyết mọi vấn đề.”** Việc chọn đúng khóa và cấp quyền giải mã vẫn cần được ràng buộc với tenant và hành động hợp lệ.

## 12. Câu hỏi tự kiểm tra

1. Vì sao một claim tenant do client gửi chưa đủ để trở thành tenant context đáng tin cậy?
2. Khi tài liệu và phiên bản có ID nội bộ theo tenant, khóa ngoại và join cần thể hiện điều gì?
3. Vì sao khóa cache có tenant vẫn có thể trả dữ liệu quá quyền cho một viewer cùng tenant?
4. Trong luồng export bất đồng bộ, quyền cần được xem xét ở những thời điểm nào?
5. Một grant chia sẻ một tài liệu xuyên tenant khác gì với việc bỏ bộ lọc tenant khỏi mọi truy vấn?

Ranh giới dữ liệu tenant được duy trì bằng các quyết định nhất quán về chủ thể, tenant, tài nguyên và hành động. Mỗi thành phần nhận dữ liệu hoặc xử lý thay người dùng cần giữ được những giới hạn đó, từ truy vấn đầu tiên đến bản sao, tác vụ nền và kết quả cuối cùng.

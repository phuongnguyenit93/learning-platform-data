# Envelope encryption trong database

> **Chương:** Envelope encryption  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Envelope encryption trong database là gì?

**Envelope encryption trong database** là thiết kế trong đó dữ liệu nhạy cảm được **mã hóa bằng data encryption key (DEK)**, rồi DEK được **bảo vệ bởi key encryption key (KEK)**. Database lưu **ciphertext, wrapped DEK và metadata cần để giải mã**, còn KEK thường được quản lý trong KMS/HSM hoặc một ranh giới tin cậy được phê duyệt. Khi đọc một bản ghi, ứng dụng phải kiểm tra quyền, unwrap DEK đúng ngữ cảnh, sau đó giải mã và xác minh tính toàn vẹn của dữ liệu.

Ví dụ, cơ sở dữ liệu đơn hàng lưu số tài khoản nhận thanh toán. Ứng dụng có thể tạo một DEK AES-256 riêng cho mỗi bản ghi, mã hóa trường số tài khoản bằng AES-GCM và dùng KEK `payments-kek/v4` của KMS để wrap DEK. Trong bảng chỉ có các byte không thể đọc trực tiếp cùng key reference. Kẻ tấn công chỉ có bản sao database **không tự có KEK** để mở hàng triệu DEK, với điều kiện ứng dụng và KMS không bị xâm nhập, thuật toán/nonce đúng, dữ liệu không có bản sao plaintext ở nơi khác.

Ý nghĩa của hai tầng khóa:

1. **DEK:** làm việc ở tầng dữ liệu; có thể có phạm vi một dòng, một đối tượng hoặc một nhóm dữ liệu.
2. **KEK:** bảo vệ DEK; có chính sách cấp quyền `Wrap/Unwrap`, cryptoperiod, rotation và audit riêng.
3. **Envelope:** gói dữ liệu lưu trữ chứa ciphertext và wrapped DEK, kèm version/nonce/tag/ngữ cảnh.
4. **Key inventory:** cho biết KEK version nào đang bảo vệ DEK nào và owner nào có trách nhiệm.
5. **KMS/HSM:** thực thi các quyền đối với KEK và có thể thực hiện key wrapping mà không đưa raw KEK ra khỏi ranh giới bảo vệ.

**Không nên đồng nhất** envelope encryption với “đã bật mã hóa database”. Một database có thể dùng **Transparent Data Encryption (TDE)** để mã hóa file trên đĩa mà vẫn trả plaintext cho người có quyền SQL. Envelope encryption ở tầng ứng dụng có thể tạo ranh giới bảo vệ khác, nhưng chỉ khi **application, identity, KMS/IAM và vận hành** đều được thiết kế nhất quán.

### Mục tiêu học tập

Sau bài này, bạn có thể chọn ranh giới mã hóa phù hợp giữa TDE/database/application, thiết kế schema lưu ciphertext và wrapped DEK, chọn độ hạt DEK, sử dụng AES-GCM với AAD/nonce đúng, lập trình mẫu Java 17, tổ chức transaction và concurrency, hiểu hạn chế SQL query/indexing, xử lý backup/WAL/CDC/analytics, rotate KEK hoặc re-encrypt DEK an toàn và xây dựng runbook điều tra sự cố.

## 2. Mô hình đe dọa: database cần chống ai?

Trước khi chọn thuật toán, phải xác định **đối thủ có thể kiểm soát những thành phần nào**. Một kiểu mã hóa bảo vệ tốt trước tấn công trộm bản sao ổ đĩa chưa chắc ngăn người có quyền gọi SQL hoặc chiếm service application.

| Tình huống | Rủi ro | Envelope encryption có thể giúp đến đâu? |
| --- | --- | --- |
| Kẻ tấn công lấy **database dump/snapshot/backup** nhưng không có KEK | Đọc trực tiếp trường nhạy cảm | **Có thể bảo vệ tính bí mật** nếu chỉ lưu ciphertext/wrapped DEK, không kèm raw key |
| DBA có quyền `SELECT` trên bảng encrypted column | Xem giá trị từng hàng | Chỉ thấy ciphertext nếu plaintext được mã hóa ở ứng dụng và DBA không có đường unwrap |
| Hệ quản trị bị chiếm và sửa bản ghi | Thay thế ciphertext hoặc metadata | AEAD/AAD có thể phát hiện sửa nội dung/ngữ cảnh, **không tự ngăn xóa hoặc rollback bản ghi cũ** |
| **Application service** bị chiếm | Gọi KMS unwrap và đọc plaintext | Khó bảo vệ bằng envelope encryption đơn thuần; phải có IAM, resource authorization, monitoring và giới hạn quyền |
| Principal KMS có quyền `Decrypt/Unwrap` bị chiếm | Lấy DEK thông qua API | Cần scoped IAM, audit, rate limits, containment và đánh giá DEK đã truy xuất |
| **Raw KEK** cùng wrapped DEK bị lộ | Unwrap DEK ngoại tuyến | Ranh giới đã bị phá; đánh giá DEK mới và re-encrypt |
| Trường plaintext còn trong **log, cache, WAL, CDC, ETL** | Lộ bản sao ngoài bảng chính | Không được bảo vệ chỉ nhờ mã hóa một cột; phải khảo sát toàn bộ luồng |
| Attacker nắm quyền **app + DB + KMS** | Đọc/giả mạo dữ liệu trong phạm vi quyền | Envelope encryption một mình không thể ngăn; cần cách ly hệ thống, kiểm soát nghiệp vụ và phát hiện sự cố |

**Giới hạn bảo vệ cần ghi rõ trong kiến trúc:** khi ứng dụng có quyền hợp lệ unwrap DEK, dữ liệu vẫn tồn tại dưới dạng rõ trong bộ nhớ ứng dụng để phục vụ nghiệp vụ. Mã hóa dữ liệu ở trạng thái nghỉ **không đồng nghĩa** dữ liệu không bao giờ có dạng rõ ở bất kỳ đâu.

### 2.1. Ba mục tiêu khác nhau

- **Confidentiality at rest:** nếu lấy được bản sao lưu trữ, không đọc trực tiếp được trường nhạy cảm.
- **Integrity of encrypted values:** không dễ tráo/sửa ciphertext mà vẫn được chấp nhận; AEAD tag và binding ngữ cảnh hỗ trợ.
- **Authorization:** ai được phép đọc trường của bản ghi nào; phải do ứng dụng, IAM và KMS policy kiểm tra.

Một thiết kế có ciphertext mạnh nhưng thiếu authorization theo tenant có thể trở thành **dịch vụ giải mã hộ mọi người**. Một thiết kế có IAM tốt nhưng **tái sử dụng nonce AES-GCM dưới cùng DEK** vẫn có thể gặp lỗi mật mã nghiêm trọng.

## 3. TDE, mã hóa trong database và mã hóa ở application khác nhau thế nào?

| Phương án | Vị trí plaintext thường xuất hiện | Ranh giới được bảo vệ chủ yếu | Giới hạn tiêu biểu |
| --- | --- | --- | --- |
| **TDE / storage encryption** | Database engine sau khi giải mã page/file | Disk file, physical backup theo khả năng sản phẩm | DBA hoặc SQL query có quyền vẫn thường thấy plaintext |
| **Database-side column/function encryption** | Database engine/function hoặc extension có key access | Một số cột/dữ liệu lưu trong bảng | DB process/role được cấp key có thể giải mã; query plan/log phải đánh giá |
| **Application-side field encryption** | Application được ủy quyền trước khi ghi/sau khi đọc | DB admin/dump không dễ thấy plaintext trường được bảo vệ | Không còn query tùy ý trực tiếp trên trường, app/KMS trở thành ranh giới nhạy cảm |
| **Client-side/end-to-end field encryption** | Client hoặc một trusted decrypting endpoint | Server database và đôi khi ứng dụng trung gian | Search/validation/authorization và key distribution phức tạp |
| **Envelope encryption** | Tùy lớp triển khai DEK/KEK | Bảo vệ DEK bằng KEK, hỗ trợ lifecycle nhiều tầng | **Là cách tổ chức khóa**, không tự xác định dữ liệu được mã hóa ở client/app/database |

**TDE và envelope encryption có thể dùng đồng thời.** Ví dụ database vẫn bật TDE, còn ứng dụng mã hóa trường số tài khoản bằng DEK và wrap DEK trong KMS. TDE bảo vệ lớp lưu trữ rộng hơn; encryption ở ứng dụng bảo vệ trường nhạy cảm khi database snapshot hoặc SQL access bị lộ. Không nên tuyên bố giải pháp này làm plaintext không thể xuất hiện trong logs, queries hoặc ứng dụng.

### 3.1. Mã hóa ở application có thật sự độc lập khỏi DBA?

Chỉ khi DBA **không có quyền** truy cập KEK hoặc vai trò application có khả năng unwrap và không thể tự deploy code/đọc secret của application. Nếu một người vừa có quyền DBA, vừa có quyền quản trị application/KMS IAM, ranh giới thực tế có thể yếu hơn sơ đồ kiến trúc.

### 3.2. Không dựa vào tên tính năng

Các hệ quản trị và dịch vụ cloud dùng các thuật ngữ “column encryption”, “always encrypted”, “client-side encryption” hoặc “encrypted field” với **semantics khác nhau**. Trước khi chọn, xác minh ai giữ DEK/KEK, vị trí giải mã, khả năng query, metadata/version, backup và quyền thực của nhà cung cấp. Bài này mô tả **kiến trúc application-side envelope encryption** làm ví dụ chính, không khẳng định một tính năng DB cụ thể tự có toàn bộ kiểm soát.

## 4. Luồng ghi: từ plaintext thành một hàng dữ liệu mã hóa

~~~mermaid
sequenceDiagram
    participant Caller as Caller
    participant App as Data service
    participant Auth as Identity + resource policy
    participant KMS as KMS/HSM giữ KEK
    participant DB as Database
    Caller->>App: Ghi thông tin nhạy cảm tenant A
    App->>Auth: Kiểm tra actor, tenant, record và purpose
    Auth-->>App: Permit / deny
    App->>App: Tạo record ID đáng tin và DEK mới
    App->>App: AES-GCM Encrypt + nonce + AAD
    App->>KMS: Wrap DEK bằng KEK/version được duyệt
    KMS-->>App: Wrapped DEK / provider key reference
    App->>DB: INSERT/UPDATE ciphertext, tag, nonce, wrapped DEK, metadata
    DB-->>App: Commit result / revision
    App-->>Caller: Record ID (không chứa raw key)
~~~

### 4.1. Kiểm soát trước khi gọi KMS

Ứng dụng xác thực principal và xác định tenant từ nguồn **đáng tin**, ví dụ claims đã được kiểm tra cộng với chính sách resource. Không nên cho client chọn `kekKeyId` hoặc `tenantId` tùy ý rồi gửi chúng thẳng vào KMS.

### 4.2. Sinh DEK

DEK phải có entropy đủ cao. Với AES-256, dùng **CSPRNG hoặc API sinh data key của KMS** phù hợp. Không dùng `Math.random()`, `java.util.Random`, hash mật khẩu hay timestamp để thay thế key generator.

### 4.3. Mã hóa AEAD

Dùng **AES-GCM** hoặc AEAD được phê duyệt; nonce/IV phải tuân thủ yêu cầu của thuật toán, đặc biệt **không trùng dưới cùng DEK**. AAD có thể ràng buộc ciphertext với `tenantId`, `recordId`, loại dữ liệu và `formatVersion`.

### 4.4. Bọc DEK

KMS/HSM dùng KEK để trả wrapped DEK; tùy API, KMS cũng có thể sinh DEK và trả plaintext DEK **tạm thời** cho workload. Một số API wrap hỗ trợ authenticated encryption context, một số cơ chế AES-KW không có AAD. Đừng giả định mọi provider tương đương.

### 4.5. Lưu transaction

Database phải lưu **ciphertext và wrapped DEK như một đơn vị nhất quán**, kèm key version/nonce/format. Không chấp nhận trường hợp ciphertext của phiên bản mới nhưng wrapped DEK của phiên bản cũ do cập nhật thiếu transaction.

## 5. Luồng đọc: giải mã nhưng vẫn giữ ranh giới quyền

~~~mermaid
sequenceDiagram
    participant Caller as Caller
    participant App as Data service
    participant Auth as Resource/tenant policy
    participant DB as Database
    participant KMS as KMS/HSM
    Caller->>App: GET record X của tenant A
    App->>Auth: Kiểm tra quyền xem X
    Auth-->>App: Permit / deny
    App->>DB: SELECT bằng tenant + record ID
    DB-->>App: Envelope row + KEK reference
    App->>App: Validate version, lengths và context
    App->>KMS: Unwrap đúng KEK version, với quyền và context
    KMS-->>App: DEK tạm thời hoặc protected operation
    App->>App: AES-GCM Decrypt và verify tag/AAD
    App-->>Caller: Trả đúng trường được phép đọc
~~~

**Điều kiện bắt buộc:** khi `AES-GCM` xác minh tag thất bại, không trả plaintext một phần và không tiếp tục thử bừa các key khác. Nếu `Unwrap` bị từ chối, trả lỗi có kiểm soát, ghi audit kỹ thuật phù hợp, **không hiển thị key blob, secret hoặc stack trace nhạy cảm** cho caller.

### 5.1. KMS IAM không thay resource authorization

KMS có thể biết service `billing-api` được `Unwrap` bằng `billing-kek`, nhưng không nhất thiết biết user đang đọc hóa đơn nào. Ứng dụng phải kiểm tra **caller → tenant → record → field/purpose** trước khi unwrap và trước khi trả dữ liệu.

### 5.2. Chặn decrypt oracle

Không tạo API kiểu `POST /decrypt {wrappedDek, ciphertext, keyId}` mở cho mọi người dùng. Cách đó có thể biến backend thành **decrypt oracle** dùng quyền KMS của service để giải mã dữ liệu mà caller không sở hữu. Chỉ giải mã **bản ghi được server truy xuất theo quyền đã xác thực**, với key binding được kiểm tra.

### 5.3. Bắt lỗi xác thực theo cách an toàn

Không nên để một endpoint trả thông tin khác biệt quá cụ thể kiểu “không đúng KEK” hay “tag AES-GCM sai” cho đối thủ, nếu những khác biệt trở thành oracle. Log nội bộ theo mã lỗi có kiểm soát; client nhận thông báo phù hợp với phân loại lỗi và chính sách bảo mật.

## 6. Chọn độ hạt DEK: per-row, per-object, per-tenant hay per-table?

**Độ hạt DEK** xác định bao nhiêu dữ liệu phụ thuộc một secret. Không có một cách chia tuyệt đối tốt cho mọi hệ thống.

| Độ hạt | Ưu điểm | Đổi lại / rủi ro |
| --- | --- | --- |
| **Một DEK mỗi hàng** | Compromise một DEK giới hạn phạm vi một hàng; dễ xác định target re-encrypt | Nhiều wrapped DEK, chi phí KMS/metadata và migration lớn hơn |
| **Một DEK mỗi đối tượng/tài liệu** | Phù hợp hóa đơn, file, bản ghi logic có nhiều cột | Phải quản lý nhiều nonce cho các phần dữ liệu trong cùng đối tượng |
| **Một DEK mỗi tenant** | Ít key objects hơn, phù hợp phân vùng tenant | Lộ một DEK ảnh hưởng nhiều hàng; multi-node nonce strategy quan trọng |
| **Một DEK mỗi bảng/collection** | Ít metadata, quản trị đơn giản | Blast radius rất rộng, khó chia phạm vi sự cố |
| **Một DEK mỗi phiên hoặc batch** | Có thể tối ưu khối lượng công việc tạm thời | Cần retention, mapping và quy tắc reuse chặt |

**Ví dụ:** hệ thống lưu thông tin thẻ nhạy cảm nên cân nhắc độ hạt theo record/field và phạm vi PCI/threat model, thay vì lấy một DEK vĩnh viễn cho mọi tenant. Ngược lại, nếu lưu hàng tỷ log ít nhạy cảm, một key per row có thể tạo chi phí và throughput không cần thiết; cần đánh giá classification và access pattern.

### 6.1. Một DEK cho nhiều cột trong một hàng

Có thể sử dụng một DEK cho nhiều trường nếu **mỗi lần AES-GCM encryption có nonce riêng** và các trường được ràng buộc với **field name/type** trong AAD. Nếu hai trường dùng **cùng DEK và cùng nonce**, bảo mật AES-GCM có thể bị phá.

Thực hành đơn giản hơn là **mã hóa một payload tổng hợp** có định dạng chuẩn dưới một DEK/nonce cho cả đối tượng, hoặc dùng DEK riêng cho từng trường theo nhu cầu truy cập. Cần cân bằng query/update và khả năng đọc từng field.

### 6.2. Caching DEK

Caching DEK giảm số lần gọi KMS nhưng kéo dài thời gian raw DEK có mặt trong RAM của app, có thể làm suy yếu khả năng revoke tức thì và mở rộng ảnh hưởng khi host bị chiếm. Nếu cache được phê duyệt, đặt **TTL, tenant scope, size limits, access tracking**, kết nối cryptoperiod và quy trình xóa cache khi sự cố.

**Không lưu raw DEK vào Redis, session store hoặc distributed cache không được thiết kế như vùng giữ secret chỉ để tăng tốc**.

## 7. Thiết kế schema lưu envelope trong database

Với PostgreSQL làm ví dụ **cú pháp SQL tham khảo**, có thể tạo bảng lưu một payload ciphertext trên mỗi `(tenant_id, record_id)`. Nếu dùng DBMS khác, cần đổi kiểu dữ liệu và cú pháp; schema không phải chuẩn bắt buộc của envelope encryption.

~~~sql
CREATE TABLE confidential_record (
    tenant_id          VARCHAR(80)  NOT NULL,
    record_id          UUID         NOT NULL,
    format_version     SMALLINT     NOT NULL,
    aead_algorithm     VARCHAR(40)  NOT NULL,
    ciphertext_and_tag BYTEA        NOT NULL,
    nonce              BYTEA        NOT NULL,
    wrapped_dek        BYTEA        NOT NULL,
    wrapping_algorithm VARCHAR(80)  NOT NULL,
    kek_key_ref        VARCHAR(255) NOT NULL,
    kek_version        VARCHAR(80)  NOT NULL,
    context_version    SMALLINT     NOT NULL,
    row_revision       BIGINT       NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, record_id),
    CHECK (format_version >= 1),
    CHECK (context_version >= 1),
    CHECK (octet_length(nonce) = 12),
    CHECK (octet_length(ciphertext_and_tag) >= 16),
    CHECK (octet_length(wrapped_dek) > 0),
    CHECK (row_revision >= 0)
);

CREATE INDEX idx_confidential_record_tenant_created
    ON confidential_record (tenant_id, created_at);
~~~

**`ciphertext_and_tag`** trong ví dụ là output của AES-GCM chứa ciphertext cùng authentication tag; vì thế **không có cột `tag` riêng**. Một định dạng khác có thể tách `tag` nhưng phải ghi rõ vị trí/độ dài. Kiểm tra `nonce=12 byte` là ràng buộc cho **profile AES-GCM 96-bit nonce đã chọn**, không phải quy tắc cho mọi thuật toán AEAD.

### 7.1. Vì sao phải lưu version?

- **`format_version`:** cách encode payload và các trường được mã hóa.
- **`context_version`:** quy tắc tạo AAD, encoding tenant/record/field.
- **`aead_algorithm`:** ví dụ profile `AES-256-GCM`.
- **`wrapping_algorithm`:** AES-KW/KWP, KMS blob hoặc provider-specific mechanism.
- **`kek_key_ref` + `kek_version`:** định danh vật liệu KEK hoặc key reference để unwrap được dữ liệu cũ.
- **`row_revision`:** quản lý optimistic concurrency, **không mặc nhiên là AAD** nếu tăng revision chỉ để rewrap.

Những trường này **không nhất thiết đều là plaintext nhạy cảm**, nhưng có thể tiết lộ key hierarchy, tenancy hoặc pattern hoạt động. Cần **giới hạn quyền đọc metadata** và retention/audit phù hợp.

### 7.2. Tại sao không chỉ lưu `keyAlias=current`?

Alias có thể đổi từ KEK `v4` sang `v5`. Bản ghi đã được bọc dưới `v4` không tự được bảo vệ bằng `v5`. Nếu chỉ lưu `current` mà không có provider blob tự định tuyến và quy tắc versioning thích hợp, hệ thống có thể **không còn unwrap được dữ liệu lịch sử**.

### 7.3. Cần giới hạn dữ liệu đầu vào

DB schema chỉ có vài `CHECK` cơ bản. Ứng dụng vẫn phải giới hạn **kích thước ciphertext, wrapped DEK, header, format version và compression**; tránh cấp phát bộ nhớ vô hạn khi đọc blob lỗi hoặc do đối thủ đưa vào.

## 8. AAD: ràng buộc ciphertext với tenant, record và field

**AAD (Additional Authenticated Data)** được xác thực trong AEAD nhưng **không được mã hóa**. Với database, AAD giúp ràng buộc ciphertext với **ngữ cảnh bản ghi**, thay vì chỉ kiểm tra rằng ciphertext được tạo bởi một DEK nào đó.

Ví dụ AAD cho trường số tài khoản:

~~~text
formatVersion = 2
purpose = "PAYMENT_ACCOUNT"
tenantId = "tenant-42"
recordId = "7c13...uuid..."
fieldName = "bank_account"
~~~

Khi giải mã, ứng dụng phải tái tạo **chính xác cùng byte AAD** từ tenant/record/purpose **đã xác thực**, không lấy tùy ý từ metadata mà caller có thể thay. Nếu attacker đổi `tenantId` hoặc tráo ciphertext sang một record khác, phép xác thực AES-GCM sẽ thất bại khi AAD không khớp.

### 8.1. Vì sao nối chuỗi tùy tiện không an toàn?

Nếu viết `tenantId + recordId`, hai cặp trường có thể tạo cùng chuỗi, ví dụ `("ab","c")` và `("a","bc")`. Dùng **length-prefix hoặc canonical serialization** với **format/context version** được khai báo.

Ví dụ dữ liệu nhị phân:

~~~text
[domainSeparator][length(tenantId)][tenantId UTF-8]
[length(recordId)][recordId UTF-8]
[length(purpose)][purpose UTF-8]
[formatVersion]
~~~

### 8.2. Không nhầm AAD với authorization

Kẻ tấn công có thể gửi một `tenantId` đúng với ciphertext của họ nhưng **không có quyền đọc nó**. AAD sẽ không tự phân biệt caller có quyền hay không. Phải kiểm tra **resource ownership và IAM** riêng, trước khi unwrap.

### 8.3. Điều gì xảy ra nếu tenant/record ID thay đổi?

Nếu `recordId` nằm trong AAD rồi ứng dụng **đổi primary key hoặc chuyển một hàng sang tenant khác**, decrypt với AAD mới sẽ thất bại. Đây là tính chất tốt để chống tráo ngữ cảnh, nhưng cần **migration có quyền, giải mã dưới ngữ cảnh cũ và mã hóa lại dưới ngữ cảnh mới**.

**Rewrap DEK không sửa được AAD của ciphertext.** Đổi context được AEAD bảo vệ thường yêu cầu **tạo ciphertext/tag mới**, ngay cả khi DEK không đổi. Để đơn giản hóa nonce policy và giảm rủi ro reuse, có thể sinh **DEK mới** trong quá trình migration.

### 8.4. KEK context khác data AAD

Một số KMS hỗ trợ **encryption context** trên API wrap/unwrap; nó có thể đóng vai trò AAD của lớp KEK theo semantics provider. Còn AES-GCM mã hóa dữ liệu có **AAD riêng**. Không giả định encryption context của KMS tự bảo vệ field/record nếu lớp dữ liệu không sử dụng AAD hoặc ứng dụng không enforce resource authorization.

## 9. Nonce, key reuse và cập nhật bản ghi

Trong AES-GCM, **cặp (DEK, nonce) phải duy nhất** cho mỗi phép mã hóa. Với nonce ngẫu nhiên 96 bit, xác suất va chạm tăng theo số lần dùng dưới cùng một DEK; có thể dùng giới hạn usage/cryptoperiod hoặc chiến lược nonce có bảo đảm uniqueness thích hợp.

### 9.1. Mỗi bản ghi một DEK

Khi mỗi hàng có **DEK mới**, dễ cấp nonce ngẫu nhiên cho phép mã hóa đầu tiên. Nhưng nếu một hàng được **UPDATE** nhiều lần mà vẫn tái sử dụng DEK, mỗi lần UPDATE cần **nonce mới chưa từng dùng với DEK đó**. Một DB transaction rollback **không có nghĩa nonce vừa dùng có thể dùng lại** nếu ciphertext/tag đã có thể bị quan sát hoặc phát ra ngoài.

### 9.2. Nhiều node ghi song song

Nếu nhiều app instances dùng cùng DEK cho một tenant, **các node phải phối hợp nonce strategy**. Không tự dùng một bộ đếm cục bộ mà có thể reset khi restart/snapshot hoặc trùng giữa node. Các cách khác có thể gồm DEK mới cho mỗi bản ghi/update hoặc phân vùng counter/namespace được quản lý.

### 9.3. Rewrap không cần mã hóa lại dữ liệu

Khi chỉ đổi KEK bọc DEK, ciphertext, nonce và data AAD **không đổi**. Vì DEK không được dùng để mã hóa lại, thao tác rewrap **không phát sinh nonce mới ở lớp dữ liệu**. Nếu đổi DEK hoặc đổi AAD, phải mã hóa lại với nonce đúng cho DEK mới.

### 9.4. Đừng tự hạ cấp khi lỗi nonce

Không chuyển sang AES-ECB/CBC không có kiểm soát toàn vẹn để “đỡ phải quản lý nonce”. Nếu yêu cầu throughput cực lớn, cân nhắc **AEAD/nonce construction chuẩn và usage limit có chứng cứ**, không tự thiết kế mode mật mã mới.

## 10. Giao dịch database và tính nhất quán của envelope

Một envelope là **một đơn vị logic**, dù lưu trên nhiều cột. Khi INSERT/UPDATE, cần tính nhất quán giữa:

- `ciphertext_and_tag` và `nonce`.
- `wrapped_dek` và `kek_key_ref/version`.
- `format_version` và `context_version`.
- `tenant_id`, `record_id` được ràng buộc trong AAD.
- Trạng thái key đang được phép dùng theo key policy.

### 10.1. KMS call nằm ngoài database transaction

KMS/HSM thường là dịch vụ **bên ngoài** và không tham gia cùng một ACID transaction với database. Do đó:

1. App có thể **đã sinh/unwrap/wrap DEK** nhưng DB transaction thất bại.
2. App có thể **ghi DB thành công** nhưng response HTTP timeout, caller retry.
3. Một job rewrap có thể nhận timeout sau khi DB update thành công.
4. Database đã commit blob tham chiếu KEK mới nhưng **KMS state/policy** chưa lan tới mọi node.

Giải pháp là thiết kế **idempotency, transaction boundaries, operation IDs, reconciliation và retry có điều kiện**. Không cho phép việc retry tạo nhiều bản ghi khác nhau hoặc ghi đè key version trái dự kiến.

### 10.2. Optimistic concurrency

Với record có `row_revision`, có thể dùng compare-and-swap:

~~~sql
UPDATE confidential_record
SET wrapped_dek = ?,
    kek_key_ref = ?,
    kek_version = ?,
    row_revision = row_revision + 1,
    updated_at = now()
WHERE tenant_id = ?
  AND record_id = ?
  AND row_revision = ?
  AND kek_version = ?;
~~~

**Update count = 1** mới chứng minh database đã thay đúng revision/version; bằng 0 nghĩa là record đã thay đổi, không tồn tại hoặc không còn khớp precondition. Job phải đọc lại, quyết định tiếp tục/hủy/retry **không ghi đè mù quáng**.

### 10.3. Tránh lost update giữa người dùng và rotation worker

Giả sử user sửa plaintext trong khi job chuyển wrapped DEK từ KEK `v2` sang `v3`. Nếu job lấy snapshot cũ rồi `UPDATE` toàn bộ hàng, nó có thể **ghi đè ciphertext mới của user**. Rewrap worker nên **chỉ cập nhật wrapped DEK/KEK reference** cùng revision guard, không thay phần dữ liệu mà nó không sở hữu; logic vẫn cần xử lý conflict đúng.

## 11. Java 17: mẫu encrypt/decrypt và rewrap cho một hàng

Ví dụ sau chạy với **JDK 17 có provider hỗ trợ `AESWrap` và `AES/GCM/NoPadding`**, không cần kết nối cloud. Nó minh họa nguyên tắc:

1. Một DEK AES-256 mới cho mỗi record.
2. DEK mã hóa plaintext bằng AES-GCM, nonce 12 byte và tag 128 bit.
3. DEK được wrap bằng KEK của **`DemoKekStore`**, mô phỏng KMS.
4. AAD là biểu diễn nhị phân length-prefixed của tenant/record/format.
5. Đọc ciphertext yêu cầu **tenant/record context đáng tin** và verify tag.
6. `rewrap` đổi KEK version **mà không đổi ciphertext/DEK**.

**CẢNH BÁO:** `DemoKekStore` giữ raw KEK trong JVM, chỉ dành cho học tập. Trong production, thay bằng **SDK KMS/HSM**, kiểm tra IAM, key state, encryption context và audit; không coi ví dụ như giải pháp bảo vệ root key.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;
import java.util.Objects;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class DatabaseEnvelopeDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int FORMAT_VERSION = 1;

    record EnvelopeRow(
            String tenantId, String recordId, int formatVersion,
            String kekVersion, byte[] nonce, byte[] wrappedDek,
            byte[] ciphertextAndTag) {
        EnvelopeRow {
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(recordId);
            Objects.requireNonNull(kekVersion);
            nonce = Objects.requireNonNull(nonce).clone();
            wrappedDek = Objects.requireNonNull(wrappedDek).clone();
            ciphertextAndTag =
                    Objects.requireNonNull(ciphertextAndTag).clone();
        }
        @Override public byte[] nonce() { return nonce.clone(); }
        @Override public byte[] wrappedDek() { return wrappedDek.clone(); }
        @Override public byte[] ciphertextAndTag() {
            return ciphertextAndTag.clone();
        }
    }

    static SecretKey newAes256() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    // CHỈ DEMO: thay bằng adapter KMS/HSM thực trong production.
    static final class DemoKekStore {
        private final Map<String, SecretKey> keys;
        DemoKekStore(Map<String, SecretKey> keys) {
            this.keys = Map.copyOf(keys);
        }
        byte[] wrap(String version, SecretKey dek) throws Exception {
            SecretKey kek = required(version);
            Cipher cipher = Cipher.getInstance("AESWrap");
            cipher.init(Cipher.WRAP_MODE, kek);
            return cipher.wrap(dek);
        }
        SecretKey unwrap(String version, byte[] blob) throws Exception {
            SecretKey kek = required(version);
            Cipher cipher = Cipher.getInstance("AESWrap");
            cipher.init(Cipher.UNWRAP_MODE, kek);
            return (SecretKey) cipher.unwrap(
                    blob, "AES", Cipher.SECRET_KEY);
        }
        private SecretKey required(String version) {
            SecretKey key = keys.get(version);
            if (key == null) {
                throw new SecurityException("KEK version unavailable");
            }
            return key;
        }
    }

    static void writeField(DataOutputStream out, String field)
            throws Exception {
        byte[] utf8 = field.getBytes(StandardCharsets.UTF_8);
        out.writeInt(utf8.length);
        out.write(utf8);
    }

    static byte[] aad(String tenantId, String recordId, int format)
            throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        writeField(out, "DB-ENVELOPE-AEAD");
        writeField(out, tenantId);
        writeField(out, recordId);
        out.writeInt(format);
        out.flush();
        return buffer.toByteArray();
    }

    static EnvelopeRow seal(
            DemoKekStore kms, String tenant, String record,
            String kekVersion, byte[] plaintext) throws Exception {
        Objects.requireNonNull(kms);
        Objects.requireNonNull(plaintext);
        if (tenant == null || tenant.isBlank()
                || record == null || record.isBlank()
                || kekVersion == null || kekVersion.isBlank()) {
            throw new IllegalArgumentException("Invalid identity/context");
        }
        SecretKey dek = newAes256();
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad(tenant, record, FORMAT_VERSION));
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        byte[] wrappedDek = kms.wrap(kekVersion, dek);
        return new EnvelopeRow(tenant, record, FORMAT_VERSION,
                kekVersion, nonce, wrappedDek, ciphertextAndTag);
    }

    static byte[] open(
            DemoKekStore kms, EnvelopeRow row,
            String authorizedTenant, String trustedRecordId)
            throws Exception {
        Objects.requireNonNull(kms);
        Objects.requireNonNull(row);
        // Ứng dụng THẬT phải xác thực quyền truy cập bản ghi TRƯỚC đây.
        if (!row.tenantId().equals(authorizedTenant)
                || !row.recordId().equals(trustedRecordId)
                || row.formatVersion() != FORMAT_VERSION
                || row.nonce().length != NONCE_BYTES
                || row.wrappedDek().length == 0
                || row.wrappedDek().length > 1024
                || row.ciphertextAndTag().length < 16) {
            throw new SecurityException("Envelope context invalid");
        }
        SecretKey dek = kms.unwrap(row.kekVersion(), row.wrappedDek());
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, row.nonce()));
        cipher.updateAAD(aad(
                authorizedTenant, trustedRecordId, FORMAT_VERSION));
        return cipher.doFinal(row.ciphertextAndTag());
    }

    static EnvelopeRow rewrap(
            DemoKekStore kms, EnvelopeRow row, String newKekVersion)
            throws Exception {
        SecretKey dek = kms.unwrap(
                row.kekVersion(), row.wrappedDek());
        byte[] newWrapped = kms.wrap(newKekVersion, dek);
        // Giữ nguyên dữ liệu AES-GCM, AAD và nonce vì KHÔNG encrypt lại.
        return new EnvelopeRow(
                row.tenantId(), row.recordId(), row.formatVersion(),
                newKekVersion, row.nonce(), newWrapped,
                row.ciphertextAndTag());
    }

    public static void main(String[] args) throws Exception {
        DemoKekStore kms = new DemoKekStore(Map.of(
                "kek-v1", newAes256(), "kek-v2", newAes256()));
        byte[] plaintext = "Example private field"
                .getBytes(StandardCharsets.UTF_8);
        EnvelopeRow original = seal(kms, "tenant-42",
                "record-91", "kek-v1", plaintext);

        byte[] recovered = open(
                kms, original, "tenant-42", "record-91");
        if (!Arrays.equals(plaintext, recovered)) {
            throw new AssertionError("Decrypt mismatch");
        }

        // Đổi KEK; ciphertext vẫn y hệt.
        EnvelopeRow rotated = rewrap(kms, original, "kek-v2");
        if (!Arrays.equals(
                original.ciphertextAndTag(),
                rotated.ciphertextAndTag())) {
            throw new AssertionError("Rewrap changed data ciphertext");
        }
        if (!Arrays.equals(plaintext,
                open(kms, rotated, "tenant-42", "record-91"))) {
            throw new AssertionError("Rewrapped envelope failed");
        }

        // Copy cùng ciphertext sang record khác bị chặn bằng AAD.
        EnvelopeRow tampered = new EnvelopeRow(
                "tenant-42", "record-92", rotated.formatVersion(),
                rotated.kekVersion(), rotated.nonce(),
                rotated.wrappedDek(), rotated.ciphertextAndTag());
        boolean rejected = false;
        try {
            open(kms, tampered, "tenant-42", "record-92");
        } catch (AEADBadTagException expected) {
            rejected = true;
        }
        if (!rejected) {
            throw new AssertionError("Context swap was accepted");
        }

        // Không in plaintext, DEK, KEK hoặc credential.
        System.out.println("Database envelope demo: PASS");
    }
}
~~~

### 11.1. Vì sao demo tạo DEK mới cho mỗi hàng?

Mỗi lần gọi `seal` sinh DEK riêng rồi mã hóa một payload duy nhất. Điều này làm đơn giản hóa quản lý nonce trong ví dụ. Nếu một record được cập nhật, cần **DEK/nonce mới hoặc chiến lược nonce không trùng**; không reuse cùng cặp key/nonce.

### 11.2. Vì sao `rewrap` không sửa ciphertext?

Nó chỉ đổi **lớp wrap của DEK**, giữ DEK và dữ liệu đã mã hóa. Đây là mẫu phù hợp cho **rotation KEK bình thường** khi DEK vẫn được tin cậy. Nếu **DEK đã bị lộ**, phải đánh giá thay DEK và **re-encrypt**, không chỉ rewrap.

### 11.3. Những giới hạn cần giữ trong đầu

- `DemoKekStore` không phải KMS, HSM, IAM hay key custody thật; raw KEK tồn tại trong JVM.
- Kiểm tra `authorizedTenant` trong code chỉ là minh họa: production cần **dịch vụ xác thực/authorization tin cậy**, không nhận `authorizedTenant` từ caller không xác thực.
- `EnvelopeRow` copy các mảng byte để tránh mutation ngoài ý muốn, nhưng **không bảo đảm zeroization mọi bản sao secret** trong bộ nhớ.
- `KeyGenerator` và `Cipher` cần provider/algorithm được phê duyệt; không fallback sang ECB nếu `AESWrap` không hỗ trợ.
- Không có SQL, transaction, backup hoặc provider-native encryption context trong đoạn code này.
- Không có giới hạn kích thước payload đầy đủ cho data ingestion; production cần **input validation, resource quotas, error handling và audit**.
- AAD demo dùng chuỗi `record-91`; với database có UUID, cần **canonical UUID encoding** và lưu thống nhất.

## 12. Java JDBC: lưu envelope theo transaction

Ở tầng persistence, chỉ lưu **các byte đã mã hóa** cùng metadata. Đoạn SQL/JDBC dưới đây là **phác thảo tích hợp**, giả định `EnvelopeRow` ở mục trước và schema PostgreSQL ở mục 7; cần dùng UUID thật, connection pool, API xác thực và mapper do ứng dụng kiểm soát.

~~~java
// Phác thảo: nằm trong transaction/application service,
// row.recordId() phải là UUID hợp lệ do server tạo trước khi seal().
static void insertEnvelope(
        java.sql.Connection conn, DatabaseEnvelopeDemo.EnvelopeRow row)
        throws java.sql.SQLException {
    String sql = """
        INSERT INTO confidential_record
        (tenant_id, record_id, format_version, aead_algorithm,
         ciphertext_and_tag, nonce, wrapped_dek, wrapping_algorithm,
         kek_key_ref, kek_version, context_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """;
    try (java.sql.PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setString(1, row.tenantId());
        ps.setObject(2, java.util.UUID.fromString(row.recordId()));
        ps.setInt(3, row.formatVersion());
        ps.setString(4, "AES-256-GCM");
        ps.setBytes(5, row.ciphertextAndTag());
        ps.setBytes(6, row.nonce());
        ps.setBytes(7, row.wrappedDek());
        ps.setString(8, "AES-KW");
        ps.setString(9, "approved-kek-ref"); // demo placeholder
        ps.setString(10, row.kekVersion());
        ps.setInt(11, 1);
        if (ps.executeUpdate() != 1) {
            throw new java.sql.SQLException("Insert did not affect one row");
        }
    }
}

// Caller kiểm soát begin/commit/rollback (hoặc framework transaction).
// Không ghép SQL bằng tenantId/recordId input để tránh SQL injection.
~~~

### 12.1. Tính nguyên tử và thứ tự thao tác

- Sinh record ID và DEK **trước khi INSERT**; không giả định database tạo ID sau insert rồi vẫn dùng được AAD đã mã hóa trước đó.
- Commit **cùng transaction** các cột ciphertext, nonce, wrapped DEK, KEK version và context version.
- Ghi audit/correlation ID đủ để phát hiện retry, nhưng **không đưa raw DEK hoặc plaintext vào SQL logs**.
- Khi DB commit lỗi sau KMS wrap, DEK vừa tạo có thể không được lưu; tùy kiến trúc có thể an toàn để bỏ bản DEK tạm, nhưng phải đảm bảo không còn blob/side effect mất kiểm soát.
- Khi HTTP response timeout sau DB commit, áp dụng **idempotency key** để không vô tình tạo hai bản ghi/phiên bản khác nhau cho cùng một lệnh.

### 12.2. Không mở transaction lâu chỉ để chờ KMS

Gọi KMS có network latency. Nếu mở database transaction rồi chờ KMS lâu, có thể tăng lock contention và connection pressure. Có thể chuẩn bị envelope trước khi bắt đầu transaction, sau đó INSERT nhanh với optimistic concurrency/idempotency; tuy nhiên phải kiểm tra **cơ chế xác thực, context và trạng thái record chưa bị thay đổi** trong khoảng chuẩn bị. Chọn đường phù hợp với consistency cần thiết.

## 13. Query, index, JOIN và tìm kiếm trên dữ liệu mã hóa

**Mã hóa đúng thường khiến dữ liệu không còn giữ tính chất có thể query như plaintext.** Ví dụ AES-GCM với nonce ngẫu nhiên tạo ciphertext khác nhau cho cùng một giá trị, vì vậy câu lệnh sau không thể tìm bản ghi theo email đã mã hóa bằng cách so sánh với một ciphertext mới:

~~~sql
-- KHÔNG hoạt động như tra cứu plaintext nếu mỗi lần mã hóa
-- dùng DEK/nonce ngẫu nhiên khác nhau:
SELECT * FROM confidential_record
WHERE ciphertext_and_tag = ?;
~~~

### 13.1. Những thao tác vẫn làm được

Database vẫn có thể:

- Filter trên **metadata không mã hóa** đã được phân loại an toàn, ví dụ `tenant_id`, `record_id`, trạng thái nghiệp vụ nếu không nhạy cảm.
- Tạo index trên `tenant_id`, `created_at`, category đã được phê duyệt.
- JOIN bằng **surrogate key ổn định** không tiết lộ secret, thay vì JOIN ciphertext của trường nhạy cảm.
- Truy xuất các ciphertext rồi giải mã **trong trusted application**, với giới hạn và phân quyền phù hợp.

**Nhưng metadata vẫn có thể nhạy cảm:** tenant, thời điểm truy cập, số lượng giao dịch hay loại tài khoản có thể tiết lộ hành vi. Không để database telemetry/analytics trở thành kênh lộ dữ liệu.

### 13.2. Blind index/search token

Với yêu cầu tìm kiếm chính xác theo một trường nhạy cảm, một số hệ thống dùng **blind index** dựa trên HMAC của giá trị đã chuẩn hóa:

\[
\mathrm{token}=\operatorname{HMAC}_{K_{\mathrm{index}}}
(\mathrm{domain}\parallel \mathrm{tenant}\parallel \mathrm{normalizedValue})
\]

**`K_index` là khóa riêng**, không phải DEK hay KEK được tái sử dụng. Token có thể dùng làm cột tra cứu equality nếu policy cho phép.

~~~sql
-- Cột token chỉ dành cho equality lookup, không chứa plaintext.
ALTER TABLE confidential_record
    ADD COLUMN lookup_token BYTEA;

CREATE INDEX idx_confidential_lookup
    ON confidential_record (tenant_id, lookup_token);
~~~

**Cảnh báo:** blind index **làm lộ tính bằng nhau và tần suất**; với dữ liệu miền nhỏ/dễ đoán, việc lộ khóa index hoặc quyền tạo token có thể hỗ trợ dictionary attacks. Nó không cung cấp tìm kiếm LIKE, sắp xếp, range query hay phép cộng trên ciphertext theo cách tổng quát. Phải đánh giá **normalization, domain separation, key rotation, token truncation/collision và side channels**.

### 13.3. Deterministic encryption, tokenization và searchable encryption

Mã hóa xác định (deterministic) có thể tạo cùng ciphertext cho cùng plaintext, nhưng cũng làm lộ equality/frequency. Không tự đổi AES-GCM sang nonce cố định để đạt tính xác định; việc **tái sử dụng nonce dưới cùng key** là lỗi nghiêm trọng. Nếu yêu cầu tìm kiếm bảo mật đặc thù, đánh giá **tokenization/vault, blind indexes, cơ chế deterministic AEAD được chuẩn hóa hoặc giải pháp searchable encryption đã được thẩm định**, cùng mô hình rò rỉ và giới hạn truy vấn.

### 13.4. Unique constraints và validation

Nếu cột email plaintext trước đây có `UNIQUE`, sau khi mã hóa ngẫu nhiên, constraint trên ciphertext **không còn đảm bảo email duy nhất**. Có thể dùng index token HMAC hoặc validation ở tầng nghiệp vụ với transaction/concurrency chặt, nhưng phải giải thích rò rỉ equality và race conditions.

**Không giải mã hàng triệu bản ghi để tìm theo email trên mỗi request** mà không có thiết kế throughput/quota; đó có thể biến hệ thống thành một luồng unwrap khổng lồ và tạo thêm bề mặt DoS.

## 14. AAD, schema evolution và thay đổi khóa chính

Khi dữ liệu đã được gắn với `tenantId`, `recordId`, `fieldName` trong AAD, **schema migration** không còn chỉ là đổi cột SQL; nó ảnh hưởng trực tiếp đến khả năng giải mã.

### 14.1. Đổi `record_id`

Nếu ứng dụng đổi UUID của record mà không re-encrypt ciphertext hoặc không giữ original authenticated identifier trong định dạng được duyệt, AAD sẽ khác và AES-GCM sẽ từ chối. Đổi định danh cần:

1. Được ủy quyền cho record/tenant.
2. Đọc envelope cũ và mở bằng **context cũ**.
3. Tạo ciphertext mới với **AAD context mới** và nonce hợp lệ; đơn giản nhất là DEK mới.
4. Ghi dữ liệu mới và key metadata **theo transaction**.
5. Kiểm tra khả năng đọc, audit và xóa bản cũ đúng retention.

**Không nên bỏ `recordId` khỏi AAD chỉ vì migration khó**, nếu việc chống tráo record là một yêu cầu bảo mật thực sự.

### 14.2. Chuyển bản ghi giữa tenant

Tenant transfer là thay đổi ranh giới ủy quyền. Không chỉ đổi `tenant_id` trong bảng rồi giữ nguyên blob, vì điều đó có thể:

- Khiến AAD không khớp và decrypt thất bại.
- Dùng lại wrapped DEK bảo vệ dưới KEK của tenant cũ.
- Làm rò dữ liệu do kiểm tra quyền ở tenant mới không phù hợp.

Một quy trình có kiểm soát sẽ **xác thực cả quyền chuyển đi và nhận**, giải mã trong môi trường được phép, mã hóa lại dưới DEK/KEK và AAD của tenant đích, kiểm tra backup/phụ thuộc rồi đóng quyền của tenant nguồn.

### 14.3. Thay format hoặc thuật toán

Khi chuyển từ `formatVersion=1` sang `formatVersion=2`, record cũ vẫn cần được đọc bằng **decoder cũ được kiểm soát** cho đến khi migration hoàn tất. Giới hạn các version được phép; không để client đưa algorithm string tùy ý khiến service chạy thuật toán lỗi thời hoặc provider không được duyệt.

**Dữ liệu AAD/format cần được ràng buộc với đúng byte được mã hóa.** Không chỉ sửa `format_version` trong database sau khi encrypt rồi kỳ vọng decrypt vẫn thành công.

### 14.4. Chống rollback bản ghi

AEAD tag có thể phát hiện sửa ciphertext, nhưng nếu attacker thay toàn bộ hàng hiện tại bằng **một hàng cũ từng hợp lệ với cùng AAD**, tag cũ vẫn có thể xác minh thành công. Để bảo vệ chống **rollback/replay dữ liệu lịch sử**, cần thêm cơ chế như **phiên bản monotonic được giữ ngoài miền sửa của attacker, audit append-only có integrity, giao dịch có counter đáng tin hoặc protocol chống replay**.

**`row_revision` chỉ lưu trong cùng database bị attacker kiểm soát không phải bảo đảm chống rollback độc lập.** Nó hữu ích cho optimistic concurrency, nhưng attacker có quyền sửa toàn bộ hàng có thể đặt revision cũ.

## 15. KMS/HSM, vùng tin cậy và quyền trên KEK

Một kiến trúc database envelope encryption thường để **database không nắm raw KEK**, chỉ lưu wrapped DEK và key references. Một managed KMS/HSM có thể giữ KEK dưới dạng **non-extractable** theo loại khóa và API được hỗ trợ.

| Thành phần | Dữ liệu/quyền hợp lý | Không nên chứa/quản lý vô điều kiện |
| --- | --- | --- |
| **Database** | Ciphertext, nonce/tag, wrapped DEK, KEK reference, version/metadata | Raw KEK, raw DEK hoặc plaintext trường nhạy cảm |
| **Application service** | DEK dạng rõ **tạm thời khi cần**, resource authorization, AAD logic | Raw KEK dài hạn, mọi tenant credential, log plaintext |
| **KMS/HSM** | KEK, Wrap/Unwrap API, key state, policies/audit | Quy tắc nghiệp vụ đầy đủ về quyền đọc từng record |
| **Identity/authorization service** | Principal, tenant/resource permissions, approval | Vật liệu khóa mật mã không cần thiết |
| **Key inventory** | Logical KEK, version, owner, cryptoperiod, provenance, dependencies | Raw secrets hoặc mật khẩu token |
| **Auditor** | Quyền xem log/metadata, kiểm tra tuân thủ | Quyền mặc định `Decrypt/Unwrap/ExportKey` |

### 15.1. Giới hạn KMS IAM

Nếu KMS chỉ biết service `payments-api` có quyền `Unwrap`, nó không tự quyết định user A có được đọc record của user B không. **Authorize dữ liệu trước**, sau đó KMS mới thực hiện một thao tác mật mã trong phạm vi service đã được cấp quyền.

Nếu provider hỗ trợ **encryption context**, có thể ràng buộc context như tenant/purpose với wrapped blob; ứng dụng vẫn phải kiểm tra rằng context được lấy từ nguồn đáng tin và được dùng thống nhất.

### 15.2. Non-extractable không có nghĩa không bị lạm dụng

Một KEK không xuất được vẫn có thể được dùng qua API `Unwrap` nếu attacker chiếm được workload credential. Do đó cần **least privilege, role separation, rate limits/monitoring, network controls và runbook revoke nhanh**.

### 15.3. Key generation và provenance

Đối với KEK có phạm vi rộng, key owner có thể yêu cầu:

- Sinh key **trong approved KMS/HSM boundary** bằng entropy/DRBG được đánh giá.
- Non-extractability theo khả năng provider thực thi.
- Key ID/version, `createdAt`, `activationAt`, policy revision và owner được đăng ký.
- `Wrap/Unwrap` tách với quyền `DeleteKey`, thay policy hoặc xuất/import.
- Quorum approval cho các thao tác root/KEK nhạy cảm theo risk tier.

Một KEK **sinh trong JVM rồi import vào HSM** không có provenance giống key được sinh bên trong HSM; bản sao ngoài HSM có thể còn tồn tại.

## 16. Rotation KEK trong database: rewrap DEK không động tới ciphertext

**Rotation KEK bình thường** là chuyển sang vật liệu KEK mới trong khi **DEK và dữ liệu mã hóa vẫn được tin cậy**. Lợi thế của envelope encryption là có thể thay lớp bọc mà không phải đọc/decrypt/re-encrypt toàn bộ plaintext.

~~~mermaid
flowchart TD
    A[KEK v4 sắp hết new-use period] --> B[Phê duyệt KEK v5 + chuẩn bị KMS]
    B --> C[Activation v5, chuyển primary WRAP_NEW]
    C --> D[Đọc wrapped DEK + version theo batch]
    D --> E[Provider unwrap v4 / rewrap v5]
    E --> F[CAS update wrapped DEK + kekVersion + revision]
    F --> G{DB update count = 1?}
    G -->|Không| H[Conflict: đọc lại, reconcile hoặc retry có điều kiện]
    G -->|Có| I[Verify decrypt và ghi audit]
    H --> D
    I --> J[Scan backups / snapshots / outbox / legacy rows]
    J --> K{Còn phụ thuộc KEK v4?}
    K -->|Có| D
    K -->|Không| L[Retire/destroy v4 theo retention]
~~~

### 16.1. Quy trình vận hành

1. **Inventory:** liệt kê DEK/records/backups được bọc dưới KEK version cũ, không chỉ bảng chính.
2. **Successor:** sinh KEK mới, đăng ký key version/owner, kiểm tra IAM, quota, backup và activation.
3. **Cutover:** ứng dụng bắt đầu wrap DEK mới dưới KEK mới; vẫn cho phép unwrap version cũ trong thời gian chuyển.
4. **Batch rewrap:** dùng API KMS/HSM phù hợp; nếu có server-side re-encrypt/rewrap không xuất raw DEK, ưu tiên theo policy.
5. **CAS update:** thay `wrapped_dek`, `kek_key_ref`, `kek_version` trong cùng database transaction, kiểm tra `row_revision`.
6. **Canary và verification:** thử decrypt một số bản ghi được chọn/đại diện và kiểm tra tính toàn vẹn.
7. **Backup/retention:** xác minh các bản snapshot, archive và downstream còn cần KEK cũ không.
8. **Retire/destroy:** không hủy bản cũ cho đến khi dependencies đã được xử lý hoặc có quyết định crypto-erasure chủ đích.

### 16.2. Không sao chép `wrapped_dek` sang KEK mới bằng sửa nhãn

Thay `kek_version = 'v5'` trong DB mà không **thực hiện rewrap thực sự** sẽ khiến unwrap thất bại hoặc gây key-confusion. Một alias `current` không phải vật liệu khóa; key version là một thành phần của định tuyến đúng.

### 16.3. Khi nào không nên chỉ rewrap?

Nếu DEK yếu, bị lộ hoặc có khả năng attacker đã lấy **KEK cũ cùng wrapped DEK cũ**, rewrap bản hiện tại **không xóa các bản sao đã bị thu thập**. Cần đánh giá **DEK mới và re-encrypt**, cùng tác động đến ciphertext/backup lịch sử.

## 17. Rotation DEK và re-encrypt không gián đoạn

**DEK rotation** thay vật liệu mã hóa dữ liệu, tạo ciphertext/tag mới. Điều này khác rewrap KEK, có thể cần đọc và xử lý lượng lớn plaintext trong môi trường được phép.

### 17.1. Khi nào nên thay DEK?

- DEK hoặc nguồn sinh DEK bị nghi compromise/entropy yếu.
- Một DEK dùng quá cryptoperiod, nonce/usage limit hoặc dữ liệu lớn hơn profile cho phép.
- Thay algorithm/format/AAD hoặc chuyển tenant/resource boundary.
- Tổ chức muốn thu hẹp phạm vi dữ liệu phụ thuộc một DEK dài hạn.
- Yêu cầu an ninh/tuân thủ thay đổi và bắt buộc re-encrypt.

### 17.2. Một quy trình an toàn

~~~text
1. Xác thực quyền migration và ghi operationId.
2. Đọc envelope cũ theo tenant + record ID + row_revision.
3. Unwrap DEK cũ bằng key version chính xác.
4. Verify tag cũ và lấy plaintext trong trusted memory.
5. Sinh DEK mới qua nguồn đã được phê duyệt.
6. Mã hóa plaintext bằng AEAD, nonce/AAD theo format mới.
7. Wrap DEK mới dưới KEK đang active.
8. CAS update toàn bộ envelope cùng metadata theo transaction.
9. Đọc lại, verify, audit và xử lý bản sao/backup cũ theo policy.
~~~

**Trạng thái lỗi:** nếu verification hoặc DB commit thất bại, phải giữ bản cũ còn có thể đọc, không xóa KEK/DEK cũ trước khi bản mới nhất quán. Nếu một record bị sửa đồng thời, rollback transaction và retry dựa trên phiên bản mới, không ghi đè dữ liệu của user.

### 17.3. Tác động tài nguyên

Re-encrypt có thể cần nhiều **đọc/ghi DB, CPU, KMS calls, memory, network, storage/WAL và thời gian**. Thử canary trên tập nhỏ, giới hạn concurrency, có checkpoint và cơ chế pause/resume. Không chạy một transaction duy nhất giữ lock hàng triệu hàng.

### 17.4. Re-encrypt không chữa việc đã lộ

Nếu attacker đã đọc plaintext trước khi key được thay, encryption mới chỉ giúp giảm nguy cơ truy cập **trong tương lai**. Không tuyên bố “dữ liệu đã an toàn trở lại hoàn toàn” khi bản cũ đã bị sao chép.

## 18. Online migration: dual read, single write và backfill

Thay format mã hóa khi ứng dụng vẫn phục vụ traffic đòi hỏi **quy trình chuyển đổi phiên bản có kiểm soát**:

~~~mermaid
flowchart TD
    Start[Triển khai reader hiểu format cũ + mới] --> Gate[Kiểm thử negative tests, KMS policy và metrics]
    Gate --> Write[Writer chỉ ghi format mới]
    Write --> Backfill[Backfill batch hàng cũ bằng CAS]
    Backfill --> Check{Có lỗi, conflict hoặc pending rows?}
    Check -->|Có| Retry[Checkpoint + reconcile + retry có điều kiện]
    Retry --> Backfill
    Check -->|Không| Audit[Kiểm tra decrypt/backup/consumers]
    Audit --> Retire[Ngừng writer/reader cũ khi đủ điều kiện]
    Retire --> Destroy[Hủy key cũ theo retention và approval]
~~~

### 18.1. Reader hai version

Reader cần nhận `formatVersion` để chọn đúng **codec/algorithm profile đã được duyệt**. Không để giá trị tùy ý từ DB kích hoạt thuật toán bị cấm. Trong giai đoạn migration, đọc định dạng cũ và mới theo policy, nhưng **writer chỉ tạo định dạng mới** sau cutover.

### 18.2. Backfill từng batch

Job dùng **cursor/checkpoint theo key ổn định**, batch size và throttling; mỗi update có `row_revision` guard. Khi job crash giữa chừng, có thể chạy lại mà không ghi đè record đã được migration. Với DB replication, giám sát **replica lag, WAL volume và lock contention**.

### 18.3. Dual write có cần không?

Việc ghi đồng thời cả ciphertext cũ và mới có thể tạo **hai bản sao nhạy cảm, tăng storage và complexity**. Nếu dùng dual write vì backward compatibility, phải bảo vệ cả hai version, có kế hoạch cắt đường cũ, audit và consistency rõ. Nhiều hệ thống có thể chọn **dual read + single new write + background backfill** để đơn giản hơn.

### 18.4. Cutover và rollback

Nếu format mới lỗi, rollback ứng dụng không được khiến writer cũ ghi dưới KEK đã retire hoặc decoder cũ không đọc được record mới. Phải xác định **rollback window, compatible reader, key availability và key version policy** trước khi deploy.

## 19. Backup, WAL, CDC, replication và analytics: nơi plaintext có thể rò rỉ

Chỉ mã hóa cột chính **không đủ** nếu hệ sinh thái dữ liệu vẫn xuất plaintext qua những đường khác.

| Thành phần | Cần kiểm tra | Biện pháp |
| --- | --- | --- |
| **Database backup/snapshot** | Có ciphertext/wrapped DEK và metadata nào? Có bản plaintext cũ không? | Retention, key dependency, backup encryption, restore test |
| **WAL/transaction log** | Những giá trị nào được ghi trước/sau encryption? | Mã hóa ở application trước SQL, kiểm tra hệ quản trị/extension |
| **CDC (Change Data Capture)** | Dữ liệu phát ra là ciphertext hay plaintext? | Phân loại connector, downstream IAM, cấm decrypt tùy tiện |
| **Read replicas** | Replica có cùng khả năng unwrap hoặc key access không? | Replica thường không cần KEK; kiểm soát ứng dụng đọc |
| **ETL/analytics/BI** | Pipeline có gọi decrypt để lấy dữ liệu rõ không? | Data minimization, tokenization, scoped access, audit |
| **SQL query logs/APM tracing** | Có bind parameters hoặc result chứa plaintext? | Redaction, không ghi raw values, access control |
| **ORM events/triggers** | Trigger có ghi bản sao rõ vào bảng phụ không? | Mapping review, migration và test end-to-end |
| **Caching/search services** | Có lưu plaintext ở Redis, search index hoặc logs không? | Encrypt/tokenize hoặc tách vùng tin cậy theo policy |
| **Exports/support bundles** | Có snapshot/dump đem ra ngoài production không? | KMS boundary, sandbox data, retention và approval |

### 19.1. WAL và CDC theo vị trí mã hóa

Nếu **application mã hóa trước khi gửi SQL**, database engine thường nhận ciphertext, nên WAL của thao tác INSERT đó chứa ciphertext thay vì plaintext của trường đã mã hóa. Nhưng nếu ứng dụng gọi **database-side decrypt** hoặc ghi giá trị rõ vào bảng tạm/triggers, các đường log/replication tương ứng có thể nhìn thấy plaintext.

**Không kết luận mọi WAL/backup luôn được bảo vệ**: phụ thuộc nơi mã hóa, DBMS, extension, cấu hình log và những bảng chưa được chuyển đổi.

### 19.2. Restore test phải đi cùng KEK

Một bản backup database chứa `wrapped_dek` nhưng KEK version đã bị hủy có thể trở thành **dữ liệu không thể giải mã**. Restore rehearsal cần kiểm tra:

1. Key ID/version và region KMS có còn truy cập được không?
2. Encryption context/AAD có thể dựng lại từ metadata đúng không?
3. Credentials, IAM, HSM partition và key state có phù hợp môi trường restore?
4. Bản backup/record có key format cũ cần decoder cũ không?
5. Việc restore có vô tình **kích hoạt/ghi** bằng key production vào môi trường test không?

Không tự copy raw KEK sang sandbox chỉ để restore nhanh. Dùng **DR đã được phê duyệt** và dữ liệu/test keys phù hợp.

## 20. Key inventory và bản đồ phụ thuộc DEK–KEK

Một bản ghi database chứa wrapped DEK không phải lúc nào cũng được liệt kê trực tiếp trong **central key inventory**. Inventory có thể lưu **KEK key versions cùng phạm vi dữ liệu, bảng, số lượng DEK và liên kết backup**, còn mapping chi tiết từng record nằm trong DB hoặc một index có integrity.

### 20.1. Metadata KEK nên theo dõi

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `keyId/version` | KEK vật liệu cụ thể, không chỉ alias |
| `ownerTeam`, `custodian` | Trách nhiệm và người vận hành |
| `purpose` | `WRAP/UNWRAP`, scope DB/tenant/service |
| `algorithm`, `providerRef` | Wrapping mechanism, KMS/HSM boundary |
| `createdAt`, `activationAt` | Nguồn sinh và hiệu lực |
| `newUseUntil`, `oldUseUntil` | Cryptoperiod cho wrap mới và unwrap cũ |
| `lifecycleState` | PRE_ACTIVE/ACTIVE/RETIRED/REVOKED... |
| `wrappedDekCount` | Phụ thuộc ở DB và version cụ thể |
| `dependentSystems`, `backupRefs` | Cần thiết trước retire/destroy |
| `policyRevision`, `auditRef` | Bằng chứng quyết định và thao tác |

### 20.2. Ví dụ bản ghi inventory

~~~json
{
  "keyId": "payments-kek",
  "keyVersion": "v5",
  "ownerTeam": "payments-security",
  "purpose": ["WRAP", "UNWRAP"],
  "tenantScope": "production/payments",
  "providerRef": "kms://example/payments-kek/v5",
  "generationBoundary": "MANAGED_KMS",
  "lifecycleState": "PRE_ACTIVE",
  "createdAt": "2026-11-28T08:00:00Z",
  "activationAt": "2026-12-01T00:00:00Z",
  "newUseUntil": "2027-03-01T00:00:00Z",
  "oldUseUntil": "2027-09-01T00:00:00Z",
  "policyRevision": 22,
  "dependentTables": ["confidential_record"],
  "wrappedDekCount": 0,
  "auditRef": "audit-keygen-00281"
}
~~~

Ví dụ mang tính khái niệm, không phải schema/API chuẩn của một KMS. Trạng thái **PRE_ACTIVE** nhất quán vì thời gian kích hoạt vẫn trong tương lai tại thời điểm ghi. `wrappedDekCount=0` minh họa version mới chưa bắt đầu được dùng, không phải số liệu thực.

## 21. Thu hồi, hủy khóa và crypto-erasure trong database

**Disable**, **revoke**, **retire**, **destroy** và **cryptographic erasure** là những khái niệm khác nhau:

- **Retire:** ngừng dùng một version cho bảo vệ mới, có thể vẫn cần unwrap dữ liệu cũ.
- **Disable:** trạng thái provider có thể chặn toàn bộ thao tác; không tự tương đương decrypt-only.
- **Revoke:** rút quyền/tin cậy vì sự cố hoặc thay chính sách; cần truyền thông đến các consumer.
- **Destroy:** tiêu hủy key material theo khả năng và quy trình provider, có thể không đảo ngược.
- **Crypto-erasure:** có chủ đích khiến dữ liệu không thể giải mã bằng cách hủy các khóa cần thiết, với giả định không còn bản sao khóa hoặc plaintext có thể phục hồi.

### 21.1. Hủy KEK có thể làm mất dữ liệu hợp lệ

Trước khi hủy KEK `v4`, phải xác định:

1. Database chính còn wrapped DEK `v4` không?
2. Snapshot/WAL archive/backup cũ có cần `v4` khi restore không?
3. Consumer, replica, ETL hoặc job offline có sử dụng `v4` không?
4. Các record đã rewrap có thực sự unwrap/decrypt bằng `v5` không?
5. Có legal hold, retention hoặc điều kiện phục hồi được data owner xác nhận không?

Nếu còn phụ thuộc, **không destroy** trừ khi tổ chức chủ động chấp nhận mất khả năng giải mã theo quyết định được ủy quyền.

### 21.2. Khóa hủy nhưng bản sao vẫn còn?

Nếu raw DEK hoặc KEK còn trong backup, heap dump, log, key export, DR copy hoặc attacker, xóa một object trong KMS **không tự chứng minh crypto-erasure đã hoàn tất**. Đánh giá khả năng phục hồi secret theo threat model.

### 21.3. Xóa một record

Khi mỗi record có DEK riêng, **làm mất khả năng khôi phục DEK duy nhất** có thể hỗ trợ crypto-erasure của record đó, nhưng phải cân nhắc wrapped DEK/DEK copies ở backup, key caching, replicated environments, plaintext exports và tình trạng shared DEK. Xóa riêng wrapped DEK ở DB chính trong khi bản sao backup vẫn tồn tại **không đủ**.

## 22. Vận hành: KMS outage, latency, quota và cache

Ứng dụng phụ thuộc vào KMS để unwrap DEK khi cần. Sự phụ thuộc này tạo **latency và availability trade-off**, nhất là khi mỗi request phải gọi mạng.

### 22.1. Khi KMS không sẵn sàng

Có các lựa chọn thiết kế có kiểm soát:

- **Fail closed:** không trả plaintext khi không thể xác thực hoặc unwrap.
- **Retry với backoff/jitter:** chỉ retry các lỗi có thể phục hồi, không loop vô hạn trên key bị revoke hoặc policy denied.
- **Circuit breaker/rate limiter:** bảo vệ app, KMS và DB khỏi retry storm.
- **HA/DR đã duyệt:** dùng vùng/cụm KMS có key availability và key reference được nhà cung cấp hỗ trợ.
- **Short-lived DEK cache nếu policy cho phép:** tăng availability nhưng kéo dài thời gian lưu raw DEK; phải có TTL, scope và incident strategy.

**Không fallback sang raw KEK lưu trong environment variable/file** nếu policy yêu cầu KEK ở HSM/KMS. Đây là hạ cấp toàn bộ ranh giới bảo vệ.

### 22.2. Giảm chi phí KMS

Một DEK mỗi bản ghi có thể tạo nhiều thao tác wrap/unwrap. Có thể tối ưu bằng **batching có kiểm soát, data-key caching ngắn hạn, phân nhóm DEK hoặc provider re-encrypt API**, nhưng mỗi biện pháp thay đổi **blast radius, key lifetime, tenant isolation hoặc access audit granularity**. Cần đánh giá theo workload và risk tier.

### 22.3. Các metric gợi ý

| Metric / cảnh báo | Ý nghĩa |
| --- | --- |
| `kmsUnwrapP95/P99` | Độ trễ đọc trường encrypted |
| `kmsPermissionDenied` | Quyền sai, compromise hoặc IAM drift |
| `kmsThrottleRate` | Quota/throttling và nguy cơ retry storm |
| `aeadTagFailureRate` | Blob lỗi, AAD mismatch hoặc bị sửa |
| `unknownKekVersion` | Mapping key/backup/migration chưa nhất quán |
| `rewrapBacklog` | KEK cũ còn nhiều phụ thuộc |
| `decryptOldVersionVolume` | Consumer còn dùng format/KEK cũ |
| `noncePolicyViolations` | Có nguy cơ trùng (key, nonce) |
| `rowVersionConflict` | CAS bị conflict khi backfill/rotation |
| `backupRestoreFailures` | Rủi ro không đọc được lịch sử |
| `rawDataLoggingAlerts` | Bản plaintext/secret bị ghi vào trace/log |

**Không ghi DEK/KEK hoặc plaintext vào metric labels, distributed trace attributes hay error reports**. Ngay cả key refs, tenant IDs và request patterns cũng có thể là metadata nhạy cảm.

## 23. Sự cố: chỉ mất database, mất KMS credential hay lộ raw KEK?

Các kịch bản khác nhau dẫn tới cách xử lý khác nhau. Không thể chỉ nói “database đã mã hóa nên không sao” hoặc “chỉ rotate KEK là xong”.

| Sự cố | Điều phải điều tra | Hướng containment/khắc phục |
| --- | --- | --- |
| **Lộ database dump** | Có raw DEK/KEK, log plaintext, token index hoặc metadata nhạy cảm không? | Cô lập dump, rà nguồn key/backup, đánh giá dữ liệu vẫn bí mật và quyền truy cập |
| **App server bị chiếm** | Raw DEK trong RAM/cache, plaintext, khả năng gọi KMS và phạm vi record? | Revoke principal, tắt API nguy hiểm, kiểm tra audit và dữ liệu đã được đọc |
| **KMS `Unwrap` credential bị chiếm** | Những wrapped DEK nào đã được unwrap và trả về? | Revoke grants/session, xác định phạm vi, đánh giá DEK mới |
| **Raw KEK bị lộ** | Attacker có bản wrapped DEK/ciphertext nào, từ backup nào? | Thay KEK, đánh giá DEK mới/re-encrypt; rewrap hiện tại không thu hồi bản sao cũ |
| **Một DEK bị lộ** | Những row/field/revisions nào dùng DEK đó? | Re-encrypt bằng DEK mới, xử lý bản cũ và tác động bí mật |
| **Nonce reuse** | Có bao nhiêu bản mã chia cùng (key, nonce)? | Cô lập, thay DEK, re-encrypt, đánh giá tính bí mật/toàn vẹn |
| **Ciphertext bị tráo giữa tenant** | AAD và authorization có phát hiện không? | Kiểm tra tag/context, chặn bản ghi lỗi, audit và điều tra quyền |
| **KEK bị hủy nhầm** | Backup, replicas, recovery copies và retention | Incident recovery theo chính sách; không tự phục hồi raw key từ nguồn không tin cậy |

### 23.1. Sự thật về rewrap sau compromise

Giả sử attacker đã lấy:

~~~text
KEK_v4
wrappedDEK_v4 = Wrap(KEK_v4, DEK_A)
ciphertext_v1 = AEAD_Encrypt(DEK_A, plaintext)
~~~

Ứng dụng tạo `KEK_v5` và lưu `Wrap(KEK_v5, DEK_A)`. **Attacker vẫn có `KEK_v4` và `wrappedDEK_v4` cũ**, nên họ vẫn có thể khôi phục `DEK_A` và giải mã bản ciphertext đã lấy. Việc rewrap các bản đang lưu không xóa bản sao đó.

Khi **DEK đã hoặc có khả năng bị lộ**, cần đánh giá thay DEK và re-encrypt. Ngay cả vậy, dữ liệu đã bị đọc hoặc được sao chép trước đó **không thể “thu hồi” bằng mật mã**.

### 23.2. Thời điểm và key provenance

Key inventory/audit cần có **key ID/version, generation source, activation, cryptoperiod, provider audit, principal, operation ID và dependency mapping** để xác định những bản ghi bị ảnh hưởng. Không tự nâng mức tin cậy của một log `createdAt` do client khai báo lên bằng chứng về provider generation.

## 24. Case study: hệ thống hóa đơn SaaS đa tenant

Một nền tảng hóa đơn phục vụ **200 tenant**; mỗi tenant có hàng triệu bản ghi. Nhóm kỹ thuật cần bảo vệ **số tài khoản ngân hàng** khỏi rủi ro lộ database dump và tránh để DBA truy cập plaintext trường này.

### 24.1. Thiết kế ban đầu

- Database bật TDE, nhưng **cột `bank_account` lưu plaintext**.
- Nhóm báo cáo có quyền `SELECT` trực tiếp qua BI và có thể đọc số tài khoản.
- Backup/CDC đôi khi được xuất sang môi trường kiểm thử.
- Một service account chung có quyền đọc dữ liệu nhiều tenant.

TDE vẫn có tác dụng bảo vệ ổ đĩa theo phạm vi của nó, nhưng **không giải quyết mọi đường SQL, BI hoặc export có quyền**.

### 24.2. Thiết kế envelope encryption

1. **Data owner** phân loại số tài khoản và định nghĩa retention.
2. **Key owner** duyệt KEK theo tenant hoặc nhóm tenant hợp lý, owner/purpose/cryptoperiod và quyền wrap/unwrap trong KMS.
3. **Data service** tạo record UUID và DEK mới, mã hóa số tài khoản bằng AES-GCM/AAD với `tenantId, recordId, fieldName`.
4. Database lưu `ciphertext_and_tag, nonce, wrapped_dek, kekVersion, formatVersion`, không lưu plaintext.
5. **Chỉ dịch vụ xử lý thanh toán được ủy quyền** mới unwrap và dùng plaintext trong bộ nhớ tạm.
6. Service báo cáo dùng **metadata tối thiểu** hoặc kết quả đã được tokenized/aggregated thay vì giải mã toàn bộ.
7. Mọi KMS unwrap và truy cập record nhạy cảm có audit/correlation ID.

### 24.3. Thách thức tra cứu theo số tài khoản

Đội hỗ trợ trước đây tìm đúng số tài khoản bằng `WHERE bank_account = ?`. Với ciphertext random, truy vấn đó không hoạt động. Nhóm có thể:

- Sử dụng reference/token do hệ thống thanh toán cung cấp nếu thích hợp.
- Xây dựng **blind index riêng theo tenant với HMAC key độc lập**, chấp nhận leakage equality/frequency sau threat review.
- Giới hạn chức năng tra cứu ở ứng dụng có quyền, không xuất raw field vào BI.

**Không chuyển sang AES-GCM nonce cố định để giữ phép so sánh SQL.**

### 24.4. Cutover

Nhóm triển khai **reader hỗ trợ bản ghi plaintext cũ được kiểm soát và bản ghi encrypted mới**, sau đó chỉ ghi format encrypted. Backfill từng batch sử dụng `row_revision`, kiểm tra correctness, telemetry và dữ liệu backup; khi hoàn tất mới cắt đường đọc plaintext cũ. Phần plaintext cũ trong backup/CDC/ETL được xử lý theo retention.

### 24.5. Rotation và sự cố

Đến hạn KEK, nhóm chuyển KEK primary, rewrap DEK và kiểm tra restore. Nếu một DEK hoặc KMS principal bị chiếm, đội an ninh **đánh giá dữ liệu đã bị truy xuất**, thay DEK/re-encrypt các hàng cần thiết, không chỉ rewrap.

**Kết luận tình huống:** thành công không nằm ở việc thêm cột `wrapped_dek`. Thành công là hệ thống có **ranh giới truy cập rõ ràng, key lifecycle, query strategy, migration, backup và audit** phù hợp với mô hình đe dọa thực sự.

## 25. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Giải pháp |
| --- | --- | --- |
| Bật TDE rồi tuyên bố DBA không đọc được cột | Hiểu sai ranh giới | Phân tích nơi plaintext xuất hiện, cân nhắc application-side encryption |
| Lưu raw KEK trong cùng database với wrapped DEK | Mất toàn bộ ranh giới bảo vệ | KMS/HSM hoặc key custody tách biệt |
| Lưu raw DEK cạnh ciphertext để tiện decrypt | Database dump đọc được dữ liệu | Chỉ lưu wrapped DEK, hạn chế plaintext DEK ở RAM |
| Dùng `Random`/timestamp sinh DEK | Key entropy yếu | CSPRNG/KMS-approved data key |
| Dùng AES-GCM với nonce cố định để dễ search | Nguy cơ phá tính bí mật và toàn vẹn | Nonce unique; thiết kế search/token riêng |
| Một DEK chung vô hạn cho mọi tenant | Blast radius lớn, nonce khó quản lý | Tách scope key và cryptoperiod |
| Không có AAD tenant/record | Có nguy cơ swap/replay context | Canonical AAD và resource authorization |
| Đưa `tenantId` từ client thẳng vào AAD/KMS context | Có thể giải mã sai tenant | Nguồn context đáng tin và kiểm tra quyền |
| Thay `record_id` mà không re-encrypt | AAD mismatch, không đọc được record | Migration dữ liệu đúng ngữ cảnh |
| Chỉ index ciphertext ngẫu nhiên để search | Query equality không hoạt động | Tách metadata, blind index hoặc tokenization theo risk review |
| Coi blind index không tiết lộ gì | Lộ equality/frequency, có thể hỗ trợ guessing | Threat model và key riêng/normalization |
| Chỉ dùng `keyAlias=current` trong record | Không tìm được KEK version cũ | Lưu key ID/version ổn định |
| Cập nhật wrapped DEK không cùng KEK reference | Envelope không nhất quán | Transaction/CAS trên toàn bộ metadata liên quan |
| Rotation job ghi đè ciphertext mới do dùng snapshot cũ | Lost update của người dùng | Optimistic locking và field-level update đúng phạm vi |
| Coi KMS call là một phần ACID transaction DB | Orphan/duplicate hoặc retry sai | Idempotency, reconciliation, audit |
| Chỉ rewrap DEK đã lộ | Attacker vẫn có cùng DEK | Thay DEK và re-encrypt khi cần |
| Destroy KEK khi backup vẫn chứa wrapped DEK cũ | Mất khả năng restore | Dependency inventory và restore rehearsal |
| Tin tag AEAD tự ngăn rollback cả row cũ | Replay hợp lệ vẫn có thể pass | Counter/audit độc lập và trusted revision |
| DB logs/CDC/BI vẫn giữ plaintext | Vỡ ranh giới kỳ vọng | Soát toàn bộ data path, redaction, migration |
| KEK non-extractable nên cho app unwrap mọi record | App/KMS principal có thể bị lạm dụng | IAM + tenant/resource authorization và monitoring |
| KMS timeout thì fallback sang KEK ở environment | Hạ cấp bảo mật | Fail-closed và DR đã duyệt |
| Không xác thực tag trước khi trả plaintext | Có thể chấp nhận dữ liệu bị sửa | AEAD decrypt/verify đầy đủ |
| Log AAD, DEK, plaintext và toàn bộ SQL bind params | Lộ dữ liệu ở observability | Logs metadata tối thiểu và phân quyền |

## 26. Checklist triển khai production

- [ ] Đã phân biệt **TDE, database-side encryption và application-side envelope encryption**?
- [ ] Threat model nói rõ chống database dump, DBA, host compromise, KMS principal và attacker sửa record tới mức nào?
- [ ] Có **Key owner, Data owner, custodian, audit responsibilities** cho KEK/DEK?
- [ ] DEK được sinh bằng **CSPRNG/KMS**, phạm vi per-row/per-object/per-tenant hợp lý?
- [ ] KEK được giữ ở boundary được duyệt, có key ID/version, usage `Wrap/Unwrap`, non-extractability nếu policy yêu cầu?
- [ ] AES-GCM/AEAD có **nonce uniqueness**, tag và giới hạn số bản mã/key?
- [ ] AAD ràng buộc **tenant/record/purpose/format** bằng canonical encoding?
- [ ] Application kiểm tra **caller → tenant → record** trước khi unwrap và trả dữ liệu?
- [ ] Database không lưu raw KEK, raw DEK hoặc plaintext trường đã được phân loại?
- [ ] Schema lưu **ciphertext/tag, nonce, wrapped DEK, KEK reference/version, format/context version** nhất quán?
- [ ] SQL/JDBC dùng prepared statements, input/size limits và transaction phù hợp?
- [ ] Có **idempotency, optimistic concurrency, CAS** cho UPDATE và rotation jobs?
- [ ] Query/index/search strategy đã được thiết kế lại, đánh giá leakage của blind index/tokenization?
- [ ] Hệ thống hỗ trợ schema/algorithm versioning; tenant transfer/PK change không làm AAD sai?
- [ ] Có biện pháp chống **rollback/replay hàng cũ** nếu threat model yêu cầu?
- [ ] KMS IAM, scoped grants, encryption context, quotas và audit được kiểm tra thực tế?
- [ ] DEK caching (nếu có) giới hạn TTL/scope và có incident revocation strategy?
- [ ] KEK rotation có rewrap batch, canary, CAS, checkpoint và restore validation?
- [ ] DEK rotation có re-encrypt, đồng bộ format/AAD và xử lý lỗi/concurrent updates?
- [ ] Online migration dùng dual-read/single-new-write/backfill hoặc phương án đã kiểm thử?
- [ ] Backup/WAL/CDC/replicas/ETL/BI/log/tracing không phát sinh đường plaintext không kiểm soát?
- [ ] Đã kiểm tra restore của **database + đúng KEK versions + decoder cũ + IAM**?
- [ ] Có runbook phân biệt **database dump leak, app compromise, KMS API abuse, raw KEK/DEK leak**?
- [ ] Không tự fallback sang software/raw KEK khi KMS unavailable?
- [ ] Có negative tests: wrong tenant, wrong record AAD, tampered tag, wrong KEK version, expired/revoked key?
- [ ] Key inventory có **key provenance, cryptoperiod, dependencies, owner và evidence** trước khi retire/destroy?
- [ ] Các quyết định export/delete/root KEK và crypto-erasure được phê duyệt/quorum theo risk tier?

## 27. Câu hỏi tự kiểm tra

**1. Envelope encryption trong database có khác TDE không?**  
Có. TDE chủ yếu bảo vệ dữ liệu ở tầng lưu trữ DB; envelope encryption mô tả DEK mã hóa dữ liệu và KEK bọc DEK. Khi ứng dụng mã hóa trước SQL, database có thể chỉ thấy ciphertext ở cấp trường.

**2. Tại sao phải lưu wrapped DEK cùng ciphertext?**  
Để có thể tìm đúng DEK khi cần giải mã sau này mà không giữ raw DEK ở trạng thái nghỉ trong database.

**3. Khi nào dùng DEK per-row tốt hơn DEK per-table?**  
Khi cần giới hạn blast radius và hỗ trợ xử lý sự cố/rotation theo từng bản ghi; đổi lại là nhiều metadata và chi phí key operations hơn.

**4. Vì sao AES-GCM cần nonce khác nhau dưới cùng DEK?**  
Tái sử dụng cùng (key, nonce) có thể làm hỏng tính bí mật/toàn vẹn của GCM. Khi update nhiều lần, phải thay nonce hoặc DEK theo strategy đã duyệt.

**5. AAD với tenantId và recordId có thay authorization không?**  
Không. AAD phát hiện sai ngữ cảnh cryptographic; ứng dụng vẫn phải kiểm tra caller có quyền đọc record/tenant đó.

**6. Vì sao không thể search trực tiếp theo ciphertext AES-GCM ngẫu nhiên?**  
Vì cùng plaintext với key/nonce khác có ciphertext khác. Cần query metadata, tokenization/blind index được đánh giá hoặc thiết kế tìm kiếm khác.

**7. Blind index HMAC có che hoàn toàn việc hai hàng cùng giá trị không?**  
Không. Một token xác định cho cùng giá trị thường làm lộ equality/frequency; phải đánh giá rủi ro suy đoán và key separation.

**8. Khi đổi record ID đã được đưa vào AAD, chỉ cập nhật primary key SQL có được không?**  
Không. AAD mới sẽ khác; cần migration và re-encrypt/re-authenticate dữ liệu với ngữ cảnh mới.

**9. Trong KEK rotation, có cần re-encrypt mọi ciphertext không?**  
Không nhất thiết. Khi DEK vẫn an toàn, có thể rewrap DEK dưới KEK mới mà giữ nguyên ciphertext dữ liệu.

**10. Nếu DEK bị lộ, chỉ rewrap dưới KEK mới có đủ không?**  
Không. DEK cũ vẫn lộ; cần đánh giá DEK mới và re-encrypt dữ liệu.

**11. Vì sao cập nhật một hàng khi rewrap cần `row_revision`?**  
Để chống lost update/conflict khi user, app hoặc migration job đồng thời sửa bản ghi, nhất là khi phải cập nhật wrapped DEK và key metadata nhất quán.

**12. AEAD có ngăn attacker khôi phục cả một hàng cũ hợp lệ không?**  
Không tự động. Tag cũ vẫn có thể hợp lệ; chống rollback yêu cầu trusted revision/audit hoặc cơ chế độc lập khác.

**13. Tại sao bản backup database còn wrapped DEK cũ liên quan đến KEK deletion?**  
Vì restore từ backup có thể cần KEK version cũ để unwrap DEK. Xóa sớm có thể khiến dữ liệu backup không thể đọc.

**14. Nếu database dump bị lộ nhưng KEK không bị lộ, dữ liệu chắc chắn an toàn không?**  
Không thể kết luận tuyệt đối. Cần xác minh source key, thuật toán/nonce, plaintext copies, metadata/search tokens, app/KMS credentials và threat model.

**15. Có nên cho ứng dụng dùng KEK lưu trong environment làm fallback khi KMS lỗi?**  
Không nếu policy yêu cầu KEK ở KMS/HSM. Dùng cơ chế HA/DR được duyệt hoặc fail-closed thay vì mở rộng ranh giới lộ secret.

## Ghi nhớ

**Envelope encryption trong database không đơn thuần là “mã hóa một cột”.** Nó là **kiến trúc quản lý DEK–KEK** xuyên suốt ứng dụng, database và KMS/HSM: DEK mã hóa dữ liệu bằng AEAD; KEK bọc DEK; database lưu ciphertext, wrapped DEK, nonce/tag, key reference/version và metadata đúng định dạng. Bảo mật thực tế đòi hỏi **resource authorization trước Unwrap, AAD ràng buộc tenant/record, nonce uniqueness, transaction/CAS, key inventory và audit**. Khi đưa vào hệ thống thật, phải giải quyết **query/index/search leakage, schema migration, backup/WAL/CDC/analytics, KMS outage, cryptoperiod, rotation và incident response**. Đặc biệt, **rewrap KEK không giống re-encrypt DEK**, và việc hủy KEK phải xét cả dữ liệu cùng backup phụ thuộc. Kết hợp **key owner, generation policy, KMS/HSM, least privilege, quorum khi cần, kiểm thử restore và quản lý toàn bộ vòng đời khóa** mới biến envelope encryption thành hàng rào bảo vệ database đáng tin cậy.

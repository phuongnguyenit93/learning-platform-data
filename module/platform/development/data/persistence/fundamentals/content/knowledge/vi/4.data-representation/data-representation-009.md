# Biểu diễn dữ liệu nhị phân lớn và thông tin mô tả

Một ứng dụng Java cho phép người dùng tải lên hóa đơn PDF, ảnh hồ sơ, tệp âm thanh hoặc video. Những tệp này có thể từ vài kilobyte đến hàng gigabyte. Hệ thống cần **lưu đúng dãy byte của tệp**, **biết tệp đó thuộc về ai và được sử dụng thế nào**, đồng thời **tìm kiếm, kiểm soát truy cập, khôi phục và xóa dữ liệu** một cách đáng tin cậy.

Bài học thuộc chương **Biểu diễn dữ liệu** của module `DATA_PERSISTENCE_FUNDAMENTALS`. Trọng tâm là phân biệt **dữ liệu nhị phân lớn** (*large binary object*, thường gọi là BLOB) với **thông tin mô tả** (*metadata*), sau đó thiết kế cách lưu trữ và truy cập chúng trong ứng dụng Java. Kiến thức này nối trực tiếp với việc chọn mô hình dữ liệu, thiết kế lược đồ và chỉ mục, quản lý giao dịch và đồng thời, xử lý lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và tối ưu hiệu năng.

## 1. Bài toán mở đầu: một hóa đơn PDF và hai loại dữ liệu

Giả sử hệ thống quản lý đơn hàng cho phép tải lên hóa đơn `invoice-42.pdf` có kích thước 8 MiB.

Từ góc nhìn nghiệp vụ, người dùng muốn biết:

- Hóa đơn thuộc đơn hàng `42` và do ai tải lên?
- Tệp có tên gì, định dạng gì, lớn bao nhiêu, tải lên lúc nào?
- Người dùng nào được phép tải xuống hoặc xóa?
- Dữ liệu tệp có nguyên vẹn so với thời điểm tải lên?
- Tệp đang chờ xử lý, đã sẵn sàng hay bị từ chối?
- Có thể thay thế tệp bằng phiên bản mới và truy xuất phiên bản cũ không?

Tuy nhiên, **các byte của tệp PDF** không trực tiếp trả lời những câu hỏi đó. Cần một tập hợp **metadata** mô tả tệp, quan hệ nghiệp vụ và chính sách truy cập.

| Phần dữ liệu | Ví dụ | Dùng để làm gì? |
| --- | --- | --- |
| **Nội dung nhị phân** (*binary payload*) | Dãy 8 MiB byte tạo nên PDF | Tải xuống, xem, phân tích hoặc chuyển đổi |
| **Metadata mô tả** | Tên gốc, MIME type, kích thước, SHA-256 | Nhận diện, kiểm tra và hiển thị |
| **Metadata nghiệp vụ** | `order_id = 42`, `owner_id = 1001`, loại tài liệu `INVOICE` | Gắn tệp với nghiệp vụ, tìm kiếm và phân quyền |
| **Metadata lưu trữ** | Bucket, object key, trạng thái `READY`, phiên bản | Định vị byte và theo dõi vòng đời lưu trữ |
| **Metadata vận hành** | Thời gian tạo, lần kiểm tra virus, mã lỗi xử lý | Quan sát, xử lý sự cố và kiểm toán |

Một bản ghi metadata **không chứa toàn bộ nội dung PDF**. Nó có thể chỉ chứa tham chiếu đến nơi lưu byte. Ngược lại, một BLOB không tự mang đầy đủ các ràng buộc nghiệp vụ; ngay cả khi định dạng tệp có metadata nội tại, hệ thống vẫn thường cần metadata riêng.

~~~mermaid
flowchart LR
    U["Người dùng tải lên PDF"] --> A["Ứng dụng Java"]
    A --> B["Kiểm tra quyền, loại tệp, giới hạn dung lượng"]
    B --> C["Nội dung: chuỗi byte"]
    B --> D["Metadata: chủ sở hữu, trạng thái, loại, kích thước"]
    C --> E[("BLOB trong DB / object store / file store")]
    D --> F[("Bảng metadata trong DB")]
    F -->|"Tham chiếu bằng object key hoặc ID"| E
~~~

**Nguyên tắc:** phân tách **nội dung**, **thông tin mô tả** và **quan hệ nghiệp vụ** khi phân tích bài toán. Có thể triển khai chúng trong cùng một hệ lưu trữ hoặc ở nhiều hệ khác nhau tùy yêu cầu.

## 2. BLOB là gì? Byte và định dạng tệp

**BLOB** là viết tắt của *Binary Large Object*: một giá trị nhị phân có thể có kích thước lớn. Trong cơ sở dữ liệu quan hệ, BLOB hoặc các kiểu nhị phân tương đương lưu **dãy byte** thay vì các giá trị văn bản/số riêng lẻ. Cách đặt tên và giới hạn tùy hệ quản trị, ví dụ:

- MySQL có các kiểu `BLOB` và biến thể dung lượng khác nhau.
- PostgreSQL có `BYTEA` và cơ chế *large object* riêng; hai cách có đặc điểm sử dụng khác nhau.
- Các cơ sở dữ liệu khác có `VARBINARY`, `BLOB` hoặc kiểu nhị phân tương đương.

Từ **BLOB** cũng thường được dùng theo nghĩa rộng để chỉ payload nhị phân lớn trong hệ thống. Khi nói chính xác về thiết kế, cần phân biệt **cột kiểu BLOB trong database** với **object trong object storage**: cùng có thể chứa dữ liệu nhị phân, nhưng giao dịch, API, chi phí và cơ chế vận hành không giống nhau.

Tệp nhị phân là dãy byte có thứ tự:

~~~text
PDF (ví dụ byte đầu, dạng hex):
25 50 44 46 2D ... 
  %  P  D  F  -

PNG (chữ ký định dạng):
89 50 4E 47 0D 0A 1A 0A ...

JPEG (thường bắt đầu):
FF D8 FF ...
~~~

Các byte đầu như vậy có thể giúp nhận diện định dạng, nhưng **không chứng minh tệp hợp lệ, không chứa nội dung độc hại hoặc đúng MIME type**. Một tệp có thể giả mạo phần đầu hoặc chứa nhiều cách diễn giải khác nhau. Đối với dữ liệu không tin cậy, phải kiểm tra thêm cấu trúc, giới hạn và chính sách xử lý.

### Kích thước: byte, KB, KiB, MB và MiB

Đơn vị phải rõ ràng:

| Đơn vị | Số byte |
| --- | ---: |
| 1 KB | 1.000 |
| 1 KiB | 1.024 |
| 1 MB | 1.000.000 |
| 1 MiB | 1.048.576 |
| 1 GiB | 1.073.741.824 |

Nếu giới hạn tải lên là **20 MiB**, giá trị giới hạn theo byte là `20 × 1.048.576 = 20.971.520 byte`. Trong schema metadata nên lưu **`size_bytes` dưới dạng số nguyên**, tránh lưu một chuỗi mơ hồ như `"20 MB"`.

Kích thước không nói lên định dạng; một byte stream 8 MiB có thể là PDF, ảnh, video, dữ liệu nén hoặc nội dung ngẫu nhiên. Muốn diễn giải phải có **quy tắc định dạng** và trình đọc phù hợp.

## 3. Metadata: mô tả được gì và không được tin điều gì?

**Metadata** là dữ liệu nói về dữ liệu khác. Với file upload, metadata có thể đến từ:

1. **Client khai báo:** tên file, `Content-Type`, mô tả người dùng nhập.
2. **Server tự đo:** số byte thật nhận được, hàm băm của nội dung, thời gian ghi.
3. **Bộ phân tích định dạng:** kích thước ảnh, số trang PDF, codec, thời lượng video.
4. **Nghiệp vụ quyết định:** chủ sở hữu, đơn hàng, chính sách lưu giữ, quyền truy cập.
5. **Hạ tầng lưu trữ trả về:** object key, version ID, ETag, trạng thái ghi.

Phải ghi nhận **nguồn gốc và độ tin cậy** của từng trường. Đặc biệt:

- `Content-Type: application/pdf` từ HTTP chỉ là **lời khai của client**, không chứng minh dữ liệu thực sự là PDF.
- Tên `invoice.pdf` không quyết định định dạng và tuyệt đối không được dùng trực tiếp làm đường dẫn vật lý.
- `Content-Length` có thể vắng mặt hoặc không đáng tin trong mọi tình huống; giới hạn dung lượng phải được kiểm soát trong khi đọc thực tế.
- Thời gian từ máy người dùng không phải luôn là thời gian lưu trữ; cần định nghĩa trường thời gian do server cấp.
- Metadata trong ảnh (như EXIF) có thể chứa vị trí hoặc thông tin riêng tư; không tự động công khai lại.
- ETag của object storage **không được mặc định xem là MD5 của toàn bộ nội dung**; ý nghĩa phụ thuộc hệ lưu trữ và cách tải lên.

### Bộ metadata tối thiểu thường cần

| Trường | Kiểu/ý nghĩa gợi ý | Nguồn/điểm kiểm tra |
| --- | --- | --- |
| `id` | ID ổn định của tệp ở tầng ứng dụng | Server sinh; không dựa vào tên file |
| `owner_id` hoặc `order_id` | Quan hệ nghiệp vụ | Xác thực, phân quyền và khóa ngoại |
| `object_key` | Khóa định vị nội dung trong kho | Server tạo; không cho client tự chỉ đường dẫn |
| `original_filename` | Tên để hiển thị | Client cung cấp; lọc/escape khi hiển thị |
| `declared_media_type` | MIME do client khai báo | Chỉ dùng như gợi ý ban đầu |
| `detected_media_type` | Loại dữ liệu server kiểm tra | Công cụ kiểm tra/giải mã phù hợp |
| `size_bytes` | Số byte thực tế của nội dung | Server đếm, dùng `BIGINT` |
| `sha256_hex` | Dấu vân tay SHA-256 trên dãy byte đã quy ước | Server tính và kiểm tra |
| `state` | `PENDING`, `READY`, `REJECTED` ... | Máy trạng thái của ứng dụng |
| `created_at`, `ready_at` | Các mốc vòng đời | Server/database cấp |
| `version` | Phiên bản metadata hoặc nội dung theo hợp đồng | Hỗ trợ đồng thời và cập nhật có điều kiện |

Không phải ứng dụng nào cũng cần tất cả các trường, nhưng **tệp đã có payload** và **tệp được phép hiển thị cho người dùng** là hai trạng thái khác nhau. Metadata về `state` giúp biểu diễn khác biệt này.

## 4. Các cách lưu payload lớn

Có ba lựa chọn thường gặp trong Java backend: **cột nhị phân của cơ sở dữ liệu**, **object storage** và **hệ thống tệp**. Một số ứng dụng còn **nhúng dữ liệu vào JSON bằng Base64**, nhưng đây chủ yếu là cách biểu diễn qua giao thức, không phải một kho lưu trữ riêng.

| Tiêu chí | BLOB/BYTEA trong database | Object storage | Tệp trên filesystem |
| --- | --- | --- | --- |
| Nơi đặt payload | Trong hệ quản trị DB | Object theo bucket/key | Tệp theo đường dẫn |
| Metadata và tìm kiếm | Cùng DB; dễ `JOIN`, dùng transaction DB | Thường thêm bảng metadata DB | Thường thêm bảng metadata DB |
| Atomicity với metadata DB | Có thể dùng một transaction DB nếu cùng DB và cơ chế hỗ trợ | Cần workflow phối hợp hai hệ thống | Cần workflow phối hợp DB và filesystem |
| Tải/xử lý tệp rất lớn | Phụ thuộc giới hạn kiểu dữ liệu, driver, tài nguyên DB | Phù hợp cho object lớn, nhiều API upload đa phần | Có thể phù hợp nhưng cần tự quản lý quyền, ổ đĩa và mở rộng |
| Backup, replication | Đi cùng chiến lược DB; có thể làm DB/backups phình to | Chính sách versioning, lifecycle, backup riêng | Backup, chia sẻ và phục hồi do hệ thống quản lý |
| Phân phối tải xuống | Thường đi qua ứng dụng/DB | Có thể phối hợp CDN, URL truy cập có thời hạn | Cần ứng dụng hoặc máy chủ phục vụ file |
| Vận hành | DB gánh thêm I/O và dung lượng lớn | Phụ thuộc dịch vụ/API, cấu hình quyền và consistency | Đơn giản trên một máy, phức tạp khi đa máy/đa vùng |

### Lựa chọn A — lưu trực tiếp trong cơ sở dữ liệu

Có thể khai báo một bảng trong PostgreSQL:

~~~sql
CREATE TABLE file_blobs (
    file_id UUID PRIMARY KEY,
    content BYTEA NOT NULL
);
~~~

Với cách này, dữ liệu nhị phân và metadata đặt trong cùng database có thể được cập nhật trong **cùng giao dịch**. Đây là ưu điểm khi bản ghi và nội dung phải xuất hiện hoặc biến mất cùng nhau.

Tuy nhiên, payload lớn khiến database có thể phải xử lý thêm bộ nhớ, I/O, replication và backup. Giới hạn mỗi kiểu dữ liệu cũng khác nhau theo engine; không nên mặc định mọi database có thể xử lý tệp nhiều gigabyte trong một cột.

**Không dùng `SELECT *` cho các danh sách metadata** nếu cột payload lớn không cần thiết. Thay vào đó, chỉ truy vấn các trường dùng để hiển thị; API tải xuống mới đọc nội dung.

### Lựa chọn B — object storage

Object storage giữ payload dưới **object key**, có thể kèm một tập metadata theo API riêng. Ví dụ khóa nội bộ:

~~~text
bucket: business-documents
key: invoices/2026/11/9d8f...-random-id
~~~

Hệ thống có thể lưu trong DB:

~~~text
file.id = 4d0e...
file.order_id = 42
file.object_key = "invoices/2026/11/9d8f...-random-id"
file.state = "READY"
~~~

Ứng dụng đọc metadata từ DB để xác định quyền và vị trí, sau đó gọi object storage lấy byte.

**Lợi ích thường gặp:** phù hợp payload lớn, có API streaming/multipart, chính sách lifecycle, khả năng phục vụ tải xuống qua hạ tầng chuyên biệt. **Giới hạn:** một transaction SQL thường **không bao trùm** thao tác PUT/DELETE bên object store; cần giải quyết lỗi một phía thành công, một phía thất bại.

Object key là **định danh nội bộ**, không nên được xem như cơ chế phân quyền. Client không được tự tải object chỉ vì đoán hoặc biết key, trừ khi một cơ chế truy cập hợp lệ đã được cấp.

### Lựa chọn C — lưu trên filesystem

Ứng dụng có thể ghi byte xuống đường dẫn do server cấp, ví dụ:

~~~text
/data/uploads/9d/8f/9d8f...bin
~~~

Cách này có thể đơn giản với dịch vụ một máy hoặc thiết bị nội bộ. Khi triển khai nhiều replica/pod, việc một máy lưu tệp **không đảm bảo** máy khác đọc được. Cần shared storage, replication hoặc chuyển sang hệ lưu trữ thích hợp. Ngoài ra, phải tự thiết kế khóa, atomic rename, đồng bộ đĩa, backup, phân quyền hệ tệp và dọn tệp mồ côi.

## 5. Không nhầm byte, Base64 và JSON

Các API thường dùng JSON. JSON là định dạng văn bản nên không chứa byte nhị phân tùy ý trực tiếp. Một cách nhúng là **Base64**:

~~~json
{
  "filename": "example.bin",
  "mediaType": "application/octet-stream",
  "contentBase64": "AQIDBA=="
}
~~~

Ở đây `AQIDBA==` giải mã thành bốn byte hex `01 02 03 04`. Base64 **không mã hóa bảo mật**, không kiểm tra nội dung hợp lệ và không làm dữ liệu bền vững.

Với `n` byte đầu vào, chuỗi Base64 chuẩn không ngắt dòng có độ dài `4 × ceil(n / 3)` ký tự ASCII (chưa tính phần vỏ JSON). Với tệp lớn, mức tăng dung lượng tiệm cận **khoảng 33%** trước khi xét nén và chi phí của runtime.

Ví dụ payload **3 MiB** có **4 MiB ký tự Base64** trước khi thêm các trường JSON. Nếu ứng dụng vừa giữ byte gốc, chuỗi Base64 và đối tượng JSON trong RAM, mức dùng bộ nhớ có thể tăng đáng kể.

Với upload/download lớn, nên cân nhắc:

- Gửi dữ liệu nhị phân qua request body (`application/octet-stream`), hoặc upload multipart theo hợp đồng API.
- Truyền metadata như các trường/form part riêng hoặc trong một bước API riêng.
- Trả metadata bằng JSON, còn endpoint tải xuống trả luồng byte.
- Dùng streaming hoặc direct-to-object-storage với quyền và giới hạn rõ ràng nếu hệ thống yêu cầu.

Một tệp **có thể lưu trong database** ở dạng byte nhưng **được vận chuyển qua HTTP** dưới dạng nhị phân trực tiếp. Đừng nhầm cách truyền với nơi lưu.

## 6. Thiết kế schema metadata và ràng buộc

Ví dụ schema PostgreSQL lưu metadata, còn payload nằm trong object storage hoặc filesystem:

~~~sql
CREATE TABLE stored_files (
    id UUID PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    order_id BIGINT,
    object_key VARCHAR(512) NOT NULL UNIQUE,
    original_filename VARCHAR(255) NOT NULL,
    declared_media_type VARCHAR(255),
    detected_media_type VARCHAR(255),
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    sha256_hex CHAR(64),
    storage_state VARCHAR(16) NOT NULL
        CHECK (storage_state IN ('PENDING', 'READY', 'REJECTED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ready_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 0
);
~~~

Đây là schema minh họa, chưa thay thế hệ thống định danh người dùng, kiểm tra quyền và quản lý object version. Trong triển khai thật, nên thêm **khóa ngoại** cho các bảng nghiệp vụ có liên quan, đồng thời xem xét quy tắc giữa `storage_state`, `ready_at` và `sha256_hex`.

Ví dụ truy vấn **metadata đã sẵn sàng** theo chủ sở hữu:

~~~sql
SELECT id, original_filename, detected_media_type,
       size_bytes, created_at
FROM stored_files
WHERE owner_id = 1001
  AND storage_state = 'READY'
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Chỉ mục gợi ý khi dạng truy vấn này xuất hiện thường xuyên:

~~~sql
CREATE INDEX idx_stored_files_owner_state_created
ON stored_files (owner_id, storage_state, created_at DESC, id DESC);
~~~

Chỉ mục được chọn theo **đường truy cập thật**, không mặc định mỗi metadata đều cần index. Tên file thường chỉ dành cho hiển thị; nếu tìm kiếm theo tên, cần xác định quy tắc chuẩn hóa, collation và cách tìm kiếm phù hợp. Dữ liệu payload không nên bị kéo vào mọi truy vấn danh sách.

### Định danh và vị trí lưu không phải một

- `id` là định danh ổn định trong nghiệp vụ hoặc API.
- `object_key` là vị trí tham chiếu tới byte, có thể thay đổi khi chuyển kho hoặc bố trí lại dữ liệu.
- `original_filename` là tên do người dùng cung cấp, có thể trùng và chứa ký tự không an toàn.
- `sha256_hex` là dấu vân tay của nội dung; **không tự động là ID nghiệp vụ**.

Sử dụng nội dung hash làm khóa có thể giúp chống trùng lặp, nhưng hai tệp có cùng byte vẫn có thể khác chủ sở hữu, quyền, thời hạn lưu và ngữ cảnh pháp lý. Không suy ra hai bản ghi nghiệp vụ là một chỉ vì hash giống nhau.

## 7. Luồng upload hoàn chỉnh: từ byte đến trạng thái READY

Một luồng upload tách biệt payload và metadata có thể như sau:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Java API
    participant D as Metadata DB
    participant O as Blob/Object Store
    C->>A: Gửi upload + thông tin nghiệp vụ
    A->>A: Xác thực, kiểm quyền, kiểm giới hạn
    A->>D: Tạo metadata PENDING / request ID
    A->>O: Stream byte vào vùng tạm hoặc object staging
    O-->>A: Xác nhận ghi payload
    A->>A: Kiểm số byte, hash, loại tệp, quét theo chính sách
    alt Hợp lệ và payload khả dụng
        A->>D: Cập nhật metadata READY + vị trí + hash
        D-->>A: Xác nhận giao dịch DB
        A-->>C: Trả file ID và trạng thái READY
    else Lỗi hoặc bị từ chối
        A->>D: Ghi trạng thái lỗi / REJECTED
        A->>O: Dọn payload tạm theo chính sách
        A-->>C: Trả kết quả lỗi phù hợp
    end
~~~

Các bước cụ thể phụ thuộc hệ thống. Nếu file cần được quét bất đồng bộ, API có thể trả trạng thái **PENDING** và công bố **READY** khi xử lý hoàn tất. Trạng thái READY chỉ nên được công bố khi các điều kiện bắt buộc đã được đáp ứng, ví dụ byte có thể đọc, hash hợp lệ, chính sách bảo mật đạt và metadata đã commit.

### Vì sao cần trạng thái PENDING?

Giả sử:

1. Java đã tạo bản ghi metadata trỏ tới `object_key`.
2. Upload bị ngắt trước khi payload được ghi xong.
3. Một request khác thấy metadata và yêu cầu tải xuống.

Nếu không có trạng thái, API có thể trả file rỗng, file thiếu hoặc lỗi khó hiểu. `PENDING` giúp phân biệt **đang chuẩn bị** với **có thể phục vụ tải xuống**.

Một luồng khác cũng hợp lệ là **ghi object tạm trước**, xác minh xong mới tạo metadata READY. Khi đó phải có cách tìm và dọn object tạm không có bản ghi DB. Chọn thứ tự theo yêu cầu idempotency, cách phục hồi và API hệ lưu trữ.

## 8. Streaming: xử lý payload lớn mà không giữ toàn bộ trong RAM

Cách xử lý ngây thơ:

~~~java
byte[] all = inputStream.readAllBytes();
store(all);
~~~

Có thể phù hợp với dữ liệu nhỏ có giới hạn chặt chẽ, nhưng với upload nhiều gigabyte hoặc nhiều yêu cầu đồng thời, `readAllBytes()` làm bộ nhớ tiêu thụ theo kích thước nội dung. Nếu 20 request cùng đọc tệp 100 MiB vào RAM thì riêng byte payload có thể chiếm khoảng **2.000 MiB**, chưa kể bộ đệm, đối tượng, framework và GC.

**Streaming** xử lý dần từng khối byte thay vì giữ toàn bộ payload cùng lúc:

~~~text
Client -> InputStream -> bộ đệm 64 KiB -> OutputStream -> kho lưu trữ
                              |
                              +--> cập nhật số byte và SHA-256
~~~

Với độ lớn buffer cố định, **bộ nhớ tại tầng copy này** gần như không phụ thuộc dung lượng file; tuy nhiên middleware HTTP, JDBC driver hoặc SDK lưu trữ có thể tự buffer thêm, nên cần đo và kiểm tra toàn bộ pipeline.

### Ví dụ Java: lưu tệp theo luồng, kiểm kích thước và SHA-256

Mã minh họa dùng Java 17+, ghi vào một thư mục do **server kiểm soát**, đặt tên file bằng UUID, giới hạn số byte thật, tạo SHA-256 trong khi đọc và chỉ công bố file sau khi ghi xong.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;

public final class BinaryFileStore {
    private BinaryFileStore() {}

    public record StoredFile(
        String objectKey,
        long sizeBytes,
        String sha256Hex
    ) {}

    public static StoredFile store(
        InputStream source,
        Path serverControlledRoot,
        long maxBytes
    ) throws IOException {
        if (source == null || maxBytes <= 0) {
            throw new IllegalArgumentException("Nguồn hoặc giới hạn không hợp lệ");
        }

        MessageDigest sha256;
        try {
            sha256 = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException impossibleOnNormalJdk) {
            throw new IllegalStateException("Thiếu SHA-256", impossibleOnNormalJdk);
        }

        Files.createDirectories(serverControlledRoot);
        Path temporary = Files.createTempFile(
            serverControlledRoot, ".upload-", ".part");

        boolean moved = false;
        try {
            byte[] buffer = new byte[64 * 1024];
            long total = 0;

            try (OutputStream output = Files.newOutputStream(
                    temporary,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                int count;
                while ((count = source.read(buffer)) != -1) {
                    if (count == 0) {
                        continue;
                    }
                    // Kiểm tra trước phép cộng để tránh overflow.
                    if (count > maxBytes - total) {
                        throw new IOException("Tệp vượt giới hạn cho phép");
                    }

                    output.write(buffer, 0, count);
                    sha256.update(buffer, 0, count);
                    total += count;
                }
            }

            String key = UUID.randomUUID().toString() + ".bin";
            Path target = serverControlledRoot.resolve(key);

            // Fail nếu provider không hỗ trợ atomic move.
            // Cần xử lý xung đột tên nếu đích đã tồn tại.
            Files.move(
                temporary,
                target,
                StandardCopyOption.ATOMIC_MOVE
            );
            moved = true;

            return new StoredFile(
                key,
                total,
                HexFormat.of().formatHex(sha256.digest())
            );
        } finally {
            if (!moved) {
                Files.deleteIfExists(temporary);
            }
        }
    }
}
~~~

Cách gọi, với `source` đến từ tầng HTTP và được tầng gọi chịu trách nhiệm đóng:

~~~java
long maxBytes = 20L * 1024 * 1024;
BinaryFileStore.StoredFile result =
    BinaryFileStore.store(source, uploadRoot, maxBytes);

System.out.println(result.objectKey());
System.out.println(result.sizeBytes());
System.out.println(result.sha256Hex());
~~~

**Các giới hạn của ví dụ phải hiểu rõ:**

1. Mã xử lý **bước ghi payload**; chưa lưu metadata DB, chưa kiểm tra quyền, không xác định MIME type và chưa quét nội dung độc hại.
2. `source` thuộc vòng đời của tầng gọi. Không sử dụng đường dẫn hoặc tên file do client cung cấp làm `serverControlledRoot` hoặc `objectKey`.
3. Tệp tạm được tạo bằng `Files.createTempFile` và atomic move (nếu được filesystem hỗ trợ) giúp giảm khả năng xuất hiện file cuối với nội dung chưa hoàn tất. **Atomic move không đồng nghĩa bền vững trước mất điện**; cần cơ chế `fsync`/force và đồng bộ metadata thư mục phù hợp với hệ điều hành/filesystem, cộng với backup/khôi phục nếu nghiệp vụ yêu cầu.
4. Ví dụ chọn **thất bại nếu atomic move không được hỗ trợ**, không tự động chuyển sang một thao tác kém bảo đảm hơn. Với hệ phân tán/object storage, cách publish object sẽ khác.
5. SHA-256 được tính trên **dãy byte upload gốc**. Nếu sau này nén, mã hóa hoặc chuyển đổi định dạng, phải chỉ rõ hash áp dụng cho phiên bản dữ liệu nào.
6. UUID ngẫu nhiên giảm nguy cơ trùng tên, nhưng không thay cho kiểm soát quyền, kiểm tra xung đột tên đích hoặc chính sách chống trùng request. Khi yêu cầu chống trùng tuyệt đối, cần ràng buộc định danh và xử lý xung đột; không dựa riêng vào hành vi thay thế đích của `ATOMIC_MOVE` vì nó phụ thuộc provider.
7. Tài nguyên mạng và độ trễ upload còn phụ thuộc timeout, backpressure và tốc độ phía client. Mã không tuyên bố dung lượng bộ nhớ của toàn bộ ứng dụng luôn cố định.

Nếu dùng Spring MVC, Jakarta Servlet hoặc framework khác, hãy kiểm tra giới hạn upload và chính sách buffering của framework trước khi áp dụng cách xử lý streaming.

## 9. Khi payload nằm trong database: JDBC và luồng nhị phân

JDBC có thể thao tác với nội dung nhị phân bằng `PreparedStatement.setBinaryStream()` hoặc `ResultSet.getBinaryStream()`. Ví dụ dùng bảng PostgreSQL `file_blobs` ở phần trước:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.util.UUID;
import javax.sql.DataSource;

// validatedFile là file đã được lưu tạm và kiểm tra.
void insertBlob(
    DataSource dataSource,
    UUID fileId,
    Path validatedFile
) throws Exception {
    long knownSize = Files.size(validatedFile);
    String sql = "INSERT INTO file_blobs (file_id, content) VALUES (?, ?)";

    try (InputStream source = Files.newInputStream(validatedFile);
         Connection connection = dataSource.getConnection();
         PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setObject(1, fileId);
        statement.setBinaryStream(2, source, knownSize);
        statement.executeUpdate();
    }
}
~~~

Ví dụ chỉ minh họa cách truyền luồng vào DB. Việc xác nhận transaction phụ thuộc `autoCommit` hoặc transaction manager; nếu phải ghi metadata cùng lúc, cần bố trí trong cùng transaction và kiểm tra rollback.

**Lưu ý:** API tên `setBinaryStream` không đảm bảo driver database sẽ không buffer toàn bộ dữ liệu ở bất cứ giai đoạn nào. Cần kiểm tra khả năng streaming và giới hạn của driver, engine, kết nối và cấu hình được sử dụng.

Khi đọc, cũng có thể dùng `getBinaryStream()` để truyền byte về response theo từng khối, thay vì tải hết blob vào một `byte[]`. Lưu ý phải giữ `ResultSet`, statement và connection còn hiệu lực trong suốt quá trình đọc; không trả một `InputStream` gắn với kết nối đã đóng rồi mới cố đọc ở tầng HTTP.

### Tránh kéo theo payload qua ORM không chủ ý

Một entity chứa trường `@Lob byte[] content` có thể khiến việc tải entity sử dụng nhiều bộ nhớ hoặc phát sinh SQL ngoài dự kiến. Chiến lược fetch thực tế phụ thuộc JPA provider và bytecode enhancement; không nên giả định annotation `LAZY` luôn bảo đảm payload không được tải.

Khi ứng dụng cần liệt kê file, hãy dùng **projection/DTO metadata** và chỉ truy xuất nội dung tại endpoint download. ORM không làm biến mất chi phí I/O, kết nối, locking hoặc việc lưu blob.

## 10. Chunking, multipart upload và đọc theo khoảng byte

Với payload lớn, một request liền mạch có thể bị gián đoạn bởi mất mạng hoặc timeout. **Chia khối (chunking)** nghĩa là chia byte thành các phần nhỏ có đánh số hoặc có offset để vận chuyển, ghi và kiểm tra.

Ví dụ tệp **1 GiB** chia thành khối **8 MiB** sẽ có:

`1 GiB / 8 MiB = 128 phần.`

~~~text
Tệp gốc: [ chunk 0 ][ chunk 1 ][ chunk 2 ] ... [ chunk 127 ]
          0..8MiB   8..16MiB  16..24MiB          ...
~~~

Metadata cho một upload session có thể bao gồm:

- `upload_id` và quyền sở hữu session.
- `expected_total_size` và kích thước/chỉ số từng phần.
- Danh sách phần đã nhận, offset/part number, checksum của từng phần nếu áp dụng.
- Trạng thái `INITIATED`, `UPLOADING`, `ASSEMBLING`, `READY` hoặc `ABORTED`.
- Thời hạn session và quy tắc dọn phần upload chưa hoàn thành.

**Điểm cần thiết kế chính xác:**

1. Phần upload phải có **định danh và thứ tự rõ ràng**; nhận phần 3 hai lần phải được xử lý theo quy tắc retry, không vô tình nối đôi.
2. Kiểm tra tổng byte, số phần, hash toàn bộ và độ nguyên vẹn trước khi công bố file.
3. Với parallel upload, thứ tự **nhận** có thể khác thứ tự **nối nội dung**; không dùng timestamp mạng để đoán.
4. Nếu client ngắt giữa chừng, hệ thống cần TTL và cleanup để tránh tích lũy dữ liệu không bao giờ hoàn tất.
5. Chính sách multipart của mỗi object store có thể có giới hạn kích thước phần và số phần; phải kiểm tra tài liệu của nhà cung cấp đang dùng.

**Đọc theo khoảng byte (range read)** là một khái niệm khác: client chỉ yêu cầu một đoạn của object, ví dụ phục vụ tua video hoặc tiếp tục tải xuống. API HTTP có cơ chế `Range` và response `206 Partial Content` khi server hỗ trợ. Không nên suy ra “upload theo phần” tự động đồng nghĩa download theo range được hỗ trợ.

Đối với video lớn, tệp lưu theo object storage và cache/CDN có hỗ trợ range thường giúp tránh truyền toàn bộ payload mỗi lần người dùng chỉ xem một đoạn. Với tệp nhỏ hoặc không cần truy cập từng đoạn, thêm cơ chế chunking phức tạp có thể không mang lại lợi ích.

## 11. Hash, checksum và tính toàn vẹn

Khi upload, ứng dụng thường cần biết “byte đã lưu có đúng như byte đã nhận hay không?”. Cách phổ biến là tính dấu vân tay:

~~~text
SHA-256(payload byte) -> 256 bit -> 64 ký tự hex
~~~

Ví dụ Java đọc theo khối và cập nhật hash:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
byte[] buffer = new byte[64 * 1024];

int n;
while ((n = source.read(buffer)) != -1) {
    if (n > 0) {
        digest.update(buffer, 0, n);
        // Đồng thời xử lý/ghi n byte nếu cần.
    }
}

String sha256Hex = HexFormat.of().formatHex(digest.digest());
~~~

Mã này cần import `MessageDigest`, `HexFormat` và xử lý `NoSuchAlgorithmException` theo môi trường ứng dụng. Nếu đã dùng `BinaryFileStore` ở trên thì không cần băm lần thứ hai trong cùng luồng upload.

Các khái niệm dễ nhầm:

| Khái niệm | Mục tiêu | Giới hạn |
| --- | --- | --- |
| **Checksum** | Phát hiện nhiều loại sai hỏng dữ liệu vô tình | Không tự bảo vệ trước kẻ tấn công có thể sửa cả nội dung và checksum |
| **Cryptographic hash (SHA-256)** | Dấu vân tay mạnh để so sánh byte và phát hiện thay đổi | Không tự xác nhận ai tạo dữ liệu hoặc dữ liệu có an toàn |
| **HMAC** | Kiểm tra toàn vẹn và nguồn theo khóa bí mật dùng chung | Cần quản lý khóa và giao thức xác thực |
| **Chữ ký số** | Xác minh nguồn ký và toàn vẹn theo cơ chế khóa công khai | Phụ thuộc tin cậy khóa, chứng thư và chính sách xác minh |
| **Encryption** | Bảo vệ tính bí mật, có thể kèm xác thực khi dùng AEAD | Không tự quyết định quyền truy cập ở tầng ứng dụng |

Lưu hash trong metadata hữu ích khi kiểm tra tải xuống hoặc phục hồi backup. Tuy nhiên, khi dữ liệu nhạy cảm, **dùng hash nội dung làm khóa công khai hoặc dấu hiệu chống trùng** có thể làm lộ sự trùng khớp giữa những người dùng khác nhau. Cần đánh giá mô hình đe dọa trước khi thiết kế deduplication xuyên tài khoản.

**Băm trên byte nào?** Nếu ảnh được nén lại hoặc PDF được chuyển đổi, file sau xử lý có hash khác file người dùng gửi. Nên lưu metadata tách biệt cho **bản gốc**, **bản đã biến đổi** và **thumbnail**, mỗi bản có kích thước, loại, hash và vòng đời riêng khi cần.

## 12. Tính nhất quán giữa metadata DB và object storage

Một database transaction không thể mặc nhiên làm cho hai hệ thống độc lập cùng commit nguyên tử. Ví dụ:

- Upload object thành công, nhưng câu `INSERT` metadata vào database thất bại: xuất hiện **object mồ côi**.
- Metadata DB commit thành công, nhưng PUT object thất bại: xuất hiện **tham chiếu tới payload không tồn tại**.
- Delete DB thành công, nhưng DELETE object thất bại: dữ liệu có thể tiếp tục tồn tại ở kho dù API không còn nhìn thấy.
- API mất kết nối sau PUT/COMMIT: client không chắc thao tác hoàn tất hay chưa và có thể gửi lại.

Một chiến lược thực tế là **quản lý trạng thái và đối soát**:

1. Gắn `upload_id` hoặc **idempotency key** cho yêu cầu.
2. Tạo bản ghi `PENDING`, không cho tải xuống như file sẵn sàng.
3. Đưa nội dung lên object key tạm; đo kích thước và hash, xác minh hoàn tất upload.
4. Xử lý kiểm tra định dạng và bảo mật theo chính sách.
5. Đưa object vào vị trí sẵn sàng nếu cần, rồi commit metadata `READY` trong DB.
6. Có job định kỳ tìm `PENDING` quá hạn và object không được tham chiếu; xử lý theo trạng thái và chính sách lưu giữ.
7. Khi retry cùng idempotency key, tra trạng thái đã có trước khi tạo hiệu ứng mới.

Bước 5 vẫn có thể gặp lỗi một phía, nên cơ chế **reconciliation** phải tiếp tục kiểm tra và sửa trạng thái. Không nên hứa “exactly once” chỉ vì có một API upload; cần thiết kế idempotency và quản lý các kết quả không chắc chắn.

### Xóa và thay phiên bản an toàn

Xóa logic thường bắt đầu bằng việc **ngừng cho truy cập** trong metadata. Xóa vật lý có thể thực hiện sau qua worker/job, dựa trên retention và quyền xóa. Với kho hỗ trợ versioning, DELETE có thể chỉ tạo *delete marker* trong khi phiên bản cũ vẫn còn; yêu cầu xóa hoàn toàn phải xét chính sách version/lifecycle/backup.

Khi thay thế nội dung đang được dùng:

- Có thể tạo **object key phiên bản mới**, kiểm tra xong rồi thay tham chiếu metadata.
- Dùng **optimistic locking** với `version` của metadata khi nhiều yêu cầu cùng cập nhật.
- Không xóa phiên bản cũ trước khi chắc chắn phiên bản mới hợp lệ nếu nghiệp vụ cần khả năng rollback.
- Nếu dùng cache/CDN, cần quy tắc vô hiệu hóa hoặc URL theo phiên bản để tránh phục vụ nội dung cũ.

## 13. Bảo mật tệp và metadata

Binary upload là điểm tiếp nhận **dữ liệu không tin cậy**. Bên cạnh xác thực và phân quyền, cần xác định chính sách cho từng loại file:

**Xác thực và quyền truy cập.** Mỗi thao tác upload, xem metadata, tải xuống, thay thế và xóa phải kiểm tra quyền theo chủ sở hữu/đơn hàng. Không dựa vào việc object key khó đoán để coi nội dung là riêng tư.

**Tên file an toàn.** Tên gốc có thể chứa `../`, dấu phân cách đường dẫn, ký tự điều khiển hoặc chuỗi gây lỗi hiển thị. Hãy lưu như dữ liệu hiển thị sau khi chuẩn hóa/giới hạn; **không dùng trực tiếp làm đường dẫn**, tên object hoặc nội dung HTML không escape.

**Loại file đáng tin.** Kiểm tra hơn một chỉ dấu: MIME do client khai báo, dấu hiệu định dạng, parser phù hợp và chính sách allowlist. Parser phải được cập nhật và có giới hạn tài nguyên vì tệp hỏng hoặc tệp khai thác lỗi có thể gây rủi ro.

**Giới hạn kích thước và tài nguyên.** Không chỉ tin `Content-Length`. Giới hạn số byte trong lúc stream, giới hạn giải nén/giải mã ảnh, số trang, pixel hoặc thời gian xử lý. Tệp nén nhỏ có thể bung ra lượng dữ liệu rất lớn (*decompression bomb*).

**Quét mã độc và xử lý nội dung hoạt động.** Nếu nghiệp vụ yêu cầu, quét trước khi `READY`; tệp HTML/SVG/PDF hoặc văn bản có thể mang nội dung hoạt động trên client. Tùy ngữ cảnh, phục vụ với `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, đúng `Content-Type` và origin phù hợp; không mặc định hiển thị inline mọi file người dùng gửi.

**Dữ liệu nhạy cảm trong metadata.** Tên file, EXIF, thời gian tạo, vị trí hoặc mô tả có thể tiết lộ thông tin cá nhân. Chỉ lưu và công khai trường cần thiết. Bảo vệ cả metadata và payload bằng quyền truy cập, TLS, mã hóa lưu trữ và quản lý khóa thích hợp.

**URL được ký có thời hạn.** Với object storage, ứng dụng có thể cấp URL truy cập giới hạn thời gian sau khi kiểm tra quyền. URL là một dạng quyền truy cập tạm; không ghi công khai vào log, không dùng TTL quá rộng và phải cân nhắc khả năng thu hồi theo nhà cung cấp.

**Integrity không đồng nghĩa antivirus.** SHA-256 đúng chỉ chứng minh dãy byte khớp với giá trị đã băm theo giả định tin cậy, không chứng minh file vô hại.

## 14. Hiệu năng và tối ưu thiết kế

Payload lớn tạo áp lực khác với metadata nhỏ. Ví dụ **10.000 tệp, mỗi tệp 20 MB**, có tổng payload khoảng **200 GB** trước khi tính replication, versioning, metadata, backup và chi phí khác.

### Bộ nhớ và kết nối Java

- Tránh nạp toàn bộ file vào `byte[]` khi không cần.
- Kiểm tra buffering của HTTP server/framework, servlet multipart parser, JDBC driver và object storage SDK.
- Dùng streaming và backpressure; đặt giới hạn request đồng thời để tránh hết RAM, file descriptor hoặc kết nối.
- Phân biệt timeout của đường truyền upload kéo dài với timeout cho truy vấn metadata ngắn.
- Theo dõi số upload đồng thời và thời gian giữ connection DB. Không nên giữ transaction DB mở trong toàn bộ thời gian client tải lên chậm nếu thiết kế cho phép tách bước.

### Chi phí database

- Truy vấn danh sách chỉ lấy metadata; không đọc BLOB.
- Đánh index trên các điều kiện thực tế: owner, order, state, created_at.
- Cân nhắc việc BLOB rất lớn trong DB làm tăng dung lượng dữ liệu, WAL, replication, thời gian backup và restore.
- Đo thời gian đọc/ghi với file nhiều kích thước; không chỉ benchmark một file rất nhỏ.
- Nếu metadata thường xuyên cập nhật, tránh lặp lại ghi nội dung lớn khi chỉ đổi tên hiển thị.

### Khả năng truy cập và băng thông

- Tối ưu **download** bằng streaming và hỗ trợ range nếu người dùng cần tua video hoặc tiếp tục tải.
- CDN/cache phù hợp với nội dung ít thay đổi và quyền truy cập cho phép; cần cơ chế vô hiệu hóa khi thay file hoặc thu hồi quyền.
- Hầu hết JPEG, MP4 và nhiều PDF đã có nén; nén thêm có thể ít hiệu quả, tốn CPU và làm khó hỗ trợ range.
- Dùng nhiều phiên bản dẫn xuất như thumbnail cho danh sách ảnh, thay vì tải ảnh gốc nhiều megabyte chỉ để hiển thị biểu tượng nhỏ.

### Dung lượng và vòng đời

Xác định ngay từ đầu:

| Yêu cầu | Câu hỏi thiết kế |
| --- | --- |
| Tăng trưởng | Mỗi ngày bao nhiêu file và bao nhiêu GiB được thêm? |
| Retention | File và phiên bản cũ phải giữ bao lâu? |
| Backup/restore | Cần phục hồi đồng bộ giữa metadata và payload ở mốc nào? |
| Chống trùng lặp | Có được chia sẻ byte giữa các chủ sở hữu không, và ai được xóa? |
| Di chuyển dữ liệu | Có thể đổi bucket/key mà giữ `id` và API ổn định không? |
| Truy vết | Cần audit ai tải xuống, ai thay file, ai xóa? |
| Chi phí | Chi phí dung lượng, request, egress, xử lý nền và restore là bao nhiêu? |

## 15. Kiểm thử và quan sát vận hành

Một thiết kế binary storage nên được kiểm thử cả **nội dung**, **metadata**, **lỗi giữa các bước** và **truy cập trái phép**.

Các kiểm thử đáng giá:

1. **Round trip byte:** upload tệp, tải xuống, so sánh SHA-256 và số byte thực tế; thử tệp rỗng nếu chính sách cho phép, tệp sát ngưỡng và vượt ngưỡng.
2. **Không tin metadata client:** đưa tên tệp có dấu phân cách đường dẫn, `Content-Type` giả và `Content-Length` không khớp để kiểm tra giới hạn ở server.
3. **Lỗi khi upload:** cắt kết nối giữa chừng, hết dung lượng, object store timeout; kiểm tra không có file READY với payload thiếu.
4. **Lỗi giao dịch metadata:** object đã ghi nhưng DB commit lỗi; kiểm tra cơ chế dọn object mồ côi và retry.
5. **Trùng request:** gửi lại cùng `upload_id`/idempotency key, xác nhận không tạo đối tượng nghiệp vụ ngoài ý muốn.
6. **Truy cập:** user khác không được tải hoặc xem metadata nếu không có quyền; URL tạm hết hạn theo chính sách.
7. **Đọc theo range:** kiểm tra offset, độ dài, lỗi phạm vi không hợp lệ và tính nhất quán khi object đổi phiên bản.
8. **Phục hồi:** khôi phục metadata DB và payload từ bản sao lưu, đối chiếu tham chiếu và hash theo tập mẫu phù hợp.

Về metrics, nên có:

| Nhóm chỉ số | Ví dụ |
| --- | --- |
| Upload | Số upload thành công/thất bại, byte/giây, p95/p99 thời gian upload |
| Validation | Số file quá giới hạn, sai định dạng, bị từ chối do chính sách |
| Trạng thái | Số `PENDING` quá hạn, `READY`, `REJECTED`, đối tượng mồ côi |
| Truy cập | Số download, latency, băng thông, lỗi truy cập |
| Kho lưu | Dung lượng theo loại và tenant, request lỗi, retry, giới hạn quota |
| Tính toàn vẹn | Số mismatch checksum/hash, lỗi đọc payload, lỗi khôi phục |

Không đưa **tên file, token URL có chữ ký, dữ liệu khách hàng hoặc object key nhạy cảm** vào nhãn metrics có cardinality cao hoặc log công khai. Dùng ID phục vụ truy vết theo chính sách riêng tư, và tách quyền vận hành khỏi quyền đọc nội dung.

## 16. Những nhầm lẫn thường gặp

**“BLOB là một định dạng tệp như PNG hoặc PDF.”** Không. BLOB mô tả giá trị nhị phân lớn; các byte của nó có thể thuộc nhiều định dạng khác nhau.

**“Có metadata MIME là biết chắc file hợp lệ.”** Không. MIME có thể do client khai báo, phải kiểm tra và xử lý dữ liệu không tin cậy.

**“Base64 giúp dữ liệu nhỏ hơn và bảo mật hơn.”** Sai. Base64 thường làm dữ liệu lớn hơn và không phải cơ chế mã hóa bảo mật.

**“Đã dùng `InputStream` thì chắc chắn không tốn nhiều RAM.”** Chưa chắc. Framework, driver hoặc SDK có thể buffer; cần kiểm chứng đường dữ liệu thực tế.

**“Hash SHA-256 chứng minh file sạch virus.”** Sai. Hash hỗ trợ xác định tính đồng nhất của byte, không đánh giá nội dung an toàn.

**“Lưu object thành công thì metadata DB cũng tự commit.”** Sai. Hai hệ lưu trữ độc lập cần quy trình phối hợp và đối soát.

**“Lưu toàn bộ payload vào một entity sẽ luôn đơn giản và nhanh.”** Không. Có nguy cơ tải byte không cần thiết, tăng I/O và memory, ảnh hưởng query list và backup.

**“Object key UUID là đủ để phân quyền tải xuống.”** Sai. API phải kiểm tra quyền, và hệ object storage phải có chính sách truy cập phù hợp.

**“Xóa bản ghi metadata là byte đã biến mất vĩnh viễn.”** Không nhất thiết. Có thể còn phiên bản, bản sao, cache, backup hoặc object mồ côi.

**“ETag luôn là MD5.”** Sai. Không được dùng ETag như checksum nội dung nếu hợp đồng của hệ lưu trữ không bảo đảm như vậy.

## 17. Câu hỏi tự kiểm tra và bài tập

**Câu 1.** Hai người dùng tải lên các file PDF có byte giống hệt nhau nhưng quyền truy cập khác nhau. Có nên gộp thành một bản ghi nghiệp vụ chỉ vì `sha256_hex` trùng không?

**Đáp án:** Không. Hash có thể được dùng để cân nhắc lưu chung payload, nhưng quyền, chủ sở hữu, metadata và chính sách xóa vẫn là các đối tượng nghiệp vụ riêng. Chia sẻ payload còn cần thiết kế vòng đời, tham chiếu và an toàn thông tin.

**Câu 2.** Một API nhận JSON chứa chuỗi Base64 của video 500 MiB. Rủi ro nào cần xem xét?

**Đáp án:** Payload tăng kích thước đáng kể và có nguy cơ bị buffer nhiều bản sao trong RAM. Nên xem xét upload nhị phân streaming/multipart hoặc direct upload có kiểm soát, kiểm giới hạn byte thực tế và phân biệt upload hoàn tất với trạng thái READY.

**Câu 3.** Database có bản ghi metadata `READY`, nhưng object store trả 404. Hệ thống nên làm gì?

**Đáp án:** Không tự trả tệp rỗng như thành công. Cần báo lỗi thích hợp, ghi nhận sự cố, đối soát metadata với kho lưu, phân tích retry/replication/version và khôi phục hoặc đánh dấu trạng thái tương ứng theo chính sách.

**Câu 4.** Một client gửi tệp tên `../../admin.pdf` với `Content-Type: application/pdf`. Hai trường này có thể được tin để quyết định đường dẫn và tính hợp lệ không?

**Đáp án:** Không. Server phải tự sinh đường dẫn/object key, kiểm soát tên chỉ dùng hiển thị, kiểm tra định dạng và giới hạn upload theo chính sách.

**Câu 5.** Tại sao cùng một file nên lưu `size_bytes`, `sha256_hex` và `detected_media_type` trong metadata?

**Đáp án:** Ba trường phục vụ mục đích khác nhau: kiểm soát dung lượng, xác minh tính đồng nhất byte và xác định định dạng xử lý. Không trường nào tự thay thế trường còn lại hoặc xác nhận toàn bộ nội dung an toàn.

**Câu 6.** Vì sao dùng object storage có thể cần trạng thái `PENDING` dù đã có transaction trên bảng SQL?

**Đáp án:** Transaction SQL không tự bao phủ việc ghi byte lên object store. `PENDING` ngăn hệ thống công bố file như đã sẵn sàng trước khi payload thực sự hoàn tất và được xác minh.

**Bài tập A — thiết kế metadata:** Viết schema cho bảng file đính kèm đơn hàng với `id`, `order_id`, `owner_id`, `object_key`, `size_bytes`, `sha256_hex`, `media_type`, `state` và mốc thời gian. Đề xuất khóa, ràng buộc và index cho truy vấn “20 tệp READY mới nhất của một đơn hàng”.

**Bài tập B — kiểm thử upload:** Thiết kế các trường hợp upload 0 byte, 19 MiB, 20 MiB, 21 MiB khi giới hạn là 20 MiB. Thử cắt mạng tại 50%, dùng MIME khai báo sai và gửi lặp cùng request ID. Nêu kết quả mong đợi của metadata, payload và cleanup.

**Bài tập C — chọn kiến trúc:** So sánh BLOB trong PostgreSQL và object storage cho một dịch vụ có 1 triệu ảnh (trung bình 4 MiB), cần thumbnail, phân quyền theo khách hàng, hỗ trợ tải hàng loạt và phục hồi sau sự cố. Đề xuất nơi lưu metadata và payload, cách ngăn object mồ côi, cách chống mất dữ liệu và chỉ số đo hiệu năng.

**Bài tập D — phục hồi:** Giả sử backup metadata DB được tạo lúc 02:00 còn bản sao payload được tạo lúc 02:05. Hãy chỉ ra những tình huống tham chiếu không khớp có thể xảy ra và đề xuất quy trình chụp/sao lưu nhất quán hoặc đối soát khi restore.

Khi thiết kế persistence cho dữ liệu nhị phân lớn, luôn tách rõ **byte nội dung**, **metadata**, **định danh nghiệp vụ**, **trạng thái xử lý** và **cơ chế cấp quyền**. Cách chia này giúp ứng dụng Java chọn đúng kho lưu trữ, chuyển byte hiệu quả, giữ các tham chiếu nhất quán và phục hồi dữ liệu đáng tin cậy khi hệ thống gặp lỗi.

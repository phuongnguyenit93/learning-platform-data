# Consistency, generation và preconditions khi cập nhật object trên Cloud Storage

Hai phiên bản của một dịch vụ Java có thể cùng đọc `gs://commerce-data/orders/state.json`, tính trạng thái mới rồi ghi đè object đó. Nếu cả hai tiến trình đều cập nhật mà không kiểm tra trạng thái đã quan sát, một lần ghi có thể **âm thầm xóa kết quả của lần ghi khác**. Vấn đề này không phải do Cloud Storage “chưa đồng bộ dữ liệu”; nó là **race condition** khi nhiều tác nhân thao tác trên cùng một object.

Cloud Storage có **strong consistency** đối với hầu hết thao tác đọc, ghi, xóa và liệt kê object. Để cập nhật an toàn trong hệ thống đồng thời, Cloud Storage còn cung cấp hai số phiên bản **`generation`** và **`metageneration`**, cùng **request preconditions** như `ifGenerationMatch` và `ifMetagenerationMatch`. Kết hợp các cơ chế này cho phép triển khai **optimistic concurrency control / compare-and-swap (CAS)** ngay tại API lưu trữ.

Bài thuộc chương **Cloud Storage** của mô-đun `CLOUD_PROVIDERS_GCP`. Trong bối cảnh học tổ chức project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu, đây là nền tảng để viết ứng dụng an toàn, tự động hóa triển khai, bảo vệ tài nguyên, kiểm soát dữ liệu nhất quán, giảm lỗi retry và theo dõi chi phí phát sinh.

**Phạm vi:** hành vi consistency của Cloud Storage, định danh phiên bản object, preconditions, đọc–sửa–ghi có điều kiện, thao tác CLI/REST/Java và các trường hợp tranh chấp. Các cơ chế **Object Versioning, soft delete, retention, IAM và caching** chỉ được đề cập khi ảnh hưởng đến bài toán này.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích những thao tác Cloud Storage nào **strongly consistent** và trường hợp nào có thể quan sát dữ liệu không mới nhất.
2. Phân biệt `generation` (phiên bản nội dung object) với `metageneration` (phiên bản metadata của một generation).
3. Dùng `ifGenerationMatch=0` để **chỉ tạo nếu chưa tồn tại live object**.
4. Dùng `ifGenerationMatch=G` để **ghi đè/xóa chỉ khi live version vẫn đúng G**.
5. Dùng **cả generation và metageneration** để cập nhật metadata không làm mất chỉnh sửa đồng thời.
6. Nhận diện `412 Precondition Failed` là xung đột điều kiện, phân biệt với lỗi IAM, object không tồn tại và lỗi tạm thời.
7. Thiết kế retry có điều kiện, idempotency, đồng bộ nhiều writers và đọc theo generation ổn định.
8. Thực hành với `gcloud storage`, REST JSON API và Cloud Storage Java client library.
9. Hiểu giới hạn của atomicity một object, Object Versioning, soft delete, CDN/browser cache và bảo vệ dữ liệu.
10. Xây dựng quy trình kiểm thử song song và observability cho ứng dụng production.

## 1. Mô hình dữ liệu: bucket, object name, live version

Cloud Storage lưu **object** trong **bucket**. Một object được nhận diện theo tên (object name) trong bucket; nếu ghi lại cùng tên, bạn tạo một **generation mới** của object.

Ví dụ:

~~~text
Bucket: commerce-lab-data
Object name: orders/state.json
URI: gs://commerce-lab-data/orders/state.json

Nội dung hiện tại:
{"orderId":"A100","status":"PENDING"}
~~~

Tên có dấu `/` là một phần của object name, không có nghĩa đây là một file trong thư mục POSIX thật. Mô hình hierarchical namespace và managed folders có các tính năng riêng; bài này xét **đọc/ghi object**.

### 1.1. Live object và noncurrent generation

Tại một thời điểm, thông thường chỉ có **một live version** cho cùng tên object. Nếu bucket bật **Object Versioning**, bản bị thay thế có thể được giữ lại dưới dạng **noncurrent version**, nhận diện bằng generation cũ. Nếu không bật Object Versioning, việc thay thế không có nghĩa bạn có thể đọc lại version cũ như một noncurrent object.

~~~mermaid
flowchart LR
    W1["Upload state.json lần 1"] --> G1["generation G1<br/>live"]
    W2["Overwrite cùng tên"] --> G2["generation G2<br/>live"]
    G1 -. "Chuyển thành noncurrent<br/>nếu bật Object Versioning" .-> V["Lịch sử phiên bản"]
    W2 --> G2
~~~

**Generation không phụ thuộc việc bật Object Versioning.** Mọi object đều có generation. Versioning quyết định **có giữ bản cũ hay không**, không phải quyết định API có cấp số generation hay không.

## 2. Strong consistency của Cloud Storage bảo đảm những gì?

Theo Google Cloud, các thao tác sau có **strong global consistency**:

| Thao tác | Sau khi API trả kết quả thành công | Ví dụ |
| --- | --- | --- |
| **Object read-after-write** | Lần đọc sau nhìn thấy object/generation vừa ghi | Upload xong, `GET` trả nội dung mới |
| **Object read-after-metadata-update** | Metadata được đọc lại thấy cập nhật mới | Đổi `Cache-Control`, đọc metadata mới |
| **Object read-after-delete** | Live object đã xóa không còn thấy ở API đọc thông thường | Xóa thành công, đọc lại live name nhận `404` |
| **Object listing** | List phản ánh object được tạo/xóa thành công | Upload rồi `ls` thấy tên mới |
| **Bucket read-after-create/update/delete** | Thao tác đọc metadata bucket phản ánh trạng thái mới | Cập nhật bucket metadata rồi đọc lại |
| **Bucket listing** | Danh sách bucket cập nhật nhất quán | Tạo bucket rồi list |
| **Folders/managed folders được hỗ trợ** | Những hoạt động tạo/đọc/xóa/liệt kê được hỗ trợ có nhất quán mạnh | Phân tích theo loại resource cụ thể |

Các bảo đảm áp dụng xuyên region, dual-region và multi-region cho những thao tác được liệt kê, không chỉ cùng zone nơi upload.

### 2.1. Atomicity của thao tác trên một object

Khi tải lên hoặc ghi đè một object, một bản tải lên dở dang không xuất hiện như một live object chỉ mới có **nửa nội dung**. Object mới có thể được đọc khi thao tác hoàn tất thành công; người đọc không nhận một object chắp vá từ hai lần overwrite.

~~~mermaid
sequenceDiagram
    participant W as Writer
    participant S as Cloud Storage
    participant R as Reader
    R->>S: GET object
    S-->>R: Generation G1
    W->>S: Upload bản thay thế G2
    Note over S: Ghi đang xử lý
    R->>S: GET object
    S-->>R: Live generation hợp lệ
    S-->>W: 2xx (G2 hoàn tất)
    R->>S: GET object
    S-->>R: Generation G2
~~~

Tuy nhiên **atomicity một object không tạo transaction trên nhiều objects**. Nếu ứng dụng cần cập nhật `manifest.json` và năm object dữ liệu như một giao dịch duy nhất, những object này có thể được cập nhật ở các thời điểm khác nhau. Cần thiết kế manifest trỏ tới **generation cố định**, dùng tên object bất biến, hoặc dùng hệ thống giao dịch thích hợp.

### 2.2. Strong consistency không tự ngăn lost update

Giả sử client A và B cùng đọc G1:

~~~mermaid
sequenceDiagram
    participant A as Writer A
    participant S as Cloud Storage
    participant B as Writer B
    A->>S: GET state.json (G1)
    B->>S: GET state.json (G1)
    S-->>A: G1 = status PENDING
    S-->>B: G1 = status PENDING
    A->>S: PUT status PACKED (không precondition)
    S-->>A: Thành công: G2
    B->>S: PUT status CANCELLED (không precondition)
    S-->>B: Thành công: G3
    Note over S: G2 bị thay thế bởi G3
~~~

Cả hai lần ghi có thể thành công và tính nhất quán vẫn đúng: **G3 là live version mới nhất**. Nhưng thay đổi G2 của A đã bị mất về mặt nghiệp vụ. Giải pháp là **optimistic concurrency control** bằng preconditions.

## 3. Những ngoại lệ quan trọng khi nói “consistent”

Không phải mọi thứ xung quanh Cloud Storage đều tức thời.

### 3.1. Public cache, browser và CDN

**Object công khai có thể được cache.** Một trình duyệt hoặc lớp cache có thể tiếp tục trả bản cũ cho tới khi TTL hết hạn, dù Cloud Storage gốc đã nhận và ghi đè live object mới. Nếu không cấu hình thời hạn cache, một object public có thể được cache tới **60 phút** theo tài liệu.

Đừng chẩn đoán một response cũ từ browser bằng cách kết luận Cloud Storage mất strong consistency. Hãy kiểm tra `Cache-Control`, `Age`/cache headers, CDN, phiên bản URL và request tới origin theo môi trường được phép.

**Cách làm:** dùng tên object có version/hash trong URL cho tài nguyên tĩnh (`app.4f2b.js`), hoặc cấu hình cache policy và invalidation phù hợp. Với nội dung cần cập nhật ngay, thiết kế bypass/không cache ở những lớp phù hợp.

### 3.2. Thay đổi IAM và một số cấu hình bucket

Việc **cấp hoặc thu hồi quyền IAM** có thể có độ trễ lan truyền, khác với việc đọc metadata object đã được cập nhật. Việc **tạo lại bucket sau khi xóa** cũng có thể có độ trễ. Một số thay đổi cấu hình như bật **Object Versioning** cần chờ propagation trước khi dựa vào hành vi thay thế/xóa; tài liệu khuyến nghị đợi ít nhất **30 giây** sau khi đổi cấu hình versioning.

Một trường hợp hiếm ở bucket đa vùng: nếu nơi bản ghi ban đầu được lưu tạm thời không khả dụng trước khi replication hoàn tất, người đọc có thể nhận **lỗi `500` có thể retry** thay vì nội dung cũ. Đây không phải kết quả đọc “stale” được mong đợi.

### 3.3. Strong consistency không đồng nghĩa xếp thứ tự nghiệp vụ

Storage đảm bảo quan sát trạng thái object sau thao tác thành công; **không bảo đảm quy tắc business** như “đơn hàng không được chuyển từ SHIPPED về NEW”. Ứng dụng phải xác định transition hợp lệ và áp dụng precondition ngay lúc ghi.

## 4. Generation: ID của phiên bản dữ liệu object

Mỗi object generation có một giá trị số `generation` do Cloud Storage cấp.

~~~json
{
  "name": "orders/state.json",
  "bucket": "commerce-lab-data",
  "generation": "1735000000000123",
  "metageneration": "1",
  "contentType": "application/json",
  "size": "36"
}
~~~

Các số trên **chỉ minh họa**, không phải response lấy từ hệ thống.

Những thuộc tính cần nhớ:

1. `generation` xác định **phiên bản nội dung** của object.
2. Khi tạo lại/overwrite một live object, generation mới **khác** generation cũ.
3. Không tự suy ra generation luôn tăng theo thời gian: Google Cloud lưu ý **giá trị của generation mới không nhất thiết lớn hơn generation cũ**.
4. Generation của hai **object khác nhau** không phải một đồng hồ toàn cục; đừng so chúng để kết luận thứ tự sự kiện.
5. Muốn đọc một **phiên bản cụ thể**, phải đưa generation vào yêu cầu đọc theo khả năng API; đọc chỉ theo tên mặc định nhắm tới live version.
6. Khi thay metadata mà không thay data object, **generation giữ nguyên**; chỉ metageneration tăng.

### 4.1. Generation không phải timestamp

Không sử dụng phép `G2 > G1` làm điều kiện nghiệp vụ “mới hơn”. Nếu cần thứ tự nghiệp vụ, lưu sequence/event time hoặc version logic trong dữ liệu của ứng dụng và áp dụng CAS lên object. Generation giúp phát hiện **object đã thay đổi** kể từ khi quan sát, không tự cung cấp ordering cho mọi object.

### 4.2. Tại sao phải ghi lại generation?

Khi ứng dụng xử lý message hoặc task:

~~~text
Order A100
Object: orders/A100.json
Observed generation: G17
Message ID: event-8042
Proposed new status: PACKED
~~~

Sau khi xử lý, ứng dụng thử ghi bản mới **chỉ nếu live generation còn là G17**. Nếu một writer khác đã ghi G18, Cloud Storage từ chối update; ứng dụng tải lại G18, xét business rule và tính toán lại.

Điều này đặc biệt hữu ích khi **GKE Pod**, **Cloud Run instances**, **Compute Engine VMs** hoặc job CI/CD có nhiều writer cùng tác động lên một object.

## 5. Metageneration: ID của phiên bản metadata

`metageneration` được cấp theo **mỗi generation** và tăng mỗi lần metadata của generation đó được cập nhật.

Ví dụ:

| Sự kiện | Generation | Metageneration | Giải thích |
| --- | --- | --- | --- |
| Upload `state.json` lần đầu | G1 | 1 | Tạo nội dung và metadata đầu tiên |
| Đổi custom metadata `owner` | G1 | 2 | Nội dung không đổi |
| Đổi `Cache-Control` | G1 | 3 | Metadata tiếp tục đổi |
| Overwrite nội dung | G2 | 1 | Generation mới có metageneration riêng |
| Đổi metadata trên G2 | G2 | 2 | Không liên quan metageneration của G1 |

**Metageneration chỉ có ý nghĩa khi đi kèm generation.** Không được so `metageneration=2` của G1 với `metageneration=2` của G2 rồi suy ra metadata giống nhau hoặc đang ở cùng trạng thái.

Metadata gồm `Cache-Control`, `Content-Type`, custom metadata, hold/retention-related fields theo khả năng API và những thuộc tính khác. Một số trường không thể sửa trực tiếp và chỉ thay khi **rewrite object**; cần đọc [Object metadata](https://cloud.google.com/storage/docs/metadata) trước khi chọn thao tác.

### 5.1. Quy tắc quan trọng cho metadata CAS

**Khi dùng `ifMetagenerationMatch` cho object, luôn kết hợp `ifGenerationMatch`** để đảm bảo đang sửa metadata của **đúng object generation**.

Nếu chỉ kiểm tra metageneration = 1, một writer có thể xóa và tạo lại object. Object mới G2 cũng bắt đầu với metageneration = 1; điều kiện đơn lẻ có thể thỏa với object **khác** so với bản đã quan sát. Cặp `(generation, metageneration)` mới là khóa kiểm tra trạng thái an toàn.

## 6. Preconditions: so sánh trạng thái ngay khi áp dụng request

**Request precondition** là điều kiện gửi kèm lời gọi Cloud Storage. Cloud Storage kiểm tra điều kiện **tại thời điểm xử lý thao tác**. Nếu không thỏa, request không được áp dụng như một cập nhật thành công.

| JSON API parameter | Ý nghĩa | Kết quả không thỏa |
| --- | --- | --- |
| `ifGenerationMatch=G` | Chỉ tiếp tục nếu live generation đúng G | `412 Precondition Failed` |
| `ifGenerationMatch=0` | Chỉ ghi khi **không có live version** cùng tên | `412` nếu live object đã tồn tại |
| `ifMetagenerationMatch=M` | Chỉ tiếp tục nếu metageneration đúng M | `412` |
| `ifGenerationNotMatch=G` | Chỉ tiếp tục nếu generation **khác** G | Với yêu cầu đọc thường trả `304 Not Modified` |
| `ifMetagenerationNotMatch=M` | Chỉ tiếp tục nếu metageneration khác M | Với yêu cầu đọc thường trả `304` |

API XML sử dụng những header tương ứng như `x-goog-if-generation-match`; REST JSON API dùng query parameter. HTTP `If-Match`/`If-None-Match` dựa trên ETag cũng có thể được dùng trong một số yêu cầu, nhưng generation/metageneration thường là lựa chọn dễ kiểm soát hơn cho Cloud Storage.

### 6.1. Cách hiểu đặc biệt của generation 0

~~~text
ifGenerationMatch=0

Live object cùng tên không tồn tại:
  → Cho phép tạo object.

Có live object cùng tên:
  → 412 Precondition Failed.

Chỉ còn những noncurrent versions (bucket bật versioning):
  → Vẫn cho phép tạo live object mới.
~~~

**`0` không có nghĩa “generation hiện tại bằng 0”** và không phải giá trị để dùng cho xóa hoặc cập nhật metadata. Tài liệu khuyến nghị chỉ dùng giá trị đặc biệt này **khi ghi dữ liệu object**.

### 6.2. Có thể kết hợp nhiều điều kiện

Một yêu cầu cập nhật metadata có thể chỉ thành công khi:

~~~text
ifGenerationMatch = G1
AND
ifMetagenerationMatch = 7
~~~

Nếu **bất kỳ điều kiện** nào sai, request bị từ chối. Cơ chế này ngăn “time-of-check vs time-of-use” (TOCTOU) vì phần kiểm tra và phần thay đổi được thực hiện tại dịch vụ trong cùng request.

### 6.3. Không dùng “kiểm tra rồi ghi” không có điều kiện

~~~text
Sai:
  1. GET state.json, thấy G1
  2. if (G1 là bản cần sửa)
  3. PUT state.json không có precondition

Đúng:
  1. GET state.json, lưu G1
  2. Tính nội dung mới
  3. PUT state.json với ifGenerationMatch=G1
  4. Nếu 412: đọc lại rồi quyết định xử lý xung đột
~~~

**Điểm mấu chốt:** chính request **PUT/PATCH/DELETE** phải mang precondition. Chỉ đọc trước khi ghi không tự bảo vệ khỏi writer khác xen vào.

## 7. Ba mẫu cập nhật an toàn quan trọng nhất

### 7.1. Create-if-absent: chỉ tạo object nếu chưa có live version

Ví dụ worker nhận event và tạo `results/event-8042.json`. Nếu hệ thống gửi lại event, không nên ghi đè kết quả trước đó:

~~~bash
gcloud storage cp result.json \
  gs://BUCKET_NAME/results/event-8042.json \
  --if-generation-match=0
~~~

Một trong các writers tạo thành công. Writer khác nhận `412` nếu đã có live object cùng tên. Đây là “first writer wins” ở mức **tên object**, không tự bảo đảm exactly-once toàn hệ thống.

### 7.2. Update-if-unchanged: compare-and-swap

Giả sử ứng dụng đã đọc generation G1, tính status mới rồi ghi:

~~~bash
gcloud storage cp state-v2.json \
  gs://BUCKET_NAME/orders/state.json \
  --if-generation-match=GENERATION_OBSERVED
~~~

Nếu không ai overwrite từ lúc đọc G1, request thành công và tạo generation mới. Nếu một writer khác đã sửa nội dung, request **thất bại `412`** thay vì silently overwrite.

### 7.3. Delete-only-the-observed-version

Một cleanup job đọc danh sách object cũ để xóa. Giữa lúc list và lúc delete, writer khác có thể thay object cùng tên. Xóa theo tên **không có precondition** dễ xóa nhầm bản mới.

~~~bash
gcloud storage rm gs://BUCKET_NAME/temp/result.json \
  --if-generation-match=GENERATION_OBSERVED
~~~

Điều kiện ngăn việc cleanup xóa live generation khác với bản nó đã xét. **Lệnh `rm` thật sự xóa object** (hoặc chuyển sang soft-deleted/noncurrent theo cấu hình bucket), vì vậy chỉ thực hiện khi đã xác minh bucket, name, generation và retention.

## 8. Cập nhật metadata mà không làm mất thay đổi từ writer khác

Ví dụ hai người cùng đọc metadata:

~~~text
Ban đầu:
  generation = G5
  metageneration = 3
  metadata = { owner: "team-commerce", stage: "draft" }

Writer A muốn:
  stage = "approved"

Writer B muốn:
  owner = "team-platform"
~~~

Nếu cả hai PATCH/UPDATE với trạng thái metadata cũ và không dùng điều kiện, một thay đổi có thể ghi đè/loại bỏ metadata của người kia theo cách request được tạo. Mẫu an toàn:

1. Đọc **cả generation và metageneration** hiện tại.
2. Tạo metadata mới bằng cách **merge** các field cần thay, không vô tình xóa field khác.
3. Gửi metadata update với **cả `ifGenerationMatch=G5` và `ifMetagenerationMatch=3`**.
4. Nếu `412`, đọc lại metadata, tính thay đổi trên bản mới và retry theo business policy.

~~~mermaid
sequenceDiagram
    participant A as Writer A
    participant B as Writer B
    participant S as Cloud Storage
    A->>S: GET metadata (G5, M3)
    B->>S: GET metadata (G5, M3)
    S-->>A: G5, M3
    S-->>B: G5, M3
    A->>S: PATCH stage, ifGen=G5, ifMeta=M3
    S-->>A: 2xx, G5/M4
    B->>S: PATCH owner, ifGen=G5, ifMeta=M3
    S-->>B: 412 (metadata đã đổi)
    B->>S: GET mới G5/M4, merge rồi PATCH có điều kiện
~~~

**Metadata update thông thường không tạo generation mới**, nên nếu chỉ dùng generation-match G5 thì cả hai PATCH có thể vẫn được cho phép. Để tránh lost update **metadata**, cần thêm metageneration-match.

## 9. Thực hành CLI: quan sát generation và xung đột

Bài lab dùng **bucket thử nghiệm đã tồn tại** và được phép ghi. Không dùng bucket chứa dữ liệu production. Các lệnh có thể phát sinh **operation charges, storage charges** và phí liên quan. Cần quyền IAM tương ứng, đồng thời không làm thay đổi những file ngoài phạm vi bài học nếu bạn chỉ đang đọc tài liệu.

### 9.1. Chuẩn bị

~~~bash
gcloud auth list
gcloud config get-value project

# Chỉ đọc: kiểm tra bucket trong project đã được duyệt
gcloud storage buckets describe gs://BUCKET_NAME
~~~

Tạo hai tệp JSON trên **máy thực hành**, không chứa secret/dữ liệu cá nhân:

~~~bash
printf '{"status":"PENDING","revision":1}\n' > state-v1.json
printf '{"status":"PACKED","revision":2}\n' > state-v2.json
~~~

### 9.2. Chỉ tạo khi chưa có live object

~~~bash
gcloud storage cp state-v1.json \
  gs://BUCKET_NAME/lab-cas/state.json \
  --if-generation-match=0
~~~

Nếu `lab-cas/state.json` đã có live version, thao tác trả lỗi `412`. **Không bỏ cờ** để “cho qua lỗi”; hãy kiểm tra vì sao object đã tồn tại.

### 9.3. Đọc generation/metageneration

~~~bash
gcloud storage objects describe \
  gs://BUCKET_NAME/lab-cas/state.json \
  --format="json(name,generation,metageneration,size,updated)"
~~~

Ví dụ giả định kết quả là G1 và M1:

~~~json
{
  "name": "lab-cas/state.json",
  "generation": "1735000000000123",
  "metageneration": "1"
}
~~~

Ghi giá trị **generation thực tế** từ output, không copy số ví dụ ở trên vào bucket khác.

### 9.4. Ghi đè chỉ khi generation không đổi

~~~bash
gcloud storage cp state-v2.json \
  gs://BUCKET_NAME/lab-cas/state.json \
  --if-generation-match=GENERATION_V1
~~~

Sau khi thành công, đọc lại metadata; live object có **generation mới**. Chạy lại cùng lệnh **vẫn giữ GENERATION_V1** sẽ nhận `412` vì điều kiện không còn đúng. Đây là **hành vi đúng**, không phải bằng chứng Cloud Storage chưa đồng bộ.

### 9.5. Thử update metadata có điều kiện

Đọc generation/metageneration mới, ví dụ G2 và M1, rồi dùng:

~~~bash
gcloud storage objects update \
  gs://BUCKET_NAME/lab-cas/state.json \
  --update-custom-metadata=reviewed-by=commerce \
  --if-generation-match=GENERATION_V2 \
  --if-metageneration-match=METAGENERATION_V2
~~~

Thao tác thành công cập nhật metadata và tăng metageneration của G2. Nếu một tiến trình khác vừa cập nhật metadata, `412` nhắc bạn đọc lại trước khi sửa.

### 9.6. Cleanup có điều kiện

~~~bash
# CHỈ dùng trong lab đã kiểm tra đúng tên và generation!
gcloud storage rm gs://BUCKET_NAME/lab-cas/state.json \
  --if-generation-match=GENERATION_CURRENT
~~~

Nếu bật **Object Versioning** hoặc **soft delete**, bản bị xóa có thể còn được lưu theo chính sách, nên kiểm tra chi phí và vòng đời thay vì mặc định mọi byte đã biến mất. Tránh xóa bucket hoặc wildcard rộng.

## 10. REST JSON API: preconditions được gửi ở đâu?

Trong **Cloud Storage JSON API**, preconditions được truyền bằng **query parameters**. Ví dụ upload theo nguyên tắc create-if-absent:

~~~bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data-binary @state-v1.json \
  "https://storage.googleapis.com/upload/storage/v1/b/BUCKET_NAME/o?uploadType=media&name=lab-cas%2Fstate.json&ifGenerationMatch=0"
~~~

Ở đây:

- `BUCKET_NAME` là bucket lab thật, phải được URL-encode nếu tên/thành phần path yêu cầu.
- `name=lab-cas%2Fstate.json` là tên object được URL-encode.
- `ifGenerationMatch=0` là precondition ở **server**, không phải logic do client kiểm tra trước.
- Access token lấy từ tài khoản CLI đang đăng nhập; **không in token vào logs hoặc commit script có token**.

Ví dụ logic thay thế với generation G1:

~~~text
POST /upload/storage/v1/b/BUCKET_NAME/o
  ?uploadType=media
  &name=lab-cas%2Fstate.json
  &ifGenerationMatch=GENERATION_V1

Nếu current live generation = G1:
  → 2xx + metadata của generation mới.

Nếu current live generation khác G1:
  → HTTP 412 Precondition Failed.
~~~

Đối với **XML API**, cơ chế tương ứng dùng header `x-goog-if-generation-match`; không trộn cú pháp JSON query parameter với XML header nếu ứng dụng sử dụng một API khác.

### 10.1. Đọc có điều kiện và HTTP 304

Nếu client đang giữ bản G1 và chỉ muốn download khi live object đã thay đổi, có thể dùng điều kiện **`ifGenerationNotMatch=G1`** với thao tác đọc được hỗ trợ. Khi object vẫn là G1, API trả `304 Not Modified` để client không tải lại dữ liệu.

Điều này khác **`ifGenerationMatch=G1`** dùng để bảo đảm “chỉ thao tác nếu version còn là G1”. Chọn điều kiện theo ý nghĩa nghiệp vụ: **kiểm tra không đổi** hay **chỉ lấy khi đã đổi**.

## 11. Ví dụ Java: optimistic concurrency khi ghi JSON

Ví dụ sử dụng **Google Cloud Storage Java client library**, dependency `com.google.cloud:google-cloud-storage`. Ứng dụng xác thực bằng **Application Default Credentials (ADC)**: trên Cloud Run/GKE/Compute Engine ưu tiên runtime identity, trên máy developer dùng local ADC hoặc impersonation; không cần tải service account JSON private key.

### 11.1. Tạo hoặc thay thế chỉ nếu không ai thay đổi

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageException;
import com.google.cloud.storage.StorageOptions;
import java.nio.charset.StandardCharsets;

public class ConditionalOrderWrite {
    public static void main(String[] args) {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "Usage: ConditionalOrderWrite BUCKET OBJECT JSON_CONTENT");
        }

        String bucket = args[0];
        String object = args[1];
        byte[] data = args[2].getBytes(StandardCharsets.UTF_8);

        Storage storage = StorageOptions.getDefaultInstance().getService();

        // Bước đọc có thể chạy song song với writer khác.
        Blob observed = storage.get(bucket, object);

        // Bước GHI mang precondition, nên race sau GET không gây lost update.
        Storage.BlobTargetOption precondition =
            observed == null
                ? Storage.BlobTargetOption.doesNotExist()
                : Storage.BlobTargetOption.generationMatch(
                    observed.getGeneration());

        BlobInfo info = BlobInfo.newBuilder(BlobId.of(bucket, object))
            .setContentType("application/json")
            .build();

        try {
            Blob written = storage.create(info, data, precondition);
            System.out.println("Saved generation: " + written.getGeneration());
        } catch (StorageException e) {
            if (e.getCode() == 412) {
                System.err.println(
                    "Conflict: object đã thay đổi; đọc lại và xét nghiệp vụ.");
                return;
            }
            throw e;
        }
    }
}
~~~

**Ví dụ tập trung vào precondition, chưa thực hiện kiểm tra transition nghiệp vụ.** Trong ứng dụng thật, cần deserialize bản G1 thành đối tượng Java, kiểm tra business invariant, tạo JSON mới rồi dùng chính generation đã đọc. Không tự động ghi đè bằng dữ liệu cũ chỉ vì xuất hiện `412`.

### 11.2. Vì sao `doesNotExist()` tương ứng generation 0?

Client library cung cấp `Storage.BlobTargetOption.doesNotExist()` để diễn đạt **chỉ upload nếu chưa có live object cùng tên**. Cơ chế server tương đương điều kiện **`ifGenerationMatch=0`**.

Đừng tự tạo chuỗi “kiểm tra `storage.get(...) == null`, sau đó upload bình thường”. Trong khoảng giữa GET và PUT, một writer khác có thể đã tạo object. **Precondition trong request ghi** mới ngăn được race đó.

## 12. Ví dụ Java: cập nhật metadata với cặp version

Cập nhật metadata có thể ảnh hưởng tới cache, xử lý downstream hoặc thông tin nghiệp vụ. Mẫu sau dùng **cả generation và metageneration**:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageException;
import com.google.cloud.storage.StorageOptions;
import java.util.HashMap;
import java.util.Map;

public class ConditionalMetadataUpdate {
    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: ConditionalMetadataUpdate BUCKET OBJECT");
        }

        Storage storage = StorageOptions.getDefaultInstance().getService();
        Blob current = storage.get(args[0], args[1]);
        if (current == null) {
            throw new IllegalStateException("Object không tồn tại");
        }

        // Merge để giữ nguyên những custom metadata khác.
        Map<String, String> updatedMetadata = new HashMap<>();
        if (current.getMetadata() != null) {
            updatedMetadata.putAll(current.getMetadata());
        }
        updatedMetadata.put("reviewed-by", "commerce-platform");

        BlobInfo next = current.toBuilder()
            .setMetadata(updatedMetadata)
            .build();

        try {
            Blob saved = storage.update(
                next,
                Storage.BlobTargetOption.generationMatch(
                    current.getGeneration()),
                Storage.BlobTargetOption.metagenerationMatch(
                    current.getMetageneration()));
            System.out.println(
                "Metadata metageneration: " + saved.getMetageneration());
        } catch (StorageException e) {
            if (e.getCode() == 412) {
                System.err.println("Metadata conflict: hãy GET và merge lại.");
                return;
            }
            throw e;
        }
    }
}
~~~

Nếu writer khác **ghi đè data** từ G1 thành G2, điều kiện generation chặn request. Nếu writer khác **chỉ đổi metadata** G1/M3 thành G1/M4, điều kiện metageneration chặn request. Hai điều kiện cùng nhau tránh cập nhật sai target hoặc làm mất metadata.

**Lưu ý:** Không truyền lại metadata cũ một cách mù quáng vào request mới sau `412`. Phải làm mới dữ liệu, đánh giá quyền/điều kiện và merge từ trạng thái mới nhất.

## 13. Xóa an toàn, retry và idempotency

### 13.1. Vì sao retry một thao tác ghi có thể nguy hiểm?

Giả sử client gửi upload, server lưu thành công G2, nhưng **kết nối mạng đứt trước khi client nhận response**. Client tưởng thất bại và gửi lại upload không điều kiện, có thể tạo G3 hoặc overwrite một cập nhật vừa được writer khác thực hiện.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Cloud Storage
    participant W as Writer khác
    C->>S: PUT nếu generation=G1
    S-->>C: Server đã ghi G2 (response bị mất)
    W->>S: PUT nếu generation=G2
    S-->>W: Thành công, G3
    C->>S: Retry PUT không điều kiện
    S-->>C: Thành công nhưng ghi đè G3 (không mong muốn)
~~~

Nếu client **giữ nguyên `ifGenerationMatch=G1` khi retry**, request không thể ghi đè G3. Nhưng retry có thể trả `412` vì **lần đầu của chính client đã thành công**.

Do đó:

- **`412` không tự chứng minh lần ghi đầu chưa từng thành công.**
- Cần đọc lại object và đối chiếu **nội dung/checksum, request ID hoặc operation marker nghiệp vụ** trước khi kết luận thất bại hay thành công.
- Nếu bản hiện tại không còn ở trạng thái mong muốn, phải làm rõ business rule thay vì bỏ precondition.

### 13.2. Những lỗi nên retry và không nên retry như nhau

| Trạng thái | Ý nghĩa điển hình | Hành động |
| --- | --- | --- |
| `412 Precondition Failed` | Object/metageneration không còn đúng giá trị đã quan sát | **Conflict/reconcile**; GET mới, tính lại, chỉ ghi khi hợp lệ |
| `304 Not Modified` | Điều kiện “not match” của request đọc không thỏa | Có thể dùng bản cache/local đang giữ |
| `404 Not Found` | Live object không tồn tại hoặc resource/generation đích không còn | Kiểm tra logic create/delete và quyền; không tự overwrite |
| `401 Unauthenticated` | Credential không hợp lệ hoặc hết hạn | Kiểm tra ADC/token |
| `403 Permission Denied` | IAM, policy, retention/hold hoặc kiểm soát khác | Kiểm tra quyền và ràng buộc; **không** tự bypass |
| `408, 429, 5xx` | Timeout, quota/rate hoặc lỗi tạm thời | Retry có kiểm soát theo hướng dẫn và tính idempotency |
| `409 Conflict` | Xung đột loại khác theo operation/API | Xem message cụ thể, không coi như CAS `412` |

**Exponential backoff với jitter** hữu ích cho lỗi tạm thời hoặc contention được chính sách cho phép retry. Tuy nhiên retry liên tục cùng precondition **đã lỗi 412** không làm nó thành công; phải đọc/trạng thái mới rồi tính lại.

### 13.3. Retry policy trong Java client

Cloud Storage Java client library hỗ trợ retry những operation idempotent và **conditionally idempotent** khi có precondition/generation phù hợp. Mức retry/timeout có thể cấu hình theo thư viện và environment.

**Đừng tự bật retry vô hạn cho write không điều kiện.** Nếu thao tác có side effect ngoài Storage (gửi Pub/Sub message, ghi database hoặc gọi API thanh toán), precondition cho Storage **không biến toàn bộ workflow thành exactly-once**. Hãy dùng event ID, deduplication key hoặc transactional outbox theo nhu cầu.

## 14. Đọc object ổn định và ranged reads

Một object lớn có thể được tải theo nhiều request **range**. Nếu client đọc bytes 0–999 của G1, giữa chừng writer overwrite object thành G2, rồi client đọc bytes 1000–1999 **theo tên** mà không cố định generation, client có thể ghép dữ liệu từ **hai phiên bản khác nhau**.

~~~text
GET Range 0-999       → G1
Writer overwrite      → G2
GET Range 1000-1999   → G2
Ghép lại              → Có thể hỏng dữ liệu
~~~

Cách an toàn:

1. Đọc metadata, ghi lại generation G1.
2. Khi download theo nhiều range, **ghim đúng generation G1** hoặc dùng generation-match precondition theo API hỗ trợ.
3. Kiểm tra response và checksum phù hợp; nếu generation không còn khả dụng, **đừng ghép** các range khác phiên bản.
4. Nếu cần bản cũ luôn tồn tại cho các read kéo dài, cân nhắc **Object Versioning** hoặc tên immutable.

**Strong consistency không giải quyết việc ứng dụng tự ghép các range thuộc hai requests khác thời điểm.** Pinning là trách nhiệm của client.

## 15. Source và destination preconditions khi copy/compose

Cloud Storage hỗ trợ các thao tác **copy/rewrite** và **compose** từ nhiều object nguồn. Chúng cũng có race condition nếu một source hoặc destination bị thay đổi trong lúc tác vụ diễn ra.

### 15.1. Copy/rewrite object

Ví dụ job lấy `staging/report.json` rồi ghi vào `published/report.json`. Có **hai loại trạng thái cần kiểm tra**:

- **Source:** có còn đúng generation mà job đã kiểm tra không?
- **Destination:** có còn chưa tồn tại hoặc đúng generation cũ mà job được quyền overwrite không?

JSON API hỗ trợ những preconditions của source theo tên có tiền tố `ifSource...` như `ifSourceGenerationMatch`; destination dùng `ifGenerationMatch` thông thường. Cần xác minh API/client library hỗ trợ option tương ứng trước khi triển khai.

~~~text
copy source Gsrc -> destination

Điều kiện:
  source generation == Gsrc
  AND destination generation == Gdst
hoặc destination không có live object (generation-match=0).

Nếu một điều kiện sai:
  412, không ghi theo trạng thái đã giả định.
~~~

### 15.2. Compose nhiều nguồn

Khi ghép các phần dữ liệu thành một object bằng **compose**, có thể chỉ định **generation-match cho từng source object** và precondition cho destination. Nếu một writer khác thay source trước khi compose, `412` giúp tránh dùng nhầm component mới.

~~~mermaid
flowchart TD
    S1["part-a: generation A1"] --> C["Compose destination"]
    S2["part-b: generation B1"] --> C
    P["source gen A1 + B1<br/>destination generation guard"] -. "Preconditions" .-> C
    C --> D["result.json: generation mới"]
~~~

Compose là **một thao tác tạo destination object**, không phải một transaction đảm bảo các nghiệp vụ ngoài Storage đồng bộ cùng thời điểm. Những source objects vẫn cần lifecycle và IAM riêng.

## 16. Object Versioning, soft delete và retention: ba vấn đề khác nhau

Preconditions bảo vệ một **lần thao tác**. Chúng không thay thế lịch sử dữ liệu hoặc bảo vệ khỏi xóa nhầm.

| Cơ chế | Trả lời câu hỏi | Không giải quyết được |
| --- | --- | --- |
| **Preconditions** | “Chỉ ghi/xóa nếu object còn đúng trạng thái đã thấy?” | Không giữ tự động các bản cũ |
| **Object Versioning** | “Có giữ noncurrent versions khi live version bị ghi đè/xóa không?” | Không tự chặn một writer có quyền ghi sai; không bảo vệ khỏi xóa bucket |
| **Soft delete** | “Có thể phục hồi object/bucket bị xóa hoặc ghi đè trong thời gian giữ không?” | Không ngăn lost update tại thời điểm thao tác |
| **Retention policy / object hold** | “Có chặn xóa/overwrite trước thời hạn hoặc khi đang hold không?” | Không thay thế kiểm soát đồng thời theo generation |
| **IAM** | “Ai được đọc/ghi/xóa object?” | Không tự kiểm tra writer dùng dữ liệu cũ |
| **Lifecycle rules** | “Object/versions nào tự chuyển storage class hoặc được xóa theo điều kiện?” | Không bảo đảm giao dịch nhiều objects |

### 16.1. Versioning và generation

Khi bật Object Versioning, overwrite tạo **generation mới live** và generation cũ trở thành **noncurrent**. Đây là lựa chọn phù hợp khi ứng dụng cần truy cập lịch sử phiên bản theo số generation. Noncurrent versions vẫn có **chi phí lưu trữ**; nên kết hợp lifecycle management.

**Quan trọng:** `ifGenerationMatch=0` vẫn có thể tạo object khi chỉ còn noncurrent versions. Nó kiểm tra **live object**, không kiểm tra “đã từng tồn tại tên này trong lịch sử”.

### 16.2. Soft delete khác noncurrent version

Cloud Storage thường bật soft delete theo mặc định ở các bucket hỗ trợ, với **mức giữ mặc định bảy ngày** tại thời điểm tài liệu hiện hành được tham chiếu; có ngoại lệ/tùy chọn thay đổi theo loại bucket và policy. Khi object bị soft-delete, bản đó **không còn đọc/ghi bình thường** mà có thể được **restore** theo quyền và thời gian giữ. Trên bucket có versioning, việc xóa live version trước tiên có thể chuyển thành **noncurrent**, không giống xóa live object trên bucket không bật versioning.

Đừng dùng `generation` để suy luận rằng một bản đã bị soft-delete vẫn đọc được như noncurrent object. Xem trạng thái và API cụ thể.

### 16.3. Retention và Object Lock có thể chặn overwrite dù CAS hợp lệ

Nếu object đang bị giữ bởi **retention policy, object retention lock hoặc hold**, một yêu cầu ghi đè/xóa có thể bị từ chối **ngay cả khi generation precondition khớp**. CAS là một điều kiện cần cho an toàn đồng thời, không phải giấy phép bỏ qua các lớp bảo vệ khác.

## 17. Thiết kế state object an toàn cho ứng dụng Java nhiều replica

Giả sử hệ thống chạy trên **Cloud Run**, mỗi instance xử lý message Pub/Sub và lưu `orders/A100.json` trên Cloud Storage.

### 17.1. Thiết kế không an toàn

~~~text
1. Instance A đọc status=PENDING.
2. Instance B cũng đọc status=PENDING.
3. A cập nhật status=PACKED, upload không điều kiện.
4. B cập nhật status=CANCELLED, upload không điều kiện.
5. Một update bị mất nhưng hai instance đều báo thành công.
~~~

### 17.2. Thiết kế an toàn hơn với CAS

~~~mermaid
flowchart TD
    E["Nhận event/order ID"] --> G["GET object + generation"]
    G --> V{"Transition hợp lệ với state đã đọc?"}
    V -->|Không| N["Reject/ignore theo business rule"]
    V -->|Có| U["Tạo payload state mới"]
    U --> C["PUT với ifGenerationMatch=G"]
    C --> R{"Kết quả?"}
    R -->|2xx| OK["Lưu generation mới + xác nhận xử lý"]
    R -->|412| GET["GET lại và quyết định merge/reject/retry có giới hạn"]
    GET --> V
    R -->|429/5xx| RET["Exponential backoff, giữ nguyên precondition"]
    RET --> C
~~~

Một chiến lược production cần thêm:

1. **Business invariant:** status chỉ chuyển theo state machine hợp lệ; không để message đến trễ ghi trạng thái cũ.
2. **Deduplication:** lưu event ID hoặc revision logic để nhận biết event đã xử lý.
3. **Read pinning:** khi tải object theo nhiều chunk, dùng generation cố định.
4. **Bounded retry:** giới hạn số lần reconcile, quan sát contention; khi xung đột liên tục, đưa vào dead-letter/queue xử lý riêng.
5. **Metrics:** theo dõi `412`, lỗi retry, payload conflicts, end-to-end latency và số events bị bỏ qua.
6. **Access control:** service account chỉ có quyền cần thiết với bucket/prefix; tránh key JSON dài hạn và quyền quá rộng.
7. **Data recovery:** bật soft delete/versioning khi phù hợp, có retention/lifecycle rõ ràng, kiểm thử phục hồi.

### 17.3. Khi nào không nên dùng một object làm database giao dịch?

Nếu nhiều writers liên tục cập nhật **cùng một object** như một counter nóng hoặc bản ghi giao dịch, CAS conflict/retry có thể tăng mạnh. Cloud Storage không phải hệ thống giao dịch hàng nhiều record, không hỗ trợ atomic multi-object compare-and-swap như một database.

Cân nhắc **Firestore, Cloud SQL, Spanner** hoặc một dịch vụ có transaction/locking phù hợp nếu cần cập nhật nhiều bản ghi, index truy vấn, atomic counter hoặc cross-record invariants. Cloud Storage phù hợp hơn cho **immutable blobs, artifacts, backups, object lớn** và trường hợp updates có tranh chấp thấp/có thể retry.

## 18. Quan sát, bảo mật và chi phí

### 18.1. Metrics nên theo dõi

| Tín hiệu | Mục đích | Hành động |
| --- | --- | --- |
| Tỷ lệ `412` trên write/PATCH/DELETE | Đo contention và stale-client requests | Kiểm tra business logic, hot objects, retry |
| `429` và `5xx` | Phân biệt hạn mức/lỗi tạm thời | Backoff với jitter, quan sát quota/throttle |
| Số lần GET trước write | Đo overhead của CAS | Cache hợp lệ generation khi có thể, hạn chế round trip |
| Download range mismatch | Phát hiện dữ liệu ghép khác generation | Pin generation, checksum |
| Object Versioning/soft-delete storage | Chi phí các phiên bản/bản đã xóa | Lifecycle, retention phù hợp |
| Egress và số operation | Chi phí do GET metadata, retry và data transfer | Billing Reports, tối ưu kích thước và tần suất |
| IAM/policy errors | Xác minh đúng runtime identity | IAM, deny, VPC Service Controls nếu có |

**Đừng xem mọi `412` là sự cố hạ tầng.** Trong một thiết kế CAS đúng, một số xung đột là **tín hiệu bình thường**. Cần đo xem tỷ lệ đó có vượt ngưỡng chấp nhận, làm tăng độ trễ hoặc gây mất tiến trình công việc hay không.

### 18.2. Preconditions có chi phí

Mẫu đọc metadata rồi ghi có điều kiện có thể tạo thêm **một lượt request** và network round trip. Với workload nhạy cảm latency/chi phí:

- Khi biết chắc object mới theo thiết kế, dùng `ifGenerationMatch=0` mà không cần GET trước.
- Khi ứng dụng đã nhận generation từ response upload, lưu nó để sử dụng ở bước kế tiếp.
- Không tăng polling tần suất cao chỉ để xem generation có đổi chưa.
- Xem **Cloud Storage operation pricing, egress và retry load** để chọn chiến lược phù hợp.

### 18.3. IAM và VPC Service Controls vẫn áp dụng

Preconditions không thay quyền truy cập. Một request có generation chính xác vẫn cần quyền `storage.objects.get/create/delete/update` thích hợp, tùy thao tác, và phải vượt qua các policy khác như VPC Service Controls, org policy, retention/hold.

Với sản phẩm GCP trong mô-đun này, nên dùng **ADC, Workload Identity Federation, service account gắn runtime**, quyền tối thiểu và Cloud Audit Logs phù hợp. Không ghi access token, URL ký có bí mật, PII hoặc object payload nhạy cảm vào debug logs chỉ để điều tra `412`.

## 19. Chẩn đoán lỗi thường gặp

| Triệu chứng | Khả năng | Kiểm tra ưu tiên |
| --- | --- | --- |
| Upload create-if-absent nhận `412` | Đã có live object cùng tên | Đọc generation hiện tại, kiểm tra xử lý event trùng |
| Overwrite nhận `412` | Writer khác thay generation | Re-read, kiểm tra transition, retry bằng generation mới nếu hợp lệ |
| Metadata patch nhận `412` | Metadata đã đổi hoặc object được overwrite | So sánh cả generation và metageneration |
| GET nhận `404` sau DELETE | Live object đã bị xóa, bình thường với strong consistency | Kiểm tra soft delete/noncurrent nếu cần phục hồi |
| Browser vẫn thấy ảnh cũ | Public cache/CDN TTL | Cache-Control, cache key, invalidation |
| List thấy object nhưng worker “mất update” | Hai writers overwrite không điều kiện | Xem generation/logs; thêm CAS |
| Download lớn bị checksum mismatch | Ranged reads ghép nhiều generations | Pin generation cho mọi range |
| Retry upload cùng token request nhưng có `412` | Lần đầu có thể đã thành công; generation nay khác | Reconcile bằng checksum/event ID, không bỏ precondition |
| `403` dù generation đúng | IAM/deny/VPC SC/retention restriction | Kiểm tra principal, permissions, policy |
| Object generation cũ không đọc được | Versioning chưa bật, version cũ đã xóa/soft-delete | Kiểm tra bucket policy và object history |
| Generation đổi nhưng metageneration lại là 1 | Object đã được rewrite | Đây là hành vi bình thường của generation mới |
| `304 Not Modified` | Điều kiện non-match trên read không thỏa | Dùng bản local/cached đúng version |
| Lỗi tăng khi scale Cloud Run | Nhiều instances cùng sửa hot object | Chuyển sang partitioning/DB hoặc điều phối updates |

### 19.1. Trình tự debug có thể lặp lại

~~~mermaid
flowchart TD
    A["Object update không như mong đợi"] --> B{"API trả 412?"}
    B -->|Có| C["So sánh observed G/M với live G/M"]
    C --> D["Xác định writer khác / retry trùng"]
    D --> E["Re-read + reconcile theo nghiệp vụ"]
    B -->|Không| F{"401/403/404/429/5xx?"}
    F -->|401/403| G["Kiểm tra ADC, IAM, deny/VPC SC/retention"]
    F -->|404| H["Kiểm tra live/noncurrent/soft-deleted"]
    F -->|429/5xx| I["Retry có idempotency và backoff"]
    E --> J["Ghi metrics, xác minh trạng thái sau xử lý"]
    G --> J
    H --> J
    I --> J
~~~

## 20. Bài tập tự kiểm tra

**Câu 1.** Upload G1 trả thành công, sau đó một client khác lập tức GET object theo tên nhưng nhận G0 cũ. Đây có phải hành vi được kỳ vọng của Cloud Storage origin?

*Gợi ý:* Không. Object read-after-write ở origin là strongly consistent; kiểm tra cache/CDN hoặc cách client xác định resource, và các lỗi hệ thống đặc biệt.

**Câu 2.** Hai workers cùng đọc G1. Worker A ghi G2 trước, worker B thử ghi với `ifGenerationMatch=G1`. Kết quả?

*Gợi ý:* Worker B nhận `412`; không được âm thầm ghi đè G2.

**Câu 3.** `ifGenerationMatch=0` có nghĩa là object có generation 0 không?

*Gợi ý:* Không. Đây là điều kiện đặc biệt “không có live object cùng tên”, kể cả khi có noncurrent versions.

**Câu 4.** Writer A chỉ sửa metadata G1/M3 thành G1/M4. Writer B chỉ kiểm tra `ifGenerationMatch=G1` rồi PATCH metadata nó đã đọc trước đó. Có an toàn không?

*Gợi ý:* Chưa. Generation vẫn G1; writer B còn phải kiểm tra `ifMetagenerationMatch=M3` để phát hiện metadata đã đổi.

**Câu 5.** Vì sao không nên dùng metageneration một mình?

*Gợi ý:* Khi object bị overwrite thành generation khác, metageneration của generation mới có thể bắt đầu lại từ 1; cần ghép với generation.

**Câu 6.** Client đã gửi PUT có `ifGenerationMatch=G1`, mất kết nối và retry trả `412`. Có chắc PUT đầu chưa thành công không?

*Gợi ý:* Không. Lần đầu có thể đã ghi G2 nhưng response bị mất. Đọc lại và so sánh operation marker/checksum.

**Câu 7.** Một chương trình download object lớn thành nhiều range có thể ghép dữ liệu bị hỏng dù Cloud Storage strong consistency không?

*Gợi ý:* Có, nếu overwrite xảy ra giữa các range requests. Pin generation để mọi range thuộc cùng version.

**Câu 8.** Object Versioning đã bật; live object bị xóa thành noncurrent. Upload mới với `ifGenerationMatch=0` có được phép không?

*Gợi ý:* Có, nếu không có live version cùng tên; precondition 0 không yêu cầu lịch sử trống.

**Câu 9.** Tại sao bật Object Versioning không thay thế preconditions?

*Gợi ý:* Versioning lưu bản cũ, nhưng writer mới vẫn có thể ghi đè live version không phù hợp nghiệp vụ. Preconditions ngăn race ngay lúc thao tác.

**Câu 10.** Một 412 có nên retry vô hạn ngay lập tức không?

*Gợi ý:* Không. Đó thường là conflict cần re-read/reconcile; retry liên tục cùng expected generation không thể tự thành công.

**Câu 11.** Trang public ảnh cũ vẫn hiển thị sau overwrite, trong khi gcloud API đọc metadata mới. Nguyên nhân có thể là gì?

*Gợi ý:* Public cache/browser/CDN, phụ thuộc `Cache-Control` và TTL.

**Câu 12.** Một job copy object từ staging sang production muốn chặn cả source bị sửa lẫn destination bị thay. Cần kiểm soát gì?

*Gợi ý:* Source generation và destination generation/existence qua preconditions được API hỗ trợ, đồng thời kiểm tra IAM.

**Câu 13.** Một API cập nhật hai objects A và B; cả hai PUT đều atomic. Có nghĩa cặp thao tác là transaction không?

*Gợi ý:* Không. Atomicity áp dụng cho từng object, không tự tạo transaction nhiều objects.

**Câu 14.** Live object có generation G2 với metageneration M1. Có nên so M1 với M5 của G1 để suy ra G2 có metadata “cũ hơn” không?

*Gợi ý:* Không. Metageneration chỉ có ý nghĩa trong cùng generation.

**Câu 15.** Cloud Storage CAS phù hợp với trường hợp nào hơn: cập nhật manifest ít tranh chấp hay counter thay đổi hàng nghìn lần/giây bởi nhiều workers?

*Gợi ý:* Manifest ít tranh chấp. Counter nóng cần cơ chế transaction/counter chuyên dụng như database.

## 21. Checklist áp dụng preconditions trong production

- [ ] Mọi object ghi đè quan trọng có chiến lược **CAS hoặc immutable name**.
- [ ] Upload mới dùng **`ifGenerationMatch=0`** khi cần chống tạo trùng.
- [ ] Overwrite/delete theo kết quả đọc dùng **`ifGenerationMatch=G`**.
- [ ] Metadata update dùng **cả G và M** khi cần bảo vệ trạng thái đã quan sát.
- [ ] Không dùng số generation như timestamp/sequence giữa các object.
- [ ] Không chỉ GET rồi PUT không điều kiện.
- [ ] Xử lý `412` như conflict và có chính sách reconcile, không tự bỏ điều kiện.
- [ ] Network retry giữ idempotency, có backoff và kiểm tra ambiguous success.
- [ ] Multi-range download ghim generation hoặc điều kiện đọc tương ứng.
- [ ] Copy/compose xét cả **source và destination preconditions** nếu có khả năng tranh chấp.
- [ ] Có kiểm thử hai writers đồng thời và lỗi mất response.
- [ ] Hiểu rõ Object Versioning, soft delete, retention và lifecycle không thay CAS.
- [ ] Cache-control/CDN và propagation IAM được tách khỏi strong consistency của object origin.
- [ ] Có IAM tối thiểu, ADC/WIF, audit logs, không in bí mật.
- [ ] Theo dõi 412 rate, retry, operation charges và RTO/RPO của dữ liệu cần phục hồi.
- [ ] Khi cần transaction nhiều objects, đánh giá dùng database thay vì lạm dụng object updates.

## 22. Những điểm cần nhớ

- **Cloud Storage strong consistency** cho đọc/ghi, xóa, metadata và list object **không tự ngăn hai writers ghi đè lẫn nhau**.
- **`generation`** định danh phiên bản dữ liệu object; mỗi lần overwrite tạo generation khác, không giả định giá trị luôn tăng.
- **`metageneration`** đếm những lần thay đổi metadata của **một generation**; bắt đầu từ 1 và phải xét cùng generation.
- **`ifGenerationMatch=0`** là create-if-absent đối với **live object**.
- **`ifGenerationMatch=G`** là compare-and-swap cho write/delete khi trạng thái G còn đúng.
- **`ifMetagenerationMatch=M`** nên đi cùng generation-match khi cập nhật metadata.
- **`412 Precondition Failed`** là bảo vệ khỏi xung đột; ứng dụng phải re-read và quyết định, không mặc định ghi đè.
- **Retry có điều kiện** giúp tránh thao tác không idempotent hoặc response bị mất làm hỏng dữ liệu.
- **Atomicity từng object khác transaction nhiều objects**; read theo range phải ghim generation để không ghép nhiều phiên bản.
- **Object Versioning, soft delete, IAM, retention, cache và Billing** là những lớp khác, bổ sung nhưng không thay thế preconditions.

Trong các hệ thống Java chạy trên Compute Engine, GKE hay Cloud Run, câu hỏi quan trọng trước khi ghi một object không chỉ là **“mình có quyền ghi không?”**, mà còn là **“đây có còn là đúng version mình đã đọc không, và nếu người khác đã ghi trước thì quy tắc nghiệp vụ xử lý thế nào?”** Preconditions biến câu trả lời thành điều kiện được kiểm tra ngay tại Cloud Storage.

## Tài liệu tham khảo chính thức

- [Cloud Storage consistency](https://cloud.google.com/storage/docs/consistency)
- [Request preconditions](https://cloud.google.com/storage/docs/request-preconditions)
- [Object metadata: generation and metageneration](https://cloud.google.com/storage/docs/metadata)
- [Cloud Storage retry strategy](https://cloud.google.com/storage/docs/retry-strategy)
- [Object Versioning](https://cloud.google.com/storage/docs/object-versioning)
- [Soft delete](https://cloud.google.com/storage/docs/soft-delete)
- [Object Lifecycle Management](https://cloud.google.com/storage/docs/lifecycle)
- [Control data lifecycles](https://cloud.google.com/storage/docs/control-data-lifecycles)
- [Upload objects from memory — Java sample](https://cloud.google.com/storage/docs/samples/storage-file-upload-from-memory)
- [Set object metadata — Java sample](https://cloud.google.com/storage/docs/samples/storage-set-metadata)
- [gcloud storage cp](https://cloud.google.com/sdk/gcloud/reference/storage/cp)
- [gcloud storage objects update](https://cloud.google.com/sdk/gcloud/reference/storage/objects/update)
- [gcloud storage rm](https://cloud.google.com/sdk/gcloud/reference/storage/rm)
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing)


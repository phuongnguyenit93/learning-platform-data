# Resumable uploads, compose và xử lý tệp lớn

Một ứng dụng học trực tuyến có thể cần nhận video dung lượng nhiều GiB, dữ liệu huấn luyện, bản sao lưu hoặc các tệp phân tích được tạo liên tục. Nếu gửi toàn bộ tệp qua một yêu cầu HTTP duy nhất, mất kết nối ở gần cuối quá trình có thể khiến người dùng phải tải lại từ đầu. Với những luồng dữ liệu chia thành nhiều mảnh, ứng dụng còn phải biết cách ghép chúng **đúng thứ tự**, tránh ghi đè nhầm và chứng minh nội dung cuối không bị hỏng.

**Cloud Storage** trong module **CLOUD_PROVIDERS_GCP** cung cấp các cơ chế phục vụ bài toán này: **resumable uploads** để tiếp tục truyền dữ liệu sau gián đoạn, **compose** để nối các object đã có trong bucket, và **parallel composite uploads** để tăng tốc tải lên trong những tình huống phù hợp.

Bài thuộc chương **Cloud Storage**, nằm trong lộ trình học Google Cloud từ project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ, phát hành, bảo mật và theo dõi độ tin cậy cùng chi phí. Trọng tâm không chỉ là câu lệnh upload: người học phải hiểu tính đúng đắn của dữ liệu, phân quyền, giới hạn sản phẩm, đường truyền và vòng đời các object tạm.

**Sau bài học, bạn có thể:**

1. Phân biệt resumable upload, compose, parallel composite upload và XML API multipart upload.
2. Mô tả trạng thái của một resumable session, cách xác định byte đã được lưu và cách tiếp tục mà không ghi sai offset.
3. Ghép các object bằng compose theo đúng thứ tự và hiểu giới hạn tối đa 32 nguồn mỗi lần.
4. Dùng generation preconditions, CRC32C và những kiểm tra ứng dụng để chống ghi đè, race condition và sai lệch nội dung.
5. Thiết kế luồng tải tệp lớn qua backend hoặc trực tiếp từ client với IAM, session URI và quyền truy cập an toàn.
6. Ước tính ảnh hưởng của lưu lượng mạng, thao tác API, object tạm, retention, soft delete và Object Versioning đến chi phí.
7. Thực hành upload, compose, xác minh kết quả và dọn tài nguyên trong bucket lab.

## 1. Tệp lớn trong Cloud Storage là một object, không phải disk block

Cloud Storage lưu dữ liệu dưới dạng **object** trong một **bucket**. Mỗi object có tên, nội dung, metadata, generation và những thuộc tính quản lý khác. Khác với Hyperdisk, object không được gắn như block device để ứng dụng sửa tùy ý từng sector; thay đổi nội dung thường tạo một phiên bản object mới thông qua thao tác ghi/compose/rewrite tương ứng.

| Khái niệm | Ý nghĩa trong bài |
| --- | --- |
| **Bucket** | Vùng chứa object với location, storage class mặc định, IAM, lifecycle và chính sách bảo vệ dữ liệu. |
| **Object name** | Đường dẫn logic, ví dụ `videos/course-42/lesson-01.mp4`; prefix dạng thư mục không mặc nhiên là thư mục hệ điều hành. |
| **Generation** | Số định danh của một phiên bản **nội dung** object; dùng làm điều kiện chống ghi đè/race condition. |
| **Metageneration** | Phiên bản thay đổi metadata object; khác generation của dữ liệu. |
| **CRC32C** | Checksum phục vụ phát hiện lỗi dữ liệu trong quá trình truyền/lưu. |
| **Resumable session URI** | URL của phiên truyền dữ liệu đang mở, có tác dụng như bearer secret. |
| **Composite object** | Object mới tạo bằng cách nối byte của những source objects trong cùng bucket theo đúng thứ tự. |

**Giới hạn kích thước:** Cloud Storage giới hạn một object ở mức **5 TiB**, bất kể được tạo bằng upload thường, resumable upload, compose hay XML multipart upload. Muốn lưu bộ dữ liệu lớn hơn, thiết kế nhiều object cùng manifest/index thay vì cố tạo một object duy nhất vượt giới hạn.

### 1.1. Ba tình huống khác nhau

**Tình huống A — Mạng không ổn định:** người dùng tải video 6 GiB từ laptop. Cần tiếp tục từ đoạn đã được Cloud Storage ghi nhận khi kết nối mất. Chọn **resumable upload**.

**Tình huống B — Dữ liệu đã chia thành object:** hệ thống nhận `part-0001`, `part-0002` và `part-0003` vào bucket. Cần tạo một object mới có nội dung lần lượt bằng các phần này. Chọn **compose**.

**Tình huống C — Muốn tận dụng nhiều luồng mạng:** máy có CPU, ổ đĩa và băng thông đủ lớn. Công cụ chia file nguồn thành các đoạn, tải chúng **song song lên object tạm**, sau đó compose thành object cuối. Đây là **parallel composite upload**; không đồng nghĩa với một resumable session duy nhất.

### 1.2. Bảng chọn phương thức ghi object

| Phương thức | Mô hình | Khả năng phục hồi | Lưu ý |
| --- | --- | --- | --- |
| **Simple/multipart request** của JSON API | Truyền object trong một request; multipart JSON API còn kèm metadata. | Nếu request thất bại thường phải thử lại việc gửi dữ liệu. | Hợp với object nhỏ; “multipart JSON API” không phải upload nhiều phần song song. |
| **Resumable upload** | Tạo session rồi gửi byte vào session bằng một hoặc nhiều yêu cầu nối tiếp. | Hỏi server về offset đã lưu rồi tiếp tục. | Phù hợp upload lớn, nguồn không ổn định và nguồn stream. |
| **Compose** | Kết hợp những object đã tồn tại. | Không truyền lại toàn bộ bytes của các source objects qua client. | 1–32 nguồn/lần, cùng bucket, thứ tự là quan trọng. |
| **Parallel composite upload** | Chia tệp, upload các object tạm song song, compose cuối. | Có thể phục hồi upload từng thành phần theo công cụ. | Tạo/xóa object tạm; yêu cầu IAM, checksum và chính sách bucket phù hợp. |
| **XML API multipart upload** | Bắt đầu một upload, gửi các part theo API XML, hoàn thành hoặc hủy. | Có thể gửi lại/tiếp tục ở cấp part theo giao thức. | Khác JSON API multipart và khác compose; cân nhắc khi hệ thống hỗ trợ. |

Không có phương thức nào tốt nhất cho mọi tệp. Hãy chọn dựa trên **kích thước, độ ổn định mạng, yêu cầu toàn vẹn dữ liệu, IAM, tính năng bucket, giá và khả năng của client**.

## 2. Resumable upload: vòng đời và các trạng thái

Với JSON API, một resumable upload thường có hai giai đoạn: **khởi tạo session** và **truyền nội dung**. Session ghi nhớ phần dữ liệu đã được chấp nhận để client có thể tiếp tục sau khi bị mất kết nối.

~~~mermaid
sequenceDiagram
    participant C as Client / uploader
    participant S as Cloud Storage
    C->>S: POST tạo resumable session (đã xác thực)
    S-->>C: 200 OK + Location: SESSION_URI
    C->>S: PUT chunk 0..N (SESSION_URI)
    S-->>C: 308 Resume Incomplete + Range
    Note over C,S: Mất kết nối hoặc timeout
    C->>S: PUT status query, Content-Range: bytes */TOTAL
    S-->>C: 308 + Range: bytes=0-K
    C->>S: PUT bytes K+1.. cuối, đúng Content-Range
    S-->>C: 200/201 + object metadata
    C->>S: GET metadata / kiểm tra checksum
    S-->>C: Generation, size, CRC32C
~~~

### 2.1. Khởi tạo session

Client được xác thực dùng endpoint JSON API với `uploadType=resumable`. Cloud Storage trả về **`Location` header** chứa session URI. URI này có thể được sử dụng cho các yêu cầu PUT tiếp theo mà không phải ký lại từng chunk theo cách khởi tạo thông thường.

**Session URI là bí mật có quyền upload.** Bất kỳ ai có URI hợp lệ có thể tiếp tục tải dữ liệu vào đích của session mà không cần thêm credential cho các yêu cầu chunk. Vì vậy:

- Chỉ dùng HTTPS; không chuyển URI sang HTTP.
- Không ghi URI vào application log, URL truy cập công khai, analytics, crash report hoặc nơi không được kiểm soát.
- Nếu lưu phục vụ tiếp tục upload sau khi ứng dụng tắt, mã hóa và bảo vệ nó như một bearer token, giới hạn thời gian và chủ sở hữu.
- Không chia sẻ session URI giữa người dùng hoặc những request không cùng upload.
- Nếu nghi lộ URI, hủy session khi có thể và tạo session mới.

**Hiệu lực:** session URI hết hạn sau **một tuần** kể từ lúc khởi tạo. Với session không còn hợp lệ, API có thể trả `410 Gone` hoặc `404 Not Found` theo thời điểm/trường hợp. Khi đó cần tạo session mới và gửi lại từ đầu; không tái sử dụng offset của session cũ.

### 2.2. Gửi dữ liệu một lần hoặc theo chunk

Một resumable session có thể nhận toàn bộ dữ liệu trong **một PUT** hoặc nhiều PUT nối tiếp. Nếu chia chunk, kích thước mỗi chunk **ngoại trừ chunk cuối** cần là bội số **256 KiB**. Tài liệu Google Cloud khuyến nghị cân nhắc chunk **từ 8 MiB** để tránh overhead quá lớn; chunk lớn hơn dùng nhiều bộ nhớ hoặc buffer hơn.

Ví dụ tệp có kích thước **20.000.000 bytes** và chọn chunk đầu tiên **8 MiB = 8.388.608 bytes**:

~~~http
PUT SESSION_URI HTTP/1.1
Content-Length: 8388608
Content-Range: bytes 0-8388607/20000000

<8388608 bytes đầu tiên của tệp>
~~~

Phản hồi khi server chưa nhận hết object có thể là:

~~~http
HTTP/1.1 308 Resume Incomplete
Range: bytes=0-8388607
~~~

**Phân biệt status:** `308 Resume Incomplete` của Cloud Storage là trạng thái upload **chưa xong**, không phải HTTP redirect mà client cần tự đi theo. Khi nhận `200 OK` hoặc `201 Created` sau PUT cuối, object đã hoàn thành theo giao thức và cần xác minh metadata/checksum.

### 2.3. Server là nguồn sự thật về offset đã lưu

Giả sử client đã gửi 8 MiB nhưng kết nối mất trước khi nhận phản hồi. Client **không được tự đoán** rằng cả chunk đã lưu, cũng không được giả định server chưa lưu byte nào. Cần gửi **status query** tới đúng session URI:

~~~http
PUT SESSION_URI HTTP/1.1
Content-Length: 0
Content-Range: bytes */20000000
~~~

Nếu server trả:

~~~http
HTTP/1.1 308 Resume Incomplete
Range: bytes=0-4194303
~~~

thì server xác nhận đã lưu **4.194.304 bytes**, với byte cuối là **4.194.303**. Yêu cầu tiếp theo phải bắt đầu ở **byte 4.194.304**, không tự động bắt đầu tại 8 MiB.

Nếu `308` **không có `Range`**, chưa có byte nào được server ghi nhận và client gửi từ byte 0. Nếu server báo `200`/`201`, upload đã hoàn thành; không tiếp tục PUT thêm dữ liệu. Nếu session không tồn tại/hết hạn, tạo session mới và truyền lại dữ liệu nguồn.

### 2.4. Không đổi nội dung nguồn giữa các lần resume

Khi Cloud Storage đã lưu một khoảng byte trong session, nó không cho phép ghi đè khoảng đó bằng nội dung mới. Nếu file nguồn thay đổi sau khi đã upload một phần, việc gửi phần còn lại từ phiên bản mới có thể tạo object **ghép từ hai phiên bản không tương thích**.

Biện pháp:

1. Khóa hoặc snapshot file nguồn ở phía client trong suốt quá trình tải lên.
2. Lưu **size, mtime và fingerprint/checksum** của file nguồn cùng upload job; từ chối resume nếu nguồn bị thay đổi.
3. Sau khi hoàn thành, so checksum và size của object cuối với bản nguồn ổn định.
4. Nếu nghi nguồn đã thay đổi, hủy session và tạo upload mới từ đầu.

### 2.5. Chunk nhỏ, chunk lớn và độ ổn định mạng

| Quyết định | Lợi ích | Chi phí/đánh đổi |
| --- | --- | --- |
| Một PUT lớn trong resumable session | Ít round trip và overhead. | Retry có thể phải xử lý lại một phần lớn khi kết nối đứt. |
| Chunk 256 KiB | Giảm buffer, phù hợp giới hạn client hẹp. | Nhiều request và xác nhận offset; overhead lớn. |
| Chunk 8–64 MiB | Thường cân bằng throughput và bộ nhớ cho tệp lớn. | Cần buffer lớn hơn; kết quả thực tế phụ thuộc mạng/SDK. |
| Upload nhiều tệp độc lập song song | Dùng băng thông và CPU tốt hơn. | Cần kiểm soát concurrency, rate limit, quota và retry. |
| Parallel composite upload một tệp | Có thể tăng tốc khi có đủ băng thông và I/O. | Object tạm, compose, checksum CRC32C, quyền xóa và chi phí. |

Chọn chunk dựa trên **băng thông, RTT, độ ổn định kết nối, RAM và thời gian thử lại**, không dựa vào một con số cố định cho mọi ứng dụng. Một số thư viện còn có buffer/chunk mặc định khác nhau; hãy kiểm tra cấu hình của SDK đang sử dụng.

## 3. Dùng gcloud CLI hoặc client library thay vì tự quản lý HTTP

Với nghiệp vụ thông thường, **ưu tiên Google Cloud CLI hoặc client libraries** vì chúng đã xử lý nhiều chi tiết của resumable session, retry, streaming và kiểm tra tính toàn vẹn. Tự viết client REST chỉ phù hợp khi môi trường không dùng được SDK, cần một giao thức đặc biệt hoặc cần kiểm soát từng request.

### 3.1. Upload một tệp với gcloud

Giả định tổ chức đã cấp cho bạn **bucket lab** và quyền tải object. Trong Bash hoặc Cloud Shell:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export BUCKET_NAME="YOUR_APPROVED_LAB_BUCKET"

# Chỉ đọc cấu hình project đang được dùng
gcloud config get-value project

# Kiểm tra tệp nguồn và dung lượng trước khi upload
ls -lh ./large-video.mp4

# Thao tác ghi vào bucket đã được cấp quyền
gcloud storage cp \
  ./large-video.mp4 \
  "gs://$BUCKET_NAME/uploads/large-video.mp4"

# Đọc lại metadata của object sau khi upload
gcloud storage objects describe \
  "gs://$BUCKET_NAME/uploads/large-video.mp4" \
  --format="yaml(name,size,generation,crc32c,md5Hash,contentType)"
~~~

**Điểm cần chú ý:** `gcloud storage cp` có thể tự dùng **resumable upload** hoặc **parallel composite upload** theo kích thước tệp, cấu hình CLI và chính sách bucket. Vì vậy **không suy rằng mọi lần chạy `cp` đều tạo một session resumable duy nhất**. Nếu cần kiểm thử chính xác một cơ chế, hãy dùng cấu hình/lựa chọn công cụ được xác minh trong môi trường lab và xem tài liệu tại thời điểm thử.

Đối với dữ liệu quan trọng, hãy áp dụng **generation preconditions** hoặc một cơ chế xuất bản đối tượng không ghi đè nhầm, nhất là khi nhiều job có thể upload cùng tên. Bản sao có `generation` mới không chứng minh rằng job đã nhắm đúng phiên bản nghiệp vụ.

### 3.2. Nguyên tắc dùng client library

Một client library tốt nên được sử dụng như sau:

1. Nhận một stream hoặc file có **nguồn dữ liệu bất biến** cho cả vòng upload.
2. Đặt object name, content type, checksum/precondition và deadline phù hợp.
3. Khởi tạo resumable session qua SDK; để SDK xử lý offset/retry khi chức năng hỗ trợ.
4. Dùng exponential backoff có giới hạn cho lỗi tạm thời; không retry không giới hạn.
5. Xác minh metadata sau hoàn thành: **bucket, name, size, generation, CRC32C**.
6. Đánh dấu job thành công trong database/chỉ mục ứng dụng **sau khi** xác minh object.

Ví dụ về phân tách trách nhiệm:

~~~mermaid
flowchart LR
    JOB["Upload job / manifest"] --> SDK["Cloud Storage SDK"]
    SDK --> GCS["Cloud Storage object"]
    GCS --> VERIFY["Kiểm tra size, generation,<br/>CRC32C hoặc nội dung"]
    VERIFY --> PUB["Đánh dấu READY<br/>trong database"]
    SDK -->|"Lỗi tạm thời"| RETRY["Retry với backoff,<br/>resume đúng session"]
    RETRY --> SDK
~~~

Một request trả thành công nhưng bước cập nhật database của ứng dụng thất bại có thể dẫn đến trạng thái “object đã tồn tại nhưng job chưa READY”. Cần thiết kế thao tác **idempotent**, đọc lại metadata và kiểm tra generation thay vì upload lại vô điều kiện.

### 3.3. Giao thức JSON API khi tự xây client

Đây là **mẫu HTTP khái niệm**, không chứa access token hoặc session URI thật. Khi khởi tạo resumable upload, bên gọi cần có credential phù hợp và có thể đặt precondition để tránh ghi đè object đã tồn tại:

~~~http
POST /upload/storage/v1/b/YOUR_BUCKET/o?uploadType=resumable&name=videos%2Flesson.mp4&ifGenerationMatch=0 HTTP/1.1
Host: storage.googleapis.com
Authorization: Bearer ACCESS_TOKEN
Content-Type: application/json; charset=UTF-8
X-Upload-Content-Type: video/mp4
X-Upload-Content-Length: 20000000
Content-Length: 2

{}
~~~

Một phản hồi khởi tạo thành công cung cấp header:

~~~http
HTTP/1.1 200 OK
Location: https://storage.googleapis.com/upload/storage/v1/b/YOUR_BUCKET/o?uploadType=resumable&upload_id=SECRET_SESSION_ID
~~~

`ifGenerationMatch=0` là điều kiện **chỉ tạo nếu tại thời điểm áp dụng không có live object cùng tên**. Nó giúp tránh việc một lần retry hoặc upload song song ghi đè bản đã tồn tại. Nếu muốn cập nhật có điều kiện, dùng **generation cụ thể** đã đọc và thiết kế xử lý `412 Precondition Failed`.

Trong thực tế, header khởi tạo, encoding tên object và body còn phụ thuộc API/metadata bạn chọn. Với một client tự viết, cần theo đúng tài liệu JSON API về initiation, upload bytes, query trạng thái và hủy session, thay vì chỉ sao chép ví dụ minh họa mà bỏ qua xử lý lỗi.

### 3.4. Xử lý status codes

| Tình huống | HTTP response thường gặp | Hành động |
| --- | --- | --- |
| Tạo resumable session | `200 OK` kèm `Location` | Lưu session URI an toàn, tiếp tục upload. |
| Chunk chưa hoàn thành | `308 Resume Incomplete` | Đọc `Range`; gửi byte tiếp theo sau byte cuối đã lưu. |
| Upload hoàn thành | `200 OK` hoặc `201 Created` | Xác minh size, checksum, generation và nghiệp vụ. |
| Token khởi tạo không hợp lệ | `401 Unauthorized` hoặc `403 Forbidden` | Kiểm tra credential, IAM, chính sách bucket. |
| Đụng generation precondition | `412 Precondition Failed` | Đọc lại object hiện tại; quyết định nghiệp vụ, không tự overwrite. |
| Session cũ đã hết hạn/hủy | `404 Not Found` hoặc `410 Gone` tùy trường hợp | Khởi tạo lại từ đầu, không dùng offset cũ. |
| `429` hoặc lỗi `5xx` tạm thời | Rate limit hoặc lỗi dịch vụ/kết nối | Backoff có jitter, hỏi trạng thái trước khi gửi lại byte. |
| Cấu hình `Content-Range` sai | `400 Bad Request` | Sửa logic range và kiểm tra session có còn hợp lệ không. |

**Retry an toàn:** sau timeout hoặc mất phản hồi, client cần phân biệt “server chưa nhận”, “server đã nhận một phần” và “object đã hoàn thành”. Với những thao tác có điều kiện, retry theo đúng **generation precondition** giúp tránh tạo kết quả sai trong trường hợp job được thực thi lặp lại.

## 4. Compose: nối object server-side theo đúng thứ tự

**Compose** tạo một object mới có nội dung là phép **nối byte trực tiếp** của các source objects. Cloud Storage thực hiện phép nối ở phía dịch vụ nên ứng dụng không phải tải toàn bộ parts về máy rồi upload lại file cuối.

Ví dụ:

~~~text
gs://course-bucket/parts/video/0001   -> "AAA"
gs://course-bucket/parts/video/0002   -> "BBB"
gs://course-bucket/parts/video/0003   -> "CCC"
                                      -----------------
gs://course-bucket/videos/final.bin   -> "AAABBBCCC"
~~~

Compose **không phải** bộ giải mã video, bộ ghép file ZIP hoặc công cụ merge CSV có hiểu cú pháp. Nó chỉ nối byte. Nếu mỗi part có header riêng, việc nối có thể tạo file không hợp lệ. Ứng dụng phải bảo đảm định dạng dữ liệu cho phép nối byte, hoặc chuẩn bị parts sao cho khi ghép sẽ thành một file hợp lệ.

### 4.1. Điều kiện và giới hạn của một lần compose

1. Mỗi request nhận **1 đến 32 source objects**; việc ghép được thực hiện **theo đúng thứ tự khai báo**.
2. Các source objects phải ở **cùng một bucket** và có **cùng storage class**. Destination cũng thuộc bucket ấy theo Compose API.
3. Source có thể là **composite object** từ lần compose trước, nên có thể dùng nhiều tầng compose khi số part lớn hơn 32.
4. Object đích vẫn tuân theo giới hạn **5 TiB** và các ràng buộc bucket khác.
5. Source objects **không tự bị xóa** sau compose mặc định; phải tự quyết định khi nào xóa.
6. Nếu object name đích đã tồn tại, phải dùng **generation precondition** để bảo vệ dữ liệu tránh ghi đè.
7. Sau compose, object đích độc lập về nội dung: xóa hoặc ghi đè source không thay đổi bytes của object đích đã hoàn thành.

### 4.2. Ví dụ compose bằng gcloud

Giả sử ba object đã có trong một bucket lab và các part thật sự có thể nối byte:

~~~bash
export BUCKET_NAME="YOUR_APPROVED_LAB_BUCKET"

# Chỉ đọc: xác nhận các part, kích thước và generation
gcloud storage objects describe "gs://$BUCKET_NAME/parts/demo/0001"
gcloud storage objects describe "gs://$BUCKET_NAME/parts/demo/0002"
gcloud storage objects describe "gs://$BUCKET_NAME/parts/demo/0003"

# Thao tác ghi: ghép ba object theo THỨ TỰ được liệt kê
gcloud storage objects compose \
  "gs://$BUCKET_NAME/parts/demo/0001" \
  "gs://$BUCKET_NAME/parts/demo/0002" \
  "gs://$BUCKET_NAME/parts/demo/0003" \
  "gs://$BUCKET_NAME/final/demo.bin"

# Chỉ đọc: xác minh object cuối
gcloud storage objects describe \
  "gs://$BUCKET_NAME/final/demo.bin" \
  --format="yaml(name,size,generation,componentCount,crc32c,md5Hash,contentType)"
~~~

Đây là bản demo căn bản. **Nếu nhiều uploader cùng dùng tên parts hoặc destination, không chạy lệnh compose không precondition như một workflow production.** Hãy dùng generation cụ thể của từng part và `ifGenerationMatch` của destination qua API/client library, hoặc cơ chế được công cụ hỗ trợ để bảo vệ tính nhất quán.

### 4.3. Composite object không có MD5 metadata

Sau compose, object kết quả là **composite object**. Điểm khác quan trọng:

- Composite object có **CRC32C** do Cloud Storage cung cấp, nhưng **không có trường MD5 metadata**.
- Không được coi **ETag** của composite object là MD5 của nội dung.
- `componentCount` cho biết số thành phần cấu thành theo cơ chế metadata; số này có thể tăng khi compose nhiều tầng.
- Khi dùng công cụ tải xuống tự viết, cần kiểm tra **CRC32C** hoặc checksum đầu-cuối khác do ứng dụng tự quản lý thay vì giả định luôn có MD5 trong Cloud Storage.

CRC32C có ích để **phát hiện lỗi truyền/lưu dữ liệu**, nhưng không phải cơ chế xác thực chống chỉnh sửa có chủ đích. Nếu cần bảo đảm tính xác thực nguồn cung cấp, dùng chữ ký số, hash có quy trình tin cậy, hoặc cơ chế bảo vệ artifact ngoài CRC32C.

### 4.4. Object metadata sau compose

Object đích có metadata riêng, chẳng hạn `Content-Type`, cache policy, custom metadata, generation và storage class. Khi dùng `gcloud storage objects compose`, `Content-Type` của object kết quả mặc định theo object nguồn đầu tiên, trừ khi được chỉ định cấu hình khác.

Do đó, nếu bạn compose ba phần của video nhưng part đầu tiên mang `application/octet-stream`, đừng kỳ vọng trình duyệt tự nhận diện kết quả là `video/mp4`. Hãy xác minh và đặt metadata đích theo quy trình được hỗ trợ. Với object công khai qua Cloud CDN, content type và cache headers có thể ảnh hưởng cách phát nội dung.

Không đưa thông tin nhạy cảm, mật khẩu hoặc upload session URI vào custom metadata. Việc đọc metadata qua IAM, signed URL hoặc cấu hình công khai phải được xem xét trong thiết kế phân quyền.

## 5. Ghép nhiều hơn 32 parts và chống race condition

### 5.1. Compose nhiều tầng

Giới hạn **32 nguồn mỗi request** không có nghĩa một composite object chỉ được tạo từ tối đa 32 phần nguyên thủy. Source của một lần compose có thể là kết quả compose trước. Ví dụ có 75 object `part-0000` đến `part-0074`:

~~~mermaid
flowchart TB
    A["part-0000 ... part-0031<br/>32 parts"] --> T1["intermediate-A"]
    B["part-0032 ... part-0063<br/>32 parts"] --> T2["intermediate-B"]
    C["part-0064 ... part-0074<br/>11 parts"] --> T3["intermediate-C"]
    T1 --> F["final-object<br/>compose A,B,C"]
    T2 --> F
    T3 --> F
~~~

Luồng thực hiện:

1. Tải/xác minh 75 parts vào cùng bucket, cùng storage class và bảo đảm kích thước tổng không vượt 5 TiB.
2. Compose parts 0–31 thành `intermediate-A`.
3. Compose parts 32–63 thành `intermediate-B`.
4. Compose parts 64–74 thành `intermediate-C`.
5. Compose ba intermediate theo thứ tự A → B → C để xuất bản kết quả.
6. **Sau khi kiểm tra object cuối**, xử lý intermediate và parts tạm theo chính sách dữ liệu và quyền xóa.

Số lần compose của ví dụ là **4** (ba lần tạo intermediate, một lần tạo cuối). Cần tính operation charges, object tạm và lifecycle; không chỉ cộng kích thước file cuối. Số thành phần cấu thành composite object có thể lớn hơn 32, nhưng số nguồn của **mỗi lần compose** vẫn không vượt 32 và object cuối không vượt 5 TiB.

### 5.2. Đặt tên part có thứ tự rõ ràng

Một scheme dễ kiểm soát:

~~~text
staging/uploads/UPLOAD_ID/manifest.json
staging/uploads/UPLOAD_ID/parts/000000
staging/uploads/UPLOAD_ID/parts/000001
staging/uploads/UPLOAD_ID/parts/000002
...
staging/uploads/UPLOAD_ID/intermediate/000000
published/videos/lesson-042.mp4
~~~

Lưu ý:

- `UPLOAD_ID` phải phân biệt từng upload job; không dùng một prefix chung cho toàn bộ khách hàng.
- Đặt tên part với số **zero-padded**, tránh việc sắp xếp chuỗi `part-1, part-10, part-2` gây sai thứ tự.
- **Manifest** cần ghi rõ part index, source object name, **generation**, size, checksum và tổng size dự kiến.
- Không tin vào thứ tự tùy ý của kết quả list object; compose bằng **thứ tự manifest**.
- Không cho client tự ý cung cấp object path của tenant khác mà backend không xác thực quyền sở hữu.

### 5.3. Generation preconditions để chống thay đổi nguồn

**Race condition:** giữa lúc hệ thống kiểm tra `part-0001` và lúc thực hiện compose, một worker khác tải lại cùng tên với bytes khác. Nếu compose “live object mới nhất” mà không kiểm tra generation, kết quả có thể trộn dữ liệu sai.

**Giải pháp:** ghi nhận generation của từng part sau upload, dùng **đúng generation** khi compose và đặt điều kiện đích chưa có (hoặc trùng generation dự kiến).

Ví dụ **ý tưởng JSON API** (giá trị generation phải lấy từ metadata thực tế, không tự đoán):

~~~http
POST /storage/v1/b/YOUR_BUCKET/o/final%2Fdemo.bin/compose?ifGenerationMatch=0 HTTP/1.1
Host: storage.googleapis.com
Authorization: Bearer ACCESS_TOKEN
Content-Type: application/json

{
  "sourceObjects": [
    {
      "name": "parts/demo/0001",
      "generation": "1700000000000001",
      "objectPreconditions": {"ifGenerationMatch": "1700000000000001"}
    },
    {
      "name": "parts/demo/0002",
      "generation": "1700000000000002",
      "objectPreconditions": {"ifGenerationMatch": "1700000000000002"}
    }
  ],
  "destination": {"contentType": "application/octet-stream"}
}
~~~

Đây là ví dụ cấu trúc request, **không chứa generation hoặc token thật** và không dùng trực tiếp để ghi vào một bucket có dữ liệu quan trọng. Với mỗi source, generation/precondition bảo vệ khỏi việc lấy nhầm phiên bản. Với destination, `ifGenerationMatch=0` giúp từ chối thao tác nếu object đích đã có phiên bản live.

Nếu nhận **`412 Precondition Failed`**, đừng chỉ bỏ điều kiện rồi thử lại. Phải xác minh:

- Có uploader nào đã xuất bản thành công cùng tên?
- Source object đã bị thay thế hoặc xóa?
- Job hiện tại có trùng upload ID hay đang xử lý một yêu cầu khác?
- Có nên trả trạng thái “đã hoàn thành” bằng object cũ sau khi kiểm tra manifest/checksum, hay cần tạo một tên đích mới?

**Tính idempotent của publish:** khi timeout xảy ra sau khi server đã compose thành công nhưng client chưa nhận phản hồi, việc retry với `ifGenerationMatch=0` có thể trả 412. Đây có thể là trạng thái **đã có kết quả đúng**, không phải lỗi đòi ghi đè. Hãy đọc metadata đích và đối chiếu generation, size, manifest và checksum để đưa ra quyết định.

### 5.4. Trạng thái upload job và điều kiện xóa parts

Một workflow bền vững có thể có các trạng thái:

~~~mermaid
flowchart LR
    NEW["NEW"] --> UP["UPLOADING"]
    UP --> READY["PARTS_VERIFIED"]
    READY --> CP["COMPOSING"]
    CP --> DONE["PUBLISHED"]
    UP --> FAIL["FAILED / ABORTED"]
    CP --> REVIEW["RETRY / CHECK DESTINATION"]
    REVIEW --> CP
    DONE --> CLEAN["CLEANED"]
~~~

Đừng xóa source objects chỉ vì **lệnh compose đã được gửi**. Chỉ xóa sau khi xác minh API/metadata và **chính sách dữ liệu cho phép**, hoặc dùng cơ chế hard-delete source trong compose có chủ đích khi phù hợp. Cần tránh worker dọn parts tạm trong khi worker compose khác vẫn đang sử dụng chúng.

## 6. Parallel composite uploads: tải nhiều phần song song

**Parallel composite upload (PCU)** kết hợp hai cơ chế đã học:

1. Chia tệp nguồn thành tối đa **32** đoạn cho một compose cuối theo cơ chế công cụ.
2. Tải nhiều đoạn **song song** thành những object tạm.
3. Dùng `compose` để tạo composite object cuối.
4. Xóa các object tạm theo chính sách sau khi xác minh hoàn thành.

~~~mermaid
flowchart LR
    FILE["Một tệp lớn trên client"] --> SPLIT["Chia đoạn"]
    SPLIT --> C1["Chunk 1 → tmp object 1"]
    SPLIT --> C2["Chunk 2 → tmp object 2"]
    SPLIT --> C3["Chunk N → tmp object N"]
    C1 --> CP["Cloud Storage compose"]
    C2 --> CP
    C3 --> CP
    CP --> FINAL["Composite object cuối"]
    CP -. "Sau kiểm tra, dọn parts tạm" .-> TMP["Temporary objects"]
~~~

Khi băng thông WAN và tốc độ đọc file nguồn đủ cao, nhiều upload song song có thể giảm thời gian so với một luồng. Nhưng với một laptop mạng yếu, hệ thống lưu trữ chậm hoặc kết nối có giới hạn, mở nhiều luồng có thể **không nhanh hơn** và còn làm tăng chi phí/khả năng lỗi.

### 6.1. Hành vi của gcloud storage

Theo tài liệu `gcloud storage cp` hiện hành, việc dùng PCU phụ thuộc cấu hình và kiểm tra tương thích. Những property quan trọng:

| Property của gcloud | Ý nghĩa |
| --- | --- |
| `storage/parallel_composite_upload_enabled` | Bật/tắt hoặc sử dụng chế độ mặc định của PCU. |
| `storage/parallel_composite_upload_threshold` | Kích thước file tối thiểu để gcloud cân nhắc PCU; mặc định **150 MiB** theo tài liệu hiện hành. |
| `storage/parallel_composite_upload_component_size` | Kích thước tối đa dự kiến của mỗi part tạm; công cụ vẫn phải thỏa giới hạn 32 parts. |
| `storage/parallel_composite_upload_component_prefix` | Prefix đặt tên những object tạm. |
| `storage/parallel_composite_upload_compatibility_check` | Cho phép kiểm tra bucket trước khi PCU theo chính sách an toàn của công cụ. |

Gcloud kiểm tra những điều kiện tương thích như **storage class Standard**, **bucket không có retention policy** và **không có default object holds** khi cơ chế compatibility check hoạt động. Khi không đủ quyền `storage.buckets.get` để kiểm tra, công cụ có thể **fallback sang upload thường** thay vì PCU.

**Không nên tắt compatibility check chỉ để làm PCU chạy trên bucket production** nếu chưa hiểu soft delete, retention, quyền xóa parts và hậu quả chi phí. Đặc biệt, việc bật PCU không bắt buộc cho mọi upload: đây là quyết định hiệu năng sau khi thử nghiệm.

### 6.2. Quyền IAM của PCU khác upload một object thông thường

Một resumable upload tạo object mới thường cần quyền **tạo object** phù hợp. Nhưng PCU còn phải:

- Tạo nhiều object tạm.
- Đọc metadata/điều kiện của source và có thể kiểm tra thông tin bucket.
- Compose các source.
- Xóa temporary objects sau khi hoàn thành.

Vì vậy principal chỉ có `roles/storage.objectCreator` có thể **upload thường thành công** nhưng không đủ quyền để thực hiện toàn bộ PCU. Một role như `roles/storage.objectUser` chứa những quyền phù hợp với nhiều thao tác trên object, nhưng việc **kiểm tra bucket-level compatibility** của CLI có thể còn yêu cầu `storage.buckets.get` theo cấu hình. Thiết kế quyền nên giới hạn trong đúng bucket/prefix được phê duyệt nếu cơ chế IAM cho phép, không cấp Storage Admin toàn project chỉ để khắc phục một lỗi của CLI.

### 6.3. PCU không luôn thay thế resumable upload

| Tiêu chí | Một resumable session | Parallel composite upload |
| --- | --- | --- |
| Truyền byte | Một luồng có thể chia thành nhiều PUT nối tiếp | Nhiều object tạm upload song song |
| Resume | Từ offset server xác nhận trong session | Mỗi phần có workflow upload/retry riêng; tool quản lý phần đã xong |
| Object cuối | Object thường, tùy cách upload | **Composite object** |
| MD5 metadata | Có thể có với object thường khi điều kiện hỗ trợ | **Không có** ở composite object |
| CRC32C | Dùng để kiểm tra tính toàn vẹn | Đặc biệt quan trọng cho từng part và object cuối |
| Dữ liệu trung gian trong bucket | Không cần tạo nhiều source objects tạm | Có; cần xử lý vòng đời và quyền xóa |
| Retention/soft delete | Phụ thuộc chính sách object cuối | Có thêm tác động lên từng object tạm |
| Khi phù hợp | Upload lớn, resume đáng tin, quyền đơn giản | Tải rất lớn, mạng đủ nhanh, bucket và IAM tương thích |

PCU có thể tăng tốc upload nhưng cũng làm phát sinh **phí thao tác, lưu trữ tạm, xử lý đối tượng bị giữ lại và công việc dọn dẹp**. Hãy đo thời gian, số thao tác và tổng chi phí trước khi bật rộng rãi.

### 6.4. Những trường hợp không nên dùng PCU

- Bucket có **retention policy** khiến parts tạm không thể xóa đúng lúc.
- Bucket bật **default object holds**, cần giải phóng holds trước khi xóa.
- Soft delete hoặc Object Versioning làm việc xóa parts tạm sinh thêm bản được giữ lại/tính phí.
- Ứng dụng tải xuống kỳ vọng object luôn có **MD5 metadata**.
- Đường mạng của uploader chỉ đủ cho một luồng hoặc nguồn đọc file không đáp ứng nhiều luồng.
- Workload yêu cầu quy trình kiểm tra checksum/định dạng đầu-cuối khác mà công cụ PCU hiện tại chưa đáp ứng.

Nếu bucket dùng lớp lưu trữ có **minimum storage duration**, object tạm bị xóa sớm có thể chịu early deletion charges. Đây là lý do nên cân nhắc Standard cho parts tạm; mọi thay đổi storage class và chính sách dữ liệu cần được đội sở hữu bucket duyệt.

## 7. Kiểm tra tính toàn vẹn: size, generation, CRC32C và manifest

“Upload báo thành công” chưa phải kết luận cuối cùng về dữ liệu. Với tệp lớn được tải trong nhiều phút/giờ, cần có **kiểm tra trước, trong và sau** để phát hiện file nguồn thay đổi, lỗi mạng, part sai thứ tự hoặc kết quả compose không đúng yêu cầu.

### 7.1. CRC32C và MD5 khác nhau

| Thuộc tính | Object upload thường | Composite object | Ý nghĩa |
| --- | --- | --- | --- |
| `size` | Có | Có | So số byte thực với manifest hoặc file nguồn. |
| `generation` | Có | Có | Định danh phiên bản nội dung được chấp nhận. |
| `crc32c` | Có theo metadata sản phẩm | Có | Phát hiện lỗi nội dung; tính ở client để đối chiếu. |
| `md5Hash` | Có thể có theo cơ chế upload và metadata | **Không có** | Không thể dựa vào trường MD5 đối với composite object. |
| `componentCount` | Không phải đặc tính chính | Có | Cho biết thành phần cấu thành theo metadata composite. |
| `ETag` | Có | Có | Không giả định ETag là MD5; đặc biệt sai với composite object. |

**CRC32C không phải chữ ký chống giả mạo.** Nếu cần phát hiện một bên có chủ đích thay nội dung và cập nhật checksum, phải có cơ chế xác thực nguồn độc lập (ví dụ chữ ký được kiểm tra hoặc hash lưu trong manifest đã xác thực).

### 7.2. Ba mức xác minh cần tách biệt

1. **Mỗi part:** tính hoặc ghi checksum và số byte ngay sau khi upload; lưu generation vào manifest.
2. **Sau compose:** kiểm tra size, generation và CRC32C của object cuối; so với checksum mong đợi của **toàn bộ chuỗi byte đúng thứ tự**.
3. **Khi tải xuống/sử dụng:** thư viện hoặc ứng dụng kiểm tra checksum của bytes đã nhận, nhất là đối với các client không tự xác minh. Nếu đối tượng chứa video, CSV, archive hoặc database dump, thêm bước **kiểm tra định dạng ứng dụng**.

Đối với PCU, Google Cloud yêu cầu coi trọng việc xác minh mỗi component và dữ liệu sau compose. Nếu cần một kiểm tra độc lập end-to-end, so checksum của file nguồn bất biến với object cuối hoặc tải object cuối về nơi an toàn để xác minh bằng công cụ đáng tin.

### 7.3. Tính CRC32C tại client bằng Python

Ví dụ dùng thư viện `google-crc32c` của Python để tính CRC32C của một file (được chạy tại máy xử lý dữ liệu **có sẵn file nguồn**, không yêu cầu truy cập Google Cloud):

~~~python
import base64
import google_crc32c

source_file = "/path/to/source-file.bin"
checksum = google_crc32c.Checksum()

with open(source_file, "rb") as stream:
    while True:
        block = stream.read(8 * 1024 * 1024)
        if not block:
            break
        checksum.update(block)

crc32c_base64 = base64.b64encode(checksum.digest()).decode("ascii")
print(crc32c_base64)
~~~

Trong môi trường chưa có thư viện, cần cài `google-crc32c` vào virtual environment đã được duyệt. Metadata CRC32C của Cloud Storage được biểu diễn bằng **base64 của giá trị 32-bit theo big-endian**; kết quả từ `checksum.digest()` trong ví dụ được chuyển sang base64 để so sánh với trường `crc32c` của object.

**Không dùng CRC32C giống MD5/SHA-256:** hai checksum khác nhau cả về thuật toán và cách biểu diễn. Nếu có SHA-256 nội bộ cho dữ liệu nguồn, hãy lưu hash này trong manifest có xác thực và so với bytes được xác minh ở đầu cuối, thay vì đi tìm trường SHA-256 mặc định trên object metadata.

### 7.4. Vấn đề khi compose nhiều tầng

CRC32C của object cuối phải được tính theo **chuỗi byte đã nối**, không phải nối các chuỗi CRC32C của từng part rồi băm như dữ liệu thông thường. Có thuật toán kết hợp CRC32C đúng về mặt toán học; nếu ứng dụng không tự triển khai và kiểm thử cơ chế ấy, cách an toàn là tính CRC32C trên tệp nguồn ban đầu hoặc trên một stream đọc các parts **theo đúng thứ tự**, rồi đối chiếu object cuối.

Với tệp dữ liệu có format không thể nối byte tùy ý, checksum đúng **không bảo đảm file hữu dụng**. Ví dụ hai file ZIP hợp lệ khi nối có thể không tạo ra một ZIP có đúng danh sách entry mong đợi. Kiểm tra cả manifest và format.

## 8. Thiết kế kiến trúc upload lớn an toàn

### 8.1. Backend nhận toàn bộ dữ liệu hay client tải thẳng lên bucket?

| Kiến trúc | Ưu điểm | Rủi ro/công việc |
| --- | --- | --- |
| **Client → backend → Cloud Storage** | Backend kiểm soát xác thực, nội dung và kiểm tra trong một pipeline. | Tốn băng thông và tài nguyên backend, nhất là khi nhiều video lớn; timeout/giới hạn body của gateway. |
| **Client → Cloud Storage qua cơ chế truy cập được backend cấp** | Byte không cần đi qua server ứng dụng; dễ mở rộng nhiều uploader. | Phải kiểm soát session URI, quyền upload, object name, CORS và xác minh sau upload. |
| **Uploader trên Compute Engine/GKE → Cloud Storage** | Phù hợp pipeline backend, có thể sử dụng service account và network gần bucket. | Cần quản lý concurrency, retry, location, IAM và chi phí. |
| **Batch chia parts rồi compose** | Có thể phục hồi theo part và tối ưu băng thông khi song song. | Manifest, race condition, object tạm, tính toàn vẹn và chi phí xử lý. |

Ví dụ mô hình tải video trực tiếp:

~~~mermaid
sequenceDiagram
    participant U as Client đã đăng nhập
    participant A as Application backend
    participant S as Cloud Storage
    participant Q as Job DB / manifest
    U->>A: Xin tạo upload cho lesson-42
    A->>A: Kiểm tra IAM nghiệp vụ, quota,<br/>type, size, object path
    A->>S: Khởi tạo upload session có điều kiện
    S-->>A: Session URI
    A->>Q: Lưu upload ID và owner
    A-->>U: Quyền upload có phạm vi / session URI
    U->>S: PUT bytes, có thể resume
    S-->>U: 308 hoặc 200/201
    U->>A: Báo hoàn tất (upload ID)
    A->>S: Đọc metadata object
    S-->>A: Generation, size, CRC32C
    A->>Q: Chỉ đánh dấu READY nếu xác minh hợp lệ
~~~

Điểm quan trọng: backend **không tin** client tự khai rằng upload đã thành công. Backend phải kiểm tra object bằng danh tính đủ quyền, bảo đảm đúng bucket, prefix, generation, size, checksum/manifest và chủ sở hữu nghiệp vụ.

### 8.2. Signed URL không đồng nghĩa session URI

**Signed URL** là cơ chế cho phép một thao tác Cloud Storage giới hạn theo phương thức, tài nguyên và thời hạn được ký. Trong những thiết kế upload hỗ trợ giao thức tương ứng, server có thể tạo signed URL để **khởi tạo** một resumable upload; sau khi session đã được tạo, client sử dụng **session URI** do Cloud Storage trả về.

| Thuộc tính | Signed URL | Resumable session URI |
| --- | --- | --- |
| Nguồn cấp | Phía có quyền ký cho một thao tác giới hạn | Cloud Storage trả về sau request tạo session |
| Quyền | Phương thức/tài nguyên/header/thời hạn đã ký | Tiếp tục gửi bytes trong **session upload cụ thể** |
| Bảo mật | Là URL có quyền truy cập, cần giữ kín đến khi hết hạn | Là bearer secret; ai có URI có thể sử dụng session |
| Quản lý vòng đời | Kiểm soát expiry của chữ ký và key dùng ký | Session thường hết hạn sau một tuần hoặc có thể hủy |

Đừng đặt session URI trong log analytics của trình duyệt hoặc mã nguồn công khai. Nếu client từ browser truy cập thẳng endpoint Cloud Storage, phải cấu hình **CORS** phù hợp trên bucket/giao thức, chỉ cho phép origin và method cần thiết, không dùng CORS như một biện pháp xác thực thay IAM hoặc signed authorization.

### 8.3. Giới hạn quyền để ngăn truy cập chéo giữa người dùng

Một hệ thống multi-tenant cần kiểm soát:

- Client chỉ được tạo object trong **namespace gắn với tài khoản/job của mình**, không thể chọn `../../tenant-khac` theo một string người dùng tự nhập mà backend không xác minh.
- **Generation precondition** để tránh overwrite object của người dùng khác hoặc một job đã hoàn tất.
- Quyền của service account backend ở **bucket/prefix** được giao theo các cơ chế IAM phù hợp; tránh Storage Admin toàn project nếu không cần.
- Quy trình xóa parts tạm chỉ tác động **đúng upload ID thuộc sở hữu job**, không dùng wildcard rộng có thể chạm object người khác.
- Giới hạn **kích thước, type, quota ứng dụng, số upload song song** và giới hạn băng thông để tránh abuse/cost spike.
- Sau upload, thực hiện scan nội dung, kiểm tra file type bằng bytes (không chỉ extension) và áp kiểm soát malware nếu yêu cầu.
- Chỉ chuyển object từ prefix `staging` sang trạng thái `published` sau khi kiểm tra thành công; người xem chỉ được truy cập nội dung được phép.

**Lưu trú dữ liệu:** khi xử lý video hoặc tài liệu chứa dữ liệu nhạy cảm, chọn location bucket theo chính sách và kiểm tra nơi chạy uploader, hệ thống phân tích, CDN, logs và bản sao. Việc dùng cùng bucket cho compose giúp giảm truyền dữ liệu qua client, nhưng không tự giải quyết mọi yêu cầu về data residency.

## 9. Hiệu năng, độ tin cậy và tổng chi phí upload

### 9.1. Đo thời gian, không chỉ quan sát progress bar

Một upload lớn có thể chậm ở một trong nhiều điểm:

| Tín hiệu | Nguyên nhân có thể | Cách đo/điều chỉnh |
| --- | --- | --- |
| Client đọc file nguồn chậm | Ổ đĩa local, CPU, antivirus, dữ liệu từ mạng khác | Đo tốc độ đọc liên tục, giảm tranh chấp I/O. |
| RTT lớn, nhiều chunk nhỏ | Overhead request và xác nhận offset | Tăng chunk hợp lý, giảm số round trip. |
| WAN có packet loss | Upload retry nhiều, throughput thấp | Theo dõi retry, RTT, mất gói; dùng resumable, backoff. |
| Một stream chưa khai thác hết băng thông | Giới hạn một luồng trong môi trường cụ thể | Thử PCU hoặc nhiều upload song song có giới hạn. |
| PCU nhiều part nhưng tổng thời gian tăng | Phí tạo/xóa, compose, nhiều kết nối cạnh tranh, nguồn đọc chậm | So sánh benchmark cùng một file và hạ concurrency. |
| Upload hoàn thành nhưng publish chậm | Checksum, scan nội dung, metadata query, thao tác compose nhiều tầng | Đo riêng `upload`, `compose`, `verify`, `publish`. |
| Nhiều retry 412 | Object name/generation trùng giữa các worker | Kiểm tra idempotency và chia upload ID. |
| Một số upload timeout sau vài giờ | Session expire, mất state, uploader thay đổi nguồn | Lưu state an toàn, kiểm tra session age và file fingerprint. |

### 9.2. Vị trí khởi tạo resumable session ảnh hưởng tốc độ

Resumable upload session được **gắn với vùng địa lý mà nó được khởi tạo**, theo cơ chế dịch vụ. Ví dụ backend ở một vị trí xa client có thể khởi tạo session khiến các request upload đi qua vùng đó. Nếu client tại châu Á nhưng server khởi tạo session gần Mỹ, đường upload có thể chịu thêm RTT và lưu lượng không mong muốn.

Với hệ thống có người dùng toàn cầu:

1. Xác định người dùng/uploader thực sự gửi bytes từ đâu.
2. Chọn kiến trúc khởi tạo session và nơi đặt bucket thích hợp với yêu cầu dữ liệu.
3. Đo upload p50/p95, tốc độ thực tế và khoảng RTT khi nhiều client dùng chung quy trình.
4. Không đưa session URI từ một vị trí khởi tạo xa sang nhiều uploader mà không đo tác động.

**Tối ưu vị trí không thay thế quy định lưu trú dữ liệu.** Hãy kiểm tra location bucket, nơi xử lý dữ liệu, quyền truy cập và các đường network liên quan.

### 9.3. Các hạng mục phí cần lập ngân sách

| Thành phần | Có thể tạo chi phí gì? | Giảm rủi ro |
| --- | --- | --- |
| **Object cuối** | Dung lượng lưu trữ theo storage class, location và thời gian | Chọn class theo vòng đời truy cập thực tế. |
| **Temporary parts** | Dung lượng lưu riêng trước/sau compose nếu chưa xóa | Dọn sau xác minh; hạn chế orphan parts. |
| **Upload/compose requests** | Phí thao tác theo bảng giá, đặc biệt nếu nhiều part và nhiều tầng compose | Đo request count, tránh chunk nhỏ không cần thiết. |
| **Download/validation** | Egress và thao tác tải xuống, tùy vị trí và đích | Tính checksum trên nguồn khi có thể; dùng phương pháp xác minh phù hợp. |
| **Soft delete/Object Versioning** | Các bản retained/noncurrent tiếp tục chiếm dung lượng | Thiết kế policy cho temp prefix/bucket riêng theo yêu cầu. |
| **Retention/minimum duration** | Early deletion charges hoặc không thể xóa parts trước thời hạn | Không dùng PCU khi không phù hợp; kiểm tra chính sách trước upload. |
| **Logging, Monitoring, database trạng thái** | Log ingestion, lưu trữ, xử lý trạng thái/metric | Không log session token; chọn retention có chủ đích. |
| **Compute/Cloud Run/GKE xử lý file** | CPU/RAM/I/O khi split, scan, transcode, checksum | Kiểm tra autoscaling, quota, timeouts và concurrency. |

Mức giá chính xác thay đổi theo location, storage class và bảng giá hiện hành. **Tạo budget alert không tạo giới hạn chi tiêu cứng.** Với pipeline xử lý video hàng loạt, phải dự báo số job, cỡ file, thời gian giữ staging và tỷ lệ upload thất bại.

### 9.4. Các chỉ số vận hành đáng theo dõi

Nên có các metric và log trạng thái **không chứa session URI**:

- `upload_started`, `upload_completed`, `upload_aborted` và thời lượng mỗi giai đoạn.
- Số byte client đã gửi và **byte server xác nhận đã lưu**, tránh chỉ dùng progress bar cục bộ.
- Tần suất `308`, số lần retry, lỗi `429/5xx` và session hết hạn.
- Thời gian compose, số parts, số tầng compose và `412` do precondition.
- Số object tạm còn tồn tại quá thời gian mong đợi, dung lượng staging và lượng soft-deleted/noncurrent data.
- Số job đã upload xong nhưng chưa verify hoặc chưa publish.
- Tỷ lệ checksum mismatch, file sai size/format, scan không đạt và restore/retry thành công.

Chia dashboard theo **loại client, vị trí, loại file, bucket và phiên bản uploader** để thấy sự cố cục bộ. Không dùng object name chứa dữ liệu cá nhân làm nhãn metric có cardinality lớn.

## 10. Bài thực hành: upload các phần và ghép lại an toàn

### 10.1. Mục tiêu và điều kiện

Bài lab dùng ba tệp ASCII rất nhỏ để chứng minh **compose ghép byte chính xác theo thứ tự**. Sau khi hiểu quy trình, bạn có thể áp dụng cho tệp lớn. Mục đích là kiểm tra correctness và thao tác, không benchmark thông lượng.

**Điều kiện:**

- Có project/bucket lab **đã được tổ chức phê duyệt** và Cloud Billing account đang hoạt động.
- Có quyền tạo, đọc metadata, tải xuống và xóa **chính object do mình tạo**; nếu quyền xóa không có, cần có người quản lý hỗ trợ bước cleanup.
- Bucket không có retention/hold khiến việc xóa object lab không thể hoàn thành hoặc gây phí đáng kể. Nếu bucket có chính sách như vậy, dừng trước khi tạo parts.
- Đang chạy gcloud trong Bash/Cloud Shell với tài khoản đăng nhập phù hợp.
- Không chạy lab trong prefix dùng bởi ứng dụng production; không tái sử dụng upload ID của người khác.

### 10.2. Chuẩn bị ba phần local và manifest đơn giản

Trên **máy của bạn**, tạo ba file không chứa thông tin cá nhân:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export BUCKET_NAME="YOUR_APPROVED_LAB_BUCKET"
export UPLOAD_ID="lab-unique-id-you-own"

gcloud config set project "$PROJECT_ID"
gcloud storage buckets describe "gs://$BUCKET_NAME" \
  --format="yaml(name,location,storageClass,softDeletePolicy,retentionPolicy)"

printf 'AAA' > part-0001.bin
printf 'BBB' > part-0002.bin
printf 'CCC' > part-0003.bin
printf 'AAABBBCCC' > expected.bin

wc -c part-0001.bin part-0002.bin part-0003.bin expected.bin
~~~

Bạn phải thấy ba part có 3 bytes mỗi part và kết quả mong đợi 9 bytes. `UPLOAD_ID` phải **duy nhất** với người học/job này, ví dụ thêm mã nhóm và thời điểm; nó là namespace tránh xóa nhầm object của người khác, không phải credential.

Đọc thông tin bucket trước khi upload để xác minh location, storage class, soft delete/retention và quyền. Nếu không có quyền `storage.buckets.get` để đọc bucket, nhờ người quản trị xác nhận chính sách; **không tự bỏ qua kiểm tra khả năng dọn parts**.

### 10.3. Upload lần lượt ba part

~~~bash
gcloud storage cp part-0001.bin \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0001.bin"

gcloud storage cp part-0002.bin \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0002.bin"

gcloud storage cp part-0003.bin \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0003.bin"
~~~

Đọc lại metadata:

~~~bash
gcloud storage objects describe \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0001.bin" \
  --format="yaml(name,size,generation,crc32c,storageClass)"

gcloud storage objects describe \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0002.bin" \
  --format="yaml(name,size,generation,crc32c,storageClass)"

gcloud storage objects describe \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0003.bin" \
  --format="yaml(name,size,generation,crc32c,storageClass)"
~~~

Xác minh từng part có **3 bytes**, đúng tên, cùng storage class và mỗi part có generation. Trong một ứng dụng lớn, kết quả này sẽ được lưu trong manifest để tránh trộn parts từ nhiều job.

### 10.4. Compose thành một object mới

~~~bash
gcloud storage objects compose \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0001.bin" \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0002.bin" \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0003.bin" \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/final.bin"
~~~

**Lưu ý về race:** chỉ chạy ví dụ sau khi xác minh đường đích `final.bin` chưa tồn tại và không có job khác ghi vào cùng prefix. Đối với production, thay cách làm bằng **compose có generation preconditions trên source và destination** như mục 5.3.

Kiểm tra kết quả:

~~~bash
gcloud storage objects describe \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/final.bin" \
  --format="yaml(name,size,generation,componentCount,crc32c,md5Hash)"

gcloud storage cp \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/final.bin" \
  ./downloaded-final.bin

cmp expected.bin downloaded-final.bin
wc -c expected.bin downloaded-final.bin
~~~

Kết quả đúng là `cmp` không in thông báo và trả **exit code 0**, hai tệp có cùng kích thước **9 bytes**. Metadata object cuối có CRC32C, còn `md5Hash` có thể **không tồn tại** vì đây là composite object.

Nếu đổi thứ tự nguồn thành `part-0002` trước `part-0001`, nội dung sẽ khác (`BBBAAACCC`) dù từng part đều upload thành công. Đó là lý do thứ tự/manifest là điều kiện nghiệp vụ chứ không chỉ là vấn đề kỹ thuật.

### 10.5. Kiểm tra tiêu chí hoàn thành

| Tiêu chí | Cách chứng minh |
| --- | --- |
| Source objects tồn tại đúng tên | Metadata của ba part trong prefix riêng |
| Source không bị thay đổi khi compose | Đọc lại generation/size sau compose |
| Object cuối nối đúng thứ tự | `cmp expected.bin downloaded-final.bin` thành công |
| Object cuối đúng kích thước | `size=9` bytes |
| Có khả năng kiểm tra toàn vẹn | Metadata `crc32c`; đối chiếu checksum của bytes đã tải |
| Hiểu cơ chế bảo vệ race | Giải thích được `ifGenerationMatch=0` và source generation |
| Dọn được object tạm | Xác nhận quyền và chính sách trước khi xóa, rồi kiểm tra lại |

### 10.6. Dọn đúng các object của bài lab

**Chỉ sau khi đã xác minh kết quả**, kiểm tra danh sách chính xác:

~~~bash
gcloud storage ls "gs://$BUCKET_NAME/staging/$UPLOAD_ID/"
~~~

Trong bucket lab không bật retention/hold ngoài dự kiến, có thể xóa **từng object cụ thể**:

~~~bash
# Thao tác xóa: CHỈ dành cho đúng upload ID và object bạn đã tạo
gcloud storage rm \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0001.bin" \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0002.bin" \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0003.bin" \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/final.bin"

gcloud storage ls "gs://$BUCKET_NAME/staging/$UPLOAD_ID/"
~~~

Nếu bucket bật **soft delete** hoặc **Object Versioning**, thao tác xóa có thể giữ các phiên bản cũ/soft-deleted và vẫn phát sinh phí. Nếu chính sách retention ngăn xóa, **không sửa hoặc vô hiệu hóa chính sách bucket dùng chung** để làm cho lab “sạch”; hãy báo người quản trị và ghi nhận object còn lại.

Các file `part-*.bin` và `downloaded-final.bin` trên máy local không tự biến mất khi xóa Cloud Storage. Có thể giữ chúng làm bằng chứng học tập hoặc xóa đúng file lab sau khi kiểm tra.

## 11. Xử lý sự cố thường gặp

| Dấu hiệu | Khả năng nguyên nhân | Cách xử lý có kiểm soát |
| --- | --- | --- |
| Upload dừng sau khi mạng mất | Client không giữ session URI hoặc không hỏi server về offset đã lưu | Dùng SDK/CLI có resumable, hoặc status query tới đúng session rồi tiếp tục từ `Range`. |
| Session trả `404` hoặc `410` | Session hết hạn, đã hủy hoặc không còn hợp lệ | Tạo session mới, xác minh dữ liệu nguồn chưa đổi rồi gửi lại từ đầu. |
| Upload nhận `308` nhưng client coi là lỗi redirect | Code HTTP tự viết xử lý nhầm response | Đọc `Range` của `Resume Incomplete`; không tự follow redirect. |
| Upload đang dở rồi `400` về `Content-Range` | Offset, tổng size, header hoặc nội dung chunk không hợp lệ | Dừng gửi, đối chiếu status query và kiểm tra session; khi cần tạo session mới. |
| Object cuối có kích thước sai | Một part thiếu, trùng, sai thứ tự hoặc file nguồn đổi giữa upload | Kiểm tra manifest, generation, size, checksum; tạo lại từ nguồn được xác minh. |
| Compose lỗi quá nhiều nguồn | Vượt 32 source objects trong một request | Chia compose thành các tầng có tối đa 32 nguồn/lần. |
| Compose thất bại do source không hợp lệ | Source không cùng bucket/class, bị thay generation hoặc đã bị xóa | Xác minh metadata từng source, generation preconditions và policy bucket. |
| Compose tạo kết quả nhưng không đúng nội dung | Parts có thứ tự sai hoặc bản thân format không cho phép nối byte | So sánh checksum/bytes và thử mở file bằng parser ứng dụng. |
| `412 Precondition Failed` | Destination đã có object hoặc source generation không khớp | Đọc lại manifest/object; quyết định idempotent, không gỡ precondition bừa bãi. |
| PCU không chạy dù file lớn | Bucket không tương thích, thiếu `storage.buckets.get`, cấu hình CLI/tệp không đạt ngưỡng | Đọc log CLI, kiểm tra threshold, permission, storage class, retention/hold; chấp nhận fallback nếu phù hợp. |
| Upload PCU để lại object tạm | Job lỗi trước compose hoặc cleanup chưa chạy | Tìm đúng upload ID/prefix, đối chiếu job, xóa theo policy nếu được phép. |
| Không xóa được temp parts | Retention/hold/permission bảo vệ object | Không phá policy production; phối hợp chủ bucket, tính chi phí tồn đọng. |
| Tổng dung lượng bucket tăng dù xóa parts | Soft delete/Object Versioning giữ bản được xóa hoặc phiên bản cũ | Xem trạng thái lưu trữ/retention và billing, đánh giá lifecycle phù hợp. |
| Tải xuống composite object báo thiếu MD5 | Composite object không có MD5 metadata | Dùng CRC32C; xác minh qua thư viện hỗ trợ hoặc checksum nguồn độc lập. |
| Tốc độ upload thấp dù có PCU | Mạng/disk nguồn chậm, concurrency quá cao hoặc retry nhiều | Đo throughput theo giai đoạn, giảm cạnh tranh, điều chỉnh cấu hình có thử nghiệm. |
| Ứng dụng đã thông báo “hoàn thành” nhưng không có object hợp lệ | Chỉ tin tín hiệu client, không đọc metadata đích hoặc kiểm tra generation | Backend xác minh object trước khi đánh dấu job READY. |

### 11.1. Quy trình điều tra upload chưa biết hoàn thành hay chưa

Khi client không nhận phản hồi cuối:

1. **Không gửi lại toàn bộ ngay lập tức** nếu session còn hợp lệ.
2. Kiểm tra trạng thái resumable session; ghi nhận `308` và `Range` nếu chưa hoàn tất.
3. Nếu server đã xác nhận hoàn tất, đọc metadata object đích và so với manifest.
4. Nếu session mất/hết hạn, đọc xem object đích có tồn tại đúng generation/size/checksum chưa; có thể thao tác trước đã thành công.
5. Nếu không có object hợp lệ, khởi tạo upload mới kèm generation precondition phù hợp.
6. Ghi lại trạng thái job, mốc thời gian, số byte đã được server xác nhận và nguyên nhân retry.

Đối với compose, nếu request timeout, **không vội compose lại vào cùng tên mà không kiểm tra**. Hãy đọc metadata đích và generation; có thể server đã tạo object thành công trước khi mạng mất.

### 11.2. Khi thấy lỗi IAM

Cần phân biệt:

- **Initiate resumable upload:** principal phải có quyền tạo/ghi object phù hợp và đáp ứng chính sách bucket.
- **PUT qua session URI:** session URI hợp lệ mang quyền upload của session; không nên cố chèn credential của một người dùng khác để sửa lỗi.
- **Compose:** cần quyền tạo object đích và các quyền trên nguồn theo Compose API/SDK đang dùng.
- **Cleanup:** xóa object tạm cần quyền xóa, đồng thời phải tôn trọng retention/hold.
- **Đọc lại metadata và validation:** cần quyền xem object theo cấu hình bucket.
- **PCU qua gcloud:** kiểm tra tương thích bucket có thể đòi thêm quyền đọc bucket; không phải upload thường luôn yêu cầu quyền này.

Giải pháp là xác định **permission bị thiếu đúng ở bước nào** và cấp quyền tối thiểu phù hợp. Không mặc định rằng Storage Admin toàn project là cách xử lý an toàn nhất.

## 12. Tình huống thiết kế: tải video khóa học dung lượng lớn

Một nền tảng học Java sử dụng Cloud Run API, Cloud Storage chứa video, database lưu metadata bài học, Cloud CDN phân phối nội dung đã được duyệt. Người dùng có thể tải video từ nhiều quốc gia, đường truyền thường gián đoạn. Mỗi video có dung lượng từ 1 đến 20 GiB; yêu cầu không mất dữ liệu, không xuất bản video sai người sở hữu và có thể giám sát chi phí.

### 12.1. Kiến trúc đề xuất để phân tích

~~~mermaid
flowchart LR
    USER["Người biên tập / uploader"] --> API["Cloud Run API<br/>xác thực, quota, manifest"]
    API --> DB[("Job DB")]
    API --> SES["Tạo resumable session<br/>có generation precondition"]
    SES --> GCS["Cloud Storage staging"]
    USER -->|"Upload bytes / resume"| GCS
    GCS --> SCAN["Verify checksum, size,<br/>type, malware scan"]
    SCAN --> PUB["Published object<br/>hoặc trạng thái READY"]
    PUB --> CDN["Load balancer / Cloud CDN"]
    CDN --> STUDENT["Người học đủ quyền"]
~~~

Đây là mô hình logic. Trong triển khai thật, cần xác định việc chuyển từ staging sang published được thực hiện bằng **copy/rewrite có điều kiện, đổi trạng thái ứng dụng hoặc một đường publish khác**; Cloud Storage không có thao tác rename object tổng quát giống hệ thống tệp POSIX trong mọi cấu hình bucket.

Một thiết kế an toàn cần trả lời:

1. **Danh tính:** ai được tạo upload session? Client có thể upload vào prefix nào?
2. **Tính liên tục:** client có giữ session URI an toàn và resume được sau refresh/offline?
3. **Tính nhất quán:** nếu người dùng thay file nguồn giữa các lần resume, hệ thống có phát hiện không?
4. **Tính đúng đắn:** metadata cuối có được xác minh theo manifest và checksum trước khi READY?
5. **Tính đồng thời:** hai người cùng phát hành một lesson có thể ghi đè nhau không?
6. **Phân phối:** video đã scan/duyệt mới được phép xuất bản qua CDN như thế nào?
7. **Chi phí:** có object tạm không được dọn hoặc bản retained kéo dài không?
8. **Khả dụng:** nếu Cloud Run instance restart, upload session và trạng thái job còn không?
9. **Bảo mật:** token, session URI và object path có bị ghi ra logs hoặc cấp cho tenant sai không?
10. **Vận hành:** metric, cảnh báo và runbook nào giúp phát hiện upload kẹt ở `COMPOSING` hoặc `VERIFYING`?

### 12.2. Bài tập định lượng và lựa chọn phương pháp

**Bài A — Tính số phần và phép compose.** Một hệ thống chia file 45 GiB thành **45 phần 1 GiB** đã được upload vào bucket. Mỗi compose nhận tối đa 32 nguồn. Hãy đề xuất cách ghép với ít tầng:

- Compose 32 phần đầu thành `intermediate-A`.
- Compose 13 phần còn lại thành `intermediate-B`.
- Compose A rồi B thành object cuối.

Tổng cộng **3 compose requests** trong phương án này. Object cuối vẫn phải dưới 5 TiB; parts và intermediate phải cùng bucket/lớp lưu trữ phù hợp, có generation preconditions và kiểm tra checksum.

**Bài B — Mất kết nối sau khi gửi 32 MiB.** Client gửi 32 MiB nhưng không nhận được phản hồi. Status query trả:

~~~http
HTTP/1.1 308 Resume Incomplete
Range: bytes=0-25165823
~~~

Hỏi byte đầu tiên của lần gửi tiếp theo là gì? **Đáp án:** byte **25.165.824** (24 MiB), vì byte cuối server xác nhận là 25.165.823. Không được tự nhảy tới 32 MiB chỉ dựa trên tiến độ phía client.

**Bài C — So sánh hai thiết kế:** với một ứng dụng thu nhận 500 video/ngày, mỗi video 4 GiB, hãy so một resumable upload cho từng video với PCU. Thu thập tốc độ upload, số lần retry, object tạm, số thao tác, tỷ lệ checksum mismatch, chi phí và công sức vận hành; chỉ chọn PCU khi thử nghiệm chứng minh lợi ích.

**Bài D — Ghi đè nhầm:** hai uploader cùng muốn xuất bản `videos/lesson-42.mp4`. Hãy dùng upload ID riêng và `ifGenerationMatch=0` hoặc generation đích đã biết để bảo vệ publish. Mô tả điều xảy ra khi một bên nhận 412.

### 12.3. Câu hỏi tự kiểm tra

**1. Resumable upload và parallel composite upload có giống nhau không?**  
Không. Resumable upload ghi vào một session có thể tiếp tục từ byte đã được lưu; PCU dùng nhiều object tạm tải song song rồi compose thành object cuối.

**2. `308 Resume Incomplete` có phải tín hiệu tải thất bại vĩnh viễn không?**  
Không. Đây là trạng thái server chưa nhận hết dữ liệu; cần đọc `Range` và tiếp tục theo đúng offset.

**3. Khi chưa có `Range` trong response 308, client phải bắt đầu từ đâu?**  
Từ byte 0, vì server chưa xác nhận đã lưu byte nào.

**4. Một lần compose nhận tối đa bao nhiêu source objects?**  
Tối đa **32**; có thể compose nhiều tầng bằng composite objects trung gian.

**5. Compose có hiểu cú pháp MP4, ZIP hoặc CSV để ghép hợp lệ không?**  
Không. Nó nối byte; ứng dụng chịu trách nhiệm về định dạng và thứ tự.

**6. Vì sao không dùng MD5 metadata làm điều kiện bắt buộc của composite object?**  
Vì composite object không có MD5 metadata; dùng CRC32C và kiểm tra đầu-cuối thích hợp.

**7. Tại sao một request compose trả 412 có thể là tín hiệu tích cực?**  
Vì precondition đã ngăn ghi đè hoặc source thay đổi; có thể kết quả của một lần thử trước đã được tạo đúng. Cần đọc lại metadata để kết luận.

**8. Xóa source parts có nhất thiết giải phóng phí lưu trữ ngay không?**  
Không. Soft delete, versioning, retention, minimum storage duration và cách tính phí có thể giữ dữ liệu hoặc phát sinh chi phí.

**9. Session URI có thể công khai vì nó chỉ là đường dẫn tới API không?**  
Không. Đây là bearer secret có quyền upload vào session; phải giữ kín và chỉ dùng HTTPS.

**10. Backend có nên tin thông báo “upload succeeded” do client tự gửi?**  
Không. Backend cần xác minh object, generation, size, checksum và quyền sở hữu trước khi xuất bản.

## 13. Tài liệu Google Cloud tham khảo

- **Resumable uploads:** https://cloud.google.com/storage/docs/resumable-uploads — session URI, expiry, chunking, hiệu năng và bảo mật.
- **Perform resumable uploads:** https://cloud.google.com/storage/docs/performing-resumable-uploads — HTTP initiation, status query, resume và cancel.
- **Compose objects:** https://cloud.google.com/storage/docs/composing-objects — gcloud/SDK, giới hạn compose và xóa source.
- **Composite objects:** https://cloud.google.com/storage/docs/composite-objects — CRC32C, MD5, ETag, metadata và semantics của object ghép.
- **Parallel composite uploads:** https://cloud.google.com/storage/docs/parallel-composite-uploads — chiến lược song song, cấu hình gcloud, quyền và chi phí tạm.
- **Data validation and change detection:** https://cloud.google.com/storage/docs/data-validation — checksum, bảo vệ dữ liệu và kiểm tra hoàn tất.
- **Generation preconditions:** https://cloud.google.com/storage/docs/request-preconditions — điều kiện ghi/compose tránh race condition.
- **Cloud Storage quotas and limits:** https://cloud.google.com/storage/quotas — object tối đa 5 TiB và 32 source objects mỗi compose.
- **JSON API compose:** https://cloud.google.com/storage/docs/json_api/v1/objects/compose — cấu trúc request và source generations.
- **Cloud Storage pricing:** https://cloud.google.com/storage/pricing — operation, lưu trữ, network, retention và chi phí liên quan.
- **Cloud Storage IAM:** https://cloud.google.com/storage/docs/access-control/iam — quyền truy cập bucket/object.
- **Object Lifecycle Management:** https://cloud.google.com/storage/docs/lifecycle — quy tắc vòng đời object, thời gian và điều kiện áp dụng.
- **Signed URLs:** https://cloud.google.com/storage/docs/access-control/signed-urls — các thao tác truy cập có thời hạn cho client.
- **Cloud Storage CORS:** https://cloud.google.com/storage/docs/cross-origin — cấu hình truy cập từ ứng dụng trình duyệt.

Các giá trị mặc định của gcloud, lựa chọn SDK, IAM, giới hạn, phương thức upload và bảng giá có thể thay đổi. Khi triển khai trên hệ thống thật, hãy đối chiếu tài liệu chính thức với **đúng API, client library, bucket policy và location** đang dùng. Một quy trình upload tệp lớn đạt yêu cầu khi có thể **tiếp tục an toàn sau gián đoạn**, tạo object cuối **đúng bytes và đúng phiên bản**, bảo vệ thông tin xác thực, đồng thời theo dõi được object tạm, chi phí và khả năng phục hồi.

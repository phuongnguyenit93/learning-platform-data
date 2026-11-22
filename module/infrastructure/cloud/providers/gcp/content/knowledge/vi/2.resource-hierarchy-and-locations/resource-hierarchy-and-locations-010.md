# Thực hành tạo project học tập và dọn tài nguyên

> **Chương:** Hệ thống tài nguyên và vị trí  
> **Module:** CLOUD_PROVIDERS_GCP  
> **Phạm vi module:** Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

**Project là ranh giới quản lý cơ bản của một bài thực hành Google Cloud.** Mỗi project có định danh, quyền truy cập, cấu hình API, hạn mức và liên kết thanh toán riêng. Nếu tạo tài nguyên thử nghiệm mà không quản lý vòng đời project, người học có thể để sót bucket, máy ảo hoặc dịch vụ tiếp tục phát sinh chi phí.

Bài thực hành này hướng dẫn tạo **một project học tập riêng**, xác định vị trí tài nguyên, kiểm tra IAM và billing, tạo một bucket Cloud Storage với tệp mẫu, sau đó **xóa tệp, xóa bucket và xác nhận kết quả**. Cuối bài có thêm lựa chọn tắt toàn bộ project nếu project được tạo chỉ để thực hành.

## 1. Mục tiêu và kết quả cần đạt

Sau bài học, bạn có thể:

1. Tạo project bằng Google Cloud Console hoặc Google Cloud CLI (`gcloud`), phân biệt **project name**, **project ID** và **project number**.
2. Hiểu project nằm ở đâu trong hệ thống **organization → folder → project**; xác định được vai trò của **region** và **zone** khi tạo tài nguyên.
3. Kiểm tra quyền IAM và điều kiện billing trước khi thực hành.
4. Tạo một bucket Cloud Storage tại một vị trí xác định, tải lên và đọc lại tệp để chứng minh tài nguyên hoạt động.
5. Dọn tài nguyên theo thứ tự an toàn, kiểm tra tài nguyên còn tồn tại và quyết định khi nào cần xóa cả project.

**Sản phẩm cuối buổi:** một bảng ghi lại project ID, vị trí bucket, kết quả kiểm tra quyền/billing, bằng chứng tệp đã tải lên, và bằng chứng bucket hoặc project đã được dọn.

## 2. Chuẩn bị trước khi tạo project

### 2.1. Tài khoản và quyền

Cần có:

- Một tài khoản được phép truy cập **Google Cloud Console** tại https://console.cloud.google.com/.
- Quyền tạo project trong tổ chức hoặc tài khoản học tập. Trong môi trường tổ chức, việc tạo project có thể cần quyền phù hợp (chẳng hạn quyền được cấp qua vai trò **Project Creator**) và có thể chịu ràng buộc về folder/organization.
- Nếu cần tạo tài nguyên sử dụng dịch vụ có tính phí, project phải được liên kết với **Cloud Billing account** đang hoạt động; người dùng cần được cấp quyền liên kết tương ứng. Khả năng đăng nhập Console **không đồng nghĩa** có quyền tạo project hoặc quản lý billing.
- Quyền phù hợp với Cloud Storage để tạo bucket, ghi/đọc object và xóa chúng. Nếu tổ chức hạn chế những thao tác này, thực hành trong project sandbox do quản trị viên cấp.

Có thể thực hành trên **project cá nhân mới** hoặc **project phòng lab đã được chỉ định**. Không xóa project dùng chung, project chứa dữ liệu quan trọng, project production hoặc project có tài nguyên của người khác.

### 2.2. Chọn công cụ

Có hai cách thực hiện tương đương:

| Cách | Phù hợp khi | Điều cần nhớ |
|---|---|---|
| **Google Cloud Console** | Mới học, muốn nhìn trực tiếp project, hierarchy, billing và tài nguyên | Luôn nhìn **Project selector** trước khi tạo/xóa |
| **Cloud Shell / gcloud CLI** | Muốn lưu lệnh để lặp lại và đối chiếu chính xác project ID | Chỉ chạy sau khi kiểm tra biến và danh tính; ưu tiên truyền tường minh `--project` |

Các khối lệnh `bash` trong bài dùng môi trường **Cloud Shell (Bash)**. Cloud Shell thường có sẵn `gcloud` và cơ chế đăng nhập thích hợp. Nếu dùng terminal riêng, hãy cài Google Cloud CLI và đăng nhập theo quy trình của tổ chức trước khi chạy. Không cần chạy cả hai cách để tạo hai project.

### 2.3. Quy tắc an toàn về chi phí và dọn dẹp

1. Dùng một project riêng cho bài lab để biết chính xác tài nguyên nào cần dọn.
2. **Không giả định dịch vụ nào miễn phí tuyệt đối.** Chi phí có thể liên quan đến lưu trữ, số request, lưu lượng mạng và tài nguyên khác; ưu đãi dùng thử phụ thuộc tài khoản.
3. Trước khi tạo tài nguyên, xem **Billing → Budgets & alerts** và thiết lập cảnh báo theo ngân sách học tập nếu có quyền. **Budget alert không phải giới hạn chi tiêu cứng** và không tự ngắt mọi dịch vụ.
4. Chỉ tạo bucket và một tệp văn bản nhỏ theo bài này; không cần tạo VM, GKE cluster, Cloud SQL hay Cloud Run để hoàn thành bài.
5. Dọn ngay sau khi xác minh kết quả; sau đó xem lại bảng điều khiển billing và danh sách tài nguyên.

## 3. Hiểu trước cấu trúc tổ chức và vị trí tài nguyên

Project không phải nơi lưu trữ theo nghĩa địa lý. Một project có thể sở hữu tài nguyên đặt ở nhiều vị trí khác nhau, tùy loại dịch vụ và chính sách tổ chức.

```text
Organization (nếu tài khoản thuộc tổ chức)
└── Folder (nếu tổ chức có phân nhóm)
    └── Project: gcp-lab-unique-1234
        ├── IAM / enabled APIs / quota / billing association
        ├── Cloud Storage bucket (location: asia-southeast1)
        ├── Cloud Run service (region, nếu triển khai sau)
        ├── Compute Engine VM (zone, nếu triển khai sau)
        └── Cloud SQL instance (region, nếu triển khai sau)
```

| Khái niệm | Bản chất | Ví dụ / lưu ý |
|---|---|---|
| **Organization** | Cấp quản trị cao nhất khi tài khoản thuộc tổ chức | Các chính sách và quyền có thể kế thừa xuống dưới |
| **Folder** | Gom nhóm project theo đội, môi trường hoặc chính sách | Có thể không tồn tại trong tài khoản cá nhân |
| **Project** | Ranh giới sở hữu tài nguyên, bật API, quản lý IAM/quota/billing | `gcp-lab-unique-1234` chỉ là ví dụ, phải chọn ID chưa được sử dụng |
| **Region** | Khu vực địa lý để đặt dịch vụ hoặc dữ liệu tùy loại tài nguyên | `asia-southeast1` là một ví dụ region tại Singapore |
| **Zone** | Phân vùng triển khai bên trong một region | `asia-southeast1-a` là một ví dụ zone, phù hợp với một số tài nguyên như VM |
| **Global resource** | Tài nguyên có phạm vi toàn cục hoặc được quản trị ngoài khái niệm region/zone thông thường | VPC network có phạm vi toàn cục; subnet của VPC là theo region |

**Project ID** là định danh dùng trong CLI/API, có tính duy nhất toàn hệ thống Google Cloud. **Project number** là mã số do Google cấp và khác project ID. **Project name** là tên hiển thị, có thể trùng với tên của project khác. Bạn sẽ dùng **project ID** xuyên suốt ví dụ để tránh chọn nhầm project.

Với Cloud Storage, bucket có **location** khi tạo, có thể là region, dual-region hoặc multi-region theo lựa chọn được hỗ trợ. Bài lab chọn **region `asia-southeast1`** để dễ xác minh. Vị trí này chỉ là ví dụ; trong hệ thống thật phải xét độ trễ, cư trú dữ liệu, khả năng sẵn có của dịch vụ, yêu cầu phục hồi và chi phí. Sau khi tạo bucket, không nên giả định việc đổi location đơn giản như đổi tên.

## 4. Bước 1 — Tạo project học tập

### Cách A: qua Console

1. Đăng nhập https://console.cloud.google.com/ và mở **Project selector** trên thanh điều hướng.
2. Chọn **New Project / Dự án mới**. Mục này có thể không xuất hiện nếu tài khoản thiếu quyền tạo project.
3. Nhập **Project name** dễ nhận biết, ví dụ `GCP Learning Lab`.
4. Kiểm tra **Project ID** được gợi ý hoặc đặt ID hợp lệ và duy nhất, ví dụ `gcp-lab-unique-1234`. Không dùng nguyên ví dụ nếu ID đã tồn tại.
5. Nếu giao diện yêu cầu, chọn **Organization** và **Location** (organization/folder) cho project. Ở màn hình tạo project, **Location này là vị trí trong cấu trúc quản lý tài nguyên**, không phải region chạy ứng dụng.
6. Chọn **Create** và đợi project xuất hiện; mở project vừa tạo và ghi lại project ID/project number.

Nếu thấy thông báo từ chối do policy/quota/quyền, cần sử dụng project lab đã cấp hoặc nhờ quản trị viên mở đúng quyền. Không di chuyển project sang organization khác hoặc tự thay đổi policy để vượt hạn chế.

### Cách B: qua Cloud Shell

Đổi ID mẫu thành ID **thực sự riêng của bạn** trước khi chạy:

```bash
# Cấu hình giá trị cho bài lab; không dùng nguyên ID mẫu nếu đã có chủ sở hữu
PROJECT_ID="gcp-lab-unique-1234"
PROJECT_NAME="GCP Learning Lab"

# Xem tài khoản gcloud đang hoạt động
gcloud auth list --filter="status:ACTIVE"

# Tạo project; trong tổ chức có thể cần thêm --folder=FOLDER_ID
# hoặc --organization=ORGANIZATION_ID tùy chính sách
gcloud projects create "$PROJECT_ID" --name="$PROJECT_NAME"

# Xác minh project vừa tạo
gcloud projects describe "$PROJECT_ID" \
  --format="table(projectId,projectNumber,name,lifecycleState)"
```

Nếu phải chọn parent trong organization, chỉ truyền **folder hoặc organization phù hợp với quyền được cấp**, theo chỉ dẫn quản trị. Trong các bước tiếp theo, mọi lệnh tạo/kiểm tra tài nguyên sẽ ghi rõ project ID để giảm nguy cơ chạy nhầm trên project mặc định.

### Điểm kiểm tra 1

Ghi lại:

| Mục | Giá trị cần tự điền |
|---|---|
| Project name | `________________________` |
| Project ID | `________________________` |
| Project number | `________________________` |
| Parent organization/folder (nếu có) | `________________________` |
| Tài khoản thao tác | `________________________` |

Chỉ tiếp tục khi project bạn chọn là **project học tập do bạn được phép thay đổi và dọn dẹp**.

## 5. Bước 2 — Kiểm tra IAM, billing, API và ngân sách

### 5.1. Kiểm tra quyền

Trong Console, chọn đúng project → **IAM & Admin → IAM**. Xác nhận tài khoản của mình có quyền đủ cho thao tác được giao; xem các principal khác đang được cấp quyền nếu chính sách cho phép. Không cấp quyền **Owner** hoặc các vai trò quản trị rộng cho mọi người chỉ để bài lab chạy được.

Cloud Shell có thể xem chính sách IAM ở **cấp project**:

```bash
gcloud projects get-iam-policy "$PROJECT_ID" \
  --format="table(bindings.role,bindings.members)"
```

IAM trên project có thể chịu tác động từ quyền kế thừa ở organization/folder hoặc các chính sách khác. Vì vậy, một danh sách IAM cấp project không phản ánh đầy đủ mọi quyền có hiệu lực.

### 5.2. Kiểm tra liên kết thanh toán

Trong Console, mở **Billing** và xem project đã liên kết Cloud Billing account phù hợp chưa. Nếu chưa và dịch vụ yêu cầu billing, hãy liên kết qua Console bằng tài khoản có quyền, theo quy định của tổ chức. Không sử dụng tài khoản thanh toán của người khác nếu chưa được cho phép.

Để xem thông tin liên kết hiện tại (nếu được cấp quyền):

```bash
gcloud billing projects describe "$PROJECT_ID"
```

Trong Console, tạo **Budget & alerts** gắn với phạm vi project nếu được phép. Có thể đặt thông báo khi chạm các tỷ lệ dự kiến hoặc thực tế theo nhu cầu. Dù có budget, bạn vẫn phải kiểm tra Billing và dọn các tài nguyên không cần thiết.

### 5.3. Kiểm tra và bật API sử dụng

Trong Console: **APIs & Services → Enabled APIs & services**. Bài lab dùng Cloud Storage; một số môi trường đã bật API phù hợp. Nếu cần, có thể dùng:

```bash
# Xem API đã bật
gcloud services list --enabled --project="$PROJECT_ID"

# Bật API phục vụ Cloud Storage khi cần
gcloud services enable storage.googleapis.com --project="$PROJECT_ID"
```

Việc bật API là cấu hình trong project; **không tự tạo dữ liệu hoặc bucket**. Nhưng tạo/sử dụng tài nguyên qua API sau đó có thể phát sinh phí.

### Điểm kiểm tra 2

Trước khi tạo bucket, tự xác nhận:

- Project ID đã đúng, project có quyền thực hành và không chứa tài nguyên production.
- Billing đã được xác nhận theo yêu cầu của tài khoản và môi trường học.
- Tài khoản có đủ quyền tạo/đọc/xóa bucket cùng object.
- Đã xem ngân sách và biết thao tác dọn dẹp cuối bài.

## 6. Bước 3 — Tạo bucket ở một vị trí xác định

Cloud Storage là dịch vụ lưu **object**. Bucket thuộc một project, có tên **duy nhất toàn cục**, được cấu hình location, storage class và chính sách truy cập. Bài lab không yêu cầu public bucket.

### Cách A: Console

1. Mở **Cloud Storage → Buckets** trong đúng project.
2. Chọn **Create**.
3. Đặt tên bucket **duy nhất toàn cục**, ví dụ `gcp-lab-unique-1234-demo-data`. Tên sẽ không dùng được nếu đã có bucket khác sở hữu.
4. Tại mục chọn vị trí lưu dữ liệu, chọn loại vị trí **Region**, sau đó chọn một region được hỗ trợ, chẳng hạn **`asia-southeast1`**.
5. Chọn **Standard** nếu giao diện yêu cầu storage class cho ví dụ lưu tệp nhỏ; không thay đổi các tùy chọn phí cao hơn nếu không có lý do.
6. Ưu tiên **Uniform bucket-level access** và cấu hình ngăn truy cập công khai theo chính sách hiện hành. Không cấp quyền công khai cho bài lab.
7. Xem lại chính sách soft delete / versioning / retention nếu giao diện hiển thị, vì các cơ chế lưu giữ có thể ảnh hưởng đến thời gian xóa và chi phí lưu trữ.
8. Chọn **Create** rồi mở bucket để xác nhận tên và location.

### Cách B: Cloud Shell

Tiếp tục dùng `PROJECT_ID` đã thiết lập. Thay tên bucket nếu trùng:

```bash
BUCKET_NAME="$PROJECT_ID-demo-data"
BUCKET_URI="gs://$BUCKET_NAME"
BUCKET_LOCATION="asia-southeast1"

# Tạo bucket vùng đơn với quyền IAM thống nhất
gcloud storage buckets create "$BUCKET_URI" \
  --project="$PROJECT_ID" \
  --location="$BUCKET_LOCATION" \
  --default-storage-class=STANDARD \
  --uniform-bucket-level-access

# Xem thuộc tính bucket vừa tạo
gcloud storage buckets describe "$BUCKET_URI"
```

Mô tả bucket phải thể hiện đúng **project sở hữu** và **location** đã chọn. Các tùy chọn ngăn public access, soft delete, versioning và retention còn phụ thuộc chính sách tổ chức và cài đặt thực tế; cần rà soát trong Console trước khi tải dữ liệu nhạy cảm.

**Lỗi thường gặp:** bucket name bị trùng; thiếu quyền `storage.buckets.create`; billing không hoạt động; location bị Organization Policy chặn; hoặc cấu hình tổ chức không cho phép lựa chọn bảo mật vừa yêu cầu. Không chuyển sang project dùng chung để lách lỗi.

### Điểm kiểm tra 3

| Thuộc tính bucket | Kết quả mong đợi |
|---|---|
| Tên | Tên mới, duy nhất, thuộc project học tập |
| Vị trí | Region đã chọn; ví dụ `asia-southeast1` |
| Storage class | Phù hợp bài lab; ví dụ `STANDARD` |
| Truy cập | Không vô tình công khai dữ liệu |
| Object | Chưa có, trước bước tải tệp |

## 7. Bước 4 — Tải tệp mẫu và xác minh

### Cách A: Console

1. Trong bucket vừa tạo, chọn **Upload files**.
2. Tạo một tệp văn bản cục bộ tên `lab-note.txt`, nội dung ví dụ: `Hello from GCP learning lab`.
3. Tải tệp lên bucket.
4. Mở danh sách object và xác nhận object `lab-note.txt` xuất hiện. Có thể mở thông tin chi tiết để kiểm tra kích thước và thời điểm tạo.

### Cách B: Cloud Shell

```bash
# Tạo một tệp văn bản nhỏ trong thư mục hiện tại của Cloud Shell
printf 'Hello from GCP learning lab\n' > lab-note.txt

# Tải tệp lên bucket
gcloud storage cp lab-note.txt "$BUCKET_URI/lab-note.txt"

# Kiểm tra object có trong bucket
gcloud storage ls "$BUCKET_URI"

# Đọc thử dữ liệu từ Cloud Storage ra màn hình
gcloud storage cat "$BUCKET_URI/lab-note.txt"
```

Nếu lệnh đọc trả đúng chuỗi văn bản đã tải lên, bạn đã thực hành luồng **tạo project → sử dụng một dịch vụ trong project → gắn location cho tài nguyên → lưu và truy xuất dữ liệu**. Có thể kiểm tra thêm thông tin object bằng Console.

**Liên hệ trách nhiệm chia sẻ:** Google Cloud quản lý nền tảng lưu trữ, còn bạn chịu trách nhiệm chọn quyền bucket/object, phân loại dữ liệu, quyết định vị trí, cấu hình lưu giữ và xóa dữ liệu thử nghiệm.

## 8. Bước 5 — Kiểm kê trước khi dọn

Trước khi xóa, xác định rõ tài nguyên **do bài lab tạo**. Không dùng lệnh xóa hàng loạt trên project chưa xác minh.

```bash
# Xác nhận project còn ở trạng thái hoạt động
gcloud projects describe "$PROJECT_ID" \
  --format="table(projectId,name,lifecycleState)"

# Liệt kê bucket thuộc project (nếu có quyền)
gcloud storage ls --project="$PROJECT_ID"

# Liệt kê nội dung của riêng bucket bài lab
gcloud storage ls "$BUCKET_URI"
```

Nếu bạn đã tạo thêm dịch vụ ngoài hướng dẫn, hãy kiểm tra và dọn **từng loại** trước khi kết thúc: VM/ổ đĩa và IP tĩnh; GKE cluster; Cloud Run; Cloud SQL và backup; load balancer; Pub/Sub; Artifact Registry; object storage; các tài nguyên tính phí khác. Không xem `gcloud storage ls` là công cụ kiểm kê toàn bộ tài nguyên trong project.

Một project có thể sở hữu tài nguyên ở nhiều **region** và **zone**. Đừng chỉ tìm trong region sử dụng để tạo bucket rồi kết luận rằng project không còn tài nguyên.

## 9. Bước 6 — Xóa object và bucket

### Cách A: Console

1. Mở đúng project → **Cloud Storage → Buckets**.
2. Mở bucket bài lab và chọn tệp `lab-note.txt`.
3. Xác nhận tên object rồi chọn **Delete**.
4. Kiểm tra bucket đã không còn object đang hoạt động.
5. Quay về danh sách bucket, chọn **đúng bucket của bài lab**, chọn **Delete** và xác nhận theo hướng dẫn.
6. Tải lại danh sách bucket; tên bucket vừa xóa không còn xuất hiện trong danh sách bucket đang hoạt động.

### Cách B: Cloud Shell

**Kiểm tra lại các biến ngay trước thao tác xóa.** Thao tác xóa là thật, nên các lệnh dưới đây chỉ dành cho bucket được tạo riêng cho bài lab:

```bash
printf 'Project: %s\nBucket: %s\n' "$PROJECT_ID" "$BUCKET_URI"
gcloud storage ls "$BUCKET_URI"

# Xóa đúng object mẫu
gcloud storage rm "$BUCKET_URI/lab-note.txt"

# Chỉ sau khi bucket không còn object cần giữ, xóa bucket
gcloud storage buckets delete "$BUCKET_URI"

# Xác minh bucket lab không còn trong danh sách bucket hiện tại
gcloud storage ls --project="$PROJECT_ID"
```

Nếu bucket không xóa được, kiểm tra xem có object khác, **object version**, chính sách **retention/hold**, quyền xóa, hoặc ràng buộc của tổ chức hay không. Không tự hạ chính sách bảo vệ hoặc xóa dữ liệu của người khác để hoàn tất lab. Tùy cấu hình soft delete hoặc lưu giữ, một số dữ liệu có thể còn trong thời hạn khôi phục và có thể ảnh hưởng chi phí.

Lệnh `gcloud storage ls --project` chỉ hỗ trợ xác minh bucket đang hiển thị, không chứng minh rằng mọi loại tài nguyên hoặc mọi khoản phí đều bằng 0.

## 10. Bước 7 — Giữ lại project hay xóa project?

Có **hai kết quả kết thúc hợp lệ**; chọn theo mục đích sử dụng project.

| Trường hợp | Hành động | Cách xác minh |
|---|---|---|
| **Project học tập sẽ dùng lại** | Giữ project, đảm bảo bucket/object và các dịch vụ tính phí của lab đã được dọn | Kiểm tra tài nguyên hiện có, APIs, Billing và budget alerts |
| **Project tạo riêng chỉ cho bài này** | Xác minh không có tài nguyên của người khác, sau đó **shutdown/delete project** nếu có quyền | Project chuyển sang trạng thái chờ xóa; theo dõi lifecycle và Billing |

### Xóa một project lab bằng Console

1. Vào **IAM & Admin → Settings** hoặc trang quản lý project tương ứng.
2. Kiểm tra lại **project name, project ID và project number**. Xác nhận đây là project độc lập phục vụ bài lab.
3. Chọn **Shut down / Delete project**, đọc thông tin về các tài nguyên bị ảnh hưởng.
4. Xác nhận bằng project ID khi giao diện yêu cầu.
5. Kiểm tra project chuyển sang trạng thái chờ xóa và không còn là project đang sử dụng.

### Xóa bằng Cloud Shell (chỉ với project độc lập)

```bash
# Xem thật kỹ ID và số project trước khi xóa
gcloud projects describe "$PROJECT_ID" \
  --format="table(projectId,projectNumber,name,lifecycleState)"

# Chỉ chạy khi đã xác minh project này được tạo riêng cho lab
gcloud projects delete "$PROJECT_ID"
```

**Phân biệt xóa tài nguyên và xóa project:** xóa bucket chỉ loại bỏ bucket đã chọn; xóa project đưa cả project vào quy trình shutdown/deletion và ảnh hưởng mọi tài nguyên, API, quyền truy cập và dịch vụ bên trong project. Project thường có một **giai đoạn chờ xóa/khôi phục** theo chính sách của Google Cloud; thao tác không nhất thiết xóa vật lý tất cả tài nguyên ngay lập tức. Không xem việc nhấn Delete như bằng chứng tuyệt đối rằng mọi chi phí đã chấm dứt tức thì. Kiểm tra trạng thái tài nguyên và báo cáo billing tiếp theo.

**Không xóa project** nếu project thuộc lớp học dùng chung, tổ chức, phòng lab được cấp dùng dài hạn, hoặc có tài nguyên không rõ chủ sở hữu. Trong các trường hợp đó, dọn riêng tài nguyên đã tạo và bàn giao cho chủ project.

## 11. Kiểm tra kết thúc và ghi nhận kết quả

Hoàn thành bảng này trước khi kết thúc thực hành:

| Hạng mục | Điều phải chứng minh | Trạng thái tự ghi |
|---|---|---|
| Project | Project ID và project number được ghi đúng | ☐ |
| Phân cấp tài nguyên | Biết project thuộc organization/folder nào, hoặc không có cấp này | ☐ |
| IAM | Đã kiểm tra quyền của tài khoản thao tác | ☐ |
| Billing | Đã xem liên kết billing và cơ chế theo dõi ngân sách | ☐ |
| Location | Đã ghi lại region của bucket và hiểu khác zone/parent location | ☐ |
| Tạo dữ liệu | `lab-note.txt` được tải lên và đọc lại thành công | ☐ |
| Dọn dữ liệu | Object và bucket mẫu đã xóa hoặc đã được bàn giao theo chính sách | ☐ |
| Dọn project | Project được giữ lại có kiểm kê hoặc đã chuyển sang chờ xóa | ☐ |
| Chi phí | Đã xem lại Billing/budget; biết có thể có độ trễ hiển thị | ☐ |

**Tiêu chí thành công:** bạn tạo và xác minh đúng một project/tài nguyên mẫu, biết location đã chọn, và đưa môi trường về trạng thái đã định: hoặc **project học tập sạch để dùng lại**, hoặc **project lab riêng được yêu cầu xóa và đã xác minh trạng thái**.

## 12. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không thấy nút tạo project | Thiếu quyền hoặc bị policy/quota giới hạn | Kiểm tra tài khoản/organization; dùng project được cấp |
| `PERMISSION_DENIED` khi gọi CLI | Thiếu role trên project, folder, billing hoặc bucket | Xác nhận danh tính và quyền cụ thể; nhờ quản trị cấp quyền tối thiểu |
| Tạo bucket báo tên không khả dụng | Tên bucket là định danh toàn cục đã có người dùng | Chọn tên mới duy nhất, giữ đúng project |
| Không chọn được location | Ràng buộc tổ chức hoặc dịch vụ không hỗ trợ lựa chọn đó | Chọn location được policy cho phép và ghi nhận thay đổi |
| Project tạo được nhưng không dùng được dịch vụ | Billing chưa phù hợp, API chưa bật, quota hoặc chính sách tổ chức | Kiểm tra từng điều kiện bằng Console và lệnh đọc |
| Không thể xóa bucket | Bucket còn object/phiên bản, retention/hold hoặc thiếu quyền | Kiểm kê đối tượng và chính sách; chỉ xóa dữ liệu mình sở hữu |
| Không thấy project sau khi xóa | Project đang trong giai đoạn shutdown/đã bị loại khỏi danh sách mặc định | Xem trạng thái lifecycle và quy trình khôi phục nếu có quyền |
| Vẫn thấy chi phí sau khi dọn | Billing có độ trễ hoặc có tài nguyên/đơn vị tính phí khác | Xem báo cáo theo project, dịch vụ và ngày phát sinh; kiểm tra sót tài nguyên |

## 13. Câu hỏi tự kiểm tra

**1. Khi tạo project trong Console, trường Location có nhất thiết là region của bucket sẽ tạo không?**  
**Trả lời:** không. Location tại màn hình tạo project thường chỉ **organization/folder parent** trong hệ thống phân cấp. Region của bucket được chọn riêng khi tạo bucket.

**2. Project ID và project name khác nhau như thế nào?**  
**Trả lời:** project ID là định danh duy nhất dùng trong nhiều API/CLI; project name là tên hiển thị. Project number là một mã số khác do Google cấp.

**3. Vì sao chỉ xóa `lab-note.txt` vẫn chưa kết luận bài lab được dọn sạch?**  
**Trả lời:** bucket vẫn còn, có thể có object khác hoặc cơ chế giữ phiên bản/soft delete; ngoài ra project có thể chứa tài nguyên từ dịch vụ khác. Cần kiểm kê và xác minh theo phạm vi lab.

**4. Budget alert có bảo đảm project không phát sinh phí vượt ngân sách không?**  
**Trả lời:** không. Alert là tín hiệu để chủ project nhận biết và xử lý; phải chủ động giới hạn và dọn tài nguyên.

**5. Có nên xóa project đang được một nhóm dùng chung để kết thúc bài thực hành cá nhân không?**  
**Trả lời:** không. Chỉ xóa tài nguyên của mình theo quyền được cấp, hoặc xin hướng dẫn từ chủ project. Xóa cả project chỉ dành cho project lab riêng đã xác minh.

**6. Một bucket Cloud Storage và một VM Compute Engine trong cùng project có bắt buộc cùng vị trí không?**  
**Trả lời:** không. Bucket có location riêng, còn VM chọn zone; các lựa chọn được chi phối bởi yêu cầu kiến trúc và chính sách tổ chức.

## Ghi nhớ

- **Project là đơn vị quản trị**, còn **region/zone là lựa chọn vị trí triển khai** cho từng loại tài nguyên; đừng nhầm parent location khi tạo project với region dữ liệu.
- **Lệnh luôn phải gắn đúng project và tên tài nguyên** trước khi thao tác, đặc biệt khi xóa.
- **IAM, billing, API, location và chính sách lưu giữ** là một phần của vòng đời tài nguyên, không chỉ là cấu hình lúc tạo.
- **Dọn dẹp là bước bắt buộc của bài thực hành cloud**: kiểm kê → xóa tài nguyên mình tạo → kiểm tra kết quả → xử lý project theo quyền sở hữu → kiểm tra billing.

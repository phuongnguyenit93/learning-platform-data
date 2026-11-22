# Quy tắc đặt tên bucket và thiết kế cấu trúc object key

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **tên bucket** với **object key** và giải thích tại sao cách đặt tên ảnh hưởng đến khả năng triển khai, truy cập, vận hành và chi phí Amazon S3.
2. Áp dụng các quy tắc đặt tên **general purpose bucket**; lựa chọn giữa **shared global namespace** và **account regional namespace**.
3. Nhận biết quy tắc tên của **directory bucket** và hiểu vì sao không thể lấy mọi quy tắc của general purpose bucket áp dụng cho loại bucket này.
4. Tạo object key nhất quán, dễ tìm kiếm theo **prefix**, hạn chế lỗi UTF-8, phân biệt chữ hoa/chữ thường, dấu gạch chéo và ký tự đặc biệt.
5. Thiết kế key theo truy vấn, phân vùng dữ liệu, môi trường, tenant, thời gian và vòng đời; tránh nhầm prefix với ranh giới bảo mật thực sự.
6. Sử dụng AWS CLI để tạo bucket mẫu, ghi object, liệt kê bằng prefix/delimiter và kiểm tra object key.
7. Đánh giá ảnh hưởng của thiết kế key đến hiệu năng request, chi phí LIST/PUT/GET, IAM policy, lifecycle và khả năng mở rộng.

## 1. Hai cấp tên cần phân biệt trong Amazon S3

**Amazon Simple Storage Service (Amazon S3)** lưu dữ liệu dưới dạng **object** trong **bucket**. Một object gồm dữ liệu (body), metadata và một **key** xác định vị trí logic của nó trong bucket. Với general purpose bucket, có thể hình dung:

```text
s3://company-orders-prod-ap-southeast-1-a1b2c3d4/
      └── orders/year=2026/month=11/day=20/order-8f42.json
          ├── Prefix: orders/year=2026/month=11/day=20/
          └── Key đầy đủ:
              orders/year=2026/month=11/day=20/order-8f42.json
```

| Thành phần | Ví dụ | Phạm vi và tính chất |
| --- | --- | --- |
| **Bucket name** | `company-orders-prod-ap-southeast-1-a1b2c3d4` | Định danh bucket theo quy tắc namespace của S3; không chứa `s3://` hay dấu `/`. |
| **Object key** | `orders/year=2026/month=11/day=20/order-8f42.json` | Định danh object **bên trong bucket**; bao gồm toàn bộ prefix và tên cuối. |
| **S3 URI** | `s3://company-orders-prod-ap-southeast-1-a1b2c3d4/orders/year=2026/month=11/day=20/order-8f42.json` | Cách biểu diễn bucket + key cho công cụ và con người; không phải object key thuần. |
| **Prefix** | `orders/year=2026/` | Chuỗi ký tự đầu của key dùng để nhóm và lọc khi list. |
| **Delimiter** | `/` | Ký tự dùng để nhóm các key khi liệt kê; trong general purpose bucket không tự tạo folder vật lý. |

**Bucket name và key có quy tắc hoàn toàn khác nhau:** tên general purpose bucket chỉ dùng chữ thường, số và một số dấu câu, trong khi object key phân biệt hoa/thường, hỗ trợ Unicode và tối đa **1.024 byte UTF-8**.

Trong một general purpose bucket, hai object `reports/2026/summary.csv` và `Reports/2026/summary.csv` là **hai key khác nhau**. Một key chỉ cần duy nhất trong bucket tại một thời điểm đối với phiên bản hiện hành. Nếu bucket bật versioning, cùng key có thể có nhiều **object versions**.

## 2. Thiết kế tên bucket trước khi triển khai

Một tên bucket tốt cần mô tả **ai sở hữu**, **môi trường**, **mục đích** và đôi khi **Region**, nhưng vẫn tuân thủ quy tắc của S3. Tên bucket là quyết định lâu dài: **không thể đổi tên hoặc đổi Region của bucket sau khi tạo**. Nếu cần tên/Region khác, thường phải tạo bucket mới, sao chép dữ liệu và cập nhật cấu hình/ứng dụng.

Tên bucket có thể xuất hiện trong URL, log, báo cáo, IAM policy và công cụ giám sát. **Không đặt bí mật, email khách hàng, tên cá nhân, token hoặc dữ liệu nhạy cảm vào bucket name**.

### 2.1. General purpose bucket: quy tắc cú pháp

Đối với **general purpose bucket**, các quy tắc chung gồm:

| Quy tắc | Chi tiết |
| --- | --- |
| Độ dài | Từ **3 đến 63 ký tự**, tính cả suffix bắt buộc nếu chọn namespace đặc biệt. |
| Ký tự cho phép | Chữ thường `a-z`, chữ số `0-9`, dấu gạch nối `-` và dấu chấm `.`. |
| Ký tự đầu/cuối | Phải là **chữ cái hoặc chữ số**. |
| Dấu chấm | Không được có hai dấu chấm liền nhau `..`. |
| Dạng địa chỉ IP | Không được có dạng địa chỉ IPv4, ví dụ `192.168.1.10`. |
| Chữ hoa, khoảng trắng, dấu gạch dưới | Không được phép. |
| Prefix dành riêng | Không bắt đầu bằng `xn--`, `sthree-` hoặc `amzn-s3-demo-`. |
| Suffix dành riêng | Không kết thúc bằng `-s3alias`, `--ol-s3`, `.mrap`, `--x-s3` hoặc `--table-s3`. |
| Suffix `-an` | Chỉ hợp lệ khi tạo bucket theo **account regional namespace** với đầy đủ quy ước. |

Các phần tên kết thúc bằng `-s3alias`, `.mrap` và `--x-s3` được dành cho những tài nguyên/cơ chế S3 khác; vì vậy không chọn suffix này cho tên general purpose bucket thông thường.

### 2.2. Ví dụ tên hợp lệ và không hợp lệ

| Tên minh họa | Đánh giá | Giải thích |
| --- | --- | --- |
| `storefront-prod-assets-ap-southeast-1-7c4f9e2a` | Hợp lệ về cú pháp | Chữ thường, dấu `-`, dài trong giới hạn, có chuỗi giảm khả năng trùng tên. |
| `team-a-logs-2026` | Hợp lệ về cú pháp | Tên đơn giản, dễ hiểu; phải kiểm tra còn khả dụng trong namespace. |
| `my.example.bucket` | Hợp lệ về cú pháp nhưng **không khuyến nghị** | Dấu chấm có thể gây vấn đề khi dùng virtual-hosted-style HTTPS và Transfer Acceleration. |
| `Storefront-Prod-Assets` | Không hợp lệ | Có chữ hoa. |
| `storefront_prod_assets` | Không hợp lệ | Có dấu gạch dưới. |
| `team..logs` | Không hợp lệ | Có hai dấu chấm liên tiếp. |
| `192.168.1.10` | Không hợp lệ | Giống địa chỉ IPv4. |
| `-prod-assets` | Không hợp lệ | Bắt đầu bằng dấu `-`. |
| `prod-assets-` | Không hợp lệ | Kết thúc bằng dấu `-`. |
| `prod.assets--x-s3` | Không hợp lệ cho general purpose bucket | Suffix dành cho directory bucket. |
| `example-data-111122223333-ap-southeast-1-an` | Hợp lệ **nếu** tạo trong account regional namespace của account đó và Region đó | Không tự coi là bucket shared global chỉ vì tên có đúng định dạng. |

**Hợp lệ về cú pháp chưa đồng nghĩa có thể tạo được.** Tên cũng phải chưa bị chiếm trong namespace tương ứng và được sử dụng theo chính sách/quota của account.

### 2.3. Vì sao nên tránh dấu chấm trong bucket name?

Tên `assets.company.example` có thể hợp lệ. Tuy nhiên, dấu `.` có những hạn chế khi dùng **virtual-hosted-style HTTPS**: chứng chỉ TLS wildcard của endpoint S3 có thể không khớp tên miền nhiều cấp. **S3 Transfer Acceleration** không cho phép tên bucket chứa dấu chấm.

Khuyến nghị cho ứng dụng hiện đại: ưu tiên `assets-company-example` hoặc tên không có dấu chấm, trừ khi bạn có yêu cầu rõ ràng như một cấu hình website/endpoint tương ứng và đã đánh giá toàn bộ khả năng tương thích.

## 3. Namespace: tính duy nhất của tên bucket

### 3.1. Shared global namespace

Với **general purpose bucket** trong shared global namespace, tên phải **duy nhất giữa tất cả AWS account và tất cả Region thuộc cùng AWS partition**. AWS partition là nhóm Region độc lập, chẳng hạn `aws`, `aws-cn`, `aws-us-gov` và `aws-eusc`.

Ví dụ: nếu account A đã tạo `company-orders-prod-ap-southeast-1-a1b2c3d4` trong Singapore ở partition `aws`, account B không thể dùng **chính tên đó** để tạo bucket general purpose tại Tokyo trong cùng partition.

Rủi ro đáng chú ý: nếu bạn **xóa** bucket thuộc shared global namespace, account khác có thể tạo lại bucket mang cùng tên sau đó và có nguy cơ nhận những request do hệ thống cũ vẫn gửi tới tên ấy. Nếu muốn giữ quyền kiểm soát một tên đã công bố, nên cân nhắc **dọn object và giữ bucket**, chặn truy cập không cần thiết thay vì xóa tên.

**Không dựa vào việc thêm mỗi `-prod` hoặc `-dev` để đảm bảo tên chưa bị chiếm.** Khi dùng shared global namespace, nên thêm hậu tố định danh ngẫu nhiên/GUID và có cơ chế xử lý `BucketAlreadyExists` khi triển khai tự động.

### 3.2. Account regional namespace

AWS hiện có thêm **account regional namespace** dành cho general purpose bucket. Đây là phần tên được dành riêng theo **AWS account + Region**, giúp bucket trong namespace này **chỉ có thể thuộc về chính account đó**, tránh bị account khác chiếm lại tên.

Định dạng:

```text
<bucket-prefix>-<12-digit-account-id>-<aws-region>-an

Ví dụ cho account 111122223333 ở Singapore:
storefront-prod-assets-111122223333-ap-southeast-1-an
```

Các điểm quan trọng:

- Tên đầy đủ vẫn không quá **63 ký tự**; phần hậu tố account/Region chiếm ngân sách ký tự của phần tên tự đặt.
- Khi tạo, request phải chọn namespace **`account-regional`** (ví dụ CLI `--bucket-namespace account-regional` hoặc API header `x-amz-bucket-namespace`).
- Chỉ account tương ứng mới được tạo bucket mang hậu tố này; nếu tên đã được chính account sử dụng, không thể tạo thêm bản sao cùng tên.
- Đây vẫn là **general purpose bucket**, có cùng khả năng S3 thông thường và yêu cầu IAM/Block Public Access như bucket khác.
- Tính năng khả dụng theo AWS Region; theo tài liệu hiện hành có ngoại lệ tại một số Region Trung Đông, nên kiểm tra bảng hỗ trợ trước khi chuẩn hóa toàn tổ chức.

**Khuyến nghị:** khi loại bucket, Region và tích hợp dịch vụ cho phép, ưu tiên account regional namespace để đảm bảo quyền sở hữu tên dài hạn. Shared global namespace vẫn hữu ích khi có yêu cầu tương thích/kiến trúc cụ thể hoặc Region chưa hỗ trợ.

### 3.3. Đề xuất convention đặt tên bucket

Với shared global namespace:

```text
<service>-<environment>-<purpose>-<region>-<unique-suffix>

storefront-prod-assets-ap-southeast-1-7c4f9e2a
payments-prod-receipts-ap-southeast-1-4d92a1bf
analytics-dev-raw-ap-northeast-1-6ca37e90
```

Với account regional namespace:

```text
<service>-<environment>-<purpose>-<account-id>-<region>-an

storefront-prod-assets-111122223333-ap-southeast-1-an
analytics-dev-raw-111122223333-ap-northeast-1-an
```

Đó là **quy ước thiết kế**, không phải cú pháp mà AWS bắt buộc cho phần `service/environment/purpose`. Nên thống nhất danh sách giá trị môi trường (ví dụ chỉ dùng `prod`, `staging`, `dev`) để tránh có cả `production`, `prd` và `prod` trong một tổ chức. Tránh dùng tên đội/phòng ban dễ đổi nếu tên bucket cần tồn tại nhiều năm.

## 4. Tên directory bucket khác general purpose bucket

Amazon S3 có loại **directory bucket** dành cho các nhu cầu và tính năng được hỗ trợ, thường liên quan S3 Express One Zone hoặc các cấu hình bucket kiểu directory. Quy tắc của nó **khác** general purpose bucket.

Một directory bucket có dạng:

```text
<base-name>--<zone-id>--x-s3

Ví dụ:
media-cache--apne1-az1--x-s3
```

Tên cần **duy nhất trong Zone** (Availability Zone hoặc Local Zone) được chọn, dài **3–63 ký tự tính cả suffix**, chỉ dùng chữ thường, số và dấu `-`, bắt đầu và kết thúc bằng chữ/số. Nó phải có suffix chứa **Zone ID** và `--x-s3`; không dùng dấu chấm. Một số prefix/suffix dành riêng tương tự general purpose bucket cũng không hợp lệ.

Phân biệt:

| Tiêu chí | General purpose bucket | Directory bucket |
| --- | --- | --- |
| Tên | Theo namespace shared global hoặc account regional. | `base-name--zone-id--x-s3`. |
| Phạm vi duy nhất | Trong namespace được chọn theo partition/account. | Trong **Zone** của bucket. |
| Ký tự dấu chấm | Cho phép theo quy tắc, nhưng thường nên tránh. | Không cho phép. |
| Cách tổ chức key | Flat namespace, các prefix dùng để mô phỏng folder. | **Hierarchical directory namespace** theo tính năng directory bucket được hỗ trợ. |
| Delimiter | Có thể chọn delimiter cho list; `/` là phổ biến. | `/` có vai trò riêng trong mô hình directory; kiểm tra yêu cầu của API. |
| API/tính năng | Đầy đủ khả năng general purpose bucket. | Có endpoint, hành vi LIST, điều kiện và API khác; không được suy ra tương đương hoàn toàn. |

**Bài này chủ yếu thiết kế cho general purpose bucket.** Khi chọn directory bucket, cần áp dụng đúng tài liệu riêng về key, directory, endpoint và thao tác tạo bucket. Cũng cần phân biệt **S3 Tables table bucket**: đó là một loại bucket chuyên cho dữ liệu bảng, có quy tắc đặt tên riêng và suffix dành riêng `--table-s3`.

## 5. Object key: danh tính thực sự của mỗi object

Với general purpose bucket, một **object key** là chuỗi Unicode được mã hóa UTF-8, dài tối đa **1.024 byte**. Giới hạn tính **toàn bộ chuỗi** gồm prefix, dấu `/` và tên file cuối cùng.

Ví dụ:

```text
images/products/2026/11/sku-1002-front.webp
└───────────── prefix ────────────┘└─tên object─┘

Key đầy đủ:
images/products/2026/11/sku-1002-front.webp
```

Các lưu ý:

- **Phân biệt chữ hoa/chữ thường:** `Customers/a.json` và `customers/a.json` là hai key.
- **UTF-8 tính theo byte:** một ký tự tiếng Việt có dấu thường chiếm nhiều hơn 1 byte; 1.024 ký tự Unicode **không** nhất thiết vừa 1.024 byte.
- **Dấu gạch chéo là một phần key:** `docs/a.pdf` và `docs//a.pdf` là hai key khác nhau.
- **Phần mở rộng là quy ước ứng dụng:** `.json`, `.jpg`, `.parquet` giúp con người/công cụ nhận biết kiểu dữ liệu nhưng S3 không bắt buộc key có phần mở rộng.
- **Key đầy đủ là danh tính:** di chuyển một object sang key mới trong general purpose bucket thường là **copy rồi delete** object cũ, có thể phát sinh request/data transfer và ảnh hưởng versioning/retention.

### 5.1. “Folder” trong general purpose bucket là gì?

General purpose bucket sử dụng **flat namespace**. Không có cây thư mục vật lý giống hệ điều hành. S3 console hiển thị folder bằng cách nhóm key theo **prefix** và delimiter:

```text
s3://storefront-prod-assets.../
    products/1002/front.webp
    products/1002/back.webp
    products/1003/front.webp
    reports/2026/11/sales.csv
```

Không cần thực hiện lệnh tạo folder trước khi ghi key `products/1002/front.webp`. Khi người dùng bấm **Create folder** trong S3 console, console có thể tạo object rỗng (0 byte) với key kết thúc `/` như `products/1002/` để hiển thị placeholder. Object rỗng này **là object thực** và có thể xuất hiện trong danh sách/chi phí request, khác với prefix được suy ra từ các key.

### 5.2. Prefix và delimiter phục vụ việc liệt kê

Giả sử bucket có bốn key:

```text
orders/2026/11/20/a.json
orders/2026/11/20/b.json
orders/2026/11/21/c.json
images/products/p01.webp
```

Nếu gọi `ListObjectsV2` với `Prefix=orders/2026/11/20/`, kết quả chỉ gồm các key bắt đầu bằng chuỗi đó. Nếu gọi `Prefix=orders/2026/11/` và `Delimiter=/`, API có thể gom những key phía dưới thành các `CommonPrefixes` như `orders/2026/11/20/` và `orders/2026/11/21/`.

**Prefix không phải một bộ lọc SQL.** S3 không tự hiểu điều kiện “tất cả đơn hàng có tổng tiền trên một triệu” nếu thông tin đó chỉ ở nội dung JSON. Bạn phải thiết kế key theo cách truy cập phổ biến hoặc dùng metadata/database/catalog/Athena và dịch vụ tìm kiếm tương ứng.

## 6. Ký tự đặc biệt, Unicode và URL

S3 cho phép nhiều ký tự UTF-8 trong object key, nhưng hệ sinh thái HTTP, SDK, CLI, XML và công cụ có thể xử lý các ký tự không giống nhau. Nên thống nhất bảng ký tự **dễ tương thích** cho hệ thống mới.

### 6.1. Quy ước nên ưu tiên

| Nhóm ký tự | Khuyến nghị |
| --- | --- |
| Chữ `a-z`, `A-Z`, số `0-9` | Hỗ trợ; thường thống nhất chữ thường cho key máy sinh để tránh nhầm. |
| Dấu `-`, `_`, `.` | Dùng khi có ý nghĩa rõ ràng; tránh dấu chấm cuối key. |
| Dấu `/` | Dùng nhất quán làm delimiter phân cấp logic. |
| Dấu cách và Unicode | Có thể dùng nhưng nên kiểm tra chuẩn hóa Unicode và URL encoding; cân nhắc thay dấu cách bằng `-`. |
| `?#%&+`, ký tự điều khiển hoặc xuống dòng | Có thể gây lỗi URL encoding, shell, XML hoặc parser; tránh trong key máy sinh. |
| Segment `.`, `..` | Tránh: nhiều thư viện/công cụ tự chuẩn hóa đường dẫn, gây thay đổi key ngoài ý muốn. |

Ví dụ:

| Object key | Đánh giá |
| --- | --- |
| `documents/2026/11/invoice-8f42.pdf` | Tốt: dễ đọc, ổn định, dễ list. |
| `users/42/avatar-4e2f.webp` | Tốt nếu ID đã được kiểm soát và người dùng có quyền phù hợp. |
| `reports/BaoCaoTháng11.xlsx` | Hợp lệ nếu trong giới hạn UTF-8, nhưng cần kiểm thử encoding ở pipeline. |
| `reports/2026/./nov.csv` | Tránh: segment `.` có thể bị chuẩn hóa. |
| `reports/2026/../nov.csv` | Tránh: segment `..` có thể bị công cụ xử lý như đường dẫn tương đối. |
| `users/alice@example.com/profile.json` | Không khuyến nghị: lộ email trong key/log/URL; dùng ID giả danh. |
| `exports/result.csv.` | Tránh: S3 console có thể loại dấu chấm cuối khi tải xuống. |

Các key bắt đầu bằng `./` không tải lên qua S3 console theo cách thông thường; key có segment `..` còn chịu quy tắc hợp lệ riêng và dễ gây hành vi ngoài ý muốn. Key đúng bằng `soap` có hạn chế với kiểu **virtual-hosted-style request**; tránh dùng tên này cho object cần truy cập qua URL dạng ấy.

### 6.2. Object key khác với URL path đã encode

Ví dụ object key là:

```text
images/holiday photo #1.jpg
```

Khi tạo HTTP URL, dấu cách và ký tự `#` cần được **percent-encode** theo quy tắc URI, nếu không `#1.jpg` có thể bị trình duyệt hiểu là fragment thay vì một phần key. Tương tự, dấu `+` có thể bị một số thành phần trung gian hiểu thành dấu cách.

**Không lấy nguyên chuỗi key từ người dùng rồi nối trực tiếp vào URL công khai.** Ưu tiên AWS SDK, presigned URL hoặc chức năng URI encoding chuẩn, đồng thời kiểm thử ký tự UTF-8 và các ký tự đặc biệt.

Với Unicode, cùng một chữ nhìn giống nhau có thể được biểu diễn bằng các chuỗi byte khác nhau (ví dụ Unicode precomposed/decomposed). S3 so sánh **key theo byte UTF-8**; nếu ứng dụng nhận văn bản người dùng, nên **chuẩn hóa Unicode** theo một quy tắc cố định trước khi sinh key.

### 6.3. Tránh nhầm key với đường dẫn hệ điều hành

Trên Windows, đường dẫn file dùng dấu `\`, còn key S3 nên dùng dấu `/`. Ví dụ đường dẫn local:

```text
C:\exports\2026\11\orders.json
```

Khi upload, nên ánh xạ tường minh sang key:

```text
exports/2026/11/orders.json
```

Đừng đưa các phần như ổ đĩa, tên máy, đường dẫn tuyệt đối hoặc dấu `..` từ người dùng vào key mà không kiểm tra. Key cần là định danh logic ổn định và an toàn với ứng dụng, không phụ thuộc hệ điều hành của máy upload.

## 7. Thiết kế key theo cách đọc và vòng đời dữ liệu

Một key convention tốt trả lời những câu hỏi: **ai sở hữu? dữ liệu thuộc loại gì? sẽ được list theo tiêu chí nào? khi nào xóa/chuyển storage class? có trùng khi ghi song song không?**

### 7.1. Bắt đầu từ mẫu truy vấn

Ví dụ hệ thống thương mại điện tử thường cần:

- Lấy một hóa đơn bằng ID.
- Liệt kê logs trong một ngày cụ thể.
- Xử lý dữ liệu raw theo lô ngày và Region.
- Giới hạn truy cập dữ liệu của từng tenant.

Ta có thể chọn:

```text
invoices/year=2026/month=11/id=inv-8f42.pdf
logs/service=checkout/year=2026/month=11/day=20/part-001.jsonl.gz
raw/source=payments/region=ap-southeast-1/year=2026/month=11/day=20/batch-0f1a.parquet
tenants/t-6f2d/assets/images/avatar-fc24.webp
```

Key có **prefix phù hợp ListObjectsV2**, không phải chỉ phục vụ việc trình bày như folder. Ví dụ cần list log tháng 11 thì `logs/service=checkout/year=2026/month=11/` có ích hơn đặt tên `all-logs/random-file` và quét toàn bucket.

### 7.2. Nên sắp xếp thứ tự các trường thế nào?

| Truy cập phổ biến | Prefix đề xuất | Điểm cần cân nhắc |
| --- | --- | --- |
| Theo dịch vụ rồi ngày | `logs/service=checkout/year=2026/month=11/day=20/` | Tốt khi người vận hành thường truy vấn một service tại một khoảng ngày. |
| Theo tenant rồi dataset | `tenants/t-6f2d/dataset=orders/year=2026/` | Dễ dùng IAM theo tenant/prefix nếu cấp quyền đúng, nhưng tenant ID không tự tạo bảo mật. |
| Theo ngày rồi nguồn | `landing/date=2026-11-20/source=payments/` | Thuận tiện cho batch xử lý tất cả nguồn trong một ngày. |
| Theo ID chính xác | `invoices/by-id/8f/42/inv-8f42.pdf` | Tạo lookup key ổn định; ứng dụng phải biết quy tắc băm/chia prefix. |

Không có một thứ tự prefix tối ưu cho mọi truy vấn. Chọn những truy vấn/công việc thường xảy ra nhất, sau đó cân nhắc **catalog/index** riêng khi cần tìm theo nhiều chiều. Sao chép cùng một object dưới nhiều key để phục vụ nhiều kiểu truy vấn có thể làm tăng storage, request và công quản lý vòng đời.

### 7.3. Thiết kế partition cho data lake

Trong data lake, convention dạng `key=value` thường tương thích tốt với những công cụ hỗ trợ Hive-style partitioning:

```text
dataset=orders/ingest_date=2026-11-20/region=ap-southeast-1/part-0001.parquet
dataset=orders/ingest_date=2026-11-20/region=ap-northeast-1/part-0002.parquet
dataset=orders/ingest_date=2026-11-21/region=ap-southeast-1/part-0003.parquet
```

Khi thiết kế, xác định rõ:

1. `ingest_date` là **ngày nhận dữ liệu** hay ngày sự kiện kinh doanh (`event_date`)? Hai trường có ý nghĩa khác nhau.
2. Quy ước thời gian **UTC** hay múi giờ doanh nghiệp? Tránh một pipeline dùng UTC, pipeline khác dùng giờ địa phương nhưng cùng tên partition.
3. Có cần phân vùng theo `region`, `tenant`, `service` không? Quá nhiều partition nhỏ có thể tạo nhiều file nhỏ, ảnh hưởng hiệu suất xử lý và chi phí request/catalog.
4. Có cơ chế **late-arriving data**, replay, idempotency và xóa dữ liệu đúng partition không?

**S3 không tự động tạo table hoặc partition metadata cho Athena/Glue chỉ vì key có `year=`.** Cần quản lý catalog và cấu hình ingest/query thích hợp.

### 7.4. Tránh ghi đè khi nhiều producer cùng upload

Nếu tất cả worker ghi `uploads/latest.json`, có thể xảy ra tranh chấp hoặc ghi đè ngoài ý muốn. Một thiết kế khác:

```text
uploads/year=2026/month=11/day=20/6fae77a0-c3a7-4d30-a153-aed42af91e8a.json
uploads/year=2026/month=11/day=20/e8a106bf-b5aa-4058-9fa2-7893abcb439d.json
```

Dùng ID duy nhất như UUID/ULID hoặc ID do nghiệp vụ cấp, và có chính sách rõ ràng cho việc retry. Nếu một sự kiện cần **idempotent**, có thể định nghĩa key dựa trên stable event ID, áp dụng conditional write (chẳng hạn `If-None-Match: *` qua API/SDK được hỗ trợ) hoặc phối hợp với database/queue để kiểm soát tác vụ.

**Bucket versioning** lưu lại nhiều phiên bản object dưới cùng key nếu bật và cấu hình phù hợp; nó giúp phục hồi ghi đè/xóa nhưng **không thay thế** thiết kế đồng bộ và cơ chế chống duplicate. Versioning cũng có thể phát sinh chi phí phiên bản cũ.

## 8. Prefix, bảo mật và quyền truy cập

Một key như `tenants/t-6f2d/private/contract.pdf` **không tự động là private** chỉ vì có chữ `private`. Quyền thực tế phụ thuộc IAM policy, bucket/access point policy, S3 Block Public Access, Object Ownership, encryption và các kiểm soát liên quan.

### 8.1. ListBucket và GetObject là hai quyền khác nhau

Đối với general purpose bucket:

- `s3:ListBucket` áp dụng lên **bucket ARN** và có thể giới hạn prefix yêu cầu thông qua điều kiện `s3:prefix`.
- `s3:GetObject` áp dụng lên **object ARN**, ví dụ `arn:aws:s3:::bucket-name/tenants/t-6f2d/*`.

Ví dụ policy **minh họa cho một IAM role** chỉ list và đọc object trong prefix tenant nhất định, với tên bucket đã được thay bằng tên thực tế:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListOnlyTenantPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::storefront-prod-assets-ap-southeast-1-a1b2c3d4",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "tenants/t-6f2d/",
            "tenants/t-6f2d/*"
          ]
        }
      }
    },
    {
      "Sid": "ReadOnlyTenantObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::storefront-prod-assets-ap-southeast-1-a1b2c3d4/tenants/t-6f2d/*"
    }
  ]
}
```

Policy này **không tự đảm bảo cách ly tenant hoàn chỉnh**. Cần xét chính sách khác, explicit Deny, quyền upload/delete, KMS key, presigned URLs, role assumption, access points và quy trình xử lý input của ứng dụng. Nếu role đã được cấp quyền S3 rộng ở nơi khác, một câu lệnh `Allow` hẹp không tự xóa quyền rộng ấy.

### 8.2. Kiểm soát dữ liệu người dùng trước khi ghép key

Giả sử API nhận `tenantId` và `filename` từ request:

```text
tenants/<tenantId>/uploads/<filename>
```

Không dùng trực tiếp `tenantId` do client gửi như bằng chứng quyền, và không cho `filename` mang `../`, dấu `/` hoặc các chuỗi gây phá cấu trúc mong muốn. Server nên xác thực người dùng, lấy tenant ID từ token/authorization đã xác minh, giới hạn tên file, sinh ID độc lập và chỉ cấp presigned URL trong vùng được phép.

**Tên key không phải cơ chế mã hóa.** Tránh đưa email, số điện thoại, mã bí mật hoặc dữ liệu cá nhân vào prefix/key, bởi tên có thể xuất hiện trong log, URL, audit và báo cáo.

## 9. Ảnh hưởng của prefix đến hiệu năng và chi phí

### 9.1. Hiệu năng S3 hiện đại

Amazon S3 tự động mở rộng theo lưu lượng và có thể đạt ít nhất **3.500 PUT/COPY/POST/DELETE** hoặc **5.500 GET/HEAD** request mỗi giây **trên mỗi partitioned prefix** cho general purpose bucket, tùy mẫu tải. Có thể tận dụng **nhiều prefix** và request song song cho workload cần throughput cao.

Điểm cần hiểu đúng:

- Đây là năng lực theo **request rate**, không phải lời hứa rằng mọi ứng dụng luôn nhận đúng tốc độ ấy ngay lập tức.
- Quá trình mở rộng diễn ra **dần dần**; khi tăng tải đột ngột có thể gặp HTTP `503 Slow Down` và cần retry với **exponential backoff/jitter**.
- **Không bắt buộc** thêm chuỗi ngẫu nhiên ở đầu tất cả object key. Thiết kế trước hết theo truy vấn và vận hành; chỉ phân bố qua nhiều prefix khi đặc điểm tải thực tế cần.
- Với xử lý song song rất lớn, có thể dùng các prefix phân bố công việc, ví dụ `shard=00/`, `shard=01/`, ..., nhưng phải có cơ chế biết shard để đọc lại dữ liệu.

Ví dụ `logs/service=checkout/year=2026/month=11/day=20/` hữu ích cho truy vấn theo ngày. Nếu tất cả worker cùng ghi vào một prefix vượt khả năng phục vụ, có thể thêm `shard=00..15/` hoặc nhóm prefix theo workload để phân phối request. Chỉ nên làm khi đã có metrics và hiểu cách liệt kê dữ liệu về sau.

### 9.2. Chi phí đến từ hành vi dùng key, không chỉ số byte lưu

Các khoản chi phí cần đánh giá gồm:

| Thành phần | Tác động của cách thiết kế key |
| --- | --- |
| **PUT/COPY/POST/LIST** | Nhiều object cực nhỏ hoặc quét prefix thường xuyên có thể tăng số request. |
| **GET/HEAD** | Đọc từng object riêng lẻ tăng số request; số file và cách chia file ảnh hưởng chi phí xử lý. |
| **Storage** | Object copies, versions cũ, lifecycle transitions và storage class ảnh hưởng dung lượng/phí. |
| **Inventory/analytics** | Có thể dùng S3 Inventory hoặc catalog để phân tích thay vì list toàn bucket lặp đi lặp lại. |
| **Data transfer** | Download và luồng ra khỏi AWS có biểu giá riêng, độc lập với việc key đẹp hay xấu. |

Một prefix có cấu trúc nhất quán giúp thiết lập **Lifecycle rule** theo prefix/tag, ví dụ chuyển `logs/` sang storage class khác hoặc xóa object đúng chính sách lưu giữ. Nhưng prefix **không tự kích hoạt** lifecycle; phải tạo và kiểm tra rule tương ứng. Hãy chú ý yêu cầu retention, Object Lock, versioning và pháp lý trước khi xóa dữ liệu.

### 9.3. Không dùng key làm hệ thống chỉ mục vạn năng

S3 hỗ trợ truy xuất theo **bucket + key** và list theo prefix. Khi cần truy vấn “tất cả đơn hàng của user X trên mọi tháng”, “toàn bộ hóa đơn quá hạn” hoặc “tìm kiếm toàn văn”, nên cân nhắc:

- **DynamoDB/RDS** lưu ID và key để truy xuất trực tiếp.
- **AWS Glue Data Catalog/Athena** cho dữ liệu phân tích có partition phù hợp.
- **S3 Inventory** cho đối soát số lượng lớn object/key/metadata.
- **OpenSearch** hoặc dịch vụ tìm kiếm chuyên dụng nếu cần tìm kiếm nội dung.

Thiết kế key tốt giảm độ phức tạp, nhưng không thay thế cơ sở dữ liệu quan hệ, chỉ mục thứ cấp hay công cụ phân tích.

## 10. Thực hành AWS CLI: tạo bucket và thử cấu trúc key

Các ví dụ bên dưới dùng **general purpose bucket** ở `ap-southeast-1`. Chạy trên môi trường thử nghiệm có AWS CLI cấu hình hợp lệ và quyền IAM tương ứng. Bucket/object phát sinh chi phí lưu trữ và request; dùng tên thực tế thuộc quyền sở hữu của bạn.

### 10.1. Kiểm tra danh tính trước khi tạo

```bash
aws sts get-caller-identity
aws configure get region
```

Từ output, ghi nhận **AWS account ID** và Region đã chọn. Không chạy thao tác tạo bucket vào nhầm account production.

### 10.2. Tạo bucket shared global namespace

Ví dụ một tên có chuỗi phân biệt (có thể đã có chủ sở hữu; thay hậu tố trước khi chạy):

```bash
aws s3api create-bucket \
  --bucket storefront-dev-assets-ap-southeast-1-7c4f9e2a \
  --region ap-southeast-1 \
  --create-bucket-configuration LocationConstraint=ap-southeast-1
```

Với Region ngoài `us-east-1`, cần `LocationConstraint` phù hợp. Riêng `us-east-1` có quy tắc tạo bucket khác; không sao chép nguyên lệnh trên rồi chỉ đổi Region mà không kiểm tra.

Nếu nhận `BucketAlreadyExists`, tên shared global đã có chủ sở hữu khác. Nếu `BucketAlreadyOwnedByYou`, không cần tạo lại bucket. Không nên tự động xóa bucket đang có để “giải phóng” tên.

### 10.3. Tạo bucket account regional namespace

Nếu account `111122223333` và Region `ap-southeast-1` phù hợp, ví dụ:

```bash
aws s3api create-bucket \
  --bucket storefront-dev-assets-111122223333-ap-southeast-1-an \
  --bucket-namespace account-regional \
  --region ap-southeast-1 \
  --create-bucket-configuration LocationConstraint=ap-southeast-1
```

**Phải thay `111122223333` bằng account ID thực tế** trước khi chạy, đồng thời kiểm tra độ dài tên và vùng hỗ trợ. Một tên có đuôi `-an` nhưng thiếu `--bucket-namespace account-regional` không phải là lệnh tạo đúng kiểu namespace này.

Chỉ cần chọn **một trong hai** ví dụ bucket cho bài lab; các bước dưới dùng `$BUCKET` đại diện cho tên đã tạo:

```bash
# Chọn tên bucket thật thuộc tài khoản thực hành.
BUCKET="storefront-dev-assets-ap-southeast-1-7c4f9e2a"
REGION="ap-southeast-1"

aws s3api head-bucket --bucket "$BUCKET" --region "$REGION"
```

Lệnh `head-bucket` xác nhận khả năng truy cập theo quyền hiện tại; phản hồi lỗi có thể do không tồn tại, không được phép hoặc sai Region. Có thể kiểm tra Region bằng `get-bucket-location` hoặc thông tin header phù hợp nếu được cấp quyền.

### 10.4. Upload object theo key đầy đủ

Giả sử máy đang có file `order.json` chứa JSON hợp lệ. Ví dụ:

```json
{
  "orderId": "ord-8f42",
  "createdAt": "2026-11-20T02:00:00Z",
  "status": "received"
}
```

Upload:

```bash
aws s3api put-object \
  --bucket "$BUCKET" \
  --key "orders/year=2026/month=11/day=20/order-8f42.json" \
  --body "./order.json" \
  --content-type "application/json" \
  --region "$REGION"
```

Không cần tạo folder `orders/`, `orders/year=2026/` hoặc `.../day=20/` trước. Đủ điều kiện IAM và cấu hình bucket, object được lưu đúng **key đầy đủ**. Nếu cùng key tồn tại và versioning không bật, lần ghi tiếp theo có thể thay object hiện tại; cân nhắc chiến lược chống ghi đè phù hợp.

Kiểm tra object:

```bash
aws s3api head-object \
  --bucket "$BUCKET" \
  --key "orders/year=2026/month=11/day=20/order-8f42.json" \
  --region "$REGION"
```

`head-object` trả metadata như `ContentLength`, `ContentType` và `LastModified` nếu quyền/đường truy cập đúng; không tải toàn bộ body.

### 10.5. Liệt kê object bằng prefix và delimiter

Liệt kê các đơn hàng của ngày 20/11:

```bash
aws s3api list-objects-v2 \
  --bucket "$BUCKET" \
  --prefix "orders/year=2026/month=11/day=20/" \
  --region "$REGION" \
  --query 'Contents[].Key'
```

Nhóm theo ngày trong tháng:

```bash
aws s3api list-objects-v2 \
  --bucket "$BUCKET" \
  --prefix "orders/year=2026/month=11/" \
  --delimiter "/" \
  --region "$REGION" \
  --query '{Objects:Contents[].Key,Prefixes:CommonPrefixes[].Prefix}'
```

Khi số object lớn, phải xét **pagination**; một phản hồi API có giới hạn số kết quả, còn AWS CLI có cơ chế phân trang mặc định và tham số `--max-items`/`--starting-token` khi cần kiểm soát. Không viết mã chỉ đọc trang đầu rồi kết luận prefix chỉ có bấy nhiêu object.

### 10.6. Kiểm tra key phân biệt hoa/thường

Nếu upload hai key:

```text
exports/Report.csv
exports/report.csv
```

Bạn sẽ có hai object riêng. Hãy xác định một convention cho ứng dụng (ví dụ toàn bộ prefix/key máy tạo là chữ thường) để tránh duplicate khó phát hiện, đặc biệt khi người dùng tải dữ liệu từ Windows hoặc hệ thống không phân biệt hoa/thường.

### 10.7. Dọn dẹp lab

Nếu chỉ tạo bucket thử nghiệm **không chứa dữ liệu thật**, có thể xóa object lab rồi xóa bucket theo quy trình S3 phù hợp. Với bucket đã bật versioning, việc xóa tất cả **current objects** chưa chắc làm bucket rỗng: các object versions và delete markers vẫn có thể tồn tại. Không dùng `aws s3 rb --force` tùy tiện trên bucket chứa dữ liệu chia sẻ.

Đối với bucket có tên công khai cố định trong shared global namespace, cân nhắc **giữ bucket trống** để bảo vệ tên thay vì xóa như đã nêu ở mục 3.

## 11. Quy trình thiết kế tên cho một hệ thống thực tế

Tình huống: công ty xây dựng ứng dụng bán hàng với hai môi trường `prod` và `dev`, lưu ảnh sản phẩm, hóa đơn PDF và log xử lý đơn hàng tại Singapore. Có nhu cầu:

- Hạn chế truy cập public; chỉ cấp URL tải hợp lệ khi người dùng được phép.
- Phân biệt môi trường và mục đích dữ liệu.
- Có thể liệt kê log theo ngày/dịch vụ, tra cứu hóa đơn theo ID và phục hồi khi ghi đè.
- Dùng lifecycle cho logs và theo dõi chi phí.

### 11.1. Đề xuất bucket

| Mục đích | Tên shared global minh họa | Gợi ý chính sách |
| --- | --- | --- |
| Ảnh sản phẩm production | `storefront-prod-assets-ap-southeast-1-7c4f9e2a` | Block Public Access, cấp quyền ứng dụng/CloudFront phù hợp. |
| Hóa đơn production | `storefront-prod-invoices-ap-southeast-1-8b1d27c4` | Bảo vệ dữ liệu, encryption, phiên bản/retention theo yêu cầu. |
| Log production | `storefront-prod-logs-ap-southeast-1-1ea40b23` | Lifecycle và quyền ghi/đọc riêng cho pipeline/log consumers. |
| Tài nguyên development | `storefront-dev-assets-ap-southeast-1-66d8a2f1` | Không dùng dữ liệu khách hàng thật nếu không cần. |

Nếu chọn account regional namespace, thay hậu tố ngẫu nhiên bằng suffix `-<account-id>-ap-southeast-1-an` theo đúng quy tắc và giới hạn 63 ký tự. Ví dụ trên chỉ minh họa cú pháp và có thể chưa có sẵn tên để tạo.

### 11.2. Đề xuất object key

```text
# Assets: mỗi ảnh có key ổn định theo product và ID ảnh
products/p-1002/images/img-6f2a.webp

# Invoices: truy cập chính xác theo invoice ID, không lộ email
invoices/year=2026/month=11/inv-8f42.pdf

# Logs: list theo service/ngày, có ID tránh đè file
logs/service=checkout/year=2026/month=11/day=20/part-8e2a.jsonl.gz
logs/service=payments/year=2026/month=11/day=20/part-d4c1.jsonl.gz
```

Ứng dụng nên lưu mapping `invoiceId → bucket + key` trong database nếu cần truy xuất thường xuyên mà không biết tháng, vì `ListObjectsV2` không phải một truy vấn database. Đối với dữ liệu nhạy cảm, phân quyền trên bucket/prefix/role và dùng presigned URL có thời hạn phù hợp khi cần phân phối object.

### 11.3. Quyết định theo vòng đời dữ liệu

1. **Ảnh sản phẩm:** key immutable khi mỗi lần upload tạo ảnh mới; cập nhật metadata/database trỏ tới key mới hoặc quản lý versioning nếu cần.
2. **Hóa đơn:** ID ổn định, kiểm soát sửa/xóa chặt, có retention/backup thích hợp; key không chứa họ tên hoặc email khách hàng.
3. **Log:** prefix theo `service` và `date` để dễ list và lifecycle; đặt object name độc lập tránh nhiều worker ghi đè.
4. **Dev:** bucket/role riêng; lifecycle ngắn hơn nếu phù hợp, theo dõi storage/request cost.
5. **Tất cả:** IAM least privilege, encryption mặc định phù hợp, Block Public Access, log/audit và quy trình thay đổi khi cần di chuyển key/bucket.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| `InvalidBucketName` khi tạo bucket | Có chữ hoa, dấu `_`, dấu chấm liền nhau, sai độ dài/suffix. | So với quy tắc naming của loại bucket/namespace đang tạo. |
| `BucketAlreadyExists` | Tên shared global đã thuộc account khác trong cùng partition. | Chọn tên khác, thêm GUID hoặc dùng account regional namespace. |
| `BucketAlreadyOwnedByYou` | Account đã sở hữu bucket tên đó. | Kiểm tra bucket và Region; không tạo trùng. |
| Tạo account regional bucket báo lỗi | Account ID/Region trong suffix sai, thiếu `--bucket-namespace` hoặc Region chưa hỗ trợ. | Kiểm tra chính xác định dạng `prefix-account-region-an` và request. |
| HTTPS gặp lỗi chứng chỉ với bucket chứa dấu chấm | Virtual-hosted-style TLS wildcard không khớp tên nhiều cấp. | Tránh dấu chấm hoặc thiết kế endpoint/certificate được hỗ trợ. |
| `NoSuchKey` dù console “nhìn giống tên” | Khác hoa/thường, ký tự Unicode, dấu cách, dấu `/` hoặc URL encoding. | Sao chép chính xác key từ metadata/ListObjects; xem byte/URL. |
| Upload file không hiện dưới folder mong muốn | Key thiếu hoặc thừa prefix/slash. | Kiểm tra key **đầy đủ** trong response và `head-object`. |
| List prefix không thấy hết object | Dùng sai prefix, filter không theo key, hoặc chưa xử lý pagination. | Kiểm tra `Prefix`, `Delimiter` và continuation token. |
| `AccessDenied` khi list/read | Thiếu quyền `s3:ListBucket`/`s3:GetObject` hoặc policy/KMS/SCP ngăn. | Kiểm tra bucket ARN và object ARN cùng conditions. |
| GET có lỗi `503 Slow Down` khi đột ngột tăng request | S3 đang mở rộng phân vùng hoặc workload quá tập trung. | Retry với exponential backoff, phân phối qua nhiều prefix nếu cần. |
| Xóa bucket không thành công | Còn objects, versions, delete markers, multipart uploads hoặc ràng buộc khác. | Kiểm kê và dọn đúng tài nguyên, không xóa nhầm bucket dùng chung. |

## 13. Bài tập tình huống

**Bối cảnh:** một doanh nghiệp có 12 AWS account và triển khai S3 tại Singapore/Tokyo. Nhóm dữ liệu muốn lưu log theo ngày, nhóm ứng dụng muốn phân phối ảnh sản phẩm, còn bộ phận kế toán cần giữ hóa đơn trong nhiều năm. Hiện tại, tên bucket lẫn lộn như `Data`, `files_prod` và `my.company.logs`; key log có dạng `log1.json`, `log2.json` nên khó truy vấn.

Hãy thiết kế:

1. Một convention tên bucket có thể dùng trong **account regional namespace**, chỉ ra cách phân biệt service, environment, purpose, account và Region.
2. Tên bucket hợp lệ cho ba loại dữ liệu; tên minh họa phải tuân thủ giới hạn 63 ký tự.
3. Key convention cho hóa đơn theo ID, ảnh theo product và logs theo service/ngày.
4. Một query list logs ngày `2026-11-20` bằng prefix.
5. IAM policy phân quyền chỉ đọc đúng `tenants/t-6f2d/` nhưng không cấp quyền tới tenant khác.
6. Kế hoạch chống duplicate khi có 100 worker upload cùng lúc.
7. Lifecycle rule theo prefix log và một cách đo storage/request cost.

**Gợi ý:** chọn namespace trước khi tạo bucket; tính độ dài suffix; dùng key ổn định hoặc ID bất biến; hạn chế thông tin nhạy cảm; xây dựng policy dựa trên bucket ARN + object ARN; đo request trước khi thêm shard ngẫu nhiên; dùng catalog/index nếu truy vấn cần nhiều chiều.

## 14. Những sai lầm phổ biến

**Sai lầm 1: “Bucket name chỉ cần duy nhất trong Region của tôi.”**  
Không đúng với **shared global namespace** của general purpose bucket: tên phải duy nhất trong toàn partition. Account regional namespace dùng quy tắc account+Region khác.

**Sai lầm 2: “Có thể đổi tên bucket sau khi tạo.”**  
Không đúng. Thay tên/Region thường cần bucket mới và kế hoạch di chuyển dữ liệu, quyền, endpoint, tài liệu tham chiếu.

**Sai lầm 3: “Folder là tài nguyên thật trong mọi S3 bucket.”**  
Không đúng với **general purpose bucket**: prefix mô phỏng phân cấp. Nhưng **directory bucket** hiện có hierarchical namespace và quy tắc riêng, không được đồng nhất hai loại.

**Sai lầm 4: “S3 không phân biệt chữ hoa/chữ thường trong object key.”**  
Không đúng. `Reports/a.csv` và `reports/a.csv` là hai key độc lập.

**Sai lầm 5: “Object key dài tối đa 1.024 ký tự tiếng Việt.”**  
Không đúng. Giới hạn là **1.024 byte UTF-8**, bao gồm prefix/delimiter.

**Sai lầm 6: “Dùng prefix tenants/t-123/private là dữ liệu tự được bảo vệ.”**  
Không đúng. Prefix chỉ là chuỗi key; bảo mật cần IAM, bucket/access point policy, Block Public Access, encryption và xác minh danh tính.

**Sai lầm 7: “Luôn phải thêm hash đầu key để S3 có hiệu năng tốt.”**  
Không đúng. S3 tự động mở rộng; chia nhiều prefix chỉ là một chiến lược khi lưu lượng thực tế cần, không thay thế thiết kế theo cách truy cập.

**Sai lầm 8: “ListObjectsV2 trả được mọi điều kiện tìm kiếm.”**  
Không đúng. S3 list theo prefix/delimiter, không lọc thuộc tính trong body như SQL.

**Sai lầm 9: “Xóa bucket rồi tạo lại sẽ luôn lấy được tên cũ.”**  
Không đúng với shared global namespace: tên có thể bị account khác đăng ký. Với account regional namespace, quy tắc sở hữu khác nhưng vẫn không thể tạo bucket trùng tên đang tồn tại.

**Sai lầm 10: “Dấu chấm hợp lệ trong bucket name thì tương thích với mọi tính năng.”**  
Không đúng. HTTPS virtual-hosted-style và S3 Transfer Acceleration có hạn chế.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Tên `Order_Prod` có tạo được general purpose bucket không?  
**Đáp án:** Không. Có chữ hoa và dấu gạch dưới `_`.

**Câu 2.** Trong shared global namespace, hai account ở Singapore và Tokyo có thể tạo cùng tên bucket không?  
**Đáp án:** Không nếu thuộc cùng AWS partition. Tên general purpose bucket trong shared global namespace phải duy nhất trong partition.

**Câu 3.** Suffix `-111122223333-ap-southeast-1-an` biểu thị điều gì?  
**Đáp án:** Account regional namespace cho account `111122223333` tại Region `ap-southeast-1`. Phải chọn đúng namespace khi gọi CreateBucket.

**Câu 4.** Object key `reports/2026/11/a.csv` có “nằm trong thư mục vật lý” `reports` của general purpose bucket không?  
**Đáp án:** Không. Đây là key flat; `reports/` là prefix logic được S3 console/CLI dùng để nhóm object.

**Câu 5.** Vì sao key `Báo cáo/2026.xlsx` có thể chiếm nhiều byte hơn số ký tự?  
**Đáp án:** Vì UTF-8 dùng nhiều byte cho một số ký tự Unicode. Giới hạn key là 1.024 **byte**.

**Câu 6.** Khi list object theo prefix `logs/year=2026/month=11/`, S3 có tự lọc nội dung file theo ngày giao dịch trong JSON không?  
**Đáp án:** Không. Chỉ những key bắt đầu bằng prefix này được xét; nội dung file không phải điều kiện của ListObjectsV2.

**Câu 7.** Bucket có dấu chấm `my.company.assets` có thể tạo không và nên dùng không?  
**Đáp án:** Có thể hợp lệ về cú pháp, nhưng không nên dùng nếu cần virtual-hosted-style HTTPS hoặc S3 Transfer Acceleration do giới hạn tên chứa dấu chấm.

**Câu 8.** Một user có `s3:GetObject` với ARN object trong `tenants/t-6f2d/*`, có được list mọi object trong bucket không?  
**Đáp án:** Không. `s3:ListBucket` là quyền riêng trên bucket; phải có IAM policy cho phép list, thường giới hạn `s3:prefix`.

**Câu 9.** Khi nhiều worker cùng ghi `uploads/latest.json`, có nguy cơ gì?  
**Đáp án:** Tranh chấp/ghi đè. Nên có key bất biến theo event/UUID, conditional write, versioning và kiểm soát idempotency theo yêu cầu.

**Câu 10.** Với directory bucket, có thể lấy quy tắc tên từ general purpose bucket rồi dùng trực tiếp không?  
**Đáp án:** Không. Directory bucket có suffix theo Zone ID và `--x-s3`, phạm vi duy nhất theo Zone, quy tắc delimiter và namespace khác.

## Tài liệu AWS chính thức

- [General purpose bucket naming rules](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html)
- [Namespaces for general purpose buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/gpbucketnamespaces.html)
- [Directory bucket naming rules](https://docs.aws.amazon.com/AmazonS3/latest/userguide/directory-bucket-naming-rules.html)
- [Working with directory buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/directory-buckets-overview.html)
- [Naming Amazon S3 objects](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-keys.html)
- [Organizing objects using prefixes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-prefixes.html)
- [ListObjectsV2 API](https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html)
- [Performance design patterns for Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-design-patterns.html)
- [Amazon S3 request performance best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html)
- [Amazon S3 access management](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-management.html)
- [AWS CLI — s3api create-bucket](https://docs.aws.amazon.com/cli/latest/reference/s3api/create-bucket.html)
- [AWS CLI — s3api list-objects-v2](https://docs.aws.amazon.com/cli/latest/reference/s3api/list-objects-v2.html)

**Ghi nhớ:** **Bucket name** quyết định danh tính, phạm vi sở hữu và khả năng tương thích của nơi lưu trữ; **object key** quyết định cách ứng dụng truy cập, liệt kê, phân quyền và quản lý vòng đời dữ liệu. Với general purpose bucket, hãy chọn đúng namespace, tên dễ hiểu và không lộ thông tin nhạy cảm; dùng prefix/key nhất quán theo access pattern, giữ an toàn khi xử lý Unicode/URL và áp quyền IAM cụ thể. Khi sử dụng **directory bucket** hoặc loại S3 bucket khác, phải áp dụng quy tắc đặt tên và API riêng cho loại đó.

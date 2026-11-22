# Xử lý throttling, service limits và thiếu compute capacity

Trong Oracle Cloud Infrastructure (OCI), một yêu cầu tạo máy ảo thất bại có thể bắt nguồn từ tốc độ gọi API, hạn mức tài nguyên của tenancy, quota của compartment hoặc lượng phần cứng còn trống tại vị trí triển khai. Các nguyên nhân này có thể xuất hiện nối tiếp trong cùng một lần mở rộng hệ thống, nhưng cần những cách xử lý khác nhau.

Bài học thuộc chương **Vận hành và xử lý sự cố** của module **CLOUD_PROVIDERS_ORACLE**. Trọng tâm là chẩn đoán và khôi phục hoạt động triển khai Compute có kiểm soát, đồng thời tính đến phân quyền IAM, mạng VCN, lưu trữ, cơ sở dữ liệu, giám sát và chi phí. Các số liệu, thời gian chờ và ngưỡng cảnh báo bên dưới là ví dụ thiết kế; giá trị thực tế phải lấy từ tenancy và dịch vụ đang vận hành.

## 1. Kết quả cần đạt

Sau bài này, người học có thể:

- Đọc HTTP status, mã lỗi và thông điệp để phân biệt throttling, service limit, compartment quota và thiếu host capacity.
- Kiểm tra đúng service, region, availability domain (AD), compartment và đơn vị tài nguyên.
- Thiết kế retry có backoff, jitter, deadline và cơ chế tránh tạo tài nguyên trùng.
- Chọn phương án giảm tải, điều chỉnh hạn mức hoặc thay đổi vị trí/shape phù hợp với ràng buộc ứng dụng.
- Chuẩn bị bằng chứng cho Oracle Support và theo dõi kết quả khôi phục bằng tín hiệu kỹ thuật lẫn chi phí.

Cần có kiến thức cơ bản về tenancy, compartment, IAM policy, region, AD, fault domain (FD), shape, OCPU, image, subnet và boot volume. Những lệnh thực hành dùng **Bash**, phù hợp với OCI Cloud Shell hoặc môi trường Bash đã cấu hình OCI CLI; không dán nguyên cú pháp xuống dòng của Bash vào PowerShell.

## 2. Phân biệt bốn lớp giới hạn

### 2.1. Throttling: yêu cầu đến quá nhanh

Throttling kiểm soát nhịp gọi dịch vụ. Một chương trình có thể chưa tạo thêm tài nguyên nào nhưng vẫn bị throttling vì liên tục gọi API liệt kê hoặc kiểm tra trạng thái. OCI mô tả phản hồi điển hình là HTTP **429**, mã **TooManyRequests**; hướng xử lý là giãn các lần gọi bằng exponential backoff. Không giả định mọi API có cùng ngưỡng hoặc cùng phạm vi áp dụng. Xem [REST APIs — Request Throttling](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/usingapi.htm).

Ví dụ: 30 pipeline cùng kiểm tra instance mỗi giây có thể gây nhiều yêu cầu dù số máy ảo đang chạy không tăng. Giảm nhịp polling và điều phối các pipeline xử lý trực tiếp nguồn phát sinh áp lực này.

### 2.2. Service limit: lượng tài nguyên được phép sử dụng

Service limit là hạn mức Oracle áp dụng cho tài nguyên. Cần đọc cả **tên limit, đơn vị và scope**: limit theo region khác limit theo AD; số OCPU khác số instance; dung lượng bộ nhớ khác dung lượng volume. Không lấy số mặc định trên một bảng tài liệu làm hạn mức chắc chắn của tenancy. Giá trị còn phụ thuộc tài khoản, subscription và các điều chỉnh đã được áp dụng. Xem [Limits by Service](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm).

Ví dụ: còn chỗ cho một instance không có nghĩa là còn đủ 16 OCPU cho shape được yêu cầu. Khi nhu cầu thực vượt allowance, cần giảm nhu cầu, thu hồi tài nguyên phù hợp hoặc yêu cầu tăng đúng limit.

### 2.3. Compartment quota: phân bổ nội bộ

Quota là cơ chế quản trị phân bổ tài nguyên giữa các compartment. Khi kiểm tra phải xét cả policy áp dụng từ compartment cha, điều kiện và các policy cùng tác động. Trong một policy, thứ tự statement có ý nghĩa; giữa nhiều policy áp dụng cùng tài nguyên, quy tắc hạn chế hơn được ưu tiên. Quota lớn hơn service limit cũng không làm tăng service limit. Xem [Quota Policy Syntax — Evaluation and Precedence](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/quota_policy_syntax.htm).

Ví dụ: tenancy còn tài nguyên nhưng compartment **dev** đã dùng hết phần được phân bổ. Chuyển workload sang compartment khác chỉ để tránh quota làm sai mục đích quản trị; cần chủ sở hữu quota xem xét lại phân bổ và nhu cầu thực.

### 2.4. Compute capacity: phần cứng thực tế còn đáp ứng được không

Host capacity là khả năng bố trí yêu cầu lên hạ tầng vật lý. Khả năng đó thay đổi theo thời điểm, shape và vị trí. Một tenancy đủ hạn mức vẫn có thể không tìm được host đáp ứng cấu hình yêu cầu. Oracle đề xuất kiểm tra các lựa chọn shape, FD và AD khi gặp thiếu capacity. Xem [Resolving Out of Host Capacity error](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/troubleshooting-out-of-host-capacity.htm).

Có thể hình dung một lần triển khai thành công cần đồng thời thỏa mãn:

~~~text
Yêu cầu hợp lệ và được IAM cho phép
  + Nhịp gọi API được chấp nhận
  + Còn service limit trong đúng scope
  + Còn quota có hiệu lực tại compartment
  + Có host capacity cho cấu hình và vị trí được chọn
  + Các phụ thuộc mạng, image, volume đáp ứng yêu cầu
~~~

Đây là các điều kiện cần để tư duy chẩn đoán, không phải thứ tự kiểm tra nội bộ được OCI cam kết.

## 3. Đọc lỗi trước khi chọn biện pháp

| Dấu hiệu | Cách hiểu ban đầu | Hành động ưu tiên |
|---|---|---|
| 429 TooManyRequests | Nhịp yêu cầu vượt mức dịch vụ chấp nhận | Giảm tốc độ, giảm đồng thời, retry có backoff |
| 400 LimitExceeded | Vượt allowance Oracle đặt cho tài nguyên | Kiểm tra limit, usage, scope và nhu cầu tăng thêm |
| 400 QuotaExceeded | Vượt quota do quản trị viên đặt | Xác định policy quota và người quản lý phân bổ |
| InternalError kèm thông điệp Out of host capacity khi launch Compute | Không bố trí được host cho yêu cầu hiện tại | Kiểm tra capacity và các phương án placement/shape |
| 401, 403, 404 NotAuthorizedOrNotFound | Có thể liên quan xác thực, quyền hoặc định danh | Kiểm tra principal, policy, region và OCID |
| Timeout hoặc lỗi máy chủ khác | Kết quả có thể chưa rõ hoặc dịch vụ lỗi tạm thời | Đối soát trạng thái rồi quyết định retry |

Ba mã lỗi đầu và lỗi phân quyền được mô tả trong [API Errors](https://docs.oracle.com/en-us/iaas/Content/API/References/apierrors.htm). Riêng Compute có trường hợp thiếu host trả về **InternalError**, được nêu tại [Known Issues for Compute](https://docs.oracle.com/en-us/iaas/Content/Compute/known-issues.htm). Vì vậy phải đọc **cả code lẫn message**; không phân loại mọi lỗi 5xx thành thiếu capacity.

Ví dụ phản hồi minh họa:

~~~json
{
  "status": 429,
  "code": "TooManyRequests",
  "message": "User-rate limit exceeded.",
  "opc-request-id": "example-request-id"
}
~~~

Không chỉ lưu chuỗi “launch failed”: cách ghi đó làm mất dữ kiện cần để phân biệt nguyên nhân. Với API bất đồng bộ, phản hồi chấp nhận thao tác cũng chưa chứng minh tài nguyên đã sẵn sàng; tiếp tục theo dõi trạng thái tài nguyên và work request nếu thao tác đó có work request.

## 4. Quy trình chẩn đoán trong một sự cố

~~~mermaid
flowchart TD
    A[Triển khai hoặc mở rộng thất bại] --> B[Lưu lỗi và ngữ cảnh yêu cầu]
    B --> C{Phân loại bằng code và message}
    C -->|TooManyRequests| D[Giảm nhịp và retry có giới hạn]
    C -->|LimitExceeded| E[Kiểm tra limit và usage đúng scope]
    C -->|QuotaExceeded| F[Kiểm tra quota có hiệu lực]
    C -->|Out of host capacity| G[Kiểm tra capacity và phương án thay thế]
    C -->|Lỗi khác| H[Điều tra IAM, cấu hình hoặc dịch vụ]
    D --> I[Đối soát tài nguyên và trạng thái ứng dụng]
    E --> I
    F --> I
    G --> I
    H --> I
    I --> J{Đã đạt mức phục vụ mục tiêu?}
    J -->|Chưa| B
    J -->|Rồi| K[Ổn định lưu lượng và ghi nhận nguyên nhân]
~~~

Trước khi thay đổi cấu hình, ghi lại tối thiểu:

| Nhóm dữ kiện | Nội dung cần lưu |
|---|---|
| Thời gian | Mốc UTC, khoảng thời gian lỗi, thời điểm thành công gần nhất |
| Định danh | Tenancy, compartment, region, AD, FD nếu có, resource/work request OCID liên quan |
| Yêu cầu | API operation, shape, OCPU, memory, image, số instance, loại capacity |
| Lỗi | HTTP status, code, message, opc-request-id của từng lần gọi quan trọng |
| Client | Công cụ/SDK và phiên bản, profile hoặc principal, timeout, cấu hình retry |
| Mức tải | Số pipeline/worker, tần suất polling, request rate, số lần retry |
| Phụ thuộc | Subnet, volume, endpoint cơ sở dữ liệu và các ràng buộc placement |

Chỉ chia sẻ thông tin cần thiết qua kênh phù hợp; loại bỏ private key, token và dữ liệu ứng dụng khỏi bản trích log. Ghi rõ lần gọi có nhận được OCID hay chưa để người xử lý tiếp không vô tình tạo thêm một nhóm tài nguyên.

## 5. Kiểm tra limits và usage bằng OCI CLI

### 5.1. Chuẩn bị ngữ cảnh và quyền

Các giá trị dưới đây là placeholder, phải thay bằng giá trị thật. Chọn một profile có quyền quan sát phù hợp, tránh dùng tài khoản quản trị toàn tenancy cho một tác vụ đọc thông thường.

~~~bash
export OCI_CLI_PROFILE='OPS_READONLY'
export TENANCY_OCID='<tenancy-ocid>'
export TARGET_COMPARTMENT_OCID='<workload-compartment-ocid>'
export REGION='<region-identifier>'
export AD='<availability-domain-name>'
~~~

Đối với Limits API, quyền xem definitions/services/values được xét ở tenancy; việc lấy resource availability cần quyền đọc tại compartment thích hợp. Ví dụ policy quan sát, để quản trị viên điều chỉnh theo cấu trúc nhóm thực tế:

~~~text
Allow group LimitsAndUsageViewers to inspect resource-availability in tenancy
Allow group LimitsAndUsageViewers to read resource-availability in compartment AppProd
~~~

Các quyền này không tự cấp quyền tạo instance, sửa quota hoặc quản lý capacity reservation. Xem [Service Limits — Required IAM Policy](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm).

### 5.2. Tìm đúng service và định nghĩa limit

Liệt kê service name mà Limits API hỗ trợ:

~~~bash
oci limits service list \
  --compartment-id "$TENANCY_OCID" \
  --region "$REGION" \
  --all
~~~

Lấy **programmatic name** từ kết quả, sau đó kiểm tra definitions:

~~~bash
export LIMITS_SERVICE='<service-name-from-result>'

oci limits definition list \
  --compartment-id "$TENANCY_OCID" \
  --service-name "$LIMITS_SERVICE" \
  --region "$REGION" \
  --all
~~~

Ghi lại name, mô tả, scope-type và đơn vị. Kiểm tra are-quotas-supported nếu muốn quản lý tài nguyên đó bằng quota. Không suy tên limit từ tên thương mại của shape. Tham khảo [service list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/service/list.html) và [definition list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/definition/list.html).

### 5.3. Lấy giá trị allowance

~~~bash
oci limits value list \
  --compartment-id "$TENANCY_OCID" \
  --service-name "$LIMITS_SERVICE" \
  --region "$REGION" \
  --all
~~~

Đối chiếu mục có đúng name và scope. Khi lọc bằng **--availability-domain**, lệnh chỉ trả về các giá trị theo AD tương ứng; đừng dùng bộ lọc đó rồi kết luận limit theo region đã biến mất. Xem [limits value list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/value/list.html).

### 5.4. Lấy usage và availability tại compartment đích

Với limit theo AD:

~~~bash
export LIMIT_NAME='<exact-limit-name>'

oci limits resource-availability get \
  --compartment-id "$TARGET_COMPARTMENT_OCID" \
  --service-name "$LIMITS_SERVICE" \
  --limit-name "$LIMIT_NAME" \
  --availability-domain "$AD" \
  --region "$REGION"
~~~

Nếu limit theo region hoặc global, bỏ tham số **--availability-domain**. API này không hỗ trợ mọi limit; tài liệu nêu có thể trả 404 khi giá trị không khả dụng. Phân biệt tình huống đó với lỗi quyền hoặc OCID trước khi kết luận. Xem [resource-availability get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability/get.html).

**Availability trong Limits API là lượng còn được phép cấp phát theo hạn mức/quota; không phải số host vật lý đang rảnh.** Khái niệm đó dựa trên usage, service limits và quotas, như mô tả tại [resource-availability](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability.html).

Nếu kết quả khó hiểu, lập bảng đối chiếu theo cùng một mốc thời gian:

~~~text
service | limit-name | unit | scope | usage | limit | available
~~~

Không coi dữ liệu trống là 0 hoặc vô hạn. Khi nhiều pipeline cùng cấp phát, dữ liệu vừa đọc có thể không còn phản ánh tình trạng lúc yêu cầu tiếp theo được xử lý. Preflight giúp phát hiện thiếu hụt dự kiến, còn phản hồi của thao tác thực mới cho biết kết quả cuối cùng.

## 6. Xử lý throttling mà không tạo thêm áp lực

### 6.1. Giảm số yêu cầu phát sinh

Bắt đầu từ nguồn gọi, kể cả khi SDK đã hỗ trợ retry:

1. Giới hạn số pipeline cùng chạy một đợt triển khai.
2. Dùng hàng đợi và số worker hữu hạn cho các thao tác tạo/sửa tài nguyên.
3. Giảm polling, tăng khoảng chờ khi tài nguyên vẫn ở trạng thái đang xử lý.
4. Tránh để nhiều worker cùng truy vấn toàn bộ tài nguyên để tìm cùng một OCID; chia sẻ kết quả phù hợp và dùng truy vấn có phạm vi hẹp.
5. Dàn thời điểm chạy inventory, đồng bộ và các công việc định kỳ để tránh dồn vào cùng một phút.

Concurrency và request rate liên quan nhưng khác nhau. Hai worker vẫn có thể tạo ra nhịp gọi rất cao nếu mỗi request kết thúc nhanh. Có thể kết hợp semaphore giới hạn số request đang xử lý với token bucket giới hạn số request bắt đầu theo thời gian. Nếu nhiều tiến trình dùng chung một allowance, bộ điều phối phải tính đến tổng tải của chúng.

### 6.2. Backoff, jitter và ngân sách retry

Backoff tăng khoảng chờ sau các lần thất bại liên tiếp. Jitter thêm tính ngẫu nhiên để các client không cùng thức dậy và retry một lúc. OCI Python SDK trình bày nhiều chiến lược, trong đó equal jitter giữ một phần thời gian chờ tối thiểu và thêm phần ngẫu nhiên; đây là một lựa chọn phù hợp để minh họa xử lý throttling. Xem [SDK Retry Behaviors](https://docs.oracle.com/en-us/iaas/tools/python/latest/sdk_behaviors/retries.html).

Ví dụ thiết kế sau dùng tối đa 6 lần gọi, tính cả lần đầu, với deadline chung 120 giây. Đây là pseudocode, không phải cấu hình mặc định OCI:

~~~text
maxAttempts = 6
baseDelay = 2 seconds
maxDelay = 30 seconds
deadline = monotonicNow() + 120 seconds

for attempt in 1..maxAttempts:
    remaining = deadline - monotonicNow()
    if remaining <= 0:
        stop with RETRY_BUDGET_EXHAUSTED

    acquire rate/concurrency permit within remaining time
    recompute remaining time
    if no permit or remaining <= 0:
        stop with RETRY_BUDGET_EXHAUSTED

    result = callOnce(timeout bounded by remaining)
    release concurrency permit

    if result is success:
        return result

    if result is not the intended throttling condition:
        return result to the appropriate handler

    if attempt == maxAttempts:
        return result with ATTEMPTS_EXHAUSTED

    ceiling = min(maxDelay, baseDelay * 2^(attempt - 1))
    delay = ceiling / 2 + random(0, ceiling / 2)

    if a valid server Retry-After hint is present:
        delay = max(delay, parsed server delay)

    if monotonicNow() + delay >= deadline:
        stop with RETRY_BUDGET_EXHAUSTED

    wait interruptibly for delay
~~~

**callOnce** phải được hiểu là một lần gọi ở lớp đang được kiểm soát. Nếu SDK tự retry bên trong, cần tính cả các lần gọi đó vào ngân sách hoặc giao toàn bộ trách nhiệm retry cho SDK. Không giả định mọi phản hồi OCI đều có Retry-After; nếu có, client cần phân tích đúng định dạng. Deadline phải bao gồm thời gian chờ permit, thời gian request và thời gian backoff.

Các khoảng equal jitter trong ví dụ lần lượt nằm trong khoảng 1–2, 2–4, 4–8, 8–16 và 15–30 giây. Trên thực tế, một request chậm có thể tiêu hết deadline trước khi đạt lần thử cuối.

### 6.3. Tránh retry ở quá nhiều tầng

Giả sử pipeline thử lại 3 lần, wrapper thử lại 3 lần và SDK thử lại 3 lần cho cùng một thao tác. Trong trường hợp xấu, có thể phát sinh tới **3 × 3 × 3 = 27 lần gọi** cho một ý định ban đầu, nếu mỗi tầng cho phép tổng cộng 3 lần thử. Hãy chỉ định rõ tầng sở hữu retry và ghi metric cho số lần gọi thực.

Không sao chép nguyên chính sách retry của SDK khác sang ứng dụng hiện tại. Kiểm tra đúng ngôn ngữ, phiên bản, service operation và cấu hình được bật. Ví dụ tài liệu [OCI Python SDK Retry API](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/retry.html) phân biệt chiến lược retry, số lần thử và giới hạn thời gian; những giá trị đó không đại diện cho mọi công cụ OCI.

### 6.4. Timeout không đồng nghĩa thao tác chưa xảy ra

Một yêu cầu tạo tài nguyên có thể đã được nhận nhưng phản hồi bị mất. Retry thiếu kiểm soát có thể tạo thêm instance hoặc volume ngoài ý muốn. Quy trình nên lưu một operation ID của ứng dụng và liên kết nó với OCID khi nhận được kết quả.

Với operation có hỗ trợ idempotency token, giữ token cho các lần retry của **cùng một ý định và cùng nội dung yêu cầu**, theo contract của API. Nếu đổi shape hoặc AD, đó là một yêu cầu khác cần được điều phối riêng. Nếu kết quả cũ chưa rõ, đối soát trước khi khởi chạy phương án mới. Tên hiển thị giống nhau không bảo đảm tài nguyên là duy nhất.

Các nguyên tắc về retry token được mô tả trong [REST APIs — Retry Tokens](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/usingapi.htm). Không coi **opc-request-id**, vốn dùng truy vết từng request, là token chống tạo trùng.

## 7. Xử lý service limit và compartment quota

### 7.1. Tính phần tăng thêm trong cùng scope

Giả sử nhóm vận hành muốn thêm 4 VM, mỗi VM dùng 4 OCPU và 32 GiB memory. Sau khi chuẩn hóa số liệu về đúng scope của các limit/quota tương ứng, có bảng giả định:

| Ràng buộc đang xét | Trần | Đã dùng | Còn lại | Nhu cầu của 4 VM |
|---|---:|---:|---:|---:|
| Service limit OCPU tại scope đích | 64 OCPU | 52 OCPU | 12 OCPU | 16 OCPU |
| Quota OCPU tại compartment đích | 32 OCPU | 24 OCPU | 8 OCPU | 16 OCPU |
| Allowance memory có hiệu lực đang xét | 400 GiB | 320 GiB | 80 GiB | 128 GiB |

Theo các ràng buộc trong bảng:

~~~text
Số VM thêm được về mặt allowance
  <= min(floor(12 / 4), floor(8 / 4), floor(80 / 32))
  = min(3, 2, 2)
  = 2
~~~

Ngay cả 2 VM cũng chỉ là cận trên của phần allowance đã xét; vẫn phải kiểm tra capacity và các phụ thuộc. Không dùng phép tính này khi các usage chưa cùng phạm vi với trần tương ứng, hoặc khi các VM thuộc những shape family bị tính vào các limit khác nhau.

### 7.2. Khi lỗi là LimitExceeded

Thực hiện theo thứ tự:

1. Xác định chính xác tài nguyên đang vướng limit, kể cả tài nguyên phụ thuộc. Launch Compute có thể liên quan đến boot volume, địa chỉ IP và các tài nguyên khác ngoài OCPU.
2. Đọc lại limit và usage ở đúng region/AD; xem các đợt cấp phát đang chạy đồng thời.
3. Kiểm kê tài nguyên có thể thu hồi cùng chủ sở hữu. Không xóa tài nguyên chỉ vì ít CPU: nó có thể phục vụ dự phòng hoặc lưu trạng thái.
4. Nếu thay đổi thiết kế phù hợp, giảm batch hoặc chuyển sang cấu hình đã kiểm chứng và có allowance riêng còn đáp ứng được.
5. Nếu nhu cầu hợp lệ vượt trần, gửi yêu cầu tăng đúng limit và theo dõi đến khi giá trị mới thực sự xuất hiện.

Trong Console, dùng trang **Limits, Quotas and Usage** để kiểm tra. Luồng yêu cầu tăng hiện được tài liệu mô tả qua menu **Help → Request a limit increase**; điền lý do, chọn service/limit, giá trị đích và scope cần thiết, sau đó rà soát trước khi gửi. Không mặc định yêu cầu sẽ được duyệt ngay. Xem [Creating a Limit Increase Request](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/create-request.htm).

Một mô tả nhu cầu hữu ích nên chứa:

~~~text
Mục tiêu: bổ sung nhóm worker trước đợt xử lý dữ liệu tháng.
Vị trí: region và AD tương ứng với limit cần tăng.
Hiện trạng: limit, usage, tên limit và đơn vị đã xác nhận.
Nhu cầu đỉnh: tải hiện hữu + mở rộng + phần chồng lấp khi rollout.
Đề nghị: giá trị tổng sau điều chỉnh, không chỉ phần cần tăng thêm.
Thời điểm cần: mốc triển khai và ảnh hưởng nếu chưa đáp ứng.
Phương án tạm: chia batch hoặc dùng nhóm worker hiện hữu.
~~~

Sau khi limit được tăng, vẫn kiểm tra quota và capacity riêng. Tăng allowance không tạo thêm host vật lý tại AD đang thiếu.

### 7.3. Khi lỗi là QuotaExceeded

Cần người quản trị quota kiểm tra:

- Tài nguyên đang thuộc compartment nào, có bị tính trong quota của compartment cha không.
- Có policy khác cùng áp dụng hoặc điều kiện giới hạn theo vị trí không.
- Usage tăng do nhu cầu thật, tài nguyên dư hay những lần retry tạo trùng.
- Cần tăng phần phân bổ của compartment, thu hồi phần chưa dùng ở nơi khác, hay điều chỉnh cách triển khai.

Thay đổi quota phải được quản lý như thay đổi phân bổ tài nguyên: ghi mục đích, mức mới, nhóm chịu chi phí và thời điểm xem lại. Không sửa policy theo chuỗi lỗi rồi bỏ qua tác động lên các nhóm khác. Nếu hạ tầng được quản lý bằng mã, cập nhật nguồn cấu hình được nhóm sử dụng để tránh lần triển khai sau ghi đè cấu hình Console.

## 8. Xử lý thiếu compute capacity

### 8.1. Kiểm tra capacity cho đúng cấu hình

Compute capacity report là công cụ khác với Limits API. Báo cáo được tạo cho một AD; tham số compartment phải là **root compartment**, tức tenancy OCID. Lệnh tạo báo cáo không launch VM và cần quyền IAM dành cho báo cáo. Xem [compute-capacity-report create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/compute-capacity-report/create.html).

Ví dụ dưới dùng **VM.Standard.E4.Flex** với 2 OCPU và 32 GiB chỉ để minh họa. Trước khi áp dụng, xác nhận shape và cấu hình đó phù hợp với region, image và workload.

~~~bash
cat > shape-availabilities.json <<'JSON'
[
  {
    "instanceShape": "VM.Standard.E4.Flex",
    "instanceShapeConfig": {
      "ocpus": 2,
      "memoryInGBs": 32
    }
  }
]
JSON

oci compute compute-capacity-report create \
  --compartment-id "$TENANCY_OCID" \
  --availability-domain "$AD" \
  --shape-availabilities file://shape-availabilities.json \
  --region "$REGION"
~~~

Các trường đáng đọc gồm **availability-status**, **available-count** và cấu hình shape tương ứng. Các trạng thái được định nghĩa gồm **AVAILABLE**, **OUT_OF_HOST_CAPACITY**, **HARDWARE_NOT_SUPPORTED**; số lượng khả dụng gắn với cấu hình đã truy vấn. Xem [Capacity Report Shape Availability — Common Types](https://docs.oracle.com/en-us/iaas/Content/pl-sql-sdk/doc/core_t.html).

AVAILABLE là tín hiệu tại thời điểm kiểm tra, không giữ chỗ cho lần launch sau. Oracle cũng nêu tính chất này trong hướng dẫn dùng capacity report khi xử lý [OCI Database with PostgreSQL Troubleshooting](https://docs.oracle.com/en-us/iaas/Content/postgresql/troubleshooting.htm). Chỉ tạo báo cáo theo nhịp hợp lý; polling chính báo cáo quá nhanh cũng làm tăng tải API.

### 8.2. Chọn phương án thay thế có chủ đích

| Phương án | Kiểm tra trước khi áp dụng | Đánh đổi cần theo dõi |
|---|---|---|
| Bỏ ghim FD khi thiết kế cho phép | Yêu cầu phân tán và quy tắc placement của hệ thống | Phân bố instance thực tế có thể thay đổi |
| Chọn FD khác trong cùng AD | Khả năng bố trí và phụ thuộc placement | Cần kiểm tra lại phân tán lỗi |
| Dùng cấu hình Flex nhỏ hơn | Mức tối thiểu OCPU/memory và hiệu năng ứng dụng | Có thể phải tăng số instance hoặc giảm throughput |
| Dùng shape family khác | CPU architecture, image, driver, giới hạn và license | Chi phí, hiệu năng và kết quả benchmark thay đổi |
| Chuyển sang AD khác nếu region có lựa chọn đó | Subnet, volume, image và vị trí dữ liệu | Thay đổi phụ thuộc theo AD và độ trễ |
| Chuyển region theo kế hoạch dự phòng | Đồng bộ dữ liệu, network, IAM, endpoint và yêu cầu lưu trú | Thời gian khôi phục và chi phí truyền/lưu trữ |
| Chờ rồi thử lại có giới hạn | Deadline nghiệp vụ và tác động hiện tại | Không có bảo đảm thời điểm xuất hiện capacity |

Thứ tự lựa chọn phụ thuộc vào ứng dụng. Với một dịch vụ Java stateless, đổi sang shape tương thích đã benchmark có thể nhanh hơn chuyển region. Với cơ sở dữ liệu có volume và cơ chế replication riêng, cần quy trình khôi phục dữ liệu cùng ứng dụng.

Không bỏ FD pinning nếu nó là một phần của yêu cầu phân tán lỗi mà chưa đánh giá lại thiết kế. Không coi mọi region đều có nhiều AD. Không tự động chuyển từ x86 sang Arm chỉ vì shape còn capacity: JVM, native library, container image và công cụ giám sát đều cần tương thích.

### 8.3. Xem lại mạng và dữ liệu khi đổi placement

Một VM tạo được nhưng không truy cập được cơ sở dữ liệu chưa phải kết quả khôi phục đạt yêu cầu. Trước khi đổi AD hoặc region, rà soát:

- Subnet regional hay gắn với AD; còn IP riêng và phù hợp với vị trí mới không.
- Route table, NSG/security list, DNS, NAT/service gateway và đường kết nối đến hệ thống khác.
- Image có dùng được tại vị trí đích; kiến trúc image có khớp shape không.
- Boot/block volume có những ràng buộc vị trí và phương án sao lưu/khôi phục nào cần xử lý.
- Endpoint, wallet/chứng thư, secret và chính sách kết nối đến dịch vụ cơ sở dữ liệu Oracle.
- RTO, RPO, độ trễ và kế hoạch chuyển traffic có còn đáp ứng yêu cầu không.

Đây là bảng rà soát thiết kế. Các dịch vụ Database, Exadata, Autonomous Database hoặc dịch vụ quản lý khác có quy trình placement và recovery riêng; không áp dụng trực tiếp thao tác đổi shape/AD của một VM lên mọi loại cơ sở dữ liệu.

### 8.4. Capacity reservation để chuẩn bị trước

Capacity reservation dành trước phần tài nguyên để dùng về sau và gắn với AD/cấu hình thích hợp. Khi tạo, có thể chỉ được cấp một phần, thậm chí 0 instance nếu không có capacity; phải đọc lượng đã được cấp thực tế. Phần capacity chưa dùng vẫn có chi phí. Service limits và quota tiếp tục áp dụng. Xem [Capacity Reservations](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/reserve-capacity.htm).

Với kế hoạch DR hoặc một đợt mở rộng quan trọng, quy trình vận hành nên gồm:

1. Chốt cấu hình ứng dụng cần và scope dự phòng.
2. Kiểm tra allowance, ngân sách và quyền dùng reservation.
3. Tạo trước, xác nhận lượng cấp thực tế và khả năng launch theo cấu hình dự kiến.
4. Diễn tập quy trình sử dụng reservation cùng mạng, dữ liệu và chuyển traffic.
5. Theo dõi phần đã dùng/chưa dùng, rồi điều chỉnh khi nhu cầu thay đổi.

Reservation phải được chuẩn bị và kiểm chứng trước thời điểm cần sử dụng. Đừng coi yêu cầu tạo reservation giữa lúc thiếu capacity là cách chắc chắn khắc phục ngay sự cố.

## 9. Tình huống xuyên suốt: một rollout gặp ba trở ngại

Một ứng dụng Java xử lý đơn hàng chạy trong compartment **AppProd**. Nhóm muốn thêm 6 worker trước giờ cao điểm. Mỗi worker dự kiến dùng 4 OCPU, 32 GiB memory, kết nối đến cơ sở dữ liệu Oracle qua private endpoint. Các con số sau là tình huống giả định.

### Giai đoạn 1: pipeline nhận 429

Nhiều pipeline cùng polling trạng thái và gọi API launch. Nhóm tạm giảm số job đồng thời, đưa các yêu cầu mở rộng vào một hàng đợi, tăng khoảng polling và bật retry có deadline tại một tầng đã xác định.

Dấu hiệu tiến triển là tỷ lệ throttling giảm và các yêu cầu được xử lý ổn định hơn. Chưa kết luận đủ capacity chỉ từ việc hết 429.

### Giai đoạn 2: sau khi giảm nhịp xuất hiện LimitExceeded

Nhu cầu bổ sung là **6 × 4 = 24 OCPU**, trong khi allowance còn lại của limit đang xét chỉ có 16 OCPU. Nhóm xác nhận tên limit, scope và usage, rồi kiểm tra thêm memory, volume và quota.

Nếu các ràng buộc còn lại cho phép, có thể chọn batch đầu tối đa 4 worker về mặt OCPU, đồng thời yêu cầu tăng limit cho phần nhu cầu còn lại và dư địa rollout. Quyết định batch nhỏ phải dựa vào throughput tối thiểu của ứng dụng; không mặc định 4 worker đáp ứng được giờ cao điểm.

### Giai đoạn 3: allowance đủ nhưng launch báo thiếu host

Với cấu hình ban đầu ghim một FD, launch tiếp theo trả thông điệp thiếu host capacity. Nhóm lấy capacity report cho cấu hình cần dùng và đối chiếu các lựa chọn đã được chuẩn bị.

Nếu thiết kế phân tán lỗi cho phép, nhóm bỏ ghim FD cho batch mới hoặc chọn phương án shape tương thích đã benchmark. Trước khi thử, đối soát những request trước để tránh sinh trùng. Nếu chọn AD khác, kiểm tra lại volume, subnet và kết nối cơ sở dữ liệu.

### Xác nhận phục hồi

Không dùng tiêu chí duy nhất là có 6 instance ở trạng thái **RUNNING**. Cần kiểm tra worker đã đăng ký vào hệ thống, health check đạt, kết nối dữ liệu hoạt động, hàng đợi giảm, tỷ lệ lỗi và độ trễ đáp ứng mục tiêu. Đồng thời kiểm kê số tài nguyên thực tế và chi phí tăng thêm sau các lần thử.

Tình huống cho thấy một biện pháp có thể gỡ được trở ngại đầu tiên rồi làm lộ trở ngại tiếp theo. Mỗi phản hồi mới cần được phân loại lại.

## 10. Giám sát để phát hiện trước khi sự cố xảy ra

### 10.1. Tín hiệu ở lớp client và hạ tầng

| Nhóm tín hiệu | Dữ liệu nên thu thập | Quyết định hỗ trợ |
|---|---|---|
| Nhịp API | Request rate, số đang xử lý, thời gian chờ permit | Điều chỉnh concurrency/rate limiter |
| Lỗi API | HTTP status, error code, operation, region | Chọn đúng nhánh xử lý |
| Retry | Số lần gọi thực, backoff, deadline exhausted | Phát hiện retry storm hoặc ngân sách quá dài |
| Hạn mức | Usage, allowance, headroom tại scope tương ứng | Lập kế hoạch tăng limit/quota |
| Triển khai | Desired count, actual count, thời gian tài nguyên sẵn sàng | Phát hiện mở rộng không đạt mục tiêu |
| Capacity | Kết quả báo cáo và launch theo cấu hình/vị trí | Đánh giá phương án shape/placement |
| Ứng dụng | Queue age, throughput, lỗi, độ trễ, kết nối DB | Xác nhận ảnh hưởng và khôi phục thực tế |

Không giả định có một metric chuẩn duy nhất chứa mọi lỗi API của mọi dịch vụ. Ứng dụng/pipeline cần có telemetry của chính client; có thể gửi custom metrics vào OCI Monitoring và log vào OCI Logging theo chuẩn của nhóm. Audit hỗ trợ đối chiếu thao tác và actor nhưng không thay thế bộ đếm request, retry và thời gian chờ của client.

Đặt OCID/request ID đầy đủ trong log phục vụ điều tra, tránh dùng chúng làm nhãn metric có số lượng giá trị quá lớn. Metric nên nhóm theo các chiều hữu ích như operation, service, error code và region.

### 10.2. Cảnh báo gắn với nhu cầu mở rộng

Ví dụ ngưỡng vận hành để nhóm tự hiệu chỉnh:

- Cảnh báo khi tỷ lệ throttling vượt ngưỡng đã chọn liên tục trong một cửa sổ thời gian.
- Cảnh báo khi headroom không đủ cho batch rollout tiếp theo hoặc cho kịch bản mất một nhóm worker.
- Cảnh báo khi desired count lớn hơn actual count quá thời gian mở rộng dự kiến.
- Cảnh báo khi số yêu cầu thất bại do hết retry budget tăng cùng queue age của ứng dụng.

Với limit hữu hạn và usage cùng scope:

~~~text
headroom = effectiveAllowance - usage

plannedPeak = steadyState
            + expectedGrowth
            + rolloutOverlap
            + recoveryBuffer
~~~

Công thức plannedPeak là mô hình lập kế hoạch. Chỉ cộng các thành phần có thể cùng tồn tại trong kịch bản đang tính; tính riêng OCPU, memory, instance, volume và các tài nguyên phụ thuộc. Nếu limit có giá trị đặc biệt hoặc dữ liệu chưa được hỗ trợ, không tự tính phần trăm sử dụng như một số hữu hạn thông thường.

## 11. Tự động hóa, chi phí và điểm dừng

Một bộ điều phối tốt có trạng thái rõ ràng:

~~~text
PENDING -> CALLING -> SUCCEEDED
                  -> RETRY_WAIT       khi gặp lỗi tạm thời phù hợp
                  -> NEEDS_LIMIT      khi thiếu service allowance
                  -> NEEDS_QUOTA      khi thiếu phân bổ nội bộ
                  -> NEEDS_CAPACITY   khi không bố trí được host
                  -> FAILED           khi cần can thiệp khác
~~~

Trạng thái nghiệp vụ này giúp hệ thống ngừng retry sai loại lỗi. Với NEEDS_LIMIT hoặc NEEDS_QUOTA, giữ một hồ sơ công việc có thể tiếp tục sau thay đổi đã xác nhận; không cho hàng trăm worker liên tục thử cùng yêu cầu đang bị chặn.

Danh sách phương án dự phòng nên cấu hình trước theo workload, chẳng hạn shape chính, shape thay thế đã benchmark và các placement hợp lệ. Mỗi phương án phải có trần số instance, giới hạn thời gian và điều kiện dừng. Nếu hết deadline, trả lỗi có bằng chứng cho nhóm vận hành; không tiếp tục mở rộng âm thầm.

Về chi phí, theo dõi cả instance mới, boot/block volume giữ lại, snapshot/backup, IP và dữ liệu sao chép. Lỗi launch không đủ để kết luận không có tài nguyên hay chi phí phát sinh; hãy kiểm kê theo operation ID, tag và OCID. Thu hồi tài nguyên dư theo đúng vòng đời và quyền quản lý của nhóm.

OCI Budgets dùng để đặt ngưỡng chi tiêu mềm và cảnh báo; bản thân budget không tự chặn mọi thao tác tạo tài nguyên. Cần kết hợp ngân sách với quota và giới hạn trong bộ điều phối. Xem [Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm).

## 12. Thực hành chẩn đoán và ghi nhận kết quả

Bài thực hành ưu tiên các lệnh quan sát ở phần 5 và báo cáo ở phần 8. Không cố tạo một lượng request lớn để ép tenancy trả 429, không tạo hàng loạt VM để làm đầy limit. Dùng phản hồi lỗi giả lập để luyện phân loại và logic retry; chỉ launch tài nguyên khi môi trường lab có kế hoạch chi phí và thu hồi rõ ràng.

### Bước 1: lập bản đồ allowance

Chọn một workload và một cấu hình dự kiến. Ghi lại service name, limit name, đơn vị, scope, giá trị limit, quota áp dụng và usage mà bạn có quyền quan sát. Đánh dấu dữ liệu không được API hỗ trợ, thay vì điền 0.

Kết quả cần có là bảng đủ thông tin để người khác tái hiện phép tính headroom trong cùng ngữ cảnh.

### Bước 2: phân loại ba phản hồi giả lập

~~~text
A. HTTP 429, code TooManyRequests
B. HTTP 400, code QuotaExceeded
C. code InternalError, message Out of host capacity
~~~

Với từng phản hồi, ghi bằng chứng còn thiếu, người chịu trách nhiệm xử lý và hành động tiếp theo. Kết quả mong đợi: A dẫn đến kiểm soát nhịp; B dẫn đến kiểm tra phân bổ compartment; C dẫn đến kiểm tra capacity/placement. Không dùng cùng một vòng retry vô hạn cho cả ba.

### Bước 3: tính nhu cầu đỉnh

Tự đặt số worker ổn định, số worker thêm khi rollout và phần phục hồi cần chuẩn bị. Tính OCPU/memory ở đỉnh rồi so với allowance hiện có. Chỉ ra scope nào được dùng cho từng phép so sánh và phụ thuộc nào chưa được kiểm tra.

### Bước 4: kiểm tra một phương án capacity

Nếu có quyền, tạo một báo cáo cho cấu hình phù hợp tại AD đích. Ghi thời gian, shape, OCPU, memory, các trạng thái trả về và giới hạn diễn giải của báo cáo. Nếu không có quyền, ghi chính xác lỗi và yêu cầu quyền quan sát phù hợp; không thay profile sang quyền quản trị ngoài phạm vi lab.

### Bước 5: soạn biên bản sự cố mẫu

~~~text
Thời gian UTC và mức ảnh hưởng:
Operation và công cụ/SDK:
Region / AD / FD:
Compartment và principal:
HTTP status / error code / message:
opc-request-id / resource OCID / work request nếu có:
Shape / OCPU / memory / số lượng cần:
Limit name / scope / usage / allowance:
Quota và capacity đã kiểm tra:
Các phương án đã thử, thời điểm và kết quả:
Tình trạng yêu cầu cũ đã rõ hay còn chưa xác định:
Hành động đề nghị và tiêu chí xác nhận phục hồi:
~~~

Biên bản đạt yêu cầu khi một người tiếp nhận có thể chọn đúng nhánh điều tra mà không phải đoán từ câu “OCI không tạo được máy”. Khi cần Oracle Support, gửi tập bằng chứng liên quan và nêu rõ tác động, tránh tiếp tục thử lại không giới hạn trong thời gian chờ.

## 13. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách kiểm tra đúng |
|---|---|
| “Console còn available nên chắc chắn launch được” | Xác định đó là allowance của Limits API hay thông tin host capacity |
| “Tăng limit sẽ hết 429” | Điều tra nhịp gọi và giới hạn của operation đang bị throttling |
| “Tenancy còn OCPU nên compartment nào cũng tạo được” | Kiểm tra quota có hiệu lực tại compartment đích |
| “Cứ đổi AD là xong” | Kiểm tra lựa chọn AD, scope limit, mạng và dữ liệu |
| “Hết timeout thì tạo lại bằng request mới” | Đối soát kết quả yêu cầu trước và cơ chế idempotency |
| “SDK đã retry nên wrapper càng retry càng tốt” | Tính tổng số lần gọi và chọn tầng chịu trách nhiệm |
| “Capacity report đã tạo nghĩa là đã giữ chỗ” | Phân biệt báo cáo thời điểm với reservation đã được cấp thực tế |
| “Có đủ instance RUNNING nghĩa là phục hồi” | Xác nhận khả năng phục vụ của ứng dụng và phụ thuộc dữ liệu |

Khi đưa runbook vào vận hành, lưu cùng cấu hình workload các lựa chọn shape/placement hợp lệ, allowance cần cho mức tải đỉnh, ngân sách retry và tiêu chí khôi phục. Cập nhật các giá trị đó khi kiến trúc, nhu cầu hoặc chính sách phân bổ thay đổi.

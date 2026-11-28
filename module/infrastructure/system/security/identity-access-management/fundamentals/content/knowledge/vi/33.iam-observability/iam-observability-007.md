# Token issuance latency

## 1. Độ trễ cấp token phản ánh điều gì?

**Token issuance latency** là thời gian cần để xử lý một yêu cầu cấp token trong một ranh giới đo đã xác định. Chỉ số này cho biết người dùng hoặc workload phải chờ bao lâu để nhận credential phục vụ bước tiếp theo, đồng thời giúp phát hiện điểm nghẽn trong dịch vụ danh tính và các thành phần phụ thuộc.

Trong một hệ thống IAM, cấp token có thể xuất hiện khi ứng dụng đổi authorization code, dùng refresh token hoặc khi workload dùng một grant được hỗ trợ để lấy access token. Một lần xử lý có thể tạo access token và, tùy giao thức, grant, chính sách, cả những loại token khác. Không mặc định mọi yêu cầu đều tạo đủ access token, ID token và refresh token.

Một con số như “cấp token mất 120 ms” chỉ có ý nghĩa khi trả lời được các câu hỏi:

- Đo từ phía client hay bên trong authorization server?
- Bắt đầu trước hay sau khi request chờ trong hàng đợi?
- Kết thúc lúc tạo xong token, lúc ghi xong phản hồi hay lúc client nhận đủ phản hồi?
- Đo grant nào, nhóm client nào và kết quả thành công hay cả lỗi?
- Các request timeout hoặc chưa hoàn tất được quan sát ra sao?

Độ trễ thấp hỗ trợ trải nghiệm sử dụng và khả năng vận hành, nhưng không chứng minh token được cấp đúng quyền. Chỉ số này phải đi cùng tỷ lệ thành công, lỗi, kiểm soát quyền và sức khỏe telemetry.

## 2. Phân biệt cấp token với những hoạt động liên quan

Không gom tất cả hoạt động liên quan đến danh tính thành một chỉ số độ trễ.

| Hoạt động | Phạm vi điển hình | Vì sao cần tách |
|---|---|---|
| Đăng nhập tương tác | Chuyển hướng, nhập thông tin, MFA, liên kết danh tính và hoàn tất phiên | Có thời gian chờ hành động của con người |
| Xử lý yêu cầu cấp token | Kiểm tra request và grant, áp dụng điều kiện, tạo token, trả kết quả | Là phạm vi chính của bài học |
| Xác minh token tại resource server | Kiểm tra token cho một request truy cập tài nguyên | Xảy ra khi sử dụng credential đã được cấp |
| Introspection | Hỏi một dịch vụ về trạng thái và thuộc tính của token | Là một loại lời gọi phụ thuộc riêng |
| Thu hồi token | Xử lý yêu cầu làm mất hiệu lực credential theo cơ chế hỗ trợ | Mục tiêu và đường xử lý khác cấp token |
| Tải khóa xác minh | Lấy thông tin khóa công khai để kiểm tra chữ ký | Không đồng nghĩa một token mới được tạo |

Ví dụ, một người dùng mất 25 giây để nhập mã MFA, sau đó ứng dụng mất 90 ms để đổi authorization code. Độ trễ của bước đổi code có thể là 90 ms; thời gian đăng nhập toàn trình lớn hơn nhiều. Cộng 25 giây vào metric cấp token sẽ làm sai nghĩa của phép đo.

Ngược lại, nếu client mất 2 giây để nhận token nhưng authorization server chỉ ghi nhận 80 ms, cần xem phần mạng, proxy, hàng đợi nằm ngoài điểm đo hoặc các lần thử lại. Không thể kết luận ngay số liệu của một bên bị sai.

## 3. Đặt ranh giới đo rõ ràng

### 3.1. Góc nhìn client và góc nhìn server

Có thể duy trì hai phép đo bổ sung cho nhau:

```text
Client bắt đầu một lần gọi
    -> mạng / proxy / hàng đợi
    -> server tiếp nhận request tại điểm đo
    -> xác minh request, grant và điều kiện cấp
    -> dựng nội dung token, ký hoặc lưu trạng thái cần thiết
    -> tạo phản hồi
    -> mạng / proxy
Client nhận đủ phản hồi hoặc kết thúc bằng lỗi
```

| Phép đo | Điểm bắt đầu minh họa | Điểm kết thúc minh họa |
|---|---|---|
| Client attempt duration | Trước một lần gửi request | Nhận đủ phản hồi hoặc lần gọi kết thúc bằng lỗi |
| Server request duration | Middleware nhận request | Framework xác nhận xử lý phản hồi hoàn tất tại điểm đo |
| Issuance processing duration | Bắt đầu phần xử lý nghiệp vụ cấp token | Hoàn tất xử lý và tạo kết quả nghiệp vụ |
| Signing duration | Trước thao tác ký | Thao tác ký kết thúc hoặc báo lỗi |

Các tên trên là ví dụ thiết kế, không phải bộ tên bắt buộc của một sản phẩm.

Một middleware ứng dụng thường không nhìn thấy thời gian request chờ ở load balancer trước khi vào ứng dụng. Tương tự, “handler trả về” có thể xảy ra trước khi phản hồi được truyền xong. Dashboard cần ghi đúng giới hạn thực tế, tránh gắn nhãn “end-to-end” cho một đoạn xử lý nội bộ.

### 3.2. Attempt và thao tác có retry

Một thao tác client có thể gồm nhiều lần gọi:

```text
Thao tác lấy token
    lần gọi 1: 700 ms -> timeout
    chờ retry: 200 ms
    lần gọi 2: 100 ms -> thành công

Thời gian thao tác: khoảng 1.000 ms, chưa kể overhead khác
Độ trễ lần gọi thành công: 100 ms
```

Nếu chỉ lưu lần gọi thành công, dashboard sẽ không thể hiện thời gian chờ thực tế của client. Nên tách metric theo từng attempt với metric theo thao tác client nếu cần theo dõi retry.

Ví dụ trên chỉ minh họa cách đo. Việc retry có an toàn hay được phép hay không phụ thuộc loại grant, tính chất sử dụng một lần của credential và hợp đồng của dịch vụ. Không dùng một chính sách retry chung cho mọi yêu cầu cấp token.

### 3.3. Đồng hồ và đơn vị

Đo khoảng thời gian trong cùng một tiến trình bằng nguồn thời gian đơn điệu phù hợp. Nguồn này giúp tránh phép đo bị ảnh hưởng bởi điều chỉnh đồng hồ lịch.

Timestamp theo thời gian lịch vẫn hữu ích để đối chiếu sự kiện giữa các hệ thống, nhưng không nên lấy hai timestamp từ hai máy khác nhau rồi mặc định hiệu của chúng chính là độ trễ chính xác. Sai lệch đồng hồ có thể làm kết quả sai hoặc âm.

Chọn một đơn vị lưu nhất quán, chẳng hạn giây, rồi đổi sang ms trên dashboard. Tên metric, biểu đồ và ngưỡng cảnh báo phải cùng thể hiện đúng đơn vị.

## 4. Theo dõi kết quả cùng với thời gian

Một request kết thúc nhanh vì credential của client không hợp lệ không thể được coi là cấp token nhanh và thành công.

Một taxonomy vận hành minh họa:

| Outcome | Ý nghĩa tại điểm đo |
|---|---|
| `success` | Đã hoàn tất điều kiện cấp token và tạo phản hồi thành công theo hợp đồng |
| `rejected` | Hệ thống từ chối request hoặc grant theo quyết định có chủ đích |
| `error` | Xử lý thất bại do lỗi nội bộ hoặc thành phần phụ thuộc |
| `timeout` | Điểm đo có thể xác định thao tác kết thúc do hết thời gian chờ |
| `cancelled` | Điểm đo nhận biết thao tác bị hủy |

Đây là nhóm kết quả do bài học đặt để giải thích cách quan sát; chúng không phải danh sách mã lỗi của một giao thức. Mỗi triển khai cần ánh xạ từ kết quả thực tế sang nhóm vận hành một cách nhất quán.

Outcome còn phụ thuộc góc nhìn. Client có thể timeout trong khi server tiếp tục xử lý và ghi nhận thành công. Hai phép đo đang mô tả hai sự kiện khác nhau. Cần liên kết trace hoặc log khi điều tra, thay vì ép chúng phải luôn có outcome giống nhau.

Không suy ra thành công chỉ từ mã HTTP nếu hợp đồng còn yêu cầu kiểm tra phản hồi hợp lệ. Ở phía client, lỗi đọc hoặc giải mã phản hồi có thể xảy ra dù server đã phát hành token. Metric server và metric client cần giữ đúng ý nghĩa riêng.

Nên có ít nhất:

- Phân bố thời gian của request thành công.
- Phân bố thời gian của các kết quả không thành công tại điểm đo.
- Số request theo outcome và tốc độ phát sinh.
- Số request đang xử lý hoặc chờ, nếu có thể quan sát.

Nếu tiến trình bị dừng trước khi ghi metric hoàn tất, request đó có thể không nằm trong histogram. Theo dõi restart, request bắt đầu, kết quả hoàn tất và tình trạng thu thập giúp nhận ra khoảng trống này.

## 5. Histogram và các phân vị

### 5.1. Vì sao trung bình chưa đủ?

Giả sử 100 request thành công có phân bố:

```text
95 request: 50 ms mỗi request
 5 request: 2.000 ms mỗi request

Trung bình = (95 × 50 + 5 × 2.000) / 100
           = 147,5 ms
```

Trung bình dưới 150 ms vẫn có thể đi cùng một nhóm request phải chờ 2 giây. Vì vậy cần quan sát phần đuôi của phân bố, thường qua p95 hoặc p99, cùng số lượng mẫu và histogram.

Phân vị p95 mô tả một mốc mà khoảng 95% giá trị quan sát không vượt quá, theo phương pháp ước lượng đang dùng. Phân vị không phải cam kết rằng mỗi nhóm người dùng hoặc mỗi instance đều có đúng tỷ lệ tương tự.

Với ít mẫu, p99 dễ biến động và phụ thuộc cách ước lượng. Đừng so sánh p99 của vài request với p99 của hàng triệu request mà bỏ qua sự khác biệt về lượng dữ liệu.

### 5.2. Chọn bucket theo câu hỏi vận hành

Một bộ ranh giới bucket minh họa, đơn vị giây:

```text
0,010; 0,025; 0,050; 0,100; 0,200;
0,300; 0,500; 1,000; 2,000; 5,000; +Inf
```

Các giá trị này không phải ngưỡng chuẩn cho IAM. Cần chọn theo độ trễ dự kiến, mục tiêu dịch vụ và những đoạn phân bố cần phân biệt.

Nếu mục tiêu minh họa là “hoàn tất trong 300 ms”, bucket tại 0,300 giây giúp đếm trực tiếp số quan sát không vượt mốc đó đối với histogram có bucket tương ứng. Nếu dùng một cơ chế histogram khác, cần hiểu chính xác cách nó biểu diễn và ước lượng ngưỡng.

Bucket quá thưa làm phần đuôi khó phân tích. Quá nhiều bucket trên nhiều tổ hợp label lại tăng chi phí lưu trữ và thu thập.

### 5.3. Tổng hợp đúng giữa các instance

Không lấy trung bình p95 hoặc p99 của từng instance rồi gọi kết quả là phân vị toàn hệ thống. Các phân vị không cộng hoặc lấy trung bình theo cách đó.

Để tìm phân vị toàn hệ thống, cần tổng hợp dữ liệu phân bố tương thích trong cùng cửa sổ và cùng phạm vi, rồi tính phân vị từ phân bố đã tổng hợp. Với histogram bucket, ranh giới bucket và ý nghĩa metric phải tương thích.

Tương tự, thời gian trung bình toàn hệ thống cần tính từ tổng thời gian chia tổng số quan sát, không lấy trung bình không trọng số của các giá trị trung bình ở những instance có lưu lượng khác nhau.

Giữ khả năng xem từng vùng hoặc từng nhóm instance. Một phân vị toàn cục có thể che sự cố chỉ ảnh hưởng đến một phần lưu lượng nhỏ.

## 6. Thiết kế metric và label

Một histogram tùy biến có thể mang tên:

```text
iam_token_request_duration_seconds{
    environment="production",
    grant_class="client_credentials",
    issuer_group="workforce",
    region="region_a",
    outcome="success"
}
```

Đây là ví dụ tự đặt. `grant_class` nên được ánh xạ từ loại grant đã nhận diện và một tập giá trị có giới hạn; request chứa giá trị tùy ý hoặc không hỗ trợ không được tự tạo vô hạn label mới.

Những chiều thường hữu ích là loại grant, khu vực, nhóm issuer, nhóm client và outcome. Chỉ thêm chiều khi có câu hỏi vận hành cụ thể cần trả lời, nguồn dữ liệu đáng tin cậy và giới hạn số giá trị rõ ràng.

Không đưa các dữ liệu sau vào label của từng request:

- Access token, refresh token, authorization code hoặc client secret.
- Subject ID, email, username hay session ID.
- Trace ID hoặc request ID.
- URL đầy đủ, exception message hoặc nội dung phản hồi tùy ý.
- Từng tenant hoặc client riêng lẻ nếu tập giá trị quá lớn và biến động mạnh.

Client ID có thể không phải bí mật, nhưng vẫn làm tăng cardinality và có thể tiết lộ thông tin cấu trúc hệ thống. Nên dùng nhóm client đã kiểm soát hoặc phương pháp điều tra chi tiết được phân quyền khi phù hợp. Băm một ID không làm giảm số giá trị khác nhau.

Trace ID có thể được dùng để liên kết một quan sát với trace bằng cơ chế hỗ trợ thích hợp, nhưng không biến thành một chiều label cho mọi chuỗi thời gian. Các phương án liên kết vẫn phải tuân thủ quyền truy cập telemetry.

## 7. Phân rã đường xử lý cấp token

Một request cấp token có thể đi qua các công việc sau, tùy triển khai:

```text
Tiếp nhận / hàng đợi
    -> kiểm tra cú pháp và cấu hình client
    -> xác thực client nếu flow yêu cầu
    -> kiểm tra grant và trạng thái liên quan
    -> áp dụng scope, audience và điều kiện cấp
    -> lấy thuộc tính cần cho claims
    -> tạo / ký token hoặc lưu trạng thái token
    -> ghi trạng thái và audit theo thiết kế
    -> trả phản hồi
```

Không phải hệ thống nào cũng làm từng bước theo đúng thứ tự tuyến tính này. Một số bước có thể song song, được cache hoặc nằm ở dịch vụ khác.

| Đoạn cần quan sát | Hiện tượng có thể thấy | Hướng kiểm tra |
|---|---|---|
| Hàng đợi hoặc thread pool | Thời gian chờ tăng khi tải tăng | Request đang chờ, giới hạn đồng thời, CPU |
| Kho client, grant hoặc phiên | Truy vấn chậm hoặc chờ kết nối | Độ trễ truy vấn, connection pool, khóa dữ liệu |
| Nguồn thuộc tính danh tính | Chỉ vài nhóm request chậm | Nguồn thuộc tính, cache, số lần gọi trên mỗi request |
| Ký token | Span ký chậm, hàng chờ dịch vụ khóa tăng | Dịch vụ khóa, kết nối, năng lực xử lý, thời điểm xoay khóa |
| Lưu trạng thái refresh token | Flow refresh chậm hoặc tranh chấp | Tính nguyên tử, transaction, chỉ mục, contention |
| Audit hoặc telemetry | Request chậm khi pipeline ghi bị nghẽn | Backpressure và hợp đồng ghi bắt buộc |
| Trả phản hồi | Server xử lý xong nhưng client vẫn chờ | Proxy, kết nối, kích thước phản hồi và timeout |

Thời gian các span không nhất thiết cộng đúng bằng tổng request. Span lồng nhau sẽ bị đếm trùng nếu cộng máy móc; span chạy song song có thời gian chồng lấp. Cần xem đường thực thi và phần chờ thực sự quyết định thời điểm hoàn tất.

Trace lấy mẫu giúp giải thích một số request chậm. Nó không tự bảo đảm đại diện cho toàn bộ phân bố. Metric đếm đầy đủ hoặc một phương pháp đo có đặc tính sampling rõ ràng mới là cơ sở thích hợp để đánh giá tỷ lệ toàn lưu lượng.

## 8. Tách lưu lượng để tránh diễn giải sai

### 8.1. Loại grant và đặc điểm đường xử lý

Authorization code, refresh token và client credentials có thể có chi phí xử lý khác nhau. So sánh chúng chỉ qua một biểu đồ tổng dễ gây nhầm lẫn.

Ví dụ, độ trễ của từng loại grant không đổi nhưng tỷ trọng flow chậm tăng. Trung bình toàn hệ thống vẫn tăng dù không có thành phần nào vừa suy giảm hiệu năng.

Theo dõi cả phân bố tổng và các lát cắt grant giúp phân biệt thay đổi cơ cấu lưu lượng với một regression trong cùng đường xử lý.

### 8.2. Warm-up, cache và xoay khóa

Sau restart, cache lạnh hoặc lần đầu kết nối tới dịch vụ ký có thể làm một số request chậm hơn. Xoay khóa, thay đổi cấu hình client hoặc cập nhật mapping claims cũng có thể ảnh hưởng đường xử lý.

Đánh dấu các mốc triển khai và thay đổi cấu hình trên dashboard để hỗ trợ đối chiếu. Việc hai sự kiện xảy ra cùng thời điểm chỉ tạo giả thuyết; cần kiểm tra trace, metric phụ thuộc và phạm vi ảnh hưởng trước khi kết luận.

Không loại bỏ toàn bộ mẫu chậm trong giai đoạn khởi động khỏi dashboard chỉ để biểu đồ tốt hơn. Nếu có metric riêng cho warm-up, vẫn cần hiểu tác động của nó lên các request thực tế.

### 8.3. Nhu cầu cấp token và hành vi client

Một workload xin token mới cho mọi request nghiệp vụ có thể tạo tải cấp phát lớn. Nhiều instance cùng khởi động hoặc cùng refresh tại một thời điểm cũng có thể tạo đợt tăng lưu lượng.

Quan sát request rate, số client hoạt động theo nhóm và tỷ lệ retry giúp nhận ra các trường hợp này. Nếu điều chỉnh cách client tái sử dụng token hoặc lên lịch refresh, phải tuân thủ thời hạn hiệu lực, ngữ cảnh sử dụng và chính sách bảo vệ credential.

Không kéo dài token vô hạn, chia sẻ token ngoài ranh giới cho phép hoặc bỏ kiểm tra quyền để làm giảm tải cấp phát.

## 9. Dashboard và mục tiêu độ trễ

Một dashboard hữu ích nên đặt các tín hiệu gần nhau:

| Nhóm tín hiệu | Câu hỏi cần trả lời |
|---|---|
| Request rate theo grant | Lưu lượng có thay đổi hoặc dồn vào một flow không? |
| Outcome và tỷ lệ thành công | Client có thực sự nhận được kết quả cần thiết không? |
| p50, p95, p99 và histogram | Phần lớn request và phần đuôi đang chờ bao lâu? |
| Timeout, cancellation và retry | Những lần chờ thất bại có đang bị che khuất không? |
| Request đang xử lý và hàng đợi | Hệ thống có tích tụ công việc chưa hoàn tất không? |
| Độ trễ phụ thuộc và tài nguyên | Đoạn nào có thể đang giới hạn xử lý? |
| Chất lượng thu thập telemetry | Dữ liệu có bị thiếu, trễ hoặc mất nguồn không? |

### 9.1. Ví dụ một SLI về thời gian hoàn tất thành công

Giả sử một nhóm dịch vụ đặt mục tiêu minh họa: request hợp lệ trong phạm vi đã chọn phải cấp token thành công và hoàn tất trong 300 ms tại điểm đo server đã công bố.

```text
good = số request đủ điều kiện,
       cấp token thành công và duration <= 300 ms

eligible = tổng số request đủ điều kiện đã được phân loại

SLI = good / eligible
```

Điều kiện “đủ điều kiện” phải xác định trước: môi trường nào, loại flow nào, cách xử lý từ chối hợp lệ, lỗi kỹ thuật và timeout. Không loại lỗi nội bộ khỏi mẫu số chỉ vì hệ thống không hoàn tất được request.

Trong một cửa sổ minh họa có 10.000 request đủ điều kiện:

```text
9.700 thành công trong 300 ms
  200 thành công nhưng chậm hơn 300 ms
  100 kết thúc bằng lỗi hoặc timeout được quan sát

SLI = 9.700 / 10.000 = 97%
```

Nếu chỉ xét các request thành công, phép tính sẽ là 9.700 / 9.900, khoảng 97,98%. Con số đó trả lời một câu hỏi khác và không thể hiện đầy đủ các request thất bại.

Ngưỡng 300 ms và tỷ lệ trong ví dụ chỉ dùng để minh họa cách định nghĩa; không phải yêu cầu chung cho mọi hệ thống IAM.

### 9.2. Request đang treo và không có dữ liệu

Histogram hoàn tất thường chưa chứa request đang xử lý. Nếu nhiều request bị treo lâu, phân vị từ các request đã xong thậm chí có thể trông tốt hơn thực tế.

Cần quan sát đồng thời request đang xử lý, thời gian sống của request nếu có, timeout và metric client. Request không bao giờ được điểm đo ghi nhận kết thúc là khoảng mù phải được giải quyết trong thiết kế phép đo.

Nếu không có quan sát trong cửa sổ, biểu diễn “không có dữ liệu” hoặc “không có request”, tùy bằng chứng đi kèm. Không hiển thị độ trễ 0 ms và diễn giải là dịch vụ đang đáp ứng tức thời.

### 9.3. Cảnh báo theo tác động

Một cảnh báo có thể xét tỷ lệ request chậm, số lượng mẫu, mức kéo dài và ảnh hưởng của flow. Theo dõi cả cửa sổ ngắn và dài có thể giúp phân biệt một đợt tăng ngắn với suy giảm kéo dài.

Không dùng p99 tăng đơn lẻ ở mẫu rất nhỏ làm bằng chứng duy nhất. Đồng thời, không bỏ qua flow quản trị hoặc workload thiết yếu chỉ vì lưu lượng thấp; nhóm này có thể cần kiểm tra tổng hợp hoặc cảnh báo theo sự kiện riêng.

Metric success-only vẫn hữu ích để điều tra hiệu năng, nhưng cần đặt bên cạnh lỗi và timeout để tránh cảnh báo “hết chậm” chỉ vì các request chậm đã chuyển sang thất bại.

## 10. Quy trình điều tra một đợt tăng latency

1. **Xác nhận phép đo.** Kiểm tra đơn vị, cửa sổ, bucket, điểm bắt đầu/kết thúc, label và thay đổi instrumentation.
2. **Xác định tác động.** Đối chiếu latency client với server, success với error, timeout và số request đang xử lý.
3. **Khoanh vùng.** Tách grant, vùng triển khai, nhóm client, issuer và phiên bản dịch vụ theo các chiều đã kiểm soát.
4. **Kiểm tra lưu lượng.** Xem tải tăng, retry, client khởi động đồng loạt hoặc thay đổi tỷ trọng flow.
5. **Phân tích đường xử lý.** Dùng trace và metric phụ thuộc để tìm phần chờ chiếm ưu thế, tránh cộng trùng span.
6. **Đối chiếu thay đổi.** Kiểm tra triển khai, xoay khóa, cấu hình claims, kho dữ liệu và các dịch vụ liên quan.
7. **Xử lý và đo lại.** Kiểm tra cả latency, tỷ lệ thành công, timeout và các điều kiện bảo mật sau thay đổi.

Ví dụ, p95 server tăng từ 80 ms lên 500 ms sau một đợt triển khai. Request rate không đổi, nhưng trace cho thấy mỗi request gọi nguồn thuộc tính ba lần thay vì một lần. Các span ký token vẫn ổn định.

Giả thuyết phù hợp là đường lấy thuộc tính vừa thay đổi hoặc lặp không cần thiết. Cần kiểm tra thay đổi triển khai và kết quả trả về của nguồn thuộc tính, thay vì lập tức tăng tài nguyên dịch vụ ký. Nếu giảm số lần gọi, vẫn phải giữ đúng tập claims và điều kiện cấp quyền.

Một tình huống khác: p95 server vẫn khoảng 80 ms nhưng p95 client lên 2 giây và số retry tăng. Hướng điều tra chuyển sang mạng, proxy, timeout, hàng đợi nằm ngoài điểm đo server hoặc sự khác biệt giữa các tập request được quan sát.

## 11. Nguyên tắc cải thiện hiệu năng trong ranh giới IAM

Khi có bằng chứng về điểm nghẽn, các biện pháp có thể gồm giảm công việc lặp, tối ưu truy vấn, điều chỉnh pool, phân phối tải hoặc kiểm soát retry. Mỗi thay đổi cần bảo toàn hợp đồng xác thực và cấp quyền.

- Cache cấu hình hoặc thuộc tính phải có phạm vi, thời hạn và cơ chế làm mới phù hợp; dữ liệu quyền cũ có thể tạo quyết định sai.
- Tăng khả năng ký phải giữ đúng quản lý khóa; không xuất private key hoặc thay cơ chế ký chỉ để lấy một con số tốt hơn.
- Điều chỉnh đồng thời cần xem khả năng của kho dữ liệu và dịch vụ khóa; đẩy thêm request vào một phụ thuộc đã bão hòa có thể tăng latency.
- Thay đổi ghi audit phải theo yêu cầu của hệ thống; không âm thầm bỏ bản ghi bắt buộc khi pipeline chậm.
- Thay đổi token lifetime, scope hoặc kiểm tra grant là thay đổi bảo mật và chức năng, không phải thao tác tối ưu latency thuần túy.

Việc cấp token nhanh hơn chỉ có giá trị nếu token vẫn thuộc đúng chủ thể, đúng client, đúng đích sử dụng và đúng phạm vi được cho phép.

## 12. Bảo vệ dữ liệu và kiểm chứng instrumentation

Telemetry có thể tiết lộ thông tin về ứng dụng, nguồn danh tính và các phụ thuộc quan trọng. Dashboard, log và trace cần được phân quyền theo nhu cầu, với thời gian lưu và khả năng xuất dữ liệu được kiểm soát.

Không thu request body hoặc response body chứa token theo mặc định. Redaction phải được thực hiện trước khi dữ liệu nhạy cảm đi vào nơi lưu trữ telemetry, không chỉ che trên giao diện hiển thị. Tránh ghi header xác thực, secret, authorization code, cookie và các credential khác.

Các tình huống sau giúp kiểm chứng ý nghĩa của phép đo:

| Tình huống | Kết quả quan sát mong đợi |
|---|---|
| Cấp token thành công | Ghi đúng một lần hoàn tất tại mỗi điểm đo đã định nghĩa |
| Credential client hoặc grant bị từ chối | Outcome từ chối được tách khỏi thành công |
| Dịch vụ ký chậm | Request latency và span tương ứng thể hiện thời gian chờ |
| Kho trạng thái lỗi | Có outcome lỗi, không chỉ thiếu một mẫu success |
| Client timeout nhưng server tiếp tục | Giữ hai góc nhìn và có khả năng liên kết khi điều tra |
| Một thao tác gồm nhiều retry | Attempt metric và operation metric không bị trộn |
| Request còn đang treo | Có tín hiệu đang xử lý; histogram hoàn tất không bị coi là toàn bộ thực tế |
| Tiến trình restart giữa request | Khoảng trống hoàn tất có thể được nhận ra qua tín hiệu liên quan |
| Không có request trong cửa sổ | Không diễn giải thành độ trễ 0 ms |
| Một instance chậm nhưng lưu lượng nhỏ | Lát cắt phù hợp vẫn phát hiện được |
| Thay đổi label hoặc bucket | Không tổng hợp các phân bố không tương thích như cùng một phép đo |
| Bật log và trace phục vụ điều tra | Credential không xuất hiện trong dữ liệu được thu thập |

Token issuance latency cần được hiểu cùng ranh giới đo, outcome, lượng request và phần công việc chưa hoàn tất. Kết hợp các góc nhìn client, server và thành phần phụ thuộc giúp tìm đúng nguyên nhân chậm trong khi duy trì các điều kiện xác thực, cấp quyền và bảo vệ credential của hệ thống IAM.

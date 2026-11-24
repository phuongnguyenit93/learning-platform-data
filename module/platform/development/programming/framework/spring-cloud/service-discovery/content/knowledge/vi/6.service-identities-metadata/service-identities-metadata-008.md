# Giới hạn kích thước metadata và những dữ liệu không nên công bố

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích metadata của instance được dùng vào mục đích gì trong service discovery.
- Nhận biết vì sao metadata cần nhỏ, ổn định, có cấu trúc và giới hạn cardinality.
- Xác định dữ liệu nhạy cảm hoặc dữ liệu không phù hợp để công bố trong registry.
- Đặt quy ước key/value, ngân sách kích thước và kiểm tra metadata trước khi đăng ký.
- Chọn nơi lưu trữ phù hợp cho secret, cấu hình nghiệp vụ và dữ liệu lớn.

## 1. Metadata trong service discovery là gì?

Một service registry lưu thông tin về dịch vụ và các instance đang cung cấp dịch vụ. Ngoài service ID, instance ID, hostname, port và trạng thái, một số registry cho phép đính kèm metadata để consumer hiểu thêm đặc điểm của instance.

Trong Spring Cloud, `ServiceInstance` cung cấp `getMetadata()` dưới dạng map key/value kiểu chuỗi. Với Eureka, metadata thường được cấu hình qua `eureka.instance.metadata-map`. Các implementation khác có thể có quy ước, giới hạn và cách đồng bộ khác nhau.

Metadata hữu ích khi consumer hoặc hạ tầng cần đưa ra quyết định dựa trên những thuộc tính ổn định, ví dụ:

- Khu vực hoặc zone triển khai: `region=ap-southeast-1`, `zone=hcm-a`.
- Phiên bản API mà instance hỗ trợ: `api-version=v2`.
- Giao thức hoặc định dạng kết nối: `protocol=https`.
- Nhóm năng lực có kiểm soát: `capability=inventory-read`.
- Nhãn rollout: `release-track=canary`.

Metadata không thay thế địa chỉ kết nối, health check, service ID hoặc cơ chế phân quyền. Nó là thông tin bổ sung để discovery consumer hiểu instance và áp dụng chính sách phù hợp.

Ví dụ cấu hình Eureka:

~~~~yaml
eureka:
  instance:
    metadata-map:
      region: ap-southeast-1
      zone: hcm-a
      api-version: v2
      protocol: https
      release-track: stable
~~~~

Chỉ công bố những key mà consumer thực sự sử dụng. Nếu không có consumer hoặc quy trình vận hành nào cần một thuộc tính, hãy cân nhắc bỏ nó.

## 2. Vì sao metadata cần nhỏ và có giới hạn?

Metadata thường được truyền cùng thông tin đăng ký hoặc được trả về trong dữ liệu discovery. Registry có thể lưu trữ, sao chép, cache, serialize và phân phối thông tin đó đến nhiều client. Vì vậy, metadata càng lớn và càng thay đổi thường xuyên thì chi phí truyền tải, bộ nhớ, xử lý và đồng bộ càng tăng.

Các vấn đề thường gặp:

- **Payload lớn:** chuỗi JSON dài, mô tả nhiều đoạn hoặc dữ liệu cấu hình nhúng làm tăng kích thước registration và registry response.
- **Nhiều key không cần thiết:** mỗi key tăng chi phí lưu trữ, serialize, parse và duy trì hợp đồng giữa provider với consumer.
- **Giá trị lặp lại:** thông tin giống nhau ở mọi instance làm registry mang thêm dữ liệu mà consumer có thể lấy từ cấu hình chung.
- **Cập nhật liên tục:** metadata thay đổi theo request, người dùng hoặc trạng thái ngắn hạn khiến registry phải xử lý biến động không cần thiết.
- **Cardinality cao:** tạo key/value riêng cho từng request, user, tenant hoặc transaction làm số biến thể tăng nhanh và gây khó khăn cho cache, metric, tìm kiếm và vận hành.
- **Dữ liệu khó tương thích:** nhúng cấu trúc JSON tùy ý vào một chuỗi khiến consumer phải parse theo một schema ngầm, dễ hỏng khi provider thay đổi.

Không có một giới hạn kích thước duy nhất áp dụng cho mọi implementation Spring Cloud và mọi registry. Giới hạn thực tế có thể đến từ API của registry, giới hạn request/response của HTTP server, reverse proxy, ingress, giới hạn lưu trữ, serialization, hoặc chính sách của nền tảng. Một giá trị được chấp nhận ở môi trường phát triển chưa chắc phù hợp với môi trường production.

Vì vậy, nhóm phát triển cần định nghĩa ngân sách metadata của riêng hệ thống, kiểm tra ở cả phía provider và pipeline triển khai, đồng thời đối chiếu giới hạn chính thức của registry đang dùng.

## 3. Thiết kế ngân sách kích thước

Một chính sách đơn giản có thể quy định:

| Thành phần | Ví dụ ngân sách nội bộ |
| --- | --- |
| Số key trên mỗi instance | Tối đa 10 key |
| Độ dài key | Tối đa 64 byte UTF-8 |
| Độ dài value | Tối đa 256 byte UTF-8 |
| Tổng key và value | Tối đa 2 KiB UTF-8 cho một instance |
| Kiểu dữ liệu | Chuỗi ngắn, có định dạng và ý nghĩa đã thống nhất |
| Tần suất thay đổi | Chỉ thay đổi khi thuộc tính instance thực sự thay đổi |

Các con số trên chỉ là ví dụ về chính sách nội bộ để bắt đầu review; chúng không phải giới hạn mặc định của Eureka, Consul hay Spring Cloud. Hãy điều chỉnh dựa trên số lượng instance, kích thước registry response, tần suất refresh, giới hạn transport và yêu cầu của sản phẩm.

Nên tính theo byte UTF-8 thay vì số ký tự. Một ký tự Unicode có thể chiếm nhiều byte. Tổng kích thước cần tính cả key, value và overhead serialization nếu cần so với giới hạn request/response thực tế.

Ngân sách cũng nên có phần dự phòng cho key mới trong các lần nâng cấp. Tránh dùng hết toàn bộ giới hạn transport chỉ cho metadata của một instance.

## 4. Chọn metadata có giá trị

Metadata tốt thường có các đặc điểm:

- **Nhỏ:** key ngắn, value ngắn, không chứa đoạn văn hoặc payload lớn.
- **Ổn định:** chỉ thay đổi khi thuộc tính triển khai hoặc năng lực của instance thay đổi.
- **Có cấu trúc:** key có quy ước, value có định dạng được kiểm tra.
- **Có mục đích:** có ít nhất một consumer hoặc quy trình vận hành sử dụng.
- **Có phạm vi rõ:** xác định thuộc tính áp dụng cho instance, service hay môi trường.
- **Có khả năng tương thích:** consumer bỏ qua key chưa biết và có giá trị mặc định hợp lý khi key tùy chọn không tồn tại.

Ví dụ key có namespace giúp tránh xung đột:

~~~~yaml
eureka:
  instance:
    metadata-map:
      platform.region: ap-southeast-1
      platform.zone: hcm-a
      contract.api-version: v2
      rollout.track: stable
~~~~

Quy ước key nên được tài liệu hóa: tên, kiểu/format, giá trị hợp lệ, ý nghĩa, chủ sở hữu và consumer phụ thuộc. Tránh dùng cùng một key với ý nghĩa khác nhau giữa các service.

Không nên dùng metadata để chứa toàn bộ cấu hình ứng dụng. Consumer cần biết địa chỉ database, feature flag hoặc giới hạn nghiệp vụ nên lấy chúng từ hệ thống cấu hình phù hợp, với quyền truy cập và vòng đời riêng.

## 5. Những dữ liệu không nên công bố trong registry

Metadata có thể được trả về cho các client có quyền đọc registry, hiển thị trên dashboard, xuất hiện trong log hoặc được sao chép vào hệ thống giám sát. Hãy giả định rằng mọi consumer được cấp quyền đọc registry đều có thể nhìn thấy metadata của instance.

Không công bố các loại dữ liệu sau:

| Loại dữ liệu | Ví dụ không nên đưa vào metadata | Nơi lưu phù hợp hơn |
| --- | --- | --- |
| Bí mật xác thực | Password, API key, access token, refresh token, client secret | Secret manager, Vault, Kubernetes Secret hoặc hệ thống quản lý secret được kiểm soát |
| Khóa mật mã | Private key, signing key, nội dung chứng thư kèm khóa riêng | KMS, HSM hoặc kho chứng thư/secret chuyên dụng |
| Dữ liệu cá nhân | Email, số điện thoại, địa chỉ, tên người dùng, mã định danh cá nhân | Hệ thống nghiệp vụ có phân quyền và chính sách bảo vệ dữ liệu |
| Dữ liệu khách hàng/tenant | Customer ID, tenant ID riêng tư, thông tin hợp đồng hoặc giao dịch | Cơ sở dữ liệu nghiệp vụ hoặc hệ thống quản lý tenant |
| Session và thông tin theo request | Session ID, cookie, correlation ID của từng request, trace baggage cá nhân | Session store, tracing system hoặc context của request |
| Payload lớn | JSON cấu hình dài, danh sách hàng nghìn phần tử, nội dung file | Config server, database, object storage hoặc API chuyên dụng |
| Thông tin hạ tầng quá chi tiết | Topology nội bộ nhạy cảm, địa chỉ quản trị, tên host chứa thông tin bí mật | CMDB hoặc hệ thống inventory hạ tầng có kiểm soát truy cập |

Không đưa secret vào metadata rồi dựa vào việc che dashboard hoặc mã hóa kết nối để bảo vệ nó. TLS bảo vệ dữ liệu trên đường truyền; TLS không tự giới hạn ai có quyền đọc metadata sau khi đã truy cập registry. Phân quyền registry và secret manager vẫn cần được cấu hình riêng.

Địa chỉ IP/hostname và port của instance là một phần tự nhiên của dữ liệu đăng ký để consumer kết nối. Tuy nhiên, chỉ công bố địa chỉ mà các consumer được phép gọi có thể truy cập. Không đưa thêm địa chỉ quản trị, endpoint debug, đường dẫn nội bộ hoặc chi tiết mạng không cần thiết vào metadata.

## 6. Metadata không phải nơi lưu trạng thái động

Không dùng metadata làm nơi cập nhật trạng thái thay đổi liên tục, ví dụ:

- Số request đang xử lý ở thời điểm hiện tại.
- CPU, memory hoặc queue depth theo từng giây.
- Số lượng user đang đăng nhập.
- Trạng thái từng đơn hàng hoặc từng tenant.
- Tỷ lệ lỗi của một cửa sổ thời gian ngắn.

Các thông tin này phù hợp hơn với metrics, health endpoint, telemetry hoặc hệ thống giám sát. Nếu một router hoặc load balancer cần biết instance có phục vụ được hay không, hãy dùng health check và cơ chế trạng thái mà implementation hỗ trợ. Metadata có thể bị cache và không bảo đảm cập nhật tức thời.

Cũng không nên nhúng thông tin bí mật hoặc trạng thái phân quyền vào metadata rồi để consumer tự quyết định quyền truy cập. Metadata là dữ liệu mô tả, không phải bằng chứng xác thực. Quyết định cho phép gọi service cần dựa trên authentication, authorization và policy đáng tin cậy.

## 7. Kiểm tra metadata trước khi đăng ký

Nên xác thực metadata tại thời điểm khởi tạo ứng dụng hoặc trước khi gọi ServiceRegistry. Ví dụ dưới đây minh họa một chính sách nội bộ với giới hạn số key, byte của key/value và tổng byte. Các con số phải được điều chỉnh theo quy định của hệ thống:

~~~~java
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.regex.Pattern;

public final class MetadataPolicy {

    private static final int MAX_ENTRIES = 10;
    private static final int MAX_KEY_BYTES = 64;
    private static final int MAX_VALUE_BYTES = 256;
    private static final int MAX_TOTAL_BYTES = 2 * 1024;

    private static final Pattern KEY_PATTERN =
            Pattern.compile("[a-zA-Z0-9][a-zA-Z0-9._-]*");

    private MetadataPolicy() {
    }

    public static void validate(Map<String, String> metadata) {
        if (metadata == null) {
            return;
        }

        if (metadata.size() > MAX_ENTRIES) {
            throw new IllegalArgumentException("Too many metadata entries");
        }

        int totalBytes = 0;

        for (Map.Entry<String, String> entry : metadata.entrySet()) {
            String key = entry.getKey();
            String value = entry.getValue();

            if (key == null || !KEY_PATTERN.matcher(key).matches()) {
                throw new IllegalArgumentException("Invalid metadata key");
            }
            if (value == null) {
                throw new IllegalArgumentException(
                        "Metadata value must not be null");
            }

            int keyBytes = key.getBytes(StandardCharsets.UTF_8).length;
            int valueBytes = value.getBytes(StandardCharsets.UTF_8).length;

            if (keyBytes > MAX_KEY_BYTES) {
                throw new IllegalArgumentException("Metadata key is too large");
            }
            if (valueBytes > MAX_VALUE_BYTES) {
                throw new IllegalArgumentException("Metadata value is too large");
            }

            totalBytes += keyBytes + valueBytes;
            if (totalBytes > MAX_TOTAL_BYTES) {
                throw new IllegalArgumentException(
                        "Metadata exceeds the configured budget");
            }
        }
    }
}
~~~~

Đoạn code trên kiểm tra cấu trúc và kích thước cơ bản. Trong production, cần bổ sung allowlist key, kiểm tra giá trị theo từng key, cấm tên key nhạy cảm, kiểm tra định dạng phiên bản/zone và kiểm thử với registry thực tế. Không log nguyên giá trị metadata khi validation thất bại vì giá trị có thể chứa thông tin nhạy cảm.

Một quy trình đăng ký an toàn có thể gồm:

1. Tạo metadata từ cấu hình đã được kiểm soát.
2. Kiểm tra key nằm trong allowlist và value đúng format.
3. Tính kích thước UTF-8 và kiểm tra ngân sách.
4. Từ chối khởi động hoặc từ chối đăng ký nếu metadata vi phạm chính sách.
5. Đăng ký instance với registry.
6. Theo dõi kích thước payload và lỗi đăng ký trong môi trường thực tế.

## 8. Quản lý thay đổi và tương thích metadata

Metadata là một hợp đồng giữa provider và consumer. Khi thay đổi key hoặc format, cần xem xét các consumer cũ có còn hoạt động được hay không.

Một số nguyên tắc:

- Thêm key mới theo hướng tương thích; consumer cũ nên bỏ qua key không nhận diện.
- Key tùy chọn phải có default rõ ràng khi không xuất hiện.
- Không đổi ý nghĩa của key hiện có mà không có kế hoạch chuyển đổi.
- Nếu value có nhiều phiên bản schema, đặt version rõ ràng và giới hạn số phiên bản cần hỗ trợ.
- Xóa key chỉ sau khi xác nhận không còn consumer phụ thuộc.
- Tránh phát sinh key động theo mỗi lần deploy nếu không có nhu cầu tra cứu thực tế.

Ví dụ consumer đọc metadata an toàn:

~~~~java
String apiVersion = instance.getMetadata()
        .getOrDefault("contract.api-version", "v1");

String region = instance.getMetadata()
        .getOrDefault("platform.region", "unknown");
~~~~

Consumer cần kiểm tra giá trị có thuộc tập được hỗ trợ hay không. Không tin cậy tuyệt đối metadata do provider tự công bố: một instance có thể khai báo sai phiên bản, zone hoặc capability. Với yêu cầu bảo mật, hãy xác minh danh tính workload và áp dụng policy độc lập.

## 9. Quan sát và rà soát metadata

Trong vận hành, theo dõi:

- Kích thước metadata trung bình, lớn nhất và phân vị cao theo service.
- Số key trên mỗi instance và số lượng key không còn consumer sử dụng.
- Tỷ lệ đăng ký thất bại do metadata không hợp lệ hoặc payload vượt giới hạn.
- Số lượng biến thể value/cardinality theo từng key.
- Các lần thay đổi schema và thời điểm rollout.
- Truy cập registry bất thường hoặc việc metadata chứa key bị cấm.

Rà soát định kỳ các key đang được công bố. Khi bỏ một key, hãy kiểm tra code consumer, dashboard, routing rule và automation có đang sử dụng nó hay không. Không ghi toàn bộ metadata vào log mặc định; chỉ log key cần thiết và đã được duyệt.

## 10. Checklist trước khi công bố metadata

- [ ] Mỗi key có consumer hoặc mục đích vận hành rõ ràng.
- [ ] Metadata chỉ chứa dữ liệu mô tả nhỏ, ổn định và có format.
- [ ] Số key, độ dài key/value và tổng byte nằm trong ngân sách nội bộ.
- [ ] Kích thước được tính theo UTF-8 byte, không chỉ theo số ký tự.
- [ ] Không có password, token, API key, private key hoặc cookie.
- [ ] Không có dữ liệu cá nhân, customer ID hoặc dữ liệu giao dịch.
- [ ] Không có payload lớn, danh sách không giới hạn hoặc JSON tùy ý.
- [ ] Không dùng metadata để thay thế health check, metrics hoặc authorization.
- [ ] Registry được bảo vệ bằng xác thực, phân quyền và TLS phù hợp.
- [ ] Consumer có thể xử lý key tùy chọn, key chưa biết và value không hợp lệ.
- [ ] Thay đổi metadata có kế hoạch tương thích và rollback.

## Ghi nhớ

- Metadata bổ sung thông tin cho service instance; nó không thay thế service ID, endpoint, health check hay authorization.
- Metadata nên nhỏ, ổn định, có cấu trúc, có mục đích và giới hạn cardinality.
- Không có một giới hạn byte chung cho mọi registry; cần kiểm tra giới hạn implementation và đặt ngân sách nội bộ.
- Không công bố secret, private key, dữ liệu cá nhân, session, thông tin khách hàng hoặc payload lớn.
- Dùng secret manager cho bí mật, config server cho cấu hình, metrics/health cho trạng thái động và object storage/database cho dữ liệu lớn.
- Xác thực metadata trước khi đăng ký, kiểm soát quyền đọc registry và rà soát consumer khi thay đổi hợp đồng.

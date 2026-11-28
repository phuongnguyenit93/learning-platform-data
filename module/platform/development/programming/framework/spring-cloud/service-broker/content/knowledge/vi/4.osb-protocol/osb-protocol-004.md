# X-Broker-API-Version và kiểm tra phiên bản giao thức

## Bối cảnh

Service broker theo Open Service Broker API (OSB API) giao tiếp với nền tảng qua HTTP. Nền tảng có thể là Cloud Foundry hoặc một hệ thống tích hợp broker để cung cấp dịch vụ trên Kubernetes. Hai phía cần hiểu cùng một hợp đồng: endpoint nào được gọi, request có cấu trúc gì, response nào hợp lệ và những khả năng giao thức nào được phép sử dụng.

OSB API dùng header HTTP `X-Broker-API-Version` để nền tảng khai báo phiên bản giao thức mà nó đang sử dụng khi gửi request tới broker. Broker dùng thông tin này để xác định request có nằm trong phạm vi tương thích hay không, đặc biệt khi broker phụ thuộc vào một tính năng chỉ xuất hiện ở phiên bản API mới hơn.

Header này thuộc **giao thức giữa Platform và Service Broker**. Nó không phải phiên bản ứng dụng broker, phiên bản Spring Boot, phiên bản thư viện Spring Cloud Open Service Broker, phiên bản catalog hay phiên bản của một service plan. Phân biệt đúng các loại phiên bản giúp tránh nâng cấp nhầm thành phần hoặc từ chối request hợp lệ.

## 1. Cấu trúc và ý nghĩa của header

Mỗi request từ Platform tới Service Broker phải chứa header `X-Broker-API-Version`. Giá trị có định dạng `MAJOR.MINOR`, ví dụ:

~~~http
X-Broker-API-Version: 2.17
~~~

Trong đó:

- `MAJOR` là số phiên bản chính. Thay đổi major có thể đi kèm thay đổi không tương thích trong hợp đồng.
- `MINOR` là số phiên bản phụ. Các lần tăng minor của OSB API được thiết kế theo hướng bổ sung, giữ khả năng tương thích với các phiên bản minor trước.

Giá trị header thể hiện phiên bản API mà Platform đang sử dụng để tạo request. Nó không khẳng định broker đã triển khai mọi tính năng của phiên bản đó. Broker cần hiểu request theo hợp đồng và chính sách tương thích mà nó hỗ trợ.

Một điểm dễ nhầm là path `/v2` và header `X-Broker-API-Version` có mục đích khác nhau:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Path phiên bản major | `/v2/catalog` | Nhóm endpoint của OSB API major version 2 |
| Header phiên bản đầy đủ | `X-Broker-API-Version: 2.17` | Phiên bản major và minor mà Platform đang sử dụng |
| Phiên bản Spring Cloud Open Service Broker | Ví dụ phiên bản dependency trong Gradle/Maven | Phiên bản thư viện triển khai broker |
| Phiên bản service plan | ID hoặc metadata do broker quản lý | Cấu hình gói dịch vụ mà khách hàng chọn |

Do đó, endpoint có thể vẫn là `GET /v2/catalog` trong khi Platform gửi header `X-Broker-API-Version: 2.17`. Không đổi path thành `/v2.17/catalog` và cũng không dùng phiên bản dependency làm giá trị header.

## 2. Header được gửi trong những request nào?

Header được yêu cầu trên các request OSB API do Platform gửi tới broker, không chỉ các thao tác thay đổi dữ liệu. Ví dụ:

| Nhóm request | Ví dụ endpoint | Header phiên bản |
|---|---|---|
| Đọc catalog | `GET /v2/catalog` | Bắt buộc |
| Cấp phát service instance | `PUT /v2/service_instances/{instance_id}` | Bắt buộc |
| Truy vấn service instance | `GET /v2/service_instances/{instance_id}` | Bắt buộc |
| Cập nhật service instance | `PATCH /v2/service_instances/{instance_id}` | Bắt buộc |
| Thu hồi service instance | `DELETE /v2/service_instances/{instance_id}` | Bắt buộc |
| Theo dõi operation | `GET /v2/service_instances/{instance_id}/last_operation` | Bắt buộc |
| Tạo binding | `PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}` | Bắt buộc |
| Thu hồi binding | `DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id}` | Bắt buộc |

Header cần có ngay cả khi request chỉ đọc catalog. Vì vậy, không nên chỉ kiểm tra phiên bản trong controller cấp phát hoặc cập nhật instance. Cơ chế kiểm tra nên được áp dụng nhất quán cho toàn bộ bề mặt endpoint OSB API.

Ví dụ request đọc catalog:

~~~http
GET /v2/catalog HTTP/1.1
Host: broker.example.internal
Authorization: Basic <broker-credentials>
X-Broker-API-Version: 2.17
Accept: application/json
~~~

Ví dụ request cấp phát:

~~~http
PUT /v2/service_instances/db-instance-42?accepts_incomplete=true HTTP/1.1
Host: broker.example.internal
Authorization: Basic <broker-credentials>
X-Broker-API-Version: 2.17
Content-Type: application/json

{
  "service_id": "database-service",
  "plan_id": "standard-plan",
  "organization_guid": "org-123",
  "space_guid": "space-456",
  "parameters": {
    "storage_gb": 20,
    "engine": "postgres"
  }
}
~~~

`2.17` trong ví dụ là giá trị minh họa. Khi tích hợp thật, cần dùng giá trị do Platform gửi và đối chiếu với phiên bản OSB API mà broker đã triển khai.

## 3. Quy tắc tương thích giữa major và minor version

### Major version

Major version phân định thế hệ hợp đồng. Thay đổi major có thể làm thay đổi cấu trúc hoặc ý nghĩa của request/response theo cách không tương thích. Một broker triển khai endpoint thuộc major version 2 không được mặc nhiên xem một major version khác là tương đương.

Khi có major version mới, cần đánh giá rõ:

- Broker có endpoint và mô hình dữ liệu tương ứng hay chưa.
- Những quy tắc xử lý, status code và error response có thay đổi không.
- Platform nào đang gọi broker và major version mà chúng hỗ trợ.
- Cần triển khai endpoint song song, adapter chuyển đổi hay một đợt nâng cấp đồng bộ.

Không nên chỉ so sánh chuỗi header hoặc bỏ qua phần major. Nếu major không thuộc hợp đồng mà broker triển khai, request không được xử lý như thể nó thuộc major hiện tại.

### Minor version

Các minor revision của OSB API được thiết kế theo hướng bổ sung. Một minor version mới có thể thêm trường, header hoặc khả năng giao thức mà không làm thay đổi cách hiểu các phần đã tồn tại trong phiên bản trước.

Điều này dẫn đến một nguyên tắc quan trọng: broker không nên từ chối mọi request chỉ vì giá trị minor trong header lớn hơn minor mà nhóm phát triển ghi nhớ hoặc từng triển khai. Header cho biết phiên bản Platform sử dụng; nó không phải phép so sánh đơn giản với số phiên bản của thư viện Java.

Tuy nhiên, broker có thể phụ thuộc vào một khả năng chỉ được định nghĩa ở minor version mới. Khi Platform khai báo phiên bản thấp hơn mức cần thiết, broker có thể trả `412 Precondition Failed` và giải thích phiên bản API mà Platform cần sử dụng. Ví dụ, nếu một luồng nghiệp vụ của broker bắt buộc dựa vào một trường hoặc hành vi được bổ sung từ minor version mới, broker phải kiểm tra Platform có công bố phiên bản đủ mới trước khi thực hiện luồng đó.

### Không biến minor version thành khóa chính xác

Một chính sách chỉ chấp nhận đúng `2.17` sẽ dễ gây lỗi tích hợp. Platform đang dùng `2.16` có thể vẫn gửi các request hoàn toàn tương thích với broker; ngược lại, Platform dùng `2.18` có thể gửi thêm dữ liệu tùy chọn mà broker không cần sử dụng.

Chính sách nên xác định:

1. Những major version mà broker thực sự hỗ trợ.
2. Phiên bản tối thiểu cần thiết cho từng tính năng mà broker sử dụng.
3. Cách xử lý các trường hoặc hành vi được bổ sung ở minor version mới.
4. Thông điệp lỗi rõ ràng khi Platform cần nâng cấp phiên bản.

Nếu một tính năng không phụ thuộc vào thay đổi giao thức mới, broker nên tiếp tục xử lý theo hợp đồng tương thích. Nếu tính năng đó bắt buộc, broker cần từ chối trước khi tạo side effect và cung cấp hướng dẫn nâng cấp cụ thể.

## 4. Quy trình kiểm tra phiên bản trong broker

Việc kiểm tra nên diễn ra ở ranh giới HTTP hoặc lớp giao thức, trước khi controller gọi service nghiệp vụ. Mục tiêu là loại request không đáp ứng hợp đồng ngay từ đầu, đồng thời không để logic kiểm tra bị lặp ở từng use case.

Quy trình đề xuất:

1. Đọc `X-Broker-API-Version` từ request.
2. Kiểm tra header có hiện diện hay không.
3. Kiểm tra giá trị có đúng định dạng `MAJOR.MINOR` hay không.
4. Chuyển hai thành phần thành số nguyên để so sánh.
5. Kiểm tra major version thuộc phạm vi broker hỗ trợ.
6. Kiểm tra Platform có đáp ứng phiên bản tối thiểu của tính năng mà request cần sử dụng hay không.
7. Chỉ sau khi hợp lệ mới chuyển request vào controller/service để xử lý nghiệp vụ.

### Thiếu header hoặc header sai định dạng

Header là dữ liệu bắt buộc theo hợp đồng. Nếu request thiếu header, đặc tả cho phép broker trả `400 Bad Request` và thông báo header là bắt buộc. Giá trị sai định dạng cũng cần được xử lý như dữ liệu request không hợp lệ, với thông báo đủ rõ để người vận hành xác định lỗi cấu hình phía Platform hoặc proxy.

Ví dụ các giá trị không phù hợp với định dạng `MAJOR.MINOR`:

| Giá trị | Vấn đề |
|---|---|
| Không có header | Thiếu dữ liệu bắt buộc |
| `2` | Thiếu thành phần minor |
| `2.17.1` | Có thành phần patch ngoài định dạng hai thành phần của header OSB API |
| `v2.17` | Có tiền tố không thuộc định dạng được mô tả |
| `two.seventeen` | Không phải hai thành phần số |
| `2.x` | Minor không phải số nguyên |
| Chuỗi rỗng | Không có giá trị phiên bản |

Không nên parse giá trị này thành số thực. Nếu coi `2.10` là số thập phân thì nó có thể bị hiểu thành `2.1`, làm sai kết quả so sánh. Hãy tách chuỗi tại dấu chấm, parse `major` và `minor` thành số nguyên, đồng thời kiểm tra số thành phần trước khi so sánh.

### Phiên bản không đáp ứng yêu cầu của broker

Nếu broker cần một khả năng chỉ có trong phiên bản API mới hơn và Platform gửi phiên bản thấp hơn, broker có thể trả `412 Precondition Failed`. Response nên nói rõ phiên bản hiện tại và phiên bản tối thiểu cần dùng. Broker phải thực hiện kiểm tra trước khi thay đổi database, tạo tài nguyên provider, ghi operation hoặc gửi công việc vào hàng đợi.

Ví dụ response minh họa:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/json

{
  "error": "UnsupportedApiVersion",
  "description": "This broker operation requires OSB API version 2.17 or later. Update the Platform API version and retry."
}
~~~

Mã lỗi `UnsupportedApiVersion` ở đây là ví dụ do broker lựa chọn; phần quan trọng là status code và mô tả phải giúp vận hành nhận biết điều kiện phiên bản không đáp ứng. Không dùng `412` thay cho mọi lỗi parse hoặc lỗi xác thực.

## 5. Phân biệt 400, 401, 403 và 412

Các lỗi ở lớp giao thức có nguyên nhân khác nhau và cần phản hồi đúng để Platform hoặc người vận hành xử lý:

| HTTP status | Khi nào dùng | Hướng xử lý |
|---|---|---|
| `400 Bad Request` | Thiếu header bắt buộc, header sai định dạng hoặc request malformed | Sửa request, cấu hình proxy hoặc client |
| `401 Unauthorized` | Thiếu hoặc sai thông tin xác thực broker | Kiểm tra credential và cơ chế authentication |
| `403 Forbidden` | Caller đã được xác thực nhưng không được phép thực hiện hành động | Kiểm tra quyền và chính sách truy cập |
| `412 Precondition Failed` | Broker yêu cầu một phiên bản API mới hơn để sử dụng tính năng mà request cần | Nâng cấp hoặc cấu hình Platform dùng phiên bản phù hợp |

`X-Broker-API-Version` không phải credential và không chứng minh danh tính caller. Một request có phiên bản hợp lệ vẫn phải đi qua authentication, authorization và kiểm tra quyền sở hữu service instance. Ngược lại, credential đúng cũng không làm cho một request thiếu header phiên bản trở thành hợp lệ.

## 6. Thiết kế bộ kiểm tra phiên bản

Nên tập trung logic đọc và kiểm tra header vào một thành phần dùng chung. Tùy kiến trúc ứng dụng, thành phần đó có thể là filter, interceptor, argument resolver hoặc cơ chế hỗ trợ sẵn trong phiên bản Spring Cloud Open Service Broker đang sử dụng.

Một thiết kế tối thiểu có các phần:

- `ApiVersion`: kiểu dữ liệu bất biến gồm `major` và `minor`.
- `ApiVersionParser`: kiểm tra định dạng và chuyển chuỗi header thành `ApiVersion`.
- `ApiVersionPolicy`: xác định major được hỗ trợ và phiên bản tối thiểu cho từng khả năng.
- `ApiVersionFilter` hoặc lớp tích hợp tương đương: đọc header, gọi parser/policy và tạo lỗi HTTP phù hợp.

Ví dụ Java dưới đây minh họa cách parse phiên bản. Đây là mã mô hình hóa, không phải API class có sẵn của Spring Cloud Open Service Broker:

~~~java
public record ApiVersion(int major, int minor)
        implements Comparable<ApiVersion> {

    public ApiVersion {
        if (major < 0 || minor < 0) {
            throw new IllegalArgumentException("Version parts must be non-negative");
        }
    }

    @Override
    public String toString() {
        return major + "." + minor;
    }

    @Override
    public int compareTo(ApiVersion other) {
        int majorComparison = Integer.compare(major, other.major);
        return majorComparison != 0
                ? majorComparison
                : Integer.compare(minor, other.minor);
    }

    public static ApiVersion parse(String value) {
        if (value == null || !value.matches("(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)")) {
            throw new IllegalArgumentException("Expected MAJOR.MINOR");
        }

        String[] parts = value.split("\\.", -1);
        try {
            return new ApiVersion(
                    Integer.parseInt(parts[0]),
                    Integer.parseInt(parts[1]));
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Version part is out of range", ex);
        }
    }
}
~~~

So sánh hai phiên bản bằng số nguyên cho kết quả đúng:

~~~java
ApiVersion.parse("2.10").compareTo(ApiVersion.parse("2.9"));
// Kết quả dương: 2.10 mới hơn 2.9
~~~

Sau bước parse, policy có thể kiểm tra khả năng cụ thể:

~~~java
void requireVersion(ApiVersion platformVersion, ApiVersion minimum) {
    if (platformVersion.compareTo(minimum) < 0) {
        throw new PreconditionFailedException(
                "This operation requires OSB API " + minimum + " or later");
    }
}
~~~

Đoạn mã trên chỉ minh họa phép so sánh. Trong ứng dụng thực tế, cần xử lý ngoại lệ thành response OSB API và kết hợp kiểm tra major version theo policy. Cũng cần quyết định rõ liệu một endpoint có yêu cầu phiên bản tối thiểu riêng hay toàn bộ broker có một mức tối thiểu chung.

### Ví dụ filter ở ranh giới HTTP

Một filter minh họa có thể kiểm tra header trước khi request đi vào controller:

~~~java
public class OsbApiVersionFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-Broker-API-Version";
    private final ApiVersionPolicy policy;
    private final ObjectMapper objectMapper;

    public OsbApiVersionFilter(
            ApiVersionPolicy policy,
            ObjectMapper objectMapper) {
        this.policy = policy;
        this.objectMapper = objectMapper;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws IOException, ServletException {

        String value = request.getHeader(HEADER);
        if (value == null || value.isBlank()) {
            writeError(response,
                    HttpServletResponse.SC_BAD_REQUEST,
                    "BadRequest",
                    "Missing required X-Broker-API-Version header");
            return;
        }

        final ApiVersion version;
        try {
            version = ApiVersion.parse(value.trim());
        } catch (IllegalArgumentException ex) {
            writeError(response,
                    HttpServletResponse.SC_BAD_REQUEST,
                    "BadRequest",
                    "X-Broker-API-Version must use MAJOR.MINOR format");
            return;
        }

        try {
            policy.validate(version, request.getRequestURI());
        } catch (PreconditionFailedException ex) {
            writeError(response,
                    HttpServletResponse.SC_PRECONDITION_FAILED,
                    "UnsupportedApiVersion",
                    ex.getMessage());
            return;
        }

        filterChain.doFilter(request, response);
    }

    private void writeError(
            HttpServletResponse response,
            int status,
            String error,
            String description) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        objectMapper.writeValue(response.getOutputStream(),
                Map.of("error", error, "description", description));
    }
}
~~~

Đây là ví dụ kiến trúc, cần điều chỉnh cho ứng dụng thực tế. Các import `ObjectMapper`, `MediaType` và `Map` được lược bỏ để tập trung vào luồng xử lý. Cần giới hạn filter cho các route OSB API, giữ nguyên các route quản trị/health check, và phối hợp thứ tự với Spring Security để không làm thay đổi cách trả lỗi authentication. Bảo đảm filter không tạo xung đột với filter hoặc cơ chế kiểm tra phiên bản mà framework đã đăng ký. Với broker dùng Spring WebFlux, cần dùng `WebFilter` và kiểu xử lý reactive tương ứng thay vì Servlet `OncePerRequestFilter`.

## 7. Tích hợp với Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp các thành phần để triển khai endpoint và hợp đồng OSB API trên Spring Boot. Khi tích hợp kiểm tra phiên bản, cần xác định rõ trách nhiệm nào framework đã xử lý và trách nhiệm nào thuộc ứng dụng.

Các nguyên tắc thực hiện:

1. Kiểm tra tài liệu của đúng phiên bản Spring Cloud Open Service Broker đang dùng để biết cơ chế hỗ trợ `X-Broker-API-Version`.
2. Không tự tạo một controller trùng với endpoint mà framework đã đăng ký.
3. Nếu framework đã kiểm tra header và từ chối phiên bản không phù hợp, cấu hình policy tại extension point được hỗ trợ thay vì thêm một filter cạnh tranh.
4. Nếu ứng dụng cần giới hạn phiên bản tối thiểu theo tính năng riêng, đặt policy ở lớp giao thức hoặc application boundary trước khi gọi nghiệp vụ.
5. Giữ service nghiệp vụ độc lập với HTTP header. Chuyển thông tin phiên bản thành một context hoặc capability đã chuẩn hóa nếu use case thật sự cần biết.

Ví dụ, `CatalogService` không nên tự đọc `HttpServletRequest` để kiểm tra header. Việc xác định request có đáp ứng giao thức hay không thuộc lớp HTTP/protocol. Catalog service chỉ cần cung cấp catalog theo mô hình mà ứng dụng quản lý. Tương tự, `ServiceInstanceService` tập trung xử lý provision, retrieve, update và deprovision sau khi request đã qua kiểm tra giao thức.

Nếu broker dùng nhiều adapter cho Cloud Foundry và Kubernetes, mỗi adapter nền tảng có thể bổ sung context hoặc chính sách riêng. Tuy nhiên, cả hai vẫn phải tuân theo cùng quy tắc phiên bản OSB API trên ranh giới Platform-to-Broker. Phiên bản Kubernetes, phiên bản Cloud Foundry và phiên bản OSB API là ba thông tin độc lập.

## 8. Khả năng tương thích khi nâng cấp

Khi nâng cấp broker hoặc Spring Cloud Open Service Broker, nhóm phát triển cần lập bảng tương thích thay vì chỉ đổi version dependency. Một lần nâng cấp có thể thay đổi thư viện Java mà không thay đổi OSB API mà broker công bố; cũng có thể bổ sung khả năng OSB API mới mà không cần thay đổi major version.

Một bảng policy nội bộ có thể được quản lý như sau:

| Thuộc tính | Ví dụ minh họa | Cách sử dụng |
|---|---|---|
| Major được hỗ trợ | `2` | Từ chối major ngoài hợp đồng đã triển khai |
| Minor thấp nhất cho tính năng cơ bản | `2.13` | Bảo đảm Platform có các khả năng tối thiểu cần dùng |
| Minor thấp nhất cho tính năng nâng cao | `2.17` | Chỉ yêu cầu khi request thực sự cần tính năng đó |
| Phiên bản thư viện Spring | Giá trị dependency riêng | Quản lý tương thích ở tầng Java/framework |
| Phiên bản catalog | Thông tin service/plan do broker quản lý | Quản lý sản phẩm được công bố |

Các con số trong bảng chỉ minh họa cách tổ chức policy, không phải tuyên bố rằng mọi broker đều phải hỗ trợ các phiên bản đó. Giá trị thực tế cần dựa trên tính năng OSB API mà broker dùng và khả năng của Platform tích hợp.

### Nguyên tắc nâng cấp an toàn

- Đọc release note và thay đổi của OSB API trước khi dùng tính năng mới.
- Giữ tương thích với các minor version cũ khi broker không phụ thuộc vào tính năng mới.
- Chỉ đặt minimum version cao hơn khi có lý do giao thức cụ thể.
- Nếu phải nâng minimum version, thông báo rõ cho đội vận hành Platform trước khi triển khai.
- Kiểm thử request từ từng Platform version được hỗ trợ, gồm catalog, provision, update, deprovision, binding và polling.
- Triển khai theo từng môi trường, theo dõi lỗi `400` và `412`, rồi mới mở rộng.
- Có kế hoạch rollback nếu Platform chưa thể nâng phiên bản hoặc proxy làm mất header.

## 9. Lỗi thường gặp trong triển khai

### Proxy hoặc ingress loại bỏ header

Một request có header ở phía Platform nhưng đến Spring Boot lại không có header có thể do reverse proxy chưa chuyển tiếp header tùy chỉnh. Hãy kiểm tra cấu hình forwarding, gateway route và log metadata an toàn ở cả hai phía. Không ghi toàn bộ request headers nếu chúng có thể chứa credential.

### Parse phiên bản thành số thực

So sánh `2.10` với `2.9` bằng kiểu `double` có thể tạo kết quả sai về mặt phiên bản. Hãy parse thành hai số nguyên và so sánh theo thứ tự major rồi minor.

### Chỉ chấp nhận một minor version

Kiểm tra bằng chuỗi bằng chính xác như `value.equals("2.17")` khiến broker từ chối các request tương thích. Hãy mô hình hóa major được hỗ trợ và yêu cầu tối thiểu của từng khả năng.

### Trả sai status code

Thiếu header hoặc request malformed thuộc nhóm `400`. Khi broker cần một phiên bản API mới hơn để sử dụng khả năng bắt buộc, `412 Precondition Failed` là phản hồi phù hợp. Không dùng `401` hoặc `403` để báo lỗi phiên bản.

### Kiểm tra phiên bản sau khi đã tạo tài nguyên

Nếu broker tạo database hoặc ghi operation rồi mới phát hiện Platform không đáp ứng phiên bản yêu cầu, hệ thống có thể để lại tài nguyên mồ côi. Hãy kiểm tra header và policy trước mọi side effect nghiệp vụ.

### Nhầm phiên bản thư viện với phiên bản giao thức

Nâng `spring-cloud-open-service-broker` lên phiên bản mới không có nghĩa tự động phải đổi giá trị header mà Platform gửi. Hai phiên bản được quản lý độc lập và phải được ghi nhận riêng trong cấu hình, tài liệu triển khai và kiểm thử.

## 10. Kiểm thử và quan sát

Kiểm thử phiên bản cần bao phủ cả trường hợp hợp lệ, lỗi định dạng và điều kiện tương thích:

| Trường hợp | Kết quả cần xác minh |
|---|---|
| Header hợp lệ, tính năng tương thích | Request đi tiếp tới controller/service |
| Thiếu header | `400 Bad Request` theo chính sách broker |
| Header rỗng hoặc sai định dạng | Request bị từ chối trước nghiệp vụ |
| Major version không hỗ trợ | Broker không xử lý như major hiện tại |
| Minor thấp hơn yêu cầu của tính năng | `412 Precondition Failed` kèm hướng dẫn nâng cấp |
| Minor mới hơn, không có phụ thuộc tính năng mới | Broker vẫn xử lý phần hợp đồng tương thích |
| Proxy chuyển tiếp request | Header tới ứng dụng giữ nguyên giá trị |
| Request phiên bản lỗi gọi provision | Không tạo instance, không ghi operation, không gọi provider |

Kiểm thử tích hợp nên gửi HTTP request thật qua endpoint broker, không chỉ gọi trực tiếp parser. Cách này xác nhận header được đọc đúng sau security filter, reverse proxy test setup và router. Với các luồng thay đổi tài nguyên, cần kiểm tra repository và mock provider để chắc chắn request bị từ chối không tạo side effect.

Về observability, nên ghi nhận:

- Số request theo major/minor version và endpoint.
- Số request thiếu hoặc sai định dạng header.
- Số response `412` theo endpoint và lý do policy.
- Phiên bản Platform được quan sát theo thời gian để lên kế hoạch nâng cấp.
- Trace ID hoặc request identity để liên kết request với log, nếu Platform gửi header tương ứng.

Không đưa `instance_id`, tenant ID hoặc giá trị header tùy ý thành nhãn metric có cardinality cao. Không log credential, token hoặc toàn bộ header nhạy cảm. Thông tin phiên bản có thể dùng cho vận hành và thống kê, nhưng không thay thế authentication hoặc authorization.

## 11. Checklist triển khai

- [ ] Tất cả endpoint OSB API đều nhận và kiểm tra `X-Broker-API-Version`.
- [ ] Header được parse theo định dạng `MAJOR.MINOR` bằng số nguyên.
- [ ] Policy phân biệt major version và minor version.
- [ ] Các minor version tương thích được xử lý theo nguyên tắc additive của OSB API.
- [ ] Chỉ trả `412` khi Platform cần phiên bản mới hơn cho khả năng broker phụ thuộc.
- [ ] Thiếu header hoặc request malformed được xử lý theo `400`.
- [ ] Kiểm tra phiên bản diễn ra trước side effect.
- [ ] Proxy và ingress giữ nguyên header khi chuyển tiếp request.
- [ ] Không trộn version của OSB API với version thư viện hoặc version catalog.
- [ ] Có integration test cho request hợp lệ, thiếu header, sai định dạng và phiên bản không đáp ứng.
- [ ] Có metric và log an toàn để phát hiện Platform cũ trước khi nâng minimum version.

## Kết luận

`X-Broker-API-Version` là tín hiệu để broker hiểu phiên bản hợp đồng mà Platform đang sử dụng. Broker cần yêu cầu header trên mọi request OSB API, parse chính xác dạng `MAJOR.MINOR`, kiểm tra tương thích trước khi gọi nghiệp vụ và trả lỗi phù hợp khi request không đáp ứng điều kiện. Chính sách tốt giữ được khả năng tương thích giữa các minor version, chỉ yêu cầu Platform nâng cấp khi một tính năng thực sự phụ thuộc vào phiên bản mới, nhờ đó việc tích hợp Cloud Foundry, Kubernetes và các nền tảng khác ổn định hơn.

## Tài liệu tham khảo

- [Open Service Broker API specification — API Version Header](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md#api-version-header)
- [Spring Cloud Open Service Broker — GitHub project](https://github.com/spring-cloud/spring-cloud-open-service-broker)

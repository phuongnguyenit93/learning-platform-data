# Bộ nhớ đệm dùng chung và customizer phụ thuộc request

## 1. Vì sao cache ảnh hưởng đến OpenAPI document?

Springdoc OpenAPI tạo tài liệu từ handler mapping, annotation, DTO, Jackson metadata, validation constraints, security configuration và các customizer. Với ứng dụng có nhiều controller, schema lồng nhau và nhiều operation, quá trình này có thể tiêu tốn CPU và thời gian.

Nếu Springdoc phải phân tích lại toàn bộ cấu trúc API mỗi lần client tải /v3/api-docs, endpoint tài liệu có thể trở thành nguồn tải lặp lại. Vì vậy, Springdoc mặc định tính OpenAPI description rồi lưu vào cache để các request sau dùng lại.

Cache giúp giảm chi phí dựng document, nhưng tạo ra một ranh giới quan trọng: nội dung đã tính có thể được dùng chung cho nhiều request. Nếu customizer lấy thông tin từ request hiện tại, ví dụ host, scheme, tenant hoặc header, kết quả của request đầu tiên có thể được giữ lại và trả cho request sau.

Bài này tập trung vào cách cache hoạt động, cách đo chi phí lần đầu và các lần đọc sau, cách cấu hình preload, và cách xử lý customizer có phụ thuộc request mà không làm rò rỉ metadata giữa các client.

## 2. Quá trình tạo tài liệu gồm những công việc nào?

Khi Springdoc cần tạo OpenAPI description, framework phải kết hợp nhiều nguồn metadata:

1. Phát hiện handler method và request mapping của Spring MVC hoặc WebFlux.
2. Đọc annotation trên controller, method, parameter và DTO.
3. Phân tích kiểu request body, response và generic type.
4. Chuyển Jackson property, enum và serialization metadata thành schema.
5. Kết hợp Bean Validation constraints.
6. Tạo components, schema references, security schemes và responses.
7. Áp dụng OpenApiCustomizer và các cấu hình document group.
8. Hoàn thiện OpenAPI model để trả về cho endpoint tài liệu.

Chi phí phụ thuộc vào kích thước và độ phức tạp của API. Một ứng dụng có vài endpoint và DTO đơn giản thường nhẹ hơn ứng dụng có hàng trăm operation, generic wrapper, polymorphic schema, HATEOAS, Data REST, nhiều group và customizer phức tạp.

Không nên xem thời gian tải /v3/api-docs chỉ là thời gian serialize JSON. Lần tạo document đầu tiên có thể phải thực hiện cả quá trình phân tích và dựng OpenAPI model.

## 3. Phân biệt lần tạo đầu tiên và các lần đọc sau

Theo cấu hình mặc định, Springdoc tính OpenAPI description một lần rồi cache. Vì vậy, request đầu tiên cần tạo description có thể chậm hơn các request sau.

| Giai đoạn | Công việc chính | Chi phí thường gặp |
|---|---|---|
| Khởi động ứng dụng | Khởi tạo Spring context, bean, handler mapping | Chi phí startup của toàn ứng dụng |
| Lần đầu tải tài liệu | Phân tích API, dựng schema, chạy customizer và lưu cache | Có thể cao nhất đối với endpoint docs |
| Các lần tải tiếp theo | Lấy description đã cache, serialize và trả HTTP | Thường thấp hơn |
| Cache miss hoặc entry bị loại | Tạo lại description cho locale tương ứng | Phát sinh lại chi phí dựng tài liệu |
| Restart hoặc tạo instance mới | Cache trong process chưa có | Có thể lặp lại chi phí lần đầu |

Cần phân biệt cache của Springdoc với HTTP response cache. Springdoc cache OpenAPI description đã tính. Request vẫn đi qua web stack, content negotiation và quá trình ghi response. JSON/YAML vẫn cần được chuyển thành representation phù hợp và truyền qua HTTP; không nên mặc định toàn bộ response bytes đã được cache.

Swagger UI cũng tải HTML, JavaScript, CSS và swagger-config. Cache OpenAPI description không đồng nghĩa tất cả tài nguyên giao diện đều dùng cùng một cache.

## 4. Cache mặc định của Springdoc

Thuộc tính chính:

~~~yaml
springdoc:
  cache:
    disabled: false
~~~

Giá trị mặc định của springdoc.cache.disabled là false, nghĩa là cache OpenAPI description được bật.

Khi cache bật:

- Springdoc tái sử dụng description đã tính.
- Request tiếp theo không cần dựng lại toàn bộ document nếu cache entry còn tồn tại.
- Một description được cache cho mỗi locale được yêu cầu qua Accept-Language.
- Cache là trạng thái trong bộ nhớ của instance ứng dụng.
- Khi instance restart, cache trong process được tạo lại.

Cache không phải một kho lưu trữ dùng chung giữa các pod hoặc máy chủ. Nếu deployment có nhiều replica, mỗi instance có cache riêng. Request đầu tiên đến từng instance có thể cần tạo description riêng, trừ khi instance đã preload.

## 5. Cache được phân biệt theo locale

Springdoc hỗ trợ tạo OpenAPI description theo locale được yêu cầu. Ví dụ client gửi:

~~~http
GET /v3/api-docs
Accept-Language: vi
~~~

hoặc:

~~~http
GET /v3/api-docs
Accept-Language: en
~~~

Document có thể chứa summary, description hoặc metadata đã được dịch theo locale. Vì nội dung khác nhau, Springdoc lưu description theo locale được yêu cầu.

Điều này có nghĩa một ứng dụng có nhiều locale có thể cần nhiều cache entries. Khi một locale chưa có entry, Springdoc phải tính description cho locale đó.

Nếu người dùng gửi nhiều giá trị Accept-Language không cần thiết, số locale được yêu cầu có thể tăng và làm cache churn. Hãy xác định danh sách ngôn ngữ tài liệu thực sự hỗ trợ, cấu hình preload đúng các locale cần thiết và giới hạn số entry theo phiên bản Springdoc đang dùng.

Không nên giả định cache key mặc định bao gồm mọi request header. Tài liệu Springdoc mô tả cache theo locale; không được coi host, tenant, user ID, role hoặc arbitrary header là một chiều phân vùng cache tự động.

## 6. Giới hạn số cache entries

Ở các phiên bản Springdoc hỗ trợ giới hạn cache, có thể cấu hình:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 100
~~~

springdoc.cache.max-entries đặt số lượng OpenAPI descriptions tối đa được giữ trong cache. Tài liệu cấu hình Springdoc v2 nêu thuộc tính này từ phiên bản 2.9.1; các dòng phiên bản khác cần kiểm tra property reference tương ứng.

Khi đạt giới hạn, entry cũ nhất theo chính sách eviction của phiên bản được dùng sẽ bị loại để nhường chỗ. Tài liệu Springdoc hiện mô tả hành vi loại entry ít được sử dụng gần đây nhất.

Giới hạn quá thấp có thể khiến locale thường dùng bị loại và phải dựng lại. Giới hạn quá cao có thể giữ nhiều OpenAPI model trong heap, đặc biệt khi document lớn hoặc có nhiều schema.

Chọn max-entries dựa trên số locale thực tế, kích thước document và heap của instance. Không tăng giới hạn chỉ để tránh cache miss nếu ứng dụng không cần nhiều locale.

## 7. Cache là bộ nhớ trong từng instance

Giả sử deployment có ba replica:

~~~text
                  Load Balancer
                  /     |     \
                 v      v      v
              Pod A   Pod B   Pod C
              Cache   Cache   Cache
~~~

Mỗi pod có process và cache riêng:

- Request đầu tiên đến Pod A có thể tạo description ở Pod A.
- Request tiếp theo đến Pod A có thể dùng lại entry.
- Request đầu tiên đến Pod B vẫn có thể cần tạo description ở Pod B.
- Khi Pod C restart, cache của Pod C bắt đầu trống.

Do load balancer phân phối request, người dùng có thể thấy một số request đầu sau deployment chậm hơn các request sau. Đây không nhất thiết là cache không hoạt động; request có thể đang tới instance chưa warm.

Không giả định cache Springdoc được chia sẻ giữa các replica. Nếu cần document giống nhau ở mọi replica, hãy bảo đảm source, profile, locale và customizer cho ra cùng kết quả; cache chỉ tối ưu trong từng process.

## 8. Khi nào nên preload OpenAPI document?

Nếu muốn chuyển chi phí tạo document từ request đầu tiên sang startup, Springdoc cung cấp preload:

~~~yaml
springdoc:
  pre-loading-enabled: true
~~~

Thuộc tính springdoc.pre-loading-enabled bật việc tải trước OpenAPI description khi ứng dụng khởi động. Mặc định thuộc tính này là false.

Có thể chỉ định các locale cần preload:

~~~yaml
springdoc:
  pre-loading-enabled: true
  pre-loading-locales:
    - vi
    - en
~~~

Nếu không chỉ định danh sách locale, Springdoc sử dụng locale mặc định theo tài liệu cấu hình của phiên bản.

Preload phù hợp khi:

- Endpoint tài liệu được gọi thường xuyên ngay sau deployment.
- Không muốn người dùng đầu tiên chịu chi phí dựng schema.
- Tài liệu có số locale nhỏ và xác định.
- Ứng dụng chấp nhận tăng thời gian startup để chuẩn bị document.

Preload không làm giảm tổng khối lượng công việc cần thực hiện; nó thay đổi thời điểm thực hiện. CPU và memory được dùng trong startup thay vì lần đầu client tải tài liệu.

## 9. Đánh đổi giữa preload và readiness

Khi bật preload, ứng dụng cần hoàn tất quá trình tạo document trước khi phục vụ đầy đủ theo luồng startup tương ứng. Điều này có thể làm startup hoặc thời gian đạt readiness dài hơn.

Cần đo:

- Thời gian từ lúc process bắt đầu tới lúc application ready.
- Thời gian tạo OpenAPI description cho từng locale preload.
- CPU và heap trong startup.
- Thời gian endpoint /v3/api-docs sau khi readiness.
- Hành vi khi có nhiều replica khởi động đồng thời.

Nếu orchestration có startup probe và readiness probe, hãy đặt ngưỡng phù hợp với startup thực tế. Không tăng timeout quá lớn để che một customizer đang gọi database hoặc HTTP service chậm.

Với ứng dụng có nhiều locale, preload toàn bộ locale có thể làm startup lâu và tăng heap. Chỉ preload locale mà người dùng thực sự cần.

Nếu customizer phụ thuộc request, preload là một vấn đề đặc biệt: lúc startup thường không có request của client để cung cấp host hoặc tenant. Không dùng request-dependent customizer cùng preload nếu chưa có fallback rõ ràng và đã xác minh hành vi.

## 10. Khi nào nên tắt cache?

Springdoc cung cấp thuộc tính:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Khi cache bị tắt, Springdoc tính lại OpenAPI description theo request thay vì dùng lại description đã cache. Tài liệu Springdoc nêu một tình huống phù hợp là Swagger UI được phục vụ qua các proxy nội bộ và bên ngoài, trong đó server URL cần được tính theo từng HTTP request.

Ví dụ, cùng một ứng dụng có thể được truy cập qua hai hostname công khai khác nhau. Nếu OpenAPI server URL được suy ra từ request hiện tại, một document đã cache từ hostname thứ nhất có thể không phù hợp với hostname thứ hai.

Tắt cache có thể giải quyết vấn đề dữ liệu phụ thuộc request, nhưng làm tăng chi phí CPU và thời gian cho mỗi lần tải tài liệu. Nếu Swagger UI hoặc monitoring liên tục tải OpenAPI document, việc dựng lại có thể trở thành tải lặp đáng kể.

Không tắt cache chỉ để làm mới document sau khi thay đổi code. Thay đổi code thường đi cùng restart/deploy, khi đó cache trong instance mới được tạo lại. Trong môi trường phát triển, có thể tắt cache để quan sát thay đổi runtime, nhưng production nên có lý do cụ thể.

## 11. Cache không tự phân biệt host, tenant hoặc người dùng

Giả sử customizer thêm server URL từ request:

~~~text
Request A:
Host = api-a.example.com

Request B:
Host = api-b.example.com
~~~

Nếu request A là lần đầu tạo document và cache đang bật, document có thể chứa server URL của api-a.example.com. Request B có thể nhận lại description đã cache đó, dù host hiện tại là api-b.example.com.

Tương tự, nếu customizer thêm metadata tenant:

~~~text
Tenant A -> x-tenant: tenant-a
Tenant B -> x-tenant: tenant-b
~~~

cache theo locale không tự tạo hai bản document riêng cho hai tenant. Một document được tạo trong ngữ cảnh tenant A có thể được dùng lại trong ngữ cảnh tenant B.

Đây không chỉ là vấn đề hiển thị sai URL. Nếu document chứa path, schema, security requirement hoặc metadata riêng theo tenant/user, việc dùng lại cache có thể làm lộ thông tin hoặc công bố sai bề mặt API.

Không đưa dữ liệu người dùng, quyền truy cập hoặc thông tin tenant riêng vào một document dùng chung nếu không có cơ chế phân vùng cache và authorization phù hợp.

## 12. OpenApiCustomizer không nhận request như tham số

OpenApiCustomizer là callback dùng để sửa OpenAPI model sau khi Springdoc xây dựng document. Interface customizer nhận OpenAPI object, không nhận trực tiếp HttpServletRequest hoặc ServerWebExchange như một tham số.

Một số ứng dụng Servlet lấy request hiện tại qua RequestContextHolder. Cách này phụ thuộc request context của thread và chỉ phù hợp với mô hình Servlet tương ứng. Không nên giả định nó có thể dùng giống hệt trong WebFlux.

Ví dụ, customizer có thể đọc một request attribute đã được filter tin cậy thiết lập:

~~~java
@Bean
OpenApiCustomizer requestAwareServerCustomizer() {
    return openApi -> {
        RequestAttributes attributes =
            RequestContextHolder.getRequestAttributes();

        if (!(attributes instanceof ServletRequestAttributes servletAttributes)) {
            return;
        }

        HttpServletRequest request = servletAttributes.getRequest();

        String publicBaseUrl =
            (String) request.getAttribute("validatedPublicBaseUrl");

        if (StringUtils.hasText(publicBaseUrl)) {
            openApi.setServers(List.of(
                new Server().url(publicBaseUrl)
            ));
        }
    };
}
~~~

Ví dụ giả định một filter phía trước đã xác minh host, forwarded headers và đặt attribute validatedPublicBaseUrl. Không đọc trực tiếp Host hoặc X-Forwarded-Host chưa được xác thực trong customizer.

Đoạn code này chỉ minh họa cho Servlet. Cần import đúng các lớp Spring và OpenAPI model theo phiên bản dự án.

## 13. Vì sao customizer phụ thuộc request nguy hiểm khi cache bật?

Giả sử customizer ở trên chạy trong lần đầu tải tài liệu:

1. Request A tới api-a.example.com.
2. Filter xác minh host và đặt validatedPublicBaseUrl.
3. Springdoc gọi customizer và ghi server URL api-a.example.com vào OpenAPI model.
4. Springdoc lưu description đã tính vào cache.
5. Request B tới api-b.example.com.
6. Nếu cache entry được dùng lại, customizer có thể không chạy lại; request B nhận document đã chứa server URL của request A.

Điều này xảy ra vì cache giữ kết quả đã tính, trong khi cache key mặc định không được thiết kế để phân biệt mọi host tùy ý.

Nếu document được tạo từ request đầu tiên có quyền hoặc tenant riêng, metadata đó cũng có thể xuất hiện trong response cho request sau. Vì vậy, customizer dùng request context phải được thiết kế cùng chính sách cache, không thể chỉ nhìn riêng code sửa OpenAPI model.

Một nguyên tắc an toàn là customizer mặc định phải deterministic: cùng cấu hình và cùng locale tạo cùng document, không phụ thuộc người dùng hoặc request bất kỳ.

## 14. Cách xử lý khi server URL thực sự phụ thuộc request

Nếu cần tính server URL theo từng request trong ứng dụng Servlet, có thể cân nhắc:

~~~yaml
springdoc:
  cache:
    disabled: true
  pre-loading-enabled: false
~~~

Khi cache tắt, customizer có thể được chạy lại trong quá trình tạo document cho request hiện tại. Preload được tắt vì quá trình startup không có request cụ thể để xác định public URL.

Trước khi áp dụng, cần xác minh:

- Request context tồn tại tại thời điểm Springdoc tạo document.
- Forwarded headers chỉ đến từ proxy đáng tin.
- Host nằm trong allowlist.
- Scheme và prefix phản ánh URL public thực tế.
- Customizer không đọc thông tin xác thực để thay đổi document theo user.
- Việc dựng lại document trên mỗi request đáp ứng tải dự kiến.

Nếu chỉ cần server URL cố định theo môi trường, hãy dùng OpenAPI bean hoặc cấu hình profile tĩnh và giữ cache bật. Đây thường là cách đơn giản và hiệu quả hơn.

Tắt cache không thay thế việc xác thực forwarded headers. Nó chỉ làm document được tính lại; dữ liệu request không đáng tin vẫn không được dùng làm metadata.

## 15. Phân biệt request context của Servlet và WebFlux

Trong Servlet, RequestContextHolder có thể cung cấp RequestAttributes gắn với thread hiện tại khi request context được thiết lập.

Trong WebFlux, xử lý request dựa trên reactive pipeline và Reactor Context. Request không được bảo đảm chạy trên cùng một thread. Vì vậy, cách đọc ThreadLocal/RequestContextHolder không phải mô hình tổng quát để lấy ServerWebExchange.

OpenApiCustomizer là callback đồng bộ nhận OpenAPI model. Không nên cố lấy reactive request bằng ThreadLocal hoặc giả định customizer sẽ có ServerWebExchange.

Nếu WebFlux cần document phụ thuộc request, hãy ưu tiên:

- Dùng server URL tĩnh hoặc relative URL.
- Tách document theo cấu hình/deployment rõ ràng.
- Dùng một endpoint tích hợp riêng có kiểm soát nếu thật sự cần request-specific output.
- Thiết kế cache key và authorization rõ ràng thay vì dùng cache mặc định theo locale cho dữ liệu tenant.

Không sao chép ví dụ Servlet dùng RequestContextHolder vào ứng dụng WebFlux mà không có thiết kế reactive phù hợp.

## 16. Customizer nên deterministic và không tạo side effect

Customizer có thể được gọi khi document được tạo lần đầu, khi cache entry bị loại, khi cache bị tắt hoặc khi instance khởi động preload. Vì vậy, customizer nên có các đặc tính:

- Không gọi database chỉ để bổ sung mô tả.
- Không gọi HTTP service ngoài nếu có thể lấy cấu hình từ startup.
- Không phát sinh side effect nghiệp vụ.
- Không lưu request data vào field của singleton bean.
- Không sửa một OpenAPI model dùng chung sau khi document đã được công bố.
- Có thể chạy lại mà không tạo tag, schema hoặc extension trùng lặp.
- Dùng dữ liệu cấu hình ổn định và đã được kiểm tra.

Ví dụ không nên:

~~~java
@Bean
OpenApiCustomizer slowCustomizer(ProductRepository repository) {
    return openApi -> {
        long count = repository.count();
        openApi.addExtension("x-product-count", count);
    };
}
~~~

Đoạn code này buộc quá trình tạo document phụ thuộc database. Nếu cache tắt, truy vấn có thể chạy mỗi lần tải tài liệu. Nếu preload bật, truy vấn có thể chạy trong startup và làm readiness chậm.

Nếu số liệu cần hiển thị là dữ liệu runtime thay đổi liên tục, OpenAPI document thường không phải nơi phù hợp. Hãy dùng endpoint metrics/status hoặc tài liệu vận hành riêng.

## 17. Lựa chọn kiến trúc cho từng nhu cầu

| Nhu cầu | Cách phù hợp | Cache |
|---|---|---|
| Một public base URL cố định theo môi trường | OpenAPI bean hoặc profile configuration | Bật |
| Tài liệu đa ngôn ngữ | Cấu hình locale, preload locale cần dùng | Bật, giới hạn entries |
| Nhiều proxy nhưng cùng public URL | Cấu hình forwarded headers và server URL ổn định | Bật |
| Một UI được truy cập qua nhiều public host, server URL phải theo request | Customizer request-aware có kiểm soát | Có thể tắt |
| Tài liệu riêng cho tenant | Document/deployment riêng hoặc cơ chế partition rõ ràng | Không dùng cache mặc định nếu key không chứa tenant |
| Metadata thay đổi theo user/role | Tách tài liệu theo audience hoặc thiết kế authorization rõ ràng | Tránh cache dùng chung theo locale |
| API lớn, docs ít thay đổi | Cache mặc định và preload nếu cần | Bật |
| Phát triển local cần quan sát customizer mỗi lần | Tạm tắt cache | Tắt trong môi trường dev |

Đừng chọn cache disabled chỉ vì một request đầu tiên chậm. Hãy xác định liệu document có thật sự phụ thuộc request hay chỉ cần preload để cải thiện trải nghiệm.

## 18. Đo chi phí lần đầu và các lần đọc sau

Để đo đúng, cần phân biệt cold generation với warm retrieval.

Một quy trình kiểm tra:

1. Khởi động một instance mới với cache bật và preload tắt.
2. Chờ ứng dụng ready.
3. Gửi request đầu tiên tới /v3/api-docs.
4. Gửi tiếp nhiều request cùng locale.
5. Ghi lại latency, CPU và allocation cho từng nhóm.
6. Khởi động instance mới và lặp lại với preload bật.
7. Lặp lại với cache disabled nếu cần so sánh.
8. Thử locale thứ hai để quan sát cache entry riêng.
9. Thử nhiều replica để quan sát cold cache theo từng instance.

Không dùng một lần đo duy nhất. Chạy nhiều vòng, loại bỏ ảnh hưởng khởi động JVM/JIT nếu mục tiêu là so sánh steady-state, và báo p50/p95/p99 thay vì chỉ báo trung bình.

Không đặt ngưỡng latency cứng trong unit test thông thường vì thời gian phụ thuộc máy chạy CI. Dùng benchmark hoặc performance test riêng với môi trường ổn định.

## 19. Theo dõi hiệu năng bằng công cụ phù hợp

Có thể dùng các công cụ chung của Spring Boot/JVM để quan sát:

- HTTP server request metrics để đo latency của endpoint docs.
- Access log hoặc reverse proxy log để tách request đầu và request sau.
- Java Flight Recorder để xem CPU, allocation và hotspot.
- Java Mission Control hoặc profiler tương đương để phân tích call stack.
- Container metrics để xem CPU, heap và thời gian startup.
- Startup/readiness logs để đo ảnh hưởng của preload.

Không giả định Springdoc cung cấp sẵn metric riêng cho số cache hit/miss nếu phiên bản đang dùng không công bố metric đó. Nếu cần cache hit ratio, phải có instrumentation phù hợp hoặc kiểm tra bằng profiling; không suy luận chỉ từ latency.

Khi benchmark, giữ cùng artifact, profile, locale, request headers, proxy route và kích thước response. Nếu thay đổi nhiều biến cùng lúc, khó biết cải thiện đến từ cache hay cấu hình khác.

## 20. Kiểm thử cache và request-dependent customizer

Cần có test xác minh cả hai trường hợp.

**Trường hợp cache bật:**

- Request A tạo document với locale vi.
- Request B cùng locale phải nhận cùng contract metadata ổn định.
- Nếu host khác nhau, document không được vô tình mang server URL theo host A khi thiết kế yêu cầu một URL cố định.
- Request locale en tạo document tiếng Anh riêng.
- Các locale không vượt giới hạn cache đã cấu hình.

**Trường hợp cache tắt:**

- Hai request có public host hợp lệ khác nhau phải nhận server URL tương ứng nếu kiến trúc yêu cầu.
- Header host giả mạo phải bị proxy/filter từ chối hoặc ghi đè.
- Request không có trusted public URL phải dùng fallback an toàn hoặc không thêm server động.
- Customizer không truy cập tenant/user data ngoài phạm vi được phép.

Có thể dùng MockMvc cho Servlet và WebTestClient cho WebFlux để kiểm tra endpoint. Tuy nhiên, test mock request không chứng minh proxy thật đã làm sạch header. Với forwarded headers, cần integration test qua ingress/reverse proxy hoặc test hạ tầng tương ứng.

## 21. Ví dụ cấu hình theo môi trường

Một cấu hình production với server URL cố định và cache bật:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 20
  pre-loading-enabled: true
  pre-loading-locales:
    - vi
    - en

app:
  api:
    public-url: https://api.example.com
~~~

OpenAPI bean dùng giá trị cấu hình:

~~~java
@Bean
OpenAPI apiOpenAPI(ApiProperties properties) {
    return new OpenAPI()
        .servers(List.of(
            new Server()
                .url(properties.publicUrl())
                .description("Public API")
        ));
}
~~~

Với cách này, document không phụ thuộc request đầu tiên. Preload tạo các locale cần thiết khi startup; cache phục vụ các request sau.

Nếu public URL thực sự thay đổi theo request và đã có filter tin cậy thiết lập request attribute, cấu hình có thể chuyển sang:

~~~yaml
springdoc:
  cache:
    disabled: true
  pre-loading-enabled: false
~~~

Chỉ dùng cấu hình thứ hai khi đã chấp nhận chi phí dựng lại document và đã bảo vệ nguồn dữ liệu request. Không bật đồng thời preload và customizer yêu cầu request context mà không có fallback rõ ràng.

## 22. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Request đầu tải docs chậm, request sau nhanh | Chi phí tạo OpenAPI description lần đầu |
| Mỗi pod có latency docs khác nhau sau deploy | Cache trong từng instance được warm ở thời điểm khác nhau |
| Server URL của host A xuất hiện khi truy cập host B | Customizer request-dependent đã tạo document được cache |
| Tenant A thấy metadata của tenant B | Cache mặc định không phân vùng theo tenant |
| Tắt cache làm CPU tăng | Mỗi request phải dựng lại description |
| Startup chậm sau khi bật preload | Chi phí tạo document chuyển sang startup |
| Locale thứ hai chậm hơn locale đầu | Cache entry cho locale đó chưa được tạo |
| Cache liên tục bị loại | Số locale vượt max-entries hoặc giới hạn quá thấp |
| Customizer chạy nhưng không có request | Preload hoặc quá trình tạo document không gắn với HTTP request |
| RequestContextHolder null | Không có Servlet request context ở thời điểm customizer chạy |
| WebFlux không lấy được request từ ThreadLocal | Reactive context không được bảo đảm gắn với thread |
| Swagger UI hiển thị URL nội bộ | Server URL hoặc forwarded headers chưa được cấu hình đúng |
| Tắt cache nhưng host giả vẫn được dùng | Chưa xác minh nguồn Host/X-Forwarded-* |
| Customizer làm docs chậm bất thường | Truy vấn database, HTTP hoặc tính toán nặng trong customizer |

Khi điều tra, so sánh document JSON của request đầu tiên và request sau, kiểm tra locale, host, profile và trạng thái cache. Đừng chỉ nhìn thời gian response mà bỏ qua nội dung document được tái sử dụng.

## 23. Nguyên tắc thiết kế cache và customizer

Khi dùng Springdoc cache cùng customizer:

1. Hiểu cache giữ OpenAPI description đã tính, không mặc định là HTTP response bytes.
2. Xem cache là trạng thái trong từng instance; mỗi pod có cache riêng.
3. Mặc định giữ cache bật cho document ổn định.
4. Dùng springdoc.cache.max-entries để giới hạn số locale entries ở phiên bản hỗ trợ.
5. Dùng preload để chuyển chi phí tạo document sang startup khi phù hợp.
6. Không giả định cache key mặc định phân biệt host, tenant, user hoặc arbitrary headers.
7. Ưu tiên customizer deterministic và không phụ thuộc request.
8. Không lưu request data trong field của singleton customizer.
9. Chỉ tắt cache khi document thật sự phải được tính theo từng request.
10. Nếu tắt cache, đánh giá lại CPU, latency và tải do Swagger UI/monitoring.
11. Không dựa vào RequestContextHolder trong WebFlux.
12. Không preload document cần request context nếu chưa có fallback.
13. Xác minh forwarded headers từ proxy tin cậy trước khi dùng chúng để tạo server URL.
14. Kiểm thử nội dung document giữa host, locale, tenant và instance khác nhau.
15. Đo cold generation, warm request và startup riêng biệt.

Cache giúp tránh dựng lại một hợp đồng ổn định. Request-dependent customizer lại yêu cầu kết quả thay đổi theo ngữ cảnh hiện tại. Khi hai cơ chế này được kết hợp mà không có quy tắc phân vùng rõ ràng, document có thể sai hoặc làm lộ metadata giữa các request. Hãy giữ document ổn định và cache bật khi có thể; chỉ tính lại theo request khi thật sự cần, với nguồn request đã xác minh và chi phí được đo lường.

## 24. Tài liệu tham khảo chính thức

- [Springdoc FAQ – Cache và server URL](https://springdoc.org/faq.html)
- [Springdoc Configuration Properties](https://springdoc.org/properties.html)
- [Springdoc OpenAPI v2 Documentation](https://springdoc.org/v2/)


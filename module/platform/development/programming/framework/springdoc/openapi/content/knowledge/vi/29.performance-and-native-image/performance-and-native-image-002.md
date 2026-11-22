# Chi phí xây dựng tài liệu lần đầu và các lần đọc sau

Springdoc không chỉ phục vụ một file OpenAPI tĩnh. Từ controller, DTO, annotation, cấu hình Spring và Jackson, thư viện phải xây dựng một OpenAPI model rồi mới trả JSON/YAML cho client. Công việc xây dựng này có thể tốn thời gian khi ứng dụng có nhiều endpoint, schema lồng nhau, nhiều group hoặc customizer phức tạp.

Trong cấu hình mặc định, Springdoc tính OpenAPI description rồi cache kết quả. Vì vậy, lần tạo đầu tiên thường tốn chi phí lớn hơn các lần đọc tiếp theo. Những request sau vẫn cần xử lý HTTP và serialize response, nhưng có thể dùng lại OpenAPI model đã tính thay vì phân tích lại toàn bộ controller và schema.

## 1. Hai giai đoạn: cold generation và warm read

Có thể hình dung vòng đời tài liệu như sau:

~~~text
Ứng dụng khởi động
       |
       v
Spring Boot đăng ký controller, bean và mapping
       |
       v
Client yêu cầu OpenAPI lần đầu
       |
       v
Springdoc phân tích endpoint, annotation, DTO và schema
       |
       v
OpenApiCustomizer / OperationCustomizer hoàn thiện model
       |
       v
OpenAPI model được cache
       |
       v
Các request tiếp theo lấy model từ cache
       |
       v
Serialize JSON/YAML và gửi response
~~~

Hai giai đoạn có đặc điểm khác nhau:

| Giai đoạn | Công việc chính | Chi phí thường thấy |
| --- | --- | --- |
| Cold generation | Phân tích mapping, annotation, generic type, DTO, validation, Jackson và customizer | CPU, reflection, cấp phát object và độ trễ cao hơn |
| Warm read | Lấy OpenAPI model đã cache, serialize response và truyền qua HTTP | Thấp hơn, nhưng vẫn có chi phí serialize, bảo mật và network |

Không nên xem warm read là thao tác miễn phí. Một tài liệu có hàng nghìn operation hoặc schema lớn vẫn tạo response đáng kể, cần serialize và truyền qua mạng ở mỗi lần tải.

## 2. Springdoc xây dựng tài liệu lần đầu như thế nào?

Khi tài liệu được yêu cầu và chưa có bản cache phù hợp, Springdoc phải thu thập thông tin từ ứng dụng:

1. Đọc handler mapping và xác định controller/operation phù hợp.
2. Phân tích annotation như @Operation, @Parameter, @ApiResponse, @Schema và @SecurityRequirement.
3. Giải quyết kiểu dữ liệu, generic, DTO lồng nhau, collection, enum và quan hệ schema.
4. Đọc metadata từ Jackson, Bean Validation và các model converter được bật.
5. Áp dụng OperationCustomizer, OpenApiCustomizer và cấu hình group.
6. Hoàn thiện OpenAPI model trước khi serialize thành JSON/YAML.

Ứng dụng càng nhiều endpoint và schema phức tạp, số lượng metadata cần phân tích càng lớn. Các customizer có thêm xử lý nghiệp vụ hoặc gọi dịch vụ bên ngoài cũng làm tăng thời gian xây dựng.

Với cấu hình lazy thông thường, request đầu tiên đến endpoint OpenAPI có thể là nơi người dùng cảm nhận chi phí này. Nếu bật preloading, công việc được chuyển sang giai đoạn khởi động ứng dụng.

## 3. Các request sau dùng cache như thế nào?

Theo cấu hình mặc định, Springdoc tính OpenAPI description một lần rồi cache kết quả. Khi client yêu cầu cùng tài liệu và cùng locale đã được tính, Springdoc có thể dùng lại model đã cache.

Ví dụ:

~~~text
GET /v3/api-docs
    -> Tính OpenAPI model và lưu cache

GET /v3/api-docs
    -> Dùng model đã cache

GET /v3/api-docs
    -> Dùng model đã cache
~~~

Cache giúp tránh lặp lại công việc phân tích controller, annotation và schema ở mỗi request. Tuy vậy, mỗi response vẫn cần đi qua HTTP stack và có thể phải serialize OpenAPI model thành JSON/YAML.

Swagger UI thường tải nhiều tài nguyên như trang giao diện, swagger-config và OpenAPI document. Nếu người dùng mở lại giao diện, request document vẫn có thể phát sinh; cache phía Springdoc giảm chi phí tạo model ở backend nhưng không thay thế cache HTTP, browser hoặc CDN.

## 4. Cấu hình cache mặc định

Các thuộc tính cache thường dùng:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 100
~~~

Ý nghĩa:

| Thuộc tính | Giá trị mặc định | Vai trò |
| --- | --- | --- |
| springdoc.cache.disabled | false | Cache OpenAPI description được bật |
| springdoc.cache.max-entries | 100 từ Springdoc 2.9.1 | Giới hạn số description cache theo locale |

Khi cache bật, Springdoc có thể phục vụ lại tài liệu đã tính. Từ Springdoc 2.9.1, số description cache được giới hạn; khi vượt giới hạn, entry ít được sử dụng gần đây nhất có thể bị loại bỏ theo chính sách LRU.

Thuộc tính max-entries cần được kiểm tra theo phiên bản Springdoc đang dùng. Nếu dự án chạy bản 2.x cũ hơn 2.9.1, đừng giả định property này đã tồn tại hoặc có cùng hành vi.

## 5. Cache theo locale và Accept-Language

Springdoc hỗ trợ nội dung tài liệu theo locale. Request có thể mang header Accept-Language để chọn ngôn ngữ mô tả:

~~~http
GET /v3/api-docs
Accept-Language: vi
~~~

Một request khác có thể yêu cầu tiếng Anh:

~~~http
GET /v3/api-docs
Accept-Language: en
~~~

Springdoc cache description theo locale được yêu cầu. Do đó, ứng dụng có nhiều ngôn ngữ có thể tạo nhiều bản OpenAPI model khác nhau. Khi giới hạn cache, cần cân nhắc số locale mà client thực sự sử dụng.

Nếu chỉ phục vụ một ngôn ngữ, không cần cấu hình preload nhiều locale. Nếu hỗ trợ nhiều locale, kiểm tra số lượng cache entry và bộ nhớ sau khi các ngôn ngữ được truy cập.

## 6. Giới hạn số entry cache

Ví dụ cấu hình:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 20
~~~

Giảm max-entries giúp giới hạn số OpenAPI description được giữ trong cache, nhưng có thể khiến locale ít dùng bị loại bỏ và phải tính lại khi được yêu cầu lần sau. Tăng giới hạn có thể giảm số lần tính lại, đổi lại cần thêm bộ nhớ.

Không nên tăng max-entries chỉ vì thấy cache miss. Trước tiên hãy xác định ứng dụng có bao nhiêu locale, có nhiều tài liệu group hay không và các request thực tế phân bố ra sao.

## 7. Preloading: chuyển chi phí sang lúc khởi động

Nếu không muốn người dùng đầu tiên phải chờ Springdoc xây dựng tài liệu, có thể bật preloading:

~~~yaml
springdoc:
  pre-loading-enabled: true
~~~

Preloading yêu cầu Springdoc tải OpenAPI khi ứng dụng khởi động. Nhờ vậy, tài liệu có thể sẵn sàng trước khi client gửi request đầu tiên.

Preloading thay đổi thời điểm phát sinh chi phí:

| Không preload | Có preload |
| --- | --- |
| Khởi động nhẹ hơn ở phần tạo tài liệu | Khởi động tốn thêm thời gian và CPU để tạo tài liệu |
| Request OpenAPI đầu tiên có thể chậm | Request OpenAPI đầu tiên thường tránh được cold generation |
| Tài liệu được tạo khi có nhu cầu | Tài liệu được tạo sớm ngay khi ứng dụng khởi động |

Preloading không loại bỏ chi phí xây dựng OpenAPI. Nó chỉ chuyển chi phí từ request đầu tiên sang startup. Nếu tài liệu lớn, cần đo thời gian startup và readiness trước khi bật trên mọi instance.

## 8. Preload nhiều locale

Có thể chỉ định danh sách locale cần tải khi khởi động:

~~~yaml
springdoc:
  pre-loading-enabled: true
  pre-loading-locales:
    - vi
    - en
~~~

Nếu không chỉ định pre-loading-locales, Springdoc preload theo locale mặc định. Danh sách locale nên giới hạn ở những ngôn ngữ mà ứng dụng thực sự công bố.

Preload nhiều locale có thể làm startup lâu hơn và sử dụng thêm CPU/bộ nhớ ban đầu vì phải chuẩn bị nhiều phiên bản nội dung. Hãy đo với số locale thật của hệ thống, không thêm ngôn ngữ dự phòng nếu không có client sử dụng.

## 9. Nhiều GroupedOpenApi làm tăng số tài liệu cần chuẩn bị

Một ứng dụng có thể tạo nhiều group như public, partner và internal:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .build();
}

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .build();
}
~~~

Mỗi group có tập operation và schema cần mô tả riêng. Khi số group tăng, chi phí xây dựng tài liệu và kích thước cache có thể tăng theo. Nếu mỗi group còn hỗ trợ nhiều locale, số biến thể tài liệu cần được tính đến khi đo hiệu năng.

Chỉ tạo group khi chúng có mục tiêu rõ ràng như phân tách audience, bảo mật hoặc vòng đời API. Không chia tài liệu thành quá nhiều group nhỏ nếu chúng chỉ khác nhau ở vài tag mà không có nhu cầu sử dụng thực tế.

## 10. Khi nào nên tắt cache?

Có thể tắt cache bằng:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Khi cache bị tắt, Springdoc tính lại OpenAPI description thay vì dùng bản cache đã tính. Điều này có thể hữu ích khi server URL hoặc nội dung cần được tính theo từng HTTP request, ví dụ cùng một Swagger UI được phục vụ qua nhiều proxy nội bộ và bên ngoài với host/scheme khác nhau.

Tắt cache làm tăng CPU và độ trễ của mỗi request tài liệu, đặc biệt khi OpenAPI có nhiều operation/schema hoặc customizer nặng. Không bật chỉ để sửa URL proxy nếu có thể cấu hình forwarded headers hoặc server URL rõ ràng hơn.

Hãy cân nhắc:

- Dùng server URL tường minh qua @OpenAPIDefinition nếu hợp đồng có địa chỉ cố định.
- Cấu hình reverse proxy và forwarded headers chính xác nếu URL phụ thuộc host/scheme public.
- Dùng cache mặc định nếu tài liệu ổn định trong suốt vòng đời ứng dụng.
- Chỉ tắt cache khi thực sự cần kết quả khác nhau theo từng request.

## 11. Customizer có thể làm tăng chi phí cold generation

OperationCustomizer và OpenApiCustomizer rất hữu ích để bổ sung metadata, nhưng logic bên trong cũng nằm trên đường tạo tài liệu.

Ví dụ một customizer không nên gọi database hoặc dịch vụ bên ngoài cho từng operation:

~~~java
@Bean
OpenApiCustomizer apiCustomizer() {
    return openApi -> {
        // Chỉ sửa metadata trong OpenAPI model.
        openApi.getInfo().setDescription("Public API documentation");
    };
}
~~~

Nên giữ customizer:

- Có kết quả xác định với cùng cấu hình.
- Không gọi HTTP hoặc database nếu không cần.
- Không quét classpath hoặc đọc file lớn lặp lại.
- Không tạo object trung gian quá lớn cho mỗi operation.
- Chỉ sửa những phần metadata thực sự cần thiết.

Nếu phải đọc cấu hình hoặc danh mục tĩnh, hãy nạp chúng một lần vào bean phù hợp rồi dùng lại. Nếu customizer cần dữ liệu động theo request, hãy đánh giá tác động đến cache và xác định rõ dữ liệu đó có thực sự thuộc hợp đồng OpenAPI hay không.

## 12. Kích thước schema và phạm vi scan

Tài liệu lớn thường có chi phí tạo và serialize cao hơn. Một số yếu tố thường làm tăng kích thước:

- Nhiều controller và operation được đưa vào tài liệu.
- DTO có nhiều property, generic hoặc quan hệ lồng nhau.
- Schema đa hình, oneOf/anyOf/allOf và tham chiếu đệ quy.
- Nhiều example hoặc description dài.
- Nhiều response status code và media type.
- Nhiều customizer bổ sung extension hoặc schema.

Có thể giới hạn phạm vi scan bằng cấu hình:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.api
  paths-to-match:
    - /api/**
  packages-to-exclude:
    - com.example.internal
  paths-to-exclude:
    - /internal/**
~~~

Giới hạn scan có thể giảm số operation cần xử lý và làm tài liệu gọn hơn. Tuy nhiên, chỉ loại những endpoint không thuộc hợp đồng cần công bố; không dùng filter để che endpoint nhạy cảm thay cho bảo mật runtime.

## 13. Phân biệt cache OpenAPI với cache HTTP

Springdoc cache OpenAPI model đã tính. Đây là cache phía ứng dụng, không đồng nghĩa với HTTP response cache.

| Lớp cache | Lưu nội dung gì? | Tác động |
| --- | --- | --- |
| Springdoc cache | OpenAPI description đã tính | Tránh phân tích lại controller/schema |
| HTTP/browser cache | Response JSON/YAML hoặc tài nguyên Swagger UI | Có thể giảm request đến backend |
| Reverse proxy/CDN cache | Response được proxy lưu theo cache policy | Có thể giảm tải backend và network |

Không tự động bật CDN cache cho tài liệu có nội dung phụ thuộc xác thực, locale hoặc request context. Nếu cache HTTP, cần xác định cache key, Vary header và chính sách quyền truy cập để tránh trả tài liệu sai audience/ngôn ngữ.

Ngay cả khi Springdoc cache hit, backend vẫn có thể phải serialize OpenAPI model và gửi response nếu HTTP cache không phục vụ được request.

## 14. Đo chi phí cold và warm

Để đánh giá đúng, cần đo riêng startup, request đầu tiên và các request lặp lại:

1. Khởi động ứng dụng mới và ghi thời điểm ứng dụng sẵn sàng.
2. Gửi request đầu tiên đến /v3/api-docs.
3. Gửi lại cùng request nhiều lần để quan sát warm read.
4. Thử từng group và locale được hỗ trợ.
5. So sánh cache bật/tắt và preload bật/tắt trong môi trường tương đương.
6. Ghi nhận CPU, heap, allocation, kích thước response và độ trễ.

Ví dụ đo thời gian request bằng curl:

~~~bash
curl -sS -o /dev/null -w "first: %{time_total}s\n" \
  http://localhost:8080/v3/api-docs

curl -sS -o /dev/null -w "warm: %{time_total}s\n" \
  http://localhost:8080/v3/api-docs

curl -sS -o /dev/null -w "warm: %{time_total}s\n" \
  http://localhost:8080/v3/api-docs
~~~

Lệnh đầu là request đầu tiên trong tiến trình đang chạy; hai lệnh sau giúp quan sát warm read. Kết quả curl bao gồm cả network và HTTP stack, vì vậy hãy chạy nhiều lần và dùng median hoặc percentile thay vì kết luận từ một mẫu.

## 15. Đo nhiều group và locale

Nếu có nhiều tài liệu, hãy đo riêng từng URL:

~~~bash
curl -sS -o /dev/null -w "default: %{time_total}s\n" \
  http://localhost:8080/v3/api-docs

curl -sS -o /dev/null -w "partner: %{time_total}s\n" \
  http://localhost:8080/v3/api-docs/partner

curl -sS -H "Accept-Language: vi" -o /dev/null \
  -w "vi: %{time_total}s\n" http://localhost:8080/v3/api-docs

curl -sS -H "Accept-Language: en" -o /dev/null \
  -w "en: %{time_total}s\n" http://localhost:8080/v3/api-docs
~~~

Khi đo locale, request phải thật sự tạo ra locale khác theo cấu hình i18n của ứng dụng. Nếu hai locale trả cùng một nội dung, không nên kết luận đã kiểm tra được chi phí dịch thuật hoặc cache riêng.

## 16. Theo dõi CPU, memory và thời gian startup

Độ trễ request không phải chỉ số duy nhất. Khi bật preload hoặc có nhiều group/locale, hãy theo dõi:

- Thời gian từ khi process bắt đầu đến khi readiness probe thành công.
- CPU trong giai đoạn Springdoc xây dựng tài liệu.
- Heap trước và sau khi OpenAPI model được tạo.
- Garbage collection và allocation rate.
- Kích thước JSON/YAML được trả về.
- p50, p95 và p99 của request tài liệu.

Java Flight Recorder có thể giúp xác định thời gian dành cho reflection, schema resolution, serialization và customizer. Spring Boot Actuator/Micrometer có thể cung cấp các chỉ số process/JVM/HTTP phù hợp nếu ứng dụng đã bật monitoring.

Không nên chỉ so sánh thời gian startup tổng thể giữa hai bản build. Cần tách thời gian khởi tạo Spring context, thời gian preload OpenAPI và thời gian readiness để biết phần nào thực sự tăng.

## 17. Chọn cấu hình theo mục tiêu vận hành

| Mục tiêu | Cấu hình gợi ý | Đánh đổi |
| --- | --- | --- |
| Tài liệu ổn định, đọc thường xuyên | Cache mặc định | Lần tạo đầu tiên có thể chậm |
| Muốn request đầu tiên nhanh hơn | pre-loading-enabled = true | Startup lâu hơn |
| Hỗ trợ nhiều locale ngay khi ứng dụng sẵn sàng | Preload các locale được dùng | Tăng chi phí startup và bộ nhớ |
| URL tài liệu phụ thuộc từng request | Cân nhắc cache.disabled = true | Mỗi request có thể phải tính lại |
| Không cần công bố tài liệu trong môi trường | api-docs.enabled = false | Endpoint OpenAPI không còn được cung cấp |

Ví dụ cấu hình production cho tài liệu ổn định:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 100
  pre-loading-enabled: true
  pre-loading-locales:
    - vi
    - en
~~~

Ví dụ cấu hình phát triển khi cần quan sát thay đổi metadata thường xuyên:

~~~yaml
springdoc:
  cache:
    disabled: true
  pre-loading-enabled: false
~~~

Không nên sao chép hai cấu hình này cho mọi môi trường. Hãy chọn theo độ ổn định của tài liệu, số locale, số group và yêu cầu về thời gian startup/request.

## 18. Khi nào nên tắt endpoint tài liệu?

Nếu môi trường production không cần phục vụ OpenAPI, có thể tắt endpoint:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Tắt Swagger UI riêng không đồng nghĩa OpenAPI JSON/YAML cũng bị tắt. Nếu mục tiêu là không cung cấp tài liệu, cần cấu hình api-docs.enabled phù hợp. Nếu pipeline CI vẫn cần đặc tả, hãy tạo tài liệu trong bước build/test hoặc dùng một môi trường chuyên dụng thay vì tắt endpoint ở nơi pipeline cần truy cập.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Request OpenAPI đầu tiên chậm | Cold generation chưa có cache | Đo cold path và cân nhắc preloading |
| Các request sau vẫn chậm | Cache bị tắt, locale thay đổi hoặc cache miss | Kiểm tra cache.disabled, Accept-Language và max-entries |
| Startup tăng sau khi bật preload | Tài liệu được tạo trong giai đoạn khởi động | Đo thời gian preload và readiness |
| Heap tăng khi hỗ trợ nhiều locale | Nhiều description được cache | Giới hạn locale và điều chỉnh max-entries |
| Một group chậm hơn group khác | Group có nhiều operation/schema hoặc customizer riêng | Đo từng group và giảm phạm vi scan phù hợp |
| Tắt cache làm CPU tăng | Mỗi request phải tính lại OpenAPI | Chỉ tắt khi cần dữ liệu theo request |
| Customizer làm cold generation kéo dài | Gọi DB/HTTP hoặc xử lý nặng khi tạo model | Loại I/O không cần thiết và tái sử dụng dữ liệu tĩnh |
| Preload xong nhưng UI vẫn chậm | Thời gian tải asset, serialize response hoặc network | Đo swagger-config, document và static resources riêng |
| URL server cần thay đổi theo proxy nhưng cache giữ URL cũ | Server URL được tính theo request nhưng model đã cache | Cấu hình forwarded headers/server URL hoặc cân nhắc tắt cache |
| Cache max-entries không có tác dụng | Phiên bản Springdoc chưa hỗ trợ thuộc tính | Kiểm tra version; max-entries được giới thiệu từ 2.9.1 |

## 20. Checklist đo và tối ưu

- [ ] Đã đo startup và readiness trước khi bật preloading.
- [ ] Đã đo request OpenAPI đầu tiên trong tiến trình mới.
- [ ] Đã đo warm read nhiều lần với cùng URL.
- [ ] Đã đo riêng từng group và locale.
- [ ] Đã xác nhận cache.disabled đang dùng giá trị mong muốn.
- [ ] Đã kiểm tra cache.max-entries theo version Springdoc.
- [ ] Đã chọn pre-loading-locales theo ngôn ngữ thực sự sử dụng.
- [ ] Customizer không gọi database/HTTP hoặc xử lý nặng không cần thiết.
- [ ] packages-to-scan và paths-to-match chỉ bao gồm API cần tài liệu hóa.
- [ ] Đã theo dõi CPU, heap, allocation, response size và latency percentile.
- [ ] Đã phân biệt Springdoc model cache với HTTP/browser/CDN cache.
- [ ] Đã xác minh Swagger UI, swagger-config và OpenAPI document sau khi đổi cấu hình.

Chi phí xây dựng OpenAPI thường tập trung ở lần tính đầu tiên; các request sau có thể dùng lại model đã cache nhưng vẫn cần serialize và truyền response. Cache mặc định phù hợp với tài liệu ổn định, còn preloading chuyển cold generation sang startup. Tắt cache chỉ nên dùng khi tài liệu cần thay đổi theo từng request và nhóm đã chấp nhận chi phí CPU/latency tăng lên. Đo riêng startup, cold request, warm read, từng group và locale giúp chọn cấu hình dựa trên dữ liệu thực tế.

## Tài liệu tham khảo

- [Springdoc OpenAPI v2 — Core properties](https://springdoc.org/v2/core-properties.html)
- [Springdoc OpenAPI v2 — FAQ: OpenAPI cache](https://springdoc.org/v2/faq.html)

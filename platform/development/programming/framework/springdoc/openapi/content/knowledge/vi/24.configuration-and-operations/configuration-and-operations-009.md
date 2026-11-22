# Nạp trước, bộ nhớ đệm và thời điểm cập nhật tài liệu

springdoc-openapi tạo đặc tả OpenAPI từ controller, model, annotation và cấu hình của ứng dụng. Việc phân tích này có thể tốn thời gian khi hệ thống có nhiều endpoint, schema lồng nhau, customizer hoặc nhiều nhóm tài liệu. Nếu tài liệu chỉ được tạo khi có request đầu tiên, người dùng có thể phải chờ lâu ở lần mở Swagger UI đầu tiên sau khi ứng dụng khởi động.

springdoc cung cấp hai cơ chế liên quan: **preloading** để nạp tài liệu trong lúc ứng dụng khởi động và **cache** để giữ kết quả OpenAPI đã tính toán cho những request sau. Cần hiểu rõ hai cơ chế này, vì chúng ảnh hưởng tới thời điểm phát sinh chi phí tạo tài liệu, bộ nhớ sử dụng, nội dung theo locale và khả năng phản ánh thông tin phụ thuộc request.

Bài này trình bày cách bật preloading, chọn locale, quản lý cache, xử lý tài liệu thay đổi theo request hoặc proxy, và kiểm tra hành vi bằng endpoint OpenAPI cùng test tích hợp.

## 1. Vì sao cần preloading và cache?

Quá trình tạo OpenAPI có thể gồm:

1. Quét các controller và mapping của Spring.
2. Phân tích annotation như @Operation, @Parameter, @Schema và @ApiResponse.
3. Phân giải kiểu request/response và generic type.
4. Xây dựng components, schemas, security schemes và references.
5. Áp dụng OpenApiCustomizer, OperationCustomizer hoặc cấu hình theo group.
6. Tạo document cuối cùng để trả về dưới dạng JSON hoặc YAML.

Nếu ứng dụng chỉ tính toán document khi có request đầu tiên tới /v3/api-docs, request đó có thể chịu toàn bộ chi phí khởi tạo. Cache giúp giữ lại kết quả đã tính để các request tiếp theo không phải tạo lại tài liệu theo cùng điều kiện.

Preloading chuyển một phần công việc tạo document sang giai đoạn khởi động ứng dụng. Khi người dùng mở tài liệu sau khi ứng dụng đã sẵn sàng, document có thể đã được nạp trước.

Hai cơ chế giải quyết hai thời điểm khác nhau:

| Cơ chế | Tác dụng chính | Đánh đổi |
|---|---|---|
| Preloading | Tạo OpenAPI trong quá trình startup | Startup có thể lâu hơn |
| Cache | Tái sử dụng document đã tính | Dùng bộ nhớ và có thể giữ nội dung cũ nếu đầu vào thay đổi lúc runtime |
| Tắt cache | Tính lại document theo request | Tăng CPU và độ trễ mỗi lần tải |
| Preloading nhiều locale | Chuẩn bị document cho nhiều ngôn ngữ | Tăng thời gian khởi động và lượng dữ liệu được giữ |

Không nên bật tất cả tùy chọn chỉ vì chúng có sẵn. Hãy dựa vào số lượng endpoint, số locale, số group và việc server URL hoặc metadata có phụ thuộc request hay không.

## 2. Bật preloading khi ứng dụng khởi động

Thuộc tính springdoc.pre-loading-enabled điều khiển việc nạp trước OpenAPI document. Giá trị mặc định là false.

application.yml:

~~~yaml
springdoc:
  pre-loading-enabled: true
~~~

Hoặc application.properties:

~~~properties
springdoc.pre-loading-enabled=true
~~~

Khi bật, springdoc nạp OpenAPI trong quá trình ứng dụng khởi động thay vì chờ lần truy cập tài liệu đầu tiên. Điều này hữu ích khi:

- API có nhiều controller hoặc schema phức tạp.
- Swagger UI được mở ngay sau khi deployment hoàn tất.
- Muốn phát hiện sớm lỗi tạo OpenAPI trong quá trình startup.
- Muốn chuyển chi phí tính toán khỏi request đầu tiên của người dùng.
- Ứng dụng có quy trình readiness yêu cầu tài liệu sẵn sàng trước khi nhận traffic.

Preloading không làm cho việc sinh tài liệu miễn phí. Chi phí được chuyển sang giai đoạn khởi động, vì vậy cần đo startup time và mức sử dụng CPU/bộ nhớ sau khi bật.

## 3. Chọn locale cần preload

Nếu tài liệu được dịch theo Accept-Language hoặc cấu hình i18n, có thể chỉ định các locale cần nạp bằng springdoc.pre-loading-locales.

Ví dụ:

~~~yaml
springdoc:
  pre-loading-enabled: true
  pre-loading-locales:
    - vi-VN
    - en-US
    - ja-JP
~~~

application.properties:

~~~properties
springdoc.pre-loading-enabled=true
springdoc.pre-loading-locales=vi-VN,en-US,ja-JP
~~~

Nếu không chỉ định pre-loading-locales, springdoc preload với default Locale của ứng dụng. Nếu có danh sách, hãy chọn những locale thực sự được công bố và có bản dịch.

Locale của document thường được lựa chọn từ header Accept-Language khi client tải OpenAPI. Ví dụ:

~~~bash
curl -H "Accept-Language: vi-VN" \
  http://localhost:8080/v3/api-docs
~~~

Và:

~~~bash
curl -H "Accept-Language: en-US" \
  http://localhost:8080/v3/api-docs
~~~

Để kết quả có nội dung khác nhau, ứng dụng cần có metadata hoặc cơ chế i18n tương ứng. Chỉ gửi Accept-Language không tự dịch mọi description được viết cố định trong annotation.

Đừng preload hàng loạt locale không dùng. Mỗi biến thể tài liệu cần thời gian tạo và có thể chiếm một vị trí cache.

## 4. Phân biệt preload với cache

Preloading và cache thường được sử dụng cùng nhau, nhưng không phải một khái niệm:

- Preloading quyết định document được tạo vào thời điểm nào.
- Cache quyết định kết quả đã tạo có được giữ để tái sử dụng hay không.

Cấu hình cache mặc định của springdoc là bật. Có thể giữ nguyên mặc định:

~~~yaml
springdoc:
  cache:
    disabled: false
~~~

Hoặc không khai báo springdoc.cache.disabled nếu không có nhu cầu đặc biệt.

Khi cache hoạt động, springdoc giữ kết quả OpenAPI đã tính toán để phục vụ những request sau. Theo FAQ chính thức, mô tả OpenAPI mặc định được tính một lần rồi cache; có thể tắt cache khi cần tính lại server URL theo từng request, ví dụ cùng Swagger UI được phục vụ qua proxy nội bộ và bên ngoài.

Nếu bật preloading nhưng tắt cache, document có thể vẫn được tạo lúc startup, nhưng request tiếp theo không được hưởng lợi từ việc tái sử dụng cache như khi cache bật. Hãy xác minh chi phí thực tế của cấu hình kết hợp trên phiên bản đang dùng.

## 5. Tắt cache khi tài liệu phụ thuộc request

Trong một số hệ thống, OpenAPI document có nội dung phụ thuộc request hiện tại. Ví dụ:

- Server URL được suy ra từ host và scheme của request.
- Ứng dụng được truy cập qua nhiều domain.
- Reverse proxy thêm prefix khác nhau.
- Customizer tạo metadata theo tenant hoặc context.
- Nội dung tài liệu thay đổi theo locale của request.

Nếu cache giữ một document được tạo từ request đầu tiên, request sau có thể nhận lại server URL hoặc metadata không phù hợp với request hiện tại.

Có thể tắt cache:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Hoặc:

~~~properties
springdoc.cache.disabled=true
~~~

Khi cache bị tắt, springdoc tính lại OpenAPI document theo request thay vì dùng kết quả cache đã lưu. Điều này có thể giúp các giá trị phụ thuộc request được cập nhật, nhưng cũng làm tăng CPU và độ trễ cho mỗi lần tải tài liệu.

Chỉ tắt cache khi có lý do cụ thể. Nếu document giống nhau ở mọi request, cache thường là lựa chọn hiệu quả hơn.

## 6. Cache theo locale và Accept-Language

Với tài liệu đa ngôn ngữ, cache cần phân biệt locale được yêu cầu. springdoc lưu một mô tả cho mỗi locale được yêu cầu qua Accept-Language.

Ví dụ:

| Request header | Biến thể tài liệu |
|---|---|
| Accept-Language: vi-VN | Tài liệu tiếng Việt |
| Accept-Language: en-US | Tài liệu tiếng Anh |
| Accept-Language: ja-JP | Tài liệu tiếng Nhật |

Nếu cache không phân biệt locale, người dùng có thể nhận nhầm nội dung ngôn ngữ. Vì vậy, hãy kiểm tra cả header request lẫn description được trả về.

Cấu hình pre-loading-locales giúp chuẩn bị trước những locale được chọn. Cache tiếp tục quản lý các biến thể được yêu cầu. Preloading locale không thay thế việc cấu hình nội dung dịch và không tự bảo đảm mọi locale đều có bản dịch đầy đủ.

Nếu ứng dụng không dùng i18n, không cần khai báo nhiều locale chỉ để làm cache lớn hơn.

## 7. Giới hạn số document trong cache

Các phiên bản springdoc mới có thuộc tính springdoc.cache.max-entries để giới hạn số mô tả OpenAPI được giữ trong cache.

Ví dụ:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 100
~~~

Hoặc:

~~~properties
springdoc.cache.disabled=false
springdoc.cache.max-entries=100
~~~

Theo tài liệu cấu hình hiện hành, mặc định max-entries là 100. Mỗi entry tương ứng với locale được yêu cầu; khi vượt giới hạn, entry ít được sử dụng gần đây nhất sẽ bị loại bỏ theo chính sách LRU.

Thuộc tính max-entries được bổ sung ở các nhánh phiên bản mới: tài liệu springdoc 2.x ghi nhận từ 2.9.1 và tài liệu nhánh 3.x ghi nhận từ 3.1.1. Nếu dự án dùng phiên bản cũ hơn, hãy kiểm tra reference tương ứng trước khi cấu hình; không giả định mọi phiên bản đều hỗ trợ thuộc tính này.

Giá trị 100 là mặc định của phiên bản được tài liệu hiện hành mô tả, không phải con số tối ưu cho mọi ứng dụng. Chọn giới hạn theo số locale thực tế, số document được cache và bộ nhớ dành cho ứng dụng.

## 8. Preloading nhiều locale có thể làm startup lâu hơn

Giả sử ứng dụng hỗ trợ ba locale vi-VN, en-US và ja-JP. Khi bật preloading cho cả ba, springdoc cần chuẩn bị document tương ứng theo cấu hình.

Nếu ứng dụng có nhiều group, schema lớn và customizer nặng, tổng thời gian chuẩn bị có thể tăng. Cần xem xét:

- Số locale thực sự được hỗ trợ.
- Số nhóm OpenAPI được công bố.
- Kích thước schema và số operation.
- Công việc của customizer.
- Bộ nhớ dành cho document đã tính.
- Thời gian readiness của deployment.
- Số instance khởi động đồng thời khi rollout.

Không nên preload locale mà ứng dụng không phục vụ. Nếu chỉ có tài liệu tiếng Việt, hãy dùng default Locale phù hợp hoặc cấu hình đúng locale đó thay vì tạo nhiều bản sao không cần thiết.

## 9. Preloading và readiness của ứng dụng

Trong môi trường Kubernetes hoặc nền tảng orchestration, startup và readiness là hai mốc khác nhau.

Preloading giúp tạo document trong startup. Tuy nhiên, readiness probe cần được thiết kế theo trạng thái mà ứng dụng thực sự cam kết. Không nên giả định rằng mọi cấu hình preload đều tự động làm health endpoint chờ đến khi mọi document/group/locale đã sẵn sàng theo cách mong muốn.

Một cách kiểm tra thực tế:

1. Bật preloading trong profile triển khai.
2. Khởi động ứng dụng với log startup được lưu.
3. Ghi nhận thời gian từ process start tới readiness.
4. Sau khi ứng dụng sẵn sàng, gọi /v3/api-docs.
5. So sánh độ trễ request đầu tiên giữa cấu hình preload bật và tắt.
6. Kiểm tra các locale được preload.
7. Kiểm tra các grouped document nếu ứng dụng có nhiều group.

Preloading có ích khi thời gian sinh tài liệu gây ảnh hưởng tới request đầu tiên. Nếu document nhỏ và request đầu tiên không có độ trễ đáng kể, việc preload có thể không mang lại lợi ích đủ lớn để đổi lấy startup time.

## 10. Cấu hình gợi ý cho môi trường phát triển

Trong local hoặc development, có thể ưu tiên trải nghiệm mở tài liệu nhanh và dễ kiểm tra:

~~~yaml
springdoc:
  pre-loading-enabled: true
  pre-loading-locales:
    - vi-VN
    - en-US
  cache:
    disabled: false
~~~

Nếu ứng dụng có nhiều locale nhưng chỉ kiểm thử một ngôn ngữ trong ngày, có thể giảm danh sách preload để startup nhanh hơn.

Khi thay đổi controller, DTO hoặc annotation, cần khởi động lại ứng dụng để nạp lại cấu trúc mới nếu không có cơ chế refresh riêng. Việc lưu file Java hoặc YAML trong IDE không tự cập nhật document đã cache của một process đang chạy.

## 11. Cấu hình gợi ý cho production

Với production có một public hostname ổn định và tài liệu ít thay đổi trong vòng đời process, thường có thể giữ cache bật:

~~~yaml
springdoc:
  pre-loading-enabled: true
  cache:
    disabled: false
~~~

Có thể preload locale mặc định hoặc danh sách locale thực sự được phục vụ.

Nếu server URL được suy ra từ request và cùng ứng dụng được truy cập qua nhiều proxy/hostname, cần cân nhắc tắt cache:

~~~yaml
springdoc:
  pre-loading-enabled: false
  cache:
    disabled: true
~~~

Đây là cấu hình minh họa cho trường hợp URL phụ thuộc request. Tắt cache đồng nghĩa document có thể được tính lại trên mỗi request, vì vậy hãy đo tải trước khi áp dụng rộng rãi.

Nếu public URL cố định, cách khác là khai báo servers tường minh để document không phụ thuộc host của request. Khi đó có thể giữ cache bật.

## 12. Tài liệu thay đổi khi nào?

OpenAPI document được tạo từ metadata của ứng dụng đang chạy. Các nguồn phổ biến gồm:

- Mapping của controller.
- DTO và kiểu generic.
- Annotation OpenAPI.
- OpenApiCustomizer và OperationCustomizer.
- Cấu hình GroupedOpenApi.
- Properties và profile.
- Locale hoặc request metadata nếu ứng dụng hỗ trợ.

Khi thay đổi source code hoặc cấu hình, process ứng dụng thường cần khởi động lại hoặc được triển khai lại để nạp metadata mới. Cache không phải cơ chế theo dõi file và tự cập nhật mọi thay đổi trong source.

Nếu document được cache, kết quả đã tạo có thể tiếp tục được dùng trong vòng đời process. Vì vậy, sau khi cập nhật controller, schema hoặc annotation, cần xác minh ứng dụng đã khởi động với artifact mới và document mới được tạo.

Không nên coi việc gọi lại /v3/api-docs là thao tác refresh cache. Khi cache bật, request có thể trả lại document đã tính trước đó.

## 13. Cập nhật OpenAPI trong ứng dụng đang chạy

Nếu ứng dụng có metadata động thay đổi trong runtime, cần xác định cơ chế tạo document:

- Nếu document được tạo từ cấu trúc controller/annotation cố định, triển khai artifact mới và khởi động lại là cách cập nhật thông thường.
- Nếu customizer đọc dữ liệu động, xác định dữ liệu đó có thay đổi theo request hay không.
- Nếu server URL hoặc nội dung phụ thuộc request, cân nhắc tắt cache.
- Nếu dữ liệu chỉ thay đổi theo cấu hình môi trường, có thể cần restart/redeploy khi cấu hình thay đổi.
- Nếu muốn tài liệu thay đổi ngay trong process mà không restart, phải có cơ chế cập nhật OpenAPI model/cache được hỗ trợ rõ ràng; không giả định springdoc tự phát hiện thay đổi.

Tránh tự tạo endpoint xóa cache bằng cách truy cập các bean nội bộ không phải API công khai. Cách đó có thể phụ thuộc implementation và dễ hỏng khi nâng phiên bản.

## 14. Cache không giống HTTP cache hoặc CDN cache

springdoc.cache.disabled điều khiển cache nội bộ của document đã tính toán. Nó không phải cấu hình HTTP Cache-Control, browser cache hoặc CDN cache.

Có thể phân biệt:

| Loại cache | Lưu ở đâu | Ảnh hưởng |
|---|---|---|
| springdoc OpenAPI cache | Trong process ứng dụng | Tái sử dụng OpenAPI model đã tính |
| HTTP cache | Browser hoặc intermediary theo HTTP headers | Có thể tái sử dụng response HTTP |
| CDN/reverse proxy cache | Hạ tầng trung gian | Có thể trả lại response đã cache ở edge |
| Build artifact | CI/CD hoặc artifact repository | Lưu file spec được xuất tại thời điểm build |

Tắt springdoc cache không tự xóa response đã được CDN cache. Ngược lại, đặt Cache-Control: no-store ở HTTP response không nhất thiết tắt cache nội bộ springdoc.

Nếu document thay đổi theo Accept-Language, HTTP cache và proxy cần xử lý Vary: Accept-Language phù hợp. Nếu document phụ thuộc host hoặc forwarded headers, cần kiểm soát cache key theo host và không để intermediary trả document của domain này cho domain khác.

## 15. Kết hợp preloading với nhiều GroupedOpenApi

Ứng dụng có thể có nhiều tài liệu theo group, ví dụ public, partner và admin:

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

Các tài liệu thường được truy cập qua:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
~~~

Mỗi group có tập operation, component và customizer có thể khác nhau. Khi ứng dụng có nhiều group, hãy kiểm tra endpoint của từng group thay vì chỉ kiểm tra /v3/api-docs mặc định.

Không giả định việc preload một document mặc định chứng minh mọi group và locale đã được chuẩn bị theo đúng yêu cầu của ứng dụng. Hãy xác minh các URL tài liệu thực tế sau startup và đo thời gian truy cập cho từng group.

Nếu group có customizer tốn thời gian, cần đo riêng vì chi phí có thể khác nhau giữa các document.

## 16. Cache và server URL phụ thuộc reverse proxy

Một trường hợp quan trọng là cùng Swagger UI được phục vụ qua nhiều hostname hoặc proxy. Server URL có thể được springdoc suy ra từ request.

Ví dụ:

~~~text
Request A:
https://api.example.com/v3/api-docs

Request B:
https://partner.example.com/v3/api-docs
~~~

Nếu document được tạo từ request A rồi cache, request B có thể nhận lại server URL của api.example.com. Điều này khiến Swagger UI ở domain partner gọi nhầm host.

FAQ chính thức của springdoc nêu trường hợp này và hướng dẫn tắt cache để server URL được tính lại trên từng HTTP request:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Trước khi tắt cache, hãy xác minh proxy gửi đúng Forwarded hoặc X-Forwarded-* và Spring Boot xử lý forwarded headers. Cache disabled không sửa được host/proto/prefix sai; nó chỉ yêu cầu tính lại document từ request hiện tại.

Nếu ứng dụng có một public URL duy nhất, có thể khai báo servers tường minh và giữ cache bật để giảm chi phí.

## 17. Đặt giới hạn cache phù hợp với số locale

Nếu phiên bản hỗ trợ springdoc.cache.max-entries, hãy chọn giới hạn dựa trên số locale và mức sử dụng thực tế.

Ví dụ ứng dụng có ba locale được phục vụ thường xuyên:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 10
~~~

Giá trị 10 trong ví dụ là giới hạn minh họa, không phải khuyến nghị cố định. Nếu có nhiều Accept-Language header khác nhau hoặc client gửi các biến thể locale không chuẩn hóa, cache có thể chứa nhiều entry hơn dự kiến cho tới khi chạm giới hạn.

Nên:

- Chuẩn hóa locale được chấp nhận.
- Chỉ công bố những ngôn ngữ có nội dung dịch.
- Theo dõi số request theo Accept-Language.
- Chọn max-entries đủ cho các locale được dùng.
- Kiểm tra hành vi eviction khi vượt giới hạn.
- Đối chiếu hỗ trợ property theo phiên bản springdoc.

Không tăng max-entries vô hạn để tránh eviction. Mỗi document có thể chứa nhiều schema và operation nên kích thước bộ nhớ phụ thuộc đáng kể vào API.

## 18. Kiểm tra cấu hình trong application.yml và application.properties

Cấu hình YAML:

~~~yaml
springdoc:
  pre-loading-enabled: true
  pre-loading-locales:
    - vi-VN
    - en-US
  cache:
    disabled: false
    max-entries: 20
~~~

Cấu hình properties tương đương:

~~~properties
springdoc.pre-loading-enabled=true
springdoc.pre-loading-locales=vi-VN,en-US
springdoc.cache.disabled=false
springdoc.cache.max-entries=20
~~~

Các nguồn cấu hình Spring Boot có thể ghi đè lẫn nhau, ví dụ:

- application.yml.
- application-{profile}.yml.
- Biến môi trường.
- Java system properties.
- Command-line arguments.
- Config server hoặc secret/config management.

Nếu hành vi không đúng như dự kiến, kiểm tra profile đang chạy và giá trị cấu hình cuối cùng. Có thể dùng Actuator env/configprops trong môi trường được bảo vệ để kiểm tra property đã bind; không công khai các endpoint quản trị này cho người dùng không có quyền.

## 19. Kiểm tra preloading và cache bằng curl

Sau khi ứng dụng khởi động, gọi OpenAPI endpoint:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

Kiểm tra locale:

~~~bash
curl -i \
  -H "Accept-Language: vi-VN" \
  http://localhost:8080/v3/api-docs
~~~

Và:

~~~bash
curl -i \
  -H "Accept-Language: en-US" \
  http://localhost:8080/v3/api-docs
~~~

So sánh:

- Response có status thành công không?
- Content-Type có phải application/json không?
- Description/summary có đúng ngôn ngữ không?
- Server URL có đúng hostname và prefix không?
- Các group có đủ path và schema không?

Có thể lưu document để so sánh:

~~~bash
curl -fsS -H "Accept-Language: vi-VN" \
  http://localhost:8080/v3/api-docs -o openapi-vi.json

curl -fsS -H "Accept-Language: en-US" \
  http://localhost:8080/v3/api-docs -o openapi-en.json
~~~

Không chỉ so sánh thời gian request rồi kết luận cache đã bật hoặc tắt. Thời gian còn phụ thuộc JVM warm-up, network, proxy và tải hệ thống. Hãy kết hợp log, cấu hình thực tế và phép đo lặp lại.

## 20. Kiểm tra thời gian startup và request đầu tiên

Để đánh giá preloading, so sánh hai lần chạy với cùng dữ liệu và môi trường:

| Chỉ số | Preloading tắt | Preloading bật |
|---|---|---|
| Startup duration | Thường ít công việc tạo OpenAPI hơn | Có thể tăng do tạo document trước |
| Request /v3/api-docs đầu tiên | Có thể chịu chi phí tính document | Có thể nhanh hơn nếu document đã được preload |
| Request tiếp theo khi cache bật | Dùng kết quả cache | Dùng kết quả cache |
| Bộ nhớ | Phụ thuộc document được tạo khi truy cập | Có thể tăng sớm hơn do document được tạo khi startup |

Đây là xu hướng cần đo, không phải bảo đảm về số mili giây. Kết quả phụ thuộc số controller, schema, locale, group và customizer.

Dùng cùng profile, JVM options, dataset và số lần đo. Bỏ qua lần chạy đầu nếu cần tách chi phí JIT hoặc class loading. Ghi nhận cả thời gian startup lẫn p50/p95 của request tài liệu.

## 21. Kiểm thử OpenAPI document bằng WebTestClient hoặc MockMvc

Có thể viết integration test xác minh endpoint tài liệu vẫn hoạt động sau khi bật preloading:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OpenApiPreloadingTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void servesOpenApiAfterApplicationStartup() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.openapi").exists()
            .jsonPath("$.paths").exists();
    }
}
~~~

Nếu hỗ trợ nhiều locale, test riêng:

~~~java
@Test
void servesVietnameseOpenApi() {
    webTestClient.get()
        .uri("/v3/api-docs")
        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi-VN")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.info.title").isNotEmpty();
}
~~~

Để chứng minh nội dung dịch, hãy kiểm tra một description hoặc summary đã được cấu hình bản dịch thay vì chỉ kiểm tra info.title tồn tại.

Test này xác minh endpoint và nội dung, không đo trực tiếp việc preloading đã xảy ra bên trong startup. Để kiểm tra lợi ích hiệu năng, cần benchmark startup và request đầu tiên trên cùng môi trường.

## 22. Kiểm tra grouped documents và locale

Nếu ứng dụng có group public và partner, tạo test cho từng endpoint:

~~~java
@Test
void servesPublicGroup() {
    webTestClient.get()
        .uri("/v3/api-docs/public")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.paths").exists();
}

@Test
void servesPartnerGroup() {
    webTestClient.get()
        .uri("/v3/api-docs/partner")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.paths").exists();
}
~~~

Nếu locale ảnh hưởng từng group, kết hợp test Accept-Language với endpoint group. Không cần tạo toàn bộ tổ hợp nếu ứng dụng không công bố chúng; ưu tiên những group và locale thực sự có người dùng.

Nếu group có security hoặc customizer riêng, test thêm nội dung và quyền truy cập tương ứng.

## 23. Cập nhật tài liệu sau khi thay đổi code

Một chu trình triển khai thường là:

1. Thay đổi controller, DTO, annotation hoặc customizer.
2. Chạy unit test và OpenAPI contract test.
3. Tạo artifact ứng dụng mới.
4. Triển khai và khởi động process mới.
5. Springdoc tạo/preload document theo cấu hình.
6. Kiểm tra /v3/api-docs và các group.
7. Kiểm tra locale và server URL.
8. So sánh OpenAPI diff với phiên bản trước.
9. Phát hành spec cho client hoặc API portal.

Nếu dùng cache, process mới sẽ có cache mới theo vòng đời của nó. Không nên cố giữ cache cũ qua lần deploy nếu mục tiêu là tài liệu phản ánh source mới.

Nếu chỉ thay đổi cấu hình ngoài ứng dụng mà không restart, cần xác minh Spring Cloud Config hoặc cơ chế refresh có cập nhật bean và document hay không. Không mặc định mọi thay đổi property sẽ tự làm springdoc tái tạo tài liệu.

## 24. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Request đầu tiên tải Swagger UI chậm | Document chỉ được tính khi có request đầu và cache chưa được tạo |
| Startup tăng sau khi bật preload | Công việc tạo OpenAPI được chuyển sang startup |
| Locale tiếng Anh vẫn nhận mô tả tiếng Việt | Chưa cấu hình bản dịch hoặc Accept-Language không được xử lý như dự kiến |
| Locale mới không có trong cache preload | Chưa thêm vào pre-loading-locales hoặc đang dùng default Locale |
| Host trong spec sai sau reverse proxy | Cache giữ server URL của request trước hoặc forwarded headers sai |
| Tắt cache nhưng request vẫn chậm | Chi phí sinh OpenAPI vẫn tồn tại và phát sinh lại ở mỗi request |
| Tài liệu cũ sau khi sửa controller | Process chưa được triển khai lại hoặc cache vẫn giữ document cũ |
| Group public đúng nhưng group partner sai | Chỉ kiểm tra document mặc định, bỏ sót group riêng |
| max-entries không có tác dụng | Phiên bản springdoc chưa hỗ trợ property hoặc cấu hình chưa được bind |
| Preload không cải thiện request đầu | Đang tắt cache, document chưa được preload như kỳ vọng hoặc thời gian bị chi phối bởi yếu tố khác |
| Memory tăng khi preload nhiều locale | Mỗi biến thể document chiếm bộ nhớ |
| CDN vẫn trả tài liệu cũ sau khi tắt springdoc cache | HTTP/CDN cache là lớp độc lập |

## 25. Quy trình lựa chọn cấu hình

Có thể dùng quy trình sau để chọn cấu hình:

1. Xác định document có lớn hoặc tốn thời gian tạo không.
2. Đo độ trễ request OpenAPI đầu tiên sau startup.
3. Nếu request đầu chậm, thử bật pre-loading-enabled.
4. Nếu có i18n, chọn đúng pre-loading-locales.
5. Giữ cache bật khi document ổn định theo request.
6. Tắt cache khi server URL hoặc metadata thực sự phụ thuộc request.
7. Chọn cache.max-entries theo số locale và phiên bản hỗ trợ.
8. Đo lại startup, request đầu tiên, request tiếp theo và bộ nhớ.
9. Kiểm tra từng group và locale.
10. Đưa test tài liệu và contract validation vào CI.

Đừng tắt cache chỉ vì muốn tài liệu cập nhật sau mỗi lần build. Khi source thay đổi, triển khai process mới thường là cách cập nhật đúng. Đừng bật preload nếu thời gian tạo document không ảnh hưởng trải nghiệm và startup budget đã chặt.

## 26. Checklist

- [ ] Đã đo thời gian tạo OpenAPI và độ trễ request đầu tiên.
- [ ] Đã xác định có cần springdoc.pre-loading-enabled hay không.
- [ ] Nếu preload nhiều ngôn ngữ, đã khai báo pre-loading-locales phù hợp.
- [ ] Nếu không khai báo locale, đã hiểu document dùng default Locale.
- [ ] Đã hiểu cache mặc định được bật.
- [ ] Chỉ tắt springdoc.cache.disabled khi document phụ thuộc request.
- [ ] Đã phân biệt springdoc cache với HTTP/CDN cache.
- [ ] Đã kiểm tra cache theo Accept-Language.
- [ ] Đã xác minh phiên bản hỗ trợ springdoc.cache.max-entries.
- [ ] Giá trị max-entries phù hợp số locale và bộ nhớ.
- [ ] Đã đo tác động preloading tới startup/readiness.
- [ ] Đã kiểm tra từng GroupedOpenApi document.
- [ ] Đã kiểm tra server URL sau proxy nếu có nhiều hostname.
- [ ] Đã triển khai lại process khi source metadata thay đổi.
- [ ] Đã kiểm tra OpenAPI JSON bằng integration test.
- [ ] Đã đưa validator và spec diff vào CI nếu API cần quản lý hợp đồng.

## 27. Nguồn tra cứu

- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html)
- [springdoc-openapi FAQ – Cache và server URL](https://springdoc.org/faq.html)
- [springdoc-openapi v2 Configuration Properties](https://springdoc.org/v2/properties.html)
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot – Application Startup and Lifecycle](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)

Preloading quyết định khi nào springdoc tạo OpenAPI document; cache quyết định kết quả có được tái sử dụng hay không. Bật preload có thể giảm độ trễ request tài liệu đầu tiên nhưng tăng startup time. Giữ cache bật khi document ổn định; tắt cache khi server URL hoặc metadata phụ thuộc request. Với tài liệu đa ngôn ngữ, hãy quản lý Accept-Language, danh sách locale preload và giới hạn cache theo phiên bản. Luôn đo startup, request đầu tiên, request tiếp theo và kiểm tra từng group trước khi chọn cấu hình production.

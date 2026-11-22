# Cấu hình tài nguyên tĩnh và chuỗi xử lý tài nguyên trong Spring WebFlux

## 1. Static resource trong một ứng dụng WebFlux

Một ứng dụng WebFlux không chỉ trả JSON từ controller. Ứng dụng thường phải phục vụ các tệp tĩnh như:

- HTML, CSS và JavaScript của giao diện.
- Ảnh, biểu tượng, font và tệp SVG.
- Tài liệu PDF hoặc tệp tải xuống được công khai.
- Asset được đóng gói trong JAR hoặc đặt trong một thư mục riêng trên máy chủ.
- Thư viện frontend được đóng gói dưới dạng WebJars.

**Static resource** là nội dung được lưu sẵn và được phục vụ theo một URL. Khi client yêu cầu URL đó, server tìm tài nguyên trong các location đã cấu hình rồi ghi nội dung ra HTTP response. Tài nguyên không cần được tạo lại từ logic nghiệp vụ trong mỗi request.

Spring WebFlux cung cấp cơ chế phục vụ static resource thông qua:

- **ResourceHandlerRegistry**: đăng ký URL pattern và các location chứa tài nguyên.
- **ResourceWebHandler**: nhận request khớp pattern, tìm Resource và ghi response.
- **ResourceResolver**: ánh xạ đường dẫn request sang Resource thực tế.
- **ResourceTransformer**: biến đổi Resource trước khi ghi response.
- **ResourceUrlProvider**: tạo URL công khai sau khi áp dụng chuỗi resolver, ví dụ chèn content hash vào tên file.
- **CacheControl** và conditional request: giúp browser/proxy tái sử dụng nội dung đã tải.

Cần phân biệt hai loại cache: cache HTTP mà browser hoặc proxy sử dụng theo response headers, và cache nội bộ của resource chain dùng để tránh lặp lại công việc resolve/transform trên server. Hai cơ chế này có mục đích và vòng đời khác nhau.

## 2. Cơ chế mặc định của Spring Boot WebFlux

Spring Boot tự cấu hình static resource handler khi ứng dụng có WebFlux.

Các thư mục classpath mặc định gồm:

~~~text
src/main/resources/
├── static/
├── public/
├── resources/
└── META-INF/
    └── resources/
~~~

Các thư mục trên là những location riêng biệt; không cần tạo đủ cả bốn. Một file trong classpath có thể được truy cập qua URL theo mapping mặc định:

~~~text
GET /
GET /index.html
GET /css/site.css
GET /images/logo.svg
~~~

Mặc định, static resources được map trên pattern **/**. Spring Boot dùng **ResourceWebHandler** của Spring WebFlux để phục vụ chúng.

### 2.1. Thay đổi URL pattern bằng application.properties

Có thể chuyển static resources sang một prefix riêng:

~~~properties
spring.webflux.static-path-pattern=/resources/**
~~~

Khi đó file:

~~~text
src/main/resources/static/css/site.css
~~~

được phục vụ qua:

~~~text
GET /resources/css/site.css
~~~

Pattern này chỉ thay URL mapping. Nó không di chuyển file trong classpath.

### 2.2. Thay đổi location bằng application.properties

Có thể chỉ định location riêng:

~~~properties
spring.web.resources.static-locations=classpath:/public-assets/,file:/srv/www/
~~~

Spring Boot sẽ dùng danh sách location này thay cho các location mặc định. Nếu muốn giữ các location mặc định, phải khai báo lại chúng trong danh sách.

Ví dụ:

~~~properties
spring.web.resources.static-locations=classpath:/static/,classpath:/public/,classpath:/resources/,classpath:/META-INF/resources/
~~~

Mỗi location phải là một thư mục hợp lệ. Với filesystem, dùng URL dạng file URI và nên kết thúc bằng dấu gạch chéo để thể hiện đây là thư mục:

~~~properties
spring.web.resources.static-locations=file:/srv/www/
~~~

Các location được xét theo thứ tự cấu hình. Nếu nhiều location có cùng đường dẫn tương đối, location được tìm thấy trước có thể quyết định Resource được phục vụ.

### 2.3. WebFlux không dùng src/main/webapp

WebFlux không phụ thuộc Servlet API theo cách Spring MVC truyền thống, do đó không dựa vào thư mục src/main/webapp để phục vụ static resources. Với ứng dụng Spring Boot WebFlux, hãy đặt nội dung trong classpath hoặc cấu hình một Resource location phù hợp.

### 2.4. WebJars

WebJars đóng gói thư viện frontend trong JAR. Spring Boot hỗ trợ URL dạng:

~~~text
/webjars/library-name/version/file
~~~

Ví dụ một thư viện có thể được phục vụ từ:

~~~text
/webjars/jquery/3.7.1/jquery.min.js
~~~

URL có version là cách được khuyến nghị vì xác định rõ phiên bản thư viện và thuận tiện cho caching. URL không có version có thể được hỗ trợ bằng WebJarsResourceResolver khi dependency org.webjars:webjars-locator-core có trên classpath; cơ chế này cần quét classpath và có thể làm tăng thời gian startup.

Có thể thay pattern WebJars bằng:

~~~properties
spring.webflux.webjars-path-pattern=/vendor/**
~~~

## 3. Đăng ký resource handler bằng WebFluxConfigurer

Khi cần kiểm soát URL pattern, location, cache headers hoặc resource chain, hãy triển khai **WebFluxConfigurer** và override **addResourceHandlers**.

Ví dụ:

~~~java
@Configuration
public class StaticResourceConfiguration
        implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(
            ResourceHandlerRegistry registry) {

        registry.addResourceHandler("/assets/**")
            .addResourceLocations("classpath:/static/assets/")
            .setCacheControl(
                CacheControl.maxAge(365, TimeUnit.DAYS)
                    .cachePublic()
            );
    }
}
~~~

Các thành phần:

- **addResourceHandler("/assets/**")**: mọi request khớp prefix /assets/ được chuyển tới handler này.
- **addResourceLocations(...)**: khai báo thư mục gốc dùng để tìm tài nguyên.
- **setCacheControl(...)**: thiết lập Cache-Control cho response static resource.

Nếu file nằm tại:

~~~text
src/main/resources/static/assets/css/site.css
~~~

URL tương ứng là:

~~~text
/assets/css/site.css
~~~

Phần prefix /assets/ của URL được bỏ khi tìm tương đối trong location classpath:/static/assets/.

### 3.1. Một handler có nhiều location

Có thể khai báo nhiều location:

~~~java
registry.addResourceHandler("/shared/**")
    .addResourceLocations(
        "classpath:/static/shared/",
        "file:/srv/www/shared/"
    );
~~~

Spring tìm Resource theo thứ tự location. Cách này hữu ích khi ứng dụng đóng gói một số asset mặc định trong JAR và cho phép bổ sung asset công khai từ filesystem.

Không thêm thư mục chứa secrets, cấu hình, file upload riêng tư hoặc dữ liệu người dùng vào danh sách location công khai.

### 3.2. Nhiều handler với chính sách riêng

Có thể đăng ký các pattern khác nhau:

~~~java
@Override
public void addResourceHandlers(
        ResourceHandlerRegistry registry) {

    registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/static/assets/")
        .setCacheControl(
            CacheControl.maxAge(365, TimeUnit.DAYS).cachePublic()
        );

    registry.addResourceHandler("/downloads/**")
        .addResourceLocations("classpath:/static/downloads/")
        .setCacheControl(CacheControl.noCache());
}
~~~

Ví dụ này cho thấy mỗi handler có thể dùng location và Cache-Control khác nhau. Với dữ liệu cần xác thực, cần thêm authorization thích hợp và kiểm soát cache theo danh tính người dùng. Một URL static công khai không phải là cơ chế bảo vệ file riêng tư.

### 3.3. Thứ tự HandlerMapping

Resource handler được đăng ký thông qua ResourceHandlerRegistry và có thứ tự mặc định thấp hơn các handler mapping thông thường. Controller mapping cụ thể thường được ưu tiên trước static resource mapping. Nếu có pattern chồng lấn, hãy thiết kế prefix rõ ràng và tránh dùng một pattern quá rộng làm mơ hồ route nghiệp vụ.

## 4. ResourceWebHandler xử lý request như thế nào?

**ResourceWebHandler** là WebHandler chuyên phục vụ static Resource. Luồng xử lý khái quát:

~~~text
HTTP request
     |
     v
HandlerMapping tìm pattern khớp
     |
     v
ResourceWebHandler
     |
     v
Lấy path tương đối trong handler mapping
     |
     v
Chuẩn hóa và kiểm tra đường dẫn
     |
     v
ResourceResolver chain
     |
     v
Tìm Resource trong các location được phép
     |
     v
ResourceTransformer chain
     |
     v
Xác định media type và HTTP metadata
     |
     v
ResourceHttpMessageWriter ghi response
~~~

Handler sử dụng path bên trong URL pattern để tìm Resource. Ví dụ pattern /assets/** và request /assets/css/site.css tạo đường dẫn tương đối css/site.css.

### 4.1. Chuẩn hóa đường dẫn và kiểm tra Resource

ResourceWebHandler chuẩn hóa input path và kiểm tra các đường dẫn không hợp lệ trước khi resolve. Sau đó resolver tìm Resource trong các location đã cấu hình.

Đường dẫn sau khi resolve phải nằm trong phạm vi được phép. **PathResourceResolver** thực hiện kiểm tra Resource có thuộc location tương ứng hoặc một trong các allowed locations hay không. Mặc định ResourceWebHandler khởi tạo allowed locations phù hợp với danh sách location của handler.

Đây là một lớp bảo vệ quan trọng chống path traversal. Tuy nhiên, ứng dụng vẫn phải giới hạn location ở đúng thư mục công khai, cập nhật Spring Framework và tránh tự viết resolver bỏ qua các kiểm tra an toàn.

### 4.2. ResourceWebHandler và HTTP response

Sau khi Resource được resolve và transform, handler xác định media type theo tên file hoặc cấu hình media type, sau đó ghi Resource bằng message writer.

Static resource handler hỗ trợ các khả năng HTTP như:

- Content-Type phù hợp với phần mở rộng.
- Content-Length khi có thể xác định.
- Last-Modified và conditional request.
- Cache-Control.
- Byte Range khi Resource và response đáp ứng điều kiện.
- Content-Encoding khi có Resource đã nén được resolver chọn.

Không cần tạo controller riêng cho từng file CSS, ảnh hoặc JavaScript. ResourceWebHandler đảm nhiệm công việc này.

## 5. ResourceResolver và ResourceTransformer khác nhau thế nào?

Đây là hai extension point chính của resource chain.

| Extension point | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **ResourceResolver** | Request path này tương ứng với Resource nào? | PathResourceResolver, VersionResourceResolver, EncodedResourceResolver |
| **ResourceTransformer** | Resource đã tìm được cần được biến đổi ra sao trước khi gửi? | CssLinkResourceTransformer, transformer tùy biến |

Resolver làm việc với ánh xạ đường dẫn và lựa chọn Resource. Transformer nhận Resource đã được resolve và tạo nội dung/Resource đầu ra phù hợp trước khi ghi response.

### 5.1. ResourceResolver

Interface ResourceResolver cho phép:

- Tìm Resource từ request path.
- Chuyển URL nội bộ thành URL công khai.
- Delegate sang resolver tiếp theo trong chain.
- Áp dụng quy tắc versioning, content encoding hoặc WebJars.

Một resolver có thể trả về Mono<Resource> hoặc Mono<String> trong các API resolve tương ứng vì WebFlux xử lý bất đồng bộ.

Các resolver tích hợp thường dùng:

| Resolver | Chức năng |
| --- | --- |
| **PathResourceResolver** | Tìm file tương đối trong các location đã đăng ký và kiểm tra boundary |
| **VersionResourceResolver** | Resolve URL có version và kiểm tra version của nội dung |
| **EncodedResourceResolver** | Chọn biến thể đã nén phù hợp với Accept-Encoding |
| **WebJarsResourceResolver** | Resolve URL WebJars không có version khi locator có mặt |
| **CachingResourceResolver** | Cache kết quả resolve để tránh tìm lại Resource |
 
### 5.2. PathResourceResolver

PathResourceResolver là resolver cơ bản, thường được đặt cuối chuỗi vì nó thực hiện bước tìm Resource thực tế trong các location.

Nó kiểm tra:

- Resource tồn tại.
- Resource có thể đọc.
- Resource nằm trong location hợp lệ hoặc allowed locations.
- Đường dẫn sau khi chuẩn hóa không thoát khỏi phạm vi đã cấu hình.

Nếu không có resolver tùy biến, ResourceWebHandler sử dụng PathResourceResolver để tìm file theo path tương đối.

Không tự đặt allowed locations quá rộng. Ví dụ cho phép toàn bộ filesystem root sẽ làm mất ý nghĩa của boundary check.

### 5.3. VersionResourceResolver

VersionResourceResolver thêm version vào URL để browser cache nội dung lâu dài nhưng vẫn nhận được phiên bản mới khi file thay đổi.

Có hai chiến lược thường dùng:

- **ContentVersionStrategy**: tính hash nội dung, thường dùng MD5, rồi thêm hash vào tên file.
- **FixedVersionStrategy**: thêm version cố định do ứng dụng cung cấp, ví dụ phiên bản release hoặc build identifier.

Ví dụ URL có content hash:

~~~text
/assets/css/site-<hash>.css
~~~

Nếu nội dung site.css thay đổi, hash thay đổi và URL công khai cũng thay đổi. Browser coi URL mới là một resource khác nên không dùng nhầm bản cache cũ.

Cấu hình:

~~~java
VersionResourceResolver versionResolver =
    new VersionResourceResolver()
        .addContentVersionStrategy("/**");
~~~

Với JavaScript dùng module loader, ContentVersionStrategy có thể không phù hợp vì đường dẫn import bên trong module cần được xử lý đồng bộ. Trong trường hợp đó, FixedVersionStrategy thường phù hợp hơn:

~~~java
VersionResourceResolver versionResolver =
    new VersionResourceResolver()
        .addFixedVersionStrategy(
            "v2026.11",
            "/**/*.js"
        )
        .addContentVersionStrategy(
            "/**/*.css",
            "/**/*.png",
            "/**/*.svg"
        );
~~~

Version cố định nên được lấy từ build metadata hoặc cấu hình release để mọi asset trong cùng một bản build dùng version nhất quán.

### 5.4. EncodedResourceResolver

EncodedResourceResolver tìm biến thể nội dung đã nén, ví dụ gzip hoặc Brotli, dựa trên header **Accept-Encoding** của request.

Ví dụ thư mục có:

~~~text
site.css
site.css.gz
site.css.br
~~~

Nếu browser gửi Accept-Encoding tương thích, resolver có thể chọn phiên bản đã nén thay vì file gốc. Server cần trả Content-Encoding phù hợp để client giải nén đúng cách.

Resolver này hữu ích khi build pipeline tạo sẵn compressed asset. Nó không tự động nén mọi file bất kỳ nếu không có biến thể tương ứng.

### 5.5. WebJarsResourceResolver

WebJarsResourceResolver giúp hỗ trợ URL không có version khi thư viện được đóng gói theo WebJars. Nó cần dependency org.webjars:webjars-locator-core để tra cứu version trong classpath.

URL có version trực tiếp thường hiệu quả hơn vì không cần dò classpath khi startup. Chỉ bật resolver versionless khi ứng dụng thực sự cần kiểu URL đó.

## 6. ResourceTransformer và tối ưu nội dung

ResourceTransformer biến đổi Resource trước khi response được ghi.

Các tình huống thường gặp:

- Viết lại URL ảnh/font bên trong CSS.
- Chèn content hash vào các link asset.
- Minify hoặc chuẩn hóa nội dung text.
- Biến đổi một resource dựa trên cấu hình build/runtime.

### 6.1. CssLinkResourceTransformer

CSS có thể tham chiếu ảnh, font hoặc file CSS khác:

~~~css
@import url("./theme.css");

.logo {
    background-image: url("../images/logo.svg");
}
~~~

Khi asset được version hóa, các URL bên trong CSS cũng phải trỏ tới phiên bản tương ứng. Nếu CSS được đổi tên nhưng link nội bộ vẫn trỏ tới URL cũ, browser có thể không tải đúng asset hoặc bỏ qua cache version.

**CssLinkResourceTransformer** phân tích các link trong CSS và dùng resource URL resolution để viết lại URL công khai. Điều này giúp link bên trong CSS tương thích với VersionResourceResolver.

Cấu hình transformer:

~~~java
CssLinkResourceTransformer cssTransformer =
    new CssLinkResourceTransformer();
~~~

### 6.2. Transformer tùy biến

Có thể triển khai ResourceTransformer cho một yêu cầu cụ thể. Một transformer nhận ServerWebExchange, Resource và ResourceTransformerChain rồi trả Mono<Resource>.

Khi viết transformer:

- Giữ nội dung và metadata cần thiết của Resource.
- Không chặn event-loop bằng thao tác I/O đồng bộ nặng.
- Không đọc file lớn toàn bộ vào bộ nhớ nếu không cần.
- Delegate sang transformer tiếp theo khi không cần thay đổi.
- Đảm bảo output ổn định nếu resource chain có cache.
- Kiểm tra dữ liệu nguồn trước khi đưa vào response.

Nếu cần tạo nội dung minified, tốt nhất thực hiện ở build pipeline khi asset tĩnh có thể được tạo sẵn. Runtime transformer nên được dùng khi có lý do thực sự cần biến đổi lúc phục vụ.

## 7. Thứ tự của resolver và transformer chain

Thứ tự resolver ảnh hưởng trực tiếp đến Resource được chọn.

Một chuỗi phổ biến khi dùng nội dung đã nén và version theo nội dung:

~~~text
Request
  |
  v
EncodedResourceResolver
  |
  v
VersionResourceResolver
  |
  v
PathResourceResolver
  |
  v
ResourceTransformer chain
  |
  v
Response writer
~~~

Khi dùng đồng thời **EncodedResourceResolver** và **VersionResourceResolver** với content-based versioning, phải đăng ký EncodedResourceResolver trước VersionResourceResolver. Như vậy version được tính dựa trên nội dung gốc, không bị ảnh hưởng bởi biến thể đã nén.

PathResourceResolver là resolver cuối chuỗi để thực hiện việc tìm Resource trong location. Khi ResourceChainRegistration tự cấu hình resolver chain, Spring bổ sung PathResourceResolver làm resolver cuối nếu cần.

Ví dụ:

~~~java
registry.addResourceHandler("/assets/**")
    .addResourceLocations("classpath:/static/assets/")
    .resourceChain(true)
    .addResolver(new EncodedResourceResolver())
    .addResolver(new VersionResourceResolver().addContentVersionStrategy("/**"))
    .addTransformer(new CssLinkResourceTransformer());
~~~

Không đảo thứ tự hai resolver trên nếu version được tính từ content và có các file đã nén.

### 7.1. Resolver và transformer có thể delegate

Resolver có thể gọi resolver tiếp theo thông qua ResourceResolverChain. Transformer có thể gọi transformer tiếp theo thông qua ResourceTransformerChain.

Cơ chế delegate cho phép ghép nhiều chiến lược độc lập. Ví dụ resolver versioning có thể xử lý phần version trước rồi để PathResourceResolver tìm file thật. CSS transformer có thể tìm các link tham chiếu thông qua resolver chain đã cấu hình.

Không viết resolver tự kết thúc chuỗi khi nó chưa tìm được Resource nếu resolver tiếp theo vẫn có thể xử lý request. Hãy tuân thủ contract của chain.

## 8. Cấu hình resource chain trong ResourceHandlerRegistry

Để bật resource chain, dùng **resourceChain(boolean cacheResources)** trên ResourceHandlerRegistration.

Ví dụ:

~~~java
registry.addResourceHandler("/assets/**")
    .addResourceLocations("classpath:/static/assets/")
    .resourceChain(true)
    .addResolver(
        new VersionResourceResolver()
            .addContentVersionStrategy("/**")
    )
    .addTransformer(new CssLinkResourceTransformer());
~~~

Tham số true bật cache nội bộ cho kết quả resolution/transformation. Điều này hữu ích trong production vì cùng một static asset thường được request nhiều lần.

Trong development, có thể dùng:

~~~java
.resourceChain(false)
~~~

để tránh giữ kết quả resolve/transform cũ trong khi nội dung file đang được thay đổi liên tục.

### 8.1. Cache mặc định của resource chain

Khi bật cache và không truyền cache riêng, Spring dùng cache trong bộ nhớ cho resolver/transformer. Các Resource thường gắn với filesystem hoặc classpath của chính process nên không nên mặc định đưa object Resource vào distributed cache.

Nếu ứng dụng truyền Cache riêng vào resourceChain(true, cache), cần quản lý key, namespace, eviction và phạm vi chia sẻ rõ ràng.

### 8.2. Cache-Control không phải resource-chain cache

Hai cấu hình sau làm hai việc khác nhau:

~~~java
.setCacheControl(
    CacheControl.maxAge(365, TimeUnit.DAYS).cachePublic()
)
~~~

Thiết lập HTTP response header để browser hoặc proxy biết thời gian có thể tái sử dụng response.

~~~java
.resourceChain(true)
~~~

Bật cache nội bộ của server cho quá trình resolve và transform.

Có thể bật HTTP caching nhưng tắt resource-chain cache, hoặc ngược lại. Không dùng một cấu hình để suy luận rằng cấu hình kia cũng đã được bật.

### 8.3. Dùng cache riêng cho từng security boundary

Nếu một ứng dụng có resource handler công khai và resource handler yêu cầu authentication, không dùng chung cache tùy biến giữa hai handler đó.

Ví dụ:
- Handler /assets/** phục vụ nội dung công khai.
- Handler /private-assets/** phục vụ nội dung phụ thuộc user hoặc tenant.

Cache dùng chung có thể khiến Resource đã resolve cho một phạm vi được tái sử dụng trong phạm vi khác nếu cache key và chính sách phân tách không phù hợp. Hãy tách cache theo handler/security boundary và ưu tiên dùng controller/service có authorization rõ ràng cho file riêng tư.

## 9. HTTP caching cho static resources

HTTP caching giúp browser và proxy tránh tải lại nội dung không đổi. Các header thường dùng:

| Header | Vai trò |
| --- | --- |
| **Cache-Control** | Quy định cache được lưu và tái sử dụng trong bao lâu |
| **Last-Modified** | Thời điểm Resource được sửa đổi lần cuối |
| **ETag** | Validator đại diện cho phiên bản nội dung |
| **If-Modified-Since** | Client hỏi Resource có thay đổi sau một thời điểm không |
| **If-None-Match** | Client hỏi ETag hiện tại có khớp không |

### 9.1. Cache-Control

Ví dụ cache trong một giờ:

~~~java
CacheControl.maxAge(1, TimeUnit.HOURS)
~~~

Ví dụ không cho cache lưu response:

~~~java
CacheControl.noStore()
~~~

Ví dụ cho cache công khai trong một năm:

~~~java
CacheControl.maxAge(365, TimeUnit.DAYS)
    .cachePublic()
~~~

Chọn policy theo tính chất nội dung:

| Nội dung | Chính sách gợi ý |
| --- | --- |
| Asset có content hash trong URL | max-age dài, public, có thể immutable |
| File không có version trong URL | max-age ngắn hoặc no-cache để revalidate |
| File cá nhân cần authorization | private hoặc no-store tùy yêu cầu bảo mật |
| Tài liệu thay đổi thường xuyên | max-age ngắn và validator phù hợp |

Không đặt public cho tài nguyên cá nhân hoặc nội dung phụ thuộc quyền truy cập chỉ để tăng tốc.

### 9.2. Last-Modified và 304 Not Modified

ResourceWebHandler đánh giá Last-Modified nếu có thể. Khi client gửi If-Modified-Since và nội dung chưa thay đổi, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
~~~

Response 304 không cần gửi lại body. Browser sử dụng bản cache đã có.

Cơ chế này giúp tiết kiệm băng thông cho các file giữ nguyên tại cùng URL.

### 9.3. ETag

ETag là validator đại diện cho một phiên bản nội dung. Client gửi If-None-Match để kiểm tra nội dung đã thay đổi chưa.

ResourceHandlerRegistration có thể cấu hình ETag generator trong các phiên bản Spring hỗ trợ API này. Generator nên tạo giá trị ổn định cho đúng representation và tránh tính toán quá tốn kém trên mỗi request.

Không tạo ETag từ một metadata thay đổi độc lập với nội dung nếu mục tiêu là nhận biết thay đổi của file. Với asset có content hash trong URL, version URL đã là một cơ chế nhận diện phiên bản hữu ích; ETag có thể bổ sung cho conditional request.

### 9.4. Cache-Control và content-hash URL phối hợp

Một asset có URL:

~~~text
/assets/site-a1b2c3....css
~~~

Nếu nội dung thay đổi, URL được tạo ra từ hash mới. Do URL thay đổi, browser có thể cache URL cũ lâu mà không lo nhận nhầm nội dung mới tại cùng địa chỉ.

Đây là lý do asset versioned có thể dùng max-age dài. Với URL không version, cache cần revalidate thường xuyên hơn vì nội dung có thể thay đổi trong khi địa chỉ vẫn giữ nguyên.

## 10. ResourceUrlProvider trong WebFlux

WebFlux có **ResourceUrlProvider** để tạo URL công khai thông qua resolver chain. Đây là cách lấy URL đã được version hóa mà không phải tự tính hash hoặc nối tên file bằng tay.

API reactive quan trọng là:

~~~java
Mono<String> getForUriString(
    String uriString,
    ServerWebExchange exchange
)
~~~

Ví dụ controller:

~~~java
@RestController
public class AssetUrlController {

    private final ResourceUrlProvider resourceUrlProvider;

    public AssetUrlController(
            ResourceUrlProvider resourceUrlProvider) {
        this.resourceUrlProvider = resourceUrlProvider;
    }

    @GetMapping(
        value = "/asset-url",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> assetUrl(ServerWebExchange exchange) {
        return resourceUrlProvider.getForUriString(
            "/assets/site.css",
            exchange
        );
    }
}
~~~

Nếu file site.css có content version, Mono có thể trả URL dạng:

~~~text
/assets/site-<content-hash>.css
~~~

Đây là URL được resolver chain tạo ra. Hash thực tế phụ thuộc nội dung file, nên không được hardcode vào HTML hoặc test.

### 10.1. WebFlux không tự rewrite URL trong mọi view

Khác với một số khả năng của Spring MVC, WebFlux không có cơ chế transparent URL rewriting cho mọi view technology thông qua non-blocking resolver chain.

Vì vậy, khi cần URL versioned trong HTML hoặc response JSON, ứng dụng có thể gọi ResourceUrlProvider trực tiếp và compose Mono vào pipeline hiện tại.

Không gọi block() trong WebFlux controller hoặc event-loop chỉ để lấy URL. Hãy trả về Mono và tiếp tục xử lý reactive.

### 10.2. CssLinkResourceTransformer và ResourceUrlProvider

CssLinkResourceTransformer có thể dùng ResourceUrlProvider để viết lại link trong CSS. Ví dụ site.css tham chiếu theme.css hoặc logo.svg; transformer có thể tạo URL công khai phù hợp với version strategy.

Nhờ vậy, việc version hóa không dừng ở file CSS chính mà còn áp dụng cho các tài nguyên được CSS tham chiếu.

## 11. Ví dụ hoàn chỉnh: Spring Boot 4.1.2, Java 17 và resource chain

Ví dụ này cấu hình một ứng dụng Spring WebFlux để:

- Phục vụ asset từ classpath:/static/assets/.
- Tạo URL versioned dựa trên content hash.
- Dùng CssLinkResourceTransformer cho link trong CSS.
- Dùng ResourceUrlProvider để trả URL công khai.
- Bật cache nội bộ cho resource chain.
- Đặt Cache-Control dài cho asset có version.

Ví dụ sử dụng **Spring Boot 4.1.2**, **Spring Framework 7.0.10** và **Java 17+**. Spring Boot 4.1.2 quản lý Spring Framework 7.0.10, là phiên bản đã vượt các mốc sửa lỗi static-resource được nêu ở phần bảo mật.

### 11.1. Cấu trúc project

~~~text
webflux-static-chain-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/staticchain/
    │   │       ├── StaticResourcesApplication.java
    │   │       ├── StaticResourceConfiguration.java
    │   │       └── AssetUrlController.java
    │   └── resources/
    │       ├── application.properties
    │       └── static/
    │           └── assets/
    │               ├── site.css
    │               ├── theme.css
    │               └── logo.svg
    └── test/
        └── java/
            └── com/example/staticchain/
                └── StaticResourceIntegrationTest.java
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-static-chain-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Không cần khai báo riêng phiên bản Spring Framework vì Spring Boot dependency management cung cấp phiên bản tương thích.

### 11.3. StaticResourcesApplication.java

~~~java
package com.example.staticchain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StaticResourcesApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            StaticResourcesApplication.class,
            args
        );
    }
}
~~~

### 11.4. StaticResourceConfiguration.java

~~~java
package com.example.staticchain;

import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.reactive.resource.CssLinkResourceTransformer;
import org.springframework.web.reactive.resource.VersionResourceResolver;

@Configuration
public class StaticResourceConfiguration
        implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(
            ResourceHandlerRegistry registry) {

        registry.addResourceHandler("/assets/**")
            .addResourceLocations("classpath:/static/assets/")
            .setCacheControl(
                CacheControl.maxAge(365, TimeUnit.DAYS)
                    .cachePublic()
            )
            .resourceChain(true)
            .addResolver(
                new VersionResourceResolver()
                    .addContentVersionStrategy("/**")
            )
            .addTransformer(
                new CssLinkResourceTransformer()
            );
    }
}
~~~

Giải thích:

1. Request bắt đầu bằng /assets/ được chuyển tới resource handler.
2. File được tìm trong classpath:/static/assets/.
3. VersionResourceResolver tính content hash và thêm vào tên URL công khai.
4. CssLinkResourceTransformer viết lại link asset trong CSS khi cần.
5. resourceChain(true) bật cache nội bộ của resolver/transformer.
6. Cache-Control cho phép browser và proxy cache asset công khai trong thời gian dài.

Ví dụ này không bật EncodedResourceResolver vì project chưa cung cấp file .gz hoặc .br. Nếu build pipeline tạo các biến thể nén, có thể thêm EncodedResourceResolver trước VersionResourceResolver.

### 11.5. AssetUrlController.java

~~~java
package com.example.staticchain;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.resource.ResourceUrlProvider;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class AssetUrlController {

    private final ResourceUrlProvider resourceUrlProvider;

    public AssetUrlController(
            ResourceUrlProvider resourceUrlProvider) {
        this.resourceUrlProvider = resourceUrlProvider;
    }

    @GetMapping(
        value = "/asset-url",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> assetUrl(ServerWebExchange exchange) {
        return resourceUrlProvider.getForUriString(
                "/assets/site.css",
                exchange
            )
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND,
                    "Static asset not found"
                )
            ));
    }
}
~~~

Controller trả Mono<String>. ResourceUrlProvider chạy qua resolver chain và tạo URL versioned. Nếu Resource không tồn tại hoặc không thể resolve, endpoint trả lỗi 404.

### 11.6. application.properties

~~~properties
spring.application.name=webflux-static-chain-demo
server.port=8080
~~~

Không cần tự cấu hình static-path-pattern vì ví dụ đăng ký mapping /assets/** bằng WebFluxConfigurer.

### 11.7. site.css

Tạo file src/main/resources/static/assets/site.css:

~~~css
@import url("./theme.css");

body {
    font-family: Arial, sans-serif;
    background: #f5f7fa;
}

.logo {
    width: 96px;
    height: 96px;
    background-image: url("./logo.svg");
}
~~~

### 11.8. theme.css

Tạo file src/main/resources/static/assets/theme.css:

~~~css
:root {
    --brand-color: #1769aa;
}

h1 {
    color: var(--brand-color);
}
~~~

### 11.9. logo.svg

Tạo file src/main/resources/static/assets/logo.svg:

~~~xml
<svg xmlns="http://www.w3.org/2000/svg"
     width="96"
     height="96"
     viewBox="0 0 96 96">
    <circle cx="48" cy="48" r="44" fill="#1769aa"/>
    <path d="M25 50 L42 67 L73 31"
          fill="none"
          stroke="#ffffff"
          stroke-width="8"
          stroke-linecap="round"
          stroke-linejoin="round"/>
</svg>
~~~

CSS transformer có thể xử lý các link CSS tham chiếu tới theme.css và logo.svg để tạo URL phù hợp với resolver chain.

### 11.10. Kiểm thử bằng WebTestClient

Tệp StaticResourceIntegrationTest.java:

~~~java
package com.example.staticchain;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class StaticResourceIntegrationTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .build();
    }

    @Test
    void resolvesVersionedUrlAndServesCss() {
        String assetPath = client.get()
            .uri("/asset-url")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_PLAIN)
            .expectBody(String.class)
            .returnResult()
            .getResponseBody();

        assertNotNull(assetPath);
        assertTrue(
            assetPath.matches(
                "/assets/site-[0-9a-f]{32}\\.css"
            )
        );

        client.get()
            .uri(assetPath)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.valueOf("text/css"))
            .expectHeader()
                .exists("Cache-Control")
            .expectBody(String.class)
            .value(body ->
                assertTrue(body.contains("font-family"))
            );
    }
}
~~~

Test thực hiện hai bước:

1. Gọi /asset-url để lấy URL có content hash do ResourceUrlProvider tạo.
2. Dùng URL đó tải CSS và xác nhận response 200, media type CSS, Cache-Control và nội dung mong đợi.

Hash được tạo từ nội dung file nên test kiểm tra định dạng thay vì hardcode một hash cố định.

### 11.11. Chạy ứng dụng

Yêu cầu JDK 17+ và Maven tương thích với Spring Boot 4.1.2:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Lấy URL versioned:

~~~bash
curl -i http://localhost:8080/asset-url
~~~

Body trả về có dạng:

~~~text
/assets/site-<content-hash>.css
~~~

Đây là dạng minh họa; hash thực tế được tính từ nội dung site.css.

Có thể lấy đường dẫn từ endpoint rồi dùng nó trong request tiếp theo:

~~~bash
ASSET_PATH=$(curl -fsS http://localhost:8080/asset-url)
curl -i "http://localhost:8080$ASSET_PATH"
~~~

Response dự kiến có status 200, Content-Type text/css và Cache-Control phù hợp. Khi nội dung site.css thay đổi, URL do /asset-url trả về sẽ thay đổi theo content hash.

Dừng ứng dụng bằng Ctrl+C.

## 12. Ví dụ cấu hình versioning và encoded resources

Nếu hệ thống build tạo sẵn asset nén, có thể mở rộng resource chain:

~~~java
registry.addResourceHandler("/assets/**")
    .addResourceLocations("classpath:/static/assets/")
    .setCacheControl(
        CacheControl.maxAge(365, TimeUnit.DAYS).cachePublic()
    )
    .resourceChain(true)
    .addResolver(new EncodedResourceResolver())
    .addResolver(
        new VersionResourceResolver()
            .addContentVersionStrategy("/**/*.css", "/**/*.svg")
            .addFixedVersionStrategy(
                "v2026.11",
                "/**/*.js"
            )
    )
    .addTransformer(new CssLinkResourceTransformer());
~~~

Trong chuỗi này:

- EncodedResourceResolver được đặt trước để chọn biến thể encoding phù hợp.
- VersionResourceResolver xử lý URL version.
- Content-based versioning được áp dụng cho CSS/SVG.
- Fixed version được áp dụng cho JavaScript trong ví dụ.
- CssLinkResourceTransformer viết lại các link CSS.

Chỉ cấu hình encoded resolver khi có file nén tương ứng và đã kiểm tra response Content-Encoding, Vary và nội dung thực tế bằng browser/client.

## 13. Cache và vận hành trong production

### 13.1. Tách policy theo loại tài nguyên

Không nên áp một max-age rất dài cho tất cả URL static nếu URL không có version. Hãy chọn policy dựa trên cách ứng dụng cập nhật nội dung.

Với URL versioned, max-age dài là hợp lý vì nội dung mới tạo URL mới. Với URL cố định, dùng thời gian cache ngắn hoặc revalidation để client phát hiện thay đổi.

### 13.2. Dùng cache nội bộ có kiểm soát

Resource chain cache giúp giảm công việc resolve và transform. Tuy nhiên, nếu file thay đổi khi ứng dụng đang chạy, cache có thể giữ kết quả cũ cho tới khi bị evict hoặc ứng dụng restart.

Trong production, static assets thường được đóng gói bất biến cùng build, do đó cache nội bộ phù hợp. Trong development, tắt cache chain hoặc khởi động lại khi asset thay đổi.

### 13.3. Không dùng chung cache giữa public và private

Spring Framework từng có advisory về việc dùng chung cache cho nhiều resource handler có location và chính sách xác thực khác nhau. Nếu public resource được resolve trước và cache chia sẻ với protected handler, nội dung bảo vệ có thể bị lộ trong một số cấu hình.

Hãy:

- Dùng cache tách biệt cho từng security boundary.
- Không dùng chung cache resolver giữa handler công khai và handler yêu cầu authentication.
- Đặt authorization trước khi phục vụ nội dung riêng tư.
- Tránh biến private document thành static URL công khai.
- Dùng Cache-Control phù hợp với nội dung nhạy cảm.

### 13.4. Giám sát

Các chỉ số hữu ích:

- Số request static resource theo URL pattern.
- Tỷ lệ 200, 304 và 404.
- Thời gian resolve Resource.
- Cache hit/miss của resource chain nếu có instrumentation.
- Lỗi đọc file và lỗi quyền filesystem.
- Tỷ lệ request có Accept-Encoding và content encoding được chọn.
- Số lần client yêu cầu URL version không tồn tại.

Không log toàn bộ nội dung file hoặc dữ liệu riêng tư khi debug static resource.

## 14. Bảo mật: path traversal và các advisory liên quan

Static resource handler là một ranh giới bảo mật. Nếu location quá rộng hoặc resolver bị cấu hình sai, request path có thể bị lợi dụng để truy cập file ngoài phạm vi dự kiến.

### 14.1. Chỉ phục vụ thư mục công khai

Ví dụ location phù hợp:

~~~java
.addResourceLocations("file:/srv/www/public/")
~~~

Không dùng:

~~~java
.addResourceLocations("file:/")
~~~

hoặc thư mục chứa toàn bộ dữ liệu ứng dụng, secret, file cấu hình, upload riêng tư.

Process của ứng dụng chỉ nên có quyền đọc đúng thư mục cần phục vụ. Hạn chế quyền filesystem làm giảm tác động nếu có lỗi ở tầng ứng dụng.

### 14.2. Không tự ghép request path thành filesystem path

Tránh viết controller kiểu:

~~~java
Path path = Paths.get("/srv/www/" + requestPath);
Resource resource = new FileSystemResource(path);
~~~

Cách này có nguy cơ path traversal, symlink escape và sai khác giữa các kiểu normalize path.

Nếu phải phục vụ file động theo ID, hãy tra metadata trong service, kiểm tra authorization, giới hạn root path và tạo Resource từ đường dẫn đã được xác minh. Không để client gửi một đường dẫn filesystem tùy ý.

### 14.3. CVE-2024-38816: functional static resources

Spring đã công bố CVE-2024-38816 liên quan WebFlux.fn và WebMvc.fn khi đồng thời dùng RouterFunctions để phục vụ static resources và cấu hình FileSystemResource location trong các phiên bản bị ảnh hưởng.

Các phiên bản Spring Framework 6.1.0 đến 6.1.12 bị ảnh hưởng; bản sửa trong nhánh 6.1 là 6.1.13. Khi dùng functional endpoint phục vụ filesystem resource, phải dùng phiên bản đã vá và kiểm tra security configuration.

### 14.4. CVE-2026-22741: encoded resource cache poisoning

Advisory này liên quan cấu hình resource chain bật caching cùng EncodedResourceResolver trong các phiên bản bị ảnh hưởng. Khi cache còn rỗng, request có thể làm cache giữ biến thể encoding không đúng, ảnh hưởng việc phục vụ asset cho client khác.

Các bản sửa OSS được công bố gồm Spring Framework 7.0.7 và 6.2.18. Các bản vá mới hơn đã bao gồm sửa lỗi này.

### 14.5. CVE-2026-41841: thông tin protected resource qua shared cache

Advisory này mô tả tình huống có nhiều resource handler dùng location khác nhau, ít nhất một handler yêu cầu authentication, nhưng các handler lại dùng chung cache. Một Resource công khai có cùng tên có thể được resolve trước và cache, tạo điều kiện để nội dung protected bị lộ trong cấu hình bị ảnh hưởng.

Các bản sửa OSS được công bố gồm Spring Framework 7.0.8 và 6.2.19. Cách phòng vệ trong thiết kế vẫn là tách cache theo security boundary và không chia sẻ cache giữa handler public/private.

### 14.6. CVE-2026-41843: path traversal qua versioned filesystem resources

Advisory này liên quan static resources được phục vụ từ filesystem cùng với versioned resource support. Trong các phiên bản bị ảnh hưởng, request có thể được tạo để resolve file bên ngoài configured locations khi attacker biết hoặc đoán được metadata cần thiết.

Các bản sửa OSS được công bố gồm Spring Framework 7.0.8 và 6.2.19. Bản 6.1.28 chỉ có trong Enterprise Support. Hãy nâng cấp lên patch mới nhất của nhánh đang được hỗ trợ.

### 14.7. Phiên bản sử dụng trong ví dụ

Ví dụ dùng Spring Boot **4.1.2**, quản lý Spring Framework **7.0.10** và yêu cầu Java 17+. Đây là phiên bản Framework mới hơn các mốc sửa lỗi 7.0.8 đã nêu.

Nếu ứng dụng đang ở Spring Framework 6.2.x, tối thiểu cần nhánh đã sửa 6.2.19 cho các advisory 2026 nêu trên; ưu tiên nâng cấp theo nhánh Spring được hỗ trợ. Nhánh 6.1 đã kết thúc OSS support và bản 6.1.28 là Enterprise Support.

Không coi việc nâng version là lý do để bỏ qua path validation, location boundary hoặc cache isolation. Luôn kiểm tra dependency tree thực tế của ứng dụng vì BOM, override hoặc dependency bắc cầu có thể kéo về một phiên bản Framework khác dự kiến.

## 15. RouterFunctions.resources và ResourceHandlerRegistry

WebFlux có thể phục vụ static resources bằng functional routing thông qua RouterFunctions.resources(...). Tuy nhiên, với static resources thông thường, **ResourceHandlerRegistry** thường là lựa chọn dễ cấu hình và tích hợp hơn.

So sánh:

| Cách | Phù hợp khi |
| --- | --- |
| **ResourceHandlerRegistry** | Phục vụ static asset theo URL pattern và location, cần resolver/transformer/cache chain |
| **RouterFunctions.resources** | Ứng dụng dùng functional routing và cần gắn resource route vào RouterFunction |
| **Controller trả Resource** | Tài nguyên được xác định bởi logic nghiệp vụ hoặc authorization theo request |

Nếu dùng RouterFunctions.resources với FileSystemResource, phải đặc biệt chú ý advisory CVE-2024-38816 và phiên bản Framework đã vá. Không tự tạo functional resource handler để thay thế các boundary check sẵn có mà không có lý do.

## 16. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Request /assets/site.css trả 404 | URL pattern hoặc location không khớp | Kiểm tra addResourceHandler, addResourceLocations và vị trí file trong classpath |
| Đã đổi static-path-pattern nhưng URL cũ không hoạt động | Mapping đã chuyển sang prefix mới | Dùng URL theo pattern mới |
| Đặt static-locations nhưng mất file trong /static | Thuộc tính thay thế danh sách location mặc định | Khai báo lại mọi location cần dùng |
| File trong filesystem không được tìm thấy | Location thiếu file URI hoặc không trỏ tới thư mục | Dùng file:/đường-dẫn-thư-mục/ và kiểm tra quyền đọc |
| File cùng tên từ location khác được trả về | Nhiều location được tìm theo thứ tự | Sắp xếp location và tránh tên file trùng ngoài ý muốn |
| URL versioned không resolve | Hash trong URL không khớp nội dung hiện tại | Tạo URL bằng ResourceUrlProvider, không hardcode hash |
| CSS dùng asset URL cũ | Chưa cấu hình CssLinkResourceTransformer | Thêm transformer và kiểm tra link tương đối trong CSS |
| Version hash thay đổi theo file nén | EncodedResourceResolver đứng sai vị trí | Đặt EncodedResourceResolver trước VersionResourceResolver |
| Browser vẫn hiển thị CSS cũ | URL không version và Cache-Control quá dài | Dùng content hash hoặc giảm max-age/revalidate |
| File đã thay đổi nhưng resource chain vẫn trả bản cũ | Cache nội bộ giữ kết quả resolve/transform | Tắt cache trong development hoặc restart/evict theo chính sách |
| Static handler trả file private | Location công khai chứa dữ liệu bảo vệ hoặc authorization thiếu | Giới hạn location và dùng endpoint có authorization |
| CSS link không được version hóa | Thiếu CssLinkResourceTransformer hoặc resolver mapping không khớp | Kiểm tra transformer và path pattern |
| WebJars URL không có version bị 404 | Thiếu webjars-locator-core | Dùng URL có version hoặc thêm locator nếu thật sự cần |
| Tên URL versioned không tương thích JS module loader | Dùng content hash cho module import | Dùng FixedVersionStrategy hoặc build-time manifest |
| Cache public giữ nội dung cá nhân | Cache policy không phù hợp | Dùng private/no-store và kiểm soát authentication |
| Path traversal qua filesystem resource | Location quá rộng, custom resolver không an toàn hoặc Framework cũ | Giới hạn root, dùng resolver chuẩn và nâng cấp bản vá |
| Protected resource bị lộ qua cache | Dùng chung cache giữa public/private handlers | Tách cache theo security boundary |
| Static response không có 304 | Validator hoặc conditional request chưa phù hợp | Kiểm tra Last-Modified, ETag, If-Modified-Since và If-None-Match |
| Asset nén được chọn sai | Resolver, cache hoặc file variant không nhất quán | Kiểm tra Accept-Encoding, Content-Encoding và thứ tự resolver |
| URL /assets/** đụng route API | Pattern quá rộng hoặc route không rõ ràng | Dùng prefix riêng cho API và static resources |

## 17. Checklist trước khi triển khai

- Static resources nằm trong location công khai có chủ đích?
- URL pattern có rõ ràng và không chồng lấn route nghiệp vụ?
- Các location có thứ tự phù hợp?
- Không expose filesystem root hoặc thư mục chứa secrets?
- ResourceHandlerRegistry được dùng đúng với nhu cầu?
- PathResourceResolver giữ boundary của location?
- ResourceResolver chain có đúng thứ tự?
- EncodedResourceResolver đứng trước VersionResourceResolver khi dùng content-based versioning?
- CssLinkResourceTransformer có được thêm nếu CSS chứa link cần version hóa?
- ResourceUrlProvider được dùng để tạo URL versioned?
- ContentVersionStrategy có phù hợp với loại asset?
- JavaScript module loader có cần FixedVersionStrategy?
- Cache-Control phù hợp với public/private và khả năng thay đổi nội dung?
- Resource-chain cache có phù hợp với môi trường?
- Cache giữa các security boundary đã được tách?
- Last-Modified/ETag/conditional request đã được kiểm tra?
- WebJars versioned URL có được ưu tiên?
- Spring Framework đã được cập nhật patch bảo mật?
- Có integration test cho URL resolve và nội dung Resource?
- Có kiểm thử path traversal và cache isolation trong ứng dụng có filesystem/private resources?
- Có theo dõi 404, 304, cache hit/miss và lỗi đọc file?

## 18. Bài tập thực hành

**Bài 1 — Static resource mặc định:** Đặt index.html và css/site.css trong classpath:/static. Chạy ứng dụng và truy cập trực tiếp bằng browser/curl.

**Bài 2 — Custom pattern:** Dùng spring.webflux.static-path-pattern để chuyển URL từ /** sang /resources/**. Xác minh URL mới.

**Bài 3 — Custom location:** Cấu hình classpath:/public-assets/ và file:/srv/www/. Kiểm tra thứ tự tìm kiếm khi hai location có cùng tên file.

**Bài 4 — ResourceHandlerRegistry:** Tạo WebFluxConfigurer và đăng ký /assets/**. Kiểm tra file được phục vụ từ đúng classpath location.

**Bài 5 — PathResourceResolver:** Tạo request có path traversal pattern. Xác minh Resource ngoài allowed location không được trả về.

**Bài 6 — Content versioning:** Cấu hình VersionResourceResolver với ContentVersionStrategy. Dùng ResourceUrlProvider lấy URL có hash và tải file.

**Bài 7 — Fixed versioning:** Cấu hình FixedVersionStrategy cho JavaScript module. Kiểm tra URL có version prefix theo release.

**Bài 8 — CSS transformer:** Tạo CSS tham chiếu theme.css và logo.svg. Thêm CssLinkResourceTransformer và quan sát link được viết lại.

**Bài 9 — Encoded resources:** Tạo site.css.gz và cấu hình EncodedResourceResolver trước VersionResourceResolver. Gửi Accept-Encoding: gzip và quan sát Content-Encoding.

**Bài 10 — Cache-Control:** Cấu hình max-age ngắn cho URL không version và max-age dài cho URL có content hash. So sánh response headers.

**Bài 11 — Last-Modified:** Gửi request đầu tiên để lấy Last-Modified, sau đó gửi If-Modified-Since. Kiểm tra response 304 khi file không đổi.

**Bài 12 — Resource-chain cache:** Chạy với resourceChain(true), thay đổi file trong development và quan sát cache. Thử resourceChain(false).

**Bài 13 — ResourceUrlProvider:** Tạo endpoint trả Mono<String> từ getForUriString và dùng URL kết quả trong HTML hoặc response JSON.

**Bài 14 — WebJars:** Thêm một WebJar, truy cập URL có version và so sánh với URL không version khi có webjars-locator-core.

**Bài 15 — Cache isolation:** Tạo hai resource handler public/private trong một test application. Kiểm tra không dùng chung cache và không thể lấy protected resource qua public mapping.

**Bài 16 — Security upgrade:** Kiểm tra dependency tree để xác nhận Spring Framework đang dùng nằm trên patch fix của các static-resource advisory.

## 19. Ghi nhớ

Spring WebFlux phục vụ static resources bằng **ResourceWebHandler**. **ResourceHandlerRegistry** đăng ký URL pattern và location; **ResourceResolver** tìm Resource; **ResourceTransformer** biến đổi Resource trước khi response được ghi.

**PathResourceResolver** là resolver nền tảng, kiểm tra Resource nằm trong location được phép. **VersionResourceResolver** tạo URL có content hash hoặc fixed version. **EncodedResourceResolver** chọn biến thể nén theo Accept-Encoding. **CssLinkResourceTransformer** viết lại các link trong CSS. **ResourceUrlProvider** tạo URL công khai bằng resolver chain.

**Cache-Control** điều khiển cache ở browser/proxy; **resourceChain(true)** bật cache resolve/transform nội bộ. Khi dùng content versioning, asset có thể cache lâu vì nội dung thay đổi sẽ tạo URL mới. Nếu dùng encoded resource và versioning, hãy đặt EncodedResourceResolver trước VersionResourceResolver. Không chia sẻ cache giữa public và protected resource handlers.

Giới hạn location, bảo vệ path boundary, cập nhật Spring Framework và kiểm tra các advisory CVE-2024-38816, CVE-2026-22741, CVE-2026-41841 và CVE-2026-41843 trước khi triển khai static-resource chain.

## 20. Tài liệu tham khảo

- Spring Framework Reference — WebFlux Configuration, Static Resources: https://docs.spring.io/spring/reference/6.2/web/webflux/config.html
- Spring Framework API — ResourceHandlerRegistry: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/config/ResourceHandlerRegistry.html
- Spring Framework API — ResourceHandlerRegistration: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/config/ResourceHandlerRegistration.html
- Spring Framework API — ResourceWebHandler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/resource/ResourceWebHandler.html
- Spring Framework API — ResourceResolver: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/resource/ResourceResolver.html
- Spring Framework API — PathResourceResolver: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/resource/PathResourceResolver.html
- Spring Framework API — VersionResourceResolver: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/resource/VersionResourceResolver.html
- Spring Framework API — EncodedResourceResolver: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/resource/EncodedResourceResolver.html
- Spring Framework API — CssLinkResourceTransformer: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/resource/CssLinkResourceTransformer.html
- Spring Framework API — ResourceUrlProvider: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/resource/ResourceUrlProvider.html
- Spring Framework Reference — WebFlux HTTP Caching: https://docs.spring.io/spring/reference/6.2/web/webflux/caching.html
- Spring Boot Reference — Reactive Web Applications / Static Content: https://docs.spring.io/spring-boot/4.1/reference/web/reactive.html
- Spring Security Advisory — CVE-2024-38816: https://spring.io/security/cve-2024-38816/
- Spring Security Advisory — CVE-2026-22741: https://spring.io/security/cve-2026-22741/
- Spring Security Advisory — CVE-2026-41841: https://spring.io/security/cve-2026-41841/
- Spring Security Advisory — CVE-2026-41843: https://spring.io/security/cve-2026-41843/
- Spring Boot 4.1.2 Release: https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/
- RFC 9111 — HTTP Caching: https://www.rfc-editor.org/rfc/rfc9111.html

# Phục vụ Resource và xử lý Range request trong Spring WebFlux

## 1. Bài toán và mục tiêu

Ứng dụng WebFlux thường phải trả về ảnh, PDF, video, tệp âm thanh, bản xuất dữ liệu hoặc tài liệu tải xuống. Spring biểu diễn các nguồn này bằng abstraction **org.springframework.core.io.Resource**. Controller mô tả Resource cần trả về; WebFlux dùng HTTP message writer để ghi nội dung thành response.

Với tệp lớn, client thường không muốn tải toàn bộ nội dung trong một lần. Trình duyệt, trình phát media hoặc công cụ download có thể gửi header **Range** để yêu cầu một đoạn byte:

~~~http
GET /api/files/sample HTTP/1.1
Host: localhost:8080
Range: bytes=2-5
~~~

Nếu tài nguyên có 10 byte, server có thể trả về bốn byte ở vị trí 2 đến 5 với status **206 Partial Content** và header **Content-Range: bytes 2-5/10**.

Spring WebFlux hỗ trợ byte-range theo **RFC 9110**. Với controller annotation trả về **Resource** hoặc **ResponseEntity<Resource>**, functional endpoint phục vụ Resource và static resource handler, Spring có thể xử lý Range tự động. Với controller, có hai điều kiện cần nhớ: Resource không được là **InputStreamResource**; nếu trả **ResponseEntity<Resource>**, status ban đầu phải là **200 OK** để cơ chế Range của framework được áp dụng.

Sau bài học, bạn có thể:

- Hiểu Resource abstraction và chọn implementation phù hợp với nguồn dữ liệu.
- Nắm ý nghĩa của Range, Accept-Ranges, Content-Range, 206 và 416.
- Phục vụ Resource qua annotated controller, functional endpoint và static resource handler.
- Hiểu vai trò của HttpRange, ResourceRegion, ResourceRegionEncoder và ResourceHttpMessageWriter.
- Kiểm tra byte range bằng curl và WebTestClient.
- Kết hợp Range với cache, ETag, Last-Modified và điều kiện HTTP.
- Phục vụ tệp an toàn, tránh path traversal, lộ dữ liệu và tiêu thụ bộ nhớ quá mức.

## 2. Resource abstraction trong Spring

**Resource** là interface của Spring để truy cập một tài nguyên. Nó cung cấp các thao tác như kiểm tra tồn tại, khả năng đọc, lấy tên tệp, độ dài, thời gian sửa đổi và mở InputStream. Nhờ abstraction này, controller không cần biết dữ liệu nằm trong classpath, filesystem hay một URL.

| Loại | Nguồn dữ liệu | Khi phù hợp |
| --- | --- | --- |
| **ClassPathResource** | Tài nguyên trong classpath hoặc JAR | Tệp mẫu, tài liệu đóng gói cùng ứng dụng, static resource |
| **FileSystemResource** | Đường dẫn trên filesystem | Tệp được lưu trong thư mục dữ liệu |
| **UrlResource** | URL hoặc URI | Tài nguyên được truy cập qua URL theo cơ chế Resource |
| **ByteArrayResource** | Mảng byte trong bộ nhớ | Nội dung nhỏ đã có sẵn trong byte[] |
| **InputStreamResource** | InputStream đã mở | Luồng chỉ đọc một lần, không phù hợp cho Range |
| **PathResource** | java.nio.file.Path | Làm việc trực tiếp với Path |

Ví dụ:

~~~java
Resource classpath = new ClassPathResource("files/manual.pdf");

Resource file = new FileSystemResource(
    "/srv/app-data/manual.pdf"
);

Resource bytes = new ByteArrayResource(
    "Hello WebFlux".getBytes(StandardCharsets.UTF_8)
);
~~~

Đây là snippet cần import các class Spring và Java tương ứng.

### 2.1. Chọn Resource có thể đọc lặp lại

Để xử lý byte range, framework phải có khả năng truy cập các đoạn khác nhau của cùng một tài nguyên. **InputStreamResource** thường đại diện cho một stream đã mở và không bảo đảm có thể đọc lại hoặc nhảy đến vị trí bất kỳ. Vì vậy, Spring WebFlux không hỗ trợ Range cho loại Resource này.

Nên chọn:

- **FileSystemResource** hoặc **PathResource** cho tệp trên ổ đĩa.
- **ClassPathResource** cho tệp đóng gói trong ứng dụng.
- **ByteArrayResource** cho nội dung nhỏ nằm trong bộ nhớ.
- Một Resource implementation tùy biến có khả năng mở stream mới và hỗ trợ đọc vùng dữ liệu theo cách phù hợp.

Không tạo InputStreamResource từ một stream duy nhất rồi mong framework đọc lại nhiều lần để phục vụ Range. Với file lớn, tránh nạp toàn bộ tệp vào byte[]; hãy dùng Resource dựa trên file hoặc nguồn hỗ trợ đọc theo vùng.

### 2.2. Resource và InputStream khác nhau

Một Resource là mô tả về nơi lấy dữ liệu; nó chưa nhất thiết đã mở stream. Ví dụ ClassPathResource có thể mở InputStream mới mỗi khi cần. Ngược lại, một InputStream đã mở là trạng thái tiêu thụ dữ liệu; khi đọc đến cuối, stream không tự quay lại đầu.

Sự khác biệt này quan trọng khi:

- Framework cần xác định content length.
- Client gửi nhiều request Range cho cùng một tệp.
- Server cần đọc một vùng byte ở giữa tệp.
- Client ngắt kết nối rồi gửi request mới để tải tiếp.
- Resource được dùng đồng thời cho nhiều request.

### 2.3. Content length và filename

Resource có các method thường dùng:

- **exists()**: tài nguyên có tồn tại không.
- **isReadable()**: tài nguyên có thể đọc không.
- **contentLength()**: độ dài nội dung theo byte.
- **lastModified()**: thời điểm sửa đổi cuối cùng.
- **getFilename()**: tên tệp nếu có.
- **getInputStream()**: mở stream đọc nội dung.

Độ dài là yếu tố cần thiết để tính byte range và Content-Range. Nếu Resource không xác định được độ dài, một số thao tác Range có thể không thực hiện được theo cách mong muốn. Với tệp tải xuống, hãy dùng implementation cung cấp kích thước đáng tin cậy.

## 3. HTTP Range request hoạt động thế nào?

Range request cho phép client yêu cầu một hoặc nhiều đoạn của representation. Với byte range, chỉ số byte bắt đầu từ **0** và vị trí cuối là **inclusive**.

Giả sử nội dung là:

~~~text
0123456789
~~~

Tài nguyên có 10 byte. Các ví dụ:

| Header Range | Ý nghĩa | Byte được yêu cầu |
| --- | --- | --- |
| **bytes=0-4** | Từ byte 0 đến byte 4 | 01234 |
| **bytes=2-5** | Từ byte 2 đến byte 5 | 2345 |
| **bytes=5-** | Từ byte 5 đến cuối | 56789 |
| **bytes=-3** | Ba byte cuối | 789 |
| **bytes=0-1,8-9** | Hai đoạn riêng biệt | 01 và 89 |

Các dạng range quan trọng:

- **Closed range**: bytes=100-199, chỉ định cả vị trí đầu và cuối.
- **Open-ended range**: bytes=100-, lấy từ vị trí 100 đến cuối representation.
- **Suffix range**: bytes=-500, lấy 500 byte cuối.
- **Multiple ranges**: bytes=0-99,200-299, yêu cầu nhiều đoạn trong cùng một request.

Byte range được tính trên **byte của representation**, không phải số ký tự Java. Với UTF-8, một ký tự có thể chiếm nhiều byte; một Range có thể bắt đầu hoặc kết thúc giữa một ký tự nhiều byte. Vì vậy, đừng diễn giải offset byte thành chỉ số ký tự.

### 3.1. Các header quan trọng

| Header | Hướng | Vai trò |
| --- | --- | --- |
| **Range** | Request | Client yêu cầu một hoặc nhiều đoạn byte |
| **Accept-Ranges** | Response | Server thông báo đơn vị range có thể hỗ trợ, thường là bytes |
| **Content-Range** | Response | Chỉ ra đoạn được gửi và tổng độ dài representation |
| **Content-Length** | Response | Độ dài body của response hiện tại |
| **Content-Type** | Response | Kiểu nội dung của representation hoặc multipart response |

**Accept-Ranges: bytes** là tín hiệu cho client biết server hỗ trợ byte range. Đây là thông tin mang tính tư vấn; client vẫn có thể gửi Range kể cả khi chưa nhận header này.

### 3.2. Status 200, 206 và 416

- **200 OK**: server trả toàn bộ representation, thường khi không có Range hoặc server không áp dụng Range.
- **206 Partial Content**: server trả một hoặc nhiều đoạn theo Range hợp lệ và có thể đáp ứng.
- **416 Range Not Satisfiable**: không có đoạn nào trong tập range có thể đáp ứng, hoặc range bị từ chối theo chính sách server.

Ví dụ response cho bytes=2-5:

~~~http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Type: text/plain
Content-Range: bytes 2-5/10
Content-Length: 4

2345
~~~

**Content-Range: bytes 2-5/10** nghĩa là response chứa byte 2 đến 5 của một representation dài tổng cộng 10 byte. Content-Length là 4 vì body của response này chỉ có bốn byte.

Khi range không thể đáp ứng, RFC 9110 khuyến nghị server trả Content-Range dạng **bytes */10** trong response 416 để client biết kích thước hiện tại của representation. Hãy kiểm tra header thực tế của phiên bản framework/server đang dùng nếu ứng dụng cần dựa vào thông tin này.

### 3.3. Multiple ranges và multipart/byteranges

Khi client gửi:

~~~http
Range: bytes=0-1,8-9
~~~

Server có thể trả một response 206 với Content-Type:

~~~http
Content-Type: multipart/byteranges; boundary=...
~~~

Mỗi phần trong body multipart có header Content-Range riêng. Ở response nhiều phần, Content-Range không nằm ở header chung của HTTP response; nó nằm trong từng body part.

Boundary được server tạo động nên không nên viết test phụ thuộc một chuỗi boundary cố định. Hãy kiểm tra media type và nội dung các part theo contract.

### 3.4. Range chỉ áp dụng cho GET

Theo HTTP semantics, GET là method được định nghĩa để xử lý Range. Server phải bỏ qua Range nếu method không hỗ trợ range semantics. Không dùng Range để phân trang danh sách nghiệp vụ; hãy dùng query parameter/page token cho pagination.

## 4. Spring WebFlux xử lý Range tự động

Trong WebFlux, cơ chế chính gồm:

- **HttpRange**: parse Range header và biểu diễn một đoạn byte.
- **ResourceRegion**: mô tả một vùng của Resource bằng vị trí bắt đầu và số byte.
- **ResourceRegionEncoder**: encode một hoặc nhiều ResourceRegion.
- **ResourceHttpMessageWriter**: ghi Resource ra HTTP response; phía server hỗ trợ ghi một hoặc nhiều ResourceRegion theo Range request.

Khi controller trả Resource hoặc ResponseEntity<Resource>, WebFlux có thể nhận biết Range header, chuyển nó thành các ResourceRegion và ghi đúng đoạn dữ liệu. Static resource handler cũng có hỗ trợ này.

Điều kiện quan trọng với annotated controller:

1. Body response phải là **Resource** hoặc **ResponseEntity<Resource>**.
2. Resource không được là **InputStreamResource**.
3. Nếu trả ResponseEntity<Resource>, status của ResponseEntity phải là **200 OK**. Resource writer sẽ xử lý Range và điều chỉnh response thành 206 khi phù hợp.
4. Không tự đặt status 206 trong controller rồi kỳ vọng framework tiếp tục phân tích Range.

Ví dụ đúng:

~~~java
@GetMapping("/files/manual")
public ResponseEntity<Resource> manual() {
    Resource resource =
        new ClassPathResource("files/manual.pdf");

    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_PDF)
        .body(resource);
}
~~~

Khi client gửi Range hợp lệ, Spring có thể trả partial response tự động. Không cần tự cắt byte[] hoặc viết vòng lặp đọc file trong controller.

Ví dụ dễ sai:

~~~java
@GetMapping("/files/manual")
public ResponseEntity<Resource> manual() {
    Resource resource =
        new InputStreamResource(openManualStream());

    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_PDF)
        .body(resource);
}
~~~

InputStreamResource không phù hợp với Range vì stream không bảo đảm đọc lại hoặc truy cập vùng byte. Hãy trả một Resource có khả năng mở/đọc lại như FileSystemResource hoặc ClassPathResource.

### 4.1. ResourceHttpMessageWriter

**ResourceHttpMessageWriter** là HttpMessageWriter chuyên ghi Resource. Trong xử lý server-side, writer:

1. Đặt Accept-Ranges phù hợp.
2. Đọc các range từ request headers.
3. Khi không có Range, ghi toàn bộ Resource.
4. Khi có một range, tính vùng tương ứng và ghi một ResourceRegion.
5. Khi có nhiều range, encode các vùng thành multipart/byteranges.
6. Khi range sai cú pháp hoặc không thể đáp ứng, kết thúc response với status 416 theo logic writer.

Writer cũng xác định Content-Type và Content-Length khi có thể. Nếu response transport hỗ trợ zero-copy và Resource là file phù hợp, framework có thể sử dụng đường ghi tối ưu; trường hợp khác dùng encoder/DataBuffer.

Không nên tự tạo ResourceHttpMessageWriter trong controller. WebFlux đã cấu hình writer qua server codec configuration. Chỉ tùy chỉnh codec khi có yêu cầu tích hợp cụ thể và đã kiểm tra ảnh hưởng đến các Resource response khác.

### 4.2. HttpRange và ResourceRegion ở mức API

Khi cần xử lý Range trong một tầng tùy biến, có thể sử dụng các API:

~~~java
List<HttpRange> ranges = request.getHeaders().getRange();

List<ResourceRegion> regions =
    HttpRange.toResourceRegions(ranges, resource);
~~~

Đây là snippet cần import **org.springframework.http.HttpRange** và **org.springframework.core.io.support.ResourceRegion**. Phương thức **getRange()** phân tích Range header; **toResourceRegions(...)** chuyển các range thành vùng tương ứng với Resource.

Các API này là công cụ mức thấp. Nếu chỉ muốn phục vụ một file, trả Resource trực tiếp thường đơn giản hơn và tận dụng đầy đủ writer của WebFlux. Khi tự xử lý, phải kiểm tra lỗi parse, range không hợp lệ, số lượng range, content length và định dạng multipart response.

## 5. Phục vụ Resource trong annotated controller

Một controller có thể trả Resource trực tiếp:

~~~java
@RestController
@RequestMapping("/api")
public class DocumentController {

    @GetMapping(
        value = "/manual",
        produces = MediaType.APPLICATION_PDF_VALUE
    )
    public Resource manual() {
        return new ClassPathResource("files/manual.pdf");
    }
}
~~~

Hoặc dùng ResponseEntity<Resource> để kiểm soát status và headers:

~~~java
@GetMapping("/manual")
public ResponseEntity<Resource> manual() {
    Resource resource =
        new ClassPathResource("files/manual.pdf");

    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_PDF)
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            ContentDisposition.inline()
                .filename("manual.pdf")
                .build()
                .toString()
        )
        .body(resource);
}
~~~

Dùng **inline** khi muốn trình duyệt cố gắng hiển thị nội dung; dùng **attachment** khi muốn gợi ý tải xuống. Filename trong Content-Disposition phải được kiểm soát và encode đúng, đặc biệt nếu nó bắt nguồn từ dữ liệu người dùng.

### 5.1. Không tự đặt Content-Length khi không cần

Resource writer có thể xác định độ dài từ Resource và đặt Content-Length. Nếu controller tự đặt một con số sai, response có thể bị cắt, client chờ thêm dữ liệu hoặc range metadata không nhất quán.

Chỉ tự đặt Content-Length khi ứng dụng thực sự biết chính xác độ dài representation sẽ gửi. Với Range, Content-Length của 206 là kích thước đoạn được gửi, không phải tổng kích thước tệp.

### 5.2. Không tự cắt Resource trước khi trả về

Nếu controller tự đọc một đoạn byte rồi trả ByteArrayResource, Range request tiếp theo sẽ được tính trên mảng byte đã cắt, không còn trên file gốc. Điều này dễ tạo Content-Range sai hoặc làm client không thể ghép các phần.

Hãy trả Resource gốc cho writer xử lý, trừ khi ứng dụng đang xây dựng một representation riêng có semantics và metadata riêng.

## 6. Phục vụ Resource bằng functional endpoint

WebFlux functional endpoint cũng hỗ trợ Range khi handler trả một Resource.

~~~java
@Configuration
public class DocumentRoutes {

    @Bean
    RouterFunction<ServerResponse> documentRoutes() {
        return RouterFunctions.route()
            .GET("/functional/manual", request -> {
                Resource resource =
                    new ClassPathResource("files/manual.pdf");

                return ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_PDF)
                    .bodyValue(resource);
            })
            .build();
    }
}
~~~

Điểm quan trọng là body của ServerResponse là **Resource** và response được tạo với status 200. WebFlux có thể áp dụng Range ở message-writing layer.

Không đọc toàn bộ file thành byte[] trước khi gọi bodyValue nếu mục tiêu là phục vụ file lớn. Trả Resource giúp framework có thể đọc nội dung theo cơ chế phù hợp.

## 7. Phục vụ static resources

Nếu ứng dụng chỉ cần phục vụ ảnh, CSS, JavaScript, PDF tĩnh hoặc tài liệu đóng gói sẵn, có thể dùng static resource handler thay vì viết controller riêng cho từng file.

Spring Boot WebFlux mặc định phục vụ static resources từ một số vị trí classpath như:

- /static
- /public
- /resources
- /META-INF/resources

Có thể tùy chỉnh mapping bằng **WebFluxConfigurer**:

~~~java
@Configuration
public class StaticResourceConfiguration
        implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(
        ResourceHandlerRegistry registry
    ) {
        registry.addResourceHandler("/assets/**")
            .addResourceLocations("classpath:/static/")
            .setCacheControl(
                CacheControl.maxAge(1, TimeUnit.DAYS).cachePublic()
            );
    }
}
~~~

Đặt file tại:

~~~text
src/main/resources/static/
    logo.png
    guide.pdf
    app.css
~~~

Request:

~~~http
GET /assets/guide.pdf
Range: bytes=0-1023
~~~

ResourceWebHandler xử lý việc tìm Resource, áp dụng resolver/transformer nếu được cấu hình và ghi response qua ResourceHttpMessageWriter. Static resources cũng có hỗ trợ Range.

### 7.1. Cache-Control và Last-Modified

Static resource handler có thể đặt **Cache-Control** để hướng dẫn browser và proxy cache nội dung. Spring cũng có thể đánh giá **Last-Modified** dựa trên Resource. Nếu client gửi điều kiện phù hợp và nội dung chưa thay đổi, server có thể trả **304 Not Modified** mà không gửi body.

Cache duration phải phù hợp với khả năng thay đổi nội dung. Với file có URL versioned/hash, thời hạn cache dài thường phù hợp hơn. Với file cập nhật tại một URL cố định, cần thời hạn ngắn hoặc validator để tránh client giữ nội dung cũ quá lâu.

### 7.2. ResourceResolver và ResourceTransformer

Static resource handler hỗ trợ:

- **ResourceResolver**: tìm Resource từ request path hoặc thay đổi cách ánh xạ URL tới tài nguyên.
- **ResourceTransformer**: biến đổi Resource trước khi phục vụ, ví dụ thay URL trong CSS hoặc tối ưu đường dẫn asset.
- **VersionResourceResolver**: tạo URL có version/hash để cache hiệu quả.
- **PathResourceResolver**: resolver mặc định tìm Resource trong các location đã cấu hình.

Không thêm resolver tùy biến nếu chưa hiểu cách kiểm tra đường dẫn và allowed locations. Resolver phải giới hạn việc truy cập đúng thư mục/tài nguyên được phép.

## 8. Ví dụ hoàn chỉnh: WebFlux Resource endpoint và Range request

Ví dụ này dùng **Java 17+**, **Spring Boot 4.1.2** và Maven. Endpoint phục vụ một file text đúng 10 byte để dễ quan sát byte offset. File nằm trong classpath và là **ClassPathResource**, không phải InputStreamResource.

Cấu trúc:

~~~text
resource-range-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/rangedemo/
    │   │       ├── RangeDemoApplication.java
    │   │       └── SampleResourceController.java
    │   └── resources/
    │       ├── application.properties
    │       └── files/
    │           └── sample.txt
    └── test/
        └── java/
            └── com/example/rangedemo/
                └── SampleResourceControllerTest.java
~~~

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>resource-range-demo</artifactId>
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

Starter WebFlux cung cấp reactive web stack và embedded server mặc định. Starter test cung cấp JUnit Jupiter, Spring Test và WebTestClient. Không thêm starter MVC vào ví dụ này.

### 8.2. File mẫu sample.txt

Tạo file **src/main/resources/files/sample.txt** với nội dung chính xác:

~~~text
0123456789
~~~

File phải có đúng **10 byte ASCII**, không thêm newline ở cuối. Điều này giúp Content-Range và kết quả test có thể tính trực tiếp.

### 8.3. Application class

Tệp **RangeDemoApplication.java**:

~~~java
package com.example.rangedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RangeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            RangeDemoApplication.class,
            args
        );
    }
}
~~~

### 8.4. Controller trả Resource

Tệp **SampleResourceController.java**:

~~~java
package com.example.rangedemo;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/files")
public class SampleResourceController {

    @GetMapping(
        value = "/sample",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public ResponseEntity<Resource> sample() {
        Resource resource =
            new ClassPathResource("files/sample.txt");

        if (!resource.exists() || !resource.isReadable()) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "Sample resource not found"
            );
        }

        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .body(resource);
    }
}
~~~

Controller trả **ResponseEntity<Resource>** với status 200. Khi có Range header, WebFlux xử lý ở tầng message writer và có thể đổi status thành 206. Resource là ClassPathResource, đáp ứng điều kiện không dùng InputStreamResource.

Không tự đặt status PARTIAL_CONTENT trong controller. Không tự đọc request.getHeaders().getRange() trong ví dụ này vì writer đã đảm nhiệm việc đó.

### 8.5. application.properties

~~~properties
spring.application.name=resource-range-demo
server.port=8080
logging.level.com.example.rangedemo=INFO
~~~

### 8.6. Test bằng WebTestClient

Tệp **SampleResourceControllerTest.java**:

~~~java
package com.example.rangedemo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class SampleResourceControllerTest {

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToController(new SampleResourceController())
            .build();
    }

    @Test
    void returnsWholeResourceWithoutRange() {
        client.get()
            .uri("/api/files/sample")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_PLAIN)
            .expectBody(String.class)
            .isEqualTo("0123456789");
    }

    @Test
    void returnsRequestedByteRange() {
        client.get()
            .uri("/api/files/sample")
            .header(HttpHeaders.RANGE, "bytes=2-5")
            .exchange()
            .expectStatus().isPartialContent()
            .expectHeader()
                .valueEquals(HttpHeaders.CONTENT_RANGE, "bytes 2-5/10")
            .expectBody(String.class)
            .isEqualTo("2345");
    }

    @Test
    void supportsSuffixRange() {
        client.get()
            .uri("/api/files/sample")
            .header(HttpHeaders.RANGE, "bytes=-3")
            .exchange()
            .expectStatus().isPartialContent()
            .expectHeader()
                .valueEquals(HttpHeaders.CONTENT_RANGE, "bytes 7-9/10")
            .expectBody(String.class)
            .isEqualTo("789");
    }

    @Test
    void rejectsUnsatisfiableRange() {
        client.get()
            .uri("/api/files/sample")
            .header(HttpHeaders.RANGE, "bytes=20-30")
            .exchange()
            .expectStatus()
            .isEqualTo(HttpStatus.REQUESTED_RANGE_NOT_SATISFIABLE);
    }
}
~~~

Test dùng **WebTestClient.bindToController(...)** để kiểm tra controller và message-writing pipeline trong môi trường WebFlux. Nó xác nhận:

- Không có Range: response 200 và toàn bộ nội dung.
- bytes=2-5: response 206, Content-Range chính xác và body chỉ có 2345.
- bytes=-3: response 206 với ba byte cuối.
- bytes=20-30: response 416 vì tệp chỉ dài 10 byte.

### 8.7. Chạy ứng dụng và test

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Lấy toàn bộ file:

~~~bash
curl -i http://localhost:8080/api/files/sample
~~~

Kết quả body:

~~~text
0123456789
~~~

Yêu cầu byte 2 đến 5:

~~~bash
curl -i -H "Range: bytes=2-5" http://localhost:8080/api/files/sample
~~~

Response quan trọng:

~~~http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Type: text/plain
Content-Range: bytes 2-5/10
Content-Length: 4

2345
~~~

Yêu cầu ba byte cuối:

~~~bash
curl -i -H "Range: bytes=-3" http://localhost:8080/api/files/sample
~~~

Body:

~~~text
789
~~~

Yêu cầu hai vùng:

~~~bash
curl -i -H "Range: bytes=0-1,8-9" http://localhost:8080/api/files/sample
~~~

Response là 206 với Content-Type **multipart/byteranges**. Mỗi part có Content-Range riêng; boundary được tạo động nên sẽ khác nhau giữa các response.

Yêu cầu ngoài kích thước tệp:

~~~bash
curl -i -H "Range: bytes=20-30" http://localhost:8080/api/files/sample
~~~

Response status là **416 Range Not Satisfiable**. RFC 9110 khuyến nghị Content-Range dạng **bytes */10** để mô tả độ dài hiện tại; hãy xác minh header thực tế theo phiên bản Spring đang triển khai.

## 9. Phục vụ tệp từ filesystem an toàn

Trong ứng dụng thật, tệp thường nằm trong thư mục dữ liệu hoặc object storage. Không nên nối trực tiếp chuỗi do client gửi vào filesystem path:

~~~java
// Không an toàn:
Path file = Paths.get("/srv/files/" + userInput);
Resource resource = new FileSystemResource(file);
~~~

Client có thể thử path traversal như **../../etc/passwd** hoặc đường dẫn tới dữ liệu ngoài thư mục dự kiến. Việc chuẩn hóa chuỗi đơn thuần chưa đủ nếu có symlink.

### 9.1. Ưu tiên tra cứu theo ID

Một API tốt hơn thường nhận file ID:

~~~http
GET /api/documents/42
~~~

Service tìm metadata của document 42, kiểm tra user có quyền đọc hay không, rồi lấy Resource từ storage. Client không được quyết định đường dẫn vật lý.

### 9.2. Nếu phải nhận tên file, giới hạn trong root

Ví dụ minh họa:

~~~java
Path root = Paths.get("/srv/app-data").toRealPath();

Path candidate = root.resolve(fileName).normalize();

if (!candidate.startsWith(root)) {
    throw new ResponseStatusException(HttpStatus.NOT_FOUND);
}

Path realFile = candidate.toRealPath();

if (!realFile.startsWith(root) || !Files.isRegularFile(realFile)) {
    throw new ResponseStatusException(HttpStatus.NOT_FOUND);
}

Resource resource = new FileSystemResource(realFile);
~~~

Đây là snippet cần import java.nio.file.* và các kiểu Spring. Kiểm tra sau **toRealPath()** giúp phát hiện symlink trỏ ra ngoài root. Ứng dụng vẫn cần xử lý race condition theo threat model và giới hạn quyền filesystem; tốt nhất là dùng ID được tra cứu từ kho metadata.

### 9.3. Kiểm tra authorization trước khi trả Resource

Range request có thể tạo nhiều request nhỏ cho cùng một file. Mỗi request phải đi qua cùng chính sách authorization như request tải toàn bộ file.

Không kiểm tra quyền chỉ ở request đầu tiên rồi cho phép các Range request tiếp theo truy cập file theo URL công khai nếu tài nguyên cần bảo vệ. Kiểm tra quyền trên từng request hoặc dùng một cơ chế download token có thời hạn, phạm vi và quyền rõ ràng.

### 9.4. Kiểm soát Content-Disposition và filename

Nếu filename xuất phát từ metadata hoặc người dùng:

- Loại bỏ CR/LF và ký tự điều khiển.
- Không dùng filename làm filesystem path.
- Dùng ContentDisposition builder của Spring để encode header.
- Chọn inline hoặc attachment theo loại tài nguyên và chính sách ứng dụng.
- Không đưa đường dẫn nội bộ hoặc tên bucket vào response.

## 10. Cache, ETag, Last-Modified và Range

Range request thường xuất hiện cùng caching và tải tiếp. Client có thể đã có một phần dữ liệu cũ và muốn tải phần còn lại; server cần bảo đảm các phần ghép lại thuộc cùng một representation.

### 10.1. Cache-Control

**Cache-Control** hướng dẫn browser/proxy cách lưu và tái sử dụng response. Ví dụ:

~~~java
CacheControl cache = CacheControl
    .maxAge(1, TimeUnit.HOURS)
    .cachePrivate();
~~~

Với dữ liệu cá nhân hoặc file cần quyền truy cập, cân nhắc **private** và chính sách xác thực phù hợp. Không đặt public cache cho nội dung riêng tư chỉ để tăng tốc download.

### 10.2. Last-Modified

Resource có thể cung cấp **lastModified()**. Static resource handler WebFlux mặc định đánh giá Last-Modified và có thể trả 304 Not Modified khi client gửi điều kiện phù hợp.

304 không có body; nó cho client biết representation đã cache vẫn có thể được dùng. Với file cập nhật tại cùng URL, Last-Modified giúp tránh truyền lại toàn bộ nội dung khi chưa thay đổi.

### 10.3. ETag

**ETag** là validator đại diện cho một phiên bản representation. Client có thể gửi If-None-Match để hỏi nội dung có thay đổi không. Nếu validator khớp theo điều kiện GET, server có thể trả 304.

Với controller tùy biến, có thể dùng **ServerWebExchange.checkNotModified(...)** để đánh giá conditional request trước khi ghi body. Ví dụ khái niệm:

~~~java
String etag = "\"manual-v42\"";
long lastModified = resource.lastModified();

if (exchange.checkNotModified(etag, lastModified)) {
    return null;
}

// Tiếp tục trả Resource nếu request cần body.
~~~

Đây là snippet minh họa cho một handler method có ServerWebExchange và Resource. Trong code thật, cần giữ chữ ký return type và xử lý response đã được đánh dấu 304 theo đúng API của handler. Không tạo ETag giả ổn định nếu nội dung có thể thay đổi mà validator không đổi.

### 10.4. Preconditions được đánh giá trước Range

Theo RFC 9110, các precondition của HTTP được đánh giá trước khi áp dụng Range. Nếu conditional GET đã đủ điều kiện trả 304, server không cần gửi 206 cho một phần của representation không thay đổi.

**If-Range** cho phép client gửi Range kèm validator. Nếu validator vẫn khớp, server áp dụng Range; nếu không khớp, server gửi toàn bộ representation như response 200 để client thay thế dữ liệu cũ.

Trang Range Requests của Spring WebFlux mô tả xử lý tự động cho Range header. Nếu ứng dụng có yêu cầu nghiêm ngặt về **If-Range**, hãy kiểm tra và test hành vi của đúng phiên bản Spring, server và cache/proxy đang triển khai; đừng giả định một validator tùy biến đã được áp dụng nếu chưa xác minh.

### 10.5. ETag phải đại diện đúng representation

Nếu cùng URL có nội dung khác nhau theo quyền truy cập, ngôn ngữ, content encoding hoặc query parameter, ETag cần đại diện cho đúng representation mà client nhận được. Nếu không, cache có thể ghép nhầm dữ liệu hoặc trả nội dung của một phiên bản khác.

Với tài nguyên thay đổi thường xuyên, có thể dùng version trong metadata hoặc checksum nội dung. Không tính hash toàn bộ tệp lớn đồng bộ trên event-loop ở mỗi request; hãy tính khi lưu/cập nhật hoặc lưu sẵn metadata phù hợp.

## 11. Những lưu ý hiệu năng và vòng đời

### 11.1. Tránh đọc toàn bộ tệp lớn vào bộ nhớ

Không nên:

~~~java
byte[] allBytes = Files.readAllBytes(path);
return new ByteArrayResource(allBytes);
~~~

Cách này tiêu thụ bộ nhớ tỷ lệ với kích thước file cho từng lần xử lý, có thể làm heap tăng mạnh khi nhiều client tải đồng thời.

Dùng **FileSystemResource** hoặc Resource dựa trên storage có thể đọc theo vùng. WebFlux Resource writer sẽ ghi nội dung theo cơ chế phù hợp.

### 11.2. Zero-copy khi có thể

Với một số server transport và Resource là file thực, framework có thể sử dụng **zero-copy** để chuyển dữ liệu từ file ra socket với ít lần sao chép giữa user space và kernel space hơn. Đây là tối ưu phụ thuộc runtime và loại Resource; không nên coi mọi Resource response đều zero-copy.

### 11.3. Client disconnect và cancellation

Client có thể hủy request giữa lúc tải. Pipeline ghi response có thể nhận cancellation và ngừng đọc tiếp. Với một file tĩnh, việc dừng đọc giúp tránh truyền dữ liệu không còn cần thiết.

Nếu việc tạo file có side effect hoặc việc download kích hoạt một nghiệp vụ, cancellation không tự rollback side effect đã hoàn tất. Phân biệt rõ hành động đọc file với hành động tạo/xuất file.

### 11.4. Giới hạn số lượng Range

Một request có thể chứa nhiều đoạn nhỏ hoặc overlap. Việc tạo và ghi nhiều region làm tăng CPU, buffer và metadata. Sử dụng phiên bản Spring đã được cập nhật, giới hạn request rate/kích thước header theo môi trường, và nếu tự xử lý Range thì đặt giới hạn số region và từ chối input quá phức tạp.

Không viết vòng lặp tự tạo hàng nghìn ResourceRegion rồi giữ toàn bộ trong bộ nhớ mà không có giới hạn. Đối với các file rất lớn hoặc media streaming, cần đo tải và kiểm thử với nhiều client đồng thời.

### 11.5. Content-Encoding và byte offset

Range tính trên byte của representation được chọn. Nếu response được nén hoặc biến đổi nội dung, byte offset của representation đã mã hóa có thể khác offset của file gốc. Vì vậy, cần thống nhất cách xử lý compression, cache và Range; không áp Range trên byte của file gốc rồi lại thay đổi representation sau đó.

## 12. Tự triển khai Range thủ công: khi nào cần?

Với use case phổ biến, hãy trả Resource để WebFlux tự xử lý. Chỉ tự triển khai khi có yêu cầu đặc biệt như:

- File đến từ storage API chỉ hỗ trợ đọc theo offset/length.
- Cần authorization riêng cho từng region.
- Cần hỗ trợ một representation được tạo động.
- Cần kiểm soát chính sách If-Range hoặc giới hạn range theo nghiệp vụ.
- Cần streaming từ object storage mà không thể biểu diễn bằng Resource tiêu chuẩn.

Nếu tự triển khai, cần thực hiện đầy đủ:

1. Chỉ áp dụng Range cho method được hỗ trợ.
2. Parse Range và kiểm tra đơn vị.
3. Xác định tổng độ dài representation.
4. Chuẩn hóa closed/open/suffix range.
5. Kiểm tra range có thể đáp ứng và tránh overflow khi tính offset.
6. Quyết định 200, 206 hoặc 416.
7. Với một range, đặt Content-Range và Content-Length chính xác.
8. Với nhiều range, tạo multipart/byteranges với boundary và Content-Range cho từng part.
9. Đánh giá conditional headers và If-Range theo RFC.
10. Xử lý cancellation, backpressure, timeout và lỗi đọc storage.
11. Không để một client yêu cầu số lượng region không giới hạn.
12. Kiểm thử ghép các đoạn byte để khôi phục đúng representation gốc.

### 12.1. Dùng HttpRange để phân tích

Ví dụ lấy các range từ request:

~~~java
List<HttpRange> ranges = request.getHeaders().getRange();

List<ResourceRegion> regions =
    HttpRange.toResourceRegions(ranges, resource);
~~~

Cần xử lý **IllegalArgumentException** khi header sai định dạng hoặc range không phù hợp với Resource. API HttpRange cung cấp parser và phép chuyển đổi sang ResourceRegion, nhưng việc tạo đúng response HTTP vẫn cần writer hoặc code xử lý multipart tương ứng.

Không chỉ đặt status 206 rồi gửi byte tùy ý. Client cần Content-Range và độ dài representation chính xác để biết đoạn vừa nhận nằm ở đâu.

## 13. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Range request vẫn nhận 200 toàn bộ file | Body không phải Resource, Resource là InputStreamResource hoặc response status không phải 200 | Trả Resource/ResponseEntity<Resource> và giữ status 200 ban đầu |
| Response không có Content-Range | Range bị bỏ qua hoặc server trả full representation | Kiểm tra Range header, status, Resource type và writer |
| Response 416 | Range ngoài kích thước hoặc header không hợp lệ | Kiểm tra tổng byte, vị trí đầu/cuối và cú pháp |
| File lớn làm heap tăng | Đọc toàn bộ vào byte[] hoặc ByteArrayResource | Dùng FileSystemResource hoặc storage hỗ trợ đọc theo vùng |
| Không lấy được content length | Resource không xác định được kích thước | Chọn Resource có length đáng tin cậy hoặc xử lý streaming có contract riêng |
| Range hoạt động với file nhỏ nhưng lỗi file lớn | Offset, buffer, storage hoặc giới hạn request chưa phù hợp | Kiểm tra kiểu số, đọc theo vùng, timeout và memory |
| Tải tiếp ghép sai nội dung | Representation đã thay đổi giữa các request | Dùng ETag/Last-Modified/If-Range đúng và giữ URL/version ổn định |
| Multiple ranges trả body khó đọc | Response là multipart/byteranges có boundary động | Parse từng part; không so sánh nguyên body với một chuỗi cố định |
| File khác bị truy cập qua URL | Client kiểm soát path và có path traversal/symlink | Dùng ID tra cứu, canonical path, authorization và root boundary |
| Filename lỗi hoặc header bị chèn | Filename lấy trực tiếp từ input | Dùng ContentDisposition builder và lọc ký tự điều khiển |
| Client không nhận được nội dung mới | Cache-Control quá dài hoặc validator sai | Chọn cache policy theo tính chất nội dung, cập nhật ETag/version |
| Compression làm Range sai offset | Byte range và representation sau nén không đồng nhất | Xác định rõ representation, content coding và thứ tự filter |
| Download vẫn chạy sau khi client ngắt | Nguồn đọc hoặc tác vụ phụ không phản ứng cancellation | Dùng Publisher hỗ trợ cancellation và quản lý resource lifecycle |
| Tự xử lý Range nhưng client không ghép được | Thiếu Content-Range, Content-Length hoặc multipart boundary đúng | Tuân thủ RFC 9110 và kiểm thử bằng client thật |

## 14. Checklist trước khi triển khai endpoint download

- Resource có thể đọc lại và không phải InputStreamResource?
- Controller trả Resource hoặc ResponseEntity<Resource> với status ban đầu 200?
- Content-Type được xác định đúng?
- Content-Disposition có filename an toàn và phù hợp inline/attachment?
- Range request trả đúng 206, Content-Range và Content-Length?
- Suffix/open-ended/multiple range đã được kiểm thử nếu cần?
- Range không đáp ứng có phản hồi 416 phù hợp?
- Resource có content length và last-modified đáng tin cậy?
- Authorization được kiểm tra trên mỗi request?
- Client không thể chọn filesystem path tùy ý?
- File lớn được stream, không đọc toàn bộ vào heap?
- Cache-Control và validator phù hợp với độ nhạy/cập nhật của file?
- Content-Encoding không làm sai offset byte?
- Cancellation và timeout được xử lý?
- Phiên bản Spring Framework đã cập nhật bản vá?
- Có test bằng WebTestClient và kiểm tra bằng curl?

## 15. Bài tập thực hành

**Bài 1 — Range cơ bản:** Dùng file 10 byte 0123456789. Gửi bytes=2-5 và giải thích vì sao body là 2345, Content-Range là bytes 2-5/10.

**Bài 2 — Suffix range:** Gửi bytes=-3. Tính vị trí bắt đầu và kết thúc theo độ dài Resource.

**Bài 3 — Open-ended range:** Gửi bytes=7-. Kiểm tra response chỉ có ba byte cuối.

**Bài 4 — Unsatisfiable range:** Gửi bytes=20-30. Quan sát status 416 và kiểm tra Content-Range theo phiên bản framework.

**Bài 5 — Multiple ranges:** Gửi bytes=0-1,8-9. Phân tích Content-Type multipart/byteranges và Content-Range trong từng part.

**Bài 6 — InputStreamResource:** Thay ClassPathResource bằng InputStreamResource. Quan sát Range không còn được hỗ trợ như trước và giải thích tính repeatable của Resource.

**Bài 7 — Static resources:** Đặt PDF trong classpath:/static, cấu hình ResourceHandlerRegistry và thử Range trên URL static.

**Bài 8 — Cache:** Cấu hình Cache-Control và kiểm tra Last-Modified/conditional request. Xác định khi nào server trả 304.

**Bài 9 — ETag:** Tạo ETag dựa trên version của tài liệu. Gửi If-None-Match và kiểm tra response khi representation chưa thay đổi.

**Bài 10 — Bảo mật path:** Viết endpoint nhận document ID, tra metadata và kiểm tra authorization. Thử payload path traversal và symlink.

**Bài 11 — File lớn:** Dùng FileSystemResource cho file lớn. Đo heap khi tải đồng thời và so sánh với cách đọc toàn bộ bằng Files.readAllBytes.

**Bài 12 — Test ghép đoạn:** Tải nhiều đoạn byte riêng biệt rồi ghép theo Content-Range. So sánh checksum với file gốc để chứng minh dữ liệu không mất hoặc đảo thứ tự.

## 16. Ghi nhớ

**Resource** là abstraction để WebFlux phục vụ file hoặc nội dung nhị phân. **Range** cho phép client lấy một phần representation theo byte offset. Khi controller trả Resource phù hợp, Spring dùng **ResourceHttpMessageWriter**, **HttpRange** và **ResourceRegion** để xử lý byte range; response có thể là 200, 206 hoặc 416 tùy request.

Để Range hoạt động tự động, dùng Resource có thể đọc lại, tránh InputStreamResource và giữ status ban đầu của ResponseEntity là 200. Với file lớn, dùng Resource dựa trên filesystem/storage có khả năng đọc theo vùng. Với nội dung riêng tư, kiểm tra quyền truy cập trên từng request và không để client điều khiển path vật lý.

Kết hợp Range với ETag, Last-Modified và cache policy để client tải tiếp đúng phiên bản. Nếu tự xử lý Range, tuân thủ RFC 9110, giới hạn số vùng, ghi Content-Range chính xác và kiểm thử cả trường hợp cancellation lẫn range không thể đáp ứng.

## 17. Tài liệu tham khảo

- Spring Framework Reference — WebFlux Range Requests: https://docs.spring.io/spring-framework/reference/web/webflux/range.html
- Spring Framework Reference — WebFlux Static Resources: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework Reference — WebFlux HTTP Caching: https://docs.spring.io/spring-framework/reference/web/webflux/caching.html
- Spring Framework API — Resource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/Resource.html
- Spring Framework API — HttpRange: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/HttpRange.html
- Spring Framework API — ResourceRegion: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/support/ResourceRegion.html
- Spring Framework API — ResourceHttpMessageWriter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/ResourceHttpMessageWriter.html
- Spring Boot Reference — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- RFC 9110 — HTTP Semantics, Range Requests and Content-Range: https://www.rfc-editor.org/rfc/rfc9110.html
- MDN — HTTP Range Requests: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Range_requests

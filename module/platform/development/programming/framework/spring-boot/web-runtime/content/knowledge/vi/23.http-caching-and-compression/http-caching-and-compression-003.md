# ETag, Last-Modified và yêu cầu HTTP có điều kiện trong Spring Boot

Khi trình duyệt gọi lại một URL, không phải lúc nào server cũng cần gửi lại toàn bộ JSON, HTML, CSS hay ảnh. Nếu client đã có bản sao hợp lệ, một **yêu cầu có điều kiện** (conditional request) cho phép xác nhận phiên bản đang giữ: **304 Not Modified** báo rằng bản đã lưu vẫn dùng được, còn **200 OK** mang nội dung mới nếu biểu diễn đã thay đổi. Hai HTTP validator thông dụng là **ETag** và **Last-Modified**. Chúng cũng hỗ trợ **điều kiện ghi** để ngăn cập nhật đè lên dữ liệu người khác, thường dùng **If-Match** và **412 Precondition Failed**.

Bài học thuộc chủ đề **Spring Boot - web-runtime / Cache và nén HTTP**. Ví dụ chính dùng **Spring Boot 3.3.x, Java 17+, Spring MVC/Servlet**, giải thích HTTP trước rồi áp dụng vào controller, tài nguyên tĩnh, nén gzip, proxy/CDN, lỗi thường gặp và test. Cần phân biệt: **cache HTTP không đồng nghĩa Spring Cache (@Cacheable)**; ETag không tự cache dữ liệu trong database và 304 không tự giảm mọi công việc xử lý trên server.

## 1. Mục tiêu và điều kiện đầu vào

Học xong, bạn có thể:

1. Nêu chức năng của **ETag**, **Last-Modified**, **Cache-Control**, **If-None-Match**, **If-Modified-Since** và chúng phối hợp với nhau thế nào.
2. Phân biệt **freshness** (cache còn mới và có thể tái sử dụng không cần hỏi server) với **validation/revalidation** (hỏi server xem bản cache có đổi không).
3. Giải thích chính xác khi nào server trả **200**, **304**, **412**; vì sao 304 không có response body và không có nghĩa tài nguyên rỗng.
4. Phân biệt **strong ETag** và **weak ETag**; hiểu giới hạn độ chính xác theo giây của HTTP-date và thứ tự ưu tiên giữa các điều kiện HTTP.
5. Tạo endpoint Spring MVC trả **ResponseEntity** cùng ETag, Last-Modified, Cache-Control; kiểm thử conditional GET bằng **MockMvc**.
6. Biết dùng **WebRequest.checkNotModified(...)** để kiểm tra validator sớm, và hiểu giới hạn của **ShallowEtagHeaderFilter**.
7. Tránh rủi ro khi API có xác thực, có nhiều biểu diễn JSON/ngôn ngữ, trả gzip/brotli hoặc đi qua proxy/CDN.
8. Thiết kế validator đủ ổn định cho cluster/rolling deploy và đủ thay đổi khi nội dung thực sự đổi.

Yêu cầu nền: HTTP request/response, header, status code, REST controller, JSON, Java 17, Spring Boot Maven/Gradle và cách gọi API bằng curl.

## 2. Hai bài toán khác nhau: cache freshness và cache validation

### 2.1. Freshness: dùng cache ngay khi còn tươi

Khi server trả:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=600
ETag: "catalog-v7"
Content-Type: application/json

{"version":7,"items":["A","B"]}
~~~

**max-age=600** cho biết bản phản hồi có thể được xem là fresh trong tối đa 600 giây theo quy tắc HTTP caching. Khi cache phù hợp và vẫn fresh, client hoặc cache trung gian **có thể trả lại bản đã lưu mà không gửi request tới origin**. Vì không gửi request nên không có 304; đây là tiết kiệm cả một lượt mạng và có thể tiết kiệm tải origin.

Cache-Control là **chính sách**; ETag là **validator**. Có ETag không đảm bảo browser cache luôn lưu response, và có cache header không tự bảo đảm nội dung được tái sử dụng trong mọi tình huống (còn phụ thuộc phương thức, status, Vary, private/public, cache implementation, authentication và policy khác).

### 2.2. Revalidation: kiểm tra bản cũ khi cần

Khi bản cache đã stale hoặc policy yêu cầu xác nhận lại, cache gửi:

~~~http
GET /api/catalog HTTP/1.1
Host: localhost:8080
If-None-Match: "catalog-v7"
~~~

Server tính hoặc tra validator hiện tại:

- Nếu biểu diễn chọn được **vẫn tương đương** với validator của client, phản hồi **304 Not Modified** với metadata cache phù hợp, **không gửi lại body**.
- Nếu có thay đổi, phản hồi **200 OK** cùng **ETag mới** và nội dung mới (nếu request hợp lệ và được phép truy cập).
- Nếu request phải trả 401, 403, 404 hoặc lỗi thông thường khác, các điều kiện không biến lỗi đó thành 304 chỉ vì client từng có ETag.

Quy trình:

~~~text
Lần 1: GET /api/catalog
        |
        v
200 OK + ETag: "catalog-v7" + JSON body
        |
        v
Client/cache lưu body + metadata (nếu được phép)

Lần 2: GET + If-None-Match: "catalog-v7"
        |
        +-- representation hiện tại vẫn v7
        |       |
        |       v
        |     304 Not Modified + headers hữu ích, KHÔNG có body
        |       |
        |       v
        |     cache dùng lại JSON body của lần trước
        |
        +-- representation đã thành v8
                |
                v
              200 OK + ETag: "catalog-v8" + body v8
~~~

**304 chỉ hữu ích nếu client/cache đã có representation để dùng lại.** Gọi một lệnh curl có If-None-Match nhưng chưa lưu body cũ có thể thấy 304 trống; điều này **không** nghĩa API trả JSON rỗng. Với ứng dụng, cache layer mới kết hợp metadata 304 với bản đã lưu.

### 2.3. Vì sao không phải mọi 304 đều giúp tiết kiệm CPU?

Validator có thể có sẵn từ metadata như **version** của bản ghi, timestamp đáng tin hoặc hash đã lưu. Khi đó server kiểm tra sớm và có thể tránh serialize JSON/truy vấn đắt tiền. Nhưng nếu phải xây đầy đủ response rồi băm body để biết ETag, **băng thông được tiết kiệm nhưng chi phí tạo nội dung vẫn còn**. Đây là lý do phân biệt **deep/application-level ETag** với **shallow ETag**.

## 3. ETag: validator theo phiên bản biểu diễn

### 3.1. Cú pháp

ETag là một response header biểu thị validator của **selected representation**:

~~~http
ETag: "product-42-v17"
ETag: W/"product-42-v17"
~~~

- **"product-42-v17"**: ETag mạnh (**strong**), không có tiền tố W/.
- **W/"product-42-v17"**: ETag yếu (**weak**).
- Dấu **ngoặc kép là một phần cú pháp** entity-tag. Không gửi ETag như product-42-v17 thiếu dấu nháy.
- Chuỗi bên trong do server quyết định: có thể dựa trên revision, hash nội dung hoặc key version hóa. Nó không nhất thiết là checksum mật mã và **không chứng minh dữ liệu an toàn/tin cậy**.

**Không dùng ETag như session token hoặc bí mật.** ETag có thể lộ cấu trúc version; nếu người dùng khác nhau có cùng URL nhưng nội dung khác nhau, phải chú ý cache policy, Vary và cách tạo validator theo biểu diễn.

### 3.2. Strong và weak khác nhau thế nào?

| Đặc điểm | Strong ETag | Weak ETag |
| --- | --- | --- |
| Ví dụ | **"v17"** | **W/"v17"** |
| Ý nghĩa | Mức nhận diện mạnh đối với bytes của selected representation | Hai representation có thể tương đương ngữ nghĩa dù bytes khác nhau |
| If-None-Match | Dùng được; áp dụng **weak comparison** | Dùng được; áp dụng **weak comparison** |
| If-Match | Dùng **strong comparison** | Không khớp strong ETag, không phù hợp làm precondition chống ghi đè |
| Range/If-Range | Có thể dùng strong ETag đúng chuẩn | Weak tag không hợp lệ làm validator của If-Range |
| Trường hợp điển hình | Biểu diễn byte ổn định và version thay khi bytes đổi | Nội dung ngữ nghĩa tương đương nhưng output có thể biến động chi tiết |

**Mạnh không đồng nghĩa an toàn bảo mật hơn.** Strong/weak là phân loại tính tương đương của representation, không phải xác thực chữ ký số. Một hệ thống có thể dùng revision làm strong ETag **nếu** bảo đảm bất kỳ biến đổi nào đối với byte biểu diễn được chọn cũng khiến validator đổi; nếu serializer, locale hoặc content encoding thay đổi mà tag không đổi, giả định strong có thể bị phá.

**If-None-Match dùng weak comparison**, nên một request có thể nhận 304 khi phía client gửi W/"abc" và server có "abc" đối với biểu diễn ngữ nghĩa tương đương. **If-Match dùng strong comparison**, nên W/"abc" không thỏa "abc" trong điều kiện ghi. Không tự so sánh chuỗi thô bằng equals khi làm HTTP precondition nếu chưa xử lý cú pháp, danh sách ETag, wildcard và quy tắc strong/weak.

### 3.3. ETag phải đại diện cho biến thể được chọn

Một URL có thể trả JSON hoặc HTML, tiếng Việt/tiếng Anh, ảnh cỡ khác nhau, hoặc bản có/không có gzip. Validator nên phản ánh **selected representation**, không chỉ tên resource.

Ví dụ không tốt:

~~~text
GET /api/report?lang=vi -> body tiếng Việt, ETag "report-v3"
GET /api/report?lang=en -> body tiếng Anh, ETag "report-v3"
~~~

Nếu hai body bytes khác mà server quảng cáo **cùng strong ETag**, client/cache có thể tái sử dụng sai. Cách sửa: mã hóa variant (lang/media type/schema/version) vào validator, dùng weak semantics khi thật sự tương đương, hoặc thay đổi URL/Cache-Control/Vary phù hợp.

Không mặc định "hash của database row" luôn đủ cho strong ETag: JSON có thể chứa computed fields, đổi schema, formatter, authorization-specific columns và content negotiation khác dữ liệu row gốc.

### 3.4. ETag không phải cơ chế chống stale write tự động

ETag dùng cho **GET cache validation** khi client gửi If-None-Match, nhưng cũng có thể dùng cho **concurrency control** khi client ghi và gửi If-Match. **GET /resource** có ETag không tự khiến **PUT /resource** từ chối dữ liệu cũ; server phải **thực thi điều kiện ghi** trước khi commit.

## 4. Last-Modified: validator theo thời điểm

### 4.1. Cú pháp HTTP-date

~~~http
Last-Modified: Tue, 02 Jan 2024 03:04:05 GMT
~~~

**Last-Modified** cho biết thời điểm representation được sửa lần cuối theo metadata của server. Client có thể gửi **If-Modified-Since**:

~~~http
GET /api/catalog HTTP/1.1
If-Modified-Since: Tue, 02 Jan 2024 03:04:05 GMT
~~~

Nếu tài nguyên chọn được có thời gian sửa cuối **không muộn hơn** giá trị client gửi, server có thể phản hồi **304** (đối với GET/HEAD). Nếu thời gian sửa mới hơn, trả response thường, ví dụ **200 + body + Last-Modified mới**.

Đối với Last-Modified:
- HTTP-date truyền theo độ phân giải **giây**, không phải milliseconds hay nanoseconds.
- Timestamp nên dựa trên nguồn đáng tin, được giữ nhất quán giữa các instance và version của dữ liệu.
- Không sinh Last-Modified bằng **Instant.now() mỗi request**, vì như vậy validator thay đổi liên tục dù nội dung không đổi.
- Không báo Last-Modified ở tương lai so với thời điểm tạo response; RFC 9110 yêu cầu xử lý giá trị metadata thời gian tương lai.
- Nếu không có thời điểm sửa đáng tin cậy, đừng bịa một giá trị chỉ để luôn có header.

### 4.2. Hạn chế của validator theo giây

Giả sử một bài viết được cập nhật hai lần trong cùng một giây: HTTP-date có thể giữ nguyên dù bytes đã đổi. Hoặc đồng hồ trên hai server lệch nhau, làm Last-Modified tiến/lùi bất thường.

Vì vậy:
- Với tài nguyên đổi thường xuyên hoặc cần precondition ghi chặt chẽ, **revision/ETag phù hợp hơn**.
- Khi dùng **If-Unmodified-Since** để chống ghi đè, chú ý độ chính xác thấp hơn If-Match.
- Không tự lấy timestamp build/deploy làm Last-Modified của một resource business nếu dữ liệu có thể đổi độc lập với deployment.
- Có thể gửi **cả ETag và Last-Modified** nếu có metadata tốt; client hiện đại thường ưu tiên ETag để revalidate.

### 4.3. Last-Modified không phải Last-Accessed

Last-Modified mô tả **dữ liệu/representation đã được thay đổi lúc nào**; nó không phải lúc client truy cập gần nhất, không liên quan đến HttpSession idle timeout, và không phải thời điểm response đã được cache lần cuối.

Không đặt Last-Modified=thời điểm request hiện tại để “cho mới”; khi nội dung không đổi, điều này phá lợi ích của conditional GET.

## 5. Các request header có điều kiện và status code

| Request header | Mục đích | So sánh / kết quả quan trọng |
| --- | --- | --- |
| **If-None-Match** | Chỉ thực thi nếu **không** có tag phù hợp; revalidate GET | Dùng weak comparison. Nếu match trên GET/HEAD → **304**; match trên phương thức khác → **412**. |
| **If-Modified-Since** | GET/HEAD chỉ khi tài nguyên mới hơn thời điểm đưa ra | Nếu không mới hơn → **304**; chỉ đánh giá khi không có If-None-Match hợp lệ đi kèm. |
| **If-Match** | Chỉ thực thi khi representation hiện tại khớp tag | Dùng **strong comparison**; không khớp thường → **412**, đặc biệt cho PUT/PATCH/DELETE. |
| **If-Unmodified-Since** | Chỉ thực thi nếu representation chưa đổi sau thời điểm cho trước | Nếu đã đổi, thường → **412**; bỏ qua khi có If-Match. |
| **If-Range** + **Range** | Lấy tiếp một phần resource nếu validator còn đúng | Khớp → có thể **206 Partial Content**; không khớp → bỏ Range và trả toàn bộ **200**. |
| **If-None-Match: *** | Thường dùng khi tạo tài nguyên nếu chưa tồn tại | Nếu đã có representation và method không phải GET/HEAD → **412**, hữu ích chống ghi đè khi tạo mới. |

### 5.1. 200, 304 và 412 nói lên điều gì?

**200 OK**: server gửi representation mới/được yêu cầu cho GET hợp lệ; có body với GET (có thể rỗng nếu tài nguyên vốn rỗng). Conditional GET có validator không trùng vẫn thường trả 200.

**304 Not Modified**: dành cho **conditional GET/HEAD** khi client đã có bản có thể tái sử dụng. **Không được gửi body hoặc trailer trong 304**. Response cần metadata cache cập nhật phù hợp; theo RFC 9110, origin phải gửi những field bắt buộc thuộc nhóm **Date, ETag, Vary, Content-Location, Cache-Control, Expires** nếu chúng cũng sẽ có trong 200 tương ứng. Last-Modified cũng hữu ích khi cần cập nhật metadata cache.

**412 Precondition Failed**: request không thỏa precondition, đặc biệt khi PUT/PATCH/DELETE dựa trên **If-Match** hoặc **If-Unmodified-Since**. Không dùng 304 để nói rằng một **PUT** đã thất bại vì ETag. Dùng 412 để client biết phải lấy lại phiên bản hiện tại trước khi cập nhật.

**404 Not Found / 401 Unauthorized / 403 Forbidden**: lỗi resource/authorization bình thường vẫn có thể thắng conditional request. ETag đã biết từ lần trước **không tạo quyền truy cập**. Kiểm tra authentication và authorization phải diễn ra trước khi cung cấp dữ liệu hoặc xác nhận riêng tư.

**428 Precondition Required**: tùy API, server có thể yêu cầu client luôn gửi If-Match trước khi cập nhật tài nguyên cần bảo vệ; đây là quy tắc thiết kế tùy chọn, khác 412.

### 5.2. Ưu tiên khi nhiều header cùng xuất hiện

RFC 9110 quy định thứ tự precondition, không được chọn điều kiện mình thích theo thứ tự ngẫu nhiên trong Java code:

1. **If-Match** trước; nếu không có thì mới xét **If-Unmodified-Since**.
2. Sau đó **If-None-Match**.
3. Với GET/HEAD **không có If-None-Match**, mới xét **If-Modified-Since**.
4. Cuối cùng, với GET có Range và If-Range, xử lý range validation tương ứng.

Ví dụ:

~~~http
GET /api/articles/42 HTTP/1.1
If-None-Match: "old"
If-Modified-Since: Tue, 02 Jan 2024 03:04:05 GMT
~~~

Giả sử tag hiện tại là **"article-42-v7"**, và Last-Modified đúng bằng ngày trên. **If-None-Match không match**, nên request nên đi tiếp tới **200 OK** cùng body; không được lấy If-Modified-Since để tự động trả 304. ETag có độ ưu tiên cao hơn date validator cho cache revalidation.

Ở chiều ngược, nếu If-None-Match khớp, GET có thể nhận 304 dù If-Modified-Since cũ hơn nhiều. Server không nên “AND” hai phép kiểm tra này.

### 5.3. Weak comparison khác strong comparison

~~~http
ETag: "rev-8"
If-None-Match: W/"rev-8"
~~~

Với **If-None-Match**, yếu và mạnh cùng tag có thể match theo **weak comparison**, nên conditional GET có thể nhận 304.

~~~http
ETag: "rev-8"
If-Match: W/"rev-8"
~~~

Với **If-Match**, so sánh strong không cho weak tag match. Nếu một client dùng weak ETag như precondition ghi, kết quả thường là **412**. Đừng tự viết logic kiểu bỏ ký tự W/ trước khi so sánh mọi điều kiện; như vậy phá ý nghĩa an toàn của If-Match.

## 6. Cache-Control tương tác với validators ra sao?

### 6.1. Các directive thường gặp

| Cache-Control | Ý nghĩa cơ bản | Khi nào dùng |
| --- | --- | --- |
| **max-age=600** | Cache có thể xem response fresh trong thời gian giới hạn | Nội dung public ít đổi, cho phép reuse không hỏi server. |
| **no-cache** | Có thể **lưu**, nhưng phải **revalidate trước khi reuse** | Muốn giữ bản cũ để nhận 304 mà luôn hỏi origin trước khi dùng. |
| **no-store** | Không được lưu request/response theo cache policy | Nội dung cá nhân nhạy cảm, token, trang chứa secret. |
| **private** | Chỉ private cache (ví dụ browser) được lưu, shared proxy không được tái sử dụng | Nội dung riêng theo người dùng nếu chính sách cho phép cache. |
| **public** | Cho phép shared caches lưu theo quy tắc HTTP | Tài nguyên thực sự công khai, có key/variant phù hợp. |
| **immutable** | Báo rằng nội dung không đổi trong thời hạn freshness | Asset có tên hash/content version, URL không thay nội dung. |

**no-cache khác no-store.** Đặt **Cache-Control: no-cache** cùng ETag có thể rất hữu ích: browser giữ body nhưng phải gửi If-None-Match mỗi lần cần dùng lại; nếu không đổi, server gửi 304. Nếu dùng **no-store**, cache không giữ body nên revalidation thông thường không còn mục đích.

Với JSON có xác thực, **private, no-cache** có thể phù hợp khi cần cache browser nhưng không chia sẻ qua proxy. Với dữ liệu cực nhạy cảm, dùng **no-store**, chấp nhận không nhận lợi ích 304 từ cache. Quyết định dựa trên sensitivity, legal policy, logout behavior, không chỉ hiệu năng.

### 6.2. HTTP cache khác Spring Cache (@Cacheable)

**HTTP cache** nằm ở browser, reverse proxy, CDN và client; nó sử dụng header như Cache-Control, Vary, ETag, Last-Modified và status 304.

**Spring Cache** như **@Cacheable** tối ưu việc gọi method/service/database phía server. Bật @Cacheable không tự sinh ETag đúng, không tự trả 304, và một ETag response không tự cache repository query. Hai lớp có thể kết hợp nhưng cần invalidation và consistency riêng.

### 6.3. Vary và các biến thể

~~~http
Vary: Accept-Encoding
~~~

**Vary** cho cache biết response có thể khác theo request header được liệt kê, ví dụ **Accept-Encoding**, **Accept-Language** hoặc **Accept**. Một strong ETag không được tái sử dụng mù quáng giữa các body byte khác nhau.

Đối với JSON user-specific, **Vary: Authorization** không phải phép màu để bảo vệ dữ liệu: phải dùng chính sách cache **private/no-store** và keying đầy đủ, tránh shared cache lưu/reuse response cá nhân. Trong môi trường có cookies, session và CDN, cần thiết kế rõ owner của cache.

## 7. Ví dụ đầy đủ: ResponseEntity với ETag + Last-Modified

Ứng dụng ví dụ phục vụ một article **được giữ cố định trong mã để demo**. Việc này giúp test có kết quả ổn định và cho thấy MVC tự xử lý conditional GET từ headers của ResponseEntity. Trong ứng dụng thật, hãy lấy **version và lastModified** từ cùng snapshot của dữ liệu, thay đổi chúng mỗi khi representation đổi.

### 7.1. Tạo project

Tạo project Maven từ **https://start.spring.io** với **Java 17**, Spring Boot **3.3.x**, group **com.example**, artifact **http-validator-demo**, package **com.example.httpvalidator**, dependencies **Spring Web** và **Spring Boot Starter Test**. Có thể dùng Maven wrapper từ project.

Cấu trúc:

~~~text
http-validator-demo/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/httpvalidator/
    HttpValidatorApplication.java
    ArticleController.java
  src/main/resources/
    application.yml
  src/test/java/com/example/httpvalidator/
    ArticleControllerTest.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>http-validator-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Spring Boot parent quản lý phiên bản Spring MVC, Jackson, Servlet và thư viện test. Version được cố định làm mốc học tập; khi triển khai thực tế hãy sử dụng patch version được tổ chức hỗ trợ và bảo trì, tránh tùy tiện nâng riêng Spring Framework không tương thích.

### 7.3. Main class

**src/main/java/com/example/httpvalidator/HttpValidatorApplication.java**

~~~java
package com.example.httpvalidator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpValidatorApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpValidatorApplication.class, args);
    }
}
~~~

### 7.4. Controller có validator ổn định

**src/main/java/com/example/httpvalidator/ArticleController.java**

~~~java
package com.example.httpvalidator;

import java.time.Instant;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ArticleController {
    private static final Instant LAST_MODIFIED =
            Instant.parse("2024-01-02T03:04:05Z");

    private static final String ARTICLE_ETAG = "\"article-42-v7\"";

    public record Article(long id, String title, long version) { }

    @GetMapping("/api/articles/{id}")
    public ResponseEntity<Article> getArticle(@PathVariable long id) {
        if (id != 42L) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        Article article = new Article(42L,
                "HTTP conditional requests", 7L);

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache().cachePrivate())
                .eTag(ARTICLE_ETAG)
                .lastModified(LAST_MODIFIED.toEpochMilli())
                .body(article);
    }
}
~~~

**Giải thích dòng quan trọng:**

1. **ARTICLE_ETAG** có dấu ngoặc kép đúng cú pháp entity-tag. ResponseEntity.BodyBuilder.eTag(...) cũng có khả năng bổ sung dấu ngoặc nếu cần; trong demo khai báo sẵn dạng canonical.
2. **LAST_MODIFIED** cố định nhằm làm test xác định. Với resource thật, lấy thời điểm cập nhật đã lưu trong DB hoặc metadata đáng tin, không dùng **Instant.now()** mỗi lần gọi.
3. **CacheControl.noCache().cachePrivate()** cho phép cache riêng giữ body nhưng yêu cầu revalidate, không dùng chung ở shared proxy.
4. **ResponseEntity** cho Spring MVC thông tin ETag/Last-Modified để hỗ trợ conditional GET. Nếu request mang validator phù hợp, MVC có thể trả **304** mà không ghi body. Tuy nhiên code ví dụ vẫn tạo đối tượng **Article** trước khi ResponseEntity hoàn tất; đây **chưa phải chiến lược tối ưu CPU sâu**.
5. **404** cho id khác 42 vẫn là 404, bất kể client gửi If-None-Match. Validator phải gắn với selected representation thực sự tồn tại.
6. Bài mẫu không truy cập database hay thực hiện authentication; không lấy code này làm API sản xuất mà chưa bổ sung authorization, nguồn dữ liệu và tính nhất quán version.

Trong dữ liệu thật, nếu cùng URL có nhiều biểu diễn theo ngôn ngữ hoặc Accept, cần đưa variant vào ETag hoặc chọn caching strategy khác. Nếu title đổi mà version vẫn 7, strong ETag của ví dụ **không còn đúng**; luôn cập nhật version khi representation đổi.

### 7.5. Cấu hình runtime

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: http-validator-demo

server:
  port: 8080
~~~

Không cần một thuộc tính Spring Boot chung để "bật ETag cho mọi controller". Code/controller quyết định validator, hoặc bạn có thể dùng filter cho shallow ETag theo nhu cầu. Trong ví dụ, header ETag/Last-Modified do ResponseEntity tạo.

### 7.6. Chạy và thử bằng curl

Linux/macOS:

~~~bash
./mvnw spring-boot:run
~~~

Windows:

~~~text
mvnw.cmd spring-boot:run
~~~

Hoặc đóng gói:

~~~bash
./mvnw clean package
java -jar target/http-validator-demo-0.0.1-SNAPSHOT.jar
~~~

Gọi thông thường:

~~~bash
curl -i http://localhost:8080/api/articles/42
~~~

Response có status **200**, ETag **"article-42-v7"**, Last-Modified **Tue, 02 Jan 2024 03:04:05 GMT**, Cache-Control ở dạng **no-cache, private** hoặc tương đương, và body JSON:

~~~json
{"id":42,"title":"HTTP conditional requests","version":7}
~~~

Kiểm chứng ETag (GET có điều kiện):

~~~bash
curl -i -H 'If-None-Match: "article-42-v7"' \
  http://localhost:8080/api/articles/42
~~~

Trên Linux/macOS, lệnh này thường nhận **304 Not Modified**, **không có body**. Trên Windows CMD, cú pháp quoting khác; có thể dùng PowerShell với lệnh curl.exe và escape dấu nháy đúng shell, hoặc Postman/HTTP client để tránh lỗi do shell.

Kiểm chứng Last-Modified:

~~~bash
curl -i -H 'If-Modified-Since: Tue, 02 Jan 2024 03:04:05 GMT' \
  http://localhost:8080/api/articles/42
~~~

Kỳ vọng **304** vì thời điểm resource không mới hơn timestamp gửi. Nếu đổi request sang **If-None-Match: "old"**, response nên là **200** cùng body.

Kiểm chứng quy tắc ưu tiên:

~~~bash
curl -i \
  -H 'If-None-Match: "old"' \
  -H 'If-Modified-Since: Tue, 02 Jan 2024 03:04:05 GMT' \
  http://localhost:8080/api/articles/42
~~~

Kỳ vọng **200**, vì khi If-None-Match có mặt và không match, If-Modified-Since không được dùng để trả 304. Nếu response thực tế không như kỳ vọng, kiểm tra proxy/filter/container và HTTP headers đã được shell gửi đúng chưa.

### 7.7. MockMvc: test status, body và precondition precedence

**src/test/java/com/example/httpvalidator/ArticleControllerTest.java**

~~~java
package com.example.httpvalidator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ArticleControllerTest {
    @Autowired
    MockMvc mvc;

    private static final String PATH = "/api/articles/42";
    private static final String ETAG = "\"article-42-v7\"";
    private static final String MODIFIED =
            "Tue, 02 Jan 2024 03:04:05 GMT";

    @Test
    void normalGetReturnsBodyAndValidators() throws Exception {
        mvc.perform(get(PATH))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.ETAG, ETAG))
                .andExpect(header().string(
                        HttpHeaders.LAST_MODIFIED, MODIFIED))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.version").value(7));
    }

    @Test
    void matchingETagReturns304WithoutBody() throws Exception {
        mvc.perform(get(PATH)
                .header(HttpHeaders.IF_NONE_MATCH, ETAG))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }

    @Test
    void unchangedDateReturns304WithoutBody() throws Exception {
        mvc.perform(get(PATH)
                .header(HttpHeaders.IF_MODIFIED_SINCE, MODIFIED))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }

    @Test
    void ifNoneMatchTakesPriorityOverIfModifiedSince()
            throws Exception {
        mvc.perform(get(PATH)
                .header(HttpHeaders.IF_NONE_MATCH, "\"older\"")
                .header(HttpHeaders.IF_MODIFIED_SINCE, MODIFIED))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title")
                        .value("HTTP conditional requests"));
    }

    @Test
    void missingResourceRemains404() throws Exception {
        mvc.perform(get("/api/articles/99")
                .header(HttpHeaders.IF_NONE_MATCH, ETAG))
                .andExpect(status().isNotFound());
    }
}
~~~

Chạy test:

~~~bash
./mvnw test
~~~

Đây là **integration test ở tầng Spring MVC** bằng MockMvc; nó xác nhận header/status/body và thứ tự kiểm tra validator qua Spring MVC. Nó **không** kiểm tra hành vi CDN, cache browser, gzip của network connector hay proxy reverse thực tế. Những phần đó cần thử bằng HTTP integration test trong môi trường triển khai.

**Kiểm tra độ chính xác stdout/output:** JSON body trong ví dụ có 3 trường với giá trị cố định. **304 không có body**; lệnh curl -i sẽ chỉ hiển thị header và dòng trống, không tự xuất JSON cũ vì curl không phải browser cache. Các header Date, Connection, Content-Length, Transfer-Encoding có thể thay đổi theo server/HTTP version; không viết test phụ thuộc tất cả byte header mặc định.

## 8. WebRequest.checkNotModified: đánh giá trước khi tạo body đắt tiền

Với resource lớn, nếu để controller serialize toàn bộ JSON/HTML rồi mới băm, 304 có thể chỉ tiết kiệm bandwidth. Spring MVC có API **WebRequest.checkNotModified(...)** để kiểm tra điều kiện ngay khi đã lấy được metadata rẻ.

Ví dụ **đoạn method minh họa trong @Controller có service/repository**, không phải file Java độc lập:

~~~java
@GetMapping("/articles/{id}")
public String viewArticle(
        @PathVariable long id,
        WebRequest webRequest,
        Model model) {

    ArticleMetadata metadata = articleService.metadata(id);

    String etag = "\"article-" + id
            + "-v" + metadata.version() + "\"";
    long lastModifiedMillis =
            metadata.updatedAt().toEpochMilli();

    if (webRequest.checkNotModified(etag, lastModifiedMillis)) {
        return null; // Spring đã chuẩn bị conditional response.
    }

    model.addAttribute("article",
            articleService.loadFullArticle(id));
    return "article";
}
~~~

Cần import **org.springframework.web.context.request.WebRequest**, **org.springframework.ui.Model**, **@GetMapping**, **@PathVariable** và các type nghiệp vụ thực. **articleService.metadata** phải được phép đọc theo authorization policy và trả metadata từ cùng resource/variant được chọn; không bịa implementation để làm snippet này trông như chạy riêng.

Lợi ích là **loadFullArticle(...)** chỉ gọi khi cần tạo body. Nhưng vẫn có các điều kiện:
- Xác thực/ủy quyền phải xảy ra trước khi tiết lộ thông tin resource, kể cả validator.
- Metadata và body phải nhất quán; nếu resource đổi giữa hai truy vấn, tag có thể mô tả v7 còn body là v8.
- Có thể dùng transaction snapshot, version check hoặc đọc lại metadata nếu cần đảm bảo tính nhất quán.
- **checkNotModified(...)** có overload cho ETag, lastModified hoặc cả hai; Spring xử lý tình huống conditional GET/HEAD, và một số precondition của phương thức thay đổi có thể dẫn đến 412.
- Không dùng return null với method/response body tùy ý mà chưa hiểu framework contract; ví dụ Spring MVC View Controller trên đây tương tự pattern được tài liệu hướng dẫn.

**ResponseEntity.eTag(...)** ở mục 7 gọn khi controller đã có representation rẻ. **WebRequest.checkNotModified(...)** thường có ích khi metadata lấy nhanh hơn body nhiều lần.

## 9. ShallowEtagHeaderFilter: tiết kiệm băng thông, không mặc định tiết kiệm xử lý

**ShallowEtagHeaderFilter** của Spring Framework có thể tính một ETag dựa trên **bytes response đã được tạo**, thông thường dùng MD5, rồi so sánh với If-None-Match. Nếu match, client có thể nhận **304** mà không cần tải lại body.

Mô hình:

~~~text
Controller/service chạy, tạo response
          |
          v
Filter buffer response body
          |
          v
Tính shallow ETag trên body
          |
          +-- If-None-Match match -> 304, không gửi body
          |
          +-- không match -> gửi response bình thường + ETag
~~~

**Ưu điểm:** ít code controller, giảm byte truyền trên mạng khi response lớn và không thay đổi.

**Giới hạn quan trọng:**
- Full response đã được tính trước khi filter so sánh, nên **không tiết kiệm CPU/DB/serialization** đáng kể.
- Buffering có thể tăng memory overhead, không phù hợp tùy tiện cho response rất lớn hoặc streaming.
- Filter này **không** là giải pháp đầy đủ cho **If-Match / If-Unmodified-Since** của update API.
- Với async Servlet request, filter cần được map cho **DispatcherType.ASYNC** để hoạt động đúng qua async dispatch.
- Nếu response body đổi theo người dùng/ngôn ngữ/encoding, ETag và cache policy phải phản ánh biến thể; không cho shared cache reuse dữ liệu sai.
- MD5 trong shallow ETag ở đây là cách nhận diện thay đổi body để tiết kiệm bandwidth, **không phải chữ ký bảo mật** hay checksum chống giả mạo.

Với API lấy dữ liệu rất đắt tiền, ưu tiên **application-level version/ETag + early conditional check**. Với static asset, dùng resource handler/versioned URL, Cache-Control và Last-Modified/ETag có chủ đích thay vì thêm filter rộng khắp mà chưa đo hiệu năng.

## 10. Tài nguyên tĩnh: Last-Modified, ETag và URL mang version

Spring MVC **ResourceHttpRequestHandler** có thể xử lý static resource (CSS, JS, ảnh, font) và sử dụng metadata **Resource.lastModified()** để hỗ trợ **Last-Modified/If-Modified-Since** khi có thể. Với Spring Boot web mặc định, các file trong classpath:/static/, classpath:/public/,... có thể được phục vụ qua static resource mapping; cấu hình thực tế ảnh hưởng cache headers.

Ví dụ cấu hình **WebMvcConfigurer** để chỉ minh họa một handler riêng cho public assets:

~~~java
package com.example.httpvalidator;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AssetConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/assets/")
                .setCacheControl(CacheControl.maxAge(
                        Duration.ofMinutes(10)).cachePublic());
    }
}
~~~

Đoạn này là **một file Java độc lập trong project mẫu ở mục 7** nếu đặt đúng package. Khi dùng thêm nó, đặt file CSS vào **src/main/resources/assets/css/app.css**; public URL là **/assets/css/app.css**. Không có nhu cầu thì không phải đăng ký handler custom; Spring Boot có static location mặc định.

**Khuyến nghị cache:**
- Asset **chưa version hóa** có thể thay nội dung tại cùng URL: dùng cache ngắn hoặc no-cache/revalidation.
- Asset **có content hash trong URL** (ví dụ /assets/app.7d2e5c.css): có thể cho cache dài và **immutable** nếu URL luôn đổi khi bytes đổi và release pipeline không xóa bản cũ sớm.
- **index.html** của SPA thường cần cache ngắn hoặc revalidation vì nó tham chiếu đến bundle mới.
- File user-private không nên đặt vào public static root.

Spring MVC có **VersionResourceResolver** tạo/hỗ trợ URL version theo content. Nếu dùng **EncodedResourceResolver** cùng **VersionResourceResolver** để phục vụ file đã gzip/brotli, tài liệu Spring Framework khuyến nghị đăng ký **EncodedResourceResolver trước VersionResourceResolver** để version được tính ổn định theo resource chưa encode. Không nhầm asset fingerprint URL (cache busting) với ETag header: chúng giải quyết bài toán liên quan nhưng không giống nhau.

## 11. Nén HTTP, Vary và tính đúng đắn của ETag

### 11.1. Bật nén trong Spring Boot

Với **Spring Boot 3.3**, có thể bật HTTP response compression:

**src/main/resources/application.yml** (cấu hình **bổ sung**, không bắt buộc cho demo nhỏ):

~~~yaml
server:
  compression:
    enabled: true
    min-response-size: 2KB
    mime-types: application/json,text/html,text/plain,text/css
~~~

Tùy server/config, gzip được thương lượng khi client gửi **Accept-Encoding** phù hợp và response đạt kích thước tối thiểu/mime type thích hợp. Spring Boot hỗ trợ compression trên Tomcat, Jetty, Reactor Netty và Undertow. Với bản Boot 3.3, mặc định minimum thường là **2 KB**. Bài demo JSON mục 7 quá nhỏ nên có thể **không được nén** dù enabled=true.

### 11.2. Nén và validation tối ưu hai thứ khác nhau

- **Compression (gzip/brotli):** giảm **số bytes của body** khi body cần gửi.
- **ETag/Last-Modified/304:** có thể tránh **gửi body hoàn toàn** khi bản cache còn phù hợp.
- **Cache freshness:** có thể tránh **gửi request** cho origin khi response vẫn fresh.

Ba lớp này bổ sung nhau, không phải cùng một kỹ thuật. Một 304 không có body để gzip; một 200 gzip vẫn cần truyền body đã nén; một cache hit fresh có thể không chạm Spring Boot server.

### 11.3. Vary: Accept-Encoding

Khi có cả bản gzip và identity (không nén), cache phải phân biệt các representation:

~~~http
Vary: Accept-Encoding
Content-Encoding: gzip
ETag: "article-v7-gzip"
~~~

Nếu server trả bản chưa nén:

~~~http
Vary: Accept-Encoding
ETag: "article-v7-identity"
~~~

Ví dụ dùng **strong ETag khác nhau** để minh họa vì body bytes của representation sau content coding không giống nhau. Theo HTTP semantics, **strong validator phải thích hợp cho selected representation**; không cho hai biến thể gzip/identity khác bytes dùng cùng strong tag chỉ vì JSON giải nén giống nhau. Một **weak ETag** có thể phù hợp hơn nếu chỉ muốn biểu thị tương đương về ngữ nghĩa giữa hai biến thể.

**Lưu ý:** Header cụ thể do Servlet container/proxy thực sự sinh có thể khác ví dụ trên. Không tự tuyên bố Spring Boot tự tạo chuỗi "article-v7-gzip"; đó là tag minh họa của một hệ thống kiểm soát variant. Nếu dùng ETag ở controller rồi để proxy nén body, phải kiểm tra proxy/container xử lý ETag và Vary đúng chuẩn, không tự sao chép một strong tag cho các bytes khác nhau.

### 11.4. Lỗi thường gặp sau khi bật gzip/CDN

1. Client báo 304 nhưng body cache không tương ứng với representation đã yêu cầu.
2. Cùng URL trả biến thể nén/không nén nhưng thiếu **Vary: Accept-Encoding**.
3. Proxy thay Content-Encoding nhưng không điều chỉnh validator hay cache key đúng.
4. ETag thay đổi qua mỗi deploy dù nội dung không đổi, làm mất tác dụng 304.
5. ETag **không đổi** khi schema/locale/serializer đổi, tạo nguy cơ reuse sai.
6. Response nhỏ chưa đủ **min-response-size**, dẫn đến kết luận sai rằng compression không bật.
7. CDN lưu user-specific JSON vì ứng dụng đặt **public, max-age** không phù hợp.

Debug bằng cách đối chiếu **status, ETag, Last-Modified, Vary, Cache-Control, Content-Encoding, Content-Type** của nhiều request thật với Accept-Encoding khác nhau. Dùng **curl --compressed -i** để kiểm tra gzip; nếu có reverse proxy, thử cả origin trực tiếp (trong môi trường được phép) và URL qua proxy/CDN.

## 12. Caching với dữ liệu động và cập nhật đồng thời

### 12.1. ETag lấy từ phiên bản nghiệp vụ

Giả sử một bài viết có revision 7:

~~~http
GET /api/articles/42 HTTP/1.1

HTTP/1.1 200 OK
ETag: "article-42-v7"
Content-Type: application/json

{"id":42,"title":"Draft A","version":7}
~~~

Người dùng sửa nội dung và gửi:

~~~http
PUT /api/articles/42 HTTP/1.1
If-Match: "article-42-v7"
Content-Type: application/json

{"title":"Draft B"}
~~~

Nếu dữ liệu vẫn phiên bản 7, server có thể cập nhật có điều kiện và tăng lên v8:

~~~http
HTTP/1.1 200 OK
ETag: "article-42-v8"
Content-Type: application/json

{"id":42,"title":"Draft B","version":8}
~~~

Nếu người khác đã cập nhật tới v8 trước đó, request mang **If-Match: "article-42-v7"** không còn hợp lệ: server thường trả **412 Precondition Failed**, không ghi đè.

**Rất quan trọng:** Để chống race, không chỉ **đọc version → so sánh → UPDATE** bằng ba thao tác rời rạc thiếu đồng bộ. Hai request có thể cùng đọc v7 rồi ghi đè. Hãy dùng **optimistic locking (@Version trong JPA)**, conditional UPDATE theo version hoặc transaction/locking đủ mạnh, và chuyển lỗi version conflict thành phản hồi 412 theo hợp đồng API.

### 12.2. Phân biệt 412 với 409 và 428

- **412 Precondition Failed:** client gửi HTTP precondition và nó không được thỏa.
- **409 Conflict:** xung đột trạng thái nghiệp vụ có thể xảy ra mà không nhất thiết gắn với precondition header; chọn theo contract cụ thể.
- **428 Precondition Required:** API yêu cầu client phải cung cấp precondition như If-Match để hạn chế lost update; dùng khi đó là policy có chủ ý.

Không mặc định mọi update thất bại vì validation đều trả 412. Với lỗi dữ liệu đầu vào, 400/422 hoặc domain status thích hợp hơn. Với quyền truy cập, 401/403 vẫn quan trọng.

### 12.3. If-None-Match: * khi tạo mới

Nếu client muốn tạo một resource **chỉ khi nó chưa tồn tại**, có thể gửi điều kiện:

~~~http
PUT /api/articles/100 HTTP/1.1
If-None-Match: *
Content-Type: application/json

{"title":"New article"}
~~~

Nếu representation đã tồn tại, precondition thất bại và request unsafe thường nhận **412**. Phải triển khai kiểm tra tồn tại **có tính nguyên tử** trên database/storage; không dùng "kiểm tra trước rồi insert" nếu hai client có thể đua nhau tạo cùng ID.

### 12.4. Last-Modified cho cập nhật có điều kiện

**If-Unmodified-Since** có thể hỗ trợ trường hợp client không có ETag, nhưng timestamp HTTP-date theo giây có thể không phân biệt hai lần sửa sát nhau. Khi cần kiểm soát lost update nghiêm túc, thường ưu tiên **If-Match strong ETag** liên kết với revision được bảo đảm tính nhất quán.

## 13. Conditional requests với HEAD, Range và streaming

### 13.1. HEAD

**HEAD** tương tự GET về metadata nhưng **không gửi response body**. Một conditional HEAD vẫn có thể nhận 304 theo HTTP semantics. Tuy nhiên HEAD 200 cũng không có body, nên lợi ích tiết kiệm dữ liệu từ conditional HEAD thường nhỏ; tài liệu RFC 9110 lưu ý ít lý do cần dùng HEAD có điều kiện.

Đừng dùng kiểm tra body của HEAD để suy ra tài nguyên rỗng.

### 13.2. Range và If-Range

Đối với file lớn, client có thể gửi:

~~~http
GET /downloads/big-file.zip HTTP/1.1
Range: bytes=1000-1999
If-Range: "file-v12"
~~~

Nếu If-Range là validator mạnh phù hợp, server có thể trả **206 Partial Content** cùng phần bytes yêu cầu. Nếu validator không phù hợp, server **bỏ qua Range** và trả **200** với bản mới đầy đủ, thay vì 412 trong trường hợp If-Range.

Không dùng weak ETag làm If-Range. Nếu ứng dụng không hỗ trợ byte-range, nó có thể trả 200; đừng tự viết logic Range phức tạp chỉ để tạo 304 cho API JSON thông thường.

### 13.3. SSE, streaming, file upload

Với streaming/SSE, response có thể không kết thúc hoặc thay đổi liên tục; shallow ETag cần buffer toàn bộ response thường không phù hợp. Với file upload/download lớn, cần validator gắn đúng bytes và Content-Encoding/Range. Với upload có precondition, thực thi authorization và atomic persistence trước khi xác nhận thành công.

## 14. Vấn đề bảo mật và dữ liệu cá nhân

HTTP caching là một lớp ngoài ứng dụng có thể nằm ở browser, CDN hoặc reverse proxy. Đừng cho phép revalidation hoặc ETag trở thành đường vòng của authorization:

- **Kiểm tra quyền truy cập trước khi trả 304** cho resource private. Một client có ETag cũ không vì thế có quyền xem dữ liệu sau khi bị revoke.
- Dữ liệu tài khoản, thông tin sức khỏe/tài chính hoặc nội dung nhạy cảm nên ưu tiên **Cache-Control: no-store** theo chính sách, thay vì public cache.
- Nếu cho phép cache browser dữ liệu user-specific, dùng **private** và kiểm tra logout/session/account switch; đừng để shared proxy dùng lại body của người khác.
- Không cho ETag chứa token, email, nội dung nhạy cảm dưới dạng dễ suy ra, hoặc hash tiết lộ secret theo cách có thể bị tấn công side-channel.
- Không dùng ETag như CSRF token, session ID hoặc authentication mechanism.
- Các response **401/403/404** phải giữ status/body phù hợp, không đổi thành 304 khi điều kiện xác thực không còn thỏa.
- Nếu có cache key theo URL nhưng dữ liệu khác nhau theo header/tenant/user, thiết kế Vary, Cache-Control và edge cache configuration đúng; không chỉ đặt ETag rồi hy vọng CDN tự hiểu tenant.

Tài nguyên tĩnh công khai thường hợp lý hơn cho shared cache. API có JWT/cookie/session yêu cầu chính sách riêng.

## 15. Debug các lỗi ETag/Last-Modified phổ biến

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/sửa |
| --- | --- | --- |
| **Mọi GET đều 200 dù nội dung không đổi** | Không có validator, request không gửi If-None-Match, ETag thay mỗi lần, cache không lưu body | So response ETag qua 2 lần, xem Cache-Control, request headers và Vary. |
| **304 nhưng curl không hiện JSON** | 304 theo HTTP không gửi body | Dùng body cache từ 200 trước; curl -i đơn lẻ không phải cache browser. |
| **Last-Modified luôn là hiện tại** | Code dùng Instant.now() trên mỗi request | Dùng thời gian sửa thực tế từ resource/version. |
| **Đổi dữ liệu nhưng vẫn 304** | Tag/version không tăng, ETag không phản ánh variant, proxy cache stale | So body, version, locale, Accept, Content-Encoding và CDN metadata. |
| **If-None-Match không trùng nhưng trả 304** | Code xét If-Modified-Since sai thứ tự | Tuân RFC 9110: If-None-Match ưu tiên hơn If-Modified-Since. |
| **PUT với If-Match yếu vẫn được cập nhật** | Bỏ W/ rồi so chuỗi, không dùng strong comparison | Sửa parser/logic precondition; kiểm tra đồng thời transaction. |
| **ETag thay sau mỗi deploy dù body giống nhau** | Dựa vào build timestamp/random ID/JSON order bất ổn | Dựa vào version/hash ổn định của selected representation. |
| **CPU vẫn cao dù thấy nhiều 304** | ShallowEtagHeaderFilter vẫn tạo body | Lấy metadata rẻ và kiểm tra condition trước khi serialize. |
| **Bật gzip làm cache sai** | ETag mạnh dùng chung cho gzip và identity; thiếu Vary | Kiểm tra Content-Encoding/Vary, phân biệt validator theo representation. |
| **CDN cache nhầm dữ liệu tài khoản** | Cache-Control public sai, key thiếu user/variant, authorization bị bỏ qua | Dùng no-store/private, sửa edge policy và purge dữ liệu sai. |
| **If-Modified-Since không bao giờ 304** | Không gửi Last-Modified hợp lệ, timestamp đổi mỗi request, method không phải GET/HEAD | Kiểm tra HTTP-date, thời gian lưu, method, ETag precedence. |
| **Static asset không có ETag** | Resource handler có thể chỉ hỗ trợ Last-Modified, filter không bật | Xem response thật; Last-Modified vẫn đủ cho nhiều use case. |
| **Range download bị hỏng sau update** | Client ghép byte của hai version | Dùng strong validator với If-Range hoặc luôn tải lại bản mới. |
| **Bộ test pass nhưng browser vẫn tải lại** | MockMvc không mô phỏng browser cache/proxy | Kiểm tra Network tab: memory/disk cache, request headers, response policy. |
| **304 xuất hiện khi user bị logout** | Auth/cache đang bypass hoặc test xem lại 304 từ cache | Kiểm tra nguồn response, authorization tại origin và policy private/no-store. |

### Quy trình kiểm chứng theo từng lớp

1. **Origin:** gọi trực tiếp Spring Boot trong môi trường được phép; lưu status, ETag, Last-Modified, Cache-Control, Vary.
2. **Conditional request:** gửi lại If-None-Match và If-Modified-Since; ghi nhận 304/200 và body. Kiểm tra priority khi cả hai có mặt.
3. **Data change:** cập nhật resource thật và chứng minh ETag/Last-Modified thay phù hợp; không chỉ test dataset bất biến.
4. **Browser:** DevTools Network để biết request có được gửi hay được phục vụ trực tiếp từ memory/disk cache.
5. **Proxy/CDN:** so response đi qua edge với origin; lưu ý edge có thể tự 304 hoặc trả cached 200 mà origin không được gọi.
6. **Compression/variants:** thử Accept-Encoding, Accept-Language, Accept, xác minh Content-Encoding, Vary và validator.
7. **Security:** thử lúc chưa login, bị revoke và giữa hai user khác nhau; đảm bảo không leak body/304 nhầm.
8. **Metrics:** đo bytes transferred, 304 rate, response generation time, DB queries và cache hit rate riêng. Nhiều 304 chưa đủ chứng minh CPU giảm.

## 16. Bài tập vận dụng

### Bài 1: Phân biệt freshness và revalidation

Cho server trả **Cache-Control: public, max-age=120** và **ETag: "v9"**.

- Sau 30 giây, browser cache phù hợp có thể dùng response không gọi origin.
- Sau khi stale, browser có thể gửi **If-None-Match: "v9"**.
- Nếu version còn v9 → 304 không body; nếu đã v10 → 200 có body mới.
- Giải thích tại sao không thể yêu cầu “mọi cache hit trả 304”: cache hit fresh không nhất thiết có request.

### Bài 2: Ưu tiên header

Server có **ETag: "x2"**, **Last-Modified** bằng ngày client gửi. Client gửi:

~~~http
GET /api/data HTTP/1.1
If-None-Match: "x1"
If-Modified-Since: Tue, 02 Jan 2024 03:04:05 GMT
~~~

Kết quả theo semantics nên là **200** nếu không có điều kiện khác cản trở, vì If-None-Match không match và được ưu tiên so với If-Modified-Since.

### Bài 3: Chống lost update

Client A và B cùng đọc resource v4. A cập nhật thành v5 với **If-Match: "v4"**. B gửi update cũ với **If-Match: "v4"** sau đó. Hãy thiết kế repository cập nhật nguyên tử theo version và trả 412 cho B. Giải thích vì sao so sánh version rồi UPDATE thiếu locking/optimistic version không đủ.

### Bài 4: Chọn cache policy

Chọn một policy cho: **public versioned JS**, **HTML index SPA**, **API kết quả tìm kiếm công khai**, **API sao kê cá nhân**. Giải thích tại sao asset hash có thể cache dài/immutable nhưng API sao kê cá nhân cần no-store hoặc chính sách rất chặt.

### Bài 5: Thử nén và validator

Tăng kích thước response JSON, bật compression và gọi bằng client chấp nhận gzip. Đối chiếu **Content-Encoding**, **Vary**, **ETag**, status 200/304. Thử thêm một proxy có compression và kiểm tra không dùng strong ETag sai giữa các dạng byte.

## 17. Checklist trước khi merge hoặc triển khai

- [ ] Mỗi representation có ETag hoặc Last-Modified **ổn định và đúng** nếu muốn conditional GET.
- [ ] ETag đổi khi bytes/variant thay đổi; weak/strong được chọn đúng semantics.
- [ ] Last-Modified lấy từ metadata thực, không từ Instant.now() mỗi request.
- [ ] Kiểm tra **If-None-Match trước If-Modified-Since** và **If-Match trước If-Unmodified-Since**.
- [ ] GET/HEAD conditional đúng nhận 304 **không body**; mismatch nhận 200/body khi hợp lệ.
- [ ] PUT/PATCH/DELETE có precondition ghi nếu cần chống lost update, trả 412 khi không thỏa.
- [ ] Persistence update được kiểm soát nguyên tử bằng optimistic locking/transaction.
- [ ] Cache-Control phân biệt **no-cache**, **no-store**, **private/public**, TTL theo loại dữ liệu.
- [ ] Không nhầm HTTP cache với Spring Cache/@Cacheable.
- [ ] Kiểm tra Vary và validator khi có Accept-Encoding/gzip, Accept-Language, content negotiation.
- [ ] Nếu dùng ShallowEtagHeaderFilter, biết nó **không giảm chi phí tính body**, cân nhắc streaming/async.
- [ ] Static asset có policy phù hợp với URL version/hash và không xóa bundle cũ quá sớm.
- [ ] Auth và authorization vẫn bắt buộc khi request có ETag cũ; dữ liệu riêng không được shared cache.
- [ ] MockMvc test 200/304/priority/404 chạy; có HTTP test trên runtime thật nếu proxy/CDN/nén quan trọng.
- [ ] Logs/metrics không lộ token hoặc dữ liệu nhạy cảm; đo CPU và bandwidth riêng.

## 18. Câu hỏi tự kiểm tra

**1. Cache-Control: no-cache có cấm lưu response?** Không. Nó yêu cầu revalidation trước khi reuse. Muốn cấm lưu nên dùng no-store.

**2. Vì sao 304 không có JSON body?** Client/cache đã có representation trước; 304 chỉ xác nhận dùng lại bản cũ và cập nhật metadata. Một curl đơn lẻ không có body cache để tự hiển thị.

**3. Nếu ETag và Last-Modified cùng có, client gửi cả hai điều kiện thì ưu tiên gì?** If-None-Match trước If-Modified-Since trên conditional GET. Đừng kết hợp bằng logic OR/AND tự tạo.

**4. Weak ETag có dùng để chống overwrite với If-Match không?** Không theo so sánh strong của If-Match; dùng strong validator liên kết với version chính xác.

**5. Vì sao version DB chưa chắc là strong ETag đúng?** Vì một version row có thể sinh nhiều body khác bytes: locale, serializer, schema, compression, quyền của người xem. Validator cần gắn với selected representation.

**6. Khi dùng ShallowEtagHeaderFilter, 304 có chứng minh DB không bị query lại?** Không. Filter thường buffer và hash body sau khi controller chạy, nên nó chủ yếu giảm bandwidth.

**7. Last-Modified có thể bỏ sót hai lần sửa trong một giây không?** Có; HTTP-date theo giây. Khi cần concurrency control mạnh, dùng version/If-Match/optimistic locking.

**8. Spring MVC có tự động xử lý conditional GET với ResponseEntity.eTag(...) không?** Có, trong đường xử lý MVC phù hợp; hãy test cụ thể status/header/body theo version Spring Framework đang dùng.

**9. Nén gzip có làm cùng strong ETag dùng chung cho bản không nén trở nên không phù hợp không?** Có thể: nếu representation bytes khác, phải chọn validator phản ánh biến thể hoặc weak semantics và Vary phù hợp.

**10. Có ETag nghĩa là client được xem resource dù đã logout?** Không. ETag không thay authorization; resource private phải kiểm tra quyền ngay cả khi request có If-None-Match.

## 19. Tài liệu chính thức

1. [RFC 9110 — HTTP Semantics, Conditional Requests](https://httpwg.org/specs/rfc9110.html): định nghĩa ETag, Last-Modified, If-None-Match, If-Match, If-Modified-Since, If-Unmodified-Since, If-Range, thứ tự preconditions và 304/412.
2. [RFC 9111 — HTTP Caching](https://httpwg.org/specs/rfc9111.html): Cache-Control, freshness, revalidation, cập nhật cached response sau 304.
3. [Spring Framework — HTTP Caching (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): ResponseEntity.eTag/lastModified, CacheControl, WebRequest.checkNotModified và Shallow ETag.
4. [Spring Framework — Shallow ETag Filter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): ShallowEtagHeaderFilter, giới hạn về CPU và async dispatch.
5. [Spring Framework — Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html): ResourceHttpRequestHandler, Last-Modified, ResourceResolver và versioned URLs.
6. [Spring Boot 3.3 — Enable HTTP Response Compression](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): server.compression.enabled, min-response-size, mime-types.
7. [MDN — ETag](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/ETag): ví dụ strong/weak tags và conditional requests.

**Tổng kết:** **Cache-Control** quyết định khi nào cached response có thể được dùng; **ETag/Last-Modified** giúp hỏi server liệu bản cũ có còn hợp lệ; **304** giảm bandwidth khi có bản cache để reuse; **If-Match + 412** có thể bảo vệ cập nhật đồng thời nếu persistence thực thi điều kiện một cách nguyên tử. Trong Spring Boot, ưu tiên **validator dựa trên metadata/version ổn định**, test 200/304/412 phù hợp với nghiệp vụ, và kiểm tra cache policy/Content-Encoding/Vary cùng security trước khi đưa vào production.
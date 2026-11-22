# Chọn phiên bản Spring Boot, Spring Data, client và Elasticsearch tương thích

Khi khởi tạo một dự án Spring Data Elasticsearch, cần chọn một bộ phiên bản có thể làm việc cùng nhau. Bộ này gồm Java runtime, Spring Boot và Spring Framework, Spring Data Elasticsearch, thư viện client dùng để gửi request, cùng Elasticsearch server nhận và xử lý request. Chỉ chọn phiên bản mới nhất của từng thành phần rồi ghép lại có thể dẫn đến lỗi dependency, lỗi API hoặc lỗi giao tiếp khi chạy ứng dụng.

Nguyên tắc thực tế là chọn Spring Boot trước, để dependency management của Spring Boot quản lý phiên bản Spring Data và các thư viện liên quan, sau đó chọn Elasticsearch server theo ma trận tương thích của đúng dòng Spring Data Elasticsearch. Client nên dùng phiên bản được bộ dependency đó quản lý. Cần xác nhận toàn bộ tổ hợp bằng dependency tree và một bài kiểm tra tích hợp với Elasticsearch server thực tế.

## 1. Những thành phần cần tương thích

Một ứng dụng Spring Data Elasticsearch thường có các lớp thành phần sau:

| Thành phần | Vai trò | Điều cần kiểm tra |
|---|---|---|
| Java runtime | Chạy ứng dụng và các thư viện | Phiên bản Java tối thiểu của Spring Boot và các thư viện |
| Spring Boot | Cung cấp auto-configuration, starter và dependency management | Phiên bản phù hợp với nền tảng ứng dụng và JDK |
| Spring Framework | Nền tảng container, DI, transaction và các API Spring | Phiên bản do Spring Boot quản lý |
| Spring Data Elasticsearch | Repository, mapping, `ElasticsearchOperations` và tích hợp Spring Data | Release train phù hợp với Spring Boot và Elasticsearch |
| Elasticsearch Java client | Chuyển lời gọi Java thành request gửi đến server | Artifact và phiên bản tương thích với Spring Data Elasticsearch |
| Elasticsearch server | Lưu index, lập chỉ mục và thực thi truy vấn | Phiên bản server nằm trong dải được Spring Data Elasticsearch hỗ trợ |

Các thành phần này liên quan với nhau nhưng không phải cùng một sản phẩm và cũng không dùng chung một số phiên bản. Ví dụ, Spring Boot có version riêng, Spring Data có release train riêng, thư viện `elasticsearch-java` có version riêng và Elasticsearch server cũng có version riêng.

### Spring Boot quản lý dependency như thế nào?

Spring Boot cung cấp một bộ dependency management thông qua BOM `spring-boot-dependencies`. BOM này quy định các phiên bản đã được nhóm Spring lựa chọn và kiểm tra cùng nhau. Khi dùng Spring Boot starter, Gradle hoặc Maven có thể lấy các phiên bản tương ứng từ BOM thay vì để từng dự án tự chọn phiên bản cho mỗi thư viện.

Với Spring Data Elasticsearch, starter thường dùng là:

```text
org.springframework.boot:spring-boot-starter-data-elasticsearch
```

Starter kéo theo Spring Data Elasticsearch và các dependency cần thiết cho cấu hình của Spring Boot. Trong dự án Spring Boot thông thường, nên để Boot quản lý các phiên bản này. Việc tự khai báo một version khác cho `spring-data-elasticsearch` hoặc `elasticsearch-java` có thể tạo ra một tổ hợp mà Spring Boot chưa kiểm tra.

### Spring Data Elasticsearch và client có vai trò gì?

Spring Data Elasticsearch cung cấp lớp tích hợp với hệ sinh thái Spring: `ElasticsearchRepository`, `ElasticsearchOperations`, mapping entity/document và cấu hình client. Client là thư viện giao tiếp cấp thấp hơn, chịu trách nhiệm gửi request đến Elasticsearch server.

Ứng dụng có thể thao tác qua repository hoặc `ElasticsearchOperations`, nhưng ở bên dưới vẫn cần một client phù hợp. Việc một class repository biên dịch được không chứng minh rằng client và server có thể giao tiếp đúng trong môi trường chạy thật.

## 2. Hiểu các thế hệ API client

Các phiên bản Spring Data Elasticsearch khác nhau có thể dùng các API client khác nhau. Đây là điểm cần chú ý khi nâng cấp từ một dự án cũ.

### Thế hệ dùng `RestHighLevelClient`

Các dòng Spring Data Elasticsearch cũ, tiêu biểu là dòng 4.x, tích hợp với Elasticsearch 7.x và sử dụng Elasticsearch REST High Level Client (`RestHighLevelClient`) trong cấu hình phổ biến.

Artifact cũ thường gặp:

```text
org.elasticsearch.client:elasticsearch-rest-high-level-client
```

API này thuộc thế hệ client cũ. Khi chuyển sang các dòng Spring Data Elasticsearch mới, không nên giữ cấu hình cũ rồi thêm client mới vào classpath với hy vọng cả hai tự tương thích.

### Thế hệ dùng Elasticsearch Java API Client

Spring Data Elasticsearch 5.x chuyển sang Elasticsearch Java API Client, có artifact:

```text
co.elastic.clients:elasticsearch-java
```

API client mới có lớp chính `co.elastic.clients.elasticsearch.ElasticsearchClient`. Nó sử dụng REST client transport ở tầng thấp hơn và cung cấp API Java được sinh theo Elasticsearch API.

Trong các dự án Spring Boot mới, thường không cần tự tạo transport và client nếu auto-configuration đã đáp ứng nhu cầu. Nếu cần cấu hình tùy chỉnh, hãy làm theo hướng dẫn đúng phiên bản Spring Data Elasticsearch đang dùng.

### Không trộn hai thế hệ client tùy tiện

`RestHighLevelClient` và `ElasticsearchClient` thuộc hai thế hệ API khác nhau. Việc thêm cả hai dependency vào một ứng dụng không tự làm chúng tương thích. Nó có thể kéo theo nhiều phiên bản thư viện HTTP, JSON hoặc core Elasticsearch khác nhau, gây xung đột dependency và làm cấu hình khó kiểm soát.

Khi nâng cấp, hãy chuyển code cấu hình và code gọi client theo API mà phiên bản Spring Data mới hỗ trợ. Không giữ bean hoặc import của client cũ nếu dòng Spring Data mới không còn sử dụng chúng.

## 3. Ma trận phiên bản theo thế hệ

Bảng dưới đây giúp nhận diện các thế hệ công nghệ thường gặp. Đây là định hướng ở mức major version, không phải cam kết rằng mọi phiên bản patch trong một hàng đều tương thích với nhau.

| Thế hệ ứng dụng | Dòng Spring Data Elasticsearch thường đi cùng | Dòng Elasticsearch server thường gặp | Client thường dùng |
|---|---|---|---|
| Spring Boot 2.x | Spring Data Elasticsearch 4.x | Elasticsearch 7.x | `RestHighLevelClient` |
| Spring Boot 3.x | Spring Data Elasticsearch 5.x | Elasticsearch 8.x | Elasticsearch Java API Client (`elasticsearch-java`) |
| Spring Boot 4.x | Spring Data Elasticsearch 6.x | Elasticsearch 9.x | Elasticsearch Java API Client (`elasticsearch-java`) |

Hãy dùng bảng này để nhận diện thế hệ, sau đó tra ma trận tương thích chính thức của đúng phiên bản Spring Data Elasticsearch. Không suy ra rằng mọi Spring Boot 3.x đều hỗ trợ mọi Elasticsearch 8.x, hoặc mọi Spring Data 5.x đều hỗ trợ mọi bản server 8.x.

### Vì sao phải kiểm tra đến minor và patch version?

Một dòng major có thể có nhiều minor release. Mỗi minor có thể cập nhật phiên bản client, sửa lỗi tích hợp hoặc bổ sung hỗ trợ cho một phiên bản Elasticsearch server cụ thể. Ví dụ, Spring Data Elasticsearch 5.2.x và 5.5.x đều thuộc major 5 nhưng không nhất thiết dùng cùng một phiên bản client hoặc có cùng ma trận server được hỗ trợ.

Vì vậy, cần kiểm tra đồng thời:

1. Phiên bản Spring Boot đang dùng.
2. Phiên bản Spring Data Elasticsearch mà BOM của Boot thực sự chọn.
3. Phiên bản client mà Spring Data/BOM chọn.
4. Phiên bản Elasticsearch server nằm trong ma trận hỗ trợ của đúng bản Spring Data Elasticsearch.

Nếu dự án dùng Spring Data độc lập, không dùng Spring Boot BOM, cần tra release train BOM và hướng dẫn tương thích của Spring Data tương ứng. Không lấy bảng major ở trên làm thay thế cho ma trận minor/patch.

## 4. Quy trình chọn phiên bản cho dự án mới

### Bước 1: Xác định nền tảng Java và Spring Boot

Trước hết, xác định JDK mà môi trường phát triển, CI và môi trường triển khai có thể sử dụng. Sau đó chọn phiên bản Spring Boot có hỗ trợ JDK đó và phù hợp với vòng đời bảo trì của dự án.

Spring Boot 3.x yêu cầu Java 17 trở lên. Các dòng Spring Boot khác có thể có baseline Java khác nhau, vì vậy hãy kiểm tra yêu cầu Java trong tài liệu của đúng phiên bản Boot thay vì suy đoán từ phiên bản đang cài trên máy.

Ví dụ, nếu dự án bị giới hạn ở một JDK cũ, việc chọn Spring Boot mới hơn chỉ vì nó có tính năng mới có thể khiến ứng dụng không khởi động được. JDK cần được thống nhất giữa IDE, Gradle/Maven, CI và runtime triển khai.

### Bước 2: Chọn Spring Boot và dùng starter

Với ứng dụng Spring Boot, thêm starter chính thức và để Boot quản lý phiên bản Spring Data Elasticsearch.

Ví dụ Gradle Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<dependency-management-plugin-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'
}
```

Ví dụ Maven:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>${spring-boot.version}</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-elasticsearch</artifactId>
    </dependency>
</dependencies>
```

Các chuỗi placeholder trong ví dụ cần được thay bằng phiên bản đã chọn của dự án. Không sao chép nguyên placeholder vào file build.

Không cần khai báo riêng version cho `spring-data-elasticsearch` hoặc `elasticsearch-java` trong trường hợp thông thường. Nếu có lý do bắt buộc phải override, cần kiểm tra dependency tree và ma trận tương thích trước khi sử dụng.

### Bước 3: Xác định Spring Data Elasticsearch thực tế được resolve

Không nên dựa vào suy đoán rằng một phiên bản Boot luôn kéo theo một phiên bản Spring Data cụ thể. Hãy xem dependency được build tool resolve.

Với Gradle:

```bash
./gradlew dependencyInsight \
  --dependency spring-data-elasticsearch \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency elasticsearch-java \
  --configuration runtimeClasspath
```

Có thể xem toàn bộ runtime dependency tree bằng:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Với Maven:

```bash
mvn dependency:tree \
  -Dincludes=org.springframework.data:spring-data-elasticsearch

mvn dependency:tree \
  -Dincludes=co.elastic.clients:elasticsearch-java
```

Nếu dependency tree có nhiều phiên bản của cùng một thư viện hoặc xuất hiện đồng thời các client thế hệ cũ và mới, hãy tìm dependency trực tiếp hoặc dependency bắc cầu đã đưa chúng vào.

### Bước 4: Chọn Elasticsearch server theo ma trận Spring Data

Sau khi biết chính xác phiên bản Spring Data Elasticsearch, mở tài liệu tương thích của phiên bản đó và chọn Elasticsearch server nằm trong dải được hỗ trợ. Cần kiểm tra cả phiên bản minor và patch nếu tài liệu nêu rõ phiên bản server tương ứng.

Không nên chọn server chỉ dựa vào số major. Một ứng dụng có thể compile thành công với client nhưng vẫn gặp lỗi runtime khi server thiếu API, có thay đổi mapping hoặc có hành vi khác với phiên bản mà Spring Data hỗ trợ.

### Bước 5: Đồng bộ phiên bản giữa môi trường

Sau khi chọn phiên bản, cần thống nhất image Elasticsearch trong máy phát triển, CI, integration test và môi trường triển khai. Không dùng tag `latest` cho một hệ thống cần kết quả tái lập, vì tag này có thể trỏ tới phiên bản khác ở lần tải sau.

Nên ghi nhận ít nhất các thông tin sau trong tài liệu dự án hoặc cấu hình build:

- JDK được dùng để build và chạy ứng dụng.
- Phiên bản Spring Boot.
- Phiên bản Spring Data Elasticsearch được resolve.
- Phiên bản Elasticsearch client được resolve.
- Phiên bản Elasticsearch server/image.

## 5. Cấu hình kết nối cơ bản trong Spring Boot

Khi starter và phiên bản tương thích đã được chọn, Spring Boot có thể tự cấu hình client dựa trên properties.

Ví dụ `application.yml` cho một Elasticsearch server phát triển chạy tại máy local:

```yaml
spring:
  elasticsearch:
    uris: http://localhost:9200
```

Nếu server yêu cầu xác thực, có thể cấu hình thông tin đăng nhập qua biến môi trường hoặc secret manager. Không commit mật khẩu, API key hoặc thông tin xác thực thật vào repository.

Tên property và các tùy chọn bảo mật có thể thay đổi theo dòng Spring Boot. Hãy tham khảo phần Elasticsearch properties trong tài liệu của phiên bản Boot cụ thể. Với cluster dùng HTTPS, cần cấu hình TLS và chứng chỉ đúng cách; không tắt xác minh chứng chỉ để né lỗi kết nối trong môi trường thật.

### Kiểm tra Elasticsearch server đang chạy

Có thể gọi endpoint gốc để xác nhận server có phản hồi và xem thông tin phiên bản:

```bash
curl http://localhost:9200
```

Nếu cluster bật bảo mật, request cần thông tin xác thực và giao thức HTTPS phù hợp. Kết quả trả về thường chứa tên cluster, tên node, version number và thông tin build. Hãy đối chiếu version number với phiên bản đã chọn trong ma trận.

### Cấu hình thủ công client khi thực sự cần

Spring Boot auto-configuration thường đủ cho kết nối cơ bản. Chỉ tạo cấu hình client thủ công khi cần tùy chỉnh transport, TLS, authentication, timeout hoặc hành vi connection pool mà properties mặc định không đáp ứng.

Khi cấu hình thủ công:

- Dùng đúng kiểu client mà phiên bản Spring Data yêu cầu.
- Tạo và quản lý vòng đời transport/client theo hướng dẫn của phiên bản đó.
- Tránh khai báo bean trùng với bean auto-configured nếu không chủ ý thay thế.
- Đảm bảo tài nguyên HTTP được đóng đúng lúc khi ứng dụng dừng.
- Kiểm tra cách truyền credentials và trust material, không ghi bí mật vào log.

Không sao chép cấu hình `RestHighLevelClient` từ một hướng dẫn Spring Data 4.x vào dự án Spring Data 5.x hoặc mới hơn mà không chuyển đổi API tương ứng.

## 6. Client và server có cần cùng một version không?

Client và server là hai artifact độc lập nên số version không nhất thiết giống hệt nhau. Tuy nhiên, điều đó không có nghĩa mọi tổ hợp đều được hỗ trợ.

Với Elasticsearch Java API Client, chính sách tương thích của client cho biết phạm vi server mà client có thể giao tiếp. Client có thể hỗ trợ một số minor version server mới hơn, nhưng không nên mặc định client mới có thể gọi mọi API trên server cũ. Một API được thêm vào client có thể chưa tồn tại ở server cũ.

Ngoài tương thích ở tầng client-server, còn phải xét Spring Data Elasticsearch. Spring Data có thể giới hạn phiên bản Elasticsearch server được hỗ trợ, dù client riêng lẻ có khả năng giao tiếp với một dải server rộng hơn.

Do đó, cần thỏa mãn đồng thời hai điều kiện:

1. Client version phù hợp với server theo chính sách tương thích của Elasticsearch Java client.
2. Server version nằm trong ma trận tương thích của phiên bản Spring Data Elasticsearch đang sử dụng.

Trong dự án Spring Boot, cách an toàn là giữ client ở phiên bản do BOM/starter quản lý và chọn server theo tài liệu Spring Data. Chỉ override client khi có yêu cầu cụ thể, có kiểm tra tương thích và có integration test chứng minh hành vi cần thiết.

## 7. Nâng cấp giữa các thế hệ

Nâng cấp major có thể ảnh hưởng đến nhiều lớp cùng lúc. Ví dụ, chuyển từ Spring Boot 2.x / Spring Data Elasticsearch 4.x sang Spring Boot 3.x / Spring Data Elasticsearch 5.x thường đồng thời liên quan đến Java baseline, Spring Framework, Jakarta namespace và Elasticsearch client API.

Một số thay đổi cần xem xét:

| Hạng mục | Khi nâng cấp cần kiểm tra |
|---|---|
| Java | JDK tối thiểu, toolchain Gradle/Maven và runtime triển khai |
| Spring Framework | API đã thay đổi hoặc bị loại bỏ giữa các major version |
| Jakarta | Các package `javax.*` liên quan có thể cần chuyển sang `jakarta.*` khi nâng cấp Spring Boot 3 |
| Spring Data Elasticsearch | Repository, mapping annotation, template và cấu hình client |
| Elasticsearch client | Chuyển từ `RestHighLevelClient` sang Elasticsearch Java API Client khi dòng Spring Data yêu cầu |
| Elasticsearch server | API, mapping, security defaults và tính năng đã thay đổi giữa các major version |
| Index hiện có | Mapping, analyzer, template và khả năng cần reindex |

Không nên nâng cấp đồng thời mọi thành phần mà không có bước kiểm tra trung gian. Hãy đọc hướng dẫn nâng cấp của Spring Boot, Spring Data Elasticsearch và Elasticsearch theo đúng các phiên bản nguồn/đích.

Một trình tự nâng cấp có thể áp dụng:

1. Ghi lại phiên bản JDK, Boot, Spring Data, client và server hiện tại.
2. Xác định phiên bản đích và kiểm tra các bước nâng cấp bắt buộc.
3. Nâng JDK và Spring Boot theo yêu cầu của phiên bản đích.
4. Để Boot BOM resolve phiên bản Spring Data và client tương ứng.
5. Chuyển code cấu hình/client cũ sang API mới nếu cần.
6. Kiểm tra mapping, repository query, custom query và serialization.
7. Chạy integration test với Elasticsearch server đúng phiên bản đích.
8. Lập kế hoạch reindex hoặc migration index nếu mapping/API thay đổi.
9. Triển khai theo từng môi trường và theo dõi lỗi kết nối, indexing, query.

## 8. Kiểm tra tương thích trong quá trình phát triển

Biên dịch thành công chỉ xác nhận rằng code và dependency có thể phối hợp ở mức compile. Nó không xác nhận server đang chạy đúng version hoặc API request thực tế được hỗ trợ.

Nên có ít nhất các lớp kiểm tra sau:

### Kiểm tra dependency

- Xem phiên bản Spring Data Elasticsearch và client thực tế trong runtime classpath.
- Tìm dependency bị override ngoài BOM.
- Tránh để hai thế hệ client cùng xuất hiện ngoài chủ ý.
- Kiểm tra dependency convergence nếu dự án có nhiều module.

### Kiểm tra kết nối

- Xác nhận URI, DNS, port và giao thức HTTP/HTTPS.
- Kiểm tra authentication và quyền truy cập index.
- Kiểm tra TLS trust chain khi dùng HTTPS.
- Đọc version của server từ endpoint hoặc thông tin cluster.

### Kiểm tra tích hợp

Chạy ứng dụng và thực hiện các thao tác thật với server tương ứng:

- Tạo hoặc xác nhận index và mapping.
- Lưu một document.
- Đọc document theo ID.
- Chạy một truy vấn repository hoặc `ElasticsearchOperations`.
- Cập nhật và xóa document.
- Kiểm tra lỗi xác thực, timeout và server không khả dụng.

Với pipeline CI, nên dùng một Elasticsearch container có tag phiên bản cố định và trùng với phiên bản server mà môi trường dự kiến triển khai. Integration test cần xác nhận cả khởi tạo index/mapping và thao tác truy vấn, vì lỗi mapping có thể chỉ xuất hiện khi gửi request.

## 9. Các lỗi thường gặp khi chọn sai phiên bản

### `NoSuchMethodError` hoặc `ClassNotFoundException`

Các lỗi này thường xuất hiện khi code được biên dịch với một API nhưng lúc chạy lại nạp một phiên bản thư viện khác, hoặc khi dependency bị xung đột. Hãy kiểm tra runtime dependency tree, BOM và các version được khai báo thủ công.

### Không tìm thấy class client cũ

Một hướng dẫn cũ có thể import `RestHighLevelClient`, trong khi dự án hiện tại sử dụng dòng Spring Data đã chuyển sang Elasticsearch Java API Client. Hãy đối chiếu ví dụ với đúng version của Spring Data và thay đổi cấu hình theo API mới.

### Client kết nối được nhưng request bị server từ chối

Kết nối TCP/HTTP thành công không bảo đảm server hỗ trợ API mà client gửi. Kiểm tra server version, endpoint, request format và ma trận tương thích của client lẫn Spring Data.

### Lỗi mapping hoặc index khi khởi động

Mapping có thể không tương thích với index cũ hoặc server version. Kiểm tra mapping hiện có, index template và cấu hình tạo index. Nếu thay đổi không thể áp dụng trực tiếp, tạo index mới và reindex theo kế hoạch.

### Local chạy được nhưng CI hoặc production lỗi

Nguyên nhân thường là các môi trường dùng JDK, image Elasticsearch, cấu hình security hoặc biến môi trường khác nhau. Pin phiên bản và đưa integration test vào CI để phát hiện sớm khác biệt.

### Dùng tag `latest`

Tag `latest` khiến cùng một cấu hình có thể tải về server version khác nhau theo thời điểm. Khi server được cập nhật ngoài dự kiến, ứng dụng có thể gặp thay đổi API hoặc hành vi. Dùng tag version cụ thể và cập nhật có chủ đích.

## 10. Ví dụ cấu hình dependency và server có kiểm soát phiên bản

Ví dụ sau minh họa cách đặt version tại một nơi và tránh ghi đè version của client trong dự án Spring Boot. Các placeholder phải được thay bằng bộ version đã xác nhận qua BOM và ma trận tương thích.

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    // Thêm thư viện Testcontainers Elasticsearch tương thích với
    // phiên bản Testcontainers mà dự án đang quản lý.
}
```

Ví dụ cấu hình môi trường local:

```yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS:http://localhost:9200}
```

Ví dụ chạy server local với Docker:

```bash
docker run --name elasticsearch-dev \
  -p 9200:9200 \
  -e discovery.type=single-node \
  -e xpack.security.enabled=false \
  docker.elastic.co/elasticsearch/elasticsearch:<elasticsearch-version>
```

Lệnh trên chỉ là ví dụ cho môi trường phát triển cô lập. Hãy thay placeholder bằng phiên bản đã được xác nhận tương thích. Cấu hình tắt security không phù hợp với môi trường dùng chung hoặc production; các môi trường đó cần authentication, TLS và quản lý secret đúng cách.

## 11. Checklist trước khi chốt bộ phiên bản

Trước khi bắt đầu code hoặc nâng cấp, hãy xác nhận các điểm sau:

- [ ] JDK đáp ứng yêu cầu của Spring Boot đã chọn.
- [ ] Phiên bản Spring Boot được pin trong build file.
- [ ] Dự án dùng `spring-boot-starter-data-elasticsearch` nếu đi theo Spring Boot.
- [ ] Spring Data Elasticsearch được resolve từ BOM và đã được xác định rõ version.
- [ ] Elasticsearch client được quản lý đồng bộ với bộ dependency của Spring Data.
- [ ] Client API đang dùng đúng thế hệ; không còn cấu hình cũ không tương thích.
- [ ] Elasticsearch server nằm trong ma trận hỗ trợ của đúng phiên bản Spring Data Elasticsearch.
- [ ] Tag Elasticsearch image được pin, không dùng `latest`.
- [ ] Local, CI và môi trường triển khai dùng bộ version đã thống nhất.
- [ ] Integration test xác nhận kết nối, mapping, ghi, đọc, cập nhật, xóa và truy vấn.
- [ ] Có kế hoạch xử lý mapping hoặc reindex nếu nâng cấp server hay Spring Data làm thay đổi index.

## 12. Kết luận

Chọn phiên bản tương thích là việc chọn một tổ hợp có kiểm soát giữa Java, Spring Boot, Spring Data Elasticsearch, Elasticsearch client và Elasticsearch server. Với dự án Spring Boot, hãy để Boot BOM quản lý Spring Data và client, sau đó chọn server theo ma trận tương thích của đúng phiên bản Spring Data. Bảng major version chỉ giúp nhận diện thế hệ; quyết định cuối cùng cần dựa vào minor/patch version trong tài liệu chính thức.

Khi đã chốt tổ hợp, pin các phiên bản trong build và container image, kiểm tra dependency tree, cấu hình bảo mật đúng môi trường và chạy integration test với server thật. Cách làm này giúp phát hiện sớm lỗi do API client, mapping hoặc khác biệt phiên bản trước khi đưa ứng dụng vào vận hành.

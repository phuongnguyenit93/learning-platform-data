# Tổ chức gói mã nguồn và cấu hình theo môi trường

Một ứng dụng Spring Data Elasticsearch thường có nhiều phần phối hợp với nhau: lớp khởi động Spring Boot, model tài liệu, repository, service xử lý nghiệp vụ, cấu hình kết nối Elasticsearch, cấu hình index và các tệp cấu hình cho từng môi trường. Nếu đặt tất cả trong một package hoặc để thông tin kết nối rải rác trong mã nguồn, ứng dụng sẽ khó mở rộng, kiểm thử và triển khai.

Tổ chức mã nguồn tốt giúp người phát triển tìm được đúng nơi cần thay đổi, làm rõ ranh giới giữa nghiệp vụ và hạ tầng tìm kiếm, đồng thời giảm nguy cơ dùng nhầm endpoint hoặc thông tin xác thực giữa local, development, staging và production. Cấu hình theo môi trường cho phép cùng một artifact chạy ở nhiều môi trường bằng cách thay đổi cấu hình bên ngoài.

Trong bài này, ta xây dựng cách tổ chức package cho một ứng dụng Spring Boot dùng Spring Data Elasticsearch, phân biệt phần nghiệp vụ với phần tích hợp Elasticsearch, rồi thiết lập cấu hình dùng chung và cấu hình riêng cho từng môi trường.

## 1. Những thành phần thường có trong ứng dụng

Một ứng dụng tìm kiếm sản phẩm có thể gồm các thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| Application | Khởi động Spring Boot và kích hoạt component scanning, auto-configuration |
| Domain | Mô hình và quy tắc nghiệp vụ của ứng dụng |
| Document hoặc persistence model | Biểu diễn dữ liệu được lưu trong Elasticsearch |
| Repository | Truy cập document thông qua Spring Data Elasticsearch |
| Application service | Điều phối nghiệp vụ và gọi repository hoặc ElasticsearchOperations |
| Web/API | Nhận HTTP request, kiểm tra đầu vào và trả response |
| Configuration | Khai báo các bean và thiết lập tích hợp cần thiết |
| Resources | Chứa application.yml, cấu hình theo profile và mapping JSON |
| Tests | Kiểm tra logic, repository và hành vi tích hợp với Elasticsearch |

Không phải dự án nào cũng cần tách toàn bộ thành các module riêng. Một ứng dụng nhỏ có thể dùng một module Gradle hoặc Maven với các package rõ ràng. Khi hệ thống lớn lên, các ranh giới này giúp tách module hoặc service dễ dàng hơn.

## 2. Chọn cách tổ chức package

Có hai cách tổ chức phổ biến: theo tầng kỹ thuật và theo chức năng nghiệp vụ. Cả hai đều có thể dùng với Spring Data Elasticsearch; lựa chọn phụ thuộc vào quy mô và cách đội ngũ phát triển làm việc.

### 2.1. Tổ chức theo tầng kỹ thuật

Với cách này, các lớp cùng vai trò được đặt trong một package:

~~~text
com.example.catalog
├── CatalogApplication.java
├── controller
│   └── ProductController.java
├── service
│   └── ProductSearchService.java
├── repository
│   └── ProductRepository.java
├── document
│   └── ProductDocument.java
├── config
│   └── ElasticsearchConfiguration.java
└── dto
    ├── ProductSearchRequest.java
    └── ProductSearchResponse.java
~~~

Ưu điểm là cấu trúc dễ hiểu với dự án nhỏ, người mới có thể tìm các controller, service hoặc repository ở một vị trí quen thuộc. Nhược điểm xuất hiện khi dự án có nhiều chức năng: package service và repository trở nên lớn, các lớp của một chức năng bị phân tán qua nhiều thư mục. Khi sửa một tính năng, người phát triển thường phải mở nhiều package.

### 2.2. Tổ chức theo chức năng nghiệp vụ

Với cách này, các lớp phục vụ cùng một chức năng được đặt cạnh nhau:

~~~text
com.example.catalog
├── CatalogApplication.java
├── product
│   ├── api
│   │   ├── ProductController.java
│   │   ├── ProductSearchRequest.java
│   │   └── ProductSearchResponse.java
│   ├── application
│   │   └── ProductSearchService.java
│   ├── domain
│   │   └── Product.java
│   └── infrastructure
│       └── elasticsearch
│           ├── ProductDocument.java
│           └── ProductRepository.java
├── category
│   ├── api
│   ├── application
│   ├── domain
│   └── infrastructure
└── shared
    └── config
        └── ElasticsearchConfiguration.java
~~~

Ưu điểm là mã của một chức năng tập trung trong một khu vực. Khi bổ sung chức năng category hoặc order, nhóm có thể mở rộng package tương ứng mà không làm package toàn cục phình to. Cách này phù hợp với ứng dụng có nhiều chức năng nghiệp vụ hoặc đang phát triển theo hướng modular monolith.

Đổi lại, cần thống nhất ý nghĩa của các package con. Nếu mỗi chức năng tự tạo một kiểu cấu trúc khác nhau, dự án sẽ khó điều hướng. Chỉ nên tạo package domain, application, api và infrastructure khi chúng thực sự giúp thể hiện ranh giới trách nhiệm.

### 2.3. Nên chọn cách nào?

Với ứng dụng nhỏ, tổ chức theo tầng kỹ thuật là đủ. Khi số chức năng tăng, tổ chức theo chức năng thường giúp giảm phụ thuộc giữa các nhóm mã. Một lựa chọn thực tế là tổ chức theo chức năng ở cấp cao nhất, rồi dùng các tầng nhỏ bên trong mỗi chức năng.

Dù chọn cách nào, nên giữ các nguyên tắc:

- Lớp khởi động ở package gốc để component scanning bao phủ các package con.
- Repository và document Elasticsearch thuộc phần hạ tầng lưu trữ/tìm kiếm.
- Service điều phối nghiệp vụ, không chứa chi tiết tạo kết nối hoặc đọc biến môi trường trực tiếp.
- Controller chỉ xử lý giao tiếp HTTP và chuyển yêu cầu vào application service.
- DTO dùng cho API không nên tự động trở thành document lưu trữ nếu hai mô hình có vòng đời hoặc cấu trúc khác nhau.
- Cấu hình dùng chung được đặt tại một vị trí dễ tìm; cấu hình theo môi trường được đặt trong resources hoặc cung cấp từ nền tảng triển khai.

## 3. Đặt lớp khởi động ở package gốc

Spring Boot dùng component scanning để tìm các thành phần như @Component, @Service, @Repository, @Controller và các lớp @Configuration. Theo mặc định, @SpringBootApplication kích hoạt component scanning từ package chứa lớp ứng dụng và các package con.

Ví dụ:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Đặt CatalogApplication trong com.example.catalog giúp Spring phát hiện các lớp trong com.example.catalog.product, com.example.catalog.category và com.example.catalog.shared.

Nếu đặt lớp khởi động trong package con như com.example.catalog.bootstrap nhưng các repository lại nằm ngoài nhánh package đó, Spring có thể không tự phát hiện chúng. Khi thật sự cần cấu trúc khác, có thể cấu hình scanBasePackages trên @SpringBootApplication hoặc khai báo riêng @EnableElasticsearchRepositories và @EntityScan theo yêu cầu của ứng dụng. Tuy nhiên, đặt lớp khởi động ở package gốc thường đơn giản và ít gây lỗi nhất.

## 4. Tổ chức phần tích hợp Spring Data Elasticsearch

Một chức năng tìm kiếm thường có document, repository và service. Ta dùng ví dụ Product để minh họa.

### 4.1. Document Elasticsearch

Document biểu diễn dữ liệu được lập chỉ mục trong Elasticsearch:

~~~java
package com.example.catalog.product.infrastructure.elasticsearch;

import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    // Constructors, getters và setters
}
~~~

@Document liên kết lớp với index. @Id đánh dấu document ID, còn @Field mô tả cách Elasticsearch lập chỉ mục từng trường. Tên index trong ví dụ là tên ổn định hoặc alias mà ứng dụng sử dụng. Việc tạo index và quản lý phiên bản mapping nên được xác định trong quy trình triển khai của dự án.

Trong ứng dụng đơn giản, domain model và document có thể là cùng một lớp. Với hệ thống phức tạp, nên tách Product trong domain khỏi ProductDocument trong infrastructure khi schema lưu trữ khác với mô hình nghiệp vụ. Khi đó, service hoặc adapter chịu trách nhiệm chuyển đổi giữa hai kiểu.

### 4.2. Repository

Repository đặt cạnh document trong package hạ tầng Elasticsearch:

~~~java
package com.example.catalog.product.infrastructure.elasticsearch;

import java.util.Optional;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySku(String sku);
}
~~~

Spring Data tạo implementation cho repository interface trong quá trình khởi động ứng dụng. Repository cung cấp các thao tác CRUD và query derivation theo tên phương thức. Với truy vấn phức tạp, có thể dùng @Query hoặc ElasticsearchOperations tùy nhu cầu.

Không nên đặt repository trong package controller hoặc domain. Repository là chi tiết truy cập dữ liệu; các lớp nghiệp vụ nên phụ thuộc vào abstraction cần thiết thay vì tự tạo ElasticsearchClient hoặc gọi HTTP trực tiếp.

### 4.3. Application service

Service điều phối yêu cầu tìm kiếm:

~~~java
package com.example.catalog.product.application;

import java.util.Optional;

import org.springframework.stereotype.Service;

import com.example.catalog.product.infrastructure.elasticsearch.ProductDocument;
import com.example.catalog.product.infrastructure.elasticsearch.ProductRepository;

@Service
public class ProductSearchService {

    private final ProductRepository productRepository;

    public ProductSearchService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public Optional<ProductDocument> findBySku(String sku) {
        return productRepository.findBySku(sku);
    }
}
~~~

Ví dụ trên giữ service đơn giản để tập trung vào vị trí package. Nếu áp dụng kiến trúc domain tách biệt, service nên trả về kiểu domain hoặc kết quả ứng dụng, rồi một adapter trong infrastructure chuyển đổi document sang domain. Điều đó giúp phần nghiệp vụ không phải phụ thuộc trực tiếp vào annotation của Spring Data.

Với các truy vấn tìm kiếm có điều kiện động, phân trang, aggregation hoặc truy vấn phức tạp, service có thể dùng ElasticsearchOperations. Hãy đặt thao tác cụ thể với Elasticsearch trong adapter hoặc lớp hạ tầng tương ứng để service không trở thành nơi tập trung mọi chi tiết kỹ thuật.

## 5. Phân biệt cấu hình chung và cấu hình theo môi trường

Ứng dụng thường chạy ở nhiều môi trường:

| Môi trường | Mục đích | Elasticsearch thường dùng |
| --- | --- | --- |
| local | Phát triển trên máy cá nhân | Container hoặc node local |
| dev | Tích hợp thay đổi đang phát triển | Cluster dùng chung cho nhóm |
| staging | Kiểm thử gần với production | Cluster có cấu hình và bảo mật tương tự production |
| production | Phục vụ người dùng thật | Cluster được quản lý, có xác thực, TLS và giám sát |
| test | Chạy kiểm thử tự động | Elasticsearch dùng riêng cho test hoặc Testcontainers |

Các giá trị như timeout, tên ứng dụng hoặc hành vi chung có thể được đặt trong cấu hình mặc định. Endpoint, thông tin xác thực, TLS và một số giới hạn tài nguyên có thể thay đổi theo môi trường.

Nguyên tắc quan trọng là cùng một bản build nên có thể triển khai ở nhiều môi trường bằng cách truyền cấu hình lúc chạy. Không cần tạo một bản JAR riêng chỉ vì URL Elasticsearch khác nhau.

## 6. Cấu hình bằng application.yml và Spring Profiles

Spring Boot hỗ trợ externalized configuration. Có thể đặt cấu hình mặc định trong application.yml và phần ghi đè trong các tệp application-{profile}.yml.

### 6.1. Cấu hình dùng chung

Tệp src/main/resources/application.yml:

~~~yaml
spring:
  application:
    name: catalog-service
  elasticsearch:
    connection-timeout: 2s
    socket-timeout: 5s

app:
  search:
    products-index: catalog-products
~~~

Phần này chứa các giá trị có thể dùng chung. Timeout là ví dụ minh họa; giá trị thực tế cần dựa trên độ trễ mạng, thời gian xử lý truy vấn và yêu cầu của hệ thống. products-index là cấu hình nghiệp vụ riêng của ứng dụng, được đặt dưới prefix app.search.

### 6.2. Cấu hình local

Tệp src/main/resources/application-local.yml:

~~~yaml
spring:
  elasticsearch:
    uris: http://localhost:9200

app:
  search:
    products-index: catalog-products-local
~~~

Khi chạy local, ứng dụng kết nối node Elasticsearch trên máy phát triển. Nếu node local bật xác thực, có thể cung cấp username và password qua biến môi trường tương ứng. Không nên ghi mật khẩu cá nhân vào tệp cấu hình được commit.

### 6.3. Cấu hình development

Tệp src/main/resources/application-dev.yml:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}

app:
  search:
    products-index: catalog-products-dev
~~~

Endpoint và credentials được cung cấp khi chạy ứng dụng. Trong CI hoặc môi trường triển khai, các biến này nên được truyền qua secret store hoặc cơ chế quản lý secret của nền tảng.

### 6.4. Cấu hình production

Tệp src/main/resources/application-prod.yml:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
    connection-timeout: 2s
    socket-timeout: 10s

app:
  search:
    products-index: catalog-products
~~~

Trong production, endpoint phải trỏ tới cluster được cấp cho ứng dụng. Bật TLS và xác minh chứng chỉ theo cấu hình bảo mật của cluster. Cách cung cấp trust material hoặc SSL bundle phụ thuộc phiên bản Spring Boot và cách tổ chức chứng chỉ của nền tảng; cần dùng đúng cơ chế được hỗ trợ bởi phiên bản dự án.

Không đưa password, API key, private key hoặc nội dung chứng chỉ bí mật vào Git. Tệp application-prod.yml chỉ nên chứa tên biến hoặc tham chiếu tới secret do nền tảng cung cấp.

### 6.5. Kích hoạt profile

Có thể kích hoạt profile bằng biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=local
~~~

Hoặc khi chạy JAR:

~~~bash
java -jar catalog-service.jar --spring.profiles.active=dev
~~~

Trong môi trường container, thường truyền SPRING_PROFILES_ACTIVE cùng các biến ELASTICSEARCH_* từ cấu hình triển khai. Không nên cố định spring.profiles.active=prod trong application.yml vì điều đó khiến việc chạy cùng artifact ở local hoặc test trở nên khó kiểm soát.

Spring Boot kết hợp cấu hình mặc định, profile và các nguồn cấu hình bên ngoài theo thứ tự ưu tiên của nó. Biến môi trường, tham số dòng lệnh và cấu hình nền tảng có thể ghi đè giá trị trong tệp. Khi một giá trị không như mong đợi, cần kiểm tra profile đang hoạt động và nguồn cấu hình có độ ưu tiên cao hơn.

## 7. Đưa cấu hình ứng dụng vào @ConfigurationProperties

Không nên đọc biến môi trường trực tiếp trong mọi service. Với các thiết lập do ứng dụng tự định nghĩa, dùng @ConfigurationProperties để gom chúng thành một kiểu có cấu trúc.

Ví dụ:

~~~java
package com.example.catalog.shared.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.search")
public class SearchProperties {

    private String productsIndex = "catalog-products";

    public String getProductsIndex() {
        return productsIndex;
    }

    public void setProductsIndex(String productsIndex) {
        this.productsIndex = productsIndex;
    }
}
~~~

Đăng ký properties:

~~~java
package com.example.catalog.shared.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(SearchProperties.class)
public class SearchConfiguration {
}
~~~

Sau đó inject SearchProperties vào thành phần cần sử dụng:

~~~java
public class ProductIndexNameProvider {

    private final SearchProperties properties;

    public ProductIndexNameProvider(SearchProperties properties) {
        this.properties = properties;
    }

    public String getIndexName() {
        return properties.getProductsIndex();
    }
}
~~~

Ví dụ dùng một provider nhỏ để minh họa việc đọc cấu hình. Trong ứng dụng thực tế, có thể inject SearchProperties trực tiếp vào adapter quản lý index hoặc lớp cần giá trị này. Nếu dùng record hoặc constructor binding, hãy áp dụng theo phiên bản Spring Boot và quy ước Java của dự án.

@ConfigurationProperties có các lợi ích:

- Gom các giá trị liên quan vào một kiểu có tên rõ ràng.
- Hỗ trợ binding từ YAML, properties, biến môi trường và các nguồn cấu hình khác.
- Có thể kết hợp validation để phát hiện cấu hình thiếu hoặc sai ngay khi khởi động.
- Giảm việc rải chuỗi tên property trong mã nguồn.
- Giúp unit test cấu hình và thành phần sử dụng cấu hình dễ dàng hơn.

Với cấu hình kết nối Elasticsearch do Spring Boot quản lý, ưu tiên các thuộc tính spring.elasticsearch.* được starter hỗ trợ. Chỉ tạo cấu hình client thủ công khi có yêu cầu cụ thể mà auto-configuration không đáp ứng, chẳng hạn cách thiết lập TLS đặc biệt hoặc nhiều cluster độc lập.

## 8. Cấu hình client và repository: khi nào cần Java configuration?

Nếu ứng dụng dùng spring-boot-starter-data-elasticsearch và các thuộc tính chuẩn của Spring Boot, auto-configuration thường đã tạo client cùng các bean cần thiết cho Spring Data. Trong trường hợp đó, không cần viết một ElasticsearchConfiguration chỉ để khai báo lại các bean mặc định.

Có thể inject abstraction của Spring Data vào service hoặc adapter:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Component;

@Component
public class ProductSearchAdapter {

    private final ElasticsearchOperations operations;

    public ProductSearchAdapter(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

ElasticsearchOperations cung cấp API cấp cao để lưu, đọc và tìm kiếm document. Dùng abstraction này giúp mã ứng dụng ít phụ thuộc hơn vào chi tiết của HTTP client.

### 8.1. Khi nào cần @EnableElasticsearchRepositories?

Spring Boot thường tự tìm repository trong vùng component scan. Có thể dùng @EnableElasticsearchRepositories khi cần chỉ định rõ package repository, chẳng hạn repository nằm ngoài package gốc:

~~~java
package com.example.catalog.shared.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.product.infrastructure.elasticsearch"
)
public class ElasticsearchRepositoryConfiguration {
}
~~~

Chỉ thêm cấu hình này khi cần điều chỉnh phạm vi scan hoặc thiết lập repository. Tránh khai báo nhiều cấu hình cùng scan một package nếu không có lý do rõ ràng.

### 8.2. Khi nào cần tự tạo client?

Một số hệ thống phải kết nối nhiều cluster, dùng cơ chế xác thực đặc biệt hoặc cấu hình TLS riêng. Khi đó có thể cần tạo client bean và cấu hình ElasticsearchOperations tương ứng. Đây là phần hạ tầng cần được cô lập trong package config hoặc infrastructure, đồng thời phải kiểm soát vòng đời, timeout và đóng tài nguyên đúng cách.

Không nên tạo một client mới trong mỗi service hoặc mỗi lần gọi repository. Client thường được quản lý như bean dùng chung trong application context. Cũng không nên trộn API client cấp thấp với repository ở mọi nơi; hãy đặt các truy vấn cấp thấp trong adapter chuyên trách.

Tên lớp, builder và API cấu hình client thay đổi theo các thế hệ Elasticsearch Java client và Spring Data Elasticsearch. Khi cần cấu hình thủ công, hãy dùng API tương thích với dependency đang được quản lý bởi Spring Boot BOM của dự án; tránh sao chép ví dụ cũ dùng RestHighLevelClient vào ứng dụng mới.

## 9. Tổ chức mapping và index resources

Mapping có thể được khai báo bằng annotation trên document hoặc bằng tệp JSON riêng. Nếu mapping phức tạp, dynamic templates nhiều hoặc cần review schema độc lập với Java entity, tệp JSON có thể dễ quản lý hơn.

Một cách bố trí tài nguyên:

~~~text
src/main/resources
├── application.yml
├── application-local.yml
├── application-dev.yml
├── application-prod.yml
└── elasticsearch
    └── mappings
        └── product-mapping.json
~~~

Document có thể tham chiếu tệp mapping bằng @Mapping nếu phiên bản Spring Data Elasticsearch của dự án hỗ trợ cách khai báo đó:

~~~java
@Document(indexName = "catalog-products")
@Mapping(mappingPath = "/elasticsearch/mappings/product-mapping.json")
public class ProductDocument {
    // Các trường document
}
~~~

Không nên khai báo cùng một schema theo hai cách mà không xác định nguồn sự thật. Nếu annotation và mapping JSON cùng mô tả một trường nhưng khác kiểu hoặc analyzer, người bảo trì sẽ khó biết cấu hình nào có hiệu lực. Chọn một cách quản lý chính, ghi rõ quy ước và kiểm tra mapping thực tế sau khi tạo index.

Với hệ thống có yêu cầu kiểm soát vòng đời index, có thể đặt mapping và settings trong thư mục resources phục vụ migration hoặc triển khai riêng. Ứng dụng runtime khi đó có thể chỉ đọc/ghi vào alias đã được provision. Cách này giúp quyền tạo index không nhất thiết phải cấp cho mọi instance ứng dụng.

## 10. Cấu hình và kiểm thử theo môi trường

Không nên dùng chung một cluster Elasticsearch cho tất cả các loại kiểm thử. Local, integration test và production có mục tiêu, dữ liệu và quyền truy cập khác nhau.

### 10.1. Local development

Một lựa chọn phổ biến là chạy Elasticsearch bằng Docker hoặc Docker Compose. Ứng dụng dùng profile local và kết nối tới endpoint trên máy phát triển. Dữ liệu local nên có thể xóa và tạo lại mà không ảnh hưởng dữ liệu dùng chung.

Ví dụ cấu hình profile local ở trên giả định Elasticsearch lắng nghe tại localhost:9200. Nếu dùng Docker Compose, hostname có thể là tên service khi ứng dụng cũng chạy trong cùng network Docker; localhost bên trong container ứng dụng trỏ tới chính container ứng dụng, không phải container Elasticsearch.

### 10.2. Unit test

Unit test cho service nên mock repository hoặc adapter để kiểm tra logic nghiệp vụ mà không cần khởi động Elasticsearch:

~~~java
@ExtendWith(MockitoExtension.class)
class ProductSearchServiceTest {

    @Mock
    private ProductRepository productRepository;

    @InjectMocks
    private ProductSearchService productSearchService;

    @Test
    void returnsProductBySku() {
        // Arrange, Act và Assert
    }
}
~~~

Đoạn mã chỉ minh họa vị trí và cách cô lập dependency. Các assertion cụ thể phụ thuộc vào hành vi service mà ứng dụng yêu cầu.

### 10.3. Integration test

Integration test cần kiểm tra tương tác thật giữa Spring Data Elasticsearch và một node Elasticsearch tương thích. Có thể dùng Testcontainers để khởi chạy container trong vòng đời test, rồi cung cấp endpoint động qua @DynamicPropertySource.

Ví dụ khung cấu hình:

~~~java
@Testcontainers
@SpringBootTest
class ProductRepositoryIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer("docker.elastic.co/elasticsearch/elasticsearch:<version>");

    @DynamicPropertySource
    static void elasticsearchProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.elasticsearch.uris", elasticsearch::getHttpHostAddress);
    }
}
~~~

Thay <version> bằng phiên bản Elasticsearch được hỗ trợ bởi phiên bản Spring Data Elasticsearch đang dùng. Một số phiên bản Elasticsearch bật bảo mật mặc định và cần cấu hình mật khẩu hoặc chứng chỉ trong test; hãy dùng cách cấu hình phù hợp với image và phiên bản được chọn. Không dùng tag latest cho test ổn định vì image có thể thay đổi mà không có thay đổi mã nguồn.

Integration test nên kiểm tra ít nhất:

- Ứng dụng khởi tạo được repository và kết nối tới node.
- Mapping được tạo đúng hoặc index đã được chuẩn bị đúng.
- Có thể lưu và truy vấn document.
- Query, sort và pagination hoạt động theo mong đợi.
- Các trường hợp dữ liệu sai hoặc trường chưa khai báo được xử lý đúng.

### 10.4. Staging và production

Staging nên gần production về phiên bản Elasticsearch, xác thực, TLS, mapping và cách cấp cấu hình. Production cần dùng endpoint và secret do nền tảng quản lý. Các thông số như số kết nối, timeout và retry nên được điều chỉnh dựa trên giám sát thực tế.

Không nên dùng dữ liệu production nhạy cảm để kiểm thử ở local hoặc dev nếu chưa có quy trình bảo vệ và làm mờ dữ liệu phù hợp. Mỗi môi trường nên có quyền truy cập và dữ liệu riêng.

## 11. Những lỗi tổ chức thường gặp

**Đặt lớp khởi động trong package quá sâu.** Spring không quét được repository hoặc service nằm ngoài nhánh package mặc định. Đặt lớp application ở package gốc hoặc cấu hình phạm vi scan có chủ đích.

**Để controller gọi ElasticsearchRepository trực tiếp.** Controller khi đó vừa xử lý HTTP vừa chứa logic truy cập dữ liệu. Hãy chuyển điều phối vào application service hoặc use case.

**Đặt mọi lớp vào package config.** Package config chỉ nên chứa cấu hình Spring và bean hạ tầng. Document, repository và logic nghiệp vụ cần có package riêng.

**Đưa URL và mật khẩu vào mã Java.** Điều này khiến thay đổi môi trường cần sửa và build lại ứng dụng, đồng thời có nguy cơ lộ secret. Hãy dùng externalized configuration và secret store.

**Commit mật khẩu vào application-prod.yml.** File cấu hình có thể được commit nếu chỉ chứa tham chiếu hoặc tên biến. Secret thật phải được cấp từ hệ thống quản lý bí mật.

**Tạo client mới trong từng service.** Việc này gây trùng cấu hình, lãng phí kết nối và khó quản lý vòng đời. Dùng bean được Spring quản lý hoặc adapter dùng chung.

**Dùng profile để thay đổi logic nghiệp vụ không cần thiết.** Profile phù hợp cho cấu hình hoặc bean chỉ tồn tại ở môi trường nhất định. Các khác biệt endpoint, credentials và timeout thường nên được biểu diễn bằng properties.

**Không kiểm tra cấu hình khi khởi động.** Một endpoint sai hoặc biến môi trường bị thiếu có thể chỉ lộ ra khi request đầu tiên chạy. Hãy xác thực các thuộc tính bắt buộc và kiểm tra kết nối theo chính sách readiness của ứng dụng.

**Dùng phiên bản client không tương thích.** Tự thêm dependency client khác phiên bản với Spring Data Elasticsearch có thể gây lỗi runtime hoặc lỗi cấu hình. Ưu tiên dependency do Spring Boot quản lý và kiểm tra ma trận tương thích.

## 12. Một cấu trúc tham khảo hoàn chỉnh

Với một ứng dụng catalog có API tìm kiếm sản phẩm và danh mục, cấu trúc có thể như sau:

~~~text
catalog-service
├── build.gradle
└── src
    ├── main
    │   ├── java
    │   │   └── com/example/catalog
    │   │       ├── CatalogApplication.java
    │   │       ├── product
    │   │       │   ├── api
    │   │       │   │   ├── ProductController.java
    │   │       │   │   ├── ProductSearchRequest.java
    │   │       │   │   └── ProductSearchResponse.java
    │   │       │   ├── application
    │   │       │   │   └── ProductSearchService.java
    │   │       │   ├── domain
    │   │       │   │   └── Product.java
    │   │       │   └── infrastructure
    │   │       │       └── elasticsearch
    │   │       │           ├── ProductDocument.java
    │   │       │           ├── ProductRepository.java
    │   │       │           └── ProductSearchAdapter.java
    │   │       ├── category
    │   │       │   ├── api
    │   │       │   ├── application
    │   │       │   ├── domain
    │   │       │   └── infrastructure
    │   │       └── shared
    │   │           └── config
    │   │               ├── SearchConfiguration.java
    │   │               └── SearchProperties.java
    │   └── resources
    │       ├── application.yml
    │       ├── application-local.yml
    │       ├── application-dev.yml
    │       ├── application-prod.yml
    │       └── elasticsearch
    │           └── mappings
    │               └── product-mapping.json
    └── test
        ├── java
        │   └── com/example/catalog
        │       ├── product
        │       │   ├── application
        │       │   │   └── ProductSearchServiceTest.java
        │       │   └── infrastructure
        │       │       └── elasticsearch
        │       │           └── ProductRepositoryIntegrationTest.java
        │       └── support
        └── resources
            └── application-test.yml
~~~

Đây là cấu trúc tham khảo, không phải danh sách package bắt buộc. Không cần tạo thư mục rỗng chỉ để khớp sơ đồ. Khi chức năng còn nhỏ, có thể gộp bớt tầng; khi có thêm chức năng, mở rộng theo cùng quy ước.

## 13. Quy trình đưa cấu hình vào ứng dụng

Khi bắt đầu dự án hoặc chuẩn hóa một ứng dụng đang chạy, có thể thực hiện theo trình tự:

1. Xác định các chức năng nghiệp vụ và chọn cách tổ chức package theo tầng hoặc theo chức năng.
2. Đặt lớp @SpringBootApplication ở package gốc để component scanning hoạt động đúng.
3. Xác định document, repository và adapter Elasticsearch nằm trong package infrastructure phù hợp.
4. Giữ controller, application service và domain model tách biệt theo trách nhiệm.
5. Đưa cấu hình dùng chung vào application.yml; tạo profile local, dev, staging hoặc prod khi có giá trị thực sự khác nhau.
6. Đưa endpoint và thông tin xác thực ra ngoài mã nguồn; cấp secret qua môi trường triển khai.
7. Dùng @ConfigurationProperties cho cấu hình riêng của ứng dụng và xác thực giá trị bắt buộc.
8. Chỉ viết Java configuration cho các bean hoặc repository scan mà auto-configuration chưa đáp ứng.
9. Chuẩn bị cấu hình mapping và index theo một nguồn sự thật được quản lý rõ ràng.
10. Viết unit test cho logic và integration test với Elasticsearch tương thích.
11. Chạy cùng một artifact ở các môi trường bằng cách cung cấp profile và cấu hình khác nhau.
12. Kiểm tra log khởi động, endpoint thực tế, trạng thái kết nối và hành vi truy vấn sau triển khai.

Một cấu trúc package tốt làm rõ nơi đặt mã và hướng phụ thuộc của ứng dụng. Cấu hình theo môi trường làm rõ những giá trị nào thay đổi khi triển khai. Khi hai phần này được tổ chức nhất quán, Spring Data Elasticsearch có thể được tích hợp như một thành phần hạ tầng rõ ràng, dễ kiểm thử và dễ vận hành.

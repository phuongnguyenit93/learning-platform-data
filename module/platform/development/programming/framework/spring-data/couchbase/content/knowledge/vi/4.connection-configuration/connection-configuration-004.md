# Cấu hình Java qua `AbstractCouchbaseConfiguration`

## 1. Mục tiêu và bối cảnh

Với **Spring Data Couchbase**, Spring Boot có thể tự cấu hình kết nối thông qua starter và các thuộc tính trong `application.yml`. Tuy nhiên, ở một số dự án bạn cần chủ động quyết định cách khởi tạo hạ tầng truy cập dữ liệu bằng Java: nguồn cấu hình được bind theo kiểu, phạm vi quét entity/repository, bucket mặc định hoặc một số tùy chỉnh ở tầng SDK.

Lớp `org.springframework.data.couchbase.config.AbstractCouchbaseConfiguration` là điểm mở rộng do **Spring Data Couchbase** cung cấp cho những tình huống này. Bằng cách kế thừa và triển khai các phương thức bắt buộc, ứng dụng cung cấp thông tin kết nối cho Spring Data, còn lớp cơ sở xây dựng những bean hạ tầng cần thiết.

Bài học thuộc chương **Cấu hình kết nối** trong module `SPRING_DATA_COUCHBASE`. Sau khi học, bạn có thể:

- Giải thích khi nào nên dùng Java configuration thay cho cấu hình tự động thông thường của Spring Boot.
- Tạo lớp kế thừa `AbstractCouchbaseConfiguration` và triển khai chính xác bốn phương thức cấu hình cốt lõi.
- Bind connection string, username, password và bucket từ cấu hình ngoài ứng dụng mà không hardcode bí mật.
- Kết nối entity mapping, `CouchbaseRepository` và `CouchbaseTemplate` với bucket/scope/collection đã chọn.
- Tránh cấu hình trùng lặp bean, sai phạm vi quét và xung đột giữa Java config với Boot auto-configuration.
- Kiểm chứng đường đọc KV và phân biệt lỗi cấu hình với lỗi truy vấn SQL++.

Các ví dụ sử dụng cách tổ chức thông dụng của **Spring Boot 3.x** và Spring Data Couchbase tương ứng do Spring Boot quản lý. API tùy chỉnh nâng cao có thể khác giữa các phiên bản Spring Data/SDK; cần đối chiếu tài liệu đúng phiên bản nếu mở rộng ngoài các phương thức căn bản.

## 2. `AbstractCouchbaseConfiguration` đảm nhiệm điều gì?

Sơ đồ trách nhiệm:

~~~mermaid
flowchart TD
    A["application.yml / biến môi trường / secret"] --> B["@ConfigurationProperties"]
    B --> C["CouchbaseJavaConfig<br/>extends AbstractCouchbaseConfiguration"]
    C --> D["Couchbase SDK: Cluster / kết nối"]
    C --> E["Spring Data: client factory,<br/>mapping, converter, template"]
    D --> E
    F["@EnableCouchbaseRepositories"] --> G["ProductRepository"]
    E --> G
    H["@Document / @Scope / @Collection"] --> E
    G --> I["Key-Value hoặc SQL++"]
    I --> J["Bucket → Scope → Collection"]
~~~

Bạn khai báo **thông tin đầu vào** thông qua các phương thức của lớp kế thừa. Spring Data dùng thông tin đó để thiết lập hạ tầng, bao gồm những thành phần cần cho mapping, template và repository.

| Thành phần | Trách nhiệm |
| --- | --- |
| `AbstractCouchbaseConfiguration` | Cung cấp điểm cấu hình trung tâm và các bean nền tảng của Spring Data |
| `getConnectionString()` | Trả về địa chỉ bootstrap tới Couchbase Cluster |
| `getUserName()` | Trả về tên user xác thực với cluster |
| `getPassword()` | Trả về password của user đó |
| `getBucketName()` | Trả về bucket mặc định cho Spring Data |
| `@EnableCouchbaseRepositories` | Cho phép quét và đăng ký các repository đồng bộ tại package được chọn |
| `@Document`, `@Scope`, `@Collection` | Chỉ dẫn ánh xạ entity vào document tại scope/collection đích |

**Phân biệt hai phía:** lớp cấu hình chỉ tạo **hạ tầng client trong ứng dụng**; nó không provision cluster, bucket, scope, collection, user hoặc index phía Couchbase Server. Các tài nguyên đó cần tồn tại trước khi ứng dụng sử dụng.

Trong một dự án chỉ có một cluster, một bucket và không cần can thiệp cơ chế khởi tạo, cấu hình chuẩn bằng `spring.couchbase.*` và `spring.data.couchbase.bucket-name` thường đủ. Java config hữu ích khi cần kiểm soát rõ ràng bean, package hoặc tích hợp với cơ chế settings của ứng dụng.

## 3. Bắt đầu từ dự án và tài nguyên Couchbase

Giả sử xây dựng dịch vụ quản lý sản phẩm với:

| Tài nguyên | Giá trị minh họa |
| --- | --- |
| Cluster local | `couchbase://127.0.0.1` |
| User ứng dụng | `inventory_app` |
| Bucket | `inventory` |
| Scope | `catalog` |
| Collection | `products` |

Bucket `inventory`, scope `catalog`, collection `products` phải được tạo trên cluster. User `inventory_app` cần quyền đọc/ghi dữ liệu đúng collection; nếu sau này chạy repository query theo thuộc tính, còn cần dịch vụ Query, quyền và chỉ mục SQL++ phù hợp.

Thêm starter Spring Data Couchbase, ví dụ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-couchbase")
}
~~~

Hoặc Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-couchbase</artifactId>
</dependency>
~~~

Nên để Spring Boot quản lý phiên bản Spring Data Couchbase và Couchbase Java SDK qua dependency management của dự án. Ví dụ Java phía dưới giả định các lớp ứng dụng đặt trong những package sau:

~~~text
com.example.inventory
├── InventoryApplication.java
├── config
│   ├── CouchbaseSettings.java
│   └── CouchbaseJavaConfig.java
├── domain
│   └── ProductDocument.java
└── repository
    └── ProductRepository.java
~~~

Cấu trúc package trên là ví dụ về cách tổ chức, không phải yêu cầu bắt buộc.

## 4. Đưa cấu hình ra khỏi mã nguồn

### 4.1. Tạo một namespace property riêng cho Java config

Để tránh nhầm giữa cấu hình do Spring Boot tự đọc và các giá trị do lớp Java config tự dùng, ví dụ này định nghĩa namespace **`app.couchbase`**:

~~~yaml
# src/main/resources/application.yml
app:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING:couchbase://127.0.0.1}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
    bucket-name: "${COUCHBASE_BUCKET:inventory}"
~~~

Đây là **thuộc tính tự định nghĩa của ứng dụng**. Spring Boot không tự hiểu `app.couchbase.*` là cấu hình Couchbase SDK; chính class settings và lớp kế thừa `AbstractCouchbaseConfiguration` sẽ đọc và sử dụng chúng.

Cách làm giúp minh họa rõ luồng dữ liệu:

~~~text
Biến môi trường → app.couchbase.* → CouchbaseSettings
             → các phương thức get...() của Java config
             → hạ tầng Spring Data Couchbase
~~~

Không để password thật trong Git. Với local, cung cấp `COUCHBASE_USERNAME` và `COUCHBASE_PASSWORD` qua môi trường chạy; với production, dùng secret manager hoặc cơ chế inject secret của nền tảng.

### 4.2. Bind sang đối tượng Java có kiểu

File `CouchbaseSettings.java`:

~~~java
package com.example.inventory.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.couchbase")
public record CouchbaseSettings(
        String connectionString,
        String username,
        String password,
        String bucketName
) {
}
~~~

Một Java `record` là cách gọn để gom các giá trị cấu hình bất biến. Các phần tử `connectionString` và `bucketName` được ánh xạ từ tên property dạng kebab-case `connection-string` và `bucket-name` nhờ relaxed binding của Spring Boot.

Lưu ý: `@ConfigurationProperties` trên record chỉ mô tả cách bind; bean settings cần được đăng ký bằng `@EnableConfigurationProperties` hoặc cơ chế scan tương ứng. Phần tiếp theo dùng `@EnableConfigurationProperties`.

Bạn có thể thêm validation ở bước hoàn thiện dự án, nhưng cần dependency validation phù hợp và cơ chế kiểm tra dữ liệu cấu hình ngay khi khởi động. Không thay thế việc kiểm tra quyền hoặc kết nối thực tế bằng validation chuỗi.

## 5. Tạo lớp kế thừa `AbstractCouchbaseConfiguration`

File `CouchbaseJavaConfig.java`:

~~~java
package com.example.inventory.config;

import com.example.inventory.repository.ProductRepository;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.couchbase.config.AbstractCouchbaseConfiguration;
import org.springframework.data.couchbase.repository.config.EnableCouchbaseRepositories;

@Configuration
@EnableConfigurationProperties(CouchbaseSettings.class)
@EnableCouchbaseRepositories(
        basePackageClasses = ProductRepository.class
)
public class CouchbaseJavaConfig extends AbstractCouchbaseConfiguration {

    private final CouchbaseSettings settings;

    public CouchbaseJavaConfig(CouchbaseSettings settings) {
        this.settings = settings;
    }

    @Override
    public String getConnectionString() {
        return settings.connectionString();
    }

    @Override
    public String getUserName() {
        return settings.username();
    }

    @Override
    public String getPassword() {
        return settings.password();
    }

    @Override
    public String getBucketName() {
        return settings.bucketName();
    }

    @Override
    protected String getMappingBasePackage() {
        return "com.example.inventory.domain";
    }
}
~~~

Bốn phương thức `getConnectionString()`, `getUserName()`, `getPassword()` và `getBucketName()` là **trọng tâm** của ví dụ. Tên `getUserName()` có chữ **N viết hoa**; không nhầm với `getUsername()` khi override.

Trong ví dụ:

1. `@Configuration` đăng ký lớp Java config với Spring và giữ cơ chế xử lý các phương thức `@Bean` mà lớp cơ sở cung cấp.
2. `@EnableConfigurationProperties(CouchbaseSettings.class)` đăng ký bean để Spring Boot bind `app.couchbase.*`.
3. `@EnableCouchbaseRepositories(basePackageClasses = ProductRepository.class)` đặt ranh giới quét repository theo package của một interface cụ thể, hạn chế lỗi thay đổi tên package trong tương lai.
4. Constructor nhận `CouchbaseSettings` thay vì gọi `System.getenv()` hoặc hardcode secret ở từng getter.
5. `getMappingBasePackage()` đặt nơi tìm entity cho mapping context khi domain nằm ngoài phạm vi mặc định của lớp cấu hình.

Với cấu trúc project khác, hãy đổi `basePackageClasses` và `getMappingBasePackage()` cho khớp đường package thực tế. Nếu file config nằm cùng package gốc bao trùm domain, bạn có thể không cần override phạm vi mapping.

**Một điểm quan trọng:** khi đã chọn chiến lược cấu hình bằng `AbstractCouchbaseConfiguration`, các getter nói trên quyết định giá trị mà lớp cấu hình cung cấp. Đừng giả định thay đổi `spring.data.couchbase.bucket-name` sẽ tự thay đổi kết quả `getBucketName()` nếu getter đang lấy `app.couchbase.bucket-name`. Hãy chọn một nguồn sự thật rõ ràng.

## 6. Liên kết document, bucket và repository

Với `getBucketName() = "inventory"`, Spring Data có bucket mặc định là `inventory`. Entity có thể chỉ rõ scope/collection đích:

~~~java
package com.example.inventory.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("catalog")
@Collection("products")
public class ProductDocument {

    @Id
    private String id;

    private String name;

    @Version
    private Long version;

    protected ProductDocument() {
    }

    public ProductDocument(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Long getVersion() {
        return version;
    }
}
~~~

File `ProductRepository.java`:

~~~java
package com.example.inventory.repository;

import com.example.inventory.domain.ProductDocument;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository
        extends CouchbaseRepository<ProductDocument, String> {
}
~~~

Khi chạy:

~~~java
ProductDocument item =
        new ProductDocument("product::SKU-001", "Mechanical keyboard");

repository.save(item);
repository.findById("product::SKU-001");
~~~

Các tầng phối hợp như sau:

| Thành phần | Giá trị kết quả | Nguồn |
| --- | --- | --- |
| Cluster | `couchbase://127.0.0.1` | `getConnectionString()` |
| User | `inventory_app` | `getUserName()` và `getPassword()` |
| Bucket | `inventory` | `getBucketName()` |
| Scope | `catalog` | `@Scope` |
| Collection | `products` | `@Collection` |
| Document key | `product::SKU-001` | `@Id` |

`@Version` phục vụ optimistic locking dựa trên CAS khi cập nhật; nó không thay đổi địa chỉ cluster hoặc bucket. TTL và giao dịch cũng có cơ chế riêng, không được “bật” chỉ bằng cách kế thừa `AbstractCouchbaseConfiguration`.

Nếu không chỉ định scope/collection, Spring Data có thể sử dụng các vùng mặc định. Đừng nhầm `bucket-name` với đường dẫn chứa cả scope/collection; phải xác định rõ mapping khi thiết kế dữ liệu nhiều collection.

## 7. Sử dụng `CouchbaseTemplate` mà không tạo bean thủ công

Một lợi ích của lớp cơ sở là cung cấp hạ tầng cần thiết để Spring Data tạo và dùng `CouchbaseTemplate` trong cấu hình phù hợp. Ví dụ service:

~~~java
package com.example.inventory.service;

import com.example.inventory.domain.ProductDocument;
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductDocumentService {

    private final CouchbaseTemplate template;

    public ProductDocumentService(CouchbaseTemplate template) {
        this.template = template;
    }

    public ProductDocument load(String id) {
        return template.findById(ProductDocument.class).one(id);
    }
}
~~~

Các phương thức template tiếp tục sử dụng hạ tầng mapping, bucket và scope/collection đã cấu hình. Cách tiếp cận này hữu ích khi muốn dùng các thao tác linh hoạt hơn repository. Tuy nhiên, việc chọn `CouchbaseTemplate` không tự tạo index cho SQL++; query theo thuộc tính vẫn phải kiểm tra dịch vụ Query, quyền và index.

Nếu tự khai báo thêm một bean `CouchbaseTemplate` trùng mục đích, bạn có thể gây nhập nhằng bean hoặc thay đổi đường truy cập dữ liệu đang dùng. Chỉ tùy biến khi có yêu cầu cụ thể và hiểu mối quan hệ giữa template, client factory, converter và bucket.

## 8. Java config và auto-configuration của Spring Boot có thể tương tác thế nào?

Đây là hai cách thiết lập thường gặp:

| Tiêu chí | Boot properties mặc định | Kế thừa `AbstractCouchbaseConfiguration` |
| --- | --- | --- |
| Điểm khởi đầu | Thêm starter rồi khai báo `spring.couchbase.*` / `spring.data.couchbase.*` | Viết lớp `@Configuration` và override getter |
| Quyết định kết nối | Boot bind properties và tạo bean nếu điều kiện phù hợp | Java config cung cấp trực tiếp giá trị cho lớp cơ sở |
| Repository scan | Boot thường tự kích hoạt khi package hợp lệ | Có thể chủ động chỉ định `@EnableCouchbaseRepositories` |
| Phù hợp với | Ứng dụng tiêu chuẩn một cluster/bucket | Cần cấu hình Java rõ ràng, scan tùy chọn hoặc điểm mở rộng |
| Rủi ro | Sai tên property hoặc nguồn override | Trùng bean, cấu hình lấy từ hai nguồn khác nhau, scan không đúng |

Trong Spring Boot, các auto-configuration thường có điều kiện dựa trên classpath và bean đã tồn tại. Khi một lớp kế thừa `AbstractCouchbaseConfiguration` tự đăng ký các bean hạ tầng, một số phần auto-configuration của Boot có thể **lùi bước** hoặc hoạt động khác so với dự án chỉ khai báo properties.

Không nên đồng thời tạo hai lớp cấu hình đầy đủ cùng kế thừa `AbstractCouchbaseConfiguration` cho một ứng dụng chỉ có một kết nối. Nếu vừa có Java config tùy chỉnh vừa có property Boot, cần xác định rõ nhóm nào thực sự là nguồn dữ liệu đầu vào và có bean nào được tạo ra; tránh phụ thuộc vào thứ tự khởi tạo bean để “tình cờ” chọn đúng cluster.

### Khi nào nên tiếp tục dùng property tiêu chuẩn?

Nếu mục tiêu chỉ là trỏ tới cluster, chọn bucket và truy cập repository, cách ngắn hơn thường là:

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${COUCHBASE_BUCKET}"
~~~

Trong trường hợp đó, có thể không cần viết lớp `CouchbaseJavaConfig`. Nếu chuyển sang Java config, hãy chuyển có chủ đích và xác nhận những bean/property nào đang thực sự được dùng.

## 9. Tùy chỉnh SDK, timeout và TLS

`AbstractCouchbaseConfiguration` nằm trên tầng hạ tầng Spring Data, nhưng vẫn dựa vào **Couchbase Java SDK** để kết nối cluster. Những nhu cầu thường xuất hiện khi tùy chỉnh sâu là:

- Connection string có nhiều seed node, hoặc kết nối TLS bằng `couchbases://`.
- Nạp trust material khi dùng CA nội bộ và xác minh hostname của máy chủ.
- Điều chỉnh timeout kết nối, KV hoặc Query theo dữ liệu đo đạc.
- Quan sát hoạt động bootstrap, topology và dịch vụ Data/Query/Index.
- Tùy chỉnh codec, converter hoặc các bean mapping trong các tình huống đặc biệt.

Cấu hình cơ bản có thể dùng connection string TLS:

~~~yaml
app:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING:couchbases://cb.example.internal}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
    bucket-name: inventory
~~~

Prefix `couchbases://` không tự khắc phục lỗi chứng chỉ. Khi có lỗi TLS cần kiểm tra DNS, hostname, chuỗi CA đáng tin cậy, network policy và hướng dẫn của môi trường Couchbase Server/Capella. Không tắt xác thực chứng chỉ trong production.

Các API/hook để tùy biến `ClusterEnvironment` phụ thuộc vào phiên bản SDK và Spring Data. Khi cần thêm timeout hoặc trust customization bằng Java, dùng điểm mở rộng chính thức của **đúng phiên bản** và tránh đăng ký một `Cluster` hoặc `ClusterEnvironment` thứ hai không đồng bộ với client factory của Spring Data.

## 10. Nếu dùng reactive thì sao?

Ứng dụng reactive dùng các interface như `ReactiveCouchbaseRepository` và `ReactiveCouchbaseTemplate`, kết hợp với Reactor `Mono`/`Flux`. Phần kết nối cluster, username/password, bucket vẫn có cùng ý nghĩa.

Với repository reactive, thay cơ chế enable repository bằng annotation thích hợp trong cấu hình tương ứng:

~~~java
import org.springframework.data.couchbase.repository.config.EnableReactiveCouchbaseRepositories;

// Đặt trên lớp cấu hình dùng cho reactive:
// @EnableReactiveCouchbaseRepositories(
//     basePackageClasses = ReactiveProductRepository.class
// )
~~~

Ví dụ interface:

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Mono;

public interface ReactiveProductRepository
        extends ReactiveCouchbaseRepository<ProductDocument, String> {

    Mono<ProductDocument> findByName(String name);
}
~~~

Đoạn annotation ở trên minh họa **việc thay kiểu repository cần quét** khi chuyển từ đồng bộ sang reactive; nó không yêu cầu tạo một lớp cấu hình `AbstractCouchbaseConfiguration` thứ hai trong cùng context. Dùng starter reactive tương ứng và tránh gọi `block()` trên luồng xử lý WebFlux.

`findByName` là truy vấn theo thuộc tính, thường cần SQL++ và chỉ mục đúng collection; việc đổi sang reactive không bỏ qua điều kiện về Query service và index. Ví dụ:

~~~sql
CREATE INDEX ix_products_name
ON `inventory`.`catalog`.`products`(`name`);
~~~

Đối với logic cần độ nhất quán sau ghi, cần hiểu sự khác biệt giữa đọc KV bằng ID và quét index SQL++, cùng các lựa chọn scan consistency. Đây là quyết định ở tầng truy vấn và API, không phải bốn phương thức kết nối cơ bản.

## 11. Những lỗi cấu hình Java thường gặp

| Biểu hiện | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Class không compile vì thiếu phương thức | Chưa triển khai đúng tên/signature getter bắt buộc | So với API của `AbstractCouchbaseConfiguration`; đặc biệt `getUserName()` |
| Bean `CouchbaseSettings` không tìm thấy | Chưa đăng ký `@ConfigurationProperties` | Thêm `@EnableConfigurationProperties` hoặc config-properties scan đúng phạm vi |
| Bean repository không xuất hiện | Sai package trong `@EnableCouchbaseRepositories` | Kiểm tra `basePackageClasses` và package thực tế |
| Entity mapping bất thường | Domain nằm ngoài mapping scan | Kiểm tra `getMappingBasePackage()`, annotation và kiểu entity |
| Duplicate bean hoặc xung đột khởi tạo | Nhiều config cùng đăng ký hạ tầng, hoặc bean tự tạo xung đột | Chỉ rõ một chiến lược cấu hình và xem bean definitions |
| Đổi `spring.data.couchbase.bucket-name` nhưng ứng dụng vẫn dùng bucket cũ | Getter lấy `app.couchbase.bucket-name` | Kiểm tra nguồn mà `getBucketName()` trả về |
| Bootstrap / TLS timeout | Connection string, DNS, network, certificate, topology sai | Kiểm tra từ chính môi trường runtime |
| Authentication failed | Secret thiếu, sai username/password hoặc user không hợp lệ | Kiểm tra môi trường và quyền RBAC mà không in password |
| Thao tác KV thất bại dù bean đã tạo | Bucket/scope/collection thiếu hoặc RBAC không đủ | Kiểm tra keyspace và quyền Data service |
| `findById` chạy nhưng `findByName` lỗi | Thiếu Query service, index hoặc quyền truy vấn | Kiểm tra SQL++ index trên `inventory.catalog.products` |

**Lưu ý về thời điểm lỗi:** một số thành phần SDK khởi tạo theo nhu cầu. Do đó “Spring context khởi động thành công” chưa chứng minh ứng dụng có thể đọc/ghi đúng collection. Cần thực hiện ít nhất một lệnh KV trên tài nguyên dự định dùng.

## 12. Kiểm chứng bằng thao tác thật

Một kiểm tra kết nối đơn giản ở môi trường local là gọi repository bằng ID dự kiến không tồn tại. Lệnh này không cần dữ liệu mẫu và thường đi qua **Key-Value API**, giúp tách lỗi kết nối/bucket khỏi lỗi SQL++/index.

~~~java
package com.example.inventory.config;

import com.example.inventory.repository.ProductRepository;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("local")
public class LocalCouchbaseProbeConfig {

    @Bean
    ApplicationRunner verifyCouchbaseKv(ProductRepository repository) {
        return args -> {
            // Optional.empty() là kết quả hợp lệ cho ID không tồn tại.
            repository.findById("probe::missing");
            System.out.println("Couchbase KV probe completed");
        };
    }
}
~~~

Đây là kiểm tra minh họa dành cho local, không phải health-check đầy đủ cho production. Nếu thao tác ném lỗi, đọc thông báo để phân biệt các lớp: bootstrap, xác thực, mở bucket, quyền collection hoặc đường tới Data service.

Khi KV hoạt động, tiếp tục kiểm chứng repository query theo thuộc tính (nếu có), sau khi đã tạo index SQL++ phù hợp. Không dùng `findAll()` như phép thử kết nối duy nhất vì nó có thể dựa vào Query service/index và dẫn tới kết luận sai rằng lỗi nằm ở kết nối.

### Danh sách kiểm tra trước triển khai

1. **Cấu hình:** `app.couchbase.*` được bind đúng, không có nguồn property xung đột hoặc fallback local đi vào production.
2. **Bean:** chỉ một cấu hình hạ tầng chính cho cluster/bucket mục tiêu; repository và entity được scan đúng.
3. **Couchbase:** cluster, bucket, scope và collection đã tồn tại; tài khoản có quyền tối thiểu.
4. **Bảo mật:** secret đến từ runtime, TLS và chứng chỉ được xác minh khi môi trường yêu cầu.
5. **Thực thi:** đọc/ghi KV thành công trên đúng collection; truy vấn SQL++ chạy được với index thích hợp.
6. **Vận hành:** log không lộ mật khẩu, timeout và độ trễ được đo theo thao tác, có cách giám sát và xử lý lỗi kết nối.

## 13. Bài tập tình huống

Một dịch vụ đơn hàng đã có `AbstractCouchbaseConfiguration`, nhưng sau khi đổi cluster production thì thao tác `save` ghi vào sai bucket. Nhóm vận hành kiểm tra thấy YAML gồm cả:

~~~yaml
spring:
  data:
    couchbase:
      bucket-name: orders_prod

app:
  couchbase:
    bucket-name: orders_local
~~~

Trong Java config, `getBucketName()` trả về `settings.bucketName()`, còn `settings` được bind từ `app.couchbase`.

**Câu hỏi:** vì sao thay `spring.data.couchbase.bucket-name` không đủ? Cần thay đổi gì để tránh lặp lỗi?

**Phân tích:** lớp Java config đang dùng namespace `app.couchbase`, do đó giá trị bucket mặc định do getter cung cấp vẫn là `orders_local`. Cần thống nhất nguồn cấu hình cho môi trường hiện tại, sửa giá trị được bind từ `app.couchbase.bucket-name` hoặc chủ động thay chiến lược cấu hình. Sau đó xác nhận cluster đích, bucket đích, quyền RBAC và thao tác KV thực tế; đồng thời loại bỏ cấu hình trùng nghĩa gây hiểu lầm.

Một tình huống khác: `findById` trả về entity nhưng `findByName` ném lỗi SQL++. Đây thường không phải lỗi `getConnectionString()` hay `getBucketName()` nếu cả hai thao tác nhắm đúng keyspace; cần kiểm tra Query service, index, quyền và scan consistency.

## 14. Tổng kết

`AbstractCouchbaseConfiguration` cho phép viết **Java configuration tường minh** cho Spring Data Couchbase. Bốn phương thức `getConnectionString()`, `getUserName()`, `getPassword()`, `getBucketName()` xác định cách kết nối cluster và bucket mặc định; `@EnableCouchbaseRepositories` cùng cơ chế mapping xác định phần repository và entity.

Hãy xem lớp cấu hình này là một phần của thiết kế tầng dữ liệu: giữ secret ngoài mã nguồn, thống nhất nguồn property, kiểm soát phạm vi quét và tránh tạo bean trùng lặp. Sau khi kết nối, các quyết định về scope/collection, chỉ mục SQL++, TTL, CAS, giao dịch và API reactive tiếp tục quyết định hiệu năng, nhất quán và khả năng vận hành của hệ thống.


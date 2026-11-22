# Quản lý bí mật kết nối bằng cấu hình môi trường

Ứng dụng Spring Data Elasticsearch thường cần một số thông tin để kết nối cluster: địa chỉ node, tên người dùng, password hoặc API key, chứng chỉ CA và các tùy chọn TLS. Những giá trị như host và timeout là cấu hình vận hành; password, API key và private key là bí mật (secret). Nếu ghi secret trực tiếp trong source code, file cấu hình được commit, Docker image hoặc câu lệnh khởi chạy, chúng có thể bị lộ qua Git history, log build, process list, image layer hoặc công cụ giám sát.

Spring Boot hỗ trợ externalized configuration: cùng một ứng dụng có thể đọc cấu hình từ YAML/properties, environment variables, system properties và các nguồn cấu hình bên ngoài. Với secret, có thể dùng biến môi trường hoặc mount secret thành file rồi nạp bằng configuration tree (configtree:). Spring Data Elasticsearch nhận các giá trị đã bind để cấu hình ClientConfiguration, bật TLS và xác thực khi tạo client.

Bài học này trình bày cách tách cấu hình khỏi mã nguồn, bind bằng @ConfigurationProperties, tiêm credential vào cấu hình client, dùng biến môi trường và secret files, triển khai với Docker/Kubernetes, xác thực bằng Basic Auth hoặc API key, xác minh TLS, xoay vòng secret và tránh vô tình ghi secret vào log hoặc endpoint quản trị.

## 1. Phân biệt cấu hình thông thường và secret

Không phải mọi giá trị kết nối đều cần được bảo vệ ở cùng mức:

| Giá trị | Ví dụ | Phân loại |
|---|---|---|
| Host và port | search.internal:9200 | Cấu hình vận hành, thường không phải secret |
| Tên index | products | Cấu hình ứng dụng |
| Connect/socket timeout | 5s, 30s | Cấu hình vận hành |
| Username | catalog-writer | Thông tin định danh; nên hạn chế chia sẻ |
| Password | Password của service account | Secret |
| API key | Encoded Elasticsearch API key | Secret |
| Private key TLS | Khóa riêng của client certificate | Secret |
| CA certificate | Chứng chỉ CA công khai | Không phải password, nhưng cần bảo vệ tính toàn vẹn |
| CA fingerprint | SHA-256 fingerprint | Không phải secret; là dữ liệu dùng xác minh trust anchor |

Host, port, index name và timeout có thể nằm trong file cấu hình được quản lý theo môi trường. Password, API key và private key phải được cấp từ nguồn quản lý secret ở runtime.

Một nguyên tắc hữu ích là:

- Source code chứa tên property và logic kết nối.
- File cấu hình chứa các giá trị không nhạy cảm hoặc placeholder.
- Nền tảng triển khai cung cấp secret khi ứng dụng chạy.
- Client chỉ nhận secret qua dependency/configuration binding, không đọc secret từ Git hoặc hard-code trong Java.

## 2. Vì sao không hard-code credential?

Ví dụ không an toàn:

~~~java
ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo("search.example.internal:9200")
        .withBasicAuth("elastic", "my-real-password")
        .build();
~~~

Password nằm trong source code. Ngay cả khi xóa dòng này ở commit sau, secret vẫn có thể tồn tại trong Git history, fork, cache, artifact và bản sao của repository.

Một cách khác cũng không an toàn:

~~~yaml
spring:
  elasticsearch:
    uris: https://search.example.internal:9200
    username: catalog-writer
    password: my-real-password
~~~

Nếu file được đóng gói trong JAR hoặc commit vào repository, mọi người có quyền đọc artifact/source có thể lấy credential. Không đặt secret thật trong application.yaml, application-prod.yaml, file .env đã commit hoặc Dockerfile.

Việc mã hóa chuỗi trong source cũng không giải quyết vấn đề nếu khóa giải mã được lưu cùng ứng dụng. Mục tiêu là tách quyền truy cập secret khỏi quyền đọc source code và chỉ cấp secret cho workload cần sử dụng nó.

## 3. Spring Boot externalized configuration

Spring Boot có thể nạp property từ nhiều nguồn:

- application.properties hoặc application.yaml.
- File cấu hình bên ngoài JAR.
- Profile-specific configuration như application-prod.yaml.
- Environment variables của hệ điều hành/container.
- Java system properties.
- SPRING_APPLICATION_JSON.
- Command-line arguments.
- Configuration trees được mount thành file.
- Các nguồn bổ sung do thư viện tích hợp cung cấp, chẳng hạn secret store.

Các nguồn có thứ tự ưu tiên. Nguồn có ưu tiên cao hơn có thể ghi đè property cùng tên từ nguồn thấp hơn. Trong thứ tự mặc định, environment variables ghi đè config data trong file; system properties có ưu tiên cao hơn environment variables; command-line arguments có ưu tiên cao hơn các nguồn đó.

Điều này cho phép cùng một JAR chạy ở máy phát triển, staging và production với host/credential khác nhau mà không cần build lại artifact.

### 3.1. Property placeholder

Trong YAML hoặc properties, có thể tham chiếu một property khác bằng cú pháp:

~~~yaml
app:
  elasticsearch:
    host: ${APP_ELASTICSEARCH_HOST}
    username: ${APP_ELASTICSEARCH_USERNAME}
    password: ${APP_ELASTICSEARCH_PASSWORD}
~~~

Spring Boot giải quyết placeholder từ Environment. Nếu property bắt buộc không tồn tại và không có giá trị mặc định, ứng dụng thường thất bại khi bind/khởi tạo cấu hình. Đây là hành vi mong muốn đối với password production: thiếu secret thì không khởi động kết nối với credential rỗng hoặc mặc định.

Có thể viết default bằng dấu hai chấm:

~~~yaml
app:
  elasticsearch:
    host: ${APP_ELASTICSEARCH_HOST:localhost:9200}
~~~

Chỉ dùng default cho giá trị không nhạy cảm và có ý nghĩa an toàn trong môi trường tương ứng. Không viết password: ${APP_ELASTICSEARCH_PASSWORD:password} hoặc mặc định API key. Default credential có thể khiến ứng dụng vô tình dùng tài khoản yếu ở môi trường production.

### 3.2. Environment variable và relaxed binding

Spring Boot hỗ trợ relaxed binding từ tên property sang tên biến môi trường. Quy tắc cơ bản:

1. Thay dấu chấm (.) bằng dấu gạch dưới (_).
2. Bỏ dấu gạch ngang (-).
3. Chuyển toàn bộ thành chữ hoa.

Ví dụ:

| Property | Environment variable |
|---|---|
| app.elasticsearch.host | APP_ELASTICSEARCH_HOST |
| app.elasticsearch.username | APP_ELASTICSEARCH_USERNAME |
| app.elasticsearch.password | APP_ELASTICSEARCH_PASSWORD |
| app.elasticsearch.ca-fingerprint | APP_ELASTICSEARCH_CAFINGERPRINT |
| app.elasticsearch.api-key | APP_ELASTICSEARCH_APIKEY |

Với @ConfigurationProperties, prefix nên dùng kebab-case chữ thường, ví dụ app.elasticsearch. Environment variable dùng chữ hoa và dấu gạch dưới.

Nếu property được khai báo trực tiếp bằng tên chuẩn trong @ConfigurationProperties, Spring có thể bind từ environment variable mà không cần lặp lại placeholder trong YAML. Ví dụ class có prefix app.elasticsearch và field password sẽ nhận APP_ELASTICSEARCH_PASSWORD.

## 4. Dùng @ConfigurationProperties để bind cấu hình kết nối

Khi có nhiều property liên quan, @ConfigurationProperties thường rõ ràng và dễ validate hơn việc rải nhiều @Value trong configuration class.

Ví dụ record:

~~~java
package com.example.catalog.config;

import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.elasticsearch")
public record ElasticsearchConnectionProperties(
        @NotBlank String host,
        @NotBlank String username,
        @NotBlank String password,
        @NotBlank String caFingerprint) {
}
~~~

Các annotation validation giúp phát hiện property bắt buộc bị thiếu hoặc chỉ chứa khoảng trắng khi ứng dụng khởi động. Cần có validation implementation trên classpath, thường là spring-boot-starter-validation.

Đăng ký properties:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

@ConfigurationPropertiesScan tìm các class cấu hình trong package ứng dụng và package con. Một cách khác là dùng @EnableConfigurationProperties(ElasticsearchConnectionProperties.class) trên configuration class cụ thể.

### 4.1. application.yaml không chứa secret

File cấu hình có thể chỉ chứa tên property và placeholder:

~~~yaml
app:
  elasticsearch:
    host: ${APP_ELASTICSEARCH_HOST}
    username: ${APP_ELASTICSEARCH_USERNAME}
    password: ${APP_ELASTICSEARCH_PASSWORD}
    ca-fingerprint: ${APP_ELASTICSEARCH_CA_FINGERPRINT}
~~~

File này có thể được commit vì không chứa giá trị credential thực. Tên host, username và fingerprint vẫn có thể được xem là thông tin nội bộ; áp dụng chính sách truy cập repository phù hợp nếu môi trường yêu cầu.

Nếu muốn bind trực tiếp từ environment variable, file YAML có thể không khai báo nhóm app.elasticsearch nào. Khi đó @ConfigurationProperties nhận giá trị từ environment source theo relaxed binding.

### 4.2. @Value và Environment

Với một property đơn giản, có thể dùng:

~~~java
@Value("${app.elasticsearch.host}")
private String elasticsearchHost;
~~~

Hoặc đọc qua Environment:

~~~java
String host = environment.getRequiredProperty("app.elasticsearch.host");
~~~

Hai cách này phù hợp với trường hợp nhỏ hoặc cần truy cập property động. Khi có một nhóm cấu hình kết nối gồm host, username, password, TLS fingerprint và timeout, @ConfigurationProperties gom chúng thành một object có kiểu, dễ kiểm tra và dễ test.

Không log object properties bằng toString() nếu object chứa secret. Record Java tự sinh toString() bao gồm các component, vì vậy có thể vô tình in password ra log. Có thể dùng class có toString() đã che secret hoặc tuyệt đối không ghi object này vào log.

## 5. Cấu hình Spring Data Elasticsearch ClientConfiguration

Spring Data Elasticsearch cung cấp ClientConfiguration để cấu hình địa chỉ cluster, SSL, timeout, headers và Basic Authentication. Với client imperative hiện hành, có thể kế thừa ElasticsearchConfiguration.

Ví dụ:

~~~java
package com.example.catalog.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ProductElasticsearchConfiguration
        extends ElasticsearchConfiguration {

    private final ElasticsearchConnectionProperties properties;

    public ProductElasticsearchConfiguration(
            ElasticsearchConnectionProperties properties) {
        this.properties = properties;
    }

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo(properties.host())
                .usingSsl(properties.caFingerprint())
                .withBasicAuth(
                        properties.username(),
                        properties.password())
                .build();
    }
}
~~~

connectedTo nhận địa chỉ host và port. usingSsl bật TLS và có overload nhận CA fingerprint. withBasicAuth cấu hình username/password cho request. Spring Data tạo client và operations bean từ cấu hình này.

Không nối username/password vào URL như https://user:password@host:9200. Credential trong URL dễ bị ghi vào log, trace, exception hoặc lịch sử lệnh.

### 5.1. Nếu dùng CA certificate thay vì fingerprint

Có thể cấu hình SSL bằng SSLContext được tạo từ CA certificate và truyền vào overload tương ứng của usingSsl. Ví dụ:

~~~java
SSLContext sslContext = createSslContextFromTrustedCa(caCertificatePath);

ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo(properties.host())
        .usingSsl(sslContext)
        .withBasicAuth(properties.username(), properties.password())
        .build();
~~~

createSslContextFromTrustedCa là helper minh họa; cách nạp certificate phụ thuộc nơi mount và thư viện TLS mà ứng dụng dùng. Nếu dùng Elasticsearch Java API Client trực tiếp, TransportUtils.sslContextFromHttpCaCrt(...) hoặc sslContextFromCaFingerprint(...) là các tiện ích được tài liệu Elasticsearch hướng dẫn.

CA certificate không cần giữ bí mật như password, nhưng cần bảo vệ tính toàn vẹn. Nếu attacker thay được CA certificate hoặc fingerprint mà ứng dụng tin cậy, họ có thể khiến ứng dụng tin nhầm endpoint.

### 5.2. Reactive client

Với ứng dụng reactive, cấu hình kế thừa ReactiveElasticsearchConfiguration:

~~~java
@Configuration
public class ReactiveProductElasticsearchConfiguration
        extends ReactiveElasticsearchConfiguration {

    private final ElasticsearchConnectionProperties properties;

    public ReactiveProductElasticsearchConfiguration(
            ElasticsearchConnectionProperties properties) {
        this.properties = properties;
    }

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo(properties.host())
                .usingSsl(properties.caFingerprint())
                .withBasicAuth(
                        properties.username(),
                        properties.password())
                .build();
    }
}
~~~

Reactive configuration tạo ReactiveElasticsearchOperations và reactive client tương ứng. Không dùng ElasticsearchConfiguration imperative cho repository reactive. Nếu cấu hình header bằng supplier trong reactive client, supplier không được block.

### 5.3. Tránh cấu hình client legacy

Spring Data Elasticsearch 6.x sử dụng Rest5Client trong cấu hình client hiện hành. Các class cấu hình legacy dựa trên RestClient cũ đã deprecated từ Spring Data Elasticsearch 6.0. Khi viết cấu hình mới, dùng ElasticsearchConfiguration hoặc ReactiveElasticsearchConfiguration tương ứng với stack.

## 6. Dùng API key thay cho username/password

Elasticsearch hỗ trợ API key authentication. API key thường phù hợp với service-to-service access vì có thể cấp quyền cụ thể, đặt expiration và thu hồi độc lập với tài khoản người dùng.

Khi dùng API key, client gửi header:

~~~http
Authorization: ApiKey ENCODED_API_KEY
~~~

Spring Data ClientConfiguration có thể thêm header mặc định:

Khi chọn API key, dùng properties class riêng để không yêu cầu username/password:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.elasticsearch")
public record ElasticsearchApiKeyProperties(
        @NotBlank String host,
        @NotBlank String apiKey,
        @NotBlank String caFingerprint) {
}
~~~

~~~java
import org.springframework.data.elasticsearch.support.HttpHeaders;

HttpHeaders headers = new HttpHeaders();
headers.add(
        "Authorization",
        "ApiKey " + properties.apiKey());

ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo(properties.host())
        .usingSsl(properties.caFingerprint())
        .withDefaultHeaders(headers)
        .build();
~~~

Trong cấu hình này, apiKey được bind từ APP_ELASTICSEARCH_APIKEY hoặc secret store. Không cấu hình đồng thời Basic Auth và API key nếu ứng dụng không có yêu cầu xác thực đặc biệt; chọn một phương thức rõ ràng để giảm nhầm lẫn.

API key là secret. Không ghi header Authorization vào log, không gửi nó cho frontend và không dùng cùng một key cho nhiều ứng dụng không liên quan.

### 6.1. Cấp quyền tối thiểu

Không nên dùng tài khoản elastic hoặc một superuser cho ứng dụng tìm kiếm/catalog. Tạo service account hoặc API key chỉ có quyền cần thiết:

- Đọc index mà ứng dụng cần search.
- Index/update document nếu ứng dụng ghi dữ liệu.
- Tạo index hoặc quản lý mapping chỉ cho thành phần triển khai được phép.
- Không cấp quyền quản trị cluster nếu ứng dụng chỉ cần đọc/ghi một index.

Tách credential theo workload, ví dụ một key chỉ đọc cho search API và một key có quyền ghi cho indexing worker. Nếu một credential bị lộ, phạm vi ảnh hưởng sẽ nhỏ hơn.

### 6.2. API key và quyền theo index

Khi tạo API key, role descriptor có thể giới hạn quyền theo index và action. Ví dụ minh họa về ý tưởng quyền:

~~~json
{
  "indices": [
    {
      "names": ["products"],
      "privileges": ["read"]
    }
  ]
}
~~~

Đây là ví dụ quyền đọc. Nếu worker cần ghi, chỉ thêm quyền phù hợp như write hoặc quyền quản lý index được yêu cầu. Không cấp all hoặc manage theo thói quen khi ứng dụng không cần chúng.

## 7. Cung cấp secret qua environment variables

Environment variable là cách phổ biến để truyền cấu hình runtime vào process/container. Ví dụ trên Linux/macOS:

~~~bash
export APP_ELASTICSEARCH_HOST="search.internal:9200"
export APP_ELASTICSEARCH_USERNAME="catalog-writer"
export APP_ELASTICSEARCH_PASSWORD="<injected-at-runtime>"
export APP_ELASTICSEARCH_CA_FINGERPRINT="<trusted-sha256-fingerprint>"

java -jar catalog-service.jar
~~~

Giá trị trong dấu ngoặc nhọn là placeholder; không dùng chuỗi này làm credential thật. Nền tảng triển khai cần cung cấp giá trị thực qua secret store hoặc cơ chế runtime phù hợp.

Trên PowerShell, có thể đặt environment variable cho process hiện tại:

~~~powershell
$env:APP_ELASTICSEARCH_HOST = "search.internal:9200"
$env:APP_ELASTICSEARCH_USERNAME = "catalog-writer"
$env:APP_ELASTICSEARCH_PASSWORD = "<injected-at-runtime>"
$env:APP_ELASTICSEARCH_CA_FINGERPRINT = "<trusted-sha256-fingerprint>"

java -jar .\catalog-service.jar
~~~

Không dùng password thật trong script được commit hoặc trong lệnh mà shell history, terminal transcript hay công cụ quản lý process có thể lưu lại. Với môi trường production, hãy để orchestrator/secret manager cung cấp environment variables hoặc secret files.

### 7.1. Ưu điểm và giới hạn của environment variables

Ưu điểm:

- Được hầu hết runtime, container platform và CI/CD hỗ trợ.
- Dễ bind vào @ConfigurationProperties.
- Không cần đóng gói secret trong JAR.
- Cùng một artifact dùng được ở nhiều môi trường.

Giới hạn:

- Environment của process có thể bị đọc bởi người có quyền phù hợp trên host/container.
- Có thể xuất hiện trong diagnostic dump hoặc script debug.
- Giá trị thường được cố định khi process khởi động; đổi secret ở nguồn không tự thay đổi environment của process đang chạy.
- Giá trị dài hoặc có ký tự đặc biệt có thể khó truyền qua một số shell/platform.

Environment variable là một kênh truyền cấu hình, không phải secret manager hoàn chỉnh. Với secret nhạy cảm, mounted secret file hoặc secret manager thường cung cấp kiểm soát truy cập và rotation tốt hơn.

### 7.2. Không truyền secret qua command-line argument

Tránh:

~~~bash
java -jar catalog-service.jar \
  --app.elasticsearch.password="real-password"
~~~

Command-line arguments có thể hiển thị trong process list, job log, shell history hoặc hệ thống giám sát. Ngoài ra, command-line property có độ ưu tiên cao và có thể ghi đè environment variable, khiến việc điều tra cấu hình trở nên khó hiểu.

Hãy truyền secret bằng runtime environment hoặc secret file được mount.

## 8. Dùng configuration tree cho secret file

Spring Boot hỗ trợ configtree: để biến tên file trong một thư mục thành property key và nội dung file thành property value. Cách này phù hợp khi Kubernetes Secret hoặc Docker Secret được mount vào container.

Ví dụ cấu trúc:

~~~text
/run/secrets/
    app.elasticsearch.username
    app.elasticsearch.password
    app.elasticsearch.ca-fingerprint
~~~

Nội dung mỗi file là giá trị tương ứng. File app.elasticsearch.password chứa password; tên file tạo ra property app.elasticsearch.password.

Thêm vào application.yaml:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Sau khi import, có thể bind như các property khác:

~~~java
@ConfigurationProperties(prefix = "app.elasticsearch")
public record ElasticsearchConnectionProperties(
        @NotBlank String username,
        @NotBlank String password,
        @NotBlank String caFingerprint) {
}
~~~

configtree: không mã hóa nội dung file. Nó chỉ đưa file đã được nền tảng mount vào Spring Environment. Quyền truy cập file, encryption at rest, phân quyền mount và rotation vẫn do nền tảng secret quản lý.

### 8.1. Optional hay required config tree?

Nếu secret volume bắt buộc phải có ở production, dùng import bắt buộc:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Nếu thêm tiền tố optional::

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Spring Boot có thể tiếp tục khởi động khi thư mục không tồn tại. Điều này phù hợp với môi trường dev/test có cấu hình thay thế, nhưng không nên vô tình che giấu việc thiếu secret trong production. Dù dùng optional import, validation của @ConfigurationProperties vẫn phải bảo đảm credential bắt buộc có giá trị trước khi tạo client.

### 8.2. Import một file hoặc file không có extension

Nếu nền tảng mount một file YAML/Properties hoàn chỉnh, có thể import file đó bằng spring.config.import. Với file không có extension, chỉ định extension hint:

~~~yaml
spring:
  config:
    import: "file:/etc/catalog/elasticsearch-config[.yaml]"
~~~

Nếu mỗi secret là một file riêng, dùng configtree:. Nếu một file chứa cả nhóm cấu hình dạng YAML/Properties, import trực tiếp file đó.

## 9. Kubernetes Secret

Kubernetes có thể mount Secret vào container dưới dạng volume. Một cách tổ chức là tạo Secret với các key trùng property name:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: catalog-elasticsearch
type: Opaque
stringData:
  app.elasticsearch.username: catalog-writer
  app.elasticsearch.password: REPLACE_WITH_SECRET_MANAGER_VALUE
  app.elasticsearch.ca-fingerprint: REPLACE_WITH_TRUSTED_FINGERPRINT
~~~

Các giá trị trên chỉ minh họa cấu trúc. Không commit Secret production chứa credential thật vào Git. Trong thực tế, dùng secret manager hoặc quy trình cấp secret của nền tảng để tạo/cập nhật Kubernetes Secret.

Deployment mount Secret:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
spec:
  template:
    spec:
      containers:
        - name: catalog-service
          image: example/catalog-service:1.0.0
          volumeMounts:
            - name: elasticsearch-secrets
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: elasticsearch-secrets
          secret:
            secretName: catalog-elasticsearch
            defaultMode: 0440
~~~

Với cấu trúc này, file trong volume được nạp qua configtree:/run/secrets/.

### 9.1. Kubernetes Secret không tự động đồng nghĩa với mã hóa

Kubernetes Secret object thường được biểu diễn bằng base64 trong manifest/API. Base64 chỉ là encoding, không phải encryption. Cần áp dụng:

- Encryption at rest cho dữ liệu Secret trong etcd.
- RBAC giới hạn ai được đọc, tạo hoặc cập nhật Secret.
- Hạn chế quyền service account và namespace.
- Chỉ mount secret vào container cần sử dụng.
- Mount read-only.
- Không đưa secret vào image hoặc ConfigMap.
- Dùng external secret manager khi cần audit, rotation và chính sách truy cập tập trung.

### 9.2. Secret dưới dạng environment variable trong Kubernetes

Kubernetes cũng có thể đưa Secret vào environment variable bằng secretKeyRef. Ví dụ:

~~~yaml
env:
  - name: APP_ELASTICSEARCH_PASSWORD
    valueFrom:
      secretKeyRef:
        name: catalog-elasticsearch
        key: password
~~~

Khi dùng cách này, Spring bind property từ environment variable. Tuy nhiên, giá trị được đưa vào environment của container và thường chỉ cập nhật khi Pod được tạo lại. Với secret file mount, file có thể được cập nhật theo cơ chế volume của Kubernetes, nhưng Spring Environment và client đã khởi tạo không tự động reload giá trị mới.

## 10. Docker secrets

Docker Swarm có thể cấp secret dưới dạng file mount trong container, thường nằm dưới /run/secrets. Spring Boot có thể đọc chúng bằng configuration tree:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Trong Compose/Swarm, có thể map tên secret vào tên file đích:

~~~yaml
services:
  catalog:
    image: example/catalog-service:1.0.0
    secrets:
      - source: elasticsearch-password
        target: app.elasticsearch.password

secrets:
  elasticsearch-password:
    file: ./local-secrets/elasticsearch-password.txt
~~~

Container nhìn thấy file /run/secrets/app.elasticsearch.password, từ đó Spring tạo property app.elasticsearch.password.

File nguồn local chỉ là ví dụ cho môi trường phát triển. Không commit file chứa secret thật. Với production, dùng secret management của nền tảng và giới hạn quyền đọc.

## 11. Dùng secret manager bên ngoài

Khi có nhiều service hoặc nhiều môi trường, secret manager giúp quản lý vòng đời credential tập trung:

- HashiCorp Vault.
- Cloud secret manager của nhà cung cấp nền tảng.
- Kubernetes external secrets integration.
- Secret store được tích hợp qua Spring Cloud hoặc thư viện tương ứng.

Spring Boot không cung cấp cơ chế mã hóa mọi property mặc định. Nó cung cấp điểm tích hợp để nạp cấu hình từ nguồn ngoài; thư viện/secret manager chịu trách nhiệm xác thực, phân quyền, đọc và có thể rotation secret.

Một luồng triển khai điển hình:

~~~text
Secret Manager
      |
      | cấp credential cho workload identity
      v
Runtime / deployment platform
      |
      | inject env hoặc mount secret file
      v
Spring Boot Environment
      |
      | bind @ConfigurationProperties
      v
ClientConfiguration
      |
      v
Elasticsearch client
~~~

Nếu dùng Vault hoặc cloud secret manager, ưu tiên workload identity/service identity thay vì lưu một credential dài hạn khác trong application config chỉ để đọc secret manager.

## 12. Không đặt secret trong profile file

Profiles như dev, staging, prod hữu ích để chọn host, index prefix, timeout hoặc feature flag:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod

app:
  elasticsearch:
    host: search-prod.internal:9200
    connect-timeout: 5s
    socket-timeout: 30s
~~~

Không đặt password production trong application-prod.yaml. Profile file thường nằm trong source hoặc artifact, còn secret nên được cấp từ môi trường triển khai.

Có thể dùng cùng một JAR cho mọi môi trường:

| Môi trường | Host | Credential |
|---|---|---|
| Local | localhost:9200 | Credential dev riêng |
| Test | Elasticsearch container | Credential test dùng một lần |
| Staging | Cluster staging | Secret staging |
| Production | Cluster production | Secret production |

Không dùng chung password/API key giữa các môi trường. Credential dev bị lộ không nên cho phép truy cập cluster production.

## 13. TLS và xác minh máy chủ

Xác thực người dùng và mã hóa kết nối là hai việc khác nhau:

- Authentication xác định client là ai.
- TLS mã hóa đường truyền và xác minh endpoint server.

Chỉ dùng HTTPS/TLS không có nghĩa client đã xác minh đúng server. Client phải tin cậy CA certificate hoặc fingerprint hợp lệ.

Với Elasticsearch tự quản lý, security features có thể bật authentication và TLS. Có thể lấy CA certificate http_ca.crt hoặc SHA-256 fingerprint của CA từ quá trình cài đặt/khởi động cluster. Xác minh fingerprint từ kênh tin cậy trước khi đưa vào cấu hình.

Ví dụ Spring Data:

~~~java
ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo(properties.host())
        .usingSsl(properties.caFingerprint())
        .withBasicAuth(properties.username(), properties.password())
        .build();
~~~

Không tắt hostname verification, không dùng trust-all certificate manager và không bỏ qua certificate validation để sửa nhanh lỗi SSL. Những cách đó khiến client có thể kết nối tới server giả mạo.

### 13.1. Phân biệt CA fingerprint với password

CA fingerprint không phải credential xác thực người dùng. Nó là giá trị dùng để xác minh CA. Nó thường không cần giữ bí mật, nhưng phải được lấy từ nguồn đáng tin cậy và thay đổi có kiểm soát khi CA được rotate.

Password/API key cần được bảo vệ bí mật và có thể thu hồi. Fingerprint/certificate cần được bảo vệ tính toàn vẹn và cập nhật đúng khi certificate authority thay đổi.

### 13.2. Không truyền credential trong URL

Không dùng:

~~~text
https://catalog-writer:secret-value@search.internal:9200
~~~

Dùng host riêng và cấu hình authentication riêng:

~~~java
ClientConfiguration.builder()
        .connectedTo("search.internal:9200")
        .usingSsl(caFingerprint)
        .withBasicAuth(username, password)
        .build();
~~~

URL có thể xuất hiện trong access log, error message, metrics label hoặc tracing span.

## 14. Giới hạn quyền của Elasticsearch account

Không sử dụng built-in superuser elastic trong ứng dụng thông thường. Tạo user hoặc API key riêng cho từng workload:

| Workload | Quyền nên cấp |
|---|---|
| Search API | Đọc/search các index được phép |
| Catalog writer | Đọc/ghi index catalog cần thiết |
| Index migration job | Tạo index/mapping/alias trong giai đoạn triển khai |
| Monitoring agent | Chỉ quyền giám sát cần thiết |

Nếu ứng dụng chỉ đọc products, không cấp quyền ghi orders hoặc quản trị cluster. Nếu worker ghi products, không cần cấp quyền xóa index hoặc quản lý user.

Quyền càng nhỏ thì sự cố lộ credential càng ít gây ảnh hưởng. Ghi lại owner, mục đích, index scope, thời hạn và quy trình thu hồi của mỗi API key.

## 15. Xoay vòng password hoặc API key

Secret có vòng đời: tạo, cấp, sử dụng, rotate, revoke. Đổi secret ở secret manager không nhất thiết làm client đang chạy tự dùng giá trị mới.

Một quy trình rotation an toàn:

1. Tạo credential mới với quyền tương đương hoặc quyền đã được thu hẹp.
2. Lưu credential mới vào secret manager hoặc secret store.
3. Cập nhật runtime secret cho workload.
4. Khởi động lại/rollout hoặc dùng cơ chế refresh client đã được thiết kế và kiểm thử.
5. Xác nhận ứng dụng mới xác thực và thực hiện được thao tác cần thiết.
6. Theo dõi lỗi authentication trong thời gian chuyển tiếp.
7. Thu hồi credential cũ sau khi mọi instance đã chuyển sang credential mới.
8. Ghi nhận thời điểm, owner và kết quả rotation.

Nếu secret được mount thành file, nền tảng có thể cập nhật nội dung file, nhưng @ConfigurationProperties đã bind và Elasticsearch client đã tạo không tự động đọc lại file. Cần restart/rollout hoặc triển khai cơ chế refresh có kiểm soát và tái tạo client.

Với API key, có thể tạo key mới trước, chuyển workload, rồi invalidate key cũ. Tránh revoke key cũ trước khi ứng dụng mới đã kết nối thành công nếu không có đường rollback.

### 15.1. Không rotation bằng cách sửa file trong image

Không build lại Docker image chỉ để thay password. Image nên bất biến; secret được cấp khi container chạy. Nếu secret thay đổi, cập nhật secret runtime và rollout workload theo quy trình.

### 15.2. Xử lý credential bị lộ

Nếu password/API key bị commit hoặc xuất hiện trong log:

- Thu hồi hoặc rotate credential ngay.
- Kiểm tra quyền và audit log của credential.
- Xác định các artifact, log, fork và môi trường có thể đã nhận secret.
- Loại secret khỏi source hiện tại, nhưng nhớ rằng xóa khỏi commit mới không xóa bản sao trong Git history.
- Xem xét lịch sử truy cập và giới hạn quyền của credential thay thế.

Không chỉ xóa dòng password rồi coi sự cố đã kết thúc; secret đã lộ phải được xem là có thể đã bị sao chép.

## 16. Tránh lộ secret qua log và observability

Không log:

- Password hoặc API key.
- Header Authorization.
- Object @ConfigurationProperties có chứa secret.
- Toàn bộ Environment hoặc property source.
- URL có username/password.
- Request/response debug chứa credential.

Không bật transport-level TRACE trong production nếu chưa đánh giá nội dung log. Log request có thể chứa headers hoặc thông tin nhạy cảm tùy client và cấu hình.

Actuator có các endpoint như env và configprops hữu ích khi điều tra cấu hình. Chúng có thể tiết lộ thông tin cấu hình; cần giới hạn endpoint được expose, bảo vệ authentication/authorization và kiểm tra chính sách sanitization. Không công khai các endpoint này trên mạng không tin cậy.

Khi log lỗi kết nối, ghi thông tin đủ để điều tra nhưng không ghi credential:

~~~java
log.error(
        "Cannot connect to Elasticsearch host {}",
        properties.host(),
        exception);
~~~

Không ghi properties object hoặc password vào message. Cũng cần xem xét liệu hostname có phải thông tin nội bộ cần che trong môi trường cụ thể hay không.

## 17. Không để secret lọt vào Git, CI/CD hoặc container image

Các vị trí thường vô tình lưu secret:

- Source code và test fixture.
- application-prod.yaml.
- .env hoặc file local.
- Dockerfile ENV hoặc ARG.
- Docker build logs.
- CI/CD variables bị echo ra stdout.
- Gradle/Maven command line.
- Shell history.
- Artifact, crash dump và support bundle.

Quy tắc thực tế:

- Thêm file secret local vào .gitignore.
- Commit .env.example chỉ chứa tên biến và placeholder.
- Không dùng ARG PASSWORD hoặc ENV PASSWORD trong Dockerfile để nhúng credential vào image.
- Dùng secret injection ở runtime.
- Mask CI/CD secret trong log và không in command có giá trị secret.
- Hạn chế ai có quyền xem pipeline variables.
- Quét repository và artifact để phát hiện credential vô tình commit.
- Khi secret đã xuất hiện trong Git, rotate nó thay vì chỉ sửa file.

Ví dụ .gitignore:

~~~gitignore
.env
.env.*
!.env.example
local-secrets/
secrets/
~~~

Ví dụ .env.example:

~~~dotenv
APP_ELASTICSEARCH_HOST=localhost:9200
APP_ELASTICSEARCH_USERNAME=
APP_ELASTICSEARCH_PASSWORD=
APP_ELASTICSEARCH_CA_FINGERPRINT=
~~~

File mẫu không chứa secret thật. Người phát triển có thể tạo file local riêng hoặc dùng secret test được cấp bởi môi trường.

## 18. Kiểm tra cấu hình bắt buộc và fail fast

Ứng dụng không nên khởi động với password mặc định hoặc giá trị rỗng rồi chỉ phát hiện lỗi khi request đầu tiên chạy.

Dùng validation:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.elasticsearch")
public record ElasticsearchConnectionProperties(
        @NotBlank String host,
        @NotBlank String username,
        @NotBlank String password,
        @NotBlank String caFingerprint) {
}
~~~

Nếu dùng API key thay cho Basic Auth, định nghĩa properties phù hợp và validate đúng phương thức được chọn. Tránh để cả password và API key là optional rồi vô tình tạo client không có authentication.

Có thể thêm validation custom để kiểm tra host format, fingerprint length/hex format hoặc đảm bảo chỉ dùng HTTPS/TLS ở profile production. Không log giá trị sai trong validation error nếu đó là secret.

Ví dụ thông báo an toàn:

~~~text
Configuration property app.elasticsearch.password must be provided
~~~

Tránh thông báo:

~~~text
Invalid Elasticsearch password: <actual-secret-value>
~~~

## 19. Kiểm thử cấu hình mà không dùng credential production

Test nên dùng credential riêng, giá trị giả hoặc container test. Không đọc secret production vào unit test và không in property trong assertion failure.

### 19.1. Unit test @ConfigurationProperties

Có thể kiểm tra binding với ApplicationContextRunner hoặc Spring Boot test properties:

~~~java
@SpringBootTest(properties = {
        "app.elasticsearch.host=localhost:9200",
        "app.elasticsearch.username=test-user",
        "app.elasticsearch.password=test-only-secret",
        "app.elasticsearch.ca-fingerprint=test-fingerprint"
})
class ElasticsearchConnectionPropertiesTest {

    @Autowired
    ElasticsearchConnectionProperties properties;

    @Test
    void bindsConnectionProperties() {
        assertThat(properties.host()).isEqualTo("localhost:9200");
        assertThat(properties.username()).isEqualTo("test-user");
        assertThat(properties.password()).isEqualTo("test-only-secret");
    }
}
~~~

Trong test thật, không in object properties hoặc password. Có thể chỉ xác nhận property tồn tại hoặc client được tạo.

### 19.2. DynamicPropertySource với Testcontainers

Khi dùng Testcontainers, địa chỉ Elasticsearch thường được tạo động. Có thể đăng ký property bằng @DynamicPropertySource:

~~~java
@DynamicPropertySource
static void elasticsearchProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "app.elasticsearch.host",
            () -> elasticsearchContainer.getHost()
                    + ":" + elasticsearchContainer.getMappedPort(9200));
    registry.add("app.elasticsearch.username", () -> "test-user");
    registry.add("app.elasticsearch.password", () -> "test-only-password");
    registry.add("app.elasticsearch.ca-fingerprint", () -> testFingerprint);
}
~~~

Đoạn minh họa giả định container và TLS fixture đã được cấu hình. Với cluster test không bật security, hãy dùng một cấu hình test riêng không yêu cầu production secret; không vô hiệu hóa TLS validation trong production chỉ để test dễ chạy.

### 19.3. Kiểm tra secret không xuất hiện trong log

Có thể dùng appender test để xác nhận password giả không xuất hiện trong log message khi khởi tạo client hoặc khi kết nối thất bại. Không cần in giá trị để debug test; assertion chỉ kiểm tra chuỗi secret không xuất hiện.

## 20. Chẩn đoán lỗi kết nối

Khi ứng dụng không kết nối được Elasticsearch, phân loại lỗi trước khi thay đổi credential:

| Triệu chứng | Khả năng nguyên nhân | Kiểm tra |
|---|---|---|
| Connection refused | Host/port sai hoặc service chưa lắng nghe | DNS, service endpoint, port, network policy |
| Unknown host | DNS hoặc hostname sai | DNS trong container/pod |
| 401 Unauthorized | Username/password/API key sai hoặc hết hạn | Secret source, key status, auth method |
| 403 Forbidden | Credential hợp lệ nhưng thiếu quyền | Role descriptor và index privileges |
| SSL handshake failure | CA/fingerprint sai, certificate hết hạn hoặc hostname mismatch | Trust chain, fingerprint, SAN và thời hạn certificate |
| Timeout | Network, cluster quá tải hoặc timeout quá thấp | Connectivity, cluster health, timeout và retry |
| Missing property | Secret chưa được mount hoặc tên property không khớp | spring.config.import, file name và env binding |
| Giá trị cũ sau rotation | Process vẫn giữ property/client cũ | Restart/refresh và rollout trạng thái |

Không xử lý lỗi TLS bằng cách bỏ xác minh certificate. Không xử lý lỗi 403 bằng cách cấp superuser; cấp đúng quyền tối thiểu cần thiết.

## 21. Kiểm tra property source an toàn

Spring Boot Actuator env và configprops có thể giúp xác định property được lấy từ nguồn nào, nhưng không nên mở chúng công khai chỉ để debug.

Khi cần chẩn đoán:

1. Kiểm tra property key và nguồn cấu hình.
2. Kiểm tra biến môi trường có tồn tại trong container hay không mà không echo giá trị secret.
3. Kiểm tra secret file có tồn tại, permission và tên file.
4. Xác nhận configtree: đã import đúng thư mục.
5. Kiểm tra @ConfigurationProperties bean đã được đăng ký và bind.
6. Kiểm tra client dùng đúng host, TLS và phương thức authentication.
7. Xem error type/status mà không log header hoặc password.

Nếu cần xác nhận secret đã được nạp, có thể kiểm tra trạng thái present/not present hoặc một fingerprint nội bộ không thể dùng để khôi phục secret; không in giá trị secret ra terminal.

## 22. Ví dụ cấu hình hoàn chỉnh bằng environment variables

File application.yaml:

~~~yaml
app:
  elasticsearch:
    host: ${APP_ELASTICSEARCH_HOST}
    username: ${APP_ELASTICSEARCH_USERNAME}
    password: ${APP_ELASTICSEARCH_PASSWORD}
    ca-fingerprint: ${APP_ELASTICSEARCH_CA_FINGERPRINT}
~~~

Properties:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.elasticsearch")
public record ElasticsearchConnectionProperties(
        @NotBlank String host,
        @NotBlank String username,
        @NotBlank String password,
        @NotBlank String caFingerprint) {
}
~~~

Client configuration:

~~~java
@Configuration
public class ProductElasticsearchConfiguration
        extends ElasticsearchConfiguration {

    private final ElasticsearchConnectionProperties properties;

    public ProductElasticsearchConfiguration(
            ElasticsearchConnectionProperties properties) {
        this.properties = properties;
    }

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo(properties.host())
                .usingSsl(properties.caFingerprint())
                .withBasicAuth(
                        properties.username(),
                        properties.password())
                .withConnectTimeout(Duration.ofSeconds(5))
                .withSocketTimeout(Duration.ofSeconds(30))
                .build();
    }
}
~~~

Nền tảng runtime cung cấp bốn environment variables. Source code và JAR không chứa credential. Spring Data tạo ElasticsearchClient và ElasticsearchOperations từ ClientConfiguration; repository dùng operations được cấu hình bên dưới.

## 23. Ví dụ cấu hình hoàn chỉnh bằng mounted secret files

File application.yaml:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"

app:
  elasticsearch:
    host: search.internal:9200
~~~

Mounted files:

~~~text
/run/secrets/
    app.elasticsearch.username
    app.elasticsearch.password
    app.elasticsearch.ca-fingerprint
~~~

@ConfigurationProperties bind host từ YAML và username/password/fingerprint từ configuration tree. Client configuration dùng cùng constructor injection như ví dụ environment variables.

Cách này phù hợp khi nền tảng quản lý secret bằng file mount. Cần bảo đảm thư mục tồn tại ở production, file permission hạn chế và import không bị đánh dấu optional nếu thiếu secret phải làm ứng dụng dừng.

## 24. Các lỗi thường gặp

### Commit password trong application.yaml

File cấu hình được đóng gói hoặc commit có thể bị nhiều người và pipeline đọc. Chỉ commit placeholder, lấy giá trị thật từ runtime secret source.

### Mã hóa password rồi commit ciphertext

Nếu khóa giải mã nằm trong cùng source hoặc artifact, attacker có cả ciphertext lẫn khóa. Dùng secret manager hoặc runtime injection.

### Dùng default credential

Default password như changeme có thể khiến ứng dụng khởi động với tài khoản yếu. Secret production phải bắt buộc và được validate.

### Đặt secret trong command-line argument

Process list, shell history và log có thể ghi lại argument. Dùng environment variables hoặc mounted secret files.

### Nghĩ environment variable là secret manager

Environment variable chỉ là một nguồn cấu hình. Nó không tự cung cấp audit, access policy, encryption at rest hoặc rotation.

### Dùng configtree nhưng không mount file

Property bị thiếu hoặc không bind. Kiểm tra spring.config.import, path, tên file và permission. Với secret bắt buộc, không dùng optional import để che lỗi triển khai.

### Dùng Kubernetes Secret nhưng quên base64 không phải encryption

Bảo vệ etcd, RBAC và quyền mount. Cân nhắc external secret manager.

### Dùng tài khoản elastic/superuser

Credential lộ có thể cho phép quản trị cluster. Tạo user/API key riêng với quyền theo index và action tối thiểu.

### Chỉ bật TLS mà không xác minh certificate

Không dùng trust-all hoặc bỏ hostname verification. Dùng CA certificate hoặc fingerprint đáng tin cậy.

### Đưa password vào URL

URL thường được log và trace. Cấu hình authentication qua client builder/header.

### Log properties object

Record toString() có thể in toàn bộ password. Không log object chứa secret; nếu cần, log trạng thái có/không có.

### Mở Actuator env/configprops cho mọi người

Endpoint có thể tiết lộ cấu hình. Giới hạn exposure và bảo vệ quyền truy cập.

### Nghĩ secret file được cập nhật thì client tự đổi password

Spring bind properties và khởi tạo client lúc startup. Cần restart/refresh có kiểm soát hoặc triển khai cơ chế rotation thực sự.

### Xóa secret khỏi file nhưng không rotate

Secret vẫn có thể tồn tại trong Git history, artifact hoặc log. Thu hồi/rotate credential đã lộ.

## 25. Quy trình quản lý secret kết nối

Khi triển khai kết nối Spring Data Elasticsearch:

1. Liệt kê property cần thiết và phân loại giá trị nào là secret.
2. Tạo service account/API key riêng cho ứng dụng.
3. Cấp quyền tối thiểu theo index và thao tác.
4. Chọn nguồn cấp secret: environment variable, config tree hoặc secret manager.
5. Giữ secret thật ngoài source, file profile và Docker image.
6. Bind property bằng @ConfigurationProperties.
7. Validate host, username và credential bắt buộc khi startup.
8. Cấu hình ClientConfiguration với TLS và authentication.
9. Xác minh CA certificate/fingerprint từ nguồn tin cậy.
10. Không log secret, Authorization header hoặc properties object.
11. Hạn chế quyền đọc secret và chỉ mount vào workload cần dùng.
12. Kiểm thử bằng credential test riêng và không dùng production secret.
13. Theo dõi lỗi 401, 403, TLS và missing property.
14. Xây quy trình rotation có rollout, xác nhận và revoke credential cũ.
15. Khi secret bị lộ, thu hồi/rotate và điều tra nơi credential đã được sao chép.

## 26. Tổng kết

Quản lý bí mật kết nối là việc tách credential khỏi source code và artifact, cấp chúng cho ứng dụng ở runtime và kiểm soát vòng đời sử dụng. Spring Boot hỗ trợ externalized configuration qua environment variables, property placeholders, @ConfigurationProperties và configuration trees. Với secret file được mount, configtree: chuyển tên file thành property key và nội dung file thành property value; Kubernetes Secret và Docker Secret có thể sử dụng cách này.

Spring Data Elasticsearch nhận các property đã bind để xây ClientConfiguration. withBasicAuth cấu hình username/password; API key có thể được gửi qua header Authorization: ApiKey .... usingSsl với CA fingerprint hoặc SSLContext giúp xác minh TLS. Không lưu password trong URL, không dùng superuser cho ứng dụng và không tắt certificate verification.

Environment variables là kênh truyền cấu hình, không thay thế secret manager. Với môi trường production, cần kiểm soát RBAC, file permissions, encryption at rest, logging, Actuator exposure và rotation. Khi secret thay đổi, property đã bind và client đã tạo không tự động cập nhật; cần rollout/reload có kiểm soát. Nếu credential đã lộ, phải thu hồi hoặc rotate thay vì chỉ xóa khỏi file hiện tại.

## Tài liệu tham khảo

- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot – Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Data Elasticsearch – Elasticsearch Clients](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Spring Data Elasticsearch – ClientConfiguration API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/ClientConfiguration.html)
- [Elasticsearch Java API Client – Connecting](https://www.elastic.co/docs/reference/elasticsearch/clients/java/setup/connecting)
- [Elasticsearch – Authentication](https://www.elastic.co/docs/api/doc/elasticsearch/authentication)
- [Kubernetes – Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Docker – Manage sensitive data with Docker secrets](https://docs.docker.com/engine/swarm/secrets/)
- [Spring Cloud Vault](https://docs.spring.io/spring-cloud-vault/reference/)

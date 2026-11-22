# Khai báo nhiều địa chỉ và lựa chọn endpoint của cluster

## 1. Endpoint là gì trong kết nối Elasticsearch?

Ứng dụng Spring Data Elasticsearch giao tiếp với Elasticsearch thông qua một client Java. Client gửi các yêu cầu HTTP hoặc HTTPS đến endpoint của Elasticsearch, nhận phản hồi rồi chuyển dữ liệu cho các abstraction như `ElasticsearchOperations` hoặc repository.

Một endpoint thường được xác định bởi hostname và cổng HTTP:

~~~text
http://es-node-1.internal:9200
https://search.example.com:9243
~~~

Trong đó:

- `http` hoặc `https` xác định giao thức kết nối.
- `es-node-1.internal` hoặc `search.example.com` là hostname có thể phân giải và truy cập từ máy chạy ứng dụng.
- `9200` hoặc `9243` là cổng HTTP API do môi trường Elasticsearch công bố.

Cần phân biệt cổng HTTP API với cổng transport nội bộ giữa các node. Trong cấu hình mặc định phổ biến, ứng dụng dùng cổng HTTP `9200`; cổng transport thường là `9300` và dành cho giao tiếp giữa các node trong cluster. Không đưa cổng transport vào cấu hình Spring Data Elasticsearch để gọi REST API.

Một cluster có thể có nhiều node và mỗi node có thể công bố endpoint HTTP riêng. Client có thể kết nối qua một endpoint ổn định do load balancer hoặc dịch vụ hạ tầng cung cấp, hoặc được cấu hình với nhiều endpoint của các node có thể nhận yêu cầu từ ứng dụng.

## 2. Vì sao cần khai báo nhiều địa chỉ?

Nếu ứng dụng chỉ biết một node, mọi yêu cầu ban đầu đều đi qua node đó. Khi node gặp sự cố hoặc không thể truy cập, ứng dụng có thể mất khả năng tìm kiếm dù những node khác trong cluster vẫn hoạt động.

Khai báo nhiều endpoint giúp client có nhiều địa chỉ để gửi yêu cầu. Với Elasticsearch REST client, các node đã cấu hình được dùng để phân phối tải; client có cơ chế xử lý lỗi node và chuyển sang node khác theo chính sách của client.

Ví dụ một cluster có ba node có HTTP endpoint:

~~~text
es-node-1.internal:9200
es-node-2.internal:9200
es-node-3.internal:9200
~~~

Luồng khái quát:

~~~text
                         Spring Boot application
                                   |
                                   v
                         Spring Data Elasticsearch
                                   |
                                   v
                              REST client
                                   |
                    +--------------+--------------+
                    |              |              |
                    v              v              v
              es-node-1      es-node-2      es-node-3
                    \              |              /
                     \             |             /
                      +-------- Elasticsearch ---+
                                cluster
~~~

Client có thể chọn một node trong danh sách cho mỗi request. Nếu một node không thể phục vụ do lỗi kết nối, client có thể tạm đánh dấu node đó không khả dụng và thử node khác theo cơ chế failover của REST client.

Điều này cải thiện khả năng chịu lỗi ở lớp kết nối. Nó không thay thế tính sẵn sàng của cluster, replica shard, giám sát hạ tầng hoặc cơ chế xử lý lỗi nghiệp vụ của ứng dụng.

## 3. Hai cách tiếp cận: một endpoint ổn định hoặc nhiều endpoint trực tiếp

Không phải lúc nào ứng dụng cũng cần biết địa chỉ của từng node. Có hai cách triển khai thường gặp:

| Cách kết nối | Cấu hình phía ứng dụng | Phù hợp khi |
|---|---|---|
| Một endpoint qua load balancer, proxy hoặc service DNS | Một hostname và cổng ổn định | Dùng Elasticsearch được quản lý, Kubernetes Service hoặc hạ tầng đã có lớp phân phối tải |
| Nhiều endpoint node trực tiếp | Danh sách hostname và cổng của các node | Ứng dụng truy cập trực tiếp các node HTTP và cần client phân phối tải, dự phòng ở phía client |

### Một endpoint qua load balancer hoặc service DNS

Ví dụ:

~~~text
search.internal.example:9200
~~~

Load balancer hoặc dịch vụ mạng đứng trước cluster và chuyển request đến node phù hợp. Ứng dụng chỉ cần cấu hình endpoint ổn định đó.

Cách này giảm sự phụ thuộc của ứng dụng vào danh sách node cụ thể. Khi node được thay thế hoặc địa chỉ IP thay đổi, hạ tầng có thể cập nhật phía sau endpoint mà không cần sửa cấu hình ứng dụng.

Trong Kubernetes, hostname của một Service thường là endpoint phù hợp hơn IP Pod riêng lẻ vì Service cung cấp địa chỉ ổn định và quản lý các backend.

### Nhiều endpoint node trực tiếp

Ví dụ:

~~~text
es-node-1.internal:9200
es-node-2.internal:9200
es-node-3.internal:9200
~~~

Cách này cho phép REST client lựa chọn giữa các node đã khai báo. Tất cả địa chỉ phải thuộc cùng một cluster, có thể truy cập từ ứng dụng và được cấu hình giao thức, xác thực tương thích.

Không nên trộn endpoint của hai cluster độc lập trong cùng một danh sách. Client có thể gửi các request liên tiếp đến hai cluster khác nhau, dẫn đến kết quả tìm kiếm, trạng thái index hoặc thao tác ghi không nhất quán.

## 4. Khai báo nhiều endpoint bằng ClientConfiguration

Spring Data Elasticsearch cung cấp `ClientConfiguration` để mô tả địa chỉ và các tùy chọn kết nối. Phương thức `connectedTo` nhận nhiều chuỗi `host:port`.

Ví dụ cấu hình cho ứng dụng dùng Spring Data Elasticsearch với `Rest5Client`:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ElasticsearchClientConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo(
                "es-node-1.internal:9200",
                "es-node-2.internal:9200",
                "es-node-3.internal:9200"
            )
            .withConnectTimeout(Duration.ofSeconds(3))
            .withSocketTimeout(Duration.ofSeconds(20))
            .build();
    }
}
~~~

Ý nghĩa các phần:

- `@Configuration` đăng ký lớp cấu hình Spring.
- `ElasticsearchConfiguration` cung cấp cấu hình client imperative của Spring Data Elasticsearch hiện đại.
- `clientConfiguration()` trả về mô tả kết nối được dùng để tạo Elasticsearch client.
- `connectedTo(...)` khai báo danh sách endpoint của cluster.
- `withConnectTimeout(...)` giới hạn thời gian thiết lập kết nối.
- `withSocketTimeout(...)` giới hạn thời gian chờ dữ liệu trên kết nối theo cấu hình client.

Khi cấu hình hoàn tất, ứng dụng có thể tiêm `ElasticsearchOperations`, `ElasticsearchClient` hoặc repository vào service. Các abstraction này dùng client đã được cấu hình; không cần tự tạo một client mới cho từng repository.

Ví dụ service sử dụng operations:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    // Các phương thức tìm kiếm sử dụng operations
}
~~~

Nên để Spring quản lý vòng đời của client dưới dạng bean dùng chung. REST client là thành phần có thể được chia sẻ giữa các request và có tài nguyên mạng, connection pool, thread nội bộ cần được đóng đúng lúc. Tránh tạo rồi bỏ một client mới mỗi lần gọi repository hoặc mỗi request HTTP của người dùng.

## 5. Cấu hình endpoint từ môi trường

Địa chỉ cluster thay đổi theo môi trường triển khai. Máy phát triển có thể dùng `localhost`, môi trường kiểm thử dùng service nội bộ, còn production dùng DNS hoặc endpoint do nền tảng cung cấp.

Không nên cố định địa chỉ production trực tiếp trong mã nguồn. Có thể đặt danh sách endpoint trong cấu hình bên ngoài:

~~~properties
app.elasticsearch.endpoints=es-node-1.internal:9200,es-node-2.internal:9200,es-node-3.internal:9200
~~~

Sau đó đọc danh sách và truyền vào `connectedTo`:

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ElasticsearchClientConfig extends ElasticsearchConfiguration {

    private final String[] endpoints;

    public ElasticsearchClientConfig(
            @Value("${app.elasticsearch.endpoints}") String endpointList) {
        this.endpoints = endpointList.split("\\s*,\\s*");
    }

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo(endpoints)
            .withConnectTimeout(Duration.ofSeconds(3))
            .withSocketTimeout(Duration.ofSeconds(20))
            .build();
    }
}
~~~

Với Spring Boot, giá trị này có thể được ghi đè bằng biến môi trường theo quy ước ánh xạ cấu hình, ví dụ `APP_ELASTICSEARCH_ENDPOINTS`. Hãy cung cấp giá trị riêng cho từng môi trường và kiểm tra rằng mỗi hostname phân giải được từ container hoặc máy ảo đang chạy ứng dụng.

Nếu endpoint được cung cấp dưới dạng URL đầy đủ, cần tách hostname, cổng và giao thức theo đúng API cấu hình của phiên bản đang sử dụng. `connectedTo` trong ví dụ nhận chuỗi `host:port`, còn giao thức HTTPS được bật bằng tùy chọn SSL riêng.

## 6. Kết nối HTTPS, xác thực và proxy

Khi Elasticsearch yêu cầu TLS, cần bật SSL trong cấu hình client. Ví dụ:

~~~java
return ClientConfiguration.builder()
    .connectedTo(
        "es-node-1.internal:9200",
        "es-node-2.internal:9200"
    )
    .usingSsl()
    .withConnectTimeout(Duration.ofSeconds(3))
    .withSocketTimeout(Duration.ofSeconds(20))
    .build();
~~~

Nếu môi trường dùng chứng chỉ CA riêng hoặc Elasticsearch cấp fingerprint, hãy cấu hình xác minh chứng chỉ theo hướng dẫn của phiên bản Spring Data Elasticsearch và Elasticsearch client tương ứng. Không tắt xác minh TLS chỉ để làm cho kết nối hoạt động.

Có thể khai báo xác thực Basic Auth:

~~~java
return ClientConfiguration.builder()
    .connectedTo("search.internal.example:9200")
    .usingSsl()
    .withBasicAuth(username, password)
    .build();
~~~

`username` và `password` cần được lấy từ secret manager, biến môi trường hoặc cơ chế quản lý bí mật phù hợp. Không ghi thông tin đăng nhập thật vào repository hoặc file cấu hình được commit.

Nếu cluster được đặt sau reverse proxy, có thể cần cấu hình proxy hoặc path prefix:

~~~java
return ClientConfiguration.builder()
    .connectedTo("gateway.internal.example:443")
    .usingSsl()
    .withPathPrefix("elasticsearch")
    .withProxy("proxy.internal.example:8080")
    .build();
~~~

Chỉ cấu hình `withPathPrefix` khi proxy thực sự yêu cầu đường dẫn đó. Cần xác nhận proxy chuyển tiếp đầy đủ các API Elasticsearch và không làm sai lệch request/response.

Các tùy chọn SSL, xác thực, timeout, header và proxy áp dụng cho client được tạo từ `ClientConfiguration`. Khi dùng nhiều endpoint trực tiếp, hãy bảo đảm các endpoint đều hỗ trợ cùng cơ chế kết nối và thông tin xác thực.

## 7. Client lựa chọn node như thế nào?

Với REST client, danh sách node là tập địa chỉ có thể gửi request. REST 5 Client phân phối request giữa các node khả dụng theo cơ chế load balancing; tài liệu client mô tả việc lựa chọn lần lượt theo round-robin. Khi có lỗi node, client có thể thực hiện failover và tạm phạt node gặp lỗi trước khi thử lại.

Ví dụ minh họa round-robin với ba node:

~~~text
Request 1 -> es-node-1
Request 2 -> es-node-2
Request 3 -> es-node-3
Request 4 -> es-node-1
Request 5 -> es-node-2
...
~~~

Đây là mô hình minh họa. Lưu lượng thực tế có thể không chia đều tuyệt đối vì request có thời gian xử lý khác nhau, node có tải khác nhau và cơ chế xử lý node lỗi có thể thay đổi thứ tự lựa chọn.

Load balancing ở client chọn node HTTP nhận request. Sau đó Elasticsearch tự định tuyến thao tác đến shard và node chứa dữ liệu liên quan. Vì vậy, node nhận HTTP request không nhất thiết là node lưu shard của tài liệu được truy vấn.

### Khi một endpoint bị lỗi

Giả sử ba endpoint đã được khai báo nhưng `es-node-2` mất kết nối:

~~~text
Request
   |
   v
REST client
   |
   +---- es-node-1: hoạt động
   |
   +---- es-node-2: lỗi kết nối
   |
   +---- es-node-3: hoạt động
~~~

REST client có thể đánh dấu node lỗi là tạm thời không khả dụng và thử node còn lại theo chính sách retry/failover của phiên bản client. Sau một khoảng thời gian, node có thể được kiểm tra lại để đưa trở lại danh sách phục vụ.

Cơ chế này xử lý lỗi ở lớp kết nối. Nó không có nghĩa mọi lỗi HTTP hoặc mọi lỗi nghiệp vụ đều được thử lại an toàn. Ví dụ, lỗi xác thực, request sai cú pháp hoặc xung đột dữ liệu cần được xử lý theo nguyên nhân thực tế. Với thao tác ghi, không nên tự giả định rằng retry luôn an toàn hoặc request chỉ được thực thi đúng một lần.

## 8. Lựa chọn node bằng NodeSelector

Trong một số cluster, không phải node nào cũng nên nhận request từ ứng dụng. Ví dụ, cluster có dedicated master node chỉ tập trung quản lý trạng thái cluster; ứng dụng thường nên gửi truy vấn đến node có vai trò phù hợp với lưu lượng HTTP, chẳng hạn coordinating node hoặc data node.

Elasticsearch REST client hỗ trợ `NodeSelector` để lọc tập node được phép nhận request. Spring Data Elasticsearch cho phép tùy chỉnh low-level client qua `withClientConfigurer`.

Ví dụ với Spring Data Elasticsearch 6 và `Rest5Client`:

Đoạn cấu hình sau chỉ phù hợp khi client đã có metadata node, chẳng hạn được cập nhật qua sniffing. Nếu ứng dụng chỉ khai báo các endpoint tĩnh và không khám phá node, hãy bỏ selector này để client sử dụng toàn bộ endpoint đã cấu hình.

~~~java
import co.elastic.clients.transport.rest5_client.low_level.NodeSelector;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;
import org.springframework.data.elasticsearch.client.elc.rest5_client.Rest5Clients;

import org.springframework.context.annotation.Configuration;

@Configuration
public class ElasticsearchClientConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo(
                "es-node-1.internal:9200",
                "es-node-2.internal:9200",
                "es-node-3.internal:9200"
            )
            .withClientConfigurer(
                Rest5Clients.ElasticsearchRest5ClientConfigurationCallback.from(
                    restClientBuilder -> {
                        restClientBuilder.setNodeSelector(
                            NodeSelector.SKIP_DEDICATED_MASTERS
                        );
                        return restClientBuilder;
                    }
                )
            )
            .build();
    }
}
~~~

`NodeSelector.SKIP_DEDICATED_MASTERS` là selector có sẵn để tránh gửi request đến các node chỉ có vai trò master chuyên dụng. Nó cần metadata và role của các node, thường được cung cấp khi sử dụng cơ chế khám phá node (sniffing). Nếu không có metadata đó, không bật selector này cho danh sách endpoint tĩnh.

Cần hiểu giới hạn của selector:

- `connectedTo(...)` xác định các endpoint ban đầu mà client biết.
- `NodeSelector` lọc các node ứng viên dựa trên thông tin node mà client có.
- Selector không tự biến một địa chỉ thành địa chỉ khác và cũng không chọn một cluster khác.
- Nếu client không có metadata cần thiết, selector dựa trên role có thể không lọc được node như mong muốn.
- Không nên cấu hình selector khiến toàn bộ node đều bị loại, vì khi đó client không còn node phù hợp để gửi request.

Với cluster chỉ có một hoặc một vài endpoint ổn định do load balancer cung cấp, thường không cần NodeSelector. Việc phân phối và chọn backend đã thuộc trách nhiệm của load balancer.

## 9. Khám phá node động (sniffing)

Danh sách endpoint khai báo bằng `connectedTo` là điểm khởi đầu để client kết nối. Trong một số môi trường, node có thể được thêm, xóa hoặc thay thế thường xuyên. Nếu muốn client tự cập nhật danh sách node từ cluster, có thể dùng cơ chế sniffing được Elasticsearch REST client hỗ trợ.

Sniffer định kỳ gọi API thông tin node để lấy danh sách node mà cluster công bố, sau đó cập nhật danh sách node của client. Một số triển khai cũng có thể kích hoạt cập nhật khi node gặp lỗi.

Với Spring Data Elasticsearch 6, có thể đăng ký Sniffer như một bean phụ thuộc vào low-level `Rest5Client`:

~~~java
import co.elastic.clients.transport.rest5_client.low_level.Rest5Client;
import co.elastic.clients.transport.rest5_client.low_level.sniffer.Sniffer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ElasticsearchSnifferConfig {

    @Bean(destroyMethod = "close")
    Sniffer elasticsearchSniffer(Rest5Client rest5Client) {
        return Sniffer.builder(rest5Client).build();
    }
}
~~~

Đảm bảo dependency Sniffer tương ứng có trong classpath. Bean được đóng khi Spring dừng ứng dụng; Sniffer cần được đóng trước REST client để giải phóng thread nền và tài nguyên.

Luồng khái quát:

~~~text
REST client
    |
    +---- gửi request đến node đã biết
    |
    +---- Sniffer gọi Nodes Info API theo chu kỳ
                |
                v
          Elasticsearch cluster
                |
                v
        Danh sách node công bố
                |
                v
        Cập nhật node cho client
~~~

Sniffing hữu ích khi ứng dụng có thể truy cập trực tiếp các địa chỉ HTTP mà cluster công bố. Tuy nhiên, nó có thể gây lỗi trong môi trường mạng có NAT, container hoặc proxy nếu các địa chỉ được Elasticsearch công bố không thể truy cập từ ứng dụng.

REST5 Sniffer mặc định giả định các node dùng HTTP. Nếu cluster dùng HTTPS, cần cấu hình `ElasticsearchNodesSniffer` với scheme `HTTPS` theo API của phiên bản client đang dùng; nếu không, lần khám phá node có thể tạo endpoint sai giao thức.

Ví dụ, ứng dụng truy cập cluster qua một load balancer công khai, nhưng API Nodes Info trả về địa chỉ nội bộ chỉ có thể truy cập từ mạng khác. Nếu client chuyển sang những địa chỉ này, request sẽ thất bại dù endpoint load balancer ban đầu vẫn hoạt động.

Vì vậy:

- Dùng endpoint qua load balancer hoặc Service DNS khi hạ tầng đã chịu trách nhiệm chọn backend và công bố địa chỉ ổn định.
- Cân nhắc sniffing khi ứng dụng được phép kết nối trực tiếp tới các node và địa chỉ node công bố có thể truy cập từ cùng mạng.
- Không bật sniffing một cách mặc định cho mọi môi trường.
- Nếu bật sniffing, kiểm tra chu kỳ cập nhật, vòng đời đóng Sniffer và việc cập nhật node khi cluster thay đổi.
- Chỉ kết hợp selector dựa trên role/attribute khi metadata của node có sẵn và đã kiểm tra kết quả.

Sniffing là cơ chế khám phá node, khác với round-robin. Round-robin lựa chọn trong danh sách node hiện có; sniffing cập nhật danh sách đó.

## 10. Chọn endpoint phù hợp với từng kiểu cluster

| Kiểu môi trường | Cách cấu hình thường phù hợp | Lý do |
|---|---|---|
| Elasticsearch chạy local một node | `localhost:9200` | Cấu hình đơn giản cho phát triển |
| Cluster tự quản lý, node có DNS ổn định | Nhiều endpoint HTTP của node phù hợp | Client có thể phân phối tải và dự phòng |
| Kubernetes | DNS của Service Elasticsearch | Service giữ endpoint ổn định khi Pod thay đổi |
| Elasticsearch được quản lý hoặc cloud | Endpoint HTTPS do nhà cung cấp cấp | Nhà cung cấp quản lý topology và cân bằng tải |
| Cluster sau reverse proxy | Hostname proxy cùng path prefix nếu cần | Ứng dụng không phải biết địa chỉ node phía sau |
| Mạng riêng có node IP thay đổi | Service discovery hoặc load balancer | Tránh giữ danh sách IP tĩnh dễ lỗi |

Khi chọn endpoint, cần xác minh:

1. Endpoint có phân giải DNS và truy cập được từ đúng nơi chạy ứng dụng.
2. Cổng đó là cổng HTTP/HTTPS API, không phải cổng transport nội bộ.
3. Tất cả endpoint trong danh sách thuộc cùng cluster.
4. Node nhận request có vai trò và tài nguyên phù hợp với workload.
5. TLS, chứng chỉ, xác thực và quyền truy cập index đều tương thích.
6. Firewall, security group và network policy cho phép kết nối.
7. Địa chỉ node mà sniffing công bố có thể truy cập nếu sử dụng khám phá động.

## 11. Kiểm tra endpoint và tình trạng cluster

Trước khi điều tra Spring Data, hãy kiểm tra endpoint từ chính máy hoặc container chạy ứng dụng. Có thể dùng `curl`:

~~~bash
curl -k https://es-node-1.internal:9200/
~~~

Trong môi trường production, cần cấu hình CA/chứng chỉ đúng và bỏ `-k`; tùy chọn `-k` chỉ nên được dùng như một phép thử tạm thời trong môi trường kiểm soát vì nó bỏ qua xác minh chứng chỉ.

Kiểm tra sức khỏe cluster:

~~~http
GET /_cluster/health
~~~

Kiểm tra các node và địa chỉ HTTP được công bố:

~~~http
GET /_nodes/http
~~~

Có thể xem các thông tin:

- Tên node và vai trò node.
- Địa chỉ HTTP publish address.
- Cluster health và trạng thái shard.
- Node nào được công bố cho client sử dụng.

Nếu một endpoint trong danh sách không kết nối được, cần xác định đó là lỗi DNS, route mạng, firewall, TLS, xác thực hay dịch vụ Elasticsearch. Thêm nhiều địa chỉ không khắc phục được lỗi cấu hình mạng hoặc chứng chỉ dùng chung.

Khi ứng dụng khởi động nhưng request thất bại, hãy kiểm tra log của client để tìm hostname, cổng, thời gian timeout và nguyên nhân gốc. Có thể bật log phù hợp của tầng HTTP/client trong môi trường kiểm thử để xem request được gửi đến node nào. Không nên bật trace toàn bộ request/response chứa dữ liệu nhạy cảm trong production mà không có chính sách bảo vệ log.

## 12. Những lỗi thường gặp khi khai báo nhiều địa chỉ

**Dùng sai cổng.** Cấu hình `9300` theo thói quen từ giao tiếp node-to-node khiến HTTP client không kết nối được. Hãy dùng cổng HTTP API mà cluster công bố.

**Khai báo hostname chỉ máy chủ ứng dụng mới phân giải được.** Một địa chỉ hoạt động trên laptop có thể không hoạt động trong container production. Kiểm tra DNS và route từ đúng runtime.

**Trộn nhiều cluster vào một danh sách.** Mỗi endpoint trong `connectedTo` phải đại diện cho cùng cluster và cùng môi trường dữ liệu. Không dùng danh sách endpoint để tạo kết nối luân phiên đến các cluster độc lập.

**Tưởng rằng thêm endpoint tự tạo cluster HA.** Khả năng chịu lỗi còn phụ thuộc vào cluster, shard replica, quorum, tải, network và chính sách retry. Client chỉ có thể lựa chọn các endpoint mà nó có thể truy cập.

**Cấu hình sniffing sau load balancer mà không kiểm tra địa chỉ publish.** Client có thể nhận các IP nội bộ không thể truy cập. Chọn một endpoint ổn định qua load balancer hoặc cấu hình mạng để các địa chỉ được công bố có thể truy cập.

**Dùng NodeSelector khi thiếu metadata.** Selector dựa trên role hoặc attribute cần thông tin node tương ứng. Hãy xác nhận client biết các role/attribute trước khi áp dụng selector.

**Tạo client cho từng request.** Điều này gây lãng phí connection pool và thread, đồng thời làm tăng số kết nối tới cluster. Dùng bean singleton do Spring quản lý.

**Retry mọi lỗi.** Không phải lỗi nào cũng có thể khắc phục bằng cách chuyển node. Lỗi 401/403, mapping, query hoặc xung đột dữ liệu cần xử lý đúng nguyên nhân. Retry thao tác ghi cũng cần xem xét khả năng lặp và tính idempotent.

**Đưa mật khẩu hoặc địa chỉ nhạy cảm vào Git.** Dùng secret manager hoặc biến môi trường và giới hạn quyền truy cập endpoint theo mạng, tài khoản và index.

## 13. Quy trình cấu hình trong dự án Spring Data Elasticsearch

Có thể thực hiện theo trình tự sau:

1. Xác định topology cluster: một node, nhiều node trực tiếp hay endpoint qua load balancer/Service.
2. Chọn endpoint HTTP/HTTPS có thể truy cập từ ứng dụng.
3. Xác nhận các endpoint thuộc cùng cluster và hỗ trợ cùng cơ chế bảo mật.
4. Đưa danh sách endpoint, timeout và thông tin kết nối vào cấu hình theo môi trường.
5. Tạo một `ClientConfiguration` và cấu hình client bean theo phiên bản Spring Data Elasticsearch đang dùng.
6. Chỉ thêm `NodeSelector` khi có yêu cầu lựa chọn theo role/attribute và client có metadata tương ứng.
7. Chỉ bật sniffing khi các địa chỉ node được công bố có thể truy cập từ ứng dụng.
8. Kiểm tra kết nối, cluster health, log failover và khả năng phục hồi khi một endpoint tạm thời không khả dụng.

## 14. Khác biệt phiên bản client cần lưu ý

API tích hợp Elasticsearch client thay đổi theo thế hệ Elasticsearch và Spring Data Elasticsearch. Ví dụ:

- Spring Data Elasticsearch 6.0 trở lên sử dụng `Rest5Client` của Elasticsearch 9 trong cấu hình imperative mặc định.
- Các phiên bản trước đó sử dụng low-level `RestClient` (legacy) cùng Elasticsearch Java API Client.
- Tên lớp callback, package và loại client được tùy chỉnh có thể khác nhau giữa `Rest5Client` và `RestClient` legacy.

Với Spring Data Elasticsearch 6, callback cấu hình low-level `Rest5Client` có dạng:

~~~java
.withClientConfigurer(
    Rest5Clients.ElasticsearchRest5ClientConfigurationCallback.from(
        restClientBuilder -> {
            // Tùy chỉnh Rest5ClientBuilder tại đây
            return restClientBuilder;
        }
    )
)
~~~

Với phiên bản sử dụng legacy `RestClient`, Spring Data cung cấp callback tương ứng trong `RestClients`. Không sao chép nguyên package callback của phiên bản mới vào dự án cũ. Hãy kiểm tra dependency thực tế và tài liệu đúng phiên bản trước khi triển khai.

## Kết luận

Khai báo nhiều endpoint giúp Spring Data Elasticsearch có nhiều node để gửi request, phân phối tải và dự phòng khi một node gặp lỗi. `ClientConfiguration.connectedTo(...)` là điểm cấu hình chính cho danh sách địa chỉ; các tùy chọn SSL, xác thực, timeout, proxy và callback cho phép điều chỉnh client theo môi trường triển khai.

Việc chọn endpoint cần dựa trên topology thực tế: dùng địa chỉ ổn định qua load balancer hoặc Service khi hạ tầng quản lý backend, hoặc khai báo nhiều node trực tiếp khi ứng dụng có thể truy cập từng node. NodeSelector hỗ trợ lọc node theo metadata; sniffing hỗ trợ cập nhật danh sách node. Cả hai cần được dùng đúng điều kiện mạng và phiên bản client.

Thiết kế kết nối tốt bắt đầu từ endpoint có thể truy cập, cùng một cluster, đúng cổng HTTP API và cơ chế bảo mật hợp lệ. Sau đó mới cấu hình phân phối tải, failover và khám phá node để ứng dụng Spring Data Elasticsearch có thể giao tiếp ổn định với cluster.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Elasticsearch Clients](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Elasticsearch Java REST 5 Client](https://www.elastic.co/docs/reference/elasticsearch/clients/java/transport/rest5-client)
- [Elasticsearch REST 5 Client — Node Selector](https://www.elastic.co/docs/reference/elasticsearch/clients/java/transport/rest5-client/config/node_selector)
- [Elasticsearch REST 5 Client — Sniffer](https://www.elastic.co/docs/reference/elasticsearch/clients/java/transport/rest5-client/sniffer)

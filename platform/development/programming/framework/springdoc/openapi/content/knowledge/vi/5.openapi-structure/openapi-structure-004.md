# Servers và biến cấu hình trong URL máy chủ

Trong OpenAPI, trường **servers** mô tả địa chỉ gốc mà client dùng để gọi các operation của API. Một server có thể là URL đầy đủ như `https://api.example.com/v1`, URL tương đối như `/gateway/orders`, hoặc URL mẫu chứa biến như `https://{tenant}.api.example.com/{basePath}`.

Khi đọc tài liệu do springdoc-openapi sinh ra, cần hiểu server URL được ghép với path như thế nào, biến trong URL được thay bằng giá trị nào và phạm vi áp dụng của từng khai báo. Đây là phần quan trọng khi API chạy qua nhiều môi trường, nhiều tenant, gateway hoặc reverse proxy.

## 1. Servers mô tả địa chỉ gốc của API

Trong tài liệu OpenAPI, `servers` là một mảng các đối tượng Server Object. Mỗi đối tượng mô tả một địa chỉ gốc mà client có thể dùng để gửi request. Ví dụ:

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Order API",
    "version": "v1"
  },
  "servers": [
    {
      "url": "https://api.example.com/v1",
      "description": "Production API"
    },
    {
      "url": "https://staging-api.example.com/v1",
      "description": "Staging API"
    }
  ],
  "paths": {
    "/orders": {
      "get": {
        "responses": {
          "200": {
            "description": "Danh sách đơn hàng"
          }
        }
      }
    }
  }
}
```

Với operation `GET /orders`, hai địa chỉ request có thể được tạo từ hai server ở trên là:

```text
https://api.example.com/v1/orders
https://staging-api.example.com/v1/orders
```

Server URL cung cấp phần địa chỉ nền; path trong `paths` cung cấp phần đường dẫn của operation. Client kết hợp chúng để tạo URL request hoàn chỉnh.

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Server URL | `https://api.example.com/v1` | Scheme, host, port nếu có và base path |
| Path | `/orders/{id}` | Đường dẫn của operation |
| Query parameter | `?status=PAID` | Giá trị truy vấn của request |
| URL hoàn chỉnh | `https://api.example.com/v1/orders/42?status=PAID` | Địa chỉ request được gửi đi |

`servers` chỉ mô tả URL trong hợp đồng API. Nó không mở cổng mạng, cấu hình DNS, cấp chứng chỉ TLS hay thay đổi địa chỉ mà Spring Boot thực sự bind để lắng nghe request.

## 2. Các dạng Server URL

OpenAPI cho phép khai báo URL tuyệt đối hoặc tương đối.

**URL tuyệt đối** chứa scheme và host:

```yaml
servers:
  - url: https://api.example.com/v1
    description: Production
  - url: https://staging-api.example.com/v1
    description: Staging
```

**URL tương đối** được phân giải dựa trên vị trí tài liệu OpenAPI hoặc ngữ cảnh triển khai:

```yaml
servers:
  - url: /api/v1
    description: API cùng origin với tài liệu
```

URL tương đối hữu ích khi tài liệu và API được phục vụ cùng domain, nhưng được đặt sau các context path hoặc reverse proxy khác nhau. Cần kiểm tra cách công cụ client phân giải URL trong môi trường thực tế.

Server URL có thể chứa scheme, host, port và base path. Ví dụ:

```text
https://api.example.com:8443/platform/orders
```

Trong đó:

- `https` là scheme.
- `api.example.com` là hostname.
- `8443` là port.
- `/platform/orders` là phần path nền của server.

Khi path item trong OpenAPI là `/customers`, URL cuối cùng sẽ nối server URL với path item thành `https://api.example.com:8443/platform/orders/customers`. Tránh khai báo cùng một đoạn path ở cả server URL và path item nếu không muốn URL bị lặp.

## 3. Cấu trúc Server Object

Một Server Object có trường `url` bắt buộc và có thể có `description` cùng `variables`.

```yaml
servers:
  - url: https://api.example.com/v1
    description: Public API
```

| Trường | Bắt buộc | Ý nghĩa |
|---|---:|---|
| `url` | Có | URL tuyệt đối hoặc tương đối của server; có thể chứa biến mẫu |
| `description` | Không | Mô tả ngắn về môi trường hoặc mục đích của server |
| `variables` | Không | Tập Server Variable Object dùng để thay thế placeholder trong URL |

Tên biến trong `variables` phải khớp với tên placeholder đặt trong cặp ngoặc nhọn ở `url`. Ví dụ, `{region}` cần một biến tên `region`.

```yaml
servers:
  - url: https://{region}.api.example.com/v1
    description: API theo khu vực
    variables:
      region:
        default: ap-southeast
        description: Khu vực triển khai
        enum:
          - ap-southeast
          - eu-central
          - us-east
```

Nếu server URL có placeholder nhưng không khai báo biến tương ứng, tài liệu không có đủ thông tin để client thay thế URL một cách xác định. Hãy kiểm tra tên biến, chữ hoa/chữ thường và giá trị mặc định.

## 4. Biến trong Server URL

Biến server cho phép một URL mẫu đại diện cho nhiều địa chỉ. Cú pháp placeholder là `{variableName}`.

Ví dụ:

```yaml
servers:
  - url: https://{tenant}.api.example.com/{basePath}
    description: API theo tenant
    variables:
      tenant:
        default: demo
        description: Mã tenant
        enum:
          - demo
          - acme
          - globex
      basePath:
        default: v1
        description: Phiên bản đường dẫn API
        enum:
          - v1
          - v2
```

Với cấu hình này, giá trị mặc định tạo ra URL:

```text
https://demo.api.example.com/v1
```

Nếu người dùng chọn `tenant=acme` và `basePath=v2`, URL được thay thành:

```text
https://acme.api.example.com/v2
```

Server variables thường hữu ích cho:

- Tenant hoặc khách hàng khi mỗi tenant có hostname riêng.
- Khu vực triển khai như `ap-southeast`, `eu-central` hoặc `us-east`.
- Phiên bản base path như `v1` và `v2`.
- Port hoặc segment cố định có một số giá trị được hỗ trợ.
- Các môi trường thử nghiệm khi URL chỉ khác một phần.

Không nên dùng server variable để biểu diễn mọi dữ liệu đầu vào của request. Path parameter, query parameter và header parameter vẫn là các khái niệm riêng, có vị trí và ý nghĩa riêng trong OpenAPI.

## 5. Default và enum của Server Variable

Mỗi Server Variable Object phải có trường `default`. Đây là giá trị được dùng khi client không chọn một giá trị khác. Trường `enum` là tùy chọn; nếu được khai báo, nó giới hạn tập giá trị được hỗ trợ.

```yaml
servers:
  - url: https://{environment}.example.com/api/{version}
    variables:
      environment:
        default: sandbox
        enum:
          - sandbox
          - staging
          - production
      version:
        default: v1
        enum:
          - v1
          - v2
```

Các quy tắc cần nhớ:

1. Placeholder trong URL phải có biến cùng tên trong `variables`.
2. Mỗi biến phải khai báo `default`.
3. Nếu có `enum`, giá trị `default` phải nằm trong danh sách đó.
4. Các giá trị biến là chuỗi và được thay vào URL theo đúng vị trí placeholder.
5. `description` giúp người đọc hiểu mục đích và các giá trị của biến.

Ví dụ sau không hợp lệ về mặt ý nghĩa vì giá trị mặc định không nằm trong enum:

```yaml
variables:
  environment:
    default: production
    enum:
      - sandbox
      - staging
```

Hãy sửa bằng cách thêm `production` vào enum hoặc chọn một giá trị mặc định có trong danh sách.

Nếu không cần giới hạn giá trị, có thể bỏ `enum`:

```yaml
variables:
  tenant:
    default: demo
    description: Tenant mặc định để thử nghiệm
```

Khi bỏ enum, tài liệu không đưa ra danh sách lựa chọn cố định. Điều đó không có nghĩa mọi giá trị đều tồn tại trên hệ thống; backend vẫn cần xác thực tenant hoặc region thực tế.

## 6. Khai báo servers bằng annotation springdoc

Với springdoc-openapi, có thể mô tả server ở cấp tài liệu bằng annotation `@OpenAPIDefinition`, `@Server` và `@ServerVariable` của swagger-annotations.

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import io.swagger.v3.oas.annotations.servers.ServerVariable;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://{tenant}.api.example.com/{basePath}",
            description = "API theo tenant",
            variables = {
                @ServerVariable(
                    name = "tenant",
                    defaultValue = "demo",
                    allowableValues = {"demo", "acme", "globex"},
                    description = "Mã tenant"
                ),
                @ServerVariable(
                    name = "basePath",
                    defaultValue = "v1",
                    allowableValues = {"v1", "v2"},
                    description = "Phiên bản API"
                )
            }
        )
    }
)
class OpenApiServerConfiguration {
}
```

Trong annotation Java:

- `@Server(url = ...)` khai báo URL mẫu.
- `variables` khai báo các biến được dùng trong URL.
- `@ServerVariable(name = ...)` phải trùng với placeholder.
- `defaultValue` tương ứng với trường `default` trong OpenAPI.
- `allowableValues` cung cấp tập giá trị cho phép, tương ứng với `enum`.
- `description` giải thích ý nghĩa của server hoặc biến.

Sau khi khởi động ứng dụng, gọi `/v3/api-docs` và kiểm tra phần `servers` trong JSON. Không chỉ dựa vào việc Swagger UI có hiển thị dropdown; cần xác minh JSON có URL, default và enum đúng như cấu hình.

## 7. Khai báo servers bằng OpenAPI model bean

Annotation phù hợp khi danh sách server cố định trong mã nguồn. Nếu URL phụ thuộc cấu hình môi trường, có thể tạo OpenAPI model bean và lấy giá trị từ Spring configuration.

Ví dụ:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI orderOpenAPI(
        @Value("${app.openapi.server-url:/}") String serverUrl
    ) {
        return new OpenAPI()
            .info(new Info()
                .title("Order API")
                .version("v1"))
            .servers(List.of(
                new Server()
                    .url(serverUrl)
                    .description("Server của môi trường hiện tại")
            ));
    }
}
```

Cấu hình môi trường phát triển:

```yaml
app:
  openapi:
    server-url: http://localhost:8080
```

Cấu hình môi trường production:

```yaml
app:
  openapi:
    server-url: https://api.example.com
```

Cách này cho phép cùng một bản build tạo tài liệu với URL khác nhau tùy cấu hình được nạp khi chạy. Hãy thống nhất một nguồn cấu hình cho metadata OpenAPI; tránh khai báo chồng chéo annotation và bean nếu chưa xác định cách các cấu hình được hợp nhất trong phiên bản springdoc đang dùng.

Nếu muốn một tài liệu dùng nhiều server cố định, có thể đưa nhiều đối tượng `Server` vào danh sách. Nếu muốn URL được quyết định theo request hoặc proxy, hãy kiểm tra cơ chế tạo base URL mặc định của springdoc và cấu hình forwarded headers trước khi tự ghi đè.

## 8. Phạm vi áp dụng: cấp tài liệu, path và operation

OpenAPI cho phép khai báo `servers` ở ba phạm vi:

- Cấp tài liệu (root): áp dụng mặc định cho toàn bộ API.
- Cấp path item: áp dụng cho các operation thuộc path đó.
- Cấp operation: áp dụng riêng cho một operation.

Ví dụ root-level server:

```yaml
servers:
  - url: https://api.example.com/v1

paths:
  /orders:
    get:
      responses:
        "200":
          description: Danh sách đơn hàng
```

Một path có thể khai báo server riêng:

```yaml
paths:
  /internal/reports:
    servers:
      - url: https://internal.example.com/reporting
    get:
      responses:
        "200":
          description: Báo cáo nội bộ
```

Một operation cũng có thể khai báo server riêng:

```yaml
paths:
  /health:
    get:
      servers:
        - url: https://status.example.com
      responses:
        "200":
          description: Trạng thái dịch vụ
```

Khi server được khai báo ở phạm vi cụ thể hơn, nó thay thế danh sách server của phạm vi rộng hơn cho path hoặc operation tương ứng. Điều này hữu ích khi API công khai và API nội bộ có host khác nhau. Hãy tránh đặt server riêng nếu không cần, vì người đọc tài liệu có thể khó nhận ra operation đang dùng host khác với phần còn lại.

Với annotation, có thể khai báo server tại `@OpenAPIDefinition` ở cấp tài liệu hoặc trong annotation `@Operation` cho operation. Khi cần cấu hình ở cấp path item, hãy sử dụng mô hình OpenAPI phù hợp hoặc customizer của springdoc để đảm bảo vị trí server được sinh đúng.

## 9. Phân biệt Server Variable với Path Parameter

Hai khái niệm này đều có placeholder trong dấu ngoặc nhọn nhưng phục vụ mục đích khác nhau.

| Tiêu chí | Server Variable | Path Parameter |
|---|---|---|
| Vị trí | Trong Server URL | Trong path của operation |
| Ví dụ | `https://{tenant}.example.com/v1` | `/orders/{orderId}` |
| Khai báo | `servers[].variables` | `paths[path][method].parameters` hoặc tham số dùng chung |
| Mục đích | Chọn địa chỉ server hoặc base URL | Truyền dữ liệu định danh cho request |
| Giá trị mặc định | Bắt buộc trong Server Variable Object | Không phải yêu cầu chung của path parameter |
| Phạm vi | Có thể ảnh hưởng nhiều operation | Gắn với một operation hoặc path |

Ví dụ kết hợp:

```yaml
servers:
  - url: https://{tenant}.api.example.com/{basePath}
    variables:
      tenant:
        default: acme
      basePath:
        default: v1

paths:
  /orders/{orderId}:
    get:
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
        - name: includeItems
          in: query
          required: false
          schema:
            type: boolean
      responses:
        "200":
          description: Chi tiết đơn hàng
```

Nếu client chọn `tenant=acme`, `basePath=v1`, `orderId=ORD-42` và `includeItems=true`, request sẽ có dạng:

```text
GET https://acme.api.example.com/v1/orders/ORD-42?includeItems=true
```

Server variable quyết định nơi gửi request. Path parameter và query parameter truyền dữ liệu cho operation sau khi server đã được chọn.

## 10. Servers trong nhiều môi trường và reverse proxy

Một dự án thường có các địa chỉ khác nhau cho local, development, staging và production. Có thể mô tả nhiều server trong tài liệu:

```yaml
servers:
  - url: http://localhost:8080/api
    description: Local development
  - url: https://dev-api.example.com/api
    description: Development
  - url: https://staging-api.example.com/api
    description: Staging
  - url: https://api.example.com/api
    description: Production
```

Nếu tất cả môi trường đều được công bố trong một tài liệu, người dùng Swagger UI có thể chọn nhầm môi trường. Với hệ thống nhạy cảm, cân nhắc chỉ công bố server phù hợp với môi trường hiện tại hoặc giới hạn quyền truy cập tài liệu.

Khi ứng dụng nằm sau reverse proxy hoặc API gateway, request bên trong Spring Boot có thể nhìn thấy scheme, host hoặc port nội bộ thay vì URL công khai. Điều này có thể làm server URL tự sinh trong tài liệu sai.

Cần kiểm tra:

- Proxy có gửi các header `Forwarded` hoặc `X-Forwarded-*` chính xác không?
- Proxy có ghi đè header forwarded do client gửi vào để tránh giả mạo host không?
- Spring Boot có được cấu hình xử lý forwarded headers theo hạ tầng đang dùng không?
- Context path hoặc prefix được gateway thêm vào có xuất hiện trong server URL không?
- URL công khai có dùng HTTPS trong khi kết nối nội bộ tới ứng dụng dùng HTTP không?

Spring Boot có thuộc tính `server.forward-headers-strategy` để chọn cách xử lý forwarded headers. Giá trị phù hợp phụ thuộc servlet container và kiến trúc triển khai; hãy đối chiếu tài liệu Spring Boot đúng phiên bản. Không nên bật tin cậy forwarded headers nếu proxy không kiểm soát và làm sạch các header đầu vào.

Nếu server URL được cấu hình tĩnh bằng annotation hoặc bean, hãy bảo đảm giá trị đó khớp với URL người dùng thực sự có thể truy cập. Cấu hình tĩnh có thể che đi sai lệch giữa URL nội bộ và URL public, vì vậy cần kiểm tra từ góc nhìn của client.

## 11. Phân biệt servers với cấu hình mạng Spring Boot

Một nhầm lẫn thường gặp là nghĩ rằng khai báo server trong OpenAPI sẽ làm Spring Boot lắng nghe tại địa chỉ đó. Hai cấu hình này có mục đích khác nhau.

| Cấu hình | Tác dụng |
|---|---|
| OpenAPI `servers[].url` | Mô tả URL gốc cho người dùng API và công cụ client |
| `server.port` | Cổng mà ứng dụng Spring Boot sử dụng |
| `server.address` | Địa chỉ interface mà ứng dụng bind, nếu được cấu hình |
| `server.servlet.context-path` | Context path của ứng dụng servlet |
| Reverse proxy / gateway | Định tuyến và có thể thay đổi host, scheme hoặc prefix bên ngoài |

Ví dụ:

```properties
server.port=8081
server.servlet.context-path=/shop
```

Ứng dụng có thể phục vụ endpoint tài liệu nội bộ tại:

```text
http://localhost:8081/shop/v3/api-docs
```

Trong khi URL công khai có thể là:

```text
https://api.example.com/store/v3/api-docs
```

Server URL của OpenAPI nên mô tả địa chỉ API mà client cần dùng, chẳng hạn `https://api.example.com/store`, chứ không nhất thiết là địa chỉ bind nội bộ `http://localhost:8081/shop`.

## 12. Kiểm tra servers trong JSON do springdoc sinh ra

Sau khi cấu hình, gọi endpoint tài liệu:

```bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
```

Dùng jq để xem danh sách server:

```bash
jq '.servers' openapi.json
```

Liệt kê URL và mô tả:

```bash
jq -r '.servers[] | [.url, (.description // "")] | @tsv' openapi.json
```

Kiểm tra biến của server đầu tiên:

```bash
jq '.servers[0].variables // {}' openapi.json
```

Có thể kiểm tra server ở cấp operation bằng cách truy vấn path cụ thể:

```bash
jq '.paths["/health"].get.servers' openapi.json
```

Nếu giá trị trả về là `null`, operation đó không có server riêng và sẽ kế thừa server theo phạm vi phù hợp.

Khi kiểm tra, hãy đối chiếu:

- URL có đúng scheme, host, port và base path không?
- Tất cả placeholder có biến tương ứng không?
- Mỗi biến có default không?
- Nếu có enum, default có nằm trong enum không?
- Các server được liệt kê có thật sự được triển khai và cho phép truy cập không?
- Path operation có bị lặp prefix với server URL không?
- Operation hoặc path nào có server riêng cần được giải thích không?

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân và cách kiểm tra |
|---|---|
| Swagger UI gọi sai host hoặc port | Server URL được sinh từ request nội bộ hoặc forwarded headers chưa được xử lý đúng. Kiểm tra proxy và `server.forward-headers-strategy`. |
| URL request bị lặp `/api/v1/api/v1` | Base path đã có trong Server URL và lại được lặp trong path item. Chọn một nơi để đặt prefix. |
| Biến URL không được thay thế | Placeholder và tên trong `variables` không khớp, hoặc thiếu `default`. |
| Giá trị mặc định không được chấp nhận | `default` không thuộc `enum`. Đồng bộ hai trường. |
| Swagger UI chỉ hiển thị một server | Tài liệu JSON chỉ có một phần tử trong `servers`, hoặc server được khai báo ở phạm vi khác ghi đè danh sách rộng hơn. |
| URL production lại trỏ localhost | Cấu hình OpenAPI đang dùng URL local hoặc giá trị mặc định sai trong profile production. |
| URL tương đối hoạt động ở local nhưng sai sau gateway | Base URL tài liệu và URL public có prefix khác nhau; kiểm tra routing và vị trí phục vụ tài liệu. |
| Client gọi được host nhưng không vào đúng API | Server URL thiếu base path hoặc path operation chưa được ghép đúng. |

## 14. Checklist thiết kế Server URL

- [ ] Đã xác định URL mà client thực sự dùng để gọi API.
- [ ] Server URL có scheme, host, port và base path đúng.
- [ ] Đã chọn URL tuyệt đối hoặc tương đối phù hợp với cách triển khai.
- [ ] Placeholder trong URL có biến tương ứng trong `variables`.
- [ ] Mỗi Server Variable có `default`.
- [ ] Nếu khai báo `enum`, giá trị `default` nằm trong danh sách.
- [ ] Server Variable không bị dùng thay cho path, query hoặc header parameter.
- [ ] Không lặp base path giữa server URL và operation path.
- [ ] Server ở cấp tài liệu, path và operation được dùng đúng phạm vi.
- [ ] Reverse proxy và forwarded headers tạo ra URL đúng từ góc nhìn client.
- [ ] Đã kiểm tra `servers` trong JSON thực tế tại `/v3/api-docs`.
- [ ] Mọi server được công bố đều là môi trường mà người dùng tài liệu được phép truy cập.

## 15. Nguồn tra cứu

- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object)
- [OpenAPI Specification – Server Variable Object](https://spec.openapis.org/oas/latest.html#server-variable-object)
- [Swagger – API Server and Base Path](https://swagger.io/docs/specification/v3_0/api-host-and-base-path/)
- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)
- [Spring Boot – Forwarded Headers](https://docs.spring.io/spring-boot/reference/howto/webserver.html)

OpenAPI định nghĩa cách mô tả server và biến URL; springdoc-openapi chịu trách nhiệm đưa metadata đó vào tài liệu được sinh từ ứng dụng Spring. Khi nâng cấp springdoc hoặc thay đổi cách triển khai qua gateway, hãy kiểm tra lại JSON đầu ra và thử URL từ môi trường của client.

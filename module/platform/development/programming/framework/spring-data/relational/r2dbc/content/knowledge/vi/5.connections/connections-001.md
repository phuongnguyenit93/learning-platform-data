# Định dạng R2DBC URL và các thuộc tính ConnectionFactoryOptions

Trong Spring Data Relational R2DBC, `ConnectionFactory` là điểm vào để lấy connection tới cơ sở dữ liệu. Để tạo factory, ứng dụng cần cung cấp thông tin về driver, máy chủ, cổng, database, thông tin xác thực và các tùy chọn bổ sung. R2DBC SPI biểu diễn những thông tin này bằng `ConnectionFactoryOptions`; nhiều driver cũng cho phép khai báo chúng trong một R2DBC URL.

URL và `ConnectionFactoryOptions` mô tả cùng một cấu hình kết nối ở hai hình thức khác nhau. URL thuận tiện cho cấu hình dạng chuỗi, còn `ConnectionFactoryOptions` phù hợp khi cần xây dựng cấu hình bằng Java, thêm tùy chọn có kiểu dữ liệu hoặc tích hợp với cấu hình của Spring. Hiểu cấu trúc và phạm vi của từng option giúp tránh dùng nhầm JDBC URL, truyền sai tên thuộc tính hoặc phụ thuộc vào tùy chọn riêng của một driver.

## 1. R2DBC URL là gì?

R2DBC URL là chuỗi định danh cấu hình kết nối theo quy ước của R2DBC. URL bắt đầu bằng scheme `r2dbc:` để phân biệt với các loại URL khác, đặc biệt là JDBC URL bắt đầu bằng `jdbc:`.

Ví dụ một URL kết nối PostgreSQL:

```text
r2dbc:postgresql://appuser:secret@db.example.com:5432/appdb?schema=public
```

Chuỗi trên cho biết driver PostgreSQL, thông tin xác thực, địa chỉ máy chủ, cổng, database và một option bổ sung. Driver cụ thể sẽ phân tích URL và chuyển các thành phần thành cấu hình mà nó hiểu.

Không có một cách viết phần địa chỉ áp dụng giống hệt cho mọi driver. Các driver có thể hỗ trợ dạng URL mạng, dạng embedded hoặc protocol riêng. Vì vậy, cần xem định dạng URL của đúng driver đang dùng thay vì giả định mọi URL đều có đủ host, port và database theo một khuôn duy nhất.

## 2. Các thành phần thường gặp trong URL

Với driver kết nối qua mạng, dạng thường gặp là:

```text
r2dbc:<driver>://[<user>[:<password>]@]<host>[:<port>]/<database>[?<option>=<value>&...]
```

Một số thành phần có ý nghĩa như sau:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `r2dbc:` | Scheme xác định đây là URL R2DBC | `r2dbc:` |
| `<driver>` | Tên driver/provider cần sử dụng | `postgresql`, `mariadb`, `mysql`, `h2` |
| `<user>` | Tên người dùng, nếu URL chứa thông tin xác thực | `appuser` |
| `<password>` | Mật khẩu, nếu được khai báo trong URL | `secret` |
| `<host>` | Tên máy chủ hoặc địa chỉ IP | `db.example.com` |
| `<port>` | Cổng dịch vụ database | `5432` |
| `<database>` | Tên database hoặc đường dẫn mà driver diễn giải | `appdb` |
| `?<option>=<value>` | Các tùy chọn bổ sung theo driver | `schema=public` |

Phần user/password có thể được đặt trong URL hoặc cấu hình riêng qua `ConnectionFactoryOptions` hay Spring. Với môi trường thật, thường nên cung cấp thông tin xác thực qua secret/configuration bên ngoài để tránh ghi mật khẩu vào URL trong log, lịch sử terminal hoặc file cấu hình được commit.

### Driver và protocol

Driver cho biết provider nào chịu trách nhiệm tạo `ConnectionFactory`. Phần protocol, nếu driver hỗ trợ, mô tả cách driver kết nối hoặc loại tài nguyên cần mở. Ví dụ:

```text
r2dbc:postgresql://localhost:5432/appdb
r2dbc:h2:mem:///testdb
r2dbc:h2:file:///./data/testdb
```

Trong URL PostgreSQL, `postgresql` là driver và phần tiếp theo mô tả endpoint mạng. Với H2, `h2` là driver còn `mem` hoặc `file` biểu thị chế độ lưu trữ. URL H2 dạng `mem:///testdb` không có host mạng; không nên cố diễn giải nó như một URL server thông thường.

Tên driver trong URL phải tương ứng với provider có trên classpath. Việc viết `r2dbc:postgresql:` không tự cài đặt driver PostgreSQL; ứng dụng vẫn cần dependency R2DBC driver phù hợp.

### Host, port và database

Đối với kết nối mạng, host xác định máy chủ và port xác định cổng dịch vụ. Nếu bỏ port, driver có thể dùng cổng mặc định riêng. Không nên tự giả định cổng mặc định khi cấu hình có thể chạy với nhiều hệ quản trị hoặc môi trường khác nhau.

Database thường được đặt ở phần path sau dấu `/`. Ý nghĩa chính xác của path do driver quyết định. Ví dụ, `appdb` trong URL PostgreSQL là tên database. Với embedded database, path có thể biểu diễn tên cơ sở dữ liệu trong bộ nhớ hoặc vị trí file.

Database và schema là hai khái niệm khác nhau. Database xác định cơ sở dữ liệu mà connection mở tới; schema thường là namespace bên trong database. Với PostgreSQL, `appdb` và `public` trong ví dụ trên lần lượt là database và schema. Không nên thay tên database bằng schema chỉ vì cả hai đều xuất hiện trong cấu hình kết nối.

### Query parameters

Phần sau dấu `?` chứa các option dạng cặp tên/giá trị, thường được phân tách bằng `&`:

```text
r2dbc:postgresql://db.example.com:5432/appdb?schema=public&sslMode=require
```

Trong ví dụ, `schema` và `sslMode` là các tùy chọn được driver PostgreSQL hỗ trợ ở những phiên bản tương ứng. Chúng không phải là tên option có thể mặc định dùng cho mọi driver. Driver khác có thể dùng tên khác, kiểu giá trị khác hoặc không hỗ trợ tính năng tương tự.

Không nên coi query parameters là một bộ thuộc tính phổ quát. R2DBC SPI cung cấp các option chung; driver/provider quyết định cách diễn giải những option riêng. Khi cấu hình TLS, timeout, application name, schema mặc định hoặc các tính năng đặc thù, hãy đối chiếu tài liệu của đúng driver và phiên bản đang dùng.

## 3. Ví dụ URL theo loại kết nối

### PostgreSQL qua mạng

```text
r2dbc:postgresql://localhost:5432/appdb
```

Có thể thêm thông tin xác thực và option riêng của driver:

```text
r2dbc:postgresql://appuser:secret@localhost:5432/appdb?schema=public
```

Nếu tách thông tin xác thực ra cấu hình Spring, URL có thể chỉ chứa endpoint và database:

```text
r2dbc:postgresql://localhost:5432/appdb
```

### H2 trong bộ nhớ

```text
r2dbc:h2:mem:///testdb
```

Đây là ví dụ thường dùng cho môi trường phát triển hoặc kiểm thử. Dữ liệu của database trong bộ nhớ có vòng đời phụ thuộc cách driver và cấu hình H2 quản lý database; không nên mặc định rằng dữ liệu tồn tại qua mọi connection hoặc sau khi ứng dụng kết thúc.

### H2 lưu trên file

```text
r2dbc:h2:file:///./data/testdb
```

Đường dẫn file được driver H2 diễn giải. Cần kiểm tra thư mục làm việc, quyền đọc/ghi và quy tắc URL của phiên bản driver. Một đường dẫn tương đối có thể trỏ tới vị trí khác nhau khi ứng dụng được chạy từ IDE, Gradle hoặc môi trường triển khai.

### Kết nối qua R2DBC Pool

Nếu ứng dụng sử dụng R2DBC Pool, thư viện pool có thể cung cấp wrapper `ConnectionFactory` cho driver nền. Một số cấu hình dùng dạng URL có prefix `pool`, ví dụ:

```text
r2dbc:pool:postgresql://localhost:5432/appdb
```

Đây là dạng do pool provider hỗ trợ, không phải prefix mà mọi driver đều hiểu. Cần có dependency pool và cấu hình đúng cách để provider pool tạo factory bao quanh factory PostgreSQL. Các tùy chọn kích thước pool và thời gian chờ cũng phụ thuộc thư viện pool, không nên nhầm chúng với option chung của driver database.

## 4. URL encoding và các ký tự đặc biệt

R2DBC URL tuân theo cách phân tách thành phần của URI. Một số ký tự có ý nghĩa cấu trúc: `@` phân tách user information với host, `:` phân tách username/password hoặc host/port, `/` phân tách path, `?` bắt đầu query string, `&` phân tách query parameters và `#` mở đầu fragment.

Nếu giá trị user, password, tên database hoặc option chứa ký tự có ý nghĩa cấu trúc, cần percent-encode giá trị đó theo quy tắc URI và quy tắc của driver. Ví dụ, mật khẩu có ký tự `@` không nên được chèn nguyên trạng vào phần user information vì parser có thể hiểu nhầm đó là ranh giới trước host.

Ví dụ minh họa về hình thức mã hóa:

| Ký tự trong dữ liệu | Dạng percent-encoded |
| --- | --- |
| khoảng trắng | `%20` |
| `@` | `%40` |
| `:` | `%3A` |
| `/` | `%2F` |
| `?` | `%3F` |
| `&` | `%26` |
| `#` | `%23` |

Không nên tự nối chuỗi mật khẩu chưa mã hóa vào URL. Nếu dùng thư viện tạo URI, hãy truyền từng thành phần qua API tương ứng để thư viện mã hóa đúng vị trí. Cũng cần kiểm tra cách driver giải mã các thành phần, vì parser của driver có thể có quy tắc riêng.

Đối với địa chỉ IPv6, phần host trong authority thường cần đặt trong dấu ngoặc vuông, ví dụ `[2001:db8::10]`, để dấu `:` bên trong địa chỉ không bị nhầm với dấu phân tách port.

## 5. `ConnectionFactoryOptions` là gì?

`io.r2dbc.spi.ConnectionFactoryOptions` là đối tượng cấu hình bất biến (immutable) của R2DBC SPI. Nó chứa các cặp option và giá trị mà provider dùng để tạo `ConnectionFactory`.

Mỗi option được biểu diễn bằng `Option<T>`, trong đó `T` thể hiện kiểu dữ liệu của giá trị. Ví dụ, port là số nguyên, SSL là boolean, còn host và database thường là chuỗi. Cách biểu diễn có kiểu giúp ứng dụng tránh phải tự xử lý mọi cấu hình như một chuỗi URL.

Các lớp quan trọng liên quan:

| Kiểu | Vai trò |
| --- | --- |
| `ConnectionFactoryOptions` | Chứa tập option hoàn chỉnh để tạo factory |
| `ConnectionFactoryOptions.Builder` | Xây dựng tập option bằng các lời gọi `option(...)` |
| `Option<T>` | Định danh một option và kiểu giá trị tương ứng |
| `ConnectionFactories` | Tìm provider phù hợp và tạo `ConnectionFactory` |
| `ConnectionFactoryProvider` | SPI mà driver/provider triển khai để hỗ trợ option và tạo factory |

`ConnectionFactoryOptions` không tự mở socket hoặc thực thi SQL. Nó chỉ mô tả cấu hình. `ConnectionFactories.get(...)` dùng tập option đó để tìm `ConnectionFactoryProvider` phù hợp, sau đó provider tạo factory thực tế.

## 6. Các option chung thường gặp

R2DBC SPI định nghĩa những option chung để các driver có thể dùng chung một cách biểu diễn cấu hình. Những option cốt lõi thường gặp gồm:

| Hằng option | Kiểu giá trị thường dùng | Ý nghĩa |
| --- | --- | --- |
| `DRIVER` | `String` | Tên driver/provider, chẳng hạn `postgresql` hoặc `h2` |
| `PROTOCOL` | `String` | Protocol hoặc chế độ kết nối do driver diễn giải, nếu có |
| `HOST` | `String` | Máy chủ database |
| `PORT` | `Integer` | Cổng kết nối |
| `USER` | `String` | Tên người dùng |
| `PASSWORD` | `CharSequence` | Mật khẩu hoặc thông tin xác thực dạng chuỗi ký tự |
| `DATABASE` | `String` | Database hoặc tài nguyên database theo driver |
| `SSL` | `Boolean` | Bật/tắt hỗ trợ SSL/TLS ở mức option chung |

Đây là các option phổ biến để hiểu cấu hình kết nối; tập option chính xác phụ thuộc phiên bản R2DBC SPI và provider. Không phải option chung nào cũng được mọi driver hỗ trợ theo cùng cách. Ví dụ, `SSL=true` chỉ biểu diễn ý định bật SSL ở mức khái quát; chế độ xác minh chứng chỉ, trust store, client certificate hoặc chính sách TLS chi tiết có thể cần option riêng của driver.

Ngoài option chung, driver có thể định nghĩa option riêng cho schema mặc định, application name, timeout, chế độ SSL, socket hoặc các tính năng đặc thù. Hãy dùng tài liệu của driver để biết tên, kiểu dữ liệu, giá trị hợp lệ và mặc định của chúng.

## 7. Xây dựng `ConnectionFactoryOptions` bằng Java

Có thể tạo option bằng `ConnectionFactoryOptions.builder()` và gọi `option(key, value)` cho từng thuộc tính. Ví dụ PostgreSQL:

```java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactoryOptions;
import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.Option;

import static io.r2dbc.spi.ConnectionFactoryOptions.*;

ConnectionFactoryOptions options = ConnectionFactoryOptions.builder()
        .option(DRIVER, "postgresql")
        .option(HOST, "localhost")
        .option(PORT, 5432)
        .option(DATABASE, "appdb")
        .option(USER, "appuser")
        .option(PASSWORD, "secret")
        .build();

ConnectionFactory connectionFactory = ConnectionFactories.get(options);
```

`DRIVER` giúp `ConnectionFactories` xác định provider cần dùng. Những option còn lại cung cấp endpoint và thông tin đăng nhập. Driver phải có trên classpath và phải hỗ trợ các option đã truyền.

Trong ví dụ này mật khẩu chỉ để minh họa. Ứng dụng thực tế nên đọc secret từ môi trường triển khai hoặc secret manager. Không ghi thông tin xác thực thật vào mã nguồn, log hoặc repository.

### Thêm option riêng của driver

Khi driver có option riêng, có thể dùng hằng `Option` mà driver cung cấp hoặc tạo option bằng `Option.valueOf(...)` nếu API yêu cầu:

```java
ConnectionFactoryOptions options = ConnectionFactoryOptions.builder()
        .option(DRIVER, "postgresql")
        .option(HOST, "localhost")
        .option(PORT, 5432)
        .option(DATABASE, "appdb")
        .option(USER, "appuser")
        .option(PASSWORD, "secret")
        .option(Option.valueOf("schema"), "public")
        .build();
```

`schema` trong ví dụ là option riêng theo khả năng của driver PostgreSQL và phiên bản đang dùng. `Option.valueOf("schema")` chỉ tạo khóa option; nó không làm cho driver tự động hỗ trợ tính năng đó. Nếu tên option sai hoặc provider không biết option, factory có thể bị từ chối hoặc tùy chọn không có hiệu lực theo hành vi của provider.

Nên ưu tiên hằng option được driver công bố nếu có, vì hằng đó giúp thể hiện rõ tên và kiểu dữ liệu mà driver mong đợi. Nếu dùng `Option.valueOf`, hãy kiểm tra chính xác tên và kiểu giá trị trong tài liệu driver.

### Tạo factory từ URL

Khi đã có URL hợp lệ và driver tương ứng trên classpath, API `ConnectionFactories` có thể nhận URL để tạo factory:

```java
ConnectionFactory connectionFactory = ConnectionFactories.get(
        "r2dbc:postgresql://localhost:5432/appdb"
);
```

Ở cách này, URL được phân tích thành cấu hình để provider phù hợp tạo factory. Nếu ứng dụng cần thêm option hoặc muốn cấu hình bằng Java, có thể xây dựng `ConnectionFactoryOptions` trực tiếp rồi truyền vào `ConnectionFactories.get(options)`.

Hai cách trên đều đi đến một `ConnectionFactory`. Chọn cách nào phụ thuộc vào nơi cấu hình được lưu, yêu cầu quản lý secret, số lượng tùy chọn và mức độ cần kiểm soát kiểu dữ liệu.

## 8. Quan hệ giữa URL và ConnectionFactoryOptions

Có thể xem URL là cách viết cấu hình dưới dạng chuỗi; `ConnectionFactoryOptions` là mô hình cấu hình có kiểu mà provider sử dụng. Quá trình khái quát:

```mermaid
flowchart TD
    A["R2DBC URL"] --> C["Phân tích thành ConnectionFactoryOptions"]
    B["Java Builder / Spring configuration"] --> C
    C --> D["ConnectionFactories.get(options)"]
    D --> E["Tìm ConnectionFactoryProvider phù hợp"]
    E --> F["Provider của driver hoặc pool"]
    F --> G["ConnectionFactory"]
```

Ví dụ cùng một cấu hình PostgreSQL có thể được biểu diễn bằng URL:

```text
r2dbc:postgresql://localhost:5432/appdb
```

Hoặc bằng Java:

```java
ConnectionFactoryOptions options = ConnectionFactoryOptions.builder()
        .option(DRIVER, "postgresql")
        .option(HOST, "localhost")
        .option(PORT, 5432)
        .option(DATABASE, "appdb")
        .build();
```

Khi dùng URL, parser của provider chuyển các phần thành option tương ứng. Khi dùng builder, ứng dụng đặt trực tiếp từng option. Với option riêng, tên và cách mã hóa trong URL do driver định nghĩa; dạng Java cần cung cấp đúng `Option` và kiểu giá trị mà driver hỗ trợ.

Không nên giả định mọi query parameter trong URL đều có một hằng `ConnectionFactoryOptions` tương ứng trong SPI. Một số option là mở rộng của driver. Cũng không nên giả định một option có cùng tên ở hai driver sẽ có cùng kiểu, mặc định hoặc ngữ nghĩa.

## 9. Cấu hình trong Spring Boot

Trong ứng dụng Spring Boot, thường không cần tự gọi `ConnectionFactories.get(...)`. Spring Boot có thể tạo bean `ConnectionFactory` từ cấu hình R2DBC và cung cấp cho `DatabaseClient`, `R2dbcEntityTemplate` cùng repository.

Ví dụ cấu hình YAML với PostgreSQL:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/appdb
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    properties:
      schema: public
```

`url` xác định driver và endpoint. `username` và `password` được khai báo riêng để tránh đưa secret vào URL. Các thuộc tính bổ sung dưới `properties` được chuyển tiếp theo cơ chế cấu hình của Spring Boot và provider; tên cùng kiểu phải phù hợp với driver đang dùng. Hãy kiểm tra tài liệu Spring Boot phiên bản dự án để xác nhận các thuộc tính được hỗ trợ.

Khi cấu hình bằng biến môi trường, ứng dụng có thể dùng cùng artifact cho nhiều môi trường:

```yaml
spring:
  r2dbc:
    url: ${R2DBC_URL}
    username: ${R2DBC_USERNAME}
    password: ${R2DBC_PASSWORD}
```

Ví dụ giá trị của `R2DBC_URL` trong môi trường phát triển:

```text
r2dbc:postgresql://localhost:5432/appdb
```

Trong môi trường kiểm thử hoặc production, chỉ cần cung cấp endpoint và secret tương ứng qua cấu hình triển khai. Không nên commit mật khẩu thật vào `application.yml`.

Nếu ứng dụng tự cấu hình nhiều `ConnectionFactory` hoặc dùng pool riêng, cần khai báo rõ factory nào được dùng cho `DatabaseClient` và transaction manager. Cấu hình URL đúng nhưng wiring nhầm factory vẫn có thể khiến repository kết nối tới database khác với dự kiến.

## 10. Phân biệt option chung và option riêng của driver

Một lỗi thường gặp là coi mọi thuộc tính kết nối đều là một phần của chuẩn R2DBC. Thực tế có ba nhóm cần phân biệt:

| Nhóm | Ví dụ | Nơi xác định ý nghĩa |
| --- | --- | --- |
| Option chung của SPI | `DRIVER`, `HOST`, `PORT`, `USER`, `PASSWORD`, `DATABASE`, `SSL` | R2DBC SPI và provider |
| Option riêng của driver | `schema`, `sslMode`, application name hoặc timeout đặc thù | Tài liệu driver và phiên bản driver |
| Option của pool | kích thước pool, thời gian chờ mượn connection, thời gian idle | Tài liệu R2DBC Pool hoặc pool provider đang dùng |

Ví dụ, `PORT` mô tả cổng kết nối và là option chung. Một thuộc tính như `sslMode=require` có thể được PostgreSQL driver hiểu, nhưng driver khác có thể dùng một option khác. Tương tự, `maxSize` là khái niệm cấu hình pool; không nên truyền nó cho driver database rồi kỳ vọng driver tự quản lý pool.

Khi đọc tài liệu hoặc ví dụ trên Internet, hãy xác định option thuộc nhóm nào và ví dụ được viết cho driver/phiên bản nào. Việc sao chép nguyên query string từ một driver sang driver khác có thể tạo cấu hình không hợp lệ hoặc khiến một số tính năng âm thầm không được áp dụng.

## 11. Các lỗi cấu hình thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không tìm thấy provider | Thiếu dependency driver hoặc tên `DRIVER` sai | Kiểm tra dependency runtime và tên driver trong URL/options |
| URL không được phân tích | Dùng sai scheme hoặc cú pháp không được driver hỗ trợ | Kiểm tra prefix `r2dbc:` và ví dụ URL của đúng driver |
| Không kết nối được host | Sai hostname, port, DNS, firewall hoặc database chưa lắng nghe | Kiểm tra endpoint từ môi trường chạy ứng dụng |
| Xác thực thất bại | Username/password sai hoặc ký tự đặc biệt chưa encode | Kiểm tra secret và cách truyền user information |
| Không mở được database | Sai tên database hoặc path theo chế độ embedded | Kiểm tra ý nghĩa path trong URL của driver |
| Option bị từ chối | Dùng tên option sai hoặc option thuộc driver khác | Đối chiếu option và kiểu dữ liệu trong tài liệu driver |
| SSL không hoạt động như mong muốn | Nhầm option `SSL` chung với chế độ TLS riêng của driver | Kiểm tra yêu cầu chứng chỉ, trust và SSL mode của driver |
| Kết nối tới sai database | URL hoặc bean `ConnectionFactory` được wiring nhầm | Kiểm tra cấu hình hiệu lực và bean được inject |
| Pool không có hiệu lực | Thiếu pool provider hoặc cấu hình pool không được kích hoạt | Kiểm tra dependency và cơ chế cấu hình pool của ứng dụng |

Khi điều tra, nên xác nhận lần lượt driver đã được nạp, URL/options được phân tích đúng, endpoint có thể truy cập, thông tin xác thực hợp lệ và các option riêng được provider chấp nhận. Nếu cần log cấu hình để chẩn đoán, phải che mật khẩu, token và các thông tin nhạy cảm trước khi ghi log.

## 12. Nguyên tắc chọn cách cấu hình

**Dùng R2DBC URL** khi cấu hình gọn, chủ yếu gồm driver và endpoint, và URL được quản lý an toàn trong cấu hình môi trường. URL dễ truyền qua biến môi trường hoặc cấu hình triển khai.

**Dùng `ConnectionFactoryOptions` builder** khi cần tạo factory bằng Java, cấu hình động, thêm option có kiểu hoặc tích hợp với logic chọn provider. Cách này cũng giúp nhìn rõ từng thành phần thay vì phải ghép một chuỗi URL.

**Dùng cấu hình Spring Boot** khi ứng dụng chạy trong hệ sinh thái Spring Boot và chỉ cần một hoặc một số ít factory theo cấu hình. Để Spring quản lý bean giúp `DatabaseClient`, template và repository dùng chung cấu hình nhất quán.

Dù chọn cách nào, hãy giữ thông tin xác thực ngoài mã nguồn, dùng đúng driver, phân biệt option SPI với option riêng của driver và kiểm tra tài liệu theo phiên bản dependency thực tế. Một cấu hình R2DBC chỉ có hiệu lực khi provider tương ứng hiểu và áp dụng các option được truyền vào.

## 13. Ghi nhớ

- R2DBC URL bắt đầu bằng `r2dbc:`; không dùng JDBC URL `jdbc:` cho R2DBC driver.
- Tên driver xác định provider; một số driver còn có protocol hoặc chế độ kết nối riêng như `mem` và `file`.
- Với URL mạng, host, port và database thường nằm trong authority/path; query string chứa các option bổ sung theo driver.
- Database và schema có vai trò khác nhau. Không phải mọi query parameter đều là option chung của R2DBC SPI.
- `ConnectionFactoryOptions` là cấu hình bất biến có kiểu, được xây dựng bằng `ConnectionFactoryOptions.builder()` và các lời gọi `option(...)`.
- `ConnectionFactories.get(...)` chọn provider phù hợp để tạo `ConnectionFactory`; driver phải có trong runtime classpath.
- Dùng option chung như `DRIVER`, `HOST`, `PORT`, `USER`, `PASSWORD`, `DATABASE` và `SSL` theo đúng kiểu; option riêng cần theo tài liệu driver.
- Ký tự đặc biệt trong URL cần được percent-encode đúng vị trí. Không đặt secret thật trong URL được ghi log hoặc commit.
- Option của connection pool thuộc cấu hình pool provider, không đồng nghĩa với option của driver database.
- Trong Spring Boot, có thể khai báo URL, username, password và thuộc tính bổ sung qua cấu hình `spring.r2dbc.*`; kiểm tra đúng phiên bản Boot và driver.

Khi cần chẩn đoán một kết nối R2DBC, hãy đọc URL thành từng thành phần, đối chiếu chúng với `ConnectionFactoryOptions`, rồi xác định provider nào chịu trách nhiệm diễn giải từng option. Cách tiếp cận này giúp phân biệt lỗi cú pháp URL, lỗi thiếu driver, lỗi endpoint và lỗi do option riêng không được hỗ trợ.

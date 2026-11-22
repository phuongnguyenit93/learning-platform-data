# Biến môi trường

Trong DSL cấu hình, **biến môi trường (environment variable)** là một giá trị văn bản được cung cấp cho tiến trình khi ứng dụng được khởi chạy hoặc khi cấu hình được nạp. Biến môi trường thường mang những thông tin thay đổi theo máy, môi trường triển khai hoặc lần chạy, chẳng hạn địa chỉ database, cổng dịch vụ, chế độ debug, đường dẫn dữ liệu và tham chiếu đến secret.

Một file DSL có thể mô tả cấu hình ứng dụng mà không ghi cứng những giá trị riêng của từng môi trường:

~~~yaml
application:
  name: order-service
  server:
    host: 0.0.0.0
    port: $APP_PORT
  database:
    host: $DB_HOST
    port: $DB_PORT
    name: $DB_NAME
    username: $DB_USERNAME
    password: $DB_PASSWORD
~~~

Khi runtime nạp cấu hình, nó đọc các biến từ process environment, thay thế hoặc liên kết chúng với những trường tương ứng, chuyển giá trị sang kiểu dữ liệu cần thiết và kiểm tra các ràng buộc. Cú pháp $NAME trong ví dụ chỉ là cách biểu diễn minh họa; DSL thực tế phải quy định chính xác cách tham chiếu, giá trị mặc định, escaping và lỗi khi biến không tồn tại.

Biến môi trường giúp cùng một artifact cấu hình được dùng ở máy phát triển, môi trường kiểm thử, staging và production với các giá trị khác nhau. Chúng cũng là giao diện phổ biến giữa ứng dụng với container, hệ thống điều phối, CI/CD và nền tảng cloud. Tuy nhiên, environment variable chỉ là một kênh truyền cấu hình; nó không tự cung cấp schema, kiểu dữ liệu, bảo mật secret hay cơ chế đồng bộ giữa các tiến trình. DSL cần định nghĩa rõ cách đọc, xác thực, ưu tiên và bảo vệ các giá trị này.

## 1. Biến môi trường là gì?

Environment variable là một cặp tên và giá trị được cung cấp cho một tiến trình. Trên nhiều hệ điều hành, môi trường của tiến trình được kế thừa từ tiến trình cha khi tiến trình con được tạo. Chương trình có thể đọc các giá trị này thông qua API của runtime hoặc thư viện hệ thống.

Ví dụ, khi khởi chạy một ứng dụng, môi trường có thể chứa:

~~~text
APP_ENV=production
APP_PORT=8080
LOG_LEVEL=INFO
DB_HOST=db.internal
DB_PORT=5432
~~~

Ứng dụng đọc các biến và dùng chúng để hoàn thiện cấu hình.

### 1.1. Tên và giá trị

Một biến có hai thành phần:

- **Name:** Tên định danh, ví dụ APP_HOST.
- **Value:** Giá trị văn bản, ví dụ api.internal.

Tên thường phân biệt chữ hoa và chữ thường trên một số hệ điều hành, nhưng không phải môi trường nào cũng có cùng quy tắc. Trên Windows, tên biến môi trường thường không phân biệt hoa thường; trên các hệ Unix-like, chúng thường phân biệt. Vì vậy, convention của DSL nên tránh tạo hai biến chỉ khác chữ hoa/thường.

### 1.2. Giá trị thường là chuỗi

Phần lớn API process environment trả về giá trị dưới dạng chuỗi. APP_PORT=8080 không tự trở thành số nguyên; runtime cần parse thành Integer. FEATURE_ENABLED=false cũng không tự trở thành Boolean.

### 1.3. Phạm vi tiến trình

Environment thường thuộc về một tiến trình và các tiến trình con được tạo từ nó. Thay đổi môi trường trong một tiến trình không tự động cập nhật môi trường của những tiến trình khác đang chạy.

### 1.4. Không phải cấu hình toàn cục tự động

Biến môi trường không tự đồng bộ giữa nhiều máy, container hoặc replica. Nền tảng triển khai phải cung cấp giá trị cho từng tiến trình hoặc nhóm tiến trình theo chính sách riêng.

### 1.5. Environment snapshot

Ứng dụng thường đọc environment khi khởi động và xây dựng một cấu hình nội bộ. Nếu giá trị môi trường bên ngoài thay đổi sau đó, tiến trình đang chạy không nhất thiết nhận được thay đổi. Muốn hỗ trợ reload, runtime phải có cơ chế rõ ràng để đọc lại nguồn cấu hình.

## 2. Vai trò trong DSL cấu hình

DSL cấu hình mô tả trạng thái mong muốn hoặc hành vi của ứng dụng. Một số thông tin ổn định theo project, một số khác thay đổi theo môi trường triển khai. Biến môi trường tạo ranh giới giữa cấu hình chung và giá trị được cung cấp khi chạy.

### 2.1. Tách cấu hình khỏi mã nguồn

Không cần ghi hostname, cổng hoặc đường dẫn cụ thể vào logic ứng dụng. Cùng một file DSL có thể tham chiếu DB_HOST, còn mỗi môi trường cung cấp giá trị tương ứng.

### 2.2. Dùng chung artifact giữa các môi trường

Project có thể đóng gói cùng một file cấu hình và triển khai ở nhiều nơi. Sự khác biệt được đưa vào environment của tiến trình thay vì sửa file trước mỗi lần phát hành.

### 2.3. Tích hợp với nền tảng vận hành

Container runtime, orchestrator, CI/CD runner và cloud platform thường có cơ chế truyền environment vào tiến trình. DSL runtime có thể tận dụng giao diện phổ biến này.

### 2.4. Cung cấp cấu hình tại thời điểm triển khai

Một số giá trị chỉ biết khi deploy, chẳng hạn hostname của dịch vụ phụ thuộc hoặc cổng được cấp động. Biến môi trường cho phép cung cấp chúng khi ứng dụng được khởi chạy.

### 2.5. Tách secret khỏi repository

Environment có thể mang giá trị secret do nền tảng cấp, nhưng cần nhớ rằng biến môi trường không phải secret manager. Cần cân nhắc cách cung cấp, quyền đọc, log, dump tiến trình và vòng đời của credential.

### 2.6. Hỗ trợ cùng một DSL trên nhiều nền tảng

Nếu DSL định nghĩa một contract environment rõ ràng, ứng dụng có thể chạy trên máy cá nhân, container hoặc máy chủ mà không phải thay đổi ngữ nghĩa cấu hình.

## 3. Phân biệt biến môi trường với các nguồn cấu hình khác

Một ứng dụng thường có nhiều nguồn cấu hình. Mỗi nguồn có đặc tính và mục đích riêng.

| Nguồn | Ví dụ | Đặc điểm |
|---|---|---|
| Giá trị mặc định trong DSL | port = 8080 | Dùng khi không có override |
| File cấu hình | application.yml | Có cấu trúc, dễ version hóa |
| Environment variable | APP_PORT=8080 | Giao diện đơn giản cho process |
| Command-line argument | --port 8080 | Thích hợp override theo lần chạy |
| Secret manager | Secret reference | Quản lý credential và quyền truy cập |
| Remote config service | Config center | Có thể cập nhật tập trung |
| Runtime API | Giá trị do ứng dụng cung cấp | Phụ thuộc logic chương trình |

### 3.1. File cấu hình

File JSON, YAML, TOML hoặc DSL có thể biểu diễn cấu trúc lồng nhau, danh sách và kiểu dữ liệu. Environment variable thường phẳng hơn, nên cần quy ước ánh xạ tên để biểu diễn các trường lồng nhau.

### 3.2. Command-line arguments

CLI arguments phù hợp với giá trị cần thay đổi cho một lần chạy hoặc thao tác quản trị. Cần có quy tắc ưu tiên giữa CLI và environment để tránh kết quả khó đoán.

### 3.3. Secret manager

Secret manager lưu credential, token và key với quyền truy cập, audit và rotation. Environment variable có thể chứa secret value hoặc chỉ chứa tên/path tham chiếu đến secret. Cách thứ hai giúp tách vòng đời secret khỏi file cấu hình.

### 3.4. Remote configuration

Config service có thể phân phối cấu hình động cho nhiều instance. Nó cần xử lý xác thực, cache, version và sự cố mạng. Environment variable đơn giản hơn nhưng thường được cố định theo vòng đời tiến trình.

### 3.5. Không nên biến mọi thứ thành environment variable

Một danh sách lớn gồm các giá trị phẳng, khó đọc và khó xác thực. Nên dùng file có cấu trúc cho cấu hình phức tạp, environment variable cho các giá trị triển khai cần override hoặc được nền tảng truyền vào.

## 4. Quy ước đặt tên biến

Tên biến cần nhất quán để người vận hành, công cụ triển khai và runtime cùng hiểu một cách.

### 4.1. Chữ hoa và dấu gạch dưới

Convention phổ biến là dùng chữ hoa, số và dấu gạch dưới:

~~~text
APP_ENV
APP_PORT
DB_HOST
DB_PORT
DB_USERNAME
LOG_LEVEL
~~~

Tên nên có nghĩa và tránh viết tắt không phổ biến.

### 4.2. Prefix của ứng dụng

Prefix giúp tránh xung đột với biến của hệ điều hành, runtime hoặc ứng dụng khác:

~~~text
ORDER_APP_ENV
ORDER_DB_HOST
ORDER_DB_PORT
ORDER_FEATURE_SCHEDULER
~~~

Với ứng dụng lớn, có thể dùng prefix theo module hoặc subsystem.

### 4.3. Ánh xạ từ cấu trúc lồng nhau

Một quy ước có thể dùng dấu gạch dưới để biểu diễn đường dẫn:

| Trường DSL | Environment name |
|---|---|
| server.port | APP_SERVER_PORT |
| database.host | APP_DATABASE_HOST |
| database.pool.maxSize | APP_DATABASE_POOL_MAX_SIZE |
| logging.level | APP_LOGGING_LEVEL |

Nếu tên trường chứa dấu gạch dưới hoặc ký tự đặc biệt, cần quy tắc escape hoặc mapping tường minh để tránh hai đường dẫn cùng tạo ra một tên.

### 4.4. Namespace và prefix

DSL có thể khai báo prefix mặc định:

~~~text
environment {
    prefix = "ORDER_"
}
~~~

Khi đó, thuộc tính database.host có thể ánh xạ thành ORDER_DATABASE_HOST. Prefix cần được áp dụng nhất quán và có thể override ở cấp ứng dụng nếu đặc tả cho phép.

### 4.5. Case sensitivity

Do khác biệt giữa nền tảng, nên chọn một dạng canonical, thường là uppercase. Runtime có thể chuẩn hóa tên để tra cứu nhưng cần phát hiện collision thay vì âm thầm chọn một biến.

### 4.6. Tránh tên quá chung

Tên như PORT, USER, PATH hoặc HOME có thể đã mang ý nghĩa đặc biệt trong hệ điều hành hoặc môi trường chạy. Prefix ứng dụng giúp giảm xung đột và hành vi ngoài dự kiến.

## 5. Khai báo environment trong DSL

DSL nên mô tả biến nào được phép đọc, biến nào bắt buộc, kiểu dữ liệu, default và ràng buộc. Điều này biến environment thành một phần có kiểm soát của cấu hình.

### 5.1. Khai báo một biến

Một cú pháp minh họa:

~~~text
environment {
    APP_PORT: Integer
}
~~~

Khai báo cho biết runtime cần đọc biến APP_PORT và parse thành Integer.

### 5.2. Giá trị mặc định

~~~text
environment {
    APP_PORT: Integer = 8080
}
~~~

Nếu biến không được cung cấp, runtime dùng default theo hợp đồng. Default không nên che giấu lỗi đối với giá trị bắt buộc như database credential production.

### 5.3. Biến bắt buộc

~~~text
environment {
    DB_HOST: String required
    DB_PASSWORD: Secret required
}
~~~

Nếu thiếu biến bắt buộc, ứng dụng nên dừng khởi động với diagnostic nêu tên biến và trường cấu hình, nhưng không tiết lộ giá trị secret.

### 5.4. Biến tùy chọn

~~~text
environment {
    TRACE_EXPORTER: String optional
}
~~~

Nếu không có biến, trường có thể không được cấu hình hoặc dùng default. Cần phân biệt optional với chuỗi rỗng được cung cấp rõ ràng.

### 5.5. Ràng buộc giá trị

~~~text
environment {
    APP_PORT: Integer = 8080
        min = 1
        max = 65535
}
~~~

Runtime parse giá trị rồi kiểm tra miền hợp lệ. Một chuỗi số nằm ngoài khoảng vẫn là cấu hình không hợp lệ.

### 5.6. Mô tả và tài liệu

Mỗi biến nên có mô tả, đơn vị, default, ví dụ không nhạy cảm và môi trường áp dụng. Tài liệu có thể được sinh từ schema để tránh lệch giữa code và README.

## 6. Thay thế biến trong giá trị cấu hình

Một DSL có thể hỗ trợ tham chiếu environment ngay trong giá trị file.

### 6.1. Tham chiếu trực tiếp

~~~yaml
server:
  port: $APP_PORT
~~~

Runtime đọc tên biến và thay bằng giá trị tương ứng. Cú pháp thực tế có thể dùng placeholder khác, nhưng phải có grammar rõ.

### 6.2. Tham chiếu trong chuỗi

~~~yaml
database:
  url: "jdbc:postgresql://$DB_HOST:$DB_PORT/$DB_NAME"
~~~

Khi interpolation được hỗ trợ trong chuỗi, runtime cần quy định escaping, encoding và xử lý ký tự đặc biệt. Giá trị chứa dấu cách, dấu nháy hoặc ký tự điều khiển có thể cần quoting hoặc encoding phù hợp.

### 6.3. Giá trị mặc định trong placeholder

Một số DSL hỗ trợ dạng tham chiếu có default:

~~~text
port = env("APP_PORT", default = "8080")
~~~

Hoặc một cú pháp placeholder riêng. Cần phân biệt default ở khai báo schema với default tại từng chỗ sử dụng; nếu cả hai cùng tồn tại, quy tắc ưu tiên phải được công bố.

### 6.4. Required placeholder

Nếu biến bắt buộc chưa có, resolver nên tạo lỗi cấu hình có thể hành động được. Không nên thay bằng chuỗi "null" hoặc một chuỗi rỗng trừ khi đó là giá trị hợp lệ được khai báo.

### 6.5. Escaping ký hiệu tham chiếu

Nếu người dùng muốn chuỗi literal có nội dung giống cú pháp placeholder, DSL cần cơ chế escape. Ví dụ, một cấu hình chứa văn bản $APP_PORT để hiển thị cho người dùng không nhất thiết muốn runtime thay thế nó.

### 6.6. Nội suy đệ quy

Giả sử SERVICE_URL chứa một chuỗi có tham chiếu đến biến khác. Runtime phải quy định có cho phép nội suy lồng hay không, giới hạn độ sâu và cách phát hiện vòng tham chiếu. Mặc định không đệ quy thường dễ hiểu và an toàn hơn.

### 6.7. Interpolation trong loại dữ liệu

Interpolation có thể xảy ra trước hoặc sau parse kiểu. Với một giá trị Integer, thường cần lấy chuỗi từ environment rồi parse thành số. Với cấu trúc phức tạp, nên dùng parser của DSL thay vì nối chuỗi tùy tiện.

## 7. Chuyển kiểu từ chuỗi sang kiểu DSL

Environment variable thường là text, trong khi DSL có thể yêu cầu Integer, Boolean, Duration, URI, enum hoặc collection.

### 7.1. Integer và decimal

~~~text
APP_PORT=8080
PAYMENT_LIMIT=250000.50
~~~

Runtime cần parse theo locale và định dạng được quy định. Đối với cấu hình máy, nên dùng dấu chấm làm dấu thập phân và không phụ thuộc locale hệ điều hành.

### 7.2. Boolean

~~~text
FEATURE_SCHEDULER=true
FEATURE_METRICS=false
~~~

Nên quy định tập literal được chấp nhận như true và false, có thể hỗ trợ chữ hoa/thường theo chính sách. Tránh diễn giải tùy tiện các giá trị như yes, on, 1 nếu DSL chưa công bố.

### 7.3. Duration

~~~text
REQUEST_TIMEOUT=30s
RETRY_DELAY=500ms
~~~

Duration cần đơn vị rõ ràng. Giá trị 30 không thể được hiểu chính xác nếu không biết là millisecond, second hay minute.

### 7.4. Enum

~~~text
LOG_LEVEL=INFO
APP_ENV=production
~~~

Runtime kiểm tra giá trị có thuộc tập enum hợp lệ không. Có thể cho phép không phân biệt case khi parse, nhưng cần chuẩn hóa giá trị nội bộ.

### 7.5. URI và endpoint

~~~text
DB_URL=postgresql://db.internal:5432/orders
~~~

Sau khi parse, runtime nên kiểm tra scheme, host, port và các ràng buộc của loại URI. Không nên chỉ kiểm tra chuỗi có tiền tố mong muốn.

### 7.6. List và map

Một biến environment phẳng có thể biểu diễn danh sách bằng JSON:

~~~text
ALLOWED_ORIGINS=["https://a.example","https://b.example"]
~~~

Hoặc dùng dấu phân cách:

~~~text
ALLOWED_ORIGINS=https://a.example,https://b.example
~~~

Nếu dùng delimiter, cần quy định cách escape khi một phần tử chứa chính ký tự phân cách. Với cấu trúc lồng nhau, file cấu hình hoặc secret/config store có cấu trúc thường phù hợp hơn một biến chuỗi dài.

### 7.7. Null và chuỗi rỗng

Biến không tồn tại, biến có giá trị rỗng và literal null là ba trạng thái khác nhau. DSL cần quy định cách biểu diễn và cách chuyển đổi. Không nên mặc định chuỗi rỗng đồng nghĩa với null.

### 7.8. Unicode và encoding

Giá trị có thể chứa Unicode. Runtime cần đọc theo encoding của nền tảng và tránh làm hỏng ký tự khi chuyển từ process environment sang model. Tên biến thường nên giới hạn ở bộ ký tự portable, còn value có thể rộng hơn.

## 8. Quy tắc ưu tiên giữa các nguồn cấu hình

Khi cùng một trường xuất hiện trong nhiều nguồn, runtime cần quy định nguồn nào thắng.

### 8.1. Một thứ tự ưu tiên điển hình

Một hệ thống có thể dùng thứ tự:

1. Giá trị mặc định trong schema.
2. File cấu hình chung.
3. File profile hoặc file môi trường.
4. Environment variable.
5. Command-line argument.
6. Override tường minh qua API quản trị.

Đây chỉ là một lựa chọn kiến trúc. DSL phải công bố thứ tự thực tế; không có thứ tự chung bắt buộc cho mọi ứng dụng.

### 8.2. Ví dụ

Giả sử file có server.port = 8080, còn environment có APP_PORT=9090. Nếu environment có ưu tiên cao hơn file, runtime dùng 9090.

### 8.3. Ưu tiên theo từng trường

Không nhất thiết mọi trường đều cho phép override từ mọi nguồn. Một số trường bảo mật hoặc bất biến có thể chỉ được thiết lập bởi nguồn quản trị.

### 8.4. Merge hay replace

Với scalar, nguồn ưu tiên cao thường thay giá trị thấp. Với list và map, cần quy định merge hay replace. Nếu list được nối tự động, người dùng có thể vô tình giữ lại một giá trị không mong muốn từ file mặc định.

### 8.5. Null và giá trị rỗng khi override

Một giá trị rỗng có thể được dùng để xóa giá trị cũ hoặc có thể bị coi là invalid. Cần quy định rõ cách biểu diễn thao tác xóa và cách xử lý trường bắt buộc.

### 8.6. Explain configuration

Runtime hoặc CLI có thể cung cấp lệnh giải thích nguồn của từng trường, ví dụ server.port đến từ APP_PORT. Khi làm vậy, cần che giá trị nhạy cảm và chỉ hiển thị source metadata an toàn.

## 9. Profile và phân tách môi trường

Profile là tập cấu hình theo mục đích chạy, chẳng hạn development, test, staging hoặc production.

### 9.1. Environment name

~~~text
APP_ENV=development
~~~

Giá trị này có thể quyết định profile được nạp. Tên profile nên nằm trong tập đã định nghĩa và không tự động mở các tính năng nguy hiểm chỉ vì chuỗi có giá trị bất kỳ.

### 9.2. Cấu hình theo profile

~~~text
profile development {
    logging.level = DEBUG
    feature.mockPayments = true
}

profile production {
    logging.level = INFO
    feature.mockPayments = false
}
~~~

Environment có thể chọn profile, còn các giá trị riêng như endpoint và credential vẫn được truyền qua nguồn phù hợp.

### 9.3. Tránh profile ngầm định nguy hiểm

Nếu APP_ENV không tồn tại hoặc sai chính tả, runtime không nên âm thầm chọn production hoặc development theo một suy đoán khó nhận biết. Cần default được công bố hoặc yêu cầu cấu hình tường minh.

### 9.4. Không dùng profile để chứa secret

Profile nên xác định hành vi và policy chung. Credential thật cần được cấp từ secret store hoặc nguồn bảo mật, không nên commit vào file profile.

### 9.5. Kiểm soát feature theo môi trường

Một số tính năng như debug endpoint, mock service hoặc verbose logging có thể chỉ được phép ở development. Validator có thể ngăn bật chúng trong production profile.

## 10. File .env và môi trường phát triển local

File .env thường được dùng để nạp các cặp tên/giá trị vào environment khi phát triển local.

### 10.1. Ví dụ file .env

~~~text
APP_ENV=development
APP_PORT=8080
DB_HOST=localhost
DB_PORT=5432
DB_NAME=orders_dev
~~~

Một công cụ như dotenv đọc file rồi đưa giá trị vào môi trường của tiến trình hoặc cung cấp một map cấu hình cho ứng dụng.

### 10.2. .env không phải chuẩn shell

Các thư viện dotenv có thể khác nhau về quoting, multiline, comment và interpolation. Không nên giả định mọi file .env đều có thể chạy trực tiếp bằng shell hoặc được mọi công cụ hiểu giống nhau.

### 10.3. File mẫu

Repository có thể chứa .env.example với tên biến và giá trị giả:

~~~text
APP_ENV=development
APP_PORT=8080
DB_HOST=localhost
DB_USERNAME=replace-me
DB_PASSWORD=replace-me
~~~

File thật chứa giá trị riêng của máy thường được thêm vào ignore list. Không đưa credential thật vào file mẫu.

### 10.4. Không commit .env thật

Nếu .env có secret, cần loại khỏi Git và kiểm tra lịch sử repository nếu đã lỡ commit. Xóa file ở commit mới không tự làm secret cũ mất hiệu lực; credential bị lộ cần được rotate.

### 10.5. Chỉ nạp file ở môi trường phù hợp

Production thường nhận environment từ nền tảng triển khai hoặc secret manager. Không nên tự động đọc một file .env tùy ý trong working directory production nếu điều đó không thuộc hợp đồng vận hành.

### 10.6. Thứ tự nạp

Nếu process environment đã có biến, dotenv loader cần quy định có ghi đè hay không. Thông thường, giá trị được cung cấp tường minh từ môi trường chạy có thể được ưu tiên hơn file local, nhưng hành vi cụ thể tùy thư viện.

## 11. Biến môi trường và secret

Secret gồm password, API token, private key, signing key, connection credential và dữ liệu xác thực khác.

### 11.1. Environment variable không tự mã hóa secret

Giá trị được đưa vào environment vẫn có thể bị lộ qua log debug, process inspection, crash dump, diagnostic endpoint hoặc công cụ quản trị. Mức độ truy cập phụ thuộc hệ điều hành và nền tảng triển khai.

### 11.2. Dùng secret manager

Secret manager có thể quản lý quyền, rotation, audit và version. Runtime có thể lấy secret qua SDK, file mount hoặc identity-based access rồi cung cấp cho cấu hình DSL.

### 11.3. Truyền reference thay vì value

Một cấu hình có thể khai báo:

~~~text
database.password = secret("production/order-db-password")
~~~

Tên và cú pháp chỉ minh họa. Secret resolver đọc giá trị từ provider được cấu hình, còn file DSL chỉ chứa reference.

### 11.4. Secret qua environment

Nếu nền tảng chỉ hỗ trợ truyền secret qua environment, cần giới hạn quyền đọc process, tránh dump environment, không log toàn bộ cấu hình và rotate giá trị theo quy trình.

### 11.5. Che giá trị nhạy cảm

Diagnostic có thể ghi:

~~~text
Configuration error: DB_PASSWORD is missing.
~~~

Không ghi nội dung thật của DB_PASSWORD. Ngay cả khi parse lỗi, runtime không nên đưa toàn bộ giá trị secret vào exception hoặc telemetry.

### 11.6. Secret trong command line

Truyền password trực tiếp qua command-line argument có thể làm lộ trong process list hoặc shell history. Nếu có thể, dùng secret manager, secure input hoặc cơ chế credential của nền tảng.

### 11.7. Rotation

Nếu secret thay đổi khi ứng dụng đang chạy, runtime cần biết có hỗ trợ reload không. Một connection pool có thể cần tạo lại connection; một signing key có thể cần giai đoạn chấp nhận đồng thời key cũ và mới.

### 11.8. Least privilege

Tiến trình chỉ nên nhận những secret cần cho chức năng của nó. Không truyền toàn bộ secret của môi trường vào mọi service hoặc job.

## 12. Environment trong container và orchestration

Container và orchestrator thường cung cấp environment cho tiến trình bên trong container.

### 12.1. Docker

Environment có thể được truyền khi chạy container qua flags hoặc file environment:

~~~text
docker run --env APP_ENV=production --env APP_PORT=8080 order-service
~~~

Lệnh chỉ minh họa. Giá trị thực tế có thể được cung cấp bởi compose file, secret store hoặc deployment system.

### 12.2. Compose

Compose có thể đọc file environment để cấu hình service. Cần phân biệt biến dùng để thay thế trong compose file với biến thực sự được truyền vào container; hai phạm vi này không phải lúc nào cũng giống nhau.

### 12.3. Kubernetes

Pod có thể nhận environment từ literal, ConfigMap hoặc Secret. ConfigMap phù hợp với cấu hình không nhạy cảm; Secret dành cho dữ liệu nhạy cảm nhưng vẫn cần cấu hình quyền truy cập, mã hóa và chính sách cluster thích hợp.

### 12.4. Secret mount và file reference

Một số nền tảng mount secret thành file thay vì environment. DSL có thể hỗ trợ nguồn file secret để tránh đưa nội dung credential vào process environment.

### 12.5. Replica

Mỗi replica có environment riêng khi được tạo. Cập nhật ConfigMap hoặc Secret không nhất thiết thay đổi environment của container đang chạy; thường cần restart hoặc rollout để tiến trình nhận giá trị mới.

### 12.6. Immutable deployment configuration

Để tái hiện deployment, có thể gắn version hoặc checksum của config với release. Thay đổi environment nên được quản lý như một thay đổi triển khai có thể audit.

## 13. Environment trong CI/CD

Pipeline thường dùng environment để truyền thông tin build, test và deploy.

### 13.1. Biến theo stage

Build, test và deploy có thể cần các giá trị khác nhau. Không nên dùng chung một credential rộng quyền cho mọi stage nếu có thể tách.

### 13.2. CI-provided variables

CI runner có thể cung cấp branch name, commit ID, build number và workspace path. DSL hoặc build script có thể đọc chúng để gắn metadata vào artifact.

### 13.3. Masking

Nền tảng CI thường có tính năng mask secret trong log, nhưng không nên dựa hoàn toàn vào masking. Ứng dụng vẫn phải tránh in environment hoặc exception chứa secret.

### 13.4. Scope

Biến có thể được đặt ở cấp project, pipeline, job hoặc step. Cần xác định biến nào được truyền đến tiến trình DSL và tránh vô tình kế thừa secret không cần thiết.

### 13.5. Pull request từ nguồn không tin cậy

Pipeline cho mã từ fork hoặc contributor không tin cậy không nên cấp secret production. Generator, test và build script cần chạy với quyền tối thiểu.

### 13.6. Artifact không chứa secret

Không ghi environment vào manifest hoặc generated source. Nếu cần provenance, chỉ lưu tên biến, nguồn cấu hình hoặc version reference đã được phép công khai.

## 14. Phân biệt biến không tồn tại, rỗng và không hợp lệ

Đây là một trong những điểm cần đặc tả rõ trong DSL configuration.

### 14.1. Không tồn tại

Environment lookup không tìm thấy tên. Runtime có thể dùng default, bỏ qua trường optional hoặc báo lỗi nếu required.

### 14.2. Giá trị rỗng

Biến có tồn tại nhưng value là chuỗi rỗng. Với một số trường, chuỗi rỗng hợp lệ; với trường khác, nó tương đương cấu hình thiếu hoặc invalid. Quy tắc cần gắn với schema.

### 14.3. Chỉ có khoảng trắng

Runtime có thể trim trước khi parse, nhưng không nên trim tất cả giá trị một cách mù quáng. Password hoặc token có thể có khoảng trắng có ý nghĩa.

### 14.4. Giá trị không parse được

Nếu APP_PORT=abc, lỗi phải nêu tên biến, kiểu mong đợi và giá trị có thể được hiển thị an toàn. Không nên tự đổi thành 0 hoặc default mà không báo.

### 14.5. Giá trị ngoài miền

APP_PORT=70000 parse được thành Integer nhưng không nằm trong miền port hợp lệ. Type parsing và semantic validation là hai bước riêng.

### 14.6. Default chỉ áp dụng khi nào?

Schema cần nói default có áp dụng khi biến không tồn tại, khi chuỗi rỗng hay cả khi parse thất bại. Thông thường, lỗi parse nên được báo thay vì âm thầm dùng default để tránh che giấu cấu hình sai.

## 15. Validation và chẩn đoán cấu hình

Environment được nạp lúc khởi động cần được xác thực trước khi ứng dụng bắt đầu nhận traffic hoặc thực hiện tác vụ.

### 15.1. Required variables

Kiểm tra tất cả biến bắt buộc và báo cùng lúc nếu có thể. Điều này giúp người vận hành sửa nhiều lỗi trong một lần thay vì khởi động lại liên tục.

### 15.2. Type validation

Parse chuỗi sang kiểu DSL như Integer, Boolean, Duration, URI, enum hoặc list.

### 15.3. Range và format validation

Kiểm tra miền số, định dạng URL nếu có, pattern tên, scheme và các constraint miền.

### 15.4. Cross-field validation

Một số trường chỉ hợp lệ khi đi cùng nhau. Ví dụ bật TLS thì có thể yêu cầu certificate reference; chọn database type PostgreSQL thì URL phải có scheme tương ứng.

### 15.5. Diagnostic có nguồn

Một thông báo nên cho biết tên biến, trường DSL tương ứng, nguồn cấu hình, kiểu hoặc constraint mong đợi và cách khắc phục.

### 15.6. Không tiết lộ secret

Thông báo chỉ nên ghi tên biến và trạng thái. Nếu cần chỉ ra giá trị sai, phải phân loại độ nhạy và che dữ liệu trước khi log.

### 15.7. Fail fast

Nếu cấu hình bắt buộc không hợp lệ, nên dừng khởi động sớm. Chạy ứng dụng với cấu hình thiếu có thể gây lỗi muộn và khó xác định nguyên nhân.

### 15.8. Validation mode

CLI có thể cung cấp lệnh validate config chỉ đọc và báo lỗi, không mở listener hoặc kết nối dịch vụ nếu không cần. Điều này hữu ích trong pipeline.

## 16. Nạp cấu hình và vòng đời tiến trình

Thời điểm đọc environment ảnh hưởng đến khả năng cập nhật và tính nhất quán của cấu hình.

### 16.1. Load at startup

Mô hình đơn giản là đọc environment một lần khi khởi động, tạo immutable configuration object rồi truyền cho các thành phần. Cách này dễ kiểm thử và tránh các module đọc những giá trị khác nhau trong cùng một tiến trình.

### 16.2. Lazy lookup

Một số ứng dụng đọc biến khi cần. Cách này có thể hữu ích cho giá trị thay đổi, nhưng khiến hành vi phụ thuộc thời điểm đọc và khó biết cấu hình hiện tại của toàn ứng dụng.

### 16.3. Reload

Nếu hỗ trợ reload, runtime cần xác định nguồn nào có thể thay đổi, ai kích hoạt reload và cách áp dụng nguyên tử. Environment của process thường không phải nguồn push update tự nhiên; có thể cần restart, signal hoặc config provider riêng.

### 16.4. Atomic configuration snapshot

Khi reload nhiều trường, nên tạo snapshot mới, validate toàn bộ rồi chuyển sang snapshot mới tại một điểm nhất quán. Tránh trạng thái một module dùng host mới nhưng port vẫn cũ trong lúc cập nhật.

### 16.5. Restart required

Một số trường không thể reload an toàn như JVM options, cổng listener hoặc thư viện native. Runtime cần đánh dấu chúng là restart-required.

### 16.6. Rotation và connection pool

Thay credential có thể cần đóng connection cũ và tạo pool mới. Không nên chỉ cập nhật chuỗi password trong config object mà bỏ qua các connection đã được xác thực trước đó.

## 17. Mapping environment vào cấu hình lồng nhau

Environment variable thường là một namespace phẳng. DSL cần quy tắc chuyển tên phẳng thành đường dẫn cấu hình.

### 17.1. Prefix và separator

Ví dụ quy ước:

~~~text
APP_DATABASE_HOST=db.internal
APP_DATABASE_POOL_MAX_SIZE=20
APP_SERVER_PORT=8080
~~~

Prefix APP_ xác định phạm vi; các phần còn lại biểu diễn path. Separator có thể là dấu gạch dưới, nhưng cần tránh nhập nhằng với tên field vốn có dấu gạch dưới.

### 17.2. Mapping tường minh

Một schema có thể khai báo mapping:

~~~text
config database.host from env("DB_HOST")
config database.port from env("DB_PORT")
config server.port from env("APP_PORT")
~~~

Mapping tường minh dễ hiểu và tránh suy đoán tên tự động, nhưng cần duy trì danh sách khai báo.

### 17.3. Mapping tự động

Với quy ước naming ổn định, runtime có thể tự ánh xạ APP_DATABASE_HOST thành database.host. Cần xác định cách xử lý acronym, camelCase, dấu gạch dưới và collision.

### 17.4. Nested map

Nếu cấu hình có map động, có thể dùng prefix như APP_LABELS_ để thu thập các biến con. Cần định nghĩa cách phân biệt key có dấu gạch dưới và key có ký tự đặc biệt.

### 17.5. List index

Một số framework dùng hậu tố số để biểu diễn phần tử list, ví dụ APP_SERVERS_0_HOST. DSL cần quy định index bắt đầu từ 0 hay 1, cách phát hiện phần tử thiếu và thứ tự kết quả.

### 17.6. Collision

Nếu hai field khác nhau chuẩn hóa thành cùng tên environment, schema phải báo lỗi lúc compile hoặc startup. Không nên chọn một field theo thứ tự duyệt không ổn định.

## 18. Environment và DSL schema

Schema giúp mô tả hợp đồng cấu hình giữa file DSL, runtime và môi trường triển khai.

### 18.1. Schema entry

Một entry có thể có tên environment variable, đường dẫn field trong config, kiểu dữ liệu, required/optional, default, constraint, mức độ nhạy cảm, mô tả, ví dụ và profile áp dụng.

### 18.2. Ví dụ schema

~~~yaml
environment:
  - name: APP_PORT
    path: server.port
    type: integer
    required: false
    default: 8080
    minimum: 1
    maximum: 65535
    description: HTTP listening port

  - name: DB_PASSWORD
    path: database.password
    type: secret
    required: true
    sensitive: true
~~~

### 18.3. Sinh tài liệu

Từ schema, toolchain có thể sinh bảng environment variables trong README hoặc deployment guide. Điều này giảm sai lệch giữa implementation và tài liệu vận hành.

### 18.4. Sinh ví dụ cấu hình

Có thể tạo .env.example hoặc manifest mẫu chỉ chứa tên biến và placeholder an toàn. Không lấy giá trị thật từ môi trường đang chạy để sinh ví dụ.

### 18.5. Schema compatibility

Khi đổi tên biến hoặc kiểu, cần migration guide hoặc alias chuyển tiếp. Xóa một biến đang được deployment sử dụng có thể làm các môi trường cũ không khởi động được.

### 18.6. Deprecation

Schema có thể đánh dấu biến cũ deprecated, đưa ra tên mới và phiên bản dự kiến loại bỏ. Runtime có thể chấp nhận biến cũ trong một thời gian và phát warning không chứa giá trị.

## 19. Tính portable giữa các hệ điều hành và shell

Tên và giá trị environment có thể bị ảnh hưởng bởi quy tắc của hệ điều hành, shell và công cụ khởi chạy.

### 19.1. Case sensitivity

Unix-like thường phân biệt APP_PORT với app_port, trong khi Windows thường không. Dùng canonical uppercase và phát hiện tên trùng sau chuẩn hóa giúp project portable hơn.

### 19.2. Ký tự hợp lệ trong tên

Tên environment portable thường dùng chữ cái ASCII, số và dấu gạch dưới; không nên phụ thuộc vào dấu chấm, dấu gạch ngang hoặc Unicode trong tên biến nếu cần chạy đa nền tảng.

### 19.3. Shell expansion

Shell có thể mở rộng $NAME trước khi lệnh được chạy. Khi truyền giá trị có ký tự đặc biệt, cần quoting đúng theo shell. DSL parser và shell parser là hai lớp khác nhau; không nên nhầm cú pháp placeholder trong file với cú pháp shell.

### 19.4. Khoảng trắng và newline

Giá trị environment có thể chứa khoảng trắng và một số nền tảng hỗ trợ newline, nhưng nhiều công cụ không xử lý multiline nhất quán. Với certificate hoặc private key, file mount/secret store thường dễ kiểm soát hơn.

### 19.5. Encoding

Không nên giả định mọi launcher và hệ điều hành dùng cùng encoding cho mọi trường hợp. Giá trị cấu hình văn bản nên được chuẩn hóa và kiểm thử với Unicode nếu miền nghiệp vụ cần.

### 19.6. Giới hạn kích thước

Hệ điều hành và nền tảng có giới hạn về kích thước environment hoặc tổng command/process metadata. Không dùng một biến khổng lồ để truyền toàn bộ cấu hình hay certificate chain.

### 19.7. Path separator

Đường dẫn dùng dấu phân cách khác nhau giữa hệ điều hành. DSL nên dùng path abstraction và chuẩn hóa ở ranh giới filesystem thay vì ghép chuỗi bằng dấu slash tùy tiện.

## 20. Mẫu cấu hình theo môi trường

Một project có thể dùng chung cấu trúc DSL nhưng cung cấp giá trị khác nhau cho từng môi trường.

### 20.1. Development

~~~text
APP_ENV=development
APP_PORT=8080
LOG_LEVEL=DEBUG
DB_HOST=localhost
DB_PORT=5432
DB_NAME=orders_dev
~~~

Development có thể dùng service local, dữ liệu thử và log chi tiết. Secret vẫn nên lấy từ nguồn local an toàn hoặc credential giả.

### 20.2. Test

~~~text
APP_ENV=test
APP_PORT=0
LOG_LEVEL=WARN
DB_HOST=127.0.0.1
DB_PORT=55432
DB_NAME=orders_test
~~~

Test có thể dùng cổng động hoặc database tạm. Runtime cần quy định liệu port 0 có nghĩa yêu cầu hệ điều hành cấp cổng hay không.

### 20.3. Staging

~~~text
APP_ENV=staging
APP_PORT=8080
LOG_LEVEL=INFO
DB_HOST=staging-db.internal
DB_PORT=5432
DB_NAME=orders_stage
~~~

Staging nên gần production về topology và policy nhưng dùng dữ liệu, credential và endpoint riêng.

### 20.4. Production

~~~text
APP_ENV=production
APP_PORT=8080
LOG_LEVEL=INFO
DB_HOST=prod-db.internal
DB_PORT=5432
DB_NAME=orders
~~~

Credential production được cấp qua secret provider hoặc cơ chế an toàn của nền tảng, không đưa vào ví dụ cấu hình hoặc repository.

### 20.5. Không dựa vào tên môi trường để suy đoán mọi giá trị

APP_ENV=production không tự cho biết database host, region hay feature policy. Những giá trị này cần được cung cấp rõ qua config source hoặc secret provider.

## 21. Quản lý cấu hình nhiều instance

Một dịch vụ có nhiều replica cần đảm bảo mỗi instance nhận cấu hình phù hợp và có thể được truy vết.

### 21.1. Đồng nhất cấu hình

Các replica của cùng một release thường cần cùng cấu hình chức năng. Nếu mỗi instance nhận environment khác nhau, hành vi có thể không nhất quán và khó debug.

### 21.2. Instance-specific values

Một số giá trị như hostname, pod name hoặc instance ID có thể khác nhau giữa replica. Cần phân biệt metadata instance với cấu hình nghiệp vụ chung.

### 21.3. Rolling update

Khi thay environment, orchestrator có thể tạo replica mới rồi thay replica cũ. Điều này cho phép chuyển đổi dần nhưng cần tương thích giữa hai cấu hình trong thời gian rollout.

### 21.4. Version cấu hình

Có thể gắn config revision hoặc checksum vào deployment metadata. Khi hai replica hoạt động khác nhau, người vận hành có thể so sánh revision.

### 21.5. Không dùng environment làm kho trạng thái

Environment là input cấu hình, không phải nơi lưu trạng thái nghiệp vụ. Không ghi tiến độ job, sequence number hoặc dữ liệu cần cập nhật liên tục vào environment.

## 22. Tái nạp và cập nhật cấu hình động

Environment truyền thống phù hợp với cấu hình tại thời điểm tạo tiến trình. Cập nhật động cần cơ chế bổ sung.

### 22.1. Restart-based reload

Nền tảng cập nhật environment bằng cách tạo tiến trình hoặc container mới. Đây là cách dễ dự đoán vì cấu hình được đọc lại khi khởi động.

### 22.2. Signal-based reload

Một số ứng dụng nhận signal để đọc lại file cấu hình. Environment của tiến trình vẫn có thể không đổi; signal chỉ kích hoạt reload từ nguồn mà ứng dụng có thể đọc lại.

### 22.3. Config provider

Nếu cần cập nhật liên tục, dùng config provider hoặc remote config service có version và notification. DSL có thể hợp nhất giá trị từ provider theo policy riêng.

### 22.4. Atomic switch

Nạp và validate snapshot mới trước khi chuyển sang dùng. Nếu cấu hình mới sai, giữ snapshot cũ và báo lỗi, thay vì để ứng dụng ở trạng thái nửa cập nhật.

### 22.5. Rollback

Lưu revision trước đó hoặc hỗ trợ chuyển lại deployment cũ. Cấu hình có thể ảnh hưởng schema và side effect; rollback cần xem xét tương thích dữ liệu chứ không chỉ khôi phục chuỗi environment.

### 22.6. Audit thay đổi

Ghi nhận ai thay đổi cấu hình, revision nào được áp dụng, thời điểm và phạm vi instance. Không ghi giá trị secret trong audit log.

## 23. Bảo mật khi sử dụng environment variable

Environment có thể chứa dữ liệu nhạy cảm và được truyền qua nhiều lớp hệ thống.

### 23.1. Least privilege

Chỉ cấp biến và secret mà tiến trình cần. Tách service account và secret scope theo ứng dụng hoặc chức năng.

### 23.2. Không log toàn bộ environment

Dump toàn bộ biến trong startup log hoặc exception có thể làm lộ token, password và thông tin hạ tầng. Nếu cần debug, dùng allowlist tên biến không nhạy cảm và che giá trị.

### 23.3. Sensitive metadata

Schema DSL có thể đánh dấu trường nhạy cảm. Logger, config inspector và report phải tôn trọng metadata đó.

### 23.4. Process inspection

Trên một số hệ thống, người có quyền phù hợp có thể đọc môi trường của tiến trình. Cần dùng quyền hệ điều hành, container isolation và secret delivery mechanism thích hợp.

### 23.5. Crash dump và diagnostic bundle

Crash dump hoặc support bundle có thể chứa environment. Công cụ thu thập cần lọc hoặc bảo vệ những dữ liệu này.

### 23.6. Không đưa secret vào tên biến

Tên biến nên mô tả mục đích như DB_PASSWORD, không chứa giá trị hoặc thông tin bí mật. Tránh tạo tên động từ dữ liệu nhạy cảm.

### 23.7. Rotation và expiration

Credential nên có thời hạn và quy trình rotate. Runtime cần có cách nhận credential mới, tạo lại connection hoặc khởi động lại theo yêu cầu.

### 23.8. Secret scanning

Repository có thể dùng secret scanning để phát hiện credential bị commit. File .env, log, generated config và fixture cần nằm trong phạm vi kiểm soát.

## 24. Quan sát và giải thích cấu hình

Khi ứng dụng chạy sai do environment, người vận hành cần biết biến nào được đọc và giá trị đến từ đâu mà không làm lộ secret.

### 24.1. Config report

Một report an toàn có thể hiển thị:

| Trường | Nguồn | Trạng thái |
|---|---|---|
| server.port | APP_PORT | Đã nạp |
| database.host | DB_HOST | Đã nạp |
| database.password | Secret provider | Đã nạp, giá trị được che |
| logging.level | Default | Dùng giá trị mặc định |

### 24.2. Missing variable diagnostics

Thông báo thiếu biến nên chỉ rõ tên, trường đích và cách cung cấp. Không nên chỉ báo configuration failed chung chung.

### 24.3. Effective configuration

Runtime có thể hiển thị cấu hình hiệu lực đã merge từ nhiều nguồn. Các trường nhạy cảm cần được redacted và quyền xem report phải được kiểm soát.

### 24.4. Provenance

Lưu nguồn của mỗi giá trị như default, file, environment, CLI hoặc secret provider. Provenance giúp giải thích tại sao giá trị có kết quả hiện tại.

### 24.5. Metrics

Có thể theo dõi số lần reload thành công/thất bại, cấu hình thiếu, validation failure và revision đang chạy. Không đưa value của biến vào metric label.

## 25. Kiểm thử cấu hình dùng biến môi trường

Kiểm thử cần xác minh cả việc đọc, parse, precedence, lỗi và tính độc lập giữa các test.

### 25.1. Inject environment

Nên có abstraction hoặc API nhận một map environment để test. Điều này tránh phụ thuộc environment thật của máy chạy test.

### 25.2. Kiểm thử default

Xóa biến khỏi test environment và xác minh default được áp dụng đúng. Kiểm tra riêng trường hợp biến không tồn tại và biến có chuỗi rỗng.

### 25.3. Kiểm thử required

Không cung cấp biến bắt buộc và xác minh runtime trả diagnostic có tên biến, trường đích và exit behavior phù hợp.

### 25.4. Kiểm thử kiểu

Kiểm tra số hợp lệ, số ngoài miền, Boolean không hợp lệ, duration thiếu đơn vị, enum không tồn tại và URI sai scheme.

### 25.5. Kiểm thử precedence

Đặt cùng một trường ở file, environment và CLI. Xác minh nguồn ưu tiên cao nhất thắng theo đặc tả. Kiểm tra merge/replace đối với list và map.

### 25.6. Kiểm thử profile

Chạy với development, test, staging, production và profile không xác định. Kiểm tra feature bị cấm ở production không thể vô tình bật.

### 25.7. Kiểm thử secret redaction

Đưa một giá trị giả nhạy cảm vào test và xác minh nó không xuất hiện trong log, exception, report hoặc telemetry.

### 25.8. Kiểm thử portability

Kiểm tra naming normalization, case collision, path separator và parsing trên các nền tảng được hỗ trợ.

### 25.9. Kiểm thử reload

Nếu hỗ trợ reload, xác minh snapshot cũ vẫn được dùng khi snapshot mới không hợp lệ, và chuyển đổi thành công là nguyên tử.

### 25.10. Không để test phụ thuộc nhau

Environment của tiến trình có thể dùng chung giữa các test trong cùng process. Cần khôi phục giá trị sau test hoặc dùng config provider riêng để test chạy độc lập và song song an toàn.

## 26. Ví dụ tổng hợp: cấu hình dịch vụ đơn hàng

Giả sử một ứng dụng DSL có file cấu hình:

~~~yaml
application:
  name: order-service
  profile: $APP_ENV

server:
  host: 0.0.0.0
  port: $APP_PORT

database:
  url: $DB_URL
  username: $DB_USERNAME
  password: $DB_PASSWORD
  pool:
    maxSize: $DB_POOL_MAX

logging:
  level: $LOG_LEVEL
~~~

Schema DSL quy định:

| Biến | Kiểu | Bắt buộc | Default hoặc constraint |
|---|---|---|---|
| APP_ENV | Enum | Có | development, test, staging, production |
| APP_PORT | Integer | Không | 8080; 1–65535 |
| DB_URL | URI | Có | Scheme PostgreSQL được hỗ trợ |
| DB_USERNAME | String | Có | Không rỗng |
| DB_PASSWORD | Secret | Có | Không hiển thị trong log |
| DB_POOL_MAX | Integer | Không | 20; lớn hơn 0 |
| LOG_LEVEL | Enum | Không | INFO |

### 26.1. Môi trường local

File .env local có thể chứa:

~~~text
APP_ENV=development
APP_PORT=8080
DB_URL=postgresql://localhost:5432/orders_dev
DB_USERNAME=orders_dev
DB_PASSWORD=local-test-secret
DB_POOL_MAX=5
LOG_LEVEL=DEBUG
~~~

File này phải được giữ ngoài repository nếu chứa credential. .env.example chỉ nên có placeholder.

### 26.2. Môi trường production

Nền tảng deploy cung cấp APP_ENV, APP_PORT, DB_URL, DB_USERNAME, DB_POOL_MAX và LOG_LEVEL. DB_PASSWORD được lấy từ secret provider hoặc secret injection được kiểm soát.

### 26.3. Nạp và kiểm tra

Runtime đọc cấu hình theo thứ tự đã định nghĩa, parse kiểu, kiểm tra profile, port và pool size. Nếu thiếu DB_URL hoặc DB_PASSWORD, ứng dụng dừng trước khi mở listener.

### 26.4. Báo lỗi an toàn

Thông báo có thể ghi DB_POOL_MAX must be a positive integer hoặc DB_PASSWORD is required. Không ghi nội dung DB_PASSWORD hoặc toàn bộ connection URL nếu URL có thể chứa credential.

### 26.5. Thay đổi giá trị

Nếu đổi APP_PORT, thường cần tạo tiến trình/container mới để listener bind cổng mới. Nếu đổi DB_PASSWORD, runtime cần thực hiện quy trình cập nhật credential và connection pool phù hợp.

## 27. Những sai lầm thường gặp

### 27.1. Coi mọi giá trị environment là chuỗi hợp lệ

Environment trả text, nhưng DSL có thể yêu cầu kiểu cụ thể. Cần parse và validate thay vì truyền chuỗi xuống mọi thành phần.

### 27.2. Không phân biệt thiếu với rỗng

Biến không tồn tại và biến có giá trị rỗng có thể mang ý nghĩa khác nhau. Schema phải quy định từng trường.

### 27.3. Dùng default để che lỗi

Nếu biến bắt buộc bị thiếu, dùng một default giả có thể khiến ứng dụng kết nối nhầm dịch vụ hoặc chạy với quyền sai. Required field nên fail fast.

### 27.4. Không quy định precedence

File, environment và CLI có thể cùng đặt một trường. Nếu không có thứ tự ưu tiên, hành vi phụ thuộc implementation hoặc thứ tự load.

### 27.5. Nhồi cấu hình phức tạp vào một biến

Một biến chứa JSON hoặc chuỗi delimiter dài khó đọc, khó validate và dễ lỗi escaping. Dùng file cấu hình có cấu trúc khi dữ liệu phức tạp.

### 27.6. Commit file .env thật

Credential có thể bị lộ trong repository và lịch sử Git. Dùng file mẫu không nhạy cảm, ignore file thật và rotate secret nếu đã lộ.

### 27.7. In toàn bộ environment để debug

Startup log hoặc crash report có thể tiết lộ token, password và endpoint nội bộ. Dùng allowlist và redaction.

### 27.8. Giả định environment tự cập nhật

Tiến trình thường đọc environment tại thời điểm khởi chạy. Thay biến ở hệ thống điều phối không tự thay đổi snapshot của tiến trình đang chạy.

### 27.9. Dùng tên biến quá chung

Tên như PORT hoặc USER có thể xung đột với môi trường khác. Dùng prefix riêng của ứng dụng.

### 27.10. Bỏ qua khác biệt hệ điều hành

Case sensitivity, ký tự tên, quoting và path khác nhau giữa Windows và Unix-like. Quy ước portable cần được kiểm thử.

### 27.11. Truyền secret qua command line

Command line có thể xuất hiện trong shell history hoặc process inspection. Ưu tiên secret store hoặc cơ chế credential an toàn.

### 27.12. Không kiểm tra cấu hình trước khi phục vụ request

Lỗi cấu hình có thể xuất hiện muộn khi người dùng đầu tiên gọi chức năng. Validate tất cả trường bắt buộc trước khi ứng dụng sẵn sàng.

## 28. Nguyên tắc thiết kế environment configuration cho DSL

Một DSL cấu hình tốt cần biến environment thành một giao diện có schema và semantics rõ ràng.

### 28.1. Khai báo hợp đồng

Định nghĩa tên, kiểu, required/optional, default, constraint và mô tả cho mỗi biến. Tránh để tên biến chỉ tồn tại trong code mà không có tài liệu.

### 28.2. Naming convention ổn định

Dùng prefix ứng dụng, canonical uppercase và quy tắc ánh xạ path rõ ràng. Phát hiện collision trước khi runtime hoạt động.

### 28.3. Parse nghiêm ngặt

Chuyển text sang kiểu DSL một cách tường minh. Phân biệt missing, empty, malformed và out-of-range.

### 28.4. Precedence được công bố

Xác định thứ tự giữa default, file, profile, environment, CLI và remote provider. Quy định merge hay replace cho collection.

### 28.5. Secret có nguồn riêng

Dùng secret manager hoặc secret reference khi có thể. Nếu phải dùng environment, kiểm soát quyền và tuyệt đối không log value.

### 28.6. Validate trước khi chạy

Kiểm tra required variable, kiểu, miền giá trị và quan hệ giữa các trường trước khi mở listener hoặc xử lý job.

### 28.7. Snapshot nhất quán

Nạp và validate thành một config object nhất quán. Nếu reload, xây snapshot mới rồi chuyển đổi nguyên tử.

### 28.8. Portable

Chọn quy tắc tên và encoding phù hợp nhiều hệ điều hành. Không phụ thuộc vào shell expansion hoặc path separator cụ thể.

### 28.9. Quan sát an toàn

Cho biết nguồn và trạng thái của cấu hình, nhưng che giá trị nhạy cảm. Không đưa secret vào metric, report hoặc crash bundle.

### 28.10. Tài liệu và kiểm thử cùng schema

Sinh .env.example, README và config reference từ schema. Kiểm thử default, precedence, profile, redaction và reload dựa trên cùng contract.

## 29. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Environment Variable | Cặp tên và giá trị được cung cấp cho một tiến trình |
| Process Environment | Tập biến môi trường mà tiến trình có thể đọc |
| Environment Lookup | Thao tác tìm giá trị theo tên biến |
| Interpolation | Thay placeholder trong cấu hình bằng giá trị được tham chiếu |
| Environment Prefix | Tiền tố dùng để nhóm biến của một ứng dụng hoặc module |
| Configuration Schema | Hợp đồng mô tả tên, kiểu, default và constraint của cấu hình |
| Type Coercion | Chuyển giá trị văn bản sang kiểu dữ liệu DSL |
| Required Variable | Biến bắt buộc phải được cung cấp |
| Default Value | Giá trị dùng khi nguồn cấu hình không cung cấp giá trị |
| Configuration Precedence | Thứ tự ưu tiên giữa nhiều nguồn cấu hình |
| Profile | Tập cấu hình theo môi trường hoặc mục đích chạy |
| Dotenv | Công cụ hoặc quy ước nạp biến từ file .env |
| Secret Manager | Dịch vụ quản lý credential và dữ liệu nhạy cảm |
| Secret Reference | Tên hoặc đường dẫn tham chiếu đến secret |
| Redaction | Che giá trị nhạy cảm trước khi ghi log hoặc report |
| Config Snapshot | Bản cấu hình nhất quán được dùng trong một thời điểm |
| Config Reload | Quá trình nạp và áp dụng cấu hình mới |
| ConfigMap | Cơ chế cung cấp cấu hình không nhạy cảm trong Kubernetes |
| Rolling Update | Thay instance theo từng đợt để duy trì dịch vụ |
| Provenance | Thông tin nguồn gốc của một giá trị cấu hình |
| Least Privilege | Chỉ cấp quyền và secret tối thiểu cần thiết |
| Environment Collision | Hai trường cấu hình ánh xạ đến cùng một tên biến |

Biến môi trường là một giao diện đơn giản và phổ biến để truyền cấu hình từ nền tảng chạy vào tiến trình DSL. Để sử dụng an toàn, DSL cần định nghĩa tên biến, kiểu dữ liệu, default, required status, interpolation, precedence và cách báo lỗi. Các giá trị nhạy cảm cần được quản lý qua secret provider hoặc cơ chế bảo vệ phù hợp, còn cấu hình phải được parse và validate trước khi ứng dụng phục vụ công việc. Khi schema, naming convention, profile, container integration, reload policy và kiểm thử được thiết kế nhất quán, cùng một project DSL có thể chạy trên nhiều môi trường mà vẫn giữ được tính dự đoán, khả năng truy vết và an toàn vận hành.

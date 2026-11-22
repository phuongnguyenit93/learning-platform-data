# Xử lý khóa trùng, sai thụt lề và khác biệt giữa trống với null trong Spring Boot

## Mục tiêu

Các file **application.properties** và **application.yml** là hai cách phổ biến để đưa cấu hình bên ngoài mã Java vào Spring Boot. Cùng một ứng dụng có thể chạy bình thường ở môi trường này nhưng khởi động lỗi hoặc nhận sai giá trị ở môi trường khác chỉ vì một khóa xuất hiện hai lần, một dòng YAML được đặt sai cấp, hoặc một giá trị được viết rỗng thay vì viết rõ **null**.

Bài học này tập trung vào ba nhóm tình huống:

1. **Khóa trùng:** một tên thuộc tính được khai báo lặp trong cùng file, hoặc cùng thuộc tính xuất hiện ở nhiều nguồn có mức ưu tiên khác nhau.
2. **Sai thụt lề:** cấu trúc YAML bị biến đổi hoặc không thể phân tích vì các dòng không nằm đúng cấp.
3. **Trống và null:** những cách viết trông tương tự nhưng có thể tạo ra chuỗi rỗng, giá trị null, khoảng trắng, chuỗi chữ “null” hoặc một thuộc tính không tồn tại.

Sau bài học, người đọc có thể giải thích vì sao Spring Boot chọn một giá trị, viết cấu hình ít gây hiểu nhầm và xác minh kết quả bằng **Environment**, **@ConfigurationProperties** và thông báo lỗi khi khởi động.

## 1. Cần phân biệt ba tầng của vấn đề

Khi nghe “cấu hình bị trùng”, hãy xác định trùng ở đâu trước khi sửa:

| Tình huống | Ví dụ | Bản chất |
| --- | --- | --- |
| Cùng khóa lặp trong một file .properties | Hai dòng app.mode=... | Một nguồn khai báo lại cùng khóa |
| Cùng khóa mapping lặp trong một tài liệu YAML | Hai mục app: ngang cấp | Trùng khóa trong cấu trúc YAML, có thể bị parser từ chối |
| Cùng tên thuộc tính ở nhiều nguồn | application.yml và biến môi trường | Spring chọn nguồn có độ ưu tiên cao hơn |
| Hai đường dẫn YAML khác nhau vì thụt lề | app.cache.ttl và app.ttl | Hai khóa khác nhau, dù tên lá cùng là ttl |
| Một giá trị có vẻ rỗng | app.name=, app.name: null | Phải xem cú pháp, kiểu dữ liệu và cơ chế nạp cấu hình |

Ba tầng có trách nhiệm khác nhau:

- **Parser của định dạng** đọc văn bản .properties hoặc YAML và tạo ra dữ liệu có cấu trúc.
- **Bộ nạp cấu hình của Spring Boot** chuyển dữ liệu thành các PropertySource, có thể làm phẳng cây YAML thành tên thuộc tính như app.cache.ttl.
- **Spring Environment và Binder** chọn giá trị theo độ ưu tiên, rồi chuyển thành kiểu mà bean hoặc mã Java yêu cầu.

Một file YAML có cú pháp hợp lệ chưa chắc có cấu trúc đúng với ứng dụng. Tương tự, một file chứa khóa hợp lệ chưa chắc giá trị của nó được chọn khi Spring có nguồn cấu hình ưu tiên cao hơn.

## 2. Khóa trùng trong application.properties

Xét file sau:

~~~properties
app.mode=standard
app.worker-count=2
app.mode=fast
~~~

Cú pháp Java properties cho phép các dòng cùng tên khóa được đọc tuần tự; với cách nạp thông dụng, khai báo sau có thể thay thế giá trị khai báo trước, vì vậy app.mode thường nhận **fast**. Dù vậy, **không nên sử dụng khai báo trùng để thiết kế cơ chế ưu tiên**: người sửa file dễ bỏ sót dòng thứ hai, công cụ kiểm tra có thể cảnh báo, và hành vi của một bộ nạp tùy chỉnh có thể khác.

Cách viết rõ ràng hơn:

~~~properties
app.mode=fast
app.worker-count=2
~~~

Nếu cần cấu hình khác nhau theo môi trường, hãy tách giá trị bằng profile hoặc nguồn cấu hình riêng, thay vì đặt hai khai báo cùng khóa trong một file:

~~~properties
# application.properties
app.mode=standard
~~~

~~~properties
# application-dev.properties
app.mode=fast
~~~

Khi profile **dev** được kích hoạt và dữ liệu cấu hình được nạp theo cơ chế mặc định, giá trị trong file theo profile có thể ghi đè giá trị cơ sở. Đây là **ưu tiên giữa các nguồn/nhóm tài liệu cấu hình**, khác với việc lặp cùng một dòng trong cùng file.

Một cách khác gây nhầm lẫn là tên khóa có khoảng trắng hoặc dấu phân cách:

~~~properties
app.mode = fast
app.timeout: 10s
~~~

Đối với định dạng .properties, dấu **=** và dấu **:** đều có thể phân tách khóa và giá trị; khoảng trắng quanh dấu phân tách được xử lý theo quy tắc của định dạng. Vì vậy hai cách viết **app.timeout=10s** và **app.timeout: 10s** biểu diễn cùng tên khóa, không phải hai namespace khác nhau.

Nên dùng một quy ước nhất quán, chẳng hạn **app.timeout=10s**, để dễ tìm trùng bằng công cụ soạn thảo và review.

## 3. Khóa trùng trong YAML: cùng cấp khác với ghi đè

YAML biểu diễn dữ liệu bằng mapping và các cấp lồng nhau. Khóa lặp ở **cùng mapping trong cùng một tài liệu YAML** là tình huống khác với nhiều PropertySource của Spring:

~~~yaml
# Không nên viết: khóa app xuất hiện hai lần trong cùng tài liệu
app:
  mode: standard

app:
  worker-count: 2
~~~

Tùy parser và cấu hình của phiên bản thư viện, duplicate key có thể gây lỗi ngay khi đọc YAML; không được giả định rằng mục app thứ hai sẽ tự động gộp với mục đầu. Spring Boot sử dụng cơ chế nạp YAML của chính nó, và người học cần xem lỗi của phiên bản thực tế khi gặp tệp trùng khóa. Không dựa vào quy tắc “dòng sau thắng” của .properties cho YAML.

Gộp các phần của cùng một mapping thành một cấu trúc duy nhất:

~~~yaml
app:
  mode: standard
  worker-count: 2
~~~

Khóa trùng có thể nằm sâu hơn, ngay cả khi chỉ xuất hiện một mục gốc:

~~~yaml
app:
  cache:
    ttl: 10s
    enabled: true
    ttl: 30s
~~~

Ở đây **ttl** xuất hiện hai lần trong mapping **cache**. Cách sửa là quyết định đúng một giá trị:

~~~yaml
app:
  cache:
    ttl: 30s
    enabled: true
~~~

### 3.1. Không nhầm với nhiều tài liệu YAML

Trong YAML, **---** đánh dấu điểm bắt đầu một tài liệu mới. Spring Boot hỗ trợ tài liệu cấu hình nhiều đoạn và điều kiện kích hoạt theo profile:

~~~yaml
app:
  mode: standard
---
spring:
  config:
    activate:
      on-profile: dev
app:
  mode: fast
~~~

Hai mục **app.mode** ở đây nằm trong **hai tài liệu YAML khác nhau**, không phải hai khóa lặp trong cùng một mapping. Khi profile **dev** hoạt động, tài liệu thứ hai có thể ghi đè cấu hình cơ sở theo quy tắc xử lý config data của Spring Boot. Khi dev không hoạt động, tài liệu có điều kiện không được áp dụng.

Điều kiện kích hoạt và thứ tự các tài liệu là một phần của bài toán ưu tiên cấu hình; không sửa một tình huống nhiều tài liệu hợp lệ thành một mapping duy nhất nếu việc đó làm mất hành vi theo profile.

### 3.2. Tên khác dạng vẫn có thể hướng đến cùng thuộc tính

Hãy quan sát hai tên:

~~~yaml
app:
  report-timeout: 10s
  reportTimeout: 20s
~~~

Ở cấp cấu trúc YAML, đây là hai chuỗi khóa khác nhau. Tuy nhiên Spring Boot có **relaxed binding** khi bind vào @ConfigurationProperties; một số dạng tên kebab-case và camelCase có thể liên hệ với cùng thuộc tính Java. Không dùng nhiều cách viết cho cùng khái niệm rồi trông chờ quy tắc thắng-thua rõ ràng.

Quy ước dễ đọc: đặt tên khóa cấu hình trong file bằng dạng canonical **chữ thường, kebab-case**, chẳng hạn **app.report-timeout**, và chỉ khai báo một nơi trong cùng nguồn.

## 4. Thụt lề YAML quyết định tên thuộc tính

YAML dùng khoảng trắng đầu dòng để biểu diễn quan hệ cha-con. Với cấu hình:

~~~yaml
app:
  cache:
    enabled: true
    ttl: 30s
  name: demo
~~~

Spring Boot có thể làm phẳng nội dung thành các tên thuộc tính:

~~~properties
app.cache.enabled=true
app.cache.ttl=30s
app.name=demo
~~~

Hình dung theo cây:

~~~text
app
├── cache
│   ├── enabled
│   └── ttl
└── name
~~~

Bây giờ đổi vị trí một dòng:

~~~yaml
app:
  cache:
    enabled: true
  ttl: 30s
  name: demo
~~~

File này vẫn có thể là **YAML hợp lệ**, nhưng tên của ttl đã đổi thành **app.ttl**. Bean đang chờ **app.cache.ttl** sẽ không tìm thấy giá trị ở khóa mong đợi. Đây là một trong những lỗi khó thấy nhất vì ứng dụng có thể không báo lỗi parser.

Phân biệt hai loại sai thụt lề:

- **Sai cấp nhưng hợp lệ:** YAML đọc được, cấu trúc property thay đổi và binding không nhận đúng dữ liệu.
- **Thụt lề không hợp lệ:** parser từ chối tệp, ứng dụng có thể dừng trong giai đoạn nạp cấu hình.

Ví dụ sai cú pháp cấu trúc:

~~~yaml
app:
  database:
    host: localhost
   port: 5432
~~~

Dòng **port** có khoảng trắng đầu dòng không phù hợp với mapping đang mở. Parser thường báo lỗi liên quan vị trí dòng/cột, thay vì tạo ra một cây thuộc tính rõ ràng.

Bản sửa:

~~~yaml
app:
  database:
    host: localhost
    port: 5432
~~~

### 4.1. Không có yêu cầu bắt buộc “luôn hai dấu cách”

YAML không quy định mọi cấp phải đúng hai dấu cách. Điều cần thiết là các phần tử cùng cấp có thụt lề nhất quán và quan hệ cha-con rõ ràng. Trong dự án thực tế, **hai dấu cách mỗi cấp** là quy ước hữu ích vì dễ quan sát bằng mắt.

~~~yaml
# Hai dấu cách/cấp: rõ ràng
app:
  database:
    host: localhost
    port: 5432
~~~

Không trộn **tab** với khoảng trắng để thụt lề cấu trúc YAML; tab không phải ký tự thụt lề hợp lệ theo cú pháp YAML. Bật chế độ hiển thị whitespace trong IDE nếu lỗi chỉ xảy ra khi copy cấu hình từ tài liệu hoặc đoạn chat.

### 4.2. Dấu gạch ngang của danh sách cũng phụ thuộc thụt lề

Ví dụ đúng:

~~~yaml
app:
  servers:
    - host: alpha.local
      port: 8080
    - host: beta.local
      port: 8081
~~~

**servers** là danh sách hai phần tử, mỗi phần tử là mapping có host và port. Khi bind, các phần tử thường tương ứng với **app.servers[0].host**, **app.servers[0].port** và tương tự cho phần tử thứ hai.

Một lỗi thường thấy:

~~~yaml
app:
  servers:
    - host: alpha.local
    port: 8080
~~~

**port** không ở đúng cấp của thuộc tính trong phần tử danh sách. Tùy vị trí cụ thể, parser có thể báo lỗi hoặc cấu trúc nhận được không đúng. Đối với list of objects, các thuộc tính của cùng phần tử phải được căn theo phần nội dung sau dấu **-**.

## 5. Trống, null, khoảng trắng và chữ “null” là bốn ý nghĩa khác nhau

Dưới đây là những cách biểu diễn dễ nhầm lẫn trong YAML:

~~~yaml
demo:
  missing-value:
  explicit-null: null
  tilde-null: ~
  empty-string: ""
  empty-single-quoted: ''
  blank-string: " "
  literal-null: "null"
  empty-list: []
  empty-map: {}
~~~

Về **ngữ nghĩa YAML trước khi Spring Boot nạp và bind**:

| Cách viết | Ý nghĩa trong dữ liệu YAML |
| --- | --- |
| missing-value: | Giá trị scalar không được cung cấp, thường được parse là null |
| explicit-null: null | Giá trị null |
| tilde-null: ~ | Giá trị null |
| empty-string: "" | Chuỗi rỗng, độ dài 0 |
| empty-single-quoted: '' | Chuỗi rỗng, độ dài 0 |
| blank-string: " " | Chuỗi có một dấu cách |
| literal-null: "null" | Chuỗi gồm bốn ký tự n-u-l-l |
| empty-list: [] | Danh sách rỗng |
| empty-map: {} | Mapping rỗng |

Tên **missing-value** trong ví dụ là tên minh họa; về cú pháp YAML, nó vẫn là một **khóa có scalar rỗng**, khác với việc khóa hoàn toàn không xuất hiện trong file.

Đừng dùng **null** như một cách viết tắt chắc chắn cho chuỗi rỗng. Đừng dùng chuỗi **"null"** để biểu diễn giá trị null: dấu nháy khiến đó trở thành văn bản.

Một khác biệt khác: trong file YAML, giá trị không đặt trong dấu nháy như **true**, **42** hoặc **null** được parser nhận diện theo quy tắc scalar YAML. Dùng dấu nháy khi cần khẳng định giá trị là chuỗi, nhất là với dữ liệu có ý nghĩa nghiệp vụ.

### 5.1. Đối chiếu với application.properties

~~~properties
demo.empty=
demo.empty-also
demo.literal-null=null
demo.literal-tilde=~
demo.with-space= 
~~~

Ở định dạng .properties:

- **demo.empty=** là chuỗi rỗng.
- **demo.empty-also** là khóa không có phần giá trị; cách đọc Java properties thông dụng coi giá trị là chuỗi rỗng.
- **demo.literal-null=null** là chuỗi văn bản **null**, không có kiểu null riêng của YAML.
- **demo.literal-tilde=~** là chuỗi **~**.
- **demo.with-space= ** phải được đánh giá theo cách parser .properties xử lý khoảng trắng sau dấu phân tách; không nên dùng một khoảng trắng không hiển thị để gửi tín hiệu nghiệp vụ.

Đặc biệt, dấu nháy trong .properties **không có chức năng giống dấu nháy của YAML**. Ví dụ:

~~~properties
demo.name=""
~~~

Trong cú pháp .properties thông dụng, dấu nháy kép là ký tự của giá trị; đừng suy đoán rằng nó tạo chuỗi rỗng giống **demo.name: ""** trong YAML. Muốn chuỗi rỗng trong .properties, viết **demo.name=**.

### 5.2. Null ở YAML không phải lệnh “xóa” một nguồn khác

Giả sử cùng một thuộc tính được khai báo ở hai nguồn:

~~~yaml
# Cấu hình cơ sở
app:
  greeting: hello
~~~

~~~yaml
# Cấu hình bổ sung có độ ưu tiên cao hơn
app:
  greeting: null
~~~

Có thể nảy sinh mong đợi rằng **null** sẽ xóa **hello**. Kết luận đó không an toàn. Spring Environment sử dụng các PropertySource, và cách một null scalar được chuyển vào PropertySource cũng như cách PropertyResolver xử lý null cần được xét theo phiên bản/bộ nạp thực tế. Thông thường, null không đóng vai trò một “tombstone” có thể bảo đảm che khuất mọi giá trị ở nguồn ưu tiên thấp hơn.

Nguyên tắc thiết kế là: **đừng coi null là cơ chế xóa hoặc tắt cấu hình qua lớp ưu tiên**. Khi nghiệp vụ cần vô hiệu hóa tính năng, khai báo một thuộc tính có ý nghĩa rõ, ví dụ:

~~~yaml
app:
  notifications:
    enabled: false
~~~

Khi cần xóa một phần tử hoặc thay danh sách/map giữa các nguồn cấu hình, hãy kiểm tra quy tắc binding cho đúng kiểu dữ liệu; không thể suy rộng quy tắc của một String scalar sang collection.

## 6. Khóa không có, khóa rỗng và giá trị mặc định

Giả sử ứng dụng cần cấu hình **app.display-name**. Ba cách viết sau truyền các ý định khác nhau:

~~~yaml
# Tình huống A: không có khóa app.display-name
app:
  enabled: true
~~~

~~~yaml
# Tình huống B: có khóa với chuỗi rỗng
app:
  display-name: ""
  enabled: true
~~~

~~~yaml
# Tình huống C: có khóa với chuỗi cụ thể
app:
  display-name: "Demo"
  enabled: true
~~~

Đối với truy cập trực tiếp bằng **Environment.getProperty("app.display-name")**, tình huống A thường cho biết không tìm thấy thuộc tính, còn B chủ đích cung cấp chuỗi rỗng, nếu nguồn nạp giữ nguyên giá trị như vậy. Tình huống C cung cấp **Demo**.

Cần tách bốn câu hỏi khi xử lý:

1. Khóa có mặt trong văn bản không?
2. Parser định dạng hiểu giá trị là kiểu gì?
3. Bộ nạp đã xuất bản giá trị gì vào Spring PropertySource?
4. Bean hoặc mã Java chuyển đổi và sử dụng giá trị đó ra sao?

Bốn kết quả có thể khác nhau. Ví dụ, một bean dùng kiểu **Duration**, **Integer** hoặc enum có thể bị lỗi chuyển đổi ở những giá trị mà một bean kiểu **String** vẫn nhận được.

### 6.1. Placeholder có mặc định và chuỗi rỗng

Spring hỗ trợ placeholder dùng giá trị mặc định, ví dụ:

~~~yaml
app:
  display-name: "${APP_DISPLAY_NAME:Demo}"
  callback-url: "${APP_CALLBACK_URL:}"
~~~

Trong cấu hình này:

- Nếu thuộc tính **APP_DISPLAY_NAME** không được giải quyết từ các nguồn, placeholder dùng giá trị mặc định **Demo**.
- Nếu **APP_CALLBACK_URL** không được giải quyết, placeholder dùng chuỗi rỗng từ phần sau dấu **:**.
- Nếu thuộc tính được giải quyết thành **chuỗi rỗng có chủ đích**, đừng mặc nhiên cho rằng phần mặc định của placeholder sẽ được chọn. Mặc định dành cho tình huống không tìm được giá trị qua cơ chế phân giải, không phải một quy tắc thay mọi chuỗi rỗng.

Đối với môi trường triển khai, nên định nghĩa rõ nhu cầu nghiệp vụ: giá trị không có có dùng default không; rỗng có được phép không; hay ứng dụng phải từ chối khởi động.

### 6.2. Dùng validation để tránh chạy với cấu hình mơ hồ

Ví dụ một tên hiển thị bắt buộc có nội dung:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotBlank String displayName
) {
}
~~~

Khi ứng dụng có hỗ trợ Jakarta Bean Validation phù hợp và đăng ký class này qua **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties**, @NotBlank giúp phát hiện giá trị null, rỗng hoặc chỉ toàn khoảng trắng cho thuộc tính bắt buộc.

Nếu nghiệp vụ **cho phép** chuỗi rỗng, không đặt @NotBlank cho thuộc tính ấy. Nếu nghiệp vụ cần phân biệt “không khai báo” với “đã khai báo chuỗi rỗng”, hãy xây dựng quy tắc rõ ngay tại lớp cấu hình và kiểm tra các nguồn thực tế, thay vì dựa vào cảm giác từ cách viết YAML.

## 7. Giá trị được bind theo cấu trúc, không chỉ theo dòng văn bản

Xét Java record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(boolean enabled, Duration ttl) {
}
~~~

Cấu hình tương ứng:

~~~yaml
app:
  cache:
    enabled: true
    ttl: 20s
~~~

Nếu thay cấu hình bằng:

~~~yaml
app:
  cache:
  enabled: true
  ttl: 20s
~~~

Hai dòng **enabled** và **ttl** giờ đã thuộc **app.enabled** và **app.ttl**. Đối với CacheProperties, **app.cache.enabled** và **app.cache.ttl** không còn được khai báo như trước; kết quả bind phụ thuộc giá trị mặc định, nguồn khác và điều kiện bắt buộc của kiểu dữ liệu.

Với **boolean** nguyên thủy, giá trị mặc định Java có thể khiến lỗi thiếu cấu hình khó nhận ra hơn một thuộc tính bắt buộc kiểu đối tượng. Dùng validation/kiểm tra khởi động thích hợp cho những cờ hoặc giá trị mà ứng dụng bắt buộc phải có.

### 7.1. Cấu trúc sai có thể gây lỗi chuyển kiểu

Một trường hợp khác:

~~~yaml
app:
  cache: fast
~~~

Nếu ứng dụng cần **app.cache.ttl**, scalar **fast** ở app.cache không thể tự biến thành một object có thuộc tính ttl. Tùy lớp cấu hình và cơ chế binding, hệ quả có thể là lỗi bind, thuộc tính không được cung cấp hoặc giá trị mặc định được sử dụng. Đọc thông báo lỗi với tên thuộc tính đầy đủ sẽ giúp xác định sai kiểu hay sai cấp.

### 7.2. Khóa lặp trong nhiều nguồn hợp lệ là bài toán ưu tiên

Ví dụ:

~~~yaml
# application.yml
app:
  cache:
    ttl: 20s
~~~

Và đặt biến môi trường:

~~~bash
APP_CACHE_TTL=40s java -jar demo.jar
~~~

Spring Boot có thể chọn **40s** vì biến môi trường thông thường có độ ưu tiên cao hơn config data trong file. Đây **không phải duplicate key lỗi YAML**; cùng tên thuộc tính nằm ở hai PropertySource khác nhau.

Nếu tiếp tục dùng:

~~~bash
APP_CACHE_TTL=40s java -Dapp.cache.ttl=50s -jar demo.jar --app.cache.ttl=60s
~~~

Trong cơ chế ưu tiên mặc định của những nguồn đang xét, tham số Spring Boot **--app.cache.ttl=60s** thắng system property **50s**, biến môi trường **40s** và file YAML **20s**.

Cần tách **“khóa xuất hiện nhiều lần trong một mapping YAML”** khỏi **“thuộc tính có nhiều ứng viên tại các nguồn hợp lệ”**. Cách sửa của hai tình huống khác nhau: tình huống đầu là sửa tài liệu; tình huống sau là xác định thứ tự ưu tiên và ý định triển khai.

## 8. Đọc lỗi khi Spring Boot nạp cấu hình

Khi ứng dụng không khởi động hoặc nhận giá trị bất ngờ, đọc lỗi theo giai đoạn:

| Dấu hiệu | Nhóm vấn đề đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Lỗi parse YAML, chỉ đến dòng/cột | Cú pháp hoặc thụt lề không hợp lệ; có thể trùng khóa | Mở đúng file/dòng; kiểm tra các mapping gần đó |
| Ứng dụng chạy nhưng bean nhận null/default | Sai cấp, sai tên thuộc tính hoặc bị nguồn khác chi phối | So sánh tên đầy đủ với @ConfigurationProperties |
| Lỗi bind/conversion | Giá trị rỗng, “null” dạng chuỗi hoặc kiểu không khớp | Xem kiểu Java và giá trị thực của thuộc tính |
| Lỗi validation @NotBlank | Thuộc tính bắt buộc thiếu, rỗng hoặc toàn khoảng trắng | Cấp giá trị hợp lệ hoặc sửa hợp đồng cấu hình |
| Chỉ sai ở một profile | Tài liệu YAML theo profile hoặc file theo profile có giá trị khác | Kiểm tra profile và thứ tự config data |
| Một lần triển khai thắng giá trị trong file | Biến môi trường, -D hoặc -- cùng khóa | Liệt kê nguồn đang hoạt động theo độ ưu tiên |

Đừng suy đoán toàn bộ lỗi từ một thông báo “failed to bind”. Cần đọc tên property, nguồn gốc cấu hình nếu được cung cấp, kiểu đích và nguyên nhân lồng bên trong exception.

### 8.1. Kiểm tra giá trị từ Spring Environment

Có thể tạo đoạn mã chẩn đoán tạm thời hoặc chỉ bật trong môi trường phát triển:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ConfigProbe implements ApplicationRunner {
    private final Environment environment;

    ConfigProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String value = environment.getProperty("app.cache.ttl");
        System.out.println("app.cache.ttl = " + value);
    }
}
~~~

Kết quả từ Environment phản ánh cơ chế phân giải cấu hình của Spring. Nó hữu ích hơn việc chỉ đọc file application.yml, vì không loại trừ biến môi trường, JVM system property hoặc tham số ứng dụng có cùng khóa.

Tuy nhiên, **null** từ Environment.getProperty(...) không tự chứng minh rằng một dòng YAML đã viết null: cũng có thể do khóa không tồn tại, sai tên, sai cấp hoặc không được nguồn đang hoạt động công bố. Muốn biết nguyên nhân, cần đối chiếu nguồn đã nạp và kiểu binding thực tế.

### 8.2. Kiểm tra sự hiện diện, nhưng không làm lộ giá trị nhạy cảm

Khi cần tìm nguồn cấu hình trong môi trường phát triển, có thể dùng ConfigurableEnvironment để xem tên các PropertySource:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

for (PropertySource<?> source : environment.getPropertySources()) {
    System.out.println(source.getName());
}
~~~

Ví dụ trên đòi biến **environment** có kiểu **ConfigurableEnvironment** trong ngữ cảnh sử dụng. Không in toàn bộ giá trị của mọi nguồn vì chúng có thể chứa mật khẩu, token, kết nối cơ sở dữ liệu hoặc thông tin nhạy cảm.

Khi Spring Boot Actuator được triển khai và được cấu hình bảo vệ phù hợp, endpoint thông tin môi trường có thể hỗ trợ truy nguyên nguồn thuộc tính; nhiều giá trị sẽ được che. Không mở công khai endpoint chỉ để gỡ lỗi YAML.

## 9. Tình huống tổng hợp: một file sai theo ba cách

Giả sử có đoạn cấu hình sau:

~~~yaml
app:
  mail:
    host: smtp.example.test
    port: 2525
  retries: 3
  retries: 5
  sender-name:
  mail:
    tls-enabled: true
~~~

Người viết mong muốn:

- Mail server có host, port và tls-enabled.
- retries bằng 5.
- sender-name là chuỗi rỗng, nghĩa là chưa có tên hiển thị.

Nhưng văn bản có ba vấn đề:

1. Mapping **mail** xuất hiện hai lần ở cùng cấp **app**. Không nên kỳ vọng parser sẽ gộp host/port với tls-enabled.
2. **retries** xuất hiện hai lần trong cùng mapping. Không nên dùng lặp khóa để ghi đè.
3. **sender-name:** là scalar không cung cấp, có ý nghĩa YAML null; nó không diễn đạt rõ yêu cầu chuỗi rỗng.

Bản viết lại thể hiện ý định trực tiếp:

~~~yaml
app:
  mail:
    host: smtp.example.test
    port: 2525
    tls-enabled: true
  retries: 5
  sender-name: ""
~~~

Nếu sender-name thực sự là thông tin **bắt buộc**, chọn một chuỗi có nghĩa hoặc khai báo quy tắc validation; việc dùng chuỗi rỗng chỉ phù hợp khi ứng dụng định nghĩa đó là đầu vào hợp lệ.

### 9.1. Cùng cấu hình ở định dạng .properties

~~~properties
app.mail.host=smtp.example.test
app.mail.port=2525
app.mail.tls-enabled=true
app.retries=5
app.sender-name=
~~~

Trong cả hai định dạng, đích hướng đến một cấu trúc thuộc tính logic thống nhất. Sự khác biệt là **YAML biểu diễn phân cấp bằng thụt lề**, còn **properties biểu diễn phân cấp trực tiếp trong tên khóa**.

Nếu một dự án có đồng thời application.properties và application.yml ở cùng vị trí, cần kiểm tra quy tắc ưu tiên config data của Spring Boot, tránh tưởng rằng Spring tự nối cả hai file theo thứ tự dòng.

## 10. Quy trình xử lý sự cố có thể lặp lại

Dùng quy trình sau mỗi khi cấu hình không đúng kỳ vọng:

**Bước 1 — Ghi tên khóa đầy đủ.** Từ bean hoặc @ConfigurationProperties, xác định chính xác khóa mong đợi, ví dụ **app.mail.tls-enabled**. Đừng chỉ tìm chữ **enabled** trên toàn file.

**Bước 2 — Kiểm tra cú pháp nguồn.** Với YAML, xác định mapping cha, khoảng trắng đầu dòng, dấu **-** của list và mọi khóa trùng trong cùng mapping. Với .properties, tìm tất cả dòng có cùng tên khóa.

**Bước 3 — Phân biệt giá trị.** Ghi rõ ứng dụng mong đợi null, không khai báo, chuỗi rỗng, chuỗi chứa khoảng trắng hay chuỗi “null”. Nếu dữ liệu nghiệp vụ yêu cầu một trạng thái bật/tắt, ưu tiên thuộc tính boolean có ý nghĩa cụ thể.

**Bước 4 — Kiểm tra tài liệu/profile có hiệu lực.** Xác định ứng dụng có nạp file hoặc tài liệu theo profile không. Cùng tên khóa trong nhiều tài liệu được phép có cơ chế ưu tiên riêng.

**Bước 5 — Tìm nguồn ưu tiên cao hơn.** Kiểm tra biến môi trường, tùy chọn JVM **-D** và tham số ứng dụng **--**. Giá trị trong file không nhất thiết là giá trị có hiệu lực.

**Bước 6 — Đọc kết quả Spring thực nhận.** Sử dụng Environment hoặc binding vào lớp cấu hình; nếu có lỗi, đọc đầy đủ property name, source và conversion/validation message.

**Bước 7 — Sửa đúng một ý định cấu hình.** Gộp mapping lặp, chỉnh lại thụt lề, dùng biểu diễn rỗng/null rõ ràng hoặc chuyển cấu hình theo profile; không che vấn đề bằng cách thêm nhiều khóa lặp hơn.

Quy trình này giúp phân biệt nguyên nhân ngay cả khi biểu hiện cuối cùng giống nhau, chẳng hạn một bean nhận giá trị mặc định.

## 11. Bài thực hành

### Bài 1: Phát hiện khóa trùng trong cùng mapping

Cho cấu hình:

~~~yaml
server:
  port: 8080
server:
  shutdown: graceful
~~~

Hãy viết lại thành một mapping server chứa cả **port** và **shutdown**.

Đáp án tham khảo:

~~~yaml
server:
  port: 8080
  shutdown: graceful
~~~

### Bài 2: Đọc sai cấp thụt lề

Cho YAML:

~~~yaml
app:
  http:
    connect-timeout: 2s
  read-timeout: 5s
~~~

Có hai khóa gì sau khi làm phẳng? Nếu dự định cả hai timeout thuộc **app.http**, hãy sửa YAML.

Đáp án: cấu trúc hiện tại biểu diễn **app.http.connect-timeout** và **app.read-timeout**. Để read-timeout cũng thuộc http:

~~~yaml
app:
  http:
    connect-timeout: 2s
    read-timeout: 5s
~~~

### Bài 3: Nhận biết giá trị trống và null

Xét đoạn sau:

~~~yaml
app:
  a:
  b: null
  c: ""
  d: " "
  e: "null"
  f: []
~~~

Ở mức dữ liệu YAML, **a** và **b** là null scalar; **c** là chuỗi rỗng; **d** là chuỗi chứa một dấu cách; **e** là chuỗi “null”; **f** là danh sách rỗng. Hãy dự đoán kết quả mà một String bean, một Collection bean và Environment có thể nhận, rồi xác minh trên đúng phiên bản Spring Boot của dự án. Phần dự đoán phải xét cả bước nạp PropertySource và binding, không kết luận chỉ từ văn bản YAML.

### Bài 4: Đối chiếu nguồn ưu tiên

File application.yml khai báo:

~~~yaml
app:
  retries: 2
~~~

Khởi chạy:

~~~bash
APP_RETRIES=4 java -Dapp.retries=6 -jar demo.jar --app.retries=8
~~~

Giả sử ứng dụng sử dụng thứ tự PropertySource mặc định và không có nguồn ưu tiên cao hơn, **Environment.getProperty("app.retries")** sẽ phân giải thành **8**. Xóa tham số **--app.retries=8** thì giá trị còn **6**; bỏ tiếp JVM system property thì biến môi trường **4** thắng file YAML **2**.

Bài này chứng minh khóa xuất hiện ở nhiều nguồn hợp lệ là bài toán ưu tiên, còn YAML trùng khóa là bài toán cấu trúc văn bản.

## 12. Những nguyên tắc cần nhớ

- Trong một file **.properties**, tránh khai báo cùng khóa hai lần; định nghĩa giá trị một lần hoặc tách theo profile.
- Trong **một tài liệu YAML**, tránh trùng khóa trong cùng mapping. Không giả định hai mapping cùng tên sẽ được tự động gộp.
- **Sai thụt lề** có thể làm YAML không parse được, hoặc nguy hiểm hơn, parse được nhưng tạo ra tên thuộc tính hoàn toàn khác.
- **Không khai báo**, **null**, **""**, **" "** và **"null"** có ý nghĩa khác nhau; Spring Boot còn có bước nạp nguồn và binding cần được kiểm tra trên giá trị thực.
- **application.properties** và **application.yml** có cú pháp biểu diễn chuỗi rỗng khác nhau; dấu nháy trong .properties không có ý nghĩa như YAML.
- Một thuộc tính có thể xuất hiện hợp lệ trong nhiều **PropertySource**; độ ưu tiên quyết định giá trị Spring nhận.
- Khi cấu hình bắt buộc, dùng **@ConfigurationProperties** và validation phù hợp để phát hiện lỗi sớm, thay vì để ứng dụng chạy với giá trị mơ hồ.
- Khi gỡ lỗi, kiểm tra tên thuộc tính đầy đủ và giá trị **Spring Environment** nhận được. Chỉ nhìn dòng trong file chưa đủ để biết hành vi runtime.

Hiểu rõ ba lớp **cú pháp văn bản → PropertySource → binding** sẽ giúp xử lý chính xác các lỗi khóa trùng, thụt lề và null/rỗng, đồng thời tránh thay đổi cấu hình theo cảm tính.

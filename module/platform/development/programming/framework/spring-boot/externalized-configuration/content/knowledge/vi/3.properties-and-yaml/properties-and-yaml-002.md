# Khoảng trắng, chú thích, ký tự đặc biệt và nối dòng trong `.properties`

## 1. Mục tiêu và bối cảnh

Tệp `.properties` là định dạng văn bản chứa các cặp khóa–giá trị, được dùng rộng rãi trong Java và Spring Boot. Một dòng trông đơn giản như `app.title=Hello` vẫn có nhiều quy tắc cú pháp: khoảng trắng có thể trở thành dấu phân cách, dấu `#` có thể là chú thích hoặc một phần giá trị, dấu gạch chéo ngược `\` có thể là ký tự escape hoặc dấu nối dòng.

Trong **Spring Boot Externalized Configuration**, tệp `application.properties` và các tệp `application-{profile}.properties` thường là nguồn cấu hình cho `Environment`, `@Value` và `@ConfigurationProperties`. Hiểu đúng cách phân tích cú pháp `.properties` giúp tránh các lỗi cấu hình khó nhận ra, đặc biệt khi giá trị chứa đường dẫn Windows, URL, dấu hai chấm, dấu bằng, khoảng trắng hoặc được viết trên nhiều dòng.

Tài liệu này tập trung vào **cú pháp của tệp `.properties`** và cách áp dụng trong ứng dụng Spring Boot. Các quy tắc cơ bản bắt nguồn từ định dạng Java properties; khi dùng Spring Boot, một số tính năng riêng của Boot như tài liệu cấu hình nhiều đoạn và placeholder được xử lý ở lớp cao hơn.

## 2. Cấu trúc cơ bản của một dòng properties

Một dòng cấu hình thường có dạng:

~~~properties
key=value
~~~

Một số cách viết tương đương về mặt phân tách khóa và giá trị:

~~~properties
app.name=Catalog Service
app.port:8080
app.enabled true
~~~

Trong các ví dụ trên, `=`, `:` hoặc khoảng trắng **không được escape** đầu tiên sau khóa đều có thể dùng làm dấu phân cách. Ba dòng khai báo ba khóa khác nhau là `app.name`, `app.port` và `app.enabled`. Không nên hiểu dấu cách luôn chỉ là ký tự trang trí; ở vị trí thích hợp, nó có thể kết thúc phần tên khóa.

Về mặt phân tích cú pháp, có thể phân biệt:

- **Dòng vật lý (natural/physical line):** chuỗi ký tự đến dấu kết thúc dòng trong tệp, thường là LF hoặc CRLF.
- **Dòng logic (logical line):** một mục cấu hình hoàn chỉnh; có thể được ghép từ nhiều dòng vật lý bằng dấu `\` cuối dòng.
- **Khóa (key):** tên thuộc tính trước dấu phân cách đầu tiên không được escape.
- **Giá trị (value):** phần còn lại sau dấu phân cách và các khoảng trắng mở đầu được bỏ qua theo quy tắc parser.

Ví dụ:

~~~properties
# Cấu hình HTTP
server.port = 8080

app.greeting = Hello, Spring Boot!
~~~

Hai dòng cấu hình có khóa `server.port` và `app.greeting`; dòng chú thích và dòng trống không tạo thành thuộc tính.

## 3. Quy tắc khoảng trắng

### 3.1. Khoảng trắng đứng trước khóa

Khoảng trắng ở đầu dòng vật lý thông thường được bỏ qua trước khi parser xác định khóa hoặc chú thích.

~~~properties
    app.name=Catalog
	app.timeout=5s
~~~

Các khóa hiệu lực vẫn là `app.name` và `app.timeout`, không bao gồm phần thụt đầu dòng. Tuy nhiên, thói quen thụt dòng như YAML dễ gây hiểu nhầm vì `.properties` không dùng indentation để biểu diễn cấu trúc lồng nhau. Nên đặt các khóa ở đầu dòng để nội dung dễ đọc và dễ đối chiếu.

### 3.2. Khoảng trắng quanh `=` hoặc `:`

Các cách viết sau mang cùng ý nghĩa:

~~~properties
app.name=Catalog
app.name = Catalog
app.name: Catalog
app.name : Catalog
~~~

Với mỗi dòng, parser nhận khóa `app.name` và giá trị `Catalog`. Những khoảng trắng được phép ở giữa khóa, dấu phân cách và đầu giá trị được bỏ qua. Trong thực tế, nên nhất quán với cách viết `key=value` hoặc `key = value` để dễ tìm kiếm và chỉnh sửa.

### 3.3. Khoảng trắng bên trong tên khóa

Khoảng trắng không được escape có thể làm kết thúc khóa sớm:

~~~properties
app name=Catalog
~~~

Dòng trên **không** tạo khóa `app name`. Theo quy tắc phân tích thông dụng, khóa là `app`; phần `name=Catalog` trở thành giá trị. Điều này rất dễ nhầm với tên khóa có chứa khoảng trắng.

Nếu thật sự cần dấu cách trong khóa, có thể escape nó:

~~~properties
app\ name=Catalog
~~~

Khóa khi đó là `app name`. Tuy vậy, đối với Spring Boot, nên dùng tên khóa có cấu trúc rõ ràng như `app.name` hoặc `app.display-name`; các tên này phù hợp hơn với property binding và ít gây nhầm lẫn.

### 3.4. Khoảng trắng ở đầu giá trị

Sau dấu phân cách, khoảng trắng đầu giá trị thường bị bỏ qua:

~~~properties
banner.message=    Hello
~~~

Giá trị sẽ bắt đầu từ `Hello`, không giữ bốn dấu cách sau `=`. Nếu khoảng trắng đầu giá trị là dữ liệu có chủ ý, dùng escape:

~~~properties
banner.message=\ Hello
~~~

Dấu `\ ` biểu diễn một dấu cách thực sự trong giá trị. Có thể escape từng dấu cách để tạo nhiều khoảng trắng đầu chuỗi:

~~~properties
banner.message=\ \ Hello
~~~

Ví dụ này biểu diễn hai dấu cách trước `Hello` theo cú pháp Java properties thông dụng. Khi giá trị có ý nghĩa về bố cục, nên kiểm thử bằng cách đọc lại property và so sánh độ dài chuỗi thay vì chỉ nhìn trên màn hình.

### 3.5. Khoảng trắng giữa và cuối giá trị

Khoảng trắng **giữa** các từ trong giá trị thông thường được giữ lại:

~~~properties
app.description=Spring Boot configuration guide
~~~

Khoảng trắng **cuối** giá trị có thể tồn tại nhưng rất khó thấy trong trình biên tập, trong diff hoặc khi hiển thị trên giao diện:

~~~properties
app.label=Catalog   
~~~

Không nên cố tình dựa vào khoảng trắng cuối dòng để điều khiển hành vi hệ thống. Các bước chuyển đổi kiểu, binding hoặc xử lý chuỗi ở lớp ứng dụng có thể tạo ra kết quả khác với việc đọc chuỗi thô. Nếu dấu cách là dữ liệu bắt buộc, hãy biểu diễn rõ ràng và kiểm tra tại nơi sử dụng.

### 3.6. Tab, dấu xuống dòng và khoảng trắng Unicode

Trong định dạng Java properties truyền thống, ký tự space, tab và form-feed thường có vai trò khoảng trắng cú pháp ở những vị trí xác định. Không phải mọi ký tự trông giống khoảng trắng trong Unicode đều được parser xem như dấu phân cách cú pháp. Vì vậy, tránh dùng non-breaking space hoặc khoảng trắng Unicode khó nhìn trong tên khóa.

Nếu cần tab hoặc xuống dòng **trong giá trị**, hãy sử dụng escape `\t` hoặc `\n` thay vì nhập một dòng vật lý mới rồi kỳ vọng giá trị tự chứa newline.

## 4. Chú thích: dấu `#` và `!`

Một dòng có ký tự không phải khoảng trắng đầu tiên là `#` hoặc `!` thường được xem là chú thích:

~~~properties
# Cấu hình kết nối dịch vụ
! Giá trị mặc định cho môi trường local
service.host=localhost
service.port=8080
~~~

Chú thích giúp giải thích mục đích cấu hình, đơn vị đo, giá trị hợp lệ và mối quan hệ giữa các khóa.

### 4.1. Dòng trống và chú thích không phải là thuộc tính

~~~properties

    # Dòng chú thích được thụt đầu dòng
app.enabled=true
~~~

Dòng trống và dòng bắt đầu bằng `#` sau các khoảng trắng mở đầu không tạo ra khóa. Có thể thêm chúng để nhóm các cấu hình liên quan.

### 4.2. Không có chú thích cuối dòng theo kiểu phổ biến trong nhiều ngôn ngữ

Trong `.properties`, các ký tự `#` và `!` **không tự động bắt đầu chú thích** khi xuất hiện giữa hoặc sau giá trị:

~~~properties
app.name=Catalog # local
message=Hello! Welcome!
theme.color=#11AAFF
~~~

Giá trị tương ứng là `Catalog # local`, `Hello! Welcome!` và `#11AAFF`. Đặc biệt, nếu viết:

~~~properties
server.port=8080 # local
~~~

toàn bộ `8080 # local` có thể được đọc như chuỗi property. Khi Spring Boot liên kết giá trị này tới số nguyên, ứng dụng có thể gặp lỗi chuyển đổi kiểu.

**Cách viết nên dùng:**

~~~properties
# Cổng cho môi trường local
server.port=8080
~~~

Tương tự, dấu `!` trong `service.url=https://example.test/path!` là ký tự giá trị, không phải dấu chú thích.

### 4.3. Dấu `#` hoặc `!` nằm trong khóa

Nếu ký tự đầu tiên không phải khoảng trắng của một dòng là `#` hoặc `!`, dòng đó bị xem là chú thích. Muốn tạo khóa thật sự bắt đầu bằng các ký tự này, phải escape:

~~~properties
\#feature=enabled
\!attention=yes
~~~

Khi phân tích cú pháp theo Java properties, các khóa là `#feature` và `!attention`. Đây là khả năng cú pháp, nhưng tên khóa như vậy không được khuyến khích cho cấu hình Spring Boot thông dụng.

### 4.4. Trường hợp đặc biệt trong Spring Boot: `#---` và `!---`

Spring Boot có cơ chế **multi-document properties**: dòng phân cách tài liệu `#---` hoặc `!---` có thể được Boot hiểu là ranh giới giữa các tài liệu cấu hình, thay vì chú thích thông thường.

~~~properties
app.name=Catalog
#---
spring.config.activate.on-profile=prod
app.name=Catalog Production
~~~

Đây là cú pháp mở rộng của **Spring Boot Config Data** và có quy tắc riêng về vị trí/dạng dấu phân cách. Không nên dùng `#---` như một dòng trang trí tùy ý trong `application.properties` của Boot nếu không muốn tách tài liệu.

## 5. Dấu gạch chéo ngược và các escape sequence

Dấu `\` là ký tự đặc biệt quan trọng của `.properties`. Nó có thể:

1. Giúp một ký tự vốn có nghĩa cú pháp trở thành ký tự dữ liệu, chẳng hạn `\ ` trong khóa.
2. Biểu diễn ký tự điều khiển như tab hoặc newline trong giá trị.
3. Biểu diễn ký tự Unicode dưới dạng `\uXXXX`.
4. Nối nhiều dòng vật lý khi xuất hiện không được escape ở cuối dòng.

### 5.1. Bảng escape thường gặp

| Cách viết trong tệp | Giá trị khi phân tích | Tình huống sử dụng |
| --- | --- | --- |
| `\t` | Một ký tự tab | Giá trị phân tách bằng tab |
| `\n` | Một ký tự xuống dòng LF | Thông báo nhiều dòng |
| `\r` | Một ký tự carriage return | Giao thức hoặc định dạng cần CR |
| `\f` | Một ký tự form feed | Tình huống văn bản đặc biệt |
| `\\` | Một dấu gạch chéo ngược `\` | Đường dẫn Windows, chuỗi regex |
| `\u0041` | Ký tự Unicode `A` | Biểu diễn ký tự theo mã Unicode |
| `\ ` | Một dấu cách | Dấu cách trong khóa hoặc đầu giá trị |
| `\=` | Dấu `=` theo nghĩa dữ liệu | Dấu bằng trong khóa |
| `\:` | Dấu `:` theo nghĩa dữ liệu | Dấu hai chấm trong khóa |
| `\#`, `\!` | Dấu `#` hoặc `!` | Khóa bắt đầu bằng dấu chú thích |

Ký tự `\=` và `\:` thường **không cần escape trong phần giá trị** sau khi parser đã tìm được dấu phân cách. Ví dụ `url=https://example.test/a?x=1` vẫn là một giá trị hợp lệ.

### 5.2. Dấu `\` trước một ký tự không có escape đặc biệt

Không nên coi dấu `\` luôn được giữ nguyên. Với quy tắc `java.util.Properties` truyền thống, một dấu `\` trước ký tự không thuộc nhóm escape được nhận diện có thể bị bỏ đi:

~~~properties
example=hello\world
~~~

Giá trị có thể trở thành `helloworld`, vì `\w` không phải escape đặc biệt và dấu gạch chéo ngược bị loại bỏ. Vì vậy, khi cần một dấu `\` thực trong chuỗi, viết `\\`.

Đừng áp dụng trực giác từ JSON hoặc Java string literal một cách máy móc: trong JSON, một escape không hợp lệ thường là lỗi cú pháp; trong Java properties truyền thống, parser có thể diễn giải khác.

### 5.3. Đường dẫn Windows

Ví dụ dễ sai:

~~~properties
storage.path=C:\temp\new
~~~

Ở đây `\t` có thể trở thành tab và `\n` thành newline. Giá trị thực tế sẽ khác đường dẫn mong muốn.

Hai cách an toàn hơn:

~~~properties
storage.path=C:\\temp\\new
~~~

hoặc, nếu thành phần dùng đường dẫn chấp nhận dấu gạch chéo xuôi:

~~~properties
storage.path=C:/temp/new
~~~

Đối với ứng dụng Java, nên chuyển giá trị thành `Path` tại nơi sử dụng và tránh tự nối đường dẫn bằng chuỗi khi có API phù hợp.

### 5.4. Dấu `=` và `:` trong tên khóa

Dấu phân cách chỉ có nghĩa cú pháp khi không được escape:

~~~properties
setting\=name=value
setting\:kind=local
~~~

Khóa thứ nhất là `setting=name`, giá trị `value`; khóa thứ hai là `setting:kind`, giá trị `local`. Trong dự án Spring Boot, nên tránh tên khóa mang dấu phân cách; chọn `setting.name` và `setting.kind` thường dễ duy trì hơn.

### 5.5. Unicode và mã hóa tệp

`\uXXXX` biểu diễn một đơn vị mã Unicode theo dạng bốn chữ số hex:

~~~properties
label=\u0043\u0061\u0074
~~~

Giá trị tương ứng là `Cat`.

Tuy nhiên, **mã hóa ký tự của tệp** và **Unicode escape trong nội dung properties** là hai vấn đề khác nhau. Java API `Properties.load(InputStream)` truyền thống giả định luồng có cách giải mã đặc thù của API đó; `Properties.load(Reader)` sử dụng bộ giải mã của `Reader`. Spring Boot có cơ chế nạp cấu hình riêng, vì vậy không nên kết luận từ hành vi của `Properties.load(InputStream)` rằng mọi tệp `application.properties` phải được lưu ở cùng một mã hóa. Trong dự án thực tế, thống nhất encoding (thường là UTF-8) trong công cụ build, editor và runtime, đồng thời kiểm tra đúng cơ chế nạp được dùng.

Không cần chuyển toàn bộ tiếng Việt thành `\uXXXX` nếu môi trường đã xử lý Unicode nhất quán.

## 6. Nối dòng vật lý thành một giá trị logic

Khi một dòng vật lý kết thúc bằng **số lẻ dấu `\` liên tiếp**, dấu gạch chéo ngược cuối cùng có thể báo hiệu giá trị tiếp tục ở dòng vật lý kế tiếp. Parser bỏ dấu `\` dùng để nối, bỏ dấu kết thúc dòng và bỏ khoảng trắng thụt đầu của dòng tiếp theo. Nó **không tự thêm** dấu cách hoặc ký tự newline vào giá trị.

### 6.1. Ví dụ nối chuỗi có dấu cách

~~~properties
app.welcome=Hello \
  Spring \
  Boot
~~~

Giá trị logic tương ứng:

~~~text
Hello Spring Boot
~~~

Dấu cách trước mỗi dấu `\` được giữ lại; khoảng trắng thụt ở đầu các dòng nối được bỏ qua. Đây là cách trải một giá trị dài trên nhiều dòng vật lý để dễ đọc.

### 6.2. Nối sát hai đoạn không có dấu cách

~~~properties
app.code=ABC\
  DEF
~~~

Kết quả là `ABCDEF`, vì không có dấu cách trước dấu nối dòng. Nếu cần `ABC DEF`, thêm dấu cách trước dấu `\` của dòng thứ nhất:

~~~properties
app.code=ABC \
  DEF
~~~

Đừng giả định hai dòng sẽ tự cách nhau một ký tự hoặc tạo chuỗi nhiều dòng.

### 6.3. Dấu `\` cuối dòng không được escape và dấu `\\`

So sánh:

~~~properties
# Ví dụ nối dòng:
first=hello\
world
~~~

Kết quả: khóa `first` có giá trị `helloworld`.

~~~properties
# Ví dụ dấu \ cuối giá trị:
second=hello\\
third=world
~~~

Kết quả: `second` chứa giá trị `hello\`; `third` là một thuộc tính độc lập có giá trị `world`. Hai dấu gạch chéo ngược cuối dòng biểu diễn một dấu `\` trong giá trị, nên dòng tiếp theo không bị ghép vào.

Quy tắc “số lẻ/số chẵn dấu `\` liên tiếp cuối dòng” là lý do không nên chỉnh sửa backslash theo cảm tính. Khi muốn giá trị kết thúc bằng dấu gạch chéo ngược, hãy escape dấu đó.

### 6.4. Dòng tiếp theo không cần lặp lại khóa

~~~properties
app.description=This service processes orders, \
  publishes events, and \
  exposes HTTP endpoints.
~~~

Toàn bộ là **một** thuộc tính `app.description`. Các dòng `publishes events...` và `exposes HTTP...` là phần tiếp của giá trị, không phải thuộc tính mới.

Nếu vô tình để dấu `\` cuối một dòng trước khi bắt đầu một khóa khác:

~~~properties
app.first=abc\
app.second=xyz
~~~

thì `app.second=xyz` có thể bị nuốt vào giá trị của `app.first`; khóa `app.second` không được khai báo như dự định. Đây là lỗi cấu hình đặc biệt nguy hiểm vì hai dòng nhìn vẫn giống hai property riêng rẽ.

### 6.5. Chú thích trên dòng nối không hoạt động như mong đợi

Sau khi một logical line đã bắt đầu và được nối qua dấu `\`, ký tự `#` hoặc `!` ở đầu dòng vật lý tiếp theo **không nhất thiết được xem là mở đầu chú thích độc lập**. Nó có thể trở thành một phần giá trị đang được nối:

~~~properties
app.message=Hello \
  #World
~~~

Với cách phân tích Java properties thông dụng, `#World` tham gia vào giá trị của `app.message`. Nếu muốn chú thích, hãy đặt ở một dòng riêng **trước** hoặc **sau** toàn bộ logical line, thay vì chen giữa các đoạn đang nối.

### 6.6. Muốn một newline thật trong giá trị thì dùng `\n`

Nối dòng và xuống dòng trong giá trị là hai ý nghĩa khác nhau:

~~~properties
mail.body=Line one\nLine two
~~~

Giá trị sau khi được đọc có chứa một ký tự newline giữa `Line one` và `Line two`. Ngược lại:

~~~properties
mail.body=Line one\
Line two
~~~

giá trị là `Line oneLine two`. Nếu muốn vừa chia tệp thành nhiều dòng vật lý vừa có newline trong chuỗi, có thể đặt escape `\n` trước dấu nối:

~~~properties
mail.body=Line one\n\
  Line two
~~~

Khi đó giá trị có newline thật giữa hai đoạn. Cần phân biệt ký tự `\n` (escape được giải mã) với LF/CRLF dùng để kết thúc dòng vật lý trong tệp.

## 7. Ví dụ thực tế trong `application.properties` của Spring Boot

Xét một ứng dụng cần tên hiển thị, URL dịch vụ, đường dẫn lưu trữ và thông báo nhiều dòng:

~~~properties
# application.properties
spring.application.name=inventory-service

# Khoảng trắng nội bộ là nội dung của giá trị.
app.display-name=Inventory Service

# Dấu : và = phía sau dấu phân cách là ký tự giá trị.
app.api-url=https://api.example.test/items?source=web&sort=name

# Có thể dùng dấu / cho đường dẫn nếu môi trường hỗ trợ.
app.storage-path=C:/inventory/data

# Nối nhiều dòng vật lý thành một thông báo một dòng.
app.notice=Inventory is available at \
  the configured API endpoint.

# Muốn newline trong giá trị, dùng escape.
app.help=Usage:\n  GET /items\n  POST /items
~~~

Ví dụ Java đọc cấu hình thông qua Spring Framework API mà Spring Boot cung cấp `Environment` đã được chuẩn bị:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class InventorySettings {
    private final Environment environment;

    public InventorySettings(Environment environment) {
        this.environment = environment;
    }

    public String displayName() {
        return environment.getRequiredProperty("app.display-name");
    }

    public String notice() {
        return environment.getRequiredProperty("app.notice");
    }
}
~~~

`notice()` nhận chuỗi đã nối từ các dòng cấu hình; `help` chứa ký tự xuống dòng vì đã dùng `\n`. Dù vậy, nếu bind vào kiểu khác qua `@ConfigurationProperties`, cần xem thêm cơ chế chuyển đổi kiểu và các quy tắc binding của Spring Boot.

### Placeholder là lớp xử lý khác với cú pháp properties

Spring Boot có thể giải quyết placeholder nhờ `Environment`:

~~~properties
app.service-url=${SERVICE_URL:https://service.example.test}
~~~

Tại cấp định dạng `.properties`, các ký tự `$`, `{` và `}` trong dòng này chỉ là văn bản. Việc nhận diện mẫu `${SERVICE_URL:...}` và thay bằng nguồn property khác hoặc giá trị mặc định là chức năng của cơ chế placeholder bên Spring, không phải đặc tính cốt lõi của file properties.

Cần chú ý thứ tự xử lý: ký tự escape của tệp `.properties` được phân tích trước, rồi giá trị mới được các thành phần Spring dùng. Không nên dựa vào việc thêm một dấu `\` ngẫu nhiên để ngăn hoặc kích hoạt placeholder; hãy dùng cơ chế được thành phần đọc cấu hình hỗ trợ.

### Không nhầm với YAML

Trong YAML, indentation, dấu `#` và chuỗi nhiều dòng `|`/`>` có ngữ nghĩa riêng. Các ví dụ sau **không có cùng quy tắc** với `.properties`:

~~~yaml
# application.yml
app:
  notice: >
    Hello
    Spring Boot
  help: |
    Line one
    Line two
~~~

Với `application.properties`, tên khóa thường được viết đầy đủ như `app.notice`; chuỗi dài dùng nối dòng `\`, còn newline thật có thể biểu diễn bằng `\n`. Không chép quy tắc comments và multiline của YAML sang properties.

## 8. Các lỗi phổ biến và cách khắc phục

### 8.1. Thêm chú thích sau giá trị số

**Sai:**

~~~properties
server.port=8080 # local
~~~

Ứng dụng có thể không chuyển được giá trị sang số nguyên.

**Đúng:**

~~~properties
# HTTP port for local development
server.port=8080
~~~

### 8.2. Viết đường dẫn Windows bằng một dấu `\`

**Dễ sai:**

~~~properties
app.path=C:\temp\reports
~~~

Dùng `C:\\temp\\reports` hoặc `C:/temp/reports` nếu hệ thống hỗ trợ. Trường hợp bắt buộc giữ literal backslash, hãy xác nhận giá trị mà Java nhận sau khi parser xử lý.

### 8.3. Cho rằng thụt dòng tạo cấu trúc lồng nhau

**Sai ý nghĩa:**

~~~properties
app:
  name: Inventory
~~~

Đây không phải YAML. Trong properties, nên viết:

~~~properties
app.name=Inventory
~~~

### 8.4. Dùng dấu cách trong khóa mà không escape

**Dễ sai:**

~~~properties
service name=Inventory
~~~

Parser có thể đọc khóa là `service`. Đặt tên `service.name` là lựa chọn rõ ràng hơn cho Spring Boot.

### 8.5. Quên dấu cách ở đoạn nối

~~~properties
message=Hello\
World
~~~

Kết quả là `HelloWorld`. Nếu muốn `Hello World`:

~~~properties
message=Hello \
World
~~~

### 8.6. Dùng dấu `\` cuối dòng mà không nhận ra

Một dấu `\` không được escape ngay trước line break sẽ ghép dòng tiếp theo vào cùng property. Điều này có thể khiến cấu hình kế tiếp biến mất khỏi `Environment`. Khi điều tra một khóa “không tồn tại”, hãy kiểm tra dòng vật lý ngay phía trước nó.

### 8.7. Muốn newline thật nhưng chỉ dùng nối dòng

**Không tạo newline:**

~~~properties
message=First\
Second
~~~

**Tạo newline:**

~~~properties
message=First\nSecond
~~~

### 8.8. Dùng `#---` làm trang trí trong Spring Boot

Nếu tệp thuộc hệ thống Config Data của Spring Boot, `#---` có thể mang nghĩa phân tách document. Để phân đoạn cho người đọc, dùng chú thích thông thường như `# ===== Cấu hình HTTP =====`.

## 9. Cách tự kiểm tra bằng Java

Để quan sát **quy tắc Java properties cơ bản** mà không cần khởi động Spring Boot, có thể tạo tệp thử:

~~~properties
# sample.properties
app.name=Catalog # demo
app.code=ABC\
  DEF
app.tab=one\two
app.space=\ Hello
app.path=C:\\temp\\reports
~~~

Và đọc bằng Java:

~~~java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public class PropertiesSyntaxDemo {
    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();

        try (Reader reader = Files.newBufferedReader(
                Path.of("sample.properties"), StandardCharsets.UTF_8)) {
            properties.load(reader);
        }

        for (String key : new String[] {
                "app.name", "app.code", "app.tab", "app.space", "app.path"
        }) {
            String value = properties.getProperty(key);
            System.out.printf("%s = <%s>, length=%d%n",
                    key, value, value == null ? -1 : value.length());
        }
    }
}
~~~

Một số điểm quan sát:

- `app.name` bao gồm cả ` # demo` ở cuối.
- `app.code` là `ABCDEF`.
- `app.tab` chứa tab thật giữa `one` và `wo` nếu khai báo `one\two` như trong ví dụ; do đó nội dung **không** phải chuỗi chữ `one\two`. Nếu muốn một dấu `\` và chữ `t`, phải viết `\\t`.
- `app.space` bắt đầu bằng một dấu cách.
- `app.path` chứa các dấu `\` thực trong đường dẫn.

Ví dụ dùng `Properties.load(Reader)` để minh họa parser Java trực tiếp. Nó không mô phỏng toàn bộ thứ tự nguồn cấu hình, profile, config import, relaxed binding và placeholder của Spring Boot. Khi kiểm tra lỗi trong Spring Boot, nên đọc **giá trị hiệu lực tại ứng dụng** bằng `Environment` hoặc bean `@ConfigurationProperties` sau khi ứng dụng đã nạp cấu hình.

## 10. Checklist khi viết và sửa tệp properties

1. **Tên khóa:** dùng `app.feature.name`, `app.client.timeout`...; tránh dấu cách và dấu phân cách không cần thiết trong khóa.
2. **Phân cách:** dùng một quy ước nhất quán, thường là `key=value`.
3. **Chú thích:** đặt `#` trên dòng riêng; không viết `# note` sau số, boolean hay URL rồi kỳ vọng bị bỏ qua.
4. **Giá trị:** xem dấu cách mở đầu có bị bỏ qua không; tránh khoảng trắng cuối dòng khó nhận biết.
5. **Backslash:** dùng `\\` khi muốn một `\` thực; cẩn thận với `\t`, `\n` và `\uXXXX`.
6. **Nối dòng:** chỉ dùng dấu `\` cuối dòng khi thật sự muốn một logical line; chủ động chèn dấu cách trước nó nếu cần phân tách từ.
7. **Newline trong giá trị:** dùng `\n` nếu cần ký tự xuống dòng, vì nối dòng không tự tạo newline.
8. **Spring Boot:** nhớ các quy tắc riêng của Config Data và multi-document separator `#---`; xác nhận profile và nguồn có độ ưu tiên cao hơn khi kết quả không như dự kiến.
9. **Điều tra:** so sánh nội dung tệp, giá trị sau khi parser đọc và giá trị đã được Spring binding; đây là các bước xử lý khác nhau.
10. **An toàn vận hành:** không in toàn bộ biến môi trường hoặc property nhạy cảm vào log chỉ để kiểm tra cú pháp.

## 11. Ghi nhớ

Trong `.properties`, khoảng trắng, dấu `#`/`!` và `\` được hiểu tùy **vị trí**:

- Khoảng trắng có thể phân cách khóa–giá trị hoặc bị bỏ qua quanh dấu phân cách; muốn giữ dấu cách đầu giá trị cần biểu diễn có chủ ý.
- `#` hoặc `!` là chú thích khi đứng đầu dòng sau khoảng trắng, nhưng ở giữa giá trị thường là dữ liệu bình thường.
- `\` mở đầu escape; ở cuối dòng với số lượng dấu `\` liên tiếp lẻ, nó có thể nối các dòng vật lý thành một thuộc tính.
- Nối dòng chỉ ghép văn bản; `\n` mới tạo ký tự newline trong giá trị.
- Spring Boot nạp và sử dụng các giá trị này qua cơ chế externalized configuration, đồng thời bổ sung các quy tắc riêng như multi-document properties và placeholder.

Hiểu được các quy tắc nhỏ này giúp cấu hình Spring Boot dễ đọc, dễ chuyển môi trường và tránh sai lệch giữa văn bản trong file với giá trị mà ứng dụng thực sự nhận được.

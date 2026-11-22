# Đường dẫn nhập cố định và đường dẫn tương đối với tệp khai báo trong Spring Boot Config Data Import

## 1. Bài toán: cùng một dòng import, nhưng tệp được tìm ở đâu?

Khi cấu hình Spring Boot lớn dần, một `application.yaml` duy nhất có thể chứa quá nhiều thiết lập. Ta thường tách chúng thành các tệp chuyên trách: `database.yaml`, `messaging.yaml`, `feature-flags.properties` hoặc phần cấu hình dùng chung cho nhiều ứng dụng.

Spring Boot hỗ trợ lệnh `spring.config.import` để nhập thêm dữ liệu cấu hình:

~~~properties
spring.config.import=common/database.properties
~~~

Điểm dễ nhầm là đường dẫn `common/database.properties` được tìm **tương đối với vị trí của tệp đang khai báo import**, không mặc nhiên tính từ thư mục bạn mở terminal. Nhưng nếu viết:

~~~properties
spring.config.import=file:./common/database.properties
~~~

thì đây lại là một **vị trí nhập cố định** theo cách phân loại của Spring Boot. `file:./...` sử dụng đường dẫn tệp tính theo thư mục làm việc của tiến trình, không lấy thư mục tệp khai báo làm gốc.

Khác biệt một tiền tố `file:` có thể khiến Spring Boot nạp một tệp khác, hoặc không tìm thấy tệp, dù tên sau cùng trông giống hệt nhau.

Sau bài học này, bạn sẽ:

- Phân biệt vị trí nhập **cố định (fixed)** và **tương đối với tệp khai báo (import relative)**.
- Dự đoán chính xác tệp nào được nạp khi các cấu hình nhập lồng nhau.
- Hiểu vai trò của `optional:`, `file:`, `classpath:` và dấu gạch chéo đầu `/`.
- Biết cách chọn đường dẫn phù hợp khi chạy JAR, đóng gói cấu hình trên classpath hoặc gắn tệp bên ngoài qua container.
- Hiểu quy tắc ưu tiên của tệp được import và cách kiểm tra khi cấu hình có giá trị ngoài dự kiến.

## 2. spring.config.import làm việc như thế nào?

Trong Spring Boot, `spring.config.import` là một phần của cơ chế **Config Data**. Một tài liệu cấu hình có thể khai báo vị trí của một hay nhiều tài liệu khác:

~~~yaml
spring:
  config:
    import: "shared/common.yaml"
~~~

Khi đọc tài liệu khai báo, Spring Boot xác định các vị trí cần nhập, nạp tài liệu tìm được và đưa các thuộc tính của chúng vào `Environment`. Những khóa trong tài liệu nhập có thể **ghi đè khóa trùng** ở tài liệu khai báo import.

Ví dụ:

~~~properties
# application.properties
app.mode=default
app.retries=2
spring.config.import=shared/override.properties
~~~

~~~properties
# shared/override.properties
app.mode=production
~~~

Nếu nhập thành công và không có nguồn ưu tiên cao hơn, kết quả là:

| Khóa | Giá trị hiệu lực | Lý do |
| --- | --- | --- |
| `app.mode` | `production` | Tệp được import ghi đè giá trị trong tệp khai báo. |
| `app.retries` | `2` | Tệp được import không định nghĩa khóa này. |

Spring Boot hợp nhất các nguồn theo từng thuộc tính; nó không bắt buộc phải chọn toàn bộ một tệp làm người thắng.

**Điểm quan trọng:** trước khi xét độ ưu tiên, Spring Boot phải biết **tệp được nhập thực sự nằm ở đâu**. Đó là lý do cần phân biệt hai loại đường dẫn.

## 3. Hai loại vị trí nhập

Theo tài liệu Spring Boot, `spring.config.import` hỗ trợ hai cách phân giải vị trí:

### 3.1. Vị trí cố định (fixed location)

Một vị trí được xem là **fixed** khi bắt đầu bằng:

- Dấu gạch chéo xuôi `/`.
- Một tiền tố dạng URL hoặc giao thức tài nguyên, chẳng hạn `file:` hoặc `classpath:`.

Ví dụ:

~~~properties
spring.config.import=classpath:/shared/defaults.properties
~~~

Hoặc:

~~~properties
spring.config.import=file:./deployment/overrides.properties
~~~

Hoặc một đường dẫn tuyệt đối của hệ thống tệp:

~~~properties
spring.config.import=file:/etc/myapp/settings.properties
~~~

Vị trí cố định được giải quyết **độc lập với tệp chứa lệnh import**. Chuyển dòng khai báo từ một tệp cấu hình sang một tệp khác không làm thay đổi *gốc phân giải do tệp khai báo cung cấp*.

Tuy nhiên, từ **fixed** không đồng nghĩa với “đường dẫn tuyệt đối ở mọi trường hợp”. Ví dụ `file:./deployment/overrides.properties` vẫn chứa `./`. Dấu chấm này liên quan đến **thư mục làm việc hiện tại của tiến trình**, nên vị trí thực có thể thay đổi nếu khởi chạy cùng một JAR từ thư mục làm việc khác.

Cần phân biệt:

| Ví dụ | Ý nghĩa chính |
| --- | --- |
| `classpath:/shared/defaults.properties` | Tìm tài nguyên tại đường dẫn trên classpath. |
| `file:/etc/myapp/settings.properties` | Tìm tệp theo đường dẫn tuyệt đối trên máy chạy tương ứng. |
| `file:./deployment/overrides.properties` | Tìm qua cơ chế `file:`, với `./` gắn với thư mục làm việc của tiến trình. |
| `/shared/defaults.properties` | Bắt đầu bằng `/` nên được phân loại fixed theo quy tắc Config Data. |

Trong ứng dụng thực tế, nên viết rõ `classpath:` hoặc `file:` để người đọc hiểu tài nguyên được lấy từ **classpath** hay **hệ thống tệp**. Cách viết này cũng tránh việc lẫn lộn giữa vị trí của JAR, vị trí của tài liệu khai báo và thư mục làm việc.

### 3.2. Vị trí tương đối với tệp khai báo (import relative location)

Nếu vị trí **không bắt đầu bằng** `/` và cũng **không có tiền tố dạng URL** như `file:` hoặc `classpath:`, Spring Boot xem đó là **import relative**:

~~~properties
spring.config.import=shared/defaults.properties
~~~

Giá trị `shared/defaults.properties` được nối với **vị trí chứa tài liệu đang khai báo import**.

Ví dụ tệp đang khai báo nằm tại:

~~~text
/demo/config/application.properties
~~~

thì đường dẫn tương đối:

~~~properties
spring.config.import=shared/defaults.properties
~~~

được giải quyết thành:

~~~text
/demo/config/shared/defaults.properties
~~~

Nếu chuyển chính tệp `application.properties` sang thư mục khác, đường dẫn mà lệnh import trỏ đến cũng thay đổi theo. Đây là hành vi có chủ ý: một nhóm cấu hình có thể được chuyển cả thư mục mà vẫn giữ các tham chiếu tương đối nội bộ.

### 3.3. Bảng nhận biết nhanh

| Giá trị của `spring.config.import` | Phân loại | Mốc phân giải |
| --- | --- | --- |
| `common.properties` | Tương đối | Thư mục/vị trí của tài liệu khai báo. |
| `common/feature.yaml` | Tương đối | Thư mục/vị trí của tài liệu khai báo. |
| `../shared/feature.yaml` | Tương đối | Vị trí tài liệu khai báo và bước đi lên thư mục cha, khi tài nguyên cho phép. |
| `file:./common.properties` | Cố định | Cơ chế `file:`, không dựa vào thư mục tài liệu khai báo. |
| `file:/opt/app/common.yaml` | Cố định | Vị trí tệp được chỉ định tường minh. |
| `classpath:/common.yaml` | Cố định | Classpath. |
| `/common.yaml` | Cố định | Vị trí bắt đầu bằng `/`. |
| `optional:common.yaml` | Tương đối | Bỏ `optional:` khi xét loại; phần còn lại là `common.yaml`. |
| `optional:file:./common.yaml` | Cố định | Bỏ `optional:` khi xét loại; phần còn lại bắt đầu bằng `file:`. |

Quy tắc cuối bảng đặc biệt quan trọng: **`optional:` không quyết định vị trí fixed hay import relative**.

## 4. Ví dụ từ đầu đến cuối với tệp trên hệ thống

Giả sử chúng ta chạy ứng dụng với cấu trúc thư mục:

~~~text
/demo/
├── application.jar
├── application.properties
└── core/
    ├── core.properties
    └── extra/
        └── extra.properties
~~~

Thư mục làm việc khi chạy ứng dụng là `/demo`, và Spring Boot nạp `/demo/application.properties` từ vị trí tìm kiếm cấu hình bên ngoài JAR.

Tệp gốc:

~~~properties
# /demo/application.properties
spring.application.name=config-demo
app.layer=application
spring.config.import=optional:core/core.properties
~~~

Tệp được nhập:

~~~properties
# /demo/core/core.properties
app.layer=core
app.timeout=20s
spring.config.import=optional:extra/extra.properties
~~~

Tệp nhập tiếp:

~~~properties
# /demo/core/extra/extra.properties
app.layer=extra
app.message=Hello
~~~

Phân giải lần lượt:

1. `/demo/application.properties` khai báo `core/core.properties`. Không có `file:` hay `classpath:` nên đây là import relative. Tệp cần tìm là `/demo/core/core.properties`.

2. `/demo/core/core.properties` khai báo `extra/extra.properties`. Đường dẫn này cũng là import relative, nhưng **mốc mới** là thư mục `/demo/core`. Tệp cần tìm là `/demo/core/extra/extra.properties`.

3. Spring Boot nạp các thuộc tính từ những tài liệu được tìm thấy theo cơ chế Config Data. Khi trùng khóa, thuộc tính của tệp được import có thể ghi đè thuộc tính ở tài liệu khai báo.

~~~text
/demo/application.properties
       |
       | spring.config.import=core/core.properties
       v
/demo/core/core.properties
       |
       | spring.config.import=extra/extra.properties
       v
/demo/core/extra/extra.properties
~~~

Trong trường hợp không bị nguồn khác ghi đè, những khóa có hiệu lực là:

| Khóa | Giá trị | Nguồn |
| --- | --- | --- |
| `spring.application.name` | `config-demo` | `application.properties` |
| `app.layer` | `extra` | `extra.properties`, do import sâu hơn. |
| `app.timeout` | `20s` | `core.properties` |
| `app.message` | `Hello` | `extra.properties` |

Điều cần nhớ là bước nhập thứ hai **không quay về `/demo` để tìm `extra/extra.properties`**. Nó tìm bên dưới thư mục của chính `core.properties`.

## 5. Chỉ cần thêm file: là đường dẫn có thể đổi nghĩa

Giữ nguyên cấu trúc thư mục ở ví dụ trước. Bây giờ thay nội dung `/demo/core/core.properties` bằng:

~~~properties
spring.config.import=optional:file:./extra/extra.properties
~~~

Đây là **fixed location**, vì sau `optional:` có tiền tố `file:`. Nếu tiến trình được chạy từ `/demo`, đường dẫn `./extra/extra.properties` hướng đến:

~~~text
/demo/extra/extra.properties
~~~

Nó **không hướng đến**:

~~~text
/demo/core/extra/extra.properties
~~~

Hệ quả là nếu không có `/demo/extra/extra.properties`, Spring Boot sẽ bỏ qua vị trí import này do có `optional:`. Thuộc tính `app.message` không được thêm từ tệp ban đầu ở `/demo/core/extra`.

Bây giờ bỏ `optional:`:

~~~properties
spring.config.import=file:./extra/extra.properties
~~~

Nếu vị trí không tồn tại, quá trình khởi động thông thường sẽ thất bại với lỗi thuộc nhóm `ConfigDataLocationNotFoundException`.

Bài học ở đây không phải rằng `file:` luôn sai. Tiền tố này là lựa chọn hợp lệ **khi bạn cố ý muốn tham chiếu một vị trí độc lập với nơi đặt tài liệu khai báo**. Vấn đề là cần biết rõ điểm gốc mà nó sử dụng.

### So sánh cùng một tên tệp

Giả sử tệp khai báo ở `/demo/core/core.properties`, còn thư mục làm việc là `/demo`:

| Import | Tệp kỳ vọng |
| --- | --- |
| `extra/extra.properties` | `/demo/core/extra/extra.properties` |
| `optional:extra/extra.properties` | `/demo/core/extra/extra.properties` nếu có |
| `file:./extra/extra.properties` | `/demo/extra/extra.properties` |
| `file:./core/extra/extra.properties` | `/demo/core/extra/extra.properties` |
| `file:/demo/core/extra/extra.properties` | `/demo/core/extra/extra.properties` |

Bảng trên giả định môi trường tệp Unix và đúng thư mục làm việc đã nêu. Khi triển khai trên Windows hay trong container, hãy thay đường dẫn ví dụ bằng đường dẫn phù hợp môi trường thực tế.

## 6. Import từ classpath: chọn đường dẫn theo vị trí tài nguyên

Không phải mọi cấu hình đều là tệp nằm cạnh JAR. Nhiều tệp `.properties` và `.yaml` được đóng gói trong `src/main/resources` rồi trở thành tài nguyên trên classpath.

Ví dụ:

~~~text
src/main/resources/
├── application.yaml
└── config/
    ├── defaults.yaml
    └── feature/
        └── flags.yaml
~~~

Trong `application.yaml` ở **gốc classpath**, ta có thể khai báo một vị trí fixed rõ ràng:

~~~yaml
spring:
  config:
    import: "classpath:/config/defaults.yaml"
~~~

Đường dẫn này trỏ đến `config/defaults.yaml` trên classpath, độc lập với việc dòng khai báo được đặt trong tệp cấu hình nào.

Giả sử `config/defaults.yaml` chứa:

~~~yaml
spring:
  config:
    import: "feature/flags.yaml"

app:
  retries: 3
~~~

Vì `feature/flags.yaml` không có tiền tố URL và không bắt đầu bằng `/`, nó được hiểu là đường dẫn **tương đối với tài liệu `config/defaults.yaml`**. Tài nguyên đích nằm tại:

~~~text
classpath:/config/feature/flags.yaml
~~~

Trong khi nếu `defaults.yaml` khai báo:

~~~yaml
spring:
  config:
    import: "classpath:/feature/flags.yaml"
~~~

thì Spring Boot sẽ tìm tài nguyên ở **gốc classpath**:

~~~text
classpath:/feature/flags.yaml
~~~

Đây là vị trí khác hẳn `classpath:/config/feature/flags.yaml`. Một tiền tố làm thay đổi cách phân giải đường dẫn, dù phần tên `feature/flags.yaml` vẫn giống nhau.

### Khi nào dùng classpath:?

`classpath:` phù hợp với tệp mặc định được đóng gói cùng ứng dụng, chẳng hạn danh sách tính năng mẫu, cấu hình có thể dùng chung trong JAR hoặc thông số không phụ thuộc bí mật của môi trường.

Nhưng một tệp ở classpath khi đã đóng gói trong JAR thường không phải chỗ thuận tiện để chỉnh sửa lúc vận hành. Cấu hình theo môi trường và bí mật nên được quản lý bằng nguồn triển khai phù hợp, ví dụ tệp ngoài JAR, biến môi trường hoặc hệ thống quản lý bí mật.

## 7. Import bằng application.yaml và application.properties có khác nhau không?

Cơ chế phân giải fixed/import relative là của **Config Data**; nó không thay đổi chỉ vì tệp khai báo được viết bằng YAML hay Java Properties.

Dạng properties:

~~~properties
spring.config.import=optional:shared/mail.properties
~~~

Dạng YAML tương ứng:

~~~yaml
spring:
  config:
    import: "optional:shared/mail.properties"
~~~

Hai cách này đều khai báo một vị trí import relative.

Dạng fixed trong properties:

~~~properties
spring.config.import=optional:classpath:/shared/mail.properties
~~~

Dạng fixed trong YAML:

~~~yaml
spring:
  config:
    import: "optional:classpath:/shared/mail.properties"
~~~

Để tránh rắc rối do cách YAML diễn giải ký tự đặc biệt, có thể đặt chuỗi import trong dấu nháy như các ví dụ.

**Không nhầm:** `spring.config.import` là tên thuộc tính cấu hình; phần sau dấu bằng hoặc sau dấu hai chấm mới là vị trí được phân loại fixed hay import relative.

## 8. Từ khóa optional: có làm đường dẫn thành cố định không?

Không. Spring Boot loại tiền tố `optional:` khỏi việc xét vị trí fixed/import relative.

Ví dụ:

~~~properties
spring.config.import=optional:secrets/local.properties
~~~

Vị trí này vẫn được giải quyết **tương đối với tệp khai báo**.

Trong khi:

~~~properties
spring.config.import=optional:file:./secrets/local.properties
~~~

vẫn là fixed vì có tiền tố `file:` sau `optional:`.

Điểm khác biệt thực sự mà `optional:` mang lại là **chính sách khi không tìm thấy vị trí**:

- Không có `optional:`: vị trí được chỉ định mà không tồn tại thường khiến Spring Boot không khởi động được.
- Có `optional:`: Spring Boot có thể tiếp tục khởi động dù vị trí đó không tồn tại.

Tuy nhiên `optional:` **không đảm bảo bỏ qua mọi lỗi**. Một tệp tồn tại nhưng có cú pháp YAML/Properties không hợp lệ vẫn có thể khiến ứng dụng khởi động thất bại. Tương tự, lỗi từ hệ thống cấu hình bên ngoài hoặc các cơ chế nạp bổ sung có thể có hành vi riêng.

### Chọn optional theo ý nghĩa của tệp

Giả sử tệp `local.properties` chỉ phục vụ máy lập trình viên:

~~~properties
spring.config.import=optional:local.properties
~~~

Bỏ qua khi thiếu tệp là hợp lý.

Nhưng nếu dịch vụ không thể hoạt động mà thiếu một tệp cấu hình quan trọng, đặt `optional:` có thể che giấu việc triển khai quên cung cấp nguồn đó. Trong trường hợp này, nhập không optional và để quá trình khởi động thông báo lỗi rõ ràng.

Đừng dùng `optional:` chỉ để “làm mất lỗi” khi chưa xác định đường dẫn thực tế.

## 9. Thứ tự import và độ ưu tiên của giá trị

Hiểu đường dẫn đúng mới là bước đầu. Khi nhiều tệp cùng định nghĩa một khóa, cần biết giá trị nào có hiệu lực.

### 9.1. Tệp nhập thắng tệp khai báo ở khóa trùng

~~~properties
# application.properties
app.label=base
spring.config.import=feature.properties
~~~

~~~properties
# feature.properties
app.label=imported
~~~

Nếu import thành công, giá trị hiệu lực của `app.label` là `imported`, trừ khi một nguồn khác có ưu tiên cao hơn ghi đè.

Dòng `spring.config.import` được khai báo trước hay sau `app.label` **không ảnh hưởng** đến quy tắc ưu tiên này:

~~~properties
spring.config.import=feature.properties
app.label=base
~~~

và:

~~~properties
app.label=base
spring.config.import=feature.properties
~~~

cho cùng kết quả đối với cặp tài liệu này.

### 9.2. Có nhiều import: vị trí sau có thể thắng vị trí trước

~~~properties
spring.config.import=one.properties,two.properties
~~~

Giả sử:

~~~properties
# one.properties
app.color=blue
~~~

~~~properties
# two.properties
app.color=green
~~~

Khi cả hai tệp cùng được nạp và không có nguồn ưu tiên cao hơn, `app.color` là `green`. Spring Boot xử lý các vị trí theo thứ tự khai báo; tệp nhập sau có thể ghi đè tệp nhập trước.

Việc chọn fixed hay import relative **quyết định tìm tệp nào**; còn **quy tắc thứ tự nạp** quyết định giá trị nào thắng giữa những nguồn thực sự đã được tìm thấy. Đây là hai câu hỏi độc lập, cần giải quyết lần lượt.

### 9.3. Một vị trí import chỉ được nạp một lần

Nếu cùng một tài nguyên được khai báo import nhiều lần trong quá trình xử lý Config Data, Spring Boot tránh nhập lặp tài nguyên đó chỉ vì xuất hiện nhiều khai báo. Không nên dựa vào việc viết cùng một import nhiều lần để tăng độ ưu tiên.

### 9.4. Profile có thể bổ sung biến thể tương ứng

Với một import như:

~~~properties
spring.config.import=feature.properties
~~~

khi profile `prod` hoạt động, Spring Boot có thể xét cả tài liệu biến thể phù hợp như `feature-prod.properties`. Vì thế, một giá trị hiệu lực có thể đến từ biến thể theo profile chứ không phải tệp `feature.properties` mà bạn nhìn thấy trước tiên.

Cần kiểm tra profile đang hoạt động và các biến thể liên quan trước khi kết luận một import đang lấy sai tệp.

## 10. Phân biệt import với spring.config.location

Ba thuộc tính sau thường bị nhầm:

| Thuộc tính | Mục đích | Cách sử dụng thường gặp |
| --- | --- | --- |
| `spring.config.import` | Một tài liệu Config Data khai báo muốn nhập thêm tài liệu khác. | Đặt trong `application.properties` hoặc `application.yaml`. |
| `spring.config.location` | Xác định các vị trí tìm cấu hình, **thay thế** các vị trí mặc định. | Cung cấp đủ sớm qua CLI, JVM System property hoặc biến môi trường. |
| `spring.config.additional-location` | **Bổ sung** các vị trí tìm cấu hình vào tập mặc định. | Cung cấp đủ sớm trước khi quá trình nạp Config Data diễn ra. |

Ví dụ:

~~~bash
java -jar app.jar --spring.config.location=optional:file:./deploy/
~~~

Thuộc tính `spring.config.location` là thiết lập khởi động sớm; Spring Boot dùng nó để xác định vị trí tìm các tệp cấu hình. Nếu trỏ vào một thư mục, đường dẫn thư mục cần có dấu `/` ở cuối để Spring Boot tìm các tên tệp cấu hình phù hợp.

Còn trong `application.properties`:

~~~properties
spring.config.import=shared/settings.properties
~~~

là chỉ thị nhập thêm dữ liệu từ tài liệu đang được đọc.

**Không xem hai cách là hoán đổi được.** Nếu bạn muốn một nhóm cấu hình di chuyển cùng thư mục gốc, import relative thường biểu đạt ý định tốt hơn. Nếu người vận hành cần quyết định toàn bộ nơi tìm cấu hình trước khi ứng dụng khởi động, `spring.config.location` hoặc `spring.config.additional-location` phù hợp hơn.

## 11. Tình huống thực tế: ứng dụng đóng gói và tệp cấu hình bên ngoài

Một ứng dụng có thể được triển khai theo cấu trúc:

~~~text
/opt/shop/
├── shop.jar
├── config/
│   ├── application.yaml
│   └── common/
│       └── limits.yaml
└── overrides/
    └── prod.yaml
~~~

Giả sử tiến trình chạy từ `/opt/shop` và Spring Boot nạp tệp `/opt/shop/config/application.yaml`.

~~~yaml
# /opt/shop/config/application.yaml
spring:
  config:
    import:
      - "common/limits.yaml"
      - "optional:file:./overrides/prod.yaml"

shop:
  mode: base
~~~

Hai import nằm cạnh nhau nhưng được giải quyết khác nhau:

| Import | Loại | Vị trí đích |
| --- | --- | --- |
| `common/limits.yaml` | Import relative | `/opt/shop/config/common/limits.yaml` |
| `optional:file:./overrides/prod.yaml` | Fixed | `/opt/shop/overrides/prod.yaml` nếu có |

Tệp `common/limits.yaml` gắn với cấu trúc của thư mục `config`. Tệp `overrides/prod.yaml` phụ thuộc thư mục làm việc `/opt/shop` khi chạy ứng dụng.

Nếu thay đổi cách khởi chạy thành:

~~~bash
cd /tmp
java -jar /opt/shop/shop.jar
~~~

thì đường dẫn fixed `file:./overrides/prod.yaml` giờ có cơ sở là `/tmp` và không còn trỏ đến `/opt/shop/overrides/prod.yaml`. Trong khi đường dẫn import relative `common/limits.yaml` vẫn được giải quyết dựa theo **tệp `application.yaml` đã được nạp**.

Muốn tránh phụ thuộc vào thư mục làm việc trong triển khai, bạn có thể sử dụng đường dẫn cố định tuyệt đối, chẳng hạn:

~~~yaml
spring:
  config:
    import: "optional:file:/opt/shop/overrides/prod.yaml"
~~~

Cách này dễ dự đoán trên máy chạy đúng cấu trúc ấy, nhưng đổi lại gắn cấu hình với đường dẫn cụ thể của hạ tầng. Với nhiều môi trường, hãy chọn quy ước thư mục rõ ràng và thống nhất giữa cấu hình với lệnh khởi chạy.

## 12. Khi nhập dữ liệu từ volume mount và configuration tree

Trong Docker hoặc Kubernetes, cấu hình có thể được gắn thành tệp bên ngoài container. Có hai kiểu thường gặp:

1. Một tệp `.properties` hoặc `.yaml` chứa nhiều khóa và giá trị.
2. Một thư mục chứa nhiều tệp nhỏ, tên tệp trở thành khóa và nội dung tệp trở thành giá trị (*configuration tree*).

Với kiểu thứ nhất:

~~~properties
spring.config.import=optional:file:/run/config/shop.yaml
~~~

Đây là vị trí **fixed** vì có `file:`.

Với kiểu thứ hai:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

`configtree:` là tiền tố nhận diện cơ chế nạp configuration tree. Tài liệu khai báo có thể đặt ở đâu cũng không làm đổi đường dẫn `/run/secrets/` trong trường hợp này.

Giả sử có:

~~~text
/run/secrets/
└── db.password
~~~

thì `db.password` có thể trở thành một thuộc tính của `Environment`. Cần bảo vệ quyền truy cập và cách phân phối bí mật; bản thân `spring.config.import` không mã hóa dữ liệu.

Không áp dụng máy móc quy tắc nối đường dẫn từ tệp YAML đối với `configtree:` như thể đó là một import relative thông thường: đây là cú pháp chỉ rõ một loại vị trí nạp dữ liệu.

## 13. Chẩn đoán khi Spring Boot không tìm thấy tệp

Khi gặp lỗi như `ConfigDataLocationNotFoundException`, hãy kiểm tra theo thứ tự sau.

### Bước 1: đọc nguyên văn giá trị import

Ví dụ:

~~~properties
spring.config.import=optional:file:./extras/settings.properties
~~~

Tách riêng:

- `optional:`: cho phép thiếu vị trí.
- `file:`: khiến vị trí là fixed.
- `./extras/settings.properties`: đường dẫn tệp liên quan đến thư mục làm việc của tiến trình.

Nếu giá trị là `optional:extras/settings.properties`, nó lại thuộc loại import relative.

### Bước 2: xác định tệp **thực sự khai báo** import

Không chỉ xem mỗi `application.yaml`. Một tệp nhập vào trước đó cũng có thể khai báo import tiếp. Với:

~~~text
config/application.yaml
config/shared/base.yaml
config/shared/local/dev.yaml
~~~

nếu `base.yaml` nhập `local/dev.yaml`, đường dẫn này được tìm từ `config/shared`, không phải từ thư mục chứa `application.yaml`.

### Bước 3: xác định thư mục làm việc khi dùng file:./

Trên hệ thống Unix, có thể chạy:

~~~bash
pwd
~~~

Hoặc log thư mục làm việc trong chương trình phát triển. Đường dẫn tương đối trong một `file:./...` có thể đổi khi chạy qua IDE, Gradle, Docker, systemd hoặc script triển khai vì mỗi công cụ có thể thiết lập working directory khác nhau.

Đừng suy ra working directory chỉ từ nơi đặt JAR.

### Bước 4: phân biệt tệp trên classpath với tệp bên ngoài

Một tài nguyên trong `src/main/resources` thường đi vào classpath khi ứng dụng đóng gói. `classpath:/...` tìm tại classpath; `file:...` tìm trên hệ thống tệp. Tên giống nhau không đảm bảo cả hai chỉ cùng một tài nguyên.

### Bước 5: kiểm tra tên, phần mở rộng và profile

Kiểm tra ký tự hoa/thường, đường dẫn thư mục, phần mở rộng `.properties` hoặc `.yaml` và profile đang hoạt động. Khi thích hợp, Spring Boot còn xét biến thể theo profile của tài liệu nhập.

Nếu đường dẫn đúng nhưng file không được nạp, hãy kiểm tra cú pháp file và quy tắc Config Data trước khi đổi `optional:`.

### Bước 6: quan sát tài liệu thực tế qua Environment

Trong lúc phát triển, có thể tạo một thành phần đọc các khóa minh họa:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigProbe implements ApplicationRunner {
    private final Environment environment;

    public ConfigProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("app.mode=" +
                environment.getProperty("app.mode", "(missing)"));
        System.out.println("app.layer=" +
                environment.getProperty("app.layer", "(missing)"));
    }
}
~~~

Việc đọc ra giá trị cho biết thuộc tính đã tham gia `Environment`, nhưng một khóa có thể bị biến môi trường, Java System property hoặc tham số CLI ghi đè. Nếu cần biết tên nguồn, có thể duyệt các `PropertySource` của `ConfigurableEnvironment` trong môi trường phát triển. Không in toàn bộ cấu hình hoặc những giá trị bí mật ra log.

Khi phân tích quá trình nạp Config Data, có thể bật log TRACE cho `org.springframework.boot.context.config` trên môi trường thử nghiệm để biết thêm manh mối về quá trình khám phá tài liệu.

## 14. Những nhầm lẫn phổ biến

**Nhầm lẫn 1 — “Không có file: nghĩa là Spring luôn tìm từ thư mục hiện tại.”**

Không đúng. Vị trí import relative lấy **tài liệu khai báo import** làm mốc. Nếu tài liệu ấy ở thư mục khác, vị trí tìm cũng khác.

**Nhầm lẫn 2 — “Có file: nghĩa là đường dẫn tuyệt đối.”**

Không đúng. `file:./a.properties` là vị trí fixed theo phân loại Config Data, nhưng `./` vẫn có thể phụ thuộc thư mục làm việc. `file:/etc/a.properties` mới chỉ rõ đường dẫn tuyệt đối kiểu Unix.

**Nhầm lẫn 3 — “optional: biến mọi import thành đường dẫn tương đối.”**

Không đúng. `optional:` chỉ tác động đến việc cho phép thiếu vị trí, không thay đổi cách phân loại fixed hay import relative.

**Nhầm lẫn 4 — “Mọi import lồng nhau đều tính từ application.yaml ban đầu.”**

Không đúng. Mỗi import relative phải giải quyết dựa trên **tài liệu trực tiếp chứa dòng khai báo đó**.

**Nhầm lẫn 5 — “Tệp khai báo import luôn có ưu tiên cao hơn tệp nhập.”**

Không đúng. Với khóa trùng trong Config Data, tệp được import có thể ghi đè giá trị của tệp khai báo. Nguồn như CLI hoặc biến môi trường có thể lại ghi đè giá trị sau cùng.

**Nhầm lẫn 6 — “Thêm import hai lần để ép ưu tiên.”**

Không đúng. Spring Boot chỉ nhập một tài nguyên một lần. Nếu cần độ ưu tiên giữa nhiều tài liệu nhập, dùng thứ tự khai báo phù hợp và cấu trúc cấu hình rõ ràng.

**Nhầm lẫn 7 — “Tệp không tồn tại và tệp sai cú pháp là một lỗi.”**

Không đúng. `optional:` cho phép xử lý **thiếu vị trí**; nó không đồng nghĩa với việc chấp nhận mọi nội dung sai.

## 15. Bài thực hành có đáp án

### Bài 1: chọn đường dẫn đúng

Cấu trúc:

~~~text
/app/
├── application.properties
└── config/
    ├── group.properties
    └── details/
        └── rules.properties
~~~

`/app/application.properties`:

~~~properties
spring.config.import=config/group.properties
~~~

Trong `/app/config/group.properties`, muốn nhập `/app/config/details/rules.properties`, hãy chọn:

A. `spring.config.import=details/rules.properties`

B. `spring.config.import=file:./details/rules.properties`

**Đáp án: A.** Đây là vị trí import relative tính từ thư mục của `group.properties`. Phương án B là fixed và, khi tiến trình chạy từ `/app`, hướng đến `/app/details/rules.properties`.

### Bài 2: chuyển tệp khai báo sang thư mục khác

Trước đây `/app/config/a.properties` có:

~~~properties
spring.config.import=common.properties
~~~

Sau khi di chuyển `a.properties` sang `/app/config/new/a.properties` mà giữ nguyên câu lệnh, Spring Boot tìm `common.properties` ở đâu?

**Đáp án:** ở `/app/config/new/common.properties`, vì vị trí nhập tính theo tệp khai báo sau khi di chuyển.

Nếu yêu cầu luôn trỏ đến `/app/config/common.properties` bất kể tệp khai báo nằm đâu, trên hệ thống này có thể dùng `file:/app/config/common.properties`.

### Bài 3: phân loại optional

Phân loại:

~~~properties
spring.config.import=optional:defaults.yaml,optional:classpath:/shared/global.yaml
~~~

**Đáp án:** `optional:defaults.yaml` là import relative; `optional:classpath:/shared/global.yaml` là fixed. Cả hai cho phép bỏ qua vị trí nếu không tồn tại.

### Bài 4: dự đoán độ ưu tiên

`application.properties`:

~~~properties
app.status=base
spring.config.import=one.properties,two.properties
~~~

`one.properties`:

~~~properties
app.status=one
~~~

`two.properties`:

~~~properties
app.status=two
~~~

**Đáp án:** nếu cả hai tệp đều được nạp từ những vị trí dự kiến và không có nguồn ưu tiên cao hơn, `app.status=two` vì vị trí import sau ghi đè vị trí import trước.

### Bài 5: tính điểm đến trong ứng dụng nhiều lớp cấu hình

Cấu trúc:

~~~text
/opt/demo/
├── app.jar
├── application.properties
├── local/
│   └── secrets.properties
└── layers/
    ├── layer.properties
    └── local/
        └── secrets.properties
~~~

Tệp `/opt/demo/application.properties` nhập `layers/layer.properties`; tệp `layer.properties` nhập `local/secrets.properties`. Tệp nào được nạp trong lần nhập thứ hai?

**Đáp án:** `/opt/demo/layers/local/secrets.properties`.

Nếu thay import thứ hai thành `file:./local/secrets.properties` và thư mục làm việc là `/opt/demo`, tệp được nạp sẽ là `/opt/demo/local/secrets.properties`.

## 16. Quy tắc quyết định khi viết cấu hình thật

| Mục đích | Nên cân nhắc | Vì sao |
| --- | --- | --- |
| Giữ các tệp liên quan trong cùng một cây thư mục và di chuyển cả cây | `spring.config.import=shared/common.yaml` | Tham chiếu đi theo tệp khai báo. |
| Nhập tài nguyên mặc định đã đóng gói trong JAR | `spring.config.import=classpath:/shared/common.yaml` | Gốc tài nguyên trên classpath được xác định rõ. |
| Nhập tệp ngoài JAR ở vị trí do hạ tầng quy định | `spring.config.import=file:/etc/app/config.yaml` | Không phụ thuộc thư mục của tệp khai báo. |
| Nhập tệp ở đường dẫn tương đối với working directory | `spring.config.import=file:./runtime/config.yaml` | Có chủ ý phụ thuộc nơi chạy tiến trình. |
| Cho phép một tệp bổ sung vắng mặt | Thêm `optional:` trước vị trí | Ứng dụng tiếp tục khi chỉ thiếu vị trí ấy. |
| Nạp các khóa từ thư mục bí mật gắn ngoài | `spring.config.import=configtree:/run/secrets/` | Dùng cơ chế configuration tree. |

**Ghi nhớ:** Khi đọc `spring.config.import`, trước hết hãy bỏ `optional:` nếu có rồi nhìn vào phần đầu còn lại. Nếu là `/` hoặc một tiền tố như `file:`, `classpath:`, đó là **fixed location**. Nếu không, đó là **import relative location**, được giải quyết theo chính tệp đang khai báo import. Sau khi xác định đúng tài nguyên, mới xét thứ tự import, profile và độ ưu tiên của các nguồn cấu hình.

**Tài liệu tham khảo:** [Spring Boot 3.3 — Externalized Configuration, phần Importing Additional Data và Using Fixed and Import Relative Locations](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
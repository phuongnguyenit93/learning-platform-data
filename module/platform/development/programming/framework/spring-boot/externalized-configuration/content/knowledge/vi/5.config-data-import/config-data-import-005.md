# Nhiều import, nhập lồng nhau và quy tắc chỉ nạp một lần trong Spring Boot 3.3

## 1. Vì sao một ứng dụng cần nhiều lần nhập cấu hình?

Một ứng dụng Spring Boot có thể bắt đầu bằng `application.properties` hoặc `application.yaml`. Khi tính năng nhiều lên, một tệp lớn thường chứa nhiều nhóm thiết lập khác nhau: giới hạn xử lý, địa chỉ dịch vụ, cấu hình gửi thông báo, thiết lập theo môi trường và các giá trị dùng chung. Thay vì chép mọi khóa vào một tệp, Spring Boot cho phép **nhập thêm dữ liệu cấu hình** bằng thuộc tính `spring.config.import`.

Một tệp có thể khai báo nhiều import, một tệp được nhập có thể tiếp tục nhập tệp khác, và cùng một tài nguyên có thể được nhiều nơi nhắc đến. Những trường hợp này dẫn tới các câu hỏi thực tế:

- Nếu hai tệp được nhập cùng định nghĩa `app.timeout`, giá trị nào được dùng?
- Nếu `application.properties` nhập `core.properties`, rồi `core.properties` nhập `limits.properties`, thứ tự ưu tiên ra sao?
- Nếu `limits.properties` được nhắc đến hai hoặc ba lần, Spring Boot có nạp và ghi đè nó lặp lại không?
- Đường dẫn tương đối trong tệp lồng nhau được tính từ đâu?
- Điều gì xảy ra khi tệp bắt buộc bị thiếu, khi import là tùy chọn, hoặc khi kích hoạt profile?

Bài này sử dụng **Spring Boot 3.3.x** và Java 17 trở lên. Mục tiêu là hiểu cách thiết kế chuỗi import, dự đoán giá trị có hiệu lực và tìm nguyên nhân khi cấu hình không như dự kiến. Các ví dụ áp dụng cho hệ thống nạp **Config Data** của Spring Boot 3.3.

## 2. Nắm đúng vai trò của `spring.config.import`

`spring.config.import` là một thuộc tính đặc biệt mà Spring Boot xử lý ở giai đoạn khởi động để nạp thêm nguồn cấu hình. Có thể khai báo nó trong `application.properties`:

```properties
spring.application.name=order-service
spring.config.import=classpath:/config/common.properties
app.name=Order API
```

Hoặc trong `application.yaml`:

```yaml
spring:
  application:
    name: order-service
  config:
    import: "classpath:/config/common.properties"

app:
  name: Order API
```

Tệp `config/common.properties` trên classpath có thể chứa:

```properties
app.name=Order API từ common
app.retry.max-attempts=4
```

Với tình huống đơn giản này, **giá trị từ tệp được nhập có ưu tiên cao hơn giá trị trong tài liệu khai báo import**. `app.name` có hiệu lực là `Order API từ common`, còn `app.retry.max-attempts` được thêm vào tập thuộc tính có thể tra cứu.

Cần phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Tài liệu khai báo import | Một tài liệu cấu hình chứa khóa `spring.config.import` |
| Vị trí import | Địa chỉ của tài nguyên cần nạp, chẳng hạn `classpath:/config/common.properties` |
| Tài liệu được nhập | Nội dung cấu hình lấy từ vị trí import |
| `PropertySource` | Nguồn giá trị mà Spring sử dụng khi giải quyết các thuộc tính |
| `Environment` | Giao diện tra cứu giá trị có hiệu lực sau khi xét các nguồn |
| Thứ tự ưu tiên | Quy tắc quyết định giá trị nào thắng khi các nguồn khai báo cùng khóa |

Việc nhập thêm tệp **không** đồng nghĩa với việc tạo một bean Spring riêng cho mỗi tệp. Đây là quá trình xây dựng tập giá trị cấu hình trước khi ứng dụng sử dụng những giá trị đó thông qua `Environment`, `@Value` hoặc `@ConfigurationProperties`.

Một sơ đồ dễ nhớ:

```text
application.properties
  spring.config.import=common.properties
          |
          v
     common.properties
          |
          v
  Các tài liệu config data được nạp
          |
          v
    Spring Environment
          |
          v
  Bean nhận giá trị cấu hình
```

## 3. Một import đơn: nguồn nhập được ưu tiên hơn tài liệu gọi nó

Giả sử classpath của ứng dụng có hai tệp:

```text
src/main/resources/
├── application.properties
└── config/
    └── common.properties
```

`application.properties`:

```properties
spring.config.import=classpath:/config/common.properties

demo.label=Ứng dụng gốc
demo.pool-size=8
```

`config/common.properties`:

```properties
demo.label=Giá trị được nhập
demo.timeout=5s
```

Khi không có nguồn cấu hình khác ghi đè, kết quả dự kiến là:

| Khóa | Giá trị | Nguồn |
| --- | --- | --- |
| `demo.label` | `Giá trị được nhập` | `common.properties`, ghi đè tệp gọi import |
| `demo.pool-size` | `8` | Chỉ có ở `application.properties` |
| `demo.timeout` | `5s` | Chỉ có ở `common.properties` |

Tài liệu Spring Boot 3.3 diễn tả các tài liệu nhập như được đặt **ngay sau tài liệu khai báo import trong thứ tự ưu tiên**. Vì vậy, tài liệu nhập có thể ghi đè các khóa của tài liệu đã gọi nó.

Cần tránh nhầm với phép chèn văn bản: Spring Boot không nối nguyên văn hai tệp thành một tệp `.properties`; nó nạp các tài liệu cấu hình và áp dụng quy tắc ưu tiên cho các khóa trùng nhau.

### Vị trí dòng khai báo trong cùng một tài liệu không làm đổi ưu tiên

Hai cách viết sau có cùng ý nghĩa:

```properties
spring.config.import=classpath:/config/common.properties
demo.label=Ứng dụng gốc
```

```properties
demo.label=Ứng dụng gốc
spring.config.import=classpath:/config/common.properties
```

`common.properties` vẫn có ưu tiên cao hơn đối với khóa `demo.label`. **Thứ tự dòng `spring.config.import` và dòng giá trị trong cùng một tài liệu không quyết định việc ghi đè.** Quy tắc này khác với thứ tự **các vị trí trong danh sách import** ở phần tiếp theo.

## 4. Nhiều import trong một tài liệu: import sau được ưu tiên

### 4.1. Cú pháp danh sách

Đặt nhiều vị trí trong một giá trị `spring.config.import`, phân tách bằng dấu phẩy:

```properties
spring.config.import=classpath:/config/base.properties,classpath:/config/override.properties
```

Đối với YAML, có thể viết cùng một danh sách dưới dạng chuỗi:

```yaml
spring:
  config:
    import: "classpath:/config/base.properties,classpath:/config/override.properties"
```

Spring Boot xử lý các vị trí **theo thứ tự được liệt kê**; nếu các tệp được nhập cùng đặt một khóa, **import ở phía sau có ưu tiên cao hơn import phía trước**.

Cấu trúc minh họa:

```text
src/main/resources/
├── application.properties
└── config/
    ├── base.properties
    └── override.properties
```

`application.properties`:

```properties
spring.config.import=classpath:/config/base.properties,classpath:/config/override.properties

demo.name=app
demo.cache.enabled=false
```

`config/base.properties`:

```properties
demo.name=base
demo.region=global
demo.cache.enabled=true
```

`config/override.properties`:

```properties
demo.name=override
demo.region=apac
```

Kết quả trong ví dụ này:

| Khóa | Giá trị cuối | Giải thích |
| --- | --- | --- |
| `demo.name` | `override` | Có cả ba nơi; import sau ghi đè import trước và tài liệu gốc |
| `demo.region` | `apac` | Có ở hai import; `override.properties` đứng sau |
| `demo.cache.enabled` | `true` | Chỉ import `base.properties` ghi đè giá trị gốc |
 
Mô hình ưu tiên cho **các tài liệu trong ví dụ**:

```text
Ưu tiên cao
    config/override.properties
             |
    config/base.properties
             |
    application.properties
Ưu tiên thấp
```

Đây là thứ tự cục bộ của chuỗi import đang xét. Nó **không** khẳng định rằng những tài liệu này luôn thắng mọi nguồn khác của Spring Boot như đối số dòng lệnh, biến môi trường, cấu hình profile hay tài liệu được nạp từ vị trí ngoài JAR.

### 4.2. Đổi thứ tự import có thể đổi kết quả

Nếu đổi:

```properties
spring.config.import=classpath:/config/override.properties,classpath:/config/base.properties
```

Thì trong ví dụ trên, `base.properties` trở thành import sau, nên `demo.name=base` và `demo.region=global`. Đổi thứ tự danh sách là một **thay đổi hành vi**, dù nội dung từng tệp giữ nguyên.

Khi triển khai, nên thể hiện chủ ý trong tên và thứ tự:

```properties
spring.config.import=classpath:/config/defaults.properties,classpath:/config/team-overrides.properties
```

Đặt mặc định trước, giá trị điều chỉnh có chủ đích sau sẽ dễ đọc hơn một danh sách có thứ tự tùy tiện.

### 4.3. Không khai báo lặp khóa `spring.config.import` trong cùng một tài liệu

Không nên viết:

```properties
spring.config.import=classpath:/config/base.properties
spring.config.import=classpath:/config/override.properties
```

Trong cùng một tài liệu `.properties`, hai dòng trùng tên thuộc tính có thể bị bộ phân tích cú pháp xử lý theo quy tắc ghi đè khóa, khiến một danh sách import không được biểu diễn rõ như dự kiến. Hãy dùng **một khai báo** chứa danh sách các vị trí, thay vì trông chờ hai dòng có cùng khóa được cộng dồn:

```properties
spring.config.import=classpath:/config/base.properties,classpath:/config/override.properties
```

Nếu tệp có nhiều **tài liệu logic** (chẳng hạn YAML phân tách bằng `---`), mỗi tài liệu có thể có khai báo import riêng; khi đó cần xét thêm điều kiện kích hoạt và thứ tự tài liệu.

## 5. Nhập lồng nhau: tệp được nhập có thể nhập tiếp

### 5.1. Ví dụ chuỗi ba cấp

Spring Boot không giới hạn `spring.config.import` ở riêng `application.properties`. Một tệp nhập vào có thể tiếp tục khai báo thuộc tính này:

```text
src/main/resources/
├── application.properties
└── config/
    ├── core.properties
    └── nested/
        └── limits.properties
```

`application.properties`:

```properties
spring.config.import=classpath:/config/core.properties

demo.mode=app
demo.limit=2
```

`config/core.properties`:

```properties
spring.config.import=classpath:/config/nested/limits.properties

demo.mode=core
demo.limit=4
```

`config/nested/limits.properties`:

```properties
demo.mode=limits
demo.limit=12
demo.audit.enabled=true
```

Đường phụ thuộc là:

```text
application.properties
        |
        | spring.config.import
        v
config/core.properties
        |
        | spring.config.import
        v
config/nested/limits.properties
```

Trong **chuỗi tuyến tính** này:

- `core.properties` được nhập bởi `application.properties`, nên có thể ghi đè `demo.mode=app`.
- `limits.properties` được nhập bởi `core.properties`, nên có thể ghi đè `demo.mode=core`.
- Giá trị cuối cùng của `demo.mode` là `limits`, của `demo.limit` là `12`; `demo.audit.enabled` là `true`.

Một tài liệu import được lồng sâu không có nghĩa luôn thắng mọi nguồn khác ở toàn ứng dụng. Khi có thêm nhánh import, nhiều profile và vị trí cấu hình, phải xem **thứ tự các tài liệu được Spring Boot thực sự xử lý**, không chỉ đếm độ sâu của tệp.

### 5.2. Phân biệt sơ đồ lồng nhau với việc đọc theo lần gọi hàm

Sơ đồ `A -> B -> C` hữu ích để hiểu quan hệ nhập, nhưng các tài liệu này không hoạt động như các hàm Java gọi lẫn nhau mỗi khi truy vấn thuộc tính. Spring Boot xử lý config data khi khởi động, xây dựng các nguồn giá trị và cung cấp chúng cho `Environment`. Bean đọc giá trị cuối cùng theo ưu tiên đã xác định.

Vì vậy, nếu một bean gọi `environment.getProperty("demo.mode")` hai lần, điều đó **không phải** hai lần mở `application.properties` hay thực hiện chuỗi import lại. Đây là tra cứu thuộc tính trong môi trường đang có.

## 6. Đường dẫn import tương đối được tính từ đâu?

Đây là phần rất dễ sai khi có import lồng nhau.

Spring Boot 3.3 phân biệt **vị trí cố định (fixed location)** và **vị trí tương đối theo tệp nhập (import-relative location)**.

- Vị trí bắt đầu bằng dấu `/` hoặc có tiền tố địa chỉ như `classpath:` hay `file:` là **cố định**; ý nghĩa của địa chỉ không thay đổi theo tệp khai báo.
- Vị trí không có dấu `/` đầu và không có tiền tố địa chỉ như trên là **tương đối theo tệp khai báo**.
- Tiền tố `optional:` **không** quyết định việc vị trí là cố định hay tương đối; xét phần địa chỉ sau `optional:`.

### 6.1. Ví dụ vị trí tương đối lồng nhau

Giả sử có các tệp ngoài ứng dụng ở thư mục làm việc `/demo`:

```text
/demo/
├── application.jar
├── application.properties
└── core/
    ├── core.properties
    └── extra/
        └── extra.properties
```

`/demo/application.properties`:

```properties
spring.config.import=optional:core/core.properties
demo.source=application
```

`/demo/core/core.properties`:

```properties
spring.config.import=optional:extra/extra.properties
demo.source=core
```

`/demo/core/extra/extra.properties`:

```properties
demo.source=extra
```

Đường dẫn `core/core.properties` được xác định tương đối theo vị trí của **`application.properties`**. Khi `core.properties` nhập `extra/extra.properties`, địa chỉ được giải quyết tương đối theo **`core.properties`**, tức `/demo/core/extra/extra.properties`.

```text
/demo/application.properties
   + "core/core.properties"
   = /demo/core/core.properties

/demo/core/core.properties
   + "extra/extra.properties"
   = /demo/core/extra/extra.properties
```

Không nên tự động ghép mọi đường dẫn import với thư mục làm việc của tiến trình hoặc với thư mục chứa JAR. **Tệp nào khai báo import thì đường dẫn import-relative được giải quyết theo tệp đó.**

### 6.2. Ví dụ vị trí cố định

Các ví dụ sau dùng địa chỉ có ngữ nghĩa rõ ràng:

```properties
spring.config.import=classpath:/config/global.properties
```

```properties
spring.config.import=file:./config/runtime.properties
```

`classpath:/...` chỉ tài nguyên trên classpath; `file:./...` chỉ đường dẫn tệp theo ngữ nghĩa của hệ thống tệp và thư mục làm việc tương ứng. Vì có tiền tố `file:`, địa chỉ này thuộc nhóm **fixed location** theo cách phân loại của cơ chế import; nó không được tự động ghép tương đối với thư mục của tệp khai báo import.

Một lỗi phổ biến là chuyển dòng:

```properties
spring.config.import=extra.properties
```

từ `application.properties` sang `core/core.properties` mà không xét lại đường dẫn. Khi di chuyển, `extra.properties` được tìm tương đối theo `core/core.properties` và có thể trỏ sang tệp khác hoặc không tồn tại.

### 6.3. Danh sách nhiều đường dẫn có thể trộn hai kiểu

Ví dụ:

```properties
spring.config.import=defaults.properties,optional:file:./deployment/override.properties,classpath:/shared/common.yaml
```

Mỗi phần tử phải được giải quyết theo **quy tắc của chính vị trí đó**. Đừng mặc định cả danh sách cùng tính từ một thư mục. Nếu việc đóng gói và triển khai giữa các môi trường khác nhau, dùng đường dẫn rõ ràng để giảm sự nhầm lẫn.

## 7. Quy tắc quan trọng: cùng một tài nguyên chỉ được import một lần

Tài liệu Spring Boot 3.3 nêu rõ một import chỉ được nạp **một lần**, bất kể nó được khai báo bao nhiêu lần.

Giả sử:

```text
application.properties
  |
  +---> defaults.properties
  |
  +---> ui.properties
           |
           +---> defaults.properties
```

`defaults.properties` được nhắc đến trực tiếp từ `application.properties` và gián tiếp từ `ui.properties`. Spring Boot không tạo thêm một bản sao của cùng tài liệu chỉ vì một đường import khác trỏ tới nó.

### 7.1. Ví dụ khai báo trùng trong danh sách

`application.properties`:

```properties
spring.config.import=classpath:/config/defaults.properties,classpath:/config/labels.properties,classpath:/config/defaults.properties
```

Về ý nghĩa **số lần nạp tài nguyên**, `defaults.properties` chỉ được nạp một lần. Không nên suy luận rằng khai báo `defaults.properties` cuối danh sách là một lượt nạp mới có thể được dùng để cưỡng ép thứ tự ưu tiên.

Cách viết tốt hơn:

```properties
spring.config.import=classpath:/config/defaults.properties,classpath:/config/labels.properties
```

Vẫn chỉ có hai nguồn import độc lập, nhưng ý đồ và cách bảo trì rõ ràng hơn.

### 7.2. Nhập lặp không đồng nghĩa với ghi đè lặp

Cần phân biệt hai khái niệm:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Import xuất hiện hai lần | Cùng vị trí được khai báo ở nhiều chỗ hoặc lặp trong danh sách |
| Tài nguyên được nạp hai lần | Quá trình đọc và đưa cùng tài nguyên vào tập config data hai lần |
| Giá trị bị ghi đè | Một nguồn khác có ưu tiên cao hơn đặt cùng khóa |
| Tra cứu giá trị nhiều lần | Bean gọi `Environment` nhiều lần sau khi khởi động |

**Khai báo import lặp không tạo ra nhiều lần nạp tài nguyên.** Tuy nhiên, các tệp cấu hình **khác nhau** hoàn toàn có thể cùng khai báo một khóa và ghi đè nhau theo ưu tiên.

Ví dụ `defaults.properties` và `labels.properties` đều có `app.label` thì kết quả có thể được quyết định bởi thứ tự ưu tiên giữa hai **tài liệu khác nhau**. Đó không phải việc `defaults.properties` được nạp hai lần.

### 7.3. Có thể dùng import lặp để giải quyết vòng phụ thuộc không?

Không nên thiết kế cấu hình dạng vòng:

```text
a.properties -> b.properties -> a.properties
```

Quy tắc nạp một lần giúp tránh hiểu nhầm rằng mỗi lần gặp lại tệp sẽ tạo thêm một bản sao. Nhưng **vòng phụ thuộc import là thiết kế khó bảo trì**: người đọc khó phân biệt tệp nào là nguồn mặc định và tệp nào có quyền ghi đè. Hãy chuyển các giá trị chung sang một tệp không nhập ngược hoặc tổ chức chuỗi import theo một chiều.

Cũng đừng dựa vào cách viết đường dẫn khác nhau để cố tình nạp lại cùng tài nguyên. Ưu tiên dùng địa chỉ thống nhất, tránh cả đường tương đối lẫn tuyệt đối cùng trỏ tới một nơi trong sơ đồ cấu hình.

### 7.4. "Chỉ một lần" không có nghĩa các tệp theo profile là cùng một tệp

`common.properties` và `common-dev.properties` là **hai tài nguyên khác nhau**. Nếu profile `dev` đang hoạt động và Spring Boot xem xét biến thể theo profile của vị trí import, việc hai tệp này cùng tham gia không vi phạm quy tắc mỗi tài nguyên chỉ nạp một lần.

Tương tự, `defaults.properties` và `defaults.yaml` là hai tài nguyên vật lý khác nhau, dù có thể chứa các khóa logic trùng nhau. Đừng dùng quy tắc nạp một lần để kết luận rằng mọi tài liệu có cùng nội dung hoặc cùng tiền tố tên sẽ bị loại bỏ.

## 8. Phối hợp nhiều import và import lồng nhau

Một hệ thống có thể có các tầng:

```text
application.properties
  |
  +---> config/base.properties
  |         |
  |         +---> config/region.properties
  |
  +---> config/tenant.properties
            |
            +---> config/feature.properties
```

Nếu `base.properties` và `tenant.properties` đều định nghĩa một khóa, cần nhớ **thứ tự vị trí trong import trực tiếp**. Nếu một tệp con được nhập từ một tệp khác, cần nhớ tài liệu được nhập có thể ghi đè tài liệu khai báo nó. Khi nhiều nhánh cùng tham gia, sơ đồ giúp nhận diện nguồn, nhưng giá trị cuối cùng còn do thứ tự các tài liệu trong quá trình nạp config data quyết định.

Để giảm phức tạp, nên áp dụng các quy ước sau:

1. Tệp gốc làm điểm vào duy nhất của sơ đồ import.
2. Mỗi nhóm cấu hình có một vị trí sở hữu rõ ràng.
3. Tệp mặc định nằm trước tệp ghi đè trong những danh sách có chủ đích.
4. Tránh một khóa bị khai báo ở quá nhiều nhánh.
5. Các tệp chứa giá trị dùng chung hạn chế nhập ngược lên tệp ở tầng cao.
6. Tránh đưa cùng một tài nguyên vào nhiều nhánh nếu không cần thiết.
7. Khi phát hiện giá trị bất ngờ, xác định tài liệu cung cấp giá trị có hiệu lực thay vì đoán chỉ từ cấu trúc thư mục.

Một sơ đồ import càng phức tạp thì càng cần chú thích về mục đích của mỗi tệp và ví dụ về cấu hình thực tế sau khi khởi động.

## 9. Tương tác với profile

Một vị trí import có thể được mở rộng thành **biến thể theo profile** khi thích hợp. Giả sử:

```text
src/main/resources/
├── application.properties
└── config/
    ├── payment.properties
    └── payment-dev.properties
```

`application.properties`:

```properties
spring.config.import=classpath:/config/payment.properties
```

`config/payment.properties`:

```properties
app.payment.endpoint=https://payments.example.test
app.payment.timeout=5s
```

`config/payment-dev.properties`:

```properties
app.payment.endpoint=http://localhost:9090
```

Khi profile `dev` hoạt động, Spring Boot có thể nạp **cả tệp nhập thông thường và biến thể theo profile**; giá trị `app.payment.endpoint` cho `dev` có thể đến từ `payment-dev.properties`, còn `app.payment.timeout` từ `payment.properties`.

```bash
java -jar app.jar --spring.profiles.active=dev
```

Cần ghi nhớ:

- Vị trí import không nhất thiết chỉ tương ứng với đúng một tệp cuối cùng trong mọi trường hợp; Spring Boot còn xem xét tệp theo profile khi phù hợp.
- Một biến thể profile được nạp sẽ không được nạp lại chỉ vì nó xuất hiện trong một tuyến nhập khác.
- Với nhiều profile đang hoạt động, cần xét thứ tự ưu tiên của các profile và các nhóm vị trí cấu hình liên quan.
- Nếu một nguồn ưu tiên cao hơn như đối số dòng lệnh hoặc biến môi trường cùng đặt `app.payment.endpoint`, nguồn đó vẫn có thể thắng giá trị từ tệp profile.

**Không** dùng `spring.profiles.active` tùy tiện trong tài liệu vốn đã được kích hoạt theo profile. Spring Boot có ràng buộc riêng đối với các thuộc tính kích hoạt profile trong tài liệu theo profile; hãy cấu hình việc kích hoạt profile từ nguồn thích hợp.

## 10. Tệp bắt buộc và tệp tùy chọn

### 10.1. Mặc định, thiếu vị trí import có thể làm ứng dụng không khởi động

Ví dụ:

```properties
spring.config.import=file:./deployment/required.properties
```

Nếu vị trí bắt buộc này không tồn tại, Spring Boot có thể ném `ConfigDataLocationNotFoundException` và không khởi động ứng dụng thành công.

Cách làm này phù hợp với cấu hình mà ứng dụng **không thể hoạt động đúng nếu thiếu**, chẳng hạn dữ liệu kết nối bắt buộc do môi trường triển khai cấp.

### 10.2. `optional:` chỉ cho phép bỏ qua vị trí không tồn tại

Nếu cấu hình bổ sung không bắt buộc:

```properties
spring.config.import=optional:file:./deployment/local.properties
```

Khi tệp không tồn tại, ứng dụng có thể tiếp tục khởi động. Nếu tệp tồn tại, các giá trị trong tệp vẫn được nạp theo quy tắc ưu tiên.

Bạn có thể kết hợp tệp bắt buộc và tệp tùy chọn trong một danh sách:

```properties
spring.config.import=classpath:/config/base.properties,optional:file:./deployment/local.properties
```

Trong ví dụ trên, `base.properties` phải tồn tại ở địa chỉ đã khai báo, trong khi `local.properties` có thể vắng mặt.

**Lưu ý:** `optional:` không biến mọi lỗi thành hợp lệ. Nó phục vụ tình huống **không tìm thấy vị trí**; nếu một tệp tồn tại nhưng YAML sai cú pháp, cấu hình có giá trị sai kiểu, hoặc một phần khác của ứng dụng khởi tạo thất bại, `optional:` không phải cơ chế tự chữa các lỗi đó.

### 10.3. Khi nào không nên dùng `optional:`?

Không nên dùng `optional:` cho mọi tệp chỉ để ứng dụng dễ khởi động. Nếu cấu hình bên ngoài là điều kiện bắt buộc để hệ thống chạy an toàn, việc âm thầm thiếu tệp có thể làm ứng dụng sử dụng giá trị mặc định không phù hợp.

Chọn tùy chọn dựa trên mục đích:

| Loại cấu hình | Có thể tùy chọn? | Lý do |
| --- | --- | --- |
| Giá trị điều chỉnh cho máy cá nhân | Thường có thể | Khi thiếu sẽ dùng cấu hình chung |
| Tệp ghi đè chỉ xuất hiện ở một vài môi trường | Có thể | Môi trường khác không cần tệp này |
| Tệp bắt buộc để truy cập dịch vụ thiết yếu | Thường không | Thiếu phải được phát hiện sớm |
| Tệp chứa cờ cấu hình quan trọng cho an toàn | Cần quyết định rõ | Không nên tự động rơi về giá trị không kiểm soát |

## 11. Ví dụ thực hành đầy đủ

Hãy tạo một ứng dụng Spring Boot 3.3.x sử dụng Java 17 và dependency `spring-boot-starter`. Ví dụ sau dùng `ApplicationRunner` để in các khóa không nhạy cảm khi ứng dụng khởi động.

### 11.1. Cấu trúc tệp

```text
src/main/
├── java/
│   └── example/importlab/
│       └── ImportLabApplication.java
└── resources/
    ├── application.properties
    ├── base/
    │   ├── defaults.properties
    │   └── nested/
    │       └── channels.properties
    └── overrides/
        └── local.properties
```

### 11.2. Tệp gốc nhập hai tệp theo thứ tự

`src/main/resources/application.properties`:

```properties
spring.application.name=config-import-lab
spring.config.import=base/defaults.properties,overrides/local.properties

demo.name=from-application
demo.channel=from-application
demo.limit=1
```

Ở đây cả hai đường dẫn là **import-relative**, được giải quyết theo vị trí `application.properties`. Nếu muốn không phụ thuộc vào nơi đặt tệp gốc, bạn cũng có thể dùng `classpath:/base/defaults.properties` và `classpath:/overrides/local.properties`.

### 11.3. Tệp được nhập đầu tiên lại nhập thêm tệp con

`src/main/resources/base/defaults.properties`:

```properties
spring.config.import=nested/channels.properties

demo.name=from-defaults
demo.channel=from-defaults
demo.limit=3
demo.description=default-layer
```

Từ vị trí `base/defaults.properties`, đường dẫn `nested/channels.properties` trỏ đến `base/nested/channels.properties`.

`src/main/resources/base/nested/channels.properties`:

```properties
demo.channel=from-nested
demo.limit=7
```

### 11.4. Tệp nhập sau ghi đè một số khóa

`src/main/resources/overrides/local.properties`:

```properties
demo.name=from-local
demo.limit=10
```

Vì `local.properties` là import sau trong danh sách ở `application.properties`, các giá trị như `demo.name` và `demo.limit` từ tệp này có thể ghi đè các giá trị tương ứng của nhánh import trước.

Trong khi đó, `demo.description` chỉ có ở `defaults.properties`, còn `demo.channel` được bổ sung từ tài liệu nhập lồng `channels.properties` và không có khai báo trong `local.properties`.

### 11.5. Viết ứng dụng Java in giá trị có hiệu lực

`src/main/java/example/importlab/ImportLabApplication.java`:

```java
package example.importlab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ImportLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ImportLabApplication.class, args);
    }

    @Bean
    ApplicationRunner showConfiguration(Environment env) {
        return args -> {
            print(env, "demo.name");
            print(env, "demo.channel");
            print(env, "demo.limit");
            print(env, "demo.description");
        };
    }

    private static void print(Environment env, String key) {
        System.out.printf("%s=%s%n", key, env.getProperty(key));
    }
}
```

Spring tự đưa `Environment` vào phương thức bean `showConfiguration`. Đoạn mã chỉ đọc những khóa minh họa; không truy xuất bí mật.

### 11.6. Khởi động và quan sát

Nếu dự án dùng Maven wrapper:

```bash
./mvnw spring-boot:run
```

Hoặc đóng gói rồi chạy với đường dẫn JAR thực tế:

```bash
java -jar target/config-import-lab-0.0.1-SNAPSHOT.jar
```

Với cấu trúc và các tệp vừa khai báo, kết quả mong đợi của những dòng do `ApplicationRunner` in là:

```text
demo.name=from-local
demo.channel=from-nested
demo.limit=10
demo.description=default-layer
```

Đây là cách diễn giải:

- `demo.name`: `local.properties` thắng các khai báo trước đó.
- `demo.channel`: `channels.properties` được nhập từ `defaults.properties` và ghi đè `from-defaults`, trong khi `local.properties` không ghi đè khóa này.
- `demo.limit`: có mặt ở nhiều cấp nhưng import sau `local.properties` đặt giá trị `10`.
- `demo.description`: chỉ có ở `defaults.properties`.

Những giá trị này là **dự đoán cho cấu hình minh họa**, với điều kiện không có đối số, biến môi trường hoặc nguồn bổ sung khác ghi đè. Muốn quan sát bản JAR, hãy đóng gói lại sau khi thay đổi tệp trong `src/main/resources`.

### 11.7. Thử tác động của thứ tự danh sách

Trong `application.properties`, đổi:

```properties
spring.config.import=overrides/local.properties,base/defaults.properties
```

Giữ nguyên các tệp còn lại rồi khởi động lại. Bạn sẽ thấy những khóa có mặt trong cả hai nhánh có thể thay đổi theo thứ tự import. Đây là thí nghiệm nhằm nhận ra rằng **thứ tự danh sách có ý nghĩa**, còn vị trí của dòng `spring.config.import` so với các dòng khác trong cùng tài liệu **không** quyết định thứ tự đó.

### 11.8. Thử import tùy chọn

Đưa danh sách về thứ tự ban đầu và thay import thứ hai thành:

```properties
spring.config.import=base/defaults.properties,optional:file:./deployment/local.properties
```

Nếu thư mục `deployment` không có `local.properties`, ứng dụng vẫn có thể chạy với các giá trị từ nhánh `defaults`. Nếu tạo tệp ở đúng vị trí làm việc của tiến trình, Spring Boot sẽ nạp các giá trị mới từ tệp ngoài đó. Đây cũng là cách quan sát sự khác biệt giữa nguồn nằm trên classpath và nguồn tệp của hệ điều hành.

## 12. Mô tả cùng một sơ đồ bằng YAML

Không bắt buộc các tệp nhập đều cùng định dạng. Ví dụ tệp gốc có thể là YAML và một trong các tệp nhập vẫn là `.properties`.

`application.yaml`:

```yaml
spring:
  application:
    name: config-import-lab
  config:
    import: "classpath:/base/defaults.properties,optional:file:./deployment/overrides.yaml"

demo:
  name: from-application
```

`deployment/overrides.yaml` (nếu tồn tại):

```yaml
demo:
  name: from-external-yaml
  limit: 20
```

Khi Spring Boot nạp YAML, các khóa phân cấp được chuyển thành dạng thuộc tính để tra cứu. Cơ chế `spring.config.import` vẫn áp dụng theo các vị trí được khai báo, không vì tệp là YAML mà thay đổi nguyên tắc cơ bản.

Nhưng khi tệp `.properties` và YAML cùng tồn tại ở những vị trí cấu hình mặc định, chúng còn chịu quy tắc ưu tiên định dạng và vị trí. **Không thể suy ra giá trị cuối cùng của ứng dụng chỉ từ thứ tự import** nếu có thêm những `PropertySource` khác.

## 13. Chẩn đoán khi giá trị khác dự kiến

Khi một ứng dụng chạy khác với cấu hình bạn vừa sửa, hãy phân tích theo luồng sau:

```text
Xác định khóa đang sai
         |
         v
Liệt kê tài liệu khai báo khóa
         |
         v
Tìm spring.config.import tại từng tài liệu
         |
         v
Giải quyết đường dẫn tương đối / cố định
         |
         v
Xác định các tài liệu nhập và các nhánh lồng
         |
         v
Kiểm tra import trùng, profile và các nguồn ưu tiên khác
         |
         v
Quan sát giá trị trong Environment
         |
         v
Sửa tệp/đường dẫn/thứ tự/nguồn ghi đè có chủ đích
```

### 13.1. Quan sát quá trình nạp config data

Trong môi trường phát triển, có thể tạm bật log chi tiết cho bộ nạp cấu hình:

```bash
java -jar app.jar --logging.level.org.springframework.boot.context.config=TRACE
```

Điều này hỗ trợ quan sát việc tìm và nạp các nguồn cấu hình. Sau khi xác định nguyên nhân, hãy tắt mức log chi tiết hoặc đưa nó về mức phù hợp; tránh đăng tải log chứa đường dẫn nội bộ hay giá trị bí mật.

### 13.2. Kiểm tra giá trị cuối trong `Environment`

Trong `ApplicationRunner` ở phần thực hành, thêm khóa muốn quan sát:

```java
System.out.println(env.getProperty("demo.name"));
```

Cách này cho biết **giá trị có hiệu lực** sau khi xử lý nguồn cấu hình. Nó không tự cung cấp đầy đủ thông tin vị trí nào đã đưa ra giá trị đó. Khi cần truy tìm nguồn, hãy kết hợp log nạp cấu hình với việc xem các `PropertySource` của `ConfigurableEnvironment` một cách thận trọng.

### 13.3. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Ứng dụng báo không tìm thấy tệp | Import bắt buộc trỏ sai nơi hoặc tệp chưa được đóng gói | Kiểm tra vị trí thực và cách giải quyết đường dẫn |
| Một khóa không nhận giá trị mới | Nguồn ưu tiên cao hơn ghi đè | Kiểm tra import sau, profile, tệp ngoài JAR, biến môi trường và đối số |
| Đổi vị trí tệp làm hỏng import con | Import-relative thay đổi thư mục gốc | Sửa đường dẫn tương đối hoặc dùng vị trí cố định thích hợp |
| Khai báo import trùng nhưng không thấy thay đổi | Spring Boot chỉ nạp tài nguyên một lần | Bỏ import trùng, đặt việc ghi đè ở tệp độc lập |
| Đã thêm `optional:` nhưng ứng dụng vẫn lỗi | Tệp có cú pháp sai hoặc lỗi không liên quan đến thiếu vị trí | Xem loại ngoại lệ và sửa cấu hình thực tế |
| Chạy JAR không thấy tệp vừa thêm | Tệp mới chưa nằm trong bản JAR đang chạy | Build lại hoặc cung cấp tệp ngoài JAR đúng vị trí |
| Profile `dev` có giá trị khác mặc định | Biến thể theo profile được nạp | Kiểm tra các tệp `-dev` cùng những nguồn ưu tiên hơn |

## 14. Thiết kế sơ đồ import dễ bảo trì

Khi số lượng tệp tăng, cấu trúc hợp lý thường quan trọng hơn việc có thể import bao nhiêu cấp. Một quy ước có thể áp dụng:

```text
application.properties
    |
    +--> config/common.properties
    |
    +--> config/module-a.properties
    |
    +--> config/module-b.properties
    |
    +--> config/overrides.properties
```

Trong cấu trúc này, `common.properties` chứa giá trị dùng chung, các tệp module sở hữu cấu hình theo chức năng, và `overrides.properties` chỉ ghi đè các khóa được phép điều chỉnh. Nếu một module cần tài liệu phụ, nên nhập nó bên trong module đó bằng đường dẫn rõ ràng.

Các nguyên tắc bảo trì:

- **Giữ một điểm vào rõ ràng.** Người đọc nên biết bắt đầu theo sơ đồ import từ đâu.
- **Không lặp một khóa ở nhiều tệp nếu không có chủ ý.** Xung đột có chủ ý phải giải thích được bằng thứ tự ưu tiên.
- **Hạn chế import lồng quá sâu.** Một chuỗi dài khiến việc đọc lý do giá trị thắng khó hơn.
- **Dùng địa chỉ nhất quán.** Tránh cùng tài nguyên được nhắc đến bằng nhiều cách viết.
- **Không biến `optional:` thành mặc định cho mọi nguồn.** Phân loại tệp bắt buộc và tùy chọn theo nhu cầu vận hành.
- **Để tệp theo profile làm phần thay đổi của môi trường.** Không sao chép tràn lan mọi khóa chung.
- **Không đặt bí mật thật trong kho mã nguồn.** Việc thêm tầng import không tự cung cấp cơ chế bảo vệ bí mật.
- **Khi thay thứ tự import, xem đó là thay đổi hành vi.** Phải xác định khóa nào bị tác động trước khi phát hành.

## 15. Bài tập tự kiểm tra

### Bài 1 — thứ tự nhiều import

`application.properties`:

```properties
spring.config.import=a.properties,b.properties
sample.value=app
```

`a.properties`:

```properties
sample.value=A
sample.only-a=present
```

`b.properties`:

```properties
sample.value=B
```

**Hỏi:** `sample.value` và `sample.only-a` là gì?

**Đáp án:** `B` và `present`. Import sau ghi đè khóa trùng, còn khóa chỉ có ở `a.properties` vẫn được sử dụng.

### Bài 2 — import lồng nhau

`application.properties` nhập `a.properties`. `a.properties` nhập `b.properties`. Cả ba cùng đặt `sample.level`, lần lượt là `app`, `A` và `B`.

**Hỏi:** Trong chuỗi tuyến tính này, giá trị cuối là gì?

**Đáp án:** `B`, vì `b.properties` được nhập bởi `a.properties`, vốn đã được nhập bởi `application.properties`.

### Bài 3 — vị trí tương đối

`/workspace/config/root.properties` có:

```properties
spring.config.import=sub/child.properties
```

`/workspace/config/sub/child.properties` có:

```properties
spring.config.import=extra/more.properties
```

**Hỏi:** Đường dẫn thứ hai được giải quyết thành đâu?

**Đáp án:** `/workspace/config/sub/extra/more.properties`, vì nó tương đối theo tệp `child.properties`.

### Bài 4 — khai báo import trùng

`application.properties` trực tiếp nhập `shared.properties`; `feature.properties` cũng nhập chính tài nguyên `shared.properties`.

**Hỏi:** Spring Boot nạp `shared.properties` bao nhiêu lần và nên tổ chức ra sao?

**Đáp án:** Một lần cho cùng tài nguyên. Nên để vị trí import chung ở một điểm rõ ràng, tránh khai báo trùng ở nhiều nhánh nếu không cần.

### Bài 5 — tệp không tồn tại

Hai cấu hình:

```properties
spring.config.import=file:./missing.properties
```

```properties
spring.config.import=optional:file:./missing.properties
```

**Hỏi:** Khác nhau ở đâu?

**Đáp án:** Với vị trí bắt buộc không tìm thấy, ứng dụng có thể dừng khởi động do ngoại lệ thiếu config data. `optional:` cho phép bỏ qua vị trí không tồn tại. Cả hai trường hợp vẫn phải có cấu hình hợp lệ cho những thuộc tính cần thiết ở nơi khác.

### Bài 6 — phân biệt nạp một lần và giá trị ưu tiên

`a.properties` và `b.properties` đều có `demo.mode`. `a.properties` được nhập hai lần, `b.properties` một lần. Có thể kết luận rằng `a.properties` thắng vì được nhắc hai lần không?

**Đáp án:** Không. Số lần khai báo cùng một import không làm tài nguyên đó có thêm lượt nạp. Giá trị có hiệu lực phụ thuộc vào **thứ tự ưu tiên của những tài liệu khác nhau** và các nguồn cấu hình còn lại.

## 16. Ghi nhớ trước khi sang bài tiếp theo

Năm quy tắc cốt lõi của `spring.config.import` trong Spring Boot 3.3:

1. **Import bổ sung tài liệu cấu hình**, và giá trị trong tài liệu được nhập có thể ghi đè giá trị của tài liệu khai báo nó.
2. **Một danh sách import được xử lý theo thứ tự khai báo; import đứng sau có ưu tiên hơn import đứng trước** đối với khóa trùng trong tình huống tương ứng.
3. **Một tệp được nhập có thể khai báo import mới**, tạo chuỗi hoặc sơ đồ nhập lồng nhau.
4. **Đường dẫn import-relative tính theo tài liệu khai báo**, còn các địa chỉ có tiền tố như `classpath:` hay `file:` được xử lý theo ngữ nghĩa vị trí cố định.
5. **Mỗi tài nguyên import chỉ được nạp một lần dù được nhắc đến nhiều lần.** Lặp khai báo không tạo thêm vòng ghi đè.

Cuối cùng, giá trị ứng dụng sử dụng vẫn là kết quả của **toàn bộ hệ thống cấu hình**, gồm profile, nguồn bên ngoài, biến môi trường, thuộc tính JVM và đối số khởi động. Khi không chắc tệp nào thắng, hãy dựng sơ đồ import, xem vị trí từng tài liệu và quan sát giá trị thực tế qua `Environment`.

### Tài liệu tham khảo

- Spring Boot 3.3 Reference — Externalized Configuration, phần *Importing Additional Data*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#importing-additional-data
- Spring Boot 3.3 Reference — *Using Fixed and Import Relative Locations*, *Property Ordering*, *Profile Specific Files*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html

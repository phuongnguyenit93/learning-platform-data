# Chuỗi, số, boolean và thời điểm cần đặt dấu nháy trong YAML

Khi cấu hình Spring Boot bằng `application.yml`, dấu nháy không chỉ để trang trí. YAML có quy tắc đọc **scalar** (giá trị đơn): `10`, `true`, `null`, một ngày tháng, hoặc chuỗi có ký tự đặc biệt có thể được diễn giải khác với điều người viết mong muốn. Vấn đề càng dễ xảy ra với mã có số 0 đầu, tên phiên bản, cờ trạng thái bằng chữ, URL, nội dung có dấu `#`, và chuỗi ngày giờ.

Bài này giải thích cách chọn **không nháy**, **nháy đơn** và **nháy kép**, đồng thời phân biệt hai bước: **YAML parser đọc giá trị** và **Spring Boot Binder chuyển giá trị vào kiểu Java**. Hiểu cả hai bước giúp cấu hình rõ ý nghĩa, nhất quán giữa môi trường và dễ chẩn đoán lỗi.

## 1. Scalar: giá trị đơn trong YAML

Ví dụ:

~~~yaml
app:
  title: Inventory Service
  version: "1.10"
  max-connections: 20
  enabled: true
  release-date: "2026-11-12"
~~~

Các dòng trên sử dụng các kiểu biểu diễn khác nhau:

| Giá trị | Ý định | Cách viết |
| --- | --- | --- |
| `Inventory Service` | Tên hiển thị | Chuỗi không nháy, hợp lệ khi không có ký tự xung đột |
| `"1.10"` | Phiên bản phải giữ nguyên chữ số | Chuỗi có nháy |
| `20` | Số lượng kết nối | Số không nháy |
| `true` | Cờ logic | Boolean không nháy |
| `"2026-11-12"` | Ngày ISO được giữ ở dạng chuỗi trước khi bind | Chuỗi có nháy |

Ba kiểu viết chuỗi phổ biến:

~~~yaml
text:
  plain: hello world
  single: 'hello world'
  double: "hello world"
~~~

Tất cả có thể biểu diễn cùng nội dung chữ `hello world`. Tuy nhiên, khi scalar giống số, boolean, null, timestamp hoặc chứa ký tự cú pháp YAML, cách đặt nháy có thể quyết định giá trị được đọc đúng hay không.

**YAML 1.1, YAML 1.2 và các parser/schema có khác biệt về quy tắc tự nhận diện kiểu.** Ví dụ chữ `yes`, `no`, `on`, `off` có thể được xử lý như boolean ở một số hệ thống nhưng như chuỗi ở hệ thống khác. Vì thế, cấu hình nên thể hiện rõ ý định thay vì phụ thuộc vào parser tự đoán.

## 2. Quy tắc thực tế: đặt nháy khi cần giữ nguyên chữ

| Dữ liệu mong muốn | Ví dụ nên viết | Lý do |
| --- | --- | --- |
| Tên bình thường | `name: "Billing API"` hoặc `name: Billing API` | Nháy tùy chọn nếu không có ký tự đặc biệt |
| Mã có số 0 đầu | `region-code: "0012"` | Bảo toàn độ dài và số 0 |
| Phiên bản | `version: "1.20"` | Không biến thành số thập phân 1.2 |
| Số để tính toán | `retry-count: 5` | Biểu diễn số |
| Cờ logic | `enabled: true` | Boolean rõ ràng |
| Chữ trông như cờ | `status-label: "off"` | Giữ chuỗi |
| Ngày lịch | `start-date: "2026-11-12"` | Giữ biểu diễn ISO nhất quán |
| Thời điểm có offset | `starts-at: "2026-11-12T09:30:00Z"` | Tránh suy luận timestamp không mong muốn |
| Duration | `timeout: 5s` hoặc `timeout: "5s"` | Binder có thể chuyển sang `Duration` |
| Chuỗi rỗng | `description: ""` | Phân biệt với null |
| Chữ “null” | `literal: "null"` | Giữ chữ, không dùng null thật |
| Chuỗi có `: ` hoặc ` #` | `title: "Status: Ready #1"` | Tránh va chạm với cú pháp YAML |

Không có quy tắc “mọi giá trị YAML đều phải đặt nháy”. Ngược lại, việc đặt nháy cho số hoặc boolean thực sự cũng không tự biến field Java thành `String`. Cần chọn cả **cú pháp YAML** lẫn **kiểu đích Java**.

## 3. Chuỗi chứa chữ số: mã không phải số

Hãy xét mã bưu chính, mã chi nhánh hoặc số điện thoại:

~~~yaml
customer:
  postal-code: "00120"
  account-code: "000045"
  telephone: "+840912345678"
  branch-code: "007"
~~~

Những giá trị này có thể chỉ chứa chữ số nhưng không dùng để cộng, trừ, nhân, chia. Người dùng thường cần giữ chính xác cách viết, bao gồm số 0 đầu, dấu `+` hoặc dấu phân cách. Nên biểu diễn bằng chuỗi và bind vào `String`.

Ví dụ rủi ro:

~~~yaml
customer:
  postal-code: 00120
~~~

Tùy parser và schema, số có chữ số 0 đầu có thể được hiểu đặc biệt hoặc mất cách biểu diễn ban đầu. Đặt nháy không làm hỏng mã; nó giúp giữ nguyên văn bản trước khi Spring chuyển đổi.

### Phiên bản, mã release, tỷ lệ hiển thị

~~~yaml
build:
  version: "1.10"
  api-version: "2.0"
  release-label: "2026.11"
  report-ratio-label: "1.00"
~~~

`1.10` và `1.1` có ý nghĩa khác nhau với nhãn phiên bản, dù tương đương nếu xét như số thập phân. Nếu viết không nháy, kiểu số có thể khiến định dạng bị thay đổi. Tương tự, tỷ lệ cần hiển thị nguyên văn nên là chuỗi, còn tỷ lệ dùng để tính toán thì cần chọn kiểu số thích hợp ở Java.

### Số có ký pháp đặc biệt

Các scalar như `1e3`, `0xFF`, `.inf`, `.nan` hoặc số có dấu gạch dưới có thể được hiểu khác nhau tùy parser/schema. Nếu đó là **mã** hoặc **nhãn**, hãy đặt nháy:

~~~yaml
identifiers:
  scientific-looking: "1e3"
  hex-looking: "0xFF"
  long-code: "00000000000000123456"
~~~

Nếu thực sự cần số để tính toán, nên kiểm tra định dạng parser và kiểu Java hỗ trợ, thay vì dùng ký pháp khó đoán trong cấu hình.

## 4. Boolean: dùng true/false cho cờ, nháy cho chữ

Boolean mô tả một quyết định hai trạng thái:

~~~yaml
features:
  enabled: true
  collect-metrics: false
~~~

Đây là cách rõ ràng nhất khi dự định bind vào `boolean` hoặc `Boolean`. Không nên dùng `on`/`off` hoặc `yes`/`no` thay cho `true`/`false` chỉ vì chúng trông gần nghĩa nhau: các bộ đọc YAML có thể suy luận khác nhau.

Khi các từ này là **nhãn hiển thị**, **enum dạng chữ** hoặc **mã**, chúng nên có nháy:

~~~yaml
workflow:
  mode: "off"
  answer-label: "yes"
  alternate-label: "no"
  visible-value: "false"
  channel: "ON"
~~~

So sánh:

~~~yaml
demo:
  a: false
  b: "false"
~~~

- `a` được viết với ý định là boolean.
- `b` được viết với ý định là chuỗi bốn chữ cái `false`.
- Nếu Spring bind `b` vào kiểu Java `boolean`, Binder vẫn có thể chuyển chuỗi `"false"` thành giá trị boolean `false`.
- Nếu muốn giữ nguyên chữ `false`, field Java nên là `String`.

Vì vậy, **nháy là quy tắc của YAML; kiểu dữ liệu Java là quyết định độc lập ở bước bind**.

Nếu ứng dụng có ba trạng thái `"manual"`, `"auto"` và `"off"`, một enum hoặc type có ý nghĩa nghiệp vụ thường phù hợp hơn cố ghép nhiều boolean.

## 5. Null và chuỗi rỗng

Các cách viết sau có ý nghĩa khác nhau ở tầng YAML:

~~~yaml
message:
  empty: ""
  missing:
  explicit-null: null
  tilde-null: ~
  literal-null: "null"
~~~

`empty` là chuỗi rỗng; `missing`, `explicit-null` và `tilde-null` được viết theo ý định null; `literal-null` là chuỗi gồm chữ “null”.

Tại Spring Boot, cách cấu hình được chuyển thành `PropertySource`, ưu tiên nguồn, placeholder và kiểu đích có thể ảnh hưởng cách giá trị null hoặc vắng mặt được sử dụng. Đừng mặc định mọi tình huống null, không khai báo và chuỗi rỗng đều có cùng kết quả. Nếu cần phân biệt chúng cho một cấu hình cụ thể, phải xác định yêu cầu và xử lý rõ ở lớp Java.

Một lỗi thực tế là viết:

~~~yaml
headers:
  auth: null
~~~

rồi cho rằng ứng dụng sẽ gửi header có giá trị chữ `null`. Nếu thực sự muốn chuỗi đó, phải viết `"null"`; tuy nhiên, nên cân nhắc tại sao ứng dụng cần một giá trị như vậy.

## 6. Ngày, giờ và timestamp: nên đặt nháy

Ngày và thời điểm là nhóm dễ nhầm vì nhìn giống chuỗi nhưng parser YAML ở một số môi trường có thể nhận diện như timestamp/date:

~~~yaml
release:
  date: "2026-11-12"
  announced-at: "2026-11-12T09:30:00Z"
  local-time: "09:30:00"
  timezone: "Asia/Ho_Chi_Minh"
  month-code: "2026-11"
~~~

Dùng nháy để bảo toàn biểu diễn ở đầu vào. Sau đó Spring Boot có thể chuyển:

- `"2026-11-12"` thành `LocalDate` nếu field đích khai báo kiểu ngày và conversion hợp lệ.
- `"2026-11-12T09:30:00Z"` thành `Instant` hoặc kiểu thời điểm thích hợp nếu có converter phù hợp.
- `"09:30:00"` thành `LocalTime` nếu field cần giờ trong ngày.
- `"Asia/Ho_Chi_Minh"` thành timezone/zone ID phù hợp hoặc giữ như chuỗi tùy thiết kế.

**Ngày lịch và thời điểm không giống nhau.** Một ngày như `2026-11-12` chưa nói rõ 00:00 ở múi giờ nào; `2026-11-12T09:30:00Z` chỉ một thời điểm có offset UTC. Nếu xử lý lịch nội địa, cần biết timezone; không dựa ngầm vào múi giờ của server.

Dấu nháy không sửa được định dạng sai. Ví dụ:

~~~yaml
report:
  report-date: "12/11/2026"
~~~

Một field `LocalDate` thường phù hợp với ISO `yyyy-MM-dd`. Nếu dự án cần `dd/MM/yyyy`, phải có cơ chế chuyển đổi rõ ràng. Chỉ thêm nháy sẽ không giúp Binder hiểu mọi định dạng.

### Duration khác timestamp

Thời lượng mô tả một khoảng thời gian:

~~~yaml
network:
  connect-timeout: 2s
  read-timeout: "750ms"
  retry-delay: 1m
~~~

Các giá trị `2s`, `750ms` và `1m` là biểu diễn duration có đơn vị. Chúng không phải số nguyên hoặc thời điểm lịch. Khi bind vào `java.time.Duration`, Spring Boot có hỗ trợ chuyển các cách viết đơn vị phù hợp. Dùng nháy hay không không quyết định kiểu Java cuối cùng.

Thời lượng không có đơn vị như `timeout: 30` dễ khiến người đọc đoán 30 ms, 30 s hay một đơn vị mặc định khác. Hãy viết đơn vị tường minh khi có thể; nếu dùng annotation `@DurationUnit`, phải hiểu rõ quy ước đó.

Tương tự, dữ liệu kích thước có thể viết:

~~~yaml
storage:
  max-upload-size: 10MB
  buffer-size: "512KB"
~~~

Spring Boot có thể chuyển các giá trị này sang `DataSize` khi kiểu đích phù hợp; chúng là biểu diễn có đơn vị, không phải “số YAML” thuần.

## 7. Khi giá trị chứa dấu : và #

YAML dùng dấu `:` để phân tách key với value. Dấu `#` có thể bắt đầu comment. Những chuỗi chứa `: ` hoặc ` #` nên được quote:

~~~yaml
messages:
  title: "Result: Success"
  text: "Completed #1"
  template: "name: value"
  label: "Product #A"
~~~

Ví dụ dễ gây lỗi hoặc mất nội dung:

~~~yaml
messages:
  title: Result: Success    # ': ' dễ bị xem như dấu phân tách
  text: Completed #1        # Phần '#1' có thể thành comment
~~~

Không phải dấu `:` nào cũng buộc đặt nháy: `https://example.invalid` thường là plain scalar hợp lệ vì sau `:` không có khoảng trắng. Nhưng nếu URL có fragment, query hoặc placeholder, cách đặt nháy thường dễ đọc hơn:

~~~yaml
endpoints:
  base-url: "https://api.example.invalid/v1"
  docs-url: "https://docs.example.invalid/guide#install"
~~~

Dấu cách đầu/cuối cũng cần được giữ rõ bằng nháy nếu nó là phần có chủ đích của chuỗi.

## 8. Khi giá trị bắt đầu bằng ký tự đặc biệt

Một plain scalar có thể không hợp lệ hoặc bị diễn giải như cú pháp YAML khi bắt đầu bằng `*`, `&`, `!`, `[`, `{`, `@`, `%` hoặc một số ký tự điều khiển khác.

~~~yaml
examples:
  wildcard: "*"
  literal-tag: "!important"
  account: "@ops"
  progress: "%ready"
  bracket-text: "[draft]"
  brace-text: "{status}"
  literal-comment: "#not-a-comment"
~~~

Dấu nháy nói rõ đây là **chuỗi**, không phải alias, anchor, tag hay cấu trúc collection.

Cũng phân biệt **chuỗi có dấu phẩy** và **danh sách YAML**:

~~~yaml
roles:
  list:
    - ADMIN
    - SUPPORT
  comma-separated-text: "ADMIN, SUPPORT"
  inline-list: [ADMIN, SUPPORT]
  literal-list: "[ADMIN, SUPPORT]"
~~~

`list` và `inline-list` là YAML sequence. `comma-separated-text` và `literal-list` là string. Đừng chỉ nhìn dấu phẩy hoặc dấu ngoặc rồi giả định cùng một kiểu.

## 9. Nháy đơn khác nháy kép như thế nào?

Cả nháy đơn và nháy kép đều dùng được để giữ scalar dạng chuỗi. Khác biệt chính là **escape**.

~~~yaml
text:
  single-quote: 'It''s ready'
  double-quote: "It's ready"
  single-path: 'C:\new\test'
  double-path: "C:\\new\\test"
  line-break: "line 1\nline 2"
  literal-slash-n: '\n'
~~~

Giải thích:

- Trong nháy đơn, muốn có dấu `'` bên trong thì viết `''`. Backslash thường được giữ nguyên như ký tự bình thường.
- Trong nháy kép, backslash mở đầu chuỗi escape: `\n` là xuống dòng, `\t` là tab, `\"` là dấu nháy kép, `\\` là một backslash.
- Nháy đơn tiện khi nội dung có nhiều đường dẫn Windows hoặc regex mà không cần escape.
- Nháy kép tiện khi thực sự muốn biểu diễn tab, xuống dòng hoặc ký tự đặc biệt bằng escape.

Ví dụ sai dễ gặp:

~~~yaml
paths:
  input: "C:\new\temp"
~~~

Các đoạn `\n` và `\t` trong nháy kép có thể làm chuỗi bị biến đổi. Nên dùng:

~~~yaml
paths:
  input: 'C:\new\temp'
~~~

hoặc escape backslash đúng cách:

~~~yaml
paths:
  input: "C:\\new\\temp"
~~~

Đối với chuỗi nhiều dòng dài (ví dụ văn bản banner, template), YAML còn có block scalar `|` và `>`. Chúng có quy tắc riêng về xuống dòng/folding; đó là lựa chọn khác với việc viết một scalar ngắn có dấu nháy.

## 10. Spring Boot: YAML parser và Binder là hai bước khác nhau

Ví dụ cấu hình:

~~~yaml
catalog:
  code: "0012"
  display-name: "Catalog: Summer #1"
  max-items: 100
  enabled: true
  release-date: "2026-11-12"
  request-timeout: 5s
  label: "off"
~~~

Kiểu Java tiếp nhận:

~~~java
package example.config;

import java.time.Duration;
import java.time.LocalDate;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        String code,
        String displayName,
        int maxItems,
        boolean enabled,
        LocalDate releaseDate,
        Duration requestTimeout,
        String label
) {}
~~~

Ở lớp ứng dụng Spring Boot, kích hoạt scan cho `@ConfigurationProperties` nếu chưa có cơ chế đăng ký khác:

~~~java
package example;

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

Bảng ý nghĩa của các cặp giá trị:

| Giá trị YAML | Kiểu Java | Kết quả mong muốn |
| --- | --- | --- |
| `"0012"` | `String code` | Giữ nguyên mã `0012` |
| `"Catalog: Summer #1"` | `String displayName` | Giữ toàn bộ dấu câu và chữ |
| `100` | `int maxItems` | Số nguyên 100 |
| `true` | `boolean enabled` | Boolean true |
| `"2026-11-12"` | `LocalDate releaseDate` | Ngày ISO |
| `5s` | `Duration requestTimeout` | 5 giây |
| `"off"` | `String label` | Chữ “off” |

Luồng xử lý khái quát:

~~~text
application.yml
      |
      v
YAML parser
  - đọc map, list, scalar
  - xử lý dấu nháy / các kiểu giá trị
      |
      v
Spring Environment / PropertySource
  - quản lý key/value và thứ tự ưu tiên
      |
      v
Spring Boot Binder
  - chuyển giá trị theo kiểu field Java
      |
      v
CatalogProperties
  - String, int, boolean, LocalDate, Duration
      |
      v
Bean sử dụng cấu hình
~~~

Do đó, `max-items: "100"` vẫn có thể bind thành `int`. Còn `code: "0012"` chỉ giữ nguyên “0012” nếu đích là `String`; bind sang `int` thì kết quả số là 12. **Dấu nháy bảo vệ biểu diễn ở tầng YAML nhưng không ghi đè kiểu đích của Binder.**

Những field không hợp lệ có thể gây lỗi startup: ví dụ `max-items: "many"` không chuyển được sang `int`, hoặc ngày không hợp định dạng không chuyển được sang `LocalDate`.

## 11. Phân biệt YAML với .properties

Cùng một cấu hình có thể viết dưới hai dạng:

~~~properties
catalog.code=0012
catalog.max-items=100
catalog.enabled=true
catalog.release-date=2026-11-12
catalog.display-name=Catalog: Summer #1
~~~

~~~yaml
catalog:
  code: "0012"
  max-items: 100
  enabled: true
  release-date: "2026-11-12"
  display-name: "Catalog: Summer #1"
~~~

File `.properties` đọc phần giá trị ở dạng text trước khi Spring chuyển theo kiểu đích. YAML có parser riêng xử lý cấu trúc và scalar, nên tác giả phải chú ý hơn tới các trường hợp số, boolean, null và ngày giờ có khả năng được suy luận kiểu.

Cả hai đều là nguồn cấu hình ứng dụng; Spring Boot có thể kết hợp nhiều nguồn như biến môi trường, tham số dòng lệnh và file cấu hình theo thứ tự ưu tiên. Dấu nháy trong YAML không quyết định nguồn nào thắng khi có key trùng.

## 12. Placeholder và secret

Một giá trị cấu hình có thể dùng placeholder do Spring giải quyết, ví dụ cấu hình URL hoặc khóa truy cập đọc từ biến môi trường. Dù YAML dùng nháy đơn hay kép, dấu nháy chủ yếu được parser YAML xử lý; nó **không mặc nhiên vô hiệu cơ chế placeholder của Spring**.

Những điểm cần nhớ:

- Chỉ dùng nháy để giữ syntax/value đúng, không coi dấu nháy là phương tiện mã hóa hoặc giấu secret.
- Secret nên đến từ cơ chế quản lý secrets hoặc biến môi trường được kiểm soát, không lưu nguyên văn trong repository.
- Không in token/password đã bind vào log.
- Chuỗi có placeholder nếu thiếu biến hoặc giá trị không phù hợp vẫn có thể gây lỗi trong giai đoạn cấu hình/binding.
- Với giá trị override, kiểm tra kiểu đích và quy tắc chuyển đổi, không chỉ hình thức viết trong `application.yml`.

## 13. Những lỗi tiêu biểu và cách sửa

### Mã bị mất số 0 đầu

~~~yaml
shipment:
  tracking-code: 0000123
~~~

Nếu đây là mã chứ không phải số lượng, hãy viết `tracking-code: "0000123"` và dùng `String trackingCode`.

### Phiên bản `1.20` thành `1.2`

~~~yaml
app:
  version: 1.20
~~~

Nếu cần nguyên văn “1.20”, hãy viết `version: "1.20"` và dùng kiểu `String`.

### Chữ “off” bị hiểu như boolean hoặc đổi nghĩa giữa parser

~~~yaml
notification:
  channel-label: off
~~~

Viết `channel-label: "off"` nếu đây là tên/mã trạng thái bằng chữ. Nếu là cờ boolean, hãy đổi rõ tên và dùng `enabled: false`.

### Có dấu : và # trong thông báo

~~~yaml
banner:
  message: Deployment: complete #1
~~~

Chuỗi này dễ va chạm với cú pháp YAML. Viết:

~~~yaml
banner:
  message: "Deployment: complete #1"
~~~

### Dùng ngày sai định dạng

~~~yaml
release:
  date: "12/11/2026"
~~~

Nếu đích Java là `LocalDate` và đang theo chuyển đổi ISO thông thường, nên viết `date: "2026-11-12"`. Trường hợp cần dạng `dd/MM/yyyy` thì cấu hình conversion/formatter phù hợp, không chỉ thay dấu nháy.

### Muốn “empty” nhưng lại khai báo null

~~~yaml
profile:
  nickname:
~~~

Nếu yêu cầu là chuỗi rỗng, dùng `nickname: ""`. Nếu yêu cầu là “chưa cung cấp”, cần xác định rõ cách Java xử lý giá trị không có/giá trị null.

### Đặt nháy nhưng vẫn sai kiểu ở Java

~~~yaml
limits:
  max-users: "ten"
~~~

Nếu field là `int maxUsers`, không thể mong Binder biến chữ “ten” thành 10. Dấu nháy hợp lệ ở YAML không đồng nghĩa hợp lệ về type conversion.

### Nghĩ rằng sửa file YAML sẽ tự làm bean đang chạy đổi giá trị

Ứng dụng Spring Boot thông thường nạp và bind cấu hình ở lúc khởi động. Việc sửa file trên đĩa không tự động tái tạo mọi bean hoặc cập nhật dependency đã được inject. Nếu có yêu cầu đổi cấu hình động, phải thiết kế cơ chế refresh và quản lý vòng đời component một cách rõ ràng.

## 14. Chọn dấu nháy qua bốn câu hỏi

Khi thấy một scalar mới trong `application.yml`, hãy hỏi:

1. **Đây là giá trị để tính toán hay một mã cần giữ nguyên cách viết?** Số lượng thường không nháy; mã, số điện thoại, version thường có nháy và dùng `String`.
2. **Giá trị có giống keyword đặc biệt không?** Nếu thật sự là boolean, dùng `true`/`false`. Nếu là chữ `"no"`, `"off"`, `"null"`, hãy đặt nháy.
3. **Giá trị có ký tự cú pháp YAML không?** Đặc biệt là `: `, ` #`, ký tự mở đầu `*`/`!`/`[`/`{`; đặt nháy để giữ văn bản.
4. **Kiểu Java nào sẽ nhận giá trị?** Kiểu đích có thể chuyển string thành `int`, `boolean`, `LocalDate` hoặc `Duration`. Chọn format và annotation phù hợp.

### Bài tập ngắn

Đọc cấu hình:

~~~yaml
demo:
  a: 12
  b: "12"
  c: true
  d: "true"
  e: "0008"
  f: "off"
  g: "2026-11-12"
  h: null
  i: "null"
  j: "Welcome: YAML #1"
  k: 500ms
~~~

Dự đoán ý định:

- `a` là số; `b` là chuỗi trông như số.
- `c` là boolean; `d` là chuỗi có chữ “true”.
- `e` là mã giữ số 0; `f` là chuỗi “off”.
- `g` là ngày được viết dạng text trước khi Binder xử lý.
- `h` là null; `i` là chữ “null”.
- `j` là một chuỗi gồm cả `:` và `#`.
- `k` là giá trị có đơn vị, có thể bind thành `Duration` khi đích đúng kiểu.

Mỗi giá trị chỉ hoàn tất ý nghĩa khi biết cả **cách viết YAML** và **kiểu Java nhận dữ liệu**.

## 15. Ghi nhớ

Dùng `true`/`false` cho boolean, số không nháy cho đại lượng số học, và quote các chuỗi có thể bị hiểu nhầm: mã `"0007"`, version `"1.10"`, chữ `"off"`/`"null"`, ngày `"2026-11-12"`, chuỗi chứa `: ` hoặc ` #`. Với duration và data size, ghi đơn vị; với thời điểm, dùng biểu diễn ISO rõ timezone/offset theo yêu cầu.

**Dấu nháy điều khiển cách YAML đọc scalar. Spring Boot Binder và khai báo kiểu Java quyết định giá trị mà ứng dụng sử dụng.**
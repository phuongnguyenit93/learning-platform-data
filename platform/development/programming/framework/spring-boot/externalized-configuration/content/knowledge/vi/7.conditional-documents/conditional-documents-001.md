# Phân biệt một tệp vật lý với nhiều tài liệu cấu hình logic trong Spring Boot 3.3

## 1. Vấn đề: một tệp có nhất thiết tương ứng với một bộ cấu hình?

Khi mới học Spring Boot, chúng ta thường nghĩ rằng một tệp `application.yaml` hay `application.properties` là một khối cấu hình duy nhất. Mô hình đó đủ dùng khi tệp chỉ chứa vài khóa chung. Nhưng một ứng dụng thường cần cùng những khóa cấu hình với các giá trị khác nhau theo môi trường chạy: máy lập trình (`dev`), kiểm thử (`test`), hoặc triển khai thật (`prod`).

Spring Boot 3.3 hỗ trợ **nhiều tài liệu cấu hình logic trong cùng một tệp vật lý** (*multi-document configuration files*). Mỗi tài liệu logic là một khối cấu hình có ranh giới riêng; nó có thể được nạp hoặc bỏ qua tùy điều kiện kích hoạt. Khi nhiều tài liệu được kích hoạt, Spring Boot xét thứ tự của chúng để tìm giá trị cuối cùng cho các khóa trùng nhau.

Điểm cần hiểu ngay:

- **Tệp vật lý (physical file)**: một tệp thực sự tồn tại trong hệ thống tệp hoặc trong classpath, chẳng hạn `src/main/resources/application.yaml`.
- **Tài liệu cấu hình logic (logical configuration document)**: một phần độc lập trong tệp, được phân chia bằng ký hiệu đặc biệt và được Spring Boot xử lý như một tài liệu cấu hình riêng.
- **Tài liệu có điều kiện**: tài liệu logic chỉ được kích hoạt khi điều kiện như `spring.config.activate.on-profile` được thỏa mãn.
- **Giá trị có hiệu lực**: giá trị của một khóa sau khi Spring Boot kết hợp các tài liệu đang hoạt động với những nguồn cấu hình khác theo thứ tự ưu tiên.

Một tệp có thể chứa một tài liệu, hai tài liệu, hoặc nhiều tài liệu. Ngược lại, **một profile** cũng có thể sử dụng nhiều tệp hoặc nhiều tài liệu logic. Vì vậy, không nên đồng nhất khái niệm *tệp*, *tài liệu*, *profile* và *nguồn giá trị cuối cùng*.

Bài này thuộc chủ đề **Spring Boot Externalized Configuration**, tập trung vào cách tổ chức các tài liệu có điều kiện trong Spring Boot 3.3.x. Ví dụ giả định Java 17 trở lên và một ứng dụng Spring Boot thông thường.

## 2. Mô hình tư duy: hai tầng cấu trúc

Hãy hình dung tệp vật lý là một **vỏ chứa**, bên trong có thể có nhiều tài liệu cấu hình:

```text
src/main/resources/application.yaml      <-- một tệp vật lý
|
+-- Tài liệu logic 1: cấu hình chung
|
+-- Tài liệu logic 2: chỉ hoạt động với profile dev
|
+-- Tài liệu logic 3: chỉ hoạt động với profile prod
```

Khi ứng dụng khởi động với profile `dev`:

```text
application.yaml
    |
    +-- tài liệu 1 (chung) --------> được nạp
    |
    +-- tài liệu 2 (on-profile dev) -> được nạp
    |
    +-- tài liệu 3 (on-profile prod) -> không được kích hoạt
                                              |
                                              v
                           Environment chỉ xét các tài liệu hợp lệ
```

Khi chạy với profile `prod`, tài liệu 1 và tài liệu 3 được kích hoạt, còn tài liệu 2 không được kích hoạt.

Điểm tinh tế: Spring Boot không chỉ đọc nguyên tệp rồi coi mọi dòng bên trong là một khối ngang nhau. Nó **phân tách tài liệu**, xét điều kiện kích hoạt từng tài liệu và đưa giá trị từ các tài liệu phù hợp vào hệ thống cấu hình.

Trong một tệp nhiều tài liệu, những tài liệu nằm **phía sau** có thể ghi đè các khóa trùng của tài liệu **phía trước**, nếu cả hai cùng được kích hoạt. Quy tắc này chỉ mô tả quan hệ giữa các tài liệu trong cùng tệp; thứ tự ưu tiên giữa những tệp, vị trí ngoài JAR, profile, biến môi trường và đối số dòng lệnh vẫn phải được xét riêng.

## 3. YAML: nhiều tài liệu được ngăn cách bằng `---`

YAML vốn có cú pháp ngăn cách tài liệu. Trong Spring Boot, để tạo nhiều tài liệu logic trong `application.yaml` hoặc `application.yml`, đặt một dòng chỉ chứa:

```yaml
---
```

Dòng phân tách phải đứng độc lập. Mỗi khối nằm giữa các dấu `---` được xem là một tài liệu logic riêng. Tài liệu đầu tiên bắt đầu ngay từ đầu tệp, không cần có dấu `---` mở đầu.

Ví dụ `src/main/resources/application.yaml`:

```yaml
spring:
  application:
    name: config-document-demo

app:
  greeting: Xin chào chung
  timeout: 5s
  feature-enabled: false

---
spring:
  config:
    activate:
      on-profile: dev

app:
  greeting: Xin chào môi trường dev
  timeout: 1s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  greeting: Xin chào môi trường production
  timeout: 10s
  feature-enabled: true
```

Tệp trên **chỉ có một đường dẫn vật lý**: `application.yaml`. Nhưng nó có **ba tài liệu cấu hình logic**:

| Tài liệu | Vị trí | Điều kiện | Nội dung tiêu biểu |
| --- | --- | --- | --- |
| 1 | Trước dấu `---` thứ nhất | Không khai báo điều kiện kích hoạt | `app.greeting`, `app.timeout`, `app.feature-enabled` |
| 2 | Giữa hai dấu `---` | `spring.config.activate.on-profile: dev` | Ghi đè lời chào và thời gian chờ cho `dev` |
| 3 | Sau dấu `---` thứ hai | `spring.config.activate.on-profile: prod` | Ghi đè lời chào, thời gian chờ, cờ tính năng cho `prod` |

Mỗi tài liệu có thể sử dụng cấu trúc YAML lồng nhau giống một tệp YAML thông thường. Các khóa lồng nhau được Spring Boot chuyển về dạng thuộc tính logic: `app.greeting`, `app.timeout`, `app.feature-enabled`.

### Kết quả theo từng lần khởi động

Khi không bật `dev` hay `prod`, chỉ tài liệu chung được áp dụng trong ví dụ:

```text
app.greeting = Xin chào chung
app.timeout = 5s
app.feature-enabled = false
```

Khởi động với:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Giá trị dự kiến:

```text
app.greeting = Xin chào môi trường dev
app.timeout = 1s
app.feature-enabled = false
```

Khóa `app.feature-enabled` không được tài liệu `dev` ghi đè, nên giá trị từ tài liệu chung vẫn được sử dụng.

Khởi động với:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Giá trị dự kiến:

```text
app.greeting = Xin chào môi trường production
app.timeout = 10s
app.feature-enabled = true
```

Những ví dụ này giả định không có nguồn khác có ưu tiên cao hơn, chẳng hạn `--app.timeout=...`, biến môi trường hoặc tệp bên ngoài.

**Không cần tạo ba bản sao của `application.yaml`** chỉ để có ba tài liệu logic. Một đường dẫn vật lý có thể chứa phần chung và các phần được kích hoạt theo điều kiện.

## 4. `.properties` cũng hỗ trợ nhiều tài liệu logic

Tính năng nhiều tài liệu không dành riêng cho YAML. Spring Boot 3.3 hỗ trợ phân tách tài liệu trong tệp `.properties` bằng một dòng chỉ chứa:

```properties
#---
```

Hoặc:

```properties
!---
```

Đây là **các dấu phân tách được Spring Boot nhận biết**, không phải một tên khóa `spring.*` mới. Nên dùng dấu phân tách trên một dòng riêng, không thêm khoảng trắng hoặc nội dung phía sau. Để tránh nhầm ranh giới với chú thích của `.properties`, cũng nên để dòng phân tách tách biệt, không đặt dòng chú thích có cùng ký tự bắt đầu ngay sát trước hoặc sau nó.

Ví dụ `src/main/resources/application.properties`:

```properties
spring.application.name=config-document-demo

app.greeting=Xin chào chung
app.timeout=5s
app.feature-enabled=false

#---
spring.config.activate.on-profile=dev

app.greeting=Xin chào môi trường dev
app.timeout=1s

#---
spring.config.activate.on-profile=prod

app.greeting=Xin chào môi trường production
app.timeout=10s
app.feature-enabled=true
```

Tệp trên có cùng mục đích với ví dụ YAML:

```text
application.properties                   <-- một tệp vật lý
  |
  +-- tài liệu 1: cấu hình chung
  |
  +-- #---
  +-- tài liệu 2: kích hoạt khi profile dev hoạt động
  |
  +-- #---
  +-- tài liệu 3: kích hoạt khi profile prod hoạt động
```

### Đừng nhầm chú thích với ranh giới tài liệu

Hai dòng sau **không tương đương**:

```properties
#--- 
```

và:

```properties
# ---- Phần cấu hình dev ----
```

Dòng đầu chỉ là ví dụ về cách một dấu phân tách có thể bị viết lệch nếu thêm dấu cách cuối dòng; hãy dùng chính xác `#---` trên một dòng riêng. Dòng thứ hai là chú thích bình thường, không phải dấu phân tách tài liệu.

Một chú thích như:

```properties
# Cấu hình dành cho dev
```

cũng không tự tạo một tài liệu cấu hình riêng. Nếu không có dấu phân tách thực sự, các khóa phía dưới vẫn thuộc cùng tài liệu logic với các khóa phía trên.

**Lưu ý cú pháp:** các dòng `#---` và `!---` là cách Spring Boot hỗ trợ nhiều tài liệu trong tệp properties. Một trình đọc `.properties` thuần Java không nhất thiết có cùng ngữ nghĩa nhiều tài liệu này. Khi giải thích hành vi, phải phân biệt việc Spring Boot nạp *config data* với việc đọc tệp bằng API `java.util.Properties` thông thường.

## 5. Dấu phân tách tạo ranh giới, điều kiện quyết định việc kích hoạt

Một tài liệu logic không nhất thiết phải có điều kiện. Nó có thể là khối cấu hình bổ sung luôn hoạt động, hoặc là khối chỉ dành cho một môi trường.

Ví dụ YAML **không dùng điều kiện**:

```yaml
app:
  name: first
  retries: 2

---
app:
  name: second
```

Cả hai tài liệu đều có thể được xét khi khởi động. Trong chính tệp này, tài liệu phía sau có ưu tiên cao hơn đối với khóa trùng:

```text
app.name    = second
app.retries = 2
```

Khóa `app.retries` chỉ có ở tài liệu đầu nên không mất đi. Ranh giới tài liệu không có nghĩa tài liệu sau xóa sạch toàn bộ khóa của tài liệu trước.

Ví dụ YAML **có điều kiện**:

```yaml
app:
  retries: 2

---
spring:
  config:
    activate:
      on-profile: dev
app:
  retries: 1
```

- Profile `dev` không hoạt động: tài liệu thứ hai không đóng góp giá trị; `app.retries=2`.
- Profile `dev` hoạt động: cả hai tài liệu phù hợp; tài liệu sau ghi đè `app.retries=1`.

Hai câu hỏi phải được trả lời theo thứ tự:

1. **Tài liệu này có được kích hoạt không?**
2. **Nếu có, thứ tự ưu tiên giữa tài liệu này và các nguồn còn lại ra sao?**

Đọc một giá trị trong tệp bằng mắt mới trả lời được “giá trị có được khai báo ở đây không”, chưa trả lời được “ứng dụng cuối cùng dùng giá trị nào”.

## 6. Điều kiện `spring.config.activate.on-profile`

Trong Spring Boot 3.3, thuộc tính:

```properties
spring.config.activate.on-profile=dev
```

hoặc YAML:

```yaml
spring:
  config:
    activate:
      on-profile: dev
```

quy định rằng **tài liệu logic chứa thuộc tính này chỉ hoạt động khi biểu thức profile tương ứng được thỏa mãn**.

Một số cách sử dụng:

```yaml
# Tài liệu chung
app:
  diagnostic: false

---
spring:
  config:
    activate:
      on-profile: dev
app:
  diagnostic: true
```

Có thể dùng biểu thức profile để mô tả điều kiện linh hoạt hơn, ví dụ:

```yaml
spring:
  config:
    activate:
      on-profile: "dev | test"
```

Biểu thức trên cho phép tài liệu hoạt động khi có `dev` **hoặc** `test` phù hợp. Với điều kiện phủ định:

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"
```

Tài liệu phù hợp khi `prod` không đang hoạt động. Hãy đặt biểu thức trong dấu nháy YAML nếu chuỗi chứa những ký tự có thể bị YAML hiểu như cú pháp, đặc biệt dấu `!`.

Profile là cơ chế **điều kiện của Spring**, không đồng nghĩa với biến môi trường hệ điều hành. Bạn có thể bật profile bằng đối số:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Hoặc đặt thuộc tính môi trường ở nơi được hỗ trợ:

```bash
SPRING_PROFILES_ACTIVE=dev java -jar app.jar
```

Trên PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar app.jar
```

Ở đây tên biến môi trường chỉ là một cách cung cấp giá trị cho thuộc tính `spring.profiles.active`. Chính Spring xác định profile nào đang hoạt động rồi xét các tài liệu có `on-profile`.

### Cấu hình không có `on-profile` vẫn có vai trò

Một tài liệu không đặt điều kiện kích hoạt là nơi phù hợp để lưu **giá trị chung** mà mọi môi trường đều có thể sử dụng. Sau đó các tài liệu có điều kiện chỉ khai báo **phần thay đổi**.

Ví dụ:

```yaml
app:
  client:
    timeout: 5s
    max-retries: 3
    enabled: true

---
spring:
  config:
    activate:
      on-profile: dev
app:
  client:
    timeout: 1s
```

Ở `dev`, `timeout=1s`, còn `max-retries=3` và `enabled=true` đến từ tài liệu chung. Cách này giảm việc lặp lại cùng một giá trị ở nhiều môi trường và giúp người đọc thấy rõ khác biệt giữa chúng.

## 7. Thứ tự tài liệu trong cùng một tệp

Trong một tệp nhiều tài liệu, Spring Boot xử lý tài liệu theo thứ tự từ trên xuống dưới. **Các tài liệu phía sau có thể ghi đè khóa được khai báo trong tài liệu phía trước**.

Ví dụ:

```yaml
app:
  mode: first
  retry-count: 1

---
app:
  mode: second

---
app:
  mode: third
```

Với cả ba tài liệu đều được kích hoạt:

```text
app.mode        = third
app.retry-count = 1
```

Trong tệp này, tài liệu 3 ghi đè `app.mode` của tài liệu 2, còn tài liệu 2 ghi đè `app.mode` của tài liệu 1. Không có tài liệu sau nào thay đổi `app.retry-count`.

### Có điều kiện thì phải lọc trước khi xét ưu tiên

Ví dụ:

```yaml
app:
  mode: common

---
spring:
  config:
    activate:
      on-profile: dev
app:
  mode: development

---
spring:
  config:
    activate:
      on-profile: prod
app:
  mode: production
```

Khi chỉ bật `dev`, tài liệu `prod` không hoạt động. Bạn **không được** kết luận rằng `production` thắng chỉ vì nó nằm cuối tệp. Giá trị là `development`.

Khi chỉ bật `prod`, giá trị là `production`.

Nếu cùng lúc cả `dev` và `prod` hoạt động, cả hai tài liệu có thể cùng phù hợp. Trong tệp này, tài liệu sau (`prod`) có thể ghi đè khóa cùng tên của tài liệu trước (`dev`). Vì vậy, không nên dùng hai profile trái ngược như `dev` và `prod` cùng lúc nếu không có lý do rõ ràng; tên profile không tự tạo quy tắc “prod luôn thắng”.

### Thứ tự trong tệp khác thứ tự giữa các nguồn cấu hình

Một ví dụ dễ nhầm:

```text
classpath:/application.yaml
    tài liệu 1: app.mode=common
    tài liệu 2: app.mode=dev (on-profile: dev)

./config/application.yaml
    app.mode=external
```

Tệp ngoài JAR ở một vị trí cấu hình mặc định có thể được ưu tiên hơn tệp classpath. Khi đó `external` có thể là giá trị cuối cùng, ngay cả khi tài liệu `dev` nằm sau tài liệu chung bên trong classpath.

Cũng vậy, đối số dòng lệnh:

```bash
java -jar app.jar --spring.profiles.active=dev --app.mode=cli
```

thường có ưu tiên cao hơn cấu hình trong tệp. **Quy tắc “tài liệu phía sau thắng” chỉ áp dụng trong ngữ cảnh thứ tự tài liệu đang xét**, không thay thế toàn bộ hệ thống ưu tiên của Spring Boot.

## 8. Một tệp nhiều tài liệu khác gì nhiều tệp theo profile?

Có hai cách tổ chức phổ biến.

### Cách A — một tệp vật lý, nhiều tài liệu logic

```text
src/main/resources/
└── application.yaml
```

Trong đó:

```yaml
app:
  endpoint: https://api.example.test
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: dev
app:
  endpoint: http://localhost:8081

---
spring:
  config:
    activate:
      on-profile: prod
app:
  timeout: 10s
```

Tất cả phần chung, `dev` và `prod` nằm trong một tệp. Người đọc xem một nơi là thấy các biến thể; đổi lại, tệp có thể dài và dễ xuất hiện nhiều tài liệu cùng ghi đè một khóa.

### Cách B — nhiều tệp vật lý theo profile

```text
src/main/resources/
├── application.yaml
├── application-dev.yaml
└── application-prod.yaml
```

`application.yaml`:

```yaml
app:
  endpoint: https://api.example.test
  timeout: 5s
```

`application-dev.yaml`:

```yaml
app:
  endpoint: http://localhost:8081
```

`application-prod.yaml`:

```yaml
app:
  timeout: 10s
```

Spring Boot nhận biết tệp theo tên `application-{profile}.yaml` khi profile tương ứng được kích hoạt.

| Tiêu chí | Một tệp nhiều tài liệu | Nhiều tệp theo profile |
| --- | --- | --- |
| Số tệp vật lý | Ít, có thể chỉ một | Nhiều tệp |
| Ranh giới | `---` trong YAML hoặc `#---` trong properties | Ranh giới tệp |
| Cách chọn phần theo profile | `spring.config.activate.on-profile` | Tên tệp chứa hậu tố profile |
| Dễ thấy mọi biến thể ở một chỗ | Có | Cần mở các tệp liên quan |
| Dễ tách quyền sở hữu hoặc đóng gói tệp theo môi trường | Kém linh hoạt hơn | Có thể thuận tiện hơn |
| Nguy cơ lặp khóa | Có giữa các tài liệu | Có giữa các tệp |
| Cách tính ưu tiên | Thứ tự tài liệu và các quy tắc config data khác | Vị trí tệp, profile và các nguồn khác |

Hai cách đều hợp lệ; Spring Boot cho phép dùng đồng thời trong một dự án. Tuy nhiên, dùng cả hai không có quy ước sẽ khiến người bảo trì khó nhận ra giá trị nào được ghi đè.

Một điều quan trọng: **tệp `application-dev.yaml` cũng có thể chứa nhiều tài liệu YAML**. “Tệp theo profile” và “tệp nhiều tài liệu” là hai chiều tổ chức khác nhau, không phải hai tính năng loại trừ nhau.

### Nên chọn cách nào?

- Nếu số biến thể nhỏ và các tài liệu điều kiện ngắn: nhiều tài liệu trong một `application.yaml` giúp tập trung cấu hình.
- Nếu khác biệt môi trường lớn hoặc có nhiều tệp phụ thuộc: nhiều tệp theo profile thường dễ bảo trì hơn.
- Nếu cấu hình do hệ thống triển khai cấp: có thể vẫn dùng tệp ngoài JAR hoặc các nguồn phù hợp với hạ tầng, không bắt buộc đưa mọi giá trị vào `application.yaml`.
- Bất kể chọn cách nào, cần làm rõ **các giá trị chung**, **các giá trị riêng theo profile** và **nguồn nào có quyền ghi đè**.

## 9. Tài liệu có điều kiện theo nền tảng đám mây

Ngoài `on-profile`, Spring Boot 3.3 còn hỗ trợ điều kiện:

```properties
spring.config.activate.on-cloud-platform=kubernetes
```

Hoặc trong YAML:

```yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
```

Tài liệu này chỉ phù hợp khi Spring Boot nhận diện nền tảng đám mây tương ứng. Ví dụ:

```yaml
app:
  discovery:
    mode: static

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
app:
  discovery:
    mode: cluster
```

Trong môi trường không được nhận diện là Kubernetes, tài liệu chung có thể cung cấp `app.discovery.mode=static`. Trong môi trường Kubernetes được nhận diện, tài liệu điều kiện có thể ghi đè thành `cluster`.

Cơ chế này cho thấy “tài liệu có điều kiện” **không chỉ đồng nghĩa với “tài liệu theo profile”**. Điều kiện có thể xét bối cảnh triển khai. Không nên dùng tùy tiện điều kiện đám mây nếu chương trình cần điều khiển rõ ràng bằng profile: hành vi phụ thuộc vào cách Spring Boot nhận diện nền tảng.

## 10. Những thuộc tính không được đặt trong tài liệu kích hoạt theo profile

Cần phân biệt hai nhóm:

- **Khai báo điều kiện của tài liệu:** `spring.config.activate.on-profile`.
- **Kích hoạt profile cho toàn ứng dụng:** `spring.profiles.active`, `spring.profiles.include` và các thiết lập liên quan đến nhóm profile.

Trong Spring Boot 3.3, `spring.profiles.active` và `spring.profiles.include` chỉ nên đặt trong những tài liệu phù hợp không bị kích hoạt theo profile. Chúng không được sử dụng trong tài liệu đặc thù profile hoặc tài liệu được kích hoạt bằng `spring.config.activate.on-profile`.

Ví dụ **không hợp lệ**:

```yaml
spring:
  config:
    activate:
      on-profile: dev
  profiles:
    active: prod
```

Đoạn mã trên cố dùng tài liệu chỉ kích hoạt ở `dev` để tự thay đổi profile hoạt động sang `prod`. Việc chọn profile phải được xác định từ các nguồn hợp lệ trước khi Spring Boot quyết định tài liệu nào được kích hoạt.

Ví dụ **hợp lý** hơn nếu mục đích là cấu hình theo profile:

```yaml
app:
  feature-enabled: false

---
spring:
  config:
    activate:
      on-profile: dev
app:
  feature-enabled: true
```

Rồi chọn profile khi khởi động:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Tương tự, không nên nhầm `spring.config.activate.on-profile=dev` với cách khai báo `spring.profiles.active=dev`. Một bên nói **“tài liệu này chỉ hợp lệ khi dev hoạt động”**, bên kia nói **“chọn dev làm profile hoạt động”**.

## 11. Liên kết cấu hình sau khi Spring Boot chọn tài liệu

Ứng dụng Java thường không cần biết một giá trị đã đến từ tài liệu logic thứ mấy. Sau khi nạp cấu hình, ứng dụng có thể dùng `Environment` hoặc `@ConfigurationProperties` như bình thường.

Giả sử `application.yaml` có:

```yaml
app:
  client:
    timeout: 5s
    max-retries: 3

---
spring:
  config:
    activate:
      on-profile: dev

app:
  client:
    timeout: 1s
```

Định nghĩa đối tượng:

```java
package example.documents;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientSettings(
        Duration timeout,
        int maxRetries
) {
}
```

Khi profile `dev` hoạt động, đối tượng `ClientSettings` sẽ nhận `timeout=1s`, `maxRetries=3` nếu không có nguồn khác ghi đè.

Chú ý sự khác nhau giữa:

1. **Tài liệu logic**: một khối bên trong `application.yaml`.
2. **Thuộc tính đã giải quyết**: chẳng hạn `app.client.timeout=1s`.
3. **Đối tượng Java**: record `ClientSettings`, có trường `Duration` và `int`.
4. **Spring bean**: đối tượng cấu hình được đăng ký để các bean khác nhận qua Dependency Injection.

Tài liệu logic không tự động tương ứng một bean. Spring Boot liên kết các giá trị có hiệu lực thành một đối tượng cấu hình có kiểu, sau khi đã xử lý điều kiện và ưu tiên.

## 12. Thực hành: một tệp YAML chứa ba tài liệu, chạy cùng một mã Java

Bạn có thể dùng dự án Spring Boot **3.3.x**, Java **17+** và dependency `spring-boot-starter`. Không cần thêm Web starter nếu chỉ muốn chạy ví dụ console.

### Bước 1 — tạo tệp `application.yaml`

Đặt tại `src/main/resources/application.yaml`:

```yaml
spring:
  application:
    name: logical-documents-lab

demo:
  message: Chế độ chung
  threshold: 10
  trace-enabled: false

---
spring:
  config:
    activate:
      on-profile: dev

demo:
  message: Chế độ lập trình
  threshold: 3
  trace-enabled: true

---
spring:
  config:
    activate:
      on-profile: prod

demo:
  message: Chế độ production
  threshold: 100
```

Ở đây tệp chứa ba tài liệu logic; hai tài liệu cuối có điều kiện.

### Bước 2 — viết ứng dụng in cấu hình

Tạo `src/main/java/example/documents/DocumentDemoApplication.java`:

```java
package example.documents;

import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class DocumentDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DocumentDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showValues(Environment env) {
        return args -> {
            System.out.println("profiles="
                    + Arrays.toString(env.getActiveProfiles()));
            System.out.println("message="
                    + env.getProperty("demo.message"));
            System.out.println("threshold="
                    + env.getProperty("demo.threshold"));
            System.out.println("traceEnabled="
                    + env.getProperty("demo.trace-enabled"));
        };
    }
}
```

`Environment` phản ánh các giá trị cấu hình đã được Spring giải quyết. Phần `getActiveProfiles()` giúp nhận diện profile được kích hoạt trong lần chạy.

### Bước 3 — chạy không chọn profile

Nếu dùng Maven wrapper:

```bash
./mvnw spring-boot:run
```

Hoặc đóng gói thành JAR rồi chạy. Thay `app.jar` bằng tên file JAR thật:

```bash
java -jar app.jar
```

Các dòng giá trị chính dự kiến:

```text
profiles=[]
message=Chế độ chung
threshold=10
traceEnabled=false
```

`profiles=[]` nghĩa là không có **active profile** được chỉ định; Spring vẫn có khái niệm profile mặc định, nhưng tài liệu ở ví dụ không đặt điều kiện theo profile mặc định ấy.

### Bước 4 — kích hoạt `dev`

Chạy:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Kết quả dự kiến:

```text
profiles=[dev]
message=Chế độ lập trình
threshold=3
traceEnabled=true
```

Lúc này tài liệu logic thứ hai hoạt động, tài liệu thứ ba không hoạt động.

### Bước 5 — kích hoạt `prod`

```bash
java -jar app.jar --spring.profiles.active=prod
```

Kết quả dự kiến:

```text
profiles=[prod]
message=Chế độ production
threshold=100
traceEnabled=false
```

`traceEnabled` vẫn là `false` từ tài liệu chung vì tài liệu `prod` không ghi đè khóa này.

### Bước 6 — quan sát ưu tiên trong cùng tệp

Chèn **một tài liệu thứ tư ở cuối `application.yaml`** để minh họa thêm một khối luôn hoạt động:

```yaml
---
demo:
  threshold: 999
```

Tài liệu này không có `on-profile`; nó được xét trong mọi profile. Do nằm phía sau, nó có thể ghi đè `demo.threshold` ở cả ba trường hợp thành `999`, nếu không có nguồn cao hơn ghi đè.

Bài thử này cho thấy một tệp nhiều tài liệu có thể trở nên khó hiểu khi người viết thêm khối chung ở cuối. Nếu mục tiêu của bạn là “giá trị chung làm mặc định, giá trị theo profile ghi đè”, hãy **đặt tài liệu chung ở trước** và tài liệu theo profile ở phía sau.

Sau khi thực hành, bỏ tài liệu thứ tư để quay về ví dụ ban đầu.

### Bước 7 — kiểm tra nguồn ghi đè ngoài tài liệu

Vẫn dùng `application.yaml` ban đầu, chạy:

```bash
java -jar app.jar --spring.profiles.active=dev --demo.threshold=77
```

Khi đó `demo.threshold=77` từ đối số dòng lệnh có thể ghi đè giá trị `3` trong tài liệu `dev`. Đây là minh chứng rằng thứ tự tài liệu trong tệp không quyết định ưu tiên của **toàn bộ** ứng dụng.

## 13. Thực hành tương đương bằng `application.properties`

Đổi tệp cấu hình của ứng dụng thử nghiệm thành `src/main/resources/application.properties` và sử dụng **một định dạng duy nhất** cho lần thử này:

```properties
spring.application.name=logical-documents-lab

demo.message=Chế độ chung
demo.threshold=10
demo.trace-enabled=false

#---
spring.config.activate.on-profile=dev
demo.message=Chế độ lập trình
demo.threshold=3
demo.trace-enabled=true

#---
spring.config.activate.on-profile=prod
demo.message=Chế độ production
demo.threshold=100
```

Chạy lại cùng lớp Java ở phần trước. Các giá trị sẽ cho thấy cơ chế nhiều tài liệu logic cũng được Spring Boot hỗ trợ trong `.properties`.

**Tránh giữ đồng thời `application.yaml` và `application.properties` có các khóa trùng trong cùng vị trí khi bạn đang thử nghiệm**, vì khi đó quy tắc ưu tiên giữa các định dạng cũng tham gia. Để học riêng một cơ chế, hãy dùng một định dạng mỗi lần.

Một chi tiết cần nhớ: dấu phân tách trong properties là `#---` hoặc `!---`, **không phải** dòng `---` trần như trong YAML. Viết sai dấu phân tách có thể khiến tệp bị phân tích khác dự kiến hoặc gây lỗi.

## 14. Kết hợp tài liệu logic với `spring.config.import`

Trong Spring Boot 3.3, một tài liệu logic có thể có `spring.config.import` để nhập thêm cấu hình. Ví dụ:

```yaml
app:
  source: common

---
spring:
  config:
    activate:
      on-profile: dev
    import: "optional:classpath:/config/dev-extra.properties"

app:
  source: dev
```

Ý nghĩa:

- Tài liệu đầu chứa cấu hình chung.
- Tài liệu thứ hai có điều kiện `on-profile: dev`.
- Khi tài liệu thứ hai được kích hoạt, Spring Boot còn xem xét tài nguyên được khai báo trong `spring.config.import`.
- Giá trị từ tài liệu nhập được xét theo quy tắc ưu tiên của hệ thống Config Data; nếu tài nguyên nhập cùng khai báo một khóa, nó có thể ghi đè giá trị trong tài liệu chứa import.

Ở đây có hai loại ranh giới:

```text
application.yaml (tệp vật lý A)
  |
  +-- tài liệu logic 1
  |
  +-- tài liệu logic 2 (điều kiện dev)
        |
        +-- import -> config/dev-extra.properties (tệp vật lý B)
```

**Tài liệu logic thứ hai vẫn là một phần của tệp A**; tệp B là một tài nguyên khác được nhập thêm. Đừng nhầm “tài liệu 2” với “tệp 2”.

Nếu sơ đồ có nhiều import và nhiều điều kiện, trước tiên hãy xác định những tài liệu nào được kích hoạt, sau đó xét quan hệ import và thứ tự ưu tiên. Trong thực tế nên hạn chế lồng quá sâu để đường đi của giá trị vẫn dễ theo dõi.

## 15. Những giới hạn và lưu ý về cách đọc tệp

### 15.1. `@PropertySource` không phải cơ chế tương đương của Config Data

Tệp nhiều tài liệu được xử lý bởi cơ chế cấu hình của Spring Boot khi nạp `application.yaml`, `application.properties` và những vị trí Config Data phù hợp.

Không nên giả định rằng:

```java
@PropertySource("classpath:custom.properties")
```

sẽ có đầy đủ cùng cách xử lý **nhiều tài liệu logic** như cơ chế Config Data của Spring Boot. Tài liệu Spring Boot nêu rõ các tệp properties hoặc YAML có nhiều tài liệu **không thể được nạp bằng `@PropertySource` hoặc `@TestPropertySource` theo cách đó**.

Nếu muốn nạp một tệp nhiều tài liệu như cấu hình ứng dụng, nên dùng các vị trí Config Data hoặc `spring.config.import` thay vì chờ `@PropertySource` hiểu mọi dấu phân tách.

### 15.2. Một tệp vật lý không có nghĩa chỉ có một nguồn giá trị

Khi Spring Boot tách các tài liệu logic, mỗi tài liệu được xét riêng trong cơ chế cấu hình. Vì vậy, số tệp trong thư mục không phản ánh đầy đủ số tài liệu cấu hình thực sự tham gia.

Ví dụ:

```text
application.yaml                1 file, 3 documents
application-dev.yaml            1 file, 2 documents
external-settings.properties    1 file, 2 documents
-----------------------------------------------------
Tổng cộng                        3 file, 7 documents
```

Con số bảy chỉ là tổng số tài liệu **được khai báo**. Bao nhiêu tài liệu thực sự **được kích hoạt** còn tùy profile, điều kiện đám mây, vị trí được nạp và nguồn cấu hình đang dùng.

### 15.3. Chú thích không chia tài liệu

Ví dụ:

```yaml
app:
  mode: basic

# Cấu hình cho dev
app:
  mode: development
```

Dòng chú thích không tạo ra tài liệu mới. Bạn cần `---` và, nếu muốn có điều kiện, `spring.config.activate.on-profile`.

Trong YAML, việc lặp các khóa ở cùng cấp trong **một tài liệu** có thể dẫn tới lỗi phân tích hoặc hành vi không như ý, tùy quy tắc parser. Không sử dụng chú thích như một phương tiện “ngầm” chia tài liệu.

### 15.4. YAML rất nhạy với thụt lề

Đúng:

```yaml
spring:
  config:
    activate:
      on-profile: dev
```

Sai về mặt ý nghĩa cấu trúc nếu viết:

```yaml
spring:
  config:
    activate:
  on-profile: dev
```

Dòng `on-profile` ở ví dụ thứ hai không nằm đúng dưới `activate`. Hãy dùng dấu cách, tránh tab, và để `---` bắt đầu ở đầu dòng. Nếu cấu hình có điều kiện không hoạt động, kiểm tra cả cú pháp và cấu trúc lồng của YAML.

### 15.5. Danh sách không luôn được ghép giữa tài liệu

Nếu tài liệu chung có:

```yaml
app:
  hosts:
    - a.example.test
    - b.example.test

---
spring:
  config:
    activate:
      on-profile: dev
app:
  hosts:
    - localhost
```

Khi liên kết vào `List<String>`, danh sách từ nguồn ưu tiên cao hơn thường **thay thế** danh sách của nguồn thấp hơn, không tự nối phần tử `localhost` vào cuối hai phần tử chung. Cần phân biệt ghi đè khóa đơn với cách liên kết cấu trúc danh sách.

### 15.6. Cấu hình có điều kiện không phải cơ chế bảo vệ bí mật

Một tài liệu chỉ kích hoạt với `prod` vẫn có thể nằm nguyên trong JAR hoặc trong repository nếu bạn đóng gói toàn bộ tệp `application.yaml`. Bởi vậy, không ghi mật khẩu, khóa API hoặc mã thông báo thật trong tài liệu `prod` chỉ vì nó không hoạt động ở `dev`. Điều kiện kích hoạt chỉ quyết định **khi nào giá trị tham gia**, không mã hóa hoặc che giấu nội dung tệp.

## 16. Chẩn đoán khi tài liệu có điều kiện không được dùng

Khi thấy một cấu hình bị bỏ qua, nên đi theo trình tự sau:

```text
Xác định khóa có kết quả khác dự kiến
           |
           v
Mở đúng tệp vật lý được ứng dụng đang chạy nạp
           |
           v
Đếm và xác định ranh giới tài liệu logic
           |
           v
Xem điều kiện on-profile / on-cloud-platform
           |
           v
Xác nhận profile và môi trường chạy
           |
           v
Kiểm tra thứ tự tài liệu đang được kích hoạt
           |
           v
Kiểm tra các nguồn có ưu tiên cao hơn
           |
           v
Đọc giá trị cuối từ Spring Environment
```

### Kiểm tra profile đang hoạt động

Trong một bean, có thể đọc:

```java
String[] profiles = environment.getActiveProfiles();
```

Hoặc xem log khởi động của Spring Boot để hiểu profile được chọn. Đừng tự suy luận profile từ tên máy hoặc tên thư mục triển khai.

### Đọc giá trị có hiệu lực

Ví dụ ở mức bean:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@Bean
ApplicationRunner showConfig(Environment env) {
    return args -> System.out.println(
            "demo.threshold=" + env.getProperty("demo.threshold"));
}
```

Đoạn này là **phương thức được đặt bên trong một lớp `@Configuration` hoặc `@SpringBootApplication`**. Nó cho thấy giá trị cuối, nhưng không tự kể toàn bộ lịch sử tài liệu nào đã thắng.

### Bật log chi tiết cho cơ chế Config Data

Khi thật sự cần chẩn đoán quá trình nạp tệp:

```bash
java -jar app.jar --logging.level.org.springframework.boot.context.config=TRACE
```

Chỉ nên bật mức log chi tiết này tạm thời trong môi trường phát triển phù hợp. Không đưa nội dung cấu hình nhạy cảm hoặc log nội bộ lên nơi công khai.

### Những lỗi cần phân biệt

| Hiện tượng | Khả năng | Cách xác định |
| --- | --- | --- |
| Dòng cấu hình dưới `#` không được xem là tài liệu mới | Đã dùng chú thích thay cho dấu phân tách | Kiểm tra `---` (YAML) hoặc `#---`/`!---` (properties) |
| Giá trị của `dev` không xuất hiện | Profile `dev` chưa hoạt động hoặc điều kiện sai | Xem `getActiveProfiles()`, kiểm tra `on-profile` |
| Giá trị `prod` xuất hiện khi cũng bật `dev` | Nhiều tài liệu cùng hoạt động và tài liệu `prod` nằm sau | Kiểm tra các active profile và thứ tự tài liệu |
| Đổi YAML nhưng chạy JAR không thấy thay đổi | JAR chưa chứa phiên bản tệp mới | Đóng gói lại hoặc kiểm tra nguồn bên ngoài |
| Giá trị trong tài liệu chung vẫn thắng dự kiến | Có tài liệu sau hoặc nguồn ưu tiên khác ghi đè | Liệt kê các nguồn, xét điều kiện và thứ tự |
| Ứng dụng lỗi khi bắt đầu | YAML sai cấu trúc, thuộc tính điều kiện đặt sai chỗ hoặc vi phạm giới hạn profile | Đọc thông báo khởi động và vị trí được chỉ ra |
| `@PropertySource` không hiểu multi-document | Dùng cơ chế đọc tệp khác Config Data | Nạp tệp qua cơ chế cấu hình Boot phù hợp |

## 17. Quy ước tổ chức nhiều tài liệu trong một tệp

Một mẫu dễ đọc:

```yaml
# 1. Cấu hình chung
app:
  service:
    endpoint: https://api.example.test
    timeout: 5s
    max-retries: 3

---
# 2. Cấu hình phát triển
spring:
  config:
    activate:
      on-profile: dev
app:
  service:
    endpoint: http://localhost:8081
    timeout: 1s

---
# 3. Cấu hình triển khai thật
spring:
  config:
    activate:
      on-profile: prod
app:
  service:
    timeout: 10s
```

Cách tổ chức này có ưu điểm:

1. **Giá trị chung nằm ở đầu tệp**, là nền tảng của mọi môi trường.
2. **Phần thay đổi theo profile nằm sau**, chỉ khai báo những khóa thực sự khác.
3. **Tên khóa thống nhất** giúp biết giá trị nào đang ghi đè.
4. **Ranh giới `---` rõ ràng** giúp người đọc nhận ra số tài liệu logic.
5. **Điều kiện ở ngay đầu khối** giúp hiểu nhanh vì sao khối có hoặc không hoạt động.
6. **Không đặt một tài liệu chung ghi đè vô tình ở cuối** nếu muốn các profile có quyền điều chỉnh.
7. **Không dùng điều kiện để chứa bí mật trực tiếp trong Git**.

Với tệp `.properties`, áp dụng cùng nguyên tắc nhưng dùng dấu phân tách tương ứng và cú pháp phẳng:

```properties
# Phần chung
app.service.endpoint=https://api.example.test
app.service.timeout=5s
app.service.max-retries=3

#---
spring.config.activate.on-profile=dev
app.service.endpoint=http://localhost:8081
app.service.timeout=1s

#---
spring.config.activate.on-profile=prod
app.service.timeout=10s
```

Khi quy mô tài liệu trở nên quá lớn, tách thành nhiều tệp theo profile hoặc chức năng có thể giúp nhóm phát triển bảo trì dễ hơn. Không có yêu cầu mọi cấu hình theo môi trường phải nằm trong một tệp duy nhất.

## 18. Bài tập dự đoán giá trị

### Bài 1 — một tệp, hai tài liệu không điều kiện

```yaml
app:
  label: first
  count: 2

---
app:
  label: second
```

**Hỏi:** `app.label` và `app.count` cuối cùng là gì?

**Gợi ý đáp án:** `second` và `2`. Cả hai tài liệu cùng được xét; tài liệu sau ghi đè khóa trùng nhưng không loại bỏ khóa riêng ở tài liệu trước.

### Bài 2 — tài liệu sau không hoạt động

```yaml
app:
  label: common

---
spring:
  config:
    activate:
      on-profile: dev
app:
  label: developer
```

Chạy ứng dụng không kích hoạt `dev`.

**Hỏi:** `app.label` là gì?

**Đáp án:** `common`, vì tài liệu thứ hai không thỏa điều kiện.

### Bài 3 — hai profile cùng hoạt động

```yaml
app:
  label: base

---
spring:
  config:
    activate:
      on-profile: dev
app:
  label: dev

---
spring:
  config:
    activate:
      on-profile: test
app:
  label: test
```

Chạy với:

```bash
java -jar app.jar --spring.profiles.active=dev,test
```

**Hỏi:** Trong chính tệp này, tài liệu nào ghi đè khóa `app.label`?

**Đáp án:** Cả tài liệu `dev` và `test` đều có điều kiện phù hợp. Tài liệu `test` nằm sau nên có thể cung cấp `app.label=test`, nếu không có nguồn khác ưu tiên cao hơn.

### Bài 4 — phân biệt ranh giới tệp và ranh giới tài liệu

Cho:

```text
application.yaml
  document 1: app.color=blue
  document 2: app.color=green (on-profile dev)

application-dev.yaml
  document 1: app.color=yellow
```

**Hỏi:** Có bao nhiêu tệp vật lý và bao nhiêu tài liệu logic? Có thể chỉ dựa vào vị trí dòng YAML để kết luận giá trị cuối cùng không?

**Đáp án:** Hai tệp vật lý, ba tài liệu logic. Không nên bỏ qua ưu tiên giữa các tệp và nguồn khác; phải xét tệp theo profile cùng toàn bộ quy tắc config data.

### Bài 5 — properties dùng sai dấu

```properties
app.name=demo
# Phần dev
spring.config.activate.on-profile=dev
app.name=demo-dev
```

**Hỏi:** Tại sao đây không phải hai tài liệu logic?

**Đáp án:** Vì không có dòng `#---` hoặc `!---` để tạo ranh giới. Dòng `# Phần dev` chỉ là chú thích. Không nên đặt điều kiện `spring.config.activate.on-profile` giữa một tài liệu rồi nghĩ rằng nó chỉ áp dụng cho các dòng nằm bên dưới.

### Bài 6 — giá trị đến từ đâu?

`application.yaml`:

```yaml
app:
  retries: 3

---
spring:
  config:
    activate:
      on-profile: dev
app:
  retries: 1
```

Chạy:

```bash
java -jar app.jar --spring.profiles.active=dev --app.retries=9
```

**Hỏi:** Bean `@ConfigurationProperties` có thể nhận `retries` bằng bao nhiêu?

**Đáp án:** `9`, vì đối số dòng lệnh có thể ghi đè các tài liệu YAML. Điều kiện `dev` vẫn hoạt động nhưng không phải nguồn quyết định giá trị cuối của khóa đó.

## 19. Những điều cần nhớ

Một bản đồ khái niệm:

```text
Một tệp vật lý (application.yaml / application.properties)
       |
       +-- Tài liệu logic 1
       |
       +-- Tài liệu logic 2 -- điều kiện kích hoạt?
       |
       +-- Tài liệu logic 3 -- điều kiện kích hoạt?
                    |
                    v
       Tài liệu phù hợp được xét theo thứ tự
                    |
                    v
       Kết hợp với các nguồn cấu hình còn lại
                    |
                    v
       Environment và @ConfigurationProperties
                    |
                    v
       Bean sử dụng giá trị có hiệu lực
```

Các kết luận chính:

- **Một tệp vật lý có thể chứa nhiều tài liệu cấu hình logic.**
- **YAML** dùng dòng `---`; **`.properties`** dùng dòng `#---` hoặc `!---` làm ranh giới.
- Mỗi tài liệu logic có thể có điều kiện kích hoạt riêng, điển hình là `spring.config.activate.on-profile`.
- Tài liệu không có điều kiện thích hợp làm nơi đặt giá trị chung. Khi tài liệu sau cũng được kích hoạt, các khóa trùng của tài liệu trước có thể bị ghi đè.
- **Tài liệu theo profile** và **tệp theo profile** là hai cách tổ chức cấu hình khác nhau, có thể cùng tồn tại.
- Thứ tự tài liệu trong một tệp chỉ là một phần của cơ chế ưu tiên; tệp ngoài JAR, biến môi trường và đối số dòng lệnh cũng có thể quyết định giá trị cuối cùng.
- Tài liệu có điều kiện không phải cơ chế bảo mật và không tự tạo một Spring bean riêng.

Khi nhìn thấy một tệp `application.yaml` dài, bước đầu tiên là tìm các dấu `---` để biết có bao nhiêu tài liệu logic. Sau đó kiểm tra điều kiện kích hoạt của mỗi tài liệu, profile thực tế và những nguồn cấu hình khác. Cách đọc theo từng lớp này giúp bạn giải thích cấu hình Spring Boot 3.3 một cách có căn cứ, ngay cả khi toàn bộ nội dung được viết trong một tệp.

## Tài liệu tham khảo

- Spring Boot 3.3 Reference — Externalized Configuration, phần *Working With Multi-Document Files*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 Reference — Externalized Configuration, phần *Activation Properties*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 Reference — *Profile Specific Files* và *Property Ordering*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html

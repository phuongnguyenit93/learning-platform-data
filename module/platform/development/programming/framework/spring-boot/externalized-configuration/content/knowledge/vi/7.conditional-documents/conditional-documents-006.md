# Kích hoạt tài liệu cấu hình theo nền tảng bằng `spring.config.activate.on-cloud-platform`

## 1. Bối cảnh và mục tiêu

Một ứng dụng Spring Boot có thể được chạy trên laptop, máy chủ thông thường, Docker hoặc nền tảng điều phối như Kubernetes. Cùng một mã nguồn và bản build vẫn cần cách cấu hình khác nhau: chạy local có thể dùng một file trên ổ đĩa, còn Kubernetes có thể cung cấp cấu hình từ ConfigMap hoặc Secret được mount thành file.

Spring Boot hỗ trợ **tài liệu cấu hình có điều kiện** (conditional configuration documents) trong cơ chế **Config Data**. Thuộc tính:

~~~properties
spring.config.activate.on-cloud-platform=kubernetes
~~~

cho biết: **chỉ kích hoạt tài liệu cấu hình chứa thuộc tính này khi Spring Boot xác định nền tảng cloud đang hoạt động là Kubernetes**.

Trong YAML, thuộc tính tương ứng là:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
~~~

Mục đích là viết một bộ cấu hình dùng chung nhưng chỉ áp dụng một số property khi môi trường chạy phù hợp, thay vì sao chép nhiều file hoặc bắt buộc người triển khai luôn truyền thêm một profile.

Cần phân biệt ba khái niệm:

- **Cloud platform**: loại nền tảng chạy ứng dụng mà Spring Boot nhận diện, ví dụ Kubernetes.
- **Spring profile**: tên môi trường hoặc tính năng do ứng dụng sử dụng, ví dụ `dev`, `test`, `prod`.
- **Config Data document**: một tài liệu logic trong `application.yml`, `application.yaml` hoặc `application.properties`; có thể được kích hoạt có điều kiện.

`spring.config.activate.on-cloud-platform` kiểm tra nền tảng cloud. Nó **không tự bật profile**, không tự tạo bean Kubernetes và không tự kết nối tới API server của Kubernetes.

## 2. Spring Boot kích hoạt một document như thế nào?

Trong mô hình Config Data của Spring Boot hiện đại, một file cấu hình vật lý có thể chứa nhiều **document logic**. Các document được xử lý theo thứ tự; document ở phía sau có thể ghi đè property của document trước trong cùng ngữ cảnh nạp.

Một document có thể khai báo metadata kích hoạt:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
~~~

Spring Boot sẽ xét điều kiện trước khi đưa các property của document này vào nguồn cấu hình hiệu lực.

- **Điều kiện đúng:** document được nạp và các property của nó có thể tham gia vào `Environment`.
- **Điều kiện sai:** document bị bỏ qua; các property nằm riêng trong document đó không trở thành cấu hình hiệu lực từ nguồn này.
- **Không có điều kiện kích hoạt:** document có thể được nạp bình thường theo location, tên file, profile và các quy tắc Config Data khác.

Ví dụ, ứng dụng có một cấu hình chung cho mọi môi trường và một cấu hình riêng cho Kubernetes:

~~~yaml
# application.yml
app:
  storage:
    directory: ./data
  messaging:
    endpoint: localhost:9092
---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes

app:
  storage:
    directory: /var/app/data
  messaging:
    endpoint: messaging.default.svc.cluster.local:9092
~~~

Diễn giải:

1. Khi chạy local và Spring Boot không phát hiện Kubernetes, document đầu cung cấp `app.storage.directory=./data` và `app.messaging.endpoint=localhost:9092`.
2. Khi chạy trong môi trường được nhận diện là Kubernetes, document thứ hai được kích hoạt. Trong phạm vi file này, nó ghi đè hai giá trị bằng `/var/app/data` và địa chỉ dịch vụ nội bộ tương ứng.
3. Một nguồn khác có độ ưu tiên cao hơn, như command-line argument trong cấu hình thông dụng, vẫn có thể ghi đè các giá trị trên.

Ví dụ chỉ minh họa cơ chế cấu hình. Địa chỉ `messaging.default.svc.cluster.local` chỉ hoạt động nếu thực tế có Service và DNS tương ứng; Spring Boot không tạo chúng từ YAML này.

## 3. Phân biệt phát hiện cloud platform và kích hoạt profile

`spring.config.activate.on-cloud-platform` dùng thông tin **CloudPlatform** được Spring Boot nhận diện. `spring.config.activate.on-profile` sử dụng một biểu thức profile. Hai thuộc tính cùng thuộc nhóm `spring.config.activate.*` nhưng kiểm tra hai điều kiện khác nhau.

| Thuộc tính | Kiểm tra | Ví dụ |
| --- | --- | --- |
| `spring.config.activate.on-cloud-platform` | Nền tảng cloud Spring Boot nhận diện | `kubernetes` |
| `spring.config.activate.on-profile` | Biểu thức Spring profile đang hoạt động | `prod | staging` |
| `spring.profiles.active` | Khai báo danh sách profile cần kích hoạt | `prod,observability` |
| `spring.main.cloud-platform` | Ghi đè kết quả tự phát hiện nền tảng cloud | `kubernetes` |

Ví dụ, trong Kubernetes nhưng ứng dụng chỉ có profile `dev`:

- Document có `on-cloud-platform=kubernetes`: **đủ điều kiện** về cloud platform.
- Document có `on-profile=prod`: **không đủ điều kiện** về profile `prod`.
- Document chứa cả `on-cloud-platform=kubernetes` và `on-profile=prod`: **không được kích hoạt**, vì chưa thỏa cả hai.

Ngược lại, chạy profile `prod` ở máy local không khiến Boot coi môi trường đó là Kubernetes.

**Không có quy tắc mặc định “profile tên `kubernetes` được bật khi chạy trên Kubernetes”.** Nếu ứng dụng có file `application-kubernetes.yml`, file đó là file **profile-specific** và được chọn theo profile `kubernetes`, chứ không tự động được nạp chỉ vì runtime đang ở Kubernetes.

## 4. Cách Spring Boot xác định CloudPlatform

Spring Boot có enum `org.springframework.boot.cloud.CloudPlatform` để biểu diễn một số nền tảng cloud được nhận diện. Tùy phiên bản, danh sách có thể gồm Kubernetes, Cloud Foundry, Heroku, SAP, Nomad, Azure App Service và các nền tảng khác. Giá trị `NONE` biểu diễn trường hợp không có cloud platform được chọn.

Đối với Kubernetes, Spring Boot dùng các dấu hiệu đặc trưng của môi trường, chẳng hạn các biến môi trường liên quan đến Kubernetes Service, để xác định ứng dụng có đang chạy trên nền tảng này hay không.

Ví dụ, trong một môi trường Kubernetes thông thường có thể tồn tại các biến kiểu:

~~~text
KUBERNETES_SERVICE_HOST
KUBERNETES_SERVICE_PORT
~~~

Việc kiểm tra cụ thể có thể thay đổi theo phiên bản Spring Boot. Vì vậy, đừng thiết kế ứng dụng dựa trên giả định rằng chỉ cần sự hiện diện của một biến bất kỳ là đủ để luôn phát hiện Kubernetes.

### 4.1. Tự phát hiện không phải xác thực hạ tầng

Nhận diện CloudPlatform dựa vào thông tin môi trường. Nó hữu ích để lựa chọn cấu hình hoặc auto-configuration, nhưng **không phải** một cơ chế xác thực rằng tiến trình thực sự thuộc một Kubernetes cluster tin cậy.

Không nên dùng `on-cloud-platform` làm ranh giới bảo mật, ví dụ “nếu là Kubernetes thì tự cho phép truy cập tài nguyên nhạy cảm”. Quyền truy cập cần được thực thi bằng cơ chế bảo mật thật, như chính sách mạng, tài khoản dịch vụ, phân quyền và quản lý secret.

### 4.2. CloudPlatform có thể được ghi đè

Khi môi trường thật không cung cấp đủ dấu hiệu nhận diện, hoặc khi cần mô phỏng hành vi trong môi trường kiểm thử, có thể dùng:

~~~bash
java -jar app.jar --spring.main.cloud-platform=kubernetes
~~~

`spring.main.cloud-platform` yêu cầu Spring Boot dùng nền tảng được chỉ định thay cho kết quả tự nhận diện. Tương tự, cấu hình:

~~~bash
java -jar app.jar --spring.main.cloud-platform=none
~~~

có thể được dùng để vô hiệu hóa phát hiện cloud platform trong các trường hợp phù hợp.

Đây là một **tùy chọn khởi động ảnh hưởng đến phát hiện cloud**, không phải cách bật Spring profile. Nếu thêm `--spring.profiles.active=prod`, đó là thuộc tính khác:

~~~bash
java -jar app.jar \
  --spring.main.cloud-platform=kubernetes \
  --spring.profiles.active=prod
~~~

Lệnh trên có thể dùng để mô phỏng **Kubernetes + profile prod** nhằm quan sát các document có điều kiện. Nó không tạo một Kubernetes cluster, không mount ConfigMap, không kết nối Secret và không cung cấp dịch vụ mạng Kubernetes thật.

### 4.3. Kiểm tra enum theo phiên bản Boot

Tên hợp lệ trong `on-cloud-platform` dựa vào `CloudPlatform` của phiên bản Spring Boot đang dùng. Chẳng hạn Kubernetes dùng `kubernetes`; với nền tảng khác, nên tra tài liệu API của đúng phiên bản để chọn tên phù hợp.

Không suy ra rằng tên nhà cung cấp cloud bất kỳ đều hợp lệ, ví dụ đặt `on-cloud-platform=my-private-cloud` rồi kỳ vọng Boot nhận diện. Cơ chế này dựa trên tập giá trị có định nghĩa của Spring Boot; muốn bổ sung môi trường tự đặt tên, Spring profile hoặc một property riêng thường phù hợp hơn.

## 5. Ví dụ chuẩn với YAML nhiều document

Trong `application.yml`, dùng `---` để phân tách các document logic:

~~~yaml
# Document 1: luôn có thể được dùng làm cấu hình cơ sở
spring:
  application:
    name: order-service

app:
  storage:
    root: ./data
  endpoints:
    inventory: http://localhost:8081

---
# Document 2: chỉ được xét khi cloud platform là Kubernetes
spring:
  config:
    activate:
      on-cloud-platform: kubernetes

app:
  storage:
    root: /mnt/order-data
  endpoints:
    inventory: http://inventory.default.svc.cluster.local:8080
~~~

Spring Boot xử lý các document theo thứ tự từ trên xuống. Nếu document thứ hai được kích hoạt, nó có thể ghi đè các giá trị cùng khóa trong document thứ nhất. Nếu bị bỏ qua, cấu hình cơ sở vẫn có thể hoạt động.

### 5.1. Ý nghĩa của ba dấu gạch ngang

Trong YAML, dấu `---` phân tách các document. Nó phải được đặt ở vị trí hợp lệ của cú pháp YAML; nó không phải tên khóa và không phải profile.

Ví dụ sai khi hiểu `---` như một property:

~~~yaml
app:
  name: catalog
  ---: kubernetes
~~~

Cách này không tạo document có điều kiện. Cần có document riêng sau dấu phân cách và khai báo `spring.config.activate.on-cloud-platform` bên trong document đó.

### 5.2. Có thể có nhiều document theo nhiều nền tảng

Ví dụ minh họa:

~~~yaml
app:
  transport:
    mode: local

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
app:
  transport:
    mode: kubernetes

---
spring:
  config:
    activate:
      on-cloud-platform: cloud-foundry
app:
  transport:
    mode: cloud-foundry
~~~

Document Kubernetes và Cloud Foundry có điều kiện độc lập. Tên nền tảng cần được Spring Boot hỗ trợ và nhận diện. Việc sử dụng nhiều document giúp gom điều kiện trong cùng file, nhưng nếu file quá dài, có thể tổ chức thành các file Config Data riêng và nhập theo điều kiện.

### 5.3. Tránh đặt các khóa chưa có mặc định trong document có điều kiện

Nếu một khóa bắt buộc chỉ xuất hiện trong document Kubernetes:

~~~yaml
---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
app:
  payment:
    endpoint: http://payment.default.svc.cluster.local
~~~

thì chạy local có thể không có `app.payment.endpoint`. Nếu ứng dụng dùng `Environment.getRequiredProperty("app.payment.endpoint")` hoặc bind vào một field bắt buộc, quá trình khởi động có thể lỗi.

Có hai hướng giải quyết:

1. Cung cấp giá trị mặc định hợp lý trong document cơ sở.
2. Thiết kế thành phần sử dụng giá trị đó cũng chỉ được tạo khi điều kiện phù hợp được thỏa, ví dụ có profile hoặc condition riêng.

Đừng nhầm việc document bị bỏ qua với việc khóa được tự động nhận giá trị rỗng hoặc giá trị dự phòng.

## 6. Ví dụ tương đương với `application.properties`

Định dạng `.properties` không dùng `---` của YAML. Spring Boot hỗ trợ phân tách document bằng **`#---` hoặc `!---`**:

~~~properties
# application.properties
spring.application.name=order-service
app.storage.root=./data
app.endpoints.inventory=http://localhost:8081
#---
spring.config.activate.on-cloud-platform=kubernetes
app.storage.root=/mnt/order-data
app.endpoints.inventory=http://inventory.default.svc.cluster.local:8080
~~~

Khi Kubernetes được nhận diện, document sau `#---` được kích hoạt; ngược lại, nó bị bỏ qua.

### 6.1. Quy tắc đặt separator trong properties

Khi dùng multi-document properties:

- Separator phải nằm trên dòng riêng với đúng `#---` hoặc `!---` theo cú pháp Boot.
- Không có khoảng trắng ở đầu dòng separator.
- Phải có **chính xác ba dấu `-`**.
- Không đặt các dòng chú thích cùng tiền tố sát ngay trước hoặc sau separator theo cách vi phạm quy tắc phân tách của Boot.

Chẳng hạn, nên đặt phần chú thích giải thích vào bên trong các document ở nơi không gây nhập nhằng:

~~~properties
app.mode=local
#---
spring.config.activate.on-cloud-platform=kubernetes
app.mode=cluster
~~~

Trong hệ thống dùng Spring Framework thuần, `#---` thường chỉ là một dòng comment. Cơ chế chia document được Spring Boot xử lý khi nạp Config Data; `@PropertySource` và `@TestPropertySource` không xử lý multi-document properties theo cách này.

### 6.2. Không nhầm với dấu `#` comment thông thường

Một dòng:

~~~properties
# Kubernetes configuration
~~~

là comment bình thường. Nhưng `#---` có ngữ nghĩa đặc biệt khi Spring Boot nạp multi-document properties. Nếu chỉ muốn kẻ phân cách đẹp mắt, dùng dòng khác như:

~~~properties
# ===== Kubernetes-specific settings =====
~~~

## 7. Kết hợp điều kiện cloud platform và profile

Spring Boot hỗ trợ cả:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
      on-profile: "prod | staging"
~~~

Nghĩa là document chỉ được kích hoạt khi:

1. Cloud platform được xác định là **Kubernetes**.
2. Biểu thức profile `prod | staging` đúng, tức **ít nhất một** trong hai profile `prod` hoặc `staging` đang hoạt động.

**Hai điều kiện khác loại được kết hợp theo AND**. Bên trong biểu thức `on-profile`, toán tử `|` thể hiện OR giữa các lựa chọn profile.

Ví dụ hoàn chỉnh:

~~~yaml
app:
  feature:
    audit-enabled: false
  integration:
    endpoint: http://localhost:8080

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
      on-profile: "prod | staging"

app:
  feature:
    audit-enabled: true
  integration:
    endpoint: http://integration.default.svc.cluster.local:8080
~~~

Bảng diễn giải khi không có nguồn khác ghi đè:

| Cloud platform | Active profiles | Document thứ hai | `app.feature.audit-enabled` |
| --- | --- | --- | --- |
| Kubernetes | `prod` | Được kích hoạt | `true` |
| Kubernetes | `staging` | Được kích hoạt | `true` |
| Kubernetes | `dev` | Bị bỏ qua | `false` |
| Không phải Kubernetes | `prod` | Bị bỏ qua | `false` |
| Không phải Kubernetes | `dev` | Bị bỏ qua | `false` |

Nếu muốn chỉ kích hoạt trong môi trường Kubernetes **và** profile `prod`, dùng:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
      on-profile: prod
~~~

Nếu muốn document chạy trên nhiều cloud platform khác nhau, không thể tự giả định `on-cloud-platform` nhận chuỗi biểu thức OR như `on-profile`. Có thể tạo các document riêng cho từng platform hoặc tổ chức cấu hình theo cơ chế khác được phiên bản Boot hỗ trợ.

## 8. Kết hợp với `spring.config.import` và Config Tree

Đây là một tình huống phổ biến khi chạy ứng dụng trên Kubernetes: cấu hình được gắn dưới dạng **volume**, mỗi file chứa một giá trị cấu hình.

Giả sử container có cấu trúc:

~~~text
/etc/app-config/
├── api.endpoint
└── api.timeout
~~~

Nội dung:

~~~text
/etc/app-config/api.endpoint  ->  https://api.internal.example
/etc/app-config/api.timeout   ->  5s
~~~

Spring Boot hỗ trợ `configtree:`, cho phép nạp từng file trong thư mục dưới dạng property có tên tương ứng. Có thể chỉ nhập cây cấu hình này khi chạy trên Kubernetes:

~~~yaml
app:
  api:
    endpoint: http://localhost:8081
    timeout: 2s

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
    import: "optional:configtree:/etc/app-config/"
~~~

Khi cloud platform được nhận diện là Kubernetes, document điều kiện được xét và import Config Tree có thể đưa `api.endpoint` và `api.timeout` vào `Environment`. Khi chạy local, document đó không được kích hoạt và import liên quan không cần tham gia nạp cấu hình.

**Lưu ý về ví dụ:** hai khóa trong Config Tree ở đây là `api.endpoint` và `api.timeout`, khác với `app.api.endpoint` và `app.api.timeout` trong document cơ sở. Nếu muốn ghi đè trực tiếp các khóa `app.api.*`, hãy đặt tên file trong cây phù hợp (ví dụ `app.api.endpoint`, `app.api.timeout`), hoặc đổi tên cấu hình cơ sở cho thống nhất.

Để nạp các file bắt buộc từ một directory, có thể bỏ `optional:`:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
    import: "configtree:/etc/app-config/"
~~~

Lúc đó thiếu location bắt buộc có thể làm ứng dụng không khởi động được. Điều này thường hữu ích nếu thiếu ConfigMap/Secret là lỗi triển khai cần phát hiện sớm. `optional:` chỉ cho phép location vắng mặt; nó không đảm bảo bỏ qua lỗi định dạng, quyền truy cập hoặc binding.

### 8.1. Config Tree khác với `file:`

Hai location sau không tương đương:

~~~text
configtree:/etc/app-config/
file:/etc/app-config/
~~~

`configtree:` xem tên file trong cây như tên property; `file:` thông thường được dùng để tìm các file cấu hình theo tên như `application.properties` hoặc `application.yml`.

Chọn đúng loại import để ứng dụng hiểu dữ liệu được mount. Không cần cài Spring Cloud Kubernetes chỉ để sử dụng cơ chế Config Data và `configtree:` cơ bản được Spring Boot hỗ trợ.

### 8.2. Không xem Config Tree là giải pháp bảo mật hoàn chỉnh

Config Tree thuận tiện khi hạ tầng cung cấp file từ Secret volume, nhưng bảo mật còn phụ thuộc vào RBAC, quyền đọc file, cách mount, quyền tài khoản dịch vụ và tránh lộ nội dung qua log hoặc endpoint chẩn đoán. `on-cloud-platform` chỉ quyết định document được áp dụng, không kiểm soát ai có quyền đọc secret.

## 9. Điều kiện cloud platform khác gì với location, precedence và import?

`spring.config.activate.on-cloud-platform` là **điều kiện để một document được tham gia nạp**. Nó không thay đổi quy tắc ưu tiên tổng quát của mọi nguồn property.

Cần phân biệt ba tầng:

1. **Tìm nguồn:** Spring Boot xét các location mặc định, `spring.config.location`, `spring.config.additional-location`, `spring.config.import` và các vị trí liên quan.
2. **Kích hoạt document:** Boot đánh giá `on-cloud-platform` và, nếu có, `on-profile` cho từng document.
3. **Tính giá trị hiệu lực:** Các property sources đã được chấp nhận tham gia cơ chế ưu tiên và ghi đè.

Ví dụ:

~~~yaml
server:
  port: 8080
---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
server:
  port: 8085
~~~

Trong cùng file và không có nguồn ưu tiên cao hơn, khi Kubernetes được nhận diện thì `server.port` có thể là `8085`. Nhưng nếu khởi chạy:

~~~bash
java -jar app.jar --server.port=9090
~~~

thì trong Spring Boot thông thường, đối số command line có độ ưu tiên cao và `server.port` trở thành `9090` dù document Kubernetes được kích hoạt.

Tương tự, một file external được nạp ở location có độ ưu tiên cao hơn có thể ghi đè property được khai báo trong document Kubernetes đóng gói trong JAR.

**Không suy luận rằng một document chứa `on-cloud-platform=kubernetes` luôn thắng các document khác.** Điều kiện chỉ cho phép document tham gia, còn kết quả cuối phụ thuộc vào location, thứ tự document và các source khác.

## 10. Cách tổ chức cấu hình theo môi trường

### 10.1. Dùng cloud condition khi nào?

Thích hợp khi khác biệt chính là **nền tảng chạy**:

- Chạy local thì dùng thư mục `./data`, chạy Kubernetes thì dùng mount `/var/app/data`.
- Chạy Kubernetes thì nhập file config tree từ volume, còn local dùng config trong project.
- Một endpoint nội bộ chỉ có ý nghĩa trong Kubernetes nên được khai báo riêng ở document Kubernetes.
- Cùng một artifact chạy cả trên Kubernetes và máy chủ thường; không muốn vận hành thêm profile chỉ để phân biệt hai hạ tầng.

### 10.2. Dùng Spring profile khi nào?

Profile thích hợp khi khác biệt chính là **mục đích môi trường hoặc chế độ vận hành**:

- `dev`: service giả lập và mức log phát triển.
- `test`: dữ liệu kiểm thử và cấu hình test.
- `prod`: cấu hình production.
- `debug`: kích hoạt công cụ chẩn đoán có kiểm soát.

Nếu cả nền tảng và môi trường đều quan trọng, có thể kết hợp `on-cloud-platform` với `on-profile` thay vì tạo nhiều tên profile phức tạp như `prod-kubernetes` hoặc `staging-kubernetes`.

### 10.3. Đừng biến cloud condition thành cách phân nhánh nghiệp vụ

Điều kiện nền tảng nên mô tả khác biệt kỹ thuật thật sự. Ví dụ, việc giá tính thuế của người dùng khác nhau theo quốc gia không nên phụ thuộc việc service chạy trên Kubernetes hay Cloud Foundry. Logic nghiệp vụ nên được quản lý bằng cấu hình nghiệp vụ, dữ liệu hoặc feature flag phù hợp.

Tương tự, việc muốn sử dụng database production không nên được quyết định chỉ dựa trên cloud platform. Kubernetes có thể chạy cả production, staging và development.

## 11. Tự thử behavior local mà không có Kubernetes cluster

Có thể dùng `spring.main.cloud-platform` để kiểm tra nhánh cấu hình. Tạo file `application.yml`:

~~~yaml
app:
  runtime:
    description: local
    path: ./data

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes

app:
  runtime:
    description: kubernetes
    path: /mnt/data
~~~

Chạy bình thường trên máy local:

~~~bash
java -jar app.jar
~~~

Khi không có cloud platform được nhận diện và không có cấu hình ép platform, các property `app.runtime.*` từ document cơ sở có hiệu lực.

Chạy với lựa chọn cloud platform tường minh:

~~~bash
java -jar app.jar --spring.main.cloud-platform=kubernetes
~~~

Trong trường hợp không có nguồn khác ghi đè các property này, document Kubernetes được kích hoạt và `app.runtime.description` nhận `kubernetes`.

Có thể kiểm tra bằng một thành phần nhỏ của ứng dụng:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationDisplay implements ApplicationRunner {
    private final Environment environment;

    public ConfigurationDisplay(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String description = environment.getProperty("app.runtime.description");
        String path = environment.getProperty("app.runtime.path");
        System.out.println("Runtime description: " + description);
        System.out.println("Runtime path: " + path);
    }
}
~~~

Đây là ví dụ kiểm tra giá trị không nhạy cảm. Không log mật khẩu, token, khóa bí mật hoặc toàn bộ `Environment` chỉ để xem document nào được kích hoạt.

**Giới hạn quan trọng:** ép `spring.main.cloud-platform=kubernetes` chỉ mô phỏng lựa chọn platform của Spring Boot. Các lời gọi tới Kubernetes API, mount thực tế, DNS dịch vụ nội bộ hoặc Kubernetes ServiceAccount vẫn không tồn tại trên máy local nếu không được cung cấp riêng. Vì vậy, hãy dùng chế độ này để kiểm tra cấu hình, không coi nó là bài kiểm thử tích hợp hạ tầng đầy đủ.

## 12. Lỗi thường gặp

### 12.1. Dùng sai tên property

**Sai:**

~~~yaml
spring:
  profiles:
    activate:
      on-cloud-platform: kubernetes
~~~

**Đúng:**

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
~~~

Tiền tố bắt buộc là `spring.config.activate`, không phải `spring.profiles.activate`.

### 12.2. Đặt điều kiện ngoài document muốn kích hoạt

Một thuộc tính chỉ chi phối **document logic chứa nó**, không tự áp điều kiện cho toàn bộ các document khác trong file.

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
app:
  mode: cluster
---
app:
  timeout: 3s
~~~

Trong ví dụ này, document đầu có điều kiện Kubernetes. Document thứ hai là một document khác và không tự kế thừa điều kiện đó. Nếu muốn document sau cũng chỉ áp dụng trên Kubernetes, hãy khai báo điều kiện cho chính document sau hoặc tổ chức lại các property vào cùng một document.

### 12.3. Tưởng `on-cloud-platform=kubernetes` sẽ bật profile `kubernetes`

Không. Nếu có `application-kubernetes.properties`, file này vẫn là file profile-specific. Điều kiện cloud không làm profile `kubernetes` tự xuất hiện trong `Environment.getActiveProfiles()`.

### 12.4. Dùng tên platform không được Spring Boot hỗ trợ

Cơ chế này dựa trên enum `CloudPlatform` của phiên bản Boot đang sử dụng. Không coi một chuỗi tên bất kỳ là biểu thức hợp lệ. Với nền tảng chưa được nhận diện, hãy cân nhắc một Spring profile hoặc property ứng dụng cụ thể.

### 12.5. Kỳ vọng file config bên ngoài tự tồn tại

Document Kubernetes có thể khai báo:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
    import: "configtree:/etc/config/"
~~~

Nếu `/etc/config/` không được mount đúng, ứng dụng có thể lỗi. Điều kiện cloud chỉ xác định có nên xét import đó; nó không tạo volume hoặc file.

### 12.6. Bỏ qua thứ tự ưu tiên

Khi một property trong document Kubernetes không có hiệu lực như mong đợi, kiểm tra biến môi trường, đối số chạy, file external, profile-specific document và location groups. Có thể document đã được kích hoạt đúng nhưng giá trị bị một nguồn ưu tiên cao hơn ghi đè.

### 12.7. Kỳ vọng giá trị tự đổi khi tiến trình chuyển môi trường

Các document Config Data được xử lý trong giai đoạn khởi động. Việc chuyển container sang cluster khác, thay đổi biến môi trường hoặc chỉnh file mount sau khi context đã sẵn sàng không đồng nghĩa các document được tự động kích hoạt lại. Nếu muốn cấu hình động, cần cơ chế refresh/reload được thiết kế riêng; ứng dụng Spring Boot thông thường cần khởi động lại để áp dụng các thay đổi lớn này.

### 12.8. Tìm cách bật profile ngay trong document có điều kiện

Không nên đặt:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
  profiles:
    active: prod
~~~

trong một document chỉ được nạp khi điều kiện cloud đúng. Đối với Config Data hiện đại, việc khai báo `spring.profiles.active`, `spring.profiles.default` hoặc các lựa chọn include/group trong document được kích hoạt có điều kiện bị giới hạn, và có thể gây lỗi cấu hình.

Cách rõ ràng hơn: đặt `spring.profiles.active` trong một nguồn cấu hình không đặc thù cho profile (hoặc cung cấp qua biến môi trường/command line), sau đó dùng `on-cloud-platform` và `on-profile` cho document cần cả hai điều kiện.

### 12.9. Dùng `@PropertySource` để đọc multi-document properties

`@PropertySource` của Spring Framework không xử lý cách chia document bằng `#---` như Config Data của Boot. Nếu dựa vào tính năng activation, đặt cấu hình vào các nguồn do Spring Boot Config Data nạp, ví dụ `application.properties`, `application.yml` hoặc các location/import phù hợp.

## 13. Quy trình chẩn đoán

Khi property của document có `on-cloud-platform=kubernetes` không xuất hiện:

1. **Kiểm tra Spring Boot version.** Xác nhận ứng dụng dùng cơ chế Config Data hỗ trợ `spring.config.activate.*` (được giới thiệu trong Spring Boot 2.4).
2. **Kiểm tra document có được nạp từ nguồn phù hợp không.** Ví dụ file `application.yml` có nằm trong Config Data locations mà Boot đang tìm không? Tên file và extension có đúng không?
3. **Kiểm tra cú pháp separator.** YAML cần `---`; properties cần `#---` hoặc `!---` với quy tắc cú pháp tương ứng.
4. **Kiểm tra đúng tên điều kiện.** Dùng `spring.config.activate.on-cloud-platform`, không dùng tên tùy ý.
5. **Kiểm tra platform thực tế.** Ứng dụng có đang được Spring Boot nhận diện là Kubernetes không? Có override `spring.main.cloud-platform` từ nguồn cấu hình khác không?
6. **Kiểm tra điều kiện còn lại.** Nếu cùng document có `on-profile`, biểu thức profile cũng phải đúng.
7. **Kiểm tra xung đột property.** Nếu document được kích hoạt nhưng giá trị không khớp, xem nguồn ưu tiên cao hơn và thứ tự document.
8. **Kiểm tra import và volume.** Khi document chứa `spring.config.import`, xem đường dẫn có tồn tại và có quyền đọc không; cân nhắc có nên dùng `optional:`.
9. **Kiểm tra context đã khởi động lại chưa.** Spring Boot không tự kích hoạt lại Config Data chỉ vì biến môi trường bên ngoài thay đổi.
10. **Đọc thông báo lỗi khởi động.** Đừng che `ConfigDataLocationNotFoundException` hay lỗi parse bằng cách bật chế độ bỏ qua lỗi cho mọi location.

Có thể bật log chi tiết liên quan Config Data trong một lần chạy chẩn đoán:

~~~bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
~~~

Thông điệp log chính xác phụ thuộc phiên bản Boot. Không bật log quá chi tiết ở môi trường có dữ liệu nhạy cảm nếu chưa kiểm soát nơi lưu và quyền xem log.

Nếu bật Spring Boot Actuator và cấu hình bảo mật phù hợp, endpoint `/actuator/env` có thể giúp kiểm tra các property sources và giá trị đã được che giấu theo chính sách. Endpoint này cũng không thay thế việc xác minh platform được nhận diện trong quá trình khởi động.

## 14. Ví dụ triển khai theo hai môi trường

### 14.1. Local development

Cấu hình cơ sở:

~~~yaml
# application.yml
app:
  cache:
    provider: in-memory
  config:
    location: ./config

---
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
app:
  cache:
    provider: redis
  config:
    location: /etc/myapp
~~~

Khởi động trên máy developer:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

Nếu không có platform Kubernetes được nhận diện, document Kubernetes bị bỏ qua. `app.cache.provider` giữ giá trị `in-memory` và `app.config.location` là `./config`.

### 14.2. Kubernetes production

Có thể dùng cùng JAR/container image với file cấu hình ở trên:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: catalog
          image: example/catalog:1.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
~~~

Trong môi trường Kubernetes được Boot nhận diện, document Kubernetes được kích hoạt. `app.cache.provider` trở thành `redis` và `app.config.location` thành `/etc/myapp`, nếu không có nguồn ưu tiên cao hơn ghi đè.

Manifest trên chỉ minh họa cách đặt profile. Giá trị `redis` không tự tạo Redis Service và `/etc/myapp` không tự được mount; những tài nguyên đó phải được triển khai riêng.

## 15. So sánh các lựa chọn

| Mục tiêu | Công cụ phù hợp | Lưu ý |
| --- | --- | --- |
| Tách cấu hình cho Kubernetes và local | `spring.config.activate.on-cloud-platform=kubernetes` | Dựa vào platform được Boot nhận diện |
| Tách dev/test/prod | `spring.config.activate.on-profile` hoặc file `application-{profile}.*` | Dựa vào active profiles |
| Chọn profile từ môi trường chạy | `spring.profiles.active`, `SPRING_PROFILES_ACTIVE` | Không tự phát hiện cloud platform |
| Buộc Boot nhận diện platform khi test | `spring.main.cloud-platform` | Chỉ mô phỏng detection, không tạo hạ tầng |
| Nạp từng file từ mounted volume | `spring.config.import=configtree:...` | Cần có đường dẫn và quyền đọc phù hợp |
| Chỉ nạp Config Tree trên Kubernetes | `on-cloud-platform` cùng `spring.config.import` | Đặt import trong document có điều kiện |
| Chọn bean Java theo nền tảng | `@ConditionalOnCloudPlatform` khi phù hợp | Điều kiện tạo bean, khác điều kiện nạp document |
| Chọn bean Java theo profile | `@Profile` | Dựa vào profile, không dựa trực tiếp trên cloud platform |

## 16. Câu hỏi thường gặp

**Có cần Spring Cloud Kubernetes để dùng `on-cloud-platform=kubernetes` không?**

Không, cơ chế kích hoạt Config Data theo `CloudPlatform` là một phần của Spring Boot. Spring Cloud Kubernetes là một tập tích hợp bổ sung cho các nhu cầu tương tác với Kubernetes, không phải điều kiện bắt buộc chỉ để dùng property này.

**Có thể dùng `spring.config.activate.on-cloud-platform` trong file `application-prod.yml` không?**

File `application-prod.yml` chỉ được xét khi profile `prod` phù hợp. Khi bên trong nó còn khai báo `on-cloud-platform=kubernetes`, document tương ứng chỉ được nạp khi thêm điều kiện cloud platform đúng. Tuy nhiên, việc đặt điều kiện kép ngay trong file theo profile có thể khó đọc hơn một document rõ ràng trong file cơ sở; hãy chọn cấu trúc phản ánh đúng chủ đích.

**Một document có thể có nhiều điều kiện không?**

Có thể kết hợp `on-cloud-platform` với `on-profile`. Document sẽ cần thỏa cả hai điều kiện. `on-profile` có cú pháp biểu thức hỗ trợ lựa chọn như `prod | staging`.

**Khi chạy Docker local, có tự được xem là Kubernetes không?**

Không. Docker container không đồng nghĩa Kubernetes. Detection phụ thuộc các dấu hiệu nền tảng mà Spring Boot thực sự nhận được, hoặc việc override `spring.main.cloud-platform`.

**Nếu Kubernetes bị phát hiện sai thì làm gì?**

Kiểm tra biến môi trường và cấu hình override. Trong trường hợp thích hợp, có thể chỉ định `spring.main.cloud-platform=none` hoặc một platform đúng theo khả năng của phiên bản Spring Boot. Việc ép platform cần được quản lý rõ trong hệ thống triển khai vì nó có thể tác động đến nhiều điều kiện và auto-configuration khác.

**Có thể dùng `on-cloud-platform` để kiểm soát feature nghiệp vụ không?**

Có thể dùng làm điều kiện cho property liên quan hạ tầng, nhưng không nên dùng nó như một cơ chế feature flag nghiệp vụ tổng quát. Nền tảng chạy và chính sách bật tính năng là hai quyết định khác nhau.

## 17. Ghi nhớ khi áp dụng

1. `spring.config.activate.on-cloud-platform` **kích hoạt một document Config Data** khi `CloudPlatform` được Spring Boot xác định phù hợp.
2. Dùng `---` trong YAML, `#---` hoặc `!---` trong properties để tổ chức nhiều document.
3. Document cơ sở cung cấp giá trị mặc định; document có điều kiện có thể ghi đè các khóa liên quan khi được kích hoạt.
4. Có thể kết hợp `on-cloud-platform` và `on-profile`, hai điều kiện cần cùng đúng.
5. `spring.profiles.active` không đồng nghĩa cloud platform; file `application-kubernetes.yml` không tự được kích hoạt chỉ vì chạy trên Kubernetes.
6. `spring.main.cloud-platform` cho phép ghi đè tự phát hiện, hữu ích khi chẩn đoán hoặc kiểm tra cấu hình.
7. `spring.config.import` trong document điều kiện có thể nhập `configtree:` chỉ khi document đó được kích hoạt.
8. Activation không quyết định mức ưu tiên tuyệt đối; vẫn phải xét Config Data locations, document order, profile và các nguồn property khác.
9. Detection cloud là lựa chọn cấu hình, không phải biện pháp xác thực hoặc quản lý secret.
10. Các thay đổi điều kiện Config Data thông thường được áp dụng khi khởi động, cần restart khi muốn đổi môi trường chạy.

### Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration, Multi-Document Files và Activation Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot API — `CloudPlatform`](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/cloud/CloudPlatform.html)
- [Spring Boot Reference — Deploying to Kubernetes](https://docs.spring.io/spring-boot/how-to/deployment/cloud.html)
- [Spring Boot Reference — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)

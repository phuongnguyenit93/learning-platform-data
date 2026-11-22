# Cú pháp chỉ số và danh sách phân tách bằng dấu phẩy trong Spring Boot

## 1. Mục tiêu bài học

Spring Boot không chỉ bind một chuỗi hoặc một số đơn lẻ từ `application.yaml` vào Java. Khi cấu hình có nhiều phần tử, bạn có thể dùng `List`, `Set`, mảng, `Map` hoặc danh sách đối tượng có cấu trúc thông qua `@ConfigurationProperties`. Hai cách khai báo danh sách xuất hiện rất thường xuyên là:

- **Cú pháp chỉ số (indexed notation):** `app.servers[0]`, `app.servers[1]`, hoặc `app.backends[0].base-url`.
- **Danh sách phân tách bằng dấu phẩy (comma-separated values):** `app.servers=alpha,beta,gamma`.

Ví dụ hai cách khai báo dưới đây cùng mô tả ba tên server:

```properties
# Cách A: các phần tử có chỉ số
app.servers[0]=alpha
app.servers[1]=beta
app.servers[2]=gamma
```

```properties
# Cách B: một giá trị có dấu phẩy
app.servers=alpha,beta,gamma
```

Trong một ứng dụng Spring Boot, hai cách đó có thể được binder chuyển thành:

```java
List<String> servers
```

Tuy vậy, **chúng không phải lựa chọn tương đương trong mọi tình huống**. Cú pháp chỉ số phù hợp khi một phần tử chứa nhiều trường, khi cần gắn số thứ tự, và khi xuất bản cấu hình từ nguồn như biến môi trường. Danh sách dấu phẩy gọn cho các giá trị scalar, nhưng cần thận trọng khi bản thân phần tử có chứa dấu phẩy. Ngoài ra, danh sách từ nhiều property source thường **được thay thế theo toàn bộ danh sách**, không tự ghép từng phần tử theo chỉ số như một bản vá.

Bài nằm trong nhóm **Collection và Map** của chủ đề **Spring Boot Externalized Configuration**. Nó tập trung vào cách **mô tả, bind, quan sát và dự đoán** danh sách, có so sánh với map để tránh các hiểu lầm phổ biến.

Sau khi hoàn thành, bạn có thể:

1. Đọc và viết thuộc tính với chỉ số `[0]`, `[1]` trong `.properties`, YAML và CLI.
2. Bind một chuỗi CSV đơn giản vào `List<String>`, `List<Integer>` hoặc `List<Duration>` khi có converter tương ứng.
3. Phân biệt `List<String>` với `List<Backend>` gồm nhiều thuộc tính lồng nhau.
4. Ánh xạ các khóa như `app.backends[0].base-url` vào Java record có cấu trúc.
5. Giải thích cách biến môi trường biểu diễn chỉ số và phân cấp.
6. Dự đoán kết quả khi file theo profile thay danh sách nền.
7. Hiểu lý do `Map` có quy tắc kết hợp khác `List`, và cách biểu diễn map key có ký tự đặc biệt.
8. Thực hành bằng ứng dụng Spring Boot 3.3, Java 21, Gradle; có cách chạy và kiểm thử.
9. Phát hiện lỗi index thiếu, dữ liệu CSV không như mong đợi, lỗi chuyển kiểu và validation.
10. Chọn một cấu trúc config dễ quản lý khi dự án triển khai qua JAR, container và nhiều profile.

**Giới hạn bài lab:** các endpoint, nhãn và mã định danh trong ví dụ là giả lập; ứng dụng console không kết nối mạng thật và không in dữ liệu nhạy cảm.

## 2. Một property đơn và một tập phần tử

Với một thuộc tính đơn:

```yaml
app:
  region: ap-southeast-1
```

Java có thể dùng:

```java
String region
```

Với nhiều region:

```yaml
app:
  regions:
    - ap-southeast-1
    - eu-west-1
    - us-east-1
```

Java dùng:

```java
List<String> regions
```

Với một danh sách endpoint có thêm tên và thời gian timeout:

```yaml
app:
  backends:
    - name: inventory
      base-url: https://inventory.example.test
      timeout: 2s
    - name: billing
      base-url: https://billing.example.test
      timeout: 3s
```

Java có thể dùng:

```java
List<Backend> backends
```

với:

```java
public record Backend(String name, URI baseUrl, Duration timeout) {}
```

Một `List` có **thứ tự**. Cùng hai phần tử nhưng đổi vị trí có thể làm thay đổi hành vi nếu ứng dụng dùng thứ tự để chọn ưu tiên hoặc fallback.

Ngược lại, `Map<String,String>` thể hiện tập key-value được truy cập qua **khóa** thay vì index:

```yaml
app:
  labels:
    team: platform
    stage: sandbox
```

Truy cập `labels.get("team")` khác với `regions.get(0)`. Đừng chuyển một map thành list chỉ vì nhìn thấy nhiều dòng YAML.

## 3. Cú pháp chỉ số `[n]` trong `.properties`

Dạng phổ biến:

```properties
app.regions[0]=ap-southeast-1
app.regions[1]=eu-west-1
app.regions[2]=us-east-1
```

Các con số trong `[]` là **chỉ số của phần tử**. Chúng bắt đầu từ `0` trong các ví dụ Java và Spring Boot thông thường.

Tương ứng khi binding:

```text
app.regions[0] --> regions.get(0) --> ap-southeast-1
app.regions[1] --> regions.get(1) --> eu-west-1
app.regions[2] --> regions.get(2) --> us-east-1
```

Mẫu này quan trọng vì nó xuất hiện trong:

- File `application.properties`.
- Đối số dòng lệnh dạng `--app.regions[0]=...`.
- Cấu hình sinh tự động từ một số hệ thống triển khai.
- Các `PropertySource` trình bày danh sách dưới dạng những khóa có index.
- Bảng quan sát và thông báo binding failure.

### 3.1. Đánh chỉ số cho object lồng nhau

Một `List<String>` chỉ cần mỗi phần tử là chuỗi. Nhưng `List<Backend>` có nhiều component:

```properties
app.backends[0].name=inventory
app.backends[0].base-url=https://inventory.example.test
app.backends[0].timeout=2s

app.backends[1].name=billing
app.backends[1].base-url=https://billing.example.test
app.backends[1].timeout=3s
```

Các khóa có index `0` cùng tạo **một** `Backend`; tương tự các khóa index `1` tạo một `Backend` khác.

Có thể hình dung:

```text
app.backends
     |
     +-- [0]
     |    +-- name      = inventory
     |    +-- base-url  = https://inventory.example.test
     |    +-- timeout   = 2s
     |
     +-- [1]
          +-- name      = billing
          +-- base-url  = https://billing.example.test
          +-- timeout   = 3s
```

Trong Java:

```java
List<Backend> backends
```

và:

```java
Backend first = backends.get(0);
URI firstUrl = first.baseUrl();
```

**Đừng** tạo các index một cách ngẫu nhiên rồi giả định Spring Boot sẽ tự hiểu thứ tự bạn muốn. Nên dùng dãy liên tiếp `0,1,2,...` khi viết cấu hình và dùng YAML list khi có thể. Nếu thiếu phần tử ở giữa hoặc chỉ truyền một index lớn, binder có thể không tạo được cấu trúc như mong muốn hoặc phát sinh lỗi; hãy coi dãy index liên tiếp là hợp đồng đầu vào của bài lab.

### 3.2. Tránh dùng chỉ số như định danh lâu dài

Nếu một backend chuyển từ index `0` sang `1`, những key như `app.backends[0].timeout` sẽ tác động đến phần tử khác. Điều này có thể nguy hiểm với file override hoặc biến môi trường cố gắng thay riêng một phần tử.

Khi mỗi đối tượng có một mã định danh độc lập và không cần thứ tự, cân nhắc:

```yaml
app:
  backend-by-name:
    inventory:
      base-url: https://inventory.example.test
      timeout: 2s
    billing:
      base-url: https://billing.example.test
      timeout: 3s
```

và Java:

```java
Map<String, BackendSettings> backendByName
```

Ở đó `inventory` và `billing` là key ổn định, không phải số thứ tự. Nếu thứ tự có ý nghĩa nghiệp vụ, `List` vẫn là lựa chọn phù hợp, nhưng hãy quản lý toàn bộ danh sách như một tập thống nhất.

## 4. YAML list và cú pháp chỉ số là hai cách biểu diễn cùng cấu trúc

YAML thường viết danh sách bằng dấu gạch đầu dòng:

```yaml
app:
  regions:
    - ap-southeast-1
    - eu-west-1
    - us-east-1
```

Cấu trúc này có thể được nhìn như:

```properties
app.regions[0]=ap-southeast-1
app.regions[1]=eu-west-1
app.regions[2]=us-east-1
```

Tương tự, YAML danh sách object:

```yaml
app:
  backends:
    - name: inventory
      base-url: https://inventory.example.test
      timeout: 2s
    - name: billing
      base-url: https://billing.example.test
      timeout: 3s
```

tương ứng với các key có index trong ví dụ ở mục 3.1.

YAML còn có cú pháp danh sách inline:

```yaml
app:
  regions: [ap-southeast-1, eu-west-1, us-east-1]
```

Đây là một **YAML sequence**, không phải một chuỗi đơn có dấu phẩy. Khi giao tiếp với người đọc, nên phân biệt:

```yaml
# YAML sequence
app:
  regions: [alpha, beta, gamma]
```

và:

```yaml
# YAML scalar string; binder có thể tách để tạo List<String>
app:
  regions: "alpha,beta,gamma"
```

Dấu phẩy trong flow sequence YAML là một phần cú pháp YAML; còn dấu phẩy trong chuỗi quoted là nội dung scalar mà binder có thể chuyển thành collection.

## 5. Danh sách phân tách bằng dấu phẩy (CSV-style)

Khi danh sách chứa các giá trị scalar đơn giản, có thể khai báo một chuỗi:

```properties
app.regions=ap-southeast-1,eu-west-1,us-east-1
```

và bind:

```java
@ConfigurationProperties(prefix = "app")
public record AppProperties(List<String> regions) {}
```

Bên trong cơ chế binding, Spring Boot dùng conversion service phù hợp để chuyển giá trị chuỗi thành `List<String>`.

YAML scalar tương tự:

```yaml
app:
  regions: "ap-southeast-1,eu-west-1,us-east-1"
```

Đừng suy diễn rằng `@Value("${app.regions}")` luôn cho cùng kiểu với `@ConfigurationProperties`. `@Value` trước hết giải placeholder rồi tùy điểm tiêm và converter mới có thể chuyển kiểu; với nhóm cấu hình có cấu trúc, `@ConfigurationProperties` là lựa chọn dễ kiểm soát hơn.

### 5.1. CSV gọn cho scalar, không phải cấu trúc object

Một chuỗi:

```properties
app.backends=inventory,billing
```

có thể tạo `List<String>` với hai tên, nhưng **không** đủ thông tin để tạo từng `Backend(name, URI baseUrl, Duration timeout)` trong bài lab. Muốn có danh sách object, khai báo các phần tử bằng YAML list hoặc các key có index:

```properties
app.backends[0].name=inventory
app.backends[0].base-url=https://inventory.example.test
app.backends[0].timeout=2s
```

Đừng cố gói nhiều thuộc tính của một object vào một chuỗi kiểu:

```properties
app.backends=inventory|https://inventory.example.test|2s,billing|https://billing.example.test|3s
```

trừ khi dự án cố ý định nghĩa converter/parser riêng và có test cho định dạng đó. Spring Boot không tự hiểu dấu `|` là cấu trúc object tùy ý của bạn.

### 5.2. Kiểu khác ngoài `String`

Nếu đích là:

```java
List<Integer> retryCodes
```

và dữ liệu:

```properties
app.retry-codes=408,429,503
```

Binder có thể chuyển mỗi phần tử thành `Integer` khi quy tắc conversion phù hợp.

Tương tự:

```java
List<Duration> retryIntervals
```

với:

```properties
app.retry-intervals=100ms,250ms,1s
```

Mỗi phần tử được conversion thành `Duration`. Nếu một phần tử như `not-a-duration` không hợp lệ, binding có thể thất bại; Spring Boot không mặc nhiên bỏ qua phần tử hỏng và dùng phần còn lại.

### 5.3. Khoảng trắng trong chuỗi CSV

Có thể gặp:

```properties
app.regions=alpha, beta, gamma
```

Với conversion thông thường, các phần tử có thể được trim cho phù hợp với target type, nhưng đừng xem quy tắc xử lý mọi whitespace và ký tự đặc biệt của mọi converter là hợp đồng bất biến. Nếu khoảng trắng là dữ liệu thực sự có ý nghĩa trong một phần tử, hãy dùng YAML sequence rõ ràng hoặc một định dạng có khả năng biểu diễn chính xác.

Trong quy ước dự án, nếu dùng CSV cho tên hoặc mã đơn giản, nên thống nhất:

```properties
app.regions=alpha,beta,gamma
```

thay vì dựa vào những biến thể dấu cách khó phân biệt trong log.

### 5.4. Một giá trị chứa dấu phẩy thì sao?

Giả sử phần tử cần giữ nguyên:

```text
Ho Chi Minh City, Viet Nam
```

Nếu viết:

```properties
app.locations=Ho Chi Minh City, Viet Nam,Hanoi
```

thì dấu phẩy nào là **nội dung** và dấu phẩy nào là **separator**? Không có đủ thông tin từ một chuỗi CSV đơn giản để phân biệt một cách an toàn.

Giải pháp dễ hiểu là dùng YAML sequence:

```yaml
app:
  locations:
    - "Ho Chi Minh City, Viet Nam"
    - "Hanoi"
```

Nếu bắt buộc dùng `.properties`, dùng indexed notation:

```properties
app.locations[0]=Ho Chi Minh City, Viet Nam
app.locations[1]=Hanoi
```

Vì mỗi phần tử đã có một key riêng, dấu phẩy trong value thuộc về nội dung của phần tử đó. Không nên giả định đặt dấu nháy kép bên trong một scalar CSV sẽ tự biến Spring Boot Binder thành parser CSV đầy đủ theo RFC 4180.

### 5.5. Giá trị rỗng và phần tử rỗng

Xét:

```properties
app.regions=
```

và:

```properties
app.regions=alpha,,gamma
```

Đây là hai tình huống khác nhau. Hành vi chuyển đổi phụ thuộc target type và converter; một chuỗi rỗng có thể dẫn tới collection rỗng hoặc cách diễn giải khác tùy ngữ cảnh, còn phần tử trống giữa hai dấu phẩy có thể gây vấn đề nếu target là số hoặc `Duration`.

Nếu collection bắt buộc có ít nhất một phần tử có ý nghĩa, hãy dùng Bean Validation:

```java
@NotEmpty List<@NotBlank String> regions
```

Với các kiểu không chấp nhận chuỗi rỗng, dựa vào converter và validation để báo lỗi sớm, không âm thầm bỏ giá trị trống.

## 6. Danh sách trong biến môi trường

Khi chạy trên Docker, CI hoặc Kubernetes, bạn thường thấy các giá trị được cấp qua biến môi trường của process.

Với danh sách scalar, cách dễ quản lý:

```text
APP_REGIONS=ap-southeast-1,eu-west-1
```

Spring Boot có thể bind giá trị đó vào `List<String> regions` theo kiểu CSV-style.

Với một phần tử có index, quy tắc tên môi trường cho list dùng **số chỉ mục được bao bởi dấu gạch dưới**:

```text
app.regions[0] -> APP_REGIONS_0_
app.regions[1] -> APP_REGIONS_1_
```

Với object lồng nhau, ý tưởng tương tự:

```text
app.backends[0].name     -> APP_BACKENDS_0_NAME
app.backends[0].base-url -> APP_BACKENDS_0_BASEURL
```

Cần lưu ý `BASEURL` là phần kết quả từ canonical `base-url`: dấu gạch nối bị loại bỏ chứ không thay bằng `_` ở giữa hai từ.

**Quy ước ánh xạ tên phổ biến từ canonical property sang biến môi trường:**

1. Dấu chấm `.` được đổi thành dấu gạch dưới `_`.
2. Dấu gạch nối `-` được bỏ.
3. Tên chuyển thành chữ hoa.
4. Với list indices, số index được đặt trong dấu gạch dưới theo quy tắc list binding.

Đây là **cách viết tương ứng cho nguồn environment**, không phải quy tắc biến mọi ký tự trong mọi dạng key thành một chuỗi duy nhất. Việc escape, map key đặc biệt và binder riêng có thể có yêu cầu khác.

### 6.1. Biến môi trường cho scalar list

Bash:

```bash
APP_REGIONS=alpha,beta,gamma ./gradlew bootRun
```

PowerShell:

```powershell
$env:APP_REGIONS = 'alpha,beta,gamma'
.\gradlew.bat bootRun
Remove-Item Env:APP_REGIONS
```

Nếu không có nguồn ưu tiên cao hơn cùng khóa, ứng dụng sẽ bind danh sách mới từ biến môi trường.

### 6.2. Biến môi trường cho indexed list

Bash:

```bash
APP_REGIONS_0_=alpha APP_REGIONS_1_=beta ./gradlew bootRun
```

PowerShell:

```powershell
${env:APP_REGIONS_0_} = 'alpha'
${env:APP_REGIONS_1_} = 'beta'
.\gradlew.bat bootRun
Remove-Item 'Env:APP_REGIONS_0_'
Remove-Item 'Env:APP_REGIONS_1_'
```

Một số hệ thống triển khai có giới hạn về ký tự trong tên biến môi trường và cách chúng truyền environment qua entrypoint. Hãy kiểm tra khả năng của nền tảng; với danh sách object phức tạp, một file YAML được mount ngoài JAR thường dễ đọc và dễ bảo trì hơn một tập biến môi trường chứa nhiều số index.

### 6.3. List từ một nguồn ưu tiên cao hơn không phải bản vá từng phần tử

Giả sử YAML nền có:

```yaml
app:
  regions:
    - alpha
    - beta
```

Nếu một nguồn ưu tiên cao hơn cung cấp danh sách chỉ có `gamma`, kết quả thường là:

```text
[gamma]
```

không phải:

```text
[gamma, beta]
```

Đây là điểm khác biệt cốt lõi so với suy nghĩ “tôi sửa index 0 nên index 1 vẫn lấy từ file cũ”. Khi một collection được cung cấp ở nguồn ưu tiên cao, Spring Boot Binder thường bind **cả list từ nguồn đó**, không merge từng index giữa các nguồn.

Muốn thay một phần tử nhưng giữ phần tử còn lại, khai báo **toàn bộ danh sách cần thiết** ở nguồn ghi đè.

## 7. Khác biệt giữa List và Map khi kết hợp nhiều nguồn

Spring Boot có quy tắc khi bind collections từ nhiều `PropertySource`.

Với `List`, cách hiểu an toàn trong các trường hợp như file profile và property source ưu tiên khác nhau là:

> Danh sách lấy từ nguồn ưu tiên phù hợp có thể **thay thế toàn bộ danh sách** từ nguồn thấp hơn. Không mặc định merge theo index.

Với `Map`, các **key khác nhau** có thể được tổng hợp từ nhiều nguồn; khi **cùng key**, nguồn ưu tiên cao hơn quyết định giá trị cho key đó.

Ví dụ cấu hình nền:

```yaml
app:
  regions:
    - alpha
    - beta
  labels:
    team: platform
    stage: base
```

File `application-dev.yaml`:

```yaml
app:
  regions:
    - local
  labels:
    stage: development
```

Khi profile `dev` được kích hoạt, dự kiến:

```text
app.regions = [local]
app.labels.team = platform
app.labels.stage = development
```

Giải thích: list đã bị thay thế bởi list của profile `dev`, trong khi map có thể giữ key `team` từ nguồn nền và nhận key `stage` từ nguồn dev.

Đừng từ ví dụ này suy rộng rằng **map của các object lồng nhau** luôn merge mọi trường theo một cách đơn giản. Quy tắc binding còn phụ thuộc target type, kiểu nguồn, cách biểu diễn và độ ưu tiên. Với một backend có nhiều field quan trọng, nên thử bằng integration test trên đúng cấu trúc runtime.

### 7.1. Map key có ký tự đặc biệt

Một tên map key có dấu slash:

```text
/api/v1
```

cần được bảo toàn khi binder xử lý property names.

Trong `.properties`, có thể dùng bracket notation:

```properties
app.labels.[/api/v1]=public-route
```

Trong YAML, các dấu ngoặc phải được đặt trong dấu nháy khi là map key:

```yaml
app:
  labels:
    "[/api/v1]": public-route
```

Khi đó Java có thể truy cập:

```java
properties.labels().get("/api/v1")
```

Lưu ý `[0]` trong list thể hiện **index**, còn `[/api/v1]` của map thể hiện **khóa nguyên văn cần giữ ký tự đặc biệt**. Dùng bracket notation đúng ngữ cảnh giúp tránh binder loại bỏ hoặc tái diễn giải ký tự trong map key.

### 7.2. Dấu chấm trong map key

Với một map `Map<String, String>`, quy tắc binding có thể bảo toàn dấu `.` ở key dạng scalar trong những trường hợp thông thường; tuy nhiên với `Map<String, Object>` hoặc nested map, dấu chấm dễ bị xem là phân cấp.

Muốn chắc chắn một key là `a.b` thay vì hai tầng `a` → `b`, dùng bracket notation khi khai báo:

```properties
app.labels.[a.b]=value
```

YAML:

```yaml
app:
  labels:
    "[a.b]": "value"
```

Đừng dựa vào việc một cấu trúc map string đơn giản tình cờ diễn giải đúng rồi áp dụng lại cho mọi kiểu map.

## 8. Lựa chọn cách khai báo theo loại dữ liệu

| Kiểu dữ liệu đích | Cách khai báo dễ đọc | Ví dụ |
| --- | --- | --- |
| `List<String>` ngắn | Comma-separated | `app.regions=alpha,beta` |
| `List<Integer>` ngắn | Comma-separated | `app.retry-codes=408,429,503` |
| `List<Duration>` ngắn | Comma-separated | `app.intervals=100ms,1s` |
| `List<String>` có phần tử chứa dấu phẩy | YAML list hoặc indexed | `app.locations[0]=City, Country` |
| `List<Backend>` nhiều trường | YAML list hoặc nhiều indexed keys | `app.backends[0].name=...` |
| `Map<String,String>` | Các tên key trực tiếp | `app.labels.team=platform` |
| `Map<String,Backend>` theo định danh | YAML map | `app.backend-by-name.inventory.base-url=...` |
| Map key có ký tự đặc biệt | Bracket notation | `app.labels.[/api/v1]=...` |

Quy tắc chọn nhanh: **scalar ít phần tử** có thể dùng CSV; **object có cấu trúc** dùng YAML sequence hoặc indexed keys; **mục có định danh ổn định** dùng map. Nếu phải vượt qua nhiều profile và cần override rõ ràng, hãy ưu tiên mô tả dữ liệu một cách tường minh thay vì rút ngắn đến mức khó quan sát.

## 9. Ứng dụng mẫu: Collection Binding Observer

Ta tạo một ứng dụng Spring Boot console gồm:

- `tags`: danh sách string được cấp bằng **comma-separated value**.
- `retryIntervals`: danh sách `Duration` cũng được cấp bằng comma-separated value.
- `backends`: danh sách object, mỗi object có `name`, `baseUrl`, `timeout`.
- `labels`: map string, gồm key thường và key có slash.
- Spring Boot Binder chuyển tất cả sang record có kiểu.
- `ApplicationRunner` in kết quả theo thứ tự và vị trí để tiện quan sát.

Ứng dụng chỉ in dữ liệu giả lập; không gửi request tới các URL và không cần cơ sở dữ liệu hoặc web server.

### 9.1. Cấu trúc thư mục

```text
collection-binding-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/collections/
    │   │   ├── CollectionBindingApplication.java
    │   │   └── DemoProperties.java
    │   └── resources/
    │       ├── application.yaml
    │       └── application-dev.yaml
    └── test/
        └── java/dev/example/collections/
            └── CollectionBindingTest.java
```

Tạo bộ khung bằng Spring Initializr, chọn Java 21, Gradle và một bản Spring Boot thuộc nhánh 3.3.x. Giữ Gradle Wrapper do dự án sinh ra.

### 9.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'collection-binding-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` hỗ trợ Bean Validation qua Jakarta Validation, giúp phát hiện danh sách thiếu hoặc object cấu hình thiếu trường bắt buộc.

Trong repository đã quản lý plugin/dependency chung, bạn nên dùng convention của repository thay vì sao chép nguyên một hệ thống build mới.

### 9.3. File `application.yaml` nền

```yaml
spring:
  main:
    web-application-type: none

demo:
  tags: "alpha,beta,gamma"
  retry-intervals: "100ms,250ms,1s"

  backends:
    - name: inventory
      base-url: "https://inventory.example.test"
      timeout: 2s
    - name: billing
      base-url: "https://billing.example.test"
      timeout: 3s

  labels:
    team: education
    stage: base
    "[/api/v1]": example-route
```

Hai trường đầu là YAML scalar có dấu phẩy. `backends` là YAML sequence. `labels` là YAML map.

Dù tên prefix trong bài là `demo`, các quy tắc áp dụng tương tự với một prefix ứng dụng khác như `app`, `client` hoặc `service`.

### 9.4. Bản `.properties` tương đương để đối chiếu

Nếu muốn dùng `.properties` **thay cho** file YAML ở cùng location, bạn có thể đặt:

```properties
spring.main.web-application-type=none

demo.tags=alpha,beta,gamma
demo.retry-intervals=100ms,250ms,1s

demo.backends[0].name=inventory
demo.backends[0].base-url=https://inventory.example.test
demo.backends[0].timeout=2s

demo.backends[1].name=billing
demo.backends[1].base-url=https://billing.example.test
demo.backends[1].timeout=3s

demo.labels.team=education
demo.labels.stage=base
demo.labels.[/api/v1]=example-route
```

Đây là ví dụ tương đương về ý nghĩa. Không tạo cả `application.properties` và `application.yaml` trong cùng location rồi giả định cả hai cùng được gộp theo đúng ý định; Spring Boot có quy tắc ưu tiên định dạng khi hai file cùng tồn tại. Trong bài lab, chọn **một trong hai** để kết quả không bị nhiễu.

### 9.5. Configuration record có List và Map

`src/main/java/dev/example/collections/DemoProperties.java`:

```java
package dev.example.collections;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        @NotEmpty List<@NotBlank String> tags,
        @NotEmpty List<@NotNull Duration> retryIntervals,
        @Valid @NotEmpty List<Backend> backends,
        Map<String, String> labels
) {
    public DemoProperties {
        tags = tags == null ? List.of() : List.copyOf(tags);
        retryIntervals = retryIntervals == null
                ? List.of() : List.copyOf(retryIntervals);
        backends = backends == null
                ? List.of() : List.copyOf(backends);
        labels = labels == null ? Map.of() : Map.copyOf(labels);
    }

    public record Backend(
            @NotBlank String name,
            @NotNull URI baseUrl,
            @NotNull Duration timeout
    ) {}
}
```

Giải thích:

1. `@ConfigurationProperties(prefix = "demo")` yêu cầu Binder đọc nhóm `demo.*`.
2. `List<String> tags` nhận dữ liệu từ scalar có dấu phẩy hoặc từ các phần tử có index.
3. `List<Duration> retryIntervals` minh họa conversion mỗi phần tử sang kiểu thời gian.
4. `@Valid List<Backend>` yêu cầu validation đi sâu vào object con; `Backend` là nested record.
5. `Map<String,String> labels` giữ dữ liệu theo key, bao gồm `"/api/v1"` nhờ bracket notation trong YAML.
6. `List.copyOf` và `Map.copyOf` giúp tránh lưu collection mutable trực tiếp vào record sau binding.
7. `@NotEmpty` yêu cầu những collection quan trọng có phần tử.
8. `@NotBlank` trên phần tử string và `@NotNull` trên component object thể hiện ràng buộc đầu vào. Muốn kiểm tra thêm domain/range của timeout, có thể dùng custom validation hoặc một cơ chế phù hợp khác.

Record bất biến ở mức reference, nhưng nếu phần tử bên trong là object mutable thì collection chỉ bất biến nông. Ví dụ dùng `Backend` record, `URI` và `Duration` để giảm trạng thái mutable.

### 9.6. Main class và console report

`src/main/java/dev/example/collections/CollectionBindingApplication.java`:

```java
package dev.example.collections;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CollectionBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(CollectionBindingApplication.class, args);
    }

    @Bean
    ApplicationRunner report(
            DemoProperties properties,
            Environment environment) {
        return args -> {
            System.out.println("=== COLLECTION BINDING LAB ===");
            System.out.println("activeProfiles = "
                    + Arrays.toString(environment.getActiveProfiles()));

            System.out.println("tags size = "
                    + properties.tags().size());
            for (int i = 0; i < properties.tags().size(); i++) {
                System.out.println("tags[" + i + "] = "
                        + properties.tags().get(i));
            }

            System.out.println("retryIntervals = "
                    + properties.retryIntervals());

            System.out.println("backends size = "
                    + properties.backends().size());
            for (int i = 0; i < properties.backends().size(); i++) {
                DemoProperties.Backend backend =
                        properties.backends().get(i);
                System.out.println(
                        "backends[" + i + "] name="
                        + backend.name()
                        + ", url=" + backend.baseUrl()
                        + ", timeout=" + backend.timeout());
            }

            System.out.println("labels.team = "
                    + properties.labels().get("team"));
            System.out.println("labels.stage = "
                    + properties.labels().get("stage"));
            System.out.println("labels./api/v1 = "
                    + properties.labels().get("/api/v1"));
        };
    }
}
```

`ApplicationRunner` chạy sau khi bean cấu hình đã được tạo/bind trong application context. Vì Spring Boot được đặt `web-application-type: none`, chương trình in kết quả rồi kết thúc, không cần HTTP server.

**Không in toàn bộ `Environment` trong ứng dụng thực.** Trong bài này, `tags`, `backends` và `labels` chỉ chứa dữ liệu giả lập; khi dùng cấu hình thật, map/list có thể chứa token, URL có credential hoặc thông tin khác không được ghi log.

## 10. Thí nghiệm 1: CSV scalar và YAML object list

Từ thư mục gốc project:

macOS/Linux:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

Những dòng chính kỳ vọng:

```text
=== COLLECTION BINDING LAB ===
activeProfiles = []
tags size = 3
tags[0] = alpha
tags[1] = beta
tags[2] = gamma
retryIntervals = [PT0.1S, PT0.25S, PT1S]
backends size = 2
backends[0] name=inventory, url=https://inventory.example.test, timeout=PT2S
backends[1] name=billing, url=https://billing.example.test, timeout=PT3S
labels.team = education
labels.stage = base
labels./api/v1 = example-route
```

Đầu ra cho `Duration` dùng cách hiển thị mặc định của Java, vì vậy `100ms` thành `PT0.1S`, `250ms` thành `PT0.25S`.

Bảng quan sát:

| Thuộc tính | Hình thức trong YAML | Java target | Kỳ vọng |
| --- | --- | --- | --- |
| `demo.tags` | Scalar CSV | `List<String>` | 3 phần tử |
| `demo.retry-intervals` | Scalar CSV | `List<Duration>` | 3 khoảng thời gian |
| `demo.backends` | YAML sequence object | `List<Backend>` | 2 record |
| `demo.labels` | YAML map | `Map<String,String>` | 3 key |

Điểm quan trọng không phải cú pháp file nào ngắn hơn, mà là Binder hiểu cấu trúc **từ dạng nguồn và kiểu Java đích**.

## 11. Thí nghiệm 2: đổi CSV thành YAML sequence

Sửa `application.yaml`:

```yaml
demo:
  tags:
    - alpha
    - beta
    - gamma
```

Giữ các mục khác như cũ. Khởi động ứng dụng mới. Kỳ vọng:

```text
tags size = 3
tags[0] = alpha
tags[1] = beta
tags[2] = gamma
```

Dù biểu diễn nguồn đã thay đổi từ chuỗi CSV sang sequence, `DemoProperties` **không cần sửa** vì kiểu đích vẫn là `List<String>`.

Bây giờ thử:

```yaml
demo:
  tags:
    - "north, central"
    - "south"
```

Kỳ vọng:

```text
tags size = 2
tags[0] = north, central
tags[1] = south
```

Dấu phẩy nằm bên trong phần tử YAML list không tự trở thành separator của collection. Đây là minh họa vì sao YAML sequence/indexed notation nên được chọn khi nội dung phần tử có dấu phẩy hoặc khoảng trắng có ý nghĩa.

Sau thí nghiệm, có thể khôi phục `tags: "alpha,beta,gamma"` để tiếp tục các bước dựa trên cấu hình nền.

## 12. Thí nghiệm 3: ghi đè CSV từ đối số CLI

Dùng cấu hình nền từ mục 9, chạy:

macOS/Linux:

```bash
./gradlew bootRun --args='--demo.tags=red,green,blue'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.tags=red,green,blue"
```

Kỳ vọng:

```text
tags size = 3
tags[0] = red
tags[1] = green
tags[2] = blue
```

Đối số CLI được Spring Boot xử lý thành nguồn cấu hình có độ ưu tiên cao hơn file `application.yaml` trong trường hợp thông thường. Vì vậy list từ CLI được dùng thay cho list nền.

Không cần truyền:

```text
--demo.tags[0]=red
--demo.tags[1]=green
--demo.tags[2]=blue
```

khi các phần tử chỉ là scalar đơn giản và không chứa dấu phẩy. Nếu muốn cấp `List<Backend>` với nhiều field, cú pháp index lại hữu ích hơn.

### 12.1. Chuỗi có dấu phẩy trong một phần tử qua CLI

Nếu bạn thử:

```bash
./gradlew bootRun --args='--demo.tags=red,green\,blue'
```

có nhiều tầng xử lý chuỗi và escape: shell, Gradle, CLI, property placeholder, converter. Đừng thiết kế hợp đồng sản xuất dựa vào một kiểu escape chưa được kiểm chứng.

Khi một phần tử chứa dấu phẩy có ý nghĩa, nên chuyển sang file YAML với sequence hoặc các thuộc tính indexed riêng. Cách đó dễ hiểu, dễ review và ít phụ thuộc parser của các lớp truyền đối số.

## 13. Thí nghiệm 4: ghi đè object list bằng các chỉ số CLI

Giả sử bạn muốn khi chạy thử chỉ có **một backend** tên `sandbox` thay vì hai backend trong YAML.

Dùng:

macOS/Linux:

```bash
./gradlew bootRun --args='--demo.backends[0].name=sandbox --demo.backends[0].base-url=https://sandbox.example.test --demo.backends[0].timeout=1s'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.backends[0].name=sandbox --demo.backends[0].base-url=https://sandbox.example.test --demo.backends[0].timeout=1s"
```

Kỳ vọng:

```text
backends size = 1
backends[0] name=sandbox, url=https://sandbox.example.test, timeout=PT1S
```

CLI đã cung cấp danh sách backend ở nguồn có ưu tiên cao hơn. **Danh sách trong YAML nền không được dùng để bổ sung backend thứ hai** vào list kết quả.

Điều dễ nhầm là chỉ truyền:

```text
--demo.backends[0].timeout=1s
```

rồi mong binder lấy `name` và `base-url` của index 0 từ YAML nền, chỉ thay timeout. Đừng dựa vào giả định đó. Khi list từ một nguồn khác được chọn, các field của phần tử cần được mô tả đủ để binding thành object hợp lệ; nếu thiếu, validation có thể báo lỗi.

Tài liệu này coi list override như **một cấu hình thay thế đầy đủ**. Nếu muốn thay đổi một vài thuộc tính theo tên định danh cố định, cân nhắc chuyển sang map hoặc cung cấp toàn bộ list tại nguồn override.

### 13.1. Cú pháp shell cho dấu ngoặc vuông

Trong Bash hoặc Zsh, dấu `[` và `]` có thể tham gia pattern matching khi không được quote đúng. Trong PowerShell, cách trích dẫn cũng khác nhau giữa lệnh trực tiếp và tham số cho Gradle.

Trong các ví dụ ở trên, toàn bộ nội dung `--args='...'` hoặc `--args="..."` được truyền như một chuỗi cho Gradle. Khi chạy JAR trực tiếp, có thể quote từng tham số chứa `[n]`:

```bash
java -jar app.jar \
  '--demo.backends[0].name=sandbox' \
  '--demo.backends[0].base-url=https://sandbox.example.test' \
  '--demo.backends[0].timeout=1s'
```

Điều này giúp shell giữ nguyên dấu ngoặc vuông để Spring Boot nhận đúng tên property.

## 14. Thí nghiệm 5: profile `dev` thay toàn bộ danh sách

Tạo `src/main/resources/application-dev.yaml`:

```yaml
demo:
  tags:
    - local
    - debug

  retry-intervals: "50ms,100ms"

  backends:
    - name: local
      base-url: "http://localhost:9090"
      timeout: 500ms

  labels:
    stage: development
```

Chạy:

macOS/Linux:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

Kỳ vọng:

```text
activeProfiles = [dev]
tags size = 2
tags[0] = local
tags[1] = debug
retryIntervals = [PT0.05S, PT0.1S]
backends size = 1
backends[0] name=local, url=http://localhost:9090, timeout=PT0.5S
labels.team = education
labels.stage = development
labels./api/v1 = example-route
```

Phân tích:

- `demo.tags` từ profile dev thay danh sách nền có ba phần tử.
- `demo.retry-intervals` cũng thay danh sách nền.
- `demo.backends` từ dev có đúng một object `local`, không tự giữ `billing`.
- `demo.labels.stage` ở dev ghi đè `base`.
- `demo.labels.team` và `[/api/v1]` không bị ghi đè và có thể tiếp tục đến từ map nền.

Vì vậy, **List và Map không nên được coi là hai collection luôn có cùng quy tắc merge**. Khi viết profile override cho List, hãy đưa vào toàn bộ danh sách cần dùng ở profile đó.

### 14.1. Chỉ ghi `backends[0].timeout` trong file dev có ổn không?

Ví dụ:

```properties
demo.backends[0].timeout=100ms
```

trong một nguồn config ưu tiên cao hơn không phải cách an toàn để chỉnh riêng timeout của phần tử `inventory` mà vẫn giữ mọi field của danh sách nền. Nó có thể khiến binder cố tạo một danh sách mới thiếu những component bắt buộc.

Nếu có nhu cầu override từng backend theo tên, một cấu trúc như `Map<String, BackendConfig>` thường phù hợp hơn. Ngay cả với map, phải kiểm thử quy tắc merge của nested objects trong những nguồn thực tế.

## 15. Thí nghiệm 6: dùng biến môi trường để thay list

Quay về cấu hình nền, không bật profile dev:

Bash:

```bash
DEMO_TAGS=from-env-1,from-env-2 ./gradlew bootRun
```

PowerShell:

```powershell
$env:DEMO_TAGS = 'from-env-1,from-env-2'
.\gradlew.bat bootRun
Remove-Item Env:DEMO_TAGS
```

Kỳ vọng list `tags` có hai phần tử từ biến môi trường, không phải ba phần tử nền. Đây là trường hợp tiện lợi cho môi trường container, miễn mỗi phần tử là scalar đơn giản và không chứa delimiter mơ hồ.

Nếu muốn ghi đè list backend bằng environment, cần cung cấp đủ các trường/index theo quy tắc tên biến:

```text
DEMO_BACKENDS_0_NAME=sandbox
DEMO_BACKENDS_0_BASEURL=https://sandbox.example.test
DEMO_BACKENDS_0_TIMEOUT=1s
```

Ở một số hệ thống triển khai, biến có chỉ số khó bảo trì hơn file YAML. Cân nhắc mount file cấu hình bên ngoài JAR khi danh sách object dài hoặc thường xuyên thay đổi.

## 16. Kiểm thử binding bằng JUnit

`src/test/java/dev/example/collections/CollectionBindingTest.java`:

```java
package dev.example.collections;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "demo.tags=from-test-a,from-test-b",
        "demo.backends[0].name=from-test",
        "demo.backends[0].base-url=https://test.example.test",
        "demo.backends[0].timeout=800ms"
})
class CollectionBindingTest {

    @Autowired
    DemoProperties properties;

    @Test
    void csvValuesAreConvertedToList() {
        assertEquals(
                List.of("from-test-a", "from-test-b"),
                properties.tags());
    }

    @Test
    void indexedPropertiesCreateOneNestedObject() {
        assertEquals(1, properties.backends().size());
        DemoProperties.Backend only =
                properties.backends().get(0);
        assertEquals("from-test", only.name());
        assertEquals(URI.create("https://test.example.test"),
                only.baseUrl());
        assertEquals(Duration.ofMillis(800),
                only.timeout());
    }

    @Test
    void otherMapKeysFromBaseSourceRemainAvailable() {
        assertEquals("education",
                properties.labels().get("team"));
        assertTrue(properties.labels().containsKey("/api/v1"));
    }
}
```

Chạy:

macOS/Linux:

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

Những test này kiểm tra hai điều khác nhau:

1. Một chuỗi CSV trong nguồn test được chuyển thành `List<String>`.
2. Các key có index trong nguồn test tạo đúng một `Backend` từ ba field.

Test về `Map` xác nhận key nền không bị mất chỉ vì một nguồn ưu tiên cao hơn ghi đè những collection khác. Nếu thay đổi config source hoặc profile, cần giữ test kiểm soát những nguồn đang được dùng thực tế.

### 16.1. Test tình huống lỗi

Để tập luyện, thử chạy với một phần tử duration sai:

```bash
./gradlew bootRun --args='--demo.retry-intervals=100ms,not-a-duration'
```

Binder sẽ không thể chuyển phần tử sai sang `Duration` theo conversion thông thường. Một ứng dụng có cấu hình quan trọng nên thất bại khi khởi động, thay vì tự âm thầm bỏ một phần tử hỏng.

Thử dùng CSV chứa chỉ khoảng trắng hoặc list trống khi record có `@NotEmpty`. Validation sẽ giúp phát hiện trường hợp cấu hình không đáp ứng hợp đồng dữ liệu. Lỗi converter và lỗi validation là hai loại khác nhau: một bên **không thể chuyển kiểu**, bên kia **chuyển được nhưng sai ràng buộc**.

Nếu muốn viết test kiểm tra lỗi khởi động, có thể dùng `ApplicationContextRunner` để tạo context có kiểm soát và assert failure, thay vì viết `@SpringBootTest` rồi để cả test suite không khởi tạo được.

## 17. So sánh cách đọc list qua `Environment`, `@Value` và `@ConfigurationProperties`

### 17.1. `Environment.getProperty()`

Với một property:

```properties
demo.tags=alpha,beta,gamma
```

bạn có thể gọi:

```java
String raw = environment.getProperty("demo.tags");
```

Kết quả thường là chuỗi gốc được lưu trong nguồn, ví dụ:

```text
alpha,beta,gamma
```

Nhưng nếu list được khai báo bằng YAML sequence hoặc các key `demo.tags[0]`, `demo.tags[1]`, **không phải nguồn nào cũng cung cấp một scalar property tên `demo.tags`**. Việc gọi `getProperty("demo.tags")` không thể thay thế một binder collection đáng tin cậy cho mọi kiểu nguồn.

### 17.2. `@Value`

Một điểm tiêm:

```java
@Value("${demo.tags}")
private String rawTags;
```

phụ thuộc vào placeholder `demo.tags` có giải được một giá trị phù hợp không. Với một scalar CSV, điều này có thể đơn giản. Nhưng với một cấu trúc có index, placeholder ở root không bảo đảm bạn sẽ nhận một chuỗi CSV đã được tổng hợp.

Nếu cần `List<String>` qua `@Value`, framework có thể chuyển từ chuỗi sang collection tùy cơ chế converter được cấu hình; tuy nhiên với **nhóm thuộc tính có cấu trúc**, `@ConfigurationProperties` rõ ràng và an toàn hơn.

### 17.3. `@ConfigurationProperties`

Với:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(List<String> tags) {}
```

Binder được thiết kế để nhận các biểu diễn khác nhau và tạo ra một list có kiểu. Đây là lựa chọn ưu tiên khi:

- Danh sách có nhiều phần tử hoặc object lồng nhau.
- Có conversion kiểu như `Duration` hoặc `URI`.
- Có profile override.
- Có validation.
- Có nhiều bean tiêu thụ cùng cấu hình.
- Cần test ổn định giữa file YAML, environment và CLI.

Đừng nhầm **tra cứu một key** (`Environment.getProperty`) với **binding một cấu trúc nhiều key** (`@ConfigurationProperties`).

## 18. Lỗi thường gặp với indexed notation

### 18.1. Dùng index bắt đầu từ 1

```properties
demo.tags[1]=alpha
demo.tags[2]=beta
```

Nếu bạn muốn list hai phần tử, nên dùng `0` và `1`. Một dãy bắt đầu bằng `1` có thể tạo lỗ hổng index `0`, khiến việc bind không đúng mong đợi. Giữ các chỉ số liên tiếp từ `0` để tránh lỗi về cấu trúc.

### 18.2. Bỏ trống một phần tử ở giữa

```properties
demo.tags[0]=alpha
demo.tags[2]=gamma
```

Không nên giả định Binder sẽ tự điền một `null` hoặc dùng file nền để lấp index `1`. Sắp xếp lại index hoặc mô tả danh sách đầy đủ.

### 18.3. Đặt tên property lồng nhau sai cấp

```properties
demo.backends[0].baseurl=https://inventory.example.test
```

Trong một số trường hợp relaxed binding có thể chấp nhận các dạng tên khác nhau, nhưng tên canonical dễ đọc là:

```properties
demo.backends[0].base-url=https://inventory.example.test
```

Giữ kebab-case trong file và placeholder để giảm mơ hồ khi chuyển sang biến môi trường.

### 18.4. Thiếu field bắt buộc của object

```properties
demo.backends[0].name=inventory
```

Nếu `Backend` record yêu cầu cả `baseUrl` và `timeout`, list source ưu tiên có thể tạo object thiếu field. Validation `@NotNull` giúp báo lỗi sớm, thay vì đến khi service gọi `backend.baseUrl()` mới gặp `NullPointerException`.

### 18.5. Dùng dấu ngoặc vuông trong shell mà không quote

Một lệnh chứa `[0]` có thể bị shell hiểu như ký tự pattern. Quote tên đối số khi chạy trực tiếp, hoặc dùng cú pháp truyền `--args` phù hợp với Gradle để Spring nhận đúng tên property.

## 19. Lỗi thường gặp với danh sách dấu phẩy

### 19.1. Phần tử chứa dấu phẩy

Dữ liệu địa chỉ hoặc nhãn có dấu phẩy nên dùng YAML list hoặc indexed properties. Tránh thiết kế parser CSV tự phát bằng cách thêm nháy trong chuỗi mà chưa thống nhất quy tắc escape.

### 19.2. Một phần tử không thể chuyển sang kiểu đích

```properties
demo.retry-intervals=100ms,error,1s
```

Binder cần chuyển các phần tử thành `Duration`; phần tử `error` không phù hợp. Không nên xử lý bằng cách đưa giá trị lỗi vào default mà không báo cho người vận hành.

### 19.3. Dùng một CSV string để mô tả object phức tạp

Không tự giả định một format như `name,url,timeout` được hiểu thành record ba field. Dùng YAML sequence hoặc indexed keys để mỗi field có tên rõ ràng, hoặc xây custom converter nếu định dạng là yêu cầu hợp lệ của sản phẩm.

### 19.4. Khoảng trắng bất ngờ

Khi người dùng copy một chuỗi CSV từ bảng tính hoặc secret manager, có thể xuất hiện khoảng trắng ở đầu/cuối. Với cấu hình quan trọng, validator nên kiểm tra nội dung có ý nghĩa, và quy ước nhập liệu nên tránh whitespace mơ hồ.

### 19.5. Một nguồn ghi đè có chuỗi rỗng

Nếu nguồn ưu tiên cao hơn cấp `demo.tags=` nhưng file nền có ba phần tử, đừng giả định Binder luôn tự trở về list nền. Nguồn ưu tiên cao có thể làm thay đổi cách giá trị được giải quyết. Với danh sách bắt buộc, dùng `@NotEmpty` và kiểm tra dữ liệu thật.

## 20. Chẩn đoán khi profile hoặc environment cho kết quả khác

Một quy trình gọn:

**Bước 1 — Xác định Java target.** Là `List<String>`, `List<Backend>`, `List<Duration>` hay `Map<String,String>`? Một source expression chỉ có ý nghĩa khi biết Binder cần tạo kiểu nào.

**Bước 2 — Liệt kê các property sources có thể chứa cùng prefix.** File nền, file theo profile, file ngoài JAR, biến môi trường, CLI, test hoặc nguồn import.

**Bước 3 — Xác định nguồn ưu tiên.** Nếu hai sources cùng khai báo list, không trộn danh sách theo index như bản vá trừ khi có một cơ chế tùy biến được thiết kế rõ.

**Bước 4 — Nhìn cách biểu diễn nguồn.** CSV scalar, YAML sequence hay các key có `[n]`? Cấu trúc khác nhau có thể tác động tới cách `Environment.getProperty` hiển thị.

**Bước 5 — Kiểm tra tên canonical.** `demo.backends[0].base-url` phải ánh xạ đến `baseUrl` của `Backend`, còn environment index tương ứng dạng `DEMO_BACKENDS_0_BASEURL`.

**Bước 6 — Kiểm tra index.** Có bắt đầu từ 0 và liên tiếp không? Mỗi object đã có đủ field chưa?

**Bước 7 — Xem conversion và validation.** Giá trị có convert được thành `Duration`, `URI` hay `int` không? List hoặc component bắt buộc có trống không?

**Bước 8 — Khởi động lại ứng dụng sau khi sửa file.** Config Data thông thường được nạp lúc startup. Một bean record đã bind không tự động thay đổi khi bạn sửa YAML ngoài tiến trình.

**Bước 9 — Ghi lại kết quả và chỉ đổi một yếu tố mỗi lần.** Dùng runner in kích thước list, chỉ số, giá trị giả lập và map keys được phép hiển thị. Không cần in toàn bộ `Environment`.

Nếu đang xử lý dữ liệu nhạy cảm hoặc danh sách các token, đừng xuất mọi phần tử để debug. Thay bằng trạng thái có/không, số lượng hoặc kiểm tra một tập khóa an toàn cho phép.

## 21. Tập bài thực hành nâng cao

### Bài A — Ba cách khai báo cùng một list

Tạo một `List<String> colors` từ:

1. YAML sequence: `[red, green, blue]`.
2. `.properties` indexed: `demo.colors[0]=red`, ...
3. `.properties` CSV: `demo.colors=red,green,blue`.

Viết một record nhỏ và `ApplicationRunner` in từng phần tử. Ghi lại những trường hợp các cấu trúc trên cho kết quả tương ứng, và kiểm tra khác biệt khi chuỗi phần tử có dấu phẩy.

### Bài B — Một list object có ba trường

Thiết kế:

```java
public record Worker(
        String name,
        int concurrency,
        Duration timeout
) {}
```

Viết indexed properties cho hai worker tên `email` và `billing`. Đảm bảo index liên tiếp, có đủ ba field mỗi object. Chuyển sang YAML sequence và chứng minh bean Java không cần sửa.

### Bài C — Ghi đè bằng profile

File nền có ba backend. File `application-dev.yaml` chỉ có một backend `local`. Dự đoán và xác nhận kích thước list. Sau đó thử chỉ ghi một thuộc tính của index `0` ở profile và ghi lại hành vi/error của ứng dụng có validation.

Giải thích vì sao cấu hình profile ở đây nên mô tả **toàn bộ danh sách muốn dùng**, thay vì chỉ sửa một phần tử từ file nền.

### Bài D — Map với key đặc biệt

Thêm:

```properties
demo.labels.[/internal/v2]=internal-route
demo.labels.[a.b]=with-dot
```

Trong Java, đọc:

```java
labels.get("/internal/v2")
labels.get("a.b")
```

Sau đó chuyển sang YAML với map key có dấu ngoặc được quote. Bài tập này phân biệt bracket **map key** và bracket **list index**.

### Bài E — Danh sách thời gian

Khai báo:

```properties
demo.retry-intervals=50ms,250ms,2s
```

Bind vào `List<Duration>` và tính tổng số mili giây trong một service thuần Java. Nếu có giá trị `invalid`, dự đoán lỗi nào xảy ra. Không cần gọi network hoặc ngủ thực sự trong bài lab.

### Bài F — Chuyển list sang map theo định danh

Giả sử ứng dụng muốn override riêng backend `billing` mà không quan tâm đến vị trí trong danh sách. Chuyển thiết kế từ:

```java
List<Backend> backends
```

sang:

```java
Map<String, BackendSettings> backendByName
```

và dùng key `inventory`, `billing`. Viết YAML cho từng backend. Giải thích lợi ích của key ổn định và trách nhiệm kiểm tra nội dung khi map value là object lồng nhau.

### Bài G — Tạo integration test cho hợp đồng cấu hình

Viết test kiểm tra ba trường hợp:

- CSV `alpha,beta` thành hai phần tử.
- Indexed object tạo đúng `Backend` với `URI` và `Duration`.
- File profile `dev` thay list nền nhưng map giữ những key không trùng.

Dùng `@SpringBootTest` hoặc `ApplicationContextRunner` và kiểm soát profile/thuộc tính nguồn để test có thể lặp lại.

## 22. Câu hỏi tự kiểm tra

**1.** `demo.tags[0]` và `demo.tags[1]` khác `demo.tags=one,two` ở điểm nào? Khi nào chúng cho cùng `List<String>`?

**2.** Vì sao viết `demo.locations=City, Country,Hanoi` không an toàn nếu `City, Country` là một phần tử duy nhất?

**3.** Với `List<Backend>`, vì sao một chuỗi `inventory,billing` không mô tả đầy đủ `baseUrl` và `timeout`?

**4.** Biến môi trường nào tương ứng với `demo.backends[0].base-url` theo quy tắc Spring Boot được nêu trong bài?

**5.** File nền có `regions=[a,b]`, file dev có `regions=[local]`. Khi dev hoạt động, list có thể là gì? Vì sao không mặc định là `[local,b]`?

**6.** Map nền có `team=platform`, `stage=base`, map dev chỉ có `stage=development`. Trường hợp điển hình nào khác với list override?

**7.** Tại sao trong YAML map key `[/api/v1]` phải được quote?

**8.** Có nên đọc `Environment.getProperty("demo.backends")` rồi kết luận nó luôn trả một chuỗi chứa tất cả object đã index không?

**9.** Một indexed list khai báo phần tử 0 và 2 nhưng thiếu 1. Bạn nên sửa thế nào?

**10.** Nếu config CSV chứa `100ms,not-a-duration`, hệ thống nên bỏ qua phần tử hỏng hay báo lỗi conversion?

**11.** Tại sao sau khi sửa `application-dev.yaml`, bạn cần chạy tiến trình mới trong bài lab?

**12.** Trường hợp nào nên chuyển từ list có index sang map có key ổn định?

**Gợi ý đối chiếu:**

1. Một cách dùng các key có index, một cách cấp scalar CSV; với target `List<String>` và dữ liệu đơn giản, cả hai có thể cho danh sách cùng thứ tự.
2. Dấu phẩy vừa là dữ liệu vừa là dấu tách; dùng YAML sequence hoặc indexed properties để bảo toàn phần tử.
3. Vì object có nhiều field; cần YAML list object hoặc indexed property keys.
4. `DEMO_BACKENDS_0_BASEURL`.
5. `[local]`, vì list từ nguồn ưu tiên có thể thay danh sách, không merge theo index với file nền.
6. Map có thể tổng hợp key `team` từ nền và ghi đè key `stage` từ dev.
7. Vì ký hiệu `[]` cần được biểu diễn như một tên key YAML hợp lệ và binder cần bảo toàn chuỗi đặc biệt.
8. Không; indexed properties không mặc định tạo scalar root `demo.backends` phù hợp cho `getProperty()`.
9. Đánh lại index liên tiếp từ 0 hoặc khai báo đủ phần tử.
10. Báo lỗi conversion; không che giấu cấu hình hỏng bằng cách bỏ phần tử.
11. Config Data thông thường nạp lúc khởi động; bean đã bind không tự refresh.
12. Khi mỗi phần tử có định danh ổn định và cần truy cập/override theo tên hơn là theo thứ tự.

## 23. Áp dụng vào dự án thực tế

Một quy ước dễ áp dụng:

```text
Scalar đơn giản, ít phần tử:
  YAML sequence hoặc comma-separated.

Scalar có ký tự phân tách đặc biệt:
  YAML sequence hoặc indexed keys.

Danh sách object có nhiều trường:
  YAML sequence hoặc indexed keys liên tiếp.

Collection ghi đè giữa profile/CLI/environment:
  Viết đầy đủ danh sách tại nguồn ưu tiên.

Các phần tử có ID ổn định, muốn override theo ID:
  Cân nhắc Map thay vì List.

Map key chứa slash/dấu chấm có ý nghĩa:
  Dùng bracket notation và quote đúng trong YAML.

Java code:
  @ConfigurationProperties + type conversion + validation.
```

Khi thiết kế cấu hình trong tổ chức, hãy tài liệu hóa tên property canonical, kiểu đích, nguồn cho phép ghi đè, chiến lược update và cách diễn giải giá trị rỗng. Dùng danh sách như **một snapshot có thứ tự** và map như **tập dữ liệu có key** sẽ giúp người vận hành đoán được kết quả giữa local, profile, CI và container.

Tóm tắt bằng một sơ đồ:

```text
application.yaml / properties / environment / CLI
                         |
                         v
                 Property Sources
                         |
                    Ưu tiên nguồn
                         |
                         v
              @ConfigurationProperties
                         |
        +----------------+----------------+
        |                |                |
   CSV / index       YAML sequence     YAML / key-value
        |                |                |
        v                v                v
  List<String>      List<Backend>    Map<String,String>
                         |
                         v
             Validation + ứng dụng dùng
```

Điều cần ghi nhớ nhất: **`[0]`, `[1]` mô tả vị trí trong collection; dấu phẩy mô tả cách chuyển một chuỗi scalar thành nhiều phần tử; còn Map mô tả key ổn định.** Khi một nguồn cấu hình ưu tiên cao thay đổi List, đừng tự ghép từng index từ nguồn thấp hơn. Hãy bind vào kiểu Java rõ ràng, thử nghiệm cả profile override và validation, rồi quan sát kết quả với một ứng dụng nhỏ như lab này.

### Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html), các mục *Type-safe Configuration Properties*, *Relaxed Binding*, *Merging Complex Types*, *Binding Maps*.
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html), cách dùng `application-dev.yaml` và profile-specific Config Data.
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html), conversion service và các kiểu collection.
# After, Before và Between: định tuyến theo thời gian và múi giờ trong Spring Cloud Gateway

Khi xây dựng **SPRING_CLOUD_GATEWAY**, bạn có thể muốn mở một API từ một thời điểm xác định, chuyển request đến backend khuyến mại trong một khung giờ hoặc ngừng nhận lưu lượng của một tuyến sau thời hạn. **After**, **Before** và **Between** là ba **Route Predicate Factory** giúp Spring Cloud Gateway lựa chọn route dựa vào **thời điểm hiện tại tại Gateway**.

Bài học thuộc chương **Điều kiện định tuyến**, tập trung vào cú pháp, ý nghĩa mốc thời gian, múi giờ, ranh giới so khớp và cách kiểm thử. Sau khi chọn được route, Gateway mới thực hiện filter chain, biến đổi path/header và chuyển tiếp đến dịch vụ. Các tính năng xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request tiếp tục cần cấu hình riêng; chúng không tự được bảo đảm chỉ vì một predicate thời gian đã khớp.

> **Phạm vi phiên bản:** Ví dụ YAML dùng cách cấu hình thường gặp ở **Spring Cloud Gateway Server WebFlux 4.x** với khóa `spring.cloud.gateway.routes`. Namespace, starter và cách khai báo trong **Gateway Server MVC** hoặc các dòng phát hành khác có thể khác nhau. Hãy kiểm tra tài liệu chính thức đúng **phiên bản Gateway, Spring Cloud release train và biến thể** đang chạy.

## 1. Predicate thời gian hoạt động tại bước nào?

Gateway nhận một request HTTP, lần lượt xét các route có trong tập định tuyến, đánh giá predicates và chọn route khớp theo cơ chế thứ tự. Với route có `After`, `Before` hoặc `Between`, Gateway so sánh **thời điểm hiện tại của tiến trình Gateway** với mốc đã cấu hình.

~~~mermaid
flowchart TD
    A["Client gửi HTTP request"] --> B["Gateway xem tập Route"]
    B --> C{"Path, Method, Header... khớp?"}
    C -->|Không| N["Xét Route tiếp theo"]
    C -->|Có| D{"After / Before / Between khớp thời điểm hiện tại?"}
    D -->|Không| N
    D -->|Có| E["Chọn Route"]
    E --> F["GatewayFilter chain: auth-related filters, path/header, limit, retry..."]
    F --> G["Routing / service discovery / downstream"]
    G --> H["Response về client"]
    N --> I{"Còn Route khác?"}
    I -->|Có| B
    I -->|Không| J["Không có Gateway route khớp; thường 404 nếu không có handler khác"]
~~~

Sơ đồ là mô hình khái niệm: Spring Security `WebFilter` có thể chặn request **trước** khi route được chọn; trong Gateway filter chain, filter cũng có thể kết thúc sớm mà không gọi downstream.

Các predicate thời gian được đánh giá **lúc xem xét request**; chúng không phải tác vụ `cron`, không tự khởi động/tắt service và không sửa `RouteDefinition` theo lịch. Route đã được cache vẫn có thể đổi từ **không khớp** sang **khớp**, hoặc ngược lại, khi thời gian thực trôi qua mà không cần khai báo lại route.

## 2. Định nghĩa chính xác của After, Before và Between

Giả sử `now` là thời điểm mà Gateway dùng để đánh giá predicate, `T` là mốc được cấu hình, còn `T1` và `T2` là hai mốc của một khoảng:

| Factory | Điều kiện để route khớp | Cú pháp rút gọn | Ý nghĩa thực tế |
|---|---|---|---|
| `After` | `now > T` | `After=T` | Chỉ nhận route **sau** mốc T |
| `Before` | `now < T` | `Before=T` | Chỉ nhận route **trước** mốc T |
| `Between` | `T1 < now < T2` | `Between=T1,T2` | Chỉ nhận route **bên trong** khoảng (T1, T2) |

Điều kiện so sánh ở đây là **nghiêm ngặt**: thời điểm **bằng đúng** ranh giới không khớp.

- `After` không nhận request nếu thời điểm hiện tại **chưa vượt qua** mốc.
- `Before` không nhận request nếu thời điểm hiện tại **đã chạm hoặc vượt qua** mốc.
- `Between` yêu cầu `T1` **sớm hơn** `T2` và thường không nhận chính hai mốc biên.

Trong ứng dụng, xác suất request rơi đúng một nano/giây biên có thể thấp, nhưng phải coi đây là đặc tính thực sự của predicate. Nếu cần quy tắc biên **bao gồm** thời điểm bắt đầu hoặc kết thúc, hãy thiết kế bổ sung bằng route fallback hoặc predicate tùy biến thay vì giả định `Between` là khoảng đóng.

### Vì sao không dùng thời gian client?

Client có thể gửi header `Date`, truyền query parameter chứa timestamp hoặc chỉnh múi giờ thiết bị. Các giá trị đó **không phải nguồn thời gian** mà ba predicate này sử dụng để quyết định route theo mặc định. Route được so khớp dựa vào thời gian ở môi trường Gateway, vì vậy kiểm soát đồng hồ Gateway và logic múi giờ quan trọng hơn đồng hồ của người gọi API.

## 3. Cú pháp thời gian: ISO-8601 và `ZonedDateTime`

Các factory thời gian ở Gateway Server WebFlux sử dụng mô hình thời gian Java như `java.time.ZonedDateTime`. Hãy truyền một mốc **ISO-8601 kèm thông tin offset/múi giờ**, thay vì chuỗi giờ địa phương không rõ vùng.

Ví dụ hợp lệ để minh họa định dạng:

~~~text
2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh]
2027-06-01T02:00:00Z
2027-05-31T22:00:00-04:00[America/New_York]
~~~

Ba chuỗi trên biểu diễn **cùng một thời điểm**:

| Cách biểu diễn | Giờ hiển thị | Tương ứng UTC |
|---|---|---|
| Thành phố Hồ Chí Minh | `2027-06-01 09:00:00 +07:00` | `2027-06-01 02:00:00Z` |
| UTC | `2027-06-01 02:00:00Z` | `2027-06-01 02:00:00Z` |
| New York vào mùa áp dụng `-04:00` | `2027-05-31 22:00:00 -04:00` | `2027-06-01 02:00:00Z` |

Khi so sánh, logic `isAfter`/`isBefore` tương ứng so thời điểm tuyệt đối trên trục thời gian. **Múi giờ khác nhau không làm thay đổi thứ tự thực của các instant**, miễn các mốc được diễn giải đúng.

### Offset và Zone ID khác nhau thế nào?

- **Offset** như `+07:00` cho biết giờ địa phương lệch UTC bao nhiêu vào **thời điểm được ghi**.
- **Zone ID** như `Asia/Ho_Chi_Minh` hoặc `America/New_York` chỉ quy tắc múi giờ khu vực, gồm thay đổi lịch sử và quy tắc giờ mùa hè nếu có.
- **`Z`** ở cuối một timestamp ISO-8601 biểu diễn offset UTC `+00:00`.

Ví dụ:

~~~text
2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh]
           |        |
           |        +-- Zone ID: vùng Asia/Ho_Chi_Minh
           +----------- Offset tại mốc đó: +07:00
~~~

Có thể dùng mốc kèm offset mà không có Zone ID khi bộ phân tích phiên bản đang dùng chấp nhận định dạng đó; dạng kèm offset rõ ràng và Zone ID thích hợp giúp người bảo trì nhìn thấy **cả giờ địa phương và vùng áp dụng**.

**Không viết:** `2027-06-01T09:00:00` rồi mong Gateway tự hiểu đây là giờ Việt Nam. Chuỗi thiếu offset/vùng không cung cấp đủ thông tin để diễn giải một `ZonedDateTime` theo cú pháp thường dùng.

### Cẩn thận với giờ mùa hè (DST)

Một số khu vực như `America/New_York` thay đổi offset theo mùa. Vì vậy, `09:00` ở New York có thể tương ứng `14:00Z` vào mùa đông (`-05:00`) hoặc `13:00Z` vào mùa hè (`-04:00`). `Asia/Ho_Chi_Minh` hiện dùng `+07:00` trong các tình huống đương đại.

Trong ngày chuyển DST có thể tồn tại **giờ địa phương bị bỏ qua** hoặc **lặp lại**. Khi lên lịch ở vùng có DST:

1. Xác định **ngày cụ thể** và Zone ID theo nghiệp vụ.
2. Tính offset đúng với ngày đó, không gán một offset cố định cho mọi mùa.
3. Tránh mốc giờ không tồn tại hoặc không duy nhất, hoặc giải quyết sự nhập nhằng bằng cách chọn instant/offset rõ ràng.
4. Kiểm tra kết quả chuyển đổi ra UTC trước khi đưa vào cấu hình.

Ví dụ `2027-01-15T09:00:00-05:00[America/New_York]` và `2027-07-15T09:00:00-04:00[America/New_York]` đều diễn đạt 09:00 theo khu vực New York tại hai ngày khác mùa. Đây là **hai thời điểm khác nhau**, không phải hai cách viết của cùng một instant.

## 4. After: bắt đầu định tuyến sau một mốc

Giả định backend phiên bản mới tại `http://localhost:9091` chỉ nên nhận route `/api/catalog/**` **sau** 09:00 ngày 01/06/2027, theo giờ Thành phố Hồ Chí Minh.

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-after
          uri: http://localhost:9091
          predicates:
            - Path=/api/catalog/**
            - 'After=2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh]'
          filters:
            - StripPrefix=1
~~~

Ý nghĩa:

- 08:59:59.999 theo múi giờ đã nêu: `After` chưa khớp.
- **09:00:00.000 đúng mốc**: `After` vẫn chưa khớp.
- 09:00:00.001: `After` có thể khớp, miễn `Path` cũng khớp và route được xét/chọn.

`After` không có nghĩa “mỗi ngày sau 09:00”; đây là **một mốc ngày giờ cố định**. Sau khi qua ngày 01/06/2027, nó tiếp tục khớp vào những ngày kế tiếp cho đến khi route/cấu hình đổi.

### Khai báo dạng đầy đủ

~~~yaml
predicates:
  - name: Path
    args:
      patterns:
        - /api/catalog/**
  - name: After
    args:
      datetime: '2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh]'
~~~

Trường `datetime` thuộc phần cấu hình factory `After`. Viết đầy đủ có ích khi review và tránh nhầm với các giá trị khác trong một chuỗi YAML.

## 5. Before: chỉ định tuyến trước thời hạn

Giả định route `/api/legacy/**` chỉ có hiệu lực **trước** 18:00 ngày 30/06/2027 theo giờ Thành phố Hồ Chí Minh.

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: legacy-before
          uri: http://localhost:9092
          predicates:
            - Path=/api/legacy/**
            - 'Before=2027-06-30T18:00:00+07:00[Asia/Ho_Chi_Minh]'
~~~

- Request 17:59:59.999 có thể khớp.
- Request **18:00:00.000 đúng mốc** không khớp.
- Request sau 18:00 không khớp route này.

Dạng đầy đủ:

~~~yaml
predicates:
  - name: Path
    args:
      patterns:
        - /api/legacy/**
  - name: Before
    args:
      datetime: '2027-06-30T18:00:00+07:00[Asia/Ho_Chi_Minh]'
~~~

**Before không tự vô hiệu hóa toàn bộ endpoint HTTP của ứng dụng.** Nếu một route khác vẫn nhận cùng `Path`, request có thể đi qua route kia; nếu không có route/handler nào khớp, kết quả thường là 404. Việc đóng một tính năng có thể còn cần kiểm soát ở backend hoặc tầng phân quyền, nhất là nếu downstream vẫn có đường truy cập khác.

## 6. Between: chỉ định tuyến trong một cửa sổ thời gian

Ví dụ một chương trình khuyến mại nhận request trong khoảng **09:00–10:00 ngày 01/06/2027**, tính theo `Asia/Ho_Chi_Minh`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: promotion-window
          uri: http://localhost:9093
          predicates:
            - Path=/api/offers/**
            - 'Between=2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh],2027-06-01T10:00:00+07:00[Asia/Ho_Chi_Minh]'
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Campaign,summer
~~~

Dạng đầy đủ biểu đạt cùng mục tiêu:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: promotion-window
          uri: http://localhost:9093
          predicates:
            - name: Path
              args:
                patterns:
                  - /api/offers/**
            - name: Between
              args:
                datetime1: '2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh]'
                datetime2: '2027-06-01T10:00:00+07:00[Asia/Ho_Chi_Minh]'
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Campaign,summer
~~~

Các field `datetime1` và `datetime2` lần lượt là **điểm bắt đầu** và **điểm kết thúc**. `datetime1` phải **trước** `datetime2`; đảo thứ tự hoặc đặt hai mốc bằng nhau là cấu hình không hợp lệ về mặt logic của factory và có thể khiến việc nạp route/khởi động thất bại.

| Thời điểm ở `Asia/Ho_Chi_Minh` | `Between` khớp? | Giải thích |
|---|---|---|
| 08:59:59.999 | Không | Chưa sau thời điểm bắt đầu |
| **09:00:00.000** | **Không** | Bằng mốc đầu |
| 09:00:00.001 | Có | Nằm bên trong khoảng |
| 09:30:00 | Có | Nằm bên trong khoảng |
| 09:59:59.999 | Có | Chưa đến mốc kết thúc |
| **10:00:00.000** | **Không** | Bằng mốc cuối |
| 10:00:00.001 | Không | Đã qua khoảng |

**Một khoảng `Between` không tự lặp hằng ngày.** Muốn lặp lại 09:00–10:00 mỗi ngày, cần công cụ lịch, cơ chế cập nhật cấu hình hoặc custom predicate có thiết kế phù hợp. Một `Between` với hai timestamp cố định không có quy tắc “ngày nào cũng vậy”.

### Cửa sổ đi qua nửa đêm

Một khung 22:00–02:00 hôm sau phải dùng **hai ngày khác nhau**:

~~~yaml
predicates:
  - Path=/api/night-service/**
  - 'Between=2027-10-12T22:00:00+07:00[Asia/Ho_Chi_Minh],2027-10-13T02:00:00+07:00[Asia/Ho_Chi_Minh]'
~~~

Nếu viết cả hai mốc vào cùng ngày 12/10, mốc `02:00` sẽ sớm hơn `22:00` và làm khoảng bị đảo thứ tự. Ví dụ trên chỉ áp dụng cho **đúng một đêm được nêu**.

## 7. Kết hợp thời gian với Path, Method và route order

Các predicate trong **cùng một route** thường kết hợp theo phép **AND**: route khớp khi vừa thỏa đường dẫn/phương thức, vừa thỏa thời gian. Ví dụ:

~~~yaml
predicates:
  - Path=/api/offers/**
  - Method=GET
  - 'Between=2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh],2027-06-01T10:00:00+07:00[Asia/Ho_Chi_Minh]'
~~~

`POST /api/offers/42` không khớp route này dù request đến lúc 09:30, vì `Method=GET` sai.

Khi **nhiều route cùng có khả năng khớp**, thứ tự route (`order`) quyết định route nào được xét trước. Giá trị `order` nhỏ hơn thường được ưu tiên; không dựa vào thứ tự YAML để xử lý các route chồng lấn.

### Thiết kế trước – trong – sau và fallback

Ví dụ ba backend khác nhau cho cùng một đường dẫn:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: offers-before
          order: -10
          uri: http://localhost:9091
          predicates:
            - Path=/api/offers/**
            - 'Before=2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh]'

        - id: offers-promotion
          order: -10
          uri: http://localhost:9092
          predicates:
            - Path=/api/offers/**
            - 'Between=2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh],2027-06-01T10:00:00+07:00[Asia/Ho_Chi_Minh]'

        - id: offers-after
          order: -10
          uri: http://localhost:9093
          predicates:
            - Path=/api/offers/**
            - 'After=2027-06-01T10:00:00+07:00[Asia/Ho_Chi_Minh]'

        - id: offers-fallback
          order: 100
          uri: http://localhost:9094
          predicates:
            - Path=/api/offers/**
~~~

Ở hai **thời điểm biên chính xác** 09:00:00 và 10:00:00, ba route có predicate thời gian đều không khớp, do điều kiện nghiêm ngặt. Route `offers-fallback` có `order` lớn hơn vẫn có thể nhận request, nếu các route khác không match.

Ở các khoảng khác, các route thời gian không chồng lấn nhau, nên dùng cùng `order=-10` không tạo mâu thuẫn về lựa chọn trong ví dụ này. Fallback cần phù hợp với nghiệp vụ: trả trang chờ, thông báo hết hạn hoặc điều phối tới backend an toàn. Nếu không cần fallback, hãy dự kiến hành vi khi **không route nào khớp**.

| Thời điểm (giờ Việt Nam) | Route dự kiến | Backend |
|---|---|---|
| 01/06/2027, 08:59:00 | `offers-before` | `localhost:9091` |
| 01/06/2027, đúng 09:00:00 | `offers-fallback` | `localhost:9094` |
| 01/06/2027, 09:15:00 | `offers-promotion` | `localhost:9092` |
| 01/06/2027, đúng 10:00:00 | `offers-fallback` | `localhost:9094` |
| 01/06/2027, 10:00:01 | `offers-after` | `localhost:9093` |

**Lưu ý:** Các ngày cố định trong bài chỉ để học cách cấu hình. Nếu triển khai ví dụ vào thời điểm khác, trạng thái route sẽ phản ánh **ngày giờ thật của Gateway**, không phản ánh các mốc mô phỏng trong bảng.

## 8. Những nguồn gây sai lệch thời gian trong hệ thống nhiều Gateway

Với một Gateway instance, giá trị hiện tại được lấy từ **đồng hồ hệ thống của tiến trình chạy Gateway**. Trong một cụm nhiều instance sau load balancer, mỗi instance có đồng hồ riêng:

~~~mermaid
flowchart LR
    C["Client"] --> L["Load balancer"]
    L --> A["Gateway A\nClock: 08:59:59"]
    L --> B["Gateway B\nClock: 09:00:02"]
    A --> X["Predicate thời gian: có thể chưa khớp"]
    B --> Y["Predicate thời gian: có thể đã khớp"]
~~~

Nếu đồng hồ hai node lệch vài giây ở sát ranh giới, cùng một request logic có thể đi tới backend khác nhau tùy instance nhận nó.

Các biện pháp vận hành:

- Đồng bộ thời gian bằng **NTP hoặc cơ chế đồng bộ thời gian đáng tin cậy**; theo dõi độ lệch giữa các node và nguồn thời gian.
- Cấu hình timestamp với **offset/Zone ID rõ ràng**, không dựa vào timezone mặc định của máy, container hoặc trình duyệt.
- Kiểm tra tài liệu và cấu hình route ở **tất cả instance**, tránh trường hợp một node đã cập nhật route còn node khác vẫn giữ cache/cấu hình cũ.
- Thiết kế khoảng đệm, fallback hoặc cơ chế chuyển hướng có khả năng chịu sai lệch vài mili/giây nếu nghiệp vụ nhạy với thời điểm bắt đầu/kết thúc.
- Nếu cần hiệu lực pháp lý hoặc thanh toán ở từng mili giây, xác nhận ở **backend có nguồn thời gian và trạng thái nghiệp vụ được quản lý tập trung**, thay vì coi predicate tại gateway là bằng chứng duy nhất.

### Thời điểm quyết định không nhất thiết là lúc downstream xử lý

Gateway đánh giá predicate trước khi filter chain và bước chuyển tiếp downstream hoàn tất. Một request đến gần cuối cửa sổ có thể **match khi được chọn route**, nhưng downstream xử lý sau khi thời hạn đã trôi qua. Ngược lại, request chỉ có thể được chọn dựa trên thời điểm Gateway đánh giá, không thể dựa vào thời điểm giao dịch thực sự được commit ở backend. Những nghiệp vụ như giá khuyến mại, hiệu lực token, thanh toán hoặc quyền truy cập nhạy cảm nên kiểm tra điều kiện nghiệp vụ tại nơi thực hiện giao dịch.

## 9. Những lỗi cấu hình phổ biến

| Sai sót | Hậu quả thường gặp | Cách xử lý |
|---|---|---|
| Dùng `2027-06-01T09:00:00` không có offset/vùng | Không parse được theo `ZonedDateTime` trong cấu hình tương ứng | Thêm `+07:00[Asia/Ho_Chi_Minh]` hoặc `Z` UTC |
| Ghi `09:00` mà nhầm UTC thành giờ Việt Nam | Route bật/tắt lệch **7 giờ** so với ý định | Chuyển giờ địa phương sang instant chính xác |
| `Between` có `datetime2` trước `datetime1` | Khoảng sai thứ tự; có thể lỗi khởi tạo route | Dùng đúng hai instant tăng dần |
| Dùng `Between` cho lịch lặp hằng ngày | Chỉ có hiệu lực ở một khoảng ngày giờ cụ thể | Thiết kế lịch lặp hoặc custom predicate phù hợp |
| Đọc `Between` như khoảng đóng | Request đúng ranh giới không match | Dự kiến fallback và kiểm thử biên |
| Dùng shortcut mà thiếu dấu phẩy giữa hai mốc | Factory nhận thiếu tham số | Dùng cú pháp đầy đủ `datetime1`/`datetime2` |
| Nhầm ngày khi khung giờ qua nửa đêm | Kết thúc trước bắt đầu | Ghi `datetime2` ở ngày hôm sau |
| Cấu hình zone/offset sai trong mùa DST | Giờ chuyển đổi ra UTC lệch dự kiến | Dùng Zone ID/offset đúng ngày và xác minh instant |
| Gateway không thấy route nhưng cho rằng đã hết hạn | Có thể thiếu dependency, sai namespace, lỗi bind hoặc route chưa refresh | Tách lỗi **route có/không** khỏi lỗi **predicate có/không match** |
| Node A nhận còn Node B từ chối | Đồng hồ, phiên bản cấu hình/cache hoặc route order khác nhau | Kiểm tra NTP, cấu hình và trạng thái từng node |

### Vì sao nên quote timestamp trong YAML?

Các giá trị có dấu `:`, dấu ngoặc vuông `[...]`, ký tự `+`, và chuỗi chứa dấu phẩy nên được đặt trong dấu nháy để người đọc và YAML parser xử lý nhất quán:

~~~yaml
predicates:
  - 'After=2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh]'
  - 'Before=2027-06-30T18:00:00+07:00[Asia/Ho_Chi_Minh]'
~~~

Ví dụ chỉ để minh họa cách quote; nếu đặt **cả After và Before** trong cùng route, chúng cần **đồng thời khớp**, tạo một khoảng thời gian giao nhau. Với khoảng thời gian đơn giản, `Between` thường thể hiện ý định rõ hơn.

YAML hợp lệ chưa chắc route đã được xây dựng: tên factory, loại tham số, tính hợp lệ của `ZonedDateTime` và các điều kiện runtime còn cần được Gateway xác nhận.

## 10. Cách kiểm thử thực tế mà không sửa đồng hồ máy chủ

Không nên chỉnh clock của máy phát triển hoặc máy Gateway production chỉ để đợi `After` hay `Between` khớp. Cách an toàn là **tạo mốc tương đối quanh thời gian hiện tại** cho môi trường thử nghiệm.

Ví dụ dùng **JShell** có sẵn trong một JDK phù hợp để in giá trị `Between` quanh thời điểm chạy:

~~~java
import java.time.*;
import java.time.format.*;

var zone = ZoneId.of("Asia/Ho_Chi_Minh");
var now = ZonedDateTime.now(zone);
var start = now.minusMinutes(5);
var end = now.plusMinutes(30);

System.out.println("After=" + start.format(DateTimeFormatter.ISO_ZONED_DATE_TIME));
System.out.println("Before=" + end.format(DateTimeFormatter.ISO_ZONED_DATE_TIME));
System.out.println("Between=" +
    start.format(DateTimeFormatter.ISO_ZONED_DATE_TIME) + "," +
    end.format(DateTimeFormatter.ISO_ZONED_DATE_TIME));
~~~

Chạy `jshell` từ terminal có JDK và nhập đoạn mã trên. Copy chuỗi `Between=...` được in ra vào một route test; khởi động lại hoặc áp dụng refresh cấu hình theo cơ chế được Gateway phiên bản đó hỗ trợ. **Mốc chỉ có hiệu lực trong cửa sổ khoảng 35 phút đã tạo**, nên thực hiện phép thử ngay; nếu quá hạn, tạo giá trị mới.

Giả định downstream test ở `localhost:9090` có endpoint `GET /orders/42` và ghi lại path/header:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: test-time-window
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
            - Method=GET
            # Thay giá trị bên dưới bằng chuỗi Between=... vừa tạo bằng JShell:
            - 'Between=2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh],2027-06-01T10:00:00+07:00[Asia/Ho_Chi_Minh]'
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Gateway-Test,time-window
~~~

Trong thử nghiệm thực tế, **phải thay** dòng `Between=...` cố định bằng output mới sinh, nếu không chưa chắc request rơi vào khoảng đang test.

Gửi:

~~~bash
curl -i http://localhost:8080/api/orders/42
curl -i -X POST http://localhost:8080/api/orders/42
~~~

Kỳ vọng khi backend đang chạy, Gateway lắng nghe 8080, cấu hình đã được nạp và request GET nằm trong cửa sổ:

- **GET** khớp `Path`, `Method`, `Between`; downstream nhận `GET /orders/42` với header `X-Gateway-Test: time-window`.
- **POST** không khớp `Method=GET` của route này, dù nằm trong cửa sổ; nếu không có route hoặc handler khác, thường nhận 404.
- Nếu GET nhận 5xx, kiểm tra kết nối downstream, DNS/TLS, filter và log; **5xx không tự chứng minh predicate thời gian sai**.

### Kiểm tra các trường hợp âm

Ở một môi trường thử nghiệm riêng, có thể tạo mốc `After` ở tương lai (route chưa match) hoặc `Before` ở quá khứ (route đã hết hạn) bằng cách tính từ `ZonedDateTime.now(zone)`. Đọc danh sách routes để xác nhận route vẫn tồn tại dù request không match. Sau đó đổi lại giá trị hợp lệ và kiểm chứng route nhận request.

Để kiểm tra **đúng giây biên**, thử nghiệm dựa vào clock hệ thống thật thường thiếu ổn định do network latency và scheduling. Với yêu cầu độ chính xác cao, dùng **kiểm thử logic thời gian tách biệt có thể cấp Clock**, hoặc một predicate tùy biến thiết kế cho việc inject `Clock`; không giả định factory built-in cung cấp sẵn tùy chọn thay clock trong YAML.

## 11. Vận hành cùng các thành phần khác của Gateway

Predicate thời gian quyết định **route nào được chọn**, còn những chức năng quan trọng vẫn có cấu hình riêng:

| Thành phần | Quan hệ với predicate thời gian | Cần kiểm chứng |
|---|---|---|
| `Path`, `Method`, `Host` | Kết hợp với `After`/`Before`/`Between` trong cùng route theo AND | Một request thỏa thời gian nhưng sai path/method vẫn bị loại khỏi route |
| Route `order` và fallback | Xác định tuyến nào được xét trước khi nhiều tuyến match | Cửa sổ biên và route chồng lấn có kết quả rõ ràng |
| `StripPrefix`, `RewritePath`, thay header | Thực hiện sau khi route được chọn | Backend nhận đúng path/header |
| Service discovery, `lb://` | Chọn instance của downstream sau khi route được xác định | Dịch vụ đã đăng ký, có load balancer phù hợp và instance khả dụng |
| Xác thực / phân quyền | Có thể được thực hiện ở tầng `WebFilter` hoặc filter phù hợp | Request không khớp route cũng được xử lý bảo mật đúng yêu cầu |
| Rate limiting | Giới hạn request theo chính sách sau/ở tầng tích hợp tương ứng | Không cho lưu lượng vượt ngưỡng bypass qua fallback route |
| Circuit breaker và retry | Kiểm soát lỗi/khả năng chịu tải khi gọi downstream | Không retry không kiểm soát; kiểm thử timeout, fallback và mã lỗi |
| TLS | Bảo vệ client → Gateway và Gateway → downstream | Certificate, trust và HTTPS không phụ thuộc vào việc predicate khớp |
| Metrics, logs, tracing | Ghi nhận route, request, lỗi và latency | Phân biệt lỗi không match route với lỗi downstream và lệch thời gian giữa node |

Ví dụ route khuyến mại chỉ mở theo `Between` **không phải cơ chế xác thực người dùng**. Ai thỏa điều kiện path/method và truy cập được Gateway trong khung giờ đều có thể được chọn route, trừ khi có chính sách xác thực/phân quyền được thiết lập. Đối với khuyến mại liên quan tiền hoặc dữ liệu nhạy cảm, backend phải thực thi điều kiện nghiệp vụ chính xác.

### Thay đổi lịch chạy có cần refresh?

- **Không nhất thiết cần refresh** chỉ vì đồng hồ đi từ trước mốc sang sau mốc; predicate đánh giá thời gian tại lần request tiếp theo.
- **Cần áp dụng quy trình cập nhật cấu hình** nếu bạn sửa giá trị timestamp, thêm/xóa route hoặc đổi URI/filter trong nguồn cấu hình. Nếu ứng dụng chỉ đọc cấu hình tĩnh khi khởi động, cần restart hoặc cơ chế reload được hỗ trợ.
- Với nhiều instance, cần kiểm tra từng node đều đã nhận cấu hình mới. Một node chưa refresh có thể có mốc khác và cho ra kết quả khác.

Nếu dùng Actuator để xem/refresh route, chỉ mở các management endpoint cần thiết theo tài liệu đúng phiên bản và bảo vệ chúng bằng quyền truy cập phù hợp.

## 12. Checklist trước khi đưa route theo thời gian lên môi trường thật

- [ ] Đã xác nhận **phiên bản và biến thể Gateway**; cú pháp YAML phù hợp với bản đang chạy.
- [ ] Đã chọn đúng `After`, `Before` hoặc `Between` theo nghiệp vụ một lần, không nhầm với lịch lặp hằng ngày.
- [ ] Mốc được viết bằng **ISO-8601** và có **offset/Zone ID rõ ràng**.
- [ ] Đã chuyển các mốc sang **UTC** để xác minh cùng một instant.
- [ ] Với vùng có DST, đã kiểm tra ngày đổi giờ, offset và giờ nhập nhằng/không tồn tại.
- [ ] `datetime1` của `Between` **sớm hơn** `datetime2`; khung qua nửa đêm dùng hai ngày đúng.
- [ ] Đã xét điều kiện **nghiêm ngặt ở hai biên** và định nghĩa fallback khi cần.
- [ ] Đã kiểm tra sự kết hợp AND với `Path`, `Method` và ưu tiên `order` của các route.
- [ ] Đồng hồ Gateway được đồng bộ; nhiều instance có cùng cấu hình/cache hợp lệ.
- [ ] Đã thử request đúng route, sai path/method, ngoài khung giờ và backend lỗi.
- [ ] Xác thực, rate limiting, retry/circuit breaker, TLS và quan sát request có chính sách riêng phù hợp.
- [ ] Các quyết định nhạy cảm về thanh toán, quyền truy cập và hết hạn được kiểm tra tại backend hoặc thành phần có thẩm quyền.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — tìm các mục **After Route Predicate Factory**, **Before Route Predicate Factory** và **Between Route Predicate Factory** của **đúng phiên bản/biến thể**.
- [Spring Cloud Gateway project](https://spring.io/projects/spring-cloud-gateway) — điểm truy cập tài liệu và thông tin phát hành dự án.
- [Java ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html) — cách biểu diễn, parse và so sánh thời gian theo múi giờ.
- [Java DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html) — định dạng ISO-8601 và `ISO_ZONED_DATE_TIME`.

**Ghi nhớ:** `After` yêu cầu **sau mốc**, `Before` yêu cầu **trước mốc**, còn `Between` yêu cầu **nằm hẳn giữa hai mốc**. Cả ba đánh giá thời điểm từ phía Gateway và so sánh các instant thực; muốn vận hành đúng phải khai báo múi giờ rõ ràng, dự kiến cách xử lý ở biên và xác minh hành vi trong cụm nhiều instance.

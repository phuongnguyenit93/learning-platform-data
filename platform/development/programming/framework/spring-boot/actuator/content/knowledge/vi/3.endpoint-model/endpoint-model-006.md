# Đọc kiểu nội dung và cấu trúc phản hồi của Actuator API

## 1. Một phản hồi phải được đọc trên ba lớp

Khi gọi một endpoint quản trị, đừng bắt đầu bằng việc tìm ngay một thuộc tính trong JSON. Hãy trả lời lần lượt:

1. **Mã trạng thái HTTP:** yêu cầu đã được xử lý với kết quả nào?
2. **Kiểu nội dung:** máy chủ thực sự gửi về JSON, văn bản hay dữ liệu nhị phân?
3. **Cấu trúc và ý nghĩa của phần thân:** với đúng endpoint và phiên bản biểu diễn đó, các trường nói lên điều gì?

Ví dụ, `200` ở dòng trạng thái, `application/vnd.spring-boot.actuator.v3+json` ở header và `"status": "UP"` trong phần thân thuộc ba lớp khác nhau. Ghép chúng thành một khái niệm “API thành công” sẽ làm mất thông tin khi chẩn đoán.

Trong mô hình endpoint, **endpoint** xác định nhóm chức năng quản trị; **thao tác** xác định việc đọc hoặc thay đổi dữ liệu; **biểu diễn (representation)** là dạng dữ liệu được gửi qua HTTP. Cùng một địa chỉ có thể có nhiều biểu diễn được hỗ trợ. Biết địa chỉ chưa đủ để biết cách giải mã.

Bài này dùng hợp đồng Actuator của **Spring Boot 3.3.x**, đối chiếu tài liệu 3.3.13. Các lệnh minh họa dùng ứng dụng đã chạy ở `http://localhost:8080`, có Actuator và quyền truy cập phù hợp; điều chỉnh địa chỉ theo môi trường thực tế. Trên Windows dùng `curl.exe` để tránh nhầm với alias của PowerShell; trên Linux/macOS dùng `curl`.

## 2. Quan sát nguyên phản hồi trước khi lọc dữ liệu

Gọi health và yêu cầu biểu diễn JSON V3:

~~~powershell
curl.exe -sS -i -H "Accept: application/vnd.spring-boot.actuator.v3+json" "http://localhost:8080/actuator/health"
~~~

Một phản hồi minh họa khi ứng dụng khỏe mạnh và không công bố chi tiết:

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

Đây là ví dụ giản lược, không phải bản ghi của mọi môi trường. Phản hồi thực có thể thêm header, dùng HTTP/2, xuống dòng khác hoặc có trạng thái sức khỏe khác.

Cách đọc:

- `HTTP/1.1 200 OK`: dòng trạng thái của HTTP.
- `Content-Type`: kiểu của phần thân đang nhận.
- Dòng trống: ngăn header với phần thân trong cách trình bày HTTP/1.1.
- `{"status":"UP"}`: nội dung JSON của health.

Tùy chọn `-i` đưa cả header vào đầu ra. Vì vậy, **không chuyển thẳng đầu ra của lệnh có `-i` vào bộ phân tích JSON**: dòng `HTTP/1.1 ...` không phải JSON. Muốn xử lý bằng chương trình, hãy tách header và phần thân thành hai luồng hoặc hai tệp.

Khi nhìn một phản hồi không như dự kiến, giữ lại cả ba lớp trên. Chỉ sao chép phần thân có thể khiến bạn bỏ qua một trang đăng nhập, một lỗi thương lượng nội dung hoặc một phản hồi do proxy tạo ra.

## 3. Hiểu đúng `Content-Type` và `Accept`

### 3.1. Header nào nói về dữ liệu nào?

| Header | Nằm ở đâu trong tình huống này? | Câu hỏi nó trả lời |
| --- | --- | --- |
| `Accept` | Yêu cầu gửi tới máy chủ | Bên gọi chấp nhận những kiểu phản hồi nào? |
| `Content-Type` của phản hồi | Phản hồi từ máy chủ | Phần thân vừa nhận có kiểu gì? |
| `Content-Type` của yêu cầu | Yêu cầu có phần thân, chẳng hạn POST | Phần thân đang gửi lên có kiểu gì? |

Gửi `Content-Type: application/json` trong một yêu cầu GET không có phần thân không thay thế cho `Accept`. Nếu mục đích là chọn kiểu phản hồi, hãy dùng `Accept`. Định nghĩa hai header được mô tả tại [Accept](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Accept) và [Content-Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Type).

Ví dụ yêu cầu JSON thông thường:

~~~powershell
curl.exe -sS -i -H "Accept: application/json" "http://localhost:8080/actuator/health"
~~~

Với endpoint hỗ trợ kiểu đó, phản hồi có thể mang `Content-Type: application/json`. Hãy đọc header thực nhận; đừng mặc định rằng máy chủ luôn trả đúng chuỗi media type bạn từng thấy trong một ảnh chụp.

### 3.2. Đọc tên media type của Actuator

Xét:

~~~text
application/vnd.spring-boot.actuator.v3+json
~~~

- `application`: nhóm kiểu nội dung.
- `vnd.spring-boot.actuator.v3`: tên biểu diễn riêng của Actuator, có thông tin phiên bản.
- `+json`: biểu diễn dùng cú pháp JSON.

Nó vẫn là dữ liệu mà bộ phân tích JSON phù hợp có thể đọc. Tuy nhiên, “phân tích được JSON” không có nghĩa là “đúng cấu trúc health” hoặc “đúng cấu trúc metrics”.

**`v3` là phiên bản Actuator API, không phải cách viết tắt của Spring Boot 3.3.** API V3 đã được hỗ trợ từ Spring Boot 2.2. API Java của Boot 3.3 liệt kê cả V2 và V3; đây là hai trục phiên bản cần phân biệt. Xem [ApiVersion của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/ApiVersion.html).

Không tự đổi `v3` thành `v3.3` hoặc `v4` theo số phiên bản thư viện. Nếu một hệ thống cũ cần V2, chỉ yêu cầu biểu diễn tương thích khi endpoint hỗ trợ và đọc đúng hợp đồng V2. Chẳng hạn tài liệu health mô tả cấu trúc V3 và chỉ rõ cách yêu cầu V2; không nên đổi header rồi giả định mọi đường dẫn trường vẫn giữ nguyên. [Hợp đồng health](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html)

### 3.3. Đừng so sánh nguyên chuỗi header một cách máy móc

Header có thể kèm tham số:

~~~text
Content-Type: text/plain;charset=UTF-8
Content-Type: application/openmetrics-text;version=1.0.0;charset=utf-8
~~~

Khi lựa chọn bộ giải mã, tách kiểu chính khỏi tham số; khi xử lý định dạng có phiên bản như OpenMetrics, vẫn phải giữ lại tham số phiên bản để chọn bộ đọc phù hợp.

Một bộ đọc JSON tổng quát có thể nhận `application/json` và các kiểu `application/*+json` được nó hỗ trợ. Sau bước đó vẫn cần kiểm tra cấu trúc riêng của endpoint. Không nên dùng riêng điều kiện “header chứa chữ json” để quyết định một phản hồi là hợp lệ.

## 4. JSON của Actuator không có một lớp bọc chung

Không có quy tắc rằng mọi endpoint đều trả:

~~~json
{
  "success": true,
  "data": {},
  "message": "OK"
}
~~~

Đây chỉ là một lớp bọc do ứng dụng có thể tự thiết kế; không phải hợp đồng chung của Actuator.

Hãy nhận diện điểm bắt đầu của từng cấu trúc:

| Địa chỉ minh họa | Các trường cần nhận diện trước | Dạng cần đọc |
| --- | --- | --- |
| `/actuator` | `_links` | Bản đồ các liên kết khám phá |
| `/actuator/health` | `status`, có thể có `components` | Trạng thái sức khỏe, có thể là cây |
| `/actuator/metrics` | `names` | Mảng tên các chỉ số |
| `/actuator/metrics/{name}` | `name`, `measurements`, `availableTags` | Một chỉ số cùng các phép đo |
| `/actuator/info` | Các khóa do nguồn thông tin đóng góp | Đối tượng thông tin ứng dụng |
| `/actuator/beans` | `contexts` | Bản đồ ngữ cảnh và các bean |

Dạng của `info` phụ thuộc các nguồn thông tin được bật và dữ liệu thực có; một đối tượng `{}` không tự chứng minh rằng endpoint hỏng. Với `beans`, tên ngữ cảnh và tên bean là khóa dữ liệu, không phải một danh sách tên cố định để chép vào chương trình. Xem [info](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/info.html) và [beans](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/beans.html).

Khi gặp JSON mới, xác định lần lượt: đối tượng hay mảng ở gốc, trường bắt buộc, trường tùy chọn, kiểu giá trị và khóa động. Thứ tự các thuộc tính của một đối tượng và cách thụt dòng không phải căn cứ để nhận diện hợp đồng.

## 5. Đọc health: trạng thái tổng hợp và cây thành phần

Phản hồi tối giản có thể chỉ gồm:

~~~json
{
  "status": "UP"
}
~~~

Khi các thành phần và chi tiết được công bố, một ví dụ minh họa là:

~~~json
{
  "status": "UP",
  "components": {
    "inventory": {
      "status": "UP",
      "details": {
        "checkedItems": 12
      }
    }
  }
}
~~~

Trong ví dụ tự dựng này:

- `status` ở gốc là trạng thái tổng hợp.
- `components` là đối tượng chứa các thành phần theo tên.
- `inventory` là tên minh họa của một thành phần, không phải thành phần mặc định của Boot.
- `details.checkedItems` là chi tiết do thành phần đó cung cấp; không thể áp dụng đường dẫn này cho mọi health indicator.

Một thành phần còn có thể chứa `components` lồng nhau. Vì vậy, không nên ép health vào một bảng phẳng có đúng các cột tên cố định. Tài liệu chính thức phân biệt rõ các đường dẫn `components.*.status`, `components.*.components` và `components.*.details`. [Cấu trúc health V3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html)

Nếu không thấy `components` hoặc `details`, trước hết kiểm tra chính sách công bố và quyền truy cập. Các thuộc tính `management.endpoint.health.show-components` và `management.endpoint.health.show-details` ảnh hưởng mức thông tin được thấy. Không suy ra “không có database” chỉ từ việc phản hồi không chứa khóa `db`.

Cần phân biệt **HTTP status** với trường **`status` của health**. Theo ánh xạ mặc định, `DOWN` và `OUT_OF_SERVICE` dẫn tới HTTP `503`; các ánh xạ có thể được tùy chỉnh. Vì thế, một phản hồi `503` vẫn có thể là JSON health hợp lệ, cần được đọc để chẩn đoán. Xem [Health Information và ánh xạ HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

Cách kết luận nên giữ đủ bằng chứng: “HTTP 503; phần thân health báo DOWN” rõ ràng hơn “JSON lỗi”. Với trạng thái tùy chỉnh, cũng không nên giả định rằng mọi chuỗi khác `UP` đều có cùng ý nghĩa.

## 6. Đọc metrics: danh mục khác với giá trị của một chỉ số

### 6.1. Danh mục

~~~powershell
curl.exe -sS -i -H "Accept: application/vnd.spring-boot.actuator.v3+json" "http://localhost:8080/actuator/metrics"
~~~

Ví dụ giản lược:

~~~json
{
  "names": [
    "jvm.memory.used",
    "process.uptime"
  ]
}
~~~

Mảng này cho biết tên nào đang có để truy vấn; nó chưa chứa số đo của từng chỉ số. Danh sách thực tế phụ thuộc ứng dụng và những bộ đo đã đăng ký. [Danh mục metrics](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html)

### 6.2. Một chỉ số

~~~powershell
curl.exe -sS -i -H "Accept: application/vnd.spring-boot.actuator.v3+json" "http://localhost:8080/actuator/metrics/jvm.memory.used"
~~~

Ví dụ minh họa đã rút gọn, số liệu tự chọn:

~~~json
{
  "name": "jvm.memory.used",
  "baseUnit": "bytes",
  "measurements": [
    {
      "statistic": "VALUE",
      "value": 41943040
    }
  ],
  "availableTags": [
    {
      "tag": "area",
      "values": ["heap", "nonheap"]
    }
  ]
}
~~~

Đọc `value` cùng với `statistic` và `baseUnit`. Trong ví dụ này, 41.943.040 byte tương đương 40 MiB. `availableTags` cho biết các chiều có thể dùng để lọc; nó không phải danh sách các số đo độc lập. Số phần tử và loại thống kê thay đổi theo loại chỉ số, vì vậy không luôn lấy phần tử đầu rồi đặt tên nó là “tổng”.

Lọc một chiều bằng tham số `tag`:

~~~powershell
curl.exe -sS -i -H "Accept: application/vnd.spring-boot.actuator.v3+json" "http://localhost:8080/actuator/metrics/jvm.memory.used?tag=area%3Aheap"
~~~

`%3A` là dấu hai chấm được mã hóa trong `area:heap`. Chỉ dùng tag và giá trị có ý nghĩa với chỉ số đang đọc. Không kỳ vọng con số tại thời điểm chạy phải trùng ví dụ; JVM tiếp tục hoạt động trong lúc quan sát.

Endpoint `metrics` phục vụ việc xem và chẩn đoán số đo; nó không phải định dạng thu thập của Prometheus. [Hợp đồng và bộ lọc metrics](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html)

## 7. Đọc `_links`: thông tin điều hướng, không phải số liệu quản trị

Theo cấu hình thông thường, trang khám phá nằm ở `/actuator`. Ví dụ một phần nội dung, chỉ giữ liên kết health:

~~~json
{
  "_links": {
    "health": {
      "href": "http://localhost:8080/actuator/health",
      "templated": false
    }
  }
}
~~~

Ở đây, `health` là tên quan hệ liên kết; `href` là địa chỉ; `templated` cho biết liên kết có phải mẫu URI hay không. Muốn biết sức khỏe, cần gọi địa chỉ health và đọc phản hồi của nó. Sự xuất hiện của liên kết không phải giá trị `UP`.

Khi gặp `templated: true`, hãy hiểu và điền các biến của mẫu trước khi sử dụng; không chép nguyên dấu ngoặc của mẫu vào một URL gọi máy móc.

Trang khám phá có thể bị tắt, và địa chỉ cơ sở có thể thay đổi. Vì vậy, thiếu `_links` ở một URL tự đoán không chứng minh Actuator chưa được cài. Đồng thời, không yêu cầu mọi payload như health hay metrics phải có `_links`. Xem [Hypermedia cho Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.hypermedia).

## 8. Những phản hồi không được đọc bằng bộ phân tích JSON

### 8.1. Thread dump dạng văn bản

Khi endpoint đã được công bố và bạn có quyền, có thể yêu cầu:

~~~powershell
curl.exe -sS -i -H "Accept: text/plain" "http://localhost:8080/actuator/threaddump"
~~~

Đầu ra là văn bản về các luồng khi biểu diễn này được chọn; `Content-Type` có thể là `text/plain;charset=UTF-8`. Cùng endpoint cũng có biểu diễn JSON. Phải chọn cách đọc theo phản hồi thực tế, không theo tên đường dẫn. [Thread dump](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/threaddump.html)

### 8.2. Prometheus và OpenMetrics

`/actuator/prometheus` yêu cầu thư viện đăng ký Prometheus phù hợp và phải được công bố. Dạng mặc định được tài liệu 3.3 mô tả là `text/plain;version=0.0.4`; nó còn hỗ trợ OpenMetrics qua `Accept` thích hợp.

Ví dụ yêu cầu OpenMetrics:

~~~powershell
curl.exe -sS -i -H "Accept: application/openmetrics-text;version=1.0.0;charset=utf-8" "http://localhost:8080/actuator/prometheus"
~~~

Các dòng khai báo và số đo trong định dạng này không phải JSON, dù tên media type bắt đầu bằng `application/`. Không đưa chúng vào bộ phân tích JSON. [Prometheus API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/prometheus.html)

### 8.3. Heap dump dạng nhị phân

`heapdump` trả dữ liệu nhị phân; định dạng phụ thuộc JVM, chẳng hạn HPROF trên HotSpot. Cần lưu và mở bằng công cụ phù hợp. Không chuyển dữ liệu đó thành chuỗi JSON, không in nó như văn bản để suy đoán nội dung. Bài này không cần tạo heap dump để thực hành đọc header. [Heap dump](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/heapdump.html)

Điểm cần giữ là: **địa chỉ thuộc Actuator không đồng nghĩa với phản hồi JSON**. Chọn bộ đọc theo kiểu nội dung và hợp đồng của thao tác.

## 9. Đọc mã HTTP mà không gán nhầm cấu trúc phần thân

| Mã hoặc nhóm mã | Hướng kiểm tra trước khi đọc payload |
| --- | --- |
| `200` | Đọc kiểu nội dung và cấu trúc đúng endpoint; không suy ra mọi thành phần của ứng dụng đều khỏe |
| `204` | Không có phần thân để phân tích; có thể là kết quả hợp lệ của thao tác ghi/xóa |
| `3xx` | Kiểm tra `Location`; có thể đang được chuyển hướng sang nơi khác |
| `401` / `403` | Kiểm tra xác thực hoặc quyền; đừng coi phần thân là payload thành công |
| `404` | Kiểm tra URL, đường dẫn cơ sở, công bố endpoint và tài nguyên con; chưa thể kết luận từ một nguyên nhân duy nhất |
| `406` | Kiểm tra khả năng đáp ứng kiểu phản hồi trong `Accept` |
| `415` | Với yêu cầu có phần thân, kiểm tra kiểu dữ liệu gửi lên |
| `503` từ health | Đọc trạng thái health và xem ánh xạ HTTP đang dùng |

Với endpoint operation, phản hồi ghi/xóa không trả giá trị có thể dùng `204 No Content`; thao tác đọc không có giá trị có thể dùng `404`. Đây là quy tắc mặc định, không thay thế các hành vi riêng như ánh xạ của health. [Trạng thái phản hồi endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.response-status)

`406` liên quan đến biểu diễn phản hồi không đáp ứng thương lượng nội dung; `415` liên quan định dạng nội dung yêu cầu không được hỗ trợ. Hai lỗi không thể được sửa bằng cùng một thao tác đổi header bất kỳ. [406](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/406), [415](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/415)

Phần thân lỗi có thể do bộ xử lý lỗi của ứng dụng, lớp bảo mật hoặc proxy tạo ra. Đừng áp cấu trúc thành công của health lên mọi phản hồi `4xx`/`5xx`, và đừng cam kết rằng tất cả lỗi đều có các trường `timestamp`, `error`, `path`.

Nếu nhận HTML khi chờ JSON, hãy ghi lại mã HTTP, `Content-Type`, `Location` nếu có và URL thực gọi. Không vội kết luận rằng JSON của Actuator sai cú pháp. Khi chẩn đoán chuyển hướng, tránh dùng `-L` ngay từ đầu vì nó có thể che mất phản hồi trung gian cần quan sát.

## 10. Quy trình thực hành: giữ bằng chứng rồi mới trích trường

### Bước 1: Tách header khỏi phần thân

Các lệnh PowerShell sau dùng GET để đọc health và lưu trong thư mục làm việc của người học:

~~~powershell
curl.exe -sS -D health.headers.txt -o health.json -w "HTTP %{http_code}" -H "Accept: application/vnd.spring-boot.actuator.v3+json" "http://localhost:8080/actuator/health"
Get-Content -LiteralPath "./health.headers.txt"
Get-Content -LiteralPath "./health.json" -Raw
~~~

`-D` lưu header; `-o` lưu phần thân; `-w` in mã HTTP cuối cùng của lần gọi. Tên `health.json` do bạn đặt không bảo đảm nội dung là JSON: vẫn phải xem status và header trước.

Nếu không kết nối được, xử lý lỗi kết nối trước khi đọc tệp. Không dùng nội dung còn sót từ một lần chạy trước làm bằng chứng cho lần gọi hiện tại.

### Bước 2: Chỉ phân tích khi phần thân và kiểu nội dung phù hợp

Sau khi xác nhận nhận được JSON health:

~~~powershell
$health = Get-Content -LiteralPath "./health.json" -Raw | ConvertFrom-Json
$health.status
~~~

Với đúng phần thân `{"status":"UP"}` ở mục 2, đầu ra của dòng cuối là:

~~~text
UP
~~~

Đây là kết quả theo dữ liệu ví dụ. Ứng dụng thực có thể báo giá trị khác. Đọc phần thân health hợp lệ vẫn hữu ích khi mã HTTP là `503`; cần ghi nhận cả hai giá trị.

### Bước 3: Không truy cập trường tùy chọn như thể nó luôn tồn tại

Nếu cần xem các thành phần, kiểm tra sự hiện diện trước:

~~~powershell
if ($null -ne $health.components) {
    $health.components.PSObject.Properties |
        ForEach-Object { "{0}: {1}" -f $_.Name, $_.Value.status }
} else {
    "Phan hoi khong cong bo components"
}
~~~

Với JSON minh họa có `inventory` ở mục 5, đầu ra là:

~~~text
inventory: UP
~~~

Với health tối giản, nhánh còn lại chỉ cho biết phản hồi không công bố thành phần; nó không chứng minh mọi thành phần đều vắng mặt. Đoạn lệnh này chỉ liệt kê cấp trực tiếp, chưa duyệt các cây `components` lồng nhau.

### Bước 4: Ghi nhận kết quả bằng một mô tả có căn cứ

Một bản ghi quan sát hữu ích có thể là:

> GET /actuator/health; HTTP 200; media type Actuator V3 JSON; status UP; không có components trong phần thân nhận được.

Một bản ghi khác có thể là:

> GET /actuator/metrics; HTTP 200; có mảng names; chưa truy vấn giá trị của từng chỉ số.

Các câu này tách điều đã thấy khỏi điều chưa kiểm tra. Chúng giúp người khác tái hiện phép quan sát mà không phải đoán bạn đã gọi endpoint nào.

## 11. Lỗi phổ biến và cách tự kiểm tra

- **Chỉ chấp nhận đúng chuỗi `application/json`:** dễ loại nhầm Actuator JSON có hậu tố `+json`. Xem xét media type được hỗ trợ, rồi kiểm tra cấu trúc.
- **Dùng một lớp dữ liệu có trường `data` cho mọi endpoint:** sẽ trích sai ngay khi gốc thực tế là `status` hoặc `names`.
- **Coi trường bị thiếu, `null`, `{}` và `[]` là một:** đây là các trạng thái dữ liệu khác nhau. Xác định ý nghĩa theo trường và endpoint cụ thể.
- **Lấy tên thành phần, context, bean hoặc tag từ ví dụ làm hằng số:** sẽ dễ hỏng khi môi trường hoặc cấu hình thay đổi.
- **Phân tích header như JSON:** thường xảy ra khi nối `curl -i` với bộ đọc JSON. Tách hai phần trước.
- **Coi mọi giá trị metrics đều là byte hoặc phần trăm:** đọc đơn vị và loại thống kê; không tự gán đơn vị.
- **Đòi JSON từ mọi endpoint:** kiểm tra các biểu diễn văn bản, OpenMetrics và nhị phân.
- **Bỏ phần thân chỉ vì health trả 503:** có thể bỏ mất bằng chứng chẩn đoán có ích.
- **Coi phản hồi ví dụ là kết quả cố định:** dữ liệu vận hành thay đổi; chỉ khẳng định đầu ra chính xác khi đầu vào đã được xác định.

## 12. Bài tập đọc phản hồi

**Tình huống 1.** Một lần gọi health trả HTTP 503, `Content-Type` là Actuator V3 JSON và phần thân là:

~~~json
{
  "status": "DOWN"
}
~~~

Có phải bộ phân tích JSON bị lỗi không?

**Gợi ý trả lời:** Không có bằng chứng về lỗi JSON trong dữ liệu này. Đây là một phần thân health hợp lệ; cần ghi nhận trạng thái DOWN và mã 503, rồi kiểm tra nguyên nhân bằng thông tin được phép thấy.

**Tình huống 2.** `/actuator/metrics` trả `{"names":["process.uptime"]}`. Có thể báo thời gian hoạt động bằng cách đếm phần tử trong `names` không?

**Gợi ý trả lời:** Không. Đó là tên chỉ số. Cần truy vấn `/actuator/metrics/process.uptime`, rồi đọc các phép đo và đơn vị thực nhận.

**Tình huống 3.** Một công cụ báo “không tìm thấy data.status”, trong khi phần thân là `{"status":"UP"}`.

**Gợi ý trả lời:** Công cụ đang áp sai cấu trúc lớp bọc. Trong phần thân này, `status` nằm ngay ở gốc.

**Tình huống 4.** Hai phản hồi thread dump lần lượt có kiểu JSON và `text/plain`. Có thể dùng chung bộ phân tích JSON không?

**Gợi ý trả lời:** Không. Chọn bộ đọc theo media type thực nhận; nếu cần một biểu diễn cụ thể, gửi `Accept` tương ứng mà endpoint hỗ trợ.

Sau các bài tập, hãy tự đọc một phản hồi theo thứ tự: **URL và thao tác → mã HTTP → kiểu nội dung → cấu trúc riêng → ý nghĩa của dữ liệu**. Chỉ kết luận trong phạm vi bằng chứng vừa quan sát.

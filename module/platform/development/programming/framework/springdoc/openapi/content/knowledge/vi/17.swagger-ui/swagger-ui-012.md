# Request interceptor, response interceptor và giới hạn tùy biến

## 1. Interceptor trong Swagger UI giải quyết việc gì?

Swagger UI cho phép người dùng đọc OpenAPI document và gửi thử request ngay trên trình duyệt. Trong một số dự án, nhóm phát triển cần bổ sung hành vi ở phía giao diện tài liệu, chẳng hạn:

- Thêm header nhận diện request được gửi từ Swagger UI.
- Gắn access token do cơ chế đăng nhập của cổng developer cung cấp.
- Ghi nhận status code của response để hỗ trợ chẩn đoán.
- Chuẩn hóa hoặc bổ sung thông tin hiển thị trong giao diện thử API.
- Thực hiện một bước xử lý chung trước khi Swagger UI gửi request hoặc sau khi nhận response.

Swagger UI cung cấp hai callback JavaScript dành cho các tình huống đó:

- **requestInterceptor** nhận request mà Swagger UI chuẩn bị gửi, cho phép đọc hoặc chỉnh sửa request trước khi gửi.
- **responseInterceptor** nhận response sau khi request hoàn tất ở tầng HTTP, cho phép đọc hoặc chỉnh sửa đối tượng response trước khi giao diện sử dụng nó.

Đây là các hook chạy trong trình duyệt của người xem tài liệu. Chúng không thay đổi controller Spring Boot, không thay thế Spring Security và không tự sửa hợp đồng OpenAPI được Springdoc sinh ra.

Với Springdoc OpenAPI, việc cấu hình endpoint Swagger UI và việc cài callback interceptor là hai việc khác nhau. Thuộc tính Springdoc có thể cấu hình đường dẫn UI hoặc URL tải OpenAPI document; callback là hàm JavaScript nên phải được cung cấp trong phần khởi tạo Swagger UI hoặc qua cơ chế tùy biến giao diện tương ứng.

## 2. requestInterceptor hoạt động như thế nào?

requestInterceptor là hàm nhận đối tượng request do Swagger Client chuẩn bị gửi. Hàm có thể kiểm tra method, URL, headers hoặc body, sau đó trả lại request đã chỉnh sửa.

Ví dụ, thêm một header nhận diện thao tác thử API:

~~~javascript
const requestInterceptor = (request) => {
  request.headers = request.headers || {};
  request.headers["X-Request-Source"] = "swagger-ui";
  return request;
};
~~~

Khi callback được cấu hình trong Swagger UI, các request phù hợp sẽ mang thêm header X-Request-Source. Backend có thể dùng header này cho mục đích chẩn đoán hoặc phân loại lưu lượng nếu chính sách hệ thống cho phép.

Không nên xem header do trình duyệt gửi là bằng chứng xác thực đáng tin cậy. Bất kỳ client HTTP nào cũng có thể tự thêm cùng header. Nếu cần xác định danh tính hoặc quyền, hãy dùng cơ chế authentication và authorization thực sự.

requestInterceptor cũng có thể thêm một header theo điều kiện:

~~~javascript
const requestInterceptor = (request) => {
  request.headers = request.headers || {};

  if (request.method === "GET") {
    request.headers["X-Read-Source"] = "api-docs";
  }

  return request;
};
~~~

Cần kiểm tra chữ hoa/chữ thường của method và cách thư viện chuẩn hóa request ở phiên bản Swagger UI đang dùng. Nếu logic phụ thuộc URL, nên so khớp theo origin/path đã xác định thay vì gắn header nhạy cảm vào mọi địa chỉ.

## 3. Đưa interceptor vào Swagger UI initialization

Swagger UI nhận cấu hình thông qua đối tượng truyền cho hàm SwaggerUIBundle. requestInterceptor và responseInterceptor là các callback JavaScript trong đối tượng cấu hình đó.

Ví dụ phần khởi tạo:

~~~javascript
const ui = SwaggerUIBundle({
  url: "/v3/api-docs",
  dom_id: "#swagger-ui",
  deepLinking: true,

  requestInterceptor: (request) => {
    request.headers = request.headers || {};
    request.headers["X-Request-Source"] = "swagger-ui";
    return request;
  },

  responseInterceptor: (response) => {
    return response;
  }
});

window.ui = ui;
~~~

Đây là phần cấu hình minh họa cần đặt trong JavaScript khởi tạo Swagger UI. Nó không phải toàn bộ file index.html; một trang tùy biến thực tế còn cần nạp đúng CSS, JavaScript bundle, preset, plugin và các thiết lập giao diện mà ứng dụng đang sử dụng.

Khi tích hợp vào Springdoc, cần giữ lại các giá trị cấu hình do trang mặc định hoặc swagger-config cung cấp. Nếu thay toàn bộ trang khởi tạo, có thể vô tình làm mất URL tài liệu, OAuth redirect, preset hoặc các thiết lập khác.

## 4. Cấu hình Springdoc và callback JavaScript là hai lớp khác nhau

Springdoc có thể cấu hình đường dẫn Swagger UI và URL tài liệu bằng application.yml:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
    config-url: /v3/api-docs/swagger-config
~~~

Trong ví dụ:

- path thay đổi đường dẫn giao diện Swagger UI.
- config-url chỉ định endpoint cấu hình Swagger UI.
- swagger-config chứa cấu hình dạng dữ liệu mà Springdoc cung cấp cho UI.

Các thuộc tính trên không tự khai báo được một hàm JavaScript. JSON không thể biểu diễn function theo cách mà Swagger UI có thể gọi như callback. Vì vậy, không thể chỉ đặt tên hàm requestInterceptor dưới dạng chuỗi trong application.yml rồi kỳ vọng Swagger UI thực thi hàm đó.

Để cài interceptor, ứng dụng cần cung cấp callback trong JavaScript khởi tạo Swagger UI. Tùy phiên bản Springdoc, có thể dùng trang index.html tùy biến hoặc extension point để biến đổi trang được tạo. Cần đối chiếu cách tùy biến với phiên bản springdoc-openapi đang sử dụng.

Đừng nhầm các thuộc tính springdoc.swagger-ui.path, springdoc.swagger-ui.config-url với requestInterceptor. Hai thuộc tính đầu điều khiển nơi UI tải trang/cấu hình; interceptor điều khiển hành vi của Swagger Client trong trình duyệt.

## 5. Tùy biến index.html mà vẫn giữ cấu hình mặc định

Một cách phổ biến để cung cấp callback là dùng trang Swagger UI tùy biến và truyền interceptor vào SwaggerUIBundle. Khi thực hiện:

1. Xác định trang Swagger UI đang được Springdoc cung cấp ở phiên bản hiện tại.
2. Dùng cơ chế override hoặc transformer được phiên bản Springdoc hỗ trợ.
3. Giữ đúng đường dẫn tới swagger-ui-bundle.js và stylesheet.
4. Giữ cấu hình URL hoặc configUrl để tải OpenAPI document.
5. Bổ sung requestInterceptor và responseInterceptor.
6. Kiểm tra OAuth redirect, group selector, deep linking và Try it out sau khi thay đổi.

Không nên sao chép một index.html từ phiên bản Swagger UI khác rồi dùng lâu dài mà không kiểm tra. Tài nguyên tĩnh và cách khởi tạo có thể thay đổi khi nâng cấp springdoc-openapi hoặc swagger-ui.

Nếu chỉ cần đổi title, đường dẫn tài liệu hoặc các tùy chọn được Springdoc hỗ trợ trực tiếp, hãy dùng application properties. Chỉ override trang khởi tạo khi cần JavaScript callback hoặc hành vi giao diện mà thuộc tính cấu hình không biểu diễn được.

## 6. responseInterceptor hoạt động như thế nào?

responseInterceptor nhận đối tượng response sau khi Swagger Client nhận kết quả HTTP. Callback có thể đọc status, headers hoặc nội dung response, sau đó trả lại response để Swagger UI tiếp tục xử lý.

Ví dụ ghi nhận status code:

~~~javascript
const responseInterceptor = (response) => {
  if (response.status >= 400) {
    console.info("Swagger UI received an HTTP error", response.status);
  }

  return response;
};
~~~

Callback này chỉ ghi nhận status code. Nó không thay đổi response mà server đã gửi và cũng không tự xử lý mọi lỗi mạng. Nếu trình duyệt không nhận được HTTP response do DNS, TLS, CORS hoặc kết nối bị ngắt, có thể không có response object để callback xử lý.

Có thể đọc một số header phục vụ chẩn đoán:

~~~javascript
const responseInterceptor = (response) => {
  const traceId = response.headers?.["x-trace-id"];

  if (traceId) {
    console.info("API trace:", traceId);
  }

  return response;
};
~~~

Tên header trong đối tượng JavaScript phụ thuộc cách Swagger Client chuẩn hóa headers. Hãy kiểm tra response object thực tế trên phiên bản đang dùng trước khi phụ thuộc vào một cách viết cụ thể.

Không ghi response body chứa dữ liệu cá nhân, token, thông tin tài khoản hoặc dữ liệu nghiệp vụ nhạy cảm vào console hay hệ thống analytics.

## 7. Thay đổi response object có ảnh hưởng gì?

responseInterceptor có thể trả về response đã chỉnh sửa. Vì đối tượng này tiếp tục được Swagger UI sử dụng, việc thay đổi status, headers hoặc body có thể ảnh hưởng nội dung hiển thị trong giao diện.

Ví dụ bổ sung một trường client-side để hỗ trợ debug:

~~~javascript
const responseInterceptor = (response) => {
  response.swaggerUiObserved = true;
  return response;
};
~~~

Trường swaggerUiObserved chỉ tồn tại trong đối tượng response ở trình duyệt. Nó không được ghi ngược về server và không xuất hiện trong HTTP response gốc.

Nếu thay đổi body, cần hiểu chính xác Swagger UI sử dụng những thuộc tính nào của response. Thay đổi cấu trúc có thể khiến phần hiển thị response không còn phản ánh payload thật. Với giao diện dùng để kiểm thử API, nên giữ nguyên response trừ khi có lý do rõ ràng để chuyển đổi.

Interceptor cũng không nên được dùng để che giấu status lỗi hoặc thay response lỗi thành thành công. Điều đó có thể khiến người dùng hiểu sai hành vi backend.

## 8. Dùng requestInterceptor để thêm access token

Có thể dùng requestInterceptor để thêm token do ứng dụng cấp, nhưng nên ưu tiên cơ chế Authorize và OAuth của Swagger UI khi API đã khai báo security scheme phù hợp.

Nếu có một token provider do cổng đăng nhập của ứng dụng cung cấp, ví dụ:

~~~javascript
const requestInterceptor = (request) => {
  request.headers = request.headers || {};

  const token = window.appAuth?.getAccessToken?.();

  if (token && !request.headers.Authorization) {
    request.headers.Authorization = "Bearer " + token;
  }

  return request;
};
~~~

Ví dụ giả định ứng dụng đã cung cấp window.appAuth và phương thức getAccessToken. Đây không phải API có sẵn của Swagger UI hoặc Springdoc; dự án phải tự tích hợp token provider.

Một số nguyên tắc:

- Không hard-code access token hoặc refresh token trong file JavaScript.
- Không đưa token vào URL query string.
- Không ghi Authorization header vào log.
- Không ghi token vào vendor extension hoặc OpenAPI document.
- Không ghi đè Authorization đã được người dùng cấp qua nút Authorize nếu không có chủ đích.
- Chỉ gửi token đến origin API đã được tin cậy.
- Kiểm tra token hết hạn và hành vi đăng nhập lại.

Nếu dùng OAuth2, hãy cấu hình security scheme và OAuth redirect theo hướng dẫn Swagger UI/Springdoc của phiên bản đang chạy. Interceptor chỉ là lớp xử lý request ở giao diện, không thay thế quy trình cấp, refresh và thu hồi token.

## 9. Không gắn header nhạy cảm vào mọi request

Một requestInterceptor toàn cục có thể được gọi cho nhiều request do Swagger UI tạo ra. Tùy luồng tải và phiên bản, các request đó có thể bao gồm việc tải tài liệu hoặc gọi operation. Vì vậy, không nên giả định callback chỉ áp dụng cho một API path duy nhất.

Nếu cần thêm token hoặc header nội bộ, hãy giới hạn theo origin/path:

~~~javascript
const requestInterceptor = (request) => {
  const target = new URL(request.url, window.location.origin);
  const apiOrigin = "https://api.example.com";

  if (target.origin === apiOrigin &&
      target.pathname.startsWith("/api/")) {
    request.headers = request.headers || {};
    request.headers["X-Request-Source"] = "swagger-ui";
  }

  return request;
};
~~~

Ví dụ này chỉ thêm header khi URL thuộc origin và path đã chọn. Hãy điều chỉnh apiOrigin và prefix theo môi trường thực tế. Nếu tài liệu được tải từ một host nhưng operation được gọi tới host khác, việc giới hạn origin giúp tránh gửi nhầm header.

Không nên thêm Authorization vào request tải OpenAPI document nếu endpoint tài liệu có cơ chế truy cập riêng hoặc dùng một credential khác. Tách chính sách bảo vệ tài liệu khỏi chính sách gọi API nghiệp vụ.

## 10. CORS khi interceptor thêm request header

Khi Swagger UI chạy trên origin khác với API, trình duyệt áp dụng Cross-Origin Resource Sharing (CORS). Việc requestInterceptor thêm header tùy chỉnh có thể làm request phát sinh preflight OPTIONS.

Ví dụ header X-Request-Source hoặc Authorization có thể khiến trình duyệt gửi preflight để hỏi server xem method và header có được phép hay không.

Backend cần cấu hình CORS phù hợp:

- Cho phép origin của trang Swagger UI.
- Cho phép method mà client cần gọi.
- Cho phép các request header như Authorization, Content-Type và header tùy chỉnh.
- Nếu dùng cookie hoặc credential, cấu hình allow-credentials và origin theo quy tắc trình duyệt.
- Chỉ expose response header mà JavaScript cần đọc, chẳng hạn X-Trace-Id.

Nếu JavaScript không đọc được response header dù header có trong network response, kiểm tra Access-Control-Expose-Headers. Nếu preflight thất bại, interceptor không thể tự sửa CORS vì chính sách này do browser và server thực thi.

Không dùng allow-origin wildcard cùng credentials khi cấu hình CORS yêu cầu credential. Hãy cấu hình origin cụ thể theo môi trường.

## 11. Interceptor không phải middleware của backend

RequestInterceptor và responseInterceptor chỉ chạy trong trình duyệt có Swagger UI. Chúng không chạy khi:

- Mobile app gọi API.
- Một backend khác gọi API.
- Người dùng gọi API bằng curl hoặc Postman.
- Một ứng dụng frontend không sử dụng Swagger UI gửi request.
- Spring Boot xử lý request trực tiếp từ client khác.

Do đó, không đặt logic nghiệp vụ, kiểm tra quyền hoặc validation bắt buộc chỉ trong interceptor. Mọi quy tắc cần bảo đảm cho tất cả client phải được thực thi ở backend.

Tương tự, responseInterceptor không sửa response mà backend gửi cho các client khác. Nó chỉ thay đổi cách Swagger UI nhận hoặc xử lý response trong phiên trình duyệt đó.

Có thể dùng interceptor cho telemetry giao diện hoặc header hỗ trợ debug, nhưng dữ liệu từ browser không được xem là nguồn xác thực đáng tin cậy.

## 12. Giới hạn khi xử lý lỗi và response

responseInterceptor phù hợp để quan sát HTTP response mà Swagger Client nhận được. Nó không thay thế các cơ chế sau:

- Exception handler trong Spring MVC.
- Error response chuẩn hóa của backend.
- Xử lý CORS.
- Retry policy ở client.
- Authentication và authorization.
- Network error handling ở tầng trình duyệt.
- Contract testing của OpenAPI document.

Một số lỗi xảy ra trước khi có response HTTP, ví dụ DNS lookup thất bại, TLS handshake lỗi, request bị browser chặn bởi CORS hoặc kết nối timeout. Những trường hợp này có thể không cung cấp response object cho responseInterceptor.

Đối với HTTP 400, 401, 403, 404 hoặc 500, server đã trả response nên interceptor có thể quan sát status và các dữ liệu response được Swagger Client cung cấp. Tuy nhiên, việc hiển thị chi tiết còn phụ thuộc cách Swagger UI xử lý response và cấu hình của phiên bản.

Không nên dùng responseInterceptor để biến lỗi 401 thành 200 hoặc xóa nội dung lỗi nhằm làm giao diện trông thành công. Hãy giữ nguyên tín hiệu lỗi để người thử API có thể đánh giá đúng kết quả.

## 13. Ví dụ kết hợp hai interceptor

Ví dụ dưới đây thêm một header nhận diện vào request và chỉ ghi nhận status của response:

~~~javascript
const ui = SwaggerUIBundle({
  url: "/v3/api-docs",
  dom_id: "#swagger-ui",
  deepLinking: true,

  requestInterceptor: (request) => {
    const target = new URL(request.url, window.location.origin);

    if (target.pathname.startsWith("/api/")) {
      request.headers = request.headers || {};
      request.headers["X-Request-Source"] = "swagger-ui";
    }

    return request;
  },

  responseInterceptor: (response) => {
    if (response.status >= 400) {
      console.info("API returned status", response.status);
    }

    return response;
  }
});

window.ui = ui;
~~~

Trong ví dụ:

- Request interceptor chỉ thêm header cho path bắt đầu bằng /api/.
- Response interceptor ghi nhận status lỗi.
- Cả hai callback đều trả lại đối tượng đầu vào.
- Không có token hoặc dữ liệu nhạy cảm được ghi vào console.

Khi đưa vào dự án, cần giữ lại các option mặc định hoặc cần thiết như presets, plugins, layout, OAuth configuration và configUrl. Ví dụ trên minh họa callback, không phải một cấu hình thay thế đầy đủ cho mọi phiên bản Swagger UI.

## 14. Các lỗi thường gặp khi cấu hình interceptor

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| requestInterceptor không chạy | Callback chưa được truyền vào SwaggerUIBundle hoặc trang UI tùy biến chưa được sử dụng |
| responseInterceptor không chạy | Request không tạo được HTTP response, callback chưa đăng ký hoặc luồng gọi không đi qua Swagger Client như dự kiến |
| YAML không nhận function | Cấu hình Springdoc dạng dữ liệu không thể biểu diễn callback JavaScript |
| Header không tới backend | CORS preflight thất bại hoặc request bị giới hạn bởi browser |
| Token bị gửi tới host ngoài dự kiến | Interceptor không giới hạn origin/path |
| Authorize hoạt động nhưng token bị ghi đè | Request interceptor ghi đè Authorization header đã có |
| Swagger UI không tải được tài liệu | custom index sai URL bundle, configUrl hoặc đường dẫn OpenAPI |
| Group selector biến mất | Trang tùy biến bỏ cấu hình swagger-config hoặc option cần thiết |
| Response hiển thị khác payload server | responseInterceptor đã thay đổi body/status hoặc cấu hình client biến đổi response |
| Không thấy responseInterceptor khi mạng lỗi | Không có HTTP response object để callback xử lý |
| Swagger UI hoạt động ở local nhưng lỗi ở staging | Origin, CORS, context path hoặc server URL khác môi trường |
| Nâng cấp Springdoc làm giao diện lỗi | Trang index tùy biến phụ thuộc tài nguyên hoặc cấu trúc khởi tạo của phiên bản cũ |

Khi điều tra, mở Developer Tools của trình duyệt và kiểm tra Console, Network, request URL, preflight OPTIONS, response headers và nội dung swagger-config. Xác minh callback đã được nạp trước khi kết luận lỗi nằm ở backend.

## 15. Kiểm thử interceptor trong trình duyệt

Có thể kiểm tra theo từng lớp:

**Kiểm tra request:**

1. Mở Swagger UI và chọn operation cần thử.
2. Thực hiện Try it out.
3. Mở Network tab.
4. Kiểm tra URL, method và header được gửi.
5. Xác nhận interceptor chỉ thay đổi request thuộc phạm vi dự kiến.
6. Kiểm tra Authorization không bị ghi đè hoặc gửi tới origin khác.

**Kiểm tra response:**

1. Gọi operation trả 2xx.
2. Gọi operation trả 4xx hoặc 5xx.
3. Kiểm tra responseInterceptor nhận status.
4. So sánh response hiển thị với response trong Network tab.
5. Xác nhận body và header không bị thay đổi ngoài chủ đích.

**Kiểm tra tình huống biên:**

- API cùng origin và khác origin.
- CORS preflight thành công và thất bại.
- Token thiếu hoặc hết hạn.
- Endpoint public và endpoint yêu cầu xác thực.
- Tải OpenAPI document và gọi operation.
- Timeout hoặc mất kết nối.
- Swagger UI group selector và OAuth redirect.

Không chỉ kiểm tra console. Hãy đối chiếu Network tab vì console log có thể bỏ qua chi tiết header, preflight và response thực tế.

## 16. Nguyên tắc sử dụng requestInterceptor và responseInterceptor

Khi tùy biến Swagger UI trong ứng dụng Spring Boot dùng Springdoc OpenAPI, hãy giữ các nguyên tắc:

1. Dùng requestInterceptor cho thay đổi request phía trình duyệt.
2. Dùng responseInterceptor để quan sát hoặc biến đổi response object trong Swagger UI.
3. Đưa callback vào JavaScript khởi tạo Swagger UI; không coi YAML/JSON config là nơi chứa function.
4. Giữ lại cấu hình mặc định cần thiết khi tùy biến index page.
5. Giới hạn header và token theo origin/path tin cậy.
6. Ưu tiên Authorize/OAuth flow cho xác thực thay vì hard-code token.
7. Cấu hình CORS ở backend khi interceptor thêm header cross-origin.
8. Không dùng interceptor thay thế authorization, validation hoặc exception handling ở server.
9. Không log token, dữ liệu cá nhân hoặc response body nhạy cảm.
10. Kiểm tra request/response trong Network tab sau mỗi lần thay đổi.

requestInterceptor và responseInterceptor giúp điều chỉnh trải nghiệm thử API trong Swagger UI. Chúng chạy ở trình duyệt và chỉ tác động đến request/response mà giao diện tài liệu xử lý. Khi callback được cấu hình đúng, giới hạn theo origin rõ ràng và backend vẫn thực thi đầy đủ bảo mật, validation cùng CORS, nhóm phát triển có thể bổ sung khả năng quan sát và hỗ trợ tích hợp mà không làm sai lệch hợp đồng API công khai.


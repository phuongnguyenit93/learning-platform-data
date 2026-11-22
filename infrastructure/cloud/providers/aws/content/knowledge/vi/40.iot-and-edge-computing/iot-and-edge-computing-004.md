# Device Shadow và đồng bộ trạng thái thiết bị

AWS IoT Device Shadow là dịch vụ của AWS IoT Core lưu trạng thái thiết bị dưới dạng tài liệu JSON trên cloud. Ứng dụng có thể đọc trạng thái gần nhất của thiết bị và ghi trạng thái mong muốn ngay cả khi thiết bị đang mất kết nối. Khi thiết bị kết nối lại, nó đọc phần chênh lệch giữa trạng thái mong muốn và trạng thái đã báo cáo, thực hiện thay đổi phù hợp rồi cập nhật trạng thái thực tế.

Device Shadow giúp tách vòng đời của ứng dụng khỏi kết nối mạng của thiết bị. Một dashboard có thể yêu cầu thermostat đặt nhiệt độ 24°C mà không cần thiết bị đang online; thiết bị có thể nhận yêu cầu sau khi kết nối lại. AWS IoT lưu trạng thái hiện tại và phát thông báo khi có thay đổi. Thiết bị và ứng dụng vẫn phải phối hợp để thực hiện, xác nhận và xử lý xung đột.

Trong hệ sinh thái AWS, Device Shadow thuộc AWS IoT Core. Dịch vụ kết hợp Thing Registry, MQTT, X.509 certificate, IoT policies, IAM, AWS IoT Rules Engine, Lambda và Fleet Indexing. Bài học tập trung vào cách thiết kế mô hình desired/reported, đồng bộ hai chiều, quản lý phiên bản, phân tách named shadow, bảo mật topic và vận hành đội thiết bị ở quy mô lớn.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích Device Shadow và vai trò của nó trong kiến trúc IoT.
- Phân biệt Thing, device, shadow document và MQTT message.
- Giải thích ý nghĩa của desired, reported và delta.
- Thiết kế luồng đồng bộ khi thiết bị online, offline và reconnect.
- Đọc các trường metadata, timestamp, version và clientToken.
- Cập nhật shadow bằng MQTT reserved topics hoặc HTTPS API.
- Phân biệt classic shadow với named shadow.
- Xử lý update conflict, message đến sai thứ tự và duplicate notification.
- Thiết kế quy ước ownership giữa cloud application và firmware.
- Bảo vệ shadow bằng X.509 certificate, AWS IoT policy và IAM least privilege.
- Kết hợp Device Shadow với IoT Rules Engine, Fleet Indexing và Device Management Jobs.
- Đánh giá giới hạn payload, request rate và số request đang chờ.
- Xây dựng quy trình kiểm tra, giám sát và khắc phục lỗi đồng bộ.

## 2. Device Shadow giải quyết vấn đề gì?

Một thiết bị IoT có thể kết nối không liên tục vì:
- Mất Wi-Fi, mạng di động hoặc Internet.
- Thiết bị ở vùng phủ sóng yếu.
- Gateway hoặc router khởi động lại.
- Thiết bị tiết kiệm năng lượng và chỉ thức dậy theo chu kỳ.
- Firmware đang cập nhật hoặc thiết bị đang reboot.
- Kết nối MQTT bị ngắt do lỗi mạng hoặc bảo trì.

Nếu ứng dụng chỉ gửi lệnh trực tiếp đến MQTT topic khi thiết bị đang offline, thiết bị có thể không nhận được yêu cầu đó. Ứng dụng phải tự quản lý trạng thái kết nối, retry, lưu lệnh, đồng bộ lại và xử lý xung đột.

Device Shadow cung cấp một nơi lưu trạng thái dùng chung:
- Ứng dụng ghi trạng thái mong muốn lên cloud.
- AWS IoT lưu trạng thái đó trong shadow document.
- Thiết bị có thể đọc shadow khi reconnect.
- AWS IoT tính toán phần khác biệt giữa desired và reported.
- Thiết bị thực hiện thay đổi và báo cáo trạng thái thực tế.

Ví dụ, một bộ điều khiển nhiệt độ đang offline. Người dùng thay đổi nhiệt độ mục tiêu từ 26°C xuống 24°C. Ứng dụng ghi desired.setpoint = 24 vào shadow. Khi thiết bị reconnect, nó đọc delta, điều chỉnh bộ điều khiển và ghi reported.setpoint = 24 sau khi xác nhận trạng thái.

Device Shadow hữu ích khi ứng dụng cần biết **trạng thái mới nhất mà cloud mong muốn và trạng thái gần nhất mà thiết bị báo cáo**. Nó không phải hệ thống lưu lịch sử mọi lệnh, hàng đợi công việc hay kho telemetry time-series.

## 3. Thing, thiết bị và shadow document

Trong AWS IoT Core:
- **Thing** là đối tượng logic đại diện cho một thiết bị hoặc tài sản trong AWS IoT Registry.
- **Device** là phần cứng/firmware thực tế, kết nối đến AWS IoT Core.
- **Shadow** là tài liệu JSON được AWS IoT lưu cho Thing.
- **Shadow document** là biểu diễn trạng thái gồm desired/reported và metadata.
- **MQTT client** là thành phần trên thiết bị hoặc ứng dụng dùng publish/subscribe với AWS IoT Core.

Một Thing có thể gắn certificate và policy để xác thực, phân quyền kết nối. Thing Registry lưu thông tin nhận dạng và thuộc tính của tài sản. Shadow là một tài nguyên trạng thái riêng; nó không tự động đồng bộ với mọi thuộc tính của Thing Registry hay nội dung MQTT tùy ý.

Một Thing không có shadow cho đến khi shadow được tạo. Có thể tạo bằng AWS IoT console, MQTT update hoặc Device Shadow API. Với classic shadow, một request get trước khi shadow được tạo sẽ nhận get/rejected; thiết bị có thể tạo shadow bằng cách gửi update đầu tiên với phần reported. Với named shadow, cần tạo named shadow tương ứng trước khi đọc.

Một Thing có thể đồng thời có classic shadow và nhiều named shadow. Mỗi shadow độc lập với các shadow khác. Nếu một thiết bị dùng nhiều shadow, firmware cần xác định rõ nguồn dữ liệu và cách đồng bộ từng shadow để tránh báo cáo các trạng thái mâu thuẫn.

## 4. Ba phần trạng thái: desired, reported và delta

Đây là mô hình cốt lõi của Device Shadow.

| Phần | Ai thường cập nhật | Ý nghĩa |
|---|---|---|
| desired | Ứng dụng cloud, backend hoặc người vận hành | Trạng thái mà hệ thống muốn thiết bị đạt được |
| reported | Firmware/thiết bị | Trạng thái mà thiết bị đang báo cáo |
| delta | AWS IoT tính toán | Các thuộc tính desired khác với reported |

Ví dụ shadow document:

~~~json
{
  "state": {
    "desired": {
      "power": "ON",
      "setpoint": 24,
      "mode": "COOL"
    },
    "reported": {
      "power": "ON",
      "setpoint": 26,
      "mode": "COOL"
    },
    "delta": {
      "setpoint": 24
    }
  },
  "version": 18,
  "timestamp": 1795161600
}
~~~

Trong ví dụ này:
- Cloud muốn nhiệt độ mục tiêu là 24°C.
- Thiết bị đang báo cáo 26°C.
- Các thuộc tính power và mode đã khớp.
- AWS IoT chỉ đưa setpoint vào delta.

Delta là trạng thái ảo được tính từ desired và reported. Client không gửi delta để cập nhật shadow. Khi hai phần desired/reported khớp nhau, delta tương ứng biến mất.

### 4.1 Quy ước ownership

Một quy ước dễ vận hành là:

- Cloud application chỉ cập nhật desired khi yêu cầu thiết bị thay đổi.
- Firmware chỉ cập nhật reported khi quan sát hoặc thực hiện được trạng thái thực tế.
- AWS IoT tính delta.
- Backend đọc reported để hiển thị trạng thái thiết bị và đánh giá việc thực hiện yêu cầu.

Tránh để nhiều thành phần cùng ghi một thuộc tính vào cả desired và reported mà không có quy ước rõ ràng. Ví dụ, backend không nên ghi reported.temperature như thể đó là cảm biến thực tế nếu nó không nhận được dữ liệu từ thiết bị.

### 4.2 Delta không phải command queue

Delta chỉ biểu diễn phần khác biệt hiện tại. Nếu cloud cập nhật desired nhiều lần khi thiết bị offline, shadow giữ trạng thái mong muốn mới nhất. Các giá trị trung gian không tạo thành danh sách lệnh cần chạy lần lượt.

Ví dụ:
1. Cloud đặt setpoint = 24.
2. Sau đó cloud đổi thành 22.
3. Thiết bị reconnect và đọc shadow.

Thiết bị cần đồng bộ về 22°C. Không có yêu cầu mặc định rằng thiết bị phải thực hiện lần lượt 24°C rồi 22°C.

Nếu mỗi lệnh đều phải được thực thi đúng một lần, có trạng thái tiến trình, deadline, retry và kết quả riêng, hãy dùng AWS IoT Device Management Jobs hoặc một hệ thống command/job phù hợp.

## 5. Cấu trúc shadow document

Một request document cơ bản:

~~~json
{
  "state": {
    "desired": {
      "power": "ON",
      "setpoint": 24
    }
  },
  "clientToken": "web-req-00042",
  "version": 17
}
~~~

Trong phần state, service lưu các field thuộc desired và reported. Những field ứng dụng tự thêm bên ngoài hai phần này không được lưu như state. Trong thiết kế thông thường, mỗi request chỉ cập nhật desired hoặc reported để giữ rõ ownership giữa cloud và firmware.

Các thuộc tính quan trọng:

| Thuộc tính | Mục đích |
|---|---|
| state.desired | Giá trị mong muốn từ cloud |
| state.reported | Giá trị thiết bị báo cáo |
| state.delta | Phần khác biệt do service tính toán trong response |
| metadata | Timestamp theo từng thuộc tính trong state |
| timestamp | Thời điểm AWS IoT tạo response document |
| version | Phiên bản shadow document |
| clientToken | Giá trị giúp liên kết request với response |

metadata được AWS IoT sinh tự động. Nó chứa timestamp của từng thuộc tính trong desired/reported, giúp client xác định thuộc tính đã được cập nhật khi nào. Metadata không tính vào giới hạn kích thước state document.

timestamp trong response là thời điểm AWS IoT tạo thông điệp, không phải đồng hồ đo chính xác thời điểm thiết bị thực hiện hành động. Khi cần thời gian đo tại thiết bị, firmware nên báo cáo field riêng như lastMeasuredAt hoặc deviceUptime.

clientToken là chuỗi do client cung cấp để ghép response với request đang chờ. Nó hữu ích trong MQTT vì nhiều request có thể được gửi trên cùng kết nối. clientToken không thay thế cơ chế version và không nên được xem là một khóa idempotency tự động.

version tăng sau mỗi lần shadow được cập nhật thành công. Client có thể dùng version để phát hiện dữ liệu cũ và tránh ghi đè trạng thái mới hơn.

## 6. Cập nhật một phần và quy tắc JSON

Shadow update thường là partial update. Client chỉ gửi các field muốn thay đổi; field khác được giữ nguyên.

Ví dụ shadow đang có:

~~~json
{
  "state": {
    "desired": {
      "power": "ON",
      "setpoint": 24,
      "mode": "COOL"
    }
  }
}
~~~

Ứng dụng gửi:

~~~json
{
  "state": {
    "desired": {
      "setpoint": 22
    }
  }
}
~~~

Sau update, power vẫn là ON, mode vẫn là COOL, còn setpoint đổi thành 22. Không cần gửi lại toàn bộ desired state.

### 6.1 Xóa một thuộc tính

Đặt giá trị thuộc tính thành null để xóa thuộc tính đó khỏi phần state tương ứng:

~~~json
{
  "state": {
    "desired": {
      "schedule": null
    }
  }
}
~~~

Đây là thao tác xóa key, không phải lưu một giá trị JSON null như một trạng thái bình thường.

### 6.2 Mảng được xử lý như một giá trị

Mảng được so sánh như một giá trị hoàn chỉnh. Nếu mảng desired khác mảng reported, toàn bộ mảng desired được đưa vào delta. Không thể cập nhật riêng một phần tử mảng theo cơ chế merge của shadow.

Ví dụ:

~~~json
{
  "state": {
    "desired": {
      "allowedModes": ["AUTO", "COOL"]
    }
  }
}
~~~

Nếu muốn đổi danh sách, hãy gửi toàn bộ mảng mới. Với danh sách dài hoặc phần tử cần cập nhật độc lập, cân nhắc mô hình object có key ổn định thay cho array.

### 6.3 Nested object

Nested object được so sánh theo field. Nếu chỉ một thuộc tính con khác nhau, delta có thể chỉ chứa đường dẫn đến thuộc tính đó.

Ví dụ desired:

~~~json
{
  "lights": {
    "color": {
      "r": 255,
      "g": 255,
      "b": 255
    }
  }
}
~~~

reported:

~~~json
{
  "lights": {
    "color": {
      "r": 255,
      "g": 0,
      "b": 255
    }
  }
}
~~~

Delta:

~~~json
{
  "lights": {
    "color": {
      "g": 255
    }
  }
}
~~~

Thiết kế schema ổn định và tránh lồng object quá sâu. AWS IoT giới hạn độ sâu của desired/reported state document.

## 7. Classic shadow và named shadow

AWS IoT hỗ trợ hai loại shadow:

| Loại | Đặc điểm | Khi nào dùng |
|---|---|---|
| Classic/unnamed shadow | Mỗi Thing có tối đa một classic shadow | Thiết bị có một nhóm trạng thái nhỏ và đơn giản |
| Named shadow | Một Thing có thể có nhiều shadow được đặt tên | Cần phân tách nhiều nhóm trạng thái hoặc quyền truy cập |

Ví dụ thiết bị gateway có thể có:
- configuration: cấu hình mạng và sampling interval.
- climate: nhiệt độ mục tiêu, chế độ điều hòa.
- maintenance: trạng thái bảo trì và thông tin chẩn đoán.

Named shadow giúp chia dữ liệu theo concern. Nó cũng có thể giúp áp dụng policy khác nhau cho từng nhóm dữ liệu, chẳng hạn service cấu hình chỉ được ghi configuration, còn ứng dụng vận hành chỉ được đọc maintenance.

Named shadow không tự tạo ranh giới bảo mật. Cần viết IoT policy để giới hạn đúng Thing, đúng shadow name và đúng topic action. Nếu mọi client đều có quyền wildcard trên mọi named shadow, lợi ích phân quyền sẽ mất đi.

Nếu hệ thống có khả năng mở rộng thành nhiều nhóm trạng thái, nên cân nhắc named shadow ngay từ đầu. Classic shadow đơn giản hơn nhưng chỉ có một namespace trạng thái không tên cho mỗi Thing.

## 8. MQTT reserved topics

Thiết bị thường giao tiếp với Device Shadow qua MQTT. Mỗi thao tác có request topic, response thành công và response lỗi.

### 8.1 Topic prefix

Classic shadow:

~~~text
$aws/things/thermostat-01/shadow
~~~

Named shadow:

~~~text
$aws/things/thermostat-01/shadow/name/climate
~~~

Sau prefix, thêm topic stub như /get, /update hoặc /delete.

### 8.2 Các topic chính

| Topic suffix | Hướng | Ý nghĩa |
|---|---|---|
| /get | Publish | Yêu cầu đọc shadow hiện tại |
| /get/accepted | Subscribe | Trả về shadow document |
| /get/rejected | Subscribe | GET bị từ chối |
| /update | Publish | Gửi partial state update |
| /update/accepted | Subscribe | Update được chấp nhận |
| /update/rejected | Subscribe | Update bị từ chối |
| /update/delta | Subscribe | Desired và reported có khác biệt |
| /update/documents | Subscribe | Thông báo document trước/sau update |
| /delete | Publish | Xóa shadow |
| /delete/accepted | Subscribe | Xóa thành công |
| /delete/rejected | Subscribe | Xóa bị từ chối |

Với named shadow climate của Thing thermostat-01, topic update là:

~~~text
$aws/things/thermostat-01/shadow/name/climate/update
~~~

Topic delta tương ứng:

~~~text
$aws/things/thermostat-01/shadow/name/climate/update/delta
~~~

Topic phân biệt chữ hoa/chữ thường. Phải dùng đúng Thing name và shadow name.

### 8.3 Subscribe trước khi publish

MQTT là publish/subscribe. Client nên subscribe các response topic trước khi gửi request. Nếu publish request trước khi subscribe, client có thể bỏ lỡ response.

Ví dụ flow GET:
1. Subscribe /get/accepted.
2. Subscribe /get/rejected.
3. Publish payload rỗng đến /get.
4. Nhận response trên một trong hai topic.

Với update, subscribe tối thiểu /update/accepted và /update/rejected; thiết bị cần nhận yêu cầu từ cloud thì subscribe thêm /update/delta.

Không subscribe wildcard rộng như $aws/things/thermostat-01/shadow/#. AWS có thể bổ sung topic mới trong cấu trúc reserved topics. Chỉ subscribe đúng các topic mà client sử dụng.

### 8.4 Xóa shadow

Client publish payload rỗng đến topic /delete và chờ /delete/accepted hoặc /delete/rejected. Xóa shadow loại bỏ tài liệu trạng thái hiện tại; thao tác này không reset version về 0. Tài liệu shadow đã xóa không thể được khôi phục bằng cách gọi GET. Nếu cần xóa, hãy xác nhận Thing không còn phụ thuộc vào shadow và audit/backup cần thiết đã được lưu ở hệ thống riêng.

## 9. Luồng đồng bộ từ cloud xuống thiết bị

Ví dụ cloud yêu cầu thermostat đặt nhiệt độ 24°C và chế độ COOL.

### Bước 1: Cloud cập nhật desired

Cloud application gửi:

~~~json
{
  "state": {
    "desired": {
      "setpoint": 24,
      "mode": "COOL"
    }
  },
  "clientToken": "dashboard-req-1001"
}
~~~

Request được publish đến topic /update của shadow tương ứng hoặc gọi UpdateThingShadow qua HTTPS API.

### Bước 2: AWS IoT cập nhật shadow

Nếu request hợp lệ:
- AWS IoT lưu desired mới.
- Version tăng.
- Metadata của các field được cập nhật.
- AWS IoT gửi /update/accepted.
- Nếu desired khác reported, AWS IoT gửi /update/delta.

/update/accepted xác nhận shadow đã nhận update. Nó không chứng minh thiết bị đã thực hiện hành động vật lý.

### Bước 3: Thiết bị nhận delta

Thiết bị nhận payload delta, ví dụ:

~~~json
{
  "state": {
    "setpoint": 24,
    "mode": "COOL"
  },
  "metadata": {
    "setpoint": {
      "timestamp": 1795161600
    },
    "mode": {
      "timestamp": 1795161600
    }
  },
  "version": 18,
  "timestamp": 1795161600
}
~~~

Firmware kiểm tra version, kiểm tra giá trị hợp lệ và áp dụng cấu hình. Không nên thực hiện một giá trị desired một cách mù quáng. Ví dụ thiết bị có thể từ chối setpoint nằm ngoài giới hạn an toàn hoặc không hỗ trợ mode được yêu cầu.

### Bước 4: Thiết bị báo cáo trạng thái thực tế

Sau khi áp dụng và xác minh, thiết bị gửi:

~~~json
{
  "state": {
    "reported": {
      "setpoint": 24,
      "mode": "COOL"
    }
  },
  "clientToken": "device-report-501"
}
~~~

AWS IoT cập nhật reported. Nếu desired và reported khớp, delta tương ứng biến mất.

### Bước 5: Ứng dụng xác nhận trạng thái

Dashboard đọc reported để hiển thị thiết bị đã áp dụng cấu hình. Nếu thiết bị không thể thực hiện, firmware có thể báo cáo trạng thái lỗi riêng, ví dụ applyStatus = REJECTED và lastError = SETPOINT_OUT_OF_RANGE.

Không nên coi update/accepted là xác nhận thiết bị đã chạy thành công. Xác nhận thực thi phải đến từ reported state hoặc một workflow job có trạng thái riêng.

## 10. Đồng bộ khi thiết bị offline và reconnect

Điểm mạnh của Device Shadow là ứng dụng có thể cập nhật desired trong lúc thiết bị offline. AWS IoT lưu trạng thái mong muốn mới nhất. Khi thiết bị reconnect, nó có thể lấy trạng thái cloud để hội tụ.

Quy trình reconnect khuyến nghị:

1. Kết nối đến AWS IoT Core bằng certificate/credential hợp lệ.
2. Subscribe các response topics và delta topics mà firmware hỗ trợ.
3. Publish /get để lấy shadow document mới nhất.
4. Nếu /get/accepted, đọc desired/reported, version và delta.
5. Nếu shadow chưa tồn tại và /get/rejected báo không có shadow, tạo shadow bằng update reported với trạng thái thiết bị hiện tại.
6. Áp dụng desired khác reported theo logic firmware.
7. Publish reported sau khi xác minh trạng thái thực tế.
8. Tiếp tục xử lý delta khi kết nối đang hoạt động.

Ví dụ sơ đồ:

~~~text
Cloud application
      |
      | Update desired while device offline
      v
AWS IoT Device Shadow
      |
      | Device reconnects
      v
Subscribe response topics
      |
      v
GET current shadow
      |
      v
Compare desired and reported
      |
      v
Apply safe changes on device
      |
      v
Publish reported state
      |
      v
Delta becomes empty for matched fields
~~~

Không dựa vào giả định thiết bị sẽ nhận mọi delta đã phát trong thời gian offline. MQTT notification có thể bị bỏ lỡ khi client không kết nối; shadow document hiện tại là nguồn để thiết bị đồng bộ lại.

Nếu desired thay đổi nhiều lần trong lúc offline, thiết bị cần hội tụ về trạng thái mong muốn mới nhất. Nếu nghiệp vụ yêu cầu chạy lần lượt từng lệnh, cần dùng hàng đợi/job riêng thay vì dựa vào delta.

## 11. Version và xử lý xung đột cập nhật

Shadow document có version. Mỗi update thành công làm version tăng. Client có thể gửi version hiện tại trong request để đảm bảo thao tác chỉ được thực hiện nếu document chưa bị client khác cập nhật.

Ví dụ client đọc shadow version 18. Trước khi client ghi, một ứng dụng khác đã cập nhật và version trở thành 19. Nếu client gửi update với version 18, AWS IoT từ chối vì version đã cũ.

Quy trình xử lý:
1. Nhận /update/rejected hoặc HTTP conflict.
2. Đọc error code/message.
3. GET shadow mới nhất.
4. Tính lại thay đổi dựa trên state mới.
5. Gửi update với version mới nếu cần bảo vệ read-modify-write.
6. Dùng backoff có jitter khi có nhiều client tranh chấp.

Ví dụ update có version:

~~~json
{
  "state": {
    "desired": {
      "setpoint": 22
    }
  },
  "version": 19,
  "clientToken": "dashboard-req-1002"
}
~~~

Nếu ứng dụng chỉ cập nhật một field độc lập và không phụ thuộc dữ liệu vừa đọc, partial update không kèm version có thể phù hợp. Nếu thao tác dựa trên trạng thái đọc trước đó, dùng version để tránh ghi đè quyết định mới của client khác.

### 11.1 Message đến sai thứ tự

Do mạng và xử lý bất đồng bộ, thiết bị có thể nhận message version cũ sau message version mới. Thiết bị nên lưu version đã xử lý và bỏ qua notification có version thấp hơn.

Nếu version bị nhảy hoặc thiết bị nghi ngờ mất message, GET lại shadow để lấy snapshot hiện tại. Không cố tái dựng trạng thái chỉ từ một chuỗi delta có thể thiếu.

### 11.2 clientToken

clientToken giúp ứng dụng ghép response với request đang chờ. Mỗi request outstanding nên có token riêng để dễ tương quan log.

Không dùng clientToken thay cho version. Token nhận diện request; version bảo vệ tính nhất quán của state.

## 12. REST API và MQTT: chọn cách truy cập

AWS IoT Device Shadow có thể được truy cập bằng:
- MQTT reserved topics.
- HTTPS REST API.
- AWS SDK hoặc AWS CLI dùng các API tương ứng.

| Tiêu chí | MQTT | HTTPS/SDK |
|---|---|---|
| Đối tượng thường dùng | Firmware/device và ứng dụng realtime | Backend service, admin tool, automation |
| Mô hình | Publish/subscribe, request/response qua topic | API request/response |
| Kết nối | Kết nối MQTT dài hạn | HTTP request |
| Thông báo delta | Subscribe /update/delta | Backend có thể subscribe MQTT hoặc dùng integration phù hợp |
| Xác thực phổ biến | X.509 certificate và AWS IoT policy | AWS credentials/IAM với SigV4 |
| Phù hợp | Thiết bị cần kết nối liên tục và nhận state change | Backend cần đọc/ghi shadow theo API |

Các API thường dùng:
- GetThingShadow: lấy shadow document.
- UpdateThingShadow: cập nhật shadow document.
- DeleteThingShadow: xóa shadow.
- ListNamedShadowsForThing: liệt kê named shadows của Thing.

ListNamedShadowsForThing là API liệt kê named shadows; classic shadow không có tên nên không xuất hiện như một named shadow.

Dù dùng MQTT hay HTTPS, semantics của desired/reported, delta và version vẫn giống nhau. Cần chọn giao thức dựa trên vị trí client và mô hình kết nối.

## 13. Bảo mật và phân quyền

Device Shadow chứa cấu hình và trạng thái thiết bị. Một principal có quyền ghi desired có thể thay đổi hành vi thiết bị; vì vậy cần giới hạn ai được update và ai chỉ được đọc.

### 13.1 Xác thực thiết bị

Thiết bị thường kết nối AWS IoT Core bằng X.509 certificate. Certificate được đăng ký, kích hoạt và gắn với Thing/policy theo mô hình quản lý thiết bị.

Nguyên tắc:
- Dùng certificate riêng cho từng thiết bị hoặc danh tính có phạm vi hẹp.
- Bảo vệ private key trong secure element/TPM nếu phần cứng hỗ trợ.
- Có quy trình rotate/revoke certificate.
- Không dùng chung private key cho cả fleet.
- Gắn certificate với Thing identity đúng quy trình.
- Dùng TLS khi kết nối.

### 13.2 AWS IoT policy cho MQTT

IoT policy kiểm soát publish, subscribe và receive trên MQTT topic. Ba action thường gặp:

| Action | Resource type | Mục đích |
|---|---|---|
| iot:Publish | topic | Cho phép gửi request đến /get, /update, /delete |
| iot:Subscribe | topicfilter | Cho phép subscribe response/delta topic |
| iot:Receive | topic | Cho phép nhận message từ topic đã subscribe |

Ví dụ policy hẹp cho một thiết bị thermostat:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iot:Connect",
      "Resource": "arn:aws:iot:ap-southeast-1:123456789012:client/thermostat-01"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Publish",
      "Resource": [
        "arn:aws:iot:ap-southeast-1:123456789012:topic/$aws/things/thermostat-01/shadow/name/climate/get",
        "arn:aws:iot:ap-southeast-1:123456789012:topic/$aws/things/thermostat-01/shadow/name/climate/update"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "iot:Subscribe",
      "Resource": [
        "arn:aws:iot:ap-southeast-1:123456789012:topicfilter/$aws/things/thermostat-01/shadow/name/climate/get/accepted",
        "arn:aws:iot:ap-southeast-1:123456789012:topicfilter/$aws/things/thermostat-01/shadow/name/climate/get/rejected",
        "arn:aws:iot:ap-southeast-1:123456789012:topicfilter/$aws/things/thermostat-01/shadow/name/climate/update/delta",
        "arn:aws:iot:ap-southeast-1:123456789012:topicfilter/$aws/things/thermostat-01/shadow/name/climate/update/accepted",
        "arn:aws:iot:ap-southeast-1:123456789012:topicfilter/$aws/things/thermostat-01/shadow/name/climate/update/rejected"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "iot:Receive",
      "Resource": [
        "arn:aws:iot:ap-southeast-1:123456789012:topic/$aws/things/thermostat-01/shadow/name/climate/get/accepted",
        "arn:aws:iot:ap-southeast-1:123456789012:topic/$aws/things/thermostat-01/shadow/name/climate/get/rejected",
        "arn:aws:iot:ap-southeast-1:123456789012:topic/$aws/things/thermostat-01/shadow/name/climate/update/delta",
        "arn:aws:iot:ap-southeast-1:123456789012:topic/$aws/things/thermostat-01/shadow/name/climate/update/accepted",
        "arn:aws:iot:ap-southeast-1:123456789012:topic/$aws/things/thermostat-01/shadow/name/climate/update/rejected"
      ]
    }
  ]
}
~~~

Đây là ví dụ minh họa; thay Region, account, Thing name và MQTT client ID theo môi trường (ví dụ trên dùng client ID thermostat-01). Policy phân quyền theo MQTT topic, không kiểm tra được các key bên trong JSON payload. Vì desired và reported cùng dùng topic /update, quyền publish vào topic này không thể chỉ cho phép firmware ghi reported bằng IoT policy. Hãy giữ quy ước firmware chỉ gửi reported, backend chỉ ghi desired, kiểm tra payload ở tầng ứng dụng và dùng IAM role riêng cho backend gọi HTTPS API. Nếu cần enforcement mạnh hơn ở biên, thiết kế thêm lớp xác thực/ủy quyền hoặc validation phù hợp thay vì dựa vào topic policy để phân biệt JSON field.

### 13.3 IAM cho HTTPS API

Backend gọi Device Shadow REST API bằng AWS credentials và IAM policy. Phân tách quyền backend với quyền MQTT certificate của thiết bị. AWS IoT policy và IAM policy là hai cơ chế phân quyền khác nhau; cấu hình một cơ chế không tự động cấp quyền cho cơ chế còn lại.

### 13.4 Nguyên tắc least privilege

- Firmware theo quy ước chỉ publish reported; policy giới hạn topic mà firmware có thể publish/subscribe.
- Backend cấu hình được desired của đúng nhóm Thing.
- Admin role riêng mới được phép delete shadow.
- Named shadow được giới hạn theo tên.
- Không cấp wildcard trên mọi Thing nếu service chỉ quản lý một nhóm thiết bị.
- Không subscribe $aws/things/THING/shadow/# một cách mặc định.
- Rà soát certificate, policy attachment và quyền truy cập định kỳ.

## 14. Tích hợp với các dịch vụ AWS khác

Device Shadow thường là một phần trong kiến trúc IoT rộng hơn.

### 14.1 AWS IoT Rules Engine

Rules Engine có thể đọc MQTT message và chuyển tiếp sự kiện đến dịch vụ AWS. Ví dụ:
- Lắng nghe update/documents để ghi audit event.
- Lắng nghe update/delta để phát hiện cấu hình mới.
- Republish một payload đã rút gọn sang topic ứng dụng.
- Gọi Lambda để kiểm tra business rule hoặc gửi notification.
- Ghi dữ liệu sự kiện vào Kinesis, S3 hoặc hệ thống analytics theo thiết kế.

Không nên ghi mọi message shadow thành telemetry nếu chỉ cần trạng thái mới nhất. Nếu cần lịch sử đầy đủ, hãy xác định rõ event schema và retention riêng.

### 14.2 AWS Lambda và backend service

Lambda hoặc service chạy trên ECS/EC2 có thể dùng AWS SDK để:
- Đọc shadow trước khi gửi cấu hình.
- Cập nhật desired.
- Xác nhận version.
- Kiểm tra reported.
- Xử lý request từ dashboard hoặc API.

Backend nên có idempotency ở tầng nghiệp vụ, ghi audit log và kiểm tra quyền của người dùng trước khi ghi desired.

### 14.3 Fleet Indexing

AWS IoT Fleet Indexing có thể index dữ liệu từ Thing Registry, Device Shadow, connectivity và các nguồn fleet liên quan. Backend có thể tìm kiếm và tổng hợp theo thuộc tính thiết bị, trạng thái hoặc nhóm.

Ví dụ:
- Tìm thiết bị có reported.firmwareVersion cũ.
- Tìm thiết bị có reported.temperature vượt ngưỡng.
- Tìm thiết bị có desired/reported chưa khớp.
- Tổng hợp trạng thái theo Thing Group hoặc loại thiết bị.

Fleet Indexing phù hợp với truy vấn fleet. Nó không thay thế thiết kế schema shadow, phân quyền hay kho dữ liệu telemetry chuyên dụng.

### 14.4 AWS IoT Device Management Jobs

Dùng Device Shadow cho trạng thái hiện tại như:
- Cấu hình mục tiêu.
- Chế độ vận hành.
- Firmware version đang báo cáo.
- Trạng thái kết nối hoặc lỗi gần nhất.

Dùng Device Management Jobs cho công việc cần tiến trình và kết quả:
- Cập nhật firmware OTA.
- Chạy maintenance task.
- Thực thi migration.
- Cài đặt package.
- Thực hiện một hành động có trạng thái queued/in-progress/succeeded/failed.

Shadow biểu diễn trạng thái mong muốn hiện tại; Jobs biểu diễn công việc cần được thực hiện và theo dõi.

## 15. Thiết kế schema shadow

Shadow document có giới hạn kích thước, vì vậy chỉ lưu những thuộc tính cần đồng bộ. Không dùng shadow như một bản sao toàn bộ database thiết bị.

Ví dụ schema cho thiết bị HVAC:

~~~json
{
  "state": {
    "desired": {
      "control": {
        "power": "ON",
        "mode": "COOL",
        "setpointC": 24
      },
      "sampling": {
        "intervalSeconds": 60
      }
    },
    "reported": {
      "control": {
        "power": "ON",
        "mode": "COOL",
        "setpointC": 24
      },
      "sampling": {
        "intervalSeconds": 60
      },
      "telemetry": {
        "lastKnownTemperatureC": 25.4,
        "lastKnownHumidityPercent": 61
      },
      "firmwareVersion": "2.4.1",
      "applyStatus": "SUCCEEDED"
    }
  }
}
~~~

Thiết kế nên:
- Dùng tên field ổn định, dễ hiểu.
- Chọn kiểu dữ liệu nhất quán.
- Có đơn vị rõ ràng trong tên field hoặc schema.
- Tách cấu hình mong muốn khỏi dữ liệu đo.
- Không ghi lịch sử telemetry dài vào shadow.
- Không lưu secret, private key, password hoặc dữ liệu nhạy cảm không cần thiết.
- Giới hạn số field và độ sâu object.
- Có quy tắc schema version nếu firmware và backend phát triển độc lập.

### 15.1 Schema evolution

Firmware cũ có thể không hiểu field mới. Backend có thể cần rollout cấu hình theo phiên bản thiết bị.

Nên:
- Thêm field theo hướng tương thích ngược.
- Không đổi ý nghĩa của field đang tồn tại.
- Dùng configSchemaVersion hoặc desiredConfigVersion khi cần.
- Thiết bị bỏ qua field chưa hỗ trợ và báo cáo trạng thái rõ ràng.
- Backend chỉ gửi cấu hình mà firmware version tương ứng có thể hiểu.
- Kiểm thử firmware cũ, firmware mới và quá trình rollback.

### 15.2 Tách state và telemetry

Shadow lưu trạng thái mới nhất, không phải lịch sử chuỗi thời gian. Có thể giữ một số giá trị tóm tắt gần nhất như lastKnownTemperatureC nếu chúng có ý nghĩa đối với trạng thái thiết bị. Nếu thiết bị gửi nhiệt độ mỗi giây, việc ghi mọi mẫu vào shadow sẽ tạo nhiều update, tăng tải và làm mất giá trị lịch sử của các mẫu trước.

Một kiến trúc phù hợp:
- Shadow: setpoint, mode, last known status, firmware version.
- MQTT telemetry topic: nhiệt độ, độ ẩm, voltage, vibration.
- IoT Rules Engine: định tuyến telemetry đến Kinesis, Timestream, S3 hoặc analytics pipeline.
- Fleet Indexing: tìm kiếm trạng thái fleet.
- CloudWatch: log và metric vận hành dịch vụ.

## 16. Giới hạn và quota cần thiết kế

Theo bảng quota AWS IoT Core hiện hành, các giới hạn Device Shadow đáng chú ý gồm:

| Giới hạn | Giá trị mặc định được công bố | Ghi chú |
|---|---:|---|
| Kích thước mỗi JSON shadow state document | 8 KB | Có thể điều chỉnh; metadata không tính vào kích thước |
| Độ sâu desired/reported | 8 cấp | Không điều chỉnh được |
| Shadow name | 64 byte UTF-8 | Không điều chỉnh được |
| Thing name | 128 byte UTF-8 | Theo giới hạn Thing |
| Request rate trên mỗi shadow | 20 request/giây | Có thể điều chỉnh |
| Request rate API shadow trên account | 4.000 request/giây | Một số Region có mặc định 400; có thể điều chỉnh theo quota |
| Request chưa được xác nhận đang bay trên mỗi Thing/kết nối | 10 | Vượt giới hạn sẽ bị từ chối với response code 429 |

Quota có thể khác theo Region và account. Trước khi triển khai fleet lớn, kiểm tra AWS General Reference và Service Quotas của Region mục tiêu.

### 16.1 Giảm payload

- Chỉ gửi field thay đổi.
- Tránh lặp metadata do ứng dụng tự tạo.
- Dùng schema gọn.
- Tách các nhóm trạng thái thành named shadows khi phù hợp.
- Không lưu telemetry array dài.
- Không gửi full shadow document khi chỉ cần update một field.

### 16.2 Điều tiết request

Nếu thiết bị hoặc backend gửi update quá nhanh:
- Coalesce nhiều thay đổi desired thành một update.
- Giới hạn số request outstanding.
- Chờ accepted/rejected trước khi gửi quá nhiều request.
- Dùng exponential backoff và jitter khi throttling.
- Tránh reconnect storm khi hàng nghìn thiết bị khởi động cùng lúc.
- Phân phối fleet rollout theo batch.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| get/rejected khi khởi tạo | Shadow chưa tồn tại | Tạo bằng update reported đầu tiên |
| update/rejected do version | Client dùng version cũ | GET state mới, merge và retry |
| update/rejected do JSON | JSON sai hoặc field ngoài state | Kiểm tra schema, chỉ dùng desired/reported |
| Payload quá lớn | Shadow document vượt giới hạn | Rút gọn field hoặc tách named shadow |
| Không nhận accepted | Chưa subscribe response trước publish hoặc thiếu quyền | Subscribe đúng topic trước request, kiểm tra policy |
| Không nhận delta | Desired đã khớp reported hoặc client chưa subscribe | GET shadow, so sánh hai phần và kiểm tra topic |
| Delta liên tục xuất hiện | Thiết bị không cập nhật reported hoặc reported sai | Kiểm tra actuator, firmware và báo cáo trạng thái |
| Device không áp dụng desired | Firmware chưa hỗ trợ field hoặc giá trị không hợp lệ | Kiểm tra capability/version và validation |
| Request bị 429 | Vượt request rate hoặc inflight limit | Giảm concurrency, backoff và xem quota |
| Cloud hiển thị trạng thái sai | Backend ghi reported thay cho thiết bị | Chốt ownership; chỉ firmware báo cáo trạng thái vật lý |
| Reconnect xử lý lệnh cũ | Firmware dựa vào notification cũ | GET snapshot, so version và đồng bộ state hiện tại |
| Named shadow không truy cập được | Sai shadow name hoặc topic ARN | Kiểm tra prefix và policy resource |

AWS IoT Device Shadow có thể ghi log lỗi vào CloudWatch Logs khi cấu hình logging phù hợp. Khi điều tra, cần đối chiếu:
- MQTT client log.
- accepted và rejected response.
- code, message, clientToken, version.
- AWS IoT logs.
- Certificate và IoT policy.
- IAM policy nếu backend dùng HTTPS API.

## 18. Quan sát và vận hành fleet

Một shadow architecture cần theo dõi cả trạng thái service và trạng thái thiết bị.

### 18.1 Các chỉ số nên quan sát

| Chỉ số | Ý nghĩa |
|---|---|
| Shadow update success/reject rate | Tỷ lệ cập nhật thành công và thất bại |
| Version conflict count | Số xung đột optimistic concurrency |
| Throttling/429 count | Số request bị giới hạn |
| Delta age | Thời gian desired chưa được reported xác nhận |
| Desired/reported mismatch count | Số thiết bị chưa hội tụ |
| Reconnect synchronization time | Thời gian thiết bị đồng bộ sau reconnect |
| Payload size distribution | Phát hiện shadow gần chạm giới hạn |
| Request latency | Thời gian phản hồi shadow operation |
| Fleet coverage | Tỷ lệ thiết bị đã báo cáo trạng thái |
| Firmware capability distribution | Số thiết bị theo phiên bản firmware |

Không phải mọi chỉ số đều có metric mặc định trong CloudWatch. Một số cần được tính từ event, Rule, backend log hoặc Fleet Indexing.

### 18.2 Cảnh báo

Có thể tạo cảnh báo khi:
- Tỷ lệ update rejected tăng bất thường.
- 429 xuất hiện liên tục.
- Nhiều thiết bị có desired/reported mismatch lâu hơn SLA.
- Fleet reconnect nhưng không báo cáo reported.
- Firmware version cũ chiếm tỷ lệ cao.
- Shadow document tăng kích thước gần giới hạn.

Cảnh báo nên phân biệt sự cố kết nối với lỗi thực thi. Thiết bị offline không nhất thiết có lỗi actuator; nhưng desired tồn tại quá lâu có thể là dấu hiệu thiết bị chưa nhận cấu hình.

### 18.3 Audit và lịch sử

Shadow lưu trạng thái hiện tại, không lưu toàn bộ lịch sử lệnh như một event log. Nếu cần audit:
- Lưu update event qua update/documents hoặc Rules Engine.
- Ghi actor, request ID, Thing name và thời điểm.
- Lưu old/new value theo yêu cầu bảo mật.
- Kiểm soát retention và quyền đọc audit log.
- Phân biệt ai yêu cầu desired và thiết bị nào xác nhận reported.

## 19. Ví dụ thực hành: điều khiển thermostat bằng named shadow

Mục tiêu: backend cập nhật nhiệt độ mục tiêu; thiết bị nhận delta, áp dụng và báo cáo lại.

### Bước 1: Chọn Thing và shadow

Thing:

~~~text
thermostat-01
~~~

Named shadow:

~~~text
climate
~~~

Topic prefix:

~~~text
$aws/things/thermostat-01/shadow/name/climate
~~~

### Bước 2: Thiết bị subscribe

Thiết bị subscribe:
- .../get/accepted
- .../get/rejected
- .../update/delta
- .../update/accepted
- .../update/rejected

Có thể subscribe .../update/documents nếu cần nhận document trước/sau update.

### Bước 3: Thiết bị khởi tạo reported

Publish vào:

~~~text
$aws/things/thermostat-01/shadow/name/climate/update
~~~

Payload:

~~~json
{
  "state": {
    "reported": {
      "power": "ON",
      "setpointC": 26,
      "mode": "AUTO",
      "firmwareVersion": "2.4.1"
    }
  },
  "clientToken": "thermostat-boot-001"
}
~~~

### Bước 4: Backend cập nhật desired

Backend publish đến cùng /update topic hoặc gọi API:

~~~json
{
  "state": {
    "desired": {
      "setpointC": 24,
      "mode": "COOL"
    }
  },
  "clientToken": "operator-change-2001"
}
~~~

### Bước 5: Thiết bị nhận delta và thực thi

Delta chứa setpointC = 24 và mode = COOL. Firmware kiểm tra giới hạn, áp dụng cấu hình, đọc lại trạng thái từ bộ điều khiển rồi gửi reported.

~~~json
{
  "state": {
    "reported": {
      "setpointC": 24,
      "mode": "COOL",
      "applyStatus": "SUCCEEDED"
    }
  },
  "clientToken": "thermostat-report-002"
}
~~~

### Bước 6: Backend xác nhận

Backend đọc shadow. Khi desired/reported khớp, delta không còn chứa các field đó. Dashboard có thể hiển thị:
- Desired setpoint: 24°C.
- Reported setpoint: 24°C.
- Apply status: SUCCEEDED.

Nếu thiết bị không hỗ trợ COOL, firmware không được báo cáo mode = COOL như thể đã áp dụng. Nó nên giữ reported mode thực tế và báo lỗi riêng để backend có thể hiển thị mismatch.

## 20. Checklist thiết kế production

- [ ] Đã xác định Thing identity và ownership.
- [ ] Đã chọn classic hay named shadow.
- [ ] Đã quy định rõ cloud chỉ ghi desired và device chỉ ghi reported.
- [ ] Delta được xem là khác biệt hiện tại, không phải hàng đợi lệnh.
- [ ] Firmware subscribe response topics trước khi publish request.
- [ ] Thiết bị GET shadow khi khởi động và reconnect.
- [ ] Thiết bị xác minh desired trước khi áp dụng.
- [ ] Thiết bị báo reported sau khi xác nhận trạng thái thực tế.
- [ ] Có xử lý version và stale message.
- [ ] Có clientToken để ghép request/response.
- [ ] Có xử lý rejected, version conflict và throttling.
- [ ] Có backoff và jitter cho retry.
- [ ] Shadow schema nhỏ, ổn định và có versioning.
- [ ] Không lưu telemetry time-series hoặc secret trong shadow.
- [ ] Đã kiểm tra giới hạn payload, nesting và request rate.
- [ ] IoT policy giới hạn đúng Thing, shadow và topic action.
- [ ] HTTPS backend dùng IAM policy riêng.
- [ ] Không cấp wildcard shadow topic không cần thiết.
- [ ] Đã cấu hình CloudWatch logging và audit event.
- [ ] Đã kiểm thử offline, reconnect, update đồng thời và firmware cũ.
- [ ] Nếu cần command/job history, đã chọn Device Management Jobs hoặc queue phù hợp.

## 21. Bài tập thực hành

### Bài 1: Desired và reported

Cloud cập nhật desired setpoint = 22, nhưng thiết bị đang báo cáo setpoint = 25.

Yêu cầu: delta chứa giá trị nào? Khi nào delta biến mất?

Đáp án: delta chứa setpoint = 22. Sau khi thiết bị áp dụng và cập nhật reported thành 22, hai phần khớp và delta biến mất.

### Bài 2: Thiết bị offline

Một thiết bị offline trong 3 giờ. Trong thời gian đó backend đổi desired từ 24 sang 23 rồi 22.

Yêu cầu: khi reconnect thiết bị nên thực hiện giá trị nào?

Đáp án: đồng bộ theo desired mới nhất là 22. Device Shadow không lưu một queue yêu cầu phải thực hiện cả 24, 23 rồi 22.

### Bài 3: Version conflict

Backend đọc version 15. Một service khác cập nhật shadow lên version 16. Backend gửi update với version 15.

Yêu cầu: xử lý như thế nào?

Đáp án: update bị từ chối do version cũ. Backend GET shadow mới nhất, merge thay đổi cần thiết và retry với version hiện tại.

### Bài 4: Xóa field

Ứng dụng muốn xóa desired field schedule.

Yêu cầu: gửi payload như thế nào?

Đáp án:

~~~json
{
  "state": {
    "desired": {
      "schedule": null
    }
  }
}
~~~

### Bài 5: Named shadow

Một gateway quản lý network config, sensor config và maintenance state.

Yêu cầu: đề xuất named shadow và lợi ích.

Đáp án gợi ý: network, sensors, maintenance. Tách concern, schema và policy theo nhóm; firmware cần đồng bộ từng shadow riêng.

### Bài 6: Throttling

Một backend gửi 40 update/giây đến cùng một shadow và nhận 429.

Yêu cầu: đề xuất biện pháp.

Đáp án: coalesce update, giảm concurrency, giới hạn inflight, backoff/jitter và kiểm tra quota có thể điều chỉnh. Không retry ngay liên tục.

### Bài 7: Phân quyền

Firmware chỉ cần đọc desired và ghi reported. Backend mới có quyền thay đổi desired.

Yêu cầu: phân chia quyền MQTT thế nào?

Đáp án: firmware subscribe delta/response và publish đến update để báo cáo reported; backend role có quyền cập nhật desired qua API cho đúng Thing. Lưu ý IoT policy chỉ phân quyền theo topic, không thể phân biệt desired với reported trong JSON body của cùng topic update. Enforce quy ước ghi ở firmware/backend và kiểm tra payload ở tầng ứng dụng. Không cấp quyền delete cho firmware nếu không cần.

### Bài 8: Chọn Shadow hay Jobs

Một nhóm thiết bị cần cập nhật firmware, theo dõi tiến trình tải, cài đặt, reboot và kết quả thành công/thất bại.

Đáp án: dùng AWS IoT Device Management Jobs để quản lý tiến trình và kết quả công việc. Có thể dùng shadow để báo cáo firmware version hiện tại hoặc phiên bản mong muốn.

## 22. Câu hỏi tự kiểm tra

1. Device Shadow lưu trữ thông tin gì?
2. Thing khác shadow như thế nào?
3. desired và reported được ai cập nhật?
4. delta được AWS IoT tính như thế nào?
5. Vì sao delta không phải command queue?
6. Shadow có thể được cập nhật khi thiết bị offline không?
7. Khi thiết bị reconnect, tại sao nên GET shadow?
8. Vì sao cần subscribe response topic trước khi publish request?
9. Classic shadow và named shadow khác nhau như thế nào?
10. metadata chứa thông tin gì?
11. timestamp khác thời gian đo tại thiết bị như thế nào?
12. clientToken có vai trò gì?
13. version giúp xử lý race condition ra sao?
14. Khi update bị từ chối vì version cũ, client cần làm gì?
15. Cập nhật một phần shadow document có giữ các field không gửi không?
16. Làm thế nào để xóa một thuộc tính desired?
17. Mảng trong shadow delta được so sánh như thế nào?
18. MQTT update/accepted chứng minh điều gì và không chứng minh điều gì?
19. Khi nào nên dùng Device Management Jobs thay cho shadow?
20. Những giới hạn payload và request rate nào cần kiểm tra?

Gợi ý trả lời:

1. Trạng thái mong muốn và trạng thái gần nhất thiết bị báo cáo.
2. Thing là tài sản logic trong Registry; shadow là tài liệu trạng thái của Thing.
3. Cloud thường cập nhật desired; thiết bị cập nhật reported.
4. So sánh desired với reported và đưa các field khác nhau vào delta.
5. Nó chỉ biểu diễn khác biệt hiện tại, không giữ lịch sử mọi yêu cầu.
6. Có, cloud có thể cập nhật shadow trong khi thiết bị offline.
7. Để lấy snapshot mới nhất và hội tụ sau khi có thể bỏ lỡ notification.
8. MQTT không bảo đảm client nhận response nếu chưa subscribe.
9. Một Thing có tối đa một classic shadow nhưng có thể có nhiều named shadow.
10. Timestamp theo từng thuộc tính.
11. Timestamp là thời điểm AWS IoT xử lý/tạo response; thời gian đo cần field riêng.
12. Ghép response với request tương ứng.
13. Client gửi version đọc được để tránh update trên state đã cũ.
14. GET state mới, merge và retry.
15. Có, các field không gửi thường được giữ nguyên.
16. Gửi field với giá trị null.
17. Cả mảng được coi như một giá trị; khác nhau thì toàn bộ mảng desired xuất hiện trong delta.
18. Nó xác nhận service đã cập nhật shadow, không xác nhận thiết bị đã thực thi.
19. Khi cần workflow công việc, tiến trình, retry và kết quả.
20. State document 8 KB mặc định, nesting 8 cấp, 20 request/giây/shadow và 10 request chưa được xác nhận mỗi Thing/kết nối.

## 23. Tài liệu tham khảo chính thức

- [AWS IoT Device Shadow service](https://docs.aws.amazon.com/iot/latest/developerguide/iot-device-shadows.html)
- [Device Shadow service documents](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-document.html)
- [Device Shadow MQTT topics](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-mqtt.html)
- [Interacting with shadows](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-data-flow.html)
- [Using shadows in devices](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-comms-device.html)
- [Using shadows in apps and services](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-comms-app.html)
- [Device Shadow REST API](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-rest-api.html)
- [Device Shadow service limits and quotas](https://docs.aws.amazon.com/general/latest/gr/iot-core.html)
- [AWS IoT Core policies](https://docs.aws.amazon.com/iot/latest/developerguide/iot-policies.html)
- [Fleet indexing](https://docs.aws.amazon.com/iot/latest/developerguide/iot-indexing.html)
- [AWS IoT Device Management Jobs](https://docs.aws.amazon.com/iot/latest/developerguide/iot-jobs.html)
- [AWS IoT Core Rules Engine](https://docs.aws.amazon.com/iot/latest/developerguide/iot-rules.html)

Giới hạn, API, MQTT topic và khả năng tích hợp có thể thay đổi theo Region và thời điểm. Trước khi triển khai fleet production, hãy xác minh tài liệu AWS hiện hành, kiểm thử firmware reconnect, concurrent update, version conflict, throttling và certificate rotation trong môi trường staging.

# Phân biệt tính năng đã phát hành với phần mở rộng phụ thuộc phiên bản

Khi triển khai service broker theo Open Service Broker API (OSB API), một tính năng được mô tả trong tài liệu chưa chắc đã dùng được ngay trên mọi nền tảng. Tính năng đó có thể thuộc phiên bản giao thức đã phát hành, là khả năng tùy chọn mà broker phải công bố, chỉ xuất hiện ở một phiên bản OSB API mới hơn, hoặc là phần mở rộng riêng của nhà cung cấp. Spring Cloud Open Service Broker cũng có vòng đời phiên bản riêng, vì vậy việc giao thức có định nghĩa một tính năng chưa đồng nghĩa phiên bản framework đang dùng đã hỗ trợ đầy đủ tính năng đó.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, việc phân biệt các nhóm này giúp thiết kế catalog chính xác, chọn đúng phiên bản thư viện, tránh gửi request mà broker không xử lý được và duy trì khả năng tương thích với Cloud Foundry, Kubernetes hoặc nền tảng khác. Bài học này tập trung vào cách nhận diện mức độ hỗ trợ và cách kiểm chứng trước khi đưa tính năng vào môi trường chạy thật.

## 1. Bốn khái niệm cần tách biệt

**Tính năng đã phát hành trong đặc tả (released specification feature)** là hành vi được định nghĩa trong một bản phát hành chính thức của OSB API. Đặc tả mô tả endpoint, trường dữ liệu, điều kiện áp dụng và cách client với broker trao đổi. Khi nói một tính năng thuộc phiên bản giao thức nào, cần dựa trên tài liệu hoặc release note của chính phiên bản đó.

**Khả năng tùy chọn (optional capability)** là tính năng đã được đặc tả chuẩn hóa nhưng không bắt buộc mọi broker phải cung cấp. Broker chỉ nên quảng bá khả năng khi đã triển khai đúng hợp đồng và có thể duy trì hành vi đó. Ví dụ, một broker có thể hỗ trợ cập nhật service instance hoặc truy xuất thông tin instance, trong khi broker khác chỉ hỗ trợ provision, bind và deprovision.

**Tính năng phụ thuộc phiên bản (version-dependent feature)** là tính năng chỉ có trong một mức phiên bản giao thức, framework hoặc nền tảng nhất định. Một thành phần cũ có thể không nhận diện trường mới, endpoint mới hoặc quy tắc xử lý mới. Việc nâng phiên bản một thành phần không tự động nâng các thành phần còn lại.

**Phần mở rộng riêng (vendor-specific extension)** là hành vi hoặc dữ liệu nằm ngoài hợp đồng chuẩn của OSB API và chỉ có ý nghĩa với một broker, nhà cung cấp hoặc nền tảng cụ thể. Phần mở rộng có thể hữu ích, nhưng client không được giả định broker khác cũng hiểu nó.

Bốn khái niệm này không loại trừ nhau. Một tính năng có thể đã được phát hành trong đặc tả nhưng vẫn là tùy chọn đối với broker. Một broker cũng có thể cung cấp phần mở rộng riêng bên cạnh các tính năng chuẩn.

## 2. Lớp nền tảng của OSB API đã phát hành

OSB API chuẩn hóa hợp đồng giữa nền tảng và service broker. Một quy trình cung cấp dịch vụ thường có các nhóm thao tác sau:

| Nhóm thao tác | Mục đích | Vai trò trong vòng đời |
|---|---|---|
| Catalog | Trả danh sách service và plan | Cho nền tảng biết broker có thể cung cấp gì |
| Provision | Yêu cầu tạo service instance | Bắt đầu cấp phát tài nguyên |
| Last operation | Tra cứu trạng thái một thao tác bất đồng bộ | Theo dõi tiến độ provision, update hoặc deprovision |
| Bind | Yêu cầu thông tin truy cập cho một consumer | Cho ứng dụng sử dụng service instance |
| Unbind | Hủy một binding | Thu hồi quyền hoặc thông tin truy cập của consumer |
| Deprovision | Yêu cầu thu hồi service instance | Kết thúc vòng đời tài nguyên |
| Update | Yêu cầu thay đổi service instance | Điều chỉnh plan hoặc cấu hình khi được hỗ trợ |

Các endpoint thuộc API v2 có hình dạng quen thuộc như:

~~~http
GET /v2/catalog
PUT /v2/service_instances/{instance_id}
GET /v2/service_instances/{instance_id}/last_operation
PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}
DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id}
DELETE /v2/service_instances/{instance_id}
PATCH /v2/service_instances/{instance_id}
~~~

Đây là hình dạng tổng quát để nhận diện nhóm thao tác. Phương thức HTTP, query parameter, request body, response code và điều kiện áp dụng cụ thể phải được đối chiếu với phiên bản OSB API mà nền tảng và broker cùng hỗ trợ. Chẳng hạn, update không có nghĩa mọi service đều cho phép đổi plan hoặc thay đổi mọi tham số.

Một broker cần triển khai đúng các thao tác bắt buộc của hợp đồng mà nó công bố. Với thao tác hoặc khả năng tùy chọn, broker chỉ công bố và nhận request khi đã hỗ trợ. Client cần dựa vào hợp đồng và capability được công bố, không suy luận chỉ từ việc một endpoint có thể tồn tại trong tài liệu.

### Phiên bản giao thức và phiên bản thư viện là hai việc khác nhau

API v2 là dòng phiên bản chính của giao thức. Trong các bản phát hành thuộc cùng dòng, đặc tả có thể bổ sung trường, capability hoặc quy tắc xử lý. Vì vậy, chỉ nhìn thấy đường dẫn /v2 chưa đủ để kết luận mọi tính năng được bổ sung về sau đều được hỗ trợ.

Trong trao đổi giữa nền tảng và broker, cần kiểm tra cơ chế chỉ báo phiên bản mà phiên bản OSB API đang áp dụng, bao gồm header phiên bản giao thức nếu có trong hợp đồng triển khai. Một header phiên bản không phải cơ chế tự động biến broker cũ thành broker mới; nó chỉ giúp hai phía xác định ngữ cảnh giao thức và áp dụng quy tắc tương ứng.

Spring Cloud Open Service Broker là thư viện triển khai phía server. Phiên bản thư viện có thể hỗ trợ một tập tính năng cụ thể của OSB API, có thể bổ sung hỗ trợ sau khi đặc tả phát hành hoặc có thể chưa cung cấp API tiện dụng cho một trường hợp mới. Do đó, phải kiểm tra tài liệu phiên bản Spring Cloud Open Service Broker thực tế của dự án, thay vì suy ra khả năng từ tên thư viện hoặc phiên bản OSB API mong muốn.

## 3. Nhận diện khả năng tùy chọn trong catalog

Catalog là nơi quan trọng để nền tảng biết một service hoặc plan hỗ trợ những khả năng nào. Các cờ capability trong catalog là cam kết về hành vi mà broker cung cấp.

Ví dụ, một service có thể khai báo:

~~~json
{
  "services": [
    {
      "id": "managed-database",
      "name": "managed-database",
      "description": "Cơ sở dữ liệu được quản lý",
      "bindable": true,
      "plan_updateable": true,
      "instances_retrievable": true,
      "bindings_retrievable": false,
      "plans": [
        {
          "id": "standard-plan",
          "name": "standard",
          "description": "Gói tiêu chuẩn",
          "free": false
        }
      ]
    }
  ]
}
~~~

Ví dụ này minh họa ý nghĩa của một số capability, không phải cấu hình mặc định cho mọi broker:

- **bindable** cho biết service có hỗ trợ tạo binding hay không.
- **plan_updateable** cho biết broker hỗ trợ thay đổi plan của service instance theo hợp đồng hay không.
- **instances_retrievable** cho biết broker có hỗ trợ truy xuất thông tin service instance hay không.
- **bindings_retrievable** cho biết broker có hỗ trợ truy xuất thông tin binding hay không.

Các capability này phải được kiểm tra theo schema và phiên bản OSB API cụ thể. Tên trường có thể quen thuộc nhưng không nên sao chép từ một ví dụ trên Internet rồi giả định mọi nền tảng đều gửi các request tương ứng.

Ví dụ, nếu broker khai báo không hỗ trợ truy xuất binding, nền tảng không được dựa vào endpoint truy xuất binding để khôi phục trạng thái. Nếu broker khai báo hỗ trợ update plan, thao tác update vẫn phải tuân thủ điều kiện, schema và chính sách của service plan. Capability không thay thế việc kiểm tra request.

### Trường schema và tham số theo service plan

OSB API có cơ chế mô tả schema cho các tham số tạo service instance, cập nhật instance và tạo binding. Nhờ đó, nền tảng có thể hiểu cấu trúc tham số mà broker mong đợi.

Ví dụ rút gọn về ý tưởng schema:

~~~json
{
  "schemas": {
    "service_instance": {
      "create": {
        "parameters": {
          "type": "object",
          "properties": {
            "database_name": {
              "type": "string"
            },
            "storage_gb": {
              "type": "integer",
              "minimum": 1
            }
          },
          "required": ["database_name"]
        }
      }
    }
  }
}
~~~

Schema mô tả dữ liệu hợp lệ cho một thao tác. Nó không tự tạo ra một endpoint mới và cũng không đảm bảo mọi phiên bản nền tảng đều hiển thị hoặc kiểm tra schema theo cùng một cách. Broker vẫn phải xác thực tham số ở phía server, vì client có thể gửi request trực tiếp hoặc bỏ qua giao diện người dùng của nền tảng.

## 4. Ví dụ về tính năng được chuẩn hóa nhưng chỉ áp dụng khi có hỗ trợ

Một số tính năng minh họa rõ sự khác biệt giữa hợp đồng đã phát hành và khả năng triển khai thực tế.

### Cập nhật service instance

OSB API định nghĩa thao tác update cho service instance. Tuy nhiên, không phải mọi service đều cho phép đổi plan hoặc thay đổi cấu hình sau khi provision.

Broker cần khai báo khả năng cập nhật phù hợp, mô tả schema tham số update nếu áp dụng và từ chối các thay đổi không được hỗ trợ theo đúng quy tắc của giao thức. Nếu plan không thể thay đổi, client không nên đưa ra lựa chọn chuyển plan như thể thao tác đó luôn khả dụng.

### Truy xuất service instance và binding

Một số nền tảng cần đọc lại thông tin instance hoặc binding để đối soát trạng thái. Đây là khả năng riêng cần được broker công bố và triển khai theo hợp đồng tương ứng. Không nên nhầm việc broker lưu dữ liệu nội bộ với việc broker hỗ trợ endpoint truy xuất công khai của OSB API.

### Xử lý bất đồng bộ

Provision hoặc deprovision có thể mất nhiều thời gian vì broker phải gọi API nhà cung cấp, chờ tạo tài nguyên hoặc thực hiện nhiều bước. OSB API có cơ chế cho phép nền tảng chấp nhận thao tác chưa hoàn tất ngay, sau đó truy vấn trạng thái qua last operation.

Ví dụ:

~~~http
PUT /v2/service_instances/instance-123?accepts_incomplete=true
Content-Type: application/json
~~~

Nếu broker chấp nhận xử lý bất đồng bộ, response sẽ cho nền tảng biết thao tác đã được tiếp nhận và cung cấp thông tin cần thiết để theo dõi. Nền tảng tiếp tục truy vấn endpoint last operation theo hợp đồng. Nếu client không cho phép thao tác bất đồng bộ mà broker không thể hoàn tất đồng bộ, broker phải trả lỗi phù hợp thay vì giả vờ đã provision thành công.

Hỗ trợ bất đồng bộ không chỉ là trả về HTTP 202. Broker còn phải lưu operation, duy trì trạng thái nhất quán, xử lý retry và trả kết quả cuối cùng có thể quan sát được.

### Yêu cầu tích hợp ở tầng binding

Một service có thể cần cung cấp thêm khả năng như syslog drain, route forwarding hoặc volume mount. Các khả năng này gắn với yêu cầu và dữ liệu binding được đặc tả. Chúng chỉ có ý nghĩa khi broker, nền tảng và môi trường chạy cùng hỗ trợ đúng hợp đồng.

Ví dụ, một broker trả thông tin volume mount không có nghĩa mọi nền tảng đều biết cách gắn volume đó vào workload. Tương tự, việc khai báo một capability không thay thế bước kiểm tra quyền, cấu hình và điều kiện của môi trường triển khai.

### Thông tin bảo trì và cập nhật plan

Một số phiên bản OSB API bổ sung cách mô tả thông tin bảo trì của plan, chẳng hạn thông tin phiên bản bảo trì hoặc thay đổi cần thiết khi cập nhật. Đây là ví dụ điển hình của trường dữ liệu phụ thuộc phiên bản: broker chỉ nên phát ra trường đó khi phiên bản giao thức và các thành phần liên quan hiểu được ngữ nghĩa của nó.

Không được xem một trường mới là dữ liệu trang trí. Nền tảng có thể dùng nó để quyết định thời điểm, cách thức hoặc điều kiện thực hiện cập nhật tài nguyên.

## 5. Phân biệt tính năng chuẩn với phần mở rộng riêng của broker

OSB API cho phép broker nhận các tham số tùy chỉnh trong những phần request được đặc tả dành cho cấu hình riêng của service. Ví dụ, broker PostgreSQL có thể nhận database name, collation hoặc giới hạn kết nối. Broker Redis có thể nhận cấu hình persistence hoặc quota.

Các tham số nghiệp vụ này không tự động trở thành tính năng chuẩn của OSB API. Chúng là hợp đồng cấu hình của service do broker cung cấp. Broker cần mô tả schema, giá trị mặc định, giới hạn và ảnh hưởng của từng tham số.

Ví dụ:

~~~json
{
  "parameters": {
    "database_name": "orders",
    "storage_gb": 50,
    "backup_window": "02:00-03:00"
  }
}
~~~

Ở đây, OSB API chuẩn hóa vị trí và cách truyền object parameters trong request. Ý nghĩa của database_name, storage_gb và backup_window do broker định nghĩa. Một broker khác có thể không nhận các trường này hoặc dùng tên và quy tắc khác.

Một phần mở rộng riêng có thể xuất hiện dưới dạng:

- Tham số cấu hình đặc thù của nhà cung cấp.
- Header hoặc metadata chỉ có ý nghĩa trong một môi trường.
- Endpoint quản trị bổ sung ngoài OSB API.
- Trường dữ liệu tùy chỉnh trong response mà client riêng biết cách xử lý.
- Quy tắc vận hành riêng như lịch bảo trì, quota hoặc chính sách backup.

Không nên đặt một trường tùy chỉnh vào vị trí mà đặc tả dành cho trường chuẩn rồi kỳ vọng nền tảng khác hiểu nó. Khi cần mở rộng, hãy dùng cơ chế mở rộng được hợp đồng cho phép, tài liệu hóa rõ phạm vi, version và hành vi khi client không hỗ trợ.

## 6. Ma trận tương thích có ba lớp

Một tính năng chỉ dùng được ổn định khi cả ba lớp liên quan đều tương thích:

| Lớp | Cần kiểm tra | Ví dụ câu hỏi |
|---|---|---|
| OSB API | Phiên bản đặc tả và capability có liên quan | Trường hoặc thao tác này có thuộc phiên bản giao thức đang dùng không? |
| Spring Cloud Open Service Broker | Phiên bản thư viện và API lập trình | Thư viện có model, handler và serializer hỗ trợ tính năng này không? |
| Nền tảng triển khai | Phiên bản và cách tích hợp của Cloud Foundry, Kubernetes hoặc nền tảng khác | Nền tảng có gửi request, đọc capability và xử lý response này không? |

Ví dụ, đặc tả OSB API có thể mô tả một trường mới. Nhưng nếu phiên bản Spring Cloud Open Service Broker của ứng dụng chưa ánh xạ trường đó, broker có thể không đọc hoặc phát dữ liệu đúng cách. Ngược lại, framework có thể cung cấp một API lập trình mới nhưng nền tảng cũ không gửi request hoặc không hiểu response tương ứng.

Với Kubernetes, cần xác định rõ cơ chế tích hợp đang dùng. Kubernetes Service và DNS phục vụ discovery; operator, controller hoặc cơ chế service binding có thể quản lý tài nguyên theo mô hình riêng. Không nên mặc định một cụm Kubernetes bất kỳ có sẵn client OSB API hoặc hỗ trợ mọi capability mà broker công bố.

Với Cloud Foundry, cần đối chiếu phiên bản nền tảng, quy trình đăng ký broker và tập tính năng OSB API mà nền tảng thực sự hỗ trợ. Tên nền tảng không đủ để xác định mức tương thích nếu chưa biết phiên bản và cấu hình triển khai.

## 7. Cách kiểm tra một tính năng trước khi triển khai

Khi nhận yêu cầu thêm một tính năng, hãy kiểm tra theo trình tự sau:

1. **Xác định tên và ngữ nghĩa chính xác.** Ghi rõ endpoint, trường, capability hoặc hành vi đang cần hỗ trợ. Tránh dùng tên gọi chung như “hỗ trợ update” nếu chưa biết update plan, tham số hay metadata nào.
2. **Tìm bản đặc tả chính thức đầu tiên có định nghĩa tính năng.** Kiểm tra release note và schema của phiên bản đó. Xác định tính năng là bắt buộc, tùy chọn hay chỉ là khuyến nghị.
3. **Kiểm tra phiên bản giao thức của nền tảng.** Xác định header phiên bản, request mẫu và response mà nền tảng gửi hoặc mong đợi.
4. **Kiểm tra phiên bản Spring Cloud Open Service Broker.** Đọc tài liệu đúng phiên bản đang dùng để xác nhận model, handler và cách serialize/deserialize.
5. **Kiểm tra capability trong catalog.** Chỉ công bố khả năng khi broker triển khai đầy đủ và có thể duy trì hành vi trong toàn bộ vòng đời.
6. **Kiểm tra phần mở rộng riêng.** Xác định client nào hiểu dữ liệu, cách version hóa, cách xử lý khi trường không được nhận diện và cách tránh xung đột với trường chuẩn.
7. **Viết kiểm thử hợp đồng.** Kiểm tra request/response, HTTP status, header, trạng thái đồng bộ hoặc bất đồng bộ, retry và các trường hợp broker không hỗ trợ tính năng.
8. **Triển khai tương thích ngược.** Khi thêm trường hoặc capability, bảo đảm client cũ vẫn có hành vi hợp lệ; không thay đổi ngữ nghĩa trường cũ một cách âm thầm.

Một bảng theo dõi tính năng giúp nhóm phát triển tránh nhầm lẫn:

| Tính năng | Phiên bản OSB API | Hỗ trợ của framework | Hỗ trợ nền tảng | Trạng thái dự án |
|---|---|---|---|---|
| Catalog và provision | Xác nhận theo baseline dự án | Đã kiểm tra | Đã kiểm tra | Đã xác nhận |
| Provision bất đồng bộ | Xác nhận phiên bản và quy tắc | Đã kiểm tra handler/trạng thái | Đã kiểm tra polling | Đã xác nhận |
| Update plan | Xác nhận capability và schema | Đã kiểm tra | Đã kiểm tra | Tùy service |
| Retrieve binding | Xác nhận capability | Đã kiểm tra endpoint | Đã kiểm tra | Có thể không hỗ trợ |
| Trường bảo trì mới | Kiểm tra phiên bản bổ sung | Kiểm tra model/serialization | Kiểm tra cách sử dụng | Chưa bật nếu thiếu tương thích |
| Tham số riêng của broker | Theo hợp đồng broker | Kiểm tra binding dữ liệu | Cần client hiểu tham số | Tài liệu hóa riêng |

Các trạng thái trong bảng là ví dụ về cách quản lý công việc. Nhóm dự án cần điền phiên bản và bằng chứng kiểm thử thực tế, không sao chép trạng thái minh họa thành kết quả đã xác nhận.

## 8. Ví dụ: thêm một capability update plan an toàn

Giả sử broker hiện cung cấp một plan database tiêu chuẩn. Đội phát triển muốn cho phép nền tảng nâng cấp instance sang plan lớn hơn.

Trước tiên, cần xác nhận phiên bản OSB API mà nền tảng hỗ trợ có định nghĩa đúng hành vi update cần dùng hay không. Tiếp theo, kiểm tra phiên bản Spring Cloud Open Service Broker có hỗ trợ xử lý update và dữ liệu liên quan hay không. Cuối cùng, xác định nền tảng có đọc capability update plan từ catalog và gửi request update đúng định dạng không.

Nếu cả ba lớp tương thích, broker mới công bố capability tương ứng. Khi nhận request, broker cần:

- Xác thực instance tồn tại và thuộc đúng service.
- Kiểm tra plan đích có thuộc service đó và được phép chuyển đổi.
- Kiểm tra các tham số update theo schema và chính sách.
- Xác định thao tác có thể hoàn tất đồng bộ hay cần xử lý bất đồng bộ.
- Lưu operation và trạng thái trước khi gọi hệ thống quản trị bên ngoài nếu cần.
- Xử lý retry idempotent để không nâng cấp tài nguyên nhiều lần.
- Chỉ báo thành công khi nhà cung cấp xác nhận trạng thái mong muốn.
- Trả lỗi có thể xử lý khi plan đích không hợp lệ hoặc nhà cung cấp từ chối thay đổi.

Nếu một trong ba lớp chưa hỗ trợ, broker không nên quảng bá capability như thể tính năng đã sẵn sàng. Có thể triển khai sau một cờ cấu hình hoặc trong môi trường thử nghiệm, nhưng cần kiểm soát rõ client nào được phép sử dụng và không làm sai hợp đồng công khai.

## 9. Những lỗi thường gặp khi quản lý phiên bản

**Dùng tài liệu phiên bản mới để viết code trên thư viện cũ.** Tài liệu mới có thể nhắc đến class hoặc trường chưa tồn tại trong dependency hiện tại. Hãy mở đúng tài liệu theo phiên bản framework của dự án và kiểm tra API thực tế trước khi triển khai.

**Cho rằng tính năng có trong đặc tả thì mọi broker phải hỗ trợ.** Nhiều capability là tùy chọn. Broker phải công bố đúng khả năng và nền tảng phải tôn trọng thông tin đó.

**Coi tham số riêng là trường chuẩn.** Một tham số do broker tự định nghĩa chỉ có ý nghĩa trong hợp đồng của broker đó. Client không nên gửi tham số này đến broker khác nếu chưa có thỏa thuận tương thích.

**Bật capability trước khi hoàn tất triển khai.** Công bố một capability tạo kỳ vọng cho nền tảng. Nếu handler, persistence, retry hoặc tích hợp nhà cung cấp chưa sẵn sàng, thao tác có thể thất bại giữa chừng và làm trạng thái tài nguyên không nhất quán.

**Chỉ kiểm thử broker mà không kiểm thử nền tảng.** Một response hợp lệ theo broker chưa đảm bảo nền tảng sẽ hiểu hoặc sử dụng nó. Kiểm thử tích hợp phải xác nhận cả request do nền tảng gửi và cách nền tảng xử lý response.

**Nâng phiên bản thư viện mà không kiểm tra thay đổi tương thích.** Phiên bản mới có thể thay đổi API lập trình, dependency hoặc cách ánh xạ dữ liệu. Cần đọc release note, kiểm thử hợp đồng và xác nhận cấu hình trước khi nâng cấp môi trường sản xuất.

## 10. Nguyên tắc triển khai trong dự án Spring Cloud Service Broker

Với ứng dụng xây dựng bằng Spring Cloud Open Service Broker, hãy quản lý phiên bản giao thức và phiên bản thư viện như hai thông tin riêng. Ghi lại phiên bản đặc tả mà broker cam kết hỗ trợ, phiên bản framework đang dùng và phiên bản nền tảng đã kiểm thử.

Catalog phải phản ánh chính xác những gì handler có thể thực hiện. Khi bổ sung một capability, cập nhật đồng bộ phần mô tả catalog, xử lý nghiệp vụ, lưu trạng thái, bảo mật, tài liệu tích hợp và kiểm thử hợp đồng. Nếu tính năng cần tham số riêng, hãy mô tả schema và giới hạn rõ ràng.

Với thao tác bất đồng bộ, lưu trạng thái operation bền vững và bảo đảm endpoint last operation phản ánh đúng tiến độ. Với binding, bảo vệ credentials và kiểm tra quyền thu hồi. Với update, kiểm tra khả năng chuyển đổi plan và xử lý lỗi từ nhà cung cấp. Với phần mở rộng riêng, version hóa hợp đồng và giữ cho client không hỗ trợ vẫn xử lý được theo quy tắc đã công bố.

Sự tương thích của một tính năng không chỉ phụ thuộc vào việc nó có tên trong đặc tả. Nó phụ thuộc vào phiên bản giao thức, mức hỗ trợ của framework, khả năng của nền tảng và việc broker thực sự triển khai đúng hợp đồng. Kiểm tra đủ các lớp này trước khi công bố capability sẽ giúp service broker hoạt động ổn định và tránh tạo ra những cam kết mà hệ thống chưa thể thực hiện.


# Các bên tham gia: nền tảng, broker, nhà cung cấp dịch vụ và ứng dụng

Open Service Broker API (OSB API) chuẩn hóa cách một **nền tảng (platform)** yêu cầu **service broker** cung cấp và quản lý các dịch vụ đi kèm ứng dụng. Nhờ hợp đồng HTTP(S) thống nhất, nền tảng có thể hiển thị danh mục dịch vụ, tạo service instance, cấp thông tin kết nối cho ứng dụng và thu hồi tài nguyên mà không cần biết chi tiết cách từng nhà cung cấp triển khai dịch vụ.

Để hiểu đúng kiến trúc, cần phân biệt bốn vai trò: nền tảng điều phối vòng đời; broker tiếp nhận yêu cầu theo OSB API; nhà cung cấp tạo và vận hành dịch vụ thực tế; ứng dụng sử dụng dịch vụ thông qua thông tin binding. Trong một số hệ thống, broker và nhà cung cấp có thể do cùng một tổ chức hoặc cùng một ứng dụng triển khai, nhưng trách nhiệm của hai vai trò vẫn khác nhau về mặt kiến trúc.

## Bức tranh tổng thể

~~~mermaid
flowchart LR
    U["Nhà phát triển / vận hành"] -->|"Chọn dịch vụ, plan, ứng dụng"| P["Nền tảng"]
    P <-->|"OSB API: catalog, provision, bind, update, delete"| B["Service broker"]
    B <-->|"API, SDK hoặc giao thức nội bộ"| S["Nhà cung cấp dịch vụ"]
    P -->|"Phân phối cấu hình binding"| A["Ứng dụng"]
    A -->|"Kết nối tới endpoint dịch vụ"| S
~~~

Luồng điều khiển thường đi từ nền tảng qua broker đến nhà cung cấp. Sau khi tài nguyên sẵn sàng, nền tảng chuyển thông tin binding cho ứng dụng. Khi chạy, ứng dụng thường kết nối tới endpoint của dịch vụ hoặc gateway do nhà cung cấp công bố; ứng dụng không cần gọi API quản trị của broker trong mỗi lần truy cập dữ liệu.

| Thành phần | Trách nhiệm chính | Thông tin hoặc tài nguyên thường quản lý |
|---|---|---|
| Nền tảng | Cung cấp trải nghiệm cho người dùng, gọi broker và điều phối vòng đời | Broker đã đăng ký, service instance ID, binding ID, trạng thái yêu cầu, cấu hình được phân phối cho ứng dụng |
| Service broker | Triển khai hợp đồng OSB API và chuyển yêu cầu thành thao tác cụ thể | Catalog, service plan, ánh xạ ID của OSB sang tài nguyên phía provider, trạng thái thao tác |
| Nhà cung cấp dịch vụ | Tạo, vận hành và bảo trì dịch vụ thực tế | Database, cluster, queue, bucket, tài khoản, endpoint và quyền truy cập |
| Ứng dụng | Tiêu thụ dịch vụ đã được cấp | Endpoint, credential, chứng thư hoặc cấu hình kết nối nhận qua binding |

## 1. Nền tảng (Platform)

Nền tảng là bên **gọi API của service broker**. Đây có thể là một nền tảng PaaS, marketplace nội bộ, bộ điều khiển quản lý dịch vụ hoặc một lớp tích hợp đứng giữa người dùng và broker.

Nền tảng thường đảm nhận các công việc sau:

- **Đăng ký và kết nối broker:** lưu địa chỉ broker, cấu hình xác thực, kiểm tra khả năng kết nối và gửi header phiên bản OSB API phù hợp.
- **Đọc catalog:** gọi **GET /v2/catalog**, sau đó hiển thị service offering và các plan mà broker công bố. Người dùng có thể chọn một dịch vụ và cấu hình phù hợp với nhu cầu.
- **Điều phối provision:** tạo yêu cầu cấp phát service instance bằng ID ổn định, gửi service ID, plan ID, thông tin ngữ cảnh và tham số cấu hình.
- **Theo dõi thao tác:** nhận kết quả đồng bộ hoặc tiếp tục polling endpoint **last_operation** nếu broker xử lý bất đồng bộ.
- **Quản lý binding:** yêu cầu broker tạo hoặc xóa binding khi ứng dụng cần sử dụng hay ngừng sử dụng service instance.
- **Phân phối cấu hình:** chuyển credential và thông tin kết nối đến ứng dụng qua cơ chế cấu hình của nền tảng.
- **Áp dụng chính sách:** kiểm soát người dùng được phép tạo dịch vụ nào, giới hạn số lượng, chi phí, vùng triển khai và quyền truy cập.

Nền tảng giữ vai trò điều phối và cung cấp trải nghiệm thống nhất. Nó không nhất thiết phải biết cách tạo database, queue hay bucket ở hạ tầng bên dưới. Chi tiết đó thuộc về broker và nhà cung cấp.

### Ví dụ trên Cloud Foundry và Kubernetes

Trên Cloud Foundry, người dùng có thể chọn dịch vụ từ marketplace hoặc dùng CLI để tạo service instance và bind instance vào ứng dụng. Nền tảng gọi broker theo OSB API, sau đó cung cấp thông tin binding cho ứng dụng, thường thông qua biến môi trường **VCAP_SERVICES**.

Trong môi trường Kubernetes, cần xác định rõ thành phần nào đóng vai trò nền tảng OSB. Kubernetes API server tự thân không đồng nghĩa với một OSB platform. Một controller, service catalog hoặc lớp tích hợp có thể gọi broker, theo dõi trạng thái yêu cầu và đưa thông tin binding vào Kubernetes Secret, volume hoặc cơ chế cấu hình tương ứng. Cách triển khai cụ thể phụ thuộc vào thành phần tích hợp được sử dụng.

## 2. Service broker

Service broker là **đầu mối triển khai OSB API**. Nền tảng gửi yêu cầu tới broker; broker xác thực và kiểm tra yêu cầu, áp dụng quy tắc nghiệp vụ, sau đó gọi API hoặc SDK của nhà cung cấp để thực hiện công việc.

Broker không chỉ là một proxy chuyển tiếp HTTP. Nó còn chịu trách nhiệm quản lý vòng đời, ánh xạ định danh, lưu trạng thái, xử lý lỗi và bảo đảm các yêu cầu lặp lại không tạo ra tài nguyên ngoài ý muốn.

### Các trách nhiệm của broker

**Công bố catalog.** Broker trả về danh sách service offering và plan mà nó hỗ trợ. Catalog cho nền tảng biết tên dịch vụ, mô tả, khả năng binding và những plan có thể lựa chọn. Mỗi offering và plan có ID riêng để các yêu cầu sau tham chiếu chính xác.

**Cấp phát và cập nhật service instance.** Khi nhận yêu cầu provision, broker kiểm tra service ID, plan ID, tham số, ngữ cảnh và quyền thực hiện. Sau đó broker yêu cầu provider tạo tài nguyên, ví dụ database hoặc message queue. Khi nhận yêu cầu update, broker xác định thay đổi được phép và chuyển đổi yêu cầu thành thao tác cập nhật ở provider.

**Tạo và thu hồi binding.** Khi nền tảng yêu cầu bind, broker có thể tạo user database, cấp token, tạo tài khoản dịch vụ hoặc chuẩn bị cấu hình kết nối. Khi unbind, broker thu hồi credential hoặc quyền truy cập tương ứng. Việc unbind thường chỉ thu hồi quyền của một consumer; nó không đồng nghĩa với xóa toàn bộ service instance.

**Deprovision.** Khi nền tảng yêu cầu xóa service instance, broker phối hợp với provider để giải phóng tài nguyên đã cấp phát và cập nhật trạng thái nội bộ. Đây là thao tác có ảnh hưởng đến dữ liệu hoặc tài nguyên thực tế, nên cần kiểm tra định danh và chính sách trước khi thực hiện.

**Lưu trạng thái và xử lý bất đồng bộ.** Broker lưu quan hệ giữa ID do nền tảng gửi và ID tài nguyên do provider trả về. Nếu một thao tác mất nhiều thời gian, broker có thể nhận yêu cầu, ghi nhận công việc, trả về **202 Accepted** và có thể kèm mã operation rồi xử lý ở background. Nền tảng tiếp tục hỏi **last_operation** cho đến khi trạng thái là **succeeded** hoặc **failed**.

**Bảo đảm tính lặp an toàn (idempotency).** Mạng có thể gián đoạn sau khi provider đã tạo tài nguyên nhưng trước khi nền tảng nhận được phản hồi. Khi nền tảng gửi lại yêu cầu, broker phải dùng instance ID hoặc binding ID đã nhận để tìm trạng thái hiện có và xử lý yêu cầu lặp một cách an toàn. Không được mặc định rằng mỗi lần nhận request là phải tạo một tài nguyên mới.

### Các endpoint OSB API thường gặp

| Nghiệp vụ | HTTP method và endpoint | Ý nghĩa |
|---|---|---|
| Đọc catalog | **GET /v2/catalog** | Nền tảng lấy service offering và plan |
| Provision | **PUT /v2/service_instances/{instance_id}** | Tạo service instance |
| Update | **PATCH /v2/service_instances/{instance_id}** | Cập nhật cấu hình hoặc plan nếu được hỗ trợ |
| Poll trạng thái instance | **GET /v2/service_instances/{instance_id}/last_operation** | Lấy trạng thái provision, update hoặc deprovision bất đồng bộ |
| Bind | **PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}** | Tạo thông tin truy cập cho consumer |
| Poll trạng thái binding | **GET /v2/service_instances/{instance_id}/service_bindings/{binding_id}/last_operation** | Theo dõi bind hoặc unbind bất đồng bộ |
| Unbind | **DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id}** | Thu hồi binding |
| Deprovision | **DELETE /v2/service_instances/{instance_id}** | Giải phóng service instance |

Các ID trong URL có ý nghĩa khác nhau. **instance_id** nhận diện một service instance xuyên suốt vòng đời; **binding_id** nhận diện một lần cấp quyền truy cập cụ thể của consumer vào instance đó. Broker cần lưu ánh xạ các ID này với tài nguyên tương ứng ở provider.

Không phải service nào cũng cần binding. Broker công bố khả năng này trong catalog bằng thuộc tính **bindable**. Nếu offering hoặc plan không hỗ trợ binding, nền tảng không nên gửi yêu cầu bind cho dịch vụ đó.

## 3. Nhà cung cấp dịch vụ (Service Provider)

Nhà cung cấp dịch vụ là hệ thống thực sự cung cấp năng lực mà ứng dụng cần sử dụng. Ví dụ:

- Hệ quản trị cơ sở dữ liệu PostgreSQL hoặc MySQL.
- Cụm message broker như RabbitMQ hoặc Kafka.
- Dịch vụ lưu trữ object.
- Dịch vụ tìm kiếm, cache hoặc quan sát hệ thống.
- Một dịch vụ SaaS bên ngoài có API quản trị và API sử dụng riêng.

Provider chịu trách nhiệm tạo và vận hành tài nguyên, bảo đảm tài nguyên hoạt động, thực thi giới hạn của plan, quản lý dung lượng và cung cấp endpoint để consumer truy cập. Provider có thể nằm trong cùng hạ tầng với broker hoặc là dịch vụ cloud bên ngoài.

### Broker và provider khác nhau ở đâu?

Hai vai trò này thường bị nhầm lẫn vì chúng có thể cùng thuộc một tổ chức. Hãy phân biệt theo loại yêu cầu mà mỗi bên xử lý:

- Broker hiểu OSB API, service ID, plan ID, instance ID và binding ID. Nó biết nền tảng đang yêu cầu nghiệp vụ nào và phải trả về phản hồi theo hợp đồng OSB.
- Provider hiểu API quản trị riêng của sản phẩm, loại tài nguyên, cấu hình hạ tầng và trạng thái vận hành. Provider không bắt buộc phải hiểu OSB API.
- Broker chuyển yêu cầu từ mô hình chung của nền tảng sang mô hình cụ thể của provider. Ví dụ, plan **small** có thể được ánh xạ thành một cấu hình database với giới hạn CPU, RAM và dung lượng nhất định.

Vì vậy, OSB API chuẩn hóa giao tiếp **giữa platform và broker**. Nó không yêu cầu mọi provider phải triển khai trực tiếp OSB API. Một broker có thể tích hợp với nhiều provider khác nhau; ngược lại, một provider có thể được tiếp cận qua nhiều broker hoặc nền tảng.

## 4. Ứng dụng (Application)

Ứng dụng là consumer cuối cùng của service. Ứng dụng thường không trực tiếp gọi các endpoint quản trị của broker để provision hoặc deprovision tài nguyên. Nhà phát triển hoặc người vận hành yêu cầu nền tảng tạo dịch vụ và bind dịch vụ đó vào ứng dụng; nền tảng phối hợp với broker để hoàn tất quy trình.

Sau khi binding thành công, nền tảng cung cấp thông tin cần thiết cho ứng dụng, có thể gồm:

- Địa chỉ host, port hoặc URI của dịch vụ.
- Tên database, queue, bucket hoặc resource.
- Username, password, access token hoặc credential tương đương.
- Chứng thư TLS, thông tin xác thực client hoặc tham số kết nối khác.

Ứng dụng đọc các giá trị này từ cơ chế cấu hình mà nền tảng cung cấp, khởi tạo client và kết nối đến dịch vụ. Ví dụ, ứng dụng Spring Boot có thể dùng URI và credential để cấu hình DataSource cho PostgreSQL. Ứng dụng không cần biết broker đã gọi API nào ở provider hoặc database được tạo trên cụm máy chủ nào.

Một service instance có thể được bind cho nhiều ứng dụng nếu offering cho phép. Mỗi binding có thể có credential riêng, nhờ đó broker có thể thu hồi quyền của một ứng dụng mà không phải xóa service instance đang được ứng dụng khác sử dụng.

## 5. Phân biệt offering, plan, instance và binding

Bốn khái niệm này mô tả bốn cấp độ khác nhau trong vòng đời dịch vụ:

| Khái niệm | Ý nghĩa | Ví dụ PostgreSQL |
|---|---|---|
| Service offering | Loại dịch vụ được broker công bố | PostgreSQL Database |
| Service plan | Một cấu hình hoặc mức dịch vụ của offering | **small**: dung lượng và tài nguyên giới hạn |
| Service instance | Tài nguyên cụ thể được tạo từ một offering và plan | Database **orders-prod** được cấp phát cho một nhóm |
| Service binding | Thông tin hoặc quyền truy cập để một consumer sử dụng instance | User **orders_app** cùng URI và password |

Có thể hình dung catalog như danh mục sản phẩm, plan như cấu hình sản phẩm, instance như tài nguyên đã đặt mua và binding như thông tin cấp quyền sử dụng tài nguyên đó.

Ví dụ catalog rút gọn dưới đây minh họa một offering có thể bind và một plan. Các ID chỉ là giá trị minh họa:

~~~json
{
  "services": [
    {
      "id": "service-postgresql",
      "name": "postgresql",
      "description": "Cơ sở dữ liệu PostgreSQL được quản lý",
      "bindable": true,
      "plans": [
        {
          "id": "plan-small",
          "name": "small",
          "description": "Plan thử nghiệm với tài nguyên giới hạn"
        }
      ]
    }
  ]
}
~~~

Catalog mô tả những gì broker có thể cung cấp; nó chưa tạo ra database nào. Tài nguyên chỉ xuất hiện khi nền tảng gửi yêu cầu provision và broker thực hiện yêu cầu đó thành công.

## 6. Luồng tương tác từ catalog đến khi ứng dụng sử dụng dịch vụ

Giả sử nhóm phát triển có ứng dụng quản lý đơn hàng và muốn sử dụng PostgreSQL.

1. **Nền tảng đọc catalog.** Nền tảng gọi **GET /v2/catalog**. Broker trả về offering PostgreSQL và plan **small**.
2. **Người dùng chọn dịch vụ.** Nhà phát triển chọn offering, plan và ứng dụng cần sử dụng. Nền tảng tạo một **instance_id** duy nhất cho yêu cầu.
3. **Nền tảng yêu cầu provision.** Nền tảng gọi **PUT /v2/service_instances/{instance_id}** với service ID, plan ID và các tham số cần thiết. Nếu nền tảng chấp nhận thao tác bất đồng bộ, request có thể kèm query parameter **accepts_incomplete=true**.
4. **Broker gọi provider.** Broker kiểm tra request, lưu trạng thái ban đầu và gọi API quản trị của provider để tạo database. Provider có thể hoàn tất ngay hoặc cần thời gian xử lý.
5. **Nền tảng theo dõi kết quả.** Nếu broker trả **202 Accepted**, nền tảng dùng endpoint **last_operation** để polling. Broker cập nhật trạng thái thành **in progress**, **succeeded** hoặc **failed**. Nền tảng chỉ tiếp tục bước phụ thuộc khi thao tác đạt trạng thái kết thúc phù hợp.
6. **Nền tảng yêu cầu bind.** Khi instance sẵn sàng, nền tảng tạo **binding_id** và gọi endpoint bind. Broker yêu cầu provider tạo user hoặc credential dành cho ứng dụng.
7. **Broker trả thông tin binding.** Broker trả credential và endpoint cần thiết theo hợp đồng OSB API. Nền tảng lưu và phân phối thông tin này bằng cơ chế bảo mật của mình.
8. **Ứng dụng kết nối.** Ứng dụng nhận cấu hình, mở kết nối tới PostgreSQL và bắt đầu xử lý dữ liệu.
9. **Khi ngừng sử dụng.** Nền tảng gọi unbind để broker thu hồi credential của ứng dụng. Khi service instance không còn cần thiết, nền tảng gọi deprovision để broker yêu cầu provider giải phóng database.

~~~mermaid
sequenceDiagram
    actor Dev as Nhà phát triển
    participant P as Nền tảng
    participant B as Service broker
    participant S as Nhà cung cấp
    participant A as Ứng dụng

    Dev->>P: Chọn PostgreSQL và plan small
    P->>B: GET /v2/catalog
    B-->>P: Offering và danh sách plan
    Dev->>P: Yêu cầu tạo service instance
    P->>B: PUT /v2/service_instances/{instance_id}
    B->>S: Tạo database
    S-->>B: Kết quả hoặc yêu cầu đang xử lý
    alt Xử lý bất đồng bộ
        B-->>P: 202 Accepted + operation
        loop Cho đến trạng thái kết thúc
            P->>B: GET .../last_operation
            B-->>P: in progress / succeeded / failed
        end
    else Xử lý đồng bộ
        B-->>P: 201 Created
    end
    P->>B: PUT .../service_bindings/{binding_id}
    B->>S: Tạo user hoặc credential
    S-->>B: Thông tin truy cập
    B-->>P: Binding response
    P-->>A: Cấp cấu hình kết nối an toàn
    A->>S: Kết nối và sử dụng dịch vụ
~~~

### Một request provision minh họa

Phần body của yêu cầu provision có thể chứa các thông tin như sau. Các trường ngữ cảnh cụ thể phụ thuộc vào nền tảng và hợp đồng mà broker hỗ trợ:

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-small",
  "organization_guid": "org-123",
  "space_guid": "space-456",
  "parameters": {
    "database_name": "orders",
    "storage_gb": 20
  }
}
~~~

**accepts_incomplete** là query parameter của request, không phải field trong JSON body. Khi nền tảng gửi giá trị **true** và broker cần xử lý bất đồng bộ, broker có thể trả **202 Accepted**, kèm mã operation nếu broker cung cấp. Nền tảng dùng mã này khi polling trạng thái.

Phản hồi binding có thể chứa cấu trúc credential tương tự ví dụ sau:

~~~json
{
  "credentials": {
    "uri": "postgresql://db.example.internal:5432/orders",
    "username": "orders_app",
    "password": "<secret>"
  }
}
~~~

Giá trị thực phải được bảo vệ như bí mật. Broker và nền tảng không nên ghi password hoặc token vào log thông thường; ứng dụng cũng không nên in credential ra console hoặc đưa vào mã nguồn.

## 7. Trách nhiệm trong Spring Cloud Service Broker

Spring Cloud Open Service Broker cung cấp bộ khung Spring Boot để xây dựng ứng dụng triển khai OSB API. Framework đảm nhiệm phần tích hợp HTTP và mô hình request/response theo hợp đồng; người phát triển tập trung vào catalog, nghiệp vụ vòng đời và kết nối tới provider.

| Thành phần trong Spring Cloud Open Service Broker | Vai trò trong broker |
|---|---|
| **CatalogService** | Cung cấp catalog để nền tảng đọc service offering và plan |
| **ServiceInstanceService** | Xử lý vòng đời service instance như create, update, delete và trạng thái thao tác |
| **ServiceInstanceBindingService** | Xử lý tạo, truy xuất khi được khai báo hỗ trợ, và xóa binding |
| Service definition và plan model | Mô tả offering, khả năng binding và các lựa chọn cấu hình được công bố |
| Request/response model | Chuyển dữ liệu OSB API thành đối tượng Java để xử lý nghiệp vụ |

Một cách tổ chức broker dễ bảo trì là giữ ranh giới rõ ràng giữa các phần:

- **Lớp API/framework:** nhận request OSB, kiểm tra cấu trúc và chuyển dữ liệu vào service tương ứng.
- **Lớp nghiệp vụ broker:** kiểm tra plan, tham số, quyền, trạng thái hiện tại và quy tắc chuyển trạng thái.
- **Lớp tích hợp provider:** gọi API hoặc SDK của PostgreSQL service, cloud vendor hay hệ thống nội bộ.
- **Lớp lưu trữ:** giữ instance ID, binding ID, provider resource ID, operation ID, trạng thái và thông tin cần thiết để phục hồi sau restart.

Ví dụ, khi **ServiceInstanceService** nhận yêu cầu provision, phần nghiệp vụ có thể tạo một bản ghi instance ở trạng thái **PROVISIONING**, ghi nhận công việc cần chạy rồi gọi provider. Nếu provider xử lý lâu, broker trả kết quả bất đồng bộ và tiến trình nền cập nhật trạng thái. Endpoint **last_operation** đọc trạng thái đã lưu để nền tảng biết khi nào có thể tiếp tục.

Với binding, **ServiceInstanceBindingService** có thể yêu cầu provider tạo user riêng cho ứng dụng, lưu ánh xạ binding ID với user đó và trả thông tin kết nối. Khi unbind, broker dùng ánh xạ đã lưu để thu hồi đúng user hoặc credential. Nhờ vậy, việc quản lý binding không phụ thuộc vào việc suy đoán tài nguyên từ tên ứng dụng.

## 8. Ranh giới bảo mật và trạng thái

Mỗi ranh giới giữa các thành phần cần một cách xác thực và quản lý bí mật phù hợp:

- **Nền tảng → broker:** chỉ nền tảng được đăng ký mới được gọi API quản trị. Kết nối cần được bảo vệ bằng HTTPS và cơ chế xác thực mà môi trường triển khai quy định.
- **Broker → provider:** broker sử dụng danh tính dịch vụ có quyền vừa đủ để tạo, cập nhật và xóa tài nguyên. Credential quản trị của provider không được chuyển xuống ứng dụng.
- **Broker → nền tảng → ứng dụng:** credential trong binding chỉ cấp quyền cần thiết cho consumer. Nên ưu tiên credential riêng theo binding nếu provider hỗ trợ, có quy trình xoay vòng và thu hồi rõ ràng.
- **Lưu trữ và log:** bảo vệ dữ liệu nhạy cảm khi lưu; che hoặc loại bỏ secret khỏi log, exception và trace; giới hạn người có thể đọc trạng thái và thông tin binding.

Trạng thái cũng cần có chủ sở hữu rõ ràng. Nền tảng biết request nào đang chờ; broker biết request đó tương ứng với resource ID nào ở provider; provider biết tài nguyên thực tế đang hoạt động hay gặp sự cố. Broker cần lưu đủ dữ liệu để tiếp tục theo dõi sau khi tiến trình khởi động lại. Nếu chỉ giữ operation trong bộ nhớ, một lần restart có thể làm mất khả năng trả lời polling hoặc dẫn đến tạo trùng tài nguyên khi request được gửi lại.

Một quy trình provision an toàn thường có các bước: xác thực request, kiểm tra ID và plan, ghi nhận trạng thái cùng khóa tương quan, gọi provider, lưu provider resource ID và kết quả, sau đó trả response phù hợp. Với thao tác bất đồng bộ, việc ghi nhận operation và cập nhật trạng thái phải nhất quán để endpoint **last_operation** luôn phản ánh tiến độ có thể kiểm chứng.

## 9. Những nhầm lẫn thường gặp

**Nền tảng và ứng dụng có phải cùng một bên không?** Không. Nền tảng điều phối và phân phối cấu hình; ứng dụng tiêu thụ dịch vụ. Người dùng có thể thao tác trên giao diện hoặc CLI của nền tảng, nhưng ứng dụng không vì thế trở thành client quản trị OSB API.

**Broker có phải database hoặc message broker không?** Không nhất thiết. Service broker là thành phần triển khai hợp đồng quản trị dịch vụ. Database hoặc message broker là dịch vụ thực tế do provider vận hành. Từ “broker” trong hai ngữ cảnh có thể giống nhau nhưng chỉ hai vai trò khác nhau.

**Tạo service instance có đồng nghĩa với bind không?** Không. Provision tạo hoặc đặt chỗ tài nguyên. Bind tạo thông tin hoặc quyền truy cập để consumer sử dụng tài nguyên đó. Một số offering không hỗ trợ binding; một số service instance có thể tồn tại mà chưa được bind vào ứng dụng nào.

**Unbind có xóa database không?** Thông thường không. Unbind thu hồi quyền truy cập của một consumer. Deprovision mới là thao tác yêu cầu giải phóng service instance. Broker phải phân biệt hai thao tác để tránh xóa dữ liệu khi một ứng dụng chỉ cần ngừng sử dụng.

**Provider có bắt buộc hiểu OSB API không?** Không. OSB API là hợp đồng giữa platform và broker. Broker có thể gọi API quản trị riêng của provider, SDK, hệ thống điều phối hoặc dịch vụ nội bộ.

## Kết luận

Nền tảng, broker, provider và ứng dụng tạo thành một chuỗi trách nhiệm liên tục. Nền tảng cung cấp trải nghiệm và điều phối; broker thực thi hợp đồng OSB và quản lý vòng đời; provider tạo và vận hành dịch vụ; ứng dụng nhận binding để sử dụng dịch vụ. Khi thiết kế một broker bằng Spring Cloud, việc xác định đúng ranh giới này giúp tổ chức catalog, xử lý provision và binding, lưu trạng thái, phục hồi thao tác bất đồng bộ và bảo vệ credential một cách nhất quán.

## Tài liệu tham khảo

- [Open Service Broker API Specification](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md) — hợp đồng giữa platform và broker, catalog, provision, binding, thao tác bất đồng bộ và polling.
- [Spring Cloud Open Service Broker Reference](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/reference/) — các abstraction Spring Boot cho catalog, service instance và service binding.
- [Open Service Broker API](https://www.openservicebrokerapi.org/) — giới thiệu mục tiêu và hệ sinh thái của OSB API.


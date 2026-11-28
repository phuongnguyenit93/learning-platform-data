# Tách luồng quản lý vòng đời khỏi luồng ứng dụng sử dụng dịch vụ

Trong module **SPRING_CLOUD_SERVICE_BROKER**, service broker được xây dựng theo Open Service Broker API (OSB API) bằng Spring Cloud để công bố catalog, service plan và thực hiện các thao tác cấp phát, cập nhật, thu hồi, binding tài nguyên. Một quyết định kiến trúc quan trọng là tách luồng quản lý vòng đời dịch vụ khỏi luồng ứng dụng sử dụng dịch vụ.

Hai luồng này có mục tiêu, tải xử lý và yêu cầu bảo mật khác nhau. Nền tảng gọi broker để yêu cầu tạo hoặc thay đổi tài nguyên; ứng dụng nhận thông tin kết nối rồi giao tiếp trực tiếp với dịch vụ được cấp phát. Broker điều phối vòng đời và quyền truy cập, còn dịch vụ thực tế xử lý lưu lượng nghiệp vụ.

## 1. Vì sao phải tách hai luồng?

Hãy xét một ứng dụng cần cơ sở dữ liệu PostgreSQL. Khi triển khai, nền tảng yêu cầu broker cấp phát một service instance, sau đó tạo binding để cấp thông tin kết nối cho ứng dụng. Broker có thể gọi API của nhà cung cấp hạ tầng, tạo database, tạo user và trả về endpoint cùng thông tin xác thực. Khi ứng dụng chạy, nó gửi truy vấn SQL trực tiếp đến PostgreSQL.

Nếu mọi truy vấn SQL đều phải đi qua broker, broker sẽ trở thành proxy dữ liệu ngoài ý muốn. Lưu lượng đọc ghi của ứng dụng có thể lớn hơn rất nhiều so với số lần tạo, cập nhật hoặc xóa dịch vụ. Broker khi đó phải gánh thêm yêu cầu về độ trễ, thông lượng, kết nối dài hạn, định tuyến, cân bằng tải và xử lý giao thức riêng của từng loại dịch vụ. Một sự cố ở broker còn có thể làm gián đoạn cả những ứng dụng đang sử dụng các dịch vụ đã được cấp phát thành công.

OSB API giải quyết một bài toán khác: cung cấp giao diện chuẩn để nền tảng yêu cầu broker quản lý dịch vụ. API này là giao diện điều khiển vòng đời, không phải giao thức truy cập dữ liệu nghiệp vụ. Vì vậy, kiến trúc nên giữ broker trên đường điều khiển và để ứng dụng kết nối trực tiếp đến endpoint của dịch vụ.

Việc tách hai luồng đem lại một số lợi ích:

- **Độc lập mở rộng:** broker mở rộng theo số lượng yêu cầu quản lý và tác vụ nền; dịch vụ dữ liệu mở rộng theo tải truy cập của ứng dụng.
- **Giảm độ trễ:** truy vấn và thông điệp của ứng dụng không phải đi qua thêm một lớp trung gian.
- **Giới hạn ảnh hưởng khi có sự cố:** broker tạm ngừng vẫn có thể khiến thao tác cấp phát mới thất bại, nhưng không nhất thiết làm mất kết nối của các ứng dụng đang hoạt động.
- **Phân quyền rõ ràng:** broker có quyền quản lý tài nguyên; ứng dụng chỉ nhận credential với quyền sử dụng cần thiết.
- **Dễ thay đổi nhà cung cấp:** broker có thể thay adapter cấp phát mà không buộc ứng dụng thay đổi cách truy cập, miễn là hợp đồng endpoint và binding được giữ ổn định.

## 2. Hai mặt phẳng kiến trúc

Có thể mô hình hóa hệ thống thành hai mặt phẳng: control plane quản lý vòng đời và data plane phục vụ lưu lượng sử dụng dịch vụ.

| Khía cạnh | Control plane — quản lý vòng đời | Data plane — sử dụng dịch vụ |
|---|---|---|
| Chủ thể gọi | Cloud Foundry, Kubernetes controller hoặc nền tảng tương thích OSB API | Ứng dụng và các thành phần nghiệp vụ |
| Giao tiếp | HTTP API theo OSB API | Giao thức của dịch vụ như SQL, Redis, AMQP hoặc HTTPS |
| Nhiệm vụ | Catalog, provision, update, bind, unbind, deprovision và theo dõi operation | Đọc ghi dữ liệu, gửi nhận thông điệp, gọi API nghiệp vụ |
| Thành phần chính | Broker API, bộ điều phối vòng đời, worker, operation store, provider adapter | Ứng dụng, endpoint dịch vụ, mạng dữ liệu và cơ chế xác thực |
| Nhịp tải | Thường ít yêu cầu hơn nhưng có thể có thao tác kéo dài | Có thể rất lớn, liên tục và nhạy với độ trễ |
| Dữ liệu nhạy cảm | Thông tin quản trị nhà cung cấp, metadata tài nguyên, credential khi tạo binding | Credential được cấp cho ứng dụng và dữ liệu nghiệp vụ |
| Yêu cầu sẵn sàng | Cần sẵn sàng khi nền tảng thực hiện thao tác quản lý | Cần sẵn sàng trong suốt thời gian ứng dụng sử dụng dịch vụ |

### 2.1. Control plane quản lý tài nguyên

Control plane tiếp nhận yêu cầu từ nền tảng, kiểm tra quyền, xác thực service offering và plan, sau đó điều phối thao tác đến hệ thống quản lý tài nguyên tương ứng. Nó lưu trạng thái service instance, binding và operation để có thể xử lý retry, truy vấn trạng thái và phục hồi sau khi tiến trình broker khởi động lại.

Một service instance đại diện cho tài nguyên dịch vụ đã được cấp phát, chẳng hạn một database, một cụm cache hoặc một namespace hàng đợi. Service plan mô tả cấu hình hoặc cấp dịch vụ mà người dùng chọn, ví dụ dung lượng, giới hạn kết nối, vùng triển khai hoặc tính năng được bật.

Binding đại diện cho mối quan hệ giữa service instance và một ứng dụng hoặc một consumer. Khi tạo binding, broker thường cấp một credential riêng và trả về các thông tin cần thiết để consumer kết nối. Tách binding khỏi instance giúp nhiều ứng dụng có thể dùng chung một instance nhưng vẫn có danh tính và quyền truy cập riêng.

### 2.2. Data plane phục vụ ứng dụng

Data plane gồm ứng dụng, endpoint của dịch vụ và đường truyền dữ liệu. Sau khi nhận binding, nền tảng cung cấp thông tin kết nối cho ứng dụng theo cơ chế của nền tảng đó. Ứng dụng đọc endpoint, tên database, username, password, certificate hoặc các thuộc tính tương ứng rồi kết nối trực tiếp.

Trong luồng này, broker không cần nhận truy vấn SQL, lệnh Redis hay thông điệp AMQP. Broker cũng không nên lưu dữ liệu nghiệp vụ chỉ để chuyển tiếp lưu lượng. Nếu một sản phẩm thực sự cần gateway hoặc proxy dữ liệu, thành phần đó nên được thiết kế như một dịch vụ data plane độc lập, có cơ chế mở rộng và vận hành riêng; không nên mặc định biến API quản lý OSB thành proxy.

## 3. Kiến trúc thành phần đề xuất

Một triển khai có thể chia thành các thành phần sau:

1. **Platform client:** Cloud Foundry hoặc controller/operator tích hợp với OSB API. Thành phần này gửi yêu cầu quản lý và nhận kết quả từ broker.
2. **Broker API:** tiếp nhận HTTP request, xác thực nền tảng, kiểm tra phiên bản API, giải mã payload và trả response đúng hợp đồng OSB.
3. **Catalog service:** cung cấp danh sách service offering, plan và metadata mà nền tảng dùng để hiển thị lựa chọn.
4. **Lifecycle coordinator:** kiểm tra điều kiện nghiệp vụ, điều phối provision/update/deprovision và quản lý trạng thái instance.
5. **Binding coordinator:** tạo hoặc thu hồi credential, lưu metadata binding và trả thông tin kết nối cho nền tảng.
6. **Operation store:** lưu operation đang chạy, trạng thái, thời điểm, loại thao tác, số lần thử và thông tin lỗi đã được làm sạch.
7. **Queue hoặc outbox cùng worker:** thực thi những thao tác cần thời gian dài mà không giữ request HTTP mở trong suốt quá trình.
8. **Provider adapter:** chuyển lệnh nghiệp vụ thành thao tác cụ thể trên nhà cung cấp database, cache, message broker hoặc hạ tầng khác.
9. **Secret store:** bảo vệ credential và bí mật quản trị. Tùy mô hình triển khai, bí mật binding có thể được trả về nền tảng để nền tảng lưu trong kho secret của mình.
10. **Data plane endpoint:** endpoint thực tế mà ứng dụng kết nối để sử dụng dịch vụ.

Sơ đồ sau thể hiện ranh giới giữa hai luồng. Đường từ ứng dụng đến endpoint dịch vụ là đường dữ liệu trực tiếp; đường qua broker chỉ phục vụ quản lý và cấp thông tin binding.

~~~mermaid
flowchart LR
    subgraph CP["Control plane — quản lý vòng đời"]
        P["Cloud Foundry / Kubernetes controller"]
        API["Spring Cloud OSB API"]
        CAT["Catalog service"]
        LC["Lifecycle và binding coordinator"]
        DB[("Instance, binding và operation store")]
        Q[["Queue / outbox"]]
        W["Background worker"]
        AD["Provider adapter"]
        PROVIDER["Nhà cung cấp tài nguyên"]
        P --> API
        API --> CAT
        API --> LC
        LC <--> DB
        LC --> Q --> W --> AD --> PROVIDER
        API -->|"Trả binding details / trạng thái"| P
    end

    subgraph DP["Data plane — sử dụng dịch vụ"]
        APP["Ứng dụng"]
        SECRET["Platform Secret / cấu hình runtime"]
        ENDPOINT["Endpoint dịch vụ"]
        APP -->|"Đọc thông tin kết nối"| SECRET
        APP -->|"SQL / Redis / AMQP / HTTPS"| ENDPOINT
    end

    LC -.->|"Cấp hoặc thu hồi credential"| PROVIDER
    P -.->|"Đưa binding vào môi trường ứng dụng"| SECRET
~~~

Trong sơ đồ, provider adapter che giấu khác biệt giữa các nhà cung cấp. Lifecycle coordinator chỉ làm việc với các khái niệm nghiệp vụ như provision, update và deprovision; nó không cần biết chi tiết lệnh CLI hoặc API riêng của từng nhà cung cấp. Đây là ranh giới giúp mở rộng catalog mà không làm broker API phụ thuộc vào một sản phẩm cụ thể.

## 4. Luồng xử lý từ catalog đến ứng dụng đang chạy

### 4.1. Công bố catalog

Nền tảng gọi endpoint catalog, thường là **GET /v2/catalog**, để lấy các service offering và plan mà broker hỗ trợ. Catalog cần mô tả ổn định các thuộc tính như service ID, tên hiển thị, plan ID, đặc tính có thể bind, khả năng cập nhật và các giới hạn liên quan.

Catalog là metadata mô tả khả năng cung cấp dịch vụ. Nó không phải danh sách mọi database hoặc credential đang tồn tại. Thông tin về từng instance được lưu và quản lý riêng trong control plane.

Việc tách catalog khỏi adapter cấp phát giúp broker có thể công bố nhiều plan mà không phải gọi nhà cung cấp mỗi khi nền tảng tải catalog. Nếu metadata được lưu hoặc cache, cần có quy trình cập nhật rõ ràng để tránh công bố plan đã ngừng hỗ trợ.

### 4.2. Cấp phát service instance

Khi người dùng chọn một plan, nền tảng gửi yêu cầu provision đến endpoint instance, ví dụ:

**PUT /v2/service_instances/{instance_id}**

Broker cần thực hiện các bước chính:

1. Xác thực caller và kiểm tra service ID, plan ID có trong catalog.
2. Kiểm tra context của nền tảng để xác định tenant, organization, space hoặc phạm vi sở hữu tương ứng.
3. Kiểm tra instance ID đã được xử lý hay chưa để bảo đảm retry không tạo tài nguyên trùng.
4. Lưu yêu cầu và operation vào kho trạng thái.
5. Thực hiện provision trực tiếp nếu thao tác hoàn tất nhanh, hoặc đưa công việc vào hàng đợi nếu cần xử lý bất đồng bộ.
6. Trả kết quả theo hợp đồng OSB API và cung cấp operation key khi cần theo dõi.

Một số thao tác tạo database hoặc cụm dịch vụ có thể kéo dài do phải gọi nhiều API hạ tầng, chờ tài nguyên được khởi tạo hoặc cấu hình mạng. Khi nền tảng cho phép xử lý bất đồng bộ qua tham số **accepts_incomplete=true**, broker có thể chấp nhận yêu cầu, trả response bất đồng bộ và cho nền tảng truy vấn trạng thái qua endpoint last operation, ví dụ:

**GET /v2/service_instances/{instance_id}/last_operation**

Trạng thái bên ngoài cần được ánh xạ nhất quán thành các giá trị mà OSB API hỗ trợ như **in progress**, **succeeded** hoặc **failed**. Không nên trả **succeeded** ngay khi mới ghi nhận công việc vào queue; chỉ trả thành công khi tài nguyên đã đạt điều kiện sẵn sàng mà broker cam kết.

### 4.3. Tạo binding

Sau khi instance sẵn sàng, nền tảng yêu cầu tạo binding, ví dụ:

**PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}**

Broker kiểm tra instance có tồn tại, có thuộc phạm vi caller được phép quản lý và có hỗ trợ binding hay không. Binding coordinator yêu cầu provider tạo credential hoặc quyền truy cập phù hợp, sau đó lưu metadata liên kết giữa binding ID, instance ID và danh tính consumer.

Response binding thường chứa các thuộc tính kết nối và credential mà ứng dụng cần. Ví dụ với database, dữ liệu có thể gồm hostname, port, database name, username và password. Với message broker, dữ liệu có thể gồm endpoint, virtual host, username, password hoặc certificate. Cấu trúc cụ thể phụ thuộc loại dịch vụ và hợp đồng binding đã công bố.

Credential nên có phạm vi quyền nhỏ nhất đủ cho ứng dụng. Nếu hai ứng dụng cùng dùng một instance, nên cân nhắc tạo hai binding với hai danh tính riêng. Khi một ứng dụng bị gỡ bỏ, broker có thể thu hồi đúng credential của binding đó mà không làm gián đoạn consumer còn lại.

### 4.4. Ứng dụng truy cập data plane

Sau khi nhận response binding, nền tảng đưa thông tin kết nối vào runtime của ứng dụng. Trên Cloud Foundry, thông tin dịch vụ thường được cung cấp trong cấu hình môi trường như **VCAP_SERVICES**. Với tích hợp Kubernetes, controller/operator có thể chuyển thông tin binding thành Kubernetes Secret hoặc một tài nguyên cấu hình tương đương.

Ứng dụng đọc thông tin kết nối và tạo client đến endpoint dịch vụ. Ví dụ:

~~~java
String jdbcUrl = environment.getRequiredProperty("SERVICE_JDBC_URL");
String username = environment.getRequiredProperty("SERVICE_USERNAME");
String password = environment.getRequiredProperty("SERVICE_PASSWORD");

DataSource dataSource = createDataSource(jdbcUrl, username, password);
~~~

Đoạn mã chỉ minh họa cách ứng dụng lấy cấu hình runtime; trong hệ thống thực tế, nên dùng cơ chế cấu hình và quản lý secret phù hợp với framework đang chạy. Ứng dụng không cần gọi broker mỗi khi thực hiện truy vấn. Nếu endpoint hoặc credential thay đổi, việc cập nhật cấu hình cần đi qua quy trình rotation/rebind hoặc cơ chế đồng bộ mà nền tảng và broker đã thống nhất.

### 4.5. Cập nhật, unbind và thu hồi instance

Khi plan hoặc tham số cấu hình thay đổi, nền tảng gửi yêu cầu update. Broker kiểm tra thay đổi có được plan cho phép, có tương thích với tài nguyên hiện tại và có cần thao tác dài hay không. Những thay đổi có nguy cơ phá vỡ kết nối cần có quy trình chuyển đổi, kiểm tra khả năng tương thích và kế hoạch phục hồi.

Khi một consumer không còn cần dịch vụ, nền tảng gửi yêu cầu unbind. Broker thu hồi credential của binding và cập nhật trạng thái binding. Khi service instance không còn được sử dụng, nền tảng gửi yêu cầu deprovision để broker giải phóng tài nguyên. Broker nên kiểm tra các binding còn tồn tại theo chính sách và hợp đồng API, tránh xóa instance khi vẫn còn consumer hợp lệ.

Thứ tự thông thường là thu hồi các binding cần thiết trước, sau đó mới deprovision instance. Hai thao tác này phải được ghi nhận độc lập để có thể retry và kiểm tra lịch sử. Việc xóa tài nguyên ở nhà cung cấp và việc cập nhật metadata trong broker không phải một transaction phân tán duy nhất; cần thiết kế xử lý lỗi và đối soát cho khoảng thời gian giữa hai bước.

## 5. Quản lý trạng thái và xử lý bất đồng bộ

Tách request API khỏi công việc dài giúp broker phản hồi nhanh và chịu được các thao tác kéo dài. Tuy nhiên, điều đó đòi hỏi trạng thái operation phải được lưu bền vững, thay vì chỉ nằm trong bộ nhớ của một request hoặc một thread.

Có thể quản lý trạng thái nội bộ theo các bước sau:

~~~mermaid
stateDiagram-v2
    [*] --> ACCEPTED
    ACCEPTED --> IN_PROGRESS
    IN_PROGRESS --> SUCCEEDED
    IN_PROGRESS --> RETRYING
    RETRYING --> IN_PROGRESS
    IN_PROGRESS --> FAILED
    RETRYING --> FAILED
    SUCCEEDED --> [*]
    FAILED --> [*]
~~~

Đây là trạng thái nội bộ minh họa. Khi trả về nền tảng, broker ánh xạ chúng sang trạng thái operation theo OSB API. Ví dụ **ACCEPTED**, **IN_PROGRESS** và **RETRYING** có thể được trả là **in progress**; **SUCCEEDED** trả là **succeeded**; **FAILED** trả là **failed**.

Một bản ghi operation nên có tối thiểu:

- operation ID và khóa định danh yêu cầu;
- service instance ID hoặc binding ID liên quan;
- loại thao tác: provision, update, deprovision hoặc thao tác binding;
- trạng thái hiện tại, thời điểm bắt đầu và kết thúc;
- số lần thử và thời điểm retry tiếp theo;
- correlation ID để liên kết log, trace và yêu cầu từ nền tảng;
- mã lỗi cùng thông điệp đã được làm sạch để phục vụ chẩn đoán.

Không lưu password, token hoặc toàn bộ payload nhạy cảm trong trường lỗi hay log. Khi operation thất bại, thông tin trả cho nền tảng cần đủ để nhận biết và xử lý lỗi nhưng không tiết lộ bí mật nội bộ của nhà cung cấp.

Worker đọc công việc từ queue, gọi provider adapter rồi cập nhật operation store. Nếu broker khởi động lại, worker khác có thể tiếp tục các công việc còn tồn tại. Vì vậy, việc nhận message cần có cơ chế xác nhận, retry và chống xử lý lặp. Một message có thể được giao lại sau timeout; hệ thống phải giả định điều đó sẽ xảy ra.

Không phải mọi thao tác đều cần bất đồng bộ. Đọc catalog hoặc tạo một binding hoàn tất nhanh có thể xử lý đồng bộ. Provision hoặc deprovision có thể cần worker nếu phải chờ hạ tầng. Quyết định dựa trên thời gian thực tế, giới hạn của nền tảng và khả năng của provider adapter; không nên biến tất cả request thành job nền nếu điều đó làm tăng độ phức tạp mà không đem lại lợi ích.

## 6. Idempotency và tính nhất quán

Nền tảng có thể gửi lại request khi timeout, mất kết nối hoặc không nhận được response dù broker đã xử lý xong. Nếu broker coi mỗi lần nhận request là một thao tác hoàn toàn mới, retry có thể tạo hai database, hai credential hoặc hai tài nguyên tính phí.

OSB API cung cấp các định danh như service instance ID và binding ID. Broker nên dùng chúng làm khóa nghiệp vụ ổn định, kết hợp với kiểm tra nội dung yêu cầu:

- Với cùng instance ID và cùng service/plan, yêu cầu provision lặp lại phải trả về kết quả hoặc operation đã tồn tại theo quy tắc idempotency của broker.
- Nếu instance ID đã gắn với service hoặc plan khác, broker phải phát hiện xung đột thay vì âm thầm thay đổi tài nguyên.
- Với cùng binding ID, broker không được tạo thêm credential mới ở mỗi lần retry.
- Update cần kiểm tra phiên bản hoặc trạng thái hiện tại để hai yêu cầu đồng thời không ghi đè lẫn nhau.
- Deprovision lặp lại cần xử lý trạng thái đã xóa theo hợp đồng OSB và chính sách của broker.

Một cách triển khai là lưu khóa idempotency, loại thao tác, định danh tài nguyên và hash của các tham số có ý nghĩa. Ràng buộc unique trong database giúp chặn hai request đồng thời cùng tạo một bản ghi. Khi request đến lần nữa, broker tra cứu bản ghi cũ và trả về trạng thái phù hợp.

Idempotency ở tầng broker chưa đủ nếu provider adapter tạo tài nguyên bằng một API không idempotent. Adapter cần truyền idempotency key hoặc một tên tài nguyên xác định đến nhà cung cấp nếu có thể. Nếu nhà cung cấp không hỗ trợ, adapter cần có bước tra cứu trước khi tạo và cơ chế đối soát để phát hiện tài nguyên đã tạo nhưng broker chưa kịp ghi nhận.

Không nên giữ một transaction database mở trong suốt thời gian gọi API hạ tầng. Thay vào đó, broker có thể dùng transaction ngắn để lưu operation cùng sự kiện outbox; worker đọc sự kiện rồi gọi provider. Kết quả từ provider được ghi vào transaction khác. Cách làm này giảm thời gian khóa dữ liệu và tránh tình huống database rollback trong khi thao tác bên ngoài đã thành công.

Một số thao tác gồm nhiều bước, ví dụ tạo database, cấu hình user, gắn firewall rule và ghi endpoint. Đây là quy trình kiểu saga: mỗi bước có trạng thái và có thể có hành động bù trừ. Nếu bước sau thất bại, broker quyết định retry, chạy compensation hoặc đánh dấu tài nguyên cần can thiệp. Không thể giả định một transaction ACID duy nhất bao phủ cả database của broker lẫn API của nhà cung cấp.

Ngoài luồng xử lý chính, nên có tác vụ reconciliation định kỳ để so sánh trạng thái broker với trạng thái tài nguyên thực tế. Tác vụ này giúp phát hiện tài nguyên mồ côi, operation bị kẹt, credential chưa được thu hồi hoặc trạng thái cập nhật không đồng nhất. Reconciliation cần có giới hạn tốc độ và quy tắc an toàn để không tự ý xóa tài nguyên hợp lệ.

## 7. Bảo mật tại ranh giới giữa hai luồng

Broker thường có quyền quản trị cao hơn ứng dụng. Nếu credential quản trị của nhà cung cấp bị lộ, kẻ tấn công có thể tác động đến nhiều instance. Vì vậy, ranh giới control plane cần được bảo vệ chặt:

- **Xác thực nền tảng:** chỉ cho phép platform client đã đăng ký gọi OSB API; sử dụng TLS và cơ chế xác thực được triển khai thống nhất, chẳng hạn HTTP Basic Auth qua TLS hoặc cơ chế xác thực bổ sung của môi trường.
- **Phân quyền theo context:** kiểm tra organization, space, namespace, tenant hoặc phạm vi sở hữu trước khi đọc, cập nhật hay xóa instance và binding.
- **Tách credential:** credential quản trị của broker không được trả cho ứng dụng. Mỗi binding chỉ nhận credential với quyền và phạm vi cần thiết.
- **Bảo vệ secret:** mã hóa khi lưu, giới hạn người có quyền đọc, tránh ghi secret vào log, trace, exception hoặc metric label.
- **Thu hồi có kiểm soát:** unbind phải thu hồi đúng credential của binding; rotation cần có thời gian chuyển tiếp và quy trình cập nhật runtime để tránh làm ứng dụng mất kết nối đột ngột.
- **Giới hạn mạng:** chỉ mở broker API cho nền tảng hoặc mạng quản trị cần thiết. Endpoint dữ liệu được bảo vệ theo cơ chế riêng của dịch vụ.
- **Audit:** ghi lại ai yêu cầu thao tác nào, trên instance/binding nào, kết quả và correlation ID; không ghi giá trị bí mật.

Data plane cũng cần bảo mật độc lập. Ứng dụng nên kết nối qua mạng riêng hoặc kênh mã hóa phù hợp, xác minh chứng thư khi cần và sử dụng credential theo nguyên tắc quyền tối thiểu. Việc broker xác thực thành công một request provision không có nghĩa ứng dụng được phép truy cập mọi dữ liệu trong instance.

## 8. Áp dụng kiến trúc trong Spring Cloud Service Broker

Spring Cloud Open Service Broker cung cấp lớp tích hợp OSB API với ứng dụng Spring. Nên xem các service của thư viện là lớp adapter ở biên hệ thống: chúng nhận request theo hợp đồng OSB, chuyển đổi sang command nghiệp vụ và trả response tương ứng. Logic cấp phát thật sự nên nằm trong các application service độc lập để có thể kiểm thử và thay provider mà không phải thay đổi giao diện API.

Có thể phân chia trách nhiệm theo các nhóm sau:

| Nhóm triển khai | Trách nhiệm |
|---|---|
| Catalog service | Đọc catalog offering/plan từ cấu hình hoặc kho metadata và trả về nền tảng |
| Service instance service | Tiếp nhận provision, update, deprovision, truy vấn instance và last operation |
| Service instance binding service | Tiếp nhận bind/unbind, tạo và thu hồi credential |
| Lifecycle coordinator | Điều phối quy tắc nghiệp vụ, trạng thái và idempotency |
| Operation repository | Lưu trạng thái operation bền vững |
| Outbox publisher / worker | Đưa công việc vào hàng đợi và thực hiện tác vụ nền |
| Provider adapter | Gọi API quản lý tài nguyên của nhà cung cấp |
| Secret adapter | Lưu hoặc truy xuất bí mật theo chính sách bảo mật |

Các service tích hợp thường gặp của thư viện gồm **CatalogService**, **ServiceInstanceService** và **ServiceInstanceBindingService**. Tên và chữ ký phương thức cụ thể cần theo phiên bản Spring Cloud Open Service Broker mà dự án sử dụng. Điều quan trọng ở cấp kiến trúc là không nhồi toàn bộ thao tác hạ tầng vào lớp xử lý HTTP; lớp tích hợp chỉ nên điều phối đến use case tương ứng.

Ví dụ, provider adapter có thể được định nghĩa bằng một hợp đồng nội bộ như sau:

~~~java
public interface ServiceResourceProvisioner {
    ProvisionedResource provision(ProvisionSpec spec);

    ProvisionedResource update(ResourceId resourceId, UpdateSpec spec);

    void deprovision(ResourceId resourceId);
}

public interface BindingCredentialService {
    BindingDetails createBinding(BindingSpec spec);

    void revokeBinding(BindingId bindingId);
}
~~~

Đây là hợp đồng minh họa cho tầng nghiệp vụ, không phải interface của OSB API. Mỗi nhà cung cấp có thể có một implementation riêng. Lifecycle coordinator làm việc với hợp đồng này để không phụ thuộc trực tiếp vào SDK hoặc HTTP client của nhà cung cấp.

Với thao tác dài, coordinator nên ghi nhận operation trước khi worker thực hiện tác vụ bên ngoài. Ví dụ dưới đây mô tả ý tưởng transaction ngắn giữa operation và outbox:

~~~java
@Transactional
public Operation acceptProvision(ProvisionCommand command) {
    Operation operation = operationRepository
        .findByIdempotencyKey(command.idempotencyKey())
        .orElseGet(() -> operationRepository.createPending(command));

    outboxRepository.appendIfAbsent(
        operation.getId(),
        new ProvisionRequested(operation.getId(), command.instanceId())
    );

    return operation;
}
~~~

Worker đọc sự kiện **ProvisionRequested**, gọi **ServiceResourceProvisioner**, sau đó cập nhật trạng thái operation. Trong triển khai thực tế, cần bảo đảm việc tạo operation và outbox có ràng buộc duy nhất phù hợp; worker phải xử lý message giao lặp; lỗi phải được phân loại thành lỗi có thể retry hoặc lỗi kết thúc. Không để request thread giữ kết nối HTTP trong lúc chờ một thao tác hạ tầng kéo dài.

Có thể dùng Spring transaction cho phần ghi metadata nội bộ, Spring scheduling hoặc một hệ thống message broker cho worker, và adapter riêng cho kho secret. Việc chọn công nghệ queue, database hay secret manager phụ thuộc môi trường triển khai. Dù chọn công nghệ nào, operation store phải tồn tại độc lập với vòng đời của process broker để trạng thái không biến mất khi ứng dụng Spring khởi động lại.

## 9. Tích hợp Cloud Foundry và Kubernetes

### 9.1. Cloud Foundry

Cloud Foundry sử dụng broker đã đăng ký để hiển thị service offering và plan. Khi người dùng tạo service instance hoặc bind instance vào ứng dụng, nền tảng gọi OSB API. Broker cấp phát tài nguyên và trả binding credentials; Cloud Foundry cung cấp thông tin binding cho ứng dụng thông qua môi trường runtime, thường là **VCAP_SERVICES**.

Ứng dụng dùng thông tin đó để kết nối đến dịch vụ. Các request nghiệp vụ đi trực tiếp đến endpoint, không qua Cloud Foundry broker. Broker chỉ được gọi lại khi cần thao tác quản lý như update, unbind hoặc deprovision.

### 9.2. Kubernetes

Trong Kubernetes, một controller, operator hoặc thành phần tích hợp OSB API có thể theo dõi tài nguyên khai báo và chuyển thay đổi thành yêu cầu đến broker. Sau khi nhận binding, thành phần tích hợp có thể lưu thông tin kết nối trong Kubernetes Secret và đưa tham chiếu Secret vào Pod hoặc workload.

Cần xác định rõ thành phần nào chịu trách nhiệm đồng bộ trạng thái giữa Custom Resource, broker và Secret. Nếu controller bị khởi động lại giữa một thao tác, nó phải có thể đọc lại trạng thái và tiếp tục reconcile. Không nên dựa vào trạng thái tạm trong bộ nhớ của controller hoặc broker.

Cả Cloud Foundry và Kubernetes đều có context riêng. Nên chuẩn hóa context thành một mô hình tenant/consumer nội bộ trước khi chuyển vào logic nghiệp vụ. Các adapter nền tảng chịu trách nhiệm chuyển đổi cấu trúc riêng; lifecycle coordinator không nên phụ thuộc trực tiếp vào tên biến môi trường của Cloud Foundry hay cấu trúc object Kubernetes.

## 10. Các quyết định thiết kế cần giữ nhất quán

| Quyết định | Cách thực hiện nên chọn | Vấn đề cần tránh |
|---|---|---|
| Ranh giới lưu lượng | Broker xử lý yêu cầu quản lý; ứng dụng kết nối endpoint dịch vụ | Chuyển toàn bộ lưu lượng ứng dụng qua broker API |
| Ranh giới nghiệp vụ | OSB adapter gọi lifecycle/binding coordinator | Đặt logic provider và xử lý retry trong controller/API handler |
| Tác vụ dài | Lưu operation, phát sự kiện và xử lý bằng worker | Giữ request HTTP mở trong thời gian dài |
| Trạng thái | Lưu bền vững instance, binding và operation | Chỉ lưu trạng thái trong memory |
| Retry | Dùng instance ID, binding ID và idempotency key ổn định | Mỗi retry lại tạo tài nguyên hoặc credential mới |
| Tính nhất quán | Transaction ngắn, outbox, compensation và reconciliation | Giả định transaction database bao phủ cả nhà cung cấp |
| Bí mật | Tách credential quản trị khỏi credential binding | Dùng chung credential quản trị cho mọi ứng dụng |
| Mở rộng nhà cung cấp | Dùng provider adapter theo hợp đồng nội bộ | Để domain service phụ thuộc SDK của một nhà cung cấp |
| Tích hợp nền tảng | Chuẩn hóa context qua platform adapter | Đưa cấu trúc Cloud Foundry/Kubernetes vào mọi lớp nghiệp vụ |

Một ngoại lệ có thể xuất hiện khi sản phẩm cung cấp chức năng proxy, gateway hoặc route service. Khi đó, proxy là một phần được thiết kế có chủ đích của data plane, với endpoint, xác thực, giám sát và năng lực mở rộng riêng. Nó không làm thay đổi vai trò cơ bản của OSB broker trong control plane.

## 11. Kiểm tra kiến trúc trước khi triển khai

Trước khi đưa broker vào môi trường thật, cần kiểm tra các câu hỏi sau:

- Ứng dụng có thể tiếp tục kết nối đến dịch vụ khi broker tạm thời không sẵn sàng hay không?
- Broker có lưu trạng thái instance, binding và operation đủ bền vững để phục hồi sau restart hay không?
- Request provision lặp lại với cùng instance ID có tạo thêm tài nguyên không?
- Request bind lặp lại với cùng binding ID có tạo thêm credential không?
- Operation bất đồng bộ có thể được truy vấn đến trạng thái kết thúc qua last operation hay không?
- Worker có thể retry an toàn khi nhà cung cấp đã thực hiện thao tác nhưng broker chưa nhận được response hay không?
- Unbind có thu hồi đúng credential và giữ nguyên quyền truy cập của binding khác hay không?
- Deprovision có xử lý rõ ràng các binding còn tồn tại và tài nguyên chưa giải phóng hay không?
- Credential quản trị và credential ứng dụng có được tách biệt, mã hóa và giới hạn quyền truy cập hay không?
- Cloud Foundry hoặc Kubernetes có thể đồng bộ binding vào runtime/Secret và phục hồi sau khi controller khởi động lại hay không?
- Log, trace và audit có correlation ID nhưng không chứa password, token hoặc dữ liệu nhạy cảm hay không?

Khi các ranh giới này được xác định rõ, service broker có thể đảm nhiệm việc cung cấp dịch vụ theo một API thống nhất, theo dõi được vòng đời và tích hợp với nhiều nền tảng. Ứng dụng vẫn sử dụng dịch vụ qua endpoint chuyên dụng với giao thức phù hợp, trong khi broker tập trung vào catalog, cấp phát, binding, cập nhật, thu hồi và trạng thái operation.

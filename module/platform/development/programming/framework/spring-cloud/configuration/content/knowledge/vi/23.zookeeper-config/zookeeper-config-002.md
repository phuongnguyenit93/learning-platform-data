# Cấu trúc znode cho cấu hình chung, ứng dụng và profile

Spring Cloud Zookeeper Config dùng Apache ZooKeeper như một nguồn property cho Spring Environment. Dữ liệu cấu hình được tổ chức thành các znode dưới một root path. Mỗi context là một znode cha; mỗi property là một znode con chứa giá trị. Spring Cloud Zookeeper tìm các context chung và context theo ứng dụng, đồng thời có thể xét context theo profile đang hoạt động.

Một cấu trúc rõ ràng giúp nhiều dịch vụ dùng chung các giá trị nền, vẫn có thể ghi đè bằng cấu hình riêng, và tách giá trị theo môi trường như dev, test hoặc prod. Khi thiết kế, cần quy ước root, default context, tên ứng dụng và profile separator nhất quán; đồng thời quản lý ACL cho từng path vì tên profile không tự tạo ra ranh giới bảo mật.

## 1. Znode lưu cấu hình như thế nào?

ZooKeeper lưu dữ liệu theo cây znode. Một znode có tên/path, có thể chứa một payload dữ liệu và có thể có các znode con. Với Spring Cloud Zookeeper Config, context cấu hình là một znode cha; tên property là znode con và nội dung znode con là giá trị property.

Ví dụ:

~~~text
/config
└── application
    ├── service.name        -> platform
    ├── feature.audit       -> true
    └── server.port         -> 8080
~~~

Ở đây, `/config/application` là context chung mặc định. Các znode lá `service.name`, `feature.audit` và `server.port` tương ứng với các property cùng tên. Dấu chấm trong tên znode là một phần tên key; nó không có nghĩa là tạo thêm nhiều cấp path.

Một property có thể được biểu diễn như sau:

| Thành phần | Giá trị |
|---|---|
| Context path | `/config/application` |
| Property key | `server.port` |
| Znode path | `/config/application/server.port` |
| Znode data | `8080` |

Khi Spring Cloud Zookeeper đọc context, nó lấy dữ liệu của các znode con và tạo property source cho Spring Environment. Không nên tạo một znode riêng cho từng ký tự của key phân cấp; dùng tên property đầy đủ làm tên node lá theo quy ước của ứng dụng.

## 2. Bốn context cơ bản

Một cách tổ chức dễ hiểu dùng hai trục:

- Phạm vi: cấu hình chung cho nhiều ứng dụng hoặc cấu hình riêng một ứng dụng.
- Profile: cấu hình mặc định hoặc cấu hình chỉ áp dụng cho một profile.

Với root mặc định `/config`, default context `application` và profile separator mặc định là dấu phẩy, các context minh họa cho dịch vụ `orders-service` chạy profile `prod` là:

| Mục đích | Context path |
|---|---|
| Cấu hình chung | `/config/application` |
| Cấu hình chung cho prod | `/config/application,prod` |
| Cấu hình riêng orders-service | `/config/orders-service` |
| Cấu hình riêng orders-service cho prod | `/config/orders-service,prod` |

Các tên context này được hình thành từ root, default context hoặc application name, và profile separator. Tên ứng dụng thường lấy từ `spring.application.name`; có thể cấu hình riêng nếu phiên bản và cách tích hợp của dự án hỗ trợ.

Sơ đồ cây:

~~~text
/config
├── application
│   ├── company.name
│   ├── observability.enabled
│   └── http.connect-timeout
├── application,prod
│   ├── observability.enabled
│   └── http.connect-timeout
├── orders-service
│   ├── orders.max-items
│   └── orders.timeout
└── orders-service,prod
    ├── orders.max-items
    ├── orders.timeout
    └── payment.mode
~~~

Nhờ cách chia này, các ứng dụng có thể kế thừa cấu hình chung, còn property đặc thù của orders-service được lưu trong context riêng.

## 3. Cấu hình root, default context và profile separator

Ví dụ khai báo các thuộc tính kết nối và định tuyến:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      config:
        enabled: true
        root: config
        default-context: application
        profile-separator: ","
~~~

Các thuộc tính có ý nghĩa:

| Thuộc tính | Vai trò |
|---|---|
| `spring.cloud.zookeeper.connect-string` | Danh sách ZooKeeper ensemble endpoints |
| `spring.cloud.zookeeper.config.enabled` | Bật hoặc tắt Zookeeper Config |
| `spring.cloud.zookeeper.config.root` | Root path chứa các context cấu hình |
| `spring.cloud.zookeeper.config.default-context` | Context mặc định dùng chung |
| `spring.cloud.zookeeper.config.profile-separator` | Ký tự phân cách context và profile |
| `spring.application.name` | Tên context riêng của ứng dụng |

Root path giúp gom các dữ liệu cấu hình của một hệ thống vào namespace riêng. Ví dụ có thể chọn `/platform-config` thay cho `/config` để tránh trùng với ứng dụng khác trong cùng ensemble. Nếu đổi root, mọi context phải được tạo dưới root mới và ACL cần áp dụng đúng path.

Default context là tên của vùng cấu hình chung. Không nên dùng tên của một dịch vụ cụ thể làm default context nếu nhiều ứng dụng cùng cần kế thừa nó.

Profile separator mặc định thường là dấu phẩy. Nếu đổi separator, ví dụ thành dấu gạch ngang, phải tạo các context tương ứng theo quy ước mới và xác nhận Spring Cloud Zookeeper phiên bản đang dùng tạo đúng path. Tránh dùng separator xuất hiện thường xuyên trong tên ứng dụng hoặc profile.

## 4. Cấu hình chung cho mọi ứng dụng

Đặt các giá trị thực sự dùng chung trong context `application`. Ví dụ:

~~~text
/config/application
├── platform.name          -> internal-platform
├── observability.enabled  -> true
├── http.connect-timeout   -> 2s
└── logging.format         -> json
~~~

Các property này có thể được đọc bởi nhiều ứng dụng tham gia cùng cấu hình ZooKeeper. Chỉ đưa vào context chung các giá trị có ý nghĩa và tương thích với mọi client. Không đặt cấu hình riêng của database, queue hoặc đối tác của một dịch vụ vào đây nếu các ứng dụng khác không được phép hoặc không thể sử dụng.

Ví dụ tạo context và property bằng ZooKeeper CLI. Tùy công cụ và phiên bản CLI, cần tạo parent znode trước khi tạo node con:

~~~bash
zkCli.sh -server zk-1.internal:2181

create /config ""
create /config/application ""
create /config/application/platform.name "internal-platform"
create /config/application/observability.enabled "true"
create /config/application/http.connect-timeout "2s"
~~~

Lệnh tạo node minh họa việc lưu key/value; trong thực tế nên dùng script quản trị hoặc công cụ provisioning có kiểm soát, có kiểm tra node đã tồn tại và xử lý cập nhật idempotent. Không nên chạy các lệnh tạo node thủ công lặp lại mà không xác định hành vi khi path đã có.

## 5. Cấu hình chung theo profile

Context `application,prod` chứa các giá trị chung chỉ áp dụng khi ứng dụng chạy profile prod:

~~~text
/config/application,prod
├── observability.enabled  -> true
├── http.connect-timeout   -> 1s
└── logging.level          -> WARN
~~~

Tương tự, có thể tạo context `application,dev` cho cấu hình dùng chung của môi trường phát triển:

~~~text
/config/application,dev
├── observability.enabled  -> true
├── http.connect-timeout   -> 5s
└── logging.level          -> DEBUG
~~~

Spring Boot xác định active profiles, còn Spring Cloud Zookeeper dùng profile separator để tìm context tương ứng. Vì vậy, các instance chạy profile khác nhau có thể nhận property source khác nhau dù cùng dùng một application name.

Profile biểu diễn môi trường hoặc nhóm hành vi. Không nên tạo profile riêng cho từng pod hoặc từng máy; thông tin định danh instance nên được quản lý bằng cơ chế khác.

## 6. Cấu hình riêng theo application

Đặt các property chỉ thuộc một dịch vụ trong context có tên ứng dụng. Ví dụ:

~~~text
/config/orders-service
├── orders.max-items  -> 50
├── orders.timeout    -> 3s
└── payment.mode      -> sandbox
~~~

Một dịch vụ khác có context riêng:

~~~text
/config/payment-service
├── payment.provider      -> internal-gateway
├── payment.retry-count   -> 3
└── payment.timeout       -> 4s
~~~

Tách application context giúp tránh đưa property đặc thù của một dịch vụ vào cấu hình chung. Nó cũng giúp policy ACL có thể cấp quyền đọc theo từng ứng dụng nếu các dịch vụ có danh tính riêng khi kết nối ZooKeeper.

Tên context cần khớp với tên ứng dụng mà Config Client sử dụng. Nếu một ứng dụng đặt `spring.application.name=orders-api` nhưng dữ liệu lại nằm dưới `/config/orders-service`, cần thống nhất tên hoặc cấu hình cơ chế ánh xạ phù hợp; không giả định client tự tìm alias.

## 7. Cấu hình riêng theo application và profile

Context kết hợp application với profile có mức cụ thể cao nhất trong mô hình bốn context:

~~~text
/config/orders-service,prod
├── orders.max-items  -> 100
├── orders.timeout    -> 1s
└── payment.mode      -> live
~~~

Với cùng một key, có thể đặt giá trị nền ở application context và ghi đè cho production trong context profile-specific:

| Context | Key | Giá trị minh họa |
|---|---|---|
| application | `http.connect-timeout` | `2s` |
| application,prod | `http.connect-timeout` | `1s` |
| orders-service | `orders.max-items` | `50` |
| orders-service,prod | `orders.max-items` | `100` |

Đây là cách tổ chức để người vận hành thấy rõ giá trị chung và ngoại lệ theo môi trường. Tuy nhiên, không suy ra thứ tự thắng chỉ từ cây znode. Spring Cloud Zookeeper tạo các property source theo context đã tìm thấy; thứ tự chính xác phải được xác minh trong Environment của ứng dụng, đặc biệt khi nhiều context cùng khai báo một key hoặc phiên bản thư viện thay đổi.

## 8. Nhiều active profile

Một ứng dụng có thể chạy nhiều profile, ví dụ:

~~~yaml
spring:
  profiles:
    active: prod,observability
~~~

Khi dùng nhiều profile, Spring Cloud Zookeeper có thể xét các context profile theo cấu hình và thứ tự profile được cung cấp. Nếu cùng key xuất hiện ở nhiều context profile, cần kiểm tra thứ tự property source thực tế để biết giá trị nào thắng.

Nên giới hạn số profile phối hợp và đặt tên có ý nghĩa. Nếu mỗi profile chứa nhiều key trùng nhau, việc dự đoán giá trị hiệu lực sẽ khó hơn và dễ phát sinh khác biệt giữa môi trường. Với các tổ hợp phức tạp, tạo một profile tổng hợp như prod-observability có thể làm cấu trúc dễ quản lý hơn, miễn là quy ước separator và tên context nhất quán.

## 9. Quy tắc ưu tiên và cách xác minh

Mục tiêu thiết kế thông thường là:

1. Cấu hình chung cung cấp giá trị nền.
2. Cấu hình chung theo profile điều chỉnh giá trị theo môi trường.
3. Cấu hình riêng ứng dụng bổ sung hoặc thay giá trị theo dịch vụ.
4. Cấu hình riêng ứng dụng theo profile cung cấp ngoại lệ cụ thể nhất.

Không nên phụ thuộc vào thứ tự tạo znode hoặc thời điểm cập nhật để quyết định ưu tiên. Hãy xác minh property source thực tế. Nếu ứng dụng có Actuator, có thể expose endpoint env trong môi trường được bảo vệ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,env
  endpoint:
    env:
      show-values: when-authorized
~~~

Sau đó truy vấn key cụ thể:

~~~bash
curl "http://localhost:8080/actuator/env/orders.timeout"
~~~

Endpoint có thể cho biết property source chứa key và nguồn đang thắng, tùy phiên bản Spring Boot và cấu hình hiển thị. Bảo vệ endpoint bằng authentication, authorization và giới hạn mạng; không bật hiển thị plaintext cho secret trong production.

Khi không dùng Actuator, có thể kiểm tra Environment bằng một diagnostic component nội bộ chỉ trả tên property source và trạng thái có/không. Không log giá trị nhạy cảm.

## 10. Cấu trúc znode theo môi trường

Có hai cách tổ chức phổ biến:

**Một ensemble với root riêng theo môi trường:**

~~~text
/platform-dev/config/...
/platform-test/config/...
/platform-prod/config/...
~~~

Ứng dụng dev và prod kết nối cùng ensemble nhưng dùng root hoặc namespace khác nhau nếu cấu hình client hỗ trợ root tương ứng. Cần ACL riêng để workload dev không đọc được dữ liệu prod.

**Các ensemble hoặc cluster tách biệt:**

~~~text
ZooKeeper Dev ensemble
└── /config/...

ZooKeeper Production ensemble
└── /config/...
~~~

Tách ensemble tạo ranh giới vận hành rõ hơn, giảm nguy cơ lỗi cấu hình hoặc quyền truy cập chéo giữa môi trường. Lựa chọn phụ thuộc yêu cầu cô lập, chi phí và quy mô hạ tầng.

Không coi việc đổi profile từ dev sang prod là biện pháp cách ly dữ liệu. Nếu một danh tính có quyền đọc cả hai context, profile chỉ là lựa chọn cấu hình của ứng dụng chứ không phải kiểm soát truy cập.

## 11. Znode persistent, version và cập nhật

Cấu hình ứng dụng thường nên lưu trong persistent znode. Ephemeral znode gắn với session của client và sẽ bị xóa khi session kết thúc; nếu dùng ephemeral cho cấu hình, một lần mất kết nối có thể làm dữ liệu biến mất ngoài ý muốn.

ZooKeeper duy trì metadata như version, ctime, mtime và zxid cho znode. Những thông tin này hỗ trợ kiểm tra cập nhật và đồng bộ, nhưng không thay thế hệ thống quản lý thay đổi như Git:

- Không có pull request/diff review tích hợp như Git.
- Không nên xem version counter của znode là lịch sử phát hành cấu hình đầy đủ.
- Muốn audit, cần ghi lại ai thay đổi path nào, giá trị nào và lý do.
- Muốn rollback, phải lưu snapshot hoặc phiên bản cấu hình đã được quản lý riêng.

Khi cập nhật node đã tồn tại, dùng thao tác setData hoặc công cụ quản trị tương ứng. Với hệ thống tự động, kiểm tra version hiện tại trước khi ghi để tránh ghi đè thay đổi đồng thời. Các cập nhật liên quan nhiều key có thể cần transaction/multi operation nếu cần tính nguyên tử ở mức ZooKeeper.

## 12. Giới hạn dữ liệu và cách đặt tên

Znode không phải kho lưu trữ file lớn. Mỗi node có giới hạn kích thước payload và ZooKeeper được tối ưu cho metadata cùng dữ liệu nhỏ. Nên lưu một property hoặc một nhóm nhỏ có quan hệ trong mỗi znode, tránh đưa cả file cấu hình lớn hoặc binary vào một node.

Quy ước đặt tên nên:

- Dùng key rõ nghĩa, ổn định và thống nhất với tên property Spring.
- Tránh dấu slash trong tên key vì slash phân tách path.
- Tránh tạo quá nhiều znode con không cần thiết.
- Không đưa secret vào tên path; path có thể xuất hiện trong log/audit.
- Giữ tên application và profile nhất quán giữa deployment và repository cấu hình.
- Có tài liệu về root, default context và profile separator cho nhóm vận hành.

Nếu property cần chứa JSON hoặc cấu trúc lớn, cân nhắc lưu một giá trị có kích thước hợp lý hoặc dùng hệ thống lưu trữ phù hợp hơn; không biến ZooKeeper thành object store.

## 13. ACL và bảo mật theo path

ZooKeeper hỗ trợ ACL ở từng znode. Quyền cần được thiết kế cho cả context cha và các node con. Một ứng dụng có thể cần quyền đọc context của chính nó và context chung, nhưng không cần quyền ghi. Quyền ghi nên thuộc về pipeline hoặc danh tính quản trị cấu hình.

Nguyên tắc:

- Dùng authentication phù hợp, chẳng hạn SASL hoặc cơ chế được hạ tầng ZooKeeper hỗ trợ.
- Cấp quyền read cho client trên đúng root/context cần dùng.
- Chỉ cấp create, write, delete cho quy trình quản trị được ủy quyền.
- Bảo vệ quyền trên parent node vì quyền create/delete có thể ảnh hưởng cấu trúc con.
- Tách quyền giữa dev, staging và production.
- Dùng TLS cho kết nối client/server khi hạ tầng hỗ trợ và yêu cầu bảo mật.
- Không dựa vào tên profile để thay thế ACL.
- Audit các thay đổi cấu hình và rà soát danh tính có quyền ghi.

Ví dụ, orders-service có thể được cấp read trên `/config/application`, `/config/application,prod`, `/config/orders-service` và `/config/orders-service,prod`. Nó không nhất thiết cần quyền đọc `/config/payment-service` hoặc quyền tạo/xóa znode.

## 14. Watcher và thay đổi cấu hình khi ứng dụng chạy

ZooKeeper hỗ trợ watch để client nhận thông báo khi znode thay đổi. Spring Cloud Zookeeper có cơ chế theo dõi thay đổi cấu hình tùy phiên bản và thiết lập. Tuy nhiên, cần phân biệt:

- Watch thông báo rằng một znode đã thay đổi.
- Config integration cập nhật property source hoặc phát sự kiện thay đổi.
- Bean chỉ áp dụng giá trị mới nếu có cơ chế rebind, refresh scope hoặc được tạo lại.

Không giả định một znode đổi là mọi field trong mọi bean tự cập nhật ngay. Kiểm tra cấu hình watcher, hành vi của phiên bản Spring Cloud Zookeeper và bean lifecycle trong ứng dụng. Nếu yêu cầu cập nhật nhất quán nhiều instance, cần thêm cơ chế phân phối/đồng bộ và theo dõi kết quả từng instance.

## 15. Kiểm tra cấu trúc bằng ZooKeeper CLI

Một số lệnh CLI hữu ích:

~~~bash
# Liệt kê context dưới root
ls /config

# Liệt kê property nodes trong context chung
ls /config/application

# Đọc một property
get /config/application/server.port

# Xem metadata và version của znode
stat /config/application/server.port
~~~

Nếu path không tồn tại, kiểm tra root, context name, profile separator và application name. Khi dùng chroot trong connection string, cần nhớ path hiển thị từ góc nhìn của client có thể tương đối với chroot đó.

Ví dụ kiểm tra cho orders-service profile prod:

~~~bash
ls /config/orders-service
ls /config/orders-service,prod
get /config/orders-service,prod/orders.timeout
~~~

CLI chỉ xác minh dữ liệu đang có trong ensemble. Để xác nhận ứng dụng thật sự nạp đúng context, cần kiểm tra log Config integration hoặc Spring Environment sau khi khởi động.

## 16. Sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra |
|---|---|---|
| Client không thấy property | Sai root, default context hoặc application name | So sánh cấu hình client với path thực tế bằng ls/get |
| Chỉ thiếu property theo profile | Profile không active hoặc separator khác | Kiểm tra spring.profiles.active và profile-separator |
| Giá trị chung không được kế thừa | Default context không đúng hoặc ACL thiếu quyền đọc | Kiểm tra context application và quyền trên path |
| Giá trị application/profile không thắng | Property source order hoặc key trùng chưa như mong muốn | Kiểm tra Actuator env và thứ tự nguồn |
| Client nhận lỗi NoNode | Context hoặc znode lá chưa tồn tại | Tạo đúng parent/node và xác minh path |
| Client nhận lỗi NoAuth | ACL hoặc authentication sai | Kiểm tra identity và ACL trên cả parent lẫn child |
| Cấu hình biến mất sau restart | Dữ liệu được tạo dưới ephemeral node hoặc bị quy trình cleanup xóa | Kiểm tra znode type và audit thay đổi |
| Thay đổi không đến client | Watcher không bật/không hoạt động hoặc client chưa xử lý refresh | Kiểm tra watcher, session và bean lifecycle |
| Ứng dụng chậm hoặc ensemble chịu tải | Quá nhiều node, payload lớn hoặc truy vấn/watch không hợp lý | Rà soát số znode, kích thước dữ liệu và client connections |

## 17. Quy trình thiết kế cấu trúc znode

1. Chọn root namespace riêng cho hệ thống hoặc môi trường.
2. Chọn default context dùng chung, thường là application.
3. Chuẩn hóa spring.application.name cho từng dịch vụ.
4. Chọn profile separator và quy ước tên profile.
5. Phân loại property thành common, common-by-profile, application và application-by-profile.
6. Tạo persistent context nodes và property leaf nodes.
7. Thiết lập ACL read cho workload và quyền write cho pipeline quản trị.
8. Kiểm tra bằng ZooKeeper CLI các path và data.
9. Khởi động ứng dụng với từng profile đại diện và kiểm tra property source/giá trị hiệu lực.
10. Ghi lại cấu trúc, audit, backup và quy trình rollback.

## 18. Checklist vận hành

- [ ] Root path không trùng namespace của ứng dụng khác.
- [ ] Default context được dùng cho giá trị thực sự chung.
- [ ] Application name khớp với tên context riêng.
- [ ] Profile separator thống nhất giữa cấu hình client và cây znode.
- [ ] Có đủ context mặc định và context profile cần thiết.
- [ ] Property key được lưu dưới dạng znode lá với data rõ ràng.
- [ ] Cấu hình dùng persistent node, không dùng ephemeral node.
- [ ] Payload nhỏ và số lượng znode được kiểm soát.
- [ ] ACL read/write được phân tách theo workload và pipeline.
- [ ] Dev/staging/prod có namespace hoặc ensemble được cô lập phù hợp.
- [ ] Thứ tự ưu tiên được xác minh bằng Environment thực tế.
- [ ] Có audit, backup và phương án rollback.

Một cây znode tốt tách được cấu hình dùng chung khỏi cấu hình riêng dịch vụ và môi trường. Root, default context, application name và profile separator tạo thành quy ước path mà mọi client phải tuân thủ. Khi mỗi property được lưu thành znode lá, ACL được giới hạn theo path và thứ tự property source được xác minh trong Spring Environment, ZooKeeper có thể cung cấp cấu hình nhất quán mà vẫn giữ quyền truy cập và vận hành có kiểm soát.

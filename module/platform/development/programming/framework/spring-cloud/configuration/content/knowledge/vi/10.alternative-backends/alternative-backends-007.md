# Vault, CredHub và kho bí mật làm backend của Config Server

Spring Cloud Config thường dùng Git để quản lý cấu hình có lịch sử commit, nhánh và tag. Tuy nhiên, nhiều hệ thống còn cần một nơi chuyên dụng để lưu mật khẩu, token, chứng thư và các giá trị nhạy cảm. HashiCorp Vault và Cloud Foundry CredHub là hai backend có thể tích hợp với Config Server để cung cấp các thuộc tính đó theo ứng dụng và profile.

Khi Config Server dùng một kho bí mật làm backend, nó trở thành lớp trung gian giữa ứng dụng và hệ thống quản lý secret. Config Server xác thực với Vault hoặc CredHub, đọc các giá trị được phép truy cập, rồi trả chúng về Config Client như các property source. Cách này giúp client chỉ cần kết nối tới Config Server, nhưng cũng có nghĩa Config Server trở thành một thành phần được tin cậy và phải được bảo vệ tương xứng.

Bài học này trình bày vai trò của Vault và CredHub, cách tổ chức secret theo application/profile, cách cấu hình backend, xác thực và phân quyền, vòng đời secret, các giới hạn khi dùng secret store làm nguồn cấu hình và cách chọn mô hình truy cập phù hợp.

Sau bài học, bạn có thể:

- Giải thích vì sao dùng secret manager thay cho việc lưu bí mật dạng rõ trong Git.
- Phân biệt Config Server đọc secret hộ client với ứng dụng tự truy cập Vault/CredHub.
- Mô tả cách Vault và CredHub ánh xạ secret thành property source.
- Cấu hình kết nối backend ở mức cơ bản và bảo vệ danh tính của Config Server.
- Thiết kế policy, phạm vi đọc, xoay vòng và thu hồi secret.
- Xử lý lỗi backend, kiểm tra cấu hình trả về và lựa chọn nơi lưu từng loại thuộc tính.

## 1. Vì sao cần backend chuyên dụng cho bí mật?

Một repository Git phù hợp để lưu cấu hình có thể review và version hóa, ví dụ:

- Mức log, timeout, giới hạn xử lý và cờ tính năng.
- Địa chỉ dịch vụ nội bộ không nhạy cảm.
- Tên queue, topic hoặc consumer group.
- Quy ước cấu hình chung giữa các ứng dụng.

Những giá trị như mật khẩu database, API token, private key, khóa ký và chứng thư cần được bảo vệ chặt hơn. Nếu commit bí mật dạng rõ vào Git, người có quyền đọc repository có thể lấy được giá trị. Lịch sử Git còn giữ lại nội dung đã xóa ở commit mới hơn. Repository private cũng không tự thay thế được hệ thống quản lý secret.

Secret manager cung cấp các khả năng chuyên biệt:

- Xác thực danh tính người dùng hoặc workload.
- Cấp quyền đọc theo đường dẫn, ứng dụng hoặc nhóm.
- Ghi audit cho thao tác truy cập.
- Xoay vòng, thu hồi hoặc cập nhật secret.
- Quản lý version của dữ liệu bí mật.
- Với một số loại secret, tạo credential động có thời hạn.

Vault và CredHub có thể làm nguồn cung cấp thuộc tính cho Config Server. Config Server lấy dữ liệu từ backend theo request, sau đó trả về cho client. Điều này giúp giữ bí mật ngoài Git, đồng thời tận dụng cơ chế phân phối cấu hình đã có.

Cần nhớ rằng sau khi Config Server trả một secret cho client, giá trị đó có thể tồn tại trong bộ nhớ ứng dụng và có thể xuất hiện trong các kênh chẩn đoán nếu không được bảo vệ. Dùng secret manager không loại bỏ trách nhiệm bảo vệ dữ liệu sau khi ứng dụng nhận được.

## 2. Hai mô hình: Config Server đọc hộ hay ứng dụng tự đọc secret?

Có hai cách tổ chức thường gặp.

### Config Server làm trung gian

~~~mermaid
flowchart TD
    A["Ứng dụng Spring Boot"] -->|"Request application/profile"| B["Config Server"]
    B -->|"Xác thực bằng workload identity"| C["Vault hoặc CredHub"]
    C -->|"Secret được phép đọc"| B
    B -->|"Environment / property sources"| A
~~~

Trong mô hình này:

1. Config Server có danh tính được cấp quyền đọc một số đường dẫn trong Vault hoặc CredHub.
2. Config Client gọi Config Server bằng cơ chế xác thực của nền tảng.
3. Config Server xác định application/profile và truy vấn backend.
4. Secret được chuyển thành thuộc tính và trả về client.
5. Ứng dụng sử dụng thuộc tính như các cấu hình Spring khác.

Ưu điểm là client không cần biết endpoint, token hoặc giao thức của từng secret manager. Việc tích hợp backend tập trung ở Config Server.

Đổi lại, Config Server có quyền đọc nhiều secret và có thể trở thành điểm tập trung rủi ro. Nếu một tài khoản hoặc tiến trình Config Server bị xâm nhập, phạm vi ảnh hưởng phụ thuộc policy mà nó được cấp. Cần giới hạn quyền đọc theo nhu cầu, bảo vệ endpoint, dùng TLS và audit truy cập.

### Ứng dụng tự truy cập secret manager

~~~mermaid
flowchart TD
    A["Ứng dụng Spring Boot"] -->|"Cấu hình thông thường"| B["Config Server / Git"]
    A -->|"Danh tính workload riêng"| C["Vault hoặc CredHub"]
    C -->|"Secret theo quyền của ứng dụng"| A
~~~

Trong mô hình này, Config Server phân phối cấu hình thông thường; từng ứng dụng dùng danh tính riêng để truy cập secret manager trực tiếp, chẳng hạn thông qua thư viện tích hợp hoặc agent của nền tảng.

Ưu điểm:

- Mỗi dịch vụ có thể chỉ được cấp quyền đọc secret của chính nó.
- Config Server không cần giữ quyền đọc toàn bộ secret của các ứng dụng.
- Một số hệ thống có thể dùng cơ chế lease, renewal hoặc cập nhật secret trực tiếp phù hợp hơn với vòng đời credential.

Đổi lại, từng ứng dụng phải cấu hình danh tính, kết nối và xử lý lỗi của secret manager. Nhóm cần chuẩn hóa cách tích hợp để tránh mỗi dịch vụ tự xây dựng một cơ chế khác nhau.

### Chọn mô hình nào?

| Tiêu chí | Config Server làm trung gian | Ứng dụng truy cập trực tiếp |
|---|---|---|
| Danh tính tới secret manager | Tập trung ở Config Server | Riêng từng workload |
| Quyền đọc | Server cần quyền trên các secret được phân phối | Có thể giới hạn theo từng ứng dụng |
| Tích hợp client | Đơn giản hơn | Mỗi ứng dụng cần tích hợp |
| Audit | Truy cập backend chủ yếu gắn với danh tính server; cần giữ ngữ cảnh request | Có thể gắn trực tiếp với danh tính workload |
| Credential động và renewal | Cần xác minh backend/client có hỗ trợ vòng đời mong muốn | Thường phù hợp hơn khi ứng dụng cần quản lý lease trực tiếp |
| Phạm vi ảnh hưởng nếu server bị xâm nhập | Có thể rộng nếu policy quá lớn | Giới hạn theo quyền của từng ứng dụng |

Không có một lựa chọn bắt buộc cho mọi hệ thống. Hãy chọn dựa trên loại secret, yêu cầu xoay vòng, phạm vi quyền và khả năng vận hành. Một hệ thống cũng có thể kết hợp cả hai mô hình: Config Server phân phối cấu hình chung, còn ứng dụng lấy credential có thời hạn trực tiếp từ Vault.

## 3. Vault backend trong Spring Cloud Config

HashiCorp Vault là hệ thống quản lý secret có khả năng xác thực workload, kiểm soát policy, audit và cung cấp nhiều loại secret. Spring Cloud Config Server có backend tích hợp với Vault để đọc dữ liệu từ một secrets engine, thường là Key/Value (KV).

### Cách ánh xạ application và profile

Với Vault KV, nhóm có thể tổ chức dữ liệu theo tên ứng dụng và profile. Một quy ước minh họa:

~~~text
Vault KV mount: secret

secret/
├── application
├── application,prod
├── orders-service
├── orders-service,prod
├── inventory-service
└── inventory-service,prod
~~~

Các tên đường dẫn chính xác phụ thuộc cấu hình backend, phiên bản Spring Cloud Config và cách đặt profile separator. Ví dụ trên dùng dấu phẩy làm dấu phân cách profile để minh họa quy ước phổ biến. Có thể cấu hình dấu phân cách khác nếu phù hợp với tổ chức.

Ý nghĩa:

- <code>application</code>: thuộc tính dùng chung cho các ứng dụng.
- <code>application,prod</code>: thuộc tính dùng chung cho profile production.
- <code>orders-service</code>: secret riêng của orders ở phạm vi mặc định.
- <code>orders-service,prod</code>: secret riêng của orders trong profile production.

Một request tới Config Server với application <code>orders-service</code> và profile <code>prod</code> sẽ được backend dùng để tìm các đường dẫn phù hợp. Secret tìm được được chuyển thành property source cho client.

### Cấu hình Vault backend

Ví dụ cấu hình cơ bản cho Config Server:

~~~yaml
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        vault:
          host: vault.internal
          port: 8200
          scheme: https
          backend: secret
          default-key: application
          profile-separator: ","
          kv-version: 2
          authentication: TOKEN
          token: ${CONFIG_SERVER_VAULT_TOKEN}
~~~

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| <code>host</code> | Hostname của Vault |
| <code>port</code> | Cổng Vault |
| <code>scheme</code> | Giao thức kết nối, production nên dùng HTTPS |
| <code>backend</code> | Tên KV mount hoặc backend được cấu hình |
| <code>default-key</code> | Tên khóa dùng cho cấu hình mặc định chung, thường là <code>application</code> |
| <code>profile-separator</code> | Dấu phân cách giữa application và profile trong quy ước đường dẫn |
| <code>kv-version</code> | Phiên bản KV engine, thường là 1 hoặc 2 |

Tên thuộc tính và các tùy chọn hỗ trợ có thể thay đổi theo phiên bản Spring Cloud Config. Hãy đối chiếu với phiên bản dependency đang dùng khi triển khai thật.

Trong ví dụ này, <code>CONFIG_SERVER_VAULT_TOKEN</code> là biến môi trường của chính tiến trình Config Server. Nó được đưa vào lúc triển khai và không được commit giá trị thật vào Git. Phương thức TOKEN phù hợp cho ví dụ hoặc môi trường kiểm thử; production nên ưu tiên phương thức xác thực workload mà nền tảng hỗ trợ, với policy giới hạn quyền đọc.

### KV version 1 và version 2

Vault KV có hai phiên bản thường gặp:

- **KV v1:** lưu cặp key/value đơn giản, không cung cấp version history theo cách của KV v2.
- **KV v2:** hỗ trợ version của secret, metadata và thao tác khôi phục phiên bản theo khả năng cấu hình của Vault.

Config Server cần được cấu hình đúng phiên bản engine. Nếu mount thực tế là KV v2 nhưng backend được khai báo là KV v1, truy vấn có thể thất bại do khác cấu trúc API. Ngược lại, khai báo nhầm KV v2 cho mount KV v1 cũng dẫn tới lỗi đọc.

Không tự thêm đoạn <code>/data/</code> vào tên backend chỉ vì API nội bộ KV v2 sử dụng đường dẫn đó. Hãy khai báo mount theo cấu hình backend mà Spring Cloud Config yêu cầu; thư viện tích hợp xử lý chi tiết API tương ứng.

### Ví dụ dữ liệu trong Vault

Có thể lưu một nhóm thuộc tính không nhạy cảm cùng một secret nhạy cảm trong cùng credential path nếu policy và chủ sở hữu phù hợp. Tuy nhiên, thường nên tách theo mức độ nhạy cảm và vòng đời.

Ví dụ dữ liệu cho dịch vụ orders:

~~~json
{
  "orders.inventory.base-url": "https://inventory.internal",
  "orders.database.username": "orders_app",
  "orders.database.password": "secret-value-managed-by-vault"
}
~~~

Đây là dữ liệu minh họa, không phải mật khẩu để sử dụng. Config Server có thể trả các cặp key/value thành thuộc tính Spring. Ứng dụng có thể bind chúng bằng <code>@ConfigurationProperties</code> như các thuộc tính khác.

## 4. Xác thực và policy cho Vault

Config Server cần một danh tính riêng để đọc Vault. Danh tính này không nên là token quản trị toàn quyền.

Vault hỗ trợ nhiều phương thức xác thực, chẳng hạn token, AppRole, Kubernetes auth hoặc các phương thức gắn với nền tảng triển khai. Chọn phương thức mà môi trường có thể cấp và xoay vòng an toàn. Tên property, enum và các trường cấu hình cụ thể phụ thuộc phiên bản Spring Cloud Config/Spring Vault.

Một số nguyên tắc:

- Dùng workload identity thay vì token cá nhân của kỹ sư.
- Chỉ cấp quyền đọc những path Config Server cần phân phối.
- Tách policy cho môi trường dev, staging và production.
- Không cấp quyền tạo, sửa hoặc xóa secret nếu Config Server chỉ cần đọc.
- Đặt thời hạn và quy trình thu hồi credential rõ ràng.
- Bật audit ở Vault để biết danh tính nào đã truy cập path nào.
- Không ghi token hoặc giá trị secret vào log.

Ví dụ policy chỉ cho phép đọc một số path:

~~~hcl
path "secret/data/application" {
  capabilities = ["read"]
}

path "secret/data/application,prod" {
  capabilities = ["read"]
}

path "secret/data/orders-service" {
  capabilities = ["read"]
}

path "secret/data/orders-service,prod" {
  capabilities = ["read"]
}
~~~

Đây là ví dụ minh họa cho KV v2 policy path. Cần điều chỉnh path theo mount, profile separator và cách tổ chức thực tế. Với production, nên giới hạn chính xác hơn theo các đường dẫn cần thiết thay vì dùng wildcard rộng.

Nếu Config Server phục vụ nhiều nhóm ứng dụng, không nên mặc định cấp cho một token quyền đọc toàn bộ mount. Có thể tách Config Server theo trust boundary hoặc dùng nhiều danh tính/backend mapping nếu kiến trúc và phiên bản hỗ trợ.

## 5. CredHub backend trong Spring Cloud Config

CredHub là dịch vụ quản lý credential thường gặp trong hệ sinh thái Cloud Foundry. Nó lưu trữ và phân phối các loại credential như password, value, JSON và certificate theo mô hình quyền truy cập của nền tảng.

Spring Cloud Config Server có backend tích hợp với CredHub. Config Server kết nối tới CredHub, tìm credential theo tên ứng dụng/profile và chuyển dữ liệu thành property source.

### Quy ước credential name

Một quy ước minh họa là đặt credential theo application và profile:

~~~text
/application/default
/orders-service/default
/orders-service/prod
/inventory-service/default
/inventory-service/prod
~~~

Tên và cách ánh xạ chính xác cần theo backend CredHub của phiên bản Spring Cloud Config. Không nên giả định mọi khả năng của Git như branch, tag hoặc commit đều tồn tại trong CredHub. CredHub dùng tên credential và quyền truy cập thay cho mô hình lịch sử Git.

### Cấu hình CredHub backend

Ví dụ cấu hình endpoint:

~~~yaml
spring:
  cloud:
    config:
      server:
        credhub:
          url: https://credhub.internal
~~~

Config Server cần được cấu hình xác thực với CredHub theo cơ chế mà nền tảng cung cấp, thường gắn với danh tính và quyền của ứng dụng trên Cloud Foundry/UAA hoặc cấu hình OAuth2 được hỗ trợ. Không lưu access token dài hạn dạng rõ trong Git.

CredHub credential có thể là JSON chứa nhiều thuộc tính:

~~~json
{
  "orders.database.username": "orders_app",
  "orders.database.password": "secret-value-managed-by-credhub",
  "orders.provider.api-key": "example-secret"
}
~~~

Backend có thể đọc JSON credential và cung cấp các phần tử như property cho Config Client. Cần kiểm tra cách đặt tên credential, kiểu credential được hỗ trợ và quy tắc mapping theo phiên bản đang dùng.

### Khi nào CredHub phù hợp?

CredHub thường phù hợp khi nền tảng đã vận hành Cloud Foundry và có quy trình cấp danh tính, quyền truy cập cũng như quản lý credential qua CredHub. Nếu hệ thống đang chạy Kubernetes hoặc hạ tầng khác, Vault hoặc secret manager gắn với nền tảng đó có thể tự nhiên hơn.

Không nên chọn CredHub chỉ vì tên gọi tương tự Vault. Hãy cân nhắc hệ sinh thái đang triển khai, khả năng tích hợp danh tính, audit, backup, rotation và kỹ năng vận hành của nhóm.

## 6. Tổ chức cấu hình thường và secret theo nguồn

Không nhất thiết mọi thuộc tính đều phải đặt trong secret manager. Cấu hình thường và bí mật có yêu cầu vòng đời khác nhau.

Một cách chia tham khảo:

| Dữ liệu | Nguồn thường phù hợp | Ví dụ |
|---|---|---|
| Cấu hình ít nhạy cảm, cần review và lịch sử | Git | Log level, timeout mặc định, feature flag |
| Bí mật tĩnh | Vault/CredHub | DB password, API key |
| Chứng thư và private key | Secret manager hoặc PKI | TLS certificate, signing key |
| Credential động, có lease | Vault hoặc dịch vụ chuyên dụng | Database user tạm thời |
| Cấu hình theo môi trường nhưng không nhạy cảm | Git profile/label | URL nội bộ, pool size |
| Tham chiếu tới secret | Git hoặc Config Server | Tên secret path, alias |

Khi dùng nhiều nguồn, Config Server có thể hỗ trợ composite repository để ghép cấu hình từ nhiều backend trong các cấu hình phù hợp. Cần xác định thứ tự ưu tiên và hành vi khi một backend không sẵn sàng. Nếu một secret backend lỗi, không nên để server âm thầm trả cấu hình thiếu mà ứng dụng vẫn khởi động với giá trị mặc định không an toàn.

Một nguyên tắc quan trọng là không nhân bản bí mật giữa Git và secret manager. Git có thể lưu tên tham chiếu, path hoặc metadata không nhạy cảm; giá trị thật nằm trong hệ thống được bảo vệ.

## 7. Secret tĩnh, secret động và vòng đời credential

Secret manager có thể cung cấp các loại dữ liệu với vòng đời khác nhau.

### Secret tĩnh

Secret tĩnh là giá trị được tạo trước và lưu lại cho đến khi được cập nhật hoặc thu hồi, ví dụ API key của nhà cung cấp hoặc mật khẩu ứng dụng. Quy trình vận hành cần:

1. Tạo secret trong Vault/CredHub.
2. Cấp quyền đọc cho đúng danh tính.
3. Xác nhận Config Server hoặc ứng dụng đọc được giá trị.
4. Phát hành hoặc refresh ứng dụng để nạp giá trị mới.
5. Xác nhận hoạt động bằng secret mới.
6. Thu hồi giá trị cũ sau khi các instance đã chuyển đổi.

Không nên thu hồi secret cũ trước khi biết tất cả consumer đã chuyển sang secret mới, trừ khi có sự cố bảo mật cần thu hồi khẩn cấp.

### Secret động

Một số backend như Vault có thể tạo credential động với thời hạn hoặc lease, ví dụ tài khoản database tạm thời. Secret động có thể giảm thời gian tồn tại của credential và giúp audit rõ hơn.

Tuy nhiên, Config Server chỉ đọc và phân phối property source không tự động bảo đảm ứng dụng gia hạn lease, thay credential trong connection pool hoặc đóng credential cũ đúng lúc. Nếu ứng dụng cần vòng đời động, cần xác minh backend integration có hỗ trợ lease/renewal trong phiên bản cụ thể hay không. Nếu không, nên để ứng dụng hoặc agent chuyên trách quản lý lease trực tiếp.

Không coi một secret động như chuỗi cấu hình bất biến có thể nạp một lần khi khởi động rồi dùng mãi.

### Xoay vòng và thu hồi

Khi xoay vòng secret:

- Xác định mọi dịch vụ và instance đang sử dụng secret.
- Tạo giá trị mới hoặc cập nhật credential theo quy trình.
- Cập nhật nguồn cung cấp và kích hoạt refresh/redeploy phù hợp.
- Xác nhận kết nối mới thành công trên tất cả instance.
- Thu hồi giá trị cũ.
- Lưu dấu vết thời gian, chủ sở hữu và kết quả xác nhận.

Nếu secret đã bị lộ, ưu tiên thu hồi hoặc xoay vòng theo quy trình ứng phó sự cố. Chỉ xóa secret khỏi Git hoặc khỏi một path hiện tại là chưa đủ nếu bản sao hoặc lịch sử vẫn còn.

## 8. Bảo vệ đường truyền và Config Server

Trong mô hình Config Server làm trung gian, secret được đọc từ backend rồi gửi qua HTTP response cho client. Vì vậy cần bảo vệ cả hai chặng:

1. Config Server tới Vault/CredHub.
2. Config Client tới Config Server.

Dùng HTTPS và xác minh chứng thư ở cả hai kết nối. Nếu backend yêu cầu mutual TLS, quản lý keystore/truststore và private key theo cơ chế secret của nền tảng. Không tắt kiểm tra chứng thư để xử lý lỗi tạm thời.

Ở phía Config Server:

- Bảo vệ endpoint cấu hình bằng xác thực và phân quyền.
- Chỉ cho phép client đọc đúng phạm vi ứng dụng cần thiết.
- Giới hạn truy cập mạng tới Config Server.
- Bảo vệ log, heap dump, trace và endpoint Actuator.
- Không trả secret cho client không được phép.
- Tách danh tính đọc Vault/CredHub khỏi danh tính quản trị máy chủ.
- Bật audit ở secret manager và lưu log truy cập Config Server.

Ở phía client:

- Chỉ cấp quyền đọc cấu hình cho workload hợp lệ.
- Không ghi secret vào log hoặc exception.
- Giới hạn quyền truy cập process, container, debug endpoint và heap dump.
- Không đưa giá trị bí mật vào metric label, tracing tag hoặc thông báo lỗi.
- Xử lý cấu hình thiếu secret như lỗi khởi động nếu secret là bắt buộc.

TLS bảo vệ đường truyền, nhưng không thay thế authorization. Một client đã xác thực vẫn cần quyền chỉ đọc đúng cấu hình của nó.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Config Server không kết nối được Vault | DNS, route, port, TLS hoặc Vault seal/unavailable | Kiểm tra kết nối từ chính Config Server và trạng thái Vault |
| HTTP 403 từ Vault | Policy không cho đọc path hoặc token sai phạm vi | Xem audit log và policy của danh tính server |
| Không tìm thấy secret | Sai backend mount, path, application/profile hoặc key | Đối chiếu quy ước tên và dữ liệu trong secret store |
| KV v1/v2 lỗi | Cấu hình sai phiên bản engine | Xác nhận mount thực tế và thuộc tính kv-version |
| Config Server khởi động được nhưng request thất bại | Backend chỉ được truy cập khi có request hoặc credential hết hạn | Đối chiếu log theo request ID |
| Config Client nhận thiếu thuộc tính | Credential JSON/path thiếu khóa hoặc mapping sai | Kiểm tra property source và validation của client |
| Secret cũ vẫn được dùng | Client chưa refresh/redeploy hoặc cache/bean giữ giá trị cũ | Xác nhận thời điểm nạp và giá trị trong từng instance |
| Một số instance đọc được, số khác lỗi | Credential hoặc truststore không đồng nhất | So sánh cấu hình runtime của từng replica |
| CredHub trả 401/403 | Danh tính OAuth/UAA hoặc quyền credential không hợp lệ | Kiểm tra binding, token lifecycle và permission |
| Ứng dụng lỗi sau rotation | Secret mới chưa được cấp đồng bộ hoặc consumer chưa nạp | Kiểm tra thứ tự rotation, refresh và kết nối mới |

Quy trình điều tra nên đi theo thứ tự:

1. Xác nhận client đang yêu cầu đúng application, profile và label.
2. Gọi endpoint Config Server và xem property source nào được trả về, tránh in secret ra màn hình chia sẻ.
3. Xác định lỗi nằm ở Config Server hay ở backend.
4. Kiểm tra danh tính mà Config Server sử dụng để truy cập secret store.
5. Kiểm tra policy, path, loại engine và version.
6. Xác nhận client đã nạp và bind giá trị mới.
7. Sau khi khôi phục, kiểm tra tất cả replica và thu hồi credential cũ nếu cần.

Không nên thử đọc secret bằng tài khoản quản trị cá nhân rồi kết luận service account của Config Server có quyền. Hãy kiểm tra bằng đúng danh tính runtime và ghi nhận audit.

## 10. Thiết kế dự phòng khi secret backend không sẵn sàng

Secret backend có thể gặp lỗi mạng, bảo trì, hết hạn credential hoặc sự cố dịch vụ. Cần quyết định trước ứng dụng sẽ phản ứng ra sao.

Với thuộc tính bắt buộc như DB password, signing key hoặc API token, thiếu secret nên làm ứng dụng không sẵn sàng hoặc không khởi động. Dùng một giá trị mặc định rỗng hoặc giả có thể khiến lỗi xuất hiện muộn hơn và khó chẩn đoán.

Với thuộc tính tùy chọn, có thể dùng fallback đã được phê duyệt nếu hành vi đó an toàn. Không dùng fallback để che lỗi backend khi dịch vụ cần bí mật để hoạt động.

Các điểm cần thiết kế:

- Timeout và retry có giới hạn cho kết nối backend.
- Chính sách fail-fast khi secret bắt buộc không thể lấy.
- Health/readiness phản ánh khả năng cung cấp cấu hình cần thiết.
- Cảnh báo khi credential gần hết hạn hoặc backend không phản hồi.
- Kế hoạch khôi phục và rollback secret.
- Hành vi của ứng dụng khi secret được xoay vòng trong lúc đang chạy.

Không mặc định rằng Config Server sẽ luôn phục vụ bản secret cũ khi backend mất kết nối. Hành vi phụ thuộc backend, cache, phiên bản và cấu hình cụ thể. Nếu cần stale-value fallback, phải thiết kế và kiểm thử rõ ràng, bao gồm giới hạn thời gian và rủi ro bảo mật.

## 11. Kiểm thử tích hợp và vận hành

Trước khi đưa backend secret vào production, nên kiểm tra cả đường đọc và quyền truy cập.

### Kiểm thử chức năng

- Config Server kết nối được tới đúng Vault mount hoặc CredHub endpoint.
- Request theo application/profile trả đúng property source.
- Cấu hình chung và cấu hình riêng được ghép theo mong đợi.
- Secret không có quyền đọc bị từ chối.
- Secret bắt buộc bị thiếu khiến client validation thất bại.
- Thay đổi secret được nạp sau refresh/redeploy theo cơ chế đã chọn.
- Client không có quyền không thể đọc cấu hình của ứng dụng khác.

### Kiểm thử bảo mật

- Config Server dùng workload identity thay vì tài khoản cá nhân.
- Policy chỉ cho phép đọc path cần thiết.
- TLS được xác minh ở cả hai chặng.
- Token và secret không xuất hiện trong log.
- Endpoint Actuator được giới hạn.
- Audit log ghi nhận danh tính và đường dẫn truy cập.
- Xoay vòng và thu hồi secret đã được diễn tập.

### Kiểm thử khả năng phục hồi

- Backend tạm thời không phản hồi.
- Credential hết hạn hoặc bị thu hồi.
- Một Config Server replica mất kết nối tới secret store.
- Secret được xoay vòng trong khi nhiều client đang chạy.
- Ứng dụng khởi động khi secret bắt buộc bị thiếu.

Kết quả kiểm thử cần thể hiện rõ ứng dụng fail-fast hay dùng fallback, thời gian phát hiện lỗi, phạm vi ảnh hưởng và cách khôi phục. Chỉ kiểm tra HTTP 200 từ Config Server là chưa đủ; phải xác nhận ứng dụng nhận đúng thuộc tính và kết nối được tới tài nguyên cần thiết.

## 12. Checklist thiết kế Vault/CredHub backend

- [ ] Đã chọn rõ Config Server làm trung gian hay từng ứng dụng truy cập secret manager trực tiếp.
- [ ] Đã chọn Vault hoặc CredHub phù hợp với nền tảng và khả năng vận hành.
- [ ] Đã thống nhất quy ước path/credential name theo application và profile.
- [ ] Đã cấu hình đúng Vault mount và KV version nếu dùng Vault.
- [ ] Đã xác minh khả năng hỗ trợ profile, label và mapping của backend theo phiên bản.
- [ ] Config Server dùng workload identity và policy chỉ đọc đúng secret cần thiết.
- [ ] Client tới Config Server và Config Server tới backend đều dùng TLS.
- [ ] Không lưu token, password hoặc private key dạng rõ trong Git.
- [ ] Có audit, rotation, revoke và chủ sở hữu cho mỗi secret.
- [ ] Đã xác định secret nào là tĩnh, secret nào có lease/renewal.
- [ ] Đã kiểm thử lỗi backend, thiếu secret và hành vi fail-fast/fallback.
- [ ] Đã xác nhận refresh/redeploy cập nhật giá trị trên mọi instance.
- [ ] Log, Actuator, trace và heap dump không làm lộ secret.

Vault và CredHub giúp đưa bí mật ra khỏi repository cấu hình và cung cấp cơ chế xác thực, phân quyền, audit cùng vòng đời secret. Khi tích hợp chúng với Spring Cloud Config, nhóm cần xác định rõ Config Server hay ứng dụng là bên truy cập backend, giới hạn quyền theo nhu cầu và kiểm soát việc phân phối giá trị tới client. Kết hợp secret manager với validation, TLS, rotation và kiểm thử phục hồi giúp cấu hình tập trung vận hành an toàn và nhất quán.


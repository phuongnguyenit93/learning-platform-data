# Lựa chọn Secrets Manager hoặc Parameter Store

Ứng dụng AWS thường cần đọc những giá trị như endpoint dịch vụ, tên bucket, feature setting, API key, mật khẩu cơ sở dữ liệu hoặc token của nhà cung cấp bên ngoài. Những giá trị này có mức độ nhạy cảm và vòng đời khác nhau. Nếu lưu tất cả trong file cấu hình, biến môi trường cố định hoặc source code, tổ chức dễ làm lộ thông tin, khó phân quyền truy cập và khó thay đổi an toàn khi hệ thống mở rộng.

AWS cung cấp hai dịch vụ thường được cân nhắc cho nhu cầu này:

- **AWS Secrets Manager** được thiết kế để quản lý secret như thông tin đăng nhập cơ sở dữ liệu, API key và token. Dịch vụ có các năng lực chuyên biệt như xoay vòng secret, tích hợp với một số dịch vụ dữ liệu, sao chép secret sang Region khác và quản lý version theo trạng thái.
- **AWS Systems Manager Parameter Store** quản lý dữ liệu cấu hình theo tên và phân cấp. Dịch vụ hỗ trợ các kiểu **String**, **StringList** và **SecureString**, tích hợp IAM/KMS, lưu lịch sử version và cung cấp các tier với giới hạn, chính sách và mô hình chi phí khác nhau.

Trong hệ sinh thái **CLOUD_PROVIDERS_AWS**, lựa chọn đúng giúp ứng dụng chạy trên EC2, ECS, EKS, Lambda hoặc pipeline CI/CD nhận cấu hình và thông tin xác thực theo cách có thể kiểm soát. Mục tiêu của module là giúp người học thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí; vì vậy cần xem xét cả độ nhạy cảm của dữ liệu, cách ứng dụng sử dụng dữ liệu, quyền IAM, KMS, vòng đời thay đổi và yêu cầu vận hành.

## 1. Hai dịch vụ giải quyết hai nhóm nhu cầu

Secrets Manager và Parameter Store có vùng chức năng giao nhau: cả hai đều lưu giá trị ngoài source code, cung cấp cơ chế bảo vệ truy cập và cho phép ứng dụng lấy giá trị bằng API hoặc SDK. Với Parameter Store, chỉ kiểu SecureString mới dùng KMS để mã hóa giá trị theo cơ chế này. Tuy nhiên, chúng có định hướng khác nhau.

Parameter Store phù hợp khi cần quản lý tập trung các cấu hình như URL dịch vụ, tên queue, ID AMI được phê duyệt, giới hạn tính năng, tên bucket hoặc một giá trị nhạy cảm đơn giản được mã hóa bằng SecureString. Hierarchy giúp tổ chức tham số theo ứng dụng, môi trường và thành phần.

Secrets Manager phù hợp khi giá trị là credential hoặc token có vòng đời bảo mật riêng. Dịch vụ giúp lưu version của secret, lên lịch xoay vòng, phối hợp cập nhật credential ở hệ thống đích và hỗ trợ sao chép secret giữa các Region. Một số dịch vụ AWS có thể tạo và quản lý secret thay cho người dùng.

| Câu hỏi | Nên bắt đầu xem xét |
|---|---|
| Giá trị là cấu hình không nhạy cảm như endpoint, tên queue hoặc ID AMI? | Parameter Store String |
| Giá trị cần mã hóa, nhưng không cần cơ chế rotation chuyên biệt? | Parameter Store SecureString |
| Cần lưu mật khẩu DB, API key hoặc token có vòng đời secret? | Secrets Manager |
| Cần tự động xoay credential và cập nhật hệ thống đích? | Secrets Manager |
| Cần lưu nhiều cấu hình theo path và đọc theo nhóm? | Parameter Store |
| Cần chia sẻ parameter advanced giữa các account? | Parameter Store advanced shared parameters |
| Cần sao chép secret sang Region khác để hỗ trợ ứng dụng đa Region? | Secrets Manager replication |
| Cần chính sách hết hạn hoặc thông báo khi parameter không đổi quá lâu? | Parameter Store advanced parameter policies |

Không nên quyết định chỉ dựa vào việc giá trị có phải là mật khẩu hay không. Cần hỏi thêm ai đọc dữ liệu, dữ liệu thay đổi bao lâu một lần, có cần rotation không, hệ thống đích có hỗ trợ rotation không, ứng dụng có thể chịu gián đoạn trong quá trình đổi credential không và chi phí theo quy mô sẽ ra sao.

## 2. So sánh khả năng chính

| Tiêu chí | AWS Secrets Manager | Systems Manager Parameter Store |
|---|---|---|
| Mục đích chính | Quản lý secret và vòng đời credential | Quản lý cấu hình và parameter tập trung |
| Kiểu dữ liệu | Secret value thường là chuỗi hoặc JSON; có thể chứa credential nhiều trường | String, StringList, SecureString |
| Mã hóa | Mã hóa secret bằng AWS KMS | SecureString dùng KMS để mã hóa giá trị |
| Xoay vòng tự động | Có rotation được quản lý cho một số secret và rotation bằng Lambda cho các trường hợp khác | Không có cơ chế credential rotation chuyên biệt tích hợp sẵn; có thể tự xây dựng automation |
| Version | Version ID và staging labels như AWSCURRENT, AWSPREVIOUS, AWSPENDING | Version số tăng dần và parameter labels |
| Phân cấp tên | Tên secret và tag; không có hierarchy path tương đương Parameter Store | Hierarchy theo path, tối đa 15 cấp |
| Sao chép đa Region | Hỗ trợ replication secret sang Region khác | Không có mô hình replica parameter đa Region tương đương; cần triển khai/đồng bộ riêng |
| Chia sẻ cross-account | Resource policy, IAM và customer managed KMS key | Shared advanced parameters qua AWS RAM |
| Chính sách parameter | Không theo mô hình expiration/no-change của Parameter Store | Advanced tier hỗ trợ Expiration, ExpirationNotification, NoChangeNotification |
| Dịch vụ tích hợp | Tích hợp chuyên biệt với một số dịch vụ và quy trình rotation | Tích hợp rộng với Systems Manager, EC2, CloudFormation và các workflow khác |
| Chi phí | Tính phí theo số secret lưu trữ và API call; rotation có thể phát sinh chi phí Lambda | Standard không có phụ phí lưu trữ; advanced tier và throughput cao có thể phát sinh phí |

Các giới hạn, giá và tính năng có thể thay đổi theo Region và thời điểm. Trước khi thiết kế hệ thống production, kiểm tra trang tài liệu và giá AWS hiện hành thay vì đưa một con số cố định vào kiến trúc.

## 3. Phân loại dữ liệu trước khi chọn dịch vụ

Hãy phân loại giá trị theo mức nhạy cảm và cách sử dụng. Một ứng dụng thương mại điện tử có thể có các dữ liệu sau:

| Dữ liệu | Tính chất | Lựa chọn tham khảo |
|---|---|---|
| ORDERS_QUEUE_URL | Endpoint, không bí mật | Parameter Store String |
| PAYMENTS_API_BASE_URL | Endpoint, không bí mật | Parameter Store String |
| FEATURE_CHECKOUT_V2 | Cờ cấu hình | Parameter Store hoặc AWS AppConfig nếu cần quản lý rollout cấu hình |
| DATABASE_PASSWORD | Credential có thể cần rotation | Secrets Manager |
| PAYMENT_PROVIDER_API_KEY | API key do bên ngoài cấp, cần quản lý vòng đời | Secrets Manager |
| LICENSE_KEY | Giá trị nhạy cảm, ít thay đổi | Parameter Store SecureString hoặc Secrets Manager tùy yêu cầu kiểm toán và vòng đời |
| APPROVED_AMI_ID | ID tài nguyên được phê duyệt | Parameter Store String |
| PRIVATE_SIGNING_KEY | Khóa mật mã có yêu cầu sử dụng và bảo vệ đặc biệt | Cân nhắc AWS KMS hoặc AWS CloudHSM; không mặc định lưu khóa riêng tư thô như một parameter |

Một secret là dữ liệu nhạy cảm cần được kiểm soát ai đọc, khi nào đọc và cách thay đổi. Một configuration parameter mô tả hành vi hoặc môi trường chạy của ứng dụng. Có thể có giá trị cấu hình không nhạy cảm nhưng rất quan trọng đối với tính sẵn sàng; ngược lại, một secret ít thay đổi vẫn cần bảo vệ nghiêm ngặt.

Nếu ứng dụng cần phân phối feature flag theo phần trăm người dùng, kiểm tra cấu hình trước khi phát hành hoặc rollout có kiểm soát, hãy xem xét AWS AppConfig. Parameter Store phù hợp để lưu cấu hình, còn AppConfig bổ sung workflow triển khai cấu hình và kiểm soát rollout. Hai dịch vụ này có thể phối hợp.

## 4. Parameter Store: cấu trúc và loại parameter

Parameter Store là một capability của AWS Systems Manager. Parameter có tên duy nhất trong account và Region. Có thể dùng path phân cấp để chia dữ liệu theo ứng dụng, môi trường và nhóm cấu hình.

Ví dụ:

~~~text
/shop/orders/dev/database/host
/shop/orders/dev/database/port
/shop/orders/prod/database/host
/shop/orders/prod/database/password
/shop/payments/prod/provider/api-url
/shop/payments/prod/provider/api-key
/platform/approved-amis/al2023
~~~

Tên parameter giúp tổ chức dữ liệu, nhưng bản thân path không phải một ranh giới bảo mật tự động. IAM policy mới quyết định principal nào được đọc hoặc ghi parameter. Cần thiết kế path cùng với policy, đặc biệt khi dùng GetParametersByPath.

### 4.1. String

String lưu văn bản không được mã hóa bằng KMS như một SecureString. Dùng cho dữ liệu cấu hình không nhạy cảm, ví dụ endpoint, tên queue, ID AMI hoặc một giá trị boolean dạng chuỗi.

~~~bash
aws ssm put-parameter \
  --name "/shop/orders/prod/feature/checkout-v2" \
  --type "String" \
  --value "enabled" \
  --description "Enable checkout v2"
~~~

Không lưu mật khẩu hoặc token vào String chỉ vì parameter nằm dưới path /prod. Path không mã hóa giá trị và không thay thế phân quyền.

### 4.2. StringList

StringList lưu danh sách các giá trị phân cách bằng dấu phẩy. Ví dụ, một danh sách subnet ID hoặc tên endpoint có thể được lưu trong một parameter. Kiểu này thuận tiện cho cấu hình đơn giản, nhưng không phải định dạng JSON tổng quát và không hỗ trợ cấu trúc lồng nhau.

~~~bash
aws ssm put-parameter \
  --name "/shop/orders/prod/allowed-regions" \
  --type "StringList" \
  --value "ap-southeast-1,ap-southeast-2"
~~~

Nếu ứng dụng cần object phức tạp, hãy dùng định dạng JSON trong String/SecureString khi phù hợp, hoặc chia thành nhiều parameter có tên rõ ràng.

### 4.3. SecureString

SecureString dành cho giá trị cần bảo vệ bằng AWS KMS, ví dụ license key, token hoặc một credential ít thay đổi. Parameter Store mã hóa giá trị khi ghi và chỉ trả plaintext khi caller yêu cầu giải mã, chẳng hạn dùng GetParameter với WithDecryption=true.

~~~bash
aws ssm put-parameter \
  --name "/shop/orders/prod/integration/license-key" \
  --type "SecureString" \
  --key-id "alias/shop-parameter-key" \
  --value "REPLACE_WITH_SECRET_VALUE" \
  --description "License key for Orders integration"
~~~

Ví dụ dùng giá trị thay thế thay cho credential thật. Không đặt giá trị secret thật trực tiếp trong shell history, CI log, script commit hoặc command line được ghi lại. Trong automation, lấy giá trị từ kênh bảo mật phù hợp và giới hạn quyền người chạy lệnh.

Để đọc parameter:

~~~bash
aws ssm get-parameter \
  --name "/shop/orders/prod/integration/license-key" \
  --with-decryption
~~~

Không có --with-decryption, API trả ciphertext/giá trị được bảo vệ thay vì plaintext. Caller cần quyền ssm:GetParameter và quyền kms:Decrypt trên key được sử dụng để giải mã.

## 5. Parameter tiers và throughput

Parameter Store có Standard và Advanced tier. Tier điều khiển giới hạn lưu trữ, kích thước giá trị, parameter policies và chia sẻ cross-account. Tier khác với throughput: throughput điều khiển tốc độ request, không phải dung lượng parameter.

| Thuộc tính | Standard | Advanced |
|---|---:|---:|
| Số lượng tối đa mỗi account/Region | 10.000 | 100.000 |
| Kích thước value tối đa | 4 KB | 8 KB |
| Parameter policies | Không | Có |
| Chia sẻ cross-account | Không | Có, qua AWS RAM |
| Các giá trị DataType url, json, jsonc | Không hỗ trợ | Hỗ trợ |
| Chi phí lưu trữ | Không phụ phí | Có tính phí |
| Có thể nâng cấp tier | Có | Không thể hạ xuống Standard |

Dùng Standard cho phần lớn cấu hình thông thường. Chỉ chọn Advanced khi cần giá trị lớn hơn, số lượng vượt giới hạn Standard, parameter policies hoặc chia sẻ cross-account. Việc nâng một parameter lên Advanced cần được xem là quyết định vòng đời vì parameter Advanced không thể hạ cấp về Standard.

### Parameter policies

Advanced parameters hỗ trợ một số policy giúp quản lý vòng đời:

- **Expiration:** xóa parameter tại thời điểm được chỉ định.
- **ExpirationNotification:** phát sự kiện EventBridge để thông báo trước thời điểm hết hạn.
- **NoChangeNotification:** phát sự kiện nếu parameter không thay đổi trong khoảng thời gian đã đặt.

Ví dụ policy có thể nhắc nhóm vận hành xem lại một AMI ID được phê duyệt nếu parameter không được cập nhật trong 60 ngày. Đây là cơ chế nhắc và quản lý vòng đời parameter, không phải cơ chế tự xoay credential tương đương Secrets Manager.

### Throughput

Nếu ứng dụng gọi Parameter Store với tần suất cao, cần xem xét throughput mặc định và chế độ throughput cao theo cấu hình account/Region. Throughput cao có thể phát sinh chi phí. Không nên tăng throughput trước khi đo request rate, sử dụng cache hợp lý và xác định các điểm đọc lặp lại.

## 6. Secrets Manager: secret, version và staging labels

Secrets Manager lưu secret dưới dạng một secret resource có metadata, version và các staging label. Giá trị có thể là chuỗi hoặc JSON, ví dụ:

~~~json
{
  "username": "orders_app",
  "password": "REPLACE_WITH_SECRET_VALUE",
  "engine": "mysql",
  "host": "orders-db.example.internal",
  "port": 3306,
  "dbname": "orders"
}
~~~

Ứng dụng có thể lấy toàn bộ JSON rồi đọc các trường cần thiết. Tránh đưa password vào phần mô tả, tag hoặc tên secret vì metadata thường có thể được đọc bởi principal rộng hơn quyền đọc giá trị.

Secrets Manager quản lý version. Một version có thể gắn một hoặc nhiều staging labels; các label thường gặp:

- **AWSCURRENT:** version hiện được xem là credential hiện hành.
- **AWSPREVIOUS:** version trước đó.
- **AWSPENDING:** version đang được chuẩn bị trong một quy trình rotation.

Ứng dụng thường đọc AWSCURRENT nếu không chỉ định version khác. Khi rotation hoàn tất, label hiện hành được chuyển sang version mới. Nhờ đó, ứng dụng không cần biết số version cụ thể mỗi lần lấy secret.

Có thể tạo secret bằng CLI:

~~~bash
aws secretsmanager create-secret \
  --name "shop/orders/prod/database" \
  --description "Database credentials for Orders production" \
  --secret-string '{"username":"orders_app","password":"REPLACE_WITH_SECRET_VALUE"}'
~~~

Không dùng mật khẩu thật trong lệnh minh họa hoặc log. Trong production, ưu tiên tạo secret qua console, IaC hoặc automation bảo mật và truyền secret value từ nguồn an toàn.

## 7. Mã hóa bằng AWS KMS và quyền truy cập

### 7.1. Secrets Manager

Secrets Manager mã hóa secret value bằng AWS KMS. Có thể dùng AWS managed key aws/secretsmanager hoặc customer managed KMS key. Customer managed key hữu ích khi cần kiểm soát key policy, audit quyền giải mã, tách quyền theo ứng dụng hoặc hỗ trợ chia sẻ cross-account.

Caller thường cần quyền secretsmanager:GetSecretValue. Khi secret sử dụng customer managed key, caller và dịch vụ cần quyền KMS phù hợp để giải mã. Với chia sẻ cross-account, không thể dùng AWS managed key aws/secretsmanager; cần customer managed key và cấu hình key policy cho account/principal đích.

### 7.2. Parameter Store SecureString

SecureString dùng KMS để mã hóa giá trị. Với key mặc định aws/ssm, việc kiểm soát chi tiết ai được giải mã có giới hạn hơn vì các principal trong account có quyền lấy parameter có thể được phép giải mã theo cấu hình key mặc định. Nếu cần phân tách quyền đọc các nhóm secret, hãy dùng customer managed key và IAM/key policy có điều kiện phù hợp.

Để đọc một SecureString, principal cần:

1. Quyền Systems Manager như ssm:GetParameter trên ARN của parameter.
2. Quyền kms:Decrypt trên KMS key dùng để mã hóa parameter.
3. Được key policy cho phép sử dụng key.

Với standard SecureString, quá trình ghi dùng KMS Encrypt; với advanced SecureString, Parameter Store sử dụng data key và cần quyền KMS tương ứng như kms:GenerateDataKey. Hãy dùng quyền đúng theo tier và hướng dẫn KMS hiện hành.

### 7.3. Least privilege và path hierarchy

Có thể cấp quyền theo ARN parameter, nhưng cần chú ý cách API GetParametersByPath được IAM authorize. Nếu principal có quyền đọc path cha với recursive=true, principal có thể đọc parameter con bên dưới path đó, kể cả khi policy có một deny ở resource con theo cách triển khai thông thường. Vì vậy, không chia sẻ một path cha rộng cho role chỉ được đọc một parameter nhạy cảm.

Ví dụ, tách path theo application và environment:

~~~text
/shop/orders/dev/*
/shop/orders/prod/*
/shop/payments/prod/*
~~~

Sau đó gán role theo ứng dụng và môi trường, kiểm tra cả GetParameter, GetParameters, GetParameterHistory và GetParametersByPath. GetParameterHistory có thể trả về các version, kể cả version hiện tại, vì vậy không được bỏ sót API này khi giới hạn quyền đọc. Với GetParametersByPath, kiểm tra quyền trên mọi path cha có thể được gọi ở chế độ recursive. Với SecureString, hạn chế kms:Decrypt bằng customer managed key có thể cung cấp thêm lớp kiểm soát giải mã.

## 8. Rotation: khi nào cần Secrets Manager?

Rotation là quá trình cập nhật credential ở cả secret store và hệ thống đích. Chỉ thay password trong Secrets Manager mà không đổi password trong database hoặc API provider sẽ làm ứng dụng mất kết nối. Tương tự, thay credential trong hệ thống đích mà không cập nhật secret có thể làm mọi client dùng credential cũ thất bại.

Secrets Manager có ba cách tiếp cận chính:

1. **Managed rotation:** dùng cho một số secret do dịch vụ AWS quản lý, ví dụ secret được tạo qua quy trình tích hợp với dịch vụ dữ liệu. Dịch vụ quản lý quy trình rotation phù hợp mà không cần người dùng tự viết Lambda rotation.
2. **Lambda rotation:** Secrets Manager gọi Lambda function theo lịch. Function cập nhật credential ở hệ thống đích và version secret.
3. **Managed external secrets rotation:** dùng cho một số secret của đối tác được hỗ trợ, cho phép rotation trên hệ thống bên ngoài theo tích hợp tương ứng.

Với Lambda rotation, quy trình tiêu chuẩn gồm bốn bước:

| Bước | Mục đích |
|---|---|
| createSecret | Tạo version mới và gắn trạng thái chờ như AWSPENDING |
| setSecret | Cập nhật credential trong database hoặc hệ thống đích |
| testSecret | Thử xác thực bằng credential mới |
| finishSecret | Chuyển AWSCURRENT sang version mới và kết thúc rotation |

Rotation schedule dùng biểu thức rate() hoặc cron() và thời gian được tính theo UTC. Cần chọn cửa sổ phù hợp với giờ bảo trì, khả năng retry và mức độ chịu lỗi của ứng dụng.

### Single-user và alternating-users

Với chiến lược **single-user**, rotation đổi mật khẩu của một user. Đây là cách đơn giản và phù hợp với nhiều trường hợp, nhưng có một khoảng thời gian ngắn trong quy trình đổi password mà ứng dụng có thể gặp lỗi xác thực nếu lấy secret hoặc tạo kết nối đúng lúc credential thay đổi. Ứng dụng cần retry hợp lý và pool connection có thể phải tạo kết nối mới.

Với chiến lược **alternating-users**, hai user có quyền tương đương được luân phiên cập nhật. Trong quá trình rotation, một user còn hiệu lực trong khi user kia được đổi credential, giúp giảm nguy cơ gián đoạn với ứng dụng có yêu cầu sẵn sàng cao. Mô hình này cần thiết kế quyền database cẩn thận và credential quản trị đủ quyền để tạo hoặc cập nhật user còn lại.

Không phải mọi hệ thống đích đều hỗ trợ managed rotation. Với API key của nhà cung cấp bên ngoài, cần xác nhận API có khả năng phát hành key mới, giữ đồng thời key cũ và mới trong thời gian chuyển tiếp hay có endpoint thu hồi key. Nếu không có API hỗ trợ, có thể cần workflow tùy chỉnh hoặc quy trình xoay vòng có kiểm soát.

## 9. Tạo lịch rotation và vận hành an toàn

Ví dụ cấu hình rotation cho một secret đã có Lambda rotation function:

~~~bash
aws secretsmanager rotate-secret \
  --secret-id "shop/orders/prod/database" \
  --rotation-lambda-arn "arn:aws:lambda:ap-southeast-1:111122223333:function:RotateOrdersDatabaseSecret" \
  --rotation-rules '{"ScheduleExpression":"rate(30 days)","Duration":"2h"}'
~~~

Ví dụ minh họa cấu trúc CLI. Lambda function, quyền invoke, kết nối tới database và secret cần được cấu hình trước. Không nên sao chép ARN giả định vào production.

Các điểm cần kiểm tra:

- Lambda rotation có thể truy cập secret và hệ thống đích qua network.
- Execution role của Lambda chỉ có quyền cần thiết.
- Secret resource policy và KMS key policy cho phép các thao tác phù hợp.
- Hệ thống đích chấp nhận việc đổi credential và có cơ chế retry.
- Log không ghi plaintext password hoặc token.
- CloudWatch alarm theo dõi lỗi rotation và thời gian chạy.
- Có quy trình dừng rotation và xử lý khi AWSPENDING bị kẹt.
- Ứng dụng lấy lại secret khi cần, không giữ credential cũ trong cache vô thời hạn.

Nếu rotation thất bại, điều tra từng bước createSecret, setSecret, testSecret, finishSecret, quyền IAM/KMS, network, database connection và version staging label. Không xóa thủ công version hoặc chuyển label nếu chưa hiểu trạng thái của hệ thống đích.

## 10. Ứng dụng lấy secret và parameter như thế nào?

Ứng dụng nên lấy giá trị bằng SDK với IAM role gắn cho workload. EC2 dùng instance profile; ECS dùng task role; Lambda dùng execution role; EKS có thể dùng IAM Roles for Service Accounts hoặc EKS Pod Identity theo mô hình được cấu hình. Không nhúng access key tĩnh vào container image hoặc source code.

### Lấy secret từ Secrets Manager bằng AWS CLI

~~~bash
aws secretsmanager get-secret-value \
  --secret-id "shop/orders/prod/database" \
  --query SecretString \
  --output text
~~~

Lệnh trả secret value ra terminal; chỉ dùng để minh họa trong môi trường an toàn. Không in kết quả ra CI log, shell transcript hoặc ticket.

### Lấy parameter bằng AWS CLI

~~~bash
aws ssm get-parameters \
  --names "/shop/orders/prod/database/host" "/shop/orders/prod/database/port" \
  --with-decryption
~~~

Nếu lấy SecureString, caller cần kms:Decrypt. Với nhiều parameter, GetParameters có thể giảm số lần gọi so với lấy từng parameter riêng lẻ.

### Cache để giảm độ trễ và API call

Ứng dụng có thể dùng AWS Secrets Manager caching client hoặc cơ chế cache có kiểm soát để giảm API call và độ trễ. Parameter Store cũng có thể được cache trong ứng dụng hoặc qua extension/integration phù hợp. Cache cần có TTL và cơ chế refresh khi secret rotation hoặc cấu hình thay đổi.

TTL quá dài có thể khiến ứng dụng tiếp tục dùng credential cũ sau rotation. TTL quá ngắn làm tăng API request và chi phí. Với connection pool, cần bảo đảm ứng dụng tạo kết nối mới bằng credential mới khi cache được refresh; không giả định mọi connection hiện hữu tự đổi password.

## 11. Tích hợp CloudFormation và hạ tầng dưới dạng mã

Không ghi plaintext secret trực tiếp vào template, parameter file hoặc output. CloudFormation hỗ trợ dynamic references để lấy giá trị từ Secrets Manager hoặc Parameter Store khi stack operation cần giá trị.

### Secrets Manager dynamic reference

Ví dụ dùng secret JSON làm mật khẩu database:

~~~yaml
Resources:
  OrdersDatabase:
    Type: AWS::RDS::DBInstance
    Properties:
      Engine: mysql
      DBInstanceClass: db.t4g.small
      AllocatedStorage: 20
      MasterUsername: orders_admin
      MasterUserPassword: '{{resolve:secretsmanager:shop/orders/prod/database:SecretString:password}}'
~~~

Ví dụ chỉ minh họa cách tham chiếu. Template production cần thêm subnet group, security group, storage encryption, backup, deletion protection và các thuộc tính RDS phù hợp. Không dùng dynamic reference trong thuộc tính tạo primary resource identifier hoặc nơi có thể làm lộ giá trị trong tên tài nguyên hay output.

### Parameter Store SecureString dynamic reference

CloudFormation có thể tham chiếu SecureString bằng cú pháp ssm-secure ở các resource property được hỗ trợ:

~~~yaml
Resources:
  OrdersDatabase:
    Type: AWS::RDS::DBInstance
    Properties:
      Engine: mysql
      MasterUsername: orders_app
      MasterUserPassword: '{{resolve:ssm-secure:/shop/orders/prod/database/password:3}}'
~~~

Dynamic reference ssm-secure yêu cầu parameter name và có thể chỉ định version số. CloudFormation không hỗ trợ truy cập SecureString Parameter Store ở account khác qua kiểu tham chiếu này; parameter label và public parameter cũng không được hỗ trợ trong dynamic reference. Chỉ dùng ở các resource property được AWS hỗ trợ.

Dynamic reference giảm việc lưu plaintext trong template, nhưng không thay thế quyền IAM của CloudFormation execution role hoặc quyền KMS. Ngoài ra, giá trị được resolve có thể được truyền tới dịch vụ đích để tạo/cập nhật resource; cần kiểm tra dịch vụ đích có lưu hoặc hiển thị giá trị theo cách nào.

## 12. Chia sẻ giữa account và Region

### 12.1. Secrets Manager cross-account

Để một principal ở account khác đọc secret, cần phối hợp:

1. Resource-based policy gắn vào secret ở account sở hữu.
2. Identity-based policy cho principal ở account tiêu thụ.
3. Customer managed KMS key và key policy cho phép giải mã phù hợp.

AWS managed key aws/secretsmanager không phù hợp cho cross-account access. Hãy giới hạn principal cụ thể, action cần thiết và resource; dùng BlockPublicPolicy khi tạo resource policy để giúp ngăn cấp quyền công khai. Tránh cấp quyền PutResourcePolicy quá rộng vì principal có thể sửa policy và mở rộng quyền truy cập.

### 12.2. Secrets Manager multi-Region replication

Secrets Manager hỗ trợ sao chép secret từ primary Region sang một hoặc nhiều replica Region. Khi giá trị secret thay đổi ở primary, thay đổi được truyền tới replica theo cơ chế replication. Quá trình này có thể bất đồng bộ, vì vậy ứng dụng ở Region nhận cần xử lý độ trễ và trạng thái replication.

Replica có thể dùng KMS key tại Region đích. Nếu ứng dụng cần failover, phải kiểm thử khả năng đọc secret ở Region dự phòng, quyền IAM/KMS, network và trạng thái replica trước khi sự cố xảy ra. Không coi việc tạo replica là đã hoàn tất toàn bộ DR plan.

### 12.3. Parameter Store cross-account

Parameter Store hỗ trợ chia sẻ Advanced parameters giữa các account thông qua AWS Resource Access Manager (AWS RAM). Standard parameters không thể chia sẻ theo cơ chế này. Account tiêu thụ cần chấp nhận resource share khi cấu hình yêu cầu, có quyền truy cập parameter và quyền KMS phù hợp nếu parameter là SecureString được mã hóa bằng customer managed key.

Parameter Store không cung cấp mô hình replica đa Region giống Secrets Manager. Nếu cần cùng một cấu hình ở nhiều Region, có thể quản lý bằng IaC hoặc pipeline đồng bộ, đồng thời xác định Region nào là nguồn chuẩn và cách xử lý khi cập nhật thất bại một phần.

## 13. Tích hợp với EC2, ECS, EKS, Lambda và CI/CD

### EC2

Gắn instance profile với quyền chỉ đọc các parameter/secret mà ứng dụng trên máy cần. Có thể dùng SSM Agent, user data hoặc ứng dụng khởi động để lấy cấu hình; tránh đưa secret vào user data vì dữ liệu này có thể được truy xuất từ metadata hoặc API quản lý instance bởi principal có quyền phù hợp.

### ECS

ECS task definition có thể tham chiếu secret từ Secrets Manager hoặc Parameter Store theo tích hợp của ECS. Khi dùng secret injection vào environment variable, giá trị được nạp khi container khởi chạy; nếu secret rotation, task đang chạy không tự nhận giá trị mới. Cần triển khai task mới hoặc dùng cơ chế đọc runtime và refresh phù hợp.

### EKS

Workload trên EKS có thể lấy secret bằng AWS SDK với IAM role thông qua EKS Pod Identity hoặc IRSA. Nếu dùng Secrets Store CSI Driver với AWS provider, secret có thể được mount vào pod theo cấu hình. Chọn cách mount hoặc API runtime dựa trên yêu cầu cập nhật, quyền truy cập và cách ứng dụng reload file.

### Lambda

Lambda execution role chỉ cần quyền đọc secret/parameter cụ thể. Có thể dùng AWS Parameters and Secrets Lambda Extension hoặc cache trong ứng dụng để giảm API call. Nếu secret rotation, đặt TTL và logic refresh phù hợp; tránh lưu plaintext vào log hoặc trả về trong error message.

### CI/CD

CodeBuild, CodePipeline hoặc hệ thống CI bên ngoài nên dùng role hoặc federation để lấy secret khi job thực sự cần. Không lưu secret trong repository, buildspec plaintext hoặc artifact. Hạn chế thời gian tồn tại của credential, giới hạn quyền theo project/environment và che thông tin nhạy cảm khỏi log.

## 14. Chi phí và lựa chọn theo quy mô

Chi phí cần được đánh giá theo mô hình sử dụng, không chỉ theo số dòng cấu hình.

Với Secrets Manager, các yếu tố chính gồm số secret lưu trữ, số API request, số replica và chi phí thành phần hỗ trợ rotation như Lambda. Secret được truy vấn liên tục bởi nhiều container có thể tạo nhiều API call nếu không cache.

Với Parameter Store, Standard parameters không có phụ phí lưu trữ theo tài liệu pricing của AWS; Advanced parameters và throughput cao có thể phát sinh phí. Nếu chọn Advanced chỉ để lưu cấu hình nhỏ mà không dùng parameter policies hoặc cross-account sharing, cần cân nhắc lại.

Một cách ước tính:

1. Đếm số secret/parameter theo ứng dụng, môi trường và Region.
2. Ước tính số workload instance và số lần đọc mỗi workload.
3. Xác định TTL cache và tần suất refresh.
4. Ước tính số lần rotation và API call liên quan.
5. Tính thêm KMS key, Lambda rotation, S3/CloudTrail hoặc dịch vụ liên quan nếu có.
6. So sánh chi phí với tác động rủi ro nếu credential không được xoay vòng hoặc cấu hình không được kiểm soát.

Không nên tiết kiệm chi phí bằng cách chuyển mọi credential cần rotation sang Parameter Store nếu sau đó phải tự xây dựng và vận hành một hệ thống rotation phức tạp. Ngược lại, không nhất thiết dùng Secrets Manager cho mọi endpoint hoặc ID không nhạy cảm.

## 15. Các lỗi thiết kế thường gặp

### Lưu secret trong String parameter

String không cung cấp mã hóa KMS cho giá trị như SecureString. Chuyển giá trị nhạy cảm sang SecureString hoặc Secrets Manager, sau đó rà soát log và lịch sử thay đổi để xác định liệu plaintext đã bị lộ hay chưa.

### Dùng SecureString với key mặc định nhưng mong muốn phân quyền giải mã chi tiết

AWS managed key aws/ssm không phù hợp khi cần tách quyền decrypt theo nhóm. Dùng customer managed key, key policy và IAM policy theo least privilege.

### Cấp quyền đọc path cha quá rộng

Quyền GetParametersByPath trên path cha có thể cho phép đọc các parameter con khi gọi recursive. Tách path theo boundary bảo mật và kiểm thử cả các API đọc theo path.

### Không tính đến rotation trong ứng dụng

Secret có thể được xoay nhưng ứng dụng giữ credential trong cache hoặc connection pool quá lâu. Thiết kế TTL, refresh, retry và tạo kết nối mới; thử nghiệm rotation khi tải thực tế.

### Đưa secret vào environment variable và nghĩ nó tự cập nhật

Secret injection lúc container khởi chạy không tự cập nhật container đang chạy sau rotation. Cần restart task/pod theo quy trình hoặc đọc secret runtime.

### Ghi secret vào log hoặc command history

Không in plaintext, không đặt secret trong command line có thể được ghi lại và không đưa secret vào error message. Dùng SDK và nguồn cấu hình bảo mật.

### Dùng một secret cho nhiều ứng dụng

Một credential dùng chung làm tăng phạm vi ảnh hưởng khi bị lộ và khó thu hồi theo từng ứng dụng. Tạo secret riêng theo workload hoặc trust boundary khi hệ thống đích cho phép.

### Sao chép secret mà không có quy trình đồng bộ

Nếu tự copy secret sang Region hoặc account khác, các bản sao có thể lệch version. Dùng Secrets Manager replication khi phù hợp hoặc xây dựng quy trình đồng bộ có nguồn chuẩn, kiểm tra trạng thái và cảnh báo lỗi.

### Dùng dynamic reference ở vị trí có thể làm lộ dữ liệu

Không tham chiếu secret trong primary identifier, output hoặc custom resource. Kiểm tra giới hạn và resource property được hỗ trợ trước khi dùng.

## 16. Quy trình ra quyết định và triển khai

Có thể dùng quy trình sau cho từng giá trị cấu hình:

1. **Phân loại:** xác định giá trị là cấu hình công khai nội bộ, dữ liệu nhạy cảm hay credential.
2. **Xác định vòng đời:** ai tạo, ai đọc, ai cập nhật, tần suất thay đổi và thời điểm hết hạn.
3. **Xác định rotation:** có cần đổi credential định kỳ không; hệ thống đích có API hỗ trợ không; ứng dụng có chịu được chuyển đổi không.
4. **Xác định phạm vi:** một app, nhiều môi trường, nhiều account hay nhiều Region.
5. **Chọn dịch vụ:** Parameter Store String/SecureString cho cấu hình phù hợp; Secrets Manager cho secret cần vòng đời chuyên biệt.
6. **Thiết kế quyền:** IAM theo workload, KMS key policy, resource policy hoặc RAM share khi cần.
7. **Thiết kế tiêu thụ:** SDK, extension, dynamic reference hoặc secret injection; xác định cache và refresh.
8. **Thiết kế kiểm toán:** CloudTrail, log rotation, thay đổi policy, người phê duyệt và bằng chứng kiểm thử.
9. **Đánh giá chi phí:** storage, API request, KMS, Lambda, throughput và replication.
10. **Kiểm thử lỗi:** quyền bị từ chối, KMS key disabled, secret không tồn tại, rotation thất bại, Region mất kết nối và credential cũ bị thu hồi.

### Ma trận quyết định ví dụ

| Tình huống | Lựa chọn khuyến nghị | Lý do |
|---|---|---|
| URL nội bộ cho service Orders | Parameter Store String | Cấu hình không bí mật, cần phân cấp |
| AMI ID chuẩn theo Region | Parameter Store String | Dữ liệu cấu hình dùng lại trong IaC |
| Token API bên thứ ba có thể xoay vòng | Secrets Manager | Cần vòng đời secret và rotation workflow |
| Mật khẩu RDS cần rotation | Secrets Manager | Có tích hợp rotation cho dịch vụ dữ liệu được hỗ trợ |
| License key mã hóa, ít thay đổi, không cần rotation | Parameter Store SecureString hoặc Secrets Manager | Chọn theo nhu cầu audit, quyền và vòng đời |
| Cấu hình advanced chia sẻ giữa account | Parameter Store Advanced + AWS RAM | Có shared parameter |
| Credential cần replica cho DR đa Region | Secrets Manager | Có secret replication |
| Feature flag cần gradual rollout | AWS AppConfig, có thể lấy cấu hình từ Parameter Store | AppConfig quản lý deployment và rollout cấu hình |

## 17. Bằng chứng vận hành và kiểm toán

Để chứng minh secret/parameter được quản lý an toàn, cần lưu bằng chứng về quyền, thay đổi, rotation và cách ứng dụng sử dụng dữ liệu.

| Câu hỏi kiểm toán | Bằng chứng |
|---|---|
| Ai có thể đọc secret? | IAM policy, secret resource policy, KMS key policy |
| Ai có thể đọc SecureString? | IAM policy cho ssm:GetParameter*, KMS decrypt permission và path policy |
| Secret được xoay khi nào? | Rotation schedule, CloudTrail event, rotation status và Lambda log đã lọc dữ liệu nhạy cảm |
| Credential mới đã hoạt động chưa? | Kết quả testSecret, health check và log ứng dụng |
| Parameter đã được rà soát chưa? | Version history, labels, parameter policy và EventBridge notification |
| Secret có bản sao DR không? | Replication status, Region đích, KMS key và bài kiểm thử failover |
| Ai thay đổi quyền truy cập? | CloudTrail, change request và người phê duyệt |
| Có lộ plaintext không? | Rà soát CI log, CloudWatch Logs, shell history, artifact và ticket |

CloudTrail ghi nhận hoạt động API và thay đổi quản trị, nhưng không nên dùng log API như nơi lưu giá trị secret. Với Lambda rotation, rà soát log và metric để chắc chắn function không ghi plaintext. Với ứng dụng, log nên chỉ ghi secret ARN/name hoặc trạng thái lấy secret, không ghi giá trị.

## 18. Checklist trước khi đưa vào production

- [ ] Đã phân loại rõ cấu hình và credential.
- [ ] Dùng String cho cấu hình không nhạy cảm; dùng SecureString hoặc Secrets Manager cho dữ liệu nhạy cảm.
- [ ] Đã chọn Standard/Advanced Parameter Store dựa trên giới hạn và tính năng thực sự cần.
- [ ] Secret cần rotation đã có quy trình cập nhật hệ thống đích và ứng dụng.
- [ ] Rotation được kiểm thử trên môi trường không production trước khi bật lịch.
- [ ] Ứng dụng có cache TTL, refresh, retry và xử lý connection pool phù hợp.
- [ ] IAM role của từng workload chỉ đọc đúng secret/parameter cần thiết.
- [ ] KMS key policy và IAM policy đã được kiểm tra; dùng customer managed key khi cần phân quyền decrypt.
- [ ] Parameter hierarchy không cấp quyền đọc path cha vượt phạm vi.
- [ ] Cross-account/Region sharing có resource policy, KMS và kiểm tra trạng thái replication.
- [ ] CloudFormation dynamic reference chỉ dùng ở resource property được hỗ trợ.
- [ ] Không có plaintext trong source code, build log, user data, artifact hoặc ticket.
- [ ] CloudTrail và cảnh báo rotation/parameter policy đã được cấu hình.
- [ ] Có quy trình khôi phục version, xử lý rotation lỗi và thu hồi credential cũ.
- [ ] Đã ước tính chi phí storage, API, KMS, Lambda, throughput và replication.

## 19. Ghi nhớ

Parameter Store là lựa chọn phù hợp cho cấu hình tập trung và các giá trị SecureString có nhu cầu bảo vệ đơn giản. Standard tier đáp ứng phần lớn cấu hình thông thường; Advanced tier bổ sung dung lượng, parameter policies và chia sẻ cross-account nhưng có chi phí. Cần thiết kế IAM và KMS cẩn thận, đặc biệt với path hierarchy và GetParametersByPath.

Secrets Manager phù hợp với credential và token có vòng đời bảo mật chuyên biệt. Dịch vụ quản lý version, rotation, tích hợp với một số dịch vụ AWS và replication đa Region. Khi dùng rotation, phải cập nhật cả secret lẫn hệ thống đích, kiểm thử credential mới và bảo đảm ứng dụng refresh đúng thời điểm.

Quyết định tốt bắt đầu từ phân loại dữ liệu, yêu cầu vòng đời và cách workload tiêu thụ giá trị. Kết hợp IAM role, KMS, cache, CloudTrail và quy trình thay đổi sẽ giúp ứng dụng AWS lấy cấu hình an toàn, duy trì khả năng sẵn sàng và kiểm soát chi phí.

## Tài liệu tham khảo

- [AWS Systems Manager Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html)
- [Choosing Parameter Tiers in Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-advanced-parameters.html)
- [Working with Parameter Hierarchies](https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-paramstore-hierarchies.html)
- [Assigning Parameter Policies](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-policies.html)
- [KMS Encryption for Parameter Store SecureString](https://docs.aws.amazon.com/systems-manager/latest/userguide/secure-string-parameter-kms-encryption.html)
- [Restricting Access to Specific Parameters and Paths](https://docs.aws.amazon.com/systems-manager/latest/userguide/ps-restrict-parameter-access.html)
- [What is AWS Secrets Manager?](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
- [Rotate AWS Secrets Manager Secrets](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html)
- [Rotation Schedules](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_schedule.html)
- [Rotation by Lambda Function](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_lambda.html)
- [Lambda Rotation Strategies](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotation-strategy.html)
- [Access Secrets from a Different Account](https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access_examples_cross.html)
- [Replicate Secrets Across Regions](https://docs.aws.amazon.com/secretsmanager/latest/userguide/replicate-secrets.html)
- [CloudFormation Dynamic References](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references.html)
- [Secrets Manager Dynamic References](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references-secretsmanager.html)
- [Parameter Store SecureString Dynamic References](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references-ssm-secure-strings.html)

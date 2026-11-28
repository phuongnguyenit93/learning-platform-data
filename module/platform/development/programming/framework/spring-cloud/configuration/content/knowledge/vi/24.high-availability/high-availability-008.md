# Đồng nhất phiên bản cấu hình giữa các Config Server

Khi triển khai nhiều Spring Cloud Config Server để tăng khả năng sẵn sàng, các instance phải trả về cùng một phiên bản cấu hình cho cùng application, profile và label. Nếu một node đọc commit mới trong Git trong khi node khác vẫn dùng commit cũ, hai Config Client có thể nhận giá trị khác nhau chỉ vì request đi qua hai node khác nhau của load balancer.

Cần phân biệt hai mục tiêu: **high availability** giúp client vẫn truy cập được khi một Config Server gặp sự cố; **configuration consistency** bảo đảm các server còn phục vụ cùng một revision và cùng cách diễn giải cấu hình. Có nhiều replica chưa tự động tạo ra tính nhất quán. Muốn đồng nhất, cần quản lý label/revision, cấu hình backend, cache/fetch, rollout và kiểm tra từng node.

Bài viết tập trung vào Git backend của Spring Cloud Config Server, cách triển khai nhiều instance sau load balancer, ghim revision bằng tag hoặc commit, kiểm tra trường `version`, xử lý node bị lệch và phối hợp refresh Config Client. Các nguyên tắc tương tự cần được áp dụng cho native hoặc composite backend, nhưng mỗi nguồn phải có cơ chế version riêng.

## 1. Kiến trúc nhiều Config Server

Một cụm Config Server thường có nhiều instance cùng chạy một phiên bản ứng dụng và cùng truy cập một Git repository. Config Client gọi một địa chỉ ổn định qua load balancer hoặc service discovery.

~~~mermaid
flowchart TD
    C[Config Clients] --> LB[Load Balancer / Service]
    LB --> S1[Config Server A]
    LB --> S2[Config Server B]
    LB --> S3[Config Server C]
    S1 --> G[Shared Git remote]
    S2 --> G
    S3 --> G
    S1 --> B[Same application/profile/label]
    S2 --> B
    S3 --> B
~~~

Mỗi Config Server có thể duy trì bản clone Git cục bộ riêng. Khi nhận request, Git backend dùng repository local và cơ chế fetch theo cấu hình để xác định revision cần phục vụ. Do đó, hai instance có thể tạm thời nhìn thấy các commit khác nhau nếu chúng fetch một branch đang thay đổi ở những thời điểm khác nhau.

Các thành phần cần đồng nhất trong cụm:

- Cùng phiên bản Config Server artifact/image và cùng Spring Cloud release train.
- Cùng Git URI, search paths, default label và quy tắc xác thực.
- Cùng cách xử lý profile, label và các property source.
- Cùng quyền truy cập Git và cùng chính sách TLS/host verification.
- Cùng phiên bản của các nguồn ngoài Git nếu dùng composite repository.
- Cùng chính sách rollout và kiểm tra revision trước khi nhận traffic.

Load balancer chỉ phân phối request. Nó không đồng bộ clone Git, không khóa revision và không xác nhận các response từ những node khác nhau giống nhau.

## 2. Phân biệt revision của ứng dụng server và revision cấu hình

Có hai phiên bản cần theo dõi riêng:

| Phiên bản | Đại diện cho | Cách kiểm soát |
| --- | --- | --- |
| Config Server release | Code, dependency, runtime và cách xử lý repository | Image tag/digest, build version, rollout |
| Configuration revision | Nội dung cấu hình được đọc từ Git hoặc backend khác | Git commit SHA, immutable tag hoặc version của secret/config store |

Hai Config Server có cùng image vẫn có thể trả cấu hình khác nhau nếu local clone hoặc label khác nhau. Ngược lại, hai server đọc cùng Git commit nhưng chạy logic khác phiên bản có thể xử lý property source hoặc encryption khác nhau.

Trong triển khai production, ghi nhận cả server build version và configuration revision. Điều này giúp xác định sự cố đến từ thay đổi code của Config Server hay thay đổi nội dung cấu hình.

## 3. Cấu hình Git backend giống nhau trên mọi node

Ví dụ cấu hình dùng chung cho các Config Server instance:

~~~yaml
server:
  port: 8888

spring:
  application:
    name: config-server
  cloud:
    config:
      server:
        git:
          uri: ${CONFIG_REPO_URI}
          default-label: release-2026.11
          clone-on-start: true
          refresh-rate: 30
          search-paths:
            - shared
            - applications
          username: ${CONFIG_GIT_USERNAME}
          password: ${CONFIG_GIT_TOKEN}
~~~

Các giá trị được inject từ cùng một nguồn deployment configuration hoặc secret manager. Không cấu hình URI, default label hoặc search path riêng cho từng replica nếu mục tiêu là chúng trả cùng tập cấu hình.

Một số thuộc tính quan trọng:

- `uri`: Git repository mà backend đọc.
- `default-label`: label được dùng khi request không chỉ định label.
- `clone-on-start`: yêu cầu clone repository khi server khởi động, giúp phát hiện lỗi truy cập sớm hơn.
- `refresh-rate`: khoảng thời gian tính bằng giây giữa các lần fetch remote theo cơ chế Git backend. Giá trị mặc định thường là 0, nghĩa là fetch theo mỗi request; hãy kiểm tra tài liệu đúng release đang dùng.
- `search-paths`: các thư mục được tìm kiếm bên trong repository.
- `username` và `password`: credential đọc Git; cần đồng nhất quyền nhưng không nhất thiết phải dùng cùng một token giữa các môi trường.

`refresh-rate` không phải cơ chế đồng bộ giữa các server. Mỗi node có thể fetch vào thời điểm khác nhau. Đặt khoảng fetch ngắn giúp branch thay đổi được nhìn thấy sớm hơn, nhưng không tạo ra một thời điểm commit chung cho toàn cụm.

## 4. Mỗi node có local clone riêng

Git backend thường clone repository vào thư mục làm việc cục bộ của Config Server. Mỗi replica nên có thư mục clone riêng, có quyền ghi phù hợp và dung lượng đủ dùng.

Có thể cấu hình `basedir`:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          basedir: /var/lib/config-server/git
          clone-on-start: true
~~~

Trong môi trường container, mount volume cho đường dẫn này nếu cần giữ clone qua lần restart. Nếu không giữ volume, server có thể clone lại khi khởi động. Dù giữ hay xóa clone, nguồn có thẩm quyền vẫn là Git remote và label/revision được chọn.

Không chia sẻ một thư mục clone đang được nhiều Config Server process sửa đổi đồng thời nếu chưa có cơ chế khóa và hỗ trợ rõ ràng. Mỗi node có clone riêng giúp giảm tranh chấp file và cho phép từng replica fetch độc lập. Điều quan trọng là chúng phải cùng truy cập một remote và cùng yêu cầu revision.

Nếu local clone bị hỏng hoặc lệch, có thể xóa cache theo quy trình bảo trì để server clone lại. Chỉ thực hiện trên node đã được rút khỏi load balancer và sau khi xác nhận đường dẫn `basedir`; không xóa thư mục dữ liệu dùng chung hoặc repository khác.

## 5. Vì sao dùng branch đang thay đổi có thể tạo cấu hình lệch?

Giả sử các Config Server cùng dùng label `main`:

- Server A fetch lúc 10:00:00 và nhận commit `a1b2c3`.
- Một commit mới được merge vào `main` lúc 10:00:15.
- Server B fetch lúc 10:00:20 và nhận commit `d4e5f6`.
- Trong khoảng thời gian này, request qua load balancer có thể nhận hai phiên bản khác nhau.

Nếu `refresh-rate` lớn hơn 0, chênh lệch có thể tồn tại đến khi từng node fetch lại. Nếu refresh rate bằng 0, mỗi request sẽ fetch theo cơ chế mặc định, nhưng branch vẫn có thể di chuyển giữa hai request; hai server vẫn có thể đọc hai commit khác nhau khi request đến ở hai thời điểm khác nhau.

Vì vậy, branch như `main` phù hợp với môi trường cần lấy cấu hình mới nhất theo nhịp phát triển, nhưng không phải định danh bất biến cho một lần phát hành. Với production cần tính tái lập, hãy ghim một tag bất biến hoặc commit SHA.

## 6. Ghim cấu hình bằng tag hoặc commit SHA

Label trong Config Server có thể là branch, tag hoặc revision Git được backend hỗ trợ. Với mỗi lần phát hành, nên tạo một tag có quy ước rõ ràng và bảo vệ tag khỏi bị di chuyển hoặc ghi đè.

Ví dụ client:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import: "configserver:http://config-server:8888"
  cloud:
    config:
      label: release-2026.11
~~~

Client yêu cầu cấu hình theo application `orders-service`, profile `prod` và label `release-2026.11`. Tất cả Config Server trong cụm sẽ được yêu cầu đọc cùng label. Nếu tag không bị thay đổi và các node đã fetch đúng tag, chúng sẽ giải quyết về cùng Git commit.

Có thể dùng commit SHA nếu quy trình triển khai muốn ghim trực tiếp revision:

~~~yaml
spring:
  cloud:
    config:
      label: a1b2c3d4e5f678901234567890abcdef12345678
~~~

Hãy xác nhận định dạng label được hỗ trợ trong phiên bản Git backend đang dùng. Dù chọn tag hay SHA, ghi lại full commit hash trong manifest triển khai. Tag chỉ bất biến khi Git provider và quy trình release bảo vệ việc sửa hoặc xóa tag.

Ghim label giúp client không bị ảnh hưởng khi branch mặc định tiến lên. Khi phát hành cấu hình mới, tạo tag mới và cập nhật label của client hoặc deployment theo một quy trình đã kiểm tra.

## 7. Kiểm tra revision trên từng Config Server

Với Git backend, response Environment JSON thường có trường `version` biểu diễn revision Git được dùng để tạo Environment. Trường này là một tín hiệu quan trọng để so sánh các node.

Endpoint dạng:

~~~text
/{application}/{profile}/{label}
~~~

Ví dụ gọi trực tiếp từng node, bỏ qua load balancer:

~~~bash
curl --fail --silent --show-error \
  http://config-server-a.internal:8888/orders-service/prod/release-2026.11

curl --fail --silent --show-error \
  http://config-server-b.internal:8888/orders-service/prod/release-2026.11
~~~

Có thể chỉ in metadata và tên property source bằng `jq`, không in giá trị cấu hình có thể chứa secret:

~~~bash
curl --fail --silent --show-error \
  http://config-server-a.internal:8888/orders-service/prod/release-2026.11 \
  | jq '{name, profiles, label, version, sources: [.propertySources[].name]}'
~~~

Lặp lại với từng node. Các trường cần so sánh:

- `name`: application được yêu cầu.
- `profiles`: profile thực tế.
- `label`: label đã được xử lý.
- `version`: Git revision.
- `propertySources[].name`: tập nguồn đã đóng góp vào Environment.

Không lưu toàn bộ response JSON vào log hoặc artifact nếu response có thể chứa secret đã giải mã. Trong kiểm tra production, chỉ trích xuất metadata không nhạy cảm.

## 8. So sánh cả nội dung cấu hình, không chỉ label

Hai node có thể trả cùng label nhưng cần xác nhận revision và property source thực tế. Với Git backend, trường `version` cho biết commit được sử dụng; nếu version giống nhau nhưng property source khác, cần kiểm tra search paths, profile, backend composite và cấu hình server.

Có thể so sánh một tập key không nhạy cảm bằng endpoint YAML:

~~~bash
curl --fail --silent --show-error \
  http://config-server-a.internal:8888/orders-service-prod.yml \
  --output node-a.yml

curl --fail --silent --show-error \
  http://config-server-b.internal:8888/orders-service-prod.yml \
  --output node-b.yml

diff -u node-a.yml node-b.yml
~~~

Chỉ dùng cách lưu file nếu endpoint không trả secret hoặc dùng fixture kiểm thử. Nếu cấu hình có secret, hãy so sánh checksum hoặc tập key đã lọc trong một công cụ an toàn; không ghi plaintext ra file tạm.

Đối với kiểm tra tổng quát, có thể xây dựng một manifest release chứa:

~~~yaml
config-release:
  id: release-2026.11
  git-commit: a1b2c3d4e5f678901234567890abcdef12345678
  applications:
    - orders-service
    - payment-service
~~~

Manifest này là metadata phát hành, không chứa secret. Mỗi node có thể được kiểm tra so với revision mong đợi trước khi được đưa vào load balancer.

## 9. Health check và readiness của Config Server

`/actuator/health` giúp biết tiến trình có hoạt động và các health indicator được cấu hình có khỏe hay không. Tuy nhiên, HTTP 200 từ health endpoint không tự chứng minh node đang phục vụ đúng Git revision với các replica còn lại.

Nên phân biệt:

- **Liveness**: JVM và ứng dụng còn hoạt động; process có thể tiếp tục chạy.
- **Readiness**: node đủ điều kiện nhận request cấu hình.
- **Configuration parity**: node đang phục vụ đúng label/revision và tập property source được mong đợi.

Một quy trình readiness cho Config Server có thể xác minh:

1. Ứng dụng khởi động và endpoint health sẵn sàng.
2. Git backend có thể đọc repository cần thiết.
3. Một request kiểm tra với application/profile/label đại diện trả về thành công.
4. Trường `version` khớp revision được release manifest chỉ định.
5. Node chỉ được đưa vào load balancer khi các điều kiện bắt buộc đều đạt.

Không nên gọi Git fetch hoặc truy vấn cấu hình nặng ở tần suất rất cao trong mỗi health probe. Có thể thực hiện parity check theo chu kỳ hoặc trong bước deployment, lưu kết quả và để readiness đọc trạng thái đã xác nhận. Khi node lệch revision, rút node khỏi load balancer hoặc đánh dấu unready cho đến khi đồng bộ.

## 10. Cấu hình load balancer và client

Config Client nên gọi một endpoint ổn định của cụm:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import: "configserver:https://config.internal.example"
  cloud:
    config:
      label: release-2026.11
~~~

Load balancer phân phối request đến các Config Server instance đủ điều kiện. Có thể dùng load balancer hạ tầng, Kubernetes Service hoặc service discovery tùy nền tảng.

Một số nguyên tắc:

- Chỉ đưa node đã qua readiness/parity check vào pool.
- Health check cần đủ nhanh và không tạo tải Git không cần thiết.
- Nếu một node lỗi Git hoặc phục vụ revision sai, loại node đó khỏi rotation.
- Giữ cùng TLS trust, authentication policy và authorization giữa các node.
- Tránh cấu hình client trỏ trực tiếp đến một node duy nhất nếu mục tiêu là HA.
- Ghi nhận node đã phục vụ request khi điều tra lỗi; có thể thêm response header nội bộ hoặc log correlation an toàn ở tầng gateway.

Sticky session không giải quyết tính nhất quán. Nó chỉ khiến một client thường xuyên quay lại cùng node; client khác vẫn có thể nhận revision khác. Ghim immutable label và kiểm tra parity mới là biện pháp cốt lõi.

## 11. Đồng nhất khi dùng nhiều backend hoặc composite repository

Git không phải nguồn duy nhất có thể đóng góp vào Environment. Nếu Config Server dùng composite repository gồm Git, Vault hoặc native backend, cùng Git commit chưa đủ để bảo đảm response giống nhau.

Cần quản lý version cho từng nguồn:

| Backend | Cách kiểm soát phiên bản |
| --- | --- |
| Git | Immutable tag hoặc commit SHA |
| Native classpath | Cùng image digest và cùng artifact |
| Native filesystem | Cùng snapshot/thư mục version bất biến được mount trên mọi node |
| Vault KV v2 | Ghi nhận secret version hoặc release metadata |
| Backend khác | Dùng version/identifier riêng và kiểm tra khả năng đọc đồng nhất |

Git label không ghim Vault KV version. Nếu Vault secret thay đổi độc lập, hai Config Server có thể trả giá trị khác nhau dù Git revision giống nhau, tùy cache và cách backend đọc secret. Cần xác định backend nào là nguồn có thẩm quyền và cách tạo một release manifest bao quát các version liên quan.

Với native filesystem, tránh cập nhật file trực tiếp trên từng host theo cách thủ công. Dùng image hoặc volume snapshot bất biến, triển khai cùng một version cho tất cả replica rồi kiểm tra checksum hoặc manifest.

## 12. Quy trình phát hành cấu hình đồng nhất

Một quy trình release có thể gồm:

1. Tạo pull request cho thay đổi cấu hình.
2. Kiểm tra YAML/properties, schema, key bắt buộc và profile liên quan.
3. Review phạm vi ảnh hưởng của file chung và file theo ứng dụng.
4. Merge thay đổi vào Git.
5. Tạo tag release bất biến hoặc ghi nhận commit SHA.
6. Cập nhật label mục tiêu cho Config Client hoặc deployment.
7. Đảm bảo tất cả Config Server đã fetch được revision đó.
8. Gọi endpoint Environment trực tiếp trên từng node và so sánh `version`.
9. Chỉ đưa node đạt parity vào load balancer.
10. Cho client refresh hoặc rollout theo nhóm.
11. Theo dõi revision và lỗi cấu hình trên từng client.
12. Ghi lại manifest, thời điểm phát hành và kế hoạch rollback.

Với cụm Config Server đang phục vụ production, có thể triển khai theo blue/green: dựng pool mới với cấu hình server và repository revision mong muốn, xác minh parity, sau đó chuyển traffic. Cách này giảm rủi ro một nửa cụm phục vụ cấu hình cũ trong lúc nửa còn lại đã chuyển mới.

## 13. Xử lý node bị lệch phiên bản

Nếu một node trả về revision khác, không nên để load balancer tiếp tục phân phối request ngẫu nhiên đến node đó.

Quy trình xử lý:

1. Ghi nhận node, application, profile, label và revision trả về.
2. Đánh dấu node unready hoặc rút khỏi load balancer.
3. Kiểm tra Git URI, credentials, network, DNS, TLS và remote branch/tag.
4. Kiểm tra `basedir`, local clone, `refresh-rate` và log fetch.
5. Xác nhận node đang dùng đúng default label và search paths.
6. Nếu clone local hỏng hoặc stale, làm mới clone theo quy trình bảo trì đã phê duyệt.
7. Gọi lại endpoint trực tiếp và xác nhận revision khớp manifest.
8. Đưa node trở lại load balancer sau khi parity check thành công.

Không sửa trực tiếp file trong local clone để ép node trả giá trị mong muốn. Local clone là cache làm việc của Git backend; thay đổi thủ công không có trong remote sẽ khó tái lập và có thể bị fetch ghi đè.

## 14. Rollback về revision đã phát hành

Khi cấu hình mới gây lỗi, rollback nên chọn một revision đã biết và có thể tái tạo. Nếu client ghim label, cập nhật về tag trước đó hoặc commit SHA đã lưu trong manifest.

Ví dụ:

~~~yaml
spring:
  cloud:
    config:
      label: release-2026.10
~~~

Sau khi đổi label, kiểm tra tất cả Config Server đều trả cùng revision cũ. Tiếp đó refresh hoặc rollout client theo quy trình. Không chỉ đổi default label trên một node; tất cả replica phải có cùng cấu hình server và cùng chính sách label.

Nếu tag đã bị thay đổi hoặc xóa, rollback sẽ khó kiểm chứng. Bảo vệ tag release và giữ manifest ghi nhận full commit SHA. Khi cần rollback khẩn cấp, có thể trỏ trực tiếp đến commit đã xác minh nếu Git backend và quy trình deployment hỗ trợ.

## 15. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Hai Config Server trả version khác nhau | Fetch branch ở thời điểm khác nhau, label khác hoặc clone stale | Gọi trực tiếp từng node và so sánh `version` |
| Cùng label nhưng property source khác | Search path, profile hoặc backend phụ khác nhau | So sánh `profiles`, `propertySources` và cấu hình server |
| Node mới không khởi động | Git credential, TLS hoặc repository không truy cập được | Kiểm tra log clone-on-start và quyền Git |
| Node trả revision cũ lâu hơn dự kiến | `refresh-rate` lớn hoặc fetch lỗi | Kiểm tra fetch log và cấu hình refresh rate |
| Health trả UP nhưng cấu hình sai | Health không kiểm tra revision parity | Bổ sung readiness/parity validation |
| Client lúc đúng lúc sai | Load balancer còn đưa node lệch revision vào pool | Kiểm tra node phục vụ request và loại node stale |
| Rollback không có tác dụng | Client vẫn dùng label khác hoặc chưa refresh | Kiểm tra client request và endpoint Environment |
| Composite response khác nhau | Vault/native backend không cùng version | Kiểm tra version riêng từng backend |
| Local clone bị lỗi hoặc dirty | Filesystem, quyền hoặc tiến trình can thiệp clone | Rút node khỏi pool, kiểm tra basedir và clone lại |

Khi chẩn đoán, luôn gọi trực tiếp từng node để tách vấn đề load balancer khỏi vấn đề backend. Sau đó so sánh application/profile/label, Git revision, property source và backend phụ. Không chỉ dựa vào một request đi qua load balancer vì request tiếp theo có thể được định tuyến sang replica khác.

## 16. Nguyên tắc vận hành

- Triển khai Config Server replicas cùng artifact và cùng cấu hình backend.
- Dùng chung Git remote, search paths, credential policy và default label.
- Mỗi node có local clone riêng; không chỉnh sửa clone bằng tay.
- Dùng immutable tag hoặc commit SHA để ghim cấu hình production.
- Hiểu `refresh-rate` là chính sách fetch của từng node, không phải đồng bộ cluster.
- Kiểm tra trường `version` và property source trực tiếp trên từng node.
- Chỉ đưa node đạt readiness và revision parity vào load balancer.
- Với native/composite backend, version hóa mọi nguồn chứ không chỉ Git.
- Theo dõi cả Config Server release lẫn configuration revision.
- Ghi manifest release và giữ revision cũ để rollback.
- Refresh client sau khi server cluster đã phục vụ thống nhất revision đích.

Tính sẵn sàng của cụm Config Server chỉ có ý nghĩa khi các node trả về cấu hình có thể giải thích và tái tạo. Dùng cùng một branch không bảo đảm cùng commit tại mọi thời điểm; dùng cùng image cũng không bảo đảm cùng nội dung backend. Ghim revision bất biến, kiểm tra `version` trên từng replica, quản lý các nguồn composite và chỉ phục vụ traffic từ node đã đạt parity giúp Config Client nhận cấu hình nhất quán trong quá trình phát hành và vận hành.

## Tài liệu tham khảo

- [Spring Cloud Config Reference – Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html)
- [Spring Cloud Config Reference – Serving Configuration](https://docs.spring.io/spring-cloud-config/reference/server/serving-configuration.html)
- [Spring Boot Reference – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)


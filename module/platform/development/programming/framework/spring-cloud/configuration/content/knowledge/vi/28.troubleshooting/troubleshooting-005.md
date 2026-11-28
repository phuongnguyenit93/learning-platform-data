# Cấu hình chưa cập nhật vì bản sao Git hoặc chu kỳ refresh-rate

Khi một thay đổi đã được merge vào Git nhưng ứng dụng vẫn đọc giá trị cũ, nguyên nhân có thể nằm ở một trong ba nơi: Git remote chưa được Config Server fetch, bản sao Git cục bộ của Config Server chưa chuyển sang revision mới, hoặc Config Client chưa tải và áp dụng lại Environment. Chỉ gọi endpoint refresh ở client không bảo đảm Config Server đã lấy commit mới nhất từ remote.

Spring Cloud Config Server dùng một local working copy làm cache cho Git backend. Thuộc tính `spring.cloud.config.server.git.refresh-rate` quyết định tần suất server kiểm tra cập nhật remote. Nếu server đang giữ bản sao cũ, Git remote tạm thời không truy cập được, hoặc client yêu cầu nhầm label, server có thể trả về cấu hình cũ dù request thành công.

Bài học này hướng dẫn cách phân biệt các tình huống đó, kiểm tra revision ở từng chặng, xử lý working copy bị lệch, cấu hình refresh-rate và thiết lập webhook để cập nhật nhanh sau commit. Bạn cũng sẽ biết khi nào cần refresh client, khi nào cần làm mới Git repository và cách tránh mất cấu hình khi Config Server khởi động lại.

Sau bài học, bạn có thể:

- Truy vết một commit từ Git remote đến Config Server và Config Client.
- Giải thích local clone, working copy và cache refresh-rate.
- Phân biệt refresh-rate bằng 0, số dương và số âm.
- Nhận biết Config Server đang phục vụ revision cũ khi Git remote gặp sự cố.
- Kiểm tra application, profile, label và branch được yêu cầu.
- Xử lý local working copy bị dirty bằng force-pull một cách an toàn.
- Phát hiện branch đã bị xóa nhưng vẫn tồn tại trong local clone.
- Dùng webhook /monitor để rút ngắn thời gian chờ refresh-rate.
- Phân biệt thông báo refresh với thao tác fetch Git.
- Đối soát revision ở mọi Config Server replica và client.

## 1. Đường đi từ commit đến giá trị ứng dụng

Một thay đổi cấu hình cần đi qua nhiều bước trước khi xuất hiện trong ứng dụng:

1. Developer hoặc pipeline commit và push thay đổi lên Git remote.
2. Config Server nhận request lấy cấu hình cho application, profile và label.
3. Git backend kiểm tra local working copy và quyết định có fetch remote hay không.
4. Config Server đọc các file phù hợp, tạo Environment và trả về client.
5. Config Client nạp lại property sources.
6. Các bean cần refresh được rebind hoặc tạo lại theo cơ chế Spring Cloud.

~~~mermaid
sequenceDiagram
    participant Dev as Developer / CI
    participant Git as Git remote
    participant Server as Config Server
    participant Local as Local Git working copy
    participant Client as Config Client
    participant Bean as Application bean

    Dev->>Git: Commit + push revision R2
    Client->>Server: GET /order-service/prod/main
    Server->>Local: Kiểm tra refresh-rate và working copy
    alt Đến thời điểm fetch
        Local->>Git: Fetch remote
        Git-->>Local: Revision R2
        Local->>Local: Checkout / cập nhật branch
    else Chưa đến thời điểm fetch
        Note over Local,Git: Tiếp tục dùng revision R1
    end
    Local-->>Server: Property files + revision
    Server-->>Client: Environment
    Client->>Bean: Refresh / rebind
~~~

Điểm dễ nhầm là refresh ở client và fetch ở server là hai thao tác riêng:

- `POST /actuator/refresh` yêu cầu Config Client lấy lại cấu hình từ Config Server và làm mới các thành phần được hỗ trợ.
- `POST /actuator/busrefresh` gửi yêu cầu refresh đến các client qua Spring Cloud Bus.
- Git fetch là thao tác của Config Server với Git remote, theo chính sách refresh của repository.
- Webhook `/monitor` có thể làm hết hiệu lực thời gian chờ refresh-rate của repository phù hợp, rồi thông báo ứng dụng cần refresh.

Nếu Config Server vẫn đang giữ revision R1, client refresh thành công vẫn có thể nhận R1. Vì vậy, hãy xác minh revision tại server trước khi điều tra bean ở client.

## 2. Config Server dùng local working copy

Với Git backend, Config Server clone repository từ remote về filesystem và đọc cấu hình từ bản sao cục bộ. Local working copy là cache do mỗi Config Server quản lý; nó giúp server không phải đọc file trực tiếp qua Git protocol trong mọi thao tác.

Ngoại lệ là Git URI dùng tiền tố `file:`. Với kiểu URI này, Config Server làm việc trực tiếp trên repository cục bộ và không tạo clone riêng. Khi triển khai nhiều Config Server replica, cần bảo đảm chúng truy cập đúng repository dùng chung trên filesystem; không áp dụng giả định về local clone riêng cho cấu hình `file:`.

Theo mặc định, Config Server clone repository khi có request cấu hình đầu tiên (lazy clone), thay vì clone ngay lúc startup. Điều này có hai hệ quả:

- Config Server có thể khởi động dù Git URI sai hoặc Git remote đang không truy cập được. Lỗi chỉ lộ ra khi request đầu tiên cần repository.
- Sau khi clone thành công, server có thể tiếp tục phục vụ dữ liệu từ local working copy nếu Git remote tạm thời mất kết nối.

Có thể bật clone-on-start:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          clone-on-start: true
~~~

Với nhiều repository được chọn bằng pattern, có thể đặt clone-on-start riêng cho repository cần kiểm tra sớm. Khi bật, Config Server clone repository trong lúc khởi động và fail-fast nếu nguồn cấu hình không hợp lệ hoặc không truy cập được.

Clone-on-start giúp phát hiện lỗi sớm; nó không tự bảo đảm mọi lần fetch sau đó đều thành công hoặc mọi replica đều cùng revision.

## 3. Hiểu đúng refresh-rate

Thuộc tính `spring.cloud.config.server.git.refresh-rate` có đơn vị giây và điều khiển tần suất Config Server fetch cập nhật từ Git remote.

| Giá trị | Hành vi |
|---|---|
| `0` (mặc định) | Fetch cập nhật từ Git mỗi khi có request cấu hình phù hợp |
| Số dương, ví dụ `60` | Chỉ fetch khi đã qua khoảng thời gian tối thiểu kể từ lần refresh gần nhất |
| Số âm | Không refresh repository từ remote |

Ví dụ:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          refresh-rate: 60
~~~

Với giá trị 60, nếu Config Server vừa fetch repository thì các request tiếp theo trong khoảng 60 giây có thể tiếp tục đọc local working copy hiện tại. Khi khoảng thời gian đã qua, một request cấu hình tiếp theo có thể kích hoạt lần fetch mới.

Refresh-rate dương giúp giảm số lần truy cập Git khi nhiều client cùng khởi động hoặc liên tục yêu cầu cấu hình. Đổi lại, commit mới có thể chưa xuất hiện trong local working copy cho đến lần fetch kế tiếp.

Giá trị âm tắt việc refresh từ remote. Webhook có thể gửi thông báo refresh cho client, nhưng không thể làm cho repository fetch khi refresh-rate âm vẫn đang vô hiệu hóa fetch. Nếu muốn webhook rút ngắn khoảng chờ, dùng refresh-rate bằng 0 hoặc một giá trị dương phù hợp.

### Ví dụ với refresh-rate 60 giây

Giả sử Config Server fetch commit R10 lúc 10:00:00, rồi Git remote nhận commit R11 lúc 10:00:15.

- Client gọi Config Server lúc 10:00:20: server có thể trả R10 vì chưa hết khoảng refresh-rate.
- Client gọi lại lúc 10:00:45: server vẫn có thể trả R10.
- Request đầu tiên sau khi hết khoảng thời gian có thể kích hoạt fetch và nhận R11.
- Các client tiếp theo đọc local working copy đã cập nhật.

Đây là thời gian tối thiểu giữa các lần refresh theo request, không phải cam kết rằng một scheduler nền sẽ fetch đúng từng giây. Hãy quan sát thời điểm fetch thực tế và revision thay vì chỉ nhìn giá trị cấu hình.

## 4. Vì sao HTTP 200 vẫn có thể trả cấu hình cũ?

Nếu Git remote mất kết nối sau khi Config Server đã clone repository thành công, server vẫn có thể phục vụ các file trong local working copy. Client nhận HTTP response hợp lệ, nhưng nội dung có thể thuộc revision cuối cùng fetch thành công.

Với refresh-rate dương, các lần thử fetch khi remote không khả dụng có thể thất bại mà không làm request hiện tại thất bại. Local working copy giữ nguyên revision cũ. Khi Git remote phục hồi, lần fetch kế tiếp mới có thể cập nhật bản sao.

Có hai tình huống cần phân biệt:

| Trạng thái Config Server | Git remote | Kết quả có thể xảy ra |
|---|---|---|
| Đã clone thành công | Tạm thời không truy cập được | Server tiếp tục trả dữ liệu từ local working copy |
| Chưa có local clone | Không truy cập được | Request cấu hình lỗi vì server không thể clone repository |
| Đã clone, refresh-rate dương | Remote có commit mới nhưng chưa đến lần fetch tiếp theo | Server trả revision cũ |
| Đã clone, refresh-rate âm | Remote có commit mới | Server tiếp tục dùng bản sao cũ cho đến khi có biện pháp vận hành khác |
| Đã clone, remote phục hồi | Request tiếp theo đến thời điểm fetch | Server có thể cập nhật local working copy |

Nếu Config Server không có bản sao cục bộ và Git remote đang down, server trả lỗi. Trong trường hợp đó, Config Client thường giữ cấu hình hiện tại vì không nhận được Environment mới. Đừng xóa local clone hoặc restart đồng loạt Config Server khi Git remote đang lỗi nếu các ứng dụng cần tiếp tục lấy cấu hình.

## 5. Kiểm tra revision server đang phục vụ

Khi nghi ngờ cấu hình bị cũ, hãy kiểm tra endpoint Config Server trực tiếp, tránh chỉ quan sát giá trị ở ứng dụng.

Ví dụ:

~~~bash
curl -sS http://localhost:8888/order-service/prod/main
~~~

Response Environment có thể chứa:

- `name`: application được yêu cầu.
- `profiles`: profile được áp dụng.
- `label`: label được yêu cầu.
- `version`: revision của repository khi backend cung cấp.
- `propertySources`: các nguồn property và giá trị được nạp.

Ví dụ rút gọn:

~~~json
{
  "name": "order-service",
  "profiles": ["prod"],
  "label": "main",
  "version": "8f31c42",
  "propertySources": [
    {
      "name": "https://git.example.internal/platform/config-repo.git/order-service-prod.yml",
      "source": {
        "feature.limit": 200
      }
    }
  ]
}
~~~

So sánh `version` với commit SHA mà pipeline vừa push. Nếu server trả revision cũ, vấn đề nằm ở repository/label/fetch hoặc replica đang nhận request. Nếu server trả revision mới nhưng ứng dụng vẫn dùng giá trị cũ, tiếp tục kiểm tra client refresh và property precedence.

Không mở endpoint cấu hình ra công khai chỉ để debug. Response có thể chứa thông tin nhạy cảm; dùng xác thực, mạng quản trị và che secret khi lưu kết quả kiểm tra.

## 6. Kiểm tra application, profile và label

Một cấu hình đúng commit vẫn có thể không xuất hiện nếu client yêu cầu sai context.

Config Server phân giải repository theo ba tham số:

- `application`: thường lấy từ `spring.application.name` của client.
- `profile`: lấy từ `spring.profiles.active`.
- `label`: nhãn Git như branch, tag hoặc commit ID.

Ví dụ client:

~~~yaml
spring:
  application:
    name: order-service
  profiles:
    active: prod
  cloud:
    config:
      label: main
~~~

Hãy kiểm tra request thực tế có đúng là `order-service/prod/main` hay không. Một client vẫn đang chạy profile `staging` sẽ không tự đọc file `order-service-prod.yml`.

Git backend mặc định dùng label `main`. Nếu không tìm thấy branch `main`, Config Server có thể thử branch `master`. Có thể tắt fallback này bằng `spring.cloud.config.server.git.try-master-branch=false` để tránh server âm thầm đọc một branch khác với mong đợi.

Nếu branch hoặc tag có dấu `/`, label trong URL cần mã hóa dấu slash bằng chuỗi `(_)`. Ví dụ branch `release/2026` được biểu diễn trong URL thành `release(_)2026`.

Ngoài ra, kiểm tra:

- Branch/tag/commit có tồn tại trên remote hay không.
- Client có đang ghim commit SHA hoặc tag cũ trong `spring.cloud.config.label` hay không.
- Git backend có chọn repository khác qua `repos` và pattern application/profile hay không.
- `search-paths` có trỏ tới thư mục chứa file cấu hình hay không.
- File có tên phù hợp như `application.yml`, `order-service.yml`, `application-prod.yml` hoặc `order-service-prod.yml` hay không.
- Profile nào đang có độ ưu tiên cao hơn khi có nhiều profile cùng hoạt động.

Một request nhiều label có thể gặp lỗi ở một label và làm toàn request lỗi. Nếu dùng nhiều label để fallback, hãy kiểm tra hành vi `continue-on-multiple-label-failure` theo phiên bản và backend đang chạy.

## 7. Branch đã xóa nhưng local clone vẫn còn

Config Server có thể giữ branch đã checkout trong local clone. Khi branch bị xóa trên Git remote, local branch đó có thể vẫn tồn tại và tiếp tục được yêu cầu bằng label cũ.

Mặc định `deleteUntrackedBranches` là `false`. Vì vậy, branch đã bị xóa trên remote có thể còn trong local repository cho đến khi server restart hoặc khi cơ chế dọn branch được bật.

Nếu cần đồng bộ branch local với remote, có thể cấu hình:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          delete-untracked-branches: true
~~~

Thuộc tính này khiến Config Server xóa các branch local không còn được theo dõi từ remote khi fetch. Hãy cân nhắc trước khi bật, đặc biệt nếu quy trình phát hành còn tham chiếu đến branch tạm hoặc branch đã xóa có chủ ý.

Nếu client yêu cầu label đã bị xóa, hãy kiểm tra cả remote và local working copy. Không kết luận rằng Git remote còn branch chỉ vì Config Server vẫn trả dữ liệu cho label đó.

## 8. Local working copy bị dirty hoặc lệch khỏi remote

Config Server cần local working copy ở trạng thái có thể cập nhật từ remote. Nếu file trong clone bị sửa thủ công, process khác thay đổi thư mục hoặc thao tác Git trước đó để lại conflict, JGit có thể không pull được nội dung mới.

Thuộc tính `force-pull` có thể buộc Config Server lấy trạng thái remote và reset local working copy khi bản sao bị dirty:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          force-pull: true
~~~

`force-pull` có tác động phá hủy thay đổi cục bộ: Config Server bỏ các sửa đổi local và reset working copy để khớp remote khi fetch. Chỉ bật khi local clone được xem là cache có thể tái tạo và không có dữ liệu thủ công cần giữ.

Trước khi bật, hãy kiểm tra:

- Ai hoặc process nào đã sửa local clone.
- Có file untracked hoặc modified nào trong working tree.
- Có thao tác vận hành nào đang dùng cùng thư mục.
- Local clone có được xem là cache tạm hay đang chứa dữ liệu cần bảo toàn.
- Cấu hình `force-pull` ở repository cụ thể nào nếu dùng nhiều Git repositories.

Không dùng force-pull để che lỗi Git credential, lỗi network hoặc sai label. Thuộc tính này xử lý local copy bị dirty; nó không làm Git remote sẵn sàng hơn.

## 9. Kiểm tra thư mục lưu local clone

Git và SVN working copies được lưu trên filesystem. Mặc định, Config Server có thể đặt chúng trong system temporary directory với tiền tố `config-repo-`. Hệ điều hành hoặc cơ chế dọn dẹp temp có thể xóa thư mục này và khiến Config Server mất bản sao cục bộ.

Có thể cấu hình một thư mục ổn định:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          basedir: /var/lib/config-server/git
          clone-on-start: true
~~~

Thư mục phải tồn tại hoặc có thể được tạo bởi process, và user chạy Config Server cần quyền đọc/ghi phù hợp. Không đặt basedir trong thư mục tạm có thể bị dọn tự động.

Trong môi trường container:

- Xác định thư mục clone có tồn tại qua lần restart hay không.
- Kiểm tra volume mount và quyền sở hữu filesystem.
- Đảm bảo mỗi Config Server replica có working copy nhất quán với remote.
- Không giả định replica A fetch thành công nghĩa là replica B đã fetch.
- Theo dõi revision và thời điểm fetch theo từng instance.
- Nếu dùng storage tạm của container, dự tính rằng restart có thể tạo local clone mới và cần truy cập Git remote.

Không để các Config Server replica ghi vào cùng một working directory mutable nếu chưa thiết kế cơ chế chia sẻ an toàn. Mỗi replica cần có bản sao mà nó có thể cập nhật độc lập hoặc dùng kiến trúc repository phù hợp với mô hình triển khai.

## 10. Dùng webhook để cập nhật sớm sau commit

Spring Cloud Config Monitor có thể nhận webhook từ Git provider. Khi thêm dependency `spring-cloud-config-monitor` và bật Spring Cloud Bus ở Config Server, endpoint `/monitor` được kích hoạt.

Webhook có thể làm hai việc:

1. Xác định ứng dụng có thể bị ảnh hưởng bởi các file đã thay đổi.
2. Nếu payload nhận diện được Git repository đã cấu hình, làm hết hiệu lực thời gian refresh-rate của repository đó để lần request cấu hình tiếp theo fetch commit mới.

Sau đó Config Server phát `RefreshRemoteApplicationEvent` đến client phù hợp. Event không mang toàn bộ file cấu hình; client sẽ gọi Config Server để lấy Environment mới.

~~~mermaid
sequenceDiagram
    participant Git as Git provider
    participant Monitor as Config Server /monitor
    participant Repo as Git repository cache
    participant Bus as Spring Cloud Bus
    participant Client as Config Client

    Git->>Monitor: Webhook sau push
    Monitor->>Repo: Nhận diện repository URL
    Monitor->>Repo: Expire refresh-rate window
    Monitor->>Bus: Publish refresh event
    Bus-->>Client: RefreshRemoteApplicationEvent
    Client->>Monitor: GET cấu hình từ Config Server
    Monitor->>Repo: Fetch nếu refresh window đã hết hiệu lực
    Repo-->>Monitor: Revision mới
    Monitor-->>Client: Environment mới
    Client->>Client: Rebind / refresh bean
~~~

Để event được truyền qua Bus, Spring Cloud Bus cần được kích hoạt ở cả Config Server và ứng dụng client. Nếu Bus không có, Config Monitor có thể dùng HTTP notifier khi có `DiscoveryClient` phù hợp trên classpath; notifier sẽ gọi refresh endpoint của từng instance.

### Webhook phải nhận diện đúng repository

Với webhook payload có repository URL khớp repository đã cấu hình, Config Server có thể expire refresh-rate của repository đó. Việc so khớp dựa trên host và repository path; protocol, credentials, SSH username và port được bỏ qua trong quá trình so sánh.

Nếu webhook không có repository URL phù hợp, Config Server vẫn có thể gửi thông báo refresh cho ứng dụng nhưng không expire refresh interval. Điều này có nghĩa client có thể nhận event, gọi Config Server và vẫn nhận bản sao cũ nếu refresh-rate chưa hết hạn.

Một `POST /monitor` thủ công với form body `path=order-service` có thể gửi thông báo cho ứng dụng phù hợp, nhưng không có repository URL để expire refresh-rate. Đừng nhầm thao tác broadcast event với thao tác buộc Git fetch.

### Bảo vệ webhook

Config Server hỗ trợ xác minh webhook secret theo provider. Nếu không cấu hình secret cho provider, request webhook từ provider đó bị từ chối. Hãy cấu hình secret đúng cơ chế chữ ký của GitHub, GitLab, Bitbucket, Gitea, Gogs hoặc Gitee.

Không tắt webhook validation chỉ để khắc phục HTTP 403. Kiểm tra header chữ ký, secret, raw request body và thời gian hệ thống theo cơ chế provider. Endpoint `/monitor` có thể kích hoạt refresh diện rộng nên phải được bảo vệ.

## 11. Path notification, ignored paths và giới hạn số file

Config Monitor mặc định xác định ứng dụng bị ảnh hưởng dựa trên đường dẫn file trong webhook:

- File `order-service.properties` nhắm đến ứng dụng `order-service`.
- File `application.properties` có thể ảnh hưởng tất cả ứng dụng.
- Có thể tùy biến logic phân tích đường dẫn bằng `PropertyPathNotificationExtractor`.

Nếu repository chứa tài liệu, script hoặc file không liên quan đến cấu hình, có thể bỏ qua bằng regex:

~~~yaml
spring:
  cloud:
    config:
      server:
        monitor:
          ignored-paths:
            - "docs/.*"
            - "scripts/.*"
~~~

Mỗi regex được áp dụng với toàn bộ đường dẫn file trong webhook. Những path bị bỏ qua không được dùng để xác định ứng dụng cần refresh.

Mặc định, Config Server xử lý tối đa 20 path từ một notification. Có thể tăng bằng:

~~~yaml
spring:
  cloud:
    config:
      server:
        monitor:
          max-paths: 50
~~~

Nếu một push thay đổi nhiều hơn giới hạn, các path còn lại không được xử lý và warning được ghi log. Khi nhiều file cấu hình được cập nhật cùng lúc, hãy kiểm tra log monitor và cân nhắc `max-paths` phù hợp.

## 12. Phân biệt các endpoint refresh

| Endpoint | Nơi gọi | Tác dụng |
|---|---|---|
| `POST /actuator/refresh` | Một Config Client | Tải lại cấu hình từ Config Server và refresh các thành phần được hỗ trợ |
| `POST /actuator/busrefresh` | Một ứng dụng có Spring Cloud Bus | Phát sự kiện refresh đến các client trong Bus |
| `POST /monitor` | Config Server | Nhận thông báo thay đổi từ Git provider hoặc path notification |
| `GET /{application}/{profile}/{label}` | Config Server | Trả Environment cho application/profile/label; Git fetch phụ thuộc repository state và refresh-rate |

Ví dụ refresh một client:

~~~bash
curl -X POST http://order-service:8080/actuator/refresh
~~~

Lệnh này làm client gọi lại Config Server. Nếu Config Server trả local working copy cũ, client vẫn có thể nhận cấu hình cũ.

Ví dụ gửi path notification:

~~~bash
curl -X POST http://config-server:8888/monitor \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "path=order-service"
~~~

Path notification có thể thông báo cho `order-service` refresh nhưng không expire refresh-rate của Git repository vì request không mang repository URL. Để lấy commit mới ngay khi refresh-rate dương chưa hết hạn, ưu tiên webhook provider có payload repository URL được nhận diện chính xác hoặc thiết kế một cơ chế vận hành riêng để cập nhật repository cache.

## 13. Nhiều Config Server replica có thể lệch revision

Mỗi Config Server replica có thể giữ local clone riêng. Khi một replica fetch thành công còn replica khác bị lỗi network hoặc chưa đến thời điểm refresh-rate, load balancer có thể đưa client tới một server đang phục vụ revision cũ.

Ví dụ:

| Config Server | Local revision | Fetch gần nhất | Kết quả |
|---|---|---|---|
| config-0 | `a81d201` | 10:05:12 | Đã cập nhật |
| config-1 | `9bc120a` | 09:58:41 | Đang cũ |
| config-2 | `a81d201` | 10:05:10 | Đã cập nhật |

Trong tình huống này, gọi endpoint nhiều lần có thể cho kết quả khác nhau tùy replica nhận request. Khi chẩn đoán, hãy gọi từng replica trực tiếp hoặc ghi nhận instance ID trong response/log để biết server nào trả dữ liệu.

Đối với mỗi replica, cần theo dõi:

- Revision hiện tại của local working copy.
- Thời điểm fetch thành công gần nhất.
- Lỗi fetch gần nhất.
- `refresh-rate` đang áp dụng.
- Git remote và label thực tế.
- Tình trạng basedir và filesystem.
- Webhook có tới đúng Config Server instance hoặc được xử lý bởi cơ chế dùng chung hay không.

Nếu dùng nhiều repository theo application pattern, kiểm tra request được route tới đúng repository definition. Một replica có thể đang chạy cấu hình server khác hoặc pattern khác với các replica còn lại.

## 14. Quy trình chẩn đoán từng bước

Khi ứng dụng chưa nhận cấu hình mới, đi theo thứ tự dưới đây.

### Bước 1: Xác nhận commit trên Git remote

Kiểm tra branch, tag hoặc commit mà pipeline đã push. Xác minh file thực sự nằm trong repository, đúng thư mục, đúng tên và đúng profile.

Không chỉ nhìn trạng thái pipeline thành công. Đối chiếu commit SHA và file diff.

### Bước 2: Xác nhận Config Client yêu cầu đúng context

Kiểm tra:

- `spring.application.name`.
- `spring.profiles.active`.
- `spring.cloud.config.label`.
- Config Server URI.
- Branch/tag/commit mà label đại diện.

Gọi trực tiếp Config Server bằng application/profile/label đang dùng.

### Bước 3: So revision trong response Config Server

Đọc trường `version` nếu backend trả về. So sánh với commit SHA mong muốn.

- Nếu version cũ: điều tra local clone, refresh-rate, remote fetch hoặc label.
- Nếu version mới: điều tra client refresh và property binding.

### Bước 4: Kiểm tra refresh-rate

Đọc cấu hình server thực tế, không chỉ file YAML dự định deploy. Xác định refresh-rate bằng 0, số dương hay số âm. Nếu là số dương, tính thời gian từ lần refresh gần nhất và kiểm tra có request nào đến sau khi khoảng thời gian hết chưa.

### Bước 5: Kiểm tra Git remote access

Từ môi trường Config Server, xác minh DNS, TLS, credential, SSH host key, firewall và quyền đọc repository. Kiểm tra log JGit/Config Server quanh thời điểm request.

Nếu remote down nhưng local clone còn, server có thể trả dữ liệu cũ. Nếu không có local clone, request có thể lỗi.

### Bước 6: Kiểm tra local working copy

Xác minh basedir có tồn tại, process có quyền ghi, filesystem không đầy và working tree có sạch không. Kiểm tra branch local, remote tracking refs và HEAD commit.

Nếu working copy dirty, xác định nguyên nhân trước khi dùng force-pull. Nếu branch đã bị xóa remote nhưng còn local, kiểm tra `deleteUntrackedBranches`.

Trên máy hoặc container đang chạy Config Server, có thể dùng các lệnh chỉ đọc sau khi đã xác định đúng thư mục working copy:

~~~bash
git -C "<working-copy>" rev-parse HEAD
git -C "<working-copy>" status --short
git -C "<working-copy>" branch -avv
git -C "<working-copy>" remote -v
git ls-remote "<remote-url>" refs/heads/main
~~~

So sánh commit local từ `rev-parse HEAD` với commit remote từ `ls-remote`. `status --short` giúp phát hiện file modified, untracked hoặc conflict có thể ngăn pull. Dùng đúng danh tính Git mà Config Server sử dụng khi kiểm tra remote; không chèn token vào URL hoặc lưu credential trong shell history. Đường dẫn `<working-copy>` phụ thuộc `basedir` và cách Config Server tạo clone, vì vậy hãy xác định từ cấu hình/runtime thực tế.

### Bước 7: Kiểm tra webhook hoặc refresh event

Nếu dùng `/monitor`, kiểm tra:

- Dependency `spring-cloud-config-monitor` có trên Config Server.
- Bus đã bật ở Config Server và client, hoặc HTTP notifier có DiscoveryClient.
- Webhook URL đúng.
- Secret/signature hợp lệ.
- Payload có repository URL khớp remote đã cấu hình.
- Path không bị `ignored-paths` loại bỏ.
- Số path không vượt `max-paths`.
- Log có cho thấy event được gửi và client nhận hay không.

### Bước 8: Xác nhận client đã áp dụng

Nếu Config Server trả revision mới, gọi refresh client và kiểm tra response. Xác minh property source mới đã vào Environment, bean cần refresh có cơ chế rebind/refresh phù hợp và không có property source local ưu tiên cao hơn ghi đè giá trị.

## 15. Bảng triệu chứng và nguyên nhân

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Git remote có commit mới nhưng Config Server trả version cũ | Refresh-rate dương chưa hết khoảng hoặc refresh-rate âm | Kiểm tra refresh-rate và thời điểm fetch |
| Webhook gửi event nhưng client vẫn nhận config cũ | Webhook không khớp repository URL nên không expire refresh-rate | Kiểm tra payload URL và log monitor |
| POST /monitor trả thành công nhưng không thấy Git fetch | Path notification chỉ broadcast, không expire refresh-rate | Dùng provider webhook có repository URL |
| Config Server trả 200 dù Git remote down | Local working copy vẫn tồn tại | So version với commit mong muốn |
| Request cấu hình lỗi sau khi Config Server restart | Lazy clone cần Git remote nhưng remote không khả dụng | Kiểm tra clone-on-start, basedir và Git connectivity |
| Một số request mới, một số request cũ | Các replica có local clone ở revision khác nhau | Gọi từng replica và so HEAD |
| Branch đã xóa vẫn trả cấu hình | Local branch cũ còn trong clone | Kiểm tra deleteUntrackedBranches |
| Branch main không có nhưng server trả dữ liệu master | Cơ chế fallback branch mặc định | Kiểm tra default-label và try-master-branch |
| Label có slash không tìm thấy | URL chưa mã hóa slash theo quy tắc (_) | Kiểm tra request label |
| Fetch không cập nhật working copy | Local working tree dirty hoặc conflict | Kiểm tra Git status và force-pull |
| Config Server trả version mới nhưng app vẫn cũ | Client chưa refresh hoặc bean không hỗ trợ refresh | Kiểm tra /actuator/refresh, property source và bean scope |
| Config Monitor không nhận webhook | Sai URL, signature, secret hoặc firewall | Kiểm tra HTTP status, header và monitor logs |

## 16. Cấu hình tham khảo cho production

Ví dụ sau đặt một refresh window 30 giây, clone repository lúc startup và dùng basedir ổn định:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          basedir: /var/lib/config-server/git
          clone-on-start: true
          refresh-rate: 30
          default-label: main
          try-master-branch: false
          delete-untracked-branches: true
          timeout: 5
~~~

Các lựa chọn cần cân nhắc:

- `refresh-rate: 30`: giảm số lần fetch nhưng tạo độ trễ cập nhật tối đa theo chu kỳ nếu không có webhook hợp lệ.
- `clone-on-start: true`: phát hiện lỗi repository ngay lúc startup.
- `basedir`: tránh phụ thuộc system temp directory.
- `default-label`: xác định branch mặc định rõ ràng.
- `try-master-branch: false`: tránh fallback ngoài ý muốn.
- `delete-untracked-branches: true`: dọn branch đã xóa khỏi remote khi fetch.
- `timeout`: giới hạn thời gian chờ thiết lập kết nối Git.

Không thêm `force-pull: true` theo mặc định nếu chưa xác nhận local working copy chỉ là cache có thể tái tạo. Nếu bật, thay đổi cục bộ sẽ bị bỏ khi fetch.

Với webhook, cấu hình `spring-cloud-config-monitor`, Bus ở cả server/client và webhook secret theo provider. Hãy kiểm tra payload thực tế có repository URL để refresh window được expire.

## 17. Thực hành mô phỏng lỗi stale configuration

Tạo môi trường staging với một Git repository, một Config Server và một Config Client.

1. Tạo branch `main`, thêm `order-service-prod.yml` với `feature.limit: 100`, rồi push.
2. Khởi động Config Server với `clone-on-start: true`, `refresh-rate: 60` và basedir ổn định.
3. Gọi `/order-service/prod/main`; ghi nhận `version` và `feature.limit`.
4. Thay giá trị thành 200, commit và push lên Git remote.
5. Gọi Config Server ngay sau commit. Quan sát local working copy và xác định response còn R1 hay đã lên R2.
6. Gọi lại sau khi refresh-rate hết khoảng; xác minh revision được cập nhật.
7. Thử `POST /actuator/refresh` trên client trước khi server fetch được commit mới; xác minh client vẫn nhận giá trị cũ.
8. Cấu hình webhook Git provider, bật monitor và Bus ở cả server/client. Push R3 rồi kiểm tra webhook có expire refresh-rate và client nhận refresh event.
9. Gửi path-only notification tới `/monitor`; quan sát event có thể được phát nhưng refresh window của repository không bị expire.
10. Ngắt Git remote sau khi local clone đã tồn tại; xác minh server tiếp tục trả revision cuối cùng.
11. Restart Config Server khi remote vẫn down; quan sát hành vi lazy clone và request lỗi.
12. Tạo một thay đổi thủ công trong local working copy test; thử fetch khi dirty, sau đó kiểm tra tác động của `force-pull`.
13. Xóa một branch trên remote nhưng vẫn yêu cầu label đó; kiểm tra local branch còn tồn tại và thử `delete-untracked-branches`.
14. Chạy hai Config Server replica; tạo tình huống một replica fetch được và replica còn lại không fetch được. So sánh revision từng replica.

Ghi lại commit SHA, local revision, Config Server instance, refresh-rate, thời điểm fetch, webhook status, event ID và client value. Chỉ đánh dấu thử nghiệm thành công khi biết rõ giá trị cũ hoặc mới đến từ chặng nào.

## 18. Checklist production

- Xác nhận Git remote có commit mong muốn và branch/tag tồn tại.
- Kiểm tra client đang yêu cầu đúng application, profile và label.
- So sánh `version` trong response Config Server với commit SHA mong muốn.
- Biết rõ refresh-rate là 0, số dương hay số âm.
- Theo dõi local working copy của từng Config Server replica.
- Dùng basedir ổn định, không phụ thuộc system temp directory.
- Bật clone-on-start cho repository cần fail-fast.
- Kiểm tra Git credential, TLS/SSH host verification và quyền đọc.
- Dùng force-pull chỉ khi local clone là cache có thể tái tạo.
- Cân nhắc delete-untracked-branches nếu branch remote bị xóa vẫn còn trong clone.
- Kiểm tra default-label và fallback main/master.
- Nếu dùng webhook, xác minh repository URL được nhận diện và refresh-rate window được expire.
- Bảo vệ /monitor bằng webhook secret.
- Kiểm tra ignored-paths, max-paths và Bus/HTTP notifier.
- Phân biệt POST client refresh với Git fetch tại server.
- Sau khi server trả revision mới, xác nhận client đã nạp và bean đã áp dụng.
- Không xóa local clone hoặc restart toàn bộ server khi Git remote đang down nếu chưa có phương án phục hồi.

## 19. Tự kiểm tra

1. Vì sao Config Server có thể trả HTTP 200 nhưng cấu hình vẫn thuộc commit cũ?
2. refresh-rate bằng 0, số dương và số âm có hành vi khác nhau thế nào?
3. Vì sao POST /actuator/refresh không bảo đảm Git remote đã được fetch?
4. Khi Git remote down sau khi clone thành công, Config Server có thể tiếp tục phục vụ dữ liệu nào?
5. Điều gì xảy ra khi Config Server restart trong lúc Git remote down và local clone không còn?
6. force-pull xử lý trường hợp nào và có thể làm mất dữ liệu gì?
7. Vì sao branch đã xóa trên remote vẫn có thể được yêu cầu bằng label cũ?
8. delete-untracked-branches giúp xử lý tình huống nào?
9. Webhook có repository URL khác path-only notification ở điểm nào liên quan đến refresh-rate?
10. Vì sao các Config Server replica có thể trả các revision khác nhau?
11. Làm thế nào xác định ứng dụng đang yêu cầu sai profile hoặc label?
12. Khi Config Server trả revision mới nhưng client vẫn dùng giá trị cũ, cần kiểm tra những gì?

Hãy thực hiện bài lab staging và ghi lại kết quả cho từng tình huống. Đặc biệt, so sánh ba trạng thái: Git remote đã có commit mới, Config Server local working copy đã cập nhật, và Config Client đã áp dụng property mới. Khi ba mốc này được kiểm tra độc lập, bạn có thể xác định chính xác nơi cấu hình đang bị chậm và chọn biện pháp phục hồi phù hợp.

## Tài liệu tham khảo

- [Spring Cloud Config — Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html)
- [Spring Cloud Config — Push Notifications and Spring Cloud Bus](https://docs.spring.io/spring-cloud-config/reference/server/push-notifications-and-bus.html)
- [Spring Cloud Config — Version Control Backend Filesystem Use](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/version-control-backend-filesystem-use.html)
- [Spring Cloud Config — Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html)
- [Spring Cloud Config — Health Indicator](https://docs.spring.io/spring-cloud-config/reference/server/health-indicator.html)
- [Spring Cloud Config — Client Refresh and Config Data](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Bus — Bus Endpoints](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/bus-endpoints.html)


# Thiết kế cấu trúc cho nhiều nhóm và nhiều môi trường

Khi một vài ứng dụng dùng chung Spring Cloud Config, một repository đơn giản có thể chỉ cần `application.yml` và một số file theo tên ứng dụng. Khi nền tảng phát triển thành hàng chục dịch vụ, nhiều nhóm và nhiều môi trường, cách đặt file tùy ý sẽ nhanh chóng gây khó khăn: khó biết ai sở hữu một thuộc tính, cấu hình dùng chung bị thay đổi ngoài dự kiến, các môi trường lệch nhau và việc quay lại phiên bản an toàn trở nên phức tạp.

Thiết kế repository cấu hình cần trả lời được bốn câu hỏi: **cấu hình nằm ở đâu, ai được thay đổi, môi trường nào nhận phiên bản nào và làm thế nào để kiểm chứng thay đổi trước khi phân phối**. Spring Cloud Config cung cấp cơ chế đọc cấu hình theo application, profile và label; Git cung cấp lịch sử và quy trình review. Cấu trúc repository tốt kết hợp hai cơ chế đó thành một quy trình có thể duy trì khi số lượng nhóm và dịch vụ tăng lên.

## 1. Nguyên tắc tổ chức repository

Một repository cấu hình cần tuân thủ một số nguyên tắc:

1. **Dễ tìm:** tên file và thư mục phản ánh rõ ứng dụng, profile hoặc phạm vi dùng chung.
2. **Có chủ sở hữu:** mỗi phần cấu hình có nhóm chịu trách nhiệm review và xử lý sự cố.
3. **Tách phần dùng chung và phần riêng:** thay đổi một dịch vụ không làm các dịch vụ khác nhận cấu hình ngoài ý muốn.
4. **Có thể tái lập:** cùng một label phải xác định được phiên bản cấu hình đã phân phối.
5. **Dễ kiểm chứng:** pull request có thể chạy kiểm tra cú pháp, schema, quy tắc bảo mật và các profile cần hỗ trợ.
6. **Ít trùng lặp:** giá trị mặc định được định nghĩa một lần; chỉ ghi đè khi có khác biệt thực sự.
7. **An toàn:** repository không chứa bí mật dạng rõ; quyền đọc và ghi được cấp theo nhu cầu.

Không có một cấu trúc thư mục duy nhất phù hợp cho mọi tổ chức. Cần chọn cấu trúc tương ứng với số ứng dụng, cách chia nhóm, yêu cầu cô lập quyền và khả năng cấu hình `search-locations` hoặc `search-paths` của Config Server.

## 2. Hiểu cách Spring Cloud Config tìm file

Với Git backend, Spring Cloud Config Server thường tìm cấu hình theo tên ứng dụng và profile. Một quy ước file phổ biến là:

| Tên file | Phạm vi |
|---|---|
| `application.yml` | Giá trị mặc định dùng chung cho các ứng dụng |
| `application-production.yml` | Giá trị dùng chung khi profile `production` hoạt động |
| `order-service.yml` | Cấu hình riêng của `order-service` |
| `order-service-staging.yml` | Cấu hình `order-service` khi chạy profile `staging` |
| `order-service-production.yml` | Cấu hình `order-service` khi chạy profile `production` |

Config Client yêu cầu cấu hình bằng tên ứng dụng, profile và label. Ví dụ, request cho `order-service`, profile `production`, label `release-2026-11` sẽ yêu cầu bộ cấu hình tương ứng từ phiên bản repository được chọn. Config Server kết hợp các property source chung và riêng theo quy tắc của backend và phiên bản đang dùng.

Ví dụ repository dạng phẳng:

```text
config-repo/
├── application.yml
├── application-staging.yml
├── application-production.yml
├── order-service.yml
├── order-service-staging.yml
├── order-service-production.yml
├── inventory-service.yml
├── inventory-service-staging.yml
└── inventory-service-production.yml
```

Cấu trúc này dễ bắt đầu và phù hợp khi số lượng file chưa lớn. Nó dùng trực tiếp quy ước tên file thông dụng của Config Server, không đòi hỏi phải thiết kế thêm đường dẫn tìm kiếm.

Khi repository có nhiều thư mục, có thể dùng `search-paths` để Config Server tìm cấu hình ở các vị trí được khai báo. Ví dụ cấu hình server:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          search-paths:
            - '{application}'
            - '{application}/{profile}'
```

Các placeholder và cú pháp search path cần được kiểm tra theo phiên bản Spring Cloud Config đang dùng. Không nên chuyển file vào thư mục con rồi mặc định cho rằng Config Server sẽ tự tìm thấy; phải cấu hình và kiểm thử đường dẫn tìm kiếm trước.

## 3. Chọn cách chia repository: một kho hay nhiều kho

Có hai cách tổ chức thường gặp. Một kho chung (monorepo) lưu cấu hình của nhiều ứng dụng; nhiều kho riêng (multi-repo) tách cấu hình theo nhóm, miền nghiệp vụ hoặc mức độ nhạy cảm.

| Tiêu chí | Một repository chung | Nhiều repository |
|---|---|---|
| Quản trị thay đổi | Một nơi review và phát hành quy ước chung | Mỗi nhóm có vòng đời phát hành riêng |
| Chia sẻ cấu hình | Dễ dùng `application.yml` và profile chung | Cần định nghĩa rõ phần chia sẻ hoặc nguồn cấu hình chung |
| Quyền truy cập | Dễ cấp quyền rộng hơn mức cần thiết nếu nhiều nhóm cùng repo | Có thể cô lập quyền đọc/ghi theo repository |
| Quy mô thay đổi | Pull request có thể lớn và nhiều nhóm cùng chạm file | Thay đổi phân tán, cần quản lý nhiều repo và credential |
| Vận hành Config Server | Một backend và quy tắc chung | Có thể cần nhiều repository URI hoặc nhiều cấu hình server |

**Một repository chung** phù hợp khi tổ chức có quy trình review thống nhất, các nhóm được phép đọc phần lớn cấu hình và cần dùng chung nhiều giá trị. Có thể dùng `CODEOWNERS`, branch protection và quy tắc pull request để chỉ định người review theo file hoặc thư mục.

**Nhiều repository** phù hợp khi các nhóm có quyền sở hữu độc lập, lịch phát hành khác nhau hoặc cần cô lập quyền đọc. Nếu một nhóm không được phép đọc cấu hình của nhóm khác, chỉ đặt file vào thư mục riêng trong cùng repo không tạo ra ranh giới bảo mật Git. Cần dùng repository riêng hoặc cơ chế phân phối có kiểm soát phù hợp với yêu cầu cô lập.

Quyết định cũng cần tính đến Config Server. Một Config Server có thể được cấu hình với nhiều backend hoặc nhiều URI theo quy tắc tìm kiếm; nếu tổ chức dùng nhiều server, cần quản lý endpoint, xác thực, khả năng sẵn sàng và phiên bản client một cách nhất quán.

## 4. Thiết kế cấu trúc thư mục cho nhiều nhóm

Nếu chọn monorepo và muốn nhóm cấu hình theo chủ sở hữu, có thể tổ chức thư mục theo nhóm hoặc domain. Ví dụ:

```text
config-repo/
├── shared/
│   ├── application.yml
│   └── application-production.yml
├── commerce/
│   ├── order-service/
│   │   ├── order-service.yml
│   │   ├── order-service-staging.yml
│   │   └── order-service-production.yml
│   └── payment-service/
│       ├── payment-service.yml
│       └── payment-service-production.yml
└── supply/
    └── inventory-service/
        ├── inventory-service.yml
        ├── inventory-service-staging.yml
        └── inventory-service-production.yml
```

Đây là cách tổ chức minh họa, không phải quy ước tự động mà Config Server nhận biết trong mọi cấu hình. Với cây thư mục trên, có thể khai báo các search path tương ứng trong Git backend, ví dụ:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          search-paths:
            - shared
            - 'commerce/{application}'
            - 'supply/{application}'
```

Các placeholder và cú pháp search path cần được kiểm tra theo phiên bản Spring Cloud Config đang dùng. Cấu trúc thực tế phải khớp đường dẫn được tìm kiếm; không nên chuyển file vào thư mục con rồi mặc định cho rằng Config Server sẽ tự tìm thấy. Cũng cần tránh việc nhiều thư mục cùng chứa một file có cùng tên nếu thứ tự tìm kiếm có thể làm kết quả trở nên khó đoán.

Một phương án khác là giữ file theo quy ước tên ở root và dùng `CODEOWNERS` để phân công quyền review. Cách này đơn giản hơn về cấu hình Config Server nhưng thư mục root có thể trở nên dài khi số lượng dịch vụ lớn.

### Cấu hình dùng chung và cấu hình theo ứng dụng

`application.yml` nên chứa những giá trị thật sự có thể áp dụng cho nhiều ứng dụng, chẳng hạn định dạng log hoặc một số timeout mặc định đã được thống nhất. Các thuộc tính chỉ có ý nghĩa với một dịch vụ nên nằm trong file riêng của dịch vụ đó.

Ví dụ:

```yaml
# application.yml
logging:
  pattern:
    level: "%5p [${spring.application.name:application}]"

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

```yaml
# order-service.yml
checkout:
  timeout: 2s
  max-retries: 2

inventory:
  service-id: inventory-service
```

Không đưa mọi thuộc tính vào `application.yml` chỉ để tránh lặp. Một giá trị chung sai có thể ảnh hưởng đến tất cả ứng dụng. Chỉ chia sẻ khi ngữ nghĩa, đơn vị đo, giới hạn và cách vận hành thực sự giống nhau.

## 5. Tổ chức profile và môi trường

Profile biểu diễn biến thể cấu hình theo môi trường hoặc mục đích chạy, ví dụ `development`, `staging` và `production`. Với mỗi ứng dụng, chỉ tạo file profile khi có thuộc tính cần thay đổi. Không cần sao chép toàn bộ file ứng dụng vào mọi môi trường.

Ví dụ:

```yaml
# order-service.yml
checkout:
  timeout: 2s
  max-retries: 2
```

```yaml
# order-service-staging.yml
checkout:
  timeout: 5s
```

```yaml
# order-service-production.yml
checkout:
  timeout: 2s
  max-retries: 1
```

Trong ví dụ này, `staging` chỉ ghi đè timeout; các thuộc tính khác vẫn lấy từ cấu hình chung của ứng dụng. `production` thay cả timeout và số lần retry. Cách viết phần khác biệt giúp giảm trùng lặp và làm rõ chủ đích.

Không nên dùng profile làm cơ chế phân quyền. Một client có thể yêu cầu profile `production` nếu nó có quyền truy cập Config Server và backend cho phép. Việc ai được đọc cấu hình production phải được bảo vệ bằng xác thực, authorization, quyền repository và chính sách phân phối tương ứng.

Nếu cần vùng, tenant hoặc nhóm triển khai ngoài môi trường, hãy quyết định rõ chúng được biểu diễn bằng profile, application name, label hay cấu trúc repository. Tránh tạo tổ hợp profile không kiểm soát như `prod-eu-blue-canary-team-a`; số tổ hợp tăng nhanh sẽ làm cấu hình khó kiểm thử. Chỉ tạo biến thể khi nó thay đổi hành vi hoặc tài nguyên thật sự.

## 6. Dùng label và Git để phát hành cấu hình

Label trong Spring Cloud Config xác định phiên bản backend được dùng khi lấy cấu hình. Với Git backend, label thường là branch, tag hoặc commit. Profile trả lời “cấu hình cho trường hợp chạy nào”; label trả lời “phiên bản cấu hình nào”. Hai khái niệm này cần được quản lý riêng.

Một quy trình phát hành an toàn thường có các bước:

1. Nhóm sở hữu tạo pull request cho thay đổi cấu hình.
2. CI kiểm tra cú pháp, schema, quy tắc bảo mật và các profile bị ảnh hưởng.
3. Chủ sở hữu và nhóm nền tảng review, phê duyệt theo phạm vi.
4. Thay đổi được merge vào nhánh tích hợp theo quy ước của tổ chức.
5. Tạo tag hoặc chọn commit bất biến làm phiên bản phát hành.
6. Triển khai hoặc cấu hình client dùng label đó ở staging; kiểm tra hành vi ứng dụng.
7. Promote cùng phiên bản cấu hình đã xác minh sang production theo quy trình phê duyệt.

Ví dụ, cùng một commit `a1b2c3d` được kiểm thử ở staging rồi phát hành cho production. Cách này giúp đảm bảo nội dung cấu hình đã kiểm chứng chính là nội dung được triển khai. Nếu production dùng một branch riêng và nhóm chép tay thay đổi từ staging sang, hai môi trường có thể dần lệch nhau.

### Branch theo môi trường hay promotion cùng một phiên bản?

Có thể dùng branch riêng như `staging` và `production`, nhưng cần chấp nhận và kiểm soát nguy cơ drift giữa các nhánh. Mỗi lần thay đổi phải được merge hoặc cherry-pick đúng thứ tự; bỏ sót một commit có thể làm cấu hình hai môi trường khác nhau ngoài ý muốn.

Một lựa chọn khác là giữ một nhánh phát triển chính và dùng tag hoặc commit label để phát hành cùng một snapshot cấu hình qua các môi trường. Sự khác nhau theo môi trường được biểu diễn bằng profile. Đây thường là cách dễ truy vết hơn khi muốn promotion một phiên bản đã kiểm thử.

Không có quy tắc bắt buộc mọi tổ chức phải dùng một chiến lược. Điều quan trọng là tài liệu hóa được label nào đang chạy ở từng môi trường, ai có quyền thay đổi nó và cách rollback về phiên bản trước.

## 7. Quy ước đặt tên và sở hữu

Tên ứng dụng phải ổn định, duy nhất và nhất quán với `spring.application.name` của Config Client. Ví dụ:

| Thành phần | Quy ước gợi ý | Ví dụ |
|---|---|---|
| Tên ứng dụng | kebab-case, phản ánh service | `order-service` |
| Profile | tên ngắn, nhất quán giữa dịch vụ | `development`, `staging`, `production` |
| File cấu hình | `{application}.yml` | `order-service.yml` |
| File profile | `{application}-{profile}.yml` | `order-service-production.yml` |
| File dùng chung | `application.yml` | `application.yml` |
| Label phát hành | tag hoặc commit có thể truy vết | `config-release-2026-11` |

Mỗi dịch vụ nên có một nhóm sở hữu chịu trách nhiệm cho ý nghĩa của các thuộc tính, giới hạn hợp lệ và ảnh hưởng khi thay đổi. Nhóm nền tảng chịu trách nhiệm quy ước chung, quyền truy cập, pipeline và vận hành Config Server. Nhóm bảo mật có thể review các thay đổi liên quan đến secret reference, policy và credential.

Trong monorepo, có thể dùng file `CODEOWNERS` để yêu cầu review theo đường dẫn. Ví dụ:

```text
/commerce/       @team-commerce
/supply/         @team-supply
/shared/         @platform-team
```

Đường dẫn trong ví dụ phải khớp cấu trúc thực tế của repository. `CODEOWNERS` hỗ trợ quy trình review Git; nó không tự giới hạn quyền đọc file đối với Config Client. Nếu cần cô lập quyền truy cập runtime, phải thiết kế authorization ở Config Server/backend hoặc tách repository/server theo ranh giới bảo mật.

## 8. Quản lý bí mật và quyền truy cập

Repository cấu hình không nên chứa password, API token, private key hoặc credential dạng rõ. Git giữ lịch sử commit, vì vậy xóa một giá trị ở commit mới không xóa nó khỏi lịch sử cũ, bản clone hay bản sao lưu.

Thay vào đó, repository có thể lưu tên secret hoặc tham chiếu tới hệ thống quản lý bí mật. Ứng dụng dùng danh tính runtime để lấy giá trị từ Vault hoặc secret manager tương ứng. Nếu tổ chức có lý do cần lưu giá trị đã mã hóa, khóa giải mã phải được quản lý bên ngoài repository và quyền gọi chức năng giải mã phải được giới hạn.

Các nguyên tắc bảo vệ cần có:

- Chỉ cấp quyền đọc repository hoặc endpoint cấu hình cho workload cần thiết.
- Dùng TLS khi client kết nối Config Server và khi server kết nối backend.
- Bảo vệ credential truy cập Git bằng secret store hoặc cơ chế credential an toàn.
- Tách quyền đọc cấu hình khỏi quyền thay đổi cấu hình.
- Bảo vệ branch chính bằng review bắt buộc, status checks và hạn chế force-push.
- Quét secret trong pull request và xử lý credential đã lộ bằng cách thu hồi hoặc rotate.
- Giới hạn nội dung endpoint Actuator `env` và `configprops`, tránh làm lộ giá trị nhạy cảm.

Nếu nhiều nhóm không được phép đọc dữ liệu của nhau, tách repository hoặc tách backend theo ranh giới quyền. Cấu trúc thư mục và `CODEOWNERS` giúp quản trị thay đổi, nhưng không thay thế cơ chế kiểm soát truy cập dữ liệu lúc runtime.

## 9. Kiểm tra chất lượng trước khi phát hành

Một thay đổi cấu hình có thể làm ứng dụng lỗi ngay khi khởi động hoặc chỉ gây lỗi khi một luồng nghiệp vụ hiếm gặp được gọi. Vì vậy, pull request nên chạy các bước kiểm tra tự động phù hợp:

| Kiểm tra | Mục tiêu |
|---|---|
| YAML parse và duplicate key | Phát hiện cú pháp sai và key trùng dễ gây ghi đè ngoài ý muốn |
| Schema hoặc validation rule | Kiểm tra kiểu dữ liệu, đơn vị, giới hạn và thuộc tính bắt buộc |
| Secret scanning | Phát hiện credential hoặc khóa nhạy cảm bị commit |
| Kiểm tra tên app/profile/label | Đảm bảo file và profile tuân theo quy ước |
| Kiểm tra tham chiếu | Phát hiện placeholder hoặc tên dịch vụ không tồn tại |
| Smoke test Config Server | Xác nhận endpoint trả đúng property source theo app/profile/label |
| Kiểm thử ứng dụng | Xác nhận ứng dụng khởi động và hành vi quan trọng phù hợp với cấu hình mới |

Khi thay đổi file dùng chung `application.yml`, cần xác định các ứng dụng bị ảnh hưởng và chạy kiểm tra rộng hơn. Khi thay đổi file riêng của một dịch vụ, phạm vi kiểm tra có thể hẹp hơn nhưng vẫn cần xác minh các profile mà dịch vụ hỗ trợ.

Đối với thuộc tính nhạy cảm về vận hành như timeout, connection pool, retry và giới hạn request, nên kiểm tra cả giá trị nhỏ nhất/lớn nhất hợp lệ và tương tác giữa các thuộc tính. Ví dụ tăng retry mà không điều chỉnh timeout tổng có thể kéo dài thời gian xử lý request và gây quá tải dây chuyền.

## 10. Cập nhật, refresh và rollback

Sau khi cấu hình được merge hoặc phát hành, client có thể nhận giá trị mới qua lần khởi động tiếp theo hoặc cơ chế refresh đã được thiết kế. Spring Cloud Config hỗ trợ lấy lại cấu hình; Spring Cloud Bus có thể phát sự kiện refresh tới nhiều instance. Tuy nhiên, thay đổi file trong Git không đồng nghĩa mọi instance tự động nhận giá trị mới ngay lập tức.

Quy trình thay đổi nên ghi nhận:

- Commit hoặc label chứa thay đổi.
- Ứng dụng và profile bị ảnh hưởng.
- Người review, người phê duyệt và thời điểm phát hành.
- Cách kiểm tra sau refresh hoặc restart.
- Cách quay lại label hoặc commit trước đó nếu có lỗi.

Với thay đổi có rủi ro cao, có thể phát hành trước cho một nhóm instance hoặc một môi trường nhỏ, quan sát metric và log, rồi mới mở rộng. Không nên refresh hàng loạt khi chưa xác định thuộc tính có thể áp dụng nóng an toàn hay không. Một số bean cần khởi động lại hoặc có cơ chế reload riêng.

Rollback thường đơn giản nhất khi cấu hình được phát hành theo tag hoặc commit bất biến: chuyển client hoặc cấu hình triển khai về label đã biết là tốt, sau đó xác nhận các instance đã nạp lại phiên bản đó. Nếu dùng branch mutable như `main`, cần lưu lại commit thực tế đã phân phối để có thể tái lập kết quả.

## 11. Ví dụ quy trình cho nhiều nhóm

Giả sử nhóm Commerce sở hữu `order-service` và `payment-service`, nhóm Supply sở hữu `inventory-service`, còn Platform sở hữu các cấu hình mặc định. Một repository chung có thể có:

```text
config-repo/
├── application.yml
├── application-production.yml
├── order-service.yml
├── order-service-staging.yml
├── order-service-production.yml
├── payment-service.yml
├── payment-service-production.yml
├── inventory-service.yml
└── inventory-service-production.yml
```

Quy trình thay đổi timeout của `order-service` có thể diễn ra như sau:

1. Nhóm Commerce mở pull request sửa `order-service-staging.yml` và giải thích lý do thay đổi.
2. CI kiểm tra YAML, schema, secret scanning và endpoint Config Server cho `order-service` với profile `staging`.
3. CODEOWNERS yêu cầu nhóm Commerce review; nếu thay đổi ảnh hưởng mặc định chung thì nhóm Platform cũng review.
4. Sau khi merge, tạo hoặc chọn một commit label bất biến để triển khai staging.
5. Kiểm tra metric, log và luồng checkout; nếu đạt yêu cầu, promote cùng commit sang production theo chính sách phát hành.
6. Nếu có lỗi, quay về commit label trước đó và xác nhận client đã nạp lại cấu hình.

Trong quy trình này, nhóm sở hữu dịch vụ hiểu ngữ nghĩa của thuộc tính; nhóm Platform giữ tính nhất quán của hạ tầng; Git lưu lại lịch sử và bằng chứng review. Quyền đọc production vẫn được quyết định bởi chính sách truy cập của repository và Config Server.

## 12. Mục tiêu cần đạt sau bài học

Sau bài này, người học cần có khả năng:

- Thiết kế cấu trúc repository cho cấu hình dùng chung và cấu hình riêng theo ứng dụng/profile.
- Chọn được cách tổ chức một repository chung hoặc nhiều repository theo quyền sở hữu và yêu cầu cô lập.
- Giải thích cách Config Server tìm file theo application, profile, label và vì sao thư mục con cần cấu hình search path phù hợp.
- Đề xuất quy ước đặt tên, CODEOWNERS và quyền review cho nhiều nhóm.
- Thiết kế quy trình phát hành cấu hình có review, kiểm tra tự động, promotion và rollback.
- Phân biệt profile với label và chọn cách phát hành phiên bản cấu hình có thể tái lập.
- Bảo vệ bí mật và quyền truy cập ở cả Git, Config Server và backend runtime.

**Tự kiểm tra:** Một tổ chức có ba nhóm sở hữu mười lăm dịch vụ. Các nhóm cần review độc lập, nhưng Platform muốn chia sẻ một số mặc định. Hãy đề xuất cấu trúc repository, cách đặt file theo application/profile, quy tắc CODEOWNERS và chiến lược label. Nếu một nhóm không được phép đọc cấu hình của nhóm khác, hãy giải thích vì sao chỉ tạo thư mục riêng trong monorepo là chưa đủ và cần bổ sung ranh giới quyền ở đâu.

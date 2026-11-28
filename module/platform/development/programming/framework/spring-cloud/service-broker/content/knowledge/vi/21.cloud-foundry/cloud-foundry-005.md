# Công bố gói và quản lý quyền truy cập bằng `cf enable-service-access`

## Catalog có service plan chưa có nghĩa mọi org đều dùng được

Khi tích hợp một service broker với Cloud Foundry, Cloud Controller lấy catalog từ broker và lưu các service offering cùng service plan để hiển thị trong Marketplace. Tuy nhiên, việc một plan đã có trong catalog không đồng nghĩa mọi tổ chức (org) đều được phép nhìn thấy hoặc provision plan đó.

Với **standard service broker**, Cloud Foundry tạo các service plan ở trạng thái private theo mặc định. Quản trị viên phải chủ động cấp quyền truy cập cho toàn bộ deployment hoặc một tập org cụ thể bằng lệnh `cf enable-service-access`. Cơ chế này giúp nhà vận hành kiểm soát plan nào được cung cấp cho nhóm khách hàng nào, ví dụ chỉ cho org `payments` dùng plan có mã hóa nâng cao hoặc chỉ cho org `development` dùng plan thử nghiệm.

Trong module `SPRING_CLOUD_SERVICE_BROKER`, broker công bố catalog theo Open Service Broker API (OSB API) và Spring Cloud Open Service Broker. Cloud Foundry dùng catalog đó để biết service và plan tồn tại; Cloud Controller quản lý quyền hiển thị/sử dụng plan. Hai lớp này phối hợp với nhau nhưng có trách nhiệm riêng: thay đổi catalog là thay đổi danh mục dịch vụ, còn `cf enable-service-access` là thay đổi phạm vi org được phép sử dụng plan.

## Standard broker và space-scoped broker

Cloud Foundry phân biệt hai loại service broker:

| Loại broker | Phạm vi công bố plan | Cách quản lý visibility |
|---|---|---|
| Standard broker | Có thể cung cấp plan cho tất cả org hoặc giới hạn ở một số org. | Admin quản lý service plan access riêng bằng `cf enable-service-access` và `cf disable-service-access`. Plan mới mặc định private. |
| Space-scoped broker | Chỉ cung cấp plan cho người dùng trong space nơi broker được đăng ký. | Visibility không được quản lý riêng bằng service access; người dùng trong space đó có thể truy cập plan của broker. |

Bài này tập trung vào standard broker và quyền truy cập service plan. Với space-scoped broker, quyền truy cập gắn với phạm vi space; không áp dụng máy móc quy trình bật visibility dành cho standard broker.

Việc đăng ký broker là bước riêng. Khi đăng ký standard broker, Cloud Controller gọi endpoint catalog của broker, xác thực và lưu catalog. Sau đó admin mới cấp quyền sử dụng plan. Nếu service hoặc plan chưa được broker công bố trong catalog, `cf enable-service-access` không thể tự tạo service hay plan đó.

## Quyền truy cập service plan có ba trạng thái

Cloud Foundry biểu diễn quyền truy cập bằng ba trạng thái:

| Giá trị `access` | Ý nghĩa | Ai có thể sử dụng plan? |
|---|---|---|
| `all` | Plan public. | Người dùng ở tất cả org. |
| `limited` | Plan được giới hạn theo org. | Người dùng thuộc những org được liệt kê. |
| `none` | Plan private. | Không org nào được cấp quyền sử dụng plan. |

Một plan mới từ standard broker có trạng thái `none` cho đến khi admin cấp quyền. Khi một org có quyền với plan, người dùng trong org đó nhìn thấy plan trong `cf marketplace`; người có vai trò Space Developer trong space tương ứng có thể provision service instance từ plan.

Quyền truy cập plan không thay thế quyền quản lý ứng dụng hoặc service instance. Người dùng vẫn cần vai trò Cloud Foundry phù hợp trong space để tạo và quản lý instance. Ngược lại, có vai trò Space Developer cũng không giúp họ provision một plan đang private hoặc không được cấp cho org.

## Điều kiện để dùng `cf enable-service-access`

Các lệnh quản lý service plan access trong Cloud Foundry yêu cầu người dùng đăng nhập với quyền **admin**. Một Space Developer hoặc Org Manager thông thường không thể tự mở plan cho org bằng các lệnh này.

Trước khi bật quyền, admin cần xác nhận:

1. Service broker đã được đăng ký trong đúng Cloud Foundry foundation.
2. Cloud Controller đã lấy catalog thành công và service offering/plan cần bật đã xuất hiện.
3. Tên service, broker và plan được xác định chính xác.
4. Org đích đã tồn tại và đúng với phạm vi phân phối dự kiến.
5. Chính sách thương mại, quota, dữ liệu và khả năng vận hành cho phép org đó sử dụng plan.

Đăng nhập và kiểm tra target:

```bash
cf login -a https://api.example.cf.example
cf target
```

Các lệnh dưới đây phải chạy trong đúng foundation. Khi thao tác access, Cloud Foundry yêu cầu admin; việc target org/space cho các lệnh quản lý access không thay thế quyền admin.

## Cú pháp `cf enable-service-access`

Cú pháp của Cloud Foundry CLI:

```bash
cf enable-service-access SERVICE [-b BROKER] [-p PLAN] [-o ORG]
```

| Tham số | Ý nghĩa |
|---|---|
| `SERVICE` | Tên service offering trong catalog. |
| `-b BROKER` | Chỉ định broker cung cấp service khi tên service bị trùng giữa nhiều broker. |
| `-p PLAN` | Chỉ định một service plan cần cấp quyền. |
| `-o ORG` | Chỉ định org được cấp quyền. |

`-p` và `-o` quyết định phạm vi cấp quyền. Nếu bỏ cả hai, lệnh cấp quyền cho tất cả plan của service đến tất cả org. Đây là thao tác có phạm vi rộng; admin cần kiểm tra kỹ trước khi chạy.

### Bật tất cả plan cho tất cả org

```bash
cf enable-service-access acme-postgresql
```

Lệnh này làm tất cả plan của service `acme-postgresql` khả dụng cho tất cả org trong foundation. Trạng thái access tương ứng là `all`.

### Bật một plan cho tất cả org

```bash
cf enable-service-access acme-postgresql -p standard
```

Chỉ plan `standard` được bật cho tất cả org. Các plan khác của service không tự động được bật bởi lệnh này.

### Bật tất cả plan cho một org

```bash
cf enable-service-access acme-postgresql -o payments
```

Tất cả plan của service được cấp cho người dùng trong org `payments`; các org khác không tự động nhận quyền này. Trạng thái access của plan là `limited`.

### Bật một plan cho một org

```bash
cf enable-service-access acme-postgresql -p enterprise -o payments
```

Chỉ org `payments` được sử dụng plan `enterprise`. Đây là cách phù hợp khi cần phân phối plan theo hợp đồng hoặc theo nhóm khách hàng.

### Xử lý tên service bị trùng

Nếu nhiều broker cùng công bố service có tên `postgresql`, cần chỉ rõ broker:

```bash
cf enable-service-access postgresql -b acme-database-broker -p enterprise -o payments
```

Tùy chọn `-b` giúp Cloud Foundry xác định đúng service offering. Nếu tên service không bị trùng, có thể bỏ `-b`. Cần dùng đúng tên broker đã đăng ký trong foundation.

## Kiểm tra quyền bằng `cf service-access`

Sau khi thay đổi, admin nên kiểm tra trạng thái thực tế thay vì chỉ dựa vào thông báo `OK` của lệnh.

Cú pháp:

```bash
cf service-access [-b BROKER] [-e SERVICE] [-o ORG]
```

Ví dụ xem toàn bộ quyền service plan:

```bash
cf service-access
```

Lọc theo broker:

```bash
cf service-access -b acme-database-broker
```

Lọc theo service:

```bash
cf service-access -e acme-postgresql
```

Lọc các plan mà một org được phép sử dụng:

```bash
cf service-access -o payments
```

Kết quả thường có các cột broker, service, plan, access và orgs. Ví dụ minh họa:

```text
broker                 service          plan        access    orgs
acme-database-broker   acme-postgresql  standard    all
acme-database-broker   acme-postgresql  enterprise  limited   payments
acme-database-broker   acme-postgresql  trial       none
```

Hãy đọc kết quả như sau:

- `standard` có `access=all`: mọi org có thể thấy và sử dụng plan.
- `enterprise` có `access=limited` và org `payments`: chỉ người dùng trong org đó được cấp quyền.
- `trial` có `access=none`: plan chưa được mở cho org nào.

## Xác minh từ góc nhìn người dùng org

`cf service-access` cho admin thấy chính sách tổng thể. Để xác nhận người dùng thực sự nhìn thấy plan, hãy kiểm tra bằng một tài khoản thuộc org đích.

```bash
cf login -a https://api.example.cf.example
cf target -o payments -s development
cf marketplace
```

Marketplace hiển thị các service và plan khả dụng trong org đang target. Có thể so sánh với một org không được cấp quyền để xác nhận plan giới hạn không bị lộ ra ngoài phạm vi.

Nếu cần kiểm tra khả năng provision, dùng một service instance thử nghiệm trong môi trường phù hợp:

```bash
cf create-service acme-postgresql enterprise test-db
cf service test-db
```

Provision là thao tác tạo tài nguyên thật và có thể phát sinh chi phí. Chỉ chạy kiểm thử này khi có môi trường thử nghiệm, quota và quyền phù hợp; việc kiểm tra Marketplace thường đủ để xác minh visibility ban đầu.

## Thu hồi quyền bằng `cf disable-service-access`

Admin có thể thu hồi quyền bằng lệnh tương ứng:

```bash
cf disable-service-access SERVICE [-b BROKER] [-p PLAN] [-o ORG]
```

Ví dụ thu hồi một plan khỏi một org:

```bash
cf disable-service-access acme-postgresql -p enterprise -o payments
```

Thu hồi toàn bộ plan của service khỏi một org:

```bash
cf disable-service-access acme-postgresql -o payments
```

Thu hồi một plan khỏi tất cả org:

```bash
cf disable-service-access acme-postgresql -p enterprise
```

Thu hồi tất cả plan của service khỏi tất cả org:

```bash
cf disable-service-access acme-postgresql
```

Lệnh không có `-p` hoặc `-o` có phạm vi rộng nhất đối với service được chỉ định. Trước khi chạy trong production, hãy xem `cf service-access` và xác nhận phạm vi ảnh hưởng.

### Giới hạn khi chuyển từ public sang limited

Cloud Foundry có một giới hạn quan trọng: không thể thu hồi riêng quyền của một org đối với plan đang được bật cho tất cả org (`access=all`). Nếu muốn chuyển plan từ public sang chỉ một số org, phải:

1. Tắt quyền của plan trên phạm vi tất cả org.
2. Bật lại quyền cho từng org được phép.
3. Kiểm tra kết quả bằng `cf service-access`.

Ví dụ chuyển plan `enterprise` từ public sang chỉ org `payments` và `finance`:

```bash
cf disable-service-access acme-postgresql -p enterprise
cf enable-service-access acme-postgresql -p enterprise -o payments
cf enable-service-access acme-postgresql -p enterprise -o finance
cf service-access -e acme-postgresql
```

Thực hiện thay đổi trong một cửa sổ vận hành đã thống nhất vì giữa bước disable và các bước enable lại, plan tạm thời không khả dụng cho mọi org. Không thể dùng một lệnh `disable` theo org để loại trừ riêng một org khỏi plan đang public.

## Service access ảnh hưởng đến điều gì?

Service access quyết định org nào có thể nhìn thấy và provision plan trong Marketplace. Nó là chính sách phân phối plan ở Cloud Controller, không phải một lệnh thao tác trực tiếp lên tài nguyên provider.

| Hành động | Tác động |
|---|---|
| `cf enable-service-access` | Mở khả năng nhìn thấy và provision plan trong phạm vi được cấp. |
| `cf disable-service-access` | Ngăn org tương ứng tiếp tục sử dụng plan theo chính sách access. |
| Thay đổi catalog của broker | Thêm, sửa hoặc loại service/plan metadata mà broker công bố. |
| `cf delete-service-broker` | Xóa broker và catalog service/plan khỏi Marketplace; có thể bị chặn nếu còn service instance. |
| `cf delete-service` | Yêu cầu deprovision một service instance cụ thể theo vòng đời OSB. |

Tắt service access không phải thao tác deprovision. Không dùng `cf disable-service-access` để xóa database hoặc thu hồi các instance hiện có; quản lý vòng đời tài nguyên đã provision vẫn phải đi qua các thao tác service instance phù hợp. Tương tự, xóa broker không phải cách thu hồi quyền plan thông thường và có thể làm mất khả năng quản lý các instance còn tồn tại.

## Phân biệt quyền service plan với quyền trong org/space

Cloud Foundry có nhiều lớp quyền khác nhau:

1. **Broker registration:** admin đăng ký broker để Cloud Controller gọi catalog và các endpoint OSB.
2. **Service plan access:** admin dùng `cf enable-service-access` để cấp quyền cho org sử dụng plan.
3. **Org/space role:** người dùng cần vai trò thích hợp, ví dụ Space Developer, để provision instance trong space.
4. **Instance/binding permissions:** quyền thao tác trên instance và binding sau khi tài nguyên đã được tạo.

Một người dùng có thể là Space Developer nhưng không nhìn thấy plan vì org chưa được cấp service access. Ngược lại, org đã có access nhưng người dùng không có vai trò Space Developer trong space thì vẫn không thể tự provision instance tại đó.

Service access cũng khác với service instance sharing. Nếu muốn chia sẻ một instance đã tồn tại giữa các space hoặc org, cần dùng capability và quy trình sharing riêng; chỉ bật service access cho plan không tự chia sẻ một instance hiện có.

## Vai trò của Spring Cloud Open Service Broker

Spring Cloud Open Service Broker giúp ứng dụng triển khai các endpoint OSB như catalog, provision, update, bind và deprovision. Trong tích hợp Cloud Foundry:

- Broker công bố service offering và plan trong catalog.
- Cloud Controller đăng ký broker, lấy catalog và lưu service/plan metadata.
- Admin Cloud Foundry quyết định plan nào public, private hoặc limited theo org.
- Người dùng trong org được cấp quyền nhìn thấy plan qua `cf marketplace` và có thể provision nếu có role phù hợp.

Ứng dụng Spring không nên nhầm `cf enable-service-access` với một endpoint của broker. Đây là lệnh quản trị Cloud Foundry CLI tác động lên access control do Cloud Controller quản lý. Broker có thể quản lý metadata và tính năng plan, nhưng không tự cấp quyền org trong Cloud Foundry chỉ bằng cách trả một trường tùy ý trong OSB catalog.

Khi thêm một plan mới vào catalog standard broker, hãy dự kiến rằng plan đó vẫn private cho đến khi admin bật access. Khi đổi tên service hoặc plan, cần kiểm tra catalog đã được Cloud Controller đồng bộ và dùng đúng tên hiển thị trong CLI. Nếu có nhiều broker cung cấp tên service giống nhau, luôn chỉ rõ `-b` để tránh thay đổi nhầm offering.

## Quy trình vận hành đề xuất

Một quy trình có thể áp dụng khi phát hành plan mới:

1. Hoàn thiện service/plan metadata trong broker và kiểm tra endpoint catalog.
2. Đăng ký hoặc cập nhật standard broker trong Cloud Foundry để Cloud Controller lấy catalog.
3. Dùng admin account chạy `cf service-access` để xác nhận plan mới ở trạng thái private.
4. Xác định org được phép dùng plan dựa trên chính sách sản phẩm, chi phí và quota.
5. Chạy `cf enable-service-access SERVICE -p PLAN -o ORG` cho từng org cần cấp.
6. Chạy `cf service-access` để kiểm tra access thành `limited` và danh sách org đúng.
7. Đăng nhập bằng user thuộc org đích, kiểm tra `cf marketplace`.
8. Nếu cần, provision instance thử nghiệm và kiểm tra operation qua `cf service`.
9. Ghi lại người phê duyệt, broker, service, plan, org, thời điểm và kết quả.
10. Định kỳ rà soát access và thu hồi quyền không còn cần thiết bằng `cf disable-service-access`.

Với plan public cho mọi org, cần có phê duyệt rõ vì một lệnh không có `-o` có thể mở toàn bộ plan của service ra cả foundation. Với plan giới hạn, duy trì danh sách org được cấp và kiểm tra lại sau khi đổi tên org, service hoặc broker.

## Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Service không xuất hiện trong Marketplace | Broker chưa đăng ký, catalog lỗi hoặc service chưa được Cloud Controller lấy. | Kiểm tra registration và catalog trước khi bật access. |
| Service có nhưng plan không xuất hiện | Plan của standard broker đang private hoặc org chưa được cấp quyền. | Dùng `cf service-access`, sau đó bật đúng plan/org. |
| `cf enable-service-access` bị từ chối | Người gọi không có quyền admin. | Dùng tài khoản admin được ủy quyền. |
| Lệnh báo service không rõ ràng | Nhiều broker cung cấp cùng tên service. | Thêm `-b BROKER`. |
| Org đích vẫn không thấy plan | Bật nhầm tên org, plan hoặc foundation; người dùng đang target org khác. | Kiểm tra `cf target`, `cf service-access -o ORG` và đăng nhập bằng user org đích. |
| Không thể disable plan cho một org | Plan đang có access `all`. | Disable trên toàn bộ org rồi enable lại cho các org được phép. |
| Người dùng thấy plan nhưng không tạo được instance | Thiếu role Space Developer, quota hoặc điều kiện khác của org/space. | Kiểm tra role, quota và lỗi provision riêng. |
| Tắt service access nhưng instance vẫn còn | Access control không phải deprovision. | Quản lý instance hiện có bằng lifecycle operation phù hợp. |

## Checklist trước khi cấp quyền plan

1. Đã xác nhận broker là standard hay space-scoped.
2. Service và plan đã xuất hiện trong catalog Cloud Foundry.
3. Người chạy lệnh có quyền admin.
4. Đã xác nhận đúng foundation, broker, service, plan và org.
5. Đã hiểu phạm vi mặc định khi bỏ `-p` hoặc `-o`.
6. Dùng `-b` nếu tên service bị trùng giữa nhiều broker.
7. Đã xem trạng thái hiện tại bằng `cf service-access`.
8. Đã cấp quyền đúng phạm vi all hoặc limited.
9. Đã xác minh từ tài khoản người dùng thuộc org đích bằng `cf marketplace`.
10. Đã phân biệt service access với org/space role và service instance sharing.
11. Đã có kế hoạch thu hồi quyền và hiểu giới hạn chuyển public sang limited.
12. Đã lưu audit record cho thay đổi access.

## Kết luận

Cloud Foundry tách việc công bố service plan khỏi việc cấp quyền sử dụng plan. Spring Cloud Open Service Broker cung cấp catalog; Cloud Controller lưu catalog và áp dụng chính sách service access. Với standard broker, admin dùng `cf enable-service-access` để mở plan cho mọi org, một org, hoặc một plan cụ thể; `cf service-access` giúp kiểm tra trạng thái `all`, `limited` và `none`. Hiểu rõ phạm vi `-p`, `-o`, `-b`, quyền admin và giới hạn khi thu hồi access giúp nhà vận hành phân phối plan đúng tổ chức mà không nhầm lẫn với việc tạo hoặc xóa service instance.

## Tài liệu tham khảo

- [Cloud Foundry Docs – Managing access to Service Plans](https://docs.cloudfoundry.org/services/access-control.html): trạng thái access, quyền admin, cách bật/tắt theo plan và org, cùng giới hạn khi plan đang public.
- [Cloud Foundry CLI Reference – enable-service-access](https://cli.cloudfoundry.org/en-US/v7/enable-service-access.html): cú pháp `SERVICE`, `-b`, `-p`, `-o`.
- [Cloud Foundry CLI Reference – service-access](https://cli.cloudfoundry.org/en-US/v7/service-access.html): cú pháp và bộ lọc trạng thái service access.
- [Cloud Foundry Docs – Managing Service Brokers](https://docs.cloudfoundry.org/services/managing-service-brokers.html): đăng ký broker, standard broker và space-scoped broker.
- [Cloud Foundry Docs – Managing service instances with the cf CLI](https://docs.cloudfoundry.org/devguide/services/managing-services.html): Marketplace và thao tác provision service instance.

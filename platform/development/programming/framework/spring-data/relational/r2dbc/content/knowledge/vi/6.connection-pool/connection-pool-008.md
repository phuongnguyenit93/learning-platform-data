# Tính ngân sách kết nối khi ứng dụng có nhiều bản sao

Khi triển khai ứng dụng Spring Data R2DBC thành nhiều instance, cần tính tổng số kết nối mà toàn bộ các instance có thể mở đến database. Giới hạn `maxSize` trong một connection pool chỉ áp dụng cho pool của một process. Nếu chạy nhiều replica, tổng khả năng mở kết nối là tổng giới hạn của tất cả pool trên tất cả replica, kể cả những replica được tạo tạm thời trong lúc scale hoặc rollout.

Nếu chỉ cấu hình pool dựa trên một instance rồi tăng số replica mà không tính lại, ứng dụng có thể vượt giới hạn kết nối của database. Hậu quả thường thấy là không tạo được kết nối mới, các yêu cầu phải chờ trong hàng đợi của pool, transaction bị chậm hoặc thất bại, và nhiều service có thể ảnh hưởng lẫn nhau vì cùng dùng một ngân sách kết nối.

## 1. Phân biệt giới hạn của một pool và giới hạn toàn hệ thống

`ConnectionPool` quản lý các kết nối được tạo từ một `ConnectionFactory`. Thuộc tính `maxSize` xác định số kết nối tối đa mà một pool có thể quản lý. Pool thường được cấu hình bên trong mỗi ứng dụng process, vì vậy mỗi replica có pool riêng và giới hạn riêng.

Ví dụ, một Deployment có 5 replica và mỗi replica có một pool `maxSize = 20` có khả năng mở tối đa 100 kết nối đến database. Nếu cùng lúc có thêm một worker chạy nền với pool tối đa 10 kết nối, tổng khả năng của hai workload là 110 kết nối.

| Phạm vi | Giới hạn được tính như thế nào |
|---|---|
| Một pool trong một process | `maxSize` của pool đó |
| Một process có nhiều pool | Tổng `maxSize` của tất cả pool trong process |
| Một workload có nhiều replica giống nhau | Số process tối đa nhân với tổng `maxSize` trên mỗi process |
| Toàn bộ hệ thống dùng chung database | Tổng khả năng mở kết nối của mọi workload, job và công cụ vận hành có thể kết nối đến database |

Pool thường tạo kết nối khi có nhu cầu hoặc theo cấu hình khởi tạo, chứ không nhất thiết mở ngay toàn bộ `maxSize`. Tuy nhiên, khi lập ngân sách, cần giả định tất cả pool có thể đạt giới hạn tối đa cùng lúc. Đây là cách tính theo năng lực tối đa, giúp hệ thống vẫn nằm trong giới hạn khi tải tăng.

## 2. Xác định ngân sách kết nối của database

Trước tiên, xác định số kết nối tối đa database cho phép và phần ngân sách phải dành cho các thành phần khác. Không nên phân toàn bộ `max_connections` hoặc giới hạn tương đương cho một ứng dụng.

Ngân sách dành cho ứng dụng có thể biểu diễn như sau:

\[
  B_{app} = C_{db} - C_{reserved} - C_{other}
\]

Trong đó:

- \(C_{db}\): giới hạn kết nối đồng thời của database hoặc của endpoint mà ứng dụng kết nối đến.
- \(C_{reserved}\): phần dành cho quản trị, giám sát, migration, backup, xử lý sự cố và headroom an toàn.
- \(C_{other}\): số kết nối tối đa dự kiến của các ứng dụng, service và workload khác dùng chung database.
- \(B_{app}\): ngân sách tối đa còn lại cho ứng dụng đang được tính.

Ví dụ, database có giới hạn 250 kết nối. Nhóm vận hành dành 20 kết nối cho công cụ quản trị và tác vụ bảo trì, các ứng dụng khác có thể dùng tối đa 70 kết nối, và nhóm dự án giữ lại 30 kết nối làm headroom. Ngân sách còn lại cho ứng dụng hiện tại là:

\[
  B_{app} = 250 - 20 - 70 - 30 = 130
\]

Con số 130 là giới hạn tổng cho toàn bộ replica và pool của ứng dụng, không phải giới hạn cho từng replica.

Giới hạn cần lấy từ cấu hình và môi trường thực tế của database. Với một số hệ quản trị, kết nối quản trị hoặc tài khoản đặc quyền có thể có cơ chế dành riêng; proxy hoặc connection broker cũng có thể áp dụng một giới hạn khác với database backend. Cần tính đúng endpoint mà ứng dụng thực sự kết nối và xác định rõ giới hạn frontend/backend nếu có proxy.

## 3. Tính số replica ở thời điểm cao điểm

Không dùng số replica đang chạy tại thời điểm quan sát làm cơ sở duy nhất. Hãy tính số process có thể đồng thời tồn tại trong tình huống tải cao nhất hoặc trong quá trình triển khai.

Các nguồn làm số process tăng gồm:

- **Horizontal scaling:** HPA hoặc cơ chế autoscaling có thể tăng replica đến `maxReplicas`.
- **Rolling update:** trong lúc rollout, replica mới có thể được tạo trước khi replica cũ dừng. Với Kubernetes Deployment, cần tính cả `maxSurge`.
- **Blue-green deployment:** môi trường mới và cũ có thể cùng hoạt động trong thời gian chuyển traffic.
- **Worker và scheduled job:** các pod xử lý nền, consumer hoặc batch job có thể tạo pool riêng dù không được tính vào số replica của API.
- **Nhiều process trên một máy hoặc pod:** nếu một pod chạy nhiều process ứng dụng, mỗi process có thể sở hữu pool riêng.

Có thể biểu diễn số process cực đại như sau:

\[
  N_{peak} = N_{steady,max} + N_{surge} + N_{extra}
\]

Trong đó \(N_{steady,max}\) là số process tối đa theo cấu hình scale, \(N_{surge}\) là số process có thể tăng thêm trong rollout hoặc chuyển môi trường, và \(N_{extra}\) là các process bổ sung như worker hoặc job nếu chúng chưa được tính trong hai nhóm trước.

Ví dụ, một Deployment có `maxReplicas = 8`, rollout cho phép `maxSurge = 2`, và có thêm 2 worker chạy nền. Nếu tất cả đều dùng cùng database và mỗi process có một pool, số process cần tính là:

\[
  N_{peak} = 8 + 2 + 2 = 12
\]

Hãy tránh cộng trùng một nhóm process. Nếu worker đã được tính trong `N_{steady,max}` thì không cộng chúng thêm lần nữa. Với nhiều Deployment hoặc workload khác nhau, có thể tính riêng từng nhóm rồi cộng tổng.

## 4. Tính maxSize tối đa cho mỗi replica

Khi các replica giống nhau và mỗi process có đúng một pool, giới hạn pool tối đa có thể tính bằng:

\[
  P_{max} \leq \left\lfloor \frac{B_{app}}{N_{peak}} \right\rfloor
\]

Trong đó \(P_{max}\) là `maxSize` của pool trên mỗi process. Dùng phép lấy phần nguyên xuống để tổng kết nối không vượt ngân sách.

Tiếp tục ví dụ trên: ngân sách ứng dụng là 130 kết nối và số process cực đại là 12. Khi đó:

\[
  P_{max} \leq \left\lfloor \frac{130}{12} \right\rfloor = 10
\]

Nếu cấu hình `maxSize = 10` trên mỗi process, tổng khả năng mở kết nối là:

\[
  C_{app,peak} = 12 \times 10 = 120
\]

Ứng dụng vẫn nằm trong ngân sách 130, còn 10 kết nối dự phòng bên trong phần ngân sách của ứng dụng. Nhóm có thể chọn `maxSize` thấp hơn nếu tải thực tế không cần 10 kết nối đồng thời trên mỗi process.

### Ví dụ cấu hình Spring Boot

Khi dùng Spring Boot với R2DBC pool, có thể đặt giới hạn trong `application.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db.internal:5432/orders
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 2
      max-size: 10
      max-acquire-time: 2s
```

Ví dụ giả định dependency R2DBC pool đã có trong ứng dụng và phiên bản Spring Boot đang dùng hỗ trợ các thuộc tính trên. `max-size: 10` là giới hạn cho mỗi application process. Khi chạy 12 process, tổng giới hạn lý thuyết của workload là 120 kết nối.

`initial-size` điều khiển số kết nối ban đầu mà pool khởi tạo theo cấu hình, không phải giới hạn tối đa. `max-acquire-time` giới hạn thời gian chờ lấy kết nối. Giá trị timeout cần được chọn dựa trên SLA và độ trễ database; đặt timeout quá dài có thể làm request giữ tài nguyên lâu, còn quá ngắn có thể khiến request thất bại trong các đợt tải tăng ngắn hạn.

Tên thuộc tính và giá trị mặc định có thể thay đổi theo phiên bản Spring Boot và R2DBC Pool. Hãy đối chiếu cấu hình với phiên bản dependency thực tế của dự án, đồng thời đặt `max-size` tường minh thay vì phụ thuộc vào default.

## 5. Trường hợp có nhiều pool trong một process

Một process có thể dùng nhiều `ConnectionFactory` hoặc nhiều pool, ví dụ một pool đọc và một pool ghi, hoặc kết nối đến hai database khác nhau. Khi đó không thể chỉ lấy `maxSize` của một pool làm ngân sách cho process.

Nếu process có \(K\) pool, giới hạn kết nối tối đa trên một process là tổng giới hạn của các pool:

\[
  P_{process} = \sum_{j=1}^{K} P_j
\]

Với nhiều nhóm workload có số process và pool khác nhau, công thức tổng quát là:

\[
  C_{total} = \sum_{i=1}^{M} N_i \times
              \left(\sum_{j=1}^{K_i} P_{i,j}\right)
\]

Trong đó \(N_i\) là số process cực đại của nhóm workload \(i\), còn \(P_{i,j}\) là `maxSize` của pool thứ \(j\) trong mỗi process thuộc nhóm đó. Tổng này phải nằm trong ngân sách kết nối đã phân bổ cho ứng dụng hoặc toàn bộ hệ thống.

Ví dụ, mỗi API replica có pool đọc tối đa 8 và pool ghi tối đa 4. Nếu có thể tồn tại 10 replica, giới hạn lý thuyết là:

\[
  10 \times (8 + 4) = 120 \text{ kết nối}
\]

Nếu một batch worker có thêm pool tối đa 6 và có thể chạy 2 process, cần cộng thêm 12 kết nối. Tổng năng lực lúc đó là 132 kết nối. Cần đưa cả pool đọc, pool ghi, pool phụ và pool của worker vào bảng tính.

Khi nhiều database độc lập có giới hạn khác nhau, lập ngân sách riêng cho từng database. Một pool kết nối đến database A không tiêu thụ giới hạn kết nối của database B, nhưng nếu hai database dùng chung proxy hoặc hạ tầng trung gian thì cần tính thêm giới hạn của thành phần dùng chung đó.

## 6. Chọn headroom và tránh cấp phát toàn bộ ngân sách

Kết quả phép chia cho biết giới hạn tối đa về mặt số học, không có nghĩa mỗi replica phải được cấu hình đến mức đó. Chọn pool nhỏ hơn có thể giúp giảm số kết nối nhàn rỗi, giảm chi phí tài nguyên trên database và hạn chế tranh chấp khi nhiều instance cùng tăng tải.

Khi chọn `maxSize`, cân nhắc:

- **Mức đồng thời thực tế:** số request cùng lúc có thao tác database, số truy vấn song song trong mỗi request và thời gian giữ connection.
- **Đặc điểm transaction:** transaction thường giữ một connection trong toàn bộ phạm vi transaction. Transaction dài có thể làm pool cạn dù số request không quá lớn.
- **Thời gian truy vấn:** query chậm làm connection được giữ lâu hơn, từ đó tăng số connection đồng thời cần thiết.
- **Mức tăng tải:** pool phải đáp ứng tải đỉnh dự kiến, nhưng không nên dùng việc tăng pool để che giấu query kém hiệu quả hoặc transaction kéo dài.
- **Tài nguyên database:** nhiều connection đồng thời có thể tiêu thụ bộ nhớ, worker, slot và các tài nguyên khác của database.
- **Headroom vận hành:** dành khoảng trống cho migration, tác vụ bảo trì, thay đổi tải và tình huống rollout. Headroom nên được xác định rõ trong ngân sách thay vì coi toàn bộ giới hạn database là khả dụng.

Reactive không có nghĩa là ứng dụng không cần giới hạn connection. Nhiều request reactive vẫn có thể cùng chờ hoặc sử dụng connection. Một luồng `flatMap` không giới hạn concurrency có thể tạo ra nhu cầu truy cập database lớn hơn dự kiến. Cần kiểm soát concurrency ở tầng xử lý và bảo đảm các thao tác database không giữ connection trong lúc chờ công việc không liên quan như gọi HTTP đến dịch vụ khác.

## 7. Proxy và connection pooling ở nhiều tầng

Một số hệ thống dùng proxy hoặc pooler như PgBouncer giữa ứng dụng và database. Khi đó cần phân biệt:

- **Client connection:** kết nối từ mỗi R2DBC pool đến proxy.
- **Backend connection:** kết nối từ proxy đến database thật.

Giới hạn `maxSize` của R2DBC pool thường giới hạn số client connection mà một process có thể mở tới proxy. Proxy có thể multiplex hoặc phân phối các client connection lên một tập backend connection tùy chế độ hoạt động. Do đó, số client connection và số backend connection không nhất thiết bằng nhau.

Việc dùng proxy không loại bỏ nhu cầu tính ngân sách. Cần kiểm tra giới hạn client của proxy, giới hạn backend theo database hoặc user, cách proxy xử lý transaction, session state và prepared statement. Chẳng hạn, chế độ pooling theo transaction có những ràng buộc khác chế độ theo session; ứng dụng không nên giả định mọi hành vi session đều được giữ nguyên khi connection backend được tái sử dụng.

Nếu không có proxy, tổng kết nối từ các pool ứng dụng thường đi trực tiếp vào giới hạn kết nối của database. Nếu có proxy, hãy lập hai ngân sách: một cho client connection đến proxy và một cho backend connection đến database.

## 8. Theo dõi pool và nhận biết thiếu ngân sách

Sau khi triển khai, cần so sánh số liệu thực tế với ngân sách đã tính. Các chỉ số hữu ích gồm:

| Chỉ số | Ý nghĩa khi theo dõi |
|---|---|
| Allocated / total connections | Số kết nối pool đã tạo và đang quản lý. So sánh với `maxSize` trên từng replica. |
| Active connections | Số kết nối đang được mượn để thực hiện thao tác. Tăng cao kéo dài có thể cho thấy pool hoặc database đang chịu tải lớn. |
| Idle connections | Số kết nối đang rảnh trong pool. Nhiều idle connection trên mọi replica có thể làm tổng kết nối cao dù tải thấp. |
| Pending acquire | Số yêu cầu đang chờ lấy connection. Giá trị tăng kéo dài là dấu hiệu pool không đáp ứng kịp nhu cầu hoặc connection bị giữ quá lâu. |
| Acquire latency / timeout | Thời gian chờ lấy connection và số lần hết thời gian chờ. Dùng để phát hiện nghẽn trước khi request thất bại hàng loạt. |
| Database connections | Tổng kết nối theo ứng dụng, user hoặc client ở phía database. Dùng để đối chiếu với ngân sách toàn hệ thống. |

Các metric cụ thể phụ thuộc phiên bản R2DBC Pool, Spring Boot và hệ thống quan sát đang dùng. Nên gắn nhãn theo application, pod/instance và pool để cộng số liệu giữa các replica. Chỉ nhìn metric của một pod sẽ bỏ sót tổng kết nối của workload.

Một số dấu hiệu thường gặp:

- **Pool chạm `maxSize` và pending acquire tăng:** ứng dụng đang cần nhiều kết nối đồng thời hơn khả năng pool cấp. Kiểm tra thời gian query, transaction, concurrency và cấu hình pool.
- **Database gần chạm giới hạn nhưng pool từng replica chưa đầy:** có thể có nhiều replica, pool khác, job hoặc ứng dụng khác cùng kết nối. Cộng số liệu toàn hệ thống.
- **Kết nối tăng đột ngột khi rollout:** số pod mới và cũ cùng tồn tại, làm tổng pool capacity tăng theo số process thực tế.
- **Nhiều kết nối idle trên nhiều replica:** `initial-size` hoặc cấu hình giữ kết nối tối thiểu có thể quá cao so với số replica. Xem xét giảm lượng kết nối khởi tạo hoặc giới hạn pool.
- **Acquire timeout dù database chưa chạm giới hạn:** có thể pool cục bộ đã đầy, connection bị giữ lâu hoặc truy vấn chậm. Giới hạn database tổng thể và giới hạn pool từng process là hai tầng khác nhau.

Không nên xử lý mọi lỗi pool bằng cách tăng `maxSize`. Nếu database đã gần giới hạn, tăng pool chỉ làm vấn đề nghiêm trọng hơn. Trước tiên cần xác định nghẽn xảy ra ở pool của ứng dụng, proxy hay database.

## 9. Quy trình lập và cập nhật ngân sách

Có thể dùng quy trình sau cho mỗi môi trường triển khai:

1. Ghi lại giới hạn kết nối thực tế của database và proxy nếu có.
2. Trừ phần dành cho quản trị, monitoring, migration, các workload khác và headroom vận hành để có ngân sách ứng dụng.
3. Liệt kê tất cả Deployment, worker, consumer, scheduled job và process có thể kết nối đến database.
4. Tính số process cao nhất, gồm autoscaling, rollout surge và thời gian chạy chồng lấn giữa phiên bản cũ với mới.
5. Liệt kê mọi pool trên mỗi process, kể cả pool đọc/ghi hoặc kết nối đến nhiều database.
6. Phân bổ `maxSize` sao cho tổng năng lực kết nối không vượt ngân sách; chọn giá trị thực tế dựa trên concurrency và thời gian giữ connection.
7. Kiểm tra metric ở tải bình thường, tải đỉnh và trong rollout; điều chỉnh pool hoặc concurrency dựa trên số liệu.
8. Tính lại ngân sách khi thay đổi `maxReplicas`, `maxSurge`, số worker, số pool, hoặc giới hạn database.

Một bảng ngân sách nhỏ giúp nhóm vận hành kiểm tra tác động của thay đổi trước khi triển khai:

| Nhóm | Process cực đại | Pool trên mỗi process | Tổng kết nối tối đa |
|---|---:|---:|---:|
| API replicas, gồm rollout surge | 10 | 1 × 10 | 100 |
| Background workers | 2 | 1 × 6 | 12 |
| **Tổng ứng dụng** | | | **112** |

Với ngân sách ứng dụng 130 kết nối trong ví dụ trước, cấu hình này còn 18 kết nối headroom. Nếu số API replica tối đa tăng từ 8 lên 12 hoặc rollout surge thay đổi, cần tính lại số process cực đại và xác nhận tổng 112 vẫn nằm trong ngân sách. Bảng phải phản ánh đúng số pool thực tế, không chỉ số pod hiển thị trong dashboard.

Ngân sách kết nối là một phần của thiết kế triển khai. Mỗi pool được cấu hình trên một replica đều góp vào tổng tải của database. Khi tính theo số process cực đại, cộng tất cả pool và dành chỗ cho các workload khác, nhóm có thể scale ứng dụng mà không vô tình vượt giới hạn kết nối ở thời điểm tải cao hoặc rollout.

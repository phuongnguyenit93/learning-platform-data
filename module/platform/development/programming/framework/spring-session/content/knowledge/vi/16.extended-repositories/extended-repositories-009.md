# Chọn kho theo yêu cầu và bằng chứng thử nghiệm thay vì chỉ đổi dependency

Spring Session tách API `HttpSession` khỏi nơi lưu dữ liệu phiên. Ứng dụng Servlet tiếp tục dùng `getAttribute`, `setAttribute`, `invalidate` và các API quen thuộc; `SessionRepositoryFilter` chuyển những thao tác đó đến một `SessionRepository` cụ thể. Repository có thể lưu phiên trong Redis, JDBC hoặc một implementation mở rộng phù hợp với phiên bản và hạ tầng của dự án.

Vì vậy, chọn kho lưu phiên là quyết định kiến trúc và vận hành. Thêm dependency Redis hoặc JDBC chỉ đưa thư viện vào classpath; nó không chứng minh kho đó phù hợp với tải thực tế, không tự chuyển dữ liệu session đang tồn tại và cũng không bảo đảm nhiều instance dùng cùng một cấu hình. Hãy chọn theo yêu cầu đo được rồi xác nhận bằng thử nghiệm có thể lặp lại.

## 1. Bắt đầu từ yêu cầu của ứng dụng

Trước khi so sánh sản phẩm hoặc thêm dependency, mô tả cách ứng dụng sử dụng session:

- Có bao nhiêu phiên hoạt động đồng thời và tốc độ tạo phiên mới là bao nhiêu?
- Mỗi request đọc/ghi session bao nhiêu lần? Có request chỉ đọc, request cập nhật thường xuyên hoặc request chạy lâu không?
- Kích thước trung bình và kích thước lớn nhất của session là bao nhiêu byte sau serialization?
- Session có chứa dữ liệu tạm thời có thể tạo lại hay trạng thái mà người dùng không được phép mất?
- Cần tìm phiên theo session ID hay còn cần tra cứu theo principal để quản lý nhiều thiết bị?
- Thời hạn không hoạt động, tuổi tuyệt đối và thời gian dọn dữ liệu được yêu cầu như thế nào?
- Khi kho dữ liệu gián đoạn, ứng dụng cần fail closed, tạm từ chối request hay có một hành vi phục hồi cụ thể?
- Các instance có cần chia sẻ phiên xuyên vùng, xuyên cụm hoặc xuyên phiên bản triển khai không?

Các câu trả lời này tạo ra tiêu chí lựa chọn. Ví dụ, một ứng dụng nội bộ có ít phiên và database quan hệ đã được vận hành tốt có thể phù hợp với JDBC. Một ứng dụng có tần suất đọc/ghi session cao, cần độ trễ thấp và có hạ tầng Redis được vận hành tin cậy có thể ưu tiên Redis. Không có lựa chọn đúng cho mọi hệ thống.

## 2. Các tiêu chí cần đánh giá

Nên đánh giá kho session theo ít nhất các nhóm sau:

| Tiêu chí | Câu hỏi cần trả lời | Bằng chứng nên thu thập |
|---|---|---|
| Độ trễ | Request có thể chấp nhận thêm bao nhiêu thời gian khi đọc/ghi session? | p50, p95, p99 của request và thao tác repository |
| Thông lượng | Kho có chịu được số request đồng thời và tốc độ tạo phiên dự kiến không? | Request/second, session operation/second, queue depth |
| Dung lượng | Có bao nhiêu session và dữ liệu trung bình/lớn nhất mỗi session? | Số phiên, byte/phiên, memory hoặc dung lượng bảng |
| Độ bền dữ liệu | Có thể chấp nhận mất session khi node hoặc kho gặp sự cố không? | Cấu hình persistence/backup, transaction, phục hồi và RPO/RTO |
| Tính sẵn sàng | Ứng dụng xử lý ra sao khi một node hoặc cả kho bị lỗi? | Failover test, thời gian phục hồi, tỷ lệ lỗi trong sự cố |
| Mẫu truy vấn | Chỉ cần tìm theo session ID hay cần tìm theo principal? | Test các API truy vấn và chi phí index |
| Hết hạn và cleanup | Phiên hết hạn có bị từ chối đúng lúc và dữ liệu được dọn ra sao? | TTL, cleanup lag, số bản ghi hết hạn tồn đọng |
| Đồng thời | Hai request cùng cập nhật một session có gây mất dữ liệu không? | Test race, lost update và quy tắc nghiệp vụ |
| Tương thích dữ liệu | Các instance đang chạy có đọc được session do phiên bản khác ghi không? | Test serialization fixture và rolling deployment |
| Vận hành | Đội ngũ có khả năng giám sát, backup, nâng cấp và xử lý sự cố không? | Runbook, dashboard, cảnh báo, thời gian thao tác thực tế |
| Bảo mật | Có thể giới hạn quyền, mã hóa đường truyền và bảo vệ dữ liệu lưu không? | ACL/role, TLS, secret rotation, backup access review |
| Chi phí | Chi phí tổng thể khi tải bình thường và tải đỉnh là bao nhiêu? | Hạ tầng, license nếu có, backup, vận hành và nhân lực |

Không nên chỉ chọn theo throughput tối đa trong một benchmark. Session store nằm trên đường xử lý request, nên độ trễ đuôi, độ ổn định khi tải đỉnh và hành vi khi kho gặp lỗi thường quan trọng không kém thông lượng trung bình.

## 3. So sánh Redis và JDBC theo workload

Redis và JDBC có đặc tính vận hành khác nhau. Bảng dưới đây là định hướng để xây dựng giả thuyết; kết quả cuối cùng phải đến từ cấu hình và tải thực tế.

| Khía cạnh | Spring Session Redis | Spring Session JDBC |
|---|---|---|
| Mô hình lưu trữ | Key/value và cấu trúc dữ liệu Redis | Bảng quan hệ cho metadata và thuộc tính phiên |
| Truy cập | Thường có độ trễ thấp khi Redis ở gần ứng dụng | Phụ thuộc database, connection pool, index và tải SQL |
| Hết hạn | Có thể dùng TTL và cơ chế expiration của Redis | Repository quản lý thời hạn và cleanup các hàng hết hạn |
| Giao dịch | Phụ thuộc thao tác và semantics của repository/Redis; không mặc định là transaction nghiệp vụ | Có thể dùng transaction JDBC và transaction manager tương ứng |
| Tra cứu theo principal | Có repository indexed hỗ trợ index principal | Repository JDBC indexed hỗ trợ truy vấn theo principal theo cấu hình/schema |
| Vận hành | Cần quản lý bộ nhớ, eviction, persistence, replication/failover và keyspace | Cần quản lý schema, index, connection pool, cleanup và backup database |
| Khả năng dùng chung hạ tầng | Cần Redis deployment đủ độ sẵn sàng và cô lập phù hợp | Có thể tận dụng database quan hệ đã có, nhưng phải đánh giá tải phụ lên database |
| Rủi ro nổi bật | Eviction/mất dữ liệu, memory pressure, failover và cấu hình TTL | Bảng tăng trưởng, query chậm, lock/connection exhaustion và cleanup lag |

Redis thường phù hợp khi yêu cầu độ trễ thấp, tải session lớn và tổ chức có năng lực vận hành Redis. JDBC có thể phù hợp khi muốn dùng database quan hệ hiện có, cần quản lý schema bằng migration và chấp nhận đặc tính độ trễ của database. Nếu session traffic lớn, dùng chung database nghiệp vụ có thể gây tranh chấp connection và tài nguyên; cần benchmark trước khi quyết định.

## 4. Xác định có cần repository mở rộng hay không

Ngoài repository cơ bản, Spring Session có thể cung cấp implementation mở rộng với khả năng như tra cứu theo principal, event hoặc tích hợp với một backend cụ thể. Tên module và tính năng có thể thay đổi theo phiên bản Spring Session. Cần xác minh artifact và tài liệu của đúng phiên bản đang dùng.

Hãy hỏi theo nghiệp vụ:

- Có cần tìm mọi session của một người dùng khi không biết session ID không?
- Có cần màn hình liệt kê thiết bị đang đăng nhập hoặc nút “đăng xuất tất cả thiết bị” không?
- Có cần Spring Security concurrent session control dựa trên registry đọc từ repository không?
- Có cần nhận event tạo, xóa hoặc hết hạn để dọn metadata phụ trợ không?
- Có cần một backend riêng mà Spring Session chưa cung cấp implementation phù hợp không?

Nếu không có nhu cầu tra cứu theo principal, repository cơ bản có thể đủ. Nếu cần tính năng indexed, chọn implementation hỗ trợ `FindByIndexNameSessionRepository` và xác minh principal thực sự được index. Nếu cần event, kiểm tra nguồn phát, cấu hình backend và khả năng giao event; không xem event listener là cơ chế duy nhất để bảo vệ quyền truy cập.

Một implementation tùy chỉnh phải đáp ứng hợp đồng `SessionRepository` và semantics mà ứng dụng dựa vào: tạo session, tìm theo ID, lưu thay đổi, xóa, timeout và hành vi khi dữ liệu không tồn tại. Nếu ứng dụng dùng các interface mở rộng như `FindByIndexNameSessionRepository`, implementation cũng phải thực hiện đúng các hợp đồng đó. Không chỉ tạo một adapter có tên phù hợp mà bỏ qua semantics về hết hạn, đồng thời hoặc lưu dữ liệu.

## 5. Dependency không phải bằng chứng repository đã được chọn

Ví dụ một dự án thêm module Redis:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.session:spring-session-data-redis")
}
```

Điều này đưa các lớp Redis vào classpath. Ứng dụng còn cần cấu hình kết nối, repository và filter theo cơ chế Spring Boot/Spring Session của phiên bản đang dùng. Nếu cùng lúc có nhiều module repository, cần xác nhận implementation nào được tạo và gắn với `SessionRepositoryFilter`.

Với Spring Boot, có thể chọn loại store bằng property nếu phiên bản hỗ trợ:

```yaml
spring:
  session:
    store-type: redis
```

Hoặc chọn JDBC:

```yaml
spring:
  session:
    store-type: jdbc
```

Các giá trị và hành vi auto-configuration phụ thuộc phiên bản Boot. Cần kiểm tra configuration metadata và bean thực tế, không chỉ kiểm tra file YAML. Đổi `store-type` không tự sao chép session từ Redis sang JDBC hoặc ngược lại.

## 6. Dùng bằng chứng từ application context

Sau khi khởi động, xác nhận repository mà ứng dụng thực sự sử dụng. Có thể kiểm tra bean trong test:

```java
@SpringBootTest
class SessionRepositorySelectionTest {

    @Autowired
    SessionRepository<?> sessionRepository;

    @Test
    void repositoryIsConfigured() {
        assertThat(sessionRepository).isNotNull();
    }
}
```

Test cơ bản này chỉ xác nhận có bean. Để chứng minh lựa chọn đúng, kiểm tra kiểu implementation hoặc các interface capability cần thiết. Ví dụ, nếu nghiệp vụ cần tra cứu theo principal, kiểm tra bean có triển khai `FindByIndexNameSessionRepository`.

Ngoài test, có thể dùng log khởi động và báo cáo điều kiện auto-configuration của Spring Boot để xem cấu hình nào được áp dụng. Không bật log chứa session ID hoặc thuộc tính nhạy cảm. Trong môi trường nhiều instance, thu thập thông tin loại repository, profile, namespace/schema và phiên bản ứng dụng từ từng node để phát hiện cấu hình lệch.

## 7. Xây dựng bộ kiểm thử hợp đồng repository

Trước khi benchmark hiệu năng, xác nhận implementation đáp ứng hành vi cần thiết. Một bộ kiểm thử hợp đồng tối thiểu nên gồm:

1. **Create:** tạo session mới, kiểm tra ID và metadata ban đầu.
2. **Save:** đặt thuộc tính, lưu session, rồi đọc lại và xác nhận giá trị.
3. **Find:** tìm đúng session theo ID; ID không tồn tại phải cho kết quả không có session theo hợp đồng.
4. **Delete:** xóa session, sau đó xác nhận không thể khôi phục.
5. **Timeout:** để session hết hạn và xác nhận repository không trả phiên đã hết hạn.
6. **Update:** thay đổi thuộc tính và metadata timeout, rồi xác nhận thay đổi được lưu.
7. **Principal index:** nếu dùng tính năng này, xác nhận tìm đúng phiên và không trả phiên của principal khác.
8. **Events:** nếu nghiệp vụ phụ thuộc event, xác nhận cấu hình phát và listener có thể xử lý lặp hoặc event đến trễ.
9. **Serialization:** lưu bằng một instance và đọc bằng instance khác có cùng serializer/classpath.
10. **Concurrency:** hai request cùng cập nhật một phiên phải có kết quả phù hợp với quy tắc nghiệp vụ đã định nghĩa.

Test hợp đồng nên chạy với backend thật trong môi trường kiểm thử, chẳng hạn Redis test hoặc DBMS cùng loại với production. Mock repository có thể hữu ích cho unit test service, nhưng không chứng minh TTL, transaction, serialization hoặc failover của backend.

## 8. Thiết kế benchmark có thể so sánh

Benchmark chỉ có ý nghĩa khi hai lựa chọn nhận cùng workload và điều kiện hạ tầng. Trước khi chạy, cố định:

- Cùng phiên bản ứng dụng, JVM, Spring Boot và Spring Session.
- Cùng cấu hình session attribute, serializer và kích thước dữ liệu.
- Cùng số instance ứng dụng, CPU/memory limit và network path.
- Cùng số phiên đồng thời, tỷ lệ tạo/đọc/cập nhật/xóa và timeout.
- Cùng thời gian warm-up, thời gian đo, tải tăng dần và tải đỉnh.
- Cùng điều kiện backup, persistence, replication và mức sẵn sàng mà production yêu cầu.

Một workload mẫu có thể mô phỏng:

| Loại thao tác | Tỷ lệ giả định | Mục đích |
|---|---:|---|
| Đọc session | 70% | Mô phỏng request chủ yếu kiểm tra trạng thái người dùng |
| Cập nhật một thuộc tính nhỏ | 20% | Mô phỏng cập nhật locale, workflow hoặc mã tham chiếu |
| Tạo session mới | 7% | Mô phỏng đăng nhập hoặc khởi tạo phiên |
| Xóa/invalidate session | 3% | Mô phỏng logout hoặc thu hồi |

Các tỷ lệ này chỉ là ví dụ khởi đầu. Hãy thay bằng tỷ lệ quan sát từ hệ thống thật hoặc dự báo có căn cứ. Nếu ứng dụng có nhiều request ghi session hoặc session rất lớn, benchmark phải phản ánh đúng đặc điểm đó.

Không chỉ đo một endpoint đơn giản. Tạo test đi qua `SessionRepositoryFilter` và HTTP stack để tính cả serialization, cookie/header resolver, filter, connection pool và repository. Đồng thời đo trực tiếp repository ở một bài test riêng để tách chi phí backend khỏi chi phí ứng dụng.

## 9. Đo các chỉ số quan trọng

Ghi nhận tối thiểu:

| Nhóm | Chỉ số |
|---|---|
| Hiệu năng request | Throughput, p50/p95/p99 latency, timeout và error rate |
| Repository | Thời gian find/save/delete, số lệnh backend trên mỗi request |
| Redis | Memory usage, hit/miss nếu phù hợp, evictions, connected clients, command latency, replication lag |
| JDBC | Active/idle connection, wait time, pool exhaustion, query latency, lock wait, deadlock |
| Dữ liệu | Session count, bytes/session, tổng dung lượng, số phiên hết hạn chưa cleanup |
| Ứng dụng | CPU, heap, GC, serialization time, thread saturation |
| Phục hồi | Thời gian failover, thời gian phục hồi, số request lỗi và session bị mất |

Độ trễ p99 đặc biệt hữu ích vì một số request chậm có thể làm người dùng cảm thấy hệ thống không ổn định dù độ trễ trung bình tốt. Theo dõi cả lúc tải bình thường và lúc tăng tải, restart node, backup hoặc failover.

## 10. Kiểm thử lỗi và phục hồi

Một kho phù hợp phải có hành vi rõ ràng khi xảy ra sự cố. Thử nghiệm có kiểm soát các tình huống:

- Redis/database tạm thời không truy cập được.
- Connection pool cạn hoặc hết timeout.
- Một node ứng dụng bị dừng giữa lúc xử lý request.
- Backend failover hoặc chuyển primary.
- Mất kết nối sau khi nghiệp vụ commit nhưng trước khi session save hoàn tất.
- Session hết TTL trong khi request khác đang sử dụng.
- Serializer lỗi hoặc một instance chạy classpath khác phiên bản.
- Cleanup/event listener bị dừng rồi khởi động lại.

Đối với mỗi tình huống, xác định request nào được retry, request nào phải thất bại, session có thể mất hay không và người dùng cần đăng nhập lại trong trường hợp nào. Không biến lỗi backend thành `session == null` một cách im lặng; không đọc được kho không đồng nghĩa session không tồn tại.

Với dữ liệu session chỉ là trạng thái phụ, có thể chấp nhận người dùng đăng nhập lại sau sự cố. Với hệ thống yêu cầu giữ trạng thái cao hơn, cần cấu hình durability/backup/replication phù hợp và xác minh bằng phục hồi thực tế, không chỉ dựa vào tài liệu sản phẩm.

## 11. Kiểm thử nhiều instance và rolling deployment

Chạy ít nhất hai instance cùng trỏ tới một backend. Tạo phiên qua instance A, lấy cookie hoặc header session ID, rồi gửi request mang định danh đó đến instance B. B phải khôi phục được cùng thuộc tính. Tiếp theo, cập nhật phiên ở A và xác nhận B đọc được thay đổi sau khi lưu theo chính sách đã chọn.

Thử thêm:

- Logout ở A rồi gửi lại ID cũ đến B.
- Hết TTL khi request luân phiên giữa A và B.
- Rolling deployment với phiên bản mới và cũ chạy đồng thời.
- Hai request cùng cập nhật một thuộc tính session.
- Thay đổi serializer hoặc class attribute và xác nhận tương thích.

Các node cần thống nhất repository, endpoint, namespace/schema, cookie/header name, serializer và chính sách timeout. Sticky session ở load balancer không thay thế backend dùng chung. Nếu mỗi node dùng store cục bộ hoặc cấu hình khác nhau, kết quả kiểm thử chuyển node sẽ phát hiện phiên không được chia sẻ.

## 12. Đánh giá chi phí vận hành và tổng chi phí sở hữu

Chi phí kho session không chỉ là giá máy chủ. Hãy tính:

- Redis memory hoặc database storage theo số phiên và kích thước serialized.
- CPU và network cho serialization, lệnh Redis hoặc truy vấn SQL.
- Replica, backup, snapshot và môi trường phục hồi.
- Connection pool và tài nguyên database nếu dùng JDBC.
- Giám sát, cảnh báo, cleanup và thời gian xử lý sự cố.
- Công sức nâng cấp schema, serializer và compatibility khi triển khai phiên bản mới.
- Năng lực trực vận hành, runbook và yêu cầu phân quyền.

Redis có thể cần bộ nhớ lớn hơn dự kiến nếu session attributes chứa object lớn hoặc key phụ/index; JDBC có thể tăng dung lượng bảng và áp lực index/cleanup. Hãy đo kích thước thực sau serialization, không ước lượng chỉ từ kích thước object trong heap.

Nếu session traffic làm ảnh hưởng database nghiệp vụ, cần tính chi phí tách database hoặc connection pool riêng. Nếu Redis dùng chung với cache không quan trọng, đánh giá chính sách eviction và khả năng cache workload đẩy session key ra khỏi bộ nhớ. Không để session quan trọng bị eviction chỉ vì cache khác dùng chung một giới hạn bộ nhớ.

## 13. Migration khi đổi repository

Đổi dependency hoặc `spring.session.store-type` không chuyển session đang tồn tại từ backend cũ sang backend mới. Cookie của client có thể còn giữ session ID cũ, nhưng repository mới không tìm thấy bản ghi tương ứng. Hệ quả thường là người dùng phải đăng nhập lại hoặc ứng dụng tạo một phiên mới khi được phép.

Trước khi chuyển đổi, chọn một trong các phương án:

1. **Kết thúc phiên cũ:** thông báo trước, chuyển traffic theo cửa sổ triển khai và yêu cầu đăng nhập lại. Đây là cách đơn giản nếu session có thể tái tạo.
2. **Migration dữ liệu:** đọc session cũ, chuyển đổi thuộc tính và serializer, ghi sang repository mới, xác minh số lượng và nội dung rồi mới chuyển traffic. Cần xử lý TTL còn lại, lỗi từng bản ghi, dữ liệu không tương thích và retry.
3. **Chuyển tiếp có thời hạn:** một lớp migration đọc từ backend cũ và ghi sang backend mới theo quy tắc rõ ràng. Cách này phức tạp, cần tránh hai nguồn cùng nhận quyền ghi và cần có thời điểm kết thúc cụ thể.

Không chạy một nửa cụm trên Redis và nửa còn lại trên JDBC với cùng cookie nếu chưa có cơ chế tương thích được thiết kế. Rolling deployment cần thống nhất nguồn dữ liệu phiên trong suốt giai đoạn chuyển tiếp. Có thể dùng namespace mới để cô lập thử nghiệm, nhưng client phải được định tuyến và chuyển định danh theo một quy tắc có kiểm soát.

## 14. Quy trình quyết định dựa trên bằng chứng

Một quy trình lựa chọn thực tế:

1. **Ghi yêu cầu:** số phiên, kích thước, tần suất đọc/ghi, timeout, query patterns, RPO/RTO và mục tiêu p95/p99.
2. **Chọn ứng viên:** Redis, JDBC hoặc implementation mở rộng đáp ứng các yêu cầu chức năng.
3. **Xác minh capability:** kiểm tra repository interface, principal index, event, TTL và serializer thực sự được hỗ trợ.
4. **Tạo cấu hình thử nghiệm:** cùng phiên bản ứng dụng, cấu hình bảo mật, dữ liệu và hạ tầng gần production.
5. **Chạy contract test:** create, find, save, delete, expiry, principal lookup và multi-instance.
6. **Chạy benchmark:** workload đại diện, tải tăng dần, tải đỉnh và đo p50/p95/p99.
7. **Chạy fault test:** backend outage, failover, connection exhaustion, restart và serialization mismatch.
8. **So sánh chi phí:** tài nguyên, backup, giám sát, vận hành và công sức nâng cấp.
9. **Ghi quyết định:** nêu tiêu chí, dữ liệu thử nghiệm, giới hạn đã biết và điều kiện cần đánh giá lại.
10. **Triển khai có kiểm soát:** canary, giám sát, rollback plan và chính sách session cũ.

## 15. Mẫu bảng quyết định

Có thể dùng bảng sau trong architecture decision record (ADR). Trọng số và điểm phải được nhóm dự án xác định từ yêu cầu, không lấy các giá trị ví dụ làm kết luận chung.

| Tiêu chí | Trọng số | Redis | JDBC | Bằng chứng cần đính kèm |
|---|---:|---:|---:|---|
| p99 latency |  |  |  | Benchmark cùng workload |
| Throughput tải đỉnh |  |  |  | Load test |
| Durability/RPO |  |  |  | Backup/restore và failover test |
| Principal lookup |  |  |  | Contract test theo principal |
| TTL/cleanup |  |  |  | Expiration và cleanup test |
| Vận hành hiện có |  |  |  | Runbook, năng lực đội ngũ |
| Chi phí tổng thể |  |  |  | Ước tính tài nguyên và nhân lực |
| Migration/compatibility |  |  |  | Rolling deployment test |

Mỗi điểm số cần gắn với bằng chứng. Nếu chưa có dữ liệu, đánh dấu chưa biết thay vì tự chấm điểm. Một lựa chọn có điểm hiệu năng tốt nhưng không đáp ứng RPO, khả năng phục hồi hoặc yêu cầu bảo mật bắt buộc phải bị loại dù tổng điểm có vẻ cao.

## 16. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách tránh |
|---|---|---|
| Chọn Redis chỉ vì nghe nói nhanh | Có thể tăng chi phí và độ phức tạp vận hành mà không giải quyết bottleneck thật | Benchmark cùng workload và tính cả failover/durability |
| Chọn JDBC vì đã có database | Session traffic có thể làm cạn connection pool hoặc tăng tải truy vấn | Tách pool, đo tải và đánh giá ảnh hưởng database nghiệp vụ |
| Chỉ thêm dependency rồi triển khai | Repository hoặc filter có thể chưa được cấu hình như mong muốn | Kiểm tra bean, auto-configuration và hành vi HTTP |
| Chỉ benchmark repository trực tiếp | Bỏ qua filter, serializer, cookie/header và application overhead | Chạy cả benchmark HTTP end-to-end |
| Chỉ đo latency trung bình | Che giấu request chậm ở p99 | Theo dõi phân vị và tải đỉnh |
| Dùng mock để kết luận backend hoạt động | Không kiểm tra TTL, transaction, serialization và failover | Dùng backend thật trong integration test |
| Đổi store type mà không có migration plan | Session ID cũ không tìm thấy ở kho mới | Chủ động kết thúc hoặc chuyển đổi session |
| Coi lỗi backend là session hết hạn | Có thể tạo phiên rỗng và che giấu sự cố xác thực | Phân biệt repository unavailable với session missing |
| Bỏ qua rolling deployment | Instance cũ và mới có thể không đọc được cùng session | Kiểm thử serializer, schema và cấu hình giữa phiên bản |

## 17. Checklist trước khi chốt repository

- [ ] Yêu cầu session được mô tả bằng số phiên, kích thước, tỷ lệ đọc/ghi và mục tiêu độ trễ.
- [ ] Đã xác định có cần principal lookup, concurrent session control hoặc session events không.
- [ ] Repository và capability thực tế đã được xác nhận trong application context.
- [ ] Contract test chạy trên backend thật.
- [ ] Benchmark đi qua HTTP filter và dùng workload gần production.
- [ ] Có số liệu p50/p95/p99, throughput, lỗi, memory hoặc connection pool.
- [ ] Đã kiểm thử TTL, cleanup, logout và request đồng thời.
- [ ] Đã thử backend outage, restart và failover theo yêu cầu.
- [ ] Đã kiểm tra hai instance đọc/ghi cùng session.
- [ ] Đã kiểm tra rolling deployment và tương thích serializer/schema.
- [ ] Có phương án migration hoặc kết thúc session cũ khi đổi backend.
- [ ] Có dashboard, cảnh báo, backup/restore và runbook vận hành.
- [ ] Quyết định được ghi lại cùng dữ liệu thử nghiệm và giới hạn còn tồn tại.

Chọn repository cho Spring Session không phải là thao tác thay một dependency. Đó là quyết định về semantics lưu phiên, hiệu năng trên đường request, khả năng phục hồi, truy vấn cần hỗ trợ và năng lực vận hành. Khi yêu cầu được lượng hóa, implementation được xác minh và lựa chọn được thử bằng contract test, benchmark cùng fault test, nhóm phát triển có bằng chứng để chọn kho phù hợp và có thể giải thích khi nào cần đánh giá lại quyết định đó.

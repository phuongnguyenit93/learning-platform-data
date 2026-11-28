# So sánh thời hạn, cơ chế dọn dữ liệu và chính sách ghi

Spring Session cung cấp cùng một mô hình `SessionRepository` cho ứng dụng Servlet, nhưng mỗi repository có cách áp dụng thời hạn, dọn dữ liệu và ghi thay đổi khác nhau. Redis có thể dùng TTL và keyspace notifications; JDBC và MongoDB thường dựa trên thời điểm hết hạn cùng tác vụ cleanup; Hazelcast có thể dùng TTL của entry trong `IMap`; còn `MapSessionRepository` không tự cung cấp hạ tầng dọn phiên.

Ngoài thời hạn, ứng dụng còn phải chọn cách theo dõi thuộc tính thay đổi (`SaveMode`) và thời điểm đẩy thay đổi xuống kho (`FlushMode`). Hai chính sách này ảnh hưởng số lần ghi, khả năng quan sát dữ liệu giữa các request và nguy cơ ghi đè khi nhiều request cùng cập nhật một session.

## 1. Ba khái niệm cần tách biệt

Khi so sánh repository, cần phân biệt ba lớp hành vi:

1. **Thời hạn hợp lệ của session:** xác định lúc nào một session không còn được chấp nhận cho request mới.
2. **Dọn dữ liệu vật lý:** xác định khi nào bản ghi hoặc key đã hết hạn được xóa khỏi kho lưu trữ.
3. **Chính sách ghi:** xác định thuộc tính nào được lưu và thời điểm thay đổi được ghi xuống kho.

Ba lớp này liên quan nhưng không đồng nhất. Một session có thể đã hết hạn về mặt logic nhưng bản ghi vẫn còn trong database hoặc Redis một thời gian. Một thuộc tính có thể đã thay đổi trong bộ nhớ của request nhưng chưa được ghi xuống kho nếu repository dùng chế độ `ON_SAVE`.

Ví dụ, một session có timeout 30 phút. Sau 30 phút không hoạt động, request tiếp theo không được khôi phục session đó. Tuy nhiên, tác vụ cleanup có thể chỉ chạy mỗi phút hoặc Redis có thể phát thông báo hết hạn muộn hơn. Khoảng trễ dọn vật lý không có nghĩa session vẫn được xác thực.

## 2. Thời hạn của Session được tính như thế nào?

Một `Session` thường có các thông tin thời gian:

- `creationTime`: thời điểm tạo phiên.
- `lastAccessedTime`: lần truy cập gần nhất.
- `maxInactiveInterval`: khoảng không hoạt động tối đa trước khi phiên hết hạn.

Có thể hình dung thời điểm hết hạn là:

```text
expirationTime = lastAccessedTime + maxInactiveInterval
```

Khi request sử dụng session, thời điểm truy cập cuối được cập nhật theo vòng đời xử lý của repository. Nếu không có request mới trước thời điểm hết hạn, session trở nên không hợp lệ.

API `SessionRepository.findById(id)` có trách nhiệm không trả về session đã hết hạn. Mã ứng dụng không nên chỉ kiểm tra xem key hoặc hàng dữ liệu còn tồn tại trong kho rồi kết luận phiên vẫn hợp lệ.

Giá trị timeout mặc định thường là 30 phút ở nhiều cấu hình Spring Session, nhưng ứng dụng cần đặt timeout theo yêu cầu nghiệp vụ và xác minh giá trị của phiên bản đang dùng. Session có timeout âm hoặc không giới hạn có thể tạo dữ liệu tồn tại rất lâu tùy repository; không nên dùng thời hạn vô hạn nếu không có chính sách thu hồi và dọn dữ liệu riêng.

## 3. Thời hạn logic khác với thời điểm xóa dữ liệu

Thời hạn logic trả lời câu hỏi: “Request này có được dùng session nữa không?”. Cleanup trả lời câu hỏi: “Khi nào kho lưu trữ thu hồi bản ghi cũ để giải phóng tài nguyên?”.

| Tình huống | Session còn hợp lệ? | Dữ liệu vật lý đã bị xóa? |
|---|---|---|
| Chưa đến thời điểm hết hạn | Có | Không |
| Đã hết hạn, cleanup chưa chạy | Không | Có thể chưa |
| Cleanup đã xóa bản ghi | Không | Có |
| Client vẫn gửi cookie hoặc ID cũ | Không nếu repository xác định đã hết hạn | Cookie có thể vẫn còn ở client |

Cookie còn tồn tại không làm session sống lại. Tương tự, việc bản ghi còn nằm trong kho để phục vụ xử lý event không có nghĩa `findById` phải trả lại session đã hết hạn.

Đây là nguyên tắc quan trọng khi thiết kế logout, giới hạn phiên đồng thời và kiểm thử bảo mật: trạng thái xác thực phải dựa trên repository và chính sách timeout, không dựa vào việc dữ liệu vật lý đã bị xóa hay chưa.

## 4. So sánh cách quản lý expiration giữa các repository

Các repository phổ biến có cách thực hiện khác nhau:

| Repository | Thời hạn và cách dọn | Ghi dữ liệu |
|---|---|---|
| `MapSessionRepository` | Kiểm tra thời hạn khi truy cập; không tự cung cấp hạ tầng cleanup tổng quát | Lưu đối tượng trong Map; việc lưu phụ thuộc thao tác repository |
| `RedisSessionRepository` | Dùng TTL của Redis cho session key; không có principal index và cleanup cron của indexed repository | Hỗ trợ `SaveMode` và `FlushMode` |
| `RedisIndexedSessionRepository` | TTL, expiration key, keyspace notifications và cleanup task định kỳ | Hỗ trợ `SaveMode` và `FlushMode` |
| `JdbcIndexedSessionRepository` | Lưu thời điểm hết hạn trong database; cleanup task xóa các hàng hết hạn | Hỗ trợ `SaveMode` và `FlushMode` |
| `MongoIndexedSessionRepository` | Lưu thời điểm hết hạn và chạy cleanup định kỳ | Dùng converter và thao tác repository; không nên giả định có cùng mọi tùy chọn SaveMode/FlushMode như Redis/JDBC |
| `HazelcastIndexedSessionRepository` | Dùng TTL trên entry của Hazelcast `IMap` | Hỗ trợ `SaveMode` và `FlushMode` |

Bảng này là định hướng kiến trúc. API, thuộc tính cấu hình và chi tiết nội bộ thay đổi theo phiên bản Spring Session, Spring Boot và module dữ liệu. Cần kiểm tra Javadoc/configuration metadata của dependency thực tế trước khi áp dụng.

## 5. MapSessionRepository: thời hạn không đồng nghĩa cleanup tự động

`MapSessionRepository` lưu session trong một `Map` mà ứng dụng cung cấp, thường là `ConcurrentHashMap`. Nó hữu ích cho kiểm thử, ví dụ đơn giản hoặc trường hợp ứng dụng tự cung cấp một Map phân tán phù hợp.

Điểm cần chú ý là `@EnableSpringHttpSession` không tự tạo hạ tầng expiration chung cho một repository tùy ý. Với Map repository, ứng dụng cần tự xác định cách dọn các session hết hạn nếu muốn tránh các entry cũ tiếp tục chiếm bộ nhớ.

Ví dụ tạo repository trong bộ nhớ:

```java
@Bean
MapSessionRepository sessionRepository() {
    return new MapSessionRepository(new ConcurrentHashMap<>());
}
```

Một tác vụ cleanup tự viết phải:
- Xác định thời điểm hết hạn dựa trên metadata session.
- Chỉ xóa session nếu nó vẫn hết hạn tại thời điểm kiểm tra.
- Tránh xóa nhầm session vừa được request khác gia hạn.
- Có giới hạn số entry xử lý mỗi lượt để không chặn request.
- Được kiểm thử khi nhiều request cùng cập nhật session.

Map trong bộ nhớ của từng JVM không tự chia sẻ dữ liệu giữa các instance. Dùng `ConcurrentHashMap` trên mỗi máy sẽ tạo các kho session độc lập; muốn chia sẻ phải dùng một implementation Map phân tán và kiểm tra kỹ TTL, consistency cùng event behavior của nó.

## 6. Redis: TTL và expiration notification

Redis repository tận dụng TTL của key. Khi session được lưu, Spring Session đặt thời hạn dựa trên `maxInactiveInterval`. Redis chịu trách nhiệm loại bỏ key khi hết TTL.

Với `RedisIndexedSessionRepository`, cơ chế expiration phức tạp hơn vì repository cần giữ dữ liệu đủ lâu để xử lý sự kiện hết hạn và duy trì chỉ mục. Repository sử dụng một expiration key riêng và có thể giữ hash session thêm một khoảng thời gian sau khi session hết hạn logic. Khi expiration key hết hạn hoặc bị xóa, keyspace notification cho phép repository phát sự kiện kết thúc phiên.

Redis không bảo đảm mọi expired notification luôn được phát đúng tại thời điểm TTL về 0. Vì vậy, indexed repository còn theo dõi các mốc expiration theo bucket và chạy cleanup task để truy cập các key đã đến hạn. Truy cập key giúp Redis tự kiểm tra TTL và xóa khi thực sự hết hạn; repository tránh tự xóa session hash theo mapping có thể đã cũ.

Với Redis repository không indexed, không nên giả định có principal index, cleanup cron hoặc cùng bộ sự kiện như indexed repository. Chọn implementation theo chức năng cần dùng, không chỉ vì cả hai đều lưu session trong Redis.

## 7. JDBC: expiration timestamp và cleanup query

`JdbcIndexedSessionRepository` lưu session và thuộc tính trong các bảng quan hệ. Bản ghi session có thời điểm hết hạn hoặc thông tin đủ để xác định thời điểm đó. Khi tìm session theo ID, repository không trả về phiên đã hết hạn.

Một tác vụ cleanup định kỳ thực hiện truy vấn xóa các session hết hạn và các thuộc tính liên quan. Trong cấu hình phổ biến, cleanup cron mặc định chạy mỗi phút; ứng dụng có thể thay đổi lịch qua `cleanupCron` hoặc thuộc tính Spring Boot tương ứng.

Ví dụ cấu hình Boot:

```yaml
spring:
  session:
    timeout: 30m
    jdbc:
      cleanup-cron: "0 * * * * *"
      flush-mode: on-save
      save-mode: on-set-attribute
```

Cleanup query tạo tải đọc/ghi trên database. Nếu có nhiều session hết hạn cùng lúc, cần theo dõi thời gian chạy query, index trên cột thời hạn và lock contention. Dùng index đúng với câu truy vấn cleanup để tránh quét toàn bảng khi dữ liệu lớn.

Không nên nhầm cleanup cron với timeout. Tăng chu kỳ cleanup chỉ làm hàng hết hạn tồn tại vật lý lâu hơn; nó không kéo dài thời gian hợp lệ của session nếu repository kiểm tra expiration đúng.

## 8. MongoDB: thời điểm hết hạn và tác vụ cleanup

`MongoIndexedSessionRepository` lưu session trong collection MongoDB và hỗ trợ chỉ mục để tìm session theo principal. Repository lưu thông tin hết hạn và có trách nhiệm dọn các session hết hạn; tài liệu API của các phiên bản phổ biến mô tả cleanup chạy mỗi phút.

Cơ chế cleanup của repository cần được phân biệt với TTL index do ứng dụng tự tạo. Không tự thêm TTL index hoặc xóa document theo cách riêng nếu chưa hiểu cấu trúc dữ liệu và event behavior của phiên bản đang dùng. TTL index của MongoDB có thể xóa document độc lập với logic phát event của Spring Session, làm cho ứng dụng mất cơ hội xử lý session-destroyed event nếu repository cần đọc document trước khi phát sự kiện.

Spring Session MongoDB hỗ trợ converter để chuyển đổi thuộc tính session, chẳng hạn converter dựa trên Java Serialization hoặc Jackson. Thay đổi converter cần tương thích với các session đang tồn tại. Việc cleanup document hết hạn không giải quyết lỗi deserialize session cũ.

Khi chọn MongoDB, hãy kiểm tra phiên bản module `spring-session-data-mongodb`, chính sách cleanup, index collection và cách event được phát trong đúng phiên bản.

## 9. Hazelcast: TTL trên entry của IMap

`HazelcastIndexedSessionRepository` lưu session trong distributed `IMap`. Hazelcast hỗ trợ TTL cho entry; repository cập nhật entry cùng thời hạn phù hợp khi session được lưu. Entry đã vượt thời hạn sẽ được Hazelcast loại bỏ theo cơ chế của map.

Điều này khác với JDBC, nơi cleanup là một truy vấn database định kỳ, và khác với Redis indexed, nơi keyspace notifications cùng expiration bucket hỗ trợ event.

Nếu dùng `MapStore` để persistence cho Hazelcast map, cần kiểm tra hành vi reload. Việc tải lại entry từ MapStore có thể kích hoạt listener tạo session lần nữa; nếu TTL mặc định của map được áp dụng khi reload, session có thể mất TTL gốc. Đây là điểm cần kiểm thử trước khi dùng MapStore cho dữ liệu session.

Hazelcast repository cũng có `SaveMode` và `FlushMode`. Vì vậy, ngoài TTL của IMap, cần chọn cách theo dõi thay đổi và ghi dữ liệu phù hợp với mức tải của cụm.

## 10. SaveMode: chọn thuộc tính nào được ghi?

`SaveMode` điều khiển cách repository theo dõi thuộc tính session cần lưu. Các chế độ thường gặp:

| Chế độ | Hành vi | Tác động |
|---|---|---|
| `ON_SET_ATTRIBUTE` | Chỉ lưu thuộc tính được thay đổi qua `setAttribute` hoặc thao tác thay đổi được repository nhận biết | Ít ghi hơn, giảm nguy cơ ghi đè thuộc tính không liên quan |
| `ON_GET_ATTRIBUTE` | Như `ON_SET_ATTRIBUTE` và thêm thuộc tính đã được đọc qua `getAttribute` | Hữu ích khi lấy object rồi sửa trực tiếp, nhưng có thể ghi lại thuộc tính chỉ đọc |
| `ALWAYS` | Lưu tất cả thuộc tính của session khi lưu session | Dễ bảo đảm mọi thuộc tính được ghi, nhưng tăng I/O và nguy cơ ghi đè khi request đồng thời |

Mặc định phổ biến của Redis, JDBC và Hazelcast là `ON_SET_ATTRIBUTE`. Chế độ này phù hợp với cách cập nhật session rõ ràng:

```java
CartState cart = (CartState) session.getAttribute("cart");
CartState updated = cart.add(productId);
session.setAttribute("cart", updated);
```

Nếu ứng dụng lấy một object mutable rồi thay đổi trực tiếp mà không gọi `setAttribute`:

```java
CartState cart = (CartState) session.getAttribute("cart");
cart.add(productId); // Không gọi session.setAttribute("cart", cart)
```

thì `ON_SET_ATTRIBUTE` có thể không nhận biết thuộc tính cần ghi. Có thể dùng object immutable và gọi lại `setAttribute`, hoặc cân nhắc `ON_GET_ATTRIBUTE` nếu mô hình code phụ thuộc vào mutable object. `ALWAYS` là lựa chọn tốn ghi hơn và không nên dùng như cách chữa mọi vấn đề serialization.

## 11. FlushMode: ghi khi lưu hay ghi ngay?

`FlushMode` điều khiển thời điểm thay đổi session được đẩy xuống kho lưu trữ:

| Chế độ | Hành vi | Ưu điểm | Đánh đổi |
|---|---|---|---|
| `ON_SAVE` | Ghi khi `SessionRepository.save(session)` được gọi; trong web request thường gần lúc response được commit | Gom thay đổi và giảm số lần truy cập store | Request khác có thể chưa thấy thay đổi cho đến lúc save |
| `IMMEDIATE` | Ghi thay đổi xuống store sớm nhất có thể, ví dụ khi tạo session hoặc set thuộc tính | Dữ liệu được chia sẻ sớm hơn giữa các request | Tăng số lần ghi và chi phí I/O; có thể ghi nhiều trạng thái trung gian |

`ON_SAVE` là mặc định phổ biến của Redis, JDBC và Hazelcast. Với request thông thường, repository filter lưu session ở cuối vòng đời request trước khi response được commit.

`IMMEDIATE` có thể hữu ích khi một luồng cần thấy thay đổi sớm trong kho session, nhưng nó không biến nhiều thao tác set attribute thành một transaction nghiệp vụ nguyên tử. Một request có thể ghi một phần thay đổi rồi gặp lỗi ở bước tiếp theo.

## 12. SaveMode và FlushMode phối hợp với nhau

Hai chế độ giải quyết hai câu hỏi khác nhau:

- `SaveMode` trả lời: thuộc tính nào được xem là cần lưu?
- `FlushMode` trả lời: khi nào các thay đổi đó được ghi xuống store?

Ví dụ, `ON_SET_ATTRIBUTE` kết hợp `ON_SAVE` có nghĩa repository theo dõi thuộc tính được thay đổi tường minh và ghi các thay đổi đó khi session được save.

`ALWAYS` kết hợp `IMMEDIATE` có thể tạo nhiều thao tác ghi hơn đáng kể: mọi thuộc tính có thể được lưu lại, và các thay đổi được đẩy xuống store sớm. Cấu hình này có thể làm tăng tải Redis/database và tăng nguy cơ request song song ghi đè dữ liệu mà request khác vừa cập nhật.

Một lựa chọn thực tế thường là bắt đầu với mặc định, sau đó chỉ thay đổi khi có trường hợp cụ thể đã được tái hiện bằng test và đo lường.

## 13. Chính sách ghi và request đồng thời

Hai request có thể cùng đọc một session ở hai instance khác nhau. Mỗi request có một bản session trong bộ nhớ riêng. Khi cả hai ghi về kho, thứ tự hoàn tất có thể khác thứ tự bắt đầu.

Ví dụ:
1. Request A đọc thuộc tính `cart` với hai sản phẩm.
2. Request B cũng đọc cùng giá trị.
3. A thêm sản phẩm X và ghi session.
4. B thêm sản phẩm Y dựa trên bản cũ rồi ghi session.
5. Nếu B ghi sau và lưu toàn bộ thuộc tính cũ, cập nhật X có thể bị mất.

`ON_SET_ATTRIBUTE` giúp giảm ghi đè những thuộc tính không thay đổi trong request. `ALWAYS` có thể tăng nguy cơ ghi lại dữ liệu cũ. Tuy nhiên, ngay cả khi chỉ lưu delta, hai request cùng sửa một thuộc tính vẫn có thể xung đột.

`SaveMode` và `FlushMode` không phải distributed lock, optimistic locking hay transaction serializable. Với số dư, tồn kho, trạng thái thanh toán hoặc giỏ hàng có nhiều cập nhật đồng thời, hãy lưu dữ liệu trong repository nghiệp vụ và dùng transaction/locking phù hợp. Session chỉ nên giữ ngữ cảnh tạm thời hoặc ID tham chiếu.

## 14. Cấu hình SaveMode, FlushMode và cleanup

Với Redis indexed, cấu hình annotation có thể chỉ định cả ba:

```java
@Configuration(proxyBeanMethods = false)
@EnableRedisIndexedHttpSession(
        maxInactiveIntervalInSeconds = 1800,
        cleanupCron = "0 * * * * *",
        saveMode = SaveMode.ON_SET_ATTRIBUTE,
        flushMode = FlushMode.ON_SAVE
)
class RedisSessionConfiguration {
}
```

Với JDBC:

```java
@Configuration(proxyBeanMethods = false)
@EnableJdbcHttpSession(
        maxInactiveIntervalInSeconds = 1800,
        cleanupCron = "0 * * * * *",
        saveMode = SaveMode.ON_SET_ATTRIBUTE,
        flushMode = FlushMode.ON_SAVE
)
class JdbcSessionConfiguration {
}
```

Nếu dùng Spring Boot auto-configuration, các thuộc tính thường có dạng:

```yaml
spring:
  session:
    jdbc:
      cleanup-cron: "0 * * * * *"
      save-mode: on-set-attribute
      flush-mode: on-save
```

Với Redis, prefix và thuộc tính repository phụ thuộc phiên bản Spring Boot; các dòng Boot mới có thể dùng `spring.session.data.redis.*`, trong khi các dòng trước đó dùng prefix khác. Hãy kiểm tra configuration metadata của phiên bản đang chạy. `cleanup-cron` chỉ áp dụng cho Redis indexed repository ở các phiên bản Boot mô tả rõ điều kiện đó.

Không phải repository nào cũng cung cấp cùng một tập tùy chọn. Mongo converter và cleanup có cấu hình riêng; Map repository yêu cầu ứng dụng tự quản lý expiration; không nên áp các thuộc tính Redis/JDBC cho chúng.

## 15. Lịch cleanup trong hệ thống nhiều instance

Với Redis indexed, JDBC và Mongo repository, cleanup task thường được đăng ký trong ApplicationContext của ứng dụng. Khi triển khai nhiều replica, mỗi instance có thể có lịch cleanup riêng. Không mặc định rằng chỉ một node trong cụm thực hiện cleanup.

Tác động có thể gồm:
- Nhiều node cùng quét các session hết hạn.
- Tăng query hoặc Redis command khi scale out.
- Tác vụ cleanup cạnh tranh tài nguyên với request thông thường.
- Event hoặc callback có thể được phát theo phạm vi repository và node, không mặc nhiên là một thông báo broadcast đúng một lần.

Repository cần xử lý an toàn khi nhiều node cùng quan sát một session hết hạn. Listener nghiệp vụ vẫn nên idempotent vì event có thể đến trễ hoặc được nhiều subscriber nhận tùy cơ chế store.

Nếu một side effect phải được thực hiện đúng một lần, chẳng hạn phát hóa đơn hoặc gửi thông báo tài chính, không dùng cleanup event của session làm cơ chế đảm bảo. Dùng outbox, message broker, unique key hoặc idempotency key trong nghiệp vụ.

## 16. Chọn chính sách theo loại ứng dụng

| Nhu cầu | Hướng lựa chọn ban đầu |
|---|---|
| Ứng dụng nhỏ, kiểm thử hoặc demo | `MapSessionRepository` và cleanup tự quản lý nếu cần |
| Nhiều instance, truy cập theo session ID, muốn TTL tự động | Redis repository cơ bản |
| Cần tìm session theo principal và xử lý event hết hạn | Redis indexed, cấu hình keyspace notifications và cleanup |
| Đã vận hành relational database tốt, cần SQL/migration | JDBC indexed và cleanup query có index phù hợp |
| Hạ tầng dùng MongoDB và cần repository indexed | Mongo indexed, converter và cleanup được kiểm thử |
| Đã có Hazelcast cluster và cần session trong IMap | Hazelcast indexed với TTL entry và chính sách MapStore rõ ràng |

Đừng chọn repository chỉ dựa trên việc nó có cleanup tự động. Hãy xét thêm:
- Số lượng session và kích thước thuộc tính.
- Tần suất đọc/ghi.
- Khả năng tìm session theo principal.
- Yêu cầu session events.
- Tải cleanup lên datastore.
- Tính sẵn sàng, backup và failover.
- Khả năng tương thích serializer khi rolling deployment.
- Mức độ cần cập nhật session ngay trong request.

## 17. Kiểm thử thời hạn, cleanup và chính sách ghi

Một bộ kiểm thử tốt cần tách ba nhóm.

**Kiểm thử thời hạn**
1. Tạo session với timeout ngắn.
2. Đọc lại trước thời điểm hết hạn và xác nhận còn hợp lệ.
3. Không truy cập cho đến sau timeout.
4. Gọi `findById` và xác nhận repository không trả session đã hết hạn.
5. Xác nhận cookie còn ở client không làm session được khôi phục.

**Kiểm thử cleanup**
1. Tạo nhiều session với thời hạn khác nhau.
2. Chờ cleanup task hoặc TTL của datastore hoạt động.
3. Kiểm tra bản ghi hết hạn được dọn theo cơ chế repository.
4. Xác nhận session chưa hết hạn không bị xóa.
5. Với Redis indexed, kiểm tra keyspace notifications và event.
6. Với JDBC/Mongo, kiểm tra query cleanup và index phù hợp.
7. Với Map, xác nhận tác vụ cleanup do ứng dụng tự quản lý thực sự chạy.

**Kiểm thử chính sách ghi**
1. Cập nhật thuộc tính bằng `setAttribute` và xác nhận dữ liệu được lưu.
2. Đọc object mutable rồi thay đổi tại chỗ; kiểm tra khác biệt giữa `ON_SET_ATTRIBUTE` và `ON_GET_ATTRIBUTE`.
3. So sánh số lần ghi giữa `ON_SAVE` và `IMMEDIATE` bằng metric hoặc spy phù hợp.
4. Gửi hai request đồng thời cập nhật hai thuộc tính khác nhau.
5. Gửi hai request đồng thời cập nhật cùng thuộc tính và xác nhận ứng dụng có chính sách xung đột rõ ràng.
6. Chạy test trên repository thật hoặc Testcontainers; mock không mô phỏng đầy đủ TTL, transaction và cleanup của datastore.

Không dùng `Thread.sleep` cố định sát ranh giới expiration nếu có thể dùng Awaitility hoặc polling có timeout. Test phải báo rõ khi cleanup/event không xuất hiện trong khoảng thời gian mong đợi.

## 18. Quan sát và xử lý sự cố

Các chỉ số nên theo dõi:
- Số session đang hoạt động và kích thước trung bình.
- Số session hết hạn theo thời gian.
- Thời gian chạy cleanup và số bản ghi bị xóa.
- Redis command rate, TTL key và độ trễ keyspace notification.
- JDBC query latency, số hàng cleanup, lock wait và connection pool.
- Mongo cleanup duration, query plan và index usage.
- Hazelcast map size, eviction/expiration count và MapStore reload.
- Số lỗi serialize/deserialize khi đọc session.
- Số lỗi listener và thời gian xử lý event.

Khi người dùng bị đăng xuất sớm, kiểm tra timeout, thời điểm truy cập cuối, cấu hình session của các instance và clock synchronization. Khi dữ liệu cũ tồn tại lâu, kiểm tra cleanup task, keyspace notifications hoặc query cleanup. Khi thuộc tính bị mất, kiểm tra SaveMode, FlushMode và các request đồng thời.

Không tăng tần suất cleanup để chữa lỗi timeout; không chuyển sang `ALWAYS` chỉ để chữa lỗi mutable object mà chưa hiểu tác động ghi đè; không chuyển sang `IMMEDIATE` chỉ vì muốn request khác thấy dữ liệu sớm hơn mà không đánh giá chi phí I/O và tính nhất quán.

## 19. Quy trình lựa chọn an toàn

Trước khi thay repository hoặc chính sách ghi:

1. Xác định loại repository và phiên bản Spring Session đang chạy.
2. Ghi rõ timeout nghiệp vụ và thời điểm session phải bị từ chối.
3. Xác định yêu cầu dọn vật lý và event; không đánh đồng chúng với timeout.
4. Chọn SaveMode theo cách code cập nhật thuộc tính.
5. Chọn FlushMode theo yêu cầu độ trễ và chi phí ghi.
6. Kiểm thử request đồng thời, đặc biệt khi cùng sửa một thuộc tính.
7. Kiểm thử cleanup trên datastore thật.
8. Đồng bộ cấu hình giữa mọi instance.
9. Theo dõi metric sau triển khai và có phương án quay lại cấu hình cũ.

## 20. Kết luận lựa chọn

Thời hạn xác định khi session không còn hợp lệ; cleanup xác định khi dữ liệu hết hạn được thu hồi khỏi kho; SaveMode và FlushMode xác định phạm vi và thời điểm ghi thay đổi. Redis, JDBC, MongoDB, Hazelcast và Map triển khai các lớp này theo những cơ chế khác nhau, vì vậy không có một cấu hình cron hay chính sách ghi áp dụng giống nhau cho mọi repository.

Hãy bắt đầu từ mặc định `ON_SET_ATTRIBUTE` kết hợp `ON_SAVE` khi repository hỗ trợ, đặt timeout rõ ràng và dùng cleanup theo cơ chế store. Chỉ thay đổi chính sách sau khi có test tái hiện vấn đề và metric chứng minh lợi ích. Với dữ liệu nghiệp vụ cần tính nhất quán cao, dùng transaction và cơ chế đồng bộ chuyên biệt; session repository không phải hệ thống khóa phân tán hay cơ sở dữ liệu nghiệp vụ.


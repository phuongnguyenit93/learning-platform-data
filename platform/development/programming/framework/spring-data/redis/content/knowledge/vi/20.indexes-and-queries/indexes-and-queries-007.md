# Ảnh hưởng của cập nhật và xóa thực thể đến chỉ mục trong Spring Data Redis

## 1. Bài toán: dữ liệu đổi nhưng kết quả truy vấn phải đổi theo

Trong Spring Data Redis Repository, một thực thể được lưu theo **ID** và có thể được tìm bằng các thuộc tính đã khai báo chỉ mục thứ cấp (*secondary index*). Ví dụ, ứng dụng quản lý giao hàng lưu bản ghi có các thuộc tính `id`, `status`, `warehouse` và `description`. Người dùng muốn truy vấn những đơn đang chờ xử lý tại từng kho.

Giả sử thực thể có trạng thái ban đầu:

```text
id          = delivery-101
status      = PENDING
warehouse   = HCM
description = Chờ đóng gói
```

Khi cập nhật trạng thái thành `SHIPPED`, các yêu cầu sau phải được đáp ứng:

- `findById("delivery-101")` trả về thực thể có trạng thái mới.
- `findByStatus("PENDING")` không còn xem thực thể đó là thành viên của nhóm cũ.
- `findByStatus("SHIPPED")` tìm thấy thực thể trong nhóm mới.
- Khi xóa thực thể, các chỉ mục dùng để tìm thực thể đó cũng cần được cập nhật.

Nếu chỉ thay đổi dữ liệu trong Redis Hash mà bỏ qua chỉ mục, ứng dụng có thể có **dữ liệu chính đúng nhưng kết quả truy vấn sai**. Đây là lý do cần hiểu vòng đời cập nhật và xóa qua Spring Data Redis Repository.

Bài học này giải thích cách chỉ mục hoạt động, điều gì diễn ra khi gọi `save` và `delete`, vì sao TTL có thể làm chỉ mục tồn đọng, và cách tổ chức luồng ghi/xóa an toàn.

## 2. Chỉ mục thứ cấp trong Redis Repository là gì?

Redis là kho dữ liệu key–value. Khi biết chính xác khóa của thực thể, việc đọc theo ID khá trực tiếp. Tuy nhiên, câu hỏi “tất cả giao hàng có `status = PENDING`” không thể được giải quyết chỉ từ ID.

Spring Data Redis Repository hỗ trợ một số truy vấn theo thuộc tính thông qua chỉ mục thứ cấp. Ta đánh dấu thuộc tính bằng `@Indexed`; Spring Data sẽ quản lý cấu trúc Redis bổ sung để liên kết **giá trị thuộc tính** với **ID của các thực thể tương ứng**.

Mô hình khái niệm:

```text
Khóa chính:
  demo:delivery:delivery-101
    id          -> delivery-101
    status      -> PENDING
    warehouse   -> HCM
    description -> Chờ đóng gói

Chỉ mục theo status:
  status=PENDING -> {delivery-101, delivery-102, ...}
  status=SHIPPED -> {delivery-203, ...}

Chỉ mục theo warehouse:
  warehouse=HCM -> {delivery-101, delivery-203, ...}
```

Các cấu trúc chỉ mục thường dựa trên Redis Set và các khóa nội bộ để Spring Data theo dõi thông tin cần dọn khi cập nhật hoặc xóa. Sơ đồ trên diễn tả **quan hệ dữ liệu**, không cam kết chính xác tên khóa hay nội dung field nội bộ của mọi phiên bản Spring Data Redis.

### Khóa chính khác với chỉ mục thứ cấp

| Thành phần | Mục đích | Ai quản lý? |
|---|---|---|
| Redis Hash của entity | Lưu dữ liệu thuộc tính của một thực thể | Redis Repository thông qua cơ chế mapping |
| ID và keyspace | Định danh thực thể, phục vụ `findById` | Entity với `@Id` và `@RedisHash` |
| Secondary index | Tìm thực thể theo một thuộc tính khác ID | Spring Data Redis theo `@Indexed` và cấu hình mapping |
| Metadata/chỉ mục phụ trợ | Theo dõi các key thuộc keyspace và thông tin hỗ trợ dọn chỉ mục | Hạ tầng Redis Repository |

Vì chỉ mục được lưu thành dữ liệu Redis bổ sung, thao tác thêm, sửa hoặc xóa thực thể có thể liên quan **nhiều key và nhiều lệnh Redis**, không đơn giản là một lệnh `HSET` hoặc `DEL` duy nhất.

## 3. Khai báo thực thể và repository để quan sát vòng đời chỉ mục

Ví dụ Spring Boot có dependency:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
```

Cấu hình Redis local:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Các giá trị này chỉ dùng cho môi trường học tập. Trên môi trường thật, cần cấu hình đúng xác thực, TLS, endpoint và Redis topology.

### 3.1. Định nghĩa entity

**`DeliverySnapshot.java`**

```java
package com.example.delivery.redis;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("demo:delivery")
public class DeliverySnapshot {

    @Id
    private String id;

    @Indexed
    private String status;

    @Indexed
    private String warehouse;

    private String description;

    public DeliverySnapshot() {
    }

    public DeliverySnapshot(
            String id,
            String status,
            String warehouse,
            String description
    ) {
        this.id = id;
        this.status = status;
        this.warehouse = warehouse;
        this.description = description;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getWarehouse() {
        return warehouse;
    }

    public void setWarehouse(String warehouse) {
        this.warehouse = warehouse;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }
}
```

`@RedisHash` chỉ định keyspace, `@Id` xác định ID còn `@Indexed` đánh dấu những thuộc tính cần dùng trong truy vấn theo giá trị. `description` không có `@Indexed` vì ví dụ không cần tìm các bản ghi theo nội dung mô tả.

### 3.2. Định nghĩa repository

**`DeliveryRepository.java`**

```java
package com.example.delivery.redis;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface DeliveryRepository
        extends CrudRepository<DeliverySnapshot, String> {

    List<DeliverySnapshot> findByStatus(String status);

    List<DeliverySnapshot> findByWarehouse(String warehouse);
}
```

Spring Data Redis sẽ triển khai repository theo cơ chế của mình khi cấu hình quét repository và Redis connection hợp lệ. Các phương thức `findByStatus` và `findByWarehouse` là truy vấn theo thuộc tính đã lập chỉ mục. Không nên mặc định mọi toán tử truy vấn của JPA đều được Redis Repository hỗ trợ.

## 4. Khi tạo thực thể mới, chỉ mục được bổ sung như thế nào?

Tạo một thực thể bằng repository:

```java
DeliverySnapshot delivery = new DeliverySnapshot(
        "delivery-101",
        "PENDING",
        "HCM",
        "Chờ đóng gói"
);

repository.save(delivery);
```

Về mặt logic, thao tác lưu cần thực hiện các việc liên quan:

1. Ánh xạ các thuộc tính của `DeliverySnapshot` sang Redis Hash tương ứng với ID.
2. Ghi dữ liệu để `findById("delivery-101")` có thể đọc lại.
3. Đăng ký ID vào các cấu trúc hỗ trợ quản lý entity trong keyspace.
4. Ghi các quan hệ chỉ mục cần thiết: `status=PENDING` và `warehouse=HCM`.
5. Lưu hoặc cập nhật thông tin phụ trợ phục vụ các lần thay đổi và xóa tiếp theo.

Sau khi lưu thành công, truy vấn:

```java
List<DeliverySnapshot> pending =
        repository.findByStatus("PENDING");

List<DeliverySnapshot> hcm =
        repository.findByWarehouse("HCM");
```

có thể trả về `delivery-101` qua cả hai nhóm nếu các dữ liệu và chỉ mục liên quan đã được tạo đúng.

**Không nên hiểu `save` là một lệnh Redis đơn lẻ.** Việc ánh xạ và cập nhật index là công việc của tầng repository, và các thao tác liên quan nhiều key không tự động có tính nguyên tử như một transaction cơ sở dữ liệu quan hệ.

## 5. Khi cập nhật thuộc tính đã lập chỉ mục

Đây là trường hợp quan trọng nhất: thuộc tính mang `@Indexed` đổi giá trị.

Ví dụ chuyển giao hàng từ `PENDING` sang `SHIPPED`:

```java
DeliverySnapshot delivery = repository.findById("delivery-101")
        .orElseThrow(() ->
                new IllegalArgumentException("Không tìm thấy giao hàng")
        );

delivery.setStatus("SHIPPED");
repository.save(delivery);
```

Sau lời gọi `save`, mô hình chỉ mục cần phản ánh:

| Thành phần | Trước cập nhật | Sau cập nhật |
|---|---|---|
| Hash `delivery-101` | `status=PENDING` | `status=SHIPPED` |
| Nhóm `status=PENDING` | Có `delivery-101` | Không còn `delivery-101` |
| Nhóm `status=SHIPPED` | Chưa có `delivery-101` | Có `delivery-101` |
| Nhóm `warehouse=HCM` | Có `delivery-101` | Vẫn có `delivery-101` |

Trong luồng lưu entity qua Spring Data Redis Repository, hạ tầng repository quản lý việc **gỡ quan hệ chỉ mục cũ và tạo quan hệ chỉ mục mới** tương ứng với trạng thái hiện tại của thực thể. Cơ chế này dựa vào mapping/index metadata của Spring Data Redis; ứng dụng không cần tự gọi `SREM` và `SADD` cho mỗi thay đổi thuộc tính.

### Cập nhật đồng thời nhiều thuộc tính đã lập chỉ mục

```java
DeliverySnapshot delivery = repository.findById("delivery-101")
        .orElseThrow();

delivery.setStatus("SHIPPED");
delivery.setWarehouse("HN");
repository.save(delivery);
```

Trạng thái mong muốn:

```text
status=PENDING  : không còn delivery-101
status=SHIPPED  : có delivery-101
warehouse=HCM  : không còn delivery-101
warehouse=HN   : có delivery-101
```

Về mặt mô hình, mỗi thuộc tính có chỉ mục chịu tác động độc lập. Nếu một đối tượng được cập nhật nhiều field trong một lần `save`, repository cần đồng bộ tất cả chỉ mục tương ứng.

### Cập nhật lại đúng giá trị cũ

Nếu `status` vẫn là `PENDING`, kết quả phân nhóm logic không đổi. Tuy nhiên, không nên dựa vào giả định rằng Spring Data Redis sẽ bỏ qua mọi thao tác ghi mạng khi `save` nhận một entity không thay đổi; cơ chế persist và hiệu năng cụ thể phụ thuộc cách triển khai và phiên bản.

## 6. Khi chỉ cập nhật thuộc tính không lập chỉ mục

Đổi `description` mà vẫn giữ `status` và `warehouse`:

```java
DeliverySnapshot delivery = repository.findById("delivery-101")
        .orElseThrow();

delivery.setDescription("Đã đóng gói, chờ bàn giao");
repository.save(delivery);
```

Vì `description` không được đánh dấu `@Indexed`, hệ thống không cần tạo một nhóm tra cứu theo chuỗi mô tả đó. Về mặt kết quả truy vấn, tư cách thành viên trong nhóm `status` và `warehouse` vẫn phải được giữ nguyên.

Điều này không đồng nghĩa với việc `save` chỉ sửa duy nhất field `description` bằng một lệnh `HSET`. Repository lưu entity theo cơ chế ánh xạ của Spring Data Redis; muốn thao tác trực tiếp lên một field với chi phí tối thiểu thì cần lựa chọn API phù hợp, đồng thời hiểu tác động tới index nếu field đó được lập chỉ mục.

### Thuộc tính chuyển thành null hoặc bị loại bỏ

Giả sử một thuộc tính có chỉ mục trước đây có giá trị `warehouse=HCM`, sau đó đổi thành `null`:

```java
delivery.setWarehouse(null);
repository.save(delivery);
```

Quan hệ trong nhóm `warehouse=HCM` không nên còn trỏ tới thực thể. Khi field không còn giá trị được lập chỉ mục, không có lý do để thực thể tiếp tục thuộc nhóm cũ. Việc null được ánh xạ ra Redis như thế nào phụ thuộc converter; điểm cần quan tâm ở đây là **cập nhật thông qua repository để các index liên quan được quản lý đồng bộ**.

Với thuộc tính tập hợp hoặc thuộc tính lồng nhau có thể lập chỉ mục, việc thêm, bớt hoặc thay phần tử cũng có thể làm thay đổi nhiều quan hệ trong chỉ mục. Nên kiểm tra giới hạn hỗ trợ của loại thuộc tính và truy vấn cụ thể trong phiên bản Spring Data Redis đang dùng.

## 7. Khi xóa thực thể qua CrudRepository

Xóa đúng một thực thể theo ID:

```java
repository.deleteById("delivery-101");
```

Hoặc đã có đối tượng:

```java
repository.delete(delivery);
```

Đối với thực thể có chỉ mục, xóa hợp lệ phải xử lý cả dữ liệu chính lẫn các mối liên hệ trong secondary index.

### Trước và sau khi xóa

Giả sử đối tượng có trạng thái:

```text
id=delivery-101
status=SHIPPED
warehouse=HN
```

Kỳ vọng sau khi xóa bằng repository:

| Thành phần | Trước xóa | Sau xóa |
|---|---|---|
| Hash của `delivery-101` | Tồn tại | Không còn |
| Tra cứu `findById` | Trả về entity | Trả về `Optional.empty()` |
| Index `status=SHIPPED` | Chứa ID | Không còn ID |
| Index `warehouse=HN` | Chứa ID | Không còn ID |
| Metadata hỗ trợ repository | Còn thông tin của thực thể | Được điều chỉnh tương ứng |

Spring Data Redis Repository sử dụng thông tin đã quản lý cho thực thể và các chỉ mục để dọn những quan hệ không còn hợp lệ. Đây là lý do **nên xóa qua repository nếu dữ liệu trước đó được tạo và lập chỉ mục bởi repository**.

### Xóa nhiều và xóa tất cả

```java
repository.deleteAll(List.of(deliveryA, deliveryB));
```

Đây là thao tác xóa một nhóm entity cụ thể. Trong khi đó:

```java
repository.deleteAll();
```

có phạm vi rộng hơn nhiều: yêu cầu xóa tất cả entity thuộc repository. Với keyspace lớn, việc dọn dữ liệu và index có thể tốn nhiều thao tác Redis. Không nên đặt `deleteAll()` sau một API công khai hoặc job tự động thiếu giới hạn và kiểm soát quyền.

**Không biến ID thành thuộc tính dùng để “đổi tên” một entity.** Nếu một bản ghi đổi ID từ `delivery-101` sang `delivery-999`, nên coi đó là quá trình tạo thực thể mới và xóa thực thể cũ theo quy trình nghiệp vụ. Chỉ đổi thuộc tính `id` trong đối tượng rồi `save` không đồng nghĩa rằng Spring Data Redis sẽ tự di chuyển key cũ cùng toàn bộ index một cách nguyên tử.

## 8. Tại sao xóa trực tiếp bằng RedisTemplate hoặc Redis CLI có thể làm chỉ mục sai?

Giả sử entity được lưu bằng repository với:

```text
ID:     delivery-101
status: PENDING
```

Sau đó một tiến trình khác xóa Redis key chính bằng lệnh:

```redis
DEL demo:delivery:delivery-101
```

Redis chỉ xóa khóa được chỉ định. Nó **không hiểu** rằng khóa đó là một entity Java có quan hệ với secondary index do Spring Data quản lý. Những khóa chỉ mục phụ trợ có thể vẫn chứa tham chiếu tới `delivery-101`.

Một lần truy vấn `findByStatus("PENDING")` sau đó có thể gặp thành viên chỉ mục không còn dữ liệu chính tương ứng. Kết quả thực tế có thể là bản ghi thiếu, truy vấn không như mong đợi hoặc thông tin index tồn đọng, tùy cơ chế đọc và trạng thái dữ liệu; không nên trông đợi repository tự sửa ngay tất cả những thay đổi thực hiện ngoài nó.

Tình huống tương tự xảy ra khi chỉnh sửa field có chỉ mục bằng lệnh thô:

```redis
HSET demo:delivery:delivery-101 status SHIPPED
```

Hash giờ chứa `SHIPPED`, nhưng index do Spring Data quản lý có thể vẫn phản ánh `PENDING`. Lệnh Redis không tự gửi thông tin tới bộ quản lý secondary index của repository để cập nhật phân nhóm.

### So sánh ba cách cập nhật

| Cách thao tác | Thay dữ liệu chính | Duy trì index repository |
|---|---|---|
| `repository.save(entity)` | Có, theo mapping của entity | Được Spring Data Redis Repository quản lý |
| `repository.deleteById(id)` | Có | Được repository quản lý trong luồng xóa |
| `redisTemplate.opsForHash().put(...)` | Có, trên field đã chọn | Không tự động đồng bộ secondary index của repository |
| `redisTemplate.delete(key)` / Redis `DEL` / `UNLINK` | Có, trên key chỉ định | Không tự động dọn metadata/index do repository quản lý |
| Redis `EXPIRE` được gọi trực tiếp | Đặt TTL lên key | Phụ thuộc cơ chế xử lý hết hạn, không tương đương thao tác repository trọn vẹn |

Vì vậy, một nguyên tắc vận hành hữu ích là: **Một namespace đã được Redis Repository quản lý nên có một cơ chế ghi/xóa thống nhất.** Nếu cần trộn thao tác thô và repository, phải chủ động thiết kế cách giữ index nhất quán; đừng mặc định hai tầng API biết mọi việc của nhau.

## 9. Thực hành: theo dõi truy vấn trước và sau cập nhật, xóa

Ví dụ sau minh họa vòng đời entity bằng API repository. Có thể đặt mã ở một runner chỉ kích hoạt trong profile học tập, tránh tạo hoặc xóa dữ liệu ngoài ý muốn khi ứng dụng chạy bình thường.

**`DeliveryIndexDemo.java`**

```java
package com.example.delivery.demo;

import com.example.delivery.redis.DeliveryRepository;
import com.example.delivery.redis.DeliverySnapshot;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("redis-index-demo")
public class DeliveryIndexDemo implements CommandLineRunner {

    private final DeliveryRepository repository;

    public DeliveryIndexDemo(DeliveryRepository repository) {
        this.repository = repository;
    }

    @Override
    public void run(String... args) {
        String id = "delivery-demo-101";

        // Dọn bản ghi thử nghiệm cũ, nếu có.
        repository.deleteById(id);

        // 1. Tạo entity với hai thuộc tính được lập chỉ mục.
        DeliverySnapshot item = new DeliverySnapshot(
                id,
                "PENDING",
                "HCM",
                "Chờ xử lý"
        );
        repository.save(item);

        System.out.println(
                "Được tìm trong PENDING: " + containsId("PENDING", id)
        );

        // 2. Thay đổi trạng thái qua repository.
        item.setStatus("SHIPPED");
        repository.save(item);

        System.out.println(
                "Còn trong PENDING: " + containsId("PENDING", id)
        );
        System.out.println(
                "Được tìm trong SHIPPED: " + containsId("SHIPPED", id)
        );

        // 3. Xóa entity qua repository.
        repository.deleteById(id);

        System.out.println(
                "Entity còn tồn tại: " + repository.existsById(id)
        );
        System.out.println(
                "Còn trong SHIPPED: " + containsId("SHIPPED", id)
        );
    }

    private boolean containsId(String status, String id) {
        return repository.findByStatus(status)
                .stream()
                .anyMatch(item -> id.equals(item.getId()));
    }
}
```

Kích hoạt runner cho môi trường thử nghiệm bằng profile `redis-index-demo` theo cách chạy Spring Boot của dự án. Redis phải có thể kết nối và repository phải được Spring đăng ký.

Nếu không có tiến trình khác thay đổi dữ liệu trong lúc thao tác, kỳ vọng về logic là:

```text
Được tìm trong PENDING: true
Còn trong PENDING: false
Được tìm trong SHIPPED: true
Entity còn tồn tại: false
Còn trong SHIPPED: false
```

Ví dụ dùng `containsId` thay vì so sánh toàn bộ `List` vì Redis trong môi trường thử nghiệm có thể đang chứa những thực thể khác cùng trạng thái.

Đây là ví dụ minh họa **hành vi cần đạt khi cập nhật và xóa qua repository**. Nếu kết quả khác mong đợi, cần xem lại chỉ mục, mapping, cấu hình repository và sự can thiệp từ tác vụ khác.

## 10. TTL và sự kiện hết hạn: chỉ mục được dọn như thế nào?

TTL đưa ra một trường hợp riêng: entity có thể biến mất vì Redis tự làm hết hạn khóa, mà ứng dụng **không hề gọi `repository.deleteById`**.

Ví dụ entity có TTL 15 phút:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash(value = "demo:temporary-delivery", timeToLive = 900)
public class TemporaryDelivery {

    @Id
    private String id;

    @Indexed
    private String status;

    public TemporaryDelivery() {
    }

    // Constructor, getter/setter có thể khai báo như ví dụ trước.
}
```

`timeToLive = 900` có đơn vị giây. Khi TTL hết hạn, Redis xóa key chính theo cơ chế expiration. Thế nhưng Redis **không tự hiểu các secondary index của Spring Data Redis**; việc dọn các quan hệ chỉ mục cần cơ chế phía Spring Data.

### 10.1. Keyspace notifications và RedisKeyExpiredEvent

Spring Data Redis Repository hỗ trợ lắng nghe sự kiện hết hạn Redis key để thực hiện công việc liên quan tới vòng đời entity và chỉ mục. Cơ chế này dựa trên Redis keyspace notifications/Redis Pub/Sub cùng listener của Spring Data Redis.

Có thể chủ động khai báo việc bật listener khi dùng cấu hình repository thủ công:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter.EnableKeyspaceEvents;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
        basePackages = "com.example.delivery.redis",
        enableKeyspaceEvents = EnableKeyspaceEvents.ON_STARTUP
)
public class RedisRepositoryConfiguration {
}
```

Đây là ví dụ khi **chủ động cấu hình** repository; không nên thêm cấu hình trùng lặp nếu dự án Spring Boot đã có cách đăng ký repository riêng. Một số môi trường Redis được quản lý không cho ứng dụng thay đổi `notify-keyspace-events`; khi đó cần cấu hình notification theo khả năng hạ tầng và xác nhận listener có thực sự nhận sự kiện.

### 10.2. Vì sao có thể tồn tại chỉ mục lỗi thời sau TTL?

Redis Pub/Sub không phải hàng đợi bền vững. Nếu ứng dụng ngừng chạy, listener chưa bật, mất kết nối hoặc Redis key hết hạn vào thời điểm không có subscriber, sự kiện hết hạn có thể **không được xử lý** bởi Spring Data Redis.

Hậu quả có thể là:

```text
Hash demo:temporary-delivery:temp-1  -> đã hết hạn
Index status=PENDING                  -> còn tham chiếu temp-1
```

Như vậy, việc có TTL cho key chính không bảo đảm rằng mọi khóa chỉ mục phụ trợ cũng được dọn ngay và đầy đủ trong mọi tình huống.

### 10.3. Shadow copy và ảnh hưởng tới bộ nhớ

Khi tính năng hỗ trợ sự kiện hết hạn được bật, Spring Data Redis có thể tạo thêm một **shadow copy** (bản sao tạm của dữ liệu entity) để cung cấp thông tin thực thể trong sự kiện expire sau khi key chính đã mất. Việc này có chi phí bộ nhớ và thời gian sống riêng.

Nếu ứng dụng không cần nội dung entity trong sự kiện hết hạn, có thể cân nhắc cấu hình `shadowCopy = OFF` theo khả năng và yêu cầu của phiên bản Spring Data Redis đang sử dụng. Tuy nhiên, tắt bản sao làm giảm thông tin có trong sự kiện; phải đánh giá cả nhu cầu xử lý expiration và cơ chế dọn chỉ mục.

**Không lấy sự kiện hết hạn làm cơ chế duy nhất cho nghiệp vụ bắt buộc xử lý chính xác một lần.** Các yêu cầu đó thường cần job có trạng thái bền vững hoặc hàng đợi thích hợp.

## 11. Điều gì xảy ra khi có nhiều tiến trình cập nhật cùng lúc?

Giả sử hai worker cùng tải entity:

```text
Trạng thái ban đầu: status=PENDING, warehouse=HCM

Worker A đọc entity.
Worker B đọc entity.

Worker A đổi status=SHIPPED và save.
Worker B đổi description=Đã xác minh và save.
```

Nếu Worker B lưu lại **toàn bộ entity cũ** sau Worker A, dữ liệu từ bản đọc cũ có thể ghi đè `status` mới. Khi đó repository có thể cập nhật index theo bản ghi mà nó vừa lưu, nhưng trạng thái cuối lại không phải ý định của Worker A.

Điểm quan trọng: **chỉ mục nhất quán với trạng thái được lưu không đồng nghĩa với việc cập nhật nghiệp vụ không bị mất**.

Ngoài ra, nếu một thao tác lưu/xóa phải tác động đến nhiều Redis key, việc có lỗi mạng hoặc lỗi giữa chừng có thể khiến dữ liệu chính và dữ liệu chỉ mục tạm thời lệch nhau. Không nên coi `save` kết hợp nhiều chỉ mục là một transaction nguyên tử toàn bộ chỉ nhờ API của `CrudRepository`.

Một số cách giảm rủi ro:

- Với thao tác có nhiều bên ghi, xác định rõ quy tắc sở hữu entity và trình tự ghi.
- Khi cần kiểm soát cập nhật đồng thời, đánh giá giải pháp optimistic locking/version, so sánh điều kiện hoặc thao tác Redis nguyên tử theo thiết kế riêng; không tự giả định một annotation của JPA có cùng tác dụng trong Redis Repository.
- Khi trạng thái chỉ là cache dẫn xuất, có thể cho phép xây dựng lại entity/index từ nguồn dữ liệu chuẩn.
- Với nghiệp vụ cần giao dịch nhiều thực thể, cân nhắc công nghệ lưu trữ phù hợp với yêu cầu nhất quán.

### Redis Cluster làm thay đổi điều gì?

Trong Redis Cluster, key có thể nằm ở nhiều hash slot. Khóa entity và các khóa index/metadata có thể rơi vào slot khác nhau. Những thao tác liên quan nhiều key hoặc cần lệnh đa key vì thế chịu các giới hạn của topology cluster.

Cần xác nhận phiên bản Spring Data Redis, Redis driver và chiến lược keyspace/index có phù hợp Redis Cluster đang sử dụng hay không. Không giả định repository update/delete tất cả index theo một lệnh đa key nguyên tử trên toàn cluster.

## 12. Cách phát hiện chỉ mục tồn đọng hoặc sai lệch

Một secondary index có thể bị sai theo hai chiều:

1. **Tham chiếu thừa:** index còn chứa một ID nhưng entity tương ứng đã bị xóa, hết hạn hoặc đổi giá trị.
2. **Tham chiếu thiếu:** entity có giá trị thuộc nhóm nhưng ID chưa được thêm vào index, ví dụ dữ liệu được ghi bằng lệnh thô mà không đi qua repository.

Bảng ví dụ:

| Dữ liệu chính | Chỉ mục | Hệ quả |
|---|---|---|
| `status=SHIPPED` | Còn ở `PENDING` | Truy vấn nhóm cũ có thể nhận tham chiếu lỗi thời |
| `status=SHIPPED` | Thiếu ở `SHIPPED` | Truy vấn nhóm mới có thể bỏ sót entity |
| Hash đã bị xóa | Index còn ID | Index tiêu tốn bộ nhớ và chứa tham chiếu không còn hợp lệ |
| Hash vẫn tồn tại | Index bị xóa thủ công | Truy vấn theo index có thể không thấy entity dù `findById` vẫn thấy |

### Quan sát ở môi trường phát triển

Sau khi lưu entity có ID `delivery-101`:

```redis
TYPE demo:delivery:delivery-101
HGETALL demo:delivery:delivery-101
```

Tìm các khóa liên quan tới keyspace trong dữ liệu thử nghiệm:

```redis
SCAN 0 MATCH demo:delivery:* COUNT 100
```

Tiếp tục `SCAN` bằng cursor trả về cho tới khi cursor trở về `0`. `COUNT` chỉ là gợi ý lượng quét từng lượt, không phải giới hạn tổng kết quả. Tên khóa index thực tế và metadata nội bộ phụ thuộc vào Spring Data Redis; trước khi kiểm tra bằng `SMEMBERS` hoặc `SSCAN`, cần xác định chính xác **key nào thật sự là Redis Set của index**.

Không dùng `KEYS demo:delivery:*` trên Redis production có số lượng key lớn, và không tự gọi `SREM` trên những khóa index nội bộ khi chưa nắm đầy đủ thông tin phụ trợ mà repository đang quản lý.

### Đối chiếu kết quả qua repository

Dùng hai đường đọc trong lúc điều tra:

```java
Optional<DeliverySnapshot> byId =
        repository.findById("delivery-101");

List<DeliverySnapshot> byStatus =
        repository.findByStatus("SHIPPED");
```

So sánh trạng thái entity lấy theo ID với sự có mặt của nó trong kết quả query theo status. Khi quan sát sai lệch, kiểm tra trước những nguồn ghi/xóa ngoài repository, thời điểm TTL hết hạn, listener và lỗi trong thao tác ghi.

Không suy luận rằng một kết quả truy vấn rỗng đồng nghĩa với “không còn Redis key”; thiếu secondary index cũng có thể khiến kết quả rỗng dù entity vẫn tồn tại.

## 13. Phòng ngừa và khôi phục khi chỉ mục không nhất quán

### 13.1. Ngăn nguồn gây sai lệch

Đối với một keyspace do Redis Repository quản lý:

1. Chỉ định một đường **ghi, cập nhật và xóa** chính thống.
2. Dùng `repository.save` khi thay đổi thuộc tính có chỉ mục; dùng `repository.deleteById` hoặc `delete` khi xóa entity.
3. Tránh thao tác thô trên hash, set chỉ mục và metadata của repository từ service khác.
4. Định nghĩa chính sách TTL và cấu hình listener phù hợp với Redis thực tế.
5. Khi cần chỉ mục cho dữ liệu cũ, chuẩn bị quy trình migration/chuyển đổi thay vì chỉ thêm `@Indexed` vào class rồi cho rằng toàn bộ bản ghi lịch sử được lập chỉ mục ngay.

### 13.2. Khi dữ liệu đã sai lệch

Việc sửa chữa phải bắt đầu bằng **xác định nguồn dữ liệu đáng tin cậy**. Ví dụ, nếu Redis chỉ là cache của cơ sở dữ liệu chính, có thể xóa và xây dựng lại một phần cache qua đường ghi repository chuẩn.

Nếu Redis là nguồn dữ liệu duy nhất, phải thận trọng hơn:

- Sao lưu hoặc chụp dữ liệu cần thiết trước khi dọn cấu trúc phụ trợ.
- Xác định phạm vi namespace và các ID thực sự có dữ liệu.
- Đối chiếu trạng thái entity với các quan hệ chỉ mục liên quan.
- Xây dựng lại thông qua đường mapping được hỗ trợ; chạy theo lô nhỏ và quan sát tác động.
- Tránh các câu lệnh xóa toàn database hoặc xóa hàng loạt index khi chưa xác định đầy đủ mối liên hệ giữa entity, keyspace và dữ liệu phụ trợ.

Không có một lệnh Redis duy nhất “sửa tất cả các secondary index của mọi repository” theo kiểu cơ sở dữ liệu quan hệ. Giải pháp khôi phục phụ thuộc cấu trúc entity, phương thức truy vấn, phiên bản thư viện và nguồn dữ liệu có thể phục hồi.

### 13.3. Không nhầm chỉ mục với nguồn sự thật

Secondary index là **cấu trúc dẫn xuất hỗ trợ tìm kiếm**. Nếu index nói rằng ID thuộc nhóm `PENDING`, điều đó không thay thế được việc xác nhận dữ liệu chính còn tồn tại và có trạng thái đúng, nhất là trong môi trường ghi đồng thời hoặc từng có thao tác bypass repository.

Trong các quy trình quan trọng, có thể cần đọc entity hiện tại và xác nhận các điều kiện nghiệp vụ trước khi thực hiện hành động tiếp theo.

## 14. Các tình huống đặc biệt cần phân biệt

| Tình huống | Điều gì cần chú ý? |
|---|---|
| Thêm `@Indexed` sau khi dữ liệu đã tồn tại | Các entity cũ có thể chưa có quan hệ index tương ứng; cần kế hoạch tái tạo/migration |
| Đổi tên thuộc tính đã lập chỉ mục | Mapping/index cũ có thể không còn phù hợp; cần quản lý dữ liệu phiên bản cũ |
| Đổi tên keyspace của `@RedisHash` | Tạo vùng key mới; dữ liệu và index cũ không tự chuyển theo |
| Chỉ đổi field không lập chỉ mục | Kết quả phân nhóm index không thay đổi về logic |
| Đổi một field `@Indexed` sang giá trị khác | Phải gỡ liên kết cũ và ghi liên kết mới |
| Đặt field đã lập chỉ mục về `null` | Quan hệ của giá trị cũ không nên còn tồn tại |
| Xóa bằng repository | Repository quản lý cả dữ liệu chính và cấu trúc index của nó |
| Xóa hash bằng Redis CLI hoặc template | Có thể để lại index/metadata của repository |
| Redis làm key hết hạn vì TTL | Cần listener expiration phù hợp để xử lý dọn chỉ mục; sự kiện có thể bị bỏ lỡ |
| Hai worker lưu hai phiên bản cũ/mới | Có nguy cơ lost update, trạng thái index cuối phụ thuộc giá trị đã được lưu |
| Redis Cluster | Phải xem giới hạn thao tác đa key trên các hash slot và cấu hình repository thực tế |

## 15. Câu hỏi luyện tập và cách suy luận

**Tình huống 1:** Có một entity `status=PENDING`, `warehouse=HCM`. Ứng dụng đổi `status` thành `SHIPPED` và gọi `repository.save`.

Suy luận: Dữ liệu chính phản ánh `SHIPPED`; liên kết với index `PENDING` phải bị gỡ và liên kết với `SHIPPED` phải được tạo. Nhóm `warehouse=HCM` vẫn giữ entity vì field `warehouse` không thay đổi.

**Tình huống 2:** Ứng dụng xóa key chính qua `StringRedisTemplate.delete(key)` rồi gọi `findByStatus("SHIPPED")`.

Suy luận: Key chính có thể đã biến mất, nhưng việc xóa trực tiếp không cập nhật các quan hệ index theo quy trình repository. Cần kiểm tra khả năng còn tham chiếu thừa thay vì coi xóa key chính đã dọn mọi dữ liệu liên quan.

**Tình huống 3:** Entity có TTL 10 phút. Trong 10 phút đó, service quản lý repository ngừng hoạt động; khi khởi động lại, truy vấn theo thuộc tính có kết quả khác mong đợi.

Suy luận: Redis có thể đã làm key chính hết hạn trong khi listener không nhận được sự kiện để dọn chỉ mục. Cần xác định cấu hình keyspace notifications, trạng thái listener và quy trình sửa chữa index, không chỉ kiểm tra annotation TTL.

**Tình huống 4:** Thêm `@Indexed` cho thuộc tính `priority` vào entity đã lưu hàng triệu bản ghi từ trước.

Suy luận: Các bản ghi đã lưu không tự động được bảo đảm có index mới chỉ vì class Java được sửa. Cần kế hoạch cập nhật lại hoặc xây dựng index từ nguồn dữ liệu đáng tin cậy, thực hiện theo lô và có giới hạn tải.

**Tình huống 5:** Hai tiến trình đồng thời đọc và lưu entity. Chỉ mục cuối cùng phản ánh đúng bản ghi mà tiến trình sau lưu, nhưng thay đổi của tiến trình trước bị mất.

Suy luận: Đồng bộ index và kiểm soát lost update là hai vấn đề khác nhau. Phải thiết kế kiểm soát ghi đồng thời ở tầng nghiệp vụ, không suy ra có bảo đảm giao dịch chỉ từ việc dùng repository.

## 16. Kết luận

Khi khai báo `@Indexed` trên thực thể Redis, Spring Data Redis Repository quản lý thêm các cấu trúc phục vụ truy vấn theo thuộc tính. Vì vậy:

- **Thêm entity** cần tạo dữ liệu chính và quan hệ index.
- **Sửa giá trị đã lập chỉ mục** cần chuyển liên kết từ giá trị cũ sang giá trị mới.
- **Sửa field không lập chỉ mục** không đổi tư cách thành viên index về mặt logic.
- **Xóa qua repository** cần dọn dữ liệu chính cùng các liên kết chỉ mục mà repository quản lý.
- **Sửa/xóa bằng lệnh Redis thô** có thể làm dữ liệu chính và index sai lệch.
- **Hết TTL, ghi đồng thời và lỗi giữa chừng** là các tình huống cần thiết kế và giám sát riêng.

Quy tắc thực hành quan trọng là **giữ thao tác ghi/xóa đi qua cùng một cơ chế quản lý entity và index**, kiểm soát vòng đời TTL, đồng thời phân biệt tính đúng đắn của chỉ mục với tính nhất quán nghiệp vụ khi có nhiều bên ghi.

### Tài liệu tham khảo

- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis — Queries and Query Methods](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/queries.html)
- [Spring Data Commons — CrudRepository](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html)
- [Redis — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)

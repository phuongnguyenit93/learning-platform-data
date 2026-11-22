# Đọc và thay đổi cấu hình bằng `incrementalAlterConfigs`

## Quản trị cấu hình Kafka bằng Java Admin API

Kafka cung cấp `AdminClient` để ứng dụng quản trị cluster mà không cần chạy lệnh CLI thủ công. Với Admin API, ứng dụng có thể đọc cấu hình của topic hoặc broker, thay đổi cấu hình khi cần, kiểm tra kết quả và tự động hóa quy trình vận hành.

Một thao tác quản trị thường gồm hai bước:

1. Dùng `describeConfigs()` để đọc cấu hình hiện tại của một `ConfigResource`.
2. Dùng `incrementalAlterConfigs()` để áp dụng một hoặc nhiều thay đổi có chủ đích.

`incrementalAlterConfigs()` hỗ trợ các thao tác `SET`, `DELETE`, `APPEND` và `SUBTRACT`. Điểm quan trọng là API này chỉ thay đổi các key được chỉ định; những cấu hình khác của resource được giữ nguyên. Điều này giúp giảm rủi ro khi tự động hóa quản trị topic/broker trong hệ thống KAFKA.

## 1. AdminClient và ConfigResource

### 1.1 Tạo AdminClient

`AdminClient` là client quản trị Kafka. Nó kết nối đến cluster thông qua `bootstrap.servers`, lấy metadata cần thiết rồi gửi các request quản trị đến broker phù hợp.

```java
Properties props = new Properties();
props.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");

try (AdminClient admin = AdminClient.create(props)) {
    // Thực hiện các thao tác quản trị tại đây.
}
```

Trong production, cấu hình thêm SASL/TLS, truststore/keystore, timeout và các thuộc tính bảo mật theo cluster. Không nhúng username/password hoặc private key trực tiếp vào source code; dùng secret manager hoặc cơ chế cấp credential phù hợp.

`AdminClient` hỗ trợ gọi bất đồng bộ và thread-safe. Các phương thức quản trị thường trả về một result chứa `KafkaFuture`; ứng dụng quyết định chờ kết quả bằng `get()`, kết hợp nhiều future hoặc xử lý theo callback. Luôn đóng client khi hoàn tất để giải phóng network connection và thread.

### 1.2 ConfigResource xác định đối tượng cần quản trị

`ConfigResource` xác định loại resource và tên resource. Một số loại thường dùng:

| Resource type | Tên resource | Ví dụ |
|---|---|---|
| `TOPIC` | Tên topic | `orders` |
| `BROKER` | Broker ID dạng chuỗi | `1` |
| `BROKER_LOGGER` | Broker ID | `1` |

Ví dụ tạo resource cho topic:

```java
ConfigResource topic = new ConfigResource(
        ConfigResource.Type.TOPIC,
        "orders"
);
```

Khi thao tác broker config, phải xác định đúng phạm vi cấu hình: dynamic config áp dụng cho một broker, cấu hình mặc định cho broker hoặc cấu hình logger. Cách biểu diễn resource và quyền cần có phụ thuộc loại cấu hình cùng phiên bản Kafka; không dùng một `ConfigResource` của topic cho cấu hình broker.

## 2. Đọc cấu hình bằng `describeConfigs()`

### 2.1 Lấy cấu hình hiện tại của topic

`describeConfigs()` trả về cấu hình của resource. Với topic, kết quả bao gồm các config entry mà broker công bố, chẳng hạn `cleanup.policy`, `retention.ms`, `min.insync.replicas`.

```java
ConfigResource resource = new ConfigResource(
        ConfigResource.Type.TOPIC,
        "orders"
);

DescribeConfigsResult result = admin.describeConfigs(List.of(resource));
Config config = result.all().get().get(resource);

for (ConfigEntry entry : config.entries()) {
    String value = entry.isSensitive() ? "<redacted>" : entry.value();
    System.out.printf("%s=%s, source=%s, readOnly=%s%n",
            entry.name(), value, entry.source(), entry.isReadOnly());
}
```

Đoạn code chỉ in giá trị không nhạy cảm. Một số config nhạy cảm có thể được broker đánh dấu `isSensitive()` và không trả giá trị thực; không cố đọc hoặc ghi giá trị bí mật vào log.

### 2.2 Hiểu nguồn của cấu hình

Một giá trị cấu hình có thể đến từ override riêng của topic/broker hoặc được kế thừa từ mặc định. `ConfigEntry.source()` giúp nhận diện nguồn, ví dụ:

- `DYNAMIC_TOPIC_CONFIG`: cấu hình động được đặt riêng cho topic.
- `DYNAMIC_BROKER_CONFIG`: cấu hình động được đặt riêng cho broker.
- `DYNAMIC_DEFAULT_BROKER_CONFIG`: cấu hình mặc định động áp dụng cho broker.
- `STATIC_BROKER_CONFIG`: cấu hình broker đến từ file cấu hình tĩnh.
- `DEFAULT_CONFIG`: giá trị mặc định của Kafka.

Các giá trị source cụ thể và cách thể hiện có thể thay đổi theo phiên bản Kafka. Khi cần giải thích vì sao một giá trị có hiệu lực, xem cả source và synonyms của entry nếu API phiên bản đang dùng cung cấp chúng. Đừng suy ra một giá trị là override riêng chỉ vì nó xuất hiện trong danh sách cấu hình.

### 2.3 Đọc cấu hình không đồng nghĩa mọi key đều có thể thay đổi

`describeConfigs()` cho biết cấu hình và metadata của entry, nhưng không bảo đảm mọi key đều có thể cập nhật động. Một số broker config chỉ đọc, một số cần restart, một số cho phép cập nhật động theo broker hoặc toàn cluster.

Trước khi thay đổi broker config, kiểm tra tài liệu cấu hình của đúng phiên bản Kafka để biết update mode. Với topic config, phần lớn cấu hình vận hành thông thường có thể cập nhật động, nhưng vẫn cần xem giới hạn và tác động của từng key.

## 3. Vì sao dùng `incrementalAlterConfigs`?

### 3.1 Khác biệt với `alterConfigs()` cũ

API `alterConfigs()` kiểu cũ thay thế cấu hình của resource theo tập cấu hình gửi lên. Nếu ứng dụng chỉ gửi một key trong khi các key khác đang có override, có nguy cơ xóa/reset những override không được gửi kèm.

`incrementalAlterConfigs()` áp dụng thay đổi theo từng key và operation. Các key không xuất hiện trong request giữ nguyên giá trị hiện tại.

Incremental AlterConfigs được bổ sung trong Kafka 2.3. Khi triển khai, hãy xác nhận broker và Java client đang dùng hỗ trợ API này; nếu môi trường có nhiều phiên bản broker, kiểm tra compatibility theo broker đích trước khi rollout công cụ quản trị.

| API | Hành vi |
|---|---|
| `alterConfigs()` | Thay thế cấu hình resource theo tập entry được gửi; entry bị bỏ khỏi request có thể bị reset |
| `incrementalAlterConfigs()` | Áp dụng operation trên các key được chỉ định; key khác không bị thay đổi |

Khi chỉ muốn thay đổi `retention.ms` mà giữ nguyên `cleanup.policy`, `min.insync.replicas` và các override khác, incremental API thể hiện ý định rõ ràng hơn.

### 3.2 Bốn operation chính

`AlterConfigOp` kết hợp một `ConfigEntry` với operation type:

| Operation | Ý nghĩa | Trường hợp sử dụng |
|---|---|---|
| `SET` | Đặt giá trị mới cho key | Đặt `retention.ms=604800000` |
| `DELETE` | Xóa override của key để resource quay về giá trị kế thừa/mặc định | Bỏ override `retention.ms` của topic |
| `APPEND` | Thêm giá trị vào cấu hình dạng danh sách | Thêm `compact` vào `cleanup.policy` |
| `SUBTRACT` | Loại giá trị khỏi cấu hình dạng danh sách | Bỏ `delete` khỏi `cleanup.policy` |

`APPEND` và `SUBTRACT` dành cho cấu hình kiểu list. Không dùng chúng cho một giá trị scalar như `retention.ms`. `SET` trên cấu hình list thay thế giá trị danh sách; `APPEND`/`SUBTRACT` thay đổi các phần tử được chỉ định.

`DELETE` không có nghĩa đặt chuỗi rỗng. Nó xóa override tương ứng để Kafka dùng giá trị kế thừa hoặc mặc định theo phạm vi cấu hình.

## 4. Thay đổi topic config bằng `incrementalAlterConfigs`

### 4.1 Tạo operation `SET`

Ví dụ đặt `min.insync.replicas` thành 2 và `retention.ms` thành 7 ngày:

```java
ConfigResource topic = new ConfigResource(
        ConfigResource.Type.TOPIC,
        "orders"
);

List<AlterConfigOp> operations = List.of(
        new AlterConfigOp(
                new ConfigEntry("min.insync.replicas", "2"),
                AlterConfigOp.OpType.SET
        ),
        new AlterConfigOp(
                new ConfigEntry("retention.ms", "604800000"),
                AlterConfigOp.OpType.SET
        )
);

Map<ConfigResource, Collection<AlterConfigOp>> changes = Map.of(
        topic, operations
);

AlterConfigsResult result = admin.incrementalAlterConfigs(changes);
result.values().get(topic).get();
```

Giá trị config được truyền dưới dạng chuỗi. Broker xác thực kiểu và miền giá trị theo định nghĩa của config. Nếu key không tồn tại hoặc giá trị không hợp lệ, future tương ứng sẽ hoàn tất với lỗi.

### 4.2 Thêm một phần tử bằng `APPEND`

Giả sử `cleanup.policy` hiện tại là `delete` và muốn bật thêm compaction. Có thể append `compact`:

```java
AlterConfigOp appendCompact = new AlterConfigOp(
        new ConfigEntry("cleanup.policy", "compact"),
        AlterConfigOp.OpType.APPEND
);

admin.incrementalAlterConfigs(Map.of(topic, List.of(appendCompact)))
        .values().get(topic).get();
```

Kết quả mong muốn là cấu hình chứa cả `delete` và `compact`, tức `cleanup.policy=delete,compact`. Đây là thay đổi danh sách, không phải thay thế toàn bộ bằng `compact`.

Trước khi append, nên đọc cấu hình hiện tại để xác định phần tử đã tồn tại chưa. Điều này đặc biệt quan trọng khi retry request sau timeout hoặc khi nhiều quy trình quản trị có thể cùng sửa một key.

### 4.3 Loại phần tử bằng `SUBTRACT`

Nếu muốn bỏ `delete` nhưng giữ `compact`:

```java
AlterConfigOp subtractDelete = new AlterConfigOp(
        new ConfigEntry("cleanup.policy", "delete"),
        AlterConfigOp.OpType.SUBTRACT
);

admin.incrementalAlterConfigs(Map.of(topic, List.of(subtractDelete)))
        .values().get(topic).get();
```

Sau thao tác, `cleanup.policy` còn `compact`. Hãy kiểm tra ý nghĩa của policy sau khi thay đổi: topic chỉ compact không còn hành vi xóa theo thời gian/dung lượng như `delete`.

### 4.4 Xóa override bằng `DELETE`

Nếu topic đang có override riêng `retention.ms` và muốn quay về giá trị kế thừa:

```java
AlterConfigOp deleteRetentionOverride = new AlterConfigOp(
        new ConfigEntry("retention.ms", null),
        AlterConfigOp.OpType.DELETE
);

admin.incrementalAlterConfigs(
        Map.of(topic, List.of(deleteRetentionOverride))
).values().get(topic).get();
```

Với operation `DELETE`, giá trị trong `ConfigEntry` không được dùng như giá trị mới; `null` thể hiện không có giá trị cần đặt. Không dùng `SET` với chuỗi rỗng để thay cho DELETE.

## 5. Validate trước khi áp dụng

`AlterConfigsOptions` hỗ trợ `validateOnly(true)` trên các phiên bản API tương ứng. Chế độ này yêu cầu broker kiểm tra request nhưng không lưu thay đổi.

```java
AlterConfigsOptions validateOptions = new AlterConfigsOptions()
        .validateOnly(true)
        .timeoutMs(10_000);

AlterConfigsResult validation = admin.incrementalAlterConfigs(
        changes,
        validateOptions
);

validation.values().get(topic).get();
```

Nếu validation thành công, có thể gửi request thật với `validateOnly(false)` hoặc options mặc định. Validate-only không giữ khóa hay reservation trên cấu hình; trạng thái resource có thể thay đổi giữa lúc validate và lúc apply. Vì vậy, vẫn cần xử lý lỗi ở request thật và đọc lại sau khi cập nhật.

## 6. Thay đổi nhiều resource và xử lý kết quả bất đồng bộ

### 6.1 Một request có thể chứa nhiều resource

Admin API nhận map từ `ConfigResource` đến danh sách operation. Ví dụ có thể thay đổi cấu hình của hai topic trong cùng request:

```java
ConfigResource orders = new ConfigResource(
        ConfigResource.Type.TOPIC, "orders");
ConfigResource payments = new ConfigResource(
        ConfigResource.Type.TOPIC, "payments");

Map<ConfigResource, Collection<AlterConfigOp>> changes = new HashMap<>();
changes.put(orders, List.of(
        new AlterConfigOp(new ConfigEntry("retention.ms", "604800000"),
                AlterConfigOp.OpType.SET)
));
changes.put(payments, List.of(
        new AlterConfigOp(new ConfigEntry("retention.ms", "1209600000"),
                AlterConfigOp.OpType.SET)
));

AlterConfigsResult result = admin.incrementalAlterConfigs(changes);
```

Kết quả được trả theo từng resource. Không giả định một request nhiều resource là transaction nguyên tử: một resource có thể thành công trong khi resource khác thất bại.

### 6.2 Kiểm tra từng future

Có thể chờ từng resource để biết kết quả cụ thể:

```java
for (Map.Entry<ConfigResource, KafkaFuture<Void>> entry
        : result.values().entrySet()) {
    ConfigResource resource = entry.getKey();
    try {
        entry.getValue().get();
        System.out.println("Updated: " + resource);
    } catch (ExecutionException exception) {
        Throwable cause = exception.getCause();
        System.err.println("Failed: " + resource + " - " + cause);
    }
}
```

Trong production, xử lý thêm `InterruptedException`, timeout và cancellation. Khi thread bị interrupt, khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` trước khi trả quyền điều khiển.

### 6.3 Timeout không đồng nghĩa chắc chắn chưa cập nhật

Nếu client timeout hoặc mất kết nối khi chờ future, broker có thể đã áp dụng cấu hình nhưng phản hồi không đến client. Không gửi lại `APPEND` hoặc `SUBTRACT` ngay mà chưa đọc trạng thái hiện tại.

Quy trình an toàn:

1. Ghi nhận resource, key, operation và request correlation ID.
2. Khi kết nối ổn định, gọi `describeConfigs()` để đọc trạng thái thực tế.
3. So sánh giá trị hiện tại với trạng thái mong muốn.
4. Chỉ gửi operation còn thiếu; tránh append trùng hoặc xóa nhầm phần tử.
5. Ghi lại kết quả và nguồn thay đổi.

`SET` đến một giá trị cố định thường dễ lặp lại hơn `APPEND`/`SUBTRACT`, nhưng vẫn cần xác minh vì cấu hình có thể bị một operator khác thay đổi đồng thời.

## 7. Đọc lại và xác minh sau khi thay đổi

Sau khi future báo thành công, gọi `describeConfigs()` để kiểm tra giá trị có hiệu lực:

```java
DescribeConfigsResult described = admin.describeConfigs(List.of(topic));
Config updated = described.all().get().get(topic);

for (ConfigEntry entry : updated.entries()) {
    if (Set.of("retention.ms", "min.insync.replicas", "cleanup.policy")
            .contains(entry.name())) {
        System.out.printf("%s=%s (source=%s)%n",
                entry.name(),
                entry.isSensitive() ? "<redacted>" : entry.value(),
                entry.source());
    }
}
```

Xác minh cả giá trị và source. Ví dụ, sau `DELETE`, giá trị có thể trở về mặc định broker; nếu chỉ so sánh chuỗi mà không xem source, ứng dụng có thể nhầm rằng override vẫn còn.

Với broker config, một số thay đổi động có thể có hiệu lực ngay, một số thay đổi chỉ có hiệu lực sau restart hoặc bị giới hạn theo update mode. Đọc lại cấu hình xác nhận metadata đã được lưu; không tự chứng minh rằng mọi thành phần runtime đã áp dụng thay đổi. Cần kiểm tra tài liệu update mode và metric/runtime behavior của broker.

## 8. Thay đổi cấu hình broker

`incrementalAlterConfigs()` có thể quản lý dynamic broker config nếu config đó cho phép cập nhật động và broker hỗ trợ operation tương ứng. Resource thường dùng `ConfigResource.Type.BROKER` với broker ID.

Ví dụ về cách biểu diễn resource broker:

```java
ConfigResource broker = new ConfigResource(
        ConfigResource.Type.BROKER,
        "1"
);
```

Sau đó tạo operation và gửi qua `incrementalAlterConfigs()` như với topic. Tuy nhiên, phải kiểm tra config cụ thể có update mode phù hợp, có cho phép thay đổi ở cấp broker hay cluster-wide, và có yêu cầu restart không.

Không dùng Admin API để cố thay đổi config tĩnh chỉ đọc hoặc config không hỗ trợ dynamic update. Những cấu hình đó cần quy trình chỉnh sửa file/broker deployment và restart có kiểm soát.

## 9. Bảo mật và quyền ACL

Admin API chịu sự kiểm soát của Kafka authorization. Thông thường:

- Đọc cấu hình resource cần quyền `DESCRIBE_CONFIGS` trên resource tương ứng.
- Thay đổi cấu hình cần quyền `ALTER_CONFIGS` trên resource tương ứng.
- Kết nối và xác thực còn phụ thuộc listener, SASL/TLS và cấu hình authorizer của cluster.

Quyền thực tế phụ thuộc loại resource và cấu hình bảo mật. Hãy cấp quyền tối thiểu cho service quản trị: chỉ các topic/broker mà nó cần thao tác, tránh dùng credential superuser trong ứng dụng nghiệp vụ.

Không ghi giá trị nhạy cảm, JAAS config, password hoặc certificate material vào log. Khi log operation, chỉ ghi resource, key, loại operation và kết quả; che giá trị nếu config có thể chứa secret.

## 10. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng `alterConfigs()` để sửa một key | Có thể reset các override khác không gửi kèm | Dùng `incrementalAlterConfigs()` cho thay đổi từng phần |
| Dùng `SET` cho list khi chỉ muốn thêm một phần tử | Thay thế toàn bộ danh sách | Dùng `APPEND` |
| Dùng `APPEND` cho scalar config | Request không hợp lệ | Dùng `SET` cho giá trị scalar |
| Dùng chuỗi rỗng thay cho `DELETE` | Tạo giá trị không hợp lệ hoặc không đúng ý định | Dùng `AlterConfigOp.OpType.DELETE` |
| Retry `APPEND` sau timeout mà không đọc lại | Có thể thêm phần tử trùng hoặc áp dụng sai trạng thái | `describeConfigs()` rồi so sánh trước khi retry |
| Nghĩ request nhiều resource là atomic | Một phần thành công, phần khác thất bại | Kiểm tra future theo từng resource và xử lý bù |
| Thay đổi broker config không kiểm tra update mode | Giá trị lưu nhưng runtime chưa áp dụng hoặc cần restart | Kiểm tra config documentation và runtime state |
| Thiếu ACL | Nhận `ClusterAuthorizationException` hoặc `TopicAuthorizationException` | Cấp `ALTER_CONFIGS`/`DESCRIBE_CONFIGS` đúng resource |
| Không đọc lại sau update | Không phát hiện cấu hình không như mong đợi | Describe và xác minh value/source |
| Log toàn bộ config | Có thể lộ thông tin nhạy cảm | Kiểm tra `isSensitive()` và redact |

## 11. Quy trình quản trị cấu hình an toàn

Một quy trình có thể dùng trong công cụ vận hành nội bộ:

1. Xác thực cluster, environment và danh tính operator/service.
2. Xác định `ConfigResource` chính xác và kiểm tra resource tồn tại.
3. Đọc cấu hình hiện tại bằng `describeConfigs()`.
4. So sánh giá trị hiện tại với giá trị mục tiêu; không tạo operation nếu đã đúng.
5. Kiểm tra update mode, kiểu config, ACL và tác động vận hành.
6. Gửi request `validateOnly` nếu broker/client hỗ trợ và kiểm tra kết quả.
7. Áp dụng operation bằng `incrementalAlterConfigs()`.
8. Kiểm tra từng future, không giả định tất cả resource thành công cùng nhau.
9. Đọc lại cấu hình và xác minh value/source/runtime behavior.
10. Ghi audit event gồm actor, resource, key, operation, timestamp và kết quả.

Với thay đổi ảnh hưởng đến retention, replication hoặc durability như `retention.ms`, `cleanup.policy` và `min.insync.replicas`, hãy đánh giá tác động đến dung lượng, khả năng replay, availability và producer behavior trước khi áp dụng.

## 12. Checklist production

- `AdminClient` dùng TLS/SASL và credential được quản lý an toàn.
- Resource type/name được xác định chính xác.
- Có quyền `DESCRIBE_CONFIGS` và `ALTER_CONFIGS` tối thiểu cần thiết.
- Đã đọc cấu hình hiện tại và hiểu source/inheritance.
- Chọn đúng `SET`, `DELETE`, `APPEND` hoặc `SUBTRACT`.
- `APPEND`/`SUBTRACT` chỉ dùng với config dạng list.
- Validate-only được dùng khi phù hợp, nhưng vẫn kiểm tra request thật.
- Future được xử lý theo từng resource và có timeout rõ ràng.
- Khi timeout không rõ kết quả, describe trước khi retry.
- Đã xác minh config sau khi cập nhật và kiểm tra update mode của broker.
- Có audit log nhưng redact giá trị nhạy cảm.
- Có kế hoạch rollback hoặc operation ngược tương ứng.

## Kết luận

`describeConfigs()` đọc cấu hình hiện tại và metadata của resource; `incrementalAlterConfigs()` thay đổi có chủ đích theo từng key bằng `SET`, `DELETE`, `APPEND` hoặc `SUBTRACT`. Khác với API thay thế cấu hình cũ, incremental API giữ nguyên các key không được chỉ định, phù hợp cho công cụ quản trị topic và broker.

Khi dùng Admin API trong KAFKA, hãy xác định đúng resource, đọc source và update mode, chọn operation phù hợp với kiểu config, kiểm tra từng future và đọc lại sau khi thay đổi. Đặc biệt, timeout không chứng minh request chưa được áp dụng; hãy đối chiếu trạng thái trước khi retry. Kết hợp ACL tối thiểu, validate-only, audit log và redaction giúp tự động hóa quản trị cấu hình an toàn, có thể quan sát và phục hồi.
